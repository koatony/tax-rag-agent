from decimal import Decimal
from typing import List, Dict, Any, Tuple, Set, Optional
from processors.models.schedule_e import (
    ScheduleEPart1InputsV1,
    ScheduleEPart1ResultV1,
    ScheduleEPropertyResultV1,
    OtherExpenseSurfaceItemV1,
    ValidationIssue,
)
from processors.validators.schedule_e import (
    validate_identity,
    validate_tax_year,
    validate_accounting_method,
    validate_nonnegative_amounts,
    detect_unsupported_cases,
    validate_1099_compliance,
    validate_properties,
)

ZERO = Decimal("0.00")

UNSUPPORTED_CODES = {
    "UNSUPPORTED_ROYALTY_PROPERTY",
    "UNSUPPORTED_MORE_THAN_THREE_PROPERTIES",
    "UNSUPPORTED_SHORT_TERM_OR_VACATION_RENTAL",
    "UNSUPPORTED_PERSONAL_USE_PROPERTY",
    "UNSUPPORTED_RENTED_LESS_THAN_15_DAYS",
    "UNRESOLVED_PERSONAL_RENTAL_ALLOCATION",
    "UNSUPPORTED_COMMERCIAL_PROPERTY",
    "UNSUPPORTED_LAND_RENTAL",
    "UNSUPPORTED_SELF_RENTAL",
    "UNSUPPORTED_OTHER_PROPERTY_TYPE",
    "UNSUPPORTED_FOREIGN_RENTAL_PROPERTY",
    "UNSUPPORTED_QJV",
    "ROUTE_TO_SCHEDULE_C_SUBSTANTIAL_SERVICES",
    "ROUTE_TO_SCHEDULE_C_REAL_ESTATE_DEALER",
    "ROUTE_TO_FORM_4835",
    "ROUTE_PERSONAL_PROPERTY_RENTAL",
    "UNKNOWN_REPORTING_ROUTE",
    "UNRESOLVED_OWNERSHIP_ALLOCATION",
    "UNRESOLVED_CONVERSION_ALLOCATION",
    "UNKNOWN_SECURITY_DEPOSIT_CHARACTER",
    "UNKNOWN_RENTAL_INCOME_TIMING",
    "UNRESOLVED_REPAIR_VS_IMPROVEMENT",
    "CAPITAL_IMPROVEMENT_MISCLASSIFIED",
    "UNRESOLVED_LEGAL_FEE_CAPITALIZATION",
    "UNRESOLVED_INTEREST_TRACING",
    "UNRESOLVED_POINTS_OR_PREPAID_INTEREST",
    "UNRESOLVED_FORM_8990_LIMITATION",
    "UNRESOLVED_AUTO_EXPENSE",
    "UNSUPPORTED_DEPLETION",
    "UNSUPPORTED_LINE_19_SPECIAL_DEDUCTION",
    "UNSUPPORTED_REAL_ESTATE_PROFESSIONAL_CASE",
    "UNSUPPORTED_ACTIVITY_GROUPING_ELECTION",
    "PRIOR_YEAR_PASSIVE_LOSS_UNRESOLVED",
    "FORM_1099_REQUIREMENT_UNKNOWN",
    "FORM_1099_FILING_STATUS_UNKNOWN"
}

def calculate_schedule_e_part1_v1(inputs: ScheduleEPart1InputsV1, allowed_years: Optional[Set[int]] = None) -> ScheduleEPart1ResultV1:
    global_errors: List[ValidationIssue] = []
    global_warnings: List[ValidationIssue] = []

    if allowed_years is None:
        try:
            import os
            import json
            current_dir = os.path.dirname(os.path.abspath(__file__))
            schema_path = os.path.abspath(os.path.join(current_dir, "..", "..", "docs", "how_to_fill_forms_docs", "schedule_e", "schedule_e_schema.json"))
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_data = json.load(f)
            allowed_years = set(schema_data.get("supported_tax_years", [2024, 2025]))
        except Exception:
            allowed_years = {2024, 2025}

    # 1. Run validations on input wrapper level
    validate_identity(inputs, global_errors)
    validate_tax_year(inputs.tax_year, allowed_years, global_errors)
    validate_accounting_method(inputs.accounting_method, "CASH", global_errors)
    validate_nonnegative_amounts(inputs, global_errors)

    if any(e.code == "UNSUPPORTED_TAX_YEAR" for e in global_errors):
        return ScheduleEPart1ResultV1(
            taxpayer_name=inputs.taxpayer_name,
            taxpayer_ssn=inputs.taxpayer_ssn,
            tax_year=inputs.tax_year,
            filing_status=inputs.filing_status,
            blocking_errors=global_errors,
            review_warnings=global_warnings,
            can_file=False,
            is_v1_supported=False
        )
    detect_unsupported_cases(inputs.special_case_flags, global_errors)
    validate_1099_compliance(inputs, global_errors)
    validate_properties(inputs, global_errors)

    if len(inputs.properties) == 0:
        global_errors.append(ValidationIssue("NO_REPORTABLE_RENTAL_PROPERTY", field="properties", message="No rental properties reported."))

    if len(inputs.properties) > 3:
        global_errors.append(ValidationIssue("UNSUPPORTED_MORE_THAN_THREE_PROPERTIES", field="properties", message="More than three properties is not supported in V1."))

    property_results: List[ScheduleEPropertyResultV1] = []
    columns = ["A", "B", "C"]

    # 2. Process each property
    for idx, prop in enumerate(inputs.properties):
        prop_errors: List[ValidationIssue] = []
        prop_warnings: List[ValidationIssue] = []
        column = columns[idx] if idx < len(columns) else None

        # Determine Property Type Code
        line_1b_code = None
        if prop.property_type == "SINGLE_FAMILY_RESIDENCE":
            line_1b_code = 1
        elif prop.property_type == "MULTI_FAMILY_RESIDENCE":
            line_1b_code = 2

        # Line 3 — Rents received
        line_3 = ZERO
        for item in prop.rental_income_items:
            if item.income_character_status == "REPORTABLE_SIMPLE_RENTAL_INCOME" and item.received_in_tax_year is True:
                line_3 += (item.gross_amount_received - item.refunded_or_returned_amount)
            else:
                # Add exclusion warning
                prop_warnings.append(ValidationIssue(
                    "RENTAL_INCOME_ITEM_EXCLUDED",
                    property_id=prop.property_id,
                    item_id=item.item_id,
                    source_document_id=item.source_document_id,
                    message=f"Income item {item.item_id} excluded because of character status ({item.income_character_status}) or timing."
                ))

        # Line 4 — Royalties (V1 does not support royalties)
        line_4 = ZERO

        # Lines 5–17 and 19 Expense buckets
        buckets = {
            "ADVERTISING": ZERO,
            "AUTO_AND_TRAVEL": ZERO,
            "CLEANING_AND_MAINTENANCE": ZERO,
            "COMMISSIONS": ZERO,
            "INSURANCE": ZERO,
            "LEGAL_AND_PROFESSIONAL": ZERO,
            "MANAGEMENT_FEES": ZERO,
            "MORTGAGE_INTEREST_FINANCIAL_INSTITUTION": ZERO,
            "OTHER_INTEREST": ZERO,
            "REPAIRS": ZERO,
            "SUPPLIES": ZERO,
            "TAXES": ZERO,
            "UTILITIES": ZERO,
        }
        line_19_items: List[OtherExpenseSurfaceItemV1] = []
        line_19_total = ZERO

        for item in prop.rental_expense_items:
            if item.deductibility_status == "DEDUCTIBLE_CURRENT" and item.paid_or_incurred_in_tax_year is True:
                adjustments = item.reimbursement_amount + item.nonrental_allocated_amount
                eligible_amount = item.gross_amount - adjustments
                
                if item.expense_category in buckets:
                    buckets[item.expense_category] += eligible_amount
                elif item.expense_category == "OTHER":
                    line_19_items.append(OtherExpenseSurfaceItemV1(
                        description=item.description or "Other expense",
                        amount=eligible_amount,
                        source_document_id=item.source_document_id,
                        item_id=item.item_id
                    ))
                    line_19_total += eligible_amount
            else:
                prop_warnings.append(ValidationIssue(
                    "RENTAL_EXPENSE_ITEM_EXCLUDED_OR_ROUTED",
                    property_id=prop.property_id,
                    item_id=item.item_id,
                    source_document_id=item.source_document_id,
                    message=f"Expense item {item.item_id} excluded because of deductibility status ({item.deductibility_status}) or timing."
                ))

        # Line 18 — Depreciation
        line_18 = None
        dep_source_id = None
        if prop.depreciation_result:
            dep_source_id = prop.depreciation_result.source_result_id
            if prop.depreciation_result.calculation_status == "CALCULATED":
                line_18 = prop.depreciation_result.depreciation_amount
            elif prop.depreciation_result.calculation_status == "NOT_APPLICABLE":
                line_18 = ZERO
            else:
                prop_errors.append(ValidationIssue(
                    "DEPRECIATION_MODULE_BLOCKED",
                    property_id=prop.property_id,
                    source_result_id=dep_source_id,
                    message="Depreciation module execution was blocked."
                ))
        else:
            prop_errors.append(ValidationIssue(
                "DEPRECIATION_RESULT_MISSING",
                property_id=prop.property_id,
                message="Depreciation result is missing."
            ))

        # Line 20 — Total expenses
        line_20 = None
        if line_18 is not None:
            line_20 = (
                buckets["ADVERTISING"] +
                buckets["AUTO_AND_TRAVEL"] +
                buckets["CLEANING_AND_MAINTENANCE"] +
                buckets["COMMISSIONS"] +
                buckets["INSURANCE"] +
                buckets["LEGAL_AND_PROFESSIONAL"] +
                buckets["MANAGEMENT_FEES"] +
                buckets["MORTGAGE_INTEREST_FINANCIAL_INSTITUTION"] +
                buckets["OTHER_INTEREST"] +
                buckets["REPAIRS"] +
                buckets["SUPPLIES"] +
                buckets["TAXES"] +
                buckets["UTILITIES"] +
                line_18 +
                line_19_total
            )

        # Pre-at-risk net income or loss
        pre_at_risk = None
        if line_20 is not None:
            pre_at_risk = line_3 - line_20

        # Line 21 — Income or loss after at-risk limitation
        line_21 = None
        at_risk_source_id = None
        if pre_at_risk is not None:
            if pre_at_risk >= ZERO:
                line_21 = pre_at_risk
            else:
                if prop.at_risk_result:
                    at_risk_source_id = prop.at_risk_result.source_result_id
                    if prop.at_risk_result.status == "NOT_REQUIRED_FULLY_AT_RISK":
                        line_21 = pre_at_risk
                    elif prop.at_risk_result.status == "CALCULATED_BY_FORM_6198":
                        line_21 = prop.at_risk_result.line_21_allowed_income_or_loss
                        if line_21 is not None and not (pre_at_risk <= line_21 <= ZERO):
                            prop_errors.append(ValidationIssue(
                                "AT_RISK_RESULT_INVALID",
                                property_id=prop.property_id,
                                source_result_id=at_risk_source_id,
                                message="At-risk result allowed loss exceeds original loss or is positive."
                            ))
                    else:
                        prop_errors.append(ValidationIssue(
                            "AT_RISK_RESULT_MISSING",
                            property_id=prop.property_id,
                            source_result_id=at_risk_source_id,
                            message="At-risk result is blocked or unknown."
                        ))
                else:
                    prop_errors.append(ValidationIssue(
                        "AT_RISK_RESULT_MISSING",
                        property_id=prop.property_id,
                        message="At-risk result is missing for property with loss."
                    ))

        # Line 22 — Deductible passive activity loss
        line_22_surface = None
        line_22_amount_for_total = ZERO
        passive_loss_source_id = None

        if pre_at_risk is not None and pre_at_risk < ZERO:
            if prop.passive_loss_result:
                passive_loss_source_id = prop.passive_loss_result.source_result_id
                if line_21 is not None and line_21 >= ZERO:
                    line_22_surface = None
                    line_22_amount_for_total = ZERO
                else:
                    if prop.passive_loss_result.status in ("LOSS_ALLOWED_WITHOUT_FORM_8582", "CALCULATED_BY_FORM_8582"):
                        line_22_surface = prop.passive_loss_result.line_22_deductible_rental_loss
                        if line_22_surface is not None:
                            line_22_amount_for_total = line_22_surface
                            if line_22_surface > ZERO:
                                prop_errors.append(ValidationIssue(
                                    "PASSIVE_LOSS_RESULT_INVALID",
                                    property_id=prop.property_id,
                                    source_result_id=passive_loss_source_id,
                                    message="Passive loss allowed amount cannot be positive."
                                ))
                    else:
                        prop_errors.append(ValidationIssue(
                            "PASSIVE_LOSS_RESULT_MISSING",
                            property_id=prop.property_id,
                            source_result_id=passive_loss_source_id,
                            message="Passive loss result is blocked or unknown."
                        ))
            else:
                if not (line_21 is not None and line_21 >= ZERO):
                    prop_errors.append(ValidationIssue(
                        "PASSIVE_LOSS_RESULT_MISSING",
                        property_id=prop.property_id,
                        message="Passive loss result is missing for property with loss."
                    ))

        property_results.append(ScheduleEPropertyResultV1(
            property_id=prop.property_id,
            property_column=column,
            line_1a_physical_address=prop.physical_address.to_str() if prop.physical_address else "",
            line_1b_property_type_code=line_1b_code,
            line_2_fair_rental_days=prop.fair_rental_days or 0,
            line_2_personal_use_days=prop.personal_use_days or 0,
            line_2_qjv_checkbox=bool(prop.qjv_status),
            line_3_rents_received=line_3,
            line_4_royalties_received=line_4,
            line_5_advertising=buckets["ADVERTISING"],
            line_6_auto_and_travel=buckets["AUTO_AND_TRAVEL"],
            line_7_cleaning_and_maintenance=buckets["CLEANING_AND_MAINTENANCE"],
            line_8_commissions=buckets["COMMISSIONS"],
            line_9_insurance=buckets["INSURANCE"],
            line_10_legal_and_professional_fees=buckets["LEGAL_AND_PROFESSIONAL"],
            line_11_management_fees=buckets["MANAGEMENT_FEES"],
            line_12_mortgage_interest=buckets["MORTGAGE_INTEREST_FINANCIAL_INSTITUTION"],
            line_13_other_interest=buckets["OTHER_INTEREST"],
            line_14_repairs=buckets["REPAIRS"],
            line_15_supplies=buckets["SUPPLIES"],
            line_16_taxes=buckets["TAXES"],
            line_17_utilities=buckets["UTILITIES"],
            line_18_depreciation=line_18,
            line_19_other_expense_items=line_19_items,
            line_19_other_expenses_total=line_19_total,
            line_20_total_expenses=line_20,
            pre_at_risk_net_income_or_loss=pre_at_risk,
            line_21_income_or_loss=line_21,
            line_22_deductible_rental_loss=line_22_surface,
            depreciation_source_result_id=dep_source_id,
            at_risk_source_result_id=at_risk_source_id,
            passive_loss_source_result_id=passive_loss_source_id,
            blocking_errors=prop_errors,
            review_warnings=prop_warnings
        ))

    # 3. Aggregate totals
    line_23a_total_rents = sum(p.line_3_rents_received for p in property_results)
    line_23b_total_royalties = ZERO
    line_23c_total_mortgage_interest = sum(p.line_12_mortgage_interest for p in property_results)

    if any(p.line_18_depreciation is None for p in property_results):
        line_23d_total_depreciation = None
    else:
        line_23d_total_depreciation = sum(p.line_18_depreciation for p in property_results)

    if any(p.line_20_total_expenses is None for p in property_results):
        line_23e_total_expenses = None
    else:
        line_23e_total_expenses = sum(p.line_20_total_expenses for p in property_results)

    # Line 24 — Income
    line_24_income = sum(
        p.line_21_income_or_loss for p in property_results
        if p.line_21_income_or_loss is not None and p.line_21_income_or_loss > ZERO
    )

    # Line 25 — Losses
    line_25_losses = sum(
        p.line_22_deductible_rental_loss for p in property_results
        if p.line_22_deductible_rental_loss is not None and p.line_22_deductible_rental_loss < ZERO
    )

    line_26_total_rental_income_or_loss = line_24_income + line_25_losses

    # Attachment coordination
    requires_form_4562_attachment = any(
        prop.depreciation_result.form_4562_attachment_required
        for prop in inputs.properties if prop.depreciation_result
    )
    requires_form_6198_attachment = any(
        prop.at_risk_result.form_6198_attachment_required
        for prop in inputs.properties if prop.at_risk_result
    )
    requires_form_8582_attachment = any(
        prop.passive_loss_result.form_8582_attachment_required
        for prop in inputs.properties if prop.passive_loss_result
    )

    requires_form_461_review = line_26_total_rental_income_or_loss < ZERO

    # Overall attachment and finalization
    has_reportable_rental_property = any(
        prop.reporting_route_status == "SCHEDULE_E_CONFIRMED"
        for prop in inputs.properties
    )

    # Collect all errors
    all_blocking_errors: List[ValidationIssue] = list(global_errors)
    all_review_warnings: List[ValidationIssue] = list(global_warnings)

    for p in property_results:
        all_blocking_errors.extend(p.blocking_errors)
        all_review_warnings.extend(p.review_warnings)

    is_v1_supported = not any(err.code in UNSUPPORTED_CODES for err in all_blocking_errors)

    # Check for missing line_18 or unresolved lines for loss properties
    every_prop_resolved = True
    for p in property_results:
        if p.line_18_depreciation is None:
            every_prop_resolved = False
        # If it has a loss (pre_at_risk < 0), must have resolved line_21 and line_22
        if p.pre_at_risk_net_income_or_loss is not None and p.pre_at_risk_net_income_or_loss < ZERO:
            if p.line_21_income_or_loss is None or p.line_22_deductible_rental_loss is None:
                every_prop_resolved = False

    can_finalize_part1 = (
        is_v1_supported
        and has_reportable_rental_property
        and len(global_errors) == 0
        and every_prop_resolved
    )

    can_transfer_line_26 = can_finalize_part1
    schedule_1_line_5_transfer_amount = line_26_total_rental_income_or_loss if can_transfer_line_26 else None

    return ScheduleEPart1ResultV1(
        taxpayer_name=inputs.taxpayer_name,
        taxpayer_ssn=inputs.taxpayer_ssn,
        tax_year=inputs.tax_year,
        filing_status=inputs.filing_status,
        line_a_form_1099_required=inputs.form_1099_compliance.requirement_status == "REQUIRED",
        line_b_forms_1099_filed_or_will_file=inputs.form_1099_compliance.filed_or_will_file_required_forms,
        properties=property_results,
        line_23a_total_rents=line_23a_total_rents,
        line_23b_total_royalties=line_23b_total_royalties,
        line_23c_total_mortgage_interest=line_23c_total_mortgage_interest,
        line_23d_total_depreciation=line_23d_total_depreciation,
        line_23e_total_expenses=line_23e_total_expenses,
        line_24_income=line_24_income,
        line_25_losses=line_25_losses,
        line_26_total_rental_income_or_loss=line_26_total_rental_income_or_loss,
        schedule_1_line_5_transfer_amount=schedule_1_line_5_transfer_amount,
        requires_form_4562_attachment=requires_form_4562_attachment,
        requires_form_6198_attachment=requires_form_6198_attachment,
        requires_form_8582_attachment=requires_form_8582_attachment,
        requires_form_461_review=requires_form_461_review,
        has_reportable_rental_property=has_reportable_rental_property,
        is_v1_supported=is_v1_supported,
        should_attach_schedule_e=has_reportable_rental_property,
        can_finalize_part1=can_finalize_part1,
        can_transfer_line_26=can_transfer_line_26,
        blocking_errors=all_blocking_errors,
        review_warnings=all_review_warnings
    )
