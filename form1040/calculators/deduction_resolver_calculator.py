from decimal import Decimal
from typing import Any
from form1040.models.deduction_resolver_model import (
    DeductionResolverInputV1,
    DeductionResolverResultV1,
)


def _to_decimal(val: Any) -> Decimal:
    if val is None:
        return Decimal("0.00")
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal("0.00")


class DeductionResolverCalculator:
    """
    Form 1040 Deduction Section 算術與決策引擎 (Lines 12e, 13a, 13b, 14)
    """

    @staticmethod
    def calculate(data: DeductionResolverInputV1) -> DeductionResolverResultV1:
        # 1. 讀取 Schedule A 輸出結果
        std_amount = Decimal("0.00")
        item_amount = Decimal("0.00")
        elect_itemize = False
        should_attach_sa = False
        review_warnings = []

        sa_res = data.schedule_a_result
        if sa_res is not None:
            std_amount = _to_decimal(getattr(sa_res, "standard_deduction_amount", None))
            item_amount = _to_decimal(getattr(sa_res, "line_17_total_itemized_deductions", None))
            elect_itemize = bool(getattr(sa_res, "line_18_elect_itemize_surface", False))
            should_attach_sa = bool(getattr(sa_res, "should_attach_schedule_a", False))

            # 檢查 Schedule A 是否包含錯誤，若有則紀錄 Review Warning
            can_file = getattr(sa_res, "can_file", True)
            is_v1_supported = getattr(sa_res, "is_v1_supported", True)
            sa_errors = getattr(sa_res, "blocking_errors", []) or []

            if can_file is False or is_v1_supported is False or sa_errors:
                err_msgs = [err.message if hasattr(err, "message") else str(err) for err in sa_errors]
                msg_detail = f" (原因：{'; '.join(err_msgs)})" if err_msgs else ""
                from form1040.models.agi_model import ProcessingIssueV1
                issue = ProcessingIssueV1(
                    code="SCHEDULE_A_FALLBACK_TO_STANDARD",
                    field="schedule_a_result",
                    message=f"Schedule A 檢驗未通過，系統已安全回退選用標準扣除額供人工審核。{msg_detail}"
                )
                review_warnings.append(issue.to_dict() if hasattr(issue, "to_dict") else issue)


        # 若未能從 sa_res 計算出標準扣除額 (std_amount == 0.00)，統一交由 Schedule A 引擎計算出精確標準扣除額 (包含盲人/老人加計金額)
        if std_amount == Decimal("0.00"):
            from processors.models.schedule_a import ScheduleAInputsV1
            from processors.calculators.schedule_a import calculate_schedule_a_v1
            dummy_inputs = ScheduleAInputsV1.from_dict({"tax_year": data.tax_year, "filing_status": data.filing_status})
            dummy_res = calculate_schedule_a_v1(dummy_inputs)
            std_amount = _to_decimal(getattr(dummy_res, "standard_deduction_amount", None))





        # 2. 決定 Line 12e 與抵扣類型
        if elect_itemize:
            # 納稅人主動勾選 Schedule A Line 18：即便列舉金額較小亦選用列舉扣除
            line_12e = item_amount
            is_itemizing = True
            deduction_type = "ITEMIZED"
            should_attach_sa = True
        elif item_amount > std_amount:
            # 列舉扣除金額大於標準扣除金額
            line_12e = item_amount
            is_itemizing = True
            deduction_type = "ITEMIZED"
            should_attach_sa = True
        else:
            # 預設選用標準扣除金額
            line_12e = std_amount
            is_itemizing = False
            deduction_type = "STANDARD"

        # 3. 讀取 Form 8995 (QBI Deduction -> Line 13a)
        line_13a_qbi = Decimal("0.00")
        qbi_res = data.form_8995_result
        if qbi_res is not None:
            qbi_val = getattr(qbi_res, "line_15_qbi_deduction", None)
            if qbi_val is None and isinstance(qbi_res, dict):
                qbi_val = qbi_res.get("line_15_qbi_deduction")
            line_13a_qbi = _to_decimal(qbi_val)

        # 4. 讀取 Schedule 1-A (Additional Deductions Line 38 -> Line 13b)
        line_13b_schedule_1a = Decimal("0.00")
        s1a_res = data.schedule_1a_result
        if s1a_res is not None:
            s1a_val = getattr(s1a_res, "line_38_additional_deductions", None)
            if s1a_val is None and isinstance(s1a_res, dict):
                s1a_val = s1a_res.get("line_38_additional_deductions")
            line_13b_schedule_1a = _to_decimal(s1a_val)

        # 5. 計算 Line 14 = Line 12e + Line 13a + Line 13b
        line_14_total = line_12e + line_13a_qbi + line_13b_schedule_1a

        return DeductionResolverResultV1(
            tax_year=data.tax_year,
            filing_status=data.filing_status,
            line_12e_deduction=line_12e,
            line_13a_qbi_deduction=line_13a_qbi,
            line_13b_schedule_1a_deductions=line_13b_schedule_1a,
            line_14_total_deductions=line_14_total,
            is_itemizing=is_itemizing,
            deduction_type_used=deduction_type,
            should_attach_schedule_a=should_attach_sa,
            status="COMPLETE",
            can_continue=True,
            blocking_errors=[],
            review_warnings=review_warnings,
        )

