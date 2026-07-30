import sys
import os
import unittest
from decimal import Decimal

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from form1040.models.credits_model import CreditsProcessorInputV1
from form1040.processors.credits_processor import CreditsProcessor


class TestCreditsProcessor(unittest.TestCase):
    def test_credits_001_normal(self):
        result = CreditsProcessor.process(
            CreditsProcessorInputV1(
                line_18_tax_before_credits=Decimal("3000"),
                schedule_8812_result={"total_ctc_odc": Decimal("2000")},
                schedule_3_result={"line_8_total": Decimal("500")},
                schedule_2_result={"line_21_total": Decimal("1200")},
            )
        )
        self.assertEqual(result.line_19_ctc_odc, Decimal("2000"))
        self.assertEqual(result.line_20_schedule3_credits, Decimal("500"))
        self.assertEqual(result.line_21_total_credits, Decimal("2500"))
        self.assertEqual(result.line_22_tax_after_credits, Decimal("500"))
        self.assertEqual(result.line_23_other_taxes, Decimal("1200"))
        self.assertEqual(result.line_24_total_tax, Decimal("1700"))
        self.assertEqual(result.status, "COMPLETE")
        self.assertTrue(result.can_continue)
        self.assertEqual(result.blocking_errors, [])

    def test_credits_002_floor_at_zero(self):
        """Line 22 must floor at 0 when credits exceed tax before credits."""
        result = CreditsProcessor.process(
            CreditsProcessorInputV1(
                line_18_tax_before_credits=Decimal("1000"),
                schedule_8812_result={"total_ctc_odc": Decimal("2000")},
                schedule_3_result={"line_8_total": Decimal("500")},
                schedule_2_result={"line_21_total": Decimal("1200")},
            )
        )
        self.assertEqual(result.line_21_total_credits, Decimal("2500"))
        self.assertEqual(result.line_22_tax_after_credits, Decimal("0"))
        self.assertEqual(result.line_24_total_tax, Decimal("1200"))
        self.assertEqual(result.status, "COMPLETE")

    def test_credits_003_missing_line_18(self):
        result = CreditsProcessor.process(
            CreditsProcessorInputV1(
                line_18_tax_before_credits=None,
                schedule_8812_result={"total_ctc_odc": Decimal("2000")},
                schedule_3_result={"line_8_total": Decimal("500")},
                schedule_2_result={"line_21_total": Decimal("1200")},
            )
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertFalse(result.can_continue)
        self.assertIsNone(result.line_22_tax_after_credits)
        self.assertIsNone(result.line_24_total_tax)
        self.assertTrue(any(err.code == "MISSING_LINE_18" for err in result.blocking_errors))

    def test_credits_004_missing_schedule_8812_result(self):
        """Schedule result entirely absent (upstream never ran) -> block."""
        result = CreditsProcessor.process(
            CreditsProcessorInputV1(
                line_18_tax_before_credits=Decimal("3000"),
                schedule_8812_result=None,
                schedule_3_result={"line_8_total": Decimal("500")},
                schedule_2_result={"line_21_total": Decimal("1200")},
            )
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertFalse(result.can_continue)
        self.assertTrue(
            any(err.code == "MISSING_SCHEDULE_8812_RESULT" for err in result.blocking_errors)
        )

    def test_credits_005_missing_amount_without_confirmation(self):
        """Amount is None but no CONFIRMED_NOT_PRESENT status -> block, not silently 0."""
        result = CreditsProcessor.process(
            CreditsProcessorInputV1(
                line_18_tax_before_credits=Decimal("3000"),
                schedule_8812_result={"total_ctc_odc": None},
                schedule_3_result={"line_8_total": Decimal("500")},
                schedule_2_result={"line_21_total": Decimal("1200")},
            )
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(
            any(err.code == "MISSING_SCHEDULE_8812_TOTAL_CTC_ODC" for err in result.blocking_errors)
        )

    def test_credits_006_confirmed_not_present_treated_as_zero(self):
        """CONFIRMED_NOT_PRESENT (e.g. no dependents) -> legitimate 0, not a block."""
        result = CreditsProcessor.process(
            CreditsProcessorInputV1(
                line_18_tax_before_credits=Decimal("3000"),
                schedule_8812_result={"status": "CONFIRMED_NOT_PRESENT", "total_ctc_odc": None},
                schedule_3_result={"line_8_total": Decimal("500")},
                schedule_2_result={"line_21_total": Decimal("1200")},
            )
        )
        self.assertEqual(result.status, "COMPLETE")
        self.assertEqual(result.line_19_ctc_odc, Decimal("0"))
        self.assertEqual(result.line_21_total_credits, Decimal("500"))

    def test_credits_007_schedule_module_blocked(self):
        result = CreditsProcessor.process(
            CreditsProcessorInputV1(
                line_18_tax_before_credits=Decimal("3000"),
                schedule_8812_result={"total_ctc_odc": Decimal("2000")},
                schedule_3_result={"status": "BLOCKED"},
                schedule_2_result={"line_21_total": Decimal("1200")},
            )
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(
            any(err.code == "SCHEDULE_3_MODULE_BLOCKED" for err in result.blocking_errors)
        )

    def test_credits_008_negative_schedule_amount(self):
        result = CreditsProcessor.process(
            CreditsProcessorInputV1(
                line_18_tax_before_credits=Decimal("3000"),
                schedule_8812_result={"total_ctc_odc": Decimal("2000")},
                schedule_3_result={"line_8_total": Decimal("-1")},
                schedule_2_result={"line_21_total": Decimal("1200")},
            )
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(
            any(err.code == "NEGATIVE_SCHEDULE_3_AMOUNT" for err in result.blocking_errors)
        )

    def test_credits_009_object_style_schedule_results(self):
        class DummySchedule8812:
            total_ctc_odc = Decimal("2000")

        class DummySchedule3:
            line_8_total = Decimal("500")

        class DummySchedule2:
            line_21_total = Decimal("1200")

        result = CreditsProcessor.process(
            CreditsProcessorInputV1(
                line_18_tax_before_credits=Decimal("3000"),
                schedule_8812_result=DummySchedule8812(),
                schedule_3_result=DummySchedule3(),
                schedule_2_result=DummySchedule2(),
            )
        )
        self.assertEqual(result.line_24_total_tax, Decimal("1700"))
        self.assertEqual(result.status, "COMPLETE")

    def test_credits_success_invariant(self):
        result = CreditsProcessor.process(
            CreditsProcessorInputV1(
                line_18_tax_before_credits=Decimal("5000"),
                schedule_8812_result={"total_ctc_odc": Decimal("1000")},
                schedule_3_result={"line_8_total": Decimal("300")},
                schedule_2_result={"line_21_total": Decimal("700")},
            )
        )
        self.assertEqual(
            result.line_21_total_credits,
            result.line_19_ctc_odc + result.line_20_schedule3_credits,
        )
        self.assertEqual(
            result.line_22_tax_after_credits,
            max(Decimal("0"), result.line_18_tax_before_credits - result.line_21_total_credits),
        )
        self.assertEqual(
            result.line_24_total_tax,
            result.line_22_tax_after_credits + result.line_23_other_taxes,
        )


if __name__ == "__main__":
    unittest.main()
