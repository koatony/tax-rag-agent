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
    (DirectIncomeParser -> IncomeAggregatorValidator -> IncomeAggregatorCalculator -> AGIValidator -> AGICalculator)
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

        # 2. 模擬上游 Schedule B, Schedule D, Schedule 1 計算完成後的 Raw Result 物件
        sb_result = ScheduleBResultV1(
            form_1040_line_2a=Decimal("0.00"),
            line_4_surface_value=Decimal("150.00"),            # Line 2b Taxable Interest
            total_qualified_dividends=Decimal("0.00"),
            line_6_total_ordinary_dividends=Decimal("405.00"), # Line 3b Ordinary Dividends
            status="COMPLETE",
        )

        sd_result = ScheduleDResultV1(
            line_7_capital_gain_or_loss=Decimal("-990.00"),     # Line 7a Capital Loss
            status="COMPLETE",
        )

        s1_result = Schedule1ResultV1(
            line_10_additional_income=Decimal("0.00"),           # Line 8 Additional Income
            line_26_adjustments_to_income=Decimal("7000.00"),     # Line 10 Adjustments to Income
            status="COMPLETE",
        )

        # 3. 執行 Form 1040 全流程組裝
        assembly_result = Form1040Orchestrator.assemble_0622_case(
            raw_llm_direct_income=llm_extracted_dict,
            schedule_b_result=sb_result,
            schedule_d_result=sd_result,
            schedule_1_result=s1_result,
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
