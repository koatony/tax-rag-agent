from typing import Optional, Union, Dict, Any
from form1040.models.income_aggregator_model import (
    IncomeAggregatorInputV1,
    IncomeSectionResultV1,
    DirectIncomeInputV1,
    ScheduleBResultV1,
    ScheduleDResultV1,
    Schedule1ResultV1,
)
from form1040.parsers.direct_income_parser import DirectIncomeParser
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
        direct_income_input: Union[DirectIncomeInputV1, Dict[str, Any]],
        schedule_b_result: Optional[ScheduleBResultV1] = None,
        schedule_d_result: Optional[ScheduleDResultV1] = None,
        schedule_1_result: Optional[Schedule1ResultV1] = None,
    ) -> IncomeSectionResultV1:
        """
        核心計算進入點 (Pure, Stateless)
        """

        # 1. Parsing & Normalization (將 Dict 適配轉為 DirectIncomeInputV1)
        if isinstance(direct_income_input, dict):
            parsed_direct_income = DirectIncomeParser.parse_dict(direct_income_input)
        else:
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

        # 4. 執行純算術加總
        return IncomeAggregatorCalculator.calculate(input_dto)
