from typing import Optional
from form1040.models.agi_model import AGIProcessorResultV1
from form1040.models.deduction_resolver_model import DeductionResolverResultV1
from form1040.models.taxable_income_model import TaxableIncomeInputV1, TaxableIncomeResultV1
from form1040.validators.taxable_income_validator import TaxableIncomeValidator
from form1040.calculators.taxable_income_calculator import TaxableIncomeCalculator


class TaxableIncomeProcessor:
    """
    Form 1040 Taxable Income 處理器 (Line 15)

    設計原則與模組說明：
    1. 職責劃分：
       - 本模組為極簡純算術與狀態傳遞模組，專職計算 Form 1040 Line 15 = max(Line 11b AGI - Line 14 Deductions, 0)。
       - 不需要 LLM、不呼叫 RAG、不讀取外部稅額表、不直接接觸 Schedule A/B/C/E/1 等細節表單。

    2. 輸入與輸出：
       - 輸入：`AGIProcessorResultV1` 與 `DeductionResolverResultV1`
       - 輸出：`TaxableIncomeResultV1` (含 `line_15_taxable_income`)
    """

    @classmethod
    def process(cls, data: TaxableIncomeInputV1) -> TaxableIncomeResultV1:
        """
        Taxable Income 處理邏輯主進入點 (Pure, Stateless)

        :param data: TaxableIncomeInputV1 包含上游 AGI 與扣除額結果
        :return: TaxableIncomeResultV1
        """
        # 1. 執行輸入與上游狀態驗證
        blocking_errors = TaxableIncomeValidator.validate(data)
        if blocking_errors:
            return TaxableIncomeResultV1.blocked(
                tax_year=data.tax_year,
                errors=blocking_errors,
            )

        # 2. 執行核心計算
        return TaxableIncomeCalculator.calculate(data)

    @classmethod
    def compute(
        cls,
        *,
        agi_result: Optional[AGIProcessorResultV1] = None,
        deduction_result: Optional[DeductionResolverResultV1] = None,
        tax_year: int = 2025,
    ) -> TaxableIncomeResultV1:
        """
        便捷進入點：自動組裝 TaxableIncomeInputV1 並調用 process
        """
        input_dto = TaxableIncomeInputV1(
            tax_year=tax_year,
            agi_result=agi_result,
            deduction_result=deduction_result,
        )
        return cls.process(input_dto)
