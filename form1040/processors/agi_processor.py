from form1040.models.agi_model import (
    AGIProcessorInputV1,
    AGIProcessorResultV1,
)
from form1040.validators.agi_validator import AGIValidator
from form1040.calculators.agi_calculator import AGICalculator


def process(data: AGIProcessorInputV1) -> AGIProcessorResultV1:
    """AGI 處理邏輯進入點，調度 Validator 與 Calculator"""
    errors = AGIValidator.validate(data)
    if errors:
        return AGIProcessorResultV1(
            line_9_total_income=data.line_9_total_income,
            line_10_adjustments_to_income=None,
            line_11_adjusted_gross_income=None,
            status="BLOCKED",
            can_continue=False,
            blocking_errors=errors,
        )

    return AGICalculator.calculate(data)


class AGIProcessor:
    """AGI Processor 統一進入點類別"""

    @staticmethod
    def process(data: AGIProcessorInputV1) -> AGIProcessorResultV1:
        return process(data)
