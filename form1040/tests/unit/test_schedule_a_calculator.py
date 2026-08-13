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

if __name__ == "__main__":
    unittest.main()
