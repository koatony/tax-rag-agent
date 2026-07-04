import json
import os
import re
from typing import Dict, Any, List, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from llm_wrappers import GeminiLLM, OllamaLLM

# ── 合法常數 ──────────────────────────────────────────────────────────────────
VALID_REVIEW_REASONS = {
    "金額衝突",
    "同一 fact 多筆且無法判斷",
    "只能靠上下文猜測",
    "歸屬或 activity scope 不明",
    "文件只有總額，但需要拆分",
    "欄位名稱模糊或模型信心不足",
}


class ScheduleEMapper:
    """
    Mapper: 負責接收 RentalIncomeAndExpenseAdapter 提取出的出租收入與費用 facts，
    並透過 LLM 將可使用的 facts 映射到 Schedule E 對應欄位。
    """

    def __init__(self, tax_year: int = 2024):
        self.tax_year = tax_year

    def map(
        self,
        mapper_input: Dict[str, Any],
        model_name: str = "gemini-2.5-pro",
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        執行 Schedule E 出租物業收支映射。

        Args:
            mapper_input: {
                "documents": list[RentalExtractionResult]
            }
            model_name: LLM 模型名稱
            api_key:    可選的 Gemini API 金鑰

        Returns:
            ScheduleEMappingResult 字典：
            {
                "items": list[ScheduleEMappingItem],
                "debug_info": { "system_prompt", "user_prompt", "raw_output" }
            }
        """
        documents: List[Dict[str, Any]] = mapper_input.get("documents") or []

        # 整理輸入 Facts Payload 給 LLM，加上 source_filename，並放在 rental_facts 鍵下
        rental_facts = []
        for doc in documents:
            filename = doc.get("source_filename") or ""
            doc_facts = doc.get("facts") or []
            for fact in doc_facts:
                fact_copy = dict(fact)
                fact_copy["source_filename"] = filename
                rental_facts.append(fact_copy)

        facts_payload = {
            "rental_facts": rental_facts
        }
        facts_payload_str = json.dumps(facts_payload, ensure_ascii=False, indent=2)

        # ── 決定 LLM 類型與初始化 ───────────────────────────────────────
        llm_provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
        is_ollama = False
        if model_name and "gemini" in model_name.lower():
            is_ollama = False
        elif model_name and ":" in model_name:
            is_ollama = True
        else:
            is_ollama = llm_provider == "ollama"

        if is_ollama:
            llm = OllamaLLM(model_name=model_name, temperature=0.0, timeout=600.0)
        else:
            api_key_to_use = api_key or os.environ.get("GEMINI_API_KEY")
            if not api_key_to_use:
                raise ValueError("環境變數 GEMINI_API_KEY 未設定，且未傳入 api_key")
            llm = GeminiLLM(
                model_name=model_name, api_key=api_key_to_use, temperature=0.0
            )

        # ── System Prompt ────────────────────────────────────────────────
        system_prompt = """你是一位專業的美國稅務表單映射專家。
你的任務是讀取提取出的的出租 Facts，並依據 IRS Schedule E 欄位定義，將適用的項目映射至 Schedule E 的對應行號 (target_line)。

【IRS Schedule E 行號定義參考】
- `line_3` (Rents received)：出租房屋所收取的全部租金收入。
- `line_4` (Royalties received)：出租房產收到的權利金收入。
- `line_5` (Advertising)：出租活動的廣告費用。
- `line_6` (Auto and travel)：出租活動相關的汽車與差旅費用。
- `line_7` (Cleaning and maintenance)：出租物業的清潔與維護費用。
- `line_8` (Commissions)：出租物業相關的佣金支出。
- `line_9` (Insurance)：與出租物業相關的所有保險費用。
- `line_10` (Legal and other professional fees)：出租物業相關的法律與其他專業諮詢費用。
- `line_11` (Management fees)：出租物業的物業管理費用。
- `line_12` (Mortgage interest paid to banks, etc.)：與出租物業相關，且明確支付給銀行、金融機構或由 Form 1098 證明的房貸利息。
- `line_13` (Other interest)：與出租活動相關，但不屬於支付給銀行等機構的其他利息（如個人/私人貸款利息等）。
- `line_14` (Repairs)：出租物業的日常修繕費用。
- `line_15` (Supplies)：出租活動耗用的物資或用品費用。
- `line_16` (Taxes)：與出租物業相關的房產稅或其他不動產稅。
- `line_17` (Utilities)：出租物業的水電、瓦斯、垃圾費等公用事業費用。
- `line_18` (Depreciation expense or depletion)：出租物業的折舊或折耗費用。
- `line_19` (Other)：與出租活動相關，且沒有其他明確欄位可歸類的必要費用。若已有 Advertising、Cleaning and maintenance、Repairs、Utilities 等明確類別，應優先使用該明確欄位，不得映射至 line_19。

【映射與處理規則】
1. 每一筆 fact 保留為獨立項目，不要在此處進行任何金額加總。
2. 僅映射事實類型 (fact_type) 有明確對應到上述 Schedule E 行號的 Fact。
3. `target_form` 必須固定為 "schedule_e"。
4. `source_category` 必須等於該筆 fact 原始所屬的分類鍵名，在此固定為 "rental_facts"。
5. `source_fact_type` 必須保留輸入 fact 原始的 `fact_type` 值。
6. `source_filename` 必須保留輸入 fact 的 `source_filename`。若輸入資料中未提供，則設為 ""。
7. 輸入 fact 的 `needs_review` 為 true 時，輸出映射項目之 `needs_review` 也必須設為 true，並保留其 `review_reason`。
8. 輸出金額 `value` 必須與輸入 fact 的 `value` 一致，不得修改金額。
9. needs_review=true 時的 review_reason 只能使用以下其中一項：
   - "金額衝突"
   - "同一 fact 多筆且無法判斷"
   - "只能靠上下文猜測"
   - "歸屬或 activity scope 不明"
   - "文件只有總額，但需要拆分"
   - "欄位名稱模糊或模型信心不足"
10. needs_review=false 時，review_reason 必須為 null。

【輸出 JSON Schema】
{
  "items": [
    {
      "target_form": "schedule_e",
      "target_line": "line_3",
      "value": 16650.0,
      "value_type": "float",
      "source_category": "rental_facts",
      "source_fact_type": "rental_income",
      "source_filename": "rental_statement.pdf",
      "needs_review": false,
      "review_reason": null
    }
  ]
}

直接返回乾淨的 JSON 字串，不要使用 markdown code block，也不要包含說明文字。"""

        user_prompt = f"以下是提取出的事實清單，請進行 Schedule E 映射：\n\n{facts_payload_str}"

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        # ── 呼叫 LLM ─────────────────────────────────────────────────────
        try:
            if is_ollama:
                resp = llm.invoke(messages)
            else:
                resp = llm.invoke(messages, response_mime_type="application/json")
            raw_output = resp.content.strip()
        except Exception as e:
            return {
                "items": [],
                "debug_info": {
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "raw_output": f"LLM 呼叫異常: {str(e)}",
                },
            }

        # ── 清理推理區塊與提取 JSON ──────────────────────────────────────
        clean_output = re.sub(
            r"<think>.*?</think>", "", raw_output, flags=re.DOTALL
        ).strip()
        match = re.search(r"\{.*\}", clean_output, re.DOTALL)
        if match:
            clean_output = match.group(0)

        # ── JSON 修復與解析 ───────────────────────────────────────────────
        try:
            from json_repair import repair_json

            repaired_output = repair_json(clean_output)
            raw_result = json.loads(repaired_output)
        except Exception as e:
            return {
                "items": [],
                "debug_info": {
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "raw_output": f"無法解析 JSON: {str(e)}\n原始回傳: {raw_output}",
                },
            }

        # ── 後處理校驗 ─────────────────────────────────────────────────────
        items_list = raw_result.get("items") or []
        processed_items: List[Dict[str, Any]] = []

        for item in items_list:
            if not isinstance(item, dict):
                continue

            target_form = str(item.get("target_form") or "schedule_e").strip().lower()
            if target_form != "schedule_e":
                continue
            target_line = str(item.get("target_line") or "").strip().lower()
            value = item.get("value")
            source_category = item.get("source_category") or "rental_facts"
            source_fact_type = item.get("source_fact_type") or ""
            source_filename = item.get("source_filename") or ""
            needs_review = bool(item.get("needs_review", False))
            review_reason = item.get("review_reason")

            # 嘗試在輸入事實中進行動態匹配，以自動校正或填補檔案與事實來源資訊
            matched_fact = None
            if value is not None:
                try:
                    target_val = float(str(value).replace("$", "").replace(",", "").strip())
                except (ValueError, TypeError):
                    target_val = None

                if target_val is not None:
                    for fact in rental_facts:
                        f_val = fact.get("value")
                        try:
                            f_val_float = float(str(f_val).replace("$", "").replace(",", "").strip())
                        except (ValueError, TypeError):
                            f_val_float = None

                        if f_val_float is not None and abs(f_val_float - target_val) < 0.01:
                            if source_fact_type and source_fact_type != fact.get("fact_type"):
                                continue
                            matched_fact = fact
                            break

            if matched_fact:
                source_fact_type = matched_fact.get("fact_type") or ""
                source_filename = matched_fact.get("source_filename") or ""
                # 如果匹配到輸入 fact，且輸入 fact 標記了 needs_review，必須傳播 review 狀態
                if matched_fact.get("needs_review", False):
                    needs_review = True
                    review_reason = matched_fact.get("review_reason") or review_reason

            # 確保值為 float
            if value is not None:
                try:
                    clean_val = str(value).replace("$", "").replace(",", "").strip()
                    value = float(clean_val)
                except (ValueError, TypeError):
                    # 若無法轉為 float 則排除該項目
                    continue
            else:
                continue

            # review_reason 標準化
            if needs_review:
                if review_reason not in VALID_REVIEW_REASONS:
                    review_reason = "欄位名稱模糊或模型信心不足"
            else:
                review_reason = None

            processed_items.append(
                {
                    "target_form": target_form,
                    "target_line": target_line,
                    "value": value,
                    "value_type": "float",
                    "source_category": source_category,
                    "source_fact_type": source_fact_type,
                    "source_filename": source_filename,
                    "needs_review": needs_review,
                    "review_reason": review_reason,
                }
            )

        return {
            "items": processed_items,
            "debug_info": {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "raw_output": raw_output,
            },
        }
