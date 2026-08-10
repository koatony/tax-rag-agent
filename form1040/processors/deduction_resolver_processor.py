from typing import Optional
from form1040.models.deduction_resolver_model import (
    DeductionResolverInputV1,
    DeductionResolverResultV1,
    Form8995ResultV1,
    Schedule1AResultV1,
)
from form1040.validators.deduction_resolver_validator import DeductionResolverValidator
from form1040.calculators.deduction_resolver_calculator import DeductionResolverCalculator
from processors.models.schedule_a import ScheduleAResultV1


class DeductionResolverProcessor:
    """
    Form 1040 Deduction Resolver 處理器 (Lines 12e, 13a, 13b, 14)

    設計原則與模組說明：
    1. Schedule A (`ScheduleAProcessor`)：
       - 已完整實作於 `processors/processors/schedule_a.py`。
       - 輸出 `ScheduleAResultV1` 包含 `standard_deduction_amount`、`line_17_total_itemized_deductions`
         與 `line_18_elect_itemize_surface`。
       - 本處理器在決定 Line 12e 時，優先檢視 Schedule A 之計算與決策結果。

    2. QBI Deduction (Form 8995/8995-A) 與 Schedule 1-A (Additional Deductions)：
       - 由於 Form 8995 與 Schedule 1-A 模組目前尚未建立，本模組先採用替代 DTO (`Form8995ResultV1`
         與 `Schedule1AResultV1`) 作為預留符號。
       - 未傳入時預設扣除金額為 `0.00`。
    """

    @classmethod
    def process(cls, data: DeductionResolverInputV1) -> DeductionResolverResultV1:
        """
        扣除額處理邏輯進入點 (Pure, Stateless)

        計算公式：
        - Line 12e = Standard Deduction 或 Itemized Deduction (預設選擇較大者；若勾選 Line 18 Elect Itemize 則強行選擇 Itemized)
        - Line 13a = Form 8995 Line 15 QBI Deduction
        - Line 13b = Schedule 1-A Line 38 Additional Deductions
        - Line 14  = Line 12e + Line 13a + Line 13b
        """
        # 1. 執行合規性驗證與上游模組阻斷錯誤傳遞
        blocking_errors = DeductionResolverValidator.validate(data)
        if blocking_errors:
            return DeductionResolverResultV1.blocked(
                tax_year=data.tax_year,
                filing_status=data.filing_status,
                errors=blocking_errors,
            )

        # 2. 執行核心決策與算術加總
        return DeductionResolverCalculator.calculate(data)
