from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
from form1040.models.income_aggregator_model import (
    DirectIncomeInputV1,
    DirectIncomeItemV1,
    W2ItemV1,
)


class IncomeAggregatorDirectIncomeParser:
    """
    Income Aggregator Direct Income 解析器與轉譯器
    將 LLM 或外層傳入之 Dict／Data 解析為結構化的 DirectIncomeInputV1 DTO
    """

    @classmethod
    def extract_and_parse(
        cls,
        doc_ctx_str: str,
        model_name: str = "gemini-2.5-pro"
    ) -> Tuple[DirectIncomeInputV1, str, str]:
        """
        一步到位：先呼叫 LLM 進行數據提取，接著自動整理成強型別的 DTO 回傳。
        """
        from .form_1040_income import Form1040IncomeLLMParser

        # 1. 呼叫底層 LLM 提取資料
        parser = Form1040IncomeLLMParser(model_name=model_name)
        raw_dict, prompt, raw_response = parser.parse(doc_ctx_str)

        # 2. 自動進行型態轉譯與整理
        dto = cls.parse_dict(raw_dict)

        return dto, prompt, raw_response

    @staticmethod
    def parse_dict(data: Any) -> DirectIncomeInputV1:
        if isinstance(data, DirectIncomeInputV1):
            return data
        if not data or not isinstance(data, dict):
            return DirectIncomeInputV1()

        # 1. Parse W-2 明細項目 (由 LLM 產出的 raw dict 統一轉換為 W2ItemV1 DTO 物件)
        raw_w2_items = data.get("w2_items") or []
        parsed_w2_items: List[W2ItemV1] = []
        for w2 in raw_w2_items:
            if isinstance(w2, dict):
                box1 = w2.get("box_1_wages")
                box2 = w2.get("box_2_federal_withholding")
                parsed_w2_items.append(
                    W2ItemV1(
                        employee_name=w2.get("employee_name"),
                        employer_name=w2.get("employer_name"),
                        tax_year=w2.get("tax_year"),
                        box_1_wages=Decimal(str(box1)) if box1 is not None else Decimal("0"),
                        box_2_federal_withholding=Decimal(str(box2)) if box2 is not None else None,
                        source_document_id=w2.get("source_document_id"),
                        status=w2.get("status", "COMPLETE"),
                    )
                )

        # 2. Parse 隨選直接收入項目 (IRA, Pension, Social Security)
        # 由於這三個項目的結構與欄位完全相同，因此使用統一的輔助函式進行 dict 到 DTO 物件的解析與轉換
        def _parse_item(key: str) -> Optional[DirectIncomeItemV1]:
            """
            解析特定的直接收入項目 (例如 'ira_distribution', 'pension_annuity', 'social_security')。
            
            從輸入的 raw dict 中提取以下欄位：
              - gross_amount: 總額 (轉換為 Decimal，預設 "0")
              - taxable_amount: 應稅金額 (轉換為 Decimal，預設 "0")
              - status: 提取狀態 (字串，預設 "EXPLICIT_VALUE")
            最後包裝成結構化的 DirectIncomeItemV1 DTO 物件回傳。
            """
            item_raw = data.get(key)
            if item_raw is None:
                return None
            if isinstance(item_raw, dict):
                gross = item_raw.get("gross_amount", "0")
                taxable = item_raw.get("taxable_amount", "0")
                return DirectIncomeItemV1(
                    gross_amount=Decimal(str(gross)),
                    taxable_amount=Decimal(str(taxable)),
                    status=item_raw.get("status", "EXPLICIT_VALUE"),
                )
            return None

        return DirectIncomeInputV1(
            w2_items=parsed_w2_items,
            ira_distribution=_parse_item("ira_distribution"),
            pension_annuity=_parse_item("pension_annuity"),
            social_security=_parse_item("social_security"),
        )
