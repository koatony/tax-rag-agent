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


class ScheduleADeductionMapper:
    """
    Mapper: 接收一或多份 ItemizedDeductionExtractionResult，
    依據 IRS Schedule A 規則，將事實映射至 Schedule A 行號或排除。
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
        執行 Schedule A 列舉扣除額映射。

        Args:
            mapper_input: {
                "documents": list[ItemizedDeductionExtractionResult]
            }
            model_name: LLM 模型名稱
            api_key:    可選的 Gemini API 金鑰

        Returns:
            {
                "items": list[ScheduleAMappedItem],
                "unmapped_items": list[ScheduleAUnmappedItem],
                "needs_review": bool,
                "debug_info": { "system_prompt", "user_prompt", "raw_output" }
            }
        """
        documents: List[Dict[str, Any]] = mapper_input.get("documents") or []

        # 整理輸入 Facts Payload 給 LLM，加上 source_filename，並放在 itemized_deduction_facts 鍵下
        # 這使得 LLM 可以動態獲取該鍵名作為 source_category
        facts_list = []
        for doc in documents:
            filename = doc.get("source_filename") or ""
            doc_facts = doc.get("facts") or []
            for fact in doc_facts:
                fact_copy = dict(fact)
                fact_copy["source_filename"] = filename
                facts_list.append(fact_copy)

        facts_payload = {
            "itemized_deduction_facts": facts_list
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
你的任務是讀取各資料來源提取出的 Facts，並依據 IRS Schedule A 欄位與行號定義，將適用的扣除項目映射至 IRS Schedule A 的對應行號 (target_line)。

【IRS Schedule A 行號定義參考】
- `line_1` (Medical and dental expenses): Medical and dental expenses you paid for yourself, spouse, and dependents.
- `line_2` (AGI): Enter amount from Form 1040, line 11 (Adjusted Gross Income).
- `line_3` (AGI limit threshold): Multiply line 2 by 7.5% (0.075).
- `line_4` (Deductible medical expenses): Subtract line 3 from line 1.
- `line_5a` (State and local income taxes or general sales taxes): State and local income taxes or general sales taxes.
- `line_5b` (State and local real estate taxes): State and local real estate taxes you paid on property not used for business or rental (e.g. personal real estate taxes).
- `line_5c` (State and local personal property taxes): State and local personal property taxes.
- `line_5d` (Total state and local taxes): Sum of lines 5a through 5c.
- `line_5e` (SALT limitation): Smaller of line 5d or $10,000 ($5,000 if married filing separately).
- `line_6` (Other taxes): Other taxes not listed above, such as foreign income taxes.
- `line_7` (Total taxes paid): Sum of lines 5e and 6.
- `line_8a` (Home mortgage interest reported on Form 1098): Home mortgage interest and points reported to you on Form 1098.
- `line_8b` (Home mortgage interest not reported on Form 1098): Home mortgage interest not reported on Form 1098.
- `line_8c` (Points not reported on Form 1098): Points not reported on Form 1098.
- `line_8e` (Total mortgage interest): Sum of lines 8a through 8c.
- `line_9` (Investment interest): Investment interest expense.
- `line_10` (Total interest paid): Sum of lines 8e and 9.
- `line_11` (Gifts by cash or check): Charitable contributions made by cash or check.
- `line_12` (Other than by cash or check): Charitable contributions other than by cash or check (noncash contributions).
- `line_13` (Carryover from prior year): Charitable contribution carryover from prior years.
- `line_14` (Total charitable gifts): Sum of lines 11 through 13.
- `line_15` (Casualty and theft losses): Casualty or theft loss(es) from Form 4684.
- `line_16` (Other itemized deductions): Other miscellaneous itemized deductions.
- `line_17` (Total itemized deductions): Sum of lines 4, 7, 10, 14, 15, and 16.

【映射與處理規則】
1. 每一筆可映射 fact 保留為獨立 mapped item，不要在 Mapper 中加總。
2. 僅映射能明確對應至上述 Schedule A 行號的 Fact。
3. `target_form` 必須固定為 "schedule_a"。
4. source_category 必須等於該筆 fact 在輸入資料中所屬的分類鍵名（例如 itemized_deduction_facts）。不得自行改名或固定輸出特定值。
5. `source_fact_type` 必須保留輸入 fact 原始的 `fact_type` 值。
6. `source_filename` 必須取自對應輸入資料中的 `source_filename`。
7. 輸入 fact 的 needs_review=true 時，mapped item 也必須為 true，並保留原 review_reason。
8. 政治捐款（political_contribution）為依法不可扣除之項目。若發現政治捐款，必須放入 `unmapped_items`，且其 `needs_review` 設為 false，且 `review_reason` 設為 "political_contribution_non_deductible"。
9. 無法安全判定對應行號的其他 fact（例如資訊不足、欄位模糊等），請放入 `unmapped_items`，且其 `needs_review` 設為 true 並填寫合適的 review_reason。
10. 不要計算 Schedule A 總額。
11. needs_review=false 時，review_reason 必須為 null（除政治捐款特殊 review_reason 以外）。
12. needs_review=true 時的 review_reason 只能使用以下其中一項，絕不可自創：
    - "金額衝突"
    - "同一 fact 多筆且無法判斷"
    - "只能靠上下文猜測"
    - "歸屬或 activity scope 不明"
    - "文件只有總額，但需要拆分"
    - "欄位名稱模糊或模型信心不足"

【輸出 JSON Schema】
{
  "items": [
    {
      "target_form": "schedule_a",
      "target_line": "line_11",
      "value": 5400.0,
      "value_type": "float",
      "source_category": "itemized_deduction_facts",
      "source_fact_type": "charitable_cash_contribution",
      "source_filename": "church_donation_receipt.pdf",
      "needs_review": false,
      "review_reason": null
    }
  ],
  "unmapped_items": [
    {
      "value": 250.0,
      "value_type": "float",
      "source_category": "itemized_deduction_facts",
      "source_fact_type": "political_contribution",
      "source_filename": "political_contribution_receipt.pdf",
      "needs_review": false,
      "review_reason": "political_contribution_non_deductible"
    }
  ],
  "needs_review": false
}

直接返回乾淨的 JSON 字串，不要使用 markdown code block，也不要包含說明文字。"""

        user_prompt = f"以下是提取出的事實清單：\n\n{facts_payload_str}"

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
                "unmapped_items": [],
                "needs_review": True,
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
                "unmapped_items": [],
                "needs_review": True,
                "debug_info": {
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "raw_output": f"無法解析 JSON: {str(e)}\n原始回傳: {raw_output}",
                },
            }

        # ── 後處理校驗 ─────────────────────────────────────────────────────
        items_list = raw_result.get("items") or []
        unmapped_items_list = raw_result.get("unmapped_items") or []

        processed_items: List[Dict[str, Any]] = []
        processed_unmapped: List[Dict[str, Any]] = []
        any_needs_review = False

        # 1. 處理 mapped items
        for item in items_list:
            if not isinstance(item, dict):
                continue

            target_form = str(item.get("target_form") or "schedule_a").strip().lower()
            if target_form != "schedule_a":
                continue
            target_line = str(item.get("target_line") or "").strip().lower()
            value = item.get("value")
            value_type = item.get("value_type") or "float"
            source_category = item.get("source_category")
            source_fact_type = item.get("source_fact_type")
            source_filename = item.get("source_filename")

            # 嘗試在輸入事實中進行動態匹配，以自動校正或填補檔案與事實來源資訊
            matched_doc = None
            matched_fact = None
            if value is not None:
                try:
                    target_val = float(str(value).replace("$", "").replace(",", "").strip())
                except (ValueError, TypeError):
                    target_val = None

                if target_val is not None:
                    for doc in documents:
                        fname = doc.get("source_filename") or ""
                        if source_filename and source_filename != fname:
                            continue
                        for fact in doc.get("facts") or []:
                            f_val = fact.get("value")
                            try:
                                f_val_float = float(str(f_val).replace("$", "").replace(",", "").strip())
                            except (ValueError, TypeError):
                                f_val_float = None

                            if f_val_float is not None and abs(f_val_float - target_val) < 0.01:
                                matched_doc = doc
                                matched_fact = fact
                                break
                        if matched_fact:
                            break

            needs_review = bool(item.get("needs_review", False))
            review_reason = item.get("review_reason")

            if matched_doc and matched_fact:
                source_category = "itemized_deduction_facts"
                source_fact_type = matched_fact.get("fact_type")
                source_filename = matched_doc.get("source_filename")
                if matched_fact.get("needs_review", False):
                    needs_review = True
                    review_reason = matched_fact.get("review_reason") or review_reason

            # 若仍無法解析則採取安全後備值
            if not source_category:
                source_category = "itemized_deduction_facts"
            if not source_fact_type:
                source_fact_type = ""
            if not source_filename:
                source_filename = ""

            # 確保值為 float
            if value is not None:
                try:
                    clean_val = str(value).replace("$", "").replace(",", "").strip()
                    value = float(clean_val)
                except (ValueError, TypeError):
                    value = 0.0
                    needs_review = True
                    review_reason = "金額衝突"

            # review_reason 標準化
            if needs_review:
                if review_reason not in VALID_REVIEW_REASONS:
                    review_reason = "欄位名稱模糊或模型信心不足"
                any_needs_review = True
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

        # 2. 處理 unmapped items
        for item in unmapped_items_list:
            if not isinstance(item, dict):
                continue

            value = item.get("value")
            value_type = item.get("value_type") or "float"
            source_category = item.get("source_category")
            source_fact_type = item.get("source_fact_type")
            source_filename = item.get("source_filename")

            # 嘗試在輸入事實中進行動態匹配，以自動校正或填補檔案與事實來源資訊
            matched_doc = None
            matched_fact = None
            if value is not None:
                try:
                    target_val = float(str(value).replace("$", "").replace(",", "").strip())
                except (ValueError, TypeError):
                    target_val = None

                if target_val is not None:
                    for doc in documents:
                        fname = doc.get("source_filename") or ""
                        if source_filename and source_filename != fname:
                            continue
                        for fact in doc.get("facts") or []:
                            f_val = fact.get("value")
                            try:
                                f_val_float = float(str(f_val).replace("$", "").replace(",", "").strip())
                            except (ValueError, TypeError):
                                f_val_float = None

                            if f_val_float is not None and abs(f_val_float - target_val) < 0.01:
                                matched_doc = doc
                                matched_fact = fact
                                break
                        if matched_fact:
                            break

            needs_review = bool(item.get("needs_review", False))
            review_reason = item.get("review_reason")

            if matched_doc and matched_fact:
                source_category = "itemized_deduction_facts"
                source_fact_type = matched_fact.get("fact_type")
                source_filename = matched_doc.get("source_filename")
                if matched_fact.get("needs_review", False):
                    needs_review = True
                    review_reason = matched_fact.get("review_reason") or review_reason

            # 若仍無法解析則採取安全後備值
            if not source_category:
                source_category = "itemized_deduction_facts"
            if not source_fact_type:
                source_fact_type = ""
            if not source_filename:
                source_filename = ""

            # 確保值為 float
            if value is not None:
                try:
                    clean_val = str(value).replace("$", "").replace(",", "").strip()
                    value = float(clean_val)
                except (ValueError, TypeError):
                    value = 0.0
                    needs_review = True
                    review_reason = "金額衝突"

            # review_reason 標準化
            if needs_review:
                if review_reason not in VALID_REVIEW_REASONS:
                    review_reason = "欄位名稱模糊或模型信心不足"
                any_needs_review = True
            else:
                if not review_reason:
                    review_reason = None

            processed_unmapped.append(
                {
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
            "unmapped_items": processed_unmapped,
            "needs_review": any_needs_review,
            "debug_info": {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "raw_output": raw_output,
            },
        }
