import sys
import os
import unittest
from decimal import Decimal

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from form1040.models.agi_model import AGIProcessorInputV1
from form1040.processors.agi_processor import process, AGIProcessor


class TestAGIProcessor(unittest.TestCase):
    def test_0622_agi(self):
        """0622 case integration test using mock upstream data."""
        input_data = AGIProcessorInputV1(
            line_9_total_income=Decimal("100555"),
            schedule1_line_26_adjustments=Decimal("7000"),
        )
        result = AGIProcessor.process(input_data)

        self.assertEqual(result.line_9_total_income, Decimal("100555"))
        self.assertEqual(result.line_10_adjustments_to_income, Decimal("7000"))
        self.assertEqual(result.line_11_adjusted_gross_income, Decimal("93555"))
        self.assertEqual(result.status, "COMPLETE")
        self.assertTrue(result.can_continue)
        self.assertEqual(result.blocking_errors, [])

    def test_agi_001_normal(self):
        result = process(
            AGIProcessorInputV1(
                line_9_total_income=Decimal("100555"),
                schedule1_line_26_adjustments=Decimal("7000"),
            )
        )
        self.assertEqual(result.line_11_adjusted_gross_income, Decimal("93555"))
        self.assertEqual(
            result.line_11_adjusted_gross_income,
            result.line_9_total_income - result.line_10_adjustments_to_income
        )

    def test_agi_002_zero_adjustments(self):
        result = process(
            AGIProcessorInputV1(
                line_9_total_income=Decimal("1000"),
                schedule1_line_26_adjustments=Decimal("0"),
            )
        )
        self.assertEqual(result.line_10_adjustments_to_income, Decimal("0"))
        self.assertEqual(result.line_11_adjusted_gross_income, Decimal("1000"))
        self.assertEqual(result.status, "COMPLETE")

    def test_agi_003_missing_line_9(self):
        result = process(
            AGIProcessorInputV1(
                line_9_total_income=None,
                schedule1_line_26_adjustments=Decimal("7000"),
            )
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertFalse(result.can_continue)
        self.assertIsNone(result.line_10_adjustments_to_income)
        self.assertIsNone(result.line_11_adjusted_gross_income)
        self.assertTrue(any(err.code == "MISSING_LINE_9" for err in result.blocking_errors))

    def test_agi_004_missing_schedule1_line_26(self):
        result = process(
            AGIProcessorInputV1(
                line_9_total_income=Decimal("100555"),
                schedule1_line_26_adjustments=None,
            )
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertFalse(result.can_continue)
        self.assertIsNone(result.line_10_adjustments_to_income)
        self.assertIsNone(result.line_11_adjusted_gross_income)
        self.assertTrue(any(err.code == "MISSING_SCHEDULE1_LINE_26" for err in result.blocking_errors))

    def test_agi_005_negative_adjustments(self):
        result = process(
            AGIProcessorInputV1(
                line_9_total_income=Decimal("100555"),
                schedule1_line_26_adjustments=Decimal("-1"),
            )
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertFalse(result.can_continue)
        self.assertTrue(any(err.code == "NEGATIVE_ADJUSTMENTS" for err in result.blocking_errors))

    def test_agi_006_negative_agi_result(self):
        result = process(
            AGIProcessorInputV1(
                line_9_total_income=Decimal("100"),
                schedule1_line_26_adjustments=Decimal("200"),
            )
        )
        self.assertEqual(result.status, "COMPLETE")
        self.assertTrue(result.can_continue)
        self.assertEqual(result.line_11_adjusted_gross_income, Decimal("-100"))


if __name__ == "__main__":
    unittest.main()
