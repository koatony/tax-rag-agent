import os
from typing import Dict, Any, List
from processors.base_parser import BaseLLMParser


class Schedule1LLMParser(BaseLLMParser):
    def get_schema_path(self) -> str:
        # 回傳Schema JSON檔案的絕對路徑
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.abspath(
            os.path.join(current_dir, "..", "..", "docs", "how_to_fill_forms_docs", "schedule_1", "schedule_1_schema.json")
        )

    def get_form_name(self) -> str:
        return "Schedule 1 (Form 1040)"

    # 給LLM看的
    def get_custom_rules(self) -> List[str]:
        return [
            "Line 3 (Business income) 與 Line 5 (Rental real estate, royalties, etc.) 請優先引用已完成的 Schedule C Line 31 / Schedule E Line 41 結果，不要自行重新計算。",
            "Line 8a、8d、8s 為表單上以括號呈現之減項欄位，請將 amount 以正數填入，並將 is_negative_adjustment 標示為 true。",
            "遇到 Schedule F、Form 4797/4684、Schedule SE、Form 2106、Form 3903、Form 8889、Form 8853、Archer MSA、Form 2555、數位資產所得、非合格遞延補償、服刑期間工資、ABLE 帳戶分配、Medicaid waiver 調整、Section 951(a)/951A(a) inclusion、Section 461(l) 超額營業虧損調整、Schedule K-1 Section 67(e) 超額扣除等情況，請在 special_case_flags 中相應標示為 true，不要自行計算金額。",
            "other_income_items 與 adjustment_items 的 line_code 請務必對齊官方表單代碼（例如 '8a'、'8z'、'11'、'24a'、'24z'），不得自創代碼。",
            "Line 19a (Alimony paid)、Line 20 (IRA deduction)、Line 21 (Student loan interest deduction) 這三筆金額，請一律透過 adjustment_items 陣列表達（line_code 分別為 '19a'、'20'、'21'），比照 Line 11/16/17/18 的做法，不要另外用其他欄位名稱重複填寫；Line 19b（受領人 SSN）、Line 19c（原協議日期）、Line 20 的 MFS 分居勾選則維持獨立欄位（line_19b_recipient_ssn、line_19c_original_agreement_date、line_20_mfs_lived_apart_flag）。",
            "IRA deduction（Line 20）等『扣除額』欄位，只能填入文件中已明確計算或聲明為『可扣除金額 (deductible amount)』的數字。若原始憑證只提供『存入金額 (contribution amount)』（例如 Traditional IRA 存款收據），但沒有明確指出該金額已通過扣除限制（如 active participant／MAGI phase-out）的判定，不得將存入金額直接當作可扣除金額填入；此時該欄位應留 0 或 null，並可在 adjustment_items 的 description 中註記『存入金額 $X，扣除額尚待確認』以供人工複核，不得自行假設全額可扣除。",
            "下方範例 JSON 中的 taxpayer_ssn 數值僅為格式示範，不是真實資料，絕對不可以照抄範例中的數字。若掃描所有隨附文件後仍找不到任何與『XXX-XX-XXXX』格式相符的社會安全號碼，taxpayer_ssn 必須填為空字串 \"\"，不得虛構、猜測、或沿用範例中的佔位數字。",
        ]

    # 給LLM看得
    def get_example_json(self) -> Dict[str, Any]:
        return {
            "taxpayer_name": "Marcus Rivera",
            "taxpayer_ssn": "XXX-XX-XXXX",
            "tax_year": 2025,
            "form_1099k_error_or_personal_loss_amount": 0.00,
            "line_1_state_local_tax_refund": 800.00,
            "line_2a_alimony_received": 0.00,
            "line_2b_original_agreement_date": None,
            "schedule_c_line_31": 15000.00,
            "line_4_other_gains_or_losses": 0.00,
            "schedule_e_line_41": 0.00,
            "line_6_farm_income": 0.00,
            "line_7_unemployment_compensation": 0.00,
            "line_7_repaid_overpayment_flag": False,
            "line_7_repaid_overpayment_amount": None,
            "other_income_items": [
                {
                    "line_code": "8b",
                    "description": None,
                    "amount": 500.00,
                    "is_negative_adjustment": False
                }
            ],
            "line_19b_recipient_ssn": None,
            "line_19c_original_agreement_date": None,
            "line_20_mfs_lived_apart_flag": False,
            "adjustment_items": [
                {
                    "line_code": "20",
                    "description": None,
                    "amount": 6000.00
                }
            ],
            "special_case_flags": {
                "has_schedule_f_income": False,
                "has_form_4797_or_4684": False,
                "has_schedule_se_deduction": False,
                "has_form_2106": False,
                "has_form_3903": False,
                "has_form_8889": False,
                "has_form_8853": False,
                "has_archer_msa_deduction": False,
                "has_form_2555": False,
                "has_digital_assets_income": False,
                "has_nonqualified_deferred_comp": False,
                "has_incarcerated_wages": False,
                "has_able_account_distribution": False,
                "has_medicaid_waiver_adjustment": False,
                "has_section_951_inclusion": False,
                "has_excess_business_loss_adjustment": False,
                "has_k1_section_67e_deduction": False
            }
        }
