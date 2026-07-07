from typing import List, Set
from decimal import Decimal
from processors.models.schedule_a import ValidationIssue # reuse ValidationIssue since it is a general class
from processors.models.schedule_b import ScheduleBInputsV1, SpecialCaseFlagsBV1

def validate_identity(inputs: ScheduleBInputsV1, errors: List[ValidationIssue]):
    if not inputs.taxpayer_name.strip():
        errors.append(ValidationIssue("MISSING_TAXPAYER_NAME", "taxpayer_name", message="Taxpayer name is missing."))
    if not inputs.taxpayer_ssn.strip():
        errors.append(ValidationIssue("MISSING_TAXPAYER_SSN", "taxpayer_ssn", message="Taxpayer SSN is missing."))

def validate_tax_year(tax_year: int, allowed: Set[int], errors: List[ValidationIssue]):
    if tax_year not in allowed:
        errors.append(ValidationIssue("UNSUPPORTED_TAX_YEAR", "tax_year", message=f"Tax year {tax_year} is not supported."))

def detect_unsupported_cases(inputs: ScheduleBInputsV1, errors: List[ValidationIssue]):
    flags = inputs.special_case_flags
    interest_items = inputs.interest_items
    dividend_items = inputs.dividend_items
    
    # 1. Nominee Distribution
    has_nominee = flags.has_nominee_distribution or \
                  any(item.nominee_amount > Decimal("0.00") for item in interest_items) or \
                  any(item.nominee_ordinary_amount > Decimal("0.00") or 
                      item.nominee_qualified_amount > Decimal("0.00") or 
                      item.nominee_amount > Decimal("0.00") for item in dividend_items)
    if has_nominee:
        errors.append(ValidationIssue("UNSUPPORTED_NOMINEE_DISTRIBUTION", "nominee", message="Nominee interest/dividends not supported in V1."))

    # 2. Accrued Interest
    has_accrued = flags.has_accrued_interest or \
                  any(item.accrued_interest > Decimal("0.00") for item in interest_items)
    if has_accrued:
        errors.append(ValidationIssue("UNSUPPORTED_ACCRUED_INTEREST", "accrued_interest", message="Accrued interest not supported in V1."))

    # 3. OID
    has_oid = flags.has_oid or \
              any(item.oid_broker_adjustment_amount > Decimal("0.00") or 
                  item.oid_taxpayer_computed_adjustment > Decimal("0.00") or 
                  item.oid_adjustment > Decimal("0.00") for item in interest_items)
    if has_oid:
        errors.append(ValidationIssue("UNSUPPORTED_OID", "oid", message="Form 1099-OID or OID adjustment not supported in V1."))

    # 4. ABP Adjustment
    has_abp = flags.has_abp_adjustment or \
              any(item.abp_broker_adjustment_amount > Decimal("0.00") or 
                  item.abp_taxpayer_computed_adjustment > Decimal("0.00") or 
                  item.bond_premium_adjustment > Decimal("0.00") for item in interest_items)
    if has_abp:
        errors.append(ValidationIssue("UNSUPPORTED_ABP_ADJUSTMENT", "abp", message="Amortizable bond premium not supported in V1."))

    # 5. Seller Financed Mortgage
    has_seller_financed = flags.has_seller_financed_mortgage or \
                           any(item.is_seller_financed for item in interest_items)
    if has_seller_financed:
        errors.append(ValidationIssue("UNSUPPORTED_SELLER_FINANCED_MORTGAGE", "seller_financed", message="Seller-financed mortgage interest not supported in V1."))

    # 6. Form 8814
    if flags.has_form_8814:
        errors.append(ValidationIssue("UNSUPPORTED_FORM_8814", "form_8814", message="Form 8814 is not supported in V1."))

    # 7. Tax Exempt Bond Premium
    if flags.has_tax_exempt_bond_premium:
        errors.append(ValidationIssue("UNSUPPORTED_TAX_EXEMPT_BOND_PREMIUM", "tax_exempt_bond_premium", message="Tax-exempt bond premium not supported in V1."))

    # 8. Contingent Payment Debt
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
