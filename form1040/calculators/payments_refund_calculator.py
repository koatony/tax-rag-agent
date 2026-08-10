from decimal import Decimal
from typing import Any, Optional, Tuple
from form1040.models.payments_refund_model import (
    PaymentsAndRefundProcessorInputV1,
    PaymentsAndRefundProcessorResultV1,
)


def _get_field(result_obj: Any, attr_name: str) -> Any:
    if result_obj is None:
        return None
    if hasattr(result_obj, attr_name):
        return getattr(result_obj, attr_name)
    if isinstance(result_obj, dict):
        return result_obj.get(attr_name)
    return None


def _extract_amount(result_obj: Any, attr_name: str) -> Decimal:
    """
    從上游子結果中取出金額欄位。若欄位為 None（Zero Policy 允許的
    CONFIRMED_NOT_PRESENT 合法情況，已由 Validator 確認），視為 Decimal("0")。
    """
    val = _get_field(result_obj, attr_name)
    if val is None:
        return Decimal("0")
    return Decimal(str(val))


def compute_totals(
    line_25a: Decimal,
    line_25b: Decimal,
    line_25c: Decimal,
    line_26: Decimal,
    line_27a: Decimal,
    line_28: Decimal,
    line_29: Decimal,
    line_30: Decimal,
    line_31: Decimal,
    line_24: Decimal,
) -> Tuple[Decimal, Decimal, Decimal, Optional[Decimal], Optional[Decimal]]:
    """
    共用算式，供 Calculator 與 Validator 的 cross-check 共用，避免兩處各自實作、日後分叉。

    line_25d_total_withholding   = line_25a + line_25b + line_25c
    line_32_other_payments_credits = line_27a + line_28 + line_29 + line_30 + line_31
    line_33_total_payments       = line_25d + line_26 + line_32

    # Line 34 / 37 互斥分支
    if line_33 > line_24:
        line_34_overpayment = line_33 - line_24
        line_37_amount_owed = None
    else:
        line_34_overpayment = None
        line_37_amount_owed = line_24 - line_33
    """
    line_25d = line_25a + line_25b + line_25c
    line_32 = line_27a + line_28 + line_29 + line_30 + line_31
    line_33 = line_25d + line_26 + line_32

    if line_33 > line_24:
        line_34: Optional[Decimal] = line_33 - line_24
        line_37: Optional[Decimal] = None
    else:
        line_34 = None
        line_37 = line_24 - line_33

    return line_25d, line_32, line_33, line_34, line_37


class PaymentsAndRefundCalculator:
    """
    PaymentsAndRefund 算術引擎 (Form 1040 Lines 25-38)

    公式定義見模組層級的 `compute_totals()`。

    # Line 35a / 36 為納稅人選擇，非公式推導（已由 Validator 確認不超過 line_34）
    """

    @staticmethod
    def calculate(data: PaymentsAndRefundProcessorInputV1) -> PaymentsAndRefundProcessorResultV1:
        line_24 = data.line_24_total_tax

        withholding_res = data.withholding_result
        line_25a = _extract_amount(withholding_res, "w2_withholding")
        line_25b = _extract_amount(withholding_res, "form1099_withholding")
        line_25c = _extract_amount(withholding_res, "other_withholding")

        line_26 = data.estimated_payments if data.estimated_payments is not None else Decimal("0")

        line_27a = _extract_amount(data.eic_result, "line_27a_eic")
        line_28 = _extract_amount(data.schedule_8812_result, "line_28_actc")
        line_29 = _extract_amount(data.form_8863_result, "line_8_aoc")
        line_30 = _extract_amount(data.form_8839_result, "line_13_refundable_credit")
        line_31 = _extract_amount(data.schedule_3_result, "line_15_total")

        line_25d, line_32, line_33, line_34, line_37 = compute_totals(
            line_25a, line_25b, line_25c, line_26,
            line_27a, line_28, line_29, line_30, line_31,
            line_24,
        )

        # Line 35a / 36 是納稅人的選擇欄位，非公式推導；Validator 已確認兩者之和不超過 line_34。
        # 這裡再做一次防禦性檢查，避免有呼叫路徑略過 Validator 直接呼叫 calculate() 而產生錯誤的 COMPLETE 結果。
        line_35a = _extract_amount(data.refund_choice, "amount_to_refund")
        line_36 = _extract_amount(data.refund_choice, "amount_to_apply_next_year")
        if line_35a + line_36 > (line_34 or Decimal("0")):
            raise ValueError(
                "line_35a + line_36 exceeds line_34 (overpayment); "
                "PaymentsAndRefundValidator.validate() must be called before calculate()."
            )

        line_38 = data.estimated_tax_penalty_result

        return PaymentsAndRefundProcessorResultV1(
            line_24_total_tax=line_24,
            line_25a_w2_withholding=line_25a,
            line_25b_1099_withholding=line_25b,
            line_25c_other_withholding=line_25c,
            line_25d_total_withholding=line_25d,
            line_26_estimated_payments=line_26,
            line_27a_eic=line_27a,
            line_28_actc=line_28,
            line_29_aoc=line_29,
            line_30_refundable_adoption_credit=line_30,
            line_31_schedule3_total=line_31,
            line_32_other_payments_credits=line_32,
            line_33_total_payments=line_33,
            line_34_overpayment=line_34,
            line_35a_refund_amount=line_35a,
            line_36_applied_to_next_year=line_36,
            line_37_amount_owed=line_37,
            line_38_estimated_tax_penalty=line_38,
            status="COMPLETE",
            can_continue=True,
            blocking_errors=[],
        )
