from typing import List, Set, Optional
from decimal import Decimal
from processors.models.schedule_a import ValidationIssue  # reuse ValidationIssue since it is a general class
from processors.models.form_4562 import Form4562InputsV1, SpecialCaseFlags4562V1

# Part III Section B (GDS) 官方已定義代碼
GDS_CODES = {"19a", "19b", "19c", "19d", "19e", "19f", "19g", "19h", "19i", "19j"}
# Part III Section C (ADS) 官方已定義代碼
ADS_CODES = {"20a", "20b", "20c", "20d", "20e"}


def validate_identity(inputs: Form4562InputsV1, errors: List[ValidationIssue]):
    """
    驗證納稅人基本身分資訊。
    - 確保納稅人姓名不為空。
    - 確保納稅人社會安全號碼 (SSN) 不為空。
    """
    if not inputs.taxpayer_name.strip():
        errors.append(ValidationIssue("MISSING_TAXPAYER_NAME", "taxpayer_name", message="Taxpayer name is missing."))
    if not inputs.taxpayer_ssn.strip():
        errors.append(ValidationIssue("MISSING_TAXPAYER_SSN", "taxpayer_ssn", message="Taxpayer SSN is missing."))


def validate_tax_year(tax_year: Optional[int], allowed: Set[int], errors: List[ValidationIssue]):
    """
    驗證申報年度是否在支援範圍內。
    """
    if tax_year is None:
        errors.append(ValidationIssue("UNSUPPORTED_TAX_YEAR", "tax_year", message="Tax year is missing in input data."))
    elif tax_year not in allowed:
        errors.append(ValidationIssue("UNSUPPORTED_TAX_YEAR", "tax_year", message=f"Tax year {tax_year} is not supported."))


def detect_unsupported_cases(inputs: Form4562InputsV1, errors: List[ValidationIssue]):
    """
    偵測 Form 4562 是否包含 V1 版本不支援的複雜情況。
    若偵測到不支援情況，記錄 ValidationIssue。
    """
    flags = inputs.special_case_flags

    # 1. Listed Property (列名財產)：涉及奢侈車限額、Section 280F 復歸、商業使用比例測試，V1 暫不支援。
    if flags.has_listed_property:
        errors.append(ValidationIssue("UNSUPPORTED_LISTED_PROPERTY", "part_v", message="Listed property (Part V) is not supported in V1."))

    # 2. Vehicle Business Use Questionnaire (Part V Section B)：5% 以上股東或關係人使用車輛之問卷，V1 暫不支援。
    if flags.has_vehicle_business_use_questions:
        errors.append(ValidationIssue("UNSUPPORTED_VEHICLE_USE_QUESTIONNAIRE", "part_v_section_b", message="Vehicle business use questionnaire (Part V Section B) is not supported in V1."))

    # 3. Employer Vehicle Exemption Questionnaire (Part V Section C)：雇主提供車輛豁免判定，V1 暫不支援。
    if flags.has_employer_vehicle_exemption_questions:
        errors.append(ValidationIssue("UNSUPPORTED_EMPLOYER_VEHICLE_EXEMPTION", "part_v_section_c", message="Employer vehicle exemption questionnaire (Part V Section C) is not supported in V1."))

    # 4. Amortization (Part VI)：依 Code Section 判定攤銷期間與可攤銷金額，V1 暫不支援。
    if flags.has_amortization:
        errors.append(ValidationIssue("UNSUPPORTED_AMORTIZATION", "part_vi", message="Amortization (Part VI) is not supported in V1."))

    # 5. Section 263A Capitalization Calculation：資本化成本之實際計算，V1 僅接收並揭露，不計算。
    if flags.has_263a_capitalization_calculation_needed:
        errors.append(ValidationIssue("UNSUPPORTED_263A_CAPITALIZATION_CALCULATION", "line_23a_23b", message="Section 263A capitalization calculation is not supported in V1."))

    # 6. Unquantified Prior Year Depreciation (偵測到折舊資產但缺已計算完成之金額)：
    # 文件中提到折舊基礎（如建物成本）與投入使用日期，但沒有給出已計算完成的年度折舊扣除額，
    # Line 17 又是單一總額欄位、無法像 Line 19/20 個別資產一樣以留空觸發阻斷，故需獨立旗標防止靜默漏報。
    if flags.has_unquantified_prior_year_depreciation:
        errors.append(ValidationIssue("UNQUANTIFIED_PRIOR_YEAR_DEPRECIATION", "line_17_macrs_prior_years", message="Depreciable property (basis/date placed in service) was found but no pre-computed annual depreciation amount was provided; Line 17 cannot be silently left as 0."))

    # 7. Listed Property Section 179 引用但 Part V 未完成：Line 7 依賴 Part V Line 29，若 Part V 未支援則不得引用。
    if inputs.line_7_listed_property_section_179_cost is not None and inputs.line_7_listed_property_section_179_cost > Decimal("0.00") and not flags.has_listed_property:
        errors.append(ValidationIssue("UNSUPPORTED_LISTED_PROPERTY_SECTION_179_REFERENCE", "line_7_listed_property_section_179_cost", message="Line 7 references Part V Line 29 but listed property (Part V) is not confirmed as completed."))


def validate_amounts(inputs: Form4562InputsV1, errors: List[ValidationIssue]):
    """
    驗證所有金額欄位是否為非負數，並確認 Part III MACRS 項目具備已計算完成之
    depreciation_deduction 值，以及 line_code 是否為官方已知代碼。
    """
    ZERO = Decimal("0.00")

    if inputs.line_1_section_179_max_amount < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "line_1_section_179_max_amount", message="Section 179 max amount cannot be negative."))
    if inputs.line_2_section_179_property_cost < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "line_2_section_179_property_cost", message="Section 179 property cost cannot be negative."))
    if inputs.line_3_section_179_threshold_cost < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "line_3_section_179_threshold_cost", message="Section 179 threshold cost cannot be negative."))
    if inputs.line_10_carryover_disallowed_deduction < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "line_10_carryover_disallowed_deduction", message="Carryover of disallowed deduction cannot be negative."))
    if inputs.line_14_special_depreciation_allowance < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "line_14_special_depreciation_allowance", message="Special depreciation allowance cannot be negative."))
    if inputs.line_15_section_168f1_election < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "line_15_section_168f1_election", message="Section 168(f)(1) election amount cannot be negative."))
    if inputs.line_16_other_depreciation < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "line_16_other_depreciation", message="Other depreciation cannot be negative."))
    if inputs.line_17_macrs_prior_years < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "line_17_macrs_prior_years", message="MACRS deductions for prior years cannot be negative."))
    if inputs.line_7_listed_property_section_179_cost is not None and inputs.line_7_listed_property_section_179_cost < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "line_7_listed_property_section_179_cost", message="Listed property Section 179 cost cannot be negative."))

    for item in inputs.section_179_property_items:
        if item.cost_business_use_only < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "cost_business_use_only", item.item_id, message="Section 179 property cost cannot be negative."))
        if item.elected_cost < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "elected_cost", item.item_id, message="Section 179 elected cost cannot be negative."))
        if item.elected_cost > item.cost_business_use_only:
            errors.append(ValidationIssue("ELECTED_COST_EXCEEDS_PROPERTY_COST", "elected_cost", item.item_id, message="Elected cost exceeds property cost (business use only)."))

    for item in inputs.macrs_gds_items:
        if item.line_code not in GDS_CODES:
            errors.append(ValidationIssue("UNKNOWN_LINE_CODE", "line_code", item.item_id, message=f"Unknown Part III Section B (GDS) line code: {item.line_code}."))
        if item.depreciation_deduction is None:
            errors.append(ValidationIssue("MACRS_DEDUCTION_NOT_PROVIDED", "depreciation_deduction", item.item_id, message="MACRS depreciation deduction (GDS) was not provided as a pre-computed final value."))
        elif item.depreciation_deduction < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "depreciation_deduction", item.item_id, message="MACRS depreciation deduction cannot be negative."))
        if item.depreciation_basis is not None and item.depreciation_basis < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "depreciation_basis", item.item_id, message="MACRS depreciation basis cannot be negative."))

    for item in inputs.macrs_ads_items:
        if item.line_code not in ADS_CODES:
            errors.append(ValidationIssue("UNKNOWN_LINE_CODE", "line_code", item.item_id, message=f"Unknown Part III Section C (ADS) line code: {item.line_code}."))
        if item.depreciation_deduction is None:
            errors.append(ValidationIssue("MACRS_DEDUCTION_NOT_PROVIDED", "depreciation_deduction", item.item_id, message="MACRS depreciation deduction (ADS) was not provided as a pre-computed final value."))
        elif item.depreciation_deduction < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "depreciation_deduction", item.item_id, message="MACRS depreciation deduction cannot be negative."))
        if item.depreciation_basis is not None and item.depreciation_basis < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "depreciation_basis", item.item_id, message="MACRS depreciation basis cannot be negative."))
