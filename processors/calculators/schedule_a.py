# =====================================================================
# REVIEW 重點 1: 單一職責原則 (Single Responsibility Principle - SRP)
# =====================================================================
# 【為什麼核心計算要獨立於 I/O 或 LLM 之外？】
# 1. 職責分離：在一個健全的微服務或模組化系統中，業務邏輯的計算（計算 AGI 7.5% 門檻、比較標準扣除額與列舉扣除額）
#    不應該與「資料是怎麼來的（例如 LLM 提取、DB 讀取）」綁定。
# 2. 提高可測試性（Testability）：當計算邏輯被獨立為一個 pure function (calculate_schedule_a_v1) 時，
#    我們在單元測試 (Unit Test) 中不需要 Mock 任何 API 或資料庫，只需傳入 Inputs 物件即可。
# =====================================================================

import re
from typing import List, Dict, Any
from decimal import Decimal
from processors.models.schedule_a import (
    ScheduleAInputsV1,
    ScheduleAResultV1,
    ValidationIssue,
    MedicalExpenseItemV1,
    TaxPaymentItemV1,
    MortgageInterestItemV1,
    CashCharityItemV1,
    SpecialCaseFlagsV1,
    load_tax_rates,
)
from processors.validators.schedule_a import (
    validate_identity,
    validate_tax_year,
    validate_nonnegative_amounts,
    detect_unsupported_cases,
    validate_paid_year,
)

def sum_decimal(iterable):
    """將可迭代項目加總為 Decimal 類型的金額。"""
    s = Decimal("0.00")
    for x in iterable:
        if x is not None:
            s += Decimal(str(x))
    return s

def is_over_65(dob_str: str, tax_year: int) -> bool:
    if not dob_str or not isinstance(dob_str, str):
        return False
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", dob_str.strip())
    if not m:
        return False
    by, bm, bd = int(m.group(1)), int(m.group(2)), int(m.group(3))
    cutoff_year = tax_year - 64
    if by < cutoff_year:
        return True
    if by == cutoff_year and bm == 1 and bd == 1:
        return True
    return False

def calculate_additional_standard_deduction(inputs: ScheduleAInputsV1) -> Decimal:
    ZERO = Decimal("0.00")
    try:
        rates = load_tax_rates(inputs.tax_year)
        std_cfg = rates.get("standard_deduction", {})
    except Exception:
        return ZERO
        
    single_hoh_rate = Decimal(str(std_cfg.get("additional_deduction_single_hoh", 1950.0)))
    joint_mfs_qss_rate = Decimal(str(std_cfg.get("additional_deduction_joint_mfs_qss", 1550.0)))
    
    status = str(inputs.filing_status or "SINGLE").upper()
    is_joint_or_mfs = status in ("MFJ", "MFS", "QSS")
    rate = joint_mfs_qss_rate if is_joint_or_mfs else single_hoh_rate
    
    conditions_count = 0
    if is_over_65(inputs.taxpayer_date_of_birth, inputs.tax_year):
        conditions_count += 1
    if inputs.taxpayer_blind:
        conditions_count += 1
        
    if is_joint_or_mfs:
        if is_over_65(inputs.spouse_date_of_birth, inputs.tax_year):
            conditions_count += 1
        if inputs.spouse_blind:
            conditions_count += 1
            
    return Decimal(conditions_count) * rate

def calculate_salt_limit_v1(tax_year: int, filing_status: str, agi: Decimal, line_5d: Decimal, has_foreign_adjustment: bool, errors: List[ValidationIssue]) -> Decimal:
    if tax_year == 2024:
        cap = Decimal("5000.00") if filing_status == "MFS" else Decimal("10000.00")
        return min(line_5d, cap)
    elif tax_year == 2025:
        floor_2025 = Decimal("5000.00") if filing_status == "MFS" else Decimal("10000.00")
        base_cap_2025 = Decimal("20000.00") if filing_status == "MFS" else Decimal("40000.00")
        
        if line_5d <= floor_2025:
            return line_5d
            
        agi_limit = Decimal("250000.00") if filing_status == "MFS" else Decimal("500000.00")
        if agi <= agi_limit and not has_foreign_adjustment:
            return min(line_5d, base_cap_2025)
        else:
            errors.append(ValidationIssue("UNSUPPORTED_2025_SALT_WORKSHEET", field="line_5e_salt_deduction", message="2025 high-income or foreign-income SALT worksheet is not supported in V1."))
            return None
    else:
        errors.append(ValidationIssue("UNSUPPORTED_TAX_YEAR", field="tax_year", message=f"Tax year {tax_year} is not supported."))
        return None

def calculate_simple_form_1098(mortgage_interest_items: List[MortgageInterestItemV1], errors: List[ValidationIssue]) -> Decimal:
    ZERO = Decimal("0.00")
    if not mortgage_interest_items:
        return ZERO
    if len(mortgage_interest_items) > 1:
        errors.append(ValidationIssue("UNSUPPORTED_MULTIPLE_MORTGAGES", field="mortgage_interest_items", message="Multiple mortgages not supported in V1."))
        return ZERO
        
    item = mortgage_interest_items[0]
    validate_paid_year(item, errors)
    
    if item.simple_mortgage_status == "UNKNOWN":
        errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="simple_mortgage_status", item_id=item.item_id, source_document_id=item.source_document_id, message="Unknown mortgage status."))
        return ZERO
    elif item.simple_mortgage_status == "LIMITATION_OR_WORKSHEET_REQUIRED":
        errors.append(ValidationIssue("UNSUPPORTED_MORTGAGE_LIMITATION", field="simple_mortgage_status", item_id=item.item_id, source_document_id=item.source_document_id, message="Mortgage limitation or worksheet required is not supported in V1."))
        return ZERO
        
    if item.paid_in_tax_year is True:
        return item.form_1098_box_1_mortgage_interest + item.deductible_points_reported_on_1098
    return ZERO

def calculate_cash_charity(cash_charity_items: List[CashCharityItemV1], errors: List[ValidationIssue], warnings: List[ValidationIssue], tax_year: int = 2024) -> Decimal:
    total = Decimal("0.00")
    ZERO = Decimal("0.00")
    for item in cash_charity_items:
        validate_paid_year(item, errors)
        
        if item.qualified_organization_status == "UNKNOWN":
            errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="qualified_organization_status", item_id=item.item_id, source_document_id=item.source_document_id, message="Unknown charity organization qualification status."))
            continue
        elif item.qualified_organization_status == "NOT_QUALIFIED":
            warnings.append(ValidationIssue("CHARITY_ORGANIZATION_NOT_QUALIFIED", field="qualified_organization_status", item_id=item.item_id, source_document_id=item.source_document_id, message="Charity organization is not qualified; excluded."))
            continue
            
        has_date_error = False
        if not item.contribution_date:
            errors.append(ValidationIssue(
                "CHARITY_CONTRIBUTION_DATE_MISSING",
                field="contribution_date",
                item_id=item.item_id,
                source_document_id=item.source_document_id,
                message=f"The contribution record identifies tax year {tax_year} but does not provide the actual contribution date."
            ))
            has_date_error = True
            
        has_ack_error = False
        net_contrib = item.gross_contribution_amount - item.goods_or_services_value
        if net_contrib >= Decimal("250.00"):
            if item.contemporaneous_acknowledgment_received is None or item.contemporaneous_acknowledgment_received is False:
                errors.append(ValidationIssue(
                    "MISSING_250_ACKNOWLEDGMENT",
                    field="contemporaneous_acknowledgment_received",
                    item_id=item.item_id,
                    source_document_id=item.source_document_id,
                    message=f"The ${int(item.gross_contribution_amount):,} contribution record does not state whether goods or services were provided in exchange."
                ))
                has_ack_error = True

        if has_date_error or has_ack_error:
            continue
            
        if item.bank_or_written_record_available is None:
            errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="bank_or_written_record_available", item_id=item.item_id, source_document_id=item.source_document_id, message="Bank or written record availability is unknown/null."))
            continue
            
        if item.goods_or_services_value > item.gross_contribution_amount:
            errors.append(ValidationIssue("ADJUSTMENT_EXCEEDS_GROSS_AMOUNT", field="goods_or_services_value", item_id=item.item_id, source_document_id=item.source_document_id, message="Goods/services value exceeds gross contribution amount."))
            continue
            
        if item.paid_in_tax_year is True and item.qualified_organization_status == "VERIFIED" and item.bank_or_written_record_available is True:
            total += net_contrib
            
    return total

def any_unsupported_case(flags: SpecialCaseFlagsV1) -> bool:
    unsupported_attributes = [
        "has_marketplace_medical_premium",
        "has_ltc_premium",
        "has_self_employed_health_insurance_overlap",
        "has_prior_year_medical_recovery",
        "sales_tax_amount_requires_calculation",
        "has_tax_refund_or_rebate_adjustment",
        "has_other_tax_line_6",
        "has_multiple_mortgages",
        "mortgage_proceeds_not_all_qualified",
        "mortgage_limitation_required",
        "has_shared_mortgage",
        "has_non_1098_mortgage_interest",
        "has_non_1098_points",
        "has_seller_financed_mortgage",
        "has_form_8396_credit",
        "has_investment_interest",
        "has_noncash_charity",
        "has_charity_carryover",
        "has_charitable_agi_limitation",
        "has_casualty_or_theft_loss",
        "has_net_qualified_disaster_loss",
        "has_line_16_item",
        "has_unresolved_mfs_joint_expense_allocation"
    ]
    for attr in unsupported_attributes:
        if getattr(flags, attr, False):
            return True
    return False

class TaxPools:
    def __init__(self):
        self.income_tax = []
        self.sales_tax = []
        self.real_estate_tax = []
        self.personal_property_tax = []

def classify_tax_items(tax_items: List[TaxPaymentItemV1], errors: List[ValidationIssue], warnings: List[ValidationIssue]) -> TaxPools:
    pools = TaxPools()
    for item in tax_items:
        validate_paid_year(item, errors)
        
        if item.tax_category == "UNKNOWN":
            errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="tax_category", item_id=item.item_id, source_document_id=item.source_document_id, message="Unknown tax category."))
            continue
            
        if item.tax_category == "FEDERAL_OR_NONDEDUCTIBLE_TAX":
            warnings.append(ValidationIssue("FEDERAL_OR_NONDEDUCTIBLE_TAX_EXCLUDED", field="tax_category", item_id=item.item_id, source_document_id=item.source_document_id, message="Federal or nondeductible tax excluded."))
            continue
            
        if item.tax_category == "BUSINESS_OR_RENTAL_TAX":
            warnings.append(ValidationIssue("BUSINESS_OR_RENTAL_TAX_EXCLUDED", field="tax_category", item_id=item.item_id, source_document_id=item.source_document_id, message="Business or rental tax excluded from Schedule A."))
            continue
            
        if item.separately_stated_nondeductible_charge > item.amount_paid:
            errors.append(ValidationIssue("ADJUSTMENT_EXCEEDS_GROSS_AMOUNT", field="separately_stated_nondeductible_charge", item_id=item.item_id, source_document_id=item.source_document_id, message="Nondeductible charge exceeds amount paid."))
            continue
            
        eligible_amt = item.amount_paid - item.separately_stated_nondeductible_charge
        
        if item.tax_category == "STATE_LOCAL_INCOME_TAX":
            if item.paid_in_tax_year is True:
                pools.income_tax.append(eligible_amt)
        elif item.tax_category == "GENERAL_SALES_TAX":
            if item.paid_in_tax_year is True:
                pools.sales_tax.append(eligible_amt)
        elif item.tax_category == "PERSONAL_REAL_ESTATE_TAX":
            if item.personal_use_confirmed is None:
                errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="personal_use_confirmed", item_id=item.item_id, source_document_id=item.source_document_id, message="Real estate tax personal use confirmation is missing or unknown."))
                continue
            if item.personal_use_confirmed is False:
                warnings.append(ValidationIssue("PERSONAL_USE_NOT_CONFIRMED", field="personal_use_confirmed", item_id=item.item_id, source_document_id=item.source_document_id, message="Real estate is not for personal use; excluded."))
                continue
            if item.actual_paid_to_taxing_authority_confirmed is None or item.actual_paid_to_taxing_authority_confirmed is False:
                # Excluded from deductible pool
                continue
            if item.personal_use_confirmed is True and item.actual_paid_to_taxing_authority_confirmed is True:
                if item.paid_in_tax_year is True:
                    pools.real_estate_tax.append(eligible_amt)
        elif item.tax_category == "PERSONAL_PROPERTY_TAX":
            if item.personal_use_confirmed is None or item.value_based_and_annual_confirmed is None:
                errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="property_confirmations", item_id=item.item_id, source_document_id=item.source_document_id, message="Personal property tax confirmations are missing or unknown."))
                continue
            if item.personal_use_confirmed is True and item.value_based_and_annual_confirmed is True:
                if item.paid_in_tax_year is True:
                    pools.personal_property_tax.append(eligible_amt)
    return pools

def calculate_schedule_a_v1(inputs: ScheduleAInputsV1) -> ScheduleAResultV1:
    errors = []
    warnings = []
    ZERO = Decimal("0.00")
    MEDICAL_RATE = Decimal("0.075")

    # 1. 校驗基本與阻斷規則
    validate_identity(inputs, errors)
    validate_tax_year(inputs.tax_year, allowed={2024, 2025}, errors=errors)
    validate_nonnegative_amounts(inputs, errors)
    detect_unsupported_cases(inputs.special_case_flags, errors)

    # 2. Medical Expense (Lines 1-4)
    medical_total = ZERO
    for item in inputs.medical_items:
        validate_paid_year(item, errors)

        if item.medical_qualification_status == "UNKNOWN":
            errors.append(ValidationIssue("UNKNOWN_MEDICAL_QUALIFICATION", field="medical_qualification_status", item_id=item.item_id, source_document_id=item.source_document_id, message="Unknown medical qualification status."))
            continue

        if item.eligible_person_status == "UNKNOWN":
            errors.append(ValidationIssue("UNKNOWN_MEDICAL_PERSON_ELIGIBILITY", field="eligible_person_status", item_id=item.item_id, source_document_id=item.source_document_id, message="Unknown medical eligible person status."))
            continue

        if (
            item.medical_qualification_status == "NOT_DEDUCTIBLE"
            or item.eligible_person_status == "NOT_ELIGIBLE"
            or item.paid_in_tax_year is False
        ):
            warnings.append(ValidationIssue("MEDICAL_ITEM_EXCLUDED", field="medical_items", item_id=item.item_id, source_document_id=item.source_document_id, message=f"Medical item {item.item_id} excluded."))
            continue

        adjustments = item.reimbursement_amount + item.tax_free_medical_account_payment

        if adjustments > item.taxpayer_paid_amount:
            errors.append(ValidationIssue("ADJUSTMENT_EXCEEDS_GROSS_AMOUNT", field="reimbursement_amount", item_id=item.item_id, source_document_id=item.source_document_id, message="Medical reimbursement and HSA/FSA offset exceeds gross taxpayer paid amount."))
            continue

        medical_total += item.taxpayer_paid_amount - adjustments

    line_1 = medical_total
    line_2 = inputs.adjusted_gross_income
    line_3 = (line_2 * MEDICAL_RATE).quantize(Decimal("0.01"))
    line_4 = max(ZERO, line_1 - line_3)

    # 3. Taxes Paid (Lines 5-7)
    tax_pools = classify_tax_items(inputs.tax_items, errors=errors, warnings=warnings)

    if inputs.line_5a_election == "INCOME_TAX":
        line_5a = sum_decimal(tax_pools.income_tax)
        sales_tax_checkbox = False
    elif inputs.line_5a_election == "GENERAL_SALES_TAX":
        line_5a = sum_decimal(tax_pools.sales_tax)
        sales_tax_checkbox = True
    elif inputs.line_5a_election is None:
        line_5a = ZERO
        sales_tax_checkbox = False
        if tax_pools.income_tax or tax_pools.sales_tax:
            errors.append(ValidationIssue("TAX_ELECTION_MISSING", field="line_5a_election", message="Tax election (income tax vs sales tax) is missing."))
    else:
        line_5a = ZERO
        sales_tax_checkbox = False
        errors.append(ValidationIssue("TAX_ELECTION_MISSING", field="line_5a_election", message="Invalid tax election value."))

    has_unconfirmed_real_estate_tax = False
    for item in inputs.tax_items:
        if item.tax_category == "PERSONAL_REAL_ESTATE_TAX" and item.actual_paid_to_taxing_authority_confirmed is not True:
            has_unconfirmed_real_estate_tax = True
            errors.append(ValidationIssue(
                "REAL_ESTATE_TAX_PAYMENT_NOT_CONFIRMED",
                field="line_5b_real_estate_taxes",
                item_id=item.item_id,
                source_document_id=item.source_document_id,
                message=f"The source reports an escrow amount but does not confirm the amount actually paid to the taxing authority during {inputs.tax_year}."
            ))

    line_5b_val = sum_decimal(tax_pools.real_estate_tax)
    line_5b = None if has_unconfirmed_real_estate_tax else line_5b_val
    line_5c = sum_decimal(tax_pools.personal_property_tax)
    line_5d = line_5a + line_5b_val + line_5c

    line_5e = calculate_salt_limit_v1(
        tax_year=inputs.tax_year,
        filing_status=inputs.filing_status,
        agi=inputs.adjusted_gross_income,
        line_5d=line_5d,
        has_foreign_adjustment=inputs.special_case_flags.has_form_2555_or_4563_or_puerto_rico_exclusion,
        errors=errors
    )

    line_6 = ZERO
    line_7 = None if line_5e is None else line_5e + line_6

    # 4. Interest Paid (Lines 8-10)
    line_8a = calculate_simple_form_1098(inputs.mortgage_interest_items, errors=errors)
    line_8b = ZERO
    line_8c = ZERO
    line_8e = line_8a + line_8b + line_8c
    line_9 = ZERO
    line_10 = line_8e + line_9

    # 5. Charitable Contributions (Lines 11-14)
    line_11 = calculate_cash_charity(inputs.cash_charity_items, errors=errors, warnings=warnings, tax_year=inputs.tax_year)
    line_12 = ZERO
    line_13 = ZERO
    line_14 = line_11 + line_12 + line_13

    # 6. Casualty and Theft Losses & Other Itemized Deductions (Lines 15-16)
    line_15 = ZERO
    line_16 = ZERO

    # 7. Total Itemized Deductions (Line 17)
    if line_7 is None:
        line_17 = None
    else:
        line_17 = line_4 + line_7 + line_10 + line_14 + line_15 + line_16

    is_v1_supported = not any_unsupported_case(inputs.special_case_flags)
    can_file = is_v1_supported and len(errors) == 0 and line_17 is not None

    standard_amount = inputs.standard_deduction_reference.standard_deduction_amount
    if standard_amount is not None:
        standard_amount = Decimal(str(standard_amount)) + calculate_additional_standard_deduction(inputs)
        
    if standard_amount is None or line_17 is None:
        is_itemizing = None
        if standard_amount is None:
            errors.append(ValidationIssue("STANDARD_DEDUCTION_REFERENCE_MISSING", field="standard_deduction_amount", message="Standard deduction amount is missing."))
    else:
        is_itemizing = (
            inputs.standard_deduction_reference.must_itemize_due_to_mfs_spouse is True
            or inputs.standard_deduction_reference.elect_itemize_even_if_less is True
            or line_17 > standard_amount
        )

    should_attach = can_file and (is_itemizing is True)

    line_18_surface = None
    if inputs.tax_year == 2025:
        line_18_surface = inputs.standard_deduction_reference.elect_itemize_even_if_less is True

    # Mask SSN
    raw_ssn = str(inputs.taxpayer_ssn or "")
    if len(raw_ssn) >= 4:
        ssn_masked = f"***-**-{raw_ssn[-4:]}"
    else:
        ssn_masked = "***-**-XXXX"

    return ScheduleAResultV1(
        taxpayer_name=inputs.taxpayer_name,
        taxpayer_ssn_masked=ssn_masked,
        tax_year=inputs.tax_year,
        filing_status=inputs.filing_status,
        line_1_medical_and_dental_expenses=line_1,
        line_2_agi=line_2,
        line_3_medical_threshold=line_3,
        line_4_deductible_medical_expenses=line_4,
        line_5a_amount=line_5a,
        line_5a_sales_tax_checkbox=sales_tax_checkbox,
        line_5b_real_estate_taxes=line_5b,
        line_5c_personal_property_taxes=line_5c,
        line_5d_salt_before_limit=line_5d,
        line_5e_salt_deduction=line_5e,
        line_6_other_taxes=line_6,
        line_7_total_taxes=line_7,
        line_8_qualifying_proceeds_checkbox=False,
        line_8a_home_mortgage_interest=line_8a,
        line_8b_non_1098_interest=line_8b,
        line_8c_non_1098_points=line_8c,
        line_8e_total_mortgage_interest=line_8e,
        line_9_investment_interest=line_9,
        line_10_total_interest_paid=line_10,
        line_11_cash_contributions=line_11,
        line_12_noncash_contributions=line_12,
        line_13_charity_carryover=line_13,
        line_14_total_charity=line_14,
        line_15_casualty_theft_loss=line_15,
        line_16_other_itemized_deductions=line_16,
        line_17_total_itemized_deductions=line_17,
        line_18_elect_itemize_surface=line_18_surface,
        standard_deduction_amount=standard_amount,
        is_itemizing=is_itemizing,
        is_v1_supported=is_v1_supported,
        should_attach_schedule_a=should_attach,
        can_file=can_file,
        blocking_errors=errors,
        review_warnings=warnings
    )
