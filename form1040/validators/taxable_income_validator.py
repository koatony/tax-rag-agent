from typing import List
from form1040.models.agi_model import ProcessingIssueV1
from form1040.models.taxable_income_model import TaxableIncomeInputV1


class TaxableIncomeValidator:
    """
    TaxableIncomeProcessor 輸入與上游模組結果驗證器
    
    職責：
    1. 驗證 AGIProcessorResultV1 與 DeductionResolverResultV1 是否合法傳入。
    2. 檢查上游模組是否有阻斷性錯誤 (Blocking Errors)，若有則予以收集傳導。
    """

    @staticmethod
    def validate(data: TaxableIncomeInputV1) -> List[ProcessingIssueV1]:
        """
        執行全方位驗證邏輯
        
        :param data: TaxableIncomeInputV1 輸入資料
        :return: 阻斷性錯誤列表 List[ProcessingIssueV1]
        """
        errors: List[ProcessingIssueV1] = []

        # 1. 檢查 AGIProcessor 結果
        if data.agi_result is None:
            errors.append(
                ProcessingIssueV1(
                    code="MISSING_AGI_RESULT",
                    field="agi_result",
                    message="未提供 AGIProcessorResultV1 上游計算結果，無法計算 Taxable Income (Line 15)",
                )
            )
        else:
            # 若 AGIProcessor 本身被阻斷或包含 blocking errors
            if hasattr(data.agi_result, "can_continue") and not data.agi_result.can_continue:
                if hasattr(data.agi_result, "blocking_errors") and data.agi_result.blocking_errors:
                    errors.extend(data.agi_result.blocking_errors)
                else:
                    errors.append(
                        ProcessingIssueV1(
                            code="AGI_PROCESSOR_BLOCKED",
                            field="agi_result",
                            message="上游 AGIProcessor 處於 BLOCKED 狀態，無法繼續計算 Line 15",
                        )
                    )

        # 2. 檢查 DeductionResolver 結果
        if data.deduction_result is None:
            errors.append(
                ProcessingIssueV1(
                    code="MISSING_DEDUCTION_RESULT",
                    field="deduction_result",
                    message="未提供 DeductionResolverResultV1 上游計算結果，無法計算 Taxable Income (Line 15)",
                )
            )
        else:
            # 若 DeductionResolver 本身被阻斷或包含 blocking errors
            if hasattr(data.deduction_result, "can_continue") and not data.deduction_result.can_continue:
                if hasattr(data.deduction_result, "blocking_errors") and data.deduction_result.blocking_errors:
                    errors.extend(data.deduction_result.blocking_errors)
                else:
                    errors.append(
                        ProcessingIssueV1(
                            code="DEDUCTION_RESOLVER_BLOCKED",
                            field="deduction_result",
                            message="上游 DeductionResolverProcessor 處於 BLOCKED 狀態，無法繼續計算 Line 15",
                        )
                    )

        return errors
