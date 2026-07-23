from form1040.models.agi_model import (
    AGIProcessorInputV1,
    AGIProcessorResultV1,
)
from form1040.validators.agi_validator import AGIValidator
from form1040.calculators.agi_calculator import AGICalculator


class AGIProcessor:
    """AGI Processor 統一進入點類別"""

    @staticmethod
    def process(data: AGIProcessorInputV1) -> AGIProcessorResultV1:
        """
        AGI 處理邏輯進入點，調度 Validator 與 Calculator。
        
        計算公式：Line 11 (AGI) = Line 9 (總收入) - Line 10 (來自 Schedule 1 Line 26 的扣除調整項)
        """
        errors = AGIValidator.validate(data)
        if errors:
            return AGIProcessorResultV1(
                line_9_total_income=data.line_9_total_income,
                line_10_adjustments_to_income=None,
                line_11_adjusted_gross_income=None,
                status="BLOCKED",
                can_continue=False,
                blocking_errors=errors,
            )

        # 進行 AGI 核心運算：
        # 1. 從 Schedule 1 的計算結果中提取 Line 26 的總調整扣除額 (作為 Form 1040 Line 10)
        # 2. 進行 AGI 減法公式運算：Form 1040 Line 11 (AGI) = Line 9 (總收入) - Line 10 (調整項)
        # 3. 回傳 COMPLETE 狀態及計算結果
        return AGICalculator.calculate(data)


