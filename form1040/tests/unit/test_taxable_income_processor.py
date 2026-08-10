from decimal import Decimal
import unittest

from form1040.models.agi_model import AGIProcessorResultV1, ProcessingIssueV1
from form1040.models.deduction_resolver_model import DeductionResolverResultV1
from form1040.models.taxable_income_model import TaxableIncomeInputV1
from form1040.processors.taxable_income_processor import TaxableIncomeProcessor


class TestTaxableIncomeProcessor(unittest.TestCase):
    """
    TaxableIncomeProcessor V1 單元測試集 (Form 1040 Line 15)
    """

    def test_normal_taxable_income_calculation(self):
        """測試一般正數 Taxable Income 計算 (AGI 120,000 - Deductions 31,500 = 88,500)"""
        agi_res = AGIProcessorResultV1(
            line_9_total_income=Decimal("120000.00"),
            line_10_adjustments_to_income=Decimal("0.00"),
            line_11_adjusted_gross_income=Decimal("120000.00"),
            status="COMPLETE",
            can_continue=True,
        )

        ded_res = DeductionResolverResultV1(
            tax_year=2025,
            filing_status="MFJ",
            line_12e_deduction=Decimal("31500.00"),
            line_13a_qbi_deduction=Decimal("0.00"),
            line_13b_schedule_1a_deductions=Decimal("0.00"),
            line_14_total_deductions=Decimal("31500.00"),
            status="COMPLETE",
            can_continue=True,
        )

        res = TaxableIncomeProcessor.compute(
            tax_year=2025,
            agi_result=agi_res,
            deduction_result=ded_res,
        )

        self.assertEqual(res.status, "COMPLETE")
        self.assertTrue(res.can_continue)
        self.assertEqual(res.line_11b_agi, Decimal("120000.00"))
        self.assertEqual(res.line_14_total_deductions, Decimal("31500.00"))
        self.assertEqual(res.line_15_taxable_income, Decimal("88500.00"))
        self.assertEqual(len(res.blocking_errors), 0)

    def test_deductions_exceed_agi_clamp_to_zero(self):
        """測試扣除額大於 AGI 時，Line 15 自動設為 0.00 並給予 Warning 提示"""
        agi_res = AGIProcessorResultV1(
            line_11_adjusted_gross_income=Decimal("20000.00"),
            status="COMPLETE",
            can_continue=True,
        )

        ded_res = DeductionResolverResultV1(
            line_14_total_deductions=Decimal("31500.00"),
            status="COMPLETE",
            can_continue=True,
        )

        res = TaxableIncomeProcessor.compute(
            tax_year=2025,
            agi_result=agi_res,
            deduction_result=ded_res,
        )

        self.assertEqual(res.status, "COMPLETE")
        self.assertEqual(res.line_15_taxable_income, Decimal("0.00"))
        self.assertEqual(len(res.review_warnings), 1)
        self.assertEqual(res.review_warnings[0].code, "DEDUCTIONS_EXCEED_AGI")

    def test_upstream_blocking_error_propagation(self):
        """測試上游 AGIProcessor 存在 Blocking Errors 時的阻斷與傳遞能力"""
        blocking_err = ProcessingIssueV1(
            code="UNSUPPORTED_SCHEDULE_1_ITEM",
            field="line_10",
            message="Schedule 1 不支援特殊項目",
        )

        agi_res = AGIProcessorResultV1(
            line_11_adjusted_gross_income=Decimal("0.00"),
            status="BLOCKED",
            can_continue=False,
            blocking_errors=[blocking_err],
        )

        ded_res = DeductionResolverResultV1(
            line_14_total_deductions=Decimal("15000.00"),
            status="COMPLETE",
            can_continue=True,
        )

        res = TaxableIncomeProcessor.compute(
            tax_year=2025,
            agi_result=agi_res,
            deduction_result=ded_res,
        )

        self.assertEqual(res.status, "BLOCKED")
        self.assertFalse(res.can_continue)
        self.assertEqual(len(res.blocking_errors), 1)
        self.assertEqual(res.blocking_errors[0].code, "UNSUPPORTED_SCHEDULE_1_ITEM")


if __name__ == "__main__":
    unittest.main()
