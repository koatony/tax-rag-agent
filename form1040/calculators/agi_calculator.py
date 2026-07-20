from form1040.models.agi_model import AGIProcessorInputV1, AGIProcessorResultV1


class AGICalculator:
    """
    AGI 算術引擎 (Form 1040 Line 11 = Line 9 - Line 10)
    """

    @staticmethod
    def calculate(data: AGIProcessorInputV1) -> AGIProcessorResultV1:
        line_10 = data.schedule1_line_26_adjustments
        line_9 = data.line_9_total_income
        line_11 = line_9 - line_10

        return AGIProcessorResultV1(
            line_9_total_income=line_9,
            line_10_adjustments_to_income=line_10,
            line_11_adjusted_gross_income=line_11,
            status="COMPLETE",
            can_continue=True,
            blocking_errors=[],
        )
