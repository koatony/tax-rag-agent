import os
from typing import Dict, Any, List
from processors.base_parser import BaseLLMParser


class Form4562LLMParser(BaseLLMParser):
    def get_schema_path(self) -> str:
        # 回傳Schema JSON檔案的絕對路徑
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.abspath(
            os.path.join(current_dir, "..", "..", "docs", "how_to_fill_forms_docs", "Form4562", "form_4562_schema.json")
        )

    def get_form_name(self) -> str:
        return "Form 4562 (Depreciation and Amortization)"

    # 給LLM看的
    def get_custom_rules(self) -> List[str]:
        return [
            "Part III MACRS 資產（macrs_gds_items / macrs_ads_items）的 depreciation_deduction 欄位，只能填入文件中已明確計算完成的當年度折舊扣除額最終數字，不得自行依 recovery_period、convention、method 反推計算。",
            "若文件中提到某項可折舊財產的資訊（例如出租房產的 building_value／purchase price 與 date_placed_in_service），但找不到文件已明確算好的『當年度折舊扣除額』數字，絕對不可以直接略過、忽略、或當作沒看到這筆資產；也不可以自己動手計算折舊金額。正確做法：將 special_case_flags.has_unquantified_prior_year_depreciation 標示為 true，讓系統阻斷並提示人工複核，不得讓 Line 17 或任何折舊欄位靜默維持在 0。",
            "只要文件針對某項具體資產（有 classification／基礎金額／回收期間等明細）提供了『已算好的當年度折舊扣除額』數字，一律將該筆填入 macrs_gds_items 或 macrs_ads_items（依 classification 對應正確的 line_code，例如 Residential rental property 對應 '19i'），不論該資產的 date_placed_in_service 是否早於 tax_year。不要只因為投入使用日期是往年，就把有明細的資產金額改填到 line_17_macrs_prior_years；line_17_macrs_prior_years 只用於文件『沒有』提供個別資產明細、只給一個涵蓋多項前期資產的『單一合計總額』時才使用。",
            "line_code 請務必對齊官方表單代碼：Part III Section B (GDS) 為 '19a'-'19j'（對應 3-year 至 Nonresidential real property），Section C (ADS) 為 '20a'-'20e'（對應 Class life 至 50-year），不得自創代碼。",
            "遇到 Part V 列名財產（自小客車、其他特定車輛、飛機、娛樂用財產）、車輛使用問卷（Section B/C）、或 Part VI 攤銷等情況，請在 special_case_flags 中相應標示為 true，不要自行計算金額或假設為 0。",
            "Line 1（Section 179 最高費用化金額）與 Line 3（門檻成本）請直接採用文件中明確標示的年度金額，不要自行依通膨調整推算。",
            "taxpayer_name 與 taxpayer_ssn 為納稅人身分欄位，即使本表主要內容是折舊資料，也請務必掃描所有隨附文件（包含 W-2、1099 等其他表單）找出納稅人姓名與社會安全號碼，不得因為該資訊出現在非折舊相關文件中就略過不填。",
            "下方範例 JSON 中的 taxpayer_ssn 數值僅為格式示範，不是真實資料，絕對不可以照抄範例中的數字。若掃描所有隨附文件後仍找不到任何與『XXX-XX-XXXX』格式相符的社會安全號碼，taxpayer_ssn 必須填為空字串 \"\"，不得虛構、猜測、或沿用範例中的佔位數字。",
        ]

    # 給LLM看得
    def get_example_json(self) -> Dict[str, Any]:
        return {
            "taxpayer_name": "Marcus & Elena Rivera",
            "taxpayer_ssn": "XXX-XX-XXXX",
            "business_activity_name": "Rental Real Estate",
            "tax_year": 2025,
            "line_1_section_179_max_amount": 0.00,
            "line_2_section_179_property_cost": 0.00,
            "line_3_section_179_threshold_cost": 0.00,
            "section_179_property_items": [],
            "line_7_listed_property_section_179_cost": None,
            "line_10_carryover_disallowed_deduction": 0.00,
            "line_11_business_income_limitation": 0.00,
            "line_14_special_depreciation_allowance": 0.00,
            "line_15_section_168f1_election": 0.00,
            "line_16_other_depreciation": 0.00,
            "line_17_macrs_prior_years": 0.00,
            "line_18_general_asset_account_election": False,
            "macrs_gds_items": [
                {
                    "line_code": "19i",
                    "classification": "Residential rental property",
                    "month_year_placed_in_service": "7/2023",
                    "depreciation_basis": 220000.00,
                    "recovery_period": "27.5 yrs.",
                    "convention": "MM",
                    "method": "S/L",
                    "depreciation_deduction": 8000.00
                }
            ],
            "macrs_ads_items": [],
            "amortization_costs_263a_interest": None,
            "amortization_costs_263a_other": None,
            "special_case_flags": {
                "has_listed_property": False,
                "has_vehicle_business_use_questions": False,
                "has_employer_vehicle_exemption_questions": False,
                "has_amortization": False,
                "has_263a_capitalization_calculation_needed": False,
                "has_unquantified_prior_year_depreciation": False
            }
        }
