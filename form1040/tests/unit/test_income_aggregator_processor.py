from decimal import Decimal
import unittest

from form1040.models.income_aggregator_model import (
    IncomeAggregatorInputV1,
    DirectIncomeInputV1,
    DirectIncomeItemV1,
    W2ItemV1,
    ScheduleBResultV1,
    ScheduleDResultV1,
    Schedule1ResultV1,
)
from form1040.processors.income_aggregator_processor import IncomeAggregatorProcessor


class TestIncomeAggregatorProcessor(unittest.TestCase):

    def test_income_aggregator_0622_case(self):
        """
        測試 0622 標竿案例：
        W-2 Wages: $46,000 + $54,000 = $100,000 (Line 1z)
        Schedule B Taxable Interest: $150 (Line 2b)
        Schedule B Ordinary Dividends: $405 (Line 3b)
        Capital Loss: $0 (Line 7a)
        Schedule 1 Additional Income: $0 (Line 8)
        預期 Line 9 = 100000 + 150 + 405 + 0 + 0 = 100555
        """
        direct_income = DirectIncomeInputV1(
            w2_items=[
                W2ItemV1(
                    employee_name="Marcus Rivera",
                    box_1_wages=Decimal("46000"),
                    tax_year=2025,
                    source_document_id="sample_01",
                ),
                W2ItemV1(
                    employee_name="Elena Rivera",
                    box_1_wages=Decimal("54000"),
                    tax_year=2025,
                    source_document_id="sample_02",
                ),
            ],
            ira_distribution=DirectIncomeItemV1(gross_amount=Decimal("0"), taxable_amount=Decimal("0")),
            pension_annuity=DirectIncomeItemV1(gross_amount=Decimal("0"), taxable_amount=Decimal("0")),
            social_security=DirectIncomeItemV1(gross_amount=Decimal("0"), taxable_amount=Decimal("0")),
        )

        sb_result = ScheduleBResultV1(
            form_1040_line_2a=Decimal("0"),
            line_4_surface_value=Decimal("150"),
            total_qualified_dividends=Decimal("0"),
            line_6_total_ordinary_dividends=Decimal("405"),
            status="COMPLETE",
        )

        sd_result = ScheduleDResultV1(
            line_7_capital_gain_or_loss=Decimal("0"),
            status="COMPLETE",
        )

        s1_result = Schedule1ResultV1(
            line_10_additional_income=Decimal("0"),
            status="COMPLETE",
        )

        inp = IncomeAggregatorInputV1(
            tax_year=2025,
            filing_status="MFJ",
            direct_income_input=direct_income,
            schedule_b_result=sb_result,
            schedule_d_result=sd_result,
            schedule_1_result=s1_result,
        )
        result = IncomeAggregatorProcessor.process(inp)

        self.assertEqual(result.status, "COMPLETE")
        self.assertTrue(result.can_continue)
        self.assertEqual(len(result.blocking_errors), 0)
        self.assertEqual(result.line_1a, Decimal("100000"))
        self.assertEqual(result.line_1z, Decimal("100000"))
        self.assertEqual(result.line_2b, Decimal("150"))
        self.assertEqual(result.line_3b, Decimal("405"))
        self.assertEqual(result.line_7a, Decimal("0"))
        self.assertEqual(result.line_8, Decimal("0"))
        self.assertEqual(result.line_9, Decimal("100555"))

    def test_tax_year_mismatch_triggers_blocking_error(self):
        """
        測試 W-2 年度與申報年度不符時，觸發 TAX_YEAR_MISMATCH 阻斷錯誤
        """
        direct_income = DirectIncomeInputV1(
            w2_items=[
                W2ItemV1(
                    employee_name="Marcus Rivera",
                    box_1_wages=Decimal("46000"),
                    tax_year=2024,  # Mismatch! Filing tax_year is 2025
                )
            ]
        )

        inp = IncomeAggregatorInputV1(
            tax_year=2025,
            filing_status="MFJ",
            direct_income_input=direct_income,
        )
        result = IncomeAggregatorProcessor.process(inp)

        self.assertEqual(result.status, "BLOCKED")
        self.assertFalse(result.can_continue)
        self.assertEqual(len(result.blocking_errors), 1)
        self.assertEqual(result.blocking_errors[0].code, "TAX_YEAR_MISMATCH")

    def test_requires_calculation_triggers_blocking_error(self):
        """
        測試 Lines 4-6 若標註需要複雜計算，觸發阻斷
        """
        direct_income = DirectIncomeInputV1(
            ira_distribution=DirectIncomeItemV1(
                gross_amount=Decimal("5000"),
                taxable_amount=Decimal("0"),
                status="TAXABILITY_REQUIRES_CALCULATION",
            )
        )

        inp = IncomeAggregatorInputV1(
            tax_year=2025,
            filing_status="MFJ",
            direct_income_input=direct_income,
        )
        result = IncomeAggregatorProcessor.process(inp)

        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.blocking_errors[0].code, "TAXABILITY_REQUIRES_CALCULATION")

    def test_upstream_schedule_b_blocked(self):
        """
        測試 Schedule B 若為 BLOCKED 狀態，阻斷 IncomeAggregator
        """
        direct_income = DirectIncomeInputV1()
        sb_result = ScheduleBResultV1(status="BLOCKED", can_continue=False)

        inp = IncomeAggregatorInputV1(
            tax_year=2025,
            filing_status="MFJ",
            direct_income_input=direct_income,
            schedule_b_result=sb_result,
        )
        result = IncomeAggregatorProcessor.process(inp)

        self.assertEqual(result.status, "BLOCKED")
        self.assertFalse(result.can_continue)

    def test_blocked_but_calculated_schedule_1_preserves_known_income(self):
        issue = {
            "code": "UNSUPPORTED_FORM_4797_4684",
            "field": "line_4_other_gains_or_losses",
            "message": "Form 4684 is not supported in V1.",
        }
        inp = IncomeAggregatorInputV1(
            tax_year=2025,
            filing_status="MFJ",
            direct_income_input=DirectIncomeInputV1(
                w2_items=[W2ItemV1(box_1_wages=Decimal("32000"), tax_year=2025)]
            ),
            schedule_1_result=Schedule1ResultV1(
                line_10_additional_income=Decimal("1650"),
                line_26_adjustments_to_income=Decimal("0"),
                status="BLOCKED",
                can_continue=True,
                can_file=False,
                is_v1_supported=False,
                blocking_errors=[issue],
            ),
        )

        result = IncomeAggregatorProcessor.process(inp)

        self.assertEqual(result.line_1a, Decimal("32000"))
        self.assertEqual(result.line_8, Decimal("1650"))
        self.assertEqual(result.line_9, Decimal("33650"))
        self.assertEqual(result.status, "COMPLETE")
        self.assertTrue(result.can_continue)
        self.assertFalse(result.can_file)
        self.assertFalse(result.is_v1_supported)
        self.assertEqual(result.blocking_errors[0].code, "UNSUPPORTED_FORM_4797_4684")

    def test_dict_input_parsing(self):
        """
        測試以 Raw Dictionary 傳入時的解析與算術
        """
        raw_dict = {
            "w2_items": [
                {"employee_name": "Alice", "box_1_wages": "60000", "tax_year": 2025},
                {"employee_name": "Bob", "box_1_wages": "40000", "tax_year": 2025},
            ]
        }

        inp = IncomeAggregatorInputV1(
            tax_year=2025,
            filing_status="Single",
            direct_income_input=raw_dict,
        )
        result = IncomeAggregatorProcessor.process(inp)

        self.assertEqual(result.status, "COMPLETE")

    def test_single_filing_ssn_filtering_and_sanitation(self):
        """
        測試 Single 身分下依據 SSN 過濾 W-2：
        1. 符號破折號會自動清理 ('555-12-3456' vs '555123456')。
        2. 只計入與納稅人 SSN 相符的 W-2。
        3. 不相符的 W-2 不計入 Line 1a，並產生非阻斷 review_warning。
        """
        direct_income = DirectIncomeInputV1(
            w2_items=[
                W2ItemV1(
                    employee_name="Marcus Rivera",
                    employee_ssn="555-12-3456",
                    box_1_wages=Decimal("46000"),
                ),
                W2ItemV1(
                    employee_name="Elena Rivera",
                    employee_ssn="555-23-4567",
                    box_1_wages=Decimal("54000"),
                ),
            ]
        )

        inp = IncomeAggregatorInputV1(
            tax_year=2025,
            filing_status="SINGLE",
            taxpayer_ssn="555123456",  # 無符號格式
            direct_income_input=direct_income,
        )
        result = IncomeAggregatorProcessor.process(inp)

        self.assertEqual(result.status, "COMPLETE")
        self.assertTrue(result.can_continue)
        self.assertEqual(result.line_1a, Decimal("46000"))  # 只包含 Marcus
        self.assertEqual(len(result.review_warnings), 1)
        self.assertEqual(result.review_warnings[0].code, "W2_SSN_MISMATCH")

    def test_mfs_filing_ssn_filtering(self):
        """
        測試 MFS (夫妻分申) 身分下依據 SSN 過濾：
        1. 只計入與 Elena SSN 相符的 W-2。
        """
        direct_income = DirectIncomeInputV1(
            w2_items=[
                W2ItemV1(
                    employee_name="Marcus Rivera",
                    employee_ssn="555-12-3456",
                    box_1_wages=Decimal("46000"),
                ),
                W2ItemV1(
                    employee_name="Elena Rivera",
                    employee_ssn="555-23-4567",
                    box_1_wages=Decimal("54000"),
                ),
            ]
        )

        inp = IncomeAggregatorInputV1(
            tax_year=2025,
            filing_status="MFS",
            taxpayer_ssn="555-23-4567",  # 帶符號格式
            direct_income_input=direct_income,
        )
        result = IncomeAggregatorProcessor.process(inp)

        self.assertEqual(result.status, "COMPLETE")
        self.assertTrue(result.can_continue)
        self.assertEqual(result.line_1a, Decimal("54000"))  # 只包含 Elena
        self.assertEqual(len(result.review_warnings), 1)
        self.assertEqual(result.review_warnings[0].code, "W2_SSN_MISMATCH")

    def test_mfj_filing_includes_all_w2s(self):
        """
        測試 MFJ (夫妻合申) 身分下合併所有 W-2
        """
        direct_income = DirectIncomeInputV1(
            w2_items=[
                W2ItemV1(
                    employee_name="Marcus Rivera",
                    employee_ssn="555-12-3456",
                    box_1_wages=Decimal("46000"),
                ),
                W2ItemV1(
                    employee_name="Elena Rivera",
                    employee_ssn="555-23-4567",
                    box_1_wages=Decimal("54000"),
                ),
            ]
        )

        inp = IncomeAggregatorInputV1(
            tax_year=2025,
            filing_status="MFJ",
            taxpayer_ssn="555-12-3456",
            direct_income_input=direct_income,
        )
        result = IncomeAggregatorProcessor.process(inp)

        self.assertEqual(result.status, "COMPLETE")
        self.assertEqual(result.line_1a, Decimal("100000"))  # 兩筆均包含
        self.assertEqual(len(result.review_warnings), 0)

    def test_parse_1099r_federal_withholding(self):
        """
        測試 DirectIncomeItemV1 解析器能精確提取 1099-R / Pension / IRA 之 federal_withholding
        """
        from form1040.parsers.income_aggregator_direct_income_parser import IncomeAggregatorDirectIncomeParser
        raw = {
            "pension_annuity": {
                "gross_amount": 15000.0,
                "taxable_amount": 15000.0,
                "federal_withholding": 1100.0
            }
        }
        res = IncomeAggregatorDirectIncomeParser.parse_dict(raw)
        self.assertIsNotNone(res.pension_annuity)
        self.assertEqual(res.pension_annuity.federal_withholding, Decimal("1100.0"))


if __name__ == "__main__":
    unittest.main()
