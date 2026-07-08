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
        return [
            "LLM 只負責提取 Schedule A 的直接輸入欄位，不得自行計算 Schedule A line values，也不得自行判斷最終可申報性。",
            "若文件沒有明確提供某個狀態，請使用 null 或 UNKNOWN，不要猜測為 true、VERIFIED、ELIGIBLE 或 CONFIRMED_SIMPLE。",
            "Mortgage interest 只有在來源明確是 taxpayer main home 或 second home 時，才可放入 mortgage_interest_items。若來源顯示為 rental property 或 business property，不得放入 Schedule A mortgage_interest_items；若 property context 不明，simple_mortgage_status 應設為 UNKNOWN。",
            "Real estate tax 只有在明確屬於 personal-use property 且已實際 paid to taxing authority 時，才可設 personal_use_confirmed=true 與 actual_paid_to_taxing_authority_confirmed=true。若只是 Form 1098 escrow amount 或未確認實際支付，請設為 null 或 false。",
            "若發現 marketplace health insurance premium、Form 1095-A、Form 8962、LTC premium、noncash charity、charity carryover、investment interest、casualty/theft loss、seller-financed mortgage、non-1098 mortgage interest、multiple mortgages、mortgage limitation/workpaper 等，請在 special_case_flags 中標示相應 flag 為 true。"
        ]


    
    def get_example_json(self) -> Dict[str, Any]:
        return {
            "taxpayer_name": "Marcus Rivera",
            "taxpayer_ssn": "123-45-6789",
            "tax_year": 2025,
            "filing_status": "MFJ",
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
                "has_ltc_premium": False,
                "has_self_employed_health_insurance_overlap": False,
                "has_prior_year_medical_recovery": False,
                "sales_tax_amount_requires_calculation": False,
                "has_tax_refund_or_rebate_adjustment": False,
                "has_form_2555_or_4563_or_puerto_rico_exclusion": False,
                "has_other_tax_line_6": False,
                "has_multiple_mortgages": False,
                "mortgage_proceeds_not_all_qualified": False,
                "mortgage_limitation_required": False,
                "has_shared_mortgage": False,
                "has_non_1098_mortgage_interest": False,
                "has_non_1098_points": False,
                "has_seller_financed_mortgage": False,
                "has_form_8396_credit": False,
                "has_investment_interest": False,
                "has_noncash_charity": False,
                "has_charity_carryover": False,
                "has_charitable_agi_limitation": False,
                "has_casualty_or_theft_loss": False,
                "has_net_qualified_disaster_loss": False,
                "has_line_16_item": False,
                "has_unresolved_mfs_joint_expense_allocation": False
            }
        }