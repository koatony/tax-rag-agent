from decimal import Decimal
from typing import Any, List, Optional
from form1040.models.agi_model import ProcessingIssueV1, AGIProcessorInputV1


def is_finite_decimal(val: Any) -> bool:
    if not isinstance(val, Decimal):
        try:
            val = Decimal(str(val))
        except Exception:
            return False
    return val.is_finite()


class AGIValidator:
    """
    AGI 輸入驗證器
    """

    @staticmethod
    def validate(data: AGIProcessorInputV1) -> List[ProcessingIssueV1]:
        errors: List[ProcessingIssueV1] = []

        # Line 9 validation
        if data.line_9_total_income is None:
            errors.append(
                ProcessingIssueV1(
                    code="MISSING_LINE_9",
                    field="line_9_total_income",
                    message="Form 1040 Line 9 is required before AGI can be calculated.",
                )
            )
        elif not is_finite_decimal(data.line_9_total_income):
            errors.append(
                ProcessingIssueV1(
                    code="INVALID_AMOUNT",
                    field="line_9_total_income",
                    message="Form 1040 Line 9 total income must be a valid finite Decimal.",
                )
            )

        # Schedule 1 Line 26 validation
        if data.schedule1_line_26_adjustments is None:
            errors.append(
                ProcessingIssueV1(
                    code="MISSING_SCHEDULE1_LINE_26",
                    field="schedule1_line_26_adjustments",
                    message="Schedule 1 Line 26 adjustments is required before AGI can be calculated.",
                )
            )
        elif not is_finite_decimal(data.schedule1_line_26_adjustments):
            errors.append(
                ProcessingIssueV1(
                    code="INVALID_AMOUNT",
                    field="schedule1_line_26_adjustments",
                    message="Schedule 1 Line 26 adjustments must be a valid finite Decimal.",
                )
            )
        elif data.schedule1_line_26_adjustments < Decimal("0"):
            errors.append(
                ProcessingIssueV1(
                    code="NEGATIVE_ADJUSTMENTS",
                    field="schedule1_line_26_adjustments",
                    message="Schedule 1 Line 26 adjustments cannot be negative.",
                )
            )

        return errors
