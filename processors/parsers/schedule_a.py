import os
from typing import Dict, Any, List
from processors.base_parser import BaseLLMParser


class ScheduleALLMParser(BaseLLMParser):
    def get_schema_path(self) -> str:
        # 回傳Schema JSON檔案的絕對路徑
        # os.path.abspath 會換成絕對路徑
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.abspath(
            os.path.join(current_dir, "..", "..", "docs", "how_to_fill_forms_docs", "schedule_a", "schedule_a_schema.json")
        )


    def get_form_name(self) -> str:
        return "Schedule A (Form 1040)"

    def get_custom_rules(self) -> List[str]:
        return []


    
    def get_example_json(self) -> Dict[str, Any]:
        return {
            "taxpayer_name": "Marcus Rivera",
            "taxpayer_ssn": "123-45-6789",
            "tax_year": 2025,
            "filing_status": "MFJ",
            "adjusted_gross_income": 0.0,
            "medical_items": [
                {
                    "item_id": "med_01",
                    "taxpayer_paid_amount": 0.0,
                    "reimbursement_amount": 0.0,
                    "tax_free_medical_account_payment": 0.0,
                    "paid_in_tax_year": True,
                    "eligible_person_status": "ELIGIBLE",
                    "medical_qualification_status": "QUALIFIED_SIMPLE",
                    "description": "Example: doctor visit co-pay"
                }
            ],
            "tax_items": [
                {
                    "item_id": "tax_01",
                    "amount_paid": 0.0,
                    "separately_stated_nondeductible_charge": 0.0,
                    "paid_in_tax_year": True,
                    "tax_category": "STATE_LOCAL_INCOME_TAX",
                    "personal_use_confirmed": True,
                    "actual_paid_to_taxing_authority_confirmed": True,
                    "value_based_and_annual_confirmed": True,
                    "description": "Example: CA state income tax withheld"
                }
            ],
            "line_5a_election": "INCOME_TAX",
            "mortgage_interest_items": [
                {
                    "item_id": "mort_01",
                    "source_document_type": "FORM_1098",
                    "lender_name": "",
                    "form_1098_box_1_mortgage_interest": 0.0,
                    "deductible_points_reported_on_1098": 0.0,
                    "paid_in_tax_year": True,
                    "simple_mortgage_status": "CONFIRMED_SIMPLE"
                }
            ],
            "cash_charity_items": [
                {
                    "item_id": "charity_01",
                    "organization_name": "",
                    "qualified_organization_status": "VERIFIED",
                    "contribution_method": "CASH",
                    "gross_contribution_amount": 0.0,
                    "goods_or_services_value": 0.0,
                    "paid_in_tax_year": True,
                    "bank_or_written_record_available": True,
                    "contemporaneous_acknowledgment_received": True
                }
            ],
            "special_case_flags": {
                "has_marketplace_medical_premium": False,
                "has_ltc_premium": False
            }
        }