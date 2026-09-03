from decimal import Decimal
from typing import Literal, Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class ProcessingIssueV1(BaseModel):
    """標準處理議題模型 (code, field, message)"""
    code: str
    field: Optional[str] = None
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "field": self.field,
            "message": self.message
        }


ValidationIssue = ProcessingIssueV1


class W2ItemV1(BaseModel):
    """W-2 明細項目 DTO"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    employee_name: Optional[str] = None
    employee_ssn: Optional[str] = None
    employer_name: Optional[str] = None
    tax_year: Optional[int] = None
    box_1_wages: Decimal = Decimal("0")
    box_2_federal_withholding: Optional[Decimal] = None
    source_document_id: Optional[str] = None
    status: str = "COMPLETE"


class DirectIncomeItemV1(BaseModel):
    """Direct Income 明細項目 DTO (Lines 4-6)
    TODO: [PLACEHOLDER] 未來擴充 Form 1099-R Box 4 / Form 1099-SSA Box 6 預扣稅欄位 (federal_withholding)
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    gross_amount: Decimal = Decimal("0")
    taxable_amount: Decimal = Decimal("0")
    federal_withholding: Optional[Decimal] = None
    status: str = "EXPLICIT_VALUE"


class DirectIncomeInputV1(BaseModel):
    """LLM 直接提取之 Income 輸入資料 DTO"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    w2_items: List[W2ItemV1] = Field(default_factory=list)
    ira_distribution: Optional[DirectIncomeItemV1] = None
    pension_annuity: Optional[DirectIncomeItemV1] = None
    social_security: Optional[DirectIncomeItemV1] = None


class ScheduleBResultV1(BaseModel):
    """Schedule B 上游 Raw Result 物件 DTO"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    form_1040_line_2a: Decimal = Decimal("0")
    line_4_surface_value: Decimal = Decimal("0")
    total_qualified_dividends: Decimal = Decimal("0")
    line_6_total_ordinary_dividends: Decimal = Decimal("0")
    status: str = "COMPLETE"
    can_continue: bool = True
    blocking_errors: List[ProcessingIssueV1] = Field(default_factory=list)


class ScheduleDResultV1(BaseModel):
    """Schedule D 上游 Raw Result 物件 DTO"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    line_7_capital_gain_or_loss: Optional[Decimal] = None
    status: str = "COMPLETE"
    source: str = "schedule_d_result"
    can_continue: bool = True
    blocking_errors: List[ProcessingIssueV1] = Field(default_factory=list)


class Schedule1ResultV1(BaseModel):
    """Schedule 1 上游 Raw Result 物件 DTO"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    line_10_additional_income: Decimal = Decimal("0")
    line_26_adjustments_to_income: Decimal = Decimal("0")
    status: str = "COMPLETE"
    can_continue: bool = True
    can_file: bool = True
    is_v1_supported: bool = True
    blocking_errors: List[ProcessingIssueV1] = Field(default_factory=list)
    review_warnings: List[ProcessingIssueV1] = Field(default_factory=list)


class ScheduleEResultV1(BaseModel):
    """Schedule E 上游 Raw Result 物件 DTO"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    line_26_total_rental_income_or_loss: Decimal = Decimal("0")
    schedule_1_line_5_transfer_amount: Optional[Decimal] = None
    status: str = "COMPLETE"
    can_continue: bool = True
    blocking_errors: List[ProcessingIssueV1] = Field(default_factory=list)
    review_warnings: List[ProcessingIssueV1] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_26_total_rental_income_or_loss": float(self.line_26_total_rental_income_or_loss),
            "schedule_1_line_5_transfer_amount": float(self.schedule_1_line_5_transfer_amount) if self.schedule_1_line_5_transfer_amount is not None else None,
            "status": self.status,
            "blocking_errors": [err.to_dict() for err in self.blocking_errors],
            "review_warnings": [warn.to_dict() for warn in self.review_warnings],
        }


class IncomeAggregatorInputV1(BaseModel):
    """IncomeAggregatorProcessor 的完整輸入契約"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    tax_year: int
    filing_status: str
    taxpayer_ssn: Optional[str] = None
    direct_income_input: DirectIncomeInputV1
    schedule_b_result: Optional[ScheduleBResultV1] = None
    schedule_d_result: Optional[ScheduleDResultV1] = None
    schedule_1_result: Optional[Schedule1ResultV1] = None


class IncomeSectionResultV1(BaseModel):
    """IncomeAggregatorProcessor 的完整輸出結果 DTO (Form 1040 Lines 1-9)"""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    tax_year: int
    filing_status: str

    line_1a: Optional[Decimal] = None
    line_1z: Optional[Decimal] = None
    line_2a: Optional[Decimal] = None
    line_2b: Optional[Decimal] = None
    line_3a: Optional[Decimal] = None
    line_3b: Optional[Decimal] = None
    line_4a: Optional[Decimal] = None
    line_4b: Optional[Decimal] = None
    line_5a: Optional[Decimal] = None
    line_5b: Optional[Decimal] = None
    line_6a: Optional[Decimal] = None
    line_6b: Optional[Decimal] = None
    line_7a: Optional[Decimal] = None
    line_8: Optional[Decimal] = None
    line_9: Optional[Decimal] = None

    status: Literal["COMPLETE", "BLOCKED"]
    can_continue: bool
    can_file: bool = True
    is_v1_supported: bool = True
    blocking_errors: List[ProcessingIssueV1] = Field(default_factory=list)
    review_warnings: List[ProcessingIssueV1] = Field(default_factory=list)

    @classmethod
    def blocked(cls, tax_year: int, filing_status: str, errors: List[ProcessingIssueV1]) -> "IncomeSectionResultV1":
        return cls(
            tax_year=tax_year,
            filing_status=filing_status,
            status="BLOCKED",
            can_continue=False,
            blocking_errors=errors,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tax_year": self.tax_year,
            "filing_status": self.filing_status,
            "line_1a": str(self.line_1a) if self.line_1a is not None else None,
            "line_1z": str(self.line_1z) if self.line_1z is not None else None,
            "line_2a": str(self.line_2a) if self.line_2a is not None else None,
            "line_2b": str(self.line_2b) if self.line_2b is not None else None,
            "line_3a": str(self.line_3a) if self.line_3a is not None else None,
            "line_3b": str(self.line_3b) if self.line_3b is not None else None,
            "line_4a": str(self.line_4a) if self.line_4a is not None else None,
            "line_4b": str(self.line_4b) if self.line_4b is not None else None,
            "line_5a": str(self.line_5a) if self.line_5a is not None else None,
            "line_5b": str(self.line_5b) if self.line_5b is not None else None,
            "line_6a": str(self.line_6a) if self.line_6a is not None else None,
            "line_6b": str(self.line_6b) if self.line_6b is not None else None,
            "line_7a": str(self.line_7a) if self.line_7a is not None else None,
            "line_8": str(self.line_8) if self.line_8 is not None else None,
            "line_9": str(self.line_9) if self.line_9 is not None else None,
            "status": self.status,
            "can_continue": self.can_continue,
            "can_file": self.can_file,
            "is_v1_supported": self.is_v1_supported,
            "blocking_errors": [e.to_dict() for e in self.blocking_errors],
            "review_warnings": [e.to_dict() for e in self.review_warnings],
        }
