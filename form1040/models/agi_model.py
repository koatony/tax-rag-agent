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
    """錯誤與警告資訊模型 (僅包含 AGI 所需的簡化欄位: code, field, message)"""
    code: str
    field: Optional[str] = None
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "field": self.field,
            "message": self.message
        }


# 別名相容
ValidationIssue = ProcessingIssueV1


class AGIProcessorInputV1(BaseModel):
    """
    AGI 處理器的輸入 DTO 模型
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    line_9_total_income: Optional[Decimal] = None
    schedule1_line_26_adjustments: Optional[Decimal] = None


class AGIProcessorResultV1(BaseModel):
    """
    AGI 處理器的輸出 DTO 模型
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    line_9_total_income: Optional[Decimal] = None
    line_10_adjustments_to_income: Optional[Decimal] = None
    line_11_adjusted_gross_income: Optional[Decimal] = None

    status: Literal["COMPLETE", "BLOCKED"]
    can_continue: bool
    blocking_errors: List[ProcessingIssueV1] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """手動將 Decimal 轉換為字串，方便 JSON 序列化（避免 float 精度遺失）"""
        return {
            "line_9_total_income": str(self.line_9_total_income) if self.line_9_total_income is not None else None,
            "line_10_adjustments_to_income": str(self.line_10_adjustments_to_income) if self.line_10_adjustments_to_income is not None else None,
            "line_11_adjusted_gross_income": str(self.line_11_adjusted_gross_income) if self.line_11_adjusted_gross_income is not None else None,
            "status": self.status,
            "can_continue": self.can_continue,
            "blocking_errors": [e.to_dict() for e in self.blocking_errors]
        }
