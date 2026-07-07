from typing import List, Set
from decimal import Decimal
from processors.models.schedule_e import (
    ScheduleEPart1InputsV1,
    ValidationIssue,
    ScheduleEPart1SpecialCaseFlagsV1,
    RentalPropertyInputV1,
)

def validate_identity(inputs: ScheduleEPart1InputsV1, errors: List[ValidationIssue]):
    if not inputs.taxpayer_name.strip():
        errors.append(ValidationIssue("MISSING_TAXPAYER_NAME", "taxpayer_name", message="Taxpayer name is missing."))
    if not inputs.taxpayer_ssn.strip():
        errors.append(ValidationIssue("MISSING_TAXPAYER_SSN", "taxpayer_ssn", message="Taxpayer SSN is missing."))

def validate_tax_year(tax_year: int, allowed: Set[int], errors: List[ValidationIssue]):
    if tax_year not in allowed:
        errors.append(ValidationIssue("UNSUPPORTED_TAX_YEAR", "tax_year", message=f"Tax year {tax_year} is not supported."))

def validate_accounting_method(method: str, expected: str, errors: List[ValidationIssue]):
    if method.upper() != expected.upper():
        errors.append(ValidationIssue("UNSUPPORTED_ACCOUNTING_METHOD", "accounting_method", message=f"Accounting method {method} is not supported. V1 only supports {expected}."))

def validate_nonnegative_amounts(inputs: ScheduleEPart1InputsV1, errors: List[ValidationIssue]):
    ZERO = Decimal("0.00")
    for prop in inputs.properties:
        for item in prop.rental_income_items:
            if item.gross_amount_received < ZERO:
                errors.append(ValidationIssue("NEGATIVE_AMOUNT", "gross_amount_received", property_id=prop.property_id, item_id=item.item_id, source_document_id=item.source_document_id, message="Gross amount received cannot be negative."))
            if item.refunded_or_returned_amount < ZERO:
                errors.append(ValidationIssue("NEGATIVE_AMOUNT", "refunded_or_returned_amount", property_id=prop.property_id, item_id=item.item_id, source_document_id=item.source_document_id, message="Refunded or returned amount cannot be negative."))

        for item in prop.rental_expense_items:
            if item.gross_amount < ZERO:
                errors.append(ValidationIssue("NEGATIVE_AMOUNT", "gross_amount", property_id=prop.property_id, item_id=item.item_id, source_document_id=item.source_document_id, message="Gross expense amount cannot be negative."))
            if item.reimbursement_amount < ZERO:
                errors.append(ValidationIssue("NEGATIVE_AMOUNT", "reimbursement_amount", property_id=prop.property_id, item_id=item.item_id, source_document_id=item.source_document_id, message="Reimbursement amount cannot be negative."))
            if item.nonrental_allocated_amount < ZERO:
                errors.append(ValidationIssue("NEGATIVE_AMOUNT", "nonrental_allocated_amount", property_id=prop.property_id, item_id=item.item_id, source_document_id=item.source_document_id, message="Non-rental allocated amount cannot be negative."))

        if prop.depreciation_result and prop.depreciation_result.depreciation_amount:
            if prop.depreciation_result.depreciation_amount < ZERO:
                errors.append(ValidationIssue("NEGATIVE_AMOUNT", "depreciation_amount", property_id=prop.property_id, source_result_id=prop.depreciation_result.source_result_id, message="Depreciation amount cannot be negative."))

def detect_unsupported_cases(flags: ScheduleEPart1SpecialCaseFlagsV1, errors: List[ValidationIssue]):
    mapping = {
        "has_royalty_property": ("UNSUPPORTED_ROYALTY_PROPERTY", "Royalty property is not supported in V1."),
        "has_more_than_three_properties": ("UNSUPPORTED_MORE_THAN_THREE_PROPERTIES", "More than three rental properties are not supported in V1."),
        "has_short_term_or_vacation_rental": ("UNSUPPORTED_SHORT_TERM_OR_VACATION_RENTAL", "Vacation/short-term rentals are not supported in V1."),
        "has_personal_use_property": ("UNSUPPORTED_PERSONAL_USE_PROPERTY", "Personal use property is not supported in V1."),
        "has_rented_less_than_15_days_case": ("UNSUPPORTED_RENTED_LESS_THAN_15_DAYS", "Used-as-home and rented less than 15 days is not supported in V1."),
        "has_commercial_property": ("UNSUPPORTED_COMMERCIAL_PROPERTY", "Commercial property is not supported in V1."),
        "has_land_rental": ("UNSUPPORTED_LAND_RENTAL", "Land rental is not supported in V1."),
        "has_self_rental": ("UNSUPPORTED_SELF_RENTAL", "Self-rental is not supported in V1."),
        "has_other_property_type": ("UNSUPPORTED_OTHER_PROPERTY_TYPE", "Property type other than Single or Multi-Family is not supported in V1."),
        "has_foreign_rental_property": ("UNSUPPORTED_FOREIGN_RENTAL_PROPERTY", "Foreign rental property is not supported in V1."),
        "has_qjv": ("UNSUPPORTED_QJV", "Qualified joint ventures are not supported in V1."),
        "has_substantial_services": ("ROUTE_TO_SCHEDULE_C_SUBSTANTIAL_SERVICES", "Substantial services provided requires Schedule C."),
        "has_real_estate_dealer_inventory_rental": ("ROUTE_TO_SCHEDULE_C_REAL_ESTATE_DEALER", "Dealer inventory rental requires Schedule C."),
        "has_farm_rental": ("ROUTE_TO_FORM_4835", "Farm rental/crop share requires Form 4835."),
        "has_personal_property_only_rental": ("ROUTE_PERSONAL_PROPERTY_RENTAL", "Personal property only rental is not supported in Schedule E."),
        "has_unresolved_ownership_allocation": ("UNRESOLVED_OWNERSHIP_ALLOCATION", "Ownership share allocation is unresolved."),
        "has_unresolved_conversion_allocation": ("UNRESOLVED_CONVERSION_ALLOCATION", "Personal-to-rental conversion allocation is unresolved."),
        "has_unknown_security_deposit_character": ("UNKNOWN_SECURITY_DEPOSIT_CHARACTER", "Security deposit tax character is unknown."),
        "has_unknown_income_timing": ("UNKNOWN_RENTAL_INCOME_TIMING", "Income tax year timing is unknown."),
        "has_unresolved_repair_vs_improvement": ("UNRESOLVED_REPAIR_VS_IMPROVEMENT", "Repair or capital improvement classification is unresolved."),
        "has_unresolved_legal_fee_capitalization": ("UNRESOLVED_LEGAL_FEE_CAPITALIZATION", "Legal fee capitalization character is unresolved."),
        "has_unresolved_interest_tracing": ("UNRESOLVED_INTEREST_TRACING", "Interest tracing/allocation is unresolved."),
        "has_unresolved_points_or_prepaid_interest": ("UNRESOLVED_POINTS_OR_PREPAID_INTEREST", "Points or prepaid interest amortization is unresolved."),
        "has_unresolved_form_8990_limitation": ("UNRESOLVED_FORM_8990_LIMITATION", "Form 8990 interest limitation is unresolved."),
        "has_unresolved_auto_expense": ("UNRESOLVED_AUTO_EXPENSE", "Auto/travel expenses are unresolved."),
        "has_depletion": ("UNSUPPORTED_DEPLETION", "Depletion is not supported in V1."),
        "has_line_19_special_deduction": ("UNSUPPORTED_LINE_19_SPECIAL_DEDUCTION", "Special Line 19 deductions are not supported in V1."),
        "has_real_estate_professional_case": ("UNSUPPORTED_REAL_ESTATE_PROFESSIONAL_CASE", "Real estate professional rules are not supported in V1."),
        "has_activity_grouping_election": ("UNSUPPORTED_ACTIVITY_GROUPING_ELECTION", "Rental activity grouping elections are not supported in V1."),
        "has_prior_year_passive_loss_not_in_external_result": ("PRIOR_YEAR_PASSIVE_LOSS_UNRESOLVED", "Prior-year suspended passive losses are unresolved.")
    }
    for attr, (code, msg) in mapping.items():
        if getattr(flags, attr, False):
            errors.append(ValidationIssue(code, field=attr, message=msg))

def validate_1099_compliance(inputs: ScheduleEPart1InputsV1, errors: List[ValidationIssue]):
    fc = inputs.form_1099_compliance
    if fc.requirement_status == "UNKNOWN":
        errors.append(ValidationIssue("FORM_1099_REQUIREMENT_UNKNOWN", field="form_1099_compliance.requirement_status", source_result_id=fc.source_result_id, message="1099 compliance requirement status is unknown."))
    elif fc.requirement_status == "REQUIRED":
        if fc.filed_or_will_file_required_forms is None:
            errors.append(ValidationIssue("FORM_1099_FILING_STATUS_UNKNOWN", field="form_1099_compliance.filed_or_will_file_required_forms", source_result_id=fc.source_result_id, message="1099 filing status is unknown but required."))

def validate_properties(inputs: ScheduleEPart1InputsV1, errors: List[ValidationIssue]):
    for prop in inputs.properties:
        # 1. Reporting route status
        if prop.reporting_route_status == "SCHEDULE_C_REQUIRED":
            errors.append(ValidationIssue("ROUTE_TO_SCHEDULE_C_SUBSTANTIAL_SERVICES", property_id=prop.property_id, message="Substantial services require Schedule C reporting."))
        elif prop.reporting_route_status == "FORM_4835_REQUIRED":
            errors.append(ValidationIssue("ROUTE_TO_FORM_4835", property_id=prop.property_id, message="Farm rental requires Form 4835 reporting."))
        elif prop.reporting_route_status in ("OTHER_ROUTE_REQUIRED", "UNKNOWN"):
            errors.append(ValidationIssue("UNKNOWN_REPORTING_ROUTE", property_id=prop.property_id, message="Unknown reporting route for property."))

        # 2. Property type
        if prop.property_type not in ("SINGLE_FAMILY_RESIDENCE", "MULTI_FAMILY_RESIDENCE"):
            if prop.property_type == "ROYALTIES":
                errors.append(ValidationIssue("UNSUPPORTED_ROYALTY_PROPERTY", property_id=prop.property_id, message="Royalty property is not supported in V1."))
            elif prop.property_type == "VACATION_SHORT_TERM_RENTAL":
                errors.append(ValidationIssue("UNSUPPORTED_SHORT_TERM_OR_VACATION_RENTAL", property_id=prop.property_id, message="Vacation/short-term rental is not supported in V1."))
            elif prop.property_type == "COMMERCIAL":
                errors.append(ValidationIssue("UNSUPPORTED_COMMERCIAL_PROPERTY", property_id=prop.property_id, message="Commercial property is not supported in V1."))
            elif prop.property_type == "LAND":
                errors.append(ValidationIssue("UNSUPPORTED_LAND_RENTAL", property_id=prop.property_id, message="Land rental is not supported in V1."))
            elif prop.property_type == "SELF_RENTAL":
                errors.append(ValidationIssue("UNSUPPORTED_SELF_RENTAL", property_id=prop.property_id, message="Self-rental is not supported in V1."))
            else:
                errors.append(ValidationIssue("UNSUPPORTED_OTHER_PROPERTY_TYPE", property_id=prop.property_id, message="Unsupported other property type in V1."))

        # 3. Days
        if prop.fair_rental_days is None or prop.fair_rental_days <= 0:
            errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="fair_rental_days", property_id=prop.property_id, message="Fair rental days must be greater than 0."))
        if prop.personal_use_days is not None and prop.personal_use_days > 0:
            errors.append(ValidationIssue("UNSUPPORTED_PERSONAL_USE_PROPERTY", field="personal_use_days", property_id=prop.property_id, message="Personal use days must be 0 in V1."))

        # 4. QJV
        if prop.qjv_status is True:
            errors.append(ValidationIssue("UNSUPPORTED_QJV", property_id=prop.property_id, message="Qualified Joint Venture is not supported in V1."))

        # 5. Ownership allocation
        if prop.ownership_allocation_status != "TAXPAYER_SHARE_CONFIRMED":
            errors.append(ValidationIssue("UNRESOLVED_OWNERSHIP_ALLOCATION", property_id=prop.property_id, message="Ownership allocation is unresolved or unconfirmed."))

        # 6. Income items validation
        for item in prop.rental_income_items:
            if item.income_character_status == "UNKNOWN":
                errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", property_id=prop.property_id, item_id=item.item_id, source_document_id=item.source_document_id, message="Rental income character is unknown."))
            if item.received_in_tax_year is None:
                errors.append(ValidationIssue("UNKNOWN_RENTAL_INCOME_TIMING", property_id=prop.property_id, item_id=item.item_id, source_document_id=item.source_document_id, message="Rental income tax year timing is unknown."))
            if item.refunded_or_returned_amount > item.gross_amount_received:
                errors.append(ValidationIssue("ADJUSTMENT_EXCEEDS_GROSS_AMOUNT", property_id=prop.property_id, item_id=item.item_id, source_document_id=item.source_document_id, message="Returned/refunded amount cannot exceed gross amount received."))

        # 7. Expense items validation
        for item in prop.rental_expense_items:
            if item.deductibility_status == "UNKNOWN":
                errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", property_id=prop.property_id, item_id=item.item_id, source_document_id=item.source_document_id, message="Expense deductibility status is unknown."))
            if item.allocation_status == "UNKNOWN":
                errors.append(ValidationIssue("UNRESOLVED_OWNERSHIP_ALLOCATION", property_id=prop.property_id, item_id=item.item_id, source_document_id=item.source_document_id, message="Expense ownership/property allocation status is unresolved."))
            if item.paid_or_incurred_in_tax_year is None:
                errors.append(ValidationIssue("UNKNOWN_EXPENSE_TIMING", property_id=prop.property_id, item_id=item.item_id, source_document_id=item.source_document_id, message="Expense tax year timing is unknown."))
            if item.external_calculation_status == "REQUIRED_BUT_MISSING":
                if item.expense_category == "AUTO_AND_TRAVEL":
                    errors.append(ValidationIssue("UNRESOLVED_AUTO_EXPENSE", property_id=prop.property_id, item_id=item.item_id, source_document_id=item.source_document_id, message="Auto expense details unresolved."))
                elif item.expense_category in ("MORTGAGE_INTEREST_FINANCIAL_INSTITUTION", "OTHER_INTEREST"):
                    errors.append(ValidationIssue("UNRESOLVED_INTEREST_TRACING", property_id=prop.property_id, item_id=item.item_id, source_document_id=item.source_document_id, message="Interest tracing unresolved."))
                else:
                    errors.append(ValidationIssue("EXTERNAL_EXPENSE_CALCULATION_MISSING", property_id=prop.property_id, item_id=item.item_id, source_document_id=item.source_document_id, message="Required external calculation is missing."))

            adjustments = item.reimbursement_amount + item.nonrental_allocated_amount
            if adjustments > item.gross_amount:
                errors.append(ValidationIssue("ADJUSTMENT_EXCEEDS_GROSS_AMOUNT", property_id=prop.property_id, item_id=item.item_id, source_document_id=item.source_document_id, message="Expense adjustments exceed gross amount."))

            if item.expense_category == "OTHER" and (not item.description or not item.description.strip()):
                errors.append(ValidationIssue("OTHER_EXPENSE_DESCRIPTION_MISSING", property_id=prop.property_id, item_id=item.item_id, source_document_id=item.source_document_id, message="Other expense description is missing."))
            if item.deductibility_status == "CAPITALIZE":
                if item.expense_category == "REPAIRS":
                    # capital improvement misclassified as repairs
                    errors.append(ValidationIssue("CAPITAL_IMPROVEMENT_MISCLASSIFIED", property_id=prop.property_id, item_id=item.item_id, source_document_id=item.source_document_id, message="Capital improvement is misclassified as repairs."))
