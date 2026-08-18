import sys
import os
import unittest
from decimal import Decimal

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from processors.models.schedule_e import ScheduleEPart1InputsV1
from processors.calculators.schedule_e import calculate_schedule_e_part1_v1

class TestScheduleECalculator(unittest.TestCase):
    def test_transfer_amount_not_none_when_blocked(self):
        """
        測試當 Schedule E 因為欄位缺失 (例如 reporting_route_status="UNKNOWN") 導致 BLOCKED 時，
        計算器依然能夠算出正確金額，且 schedule_1_line_5_transfer_amount 照常結轉，而不是 None。
        """
        # 建構測試資料，刻意不填寫 reporting_route_status 和 ownership_allocation_status
        inputs_payload = {
            "taxpayer_name": "Marcus Rivera",
            "taxpayer_ssn": "123-45-6789",
            "tax_year": 2025,
            "filing_status": "MFJ",
            "accounting_method": "CASH",
            "form_1099_compliance": {
                "requirement_status": "REQUIRED",
                "filed_or_will_file_required_forms": True,
                "source_result_id": "res_1099_01"
            },
            "properties": [
                {
                    "property_id": "prop_001",
                    "physical_address": {
                        "street": "5200 Green Valley Drive",
                        "city": "Sacramento",
                        "state": "CA",
                        "zip_code": "95841",
                        "country": "US"
                    },
                    "property_type": "SINGLE_FAMILY_RESIDENCE",
                    # 刻意漏掉 reporting_route_status 和 ownership_allocation_status，讓它們預設為 UNKNOWN
                    "fair_rental_days": 365,
                    "personal_use_days": 0,
                    "qjv_status": False,
                    "rental_income_items": [
                        {
                            "item_id": "inc_01",
                            "gross_amount_received": 15000.0,
                            "refunded_or_returned_amount": 0.0,
                            "income_character_status": "REPORTABLE_SIMPLE_RENTAL_INCOME",
                            "received_in_tax_year": True
                        }
                    ],
                    "rental_expense_items": [
                        {
                            "item_id": "exp_ins",
                            "expense_category": "INSURANCE",
                            "gross_amount": 1000.0,
                            "reimbursement_amount": 0.0,
                            "nonrental_allocated_amount": 0.0,
                            "deductibility_status": "DEDUCTIBLE_CURRENT",
                            "allocation_status": "TAXPAYER_SHARE_CONFIRMED",
                            "paid_or_incurred_in_tax_year": True
                        }
                    ],
                    "depreciation_result": {
                        "property_id": "prop_001",
                        "tax_year": 2025,
                        "calculation_status": "CALCULATED",
                        "depreciation_amount": 4000.0,
                        "form_4562_attachment_required": False,
                        "source_result_id": "dep_res_01"
                    }
                }
            ]
        }

        v1_inputs = ScheduleEPart1InputsV1.from_dict(inputs_payload)
        res = calculate_schedule_e_part1_v1(v1_inputs, allowed_years={2024, 2025})

        # 1. 驗證是否因為欄位缺失而被判定為無法申報
        self.assertFalse(res.can_finalize_part1)
        
        # 2. 驗證阻斷列表中含有預期的錯誤
        blocking_errors = [err.code for err in res.blocking_errors]
        self.assertIn("UNKNOWN_REPORTING_ROUTE", blocking_errors)
        self.assertIn("UNRESOLVED_OWNERSHIP_ALLOCATION", blocking_errors)

        # 3. 關鍵驗證：雖然被阻斷，但轉移金額依然照常計算出來 (15000 - 1000 - 4000 = 10000)，而不是 None
        self.assertEqual(res.line_26_total_rental_income_or_loss, Decimal("10000.00"))
        self.assertEqual(res.schedule_1_line_5_transfer_amount, Decimal("10000.00"))

    def test_form_4562_attachment_rules_prior_year_vs_current_year(self):
        """
        測試 Form 4562 檢附規則：
        1. 往年 (如 2023/07) 投入使用之常規住宅出租房，2025 稅務年度申報 $8,000 折舊時，is_form_4562_required 為 False，且有明確理由說明。
        2. 當年度 (2025/07) 新投入使用之財產，is_form_4562_required 為 True，且有明確理由說明。
        """
        from processors.models.form_4562 import Form4562InputsV1
        from processors.calculators.form_4562 import calculate_form_4562_v1

        # 情境 A：2023/07 投入使用 (往年)
        inputs_prior_year = {
            "taxpayer_name": "Marcus Rivera",
            "taxpayer_ssn": "123-45-6789",
            "business_activity_name": "Rental Real Estate",
            "tax_year": 2025,
            "macrs_gds_items": [
                {
                    "line_code": "19i",
                    "classification": "Residential rental property",
                    "month_year_placed_in_service": "7/2023",
                    "depreciation_basis": 220000.00,
                    "recovery_period": "27.5 yrs.",
                    "convention": "MM",
                    "method": "S/L",
                    "depreciation_deduction": 8000.00
                }
            ]
        }
        res_prior = calculate_form_4562_v1(Form4562InputsV1.from_dict(inputs_prior_year), allowed_years={2024, 2025})
        self.assertFalse(res_prior.is_form_4562_required)
        self.assertFalse(res_prior.should_attach_form_4562)
        self.assertIn("無須檢附 Form 4562", res_prior.form_4562_attachment_reason)

        # 情境 B：2025/07 投入使用 (當年度新投入)
        inputs_current_year = {
            "taxpayer_name": "Marcus Rivera",
            "taxpayer_ssn": "123-45-6789",
            "business_activity_name": "Rental Real Estate",
            "tax_year": 2025,
            "macrs_gds_items": [
                {
                    "line_code": "19i",
                    "classification": "Residential rental property",
                    "month_year_placed_in_service": "7/2025",
                    "depreciation_basis": 220000.00,
                    "recovery_period": "27.5 yrs.",
                    "convention": "MM",
                    "method": "S/L",
                    "depreciation_deduction": 8000.00
                }
            ]
        }
        res_current = calculate_form_4562_v1(Form4562InputsV1.from_dict(inputs_current_year), allowed_years={2024, 2025})
        self.assertTrue(res_current.is_form_4562_required)
        self.assertTrue(res_current.should_attach_form_4562)
        self.assertIn("需要檢附 Form 4562", res_current.form_4562_attachment_reason)

if __name__ == "__main__":
    unittest.main()
