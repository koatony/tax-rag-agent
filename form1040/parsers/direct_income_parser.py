from decimal import Decimal
from typing import Dict, Any, List, Optional
from form1040.models.income_aggregator_model import (
    DirectIncomeInputV1,
    DirectIncomeItemV1,
    W2ItemV1,
)


class DirectIncomeParser:
    """
    Direct Income 解析器與轉譯器
    將 LLM 或外層傳入之 Dict／Data 解析為結構化的 DirectIncomeInputV1 DTO
    """

    @staticmethod
    def parse_dict(data: Dict[str, Any]) -> DirectIncomeInputV1:
        if not data:
            return DirectIncomeInputV1()

        # 1. Parse W-2 明細項目
        raw_w2_items = data.get("w2_items") or []
        parsed_w2_items: List[W2ItemV1] = []
        for w2 in raw_w2_items:
            if isinstance(w2, W2ItemV1):
                parsed_w2_items.append(w2)
            elif isinstance(w2, dict):
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
        def _parse_item(key: str) -> Optional[DirectIncomeItemV1]:
            item_raw = data.get(key)
            if item_raw is None:
                return None
            if isinstance(item_raw, DirectIncomeItemV1):
                return item_raw
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
