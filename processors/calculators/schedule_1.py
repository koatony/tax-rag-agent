# =====================================================================
# 說明: 本檔案實現 Schedule 1 (Form 1040) V1 引擎之 Layer 2 (正規化與中間計算)，
# 格式參考 processors/calculators/schedule_b.py。
# 核心計算入口為 calculate_schedule_1_v1(inputs) -> Schedule1ResultV1。
# 依據 docs/how_to_fill_forms_docs/schedule_1/schedule1_complete.md 撰寫。
# =====================================================================

import os
import json
from decimal import Decimal
from typing import Dict, Any, List, Set, Optional

from processors.models.schedule_a import ValidationIssue
from processors.models.schedule_1 import (
    OtherIncomeItemV1,
    AdjustmentItemV1,
    Schedule1InputsV1,
    Schedule1ResultV1,
)
from processors.validators.schedule_1 import (
    validate_identity,
    validate_tax_year,
    detect_unsupported_cases,
    validate_amounts,
    SUPPORTED_PART_II_LINES,
)


def sum_decimal(iterable) -> Decimal:
    """將可迭代項目加總為 Decimal 類型的金額。"""
    s = Decimal("0.00")
    for x in iterable:
        if x is not None:
            s += Decimal(str(x))
    return s


def signed_amount(item: OtherIncomeItemV1) -> Decimal:
    """
    Line 8a、8d、8s 等表單上以括號呈現之減項，轉換為負值計入 Line 9 加總；
    其餘項目維持正值。
    """
    return -item.amount if item.is_negative_adjustment else item.amount


def any_special_case(flags) -> bool:
    """判斷是否觸發任一 V1 不支援之特殊案件旗標。"""
    if flags:
        for attr in [
            "has_schedule_f_income",
            "has_form_4797_or_4684",
            "has_schedule_se_deduction",
            "has_form_2106",
            "has_form_3903",
            "has_form_8889",
            "has_form_8853",
            "has_archer_msa_deduction",
            "has_form_2555",
            "has_digital_assets_income",
            "has_nonqualified_deferred_comp",
            "has_incarcerated_wages",
            "has_able_account_distribution",
            "has_medicaid_waiver_adjustment",
            "has_section_951_inclusion",
            "has_excess_business_loss_adjustment",
            "has_k1_section_67e_deduction",
        ]:
            if getattr(flags, attr, False) is True:
                return True
    return False


def calculate_schedule_1_v1(inputs: Schedule1InputsV1, allowed_years: Optional[Set[int]] = None) -> Schedule1ResultV1:
    errors: List[ValidationIssue] = []

    if allowed_years is None:
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            schema_path = os.path.abspath(os.path.join(current_dir, "..", "..", "docs", "how_to_fill_forms_docs", "schedule_1", "schedule_1_schema.json"))
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_data = json.load(f)
            allowed_years = set(schema_data.get("supported_tax_years", [2024, 2025]))
        except Exception:
            allowed_years = {2024, 2025}

    # 1. Validation identity & tax year
    validate_identity(inputs, errors)
    validate_tax_year(inputs.tax_year, allowed_years, errors)

    if any(e.code == "UNSUPPORTED_TAX_YEAR" for e in errors):
        raw_ssn = str(inputs.taxpayer_ssn or "")
        ssn_masked = f"***-**-{raw_ssn[-4:]}" if len(raw_ssn) >= 4 else "***-**-XXXX"
        return Schedule1ResultV1(
            taxpayer_name=inputs.taxpayer_name,
            taxpayer_ssn_masked=ssn_masked,
            tax_year=inputs.tax_year,
            blocking_errors=errors,
            can_file=False,
        )

    # 2. Part I: Additional Income

    # Line 3：引用已完成 Schedule C Line 31（若尚未提供則以 0.00 代入）
    line_3_business_income = inputs.schedule_c_line_31 if inputs.schedule_c_line_31 is not None else Decimal("0.00")

    # Line 5：引用已完成 Schedule E Line 41（若尚未提供則以 0.00 代入）
    line_5_rental_royalty_income = inputs.schedule_e_line_41 if inputs.schedule_e_line_41 is not None else Decimal("0.00")

    # Line 9：Line 8a 至 8z 加總（括號減項以負值計入）
    other_income_entries = inputs.other_income_items
    line_9_total_other_income = sum_decimal(signed_amount(item) for item in other_income_entries)

    # Line 10：Lines 1-7 及 9 合計，等於 Form 1040 Line 8
    line_10_additional_income = (
        inputs.line_1_state_local_tax_refund
        + inputs.line_2a_alimony_received
        + line_3_business_income
        + inputs.line_4_other_gains_or_losses
        + line_5_rental_royalty_income
        + inputs.line_6_farm_income
        + inputs.line_7_unemployment_compensation
        + line_9_total_other_income
    )

    # 3. Part II: Adjustments to Income

    adjustment_entries = inputs.adjustment_items

    # 檢查調整項目之扣除資格審核警告
    warnings: List[ValidationIssue] = []
    for item in adjustment_entries:
        if getattr(item, "is_deductibility_confirmed", True) is False:
            warnings.append(ValidationIssue(
                "UNCONFIRMED_DEDUCTIBILITY",
                field="is_deductibility_confirmed",
                item_id=item.item_id,
                message=f"根據美國稅法 IRC §219 及 IRS 規定，Line {item.line_code} 扣除額資格尚待驗證（需確認職場退休計畫覆蓋與 AGI / MAGI 限額），目前先按原始金額 ${item.amount} 納入計算，需要人工審核複查。"
            ))

    # Line 25：Line 24a 至 24z 加總
    line_25_total_other_adjustments = sum_decimal(
        item.amount for item in adjustment_entries if item.line_code and item.line_code.startswith("24")
    )

    # Line 26：V1 支援之 Line 11-23 子集加總，加上 Line 25
    line_26_adjustments_to_income = sum_decimal(
        item.amount for item in adjustment_entries if item.line_code in SUPPORTED_PART_II_LINES
    ) + line_25_total_other_adjustments

    # 4. Perform Validation
    detect_unsupported_cases(inputs, errors)
    validate_amounts(inputs, errors)

    # 5. 申報判定
    has_special_case = any_special_case(inputs.special_case_flags)

    is_schedule_1_required = (
        line_10_additional_income != Decimal("0.00")
        or line_26_adjustments_to_income != Decimal("0.00")
        or has_special_case
    )

    # Mask taxpayer SSN
    raw_ssn = str(inputs.taxpayer_ssn or "")
    if len(raw_ssn) >= 4:
        taxpayer_ssn_masked = f"***-**-{raw_ssn[-4:]}"
    else:
        taxpayer_ssn_masked = "***-**-XXXX"

    is_v1_supported = not has_special_case
    can_file = is_v1_supported and len(errors) == 0 and len(warnings) == 0
    should_attach_schedule_1 = is_schedule_1_required and can_file

    return Schedule1ResultV1(
        taxpayer_name=inputs.taxpayer_name,
        taxpayer_ssn_masked=taxpayer_ssn_masked,
        tax_year=inputs.tax_year,
        form_1099k_error_or_personal_loss_amount=inputs.form_1099k_error_or_personal_loss_amount,
        line_1_state_local_tax_refund=inputs.line_1_state_local_tax_refund,
        line_2a_alimony_received=inputs.line_2a_alimony_received,
        line_2b_original_agreement_date=inputs.line_2b_original_agreement_date,
        line_3_business_income=line_3_business_income,
        line_4_other_gains_or_losses=inputs.line_4_other_gains_or_losses,
        line_5_rental_royalty_income=line_5_rental_royalty_income,
        line_6_farm_income=inputs.line_6_farm_income,
        line_7_unemployment_compensation=inputs.line_7_unemployment_compensation,
        other_income_entries=other_income_entries,
        line_9_total_other_income=line_9_total_other_income,
        line_10_additional_income=line_10_additional_income,
        line_19b_recipient_ssn=inputs.line_19b_recipient_ssn,
        line_19c_original_agreement_date=inputs.line_19c_original_agreement_date,
        adjustment_entries=adjustment_entries,
        line_25_total_other_adjustments=line_25_total_other_adjustments,
        line_26_adjustments_to_income=line_26_adjustments_to_income,
        is_schedule_1_required=is_schedule_1_required,
        blocking_errors=errors,
        review_warnings=warnings,
        blocking_validation_error=(len(errors) > 0),
        is_v1_supported=is_v1_supported,
        can_file=can_file,
        should_attach_schedule_1=should_attach_schedule_1,
    )
