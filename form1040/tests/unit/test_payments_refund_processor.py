import sys
import os
import unittest
from decimal import Decimal

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from form1040.models.payments_refund_model import PaymentsAndRefundProcessorInputV1
from form1040.processors.payments_refund_processor import PaymentsAndRefundProcessor


def _full_valid_kwargs(**overrides):
    """Baseline input where every sub-result is present and all amounts are 0."""
    base = dict(
        line_24_total_tax=Decimal("1000"),
        withholding_result={"w2_withholding": Decimal("0"), "form1099_withholding": Decimal("0"), "other_withholding": Decimal("0")},
        estimated_payments=Decimal("0"),
        eic_result={"line_27a_eic": Decimal("0")},
        schedule_8812_result={"line_28_actc": Decimal("0")},
        form_8863_result={"line_8_aoc": Decimal("0")},
        form_8839_result={"line_13_refundable_credit": Decimal("0")},
        schedule_3_result={"line_15_total": Decimal("0")},
        refund_choice=None,
        estimated_tax_penalty_result=Decimal("0"),
    )
    base.update(overrides)
    return base


class TestPaymentsAndRefundProcessor(unittest.TestCase):
    def test_payref_001_overpayment_branch(self):
        result = PaymentsAndRefundProcessor.process(
            PaymentsAndRefundProcessorInputV1(
                **_full_valid_kwargs(
                    line_24_total_tax=Decimal("1000"),
                    withholding_result={"w2_withholding": Decimal("2000"), "form1099_withholding": Decimal("0"), "other_withholding": Decimal("0")},
                    refund_choice={"amount_to_refund": Decimal("500"), "amount_to_apply_next_year": Decimal("500")},
                )
            )
        )
        self.assertEqual(result.status, "COMPLETE")
        self.assertEqual(result.line_33_total_payments, Decimal("2000"))
        self.assertEqual(result.line_34_overpayment, Decimal("1000"))
        self.assertIsNone(result.line_37_amount_owed)
        self.assertEqual(result.line_35a_refund_amount, Decimal("500"))
        self.assertEqual(result.line_36_applied_to_next_year, Decimal("500"))

    def test_payref_002_amount_owed_branch(self):
        result = PaymentsAndRefundProcessor.process(
            PaymentsAndRefundProcessorInputV1(
                **_full_valid_kwargs(
                    line_24_total_tax=Decimal("5000"),
                    withholding_result={"w2_withholding": Decimal("1000"), "form1099_withholding": Decimal("0"), "other_withholding": Decimal("0")},
                )
            )
        )
        self.assertEqual(result.status, "COMPLETE")
        self.assertEqual(result.line_33_total_payments, Decimal("1000"))
        self.assertIsNone(result.line_34_overpayment)
        self.assertEqual(result.line_37_amount_owed, Decimal("4000"))

    def test_payref_003_line_33_equals_line_24_goes_to_owe_branch(self):
        """Mapping doc: only line_33 > line_24 triggers overpayment; equal totals owe 0."""
        result = PaymentsAndRefundProcessor.process(
            PaymentsAndRefundProcessorInputV1(
                **_full_valid_kwargs(
                    line_24_total_tax=Decimal("1000"),
                    withholding_result={"w2_withholding": Decimal("1000"), "form1099_withholding": Decimal("0"), "other_withholding": Decimal("0")},
                )
            )
        )
        self.assertIsNone(result.line_34_overpayment)
        self.assertEqual(result.line_37_amount_owed, Decimal("0"))

    def test_payref_004_missing_line_24(self):
        result = PaymentsAndRefundProcessor.process(
            PaymentsAndRefundProcessorInputV1(**_full_valid_kwargs(line_24_total_tax=None))
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertFalse(result.can_continue)
        self.assertIsNone(result.line_34_overpayment)
        self.assertIsNone(result.line_37_amount_owed)
        self.assertTrue(any(err.code == "MISSING_LINE_24" for err in result.blocking_errors))

    def test_payref_005_missing_withholding_result_entirely(self):
        result = PaymentsAndRefundProcessor.process(
            PaymentsAndRefundProcessorInputV1(**_full_valid_kwargs(withholding_result=None))
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any(err.code == "MISSING_WITHHOLDING_RESULT" for err in result.blocking_errors))
        # Should not also spam per-field MISSING_LINE_25* errors for the same missing result
        self.assertFalse(any(err.code.startswith("MISSING_LINE_25") for err in result.blocking_errors))

    def test_payref_006_withholding_field_missing_without_confirmation(self):
        """Amount is None but no CONFIRMED_NOT_PRESENT status -> block, not silently 0."""
        result = PaymentsAndRefundProcessor.process(
            PaymentsAndRefundProcessorInputV1(
                **_full_valid_kwargs(
                    withholding_result={"w2_withholding": None, "form1099_withholding": Decimal("0"), "other_withholding": Decimal("0")}
                )
            )
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any(err.code == "MISSING_LINE_25A_W2_WITHHOLDING" for err in result.blocking_errors))

    def test_payref_007_withholding_confirmed_not_present_treated_as_zero(self):
        result = PaymentsAndRefundProcessor.process(
            PaymentsAndRefundProcessorInputV1(
                **_full_valid_kwargs(
                    withholding_result={
                        "status": "CONFIRMED_NOT_PRESENT",
                        "w2_withholding": None,
                        "form1099_withholding": None,
                        "other_withholding": None,
                    }
                )
            )
        )
        self.assertEqual(result.status, "COMPLETE")
        self.assertEqual(result.line_25d_total_withholding, Decimal("0"))

    def test_payref_008_missing_line_26_estimated_payments(self):
        result = PaymentsAndRefundProcessor.process(
            PaymentsAndRefundProcessorInputV1(**_full_valid_kwargs(estimated_payments=None))
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any(err.code == "MISSING_LINE_26" for err in result.blocking_errors))

    def test_payref_009_missing_eic_result(self):
        result = PaymentsAndRefundProcessor.process(
            PaymentsAndRefundProcessorInputV1(**_full_valid_kwargs(eic_result=None))
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any(err.code == "MISSING_EIC_RESULT" for err in result.blocking_errors))

    def test_payref_010_missing_line_38_penalty(self):
        result = PaymentsAndRefundProcessor.process(
            PaymentsAndRefundProcessorInputV1(**_full_valid_kwargs(estimated_tax_penalty_result=None))
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any(err.code == "MISSING_LINE_38" for err in result.blocking_errors))

    def test_payref_011_refund_choice_exceeds_overpayment(self):
        result = PaymentsAndRefundProcessor.process(
            PaymentsAndRefundProcessorInputV1(
                **_full_valid_kwargs(
                    line_24_total_tax=Decimal("1000"),
                    withholding_result={"w2_withholding": Decimal("2000"), "form1099_withholding": Decimal("0"), "other_withholding": Decimal("0")},
                    refund_choice={"amount_to_refund": Decimal("900"), "amount_to_apply_next_year": Decimal("900")},
                )
            )
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any(err.code == "REFUND_CHOICE_EXCEEDS_OVERPAYMENT" for err in result.blocking_errors))

    def test_payref_012_refund_choice_without_overpayment(self):
        """No overpayment (owe branch) but taxpayer still set 35a/36 -> block."""
        result = PaymentsAndRefundProcessor.process(
            PaymentsAndRefundProcessorInputV1(
                **_full_valid_kwargs(
                    line_24_total_tax=Decimal("5000"),
                    withholding_result={"w2_withholding": Decimal("1000"), "form1099_withholding": Decimal("0"), "other_withholding": Decimal("0")},
                    refund_choice={"amount_to_refund": Decimal("100"), "amount_to_apply_next_year": Decimal("0")},
                )
            )
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any(err.code == "REFUND_CHOICE_WITHOUT_OVERPAYMENT" for err in result.blocking_errors))

    def test_payref_013_negative_amount_blocked(self):
        result = PaymentsAndRefundProcessor.process(
            PaymentsAndRefundProcessorInputV1(**_full_valid_kwargs(estimated_payments=Decimal("-1")))
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any(err.code == "NEGATIVE_LINE_26_AMOUNT" for err in result.blocking_errors))

    def test_payref_014_object_style_sub_results(self):
        class DummyWithholding:
            w2_withholding = Decimal("1500")
            form1099_withholding = Decimal("200")
            other_withholding = Decimal("0")

        result = PaymentsAndRefundProcessor.process(
            PaymentsAndRefundProcessorInputV1(**_full_valid_kwargs(withholding_result=DummyWithholding()))
        )
        self.assertEqual(result.status, "COMPLETE")
        self.assertEqual(result.line_25d_total_withholding, Decimal("1700"))

    def test_payref_success_invariant(self):
        result = PaymentsAndRefundProcessor.process(
            PaymentsAndRefundProcessorInputV1(
                **_full_valid_kwargs(
                    line_24_total_tax=Decimal("2000"),
                    withholding_result={"w2_withholding": Decimal("1000"), "form1099_withholding": Decimal("500"), "other_withholding": Decimal("100")},
                    estimated_payments=Decimal("200"),
                    eic_result={"line_27a_eic": Decimal("50")},
                    schedule_8812_result={"line_28_actc": Decimal("30")},
                    form_8863_result={"line_8_aoc": Decimal("20")},
                    form_8839_result={"line_13_refundable_credit": Decimal("10")},
                    schedule_3_result={"line_15_total": Decimal("5")},
                )
            )
        )
        self.assertEqual(
            result.line_25d_total_withholding,
            result.line_25a_w2_withholding + result.line_25b_1099_withholding + result.line_25c_other_withholding,
        )
        self.assertEqual(
            result.line_32_other_payments_credits,
            result.line_27a_eic + result.line_28_actc + result.line_29_aoc
            + result.line_30_refundable_adoption_credit + result.line_31_schedule3_total,
        )
        self.assertEqual(
            result.line_33_total_payments,
            result.line_25d_total_withholding + result.line_26_estimated_payments + result.line_32_other_payments_credits,
        )
        # Line 34 / 37 mutual exclusivity: exactly one is None
        self.assertNotEqual(result.line_34_overpayment is None, result.line_37_amount_owed is None)


if __name__ == "__main__":
    unittest.main()
