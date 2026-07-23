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
    def compute(
        cls,
        *,
        tax_year: int,
        filing_status: str,
        direct_income_input: DirectIncomeInputV1,
        schedule_b_result: Optional[ScheduleBResultV1] = None,
        schedule_d_result: Optional[ScheduleDResultV1] = None,
        schedule_1_result: Optional[Schedule1ResultV1] = None,
    ) -> IncomeSectionResultV1:
        """
        核心計算進入點 (Pure, Stateless)
        """

        # 1. Normalization (確保不為 None)
        parsed_direct_income = direct_income_input or DirectIncomeInputV1()

        # 2. 建立標準 Input DTO
        input_dto = IncomeAggregatorInputV1(
            tax_year=tax_year,
            filing_status=filing_status,
            direct_income_input=parsed_direct_income,
            schedule_b_result=schedule_b_result,
            schedule_d_result=schedule_d_result,
            schedule_1_result=schedule_1_result,
        )

        # 3. 執行業務邏輯與一致性驗證
        blocking_errors = IncomeAggregatorValidator.validate(input_dto)
        if blocking_errors:
            return IncomeSectionResultV1.blocked(
                tax_year=tax_year,
                filing_status=filing_status,
                errors=blocking_errors,
            )

        # 4. 執行純算術加總：
        # - Line 1a & Line 1z: W-2 薪資總和
        # - Line 2b & Line 3b: Schedule B 的應稅利息與普通股利
        # - Line 4b, 5b, 6b: IRA/退休金/社福金的應稅金額
        # - Line 7a: Schedule D 的資本損益
        # - Line 8: Schedule 1 Line 10 的額外收入
        # - Line 9 (總收入) = Line 1z + 2b + 3b + 4b + 5b + 6b + 7a + 8
        return IncomeAggregatorCalculator.calculate(input_dto)
