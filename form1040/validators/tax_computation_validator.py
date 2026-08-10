from typing import List
from form1040.models.agi_model import ProcessingIssueV1
from form1040.models.tax_computation_model import (
    TaxComputationInputV1,
    ApplicabilityStatus,
)


class TaxComputationValidator:
    """
    TaxComputationProcessor 輸入與適性驗證器
    
    執行三層防禦檢查：
    1. 基礎邊界與年度驗證 (tax_year == 2025, line_15 >= 0)
    2. 上游阻斷錯誤傳遞
    3. 一般所得稅適性檢查 (ordinary_tax_eligibility) 與 Schedule 2 狀態檢查 (schedule_2_status)
    """

    @staticmethod
    def validate(data: TaxComputationInputV1) -> List[ProcessingIssueV1]:
        errors: List[ProcessingIssueV1] = []

        # 1. 檢查稅務年度
        if data.tax_year != 2025:
            errors.append(
                ProcessingIssueV1(
                    code="UNSUPPORTED_TAX_YEAR",
                    field="tax_year",
                    message=f"TaxComputationProcessor V1 僅支援 2025 稅務年度，當前傳入為 {data.tax_year}",
                )
            )

        # 2. 檢查上游 TaxableIncomeProcessor 結果
        if data.taxable_income_result is None:
            errors.append(
                ProcessingIssueV1(
                    code="MISSING_TAXABLE_INCOME_RESULT",
                    field="taxable_income_result",
                    message="未提供 TaxableIncomeResultV1 上游計算結果，無法進行所得稅計算",
                )
            )
        else:
            # 繼承上游阻斷錯誤
            if hasattr(data.taxable_income_result, "can_continue") and not data.taxable_income_result.can_continue:
                if hasattr(data.taxable_income_result, "blocking_errors") and data.taxable_income_result.blocking_errors:
                    errors.extend(data.taxable_income_result.blocking_errors)
                else:
                    errors.append(
                        ProcessingIssueV1(
                            code="UPSTREAM_BLOCKED",
                            field="taxable_income_result",
                            message="上游 TaxableIncomeProcessor 處於 BLOCKED 狀態，無法繼續計算所得稅 Line 16",
                        )
                    )
            
            # 檢查 Line 15 是否小於 0
            line_15 = getattr(data.taxable_income_result, "line_15_taxable_income", None)
            if line_15 is not None and line_15 < 0:
                errors.append(
                    ProcessingIssueV1(
                        code="NEGATIVE_TAXABLE_INCOME",
                        field="line_15_taxable_income",
                        message=f"Form 1040 Line 15 (Taxable Income) 不能為負數: ${line_15}",
                    )
                )

        # 3. 檢查 Ordinary Tax Eligibility (一般所得稅適用性)
        eligibility = data.ordinary_tax_eligibility
        if eligibility is None:
            errors.append(
                ProcessingIssueV1(
                    code="MISSING_ORDINARY_TAX_ELIGIBILITY",
                    field="ordinary_tax_eligibility",
                    message="未提供 OrdinaryTaxEligibilityV1 適性判定資料，無法確認計稅路徑",
                )
            )
        else:
            # 3a. Qualified Dividends 檢查
            if eligibility.qualified_dividends_amount > 0:
                errors.append(
                    ProcessingIssueV1(
                        code="SPECIAL_TAX_METHOD_UNSUPPORTED",
                        field="ordinary_tax_eligibility.qualified_dividends_amount",
                        message=f"存在合格股利 (${eligibility.qualified_dividends_amount})，依規定需套用 Qualified Dividends and Capital Gain Tax Worksheet，V1 尚不支援",
                    )
                )

            # 3b. Capital Gain 檢查
            if eligibility.capital_gain_or_loss_amount > 0:
                errors.append(
                    ProcessingIssueV1(
                        code="SPECIAL_TAX_METHOD_UNSUPPORTED",
                        field="ordinary_tax_eligibility.capital_gain_or_loss_amount",
                        message=f"存在淨資本利得 (${eligibility.capital_gain_or_loss_amount})，依規定需套用 Schedule D Tax Worksheet，V1 尚不支援",
                    )
                )

            # 3c. 特殊表單檢查 (Form 8615, Schedule J, Form 2555)
            if eligibility.form_8615_required:
                errors.append(
                    ProcessingIssueV1(
                        code="SPECIAL_TAX_METHOD_UNSUPPORTED",
                        field="ordinary_tax_eligibility.form_8615_required",
                        message="本申報案包含兒童投資所得稅 Form 8615，V1 尚不支援",
                    )
                )

            if eligibility.schedule_j_required:
                errors.append(
                    ProcessingIssueV1(
                        code="SPECIAL_TAX_METHOD_UNSUPPORTED",
                        field="ordinary_tax_eligibility.schedule_j_required",
                        message="本申報案包含農漁民所得平均計稅 Schedule J，V1 尚不支援",
                    )
                )

            if eligibility.form_2555_required:
                errors.append(
                    ProcessingIssueV1(
                        code="SPECIAL_TAX_METHOD_UNSUPPORTED",
                        field="ordinary_tax_eligibility.form_2555_required",
                        message="本申報案包含海外所得豁免 Form 2555，依規定需套用 Foreign Earned Income Tax Worksheet，V1 尚不支援",
                    )
                )

            # 3d. eligibility 狀態檢查
            if eligibility.status != ApplicabilityStatus.APPLICABLE:
                errors.append(
                    ProcessingIssueV1(
                        code="SPECIAL_TAX_METHOD_UNSUPPORTED",
                        field="ordinary_tax_eligibility.status",
                        message=f"一般所得稅路徑適性狀態不符合 APPLICABLE (當前狀態: {eligibility.status})",
                    )
                )

        # 4. 檢查 Schedule 2 狀態
        if data.schedule_2_status != ApplicabilityStatus.NOT_APPLICABLE:
            errors.append(
                ProcessingIssueV1(
                    code="SCHEDULE_2_UNRESOLVED_OR_UNSUPPORTED",
                    field="schedule_2_status",
                    message=f"Schedule 2 必須明確確認為 NOT_APPLICABLE，當前狀態為 {data.schedule_2_status}",
                )
            )

        return errors
