import sys
import os
import unittest
from decimal import Decimal

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from form1040.models.deduction_resolver_model import (
    DeductionResolverInputV1,
    Form8995ResultV1,
    Schedule1AResultV1,
)
from form1040.models.agi_model import ProcessingIssueV1
from form1040.processors.deduction_resolver_processor import DeductionResolverProcessor
from processors.models.schedule_a import ScheduleAResultV1


class TestDeductionResolverProcessor(unittest.TestCase):
    def test_standard_deduction_chosen_when_larger(self):
        """當 Standard Deduction 金額大於 Itemized Deduction 時，預設選用 Standard Deduction"""
        sa_res = ScheduleAResultV1(
            standard_deduction_amount=Decimal("15000.00"),
            line_17_total_itemized_deductions=Decimal("10000.00"),
            line_18_elect_itemize_surface=False,
            is_itemizing=False,
            should_attach_schedule_a=False,
            can_file=True,
        )
        inp = DeductionResolverInputV1(
            tax_year=2025,
            filing_status="SINGLE",
            schedule_a_result=sa_res,
        )
        res = DeductionResolverProcessor.process(inp)

        self.assertEqual(res.status, "COMPLETE")
        self.assertEqual(res.line_12e_deduction, Decimal("15000.00"))
        self.assertEqual(res.line_13a_qbi_deduction, Decimal("0.00"))
        self.assertEqual(res.line_13b_schedule_1a_deductions, Decimal("0.00"))
        self.assertEqual(res.line_14_total_deductions, Decimal("15000.00"))
        self.assertFalse(res.is_itemizing)
        self.assertEqual(res.deduction_type_used, "STANDARD")

    def test_itemized_deduction_chosen_when_larger(self):
        """當 Itemized Deduction 金額大於 Standard Deduction 時，自動選用 Itemized Deduction"""
        sa_res = ScheduleAResultV1(
            standard_deduction_amount=Decimal("15000.00"),
            line_17_total_itemized_deductions=Decimal("22000.00"),
            line_18_elect_itemize_surface=False,
            is_itemizing=True,
            should_attach_schedule_a=True,
            can_file=True,
        )
        inp = DeductionResolverInputV1(
            tax_year=2025,
            filing_status="SINGLE",
            schedule_a_result=sa_res,
        )
        res = DeductionResolverProcessor.process(inp)

        self.assertEqual(res.status, "COMPLETE")
        self.assertEqual(res.line_12e_deduction, Decimal("22000.00"))
        self.assertEqual(res.line_14_total_deductions, Decimal("22000.00"))
        self.assertTrue(res.is_itemizing)
        self.assertEqual(res.deduction_type_used, "ITEMIZED")
        self.assertTrue(res.should_attach_schedule_a)

    def test_elect_itemize_forces_itemized_even_if_smaller(self):
        """當納稅人勾選 Schedule A Line 18 (elect itemize) 時，即便 Itemized Deduction 較小亦強行選用"""
        sa_res = ScheduleAResultV1(
            standard_deduction_amount=Decimal("15000.00"),
            line_17_total_itemized_deductions=Decimal("8000.00"),
            line_18_elect_itemize_surface=True,
            is_itemizing=True,
            should_attach_schedule_a=True,
            can_file=True,
        )
        inp = DeductionResolverInputV1(
            tax_year=2025,
            filing_status="SINGLE",
            schedule_a_result=sa_res,
        )
        res = DeductionResolverProcessor.process(inp)

        self.assertEqual(res.status, "COMPLETE")
        self.assertEqual(res.line_12e_deduction, Decimal("8000.00"))
        self.assertEqual(res.line_14_total_deductions, Decimal("8000.00"))
        self.assertTrue(res.is_itemizing)
        self.assertEqual(res.deduction_type_used, "ITEMIZED")
        self.assertTrue(res.should_attach_schedule_a)

    def test_qbi_and_schedule_1a_included_in_line_14(self):
        """測試 Form 8995 (Line 13a) 與 Schedule 1-A (Line 13b) 正確與 Line 12e 加總至 Line 14"""
        sa_res = ScheduleAResultV1(
            standard_deduction_amount=Decimal("15000.00"),
            line_17_total_itemized_deductions=Decimal("10000.00"),
            can_file=True,
        )
        qbi_res = Form8995ResultV1(line_15_qbi_deduction=Decimal("3500.00"))
        s1a_res = Schedule1AResultV1(line_38_additional_deductions=Decimal("1200.00"))

        inp = DeductionResolverInputV1(
            tax_year=2025,
            filing_status="SINGLE",
            schedule_a_result=sa_res,
            form_8995_result=qbi_res,
            schedule_1a_result=s1a_res,
        )
        res = DeductionResolverProcessor.process(inp)

        self.assertEqual(res.status, "COMPLETE")
        self.assertEqual(res.line_12e_deduction, Decimal("15000.00"))
        self.assertEqual(res.line_13a_qbi_deduction, Decimal("3500.00"))
        self.assertEqual(res.line_13b_schedule_1a_deductions, Decimal("1200.00"))
        self.assertEqual(res.line_14_total_deductions, Decimal("19700.00"))

    def test_fallback_to_standard_deduction_on_schedule_a_issue(self):
        """測試當 Schedule A 回傳 can_file=False 或含有 blocking_errors 時，安全回退至 Standard Deduction 並記錄 warning"""
        sa_res = ScheduleAResultV1(
            standard_deduction_amount=Decimal("15750.00"),
            line_17_total_itemized_deductions=Decimal("10000.00"),
            can_file=False,
            blocking_errors=[
                ProcessingIssueV1(
                    code="UNSUPPORTED_MORTGAGE_CASE",
                    field="mortgage_items",
                    message="Mortgage interest case is unsupported in V1.",
                )
            ],
        )

        inp = DeductionResolverInputV1(
            tax_year=2025,
            filing_status="SINGLE",
            schedule_a_result=sa_res,
        )
        res = DeductionResolverProcessor.process(inp)

        self.assertEqual(res.status, "COMPLETE")
        self.assertTrue(res.can_continue)
        self.assertEqual(res.deduction_type_used, "STANDARD")
        self.assertEqual(res.line_12e_deduction, Decimal("15750.00"))
        self.assertTrue(len(res.review_warnings) >= 1)


    def test_to_dict_formatting(self):
        """測試 DeductionResolverResultV1.to_dict 格式轉換正常"""
        inp = DeductionResolverInputV1(
            tax_year=2025,
            filing_status="SINGLE",
            schedule_a_result=ScheduleAResultV1(
                standard_deduction_amount=Decimal("15000.00"),
                line_17_total_itemized_deductions=Decimal("0.00"),
            ),
        )
        res = DeductionResolverProcessor.process(inp)
        res_dict = res.to_dict()
        self.assertEqual(res_dict["line_12e_deduction"], 15000.0)
        self.assertEqual(res_dict["line_14_total_deductions"], 15000.0)
        self.assertEqual(res_dict["status"], "COMPLETE")


if __name__ == "__main__":
    unittest.main()
