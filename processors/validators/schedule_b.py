from typing import List, Set
from decimal import Decimal
from processors.models.schedule_a import ValidationIssue # reuse ValidationIssue since it is a general class
from processors.models.schedule_b import ScheduleBInputsV1, SpecialCaseFlagsBV1

def validate_identity(inputs: ScheduleBInputsV1, errors: List[ValidationIssue]):
    """
    驗證納稅人基本身分資訊。
    - 確保納稅人姓名不為空。
    - 確保納稅人社會安全號碼 (SSN) 不為空。
    """
    if not inputs.taxpayer_name.strip():
        errors.append(ValidationIssue("MISSING_TAXPAYER_NAME", "taxpayer_name", message="Taxpayer name is missing."))
    if not inputs.taxpayer_ssn.strip():
        errors.append(ValidationIssue("MISSING_TAXPAYER_SSN", "taxpayer_ssn", message="Taxpayer SSN is missing."))

def validate_tax_year(tax_year: int, allowed: Set[int], errors: List[ValidationIssue]):
    """
    驗證申報年度是否在支援範圍內。
    - 目前 V1 版本僅支援 2024 2025 年。
    """
    if tax_year not in allowed:
        errors.append(ValidationIssue("UNSUPPORTED_TAX_YEAR", "tax_year", message=f"Tax year {tax_year} is not supported."))

def detect_unsupported_cases(inputs: ScheduleBInputsV1, errors: List[ValidationIssue]):
    """
    偵測 Schedule B 是否包含 V1 版本不支援的複雜情況。
    若偵測到不支援情況，記錄 ValidationIssue
    """
    flags = inputs.special_case_flags
    
    # 1. Nominee Distribution (代名持有人分配/代收代付)：
    # 這需要將代收代付的金額從申報中扣除，並另外向實際所有人寄送 1099 表單，申報流程複雜，V1 暫不支援。
    if flags.has_nominee_distribution:
        errors.append(ValidationIssue("UNSUPPORTED_NOMINEE_DISTRIBUTION", "nominee", message="Nominee interest/dividends not supported in V1."))

    # 2. Accrued Interest (應計利息)：
    # 買賣債券時付給前手的應計利息調整，需要申報額外的利息減項，V1 暫不支援。
    if flags.has_accrued_interest:
        errors.append(ValidationIssue("UNSUPPORTED_ACCRUED_INTEREST", "accrued_interest", message="Accrued interest not supported in V1."))

    # 3. OID (原始發行折價調整)：
    # 折價發行債券的應計利息調整，計算極其複雜（需依國稅局 Pub 1212 逐期推算），V1 暫不支援。
    if flags.has_oid:
        errors.append(ValidationIssue("UNSUPPORTED_OID", "oid", message="Form 1099-OID or OID adjustment not supported in V1."))

    # 4. ABP Adjustment (債券溢價攤銷調整)：
    # 溢價購買應稅債券的攤銷扣除額，需要申報利息減項，V1 暫不支援。
    if flags.has_abp_adjustment:
        errors.append(ValidationIssue("UNSUPPORTED_ABP_ADJUSTMENT", "abp", message="Amortizable bond premium not supported in V1."))

    # 5. Seller Financed Mortgage (賣方融資房貸利息)：
    # 作為債權人收取買方利息，申報時必須在 Schedule B 填寫買方的姓名、SSN 與地址，資訊蒐集與填寫複雜，V1 暫不支援。
    if flags.has_seller_financed_mortgage:
        errors.append(ValidationIssue("UNSUPPORTED_SELLER_FINANCED_MORTGAGE", "seller_financed", message="Seller-financed mortgage interest not supported in V1."))

    # 6. Form 8814 (合併申報子女利息股利)：
    # 需要申報並計算未成年子女的未勞動所得，與子女所得稅率連動計算，V1 暫不支援。
    if flags.has_form_8814:
        errors.append(ValidationIssue("UNSUPPORTED_FORM_8814", "form_8814", message="Form 8814 is not supported in V1."))

    # 7. Tax Exempt Bond Premium (免稅債券溢價攤銷)：
    # 免稅債券的溢價攤銷，雖不影響應稅利息，但需調整債券成本且申報，V1 暫不支援。
    if flags.has_tax_exempt_bond_premium:
        errors.append(ValidationIssue("UNSUPPORTED_TAX_EXEMPT_BOND_PREMIUM", "tax_exempt_bond_premium", message="Tax-exempt bond premium not supported in V1."))

    # 8. Contingent Payment Debt (或有支付債務工具)：
    # 利息金額不固定的複雜債務工具，須採特定預估收益率法計算，V1 暫不支援。
    if flags.has_contingent_payment_debt:
        errors.append(ValidationIssue("UNSUPPORTED_CONTINGENT_PAYMENT_DEBT", "contingent_payment_debt", message="Contingent payment debt not supported in V1."))

def validate_amounts(inputs: ScheduleBInputsV1, errors: List[ValidationIssue]):
    ZERO = Decimal("0.00")
    for item in inputs.interest_items:
        if item.tax_character == "UNKNOWN":
            errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", "tax_character", item.item_id, message="Unable to determine tax character of interest item."))
        if item.payer_reported_amount < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "payer_reported_amount", item.item_id, message="Payer reported amount cannot be negative."))
            
    for item in inputs.dividend_items:
        if item.ordinary_dividends < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "ordinary_dividends", item.item_id, message="Ordinary dividends cannot be negative."))
        if item.qualified_dividends < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "qualified_dividends", item.item_id, message="Qualified dividends cannot be negative."))
        if item.exempt_interest_dividends < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "exempt_interest_dividends", item.item_id, message="Exempt interest dividends cannot be negative."))
        if item.qualified_dividends > item.ordinary_dividends:
            errors.append(ValidationIssue("QUALIFIED_DIVIDENDS_EXCEED_ORDINARY", "qualified_dividends", item.item_id, message="Qualified dividends exceed ordinary dividends."))

def validate_form_8815(inputs: ScheduleBInputsV1, line_3_exclusion: Decimal, errors: List[ValidationIssue]):
    f8815 = inputs.form_8815
    if line_3_exclusion > Decimal("0.00") and not f8815.is_completed:
        errors.append(ValidationIssue("FORM_8815_NOT_COMPLETED", "form_8815", message="Form 8815 must be completed to claim exclusions."))
    if line_3_exclusion > f8815.eligible_series_ee_i_interest_included_in_line_2:
        errors.append(ValidationIssue("FORM8815_EXCLUSION_EXCEEDS_ELIGIBLE_INTEREST", "line_14_excludable_interest", message="Line 14 exclusions exceed eligible EE/I interest included in Line 2."))

def validate_part_iii(inputs: ScheduleBInputsV1, is_part_iii_required: bool, errors: List[ValidationIssue]):
    """
    驗證 Schedule B Part III (國外帳戶與信託問卷) 的填寫完整性。
    
    主要驗證規則包括：
    1. 確保基本問卷已回答：海外金融帳戶宣告 (foreign_account_q1 / Q1) 與海外信託宣告 (foreign_trust_q8 / Q8) 不得為 None。
    2. 若符合強制填寫 Part III 的條件 (is_part_iii_required 為 True)：
       - 當海外金融帳戶 Q1 為 Yes (True) 時，必須回答是否需申報 FBAR (fbar_q2 / Q2)。
       - 當 FBAR Q2 為 Yes (True) 時，必須填寫具體的海外國家清單 (foreign_countries)。
    """
    q1 = inputs.foreign_account_q1
    q8 = inputs.foreign_trust_q8
    
    if q1 is None:
        errors.append(ValidationIssue("PART_III_ANSWER_MISSING", "foreign_account_q1", message="Foreign account screening answer missing (must be True or False)."))
    if q8 is None:
        errors.append(ValidationIssue("PART_III_ANSWER_MISSING", "foreign_trust_q8", message="Foreign trust screening answer missing (must be True or False)."))
        
    if is_part_iii_required and q1 is not None and q8 is not None:
        if q1 is True:
            q2 = inputs.fbar_q2
            if q2 is None:
                errors.append(ValidationIssue("PART_III_ANSWER_MISSING", "fbar_q2", message="FBAR requirement answer missing in Part III."))
            elif q2 is True:
                countries = inputs.foreign_countries or []
                if not countries or len(countries) == 0:
                    errors.append(ValidationIssue("FBAR_COUNTRY_MISSING", "foreign_countries", message="FBAR countries list is empty."))
