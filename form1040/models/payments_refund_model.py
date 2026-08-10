from decimal import Decimal
from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

"""
【為什麼要使用 Pydantic 的 BaseModel？】
1. 強型別檢查與驗證：確保傳入與輸出的資料欄位名稱、型別符合預期。
2. 方便序列化：Pydantic 模型可輕鬆轉換為 JSON 或 Python 字典，適合 API 與跨模組傳遞。
3. 減少 Bug：避免使用純 Python dict 時因拼錯鍵名（Key Error）導致運行期崩潰。
"""


class ProcessingIssueV1(BaseModel):
    """錯誤與警告資訊模型 (僅包含 PaymentsAndRefund 所需的簡化欄位: code, field, message)"""
    code: str
    field: Optional[str] = None
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "field": self.field,
            "message": self.message
        }


class PaymentsAndRefundProcessorInputV1(BaseModel):
    """
    PaymentsAndRefundProcessor 的輸入 DTO 模型 (Form 1040 Lines 25-38)

    【arbitrary_types_allowed=True】
    允許 withholding_result / eic_result / schedule_8812_result / form_8863_result /
    form_8839_result / schedule_3_result / refund_choice 以 Any（上游 Processor 的
    結果物件或 dict）型式直接通過驗證。
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # 上游 CreditsProcessor 輸出 (Line 24)，僅接收不重算
    line_24_total_tax: Optional[Decimal] = None

    # Line 25a/25b/25c 來源
    withholding_result: Optional[Any] = None

    # Line 26 — 納稅人申報之預估稅款繳納
    estimated_payments: Optional[Decimal] = None

    # Line 27a — EIC
    eic_result: Optional[Any] = None

    # Line 28 — Schedule 8812 ACTC
    schedule_8812_result: Optional[Any] = None

    # Line 29 — Form 8863, Line 8
    form_8863_result: Optional[Any] = None

    # Line 30 — Form 8839, Line 13
    form_8839_result: Optional[Any] = None

    # Line 31 — Schedule 3, Line 15
    schedule_3_result: Optional[Any] = None

    # Line 35a / 36 — 納稅人選擇 (退稅 / 轉為隔年預估稅)
    refund_choice: Optional[Any] = None

    # Line 38 — 預估稅罰款 (獨立於 Line 34/37 判斷之外)
    estimated_tax_penalty_result: Optional[Decimal] = None


class PaymentsAndRefundProcessorResultV1(BaseModel):
    """
    PaymentsAndRefundProcessor 的輸出 DTO 模型

    Line 34 (Overpayment) 與 Line 37 (Amount You Owe) 互斥：
    - line_33 > line_24 時，僅 line_34 有值，line_37 為 None
    - 否則僅 line_37 有值，line_34 為 None
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    line_24_total_tax: Optional[Decimal] = None

    line_25a_w2_withholding: Optional[Decimal] = None
    line_25b_1099_withholding: Optional[Decimal] = None
    line_25c_other_withholding: Optional[Decimal] = None
    line_25d_total_withholding: Optional[Decimal] = None

    line_26_estimated_payments: Optional[Decimal] = None

    line_27a_eic: Optional[Decimal] = None
    line_28_actc: Optional[Decimal] = None
    line_29_aoc: Optional[Decimal] = None
    line_30_refundable_adoption_credit: Optional[Decimal] = None
    line_31_schedule3_total: Optional[Decimal] = None
    line_32_other_payments_credits: Optional[Decimal] = None

    line_33_total_payments: Optional[Decimal] = None

    line_34_overpayment: Optional[Decimal] = None
    line_35a_refund_amount: Optional[Decimal] = None
    line_36_applied_to_next_year: Optional[Decimal] = None
    line_37_amount_owed: Optional[Decimal] = None

    line_38_estimated_tax_penalty: Optional[Decimal] = None

    status: Literal["COMPLETE", "BLOCKED"]
    can_continue: bool
    blocking_errors: List[ProcessingIssueV1] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """手動將 Decimal 轉換為字串，方便 JSON 序列化（避免 float 精度遺失）"""
        def _s(v: Optional[Decimal]) -> Optional[str]:
            return str(v) if v is not None else None

        return {
            "line_24_total_tax": _s(self.line_24_total_tax),
            "line_25a_w2_withholding": _s(self.line_25a_w2_withholding),
            "line_25b_1099_withholding": _s(self.line_25b_1099_withholding),
            "line_25c_other_withholding": _s(self.line_25c_other_withholding),
            "line_25d_total_withholding": _s(self.line_25d_total_withholding),
            "line_26_estimated_payments": _s(self.line_26_estimated_payments),
            "line_27a_eic": _s(self.line_27a_eic),
            "line_28_actc": _s(self.line_28_actc),
            "line_29_aoc": _s(self.line_29_aoc),
            "line_30_refundable_adoption_credit": _s(self.line_30_refundable_adoption_credit),
            "line_31_schedule3_total": _s(self.line_31_schedule3_total),
            "line_32_other_payments_credits": _s(self.line_32_other_payments_credits),
            "line_33_total_payments": _s(self.line_33_total_payments),
            "line_34_overpayment": _s(self.line_34_overpayment),
            "line_35a_refund_amount": _s(self.line_35a_refund_amount),
            "line_36_applied_to_next_year": _s(self.line_36_applied_to_next_year),
            "line_37_amount_owed": _s(self.line_37_amount_owed),
            "line_38_estimated_tax_penalty": _s(self.line_38_estimated_tax_penalty),
            "status": self.status,
            "can_continue": self.can_continue,
            "blocking_errors": [e.to_dict() for e in self.blocking_errors],
        }
