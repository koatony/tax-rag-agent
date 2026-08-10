from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

from form1040.models.agi_model import AGIProcessorResultV1, ProcessingIssueV1
from form1040.models.deduction_resolver_model import DeductionResolverResultV1


class TaxableIncomeInputV1(BaseModel):
    """
    TaxableIncomeProcessor V1 輸入 DTO 介面
    
    包含計算 Form 1040 Line 15 (Taxable Income) 所需的上游結果：
    - agi_result: AGIProcessor 的輸出 DTO (提供 Line 11b AGI)
    - deduction_result: DeductionResolverProcessor 的輸出 DTO (提供 Line 14 Total Deductions)
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    tax_year: int = 2025
    agi_result: Optional[AGIProcessorResultV1] = None
    deduction_result: Optional[DeductionResolverResultV1] = None


class TaxableIncomeResultV1(BaseModel):
    """
    TaxableIncomeProcessor V1 輸出 DTO 介面 (Form 1040 Line 15)
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    tax_year: int = 2025

    # 線頭核心欄位
    line_11b_agi: Decimal = Decimal("0.00")
    line_14_total_deductions: Decimal = Decimal("0.00")
    line_15_taxable_income: Decimal = Decimal("0.00")

    # 合規性與業務狀態
    is_v1_supported: bool = True
    can_file: bool = True

    # 執行狀態與錯誤控制
    status: str = "COMPLETE"  # "COMPLETE" | "BLOCKED"
    can_continue: bool = True
    blocking_errors: List[ProcessingIssueV1] = Field(default_factory=list)
    review_warnings: List[ProcessingIssueV1] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """將結果轉換為字典格式，方便 API 回傳或 JSON 序列化"""
        return {
            "tax_year": self.tax_year,
            "line_11b_agi": str(self.line_11b_agi),
            "line_14_total_deductions": str(self.line_14_total_deductions),
            "line_15_taxable_income": str(self.line_15_taxable_income),
            "is_v1_supported": self.is_v1_supported,
            "can_file": self.can_file,
            "status": self.status,
            "can_continue": self.can_continue,
            "blocking_errors": [err.to_dict() for err in self.blocking_errors],
            "review_warnings": [warn.to_dict() for warn in self.review_warnings],
        }

    @classmethod
    def blocked(
        cls,
        tax_year: int,
        errors: List[ProcessingIssueV1],
    ) -> "TaxableIncomeResultV1":
        """建構因上游阻斷錯誤 (Blocking Errors) 而無法完成計算的預設失敗物件"""
        return cls(
            tax_year=tax_year,
            line_11b_agi=Decimal("0.00"),
            line_14_total_deductions=Decimal("0.00"),
            line_15_taxable_income=Decimal("0.00"),
            is_v1_supported=False,
            can_file=False,
            status="BLOCKED",
            can_continue=False,
            blocking_errors=errors,
        )
