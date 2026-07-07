from typing import List, Set
from decimal import Decimal
from processors.models.schedule_a import (
    ScheduleAInputsV1,
    ValidationIssue,
    SpecialCaseFlagsV1,
)

def validate_identity(inputs: ScheduleAInputsV1, errors: List[ValidationIssue]):
    if not inputs.taxpayer_name.strip():
        errors.append(ValidationIssue("MISSING_TAXPAYER_NAME", "taxpayer_name", message="Taxpayer name is missing."))
    if not inputs.taxpayer_ssn.strip():
        errors.append(ValidationIssue("MISSING_TAXPAYER_SSN", "taxpayer_ssn", message="Taxpayer SSN is missing."))

def validate_tax_year(tax_year: int, allowed: Set[int], errors: List[ValidationIssue]):
    if tax_year not in allowed:
        errors.append(ValidationIssue("UNSUPPORTED_TAX_YEAR", "tax_year", message=f"Tax year {tax_year} is not supported."))

def validate_nonnegative_amounts(inputs: ScheduleAInputsV1, errors: List[ValidationIssue]):
    ZERO = Decimal("0.00")
    if inputs.adjusted_gross_income < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "adjusted_gross_income", message="Adjusted Gross Income cannot be negative."))
        
    for item in inputs.medical_items:
        if item.taxpayer_paid_amount < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "taxpayer_paid_amount", item.item_id, item.source_document_id, "Taxpayer paid amount cannot be negative."))
        if item.reimbursement_amount < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "reimbursement_amount", item.item_id, item.source_document_id, "Reimbursement amount cannot be negative."))
        if item.tax_free_medical_account_payment < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "tax_free_medical_account_payment", item.item_id, item.source_document_id, "Tax free medical account payment cannot be negative."))
            
    for item in inputs.tax_items:
        if item.amount_paid < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "amount_paid", item.item_id, item.source_document_id, "Amount paid cannot be negative."))
        if item.separately_stated_nondeductible_charge < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "separately_stated_nondeductible_charge", item.item_id, item.source_document_id, "Separately stated nondeductible charge cannot be negative."))
            
    for item in inputs.mortgage_interest_items:
        if item.form_1098_box_1_mortgage_interest < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "form_1098_box_1_mortgage_interest", item.item_id, item.source_document_id, "Mortgage interest cannot be negative."))
        if item.deductible_points_reported_on_1098 < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "deductible_points_reported_on_1098", item.item_id, item.source_document_id, "Mortgage points cannot be negative."))
            
    for item in inputs.cash_charity_items:
        if item.gross_contribution_amount < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "gross_contribution_amount", item.item_id, item.source_document_id, "Gross contribution amount cannot be negative."))
        if item.goods_or_services_value < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "goods_or_services_value", item.item_id, item.source_document_id, "Goods or services value cannot be negative."))

def detect_unsupported_cases(flags: SpecialCaseFlagsV1, errors: List[ValidationIssue]):
    mapping = {
        "has_marketplace_medical_premium": ("UNSUPPORTED_MARKETPLACE_MEDICAL_PREMIUM", "Marketplace/Form 1095-A/Form 8962 premium is not supported in V1."),
        "has_ltc_premium": ("UNSUPPORTED_LTC_PREMIUM", "LTC insurance premium is not supported in V1."),
        "has_self_employed_health_insurance_overlap": ("UNSUPPORTED_SELF_EMPLOYED_HEALTH_INSURANCE", "Self-employed health insurance deduction coordination is not supported in V1."),
        "has_prior_year_medical_recovery": ("UNSUPPORTED_PRIOR_YEAR_MEDICAL_RECOVERY", "Prior year medical reimbursement/tax benefit rule is not supported in V1."),
        "sales_tax_amount_requires_calculation": ("SALES_TAX_AMOUNT_NOT_RESOLVED", "General sales tax amount requires calculation/tables which is not supported in V1."),
        "has_tax_refund_or_rebate_adjustment": ("UNSUPPORTED_TAX_REFUND_ADJUSTMENT", "Tax refund or rebate adjustment is not supported in V1."),
        "has_other_tax_line_6": ("UNSUPPORTED_OTHER_TAX_LINE_6", "Schedule A Line 6 other taxes are not supported in V1."),
        "has_multiple_mortgages": ("UNSUPPORTED_MULTIPLE_MORTGAGES", "Multiple mortgages or multiple properties are not supported in V1."),
        "mortgage_proceeds_not_all_qualified": ("UNSUPPORTED_MORTGAGE_PROCEEDS_ALLOCATION", "Mortgage proceeds not fully used for buy/build/improve is not supported in V1."),
        "mortgage_limitation_required": ("UNSUPPORTED_MORTGAGE_LIMITATION", "Mortgage principal limit or FMV limit calculation is not supported in V1."),
        "has_shared_mortgage": ("UNSUPPORTED_SHARED_MORTGAGE", "Shared mortgage interest is not supported in V1."),
        "has_non_1098_mortgage_interest": ("UNSUPPORTED_NON_1098_MORTGAGE_INTEREST", "Mortgage interest not reported on Form 1098 is not supported in V1."),
        "has_non_1098_points": ("UNSUPPORTED_NON_1098_POINTS", "Points not reported on Form 1098 is not supported in V1."),
        "has_seller_financed_mortgage": ("UNSUPPORTED_SELLER_FINANCED_MORTGAGE", "Seller-financed mortgage is not supported in V1."),
        "has_form_8396_credit": ("UNSUPPORTED_FORM_8396", "Form 8396 mortgage interest credit is not supported in V1."),
        "has_investment_interest": ("UNSUPPORTED_INVESTMENT_INTEREST", "Investment interest/Form 4952 is not supported in V1."),
        "has_noncash_charity": ("UNSUPPORTED_NONCASH_CHARITY", "Noncash charity/Form 8283 is not supported in V1."),
        "has_charity_carryover": ("UNSUPPORTED_CHARITY_CARRYOVER", "Charitable contribution carryover is not supported in V1."),
        "has_charitable_agi_limitation": ("UNSUPPORTED_CHARITABLE_AGI_LIMITATION", "Charitable AGI limitation calculation is not supported in V1."),
        "has_casualty_or_theft_loss": ("UNSUPPORTED_FORM_4684", "Casualty or theft loss/Form 4684 is not supported in V1."),
        "has_net_qualified_disaster_loss": ("UNSUPPORTED_NET_QUALIFIED_DISASTER_LOSS", "Net qualified disaster loss is not supported in V1."),
        "has_line_16_item": ("UNSUPPORTED_LINE_16_ITEM", "Schedule A Line 16 other itemized deductions are not supported in V1."),
        "has_unresolved_mfs_joint_expense_allocation": ("UNSUPPORTED_MFS_JOINT_EXPENSE_ALLOCATION", "MFS joint expense allocation is not supported in V1.")
    }
    for attr, (code, msg) in mapping.items():
        if getattr(flags, attr, False):
            errors.append(ValidationIssue(code, field=attr, message=msg))

def validate_paid_year(item, errors: List[ValidationIssue]):
    if item.paid_in_tax_year is None:
        errors.append(ValidationIssue(
            "UNKNOWN_PAID_IN_TAX_YEAR",
            field="paid_in_tax_year",
            item_id=item.item_id,
            source_document_id=item.source_document_id,
            message="Payment year is unknown."
        ))
