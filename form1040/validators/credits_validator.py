from decimal import Decimal
from typing import Any, List, Optional, Tuple
from form1040.models.credits_model import ProcessingIssueV1, CreditsProcessorInputV1


def is_finite_decimal(val: Any) -> bool:
    if not isinstance(val, Decimal):
        try:
            val = Decimal(str(val))
        except Exception:
            return False
    return val.is_finite()


def _get_status(schedule_res: Any) -> Optional[str]:
    if schedule_res is None:
        return None
    return getattr(schedule_res, "status", None) or (
        schedule_res.get("status") if isinstance(schedule_res, dict) else None
    )


def _get_field(schedule_res: Any, attr_name: str) -> Any:
    if schedule_res is None:
        return None
    if hasattr(schedule_res, attr_name):
        return getattr(schedule_res, attr_name)
    if isinstance(schedule_res, dict):
        return schedule_res.get(attr_name)
    return None


def _validate_schedule_amount(
    schedule_res: Any,
    attr_name: str,
    schedule_label: str,
    missing_result_code: str,
    blocked_code: str,
    missing_amount_code: str,
    invalid_amount_code: str,
    negative_amount_code: str,
    field_name: str,
) -> Tuple[Optional[Decimal], List[ProcessingIssueV1]]:
    """
    驗證單一 Schedule 子結果，回傳 (amount, errors)。

    Zero Policy 區分：
    - schedule_res 為 None → 上游根本沒有執行/傳入該 Schedule → 阻斷（MISSING_*_RESULT）。
    - schedule_res.status == "BLOCKED" → 上游模組執行阻斷 → 阻斷。
    - schedule_res 存在但金額欄位為 None：
        - 若 schedule_res.status == "CONFIRMED_NOT_PRESENT" → 合法情況（例如納稅人本來就沒有
          dependents，Schedule 8812 結果本來就是 0），視為 Decimal("0")，不阻斷。
        - 否則視為資料未提取或上游出錯 → 阻斷（MISSING_*_LINE）。
    """
    errors: List[ProcessingIssueV1] = []

    if schedule_res is None:
        errors.append(
            ProcessingIssueV1(
                code=missing_result_code,
                field=field_name,
                message=f"{schedule_label} result is required to compute Line 19-24 credits.",
            )
        )
        return None, errors

    status = _get_status(schedule_res)
    if status == "BLOCKED":
        errors.append(
            ProcessingIssueV1(
                code=blocked_code,
                field=field_name,
                message=f"{schedule_label} module execution was blocked.",
            )
        )

    amount = _get_field(schedule_res, attr_name)

    if amount is None:
        if status == "CONFIRMED_NOT_PRESENT":
            return Decimal("0"), errors
        errors.append(
            ProcessingIssueV1(
                code=missing_amount_code,
                field=field_name,
                message=f"{schedule_label} amount is required before credits can be calculated.",
            )
        )
        return None, errors

    try:
        amount = Decimal(str(amount))
    except Exception:
        errors.append(
            ProcessingIssueV1(
                code=invalid_amount_code,
                field=field_name,
                message=f"{schedule_label} amount must be a valid finite Decimal.",
            )
        )
        return None, errors

    if not is_finite_decimal(amount):
        errors.append(
            ProcessingIssueV1(
                code=invalid_amount_code,
                field=field_name,
                message=f"{schedule_label} amount must be a valid finite Decimal.",
            )
        )
        return None, errors

    if amount < Decimal("0"):
        errors.append(
            ProcessingIssueV1(
                code=negative_amount_code,
                field=field_name,
                message=f"{schedule_label} amount cannot be negative.",
            )
        )
        return None, errors

    return amount, errors


class CreditsValidator:
    """
    Credits 輸入驗證器 (Form 1040 Lines 19-24)
    """

    @staticmethod
    def validate(data: CreditsProcessorInputV1) -> List[ProcessingIssueV1]:
        errors: List[ProcessingIssueV1] = []

        # Line 18 validation — Zero Policy: None 代表上游未計算或出錯，禁止補 0
        if data.line_18_tax_before_credits is None:
            errors.append(
                ProcessingIssueV1(
                    code="MISSING_LINE_18",
                    field="line_18_tax_before_credits",
                    message="Form 1040 Line 18 (tax before credits) is required before credits can be calculated.",
                )
            )
        elif not is_finite_decimal(data.line_18_tax_before_credits):
            errors.append(
                ProcessingIssueV1(
                    code="INVALID_AMOUNT",
                    field="line_18_tax_before_credits",
                    message="Form 1040 Line 18 must be a valid finite Decimal.",
                )
            )

        # Line 19 — Schedule 8812
        _, sched_8812_errors = _validate_schedule_amount(
            data.schedule_8812_result,
            "total_ctc_odc",
            "Schedule 8812",
            missing_result_code="MISSING_SCHEDULE_8812_RESULT",
            blocked_code="SCHEDULE_8812_MODULE_BLOCKED",
            missing_amount_code="MISSING_SCHEDULE_8812_TOTAL_CTC_ODC",
            invalid_amount_code="INVALID_AMOUNT",
            negative_amount_code="NEGATIVE_SCHEDULE_8812_AMOUNT",
            field_name="schedule_8812_result",
        )
        errors.extend(sched_8812_errors)

        # Line 20 — Schedule 3, Line 8
        _, sched_3_errors = _validate_schedule_amount(
            data.schedule_3_result,
            "line_8_total",
            "Schedule 3",
            missing_result_code="MISSING_SCHEDULE_3_RESULT",
            blocked_code="SCHEDULE_3_MODULE_BLOCKED",
            missing_amount_code="MISSING_SCHEDULE_3_LINE_8",
            invalid_amount_code="INVALID_AMOUNT",
            negative_amount_code="NEGATIVE_SCHEDULE_3_AMOUNT",
            field_name="schedule_3_result",
        )
        errors.extend(sched_3_errors)

        # Line 23 — Schedule 2, Line 21
        _, sched_2_errors = _validate_schedule_amount(
            data.schedule_2_result,
            "line_21_total",
            "Schedule 2",
            missing_result_code="MISSING_SCHEDULE_2_RESULT",
            blocked_code="SCHEDULE_2_MODULE_BLOCKED",
            missing_amount_code="MISSING_SCHEDULE_2_LINE_21",
            invalid_amount_code="INVALID_AMOUNT",
            negative_amount_code="NEGATIVE_SCHEDULE_2_AMOUNT",
            field_name="schedule_2_result",
        )
        errors.extend(sched_2_errors)

        return errors
