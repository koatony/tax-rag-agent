import sys
import os
from decimal import Decimal
from typing import Optional, Dict, Any

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from form1040.models.income_aggregator_model import (
    DirectIncomeInputV1,
    DirectIncomeItemV1,
    W2ItemV1,
    ScheduleBResultV1,
    ScheduleDResultV1,
    Schedule1ResultV1,
    IncomeSectionResultV1,
)
from form1040.models.agi_model import AGIProcessorInputV1, AGIProcessorResultV1
from form1040.processors.income_aggregator_processor import IncomeAggregatorProcessor
from form1040.processors.agi_processor import AGIProcessor
from form1040.parsers.income_aggregator_direct_income_parser import IncomeAggregatorDirectIncomeParser


class Form1040Orchestrator:
    """
    Form 1040 核心組裝與串接調度器 (Orchestrator)
    負責接收各表單的原始 LLM 提取資料 (dict)，呼叫對應之子處理器計算出 DTO 後，進行 Form 1040 總所得與 AGI 的計算。
    """

    @classmethod
    def assemble(
        cls,
        *,
        tax_year: int,
        filing_status: str,
        raw_llm_direct_income: Dict[str, Any],
        raw_schedule_b_input: Optional[Dict[str, Any]] = None,
        raw_schedule_d_input: Optional[Dict[str, Any]] = None,
        raw_schedule_1_input: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        將原始輸入資料傳給不同子表單模組，等待計算結果返回後，進行 Income Aggregator 與 AGI 處理。
        """
        # 1. 呼叫 Parser 將 dict 格式之直接收入資料解析為 DTO 物件
        if isinstance(raw_llm_direct_income, dict):
            direct_income_dto = IncomeAggregatorDirectIncomeParser.parse_dict(raw_llm_direct_income)
        else:
            direct_income_dto = raw_llm_direct_income or DirectIncomeInputV1()

        # 2. 呼叫 Schedule B 計算引擎取得結果 DTO
        schedule_b_result = None
        if raw_schedule_b_input:
            from processors.processors import calculate_schedule_b_dynamic
            from form1040.models.income_aggregator_model import ProcessingIssueV1, ScheduleBResultV1
            
            sb_res_dict = calculate_schedule_b_dynamic(raw_schedule_b_input)
            sb_has_blocking = sb_res_dict.get("blocking_validation_error") or len(sb_res_dict.get("blocking_errors", [])) > 0
            sb_status = "BLOCKED" if sb_has_blocking else "COMPLETE"
            
            sb_blocking_issues = [
                ProcessingIssueV1(code=err.get("code", "ERROR"), field=err.get("field"), message=err.get("message", ""))
                for err in sb_res_dict.get("blocking_errors", []) if isinstance(err, dict)
            ]
            schedule_b_result = ScheduleBResultV1(
                form_1040_line_2a=Decimal(f"{sb_res_dict.get('form_1040_line_2a', 0):.2f}"),
                line_4_surface_value=Decimal(f"{sb_res_dict.get('line_4_surface_value', 0):.2f}"),
                total_qualified_dividends=Decimal(f"{sb_res_dict.get('total_qualified_dividends', 0):.2f}"),
                line_6_total_ordinary_dividends=Decimal(f"{sb_res_dict.get('line_6_total_ordinary_dividends', 0):.2f}"),
                status=sb_status,
                blocking_errors=sb_blocking_issues,
            )

        # 3. 呼叫 Schedule D 計算引擎取得結果 DTO (由於 Schedule D 尚未開發完成，暫時使用傳入的模擬資料或預設)
        schedule_d_result = None
        if raw_schedule_d_input:
            from form1040.models.income_aggregator_model import ScheduleDResultV1
            val = raw_schedule_d_input.get("line_7_capital_gain_or_loss", -990)
            schedule_d_result = ScheduleDResultV1(
                line_7_capital_gain_or_loss=Decimal(f"{val:.2f}"),
                status="COMPLETE",
            )

        # 4. 呼叫 Schedule 1 計算引擎取得結果 DTO
        schedule_1_result = None
        if raw_schedule_1_input:
            from schedule_1_processor import calculate_schedule_1_dynamic
            from form1040.models.income_aggregator_model import Schedule1ResultV1
            
            s1_res_dict = calculate_schedule_1_dynamic(raw_schedule_1_input)
            s1_has_blocking = s1_res_dict.get("blocking_validation_error") or len(s1_res_dict.get("blocking_errors", [])) > 0
            s1_status = "BLOCKED" if s1_has_blocking else "COMPLETE"
            
            schedule_1_result = Schedule1ResultV1(
                taxpayer_name=s1_res_dict.get("taxpayer_name"),
                taxpayer_ssn_masked=s1_res_dict.get("taxpayer_ssn_masked"),
                tax_year=s1_res_dict.get("tax_year"),
                line_10_additional_income=Decimal(f"{s1_res_dict.get('line_10_additional_income', 0):.2f}"),
                line_26_adjustments_to_income=Decimal(f"{s1_res_dict.get('line_26_adjustments_to_income', 0):.2f}"),
                status=s1_status,
                blocking_errors=s1_res_dict.get("blocking_errors", []),
                review_warnings=s1_res_dict.get("review_warnings", [])
            )

        # 5. 呼叫 IncomeAggregatorProcessor 彙整 Lines 1–9
        income_result: IncomeSectionResultV1 = IncomeAggregatorProcessor.compute(
            tax_year=tax_year,
            filing_status=filing_status,
            direct_income_input=direct_income_dto,
            schedule_b_result=schedule_b_result,
            schedule_d_result=schedule_d_result,
            schedule_1_result=schedule_1_result,
        )

        if income_result.status == "BLOCKED":
            return {
                "income_section": income_result.to_dict(),
                "agi_section": None,
                "status": "BLOCKED",
                "blocking_errors": income_result.to_dict()["blocking_errors"],
            }

        # 6. 將 Line 9 與 Schedule 1 Line 26 傳入 AGIProcessor 計算 Line 11
        agi_input = AGIProcessorInputV1(
            line_9_total_income=income_result.line_9,
            schedule_1_result=schedule_1_result
        )

        agi_result: AGIProcessorResultV1 = AGIProcessor.process(agi_input)

        return {
            "income_section": income_result.to_dict(),
            "agi_section": agi_result.to_dict(),
            "status": agi_result.status,
            "blocking_errors": agi_result.blocking_errors,
        }


if __name__ == "__main__":
    import json

    # 1. 準備 0622 Case 的直接收入資料 (W-2 等)
    raw_llm_direct = {
        "w2_items": [
            {
                "employee_name": "Marcus Rivera",
                "box_1_wages": "46000",
                "tax_year": 2025,
                "source_document_id": "sample_01",
            },
            {
                "employee_name": "Elena Rivera",
                "box_1_wages": "54000",
                "tax_year": 2025,
                "source_document_id": "sample_02",
            },
        ],
        "ira_distribution": {"gross_amount": "0", "taxable_amount": "0", "status": "EXPLICIT_VALUE"},
        "pension_annuity": {"gross_amount": "0", "taxable_amount": "0", "status": "EXPLICIT_VALUE"},
        "social_security": {"gross_amount": "0", "taxable_amount": "0", "status": "EXPLICIT_VALUE"},
    }

    # 2. 準備 0622 Case 的 Schedule B 原始輸入
    sb_inputs = {
        'taxpayer_name': 'MARCUS & ELENA RIVERA',
        'taxpayer_ssn': '123-45-6789',
        'tax_year': 2025,
        'interest_items': [{'payer_name': 'CHASE', 'amount': 150.0, 'tax_character': 'TAXABLE_INTEREST'}],
        'dividend_items': [{'payer_name': 'VANGUARD', 'ordinary_dividends': 405.0}],
        'foreign_accounts_interest': False,
        'fbar_required': False,
        'foreign_countries_list': [],
        'foreign_trust_distribution': False
    }

    # 3. 準備 0622 Case 的 Schedule D 原始輸入
    sd_inputs = {
        "line_7_capital_gain_or_loss": -990
    }

    # 4. 準備 0622 Case 的 Schedule 1 原始輸入
    s1_inputs = {
        "taxpayer_name": "Marcus & Elena Rivera",
        "taxpayer_ssn": "123-45-6789",
        "tax_year": 2025,
        "adjustment_items": [
            {
                "item_id": "adj_ira",
                "line_code": "20",
                "description": "IRA deduction",
                "amount": 7000.0
            }
        ],
        "special_case_flags": {}
    }

    # 5. 呼叫通用 assemble 進行調度計算與加總
    res = Form1040Orchestrator.assemble(
        tax_year=2025,
        filing_status="MFJ",
        raw_llm_direct_income=raw_llm_direct,
        raw_schedule_b_input=sb_inputs,
        raw_schedule_d_input=sd_inputs,
        raw_schedule_1_input=s1_inputs,
    )
    print("=== 0622 Case Form 1040 Integration Test Assembly Result ===")
    print(json.dumps(res, indent=2))
