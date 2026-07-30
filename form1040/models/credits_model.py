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
    """錯誤與警告資訊模型 (僅包含 Credits 所需的簡化欄位: code, field, message)"""
    code: str
    field: Optional[str] = None
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "field": self.field,
            "message": self.message
        }


class CreditsProcessorInputV1(BaseModel):
    """
    CreditsProcessor 的輸入 DTO 模型 (Form 1040 Lines 19-24)

    【arbitrary_types_allowed=True】
    允許 schedule_8812_result / schedule_3_result / schedule_2_result 以
    Any（上游 Schedule Processor 的結果物件或 dict）型式直接通過驗證。
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # 上游 TaxComputationProcessor 輸出，僅接收不重算
    line_18_tax_before_credits: Optional[Decimal] = None

    # 關聯的 Schedule 計算結果
    schedule_8812_result: Optional[Any] = None  # Line 19: Child Tax Credit / ODC
    schedule_3_result: Optional[Any] = None     # Line 20: Schedule 3, Line 8
    schedule_2_result: Optional[Any] = None     # Line 23: Schedule 2, Line 21


class CreditsProcessorResultV1(BaseModel):
    """
    CreditsProcessor 的輸出 DTO 模型
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    line_18_tax_before_credits: Optional[Decimal] = None
    line_19_ctc_odc: Optional[Decimal] = None
    line_20_schedule3_credits: Optional[Decimal] = None
    line_21_total_credits: Optional[Decimal] = None
    line_22_tax_after_credits: Optional[Decimal] = None
    line_23_other_taxes: Optional[Decimal] = None
    line_24_total_tax: Optional[Decimal] = None

    status: Literal["COMPLETE", "BLOCKED"]
    can_continue: bool
    blocking_errors: List[ProcessingIssueV1] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """手動將 Decimal 轉換為字串，方便 JSON 序列化（避免 float 精度遺失）"""
        return {
            "line_18_tax_before_credits": str(self.line_18_tax_before_credits) if self.line_18_tax_before_credits is not None else None,
            "line_19_ctc_odc": str(self.line_19_ctc_odc) if self.line_19_ctc_odc is not None else None,
            "line_20_schedule3_credits": str(self.line_20_schedule3_credits) if self.line_20_schedule3_credits is not None else None,
            "line_21_total_credits": str(self.line_21_total_credits) if self.line_21_total_credits is not None else None,
            "line_22_tax_after_credits": str(self.line_22_tax_after_credits) if self.line_22_tax_after_credits is not None else None,
            "line_23_other_taxes": str(self.line_23_other_taxes) if self.line_23_other_taxes is not None else None,
            "line_24_total_tax": str(self.line_24_total_tax) if self.line_24_total_tax is not None else None,
            "status": self.status,
            "can_continue": self.can_continue,
            "blocking_errors": [e.to_dict() for e in self.blocking_errors]
        }
