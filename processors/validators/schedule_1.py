from typing import List, Set, Optional
from decimal import Decimal
from processors.models.schedule_a import ValidationIssue  # reuse ValidationIssue since it is a general class
from processors.models.schedule_1 import Schedule1InputsV1, SpecialCaseFlags1V1

# Part II Line 11-23 中 V1 支援直接輸出的子集
SUPPORTED_PART_II_LINES = {"11", "16", "17", "18", "19a", "20", "21"}
# Part I Line 8a-8z 中 V1 支援之代碼（含括號減項 8a/8d/8s）
SUPPORTED_LINE_8_CODES = {
    "8a", "8b", "8c", "8d", "8g", "8h", "8i", "8j", "8k", "8l", "8m", "8s", "8v", "8z",
}
# Part II Line 24a-24z 中 V1 支援之代碼
SUPPORTED_LINE_24_CODES = {"24a", "24c", "24e", "24f", "24g", "24h", "24i", "24z"}
# Part II Line 11-23 中所有已定義之官方代碼（用於偵測未知代碼；不支援計算之代碼由 detect_unsupported_cases 阻斷）
ALL_KNOWN_PART_II_LINES = {"11", "12", "13", "14", "15", "16", "17", "18", "19a", "20", "21", "23"}
# Part I Line 8a-8z 中所有已定義之官方代碼
ALL_KNOWN_LINE_8_CODES = {
    "8a", "8b", "8c", "8d", "8e", "8f", "8g", "8h", "8i", "8j", "8k", "8l",
    "8m", "8n", "8o", "8p", "8q", "8r", "8s", "8t", "8u", "8v", "8z",
}
# Part II Line 24a-24z 中所有已定義之官方代碼
ALL_KNOWN_LINE_24_CODES = {"24a", "24b", "24c", "24d", "24e", "24f", "24g", "24h", "24i", "24j", "24k", "24z"}


def validate_identity(inputs: Schedule1InputsV1, errors: List[ValidationIssue]):
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


def detect_unsupported_cases(inputs: Schedule1InputsV1, errors: List[ValidationIssue]):
    """
    偵測 Schedule 1 是否包含 V1 版本不支援的複雜情況（需另行計算之附屬表單）。
    若偵測到不支援情況，記錄 ValidationIssue。
    """
    flags = inputs.special_case_flags

    # 1. Schedule F 農場所得或虧損 (Line 6)：計算複雜，需完整附表，V1 暫不支援。
    if flags.has_schedule_f_income:
        errors.append(ValidationIssue("UNSUPPORTED_SCHEDULE_F", "line_6_farm_income", message="Schedule F farm income/loss is not supported in V1."))

    # 2. Form 4797／Form 4684 其他利得或虧損 (Line 4)：需依附屬表單計算，V1 暫不支援。
    if flags.has_form_4797_or_4684:
        errors.append(ValidationIssue("UNSUPPORTED_FORM_4797_4684", "line_4_other_gains_or_losses", message="Form 4797/4684 other gains or losses is not supported in V1."))

    # 3. Schedule SE 自雇稅可扣除部分 (Line 15)：需依附屬表單計算，V1 暫不支援。
    if flags.has_schedule_se_deduction:
        errors.append(ValidationIssue("UNSUPPORTED_SCHEDULE_SE_DEDUCTION", "line_15", message="Deductible part of self-employment tax is not supported in V1."))

    # 4. Form 2106 預備役／表演藝術家／按件計酬政府官員費用 (Line 12)：V1 暫不支援。
    if flags.has_form_2106:
        errors.append(ValidationIssue("UNSUPPORTED_FORM_2106", "line_12", message="Form 2106 business expenses is not supported in V1."))

    # 5. Form 3903 軍人搬遷費用 (Line 14)：V1 暫不支援。
    if flags.has_form_3903:
        errors.append(ValidationIssue("UNSUPPORTED_FORM_3903", "line_14", message="Form 3903 moving expenses is not supported in V1."))

    # 6. Form 8889 HSA 扣除額／分配所得 (Line 13／8f)：V1 暫不支援。
    if flags.has_form_8889:
        errors.append(ValidationIssue("UNSUPPORTED_FORM_8889", "line_13", message="Form 8889 HSA deduction/income is not supported in V1."))

    # 7. Form 8853 Archer MSA／Long-term care 所得 (Line 8e)：V1 暫不支援。
    if flags.has_form_8853:
        errors.append(ValidationIssue("UNSUPPORTED_FORM_8853", "line_8e", message="Form 8853 income is not supported in V1."))

    # 8. Archer MSA 扣除額 (Line 23)：V1 暫不支援。
    if flags.has_archer_msa_deduction:
        errors.append(ValidationIssue("UNSUPPORTED_ARCHER_MSA_DEDUCTION", "line_23", message="Archer MSA deduction is not supported in V1."))

    # 9. Form 2555 海外所得排除／住房扣除 (Line 8d／24j)：V1 暫不支援。
    if flags.has_form_2555:
        errors.append(ValidationIssue("UNSUPPORTED_FORM_2555", "line_8d", message="Form 2555 foreign earned income exclusion/housing deduction is not supported in V1."))

    # 10. 數位資產所得 (Line 8v)：V1 暫不支援自動判定歸類，需人工確認。
    if flags.has_digital_assets_income:
        errors.append(ValidationIssue("UNSUPPORTED_DIGITAL_ASSETS_INCOME", "line_8v", message="Digital assets income is not supported in V1."))

    # 11. 非合格遞延補償計畫或 457 計畫年金 (Line 8t)：V1 暫不支援。
    if flags.has_nonqualified_deferred_comp:
        errors.append(ValidationIssue("UNSUPPORTED_NONQUALIFIED_DEFERRED_COMP", "line_8t", message="Nonqualified deferred compensation income is not supported in V1."))

    # 12. 服刑期間工資 (Line 8u)：V1 暫不支援。
    if flags.has_incarcerated_wages:
        errors.append(ValidationIssue("UNSUPPORTED_INCARCERATED_WAGES", "line_8u", message="Wages earned while incarcerated is not supported in V1."))

    # 13. ABLE 帳戶應稅分配 (Line 8q)：V1 暫不支援。
    if flags.has_able_account_distribution:
        errors.append(ValidationIssue("UNSUPPORTED_ABLE_ACCOUNT_DISTRIBUTION", "line_8q", message="Taxable ABLE account distribution is not supported in V1."))

    # 14. Medicaid waiver payments 調整 (Line 8s)：V1 暫不支援。
    if flags.has_medicaid_waiver_adjustment:
        errors.append(ValidationIssue("UNSUPPORTED_MEDICAID_WAIVER_ADJUSTMENT", "line_8s", message="Medicaid waiver payments adjustment is not supported in V1."))

    # 15. Section 951(a)／951A(a) inclusion (Line 8n／8o)：V1 暫不支援。
    if flags.has_section_951_inclusion:
        errors.append(ValidationIssue("UNSUPPORTED_SECTION_951_INCLUSION", "line_8n", message="Section 951(a)/951A(a) inclusion is not supported in V1."))

    # 16. Section 461(l) 超額營業虧損調整 (Line 8p)：V1 暫不支援。
    if flags.has_excess_business_loss_adjustment:
        errors.append(ValidationIssue("UNSUPPORTED_EXCESS_BUSINESS_LOSS_ADJUSTMENT", "line_8p", message="Section 461(l) excess business loss adjustment is not supported in V1."))

    # 17. Schedule K-1 (Form 1041) Section 67(e) 超額扣除 (Line 24k)：V1 暫不支援。
    if flags.has_k1_section_67e_deduction:
        errors.append(ValidationIssue("UNSUPPORTED_K1_SECTION_67E_DEDUCTION", "line_24k", message="Schedule K-1 Section 67(e) excess deduction is not supported in V1."))

    # 18. 交叉驗證：Line 4／Line 6 出現非零金額，但對應的特殊案件旗標卻未標示為 true。
    # Line 4／Line 6 本質上屬於「需另行計算之附屬表單」範疇（見上方 #1、#2），任何非零金額
    # 都代表資料來源涉及 Form 4797/4684 或 Schedule F，理論上一定會同時觸發對應旗標；
    # 若金額非零但旗標為 False，代表 LLM 抽取時可能遺漏設定旗標，屬於資料不一致，須阻斷避免
    # 該筆金額在未經人工複核的情況下被靜默計入 Line 10。
    ZERO = Decimal("0.00")
    if inputs.line_4_other_gains_or_losses != ZERO and not flags.has_form_4797_or_4684:
        errors.append(ValidationIssue("UNFLAGGED_FORM_4797_4684_AMOUNT", "line_4_other_gains_or_losses", message="Line 4 has a non-zero amount but has_form_4797_or_4684 was not set; flag and amount must be consistent."))
    if inputs.line_6_farm_income != ZERO and not flags.has_schedule_f_income:
        errors.append(ValidationIssue("UNFLAGGED_SCHEDULE_F_AMOUNT", "line_6_farm_income", message="Line 6 has a non-zero amount but has_schedule_f_income was not set; flag and amount must be consistent."))


def validate_amounts(inputs: Schedule1InputsV1, errors: List[ValidationIssue]):
    """
    驗證所有金額欄位是否為非負數，並偵測 line_code 是否為官方已知代碼、是否重複，
    以及是否落入 V1 不支援之單筆 line_code 範圍。
    """
    ZERO = Decimal("0.00")

    # 注意：line_4_other_gains_or_losses（Line 4 "Other gains or (losses)"）與
    # line_6_farm_income（Line 6 "Farm income or (loss)"）在官方表單上允許為負數（虧損），
    # 因此刻意不對這兩個欄位做負數檢查，避免誤擋合法的虧損金額。

    if inputs.form_1099k_error_or_personal_loss_amount < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "form_1099k_error_or_personal_loss_amount", message="Form 1099-K error/personal-loss amount cannot be negative."))
    if inputs.line_7_repaid_overpayment_amount is not None and inputs.line_7_repaid_overpayment_amount < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "line_7_repaid_overpayment_amount", message="Repaid unemployment overpayment amount cannot be negative."))

    if inputs.line_1_state_local_tax_refund < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "line_1_state_local_tax_refund", message="State/local tax refund cannot be negative."))
    if inputs.line_2a_alimony_received < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "line_2a_alimony_received", message="Alimony received cannot be negative."))
    if inputs.line_7_unemployment_compensation < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "line_7_unemployment_compensation", message="Unemployment compensation cannot be negative."))
    # Line 19a／20／21 的金額改由 adjustment_items（line_code = "19a"/"20"/"21"）表達，
    # 負數檢查已涵蓋在下方 adjustment_items 迴圈的通用 "amount < ZERO" 檢查中。

    seen_line8_codes = set()
    for item in inputs.other_income_items:
        if item.line_code not in ALL_KNOWN_LINE_8_CODES:
            errors.append(ValidationIssue("UNKNOWN_LINE_CODE", "line_code", item.item_id, message=f"Unknown Schedule 1 Part I line code: {item.line_code}."))
            continue
        if item.line_code != "8z" and item.line_code in seen_line8_codes:
            errors.append(ValidationIssue("DUPLICATE_LINE_CODE", "line_code", item.item_id, message=f"Duplicate Schedule 1 Part I line code: {item.line_code}."))
        seen_line8_codes.add(item.line_code)

        if item.amount < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "amount", item.item_id, message="Other income amount cannot be negative."))
        if item.line_code not in SUPPORTED_LINE_8_CODES:
            errors.append(ValidationIssue("UNSUPPORTED_LINE_8_ITEM", "line_code", item.item_id, message=f"Schedule 1 Part I line {item.line_code} is not supported in V1."))

    seen_part_ii_codes = set()
    for item in inputs.adjustment_items:
        is_known = item.line_code in ALL_KNOWN_PART_II_LINES or item.line_code in ALL_KNOWN_LINE_24_CODES
        if not is_known:
            errors.append(ValidationIssue("UNKNOWN_LINE_CODE", "line_code", item.item_id, message=f"Unknown Schedule 1 Part II line code: {item.line_code}."))
            continue
        if item.line_code != "24z" and item.line_code in seen_part_ii_codes:
            errors.append(ValidationIssue("DUPLICATE_LINE_CODE", "line_code", item.item_id, message=f"Duplicate Schedule 1 Part II line code: {item.line_code}."))
        seen_part_ii_codes.add(item.line_code)

        if item.amount < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "amount", item.item_id, message="Adjustment amount cannot be negative."))
        if item.line_code in ALL_KNOWN_PART_II_LINES and item.line_code not in SUPPORTED_PART_II_LINES:
            errors.append(ValidationIssue("UNSUPPORTED_PART_II_ITEM", "line_code", item.item_id, message=f"Schedule 1 Part II line {item.line_code} is not supported in V1."))
        if item.line_code in ALL_KNOWN_LINE_24_CODES and item.line_code not in SUPPORTED_LINE_24_CODES:
            errors.append(ValidationIssue("UNSUPPORTED_LINE_24_ITEM", "line_code", item.item_id, message=f"Schedule 1 Part II line {item.line_code} is not supported in V1."))
