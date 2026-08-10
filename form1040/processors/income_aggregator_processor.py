from typing import Optional
from form1040.models.income_aggregator_model import (
    IncomeAggregatorInputV1,
    IncomeSectionResultV1,
    DirectIncomeInputV1,
    ScheduleBResultV1,
    ScheduleDResultV1,
    Schedule1ResultV1,
)

from form1040.validators.income_aggregator_validator import IncomeAggregatorValidator
from form1040.calculators.income_aggregator_calculator import IncomeAggregatorCalculator


class IncomeAggregatorProcessor:
    """
    Form 1040 Income Aggregator 處理器 (Lines 1a–9)
    負責組裝與調度 Parser, Validator 與 Calculator 進行所得總額彙整。
    """

    @classmethod
    def process(cls, data: IncomeAggregatorInputV1) -> IncomeSectionResultV1:
        """
        核心所得彙整邏輯進入點 (Pure, Stateless)
        """
        # 1. Normalization (確保 direct_income_input 不為 None)
        if data.direct_income_input is None:
            data.direct_income_input = DirectIncomeInputV1()

        # 2. 執行業務邏輯與一致性驗證
        blocking_errors = IncomeAggregatorValidator.validate(data)
        if blocking_errors:
            return IncomeSectionResultV1.blocked(
                tax_year=data.tax_year,
                filing_status=data.filing_status,
                errors=blocking_errors,
            )

        # 3. 執行純算術加總：
        return IncomeAggregatorCalculator.calculate(data)
