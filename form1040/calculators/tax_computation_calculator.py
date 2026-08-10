from decimal import Decimal
from typing import Dict, Any, List
from form1040.models.agi_model import ProcessingIssueV1
from form1040.models.tax_computation_model import (
    TaxComputationInputV1,
    TaxComputationResultV1,
    TaxComputationMethod,
    ApplicabilityStatus,
)
from form1040.tax_rules.tax_rule_provider import TaxRuleProvider, TaxRuleNotFoundError


class TaxComputationCalculator:
    """
    TaxComputation 核心算術與查表計算引擎 (Pure & Deterministic)
    
    公式與規範：
    1. Line 15 == 0 ➔ ZERO_TAX, Line 16 = 0.00
    2. Line 15 < 100,000 ➔ 查 2025 IRS Tax Table (TAX_TABLE)
    3. Line 15 >= 100,000 ➔ 使用 2025 Tax Computation Worksheet 套算 (TAX_COMPUTATION_WORKSHEET)
    4. Line 17 = 0.00 (已確認 Schedule 2 不適用)
    5. Line 18 = Line 16 + Line 17
    """

    @staticmethod
    def calculate(
        data: TaxComputationInputV1,
        tax_rule_provider: TaxRuleProvider = None,
    ) -> TaxComputationResultV1:
        if tax_rule_provider is None:
            tax_rule_provider = TaxRuleProvider.get_instance()

        line_15 = data.taxable_income_result.line_15_taxable_income
        filing_status_str = data.filing_status.value if hasattr(data.filing_status, "value") else str(data.filing_status)

        review_warnings: List[ProcessingIssueV1] = []
        blocking_errors: List[ProcessingIssueV1] = []

        # 1. 判斷計算路徑與執行 Line 16 計算
        if line_15 == Decimal("0.00"):
            method = TaxComputationMethod.ZERO_TAX
            line_16 = Decimal("0.00")
        elif line_15 < Decimal("100000"):
            method = TaxComputationMethod.TAX_TABLE
            try:
                line_16 = tax_rule_provider.lookup_tax_table(
                    filing_status=filing_status_str,
                    taxable_income=line_15,
                )
            except TaxRuleNotFoundError as e:
                blocking_errors.append(
                    ProcessingIssueV1(
                        code="NO_TAX_TABLE_ROW_MATCHED",
                        field="line_15_taxable_income",
                        message=str(e),
                    )
                )
                return TaxComputationResultV1.blocked(
                    tax_year=data.tax_year,
                    filing_status=data.filing_status,
                    errors=blocking_errors,
                )
        else:
            method = TaxComputationMethod.TAX_COMPUTATION_WORKSHEET
            try:
                line_16 = tax_rule_provider.compute_tax_computation_worksheet(
                    filing_status=filing_status_str,
                    taxable_income=line_15,
                )
            except TaxRuleNotFoundError as e:
                blocking_errors.append(
                    ProcessingIssueV1(
                        code="NO_WORKSHEET_RULE_MATCHED",
                        field="line_15_taxable_income",
                        message=str(e),
                    )
                )
                return TaxComputationResultV1.blocked(
                    tax_year=data.tax_year,
                    filing_status=data.filing_status,
                    errors=blocking_errors,
                )

        # 2. Line 17 與 Line 18 計算
        line_17 = Decimal("0.00")
        line_18 = line_16 + line_17

        # 3. 組合來源追溯標記
        source_trace = {
            "line_15": "TAXABLE_INCOME_PROCESSOR",
            "line_16": method.value,
            "line_17": "SCHEDULE_2_NOT_APPLICABLE",
            "line_18": "LINE_16_PLUS_LINE_17",
        }

        # 4. 繼承上游 can_file / is_v1_supported 標記
        upstream_is_supported = True
        upstream_can_file = True

        if data.taxable_income_result:
            if hasattr(data.taxable_income_result, "is_v1_supported") and not data.taxable_income_result.is_v1_supported:
                upstream_is_supported = False
            if hasattr(data.taxable_income_result, "can_file") and not data.taxable_income_result.can_file:
                upstream_can_file = False

        return TaxComputationResultV1(
            tax_year=data.tax_year,
            filing_status=data.filing_status,
            line_15_taxable_income=line_15,
            line_16_tax=line_16,
            line_17_schedule_2_line_3=line_17,
            line_18_tax_before_credits=line_18,
            computation_method=method,
            tax_rule_version="2025-final-v1",
            is_v1_supported=upstream_is_supported,
            can_file=upstream_can_file,
            source_trace=source_trace,
            status="COMPLETE",
            can_continue=True,
            blocking_errors=[],
            review_warnings=review_warnings,
        )
