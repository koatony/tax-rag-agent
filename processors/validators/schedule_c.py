from typing import List, Set
from decimal import Decimal
from processors.models.schedule_a import ValidationIssue
from processors.models.schedule_c import ScheduleCInputsV1

def validate_identity(inputs: ScheduleCInputsV1, errors: List[ValidationIssue]):
    if not inputs.proprietor_name.strip():
        errors.append(ValidationIssue("MISSING_PROPRIETOR_NAME", "proprietor_name", message="Proprietor name is missing."))
    if not inputs.ssn.strip():
        errors.append(ValidationIssue("MISSING_SSN", "ssn", message="SSN is missing."))

def validate_nonnegative_amounts(inputs: ScheduleCInputsV1, errors: List[ValidationIssue]):
    ZERO = Decimal("0.00")
    fields_to_check = [
        ("line_1_gross_receipts", inputs.line_1_gross_receipts),
        ("line_2_returns_allowances", inputs.line_2_returns_allowances),
        ("line_6_other_income", inputs.line_6_other_income),
        ("line_8_advertising", inputs.line_8_advertising),
        ("line_10_commissions_fees", inputs.line_10_commissions_fees),
        ("line_11_contract_labor", inputs.line_11_contract_labor),
        ("line_12_depletion", inputs.line_12_depletion),
        ("line_14_employee_benefit_programs", inputs.line_14_employee_benefit_programs),
        ("line_15_insurance", inputs.line_15_insurance),
        ("line_16a_mortgage_interest", inputs.line_16a_mortgage_interest),
        ("line_16b_other_interest", inputs.line_16b_other_interest),
        ("line_17_legal_professional", inputs.line_17_legal_professional),
        ("line_18_office_expense", inputs.line_18_office_expense),
        ("line_19_pension_profit_sharing", inputs.line_19_pension_profit_sharing),
        ("line_20a_rent_machinery_equipment", inputs.line_20a_rent_machinery_equipment),
        ("line_20b_rent_other_property", inputs.line_20b_rent_other_property),
        ("line_21_repairs_maintenance", inputs.line_21_repairs_maintenance),
        ("line_22_supplies", inputs.line_22_supplies),
        ("line_23_taxes_licenses", inputs.line_23_taxes_licenses),
        ("line_25_utilities", inputs.line_25_utilities),
        ("line_36_purchases_less_personal", inputs.line_36_purchases_less_personal),
        ("line_38_materials_supplies", inputs.line_38_materials_supplies),
        ("line_39_other_costs", inputs.line_39_other_costs),
        ("line_41_ending_inventory", inputs.line_41_ending_inventory),
        ("line_44a_business_miles", inputs.line_44a_business_miles),
        ("line_44b_commuting_miles", inputs.line_44b_commuting_miles),
        ("line_44c_other_miles", inputs.line_44c_other_miles),
    ]
    for field_name, val in fields_to_check:
        if val < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", field_name, message=f"{field_name} cannot be negative."))
