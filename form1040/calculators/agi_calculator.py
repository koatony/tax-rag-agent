from decimal import Decimal
from form1040.models.agi_model import (
    AGIProcessorInputV1,
    AGIProcessorResultV1,
    ProcessingIssueV1,
)


class AGICalculator:
    """
    AGI 算術引擎 (Form 1040 Line 11 = Line 9 - Line 10)
    """

    @staticmethod
    def calculate(data: AGIProcessorInputV1) -> AGIProcessorResultV1:
        # 從 schedule_1_result 中取得 Line 26 調整值
        line_10 = Decimal("0")
        s1_res = data.schedule_1_result
        if s1_res is not None:
            val = None
            if hasattr(s1_res, "line_26_adjustments_to_income"):
                val = getattr(s1_res, "line_26_adjustments_to_income")
            elif isinstance(s1_res, dict):
                val = s1_res.get("line_26_adjustments_to_income")
                if val is None:
                    val = s1_res.get("line26")
            
            if val is not None:
                line_10 = Decimal(str(val))

        line_9 = data.line_9_total_income
        
        # 計算 Form 1040 Line 11 (AGI = Line 9 - Line 10)
        line_11 = None
        if line_9 is not None and line_10 is not None:
            line_11 = line_9 - line_10

        s1_status = getattr(s1_res, "status", None) if s1_res is not None else None
        s1_can_file = getattr(s1_res, "can_file", True) if s1_res is not None else True
        s1_is_supported = getattr(s1_res, "is_v1_supported", True) if s1_res is not None else True
        s1_errors = getattr(s1_res, "blocking_errors", []) if s1_res is not None else []
        if isinstance(s1_res, dict):
            s1_status = s1_res.get("status", s1_status)
            s1_can_file = s1_res.get("can_file", s1_can_file)
            s1_is_supported = s1_res.get("is_v1_supported", s1_is_supported)
            s1_errors = s1_res.get("blocking_errors", s1_errors)
        upstream_is_unfileable = bool(
            not s1_can_file
            or not s1_is_supported
            or s1_errors
        )
        normalized_errors = []
        for error in s1_errors or []:
            if isinstance(error, ProcessingIssueV1):
                normalized_errors.append(error)
            elif isinstance(error, dict):
                normalized_errors.append(ProcessingIssueV1(**error))
            else:
                normalized_errors.append(ProcessingIssueV1(
                    code=getattr(error, "code", "SCHEDULE_1_ERROR"),
                    field=getattr(error, "field", "schedule_1_result"),
                    message=getattr(error, "message", str(error)),
                ))

        return AGIProcessorResultV1(
            line_9_total_income=line_9,
            line_10_adjustments_to_income=line_10,
            line_11_adjusted_gross_income=line_11,
            status="COMPLETE",
            can_continue=True,
            can_file=not upstream_is_unfileable,
            is_v1_supported=not upstream_is_unfileable,
            blocking_errors=normalized_errors,
        )
