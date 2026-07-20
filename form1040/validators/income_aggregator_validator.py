from typing import List
from form1040.models.income_aggregator_model import (
    IncomeAggregatorInputV1,
    ProcessingIssueV1,
)


class IncomeAggregatorValidator:
    """
    IncomeAggregator 輸入與業務邏輯驗證器
    專注於驗證 Tax Year 一致性、狀態防呆與上游 Schedule 結果完整性。
    """

    @staticmethod
    def validate(input_dto: IncomeAggregatorInputV1) -> List[ProcessingIssueV1]:
        errors: List[ProcessingIssueV1] = []

        target_tax_year = input_dto.tax_year

        # 1. 驗證 W-2 項目之 Tax Year 與申報年度一致性
        direct_input = input_dto.direct_income_input
        if direct_input and direct_input.w2_items:
            for idx, w2 in enumerate(direct_input.w2_items):
                if w2.tax_year is not None and w2.tax_year != target_tax_year:
                    errors.append(
                        ProcessingIssueV1(
                            code="TAX_YEAR_MISMATCH",
                            field=f"direct_income_input.w2_items[{idx}].tax_year",
                            message=f"W-2 憑證年度 ({w2.tax_year}) 與申報年度 ({target_tax_year}) 不符",
                        )
                    )
                if w2.status == "BLOCKED":
                    errors.append(
                        ProcessingIssueV1(
                            code="W2_ITEM_BLOCKED",
                            field=f"direct_income_input.w2_items[{idx}]",
                            message=f"W-2 項目 [{w2.employer_name or idx}] 處於 BLOCKED 狀態",
                        )
                    )
                elif w2.status == "UNKNOWN":
                    errors.append(
                        ProcessingIssueV1(
                            code="W2_ITEM_UNKNOWN",
                            field=f"direct_income_input.w2_items[{idx}]",
                            message=f"W-2 項目 [{w2.employer_name or idx}] 狀態為 UNKNOWN",
                        )
                    )

        # 2. 驗證 Lines 4–6 提取狀態
        if direct_input:
            for field_name, item in [
                ("ira_distribution", direct_input.ira_distribution),
                ("pension_annuity", direct_input.pension_annuity),
                ("social_security", direct_input.social_security),
            ]:
                if item is not None:
                    if item.status == "TAXABILITY_REQUIRES_CALCULATION":
                        errors.append(
                            ProcessingIssueV1(
                                code="TAXABILITY_REQUIRES_CALCULATION",
                                field=f"direct_income_input.{field_name}",
                                message=f"{field_name} 需要複雜應稅計算，現階段不支援自動加總",
                            )
                        )
                    elif item.status == "UNKNOWN":
                        errors.append(
                            ProcessingIssueV1(
                                code="ITEM_STATUS_UNKNOWN",
                                field=f"direct_income_input.{field_name}",
                                message=f"{field_name} 提取狀態為 UNKNOWN",
                            )
                        )

        # 3. 驗證 Schedule B 結果
        sb = input_dto.schedule_b_result
        if sb is not None:
            if sb.status == "BLOCKED" or not sb.can_continue:
                if sb.blocking_errors:
                    errors.extend(sb.blocking_errors)
                else:
                    errors.append(
                        ProcessingIssueV1(
                            code="SCHEDULE_B_BLOCKED",
                            field="schedule_b_result",
                            message="Schedule B 計算阻斷，無法完成 Income Aggregation",
                        )
                    )

        # 4. 驗證 Schedule D 結果
        sd = input_dto.schedule_d_result
        if sd is not None:
            if sd.status == "BLOCKED" or not sd.can_continue:
                if sd.blocking_errors:
                    errors.extend(sd.blocking_errors)
                else:
                    errors.append(
                        ProcessingIssueV1(
                            code="SCHEDULE_D_BLOCKED",
                            field="schedule_d_result",
                            message="Schedule D 算術阻斷，無法完成 Income Aggregation",
                        )
                    )
            elif sd.status == "UNKNOWN":
                errors.append(
                    ProcessingIssueV1(
                        code="SCHEDULE_D_UNKNOWN",
                        field="schedule_d_result",
                        message="Schedule D 狀態為 UNKNOWN",
                    )
                )
            elif sd.status == "COMPLETE" and sd.line_7_capital_gain_or_loss is None:
                errors.append(
                    ProcessingIssueV1(
                        code="CAPITAL_RESULT_MISSING",
                        field="schedule_d_result.line_7_capital_gain_or_loss",
                        message="Schedule D 狀態為 COMPLETE 但缺少 line_7_capital_gain_or_loss 金額",
                    )
                )

        # 5. 驗證 Schedule 1 結果
        s1 = input_dto.schedule_1_result
        if s1 is not None:
            if s1.status == "BLOCKED" or not s1.can_continue:
                if s1.blocking_errors:
                    errors.extend(s1.blocking_errors)
                else:
                    errors.append(
                        ProcessingIssueV1(
                            code="SCHEDULE_1_BLOCKED",
                            field="schedule_1_result",
                            message="Schedule 1 計算阻斷，無法完成 Income Aggregation",
                        )
                    )

        return errors
