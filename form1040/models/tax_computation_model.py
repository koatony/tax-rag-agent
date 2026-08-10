from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field

from form1040.models.agi_model import ProcessingIssueV1
from form1040.models.taxable_income_model import TaxableIncomeResultV1


class FilingStatus(str, Enum):
    SINGLE = "SINGLE"
    MFJ = "MFJ"
    MFS = "MFS"
    HOH = "HOH"
    QSS = "QSS"


class ApplicabilityStatus(str, Enum):
    """
    適用性狀態列舉值
    
    用以標記特定稅表、計稅路徑或規則對當前報稅案件的適用程度。
    - APPLICABLE: 適用
    - NOT_APPLICABLE: 不適用
    - UNRESOLVED: 待判定/未決定
    - UNSUPPORTED: 不支援（例如：案件包含了本系統目前尚未實作的特殊計稅路徑）
    """
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNRESOLVED = "UNRESOLVED"
    UNSUPPORTED = "UNSUPPORTED"


class TaxComputationMethod(str, Enum):
    """
    所得稅計算方法列舉值
    
    用以定義當前報稅案件採用的應納稅額（Form 1040 Line 16）計算方式。
    - ZERO_TAX: 免稅（應納稅所得額為 0 或負數，無須計稅）
    - TAX_TABLE: 查表法（適用於 Taxable Income < $100,000 的案件，依據 IRS 官方 Tax Table 查表）
    - TAX_COMPUTATION_WORKSHEET: 算術套算法（適用於 Taxable Income >= $100,000 的案件，依據 IRS 官方 Tax Computation Worksheet 計算）
    - UNSUPPORTED: 不支援的計稅方法（例如案件包含合格股利、資本利得等需要走特殊計稅工作表的情況）
    """
    ZERO_TAX = "ZERO_TAX"
    TAX_TABLE = "TAX_TABLE"
    TAX_COMPUTATION_WORKSHEET = "TAX_COMPUTATION_WORKSHEET"
    UNSUPPORTED = "UNSUPPORTED"


class OrdinaryTaxEligibilityV1(BaseModel):
    """
    一般所得稅路徑適性評估 DTO
    
    評估案件是否符合走一般 Tax Table / Tax Computation Worksheet 的條件。
    若包含合格股利 (Qualified Dividends)、資本利得收益 (Capital Gains)、海外所得豁免 (Foreign Earned Income Exclusion) 等，
    則不符合一般計稅路徑（必須使用對應的特殊計稅工作表，如 Qualified Dividends and Capital Gain Tax Worksheet）。
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # 來自報稅表單/上游計算的合格股利金額 (Form 1040 Line 3a)
    qualified_dividends_amount: Decimal = Decimal("0.00")
    # 來自報稅表單/上游計算的資本利得或損失金額 (Form 1040 Line 7)
    capital_gain_or_loss_amount: Decimal = Decimal("0.00")

    # 是否需要申報特殊表單（例如 Form 8615, Schedule J, Form 2555 等）
    # 這些表單的存在會影響計稅路徑判定
    form_8615_required: bool = False
    schedule_j_required: bool = False
    form_2555_required: bool = False

    # 當前案件對一般計稅路徑的適用狀態
    status: ApplicabilityStatus = ApplicabilityStatus.APPLICABLE


class TaxComputationInputV1(BaseModel):
    """
    TaxComputationProcessor V1 輸入 DTO 介面
    
    定義了進行 Form 1040 所得稅計算（Lines 16, 17, 18）所需的輸入資料。
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    tax_year: int = 2025
    filing_status: FilingStatus = FilingStatus.SINGLE

    # 來自上游 TaxableIncomeProcessor 的輸出結果 (TaxableIncomeResultV1)
    # 提供 Form 1040 Line 15 (Taxable Income) 等所得稅計算的基礎金額資訊
    taxable_income_result: Optional[TaxableIncomeResultV1] = None
    
    # 評估案件是否符合走一般計稅路徑（如 Tax Table / Tax Computation Worksheet）的適性評估資訊
    ordinary_tax_eligibility: Optional[OrdinaryTaxEligibilityV1] = None

    # 是否適用 Schedule 2 的狀態評估（預設為不適用 NOT_APPLICABLE）
    schedule_2_status: ApplicabilityStatus = ApplicabilityStatus.NOT_APPLICABLE


class TaxComputationResultV1(BaseModel):
    """
    TaxComputationProcessor V1 輸出 DTO 介面 (Form 1040 Lines 16, 17, 18)
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    tax_year: int = 2025
    filing_status: FilingStatus = FilingStatus.SINGLE

    # Form 1040 線頭欄位
    line_15_taxable_income: Decimal = Decimal("0.00")
    line_16_tax: Decimal = Decimal("0.00")
    line_17_schedule_2_line_3: Decimal = Decimal("0.00")
    line_18_tax_before_credits: Decimal = Decimal("0.00")

    # 查表與算術後設資料
    computation_method: TaxComputationMethod = TaxComputationMethod.TAX_TABLE
    tax_rule_version: str = "2025-final-v1"

    # 合規性與業務狀態
    is_v1_supported: bool = True
    can_file: bool = True

    # 追溯與錯誤控制
    source_trace: Dict[str, str] = Field(default_factory=dict)
    status: str = "COMPLETE"  # "COMPLETE" | "BLOCKED"
    can_continue: bool = True
    blocking_errors: List[ProcessingIssueV1] = Field(default_factory=list)
    review_warnings: List[ProcessingIssueV1] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """將結果轉換為字典格式，方便 API 回傳與 JSON 序列化"""
        return {
            "tax_year": self.tax_year,
            "filing_status": self.filing_status.value if isinstance(self.filing_status, Enum) else str(self.filing_status),
            "line_15_taxable_income": str(self.line_15_taxable_income),
            "line_16_tax": str(self.line_16_tax),
            "line_17_schedule_2_line_3": str(self.line_17_schedule_2_line_3),
            "line_18_tax_before_credits": str(self.line_18_tax_before_credits),
            "computation_method": self.computation_method.value if isinstance(self.computation_method, Enum) else str(self.computation_method),
            "tax_rule_version": self.tax_rule_version,
            "is_v1_supported": self.is_v1_supported,
            "can_file": self.can_file,
            "source_trace": self.source_trace,
            "status": self.status,
            "can_continue": self.can_continue,
            "blocking_errors": [err.to_dict() for err in self.blocking_errors],
            "review_warnings": [warn.to_dict() for warn in self.review_warnings],
        }

    @classmethod
    def blocked(
        cls,
        tax_year: int,
        filing_status: FilingStatus,
        errors: List[ProcessingIssueV1],
    ) -> "TaxComputationResultV1":
        """建構因阻斷性錯誤 (Blocking Errors) 而無法完成稅額計算的預設失敗物件"""
        return cls(
            tax_year=tax_year,
            filing_status=filing_status,
            line_15_taxable_income=Decimal("0.00"),
            line_16_tax=Decimal("0.00"),
            line_17_schedule_2_line_3=Decimal("0.00"),
            line_18_tax_before_credits=Decimal("0.00"),
            computation_method=TaxComputationMethod.UNSUPPORTED,
            is_v1_supported=False,
            can_file=False,
            status="BLOCKED",
            can_continue=False,
            blocking_errors=errors,
        )
