from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

from form1040.models.agi_model import ProcessingIssueV1
from processors.models.schedule_a import ScheduleAResultV1


class Form8995ResultV1(BaseModel):
    """Form 8995 (QBI Deduction) 替代用 Placeholder DTO"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    line_15_qbi_deduction: Decimal = Decimal("0.00")
    status: str = "COMPLETE"
    can_continue: bool = True
    blocking_errors: List[ProcessingIssueV1] = Field(default_factory=list)


class Schedule1AResultV1(BaseModel):
    """Schedule 1-A (Additional Deductions) 替代用 Placeholder DTO"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    line_38_additional_deductions: Decimal = Decimal("0.00")
    status: str = "COMPLETE"
    can_continue: bool = True
    blocking_errors: List[ProcessingIssueV1] = Field(default_factory=list)


class DeductionResolverInputV1(BaseModel):
    """DeductionResolverProcessor 的完整輸入 DTO 介面"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    tax_year: int = 2025
    filing_status: str = "SINGLE"
    schedule_a_result: Optional[ScheduleAResultV1] = None
    form_8995_result: Optional[Form8995ResultV1] = None
    schedule_1a_result: Optional[Schedule1AResultV1] = None


class DeductionResolverResultV1(BaseModel):
    """Form 1040 Deduction Section 最終輸出結果 DTO"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    tax_year: int = 2025
    filing_status: str = "SINGLE"

    # Form 1040 線頭欄位
    line_12e_deduction: Decimal = Decimal("0.00")
    line_13a_qbi_deduction: Decimal = Decimal("0.00")
    line_13b_schedule_1a_deductions: Decimal = Decimal("0.00")
    line_14_total_deductions: Decimal = Decimal("0.00")

    # 附帶決策狀態
    is_itemizing: bool = False
    deduction_type_used: str = "STANDARD"  # "STANDARD" | "ITEMIZED"
    should_attach_schedule_a: bool = False

    # 執行狀態與錯誤控制
    status: str = "COMPLETE"  # "COMPLETE" | "BLOCKED"
    can_continue: bool = True
    blocking_errors: List[ProcessingIssueV1] = Field(default_factory=list)
    review_warnings: List[Dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def blocked(
        cls,
        *,
        tax_year: int = 2025,
        filing_status: str = "SINGLE",
        errors: List[ProcessingIssueV1],
    ) -> "DeductionResolverResultV1":
        """建立 BLOCKED 狀態之結果 instance"""
        return cls(
            tax_year=tax_year,
            filing_status=filing_status,
            status="BLOCKED",
            can_continue=False,
            blocking_errors=errors,
        )

    def to_dict(self) -> Dict[str, Any]:
        """轉為字典格式以利 API / JSON 輸出"""
        return {
            "tax_year": self.tax_year,
            "filing_status": self.filing_status,
            "line_12e_deduction": float(self.line_12e_deduction),
            "line_13a_qbi_deduction": float(self.line_13a_qbi_deduction),
            "line_13b_schedule_1a_deductions": float(self.line_13b_schedule_1a_deductions),
            "line_14_total_deductions": float(self.line_14_total_deductions),
            "is_itemizing": self.is_itemizing,
            "deduction_type_used": self.deduction_type_used,
            "should_attach_schedule_a": self.should_attach_schedule_a,
            "status": self.status,
            "can_continue": self.can_continue,
            "blocking_errors": [
                err.to_dict() if hasattr(err, "to_dict") else err
                for err in self.blocking_errors
            ],
            "review_warnings": self.review_warnings,
        }
