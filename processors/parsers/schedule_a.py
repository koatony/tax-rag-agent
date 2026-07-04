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
            "adjusted_gross_income": 125000.00,
            "medical_items": [],
            "tax_items": [],
            "line_5a_election": "INCOME_TAX",
            "mortgage_interest_items": [],
            "cash_charity_items": [],
            "special_case_flags": {
                "has_marketplace_medical_premium": false,
                "has_ltc_premium": false
            }
        }