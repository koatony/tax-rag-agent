import os 
from typing import Dict, Any, List
from processors.base_parser import BaseLLMParser

class ScheduleCLLMParser(BaseLLMParser):
    def get_schema_path(self) -> str:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.abspath(
            os.path.join(current_dir, "..", "..", "docs", "how_to_fill_forms_docs", "schedule_c", "schedule_c_schema.json")
        )

    def get_form_name(self) -> str:
        return "Schedule C (Form 1040)"

    def get_custom_rules(self) -> List[str]:
        return [
            "絕對不要自行計算任何毛利或總費用公式，保持原始金額。例如不要對餐飲費折半，直接提取收據或損益表中的原始總額。",
            "絕對不要根據任何商務用途比例、個人使用比例或出差天數比例進行折算，必須提取文件中最原始的總金額。所有比例折算與公式計算均由下游系統自動處理。",
            "提取 'other_expense_items'（其他營業費用）時，僅限包含符合 IRS 規定普通且必要之可扣除商業支出。絕對不可將個人生活支出、政府罰金與罰款 (fines/penalties)、政治捐款等不可扣除項目納入 'other_expense_items'；如發現有此類非營業或不可扣除支出，應予以排除且不可申報。",
            "對於以 '_from_module' 或 '_final' 結尾的欄位（如 line_4_cogs_from_module, line_9_car_truck_expenses_final, line_13_depreciation_from_form4562, line_30_home_office_from_module），僅在輸入文件中有明確標明該項計算完成之最終總額時才進行提取。絕對不要自己嘗試累加零散收據、計算存貨公式或估算金額；如果文件中沒有明確的最終總額，請直接填寫 null (None)。"
        ]

    def get_example_json(self) -> Dict[str, Any]:
        return {
            "proprietor_name": "Marcus Rivera",
            "taxpayer_ssn": "123-45-6789",
            "tax_year": 2025,
            "principal_business": "Retail sales",
            "principal_activity_code": "453910",
            "business_name": "Creature Comforts",
            "ein": "94-7654321",
            "business_address": "1450 Arden Way, Sacramento, CA 95815",
            "accounting_method": "CASH",
            "line_g_material_participation": True,
            "line_h_started_or_acquired": False,
            "line_i_payment_requiring_1099": False,
            "line_j_filed_required_1099": None,
            "income": {
                "line_1_gross_receipts": 12000.00,
                "line_2_returns_allowances": 0.00,
                "line_6_other_income": 0.00
            },
            "expenses": {
                "line_8_advertising": 150.00,
                "line_9_car_truck_expenses_final": None,
                "line_10_commissions_fees": 0.00,
                "line_11_contract_labor": 0.00,
                "line_12_depletion": 0.00,
                "line_14_employee_benefit_programs": 0.00,
                "line_15_insurance": 0.00,
                "line_16a_mortgage_interest": 0.00,
                "line_16b_other_interest": 0.00,
                "line_17_legal_professional": 0.00,
                "line_18_office_expense": 0.00,
                "line_19_pension_profit_sharing": 0.00,
                "line_20a_rent_machinery_equipment": 0.00,
                "line_20b_rent_other_property": 0.00,
                "line_21_repairs_maintenance": 0.00,
                "line_22_supplies": 0.00,
                "line_23_taxes_licenses": 0.00,
                "line_24a_travel_final": None,
                "meals_50_percent_source_amount": 0.00,
                "meals_100_percent_source_amount": 0.00,
                "entertainment_source_amount": 0.00,
                "line_25_utilities": 600.00,
                "line_26_wages_final": None,
                "line_13_depreciation_from_form4562": None,
                "line_30_home_office_from_module": None,
                "line_4_cogs_from_module": None
            },
            "other_expense_items": [
                {
                    "item_id": "exp_item_1",
                    "name": "Software Subscription",
                    "amount": 299.99,
                    "source_document_id": "doc_abc123",
                    "confidence": "HIGH"
                }
            ],
            "loss_at_risk_answer": None,
            "special_case_flags": {
                "has_inventory_or_cogs": False,
                "has_vehicle_expense_requiring_calculation": False,
                "has_depreciation_or_section179": False,
                "has_home_office": False,
                "has_mixed_travel": False,
                "has_uncertain_meals_or_entertainment": False,
                "has_employee_wages_or_payroll_credit": False,
                "has_owner_draw_in_expenses": False,
                "has_uncertain_expense_category": False,
                "has_rental_or_royalty_activity": False,
                "has_farm_activity": False,
                "has_business_asset_sale": False,
                "has_passive_activity_issue": False,
                "has_at_risk_limitation_issue": False,
                "has_qbi_request": False,
                "has_schedule_se_request": False
            }
        }
