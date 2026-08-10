from decimal import Decimal
from typing import List
from form1040.models.agi_model import ProcessingIssueV1
from form1040.models.taxable_income_model import TaxableIncomeInputV1, TaxableIncomeResultV1


class TaxableIncomeCalculator:
    """
    TaxableIncome 核心算術與決策計算引擎 (Pure & Deterministic)
    
    公式與規範：
    1. Line 11b (AGI) 來自 AGIProcessorResultV1 的 line_11_adjusted_gross_income。
    2. Line 14 (Total Deductions) 來自 DeductionResolverResultV1 的 line_14_total_deductions。
    3. Line 15 (Taxable Income) = max(Line 11b - Line 14, Decimal("0.00"))。
    4. 當 Line 11b - Line 14 <= 0 時，Line 15 為 0.00，並加入提示性 Warning。
    """

    @staticmethod
    def calculate(data: TaxableIncomeInputV1) -> TaxableIncomeResultV1:
        """
        執行 Line 15 減法計算與狀態建構
        """
        review_warnings: List[ProcessingIssueV1] = []

        # 1. 安全提取 Decimal 數值
        agi_val = getattr(data.agi_result, "line_11_adjusted_gross_income", None)
        if agi_val is None:
            agi_val = Decimal("0.00")
        else:
            agi_val = Decimal(str(agi_val))

        ded_val = getattr(data.deduction_result, "line_14_total_deductions", None)
        if ded_val is None:
            ded_val = Decimal("0.00")
        else:
            ded_val = Decimal(str(ded_val))

        # 2. 執行核心減法運算
        diff = agi_val - ded_val
        if diff <= Decimal("0.00"):
            line_15_taxable_income = Decimal("0.00")
            if diff < Decimal("0.00"):
                review_warnings.append(
                    ProcessingIssueV1(
                        code="DEDUCTIONS_EXCEED_AGI",
                        field="line_15_taxable_income",
                        message=f"總扣除額 (${ded_val}) 超過 AGI (${agi_val})，Form 1040 Line 15 依規定設為 $0.00",
                    )
                )
        else:
            line_15_taxable_income = diff

        # 3. 繼承上游業務合規標記 (can_file / is_v1_supported)
        upstream_is_supported = True
        upstream_can_file = True

        if data.agi_result:
            if hasattr(data.agi_result, "is_v1_supported") and not data.agi_result.is_v1_supported:
                upstream_is_supported = False
            if hasattr(data.agi_result, "can_file") and not data.agi_result.can_file:
                upstream_can_file = False

        if data.deduction_result:
            if hasattr(data.deduction_result, "is_v1_supported") and not data.deduction_result.is_v1_supported:
                upstream_is_supported = False
            if hasattr(data.deduction_result, "can_file") and not data.deduction_result.can_file:
                upstream_can_file = False

        return TaxableIncomeResultV1(
            tax_year=data.tax_year,
            line_11b_agi=agi_val,
            line_14_total_deductions=ded_val,
            line_15_taxable_income=line_15_taxable_income,
            is_v1_supported=upstream_is_supported,
            can_file=upstream_can_file,
            status="COMPLETE",
            can_continue=True,
            blocking_errors=[],
            review_warnings=review_warnings,
        )
