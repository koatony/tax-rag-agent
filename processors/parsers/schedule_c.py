import os 
from typing import Dict, Any, List
from processors.base_parser import BaseLLMParser


class ScheduleCLLMParser(BaseLLMParser):
    def get_schema_path(self) -> str:
        # 回傳Schema JSON檔案的絕對路徑
        # os.path.abspath 會換成絕對路徑
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.abspath(
            os.path.join(current_dir, "..", "..", "docs", "how_to_fill_forms_docs", "schedule_c", "schedule_c_schema.json")
        )

    def get_form_name(self) -> str:
        return "Schedule C (Form 1040)"

    def get_custom_rules(self) -> List[str]:
        return [
            "絕對不要自行計算任何毛利或總費用公式，保持原始金額。例如不要對餐飲費折半，直接提取收據或損益表中的原始總額。",
            "絕對不要根據任何商務用途比例、個人使用比例或出差天數比例進行折算，必須提取文件中最原始的總金額。所有比例折算與公式計算均由下游系統自動處理。"
        ]

    def get_example_json(self) -> Dict[str, Any]:
        return {
            "proprietor_name": "Marcus Rivera",
            "ssn": "123-45-6789",
            "principal_business": "Retail sales",
            "line_1_gross_receipts": 12000.00,
            "line_8_advertising": 150.00,
            "accounting_method": "Cash",
            "started_acquired_2025": False,
            "other_misc_expenses_list": []
        }
