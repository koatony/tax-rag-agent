import os
from typing import Dict, Any, List
from processors.base_parser import BaseLLMParser


class Form1040IncomeLLMParser(BaseLLMParser):
    """
    Form 1040 Direct Income (Lines 1-6) 真實 LLM 提取解析器
    讀取原始文字/憑證內容並呼叫 Gemini API 進行數據提取。
    """

    def get_schema_path(self) -> str:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.abspath(
            os.path.join(
                current_dir,
                "..",
                "..",
                "docs",
                "how_to_fill_forms_docs",
                "Form1040",
                "income_aggregator_schema.json",
            )
        )

    def get_form_name(self) -> str:
        return "Form 1040 Direct Income (Lines 1-6)"

    def get_custom_rules(self) -> List[str]:
        return [
            "請從上傳的 W-2 憑證中精確提取所有 W-2 納稅人姓名 (employee_name)、員工社會安全號碼 (employee_ssn, 取自 Box a, 例如 '555-12-3456')、雇主名稱 (employer_name)、Box 1 工資 (box_1_wages)、Box 2 聯邦扣繳 (box_2_federal_withholding) 以及稅務年度 (tax_year)。",
            "若沒有相關的 IRA、Pension 或 Social Security 憑證，請將其 gross_amount 與 taxable_amount 設為 0.00。",
            "若有多張 W-2 憑證，請分別作為 w2_items 陣列中的獨立物件輸出。",
        ]

    def get_example_json(self) -> Dict[str, Any]:
        return {
            "w2_items": [
                {
                    "employee_name": "Marcus Rivera",
                    "employee_ssn": "555-12-3456",
                    "employer_name": "The Pet Shop Inc.",
                    "box_1_wages": 46000.00,
                    "box_2_federal_withholding": 5200.00,
                    "tax_year": 2025,
                },
                {
                    "employee_name": "Elena Rivera",
                    "employee_ssn": "555-23-4567",
                    "employer_name": "Sacramento High School",
                    "box_1_wages": 54000.00,
                    "box_2_federal_withholding": 6100.00,
                    "tax_year": 2025,
                },
            ],
            "ira_distribution": {"gross_amount": 0.00, "taxable_amount": 0.00},
            "pension_annuity": {"gross_amount": 0.00, "taxable_amount": 0.00},
            "social_security": {"gross_amount": 0.00, "taxable_amount": 0.00},
        }
