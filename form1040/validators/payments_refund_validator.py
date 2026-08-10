from decimal import Decimal
from typing import Any, List, Optional, Tuple
from form1040.models.payments_refund_model import (
    ProcessingIssueV1,
    PaymentsAndRefundProcessorInputV1,
)
from form1040.calculators.payments_refund_calculator import compute_totals


def is_finite_decimal(val: Any) -> bool:
    if not isinstance(val, Decimal):
        try:
            val = Decimal(str(val))
        except Exception:
            return False
    return val.is_finite()


def _get_status(result_obj: Any) -> Optional[str]:
    if result_obj is None:
        return None
    return getattr(result_obj, "status", None) or (
        result_obj.get("status") if isinstance(result_obj, dict) else None
    )


def _get_field(result_obj: Any, attr_name: str) -> Any:
    if result_obj is None:
        return None
    if hasattr(result_obj, attr_name):
        return getattr(result_obj, attr_name)
    if isinstance(result_obj, dict):
        return result_obj.get(attr_name)
    return None


def _validate_result_amount(
    result_obj: Any,
    attr_name: str,
    label: str,
    missing_result_code: str,
    blocked_code: str,
    missing_amount_code: str,
    invalid_amount_code: str,
    negative_amount_code: str,
    field_name: str,
) -> Tuple[Optional[Decimal], List[ProcessingIssueV1]]:
    """
    驗證單一上游子結果的金額欄位，回傳 (amount, errors)。

    Zero Policy 區分：
    - result_obj 為 None → 上游根本沒有執行/傳入 → 阻斷（MISSING_*_RESULT）。
    - result_obj.status == "BLOCKED" → 上游模組執行阻斷 → 阻斷。
    - result_obj 存在但金額欄位為 None：
        - 若 result_obj.status == "CONFIRMED_NOT_PRESENT" → 合法的「金額本來就是 0」情況，
          視為 Decimal("0")，不阻斷。
        - 否則視為「資料未提取」→ 阻斷（MISSING_*_LINE），不可補 0。
    """
    errors: List[ProcessingIssueV1] = []

    if result_obj is None:
        errors.append(
            ProcessingIssueV1(
                code=missing_result_code,
                field=field_name,
                message=f"{label} result is required to compute Line 25-38 payments/refund.",
            )
        )
        return None, errors

    status = _get_status(result_obj)
    if status == "BLOCKED":
        errors.append(
            ProcessingIssueV1(
                code=blocked_code,
                field=field_name,
                message=f"{label} module execution was blocked.",
            )
        )

    amount = _get_field(result_obj, attr_name)

    if amount is None:
        if status == "CONFIRMED_NOT_PRESENT":
            return Decimal("0"), errors
        errors.append(
            ProcessingIssueV1(
                code=missing_amount_code,
                field=field_name,
                message=f"{label} amount is required before payments/refund can be calculated.",
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
                message=f"{label} amount must be a valid finite Decimal.",
            )
        )
        return None, errors

    if not is_finite_decimal(amount):
        errors.append(
            ProcessingIssueV1(
                code=invalid_amount_code,
                field=field_name,
                message=f"{label} amount must be a valid finite Decimal.",
            )
        )
        return None, errors

    if amount < Decimal("0"):
        errors.append(
            ProcessingIssueV1(
                code=negative_amount_code,
                field=field_name,
                message=f"{label} amount cannot be negative.",
            )
        )
        return None, errors

    return amount, errors


class PaymentsAndRefundValidator:
    """
    PaymentsAndRefund 輸入驗證器 (Form 1040 Lines 25-38)
    """

    @staticmethod
    def validate(data: PaymentsAndRefundProcessorInputV1) -> List[ProcessingIssueV1]:
        errors: List[ProcessingIssueV1] = []

        # Line 24 validation — Zero Policy: None 代表上游 CreditsProcessor 未計算或出錯，
        # 觸發 MISSING_LINE_24 阻斷錯誤，禁止補 0
        line_24: Optional[Decimal] = None
        if data.line_24_total_tax is None:
            errors.append(
                ProcessingIssueV1(
                    code="MISSING_LINE_24",
                    field="line_24_total_tax",
                    message="Form 1040 Line 24 (total tax) from CreditsProcessor is required before payments/refund can be calculated.",
                )
            )
        elif not is_finite_decimal(data.line_24_total_tax):
            errors.append(
                ProcessingIssueV1(
                    code="INVALID_AMOUNT",
                    field="line_24_total_tax",
                    message="Form 1040 Line 24 must be a valid finite Decimal.",
                )
            )
        else:
            line_24 = data.line_24_total_tax

        # withholding_result 若整體缺失 → 一次性回報，不逐欄位重複報 MISSING_RESULT
        withholding_res = data.withholding_result
        line_25a: Optional[Decimal] = None
        line_25b: Optional[Decimal] = None
        line_25c: Optional[Decimal] = None

        if withholding_res is None:
            errors.append(
                ProcessingIssueV1(
                    code="MISSING_WITHHOLDING_RESULT",
                    field="withholding_result",
                    message="Withholding result is required to compute Line 25a-25c.",
                )
            )
        else:
            wh_status = _get_status(withholding_res)
            if wh_status == "BLOCKED":
                errors.append(
                    ProcessingIssueV1(
                        code="WITHHOLDING_MODULE_BLOCKED",
                        field="withholding_result",
                        message="Withholding module execution was blocked.",
                    )
                )

            for attr, code_prefix, field_label, target_attr_name in (
                ("w2_withholding", "MISSING_LINE_25A_W2_WITHHOLDING", "Line 25a W-2 withholding", "line_25a"),
                ("form1099_withholding", "MISSING_LINE_25B_1099_WITHHOLDING", "Line 25b 1099 withholding", "line_25b"),
                ("other_withholding", "MISSING_LINE_25C_OTHER_WITHHOLDING", "Line 25c other withholding", "line_25c"),
            ):
                amount = _get_field(withholding_res, attr)
                if amount is None:
                    if wh_status == "CONFIRMED_NOT_PRESENT":
                        amount = Decimal("0")
                    else:
                        errors.append(
                            ProcessingIssueV1(
                                code=code_prefix,
                                field="withholding_result",
                                message=f"{field_label} is required (data not yet extracted).",
                            )
                        )
                        continue
                else:
                    try:
                        amount = Decimal(str(amount))
                    except Exception:
                        errors.append(
                            ProcessingIssueV1(
                                code="INVALID_AMOUNT",
                                field="withholding_result",
                                message=f"{field_label} must be a valid finite Decimal.",
                            )
                        )
                        continue
                    if not is_finite_decimal(amount) or amount < Decimal("0"):
                        errors.append(
                            ProcessingIssueV1(
                                code="INVALID_AMOUNT" if not is_finite_decimal(amount) else "NEGATIVE_WITHHOLDING_AMOUNT",
                                field="withholding_result",
                                message=f"{field_label} must be a valid, non-negative finite Decimal.",
                            )
                        )
                        continue

                if target_attr_name == "line_25a":
                    line_25a = amount
                elif target_attr_name == "line_25b":
                    line_25b = amount
                else:
                    line_25c = amount

        # Line 26 — 納稅人申報之預估稅款繳納 (直接欄位，非子結果)
        line_26: Optional[Decimal] = None
        if data.estimated_payments is None:
            errors.append(
                ProcessingIssueV1(
                    code="MISSING_LINE_26",
                    field="estimated_payments",
                    message="Line 26 estimated tax payments is required (data not yet extracted).",
                )
            )
        elif not is_finite_decimal(data.estimated_payments):
            errors.append(
                ProcessingIssueV1(
                    code="INVALID_AMOUNT",
                    field="estimated_payments",
                    message="Line 26 estimated tax payments must be a valid finite Decimal.",
                )
            )
        elif data.estimated_payments < Decimal("0"):
            errors.append(
                ProcessingIssueV1(
                    code="NEGATIVE_LINE_26_AMOUNT",
                    field="estimated_payments",
                    message="Line 26 estimated tax payments cannot be negative.",
                )
            )
        else:
            line_26 = data.estimated_payments

        # Line 27a — EIC
        line_27a, eic_errors = _validate_result_amount(
            data.eic_result,
            "line_27a_eic",
            "EIC",
            missing_result_code="MISSING_EIC_RESULT",
            blocked_code="EIC_MODULE_BLOCKED",
            missing_amount_code="MISSING_LINE_27A_EIC",
            invalid_amount_code="INVALID_AMOUNT",
            negative_amount_code="NEGATIVE_LINE_27A_AMOUNT",
            field_name="eic_result",
        )
        errors.extend(eic_errors)

        # Line 28 — Schedule 8812 ACTC
        line_28, actc_errors = _validate_result_amount(
            data.schedule_8812_result,
            "line_28_actc",
            "Schedule 8812 (ACTC)",
            missing_result_code="MISSING_SCHEDULE_8812_RESULT",
            blocked_code="SCHEDULE_8812_MODULE_BLOCKED",
            missing_amount_code="MISSING_LINE_28_ACTC",
            invalid_amount_code="INVALID_AMOUNT",
            negative_amount_code="NEGATIVE_LINE_28_AMOUNT",
            field_name="schedule_8812_result",
        )
        errors.extend(actc_errors)

        # Line 29 — Form 8863, Line 8
        line_29, aoc_errors = _validate_result_amount(
            data.form_8863_result,
            "line_8_aoc",
            "Form 8863 (American Opportunity Credit)",
            missing_result_code="MISSING_FORM_8863_RESULT",
            blocked_code="FORM_8863_MODULE_BLOCKED",
            missing_amount_code="MISSING_LINE_29_AOC",
            invalid_amount_code="INVALID_AMOUNT",
            negative_amount_code="NEGATIVE_LINE_29_AMOUNT",
            field_name="form_8863_result",
        )
        errors.extend(aoc_errors)

        # Line 30 — Form 8839, Line 13
        line_30, adoption_errors = _validate_result_amount(
            data.form_8839_result,
            "line_13_refundable_credit",
            "Form 8839 (Refundable Adoption Credit)",
            missing_result_code="MISSING_FORM_8839_RESULT",
            blocked_code="FORM_8839_MODULE_BLOCKED",
            missing_amount_code="MISSING_LINE_30_ADOPTION_CREDIT",
            invalid_amount_code="INVALID_AMOUNT",
            negative_amount_code="NEGATIVE_LINE_30_AMOUNT",
            field_name="form_8839_result",
        )
        errors.extend(adoption_errors)

        # Line 31 — Schedule 3, Line 15
        line_31, sch3_errors = _validate_result_amount(
            data.schedule_3_result,
            "line_15_total",
            "Schedule 3 (Line 15)",
            missing_result_code="MISSING_SCHEDULE_3_RESULT",
            blocked_code="SCHEDULE_3_MODULE_BLOCKED",
            missing_amount_code="MISSING_LINE_31_SCHEDULE3_TOTAL",
            invalid_amount_code="INVALID_AMOUNT",
            negative_amount_code="NEGATIVE_LINE_31_AMOUNT",
            field_name="schedule_3_result",
        )
        errors.extend(sch3_errors)

        # Line 38 — 預估稅罰款 (獨立計算規則，但仍需資料存在才能填入本表)
        line_38: Optional[Decimal] = None
        if data.estimated_tax_penalty_result is None:
            errors.append(
                ProcessingIssueV1(
                    code="MISSING_LINE_38",
                    field="estimated_tax_penalty_result",
                    message="Line 38 estimated tax penalty is required (data not yet extracted).",
                )
            )
        elif not is_finite_decimal(data.estimated_tax_penalty_result):
            errors.append(
                ProcessingIssueV1(
                    code="INVALID_AMOUNT",
                    field="estimated_tax_penalty_result",
                    message="Line 38 estimated tax penalty must be a valid finite Decimal.",
                )
            )
        elif data.estimated_tax_penalty_result < Decimal("0"):
            errors.append(
                ProcessingIssueV1(
                    code="NEGATIVE_LINE_38_AMOUNT",
                    field="estimated_tax_penalty_result",
                    message="Line 38 estimated tax penalty cannot be negative.",
                )
            )
        else:
            line_38 = data.estimated_tax_penalty_result

        # Line 35a / 36 — 納稅人選擇欄位，非公式推導。
        # 驗證邏輯：line_35a + line_36 是否超過 line_34 (Overpayment)，而非套用一般 Zero Policy。
        # 若目前已收集到阻斷錯誤（代表 line_24/25/26/27a/28/29/30/31 中有資料不完整），
        # 無法可靠地重建 line_34，因此跳過此交叉驗證，避免產生誤導性的額外錯誤。
        if not errors:
            refund_choice = data.refund_choice
            line_35a_raw = _get_field(refund_choice, "amount_to_refund")
            line_36_raw = _get_field(refund_choice, "amount_to_apply_next_year")

            cross_check_errors: List[ProcessingIssueV1] = []
            line_35a: Decimal = Decimal("0")
            line_36: Decimal = Decimal("0")

            for raw, label, field_label in (
                (line_35a_raw, "line_35a", "Line 35a (amount to be refunded)"),
                (line_36_raw, "line_36", "Line 36 (amount applied to next year)"),
            ):
                if raw is None:
                    continue
                try:
                    amt = Decimal(str(raw))
                except Exception:
                    cross_check_errors.append(
                        ProcessingIssueV1(
                            code="INVALID_AMOUNT",
                            field="refund_choice",
                            message=f"{field_label} must be a valid finite Decimal.",
                        )
                    )
                    continue
                if not is_finite_decimal(amt) or amt < Decimal("0"):
                    cross_check_errors.append(
                        ProcessingIssueV1(
                            code="INVALID_AMOUNT",
                            field="refund_choice",
                            message=f"{field_label} must be a valid, non-negative finite Decimal.",
                        )
                    )
                    continue
                if label == "line_35a":
                    line_35a = amt
                else:
                    line_36 = amt

            errors.extend(cross_check_errors)

            if not cross_check_errors and line_24 is not None:
                # 與 PaymentsAndRefundCalculator 共用同一份公式，避免 Validator / Calculator
                # 各自實作 line_25d/32/33/34 而日後分叉（見 code review）。
                _, _, line_33, line_34, _ = compute_totals(
                    line_25a or Decimal("0"),
                    line_25b or Decimal("0"),
                    line_25c or Decimal("0"),
                    line_26 or Decimal("0"),
                    line_27a or Decimal("0"),
                    line_28 or Decimal("0"),
                    line_29 or Decimal("0"),
                    line_30 or Decimal("0"),
                    line_31 or Decimal("0"),
                    line_24,
                )

                if line_33 > line_24:
                    if (line_35a + line_36) > line_34:
                        errors.append(
                            ProcessingIssueV1(
                                code="REFUND_CHOICE_EXCEEDS_OVERPAYMENT",
                                field="refund_choice",
                                message="Line 35a + Line 36 cannot exceed Line 34 (overpayment).",
                            )
                        )
                else:
                    if (line_35a + line_36) > Decimal("0"):
                        errors.append(
                            ProcessingIssueV1(
                                code="REFUND_CHOICE_WITHOUT_OVERPAYMENT",
                                field="refund_choice",
                                message="Line 35a/36 cannot be set when there is no overpayment (Line 33 <= Line 24).",
                            )
                        )

        return errors
