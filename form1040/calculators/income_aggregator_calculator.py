from decimal import Decimal
from form1040.models.income_aggregator_model import (
    IncomeAggregatorInputV1,
    IncomeSectionResultV1,
)


class IncomeAggregatorCalculator:
    """
    IncomeAggregator 純確定性算術引擎
    專注執行 Form 1040 Lines 1a–9 的精確 Decimal 加總與項目映射。
    """

    @staticmethod
    def calculate(input_dto: IncomeAggregatorInputV1) -> IncomeSectionResultV1:
        direct_input = input_dto.direct_income_input
        sb = input_dto.schedule_b_result
        sd = input_dto.schedule_d_result
        s1 = input_dto.schedule_1_result

        # Line 1a & Line 1z (W-2 Wages 加總)
        w2_wages_sum = Decimal("0")
        if direct_input and direct_input.w2_items:
            for w2 in direct_input.w2_items:
                w2_wages_sum += w2.box_1_wages

        line_1a = w2_wages_sum
        line_1z = line_1a

        # Lines 2a, 2b, 3a, 3b (Schedule B)
        line_2a = sb.form_1040_line_2a if sb else Decimal("0")
        line_2b = sb.line_4_surface_value if sb else Decimal("0")
        line_3a = sb.total_qualified_dividends if sb else Decimal("0")
        line_3b = sb.line_6_total_ordinary_dividends if sb else Decimal("0")

        # Lines 4a, 4b (IRA Distributions)
        ira = direct_input.ira_distribution if direct_input else None
        line_4a = ira.gross_amount if ira else Decimal("0")
        line_4b = ira.taxable_amount if ira else Decimal("0")

        # Lines 5a, 5b (Pensions & Annuities)
        pension = direct_input.pension_annuity if direct_input else None
        line_5a = pension.gross_amount if pension else Decimal("0")
        line_5b = pension.taxable_amount if pension else Decimal("0")

        # Lines 6a, 6b (Social Security Benefits)
        ss = direct_input.social_security if direct_input else None
        line_6a = ss.gross_amount if ss else Decimal("0")
        line_6b = ss.taxable_amount if ss else Decimal("0")

        # Line 7a (Schedule D Capital Gain or Loss)
        line_7a = Decimal("0")
        if sd and sd.line_7_capital_gain_or_loss is not None:
            line_7a = sd.line_7_capital_gain_or_loss

        # Line 8 (Schedule 1 Line 10 Additional Income)
        line_8 = s1.line_10_additional_income if s1 else Decimal("0")

        # Line 9 (Total Income = 1z + 2b + 3b + 4b + 5b + 6b + 7a + 8)
        line_9 = line_1z + line_2b + line_3b + line_4b + line_5b + line_6b + line_7a + line_8

        return IncomeSectionResultV1(
            tax_year=input_dto.tax_year,
            filing_status=input_dto.filing_status,
            line_1a=line_1a,
            line_1z=line_1z,
            line_2a=line_2a,
            line_2b=line_2b,
            line_3a=line_3a,
            line_3b=line_3b,
            line_4a=line_4a,
            line_4b=line_4b,
            line_5a=line_5a,
            line_5b=line_5b,
            line_6a=line_6a,
            line_6b=line_6b,
            line_7a=line_7a,
            line_8=line_8,
            line_9=line_9,
            status="COMPLETE",
            can_continue=True,
            blocking_errors=[],
            review_warnings=[],
        )
