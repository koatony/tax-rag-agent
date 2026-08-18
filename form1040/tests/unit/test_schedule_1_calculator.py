import sys
import os
import unittest
from decimal import Decimal

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from processors.models.schedule_1 import Schedule1InputsV1, AdjustmentItemV1
from processors.calculators.schedule_1 import calculate_schedule_1_v1
from processors.parsers.schedule_1 import Schedule1LLMParser


class TestSchedule1CalculatorAndParser(unittest.TestCase):
    def test_adjustment_item_with_confirmed_deductibility(self):
        """
        測試當 is_deductibility_confirmed 為 True 時：
        1. 正常計算金額（如 7000.00）。
        2. 不產生 UNCONFIRMED_DEDUCTIBILITY 警告。
        """
        inputs_payload = {
            "taxpayer_name": "Marcus Rivera",
            "taxpayer_ssn": "123-45-6789",
            "tax_year": 2025,
            "adjustment_items": [
                {
                    "item_id": "adj_01",
                    "line_code": "20",
                    "description": "IRA deduction",
                    "amount": 7000.00,
                    "is_deductibility_confirmed": True
                }
            ]
        }

        v1_inputs = Schedule1InputsV1.from_dict(inputs_payload)
        res = calculate_schedule_1_v1(v1_inputs, allowed_years={2024, 2025})

        # 驗證金額正常累計至 Line 26
        self.assertEqual(res.line_26_adjustments_to_income, Decimal("7000.00"))

        # 驗證未產生 UNCONFIRMED_DEDUCTIBILITY 警告
        warning_codes = [warn.code for warn in res.review_warnings]
        self.assertNotIn("UNCONFIRMED_DEDUCTIBILITY", warning_codes)

    def test_adjustment_item_with_unconfirmed_deductibility(self):
        """
        測試當 is_deductibility_confirmed 為 False 時：
        1. 計算過程相同（7000.00 仍納入 Line 26 總額）。
        2. 產生 review_warnings 提示人工複查 (UNCONFIRMED_DEDUCTIBILITY)。
        """
        inputs_payload = {
            "taxpayer_name": "Marcus Rivera",
            "taxpayer_ssn": "123-45-6789",
            "tax_year": 2025,
            "adjustment_items": [
                {
                    "item_id": "adj_01",
                    "line_code": "20",
                    "description": "Traditional IRA contribution",
                    "amount": 7000.00,
                    "is_deductibility_confirmed": False
                }
            ]
        }

        v1_inputs = Schedule1InputsV1.from_dict(inputs_payload)
        res = calculate_schedule_1_v1(v1_inputs, allowed_years={2024, 2025})

        # 驗證金額計算相同（7000.00 仍計入 Line 26 扣除總額）
        self.assertEqual(res.line_26_adjustments_to_income, Decimal("7000.00"))

        # 驗證產生 UNCONFIRMED_DEDUCTIBILITY 警告且訊息包含 IRC §219 法律依據
        warning_codes = [warn.code for warn in res.review_warnings]
        self.assertIn("UNCONFIRMED_DEDUCTIBILITY", warning_codes)
        self.assertTrue(any("IRC §219" in warn.message for warn in res.review_warnings))

        # 驗證需要人工複查，can_file 為 False（不可直接提交）
        self.assertFalse(res.can_file)

    def test_parser_custom_rules_and_example_json_format(self):
        """
        測試 LLM Parser 規則與範例 JSON：
        1. get_custom_rules 包含 is_deductibility_confirmed 的說明。
        2. get_example_json 中的 adjustment_items 包含 is_deductibility_confirmed 欄位與數值。
        """
        parser = Schedule1LLMParser()
        rules = parser.get_custom_rules()
        example_json = parser.get_example_json()

        # 驗證規則包含 bool 欄位要求說明
        rule_str = " ".join(rules)
        self.assertIn("is_deductibility_confirmed", rule_str)

        # 驗證範例 JSON 中包含 amount 數值與 is_deductibility_confirmed
        adj_item = example_json["adjustment_items"][0]
        self.assertIn("is_deductibility_confirmed", adj_item)
        self.assertEqual(adj_item["amount"], 7000.00)
        self.assertIsInstance(adj_item["is_deductibility_confirmed"], bool)


if __name__ == "__main__":
    unittest.main()
