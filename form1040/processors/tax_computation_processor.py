from typing import Optional, Union
from decimal import Decimal
from form1040.models.tax_computation_model import (
    TaxComputationInputV1,
    TaxComputationResultV1,
    FilingStatus,
    ApplicabilityStatus,
    OrdinaryTaxEligibilityV1,
)
from form1040.models.taxable_income_model import TaxableIncomeResultV1
from form1040.validators.tax_computation_validator import TaxComputationValidator
from form1040.calculators.tax_computation_calculator import TaxComputationCalculator
from form1040.tax_rules.tax_rule_provider import TaxRuleProvider


class TaxComputationProcessor:
    """
    Form 1040 Tax Computation 處理器 (Lines 16, 17, 18)

    設計原則與模組說明：
    1. 職責範圍：
       - 計算 Form 1040 Line 16 (一般所得稅)、Line 17 (Schedule 2 Line 3) 與 Line 18 (稅前小計 Line 16 + Line 17)。
       - 包含 2025 IRS Tax Table 查表法 (< $100,000) 與 Tax Computation Worksheet 套算法 (>= $100,000)。
       - 嚴格落實防禦性驗證，若包含 Qualified Dividends、Capital Gain 收益或特殊表單 (Form 2555/8615 等)，主動拋出 Blocking Error 予以阻斷。

    2. 純粹與確定性：
       - 完全為無狀態確定性程式，不使用 LLM 估算稅額。
    """

    @classmethod
    def process(
        cls,
        data: TaxComputationInputV1,
        tax_rule_provider: Optional[TaxRuleProvider] = None,
    ) -> TaxComputationResultV1:
        """
        所得稅計算處理邏輯主進入點 (Pure, Stateless)
        """
        # 1. 執行輸入與適性驗證
        blocking_errors = TaxComputationValidator.validate(data)
        if blocking_errors:
            return TaxComputationResultV1.blocked(
                tax_year=data.tax_year,
                filing_status=data.filing_status,
                errors=blocking_errors,
            )

        # 2. 執行核心查表與算術計算
        return TaxComputationCalculator.calculate(data, tax_rule_provider=tax_rule_provider)

    @classmethod
    def compute(
        cls,
        *,
        taxable_income_result: Optional[TaxableIncomeResultV1] = None,
        filing_status: Union[FilingStatus, str] = FilingStatus.SINGLE,
        ordinary_tax_eligibility: Optional[OrdinaryTaxEligibilityV1] = None,
        schedule_2_status: ApplicabilityStatus = ApplicabilityStatus.NOT_APPLICABLE,
        tax_year: int = 2025,
        tax_rule_provider: Optional[TaxRuleProvider] = None,
    ) -> TaxComputationResultV1:
        """
        便捷進入點：自動組裝 TaxComputationInputV1 並調用 process
        """
        if isinstance(filing_status, str):
            try:
                filing_status_enum = FilingStatus(filing_status.upper())
            except ValueError:
                filing_status_enum = FilingStatus.SINGLE
        else:
            filing_status_enum = filing_status

        if ordinary_tax_eligibility is None:
            ordinary_tax_eligibility = OrdinaryTaxEligibilityV1()

        input_dto = TaxComputationInputV1(
            tax_year=tax_year,
            filing_status=filing_status_enum,
            taxable_income_result=taxable_income_result,
            ordinary_tax_eligibility=ordinary_tax_eligibility,
            schedule_2_status=schedule_2_status,
        )
        return cls.process(input_dto, tax_rule_provider=tax_rule_provider)
