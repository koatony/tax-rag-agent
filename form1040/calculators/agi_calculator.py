from decimal import Decimal
from form1040.models.agi_model import AGIProcessorInputV1, AGIProcessorResultV1


class AGICalculator:
    """
    AGI 算術引擎 (Form 1040 Line 11 = Line 9 - Line 10)
    """

    @staticmethod
    def calculate(data: AGIProcessorInputV1) -> AGIProcessorResultV1:
        # 從 schedule_1_result 中取得 Line 26 調整值
        line_10 = Decimal("0")
        s1_res = data.schedule_1_result
        if s1_res is not None:
            val = None
            if hasattr(s1_res, "line_26_adjustments_to_income"):
                val = getattr(s1_res, "line_26_adjustments_to_income")
            elif isinstance(s1_res, dict):
                val = s1_res.get("line_26_adjustments_to_income")
                if val is None:
                    val = s1_res.get("line26")
            
            if val is not None:
                line_10 = Decimal(str(val))

        line_9 = data.line_9_total_income
        
        # 計算 Form 1040 Line 11 (AGI = Line 9 - Line 10)
        line_11 = None
        if line_9 is not None and line_10 is not None:
            line_11 = line_9 - line_10

        return AGIProcessorResultV1(
            line_9_total_income=line_9,
            line_10_adjustments_to_income=line_10,
            line_11_adjusted_gross_income=line_11,
            status="COMPLETE",
            can_continue=True,
            blocking_errors=[],
        )
