from decimal import Decimal
import unittest

from form1040.models.taxable_income_model import TaxableIncomeResultV1
from form1040.models.tax_computation_model import (
    TaxComputationInputV1,
    FilingStatus,
    ApplicabilityStatus,
    OrdinaryTaxEligibilityV1,
    TaxComputationMethod,
)
from form1040.processors.tax_computation_processor import TaxComputationProcessor


class TestTaxComputationProcessor(unittest.TestCase):
    """
    TaxComputationProcessor V1 單元測試集 (Form 1040 Lines 16, 17, 18)
    """

    def test_tax_table_lookup_mfj(self):
        """測試 Line 15 < $100,000 的 2025 IRS Tax Table 查表法 (Line 15 = $68,065, MFJ => Line 16 = $7,692)"""
        taxable_res = TaxableIncomeResultV1(
            tax_year=2025,
            line_11b_agi=Decimal("99565.00"),
            line_14_total_deductions=Decimal("31500.00"),
            line_15_taxable_income=Decimal("68065.00"),
            status="COMPLETE",
            can_continue=True,
        )

        eligibility = OrdinaryTaxEligibilityV1(
            qualified_dividends_amount=Decimal("0.00"),
            capital_gain_or_loss_amount=Decimal("-990.00"),
            status=ApplicabilityStatus.APPLICABLE,
        )

        inp = TaxComputationInputV1(
            tax_year=2025,
            filing_status=FilingStatus.MFJ,
            taxable_income_result=taxable_res,
            ordinary_tax_eligibility=eligibility,
            schedule_2_status=ApplicabilityStatus.NOT_APPLICABLE,
        )
        res = TaxComputationProcessor.process(inp)

        self.assertEqual(res.status, "COMPLETE")
        self.assertTrue(res.can_continue)
        self.assertEqual(res.computation_method, TaxComputationMethod.TAX_TABLE)
        self.assertEqual(res.line_15_taxable_income, Decimal("68065.00"))
        self.assertEqual(res.line_16_tax, Decimal("7692.00"))
        self.assertEqual(res.line_17_schedule_2_line_3, Decimal("0.00"))
        self.assertEqual(res.line_18_tax_before_credits, Decimal("7692.00"))

    def test_tax_computation_worksheet_mfj(self):
        """測試 Line 15 >= $100,000 的 Tax Computation Worksheet 套算法 (Line 15 = $120,000, MFJ => Line 16 = $16,228)"""
        taxable_res = TaxableIncomeResultV1(
            tax_year=2025,
            line_15_taxable_income=Decimal("120000.00"),
            status="COMPLETE",
            can_continue=True,
        )

        eligibility = OrdinaryTaxEligibilityV1(
            qualified_dividends_amount=Decimal("0.00"),
            capital_gain_or_loss_amount=Decimal("0.00"),
            status=ApplicabilityStatus.APPLICABLE,
        )

        inp = TaxComputationInputV1(
            tax_year=2025,
            filing_status=FilingStatus.MFJ,
            taxable_income_result=taxable_res,
            ordinary_tax_eligibility=eligibility,
            schedule_2_status=ApplicabilityStatus.NOT_APPLICABLE,
        )
        res = TaxComputationProcessor.process(inp)

        self.assertEqual(res.status, "COMPLETE")
        self.assertEqual(res.computation_method, TaxComputationMethod.TAX_COMPUTATION_WORKSHEET)
        self.assertEqual(res.line_16_tax, Decimal("16228.00"))
        self.assertEqual(res.line_18_tax_before_credits, Decimal("16228.00"))

    def test_zero_taxable_income(self):
        """測試 Line 15 = 0 時填 ZERO_TAX ($0.00)"""
        taxable_res = TaxableIncomeResultV1(
            tax_year=2025,
            line_15_taxable_income=Decimal("0.00"),
            status="COMPLETE",
            can_continue=True,
        )

        eligibility = OrdinaryTaxEligibilityV1(status=ApplicabilityStatus.APPLICABLE)

        inp = TaxComputationInputV1(
            tax_year=2025,
            filing_status=FilingStatus.SINGLE,
            taxable_income_result=taxable_res,
            ordinary_tax_eligibility=eligibility,
            schedule_2_status=ApplicabilityStatus.NOT_APPLICABLE,
        )
        res = TaxComputationProcessor.process(inp)

        self.assertEqual(res.status, "COMPLETE")
        self.assertEqual(res.computation_method, TaxComputationMethod.ZERO_TAX)
        self.assertEqual(res.line_16_tax, Decimal("0.00"))
        self.assertEqual(res.line_18_tax_before_credits, Decimal("0.00"))

    def test_qualified_dividends_blocking(self):
        """測試包含 Qualified Dividends > 0 時觸發 SPECIAL_TAX_METHOD_UNSUPPORTED 阻斷"""
        taxable_res = TaxableIncomeResultV1(
            tax_year=2025,
            line_15_taxable_income=Decimal("50000.00"),
            status="COMPLETE",
            can_continue=True,
        )

        eligibility = OrdinaryTaxEligibilityV1(
            qualified_dividends_amount=Decimal("500.00"),
            capital_gain_or_loss_amount=Decimal("0.00"),
            status=ApplicabilityStatus.APPLICABLE,
        )

        inp = TaxComputationInputV1(
            tax_year=2025,
            filing_status=FilingStatus.SINGLE,
            taxable_income_result=taxable_res,
            ordinary_tax_eligibility=eligibility,
            schedule_2_status=ApplicabilityStatus.NOT_APPLICABLE,
        )
        res = TaxComputationProcessor.process(inp)

        self.assertEqual(res.status, "BLOCKED")
        self.assertFalse(res.can_continue)
        self.assertEqual(len(res.blocking_errors), 1)
        self.assertEqual(res.blocking_errors[0].code, "SPECIAL_TAX_METHOD_UNSUPPORTED")

    def test_schedule_2_unsupported_blocking(self):
        """測試 Schedule 2 狀態不為 NOT_APPLICABLE 時發出阻斷」"""
        taxable_res = TaxableIncomeResultV1(
            tax_year=2025,
            line_15_taxable_income=Decimal("50000.00"),
            status="COMPLETE",
            can_continue=True,
        )

        eligibility = OrdinaryTaxEligibilityV1(status=ApplicabilityStatus.APPLICABLE)

        inp = TaxComputationInputV1(
            tax_year=2025,
            filing_status=FilingStatus.SINGLE,
            taxable_income_result=taxable_res,
            ordinary_tax_eligibility=eligibility,
            schedule_2_status=ApplicabilityStatus.UNRESOLVED,
        )
        res = TaxComputationProcessor.process(inp)

        self.assertEqual(res.status, "BLOCKED")
        self.assertEqual(res.blocking_errors[0].code, "SCHEDULE_2_UNRESOLVED_OR_UNSUPPORTED")


if __name__ == "__main__":
    unittest.main()
