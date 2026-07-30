from decimal import Decimal
from typing import Any, Optional
from form1040.models.credits_model import CreditsProcessorInputV1, CreditsProcessorResultV1


def _get_field(schedule_res: Any, attr_name: str) -> Any:
    if schedule_res is None:
        return None
    if hasattr(schedule_res, attr_name):
        return getattr(schedule_res, attr_name)
    if isinstance(schedule_res, dict):
        return schedule_res.get(attr_name)
    return None


def _extract_amount(schedule_res: Any, attr_name: str) -> Decimal:
    """
    從 Schedule 結果中取出金額欄位。若欄位為 None（Zero Policy 允許的
    CONFIRMED_NOT_PRESENT 合法情況，已由 Validator 確認），視為 Decimal("0")。
    """
    val = _get_field(schedule_res, attr_name)
    if val is None:
        return Decimal("0")
    return Decimal(str(val))


class CreditsCalculator:
    """
    Credits 算術引擎 (Form 1040 Lines 19-24)

    line_19_ctc_odc            = Schedule8812Result.total_ctc_odc
    line_20_schedule3_credits  = Schedule3Result.line_8_total
    line_21_total_credits      = line_19 + line_20
    line_22_tax_after_credits  = max(0, line_18 - line_21)   # 官方明文 floor at 0
    line_23_other_taxes        = Schedule2Result.line_21_total
    line_24_total_tax          = line_22 + line_23
    """

    @staticmethod
    def calculate(data: CreditsProcessorInputV1) -> CreditsProcessorResultV1:
        line_18 = data.line_18_tax_before_credits

        line_19 = _extract_amount(data.schedule_8812_result, "total_ctc_odc")
        line_20 = _extract_amount(data.schedule_3_result, "line_8_total")
        line_21 = line_19 + line_20

        # 官方文字：「Subtract line 21 from line 18. If zero or less, enter -0-」
        # 與 AGI Line 11a 不同，此處必須 floor at 0，不可為負數。
        line_22 = max(Decimal("0"), line_18 - line_21)

        line_23 = _extract_amount(data.schedule_2_result, "line_21_total")
        line_24 = line_22 + line_23

        return CreditsProcessorResultV1(
            line_18_tax_before_credits=line_18,
            line_19_ctc_odc=line_19,
            line_20_schedule3_credits=line_20,
            line_21_total_credits=line_21,
            line_22_tax_after_credits=line_22,
            line_23_other_taxes=line_23,
            line_24_total_tax=line_24,
            status="COMPLETE",
            can_continue=True,
            blocking_errors=[],
        )
