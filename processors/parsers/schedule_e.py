import os
from typing import Dict, Any, List
from processors.base_parser import BaseLLMParser


class ScheduleELLMParser(BaseLLMParser):
    def get_schema_path(self) -> str:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.abspath(
            os.path.join(current_dir, "..", "..", "docs", "how_to_fill_forms_docs", "schedule_e", "schedule_e_schema.json")
        )

    def get_form_name(self) -> str:
        return "Schedule E (Form 1040) Part I"

    def get_custom_rules(self) -> List[str]:
        return [
            "只提取與長期住宅出租地產相關的收入與支出 facts，排除 royalties、commercial 等 V1 不支援的項目。",
            "折舊金額（Line 18）必須從 Form 4562 或外部折舊模組獲取，不得自行計算。"
        ]

    def get_example_json(self) -> Dict[str, Any]:
        return {
            "taxpayer_name": "Marcus Rivera",
            "taxpayer_ssn": "123-45-6789",
            "tax_year": 2025,
            "filing_status": "MFJ",
            "accounting_method": "CASH",
            "form_1099_compliance": {
                "requirement_status": "REQUIRED",
                "filed_or_will_file_required_forms": True,
                "source_result_id": "res_1099_01"
            },
            "special_case_flags": {},
            "properties": [
                {
                    "property_id": "prop_001",
                    "physical_address": {
                        "street": "5200 Green Valley Drive, Unit 208",
                        "city": "Sacramento",
                        "state": "CA",
                        "zip_code": "95841",
                        "country": "US"
                    },
                    "property_type": "SINGLE_FAMILY_RESIDENCE",
                    "reporting_route_status": "SCHEDULE_E_CONFIRMED",
                    "fair_rental_days": 365,
                    "personal_use_days": 0,
                    "qjv_status": False,
                    "ownership_allocation_status": "TAXPAYER_SHARE_CONFIRMED",
                    "rental_income_items": [
                        {
                            "item_id": "inc_01",
                            "gross_amount_received": 16650.0,
                            "refunded_or_returned_amount": 0.0,
                            "income_character_status": "REPORTABLE_SIMPLE_RENTAL_INCOME",
                            "received_in_tax_year": True
                        }
                    ],
                    "rental_expense_items": [
                        {
                            "item_id": "exp_ins",
                            "expense_category": "INSURANCE",
                            "gross_amount": 900.0,
                            "reimbursement_amount": 0.0,
                            "nonrental_allocated_amount": 0.0,
                            "deductibility_status": "DEDUCTIBLE_CURRENT",
                            "allocation_status": "TAXPAYER_SHARE_CONFIRMED",
                            "paid_or_incurred_in_tax_year": True
                        },
                        {
                            "item_id": "exp_int",
                            "expense_category": "MORTGAGE_INTEREST_FINANCIAL_INSTITUTION",
                            "gross_amount": 4800.0,
                            "reimbursement_amount": 0.0,
                            "nonrental_allocated_amount": 0.0,
                            "deductibility_status": "DEDUCTIBLE_CURRENT",
                            "allocation_status": "TAXPAYER_SHARE_CONFIRMED",
                            "paid_or_incurred_in_tax_year": True
                        },
                        {
                            "item_id": "exp_rep",
                            "expense_category": "REPAIRS",
                            "gross_amount": 550.0,
                            "reimbursement_amount": 0.0,
                            "nonrental_allocated_amount": 0.0,
                            "deductibility_status": "DEDUCTIBLE_CURRENT",
                            "allocation_status": "TAXPAYER_SHARE_CONFIRMED",
                            "paid_or_incurred_in_tax_year": True
                        },
                        {
                            "item_id": "exp_tax",
                            "expense_category": "TAXES",
                            "gross_amount": 2400.0,
                            "reimbursement_amount": 0.0,
                            "nonrental_allocated_amount": 0.0,
                            "deductibility_status": "DEDUCTIBLE_CURRENT",
                            "allocation_status": "TAXPAYER_SHARE_CONFIRMED",
                            "paid_or_incurred_in_tax_year": True
                        }
                    ],
                    "depreciation_result": {
                        "property_id": "prop_001",
                        "tax_year": 2025,
                        "calculation_status": "CALCULATED",
                        "depreciation_amount": 8000.0,
                        "form_4562_attachment_required": False,
                        "source_result_id": "dep_res_01"
                    }
                }
            ]
        }
