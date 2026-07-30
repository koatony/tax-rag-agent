from form1040.models.credits_model import (
    CreditsProcessorInputV1,
    CreditsProcessorResultV1,
)
from form1040.validators.credits_validator import CreditsValidator
from form1040.calculators.credits_calculator import CreditsCalculator


class CreditsProcessor:
    """CreditsProcessor 統一進入點類別 (Form 1040 Lines 19-24: Credits & Total Tax)"""

    @staticmethod
    def process(data: CreditsProcessorInputV1) -> CreditsProcessorResultV1:
        """
        Credits 處理邏輯進入點，調度 Validator 與 Calculator。

        計算公式：
        Line 21 (Total credits) = Line 19 (CTC/ODC) + Line 20 (Schedule 3, Line 8)
        Line 22 (Tax after credits) = max(0, Line 18 - Line 21)
        Line 24 (Total tax) = Line 22 + Line 23 (Schedule 2, Line 21)
        """
        errors = CreditsValidator.validate(data)
        if errors:
            return CreditsProcessorResultV1(
                line_18_tax_before_credits=data.line_18_tax_before_credits,
                line_19_ctc_odc=None,
                line_20_schedule3_credits=None,
                line_21_total_credits=None,
                line_22_tax_after_credits=None,
                line_23_other_taxes=None,
                line_24_total_tax=None,
                status="BLOCKED",
                can_continue=False,
                blocking_errors=errors,
            )

        # 進行 Credits 核心運算：
        # 1. 從 Schedule 8812 / Schedule 3 取得抵免額，加總為 Line 21
        # 2. Line 22 = max(0, Line 18 - Line 21)（官方明文 floor at 0）
        # 3. 從 Schedule 2 取得其他稅額，加總為 Line 24 (Total Tax)
        # 4. 回傳 COMPLETE 狀態及計算結果
        return CreditsCalculator.calculate(data)
