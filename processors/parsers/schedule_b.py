import os 
from typing import Dict, Any, List
from processors.base_parser import BaseLLMParser


class ScheduleBLLMParser(BaseLLMParser):
    def get_schema_path(self) -> str:
        # 回傳Schema JSON檔案的絕對路徑
        # os.path.abspath 會換成絕對路徑
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.abspath(
            os.path.join(current_dir, "..", "..", "docs", "how_to_fill_forms_docs", "schedule_b", "schedule_b_schema.json")
        )

    def get_form_name(self) -> str:
        return "Schedule B (Form 1040)"

    # 給LLM看的
    def get_custom_rules(self) -> List[str]:
        return [
            "遇到 Nominee、Accrued Interest、OID、ABP 調整等，請在 special_case_flags 中相應標示。",
            "若 Form 1099-B 或 Form 8949 交易明細中含有 accrued market discount (或市場折價)，請將該筆交易原始的 proceeds, cost_basis, 與 accrued_market_discount 數值提取並寫入 market_discount_items 陣列中，且 special_case_flags.has_market_discount 需標示為 true。"
        ]

    # 給LLM看得
    def get_example_json(self) -> Dict[str, Any]:
        return {
    "taxpayer_name": "Marcus Rivera",
    "taxpayer_ssn": "123-45-6789",
    "tax_year": 2025,
    "interest_items": [
        {
            "statement_issuer_name": None,
            "source_document_type": "1099-INT",
            "source_box": "1",
            "payer_name": "Chase Bank",
            "payer_reported_amount": 150.00,
            "tax_character": "TAXABLE_INTEREST",
            "is_series_ee_or_i_interest": False
        }
    ],
    "dividend_items": [
        {
            "statement_issuer_name": None,
            "source_document_type": "1099-DIV",
            "payer_name": "Vanguard Services",
            "ordinary_dividends": 405.00,
            "qualified_dividends": 0.00,
            "exempt_interest_dividends": 0.00
        }
    ],
    "market_discount_items": [
        {
            "payer_name": "Chase Brokerage",
            "proceeds": 8000.00,
            "cost_basis": 7900.00,
            "accrued_market_discount": 200.00
        }
    ],
    "foreign_account_q1": False,
    "fbar_q2": False,
    "foreign_countries": [],
    "foreign_trust_q8": False,
    "special_case_flags": {
        "has_nominee_distribution": False,
        "has_accrued_interest": False,
        "has_oid": False,
        "has_abp_adjustment": False,
        "has_market_discount": True,
        "has_seller_financed_mortgage": False,
        "has_form_8814": False,
        "has_tax_exempt_bond_premium": False,
        "has_contingent_payment_debt": False
    }
}

