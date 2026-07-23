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


class Form1040Orchestrator:
    """
    Form 1040 核心組裝與串接調度器 (Orchestrator)
    負責將 Direct Income、Schedule B、Schedule D、Schedule 1 結果組裝計算 Line 9 (Total Income) 隨後算得 Line 11 (AGI)。
    """

    @classmethod
    def assemble_0622_case(
        cls,
        raw_llm_direct_income: Optional[Dict[str, Any]] = None,
        schedule_b_result: Optional[ScheduleBResultV1] = None,
        schedule_d_result: Optional[ScheduleDResultV1] = None,
        schedule_1_result: Optional[Schedule1ResultV1] = None,
    ) -> Dict[str, Any]:
        tax_year = 2025
        filing_status = "MFJ"

        # 1. 預設 0622 Case 的 LLM 提取結果 (若外部未傳入)
        if raw_llm_direct_income is None:
            raw_llm_direct_income = {
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

        # 2. 預設 0622 Case 的上游 Schedule 輸出結果 (若外部未傳入)
        if schedule_b_result is None:
            schedule_b_result = ScheduleBResultV1(
                form_1040_line_2a=Decimal("0"),
                line_4_surface_value=Decimal("150"),        # Line 2b Taxable Interest
                total_qualified_dividends=Decimal("0"),
                line_6_total_ordinary_dividends=Decimal("405"), # Line 3b Ordinary Dividends
                status="COMPLETE",
            )

        if schedule_d_result is None:
            schedule_d_result = ScheduleDResultV1(
                line_7_capital_gain_or_loss=Decimal("-990"), # Line 7a Capital Loss
                status="COMPLETE",
            )

        if schedule_1_result is None:
            # 引入並呼叫真實的 Schedule 1 計算引擎
            from schedule_1_processor import calculate_schedule_1_dynamic
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
            s1_res_dict = calculate_schedule_1_dynamic(s1_inputs)
            
            # 計算 status (依據有無阻斷錯誤)
            s1_has_blocking = s1_res_dict.get("blocking_validation_error") or len(s1_res_dict.get("blocking_errors", [])) > 0
            s1_status = "BLOCKED" if s1_has_blocking else "COMPLETE"
            
            # 手動轉換型別以符合 Orchestrator 對 Schedule1ResultV1 的型別期望
            schedule_1_result = Schedule1ResultV1(
                taxpayer_name=s1_res_dict.get("taxpayer_name"),
                taxpayer_ssn_masked=s1_res_dict.get("taxpayer_ssn_masked"),
                tax_year=s1_res_dict.get("tax_year"),
                line_10_additional_income=Decimal(str(s1_res_dict.get("line_10_additional_income", 0))),
                line_26_adjustments_to_income=Decimal(str(s1_res_dict.get("line_26_adjustments_to_income", 0))),
                status=s1_status,
                blocking_errors=s1_res_dict.get("blocking_errors", []),
                review_warnings=s1_res_dict.get("review_warnings", [])
            )

        # 3. 步驟一：呼叫 IncomeAggregatorProcessor 彙整 Lines 1–9
        income_result: IncomeSectionResultV1 = IncomeAggregatorProcessor.compute(
            tax_year=tax_year,
            filing_status=filing_status,
            direct_income_input=raw_llm_direct_income,
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

        # 4. 步驟二：將 Line 9 與 Schedule 1 Line 26 傳入 AGIProcessor 計算 Line 11
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
    res = Form1040Orchestrator.assemble_0622_case()
    print("=== 0622 Case Form 1040 Integration Test Assembly Result ===")
    print(json.dumps(res, indent=2))
