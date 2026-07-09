from decimal import Decimal
from typing import List, Dict, Any
from processors.models.schedule_a import ValidationIssue
from processors.models.schedule_c import ScheduleCInputsV1, ScheduleCResultV1
from processors.validators.schedule_c import (
    validate_identity,
    validate_nonnegative_amounts,
    detect_unsupported_cases,
    validate_questionnaire,
    validate_meals_and_entertainment,
)

def calculate_schedule_c_v1(inputs: ScheduleCInputsV1) -> ScheduleCResultV1:
    errors: List[ValidationIssue] = []
    warnings: List[ValidationIssue] = []
    ZERO = Decimal("0.00")

    # 1. Run Validators
    validate_identity(inputs, errors)
    validate_nonnegative_amounts(inputs, errors)
    detect_unsupported_cases(inputs, errors)
    validate_questionnaire(inputs, errors)
    validate_meals_and_entertainment(inputs, warnings)

    # 2. Check for low confidence other expenses
    for item in inputs.other_expense_items:
        if item.confidence == "LOW":
            warnings.append(ValidationIssue(
                "LOW_CONFIDENCE_OTHER_EXPENSE",
                field="other_expense_items",
                item_id=item.item_id,
                source_document_id=item.source_document_id,
                message=f"Other expense item '{item.name}' has LOW confidence."
            ))

    def coalesce_decimal(val) -> Decimal:
        return val if val is not None else Decimal("0.00")

    # 3. Calculate Income
    line_1_gross_receipts = inputs.income.line_1_gross_receipts
    line_2_returns_allowances = inputs.income.line_2_returns_allowances
    if line_1_gross_receipts is not None:
        line_3_net_receipts = line_1_gross_receipts - line_2_returns_allowances
        if line_3_net_receipts < ZERO:
            errors.append(ValidationIssue("NEGATIVE_NET_RECEIPTS", "line_3_net_receipts", message="Net receipts cannot be negative."))
    else:
        line_3_net_receipts = None

    # 4. COGS
    if inputs.special_case_flags.has_inventory_or_cogs:
        if inputs.special_case_flags.cogs_module_completed:
            line_4_cogs = inputs.expenses.line_4_cogs_from_module
        else:
            line_4_cogs = None
    else:
        line_4_cogs = Decimal("0.00")

    line_6_other_income = inputs.income.line_6_other_income

    # Gross Profit & Gross Income Calculation
    # If any required inputs are missing, gross profit/income should be None.
    if line_3_net_receipts is None or line_4_cogs is None:
        line_5_gross_profit = None
        line_7_gross_income = None
    else:
        line_5_gross_profit = line_3_net_receipts - line_4_cogs
        line_7_gross_income = line_5_gross_profit + coalesce_decimal(line_6_other_income)

    # 5. Expenses (Lines 8-27)
    line_8 = inputs.expenses.line_8_advertising
    
    if inputs.special_case_flags.has_vehicle_expense_requiring_calculation:
        line_9 = inputs.expenses.line_9_car_truck_expenses_final
    else:
        line_9 = inputs.expenses.line_9_car_truck_expenses_final or Decimal("0.00")
        
    line_10 = inputs.expenses.line_10_commissions_fees
    line_11 = inputs.expenses.line_11_contract_labor
    line_12 = inputs.expenses.line_12_depletion
    
    if inputs.special_case_flags.has_depreciation_or_section179:
        line_13 = inputs.expenses.line_13_depreciation_from_form4562
    else:
        line_13 = inputs.expenses.line_13_depreciation_from_form4562 or Decimal("0.00")
        
    line_14 = inputs.expenses.line_14_employee_benefit_programs
    line_15 = inputs.expenses.line_15_insurance
    line_16a = inputs.expenses.line_16a_mortgage_interest
    line_16b = inputs.expenses.line_16b_other_interest
    line_17 = inputs.expenses.line_17_legal_professional
    line_18 = inputs.expenses.line_18_office_expense
    line_19 = inputs.expenses.line_19_pension_profit_sharing
    line_20a = inputs.expenses.line_20a_rent_machinery_equipment
    line_20b = inputs.expenses.line_20b_rent_other_property
    line_21 = inputs.expenses.line_21_repairs_maintenance
    line_22 = inputs.expenses.line_22_supplies
    line_23 = inputs.expenses.line_23_taxes_licenses
    
    if inputs.special_case_flags.has_mixed_travel:
        line_24a = inputs.expenses.line_24a_travel_final
    else:
        line_24a = inputs.expenses.line_24a_travel_final or Decimal("0.00")
    
    # Meals & Entertainment
    line_24b = inputs.expenses.meals_50_percent_source_amount * Decimal("0.50") + inputs.expenses.meals_100_percent_source_amount

    line_25 = inputs.expenses.line_25_utilities
    
    if inputs.special_case_flags.has_employee_wages_or_payroll_credit:
        line_26 = inputs.expenses.line_26_wages_final
    else:
        line_26 = inputs.expenses.line_26_wages_final or Decimal("0.00")
        
    line_27a_energy_efficient_building_deduction = ZERO

    # Other Expenses Part V
    line_48_total_other_expenses = ZERO
    for item in inputs.other_expense_items:
        name_lower = item.name.lower()
        if "fine" in name_lower or "penalty" in name_lower:
            errors.append(ValidationIssue(
                "NONDEDUCTIBLE_FINE_OR_PENALTY",
                field="other_expense_items",
                item_id=item.item_id,
                source_document_id=item.source_document_id,
                message=f"Nondeductible fine/penalty '{item.name}' found in other expenses."
            ))
            continue
        line_48_total_other_expenses += item.amount
        
    line_27b = line_48_total_other_expenses

    # Check if any required module-based expense is missing when flags are set
    has_missing_required_expense = (
        line_9 is None or
        line_13 is None or
        line_24a is None or
        line_26 is None
    )

    # Total Expenses (Line 28)
    if has_missing_required_expense:
        line_28_total_expenses = None
    else:
        line_28_total_expenses = (
            coalesce_decimal(line_8) + coalesce_decimal(line_9) + coalesce_decimal(line_10) +
            coalesce_decimal(line_11) + coalesce_decimal(line_12) + coalesce_decimal(line_13) +
            coalesce_decimal(line_14) + coalesce_decimal(line_15) + coalesce_decimal(line_16a) +
            coalesce_decimal(line_16b) + coalesce_decimal(line_17) + coalesce_decimal(line_18) +
            coalesce_decimal(line_19) + coalesce_decimal(line_20a) + coalesce_decimal(line_20b) +
            coalesce_decimal(line_21) + coalesce_decimal(line_22) + coalesce_decimal(line_23) +
            coalesce_decimal(line_24a) + coalesce_decimal(line_24b) + coalesce_decimal(line_25) +
            coalesce_decimal(line_26) + coalesce_decimal(line_27a_energy_efficient_building_deduction) +
            coalesce_decimal(line_27b)
        )

    # 6. Profit or Loss
    if line_7_gross_income is None or line_28_total_expenses is None:
        line_29_tentative_profit_or_loss = None
    else:
        line_29_tentative_profit_or_loss = line_7_gross_income - line_28_total_expenses
    
    if inputs.special_case_flags.has_home_office:
        line_30 = inputs.expenses.line_30_home_office_from_module
    else:
        line_30 = inputs.expenses.line_30_home_office_from_module or Decimal("0.00")
        
    if line_29_tentative_profit_or_loss is None or line_30 is None:
        line_31_net_profit_or_loss = None
    else:
        line_31_net_profit_or_loss = line_29_tentative_profit_or_loss - line_30

    # 7. Loss case, At-Risk & Passive activities
    line_32_at_risk_surface = None
    if line_31_net_profit_or_loss is not None and line_31_net_profit_or_loss < ZERO:
        if inputs.loss_at_risk_answer == "ALL_AT_RISK":
            line_32_at_risk_surface = "32a"
        elif inputs.loss_at_risk_answer == "SOME_NOT_AT_RISK":
            line_32_at_risk_surface = "32b"
            errors.append(ValidationIssue("FORM_6198_REQUIRED", "loss_at_risk_answer", message="Form 6198 is required because some investment is not at risk."))
        else:
            errors.append(ValidationIssue("AT_RISK_ANSWER_MISSING", "loss_at_risk_answer", message="Loss at-risk answer is missing."))

        if inputs.line_g_material_participation is False:
            errors.append(ValidationIssue("PASSIVE_ACTIVITY_REVIEW_REQUIRED", "line_g_material_participation", message="Passive activity review is required since material participation is False and there is a net loss."))

        # Excess business loss check
        if line_31_net_profit_or_loss < Decimal("-313000.00"):
            errors.append(ValidationIssue("FORM_461_REVIEW_REQUIRED", "line_31_net_profit_or_loss", message="Form 461 review is required for excess business loss limitation."))

    # 8. Determine V1 States
    has_identity = bool(inputs.proprietor_name.strip() and inputs.taxpayer_ssn.strip())
    
    # Check if there is at least one income or expense input
    has_income_or_expense = (
        (inputs.income.line_1_gross_receipts is not None and inputs.income.line_1_gross_receipts > ZERO) or
        inputs.income.line_2_returns_allowances > ZERO or
        inputs.income.line_6_other_income > ZERO or
        len(inputs.other_expense_items) > 0 or
        any(
            val > ZERO
            for k, val in inputs.expenses.__dict__.items()
            if val is not None and k not in ("line_13_depreciation_from_form4562", "line_30_home_office_from_module", "line_4_cogs_from_module")
        )
    )
    can_map = bool(has_identity and has_income_or_expense)

    unsupported_codes = {
        "WRONG_FORM_RENTAL_OR_ROYALTY",
        "WRONG_FORM_FARM_INCOME",
        "UNSUPPORTED_ASSET_SALE",
        "OWNER_DRAW_INCLUDED_IN_EXPENSES",
        "UNCERTAIN_MEALS_ENTERTAINMENT_CLASSIFICATION",
        "UNCERTAIN_EXPENSE_CLASSIFICATION",
        "UNSUPPORTED_COGS_IN_V1",
        "UNSUPPORTED_VEHICLE_CALCULATION_IN_V1",
        "FORM_4562_REQUIRED",
        "FORM_8829_OR_SIMPLIFIED_HOME_OFFICE_REQUIRED",
        "UNSUPPORTED_TRAVEL_ALLOCATION_IN_V1",
        "PAYROLL_OR_OWNER_DRAW_REVIEW_REQUIRED",
        "FORM_6198_REQUIRED",
        "AT_RISK_ANSWER_MISSING",
        "PASSIVE_ACTIVITY_REVIEW_REQUIRED",
        "FORM_461_REVIEW_REQUIRED",
        "FORM_1099_ANSWER_MISSING"
    }
    
    any_unsupported = any(err.code in unsupported_codes for err in errors)
    is_v1_supported = not any_unsupported
    can_file = bool(is_v1_supported and len(errors) == 0)

    optional_missing = not (
        inputs.principal_business and
        inputs.principal_activity_code and
        inputs.business_name and
        inputs.ein and
        inputs.business_address and
        inputs.accounting_method
    )
    low_confidence = any(item.confidence == "LOW" for item in inputs.other_expense_items)
    needs_review = bool(len(warnings) > 0 or low_confidence or optional_missing)

    # SSN Masking for result
    raw_ssn = str(inputs.taxpayer_ssn or "")
    if len(raw_ssn) >= 4:
        ssn_masked = f"***-**-{raw_ssn[-4:]}"
    else:
        ssn_masked = "***-**-XXXX"

    return ScheduleCResultV1(
        proprietor_name=inputs.proprietor_name,
        taxpayer_ssn_masked=ssn_masked,
        tax_year=inputs.tax_year,
        principal_business=inputs.principal_business,
        principal_activity_code=inputs.principal_activity_code,
        business_name=inputs.business_name,
        ein=inputs.ein,
        business_address=inputs.business_address,
        accounting_method=inputs.accounting_method,
        line_g_material_participation=inputs.line_g_material_participation,
        line_h_started_or_acquired=inputs.line_h_started_or_acquired,
        line_i_payment_requiring_1099=inputs.line_i_payment_requiring_1099,
        line_j_filed_required_1099=inputs.line_j_filed_required_1099 if inputs.line_i_payment_requiring_1099 is True else None,
        line_1_gross_receipts=line_1_gross_receipts,
        line_2_returns_allowances=line_2_returns_allowances,
        line_3_net_receipts=line_3_net_receipts,
        line_4_cogs=line_4_cogs,
        line_5_gross_profit=line_5_gross_profit,
        line_6_other_income=line_6_other_income,
        line_7_gross_income=line_7_gross_income,
        line_8_advertising=line_8,
        line_9_car_truck_expenses=line_9,
        line_10_commissions_fees=line_10,
        line_11_contract_labor=line_11,
        line_12_depletion=line_12,
        line_13_depreciation=line_13,
        line_14_employee_benefit_programs=line_14,
        line_15_insurance=line_15,
        line_16a_mortgage_interest=line_16a,
        line_16b_other_interest=line_16b,
        line_17_legal_professional=line_17,
        line_18_office_expense=line_18,
        line_19_pension_profit_sharing=line_19,
        line_20a_rent_machinery_equipment=line_20a,
        line_20b_rent_other_property=line_20b,
        line_21_repairs_maintenance=line_21,
        line_22_supplies=line_22,
        line_23_taxes_licenses=line_23,
        line_24a_travel=line_24a,
        line_24b_deductible_meals=line_24b,
        line_25_utilities=line_25,
        line_26_wages=line_26,
        line_27a_energy_efficient_building_deduction=line_27a_energy_efficient_building_deduction,
        line_27b_other_expenses=line_27b,
        line_28_total_expenses=line_28_total_expenses,
        line_29_tentative_profit_or_loss=line_29_tentative_profit_or_loss,
        line_30_home_office=line_30,
        line_31_net_profit_or_loss=line_31_net_profit_or_loss,
        line_32_at_risk_surface=line_32_at_risk_surface,
        line_48_total_other_expenses=line_48_total_other_expenses,
        other_expense_items=inputs.other_expense_items,
        can_map=can_map,
        is_v1_supported=is_v1_supported,
        can_file=can_file,
        needs_review=needs_review,
        blocking_errors=errors,
        review_warnings=warnings,
    )
