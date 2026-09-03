import sys
import os
import unittest
from decimal import Decimal

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from processors.models.schedule_a import ScheduleAInputsV1
from processors.calculators.schedule_a import calculate_schedule_a_v1

class TestScheduleACalculator(unittest.TestCase):
    def test_missing_agi_blocks_but_calculates_with_zero(self):
        """
        測試當 AGI 缺失 (None) 時：
        1. 應該會觸發 MISSING_AGI_INPUT 阻斷錯誤。
        2. 計算時 AGI 視為 0.00，使醫療扣除額與稅務加總仍能順暢算出結果。
        """
        inputs_payload = {
            "taxpayer_name": "Marcus Rivera",
            "taxpayer_ssn": "123-45-6789",
            "taxpayer_date_of_birth": "1980-01-01",
            "tax_year": 2025,
            "filing_status": "MFJ",
            # 刻意不提供 adjusted_gross_income / agi 欄位
            "medical_items": [
                {
                    "item_id": "med_01",
                    "taxpayer_paid_amount": 10000.0,
                    "reimbursement_amount": 0.0,
                    "tax_free_medical_account_payment": 0.0,
                    "paid_in_tax_year": True,
                    "eligible_person_status": "ELIGIBLE",
                    "medical_qualification_status": "QUALIFIED_SIMPLE"
                }
            ]
        }
        
        v1_inputs = ScheduleAInputsV1.from_dict(inputs_payload)
        self.assertIsNone(v1_inputs.adjusted_gross_income) # 確認 AGI 在 Model 裡被解析為 None
        
        res = calculate_schedule_a_v1(v1_inputs, allowed_years={2024, 2025})
        
        # 驗證阻斷與錯誤原因
        self.assertFalse(res.can_file)
        blocking_errors = [err.code for err in res.blocking_errors]
        self.assertIn("MISSING_AGI_INPUT", blocking_errors)
        
        # 驗證計算：因為 AGI 視為 0.00，起點門檻 (7.5% of AGI) 為 0，醫療扣除額應為 10000.00
        self.assertEqual(res.line_2_agi, Decimal("0.00"))
        self.assertEqual(res.line_3_medical_threshold, Decimal("0.00"))
        self.assertEqual(res.line_4_deductible_medical_expenses, Decimal("10000.00"))

    def test_dynamic_agi_calculates_threshold_correctly(self):
        """
        測試當 AGI 正常傳入時：
        1. 應該使用該動態傳入的 AGI 進行計算。
        2. 門檻為 7.5% AGI，醫療扣除額為 max(0, medical_expenses - 7.5% AGI)。
        """
        inputs_payload = {
            "taxpayer_name": "Marcus Rivera",
            "taxpayer_ssn": "123-45-6789",
            "taxpayer_date_of_birth": "1980-01-01",
            "tax_year": 2025,
            "filing_status": "MFJ",
            "adjusted_gross_income": 100000.00, # AGI 為 100000.00
            "medical_items": [
                {
                    "item_id": "med_01",
                    "taxpayer_paid_amount": 10000.0,
                    "reimbursement_amount": 0.0,
                    "tax_free_medical_account_payment": 0.0,
                    "paid_in_tax_year": True,
                    "eligible_person_status": "ELIGIBLE",
                    "medical_qualification_status": "QUALIFIED_SIMPLE"
                }
            ]
        }
        
        v1_inputs = ScheduleAInputsV1.from_dict(inputs_payload)
        self.assertEqual(v1_inputs.adjusted_gross_income, Decimal("100000.00"))
        
        res = calculate_schedule_a_v1(v1_inputs, allowed_years={2024, 2025})
        
        # 驗證無 AGI 阻斷錯誤
        blocking_errors = [err.code for err in res.blocking_errors]
        self.assertNotIn("MISSING_AGI_INPUT", blocking_errors)
        
        # 驗證計算：
        # line_2_agi = 100000.00
        # line_3_medical_threshold = 100000 * 7.5% = 7500.00
        # line_4_deductible_medical_expenses = max(0, 10000 - 7500) = 2500.00
        self.assertEqual(res.line_2_agi, Decimal("100000.00"))
        self.assertEqual(res.line_3_medical_threshold, Decimal("7500.00"))
        self.assertEqual(res.line_4_deductible_medical_expenses, Decimal("2500.00"))

    def test_unknown_charity_qualification_retains_candidate_and_adds_warning(self):
        """
        測試當 Charity 捐款項目的 qualified_organization_status 為 UNKNOWN 時：
        1. 扣除金額 candidate total 仍應保留（例如 5400.00），不直接算作 0。
        2. 不加入 blocking_errors，而是寫入 review_warnings (UNKNOWN_TAX_CHARACTER)。
        """
        inputs_payload = {
            "taxpayer_name": "Marcus Rivera",
            "taxpayer_ssn": "123-45-6789",
            "taxpayer_date_of_birth": "1980-01-01",
            "tax_year": 2025,
            "filing_status": "MFJ",
            "adjusted_gross_income": 100000.00,
            "cash_charity_items": [
                {
                    "item_id": "charity_01",
                    "gross_contribution_amount": 5400.0,
                    "goods_or_services_value": 0.0,
                    "contribution_date": "2025-06-01",
                    "paid_in_tax_year": True,
                    "qualified_organization_status": "UNKNOWN",
                    "bank_or_written_record_available": True,
                    "contemporaneous_acknowledgment_received": True
                }
            ]
        }

        v1_inputs = ScheduleAInputsV1.from_dict(inputs_payload)
        res = calculate_schedule_a_v1(v1_inputs, allowed_years={2024, 2025})

        # 驗證 Line 11/14 扣除候選金額保留為 5400.00
        self.assertEqual(res.line_11_cash_contributions, Decimal("5400.00"))
        self.assertEqual(res.line_14_total_charity, Decimal("5400.00"))

        # 驗證 blocking_errors 無 UNKNOWN_TAX_CHARACTER
        blocking_codes = [err.code for err in res.blocking_errors]
        self.assertNotIn("UNKNOWN_TAX_CHARACTER", blocking_codes)

        # 驗證 review_warnings 包含 UNKNOWN_TAX_CHARACTER 且訊息含法律依據 IRC §170(c)
        warning_codes = [warn.code for warn in res.review_warnings]
        self.assertIn("UNKNOWN_TAX_CHARACTER", warning_codes)
        self.assertTrue(any("IRC §170(c)" in warn.message for warn in res.review_warnings))

        # 驗證需要人工複查，can_file 為 False（不可直接提交）
        self.assertFalse(res.can_file)

    def test_missing_charity_contribution_date_retains_candidate_and_adds_warning(self):
        """
        測試當 Charity 捐款項目的 contribution_date 缺失時：
        1. 扣除金額 candidate total 仍應保留（5400.00），不直接算出 0。
        2. 記錄 CHARITY_CONTRIBUTION_DATE_MISSING 為 review_warning（內含 IRC §170 法律依據）。
        3. can_file 為 False（需要人工審核複查，不能直接提交）。
        """
        inputs_payload = {
            "taxpayer_name": "Marcus Rivera",
            "taxpayer_ssn": "123-45-6789",
            "taxpayer_date_of_birth": "1980-01-01",
            "tax_year": 2025,
            "filing_status": "MFJ",
            "adjusted_gross_income": 100000.00,
            "cash_charity_items": [
                {
                    "item_id": "charity_02",
                    "gross_contribution_amount": 5400.0,
                    "goods_or_services_value": 0.0,
                    "contribution_date": None,  # 日期缺失
                    "paid_in_tax_year": True,
                    "qualified_organization_status": "VERIFIED",
                    "bank_or_written_record_available": True,
                    "contemporaneous_acknowledgment_received": True
                }
            ]
        }

        v1_inputs = ScheduleAInputsV1.from_dict(inputs_payload)
        res = calculate_schedule_a_v1(v1_inputs, allowed_years={2024, 2025})

        # 驗證金額保留 5400.00 納入計算
        self.assertEqual(res.line_11_cash_contributions, Decimal("5400.00"))
        self.assertEqual(res.line_14_total_charity, Decimal("5400.00"))

        # 驗證產生 CHARITY_CONTRIBUTION_DATE_MISSING 警告與 IRC §170 法律依據
        warning_codes = [warn.code for warn in res.review_warnings]
        self.assertIn("CHARITY_CONTRIBUTION_DATE_MISSING", warning_codes)
        self.assertTrue(any("IRC §170" in warn.message for warn in res.review_warnings))

        # 驗證需要人工複查，can_file 為 False
        self.assertFalse(res.can_file)

    def test_unusable_schedule_a_falls_back_to_standard_and_adds_warning(self):
        """
        測試當 Schedule A 列舉總額大於 Standard Deduction，但因 Blocking Error 導致 can_file 為 False 時：
        1. is_itemizing 應為 False。
        2. should_attach_schedule_a 應為 False。
        3. review_warnings 中應包含 SCHEDULE_A_UNUSABLE_FALLBACK_TO_STANDARD 警告說明原因。
        """
        inputs_payload = {
            "taxpayer_name": "Marcus Rivera",
            "taxpayer_ssn": "123-45-6789",
            "taxpayer_date_of_birth": "1980-01-01",
            "tax_year": 2025,
            "filing_status": "SINGLE",
            "adjusted_gross_income": 50000.00, # AGI 50k
            "line_5a_election": "INCOME_TAX",
            "tax_items": [
                {
                    "item_id": "tax_01",
                    "tax_category": "STATE_LOCAL_INCOME_TAX",
                    "amount_paid": 30000.0,
                    "paid_in_tax_year": True
                }
            ],
            "special_case_flags": {
                "has_ltc_premium": True
            }
        }

        v1_inputs = ScheduleAInputsV1.from_dict(inputs_payload)
        res = calculate_schedule_a_v1(v1_inputs, allowed_years={2024, 2025})

        self.assertFalse(res.can_file)
        self.assertFalse(res.is_itemizing)
        self.assertFalse(res.should_attach_schedule_a)

        warning_codes = [warn.code for warn in res.review_warnings]
        self.assertIn("SCHEDULE_A_UNUSABLE_FALLBACK_TO_STANDARD", warning_codes)
        warning_msg = next(w.message for w in res.review_warnings if w.code == "SCHEDULE_A_UNUSABLE_FALLBACK_TO_STANDARD")
        self.assertIn("無法申報 Schedule A", warning_msg)

if __name__ == "__main__":
    unittest.main()
