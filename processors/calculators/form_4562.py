# =====================================================================
# 說明: 本檔案實現 Form 4562 (Depreciation and Amortization) V1 引擎之
# Layer 2 (正規化與中間計算)，格式參考 processors/calculators/schedule_b.py。
# 核心計算入口為 calculate_form_4562_v1(inputs) -> Form4562ResultV1。
# 依據 docs/how_to_fill_forms_docs/Form4562/form4562_complete.md 撰寫。
# =====================================================================

import os
import json
from decimal import Decimal
from typing import Dict, Any, List, Set, Optional

from processors.models.schedule_a import ValidationIssue
from processors.models.form_4562 import (
    Section179ItemV1,
    MACRSItemV1,
    Form4562InputsV1,
    Form4562ResultV1,
)
from processors.validators.form_4562 import (
    validate_identity,
    validate_tax_year,
    detect_unsupported_cases,
    validate_amounts,
)


def sum_decimal(iterable) -> Decimal:
    """將可迭代項目加總為 Decimal 類型的金額。"""
    s = Decimal("0.00")
    for x in iterable:
        if x is not None:
            s += Decimal(str(x))
    return s


def mask_ssn(raw_ssn) -> str:
    """將 SSN 遮罩為 ***-**-XXXX 格式，供提前 return 與正常計算路徑共用。"""
    raw_ssn = str(raw_ssn or "")
    if len(raw_ssn) >= 4:
        return f"***-**-{raw_ssn[-4:]}"
    return "***-**-XXXX"


def any_special_case(flags) -> bool:
    """判斷是否觸發任一 V1 不支援之特殊案件旗標。"""
    if flags:
        for attr in [
            "has_listed_property",
            "has_vehicle_business_use_questions",
            "has_employer_vehicle_exemption_questions",
            "has_amortization",
            "has_263a_capitalization_calculation_needed",
            "has_unquantified_prior_year_depreciation",
        ]:
            if getattr(flags, attr, False) is True:
                return True
    return False


def calculate_form_4562_v1(inputs: Form4562InputsV1, allowed_years: Optional[Set[int]] = None) -> Form4562ResultV1:
    errors: List[ValidationIssue] = []

    if allowed_years is None:
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            schema_path = os.path.abspath(os.path.join(current_dir, "..", "..", "docs", "how_to_fill_forms_docs", "Form4562", "form_4562_schema.json"))
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_data = json.load(f)
            allowed_years = set(schema_data.get("supported_tax_years", [2024, 2025]))
        except Exception:
            allowed_years = {2024, 2025}

    # 1. Validation identity & tax year
    validate_identity(inputs, errors)
    validate_tax_year(inputs.tax_year, allowed_years, errors)

    if any(e.code == "UNSUPPORTED_TAX_YEAR" for e in errors):
        ssn_masked = mask_ssn(inputs.taxpayer_ssn)
        return Form4562ResultV1(
            taxpayer_name=inputs.taxpayer_name,
            taxpayer_ssn_masked=ssn_masked,
            business_activity_name=inputs.business_activity_name,
            tax_year=inputs.tax_year,
            blocking_errors=errors,
            can_file=False,
        )

    ZERO = Decimal("0.00")

    # 2. Part I: Election To Expense Certain Property Under Section 179

    # Line 4：限額縮減金額（Line 2 減 Line 3，若為負則為 0）
    line_4_reduction_in_limitation = max(ZERO, inputs.line_2_section_179_property_cost - inputs.line_3_section_179_threshold_cost)

    # Line 5：當年度 Section 179 金額上限（Line 1 減 Line 4，若為負則為 0）
    line_5_dollar_limitation = max(ZERO, inputs.line_1_section_179_max_amount - line_4_reduction_in_limitation)

    # Line 6：一般 Section 179 財產已選擇費用化成本小計
    section_179_entries = inputs.section_179_property_items
    line_6_elected_cost_subtotal = sum_decimal(item.elected_cost for item in section_179_entries)

    warnings: List[ValidationIssue] = []
    # Line 2（當年度投入使用之 Section 179 財產「總」成本）與 Line 6 (c)（已選擇費用化成本小計）
    # 概念上不必然相等（Line 2 涵蓋所有投入使用之財產，Line 6 僅列出已選擇費用化的部分），
    # 因此不阻斷；但若 Line 6 加總明顯超過 Line 2，代表資料可能有缺漏或誤植，提示人工複核。
    if line_6_elected_cost_subtotal > inputs.line_2_section_179_property_cost:
        warnings.append(ValidationIssue(
            "SECTION_179_ELECTED_COST_EXCEEDS_LINE_2",
            "line_6_elected_cost_subtotal",
            message="Line 6 elected cost subtotal exceeds Line 2 total Section 179 property cost; please verify source data for omissions."
        ))

    # Line 7：列名財產 Section 179 引用值（V1 若無列名財產則為 0）
    line_7_listed_property_section_179_cost = inputs.line_7_listed_property_section_179_cost if inputs.line_7_listed_property_section_179_cost is not None else ZERO

    # Line 8：Line 6 (c) 與 Line 7 加總
    line_8_total_elected_cost = line_6_elected_cost_subtotal + line_7_listed_property_section_179_cost

    # Line 9：Line 5 與 Line 8 取小
    line_9_tentative_deduction = min(line_5_dollar_limitation, line_8_total_elected_cost)

    # Line 11：業務所得（非負）與 Line 5 取小
    line_11_surface_value = min(max(inputs.line_11_business_income_limitation, ZERO), line_5_dollar_limitation)

    # Line 12：Line 9 加 Line 10，但不超過 Line 11
    line_12_section_179_expense_deduction = min(
        line_9_tentative_deduction + inputs.line_10_carryover_disallowed_deduction,
        line_11_surface_value
    )

    # Line 13：Line 9 加 Line 10 減 Line 12
    line_13_carryover_to_next_year = (
        line_9_tentative_deduction + inputs.line_10_carryover_disallowed_deduction - line_12_section_179_expense_deduction
    )

    # 3. Part III: MACRS Depreciation 彙總
    macrs_gds_entries = inputs.macrs_gds_items
    macrs_ads_entries = inputs.macrs_ads_items

    line_19_gds_total = sum_decimal(item.depreciation_deduction for item in macrs_gds_entries if item.depreciation_deduction is not None)
    line_20_ads_total = sum_decimal(item.depreciation_deduction for item in macrs_ads_entries if item.depreciation_deduction is not None)

    # 4. Part IV: Summary
    line_21_listed_property_summary = ZERO  # V1 不支援 Part V

    line_22_total_depreciation_and_amortization = (
        line_12_section_179_expense_deduction
        + inputs.line_14_special_depreciation_allowance
        + inputs.line_15_section_168f1_election
        + inputs.line_16_other_depreciation
        + inputs.line_17_macrs_prior_years
        + line_19_gds_total
        + line_20_ads_total
        + line_21_listed_property_summary
    )

    # 5. Perform Validation
    detect_unsupported_cases(inputs, errors)
    validate_amounts(inputs, errors)

    # 6. 申報判定
    has_special_case = any_special_case(inputs.special_case_flags)

    is_form_4562_required = (
        inputs.line_2_section_179_property_cost > ZERO
        or line_9_tentative_deduction > ZERO
        or inputs.line_14_special_depreciation_allowance > ZERO
        or inputs.line_15_section_168f1_election > ZERO
        or inputs.line_16_other_depreciation > ZERO
        or inputs.line_17_macrs_prior_years > ZERO
        or len(macrs_gds_entries) > 0
        or len(macrs_ads_entries) > 0
        or has_special_case
    )

    # Mask taxpayer SSN
    taxpayer_ssn_masked = mask_ssn(inputs.taxpayer_ssn)

    is_v1_supported = not has_special_case
    can_file = is_v1_supported and len(errors) == 0
    should_attach_form_4562 = is_form_4562_required and can_file

    return Form4562ResultV1(
        taxpayer_name=inputs.taxpayer_name,
        taxpayer_ssn_masked=taxpayer_ssn_masked,
        business_activity_name=inputs.business_activity_name,
        tax_year=inputs.tax_year,
        line_1_section_179_max_amount=inputs.line_1_section_179_max_amount,
        line_2_section_179_property_cost=inputs.line_2_section_179_property_cost,
        line_3_section_179_threshold_cost=inputs.line_3_section_179_threshold_cost,
        line_4_reduction_in_limitation=line_4_reduction_in_limitation,
        line_5_dollar_limitation=line_5_dollar_limitation,
        section_179_entries=section_179_entries,
        line_6_elected_cost_subtotal=line_6_elected_cost_subtotal,
        line_7_listed_property_section_179_cost=line_7_listed_property_section_179_cost,
        line_8_total_elected_cost=line_8_total_elected_cost,
        line_9_tentative_deduction=line_9_tentative_deduction,
        line_10_carryover_disallowed_deduction=inputs.line_10_carryover_disallowed_deduction,
        line_11_surface_value=line_11_surface_value,
        line_12_section_179_expense_deduction=line_12_section_179_expense_deduction,
        line_13_carryover_to_next_year=line_13_carryover_to_next_year,
        line_14_special_depreciation_allowance=inputs.line_14_special_depreciation_allowance,
        line_15_section_168f1_election=inputs.line_15_section_168f1_election,
        line_16_other_depreciation=inputs.line_16_other_depreciation,
        line_17_macrs_prior_years=inputs.line_17_macrs_prior_years,
        line_18_general_asset_account_election=inputs.line_18_general_asset_account_election,
        macrs_gds_entries=macrs_gds_entries,
        line_19_gds_total=line_19_gds_total,
        macrs_ads_entries=macrs_ads_entries,
        line_20_ads_total=line_20_ads_total,
        line_21_listed_property_summary=line_21_listed_property_summary,
        line_22_total_depreciation_and_amortization=line_22_total_depreciation_and_amortization,
        line_23a_263a_interest=inputs.amortization_costs_263a_interest,
        line_23b_263a_other=inputs.amortization_costs_263a_other,
        is_form_4562_required=is_form_4562_required,
        blocking_errors=errors,
        review_warnings=warnings,
        blocking_validation_error=(len(errors) > 0),
        is_v1_supported=is_v1_supported,
        can_file=can_file,
        should_attach_form_4562=should_attach_form_4562,
    )
