from form1040.models.payments_refund_model import (
    PaymentsAndRefundProcessorInputV1,
    PaymentsAndRefundProcessorResultV1,
)
from form1040.validators.payments_refund_validator import PaymentsAndRefundValidator
from form1040.calculators.payments_refund_calculator import PaymentsAndRefundCalculator


class PaymentsAndRefundProcessor:
    """PaymentsAndRefundProcessor 統一進入點類別 (Form 1040 Lines 25-38: Payments / Refund / Amount You Owe)"""

    @staticmethod
    def process(data: PaymentsAndRefundProcessorInputV1) -> PaymentsAndRefundProcessorResultV1:
        """
        PaymentsAndRefund 處理邏輯進入點，調度 Validator 與 Calculator。

        計算公式：
        Line 25d (Total withholding) = Line 25a + Line 25b + Line 25c
        Line 32 (Other payments/credits) = Line 27a + Line 28 + Line 29 + Line 30 + Line 31
        Line 33 (Total payments) = Line 25d + Line 26 + Line 32
        Line 34 (Overpayment) / Line 37 (Amount You Owe) — 互斥分支：
            若 Line 33 > Line 24，僅計算 Line 34；否則僅計算 Line 37。
        """
        errors = PaymentsAndRefundValidator.validate(data)
        if errors:
            return PaymentsAndRefundProcessorResultV1(
                line_24_total_tax=data.line_24_total_tax,
                line_25a_w2_withholding=None,
                line_25b_1099_withholding=None,
                line_25c_other_withholding=None,
                line_25d_total_withholding=None,
                line_26_estimated_payments=None,
                line_27a_eic=None,
                line_28_actc=None,
                line_29_aoc=None,
                line_30_refundable_adoption_credit=None,
                line_31_schedule3_total=None,
                line_32_other_payments_credits=None,
                line_33_total_payments=None,
                line_34_overpayment=None,
                line_35a_refund_amount=None,
                line_36_applied_to_next_year=None,
                line_37_amount_owed=None,
                line_38_estimated_tax_penalty=None,
                status="BLOCKED",
                can_continue=False,
                blocking_errors=errors,
            )

        # 進行 PaymentsAndRefund 核心運算：
        # 1. 從 withholding_result / eic_result / schedule_8812_result / form_8863_result /
        #    form_8839_result / schedule_3_result 取得各項金額，加總為 Line 25d / Line 32 / Line 33
        # 2. 依 Line 33 與 Line 24 的大小關係，計算互斥的 Line 34 (Overpayment) 或 Line 37 (Amount You Owe)
        # 3. 併入納稅人選擇的 Line 35a / Line 36 與獨立計算的 Line 38 罰款
        # 4. 回傳 COMPLETE 狀態及計算結果
        return PaymentsAndRefundCalculator.calculate(data)
