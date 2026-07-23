from decimal import Decimal
import unittest

from form1040.orchestrator import Form1040Orchestrator
from form1040.models.income_aggregator_model import (
    ScheduleBResultV1,
    ScheduleDResultV1,
    Schedule1ResultV1,
)


class TestForm10400622Integration(unittest.TestCase):
    """
    Form 1040 Case 0622 完整端到端整合測試 (End-to-End Integration Test)
    模擬 LLM 讀取 0622 Word 憑證後提取出的 JSON Dict，經過完整 Pipeline
    (IncomeAggregatorDirectIncomeParser -> IncomeAggregatorValidator -> IncomeAggregatorCalculator -> AGIValidator -> AGICalculator)
    驗證最終 Form 1040 Line 9 與 Line 11 之精確結果。
    """

    def test_0622_full_pipeline(self):
        # 1. 模擬 LLM 從 0622 原始憑證 (Marcus & Elena Rivera W-2, IRA 等) 提取之 Raw Dict
        llm_extracted_dict = {
            "w2_items": [
                {
                    "employee_name": "Marcus Rivera",
                    "employer_name": "TechCorp",
                    "box_1_wages": "46000.00",
                    "box_2_federal_withholding": "5200.00",
                    "tax_year": 2025,
                    "source_document_id": "doc_w2_marcus",
                    "status": "COMPLETE",
                },
                {
                    "employee_name": "Elena Rivera",
                    "employer_name": "EduCorp",
                    "box_1_wages": "54000.00",
                    "box_2_federal_withholding": "6100.00",
                    "tax_year": 2025,
                    "source_document_id": "doc_w2_elena",
                    "status": "COMPLETE",
                },
            ],
            "ira_distribution": {
                "gross_amount": "0.00",
                "taxable_amount": "0.00",
                "status": "EXPLICIT_VALUE",
            },
            "pension_annuity": {
                "gross_amount": "0.00",
                "taxable_amount": "0.00",
                "status": "EXPLICIT_VALUE",
            },
            "social_security": {
                "gross_amount": "0.00",
                "taxable_amount": "0.00",
                "status": "EXPLICIT_VALUE",
            },
        }

        # 2. 準備上游各表單的原始輸入 Dict 資料
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

        sd_inputs = {
            "line_7_capital_gain_or_loss": -990.00
        }

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

        # 3. 執行 Form 1040 全流程組裝 (由 Orchestrator 內部調度子計算引擎)
        assembly_result = Form1040Orchestrator.assemble(
            tax_year=2025,
            filing_status="MFJ",
            raw_llm_direct_income=llm_extracted_dict,
            raw_schedule_b_input=sb_inputs,
            raw_schedule_d_input=sd_inputs,
            raw_schedule_1_input=s1_inputs,
        )

        # 4. 驗證全流程計算狀態
        self.assertEqual(assembly_result["status"], "COMPLETE")
        self.assertEqual(len(assembly_result["blocking_errors"]), 0)

        income_sec = assembly_result["income_section"]
        agi_sec = assembly_result["agi_section"]

        # 5. 逐行驗證 Income Section (Lines 1-9)
        self.assertEqual(income_sec["line_1a"], "100000.00")
        self.assertEqual(income_sec["line_1z"], "100000.00")
        self.assertEqual(income_sec["line_2b"], "150.00")
        self.assertEqual(income_sec["line_3b"], "405.00")
        self.assertEqual(income_sec["line_7a"], "-990.00")
        self.assertEqual(income_sec["line_8"], "0.00")
        self.assertEqual(income_sec["line_9"], "99565.00")  # 100000 + 150 + 405 - 990 = 99565.00

        # 6. 逐行驗證 AGI Section (Lines 9-11)
        self.assertEqual(agi_sec["line_9_total_income"], "99565.00")
        self.assertEqual(agi_sec["line_10_adjustments_to_income"], "7000.00")
        self.assertEqual(agi_sec["line_11_adjusted_gross_income"], "92565.00") # 99565 - 7000 = 92565.00


if __name__ == "__main__":
    unittest.main()
