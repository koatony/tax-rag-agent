import json
from decimal import Decimal
from typing import Dict, Any, List, Optional

def mask_ssn(ssn: str) -> str:
    if not ssn:
        return ""
    clean = ssn.strip()
    if clean.startswith("***") or clean.startswith("XXX"):
        return clean
    parts = clean.split("-")
    if len(parts) == 3 and len(parts[2]) == 4:
        return f"***-**-{parts[2]}"
    digits = [c for c in clean if c.isdigit()]
    if len(digits) >= 4:
        return f"***-**-{''.join(digits[-4:])}"
    return "***-**-****"

class ValidationIssue:
    def __init__(self, code: str, field: Optional[str] = None, property_id: Optional[str] = None, item_id: Optional[str] = None, source_document_id: Optional[str] = None, source_result_id: Optional[str] = None, message: str = ""):
        self.code = code
        self.field = field
        self.property_id = property_id
        self.item_id = item_id
        self.source_document_id = source_document_id
        self.source_result_id = source_result_id
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "field": self.field,
            "property_id": self.property_id,
            "item_id": self.item_id,
            "source_document_id": self.source_document_id,
            "source_result_id": self.source_result_id,
            "message": self.message
        }

class Form1099ComplianceResultV1:
    def __init__(self, **kwargs):
        self.requirement_status = str(kwargs.get("requirement_status", "UNKNOWN")).upper()
        self.filed_or_will_file_required_forms = kwargs.get("filed_or_will_file_required_forms")
        if self.filed_or_will_file_required_forms is not None:
            if isinstance(self.filed_or_will_file_required_forms, str):
                self.filed_or_will_file_required_forms = self.filed_or_will_file_required_forms.lower() in ("true", "yes")
            else:
                self.filed_or_will_file_required_forms = bool(self.filed_or_will_file_required_forms)
        self.source_result_id = kwargs.get("source_result_id")
        self.source_document_ids = kwargs.get("source_document_ids") or []

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Form1099ComplianceResultV1":
        return cls(**data)

class RentalPropertyAddressV1:
    def __init__(self, **kwargs):
        self.street = str(kwargs.get("street", ""))
        self.city = str(kwargs.get("city", ""))
        self.state = str(kwargs.get("state", ""))
        self.zip_code = str(kwargs.get("zip_code", ""))
        self.country = str(kwargs.get("country", ""))

    def to_str(self) -> str:
        parts = [self.street, self.city, self.state, self.zip_code, self.country]
        return ", ".join([p for p in parts if p])

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RentalPropertyAddressV1":
        return cls(**data)

class RentalIncomeItemV1:
    def __init__(self, **kwargs):
        self.item_id = str(kwargs.get("item_id", ""))
        self.source_document_id = kwargs.get("source_document_id")
        self.description = kwargs.get("description")
        
        self.received_in_tax_year = kwargs.get("received_in_tax_year")
        if self.received_in_tax_year is not None:
            self.received_in_tax_year = bool(self.received_in_tax_year)
            
        self.gross_amount_received = Decimal(str(kwargs.get("gross_amount_received", "0.00")))
        self.refunded_or_returned_amount = Decimal(str(kwargs.get("refunded_or_returned_amount", "0.00")))
        self.income_character_status = str(kwargs.get("income_character_status", "UNKNOWN")).upper()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RentalIncomeItemV1":
        return cls(**data)

class RentalExpenseItemV1:
    def __init__(self, **kwargs):
        self.item_id = str(kwargs.get("item_id", ""))
        self.source_document_id = kwargs.get("source_document_id")
        self.description = kwargs.get("description")
        
        self.paid_or_incurred_in_tax_year = kwargs.get("paid_or_incurred_in_tax_year")
        if self.paid_or_incurred_in_tax_year is not None:
            self.paid_or_incurred_in_tax_year = bool(self.paid_or_incurred_in_tax_year)
            
        self.gross_amount = Decimal(str(kwargs.get("gross_amount", "0.00")))
        self.reimbursement_amount = Decimal(str(kwargs.get("reimbursement_amount", "0.00")))
        self.nonrental_allocated_amount = Decimal(str(kwargs.get("nonrental_allocated_amount", "0.00")))
        self.expense_category = str(kwargs.get("expense_category", "UNKNOWN")).upper()
        self.deductibility_status = str(kwargs.get("deductibility_status", "UNKNOWN")).upper()
        self.allocation_status = str(kwargs.get("allocation_status", "UNKNOWN")).upper()
        self.external_calculation_status = str(kwargs.get("external_calculation_status", "NOT_REQUIRED")).upper()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RentalExpenseItemV1":
        return cls(**data)

class ExternalDepreciationResultV1:
    def __init__(self, **kwargs):
        self.property_id = str(kwargs.get("property_id", ""))
        self.tax_year = int(kwargs.get("tax_year", 0))
        self.calculation_status = str(kwargs.get("calculation_status", "BLOCKED")).upper()
        
        self.depreciation_amount = kwargs.get("depreciation_amount")
        if self.depreciation_amount is not None:
            self.depreciation_amount = Decimal(str(self.depreciation_amount))
            
        self.form_4562_attachment_required = kwargs.get("form_4562_attachment_required")
        if self.form_4562_attachment_required is not None:
            self.form_4562_attachment_required = bool(self.form_4562_attachment_required)
            
        self.source_result_id = str(kwargs.get("source_result_id", ""))
        self.source_document_ids = kwargs.get("source_document_ids") or []
        self.blocking_errors = kwargs.get("blocking_errors") or []
        self.review_warnings = kwargs.get("review_warnings") or []

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExternalDepreciationResultV1":
        return cls(**data)

class AtRiskLimitationResultV1:
    def __init__(self, **kwargs):
        self.property_id = str(kwargs.get("property_id", ""))
        self.tax_year = int(kwargs.get("tax_year", 0))
        self.status = str(kwargs.get("status", "UNKNOWN")).upper()
        
        self.line_21_allowed_income_or_loss = kwargs.get("line_21_allowed_income_or_loss")
        if self.line_21_allowed_income_or_loss is not None:
            self.line_21_allowed_income_or_loss = Decimal(str(self.line_21_allowed_income_or_loss))
            
        self.form_6198_attachment_required = kwargs.get("form_6198_attachment_required")
        if self.form_6198_attachment_required is not None:
            self.form_6198_attachment_required = bool(self.form_6198_attachment_required)
            
        self.source_result_id = kwargs.get("source_result_id")
        self.blocking_errors = kwargs.get("blocking_errors") or []

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AtRiskLimitationResultV1":
        return cls(**data)

class PassiveLossLimitationResultV1:
    def __init__(self, **kwargs):
        self.property_id = str(kwargs.get("property_id", ""))
        self.tax_year = int(kwargs.get("tax_year", 0))
        self.status = str(kwargs.get("status", "UNKNOWN")).upper()
        
        self.line_22_deductible_rental_loss = kwargs.get("line_22_deductible_rental_loss")
        if self.line_22_deductible_rental_loss is not None:
            self.line_22_deductible_rental_loss = Decimal(str(self.line_22_deductible_rental_loss))
            
        self.includes_prior_year_unallowed_loss = bool(kwargs.get("includes_prior_year_unallowed_loss", False))
        
        self.form_8582_attachment_required = kwargs.get("form_8582_attachment_required")
        if self.form_8582_attachment_required is not None:
            self.form_8582_attachment_required = bool(self.form_8582_attachment_required)
            
        self.source_result_id = kwargs.get("source_result_id")
        self.blocking_errors = kwargs.get("blocking_errors") or []

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PassiveLossLimitationResultV1":
        return cls(**data)

class ScheduleEPart1SpecialCaseFlagsV1:
    def __init__(self, **kwargs):
        self.has_royalty_property = bool(kwargs.get("has_royalty_property", False))
        self.has_more_than_three_properties = bool(kwargs.get("has_more_than_three_properties", False))
        self.has_short_term_or_vacation_rental = bool(kwargs.get("has_short_term_or_vacation_rental", False))
        self.has_personal_use_property = bool(kwargs.get("has_personal_use_property", False))
        self.has_rented_less_than_15_days_case = bool(kwargs.get("has_rented_less_than_15_days_case", False))
        self.has_commercial_property = bool(kwargs.get("has_commercial_property", False))
        self.has_land_rental = bool(kwargs.get("has_land_rental", False))
        self.has_self_rental = bool(kwargs.get("has_self_rental", False))
        self.has_other_property_type = bool(kwargs.get("has_other_property_type", False))
        self.has_foreign_rental_property = bool(kwargs.get("has_foreign_rental_property", False))
        self.has_qjv = bool(kwargs.get("has_qjv", False))
        self.has_substantial_services = bool(kwargs.get("has_substantial_services", False))
        self.has_real_estate_dealer_inventory_rental = bool(kwargs.get("has_real_estate_dealer_inventory_rental", False))
        self.has_farm_rental = bool(kwargs.get("has_farm_rental", False))
        self.has_personal_property_only_rental = bool(kwargs.get("has_personal_property_only_rental", False))
        self.has_unresolved_ownership_allocation = bool(kwargs.get("has_unresolved_ownership_allocation", False))
        self.has_unresolved_conversion_allocation = bool(kwargs.get("has_unresolved_conversion_allocation", False))
        self.has_unknown_security_deposit_character = bool(kwargs.get("has_unknown_security_deposit_character", False))
        self.has_unknown_income_timing = bool(kwargs.get("has_unknown_income_timing", False))
        self.has_unresolved_repair_vs_improvement = bool(kwargs.get("has_unresolved_repair_vs_improvement", False))
        self.has_unresolved_legal_fee_capitalization = bool(kwargs.get("has_unresolved_legal_fee_capitalization", False))
        self.has_unresolved_interest_tracing = bool(kwargs.get("has_unresolved_interest_tracing", False))
        self.has_unresolved_points_or_prepaid_interest = bool(kwargs.get("has_unresolved_points_or_prepaid_interest", False))
        self.has_unresolved_form_8990_limitation = bool(kwargs.get("has_unresolved_form_8990_limitation", False))
        self.has_unresolved_auto_expense = bool(kwargs.get("has_unresolved_auto_expense", False))
        self.has_depletion = bool(kwargs.get("has_depletion", False))
        self.has_line_19_special_deduction = bool(kwargs.get("has_line_19_special_deduction", False))
        self.has_real_estate_professional_case = bool(kwargs.get("has_real_estate_professional_case", False))
        self.has_activity_grouping_election = bool(kwargs.get("has_activity_grouping_election", False))
        self.has_prior_year_passive_loss_not_in_external_result = bool(kwargs.get("has_prior_year_passive_loss_not_in_external_result", False))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduleEPart1SpecialCaseFlagsV1":
        return cls(**data)

class RentalPropertyInputV1:
    def __init__(self, **kwargs):
        self.property_id = str(kwargs.get("property_id", ""))
        self.source_document_ids = kwargs.get("source_document_ids") or []
        
        addr_data = kwargs.get("physical_address")
        if isinstance(addr_data, dict):
            self.physical_address = RentalPropertyAddressV1.from_dict(addr_data)
        else:
            self.physical_address = addr_data

        self.property_type = str(kwargs.get("property_type", "UNKNOWN")).upper()
        self.other_property_description = kwargs.get("other_property_description")
        self.reporting_route_status = str(kwargs.get("reporting_route_status", "UNKNOWN")).upper()

        self.fair_rental_days = kwargs.get("fair_rental_days")
        if self.fair_rental_days is not None:
            self.fair_rental_days = int(self.fair_rental_days)
            
        self.personal_use_days = kwargs.get("personal_use_days")
        if self.personal_use_days is not None:
            self.personal_use_days = int(self.personal_use_days)

        self.qjv_status = kwargs.get("qjv_status")
        if self.qjv_status is not None:
            self.qjv_status = bool(self.qjv_status)

        self.ownership_allocation_status = str(kwargs.get("ownership_allocation_status", "UNKNOWN")).upper()

        self.rental_income_items = [
            RentalIncomeItemV1.from_dict(x) if isinstance(x, dict) else x
            for x in kwargs.get("rental_income_items") or []
        ]
        self.rental_expense_items = [
            RentalExpenseItemV1.from_dict(x) if isinstance(x, dict) else x
            for x in kwargs.get("rental_expense_items") or []
        ]

        dep_data = kwargs.get("depreciation_result")
        if isinstance(dep_data, dict):
            self.depreciation_result = ExternalDepreciationResultV1.from_dict(dep_data)
        else:
            self.depreciation_result = dep_data

        at_risk_data = kwargs.get("at_risk_result")
        if isinstance(at_risk_data, dict):
            self.at_risk_result = AtRiskLimitationResultV1.from_dict(at_risk_data)
        else:
            self.at_risk_result = at_risk_data

        passive_data = kwargs.get("passive_loss_result")
        if isinstance(passive_data, dict):
            self.passive_loss_result = PassiveLossLimitationResultV1.from_dict(passive_data)
        else:
            self.passive_loss_result = passive_data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RentalPropertyInputV1":
        return cls(**data)

class ScheduleEPart1InputsV1:
    def __init__(self, **kwargs):
        self.taxpayer_name = str(kwargs.get("taxpayer_name", ""))
        self.taxpayer_ssn = str(kwargs.get("taxpayer_ssn", ""))
        self.tax_year = int(kwargs.get("tax_year", 0))
        self.filing_status = str(kwargs.get("filing_status", "SINGLE")).upper()
        self.accounting_method = str(kwargs.get("accounting_method", "CASH")).upper()

        f1099 = kwargs.get("form_1099_compliance")
        if isinstance(f1099, dict):
            self.form_1099_compliance = Form1099ComplianceResultV1.from_dict(f1099)
        elif f1099 is None:
            self.form_1099_compliance = Form1099ComplianceResultV1()
        else:
            self.form_1099_compliance = f1099

        self.properties = [
            RentalPropertyInputV1.from_dict(x) if isinstance(x, dict) else x
            for x in kwargs.get("properties") or []
        ]

        flags = kwargs.get("special_case_flags")
        if isinstance(flags, dict):
            self.special_case_flags = ScheduleEPart1SpecialCaseFlagsV1.from_dict(flags)
        elif flags is None:
            self.special_case_flags = ScheduleEPart1SpecialCaseFlagsV1()
        else:
            self.special_case_flags = flags

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduleEPart1InputsV1":
        return cls(**data)

class OtherExpenseSurfaceItemV1:
    def __init__(self, description: str, amount: Decimal, source_document_id: Optional[str] = None, item_id: Optional[str] = None):
        self.description = description
        self.amount = amount
        self.source_document_id = source_document_id
        self.item_id = item_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "amount": float(self.amount),
            "source_document_id": self.source_document_id,
            "item_id": self.item_id
        }

class ScheduleEPropertyResultV1:
    def __init__(self, **kwargs):
        self.property_id = kwargs.get("property_id", "")
        self.property_column = kwargs.get("property_column")  # A | B | C

        self.line_1a_physical_address = kwargs.get("line_1a_physical_address", "")
        self.line_1b_property_type_code = kwargs.get("line_1b_property_type_code")
        self.line_2_fair_rental_days = kwargs.get("line_2_fair_rental_days", 0)
        self.line_2_personal_use_days = kwargs.get("line_2_personal_use_days", 0)
        self.line_2_qjv_checkbox = bool(kwargs.get("line_2_qjv_checkbox", False))

        self.line_3_rents_received = kwargs.get("line_3_rents_received", Decimal("0.00"))
        self.line_4_royalties_received = kwargs.get("line_4_royalties_received", Decimal("0.00"))

        self.line_5_advertising = kwargs.get("line_5_advertising", Decimal("0.00"))
        self.line_6_auto_and_travel = kwargs.get("line_6_auto_and_travel", Decimal("0.00"))
        self.line_7_cleaning_and_maintenance = kwargs.get("line_7_cleaning_and_maintenance", Decimal("0.00"))
        self.line_8_commissions = kwargs.get("line_8_commissions", Decimal("0.00"))
        self.line_9_insurance = kwargs.get("line_9_insurance", Decimal("0.00"))
        self.line_10_legal_and_professional_fees = kwargs.get("line_10_legal_and_professional_fees", Decimal("0.00"))
        self.line_11_management_fees = kwargs.get("line_11_management_fees", Decimal("0.00"))
        self.line_12_mortgage_interest = kwargs.get("line_12_mortgage_interest", Decimal("0.00"))
        self.line_13_other_interest = kwargs.get("line_13_other_interest", Decimal("0.00"))
        self.line_14_repairs = kwargs.get("line_14_repairs", Decimal("0.00"))
        self.line_15_supplies = kwargs.get("line_15_supplies", Decimal("0.00"))
        self.line_16_taxes = kwargs.get("line_16_taxes", Decimal("0.00"))
        self.line_17_utilities = kwargs.get("line_17_utilities", Decimal("0.00"))
        self.line_18_depreciation = kwargs.get("line_18_depreciation")

        self.line_19_other_expense_items = kwargs.get("line_19_other_expense_items") or []
        self.line_19_other_expenses_total = kwargs.get("line_19_other_expenses_total", Decimal("0.00"))

        self.line_20_total_expenses = kwargs.get("line_20_total_expenses")
        self.pre_at_risk_net_income_or_loss = kwargs.get("pre_at_risk_net_income_or_loss")
        self.line_21_income_or_loss = kwargs.get("line_21_income_or_loss")
        self.line_22_deductible_rental_loss = kwargs.get("line_22_deductible_rental_loss")

        self.depreciation_source_result_id = kwargs.get("depreciation_source_result_id")
        self.at_risk_source_result_id = kwargs.get("at_risk_source_result_id")
        self.passive_loss_source_result_id = kwargs.get("passive_loss_source_result_id")

        self.blocking_errors = kwargs.get("blocking_errors") or []
        self.review_warnings = kwargs.get("review_warnings") or []

    def to_dict(self) -> Dict[str, Any]:
        def to_val(v):
            if isinstance(v, Decimal):
                return float(v)
            return v
        return {
            "property_id": self.property_id,
            "property_column": self.property_column,
            "line_1a_physical_address": self.line_1a_physical_address,
            "line_1b_property_type_code": self.line_1b_property_type_code,
            "line_2_fair_rental_days": self.line_2_fair_rental_days,
            "line_2_personal_use_days": self.line_2_personal_use_days,
            "line_2_qjv_checkbox": self.line_2_qjv_checkbox,
            "line_3_rents_received": to_val(self.line_3_rents_received),
            "line_4_royalties_received": to_val(self.line_4_royalties_received),
            "line_5_advertising": to_val(self.line_5_advertising),
            "line_6_auto_and_travel": to_val(self.line_6_auto_and_travel),
            "line_7_cleaning_and_maintenance": to_val(self.line_7_cleaning_and_maintenance),
            "line_8_commissions": to_val(self.line_8_commissions),
            "line_9_insurance": to_val(self.line_9_insurance),
            "line_10_legal_and_professional_fees": to_val(self.line_10_legal_and_professional_fees),
            "line_11_management_fees": to_val(self.line_11_management_fees),
            "line_12_mortgage_interest": to_val(self.line_12_mortgage_interest),
            "line_13_other_interest": to_val(self.line_13_other_interest),
            "line_14_repairs": to_val(self.line_14_repairs),
            "line_15_supplies": to_val(self.line_15_supplies),
            "line_16_taxes": to_val(self.line_16_taxes),
            "line_17_utilities": to_val(self.line_17_utilities),
            "line_18_depreciation": to_val(self.line_18_depreciation),
            "line_19_other_expense_items": [x.to_dict() for x in self.line_19_other_expense_items],
            "line_19_other_expenses_total": to_val(self.line_19_other_expenses_total),
            "line_20_total_expenses": to_val(self.line_20_total_expenses),
            "pre_at_risk_net_income_or_loss": to_val(self.pre_at_risk_net_income_or_loss),
            "line_21_income_or_loss": to_val(self.line_21_income_or_loss),
            "line_22_deductible_rental_loss": to_val(self.line_22_deductible_rental_loss),
            "depreciation_source_result_id": self.depreciation_source_result_id,
            "at_risk_source_result_id": self.at_risk_source_result_id,
            "passive_loss_source_result_id": self.passive_loss_source_result_id,
            "blocking_errors": [x.to_dict() if hasattr(x, "to_dict") else x for x in self.blocking_errors],
            "review_warnings": [x.to_dict() if hasattr(x, "to_dict") else x for x in self.review_warnings],
        }

class ScheduleEPart1ResultV1:
    def __init__(self, **kwargs):
        self.taxpayer_name = kwargs.get("taxpayer_name", "")
        self.taxpayer_ssn_masked = mask_ssn(kwargs.get("taxpayer_ssn", ""))
        self.tax_year = int(kwargs.get("tax_year", 0))
        self.filing_status = kwargs.get("filing_status", "")

        self.line_a_form_1099_required = kwargs.get("line_a_form_1099_required")
        if self.line_a_form_1099_required is not None:
            self.line_a_form_1099_required = bool(self.line_a_form_1099_required)
            
        self.line_b_forms_1099_filed_or_will_file = kwargs.get("line_b_forms_1099_filed_or_will_file")
        if self.line_b_forms_1099_filed_or_will_file is not None:
            self.line_b_forms_1099_filed_or_will_file = bool(self.line_b_forms_1099_filed_or_will_file)

        self.properties = kwargs.get("properties") or []

        self.line_23a_total_rents = kwargs.get("line_23a_total_rents")
        if self.line_23a_total_rents is not None:
            self.line_23a_total_rents = Decimal(str(self.line_23a_total_rents))

        self.line_23b_total_royalties = kwargs.get("line_23b_total_royalties")
        if self.line_23b_total_royalties is not None:
            self.line_23b_total_royalties = Decimal(str(self.line_23b_total_royalties))

        self.line_23c_total_mortgage_interest = kwargs.get("line_23c_total_mortgage_interest")
        if self.line_23c_total_mortgage_interest is not None:
            self.line_23c_total_mortgage_interest = Decimal(str(self.line_23c_total_mortgage_interest))

        self.line_23d_total_depreciation = kwargs.get("line_23d_total_depreciation")
        if self.line_23d_total_depreciation is not None:
            self.line_23d_total_depreciation = Decimal(str(self.line_23d_total_depreciation))

        self.line_23e_total_expenses = kwargs.get("line_23e_total_expenses")
        if self.line_23e_total_expenses is not None:
            self.line_23e_total_expenses = Decimal(str(self.line_23e_total_expenses))

        self.line_24_income = kwargs.get("line_24_income")
        if self.line_24_income is not None:
            self.line_24_income = Decimal(str(self.line_24_income))

        self.line_25_losses = kwargs.get("line_25_losses")
        if self.line_25_losses is not None:
            self.line_25_losses = Decimal(str(self.line_25_losses))

        self.line_26_total_rental_income_or_loss = kwargs.get("line_26_total_rental_income_or_loss")
        if self.line_26_total_rental_income_or_loss is not None:
            self.line_26_total_rental_income_or_loss = Decimal(str(self.line_26_total_rental_income_or_loss))

        self.schedule_1_line_5_transfer_amount = kwargs.get("schedule_1_line_5_transfer_amount")
        if self.schedule_1_line_5_transfer_amount is not None:
            self.schedule_1_line_5_transfer_amount = Decimal(str(self.schedule_1_line_5_transfer_amount))

        self.requires_form_4562_attachment = kwargs.get("requires_form_4562_attachment")
        if self.requires_form_4562_attachment is not None:
            self.requires_form_4562_attachment = bool(self.requires_form_4562_attachment)
            
        self.requires_form_6198_attachment = kwargs.get("requires_form_6198_attachment")
        if self.requires_form_6198_attachment is not None:
            self.requires_form_6198_attachment = bool(self.requires_form_6198_attachment)
            
        self.requires_form_8582_attachment = kwargs.get("requires_form_8582_attachment")
        if self.requires_form_8582_attachment is not None:
            self.requires_form_8582_attachment = bool(self.requires_form_8582_attachment)
            
        self.requires_form_461_review = bool(kwargs.get("requires_form_461_review", False))

        self.has_reportable_rental_property = bool(kwargs.get("has_reportable_rental_property", False))
        self.is_v1_supported = bool(kwargs.get("is_v1_supported", False))
        self.should_attach_schedule_e = bool(kwargs.get("should_attach_schedule_e", False))
        self.can_finalize_part1 = bool(kwargs.get("can_finalize_part1", False))
        self.can_transfer_line_26 = bool(kwargs.get("can_transfer_line_26", False))

        self.blocking_errors = kwargs.get("blocking_errors") or []
        self.review_warnings = kwargs.get("review_warnings") or []

    def to_dict(self) -> Dict[str, Any]:
        def to_val(v):
            if isinstance(v, Decimal):
                return float(v)
            return v
        return {
            "taxpayer_name": self.taxpayer_name,
            "taxpayer_ssn_masked": self.taxpayer_ssn_masked,
            "tax_year": self.tax_year,
            "filing_status": self.filing_status,
            "line_a_form_1099_required": self.line_a_form_1099_required,
            "line_b_forms_1099_filed_or_will_file": self.line_b_forms_1099_filed_or_will_file,
            "properties": [p.to_dict() if hasattr(p, "to_dict") else p for p in self.properties],
            "line_23a_total_rents": to_val(self.line_23a_total_rents),
            "line_23b_total_royalties": to_val(self.line_23b_total_royalties),
            "line_23c_total_mortgage_interest": to_val(self.line_23c_total_mortgage_interest),
            "line_23d_total_depreciation": to_val(self.line_23d_total_depreciation),
            "line_23e_total_expenses": to_val(self.line_23e_total_expenses),
            "line_24_income": to_val(self.line_24_income),
            "line_25_losses": to_val(self.line_25_losses),
            "line_26_total_rental_income_or_loss": to_val(self.line_26_total_rental_income_or_loss),
            "schedule_1_line_5_transfer_amount": to_val(self.schedule_1_line_5_transfer_amount),
            "requires_form_4562_attachment": self.requires_form_4562_attachment,
            "requires_form_6198_attachment": self.requires_form_6198_attachment,
            "requires_form_8582_attachment": self.requires_form_8582_attachment,
            "requires_form_461_review": self.requires_form_461_review,
            "has_reportable_rental_property": self.has_reportable_rental_property,
            "is_v1_supported": self.is_v1_supported,
            "should_attach_schedule_e": self.should_attach_schedule_e,
            "can_finalize_part1": self.can_finalize_part1,
            "can_transfer_line_26": self.can_transfer_line_26,
            "blocking_errors": [x.to_dict() if hasattr(x, "to_dict") else x for x in self.blocking_errors],
            "review_warnings": [x.to_dict() if hasattr(x, "to_dict") else x for x in self.review_warnings],
        }
