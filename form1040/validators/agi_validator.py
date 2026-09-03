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

        # 必須從 schedule_1_result 中取得 Line 26 調整值，不接受任何其他回退方式
        adjustments = None
        s1_res = data.schedule_1_result
        if s1_res is None:
            errors.append(
                ProcessingIssueV1(
                    code="MISSING_SCHEDULE_1_RESULT",
                    field="schedule_1_result",
                    message="Schedule 1 result is required to compute adjustments to income (Line 10).",
                )
            )
        else:
            # 檢查上游 Schedule 1 是否執行阻斷
            s1_status = getattr(s1_res, "status", None) or (s1_res.get("status") if isinstance(s1_res, dict) else None)
            s1_can_continue = getattr(s1_res, "can_continue", None)
            if isinstance(s1_res, dict):
                s1_can_continue = s1_res.get("can_continue", s1_can_continue)
            if s1_status == "BLOCKED" and s1_can_continue is not True:
                errors.append(
                    ProcessingIssueV1(
                        code="SCHEDULE_1_MODULE_BLOCKED",
                        field="schedule_1_result",
                        message="Schedule 1 module execution was blocked.",
                    )
                )
            
            if hasattr(s1_res, "line_26_adjustments_to_income"):
                adjustments = getattr(s1_res, "line_26_adjustments_to_income")
            elif isinstance(s1_res, dict):
                adjustments = s1_res.get("line_26_adjustments_to_income")
                if adjustments is None:
                    adjustments = s1_res.get("line26")
            
            if adjustments is not None:
                try:
                    adjustments = Decimal(str(adjustments))
                except Exception:
                    pass

        # Schedule 1 Line 26 validation
        if s1_res is not None and adjustments is None:
            errors.append(
                ProcessingIssueV1(
                    code="MISSING_SCHEDULE1_LINE_26",
                    field="schedule_1_result",
                    message="Schedule 1 Line 26 adjustments is required before AGI can be calculated.",
                )
            )
        elif adjustments is not None:
            if not is_finite_decimal(adjustments):
                errors.append(
                    ProcessingIssueV1(
                        code="INVALID_AMOUNT",
                        field="schedule_1_result",
                        message="Schedule 1 Line 26 adjustments must be a valid finite Decimal.",
                    )
                )
            elif adjustments < Decimal("0"):
                errors.append(
                    ProcessingIssueV1(
                        code="NEGATIVE_ADJUSTMENTS",
                        field="schedule_1_result",
                        message="Schedule 1 Line 26 adjustments cannot be negative.",
                    )
                )

        return errors
