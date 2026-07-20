from typing import List, Set, Optional
from decimal import Decimal
from processors.models.schedule_a import ValidationIssue
from processors.models.schedule_c import ScheduleCInputsV1

def validate_identity(inputs: ScheduleCInputsV1, errors: List[ValidationIssue], allowed: Optional[Set[int]] = None):
    if not inputs.proprietor_name.strip():
        errors.append(ValidationIssue("MISSING_PROPRIETOR_NAME", "proprietor_name", message="Proprietor name is missing."))
    if not inputs.taxpayer_ssn.strip():
        errors.append(ValidationIssue("MISSING_SSN", "taxpayer_ssn", message="SSN is missing."))
    
    allowed_set = allowed if allowed is not None else {2024, 2025}
    if inputs.tax_year is None:
        errors.append(ValidationIssue("UNSUPPORTED_TAX_YEAR", "tax_year", message="Tax year is missing in input data."))
    elif inputs.tax_year not in allowed_set:
        errors.append(ValidationIssue("UNSUPPORTED_TAX_YEAR", "tax_year", message=f"Tax year {inputs.tax_year} is not supported."))
    if inputs.income.line_1_gross_receipts is None:
        errors.append(ValidationIssue("MISSING_GROSS_RECEIPTS", "line_1_gross_receipts", message="Gross receipts are missing."))

def validate_nonnegative_amounts(inputs: ScheduleCInputsV1, errors: List[ValidationIssue]):
    ZERO = Decimal("0.00")
    # Check income fields
    if inputs.income.line_1_gross_receipts is not None and inputs.income.line_1_gross_receipts < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "line_1_gross_receipts", message="Gross receipts cannot be negative."))
    if inputs.income.line_2_returns_allowances < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "line_2_returns_allowances", message="Returns and allowances cannot be negative."))
    if inputs.income.line_6_other_income < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "line_6_other_income", message="Other income cannot be negative."))

    # Check expense fields
    exp = inputs.expenses
    expense_fields = [
        ("line_8_advertising", exp.line_8_advertising),
        ("line_10_commissions_fees", exp.line_10_commissions_fees),
        ("line_11_contract_labor", exp.line_11_contract_labor),
        ("line_12_depletion", exp.line_12_depletion),
        ("line_14_employee_benefit_programs", exp.line_14_employee_benefit_programs),
        ("line_15_insurance", exp.line_15_insurance),
        ("line_16a_mortgage_interest", exp.line_16a_mortgage_interest),
        ("line_16b_other_interest", exp.line_16b_other_interest),
        ("line_17_legal_professional", exp.line_17_legal_professional),
        ("line_18_office_expense", exp.line_18_office_expense),
        ("line_19_pension_profit_sharing", exp.line_19_pension_profit_sharing),
        ("line_20a_rent_machinery_equipment", exp.line_20a_rent_machinery_equipment),
        ("line_20b_rent_other_property", exp.line_20b_rent_other_property),
        ("line_21_repairs_maintenance", exp.line_21_repairs_maintenance),
        ("line_22_supplies", exp.line_22_supplies),
        ("line_23_taxes_licenses", exp.line_23_taxes_licenses),
        ("meals_50_percent_source_amount", exp.meals_50_percent_source_amount),
        ("meals_100_percent_source_amount", exp.meals_100_percent_source_amount),
        ("entertainment_source_amount", exp.entertainment_source_amount),
        ("line_25_utilities", exp.line_25_utilities),
    ]

    # Nullable fields to check if not None
    nullable_fields = [
        ("line_9_car_truck_expenses_final", exp.line_9_car_truck_expenses_final),
        ("line_24a_travel_final", exp.line_24a_travel_final),
        ("line_26_wages_final", exp.line_26_wages_final),
        ("line_13_depreciation_from_form4562", exp.line_13_depreciation_from_form4562),
        ("line_30_home_office_from_module", exp.line_30_home_office_from_module),
        ("line_4_cogs_from_module", exp.line_4_cogs_from_module),
    ]

    for name, val in expense_fields:
        if val < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", name, message=f"{name} cannot be negative."))

    for name, val in nullable_fields:
        if val is not None and val < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", name, message=f"{name} cannot be negative."))

    # Check other expense items
    for idx, item in enumerate(inputs.other_expense_items):
        if item.amount < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", f"other_expense_items[{idx}].amount", item_id=item.item_id, message="Other expense amount cannot be negative."))

def detect_unsupported_cases(inputs: ScheduleCInputsV1, errors: List[ValidationIssue]):
    flags = inputs.special_case_flags
    exp = inputs.expenses

    # 1. Non-trade/business type checks
    if flags.has_rental_or_royalty_activity:
        errors.append(ValidationIssue("WRONG_FORM_RENTAL_OR_ROYALTY", "has_rental_or_royalty_activity", message="Rental or royalty activity is not supported in Schedule C V1."))
    if flags.has_farm_activity:
        errors.append(ValidationIssue("WRONG_FORM_FARM_INCOME", "has_farm_activity", message="Farming activity is not supported in Schedule C V1."))
    if flags.has_business_asset_sale:
        errors.append(ValidationIssue("UNSUPPORTED_ASSET_SALE", "has_business_asset_sale", message="Business asset sale is not supported in V1."))
    if flags.has_passive_activity_issue:
        errors.append(ValidationIssue("PASSIVE_ACTIVITY_LIMITATION", "has_passive_activity_issue", message="Passive activity loss limitation is not supported in V1."))
    if flags.has_at_risk_limitation_issue:
        errors.append(ValidationIssue("AT_RISK_LIMITATION", "has_at_risk_limitation_issue", message="At-risk limitation is not supported in V1."))
    if flags.has_qbi_request:
        errors.append(ValidationIssue("UNSUPPORTED_QBI_CALCULATION", "has_qbi_request", message="Qualified Business Income (QBI) deduction calculation is not supported in V1."))
    if flags.has_schedule_se_request:
        errors.append(ValidationIssue("UNSUPPORTED_SE_TAX_CALCULATION", "has_schedule_se_request", message="Self-Employment Tax (Schedule SE) calculation is not supported in V1."))

    # 2. General Special flags checking blocking cases
    if flags.has_owner_draw_in_expenses:
        errors.append(ValidationIssue("OWNER_DRAW_INCLUDED_IN_EXPENSES", "has_owner_draw_in_expenses", message="Owner salary/draw is not allowed as a business expense on Schedule C."))
    if flags.has_uncertain_meals_or_entertainment:
        errors.append(ValidationIssue("UNCERTAIN_MEALS_ENTERTAINMENT_CLASSIFICATION", "has_uncertain_meals_or_entertainment", message="Meals/entertainment classification is uncertain."))
    if flags.has_uncertain_expense_category:
        errors.append(ValidationIssue("UNCERTAIN_EXPENSE_CLASSIFICATION", "has_uncertain_expense_category", message="Uncertain expense category requires review."))

    # 3. Missing upstream module inputs for special features
    if flags.has_inventory_or_cogs:
        if not flags.cogs_module_completed or exp.line_4_cogs_from_module is None:
            errors.append(ValidationIssue("COGS_MODULE_REQUIRED", "line_4_cogs_from_module", message="COGS/inventory is detected but completed COGS module output is missing."))
    if flags.has_vehicle_expense_requiring_calculation and exp.line_9_car_truck_expenses_final is None:
        errors.append(ValidationIssue("UNSUPPORTED_VEHICLE_CALCULATION_IN_V1", "line_9_car_truck_expenses_final", message="Vehicle calculation is not supported in V1 without upstream final amount."))
    if flags.has_depreciation_or_section179 and exp.line_13_depreciation_from_form4562 is None:
        errors.append(ValidationIssue("FORM_4562_REQUIRED", "line_13_depreciation_from_form4562", message="Form 4562 depreciation is not supported in V1 without upstream module output."))
    if flags.has_home_office and exp.line_30_home_office_from_module is None:
        errors.append(ValidationIssue("FORM_8829_OR_SIMPLIFIED_HOME_OFFICE_REQUIRED", "line_30_home_office_from_module", message="Home office deduction is not supported in V1 without upstream module output."))
    if flags.has_mixed_travel and exp.line_24a_travel_final is None:
        errors.append(ValidationIssue("UNSUPPORTED_TRAVEL_ALLOCATION_IN_V1", "line_24a_travel_final", message="Mixed/international travel allocation is not supported in V1 without upstream final amount."))
    if flags.has_employee_wages_or_payroll_credit and exp.line_26_wages_final is None:
        errors.append(ValidationIssue("PAYROLL_OR_OWNER_DRAW_REVIEW_REQUIRED", "line_26_wages_final", message="Employee wages require review or final amount in V1."))

def validate_questionnaire(inputs: ScheduleCInputsV1, errors: List[ValidationIssue]):
    if inputs.line_i_payment_requiring_1099 is True:
        if inputs.line_j_filed_required_1099 is None:
            errors.append(ValidationIssue(
                "FORM_1099_ANSWER_MISSING",
                "line_j_filed_required_1099",
                message="Line J (whether required Forms 1099 were filed) must be answered when Line I is Yes."
            ))

def validate_meals_and_entertainment(inputs: ScheduleCInputsV1, warnings: List[ValidationIssue]):
    if inputs.expenses.meals_100_percent_source_amount > Decimal("0.00"):
        warnings.append(ValidationIssue(
            "REVIEW_100_PCT_MEALS",
            "meals_100_percent_source_amount",
            message="100% deductible meals (e.g. employee holiday party) are claimed; please verify they meet the IRS requirements for full deduction."
        ))
