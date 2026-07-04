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


class Form1040WagesMapper:
    """
    Mapper: 接收一或多份 W2ExtractionResult，
    依據指定報稅年度的 2024 Form 1040 Line 1a 規則，
    將 w2_box_1_wages 映射為獨立的 Form1040MappedItem。

    加總責任由 aggregate_form_1040_line_1a() 函數承擔，
    Mapper 本身不執行加總。
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
        執行 Form 1040 Line 1a wages 映射。

        Args:
            mapper_input: {
                "tax_year": int,
                "w2_documents": list[W2ExtractionResult],
                "other_fact_categories": dict  (預留)
            }
            model_name: LLM 模型名稱
            api_key:    可選的 Gemini API 金鑰

        Returns:
            {
                "items": list[Form1040MappedItem],
                "debug_info": { "system_prompt", "user_prompt", "raw_output" }
            }
        """
        documents: List[Dict[str, Any]] = mapper_input.get("documents") or mapper_input.get("w2_documents") or []

        # 只送給 LLM 需要的欄位（排除 debug_info）
        clean_docs = []
        for doc in documents:
            clean_docs.append(
                {
                    "source_filename": doc.get("source_filename"),
                    "facts": doc.get("facts") or [],
                    "document_needs_review": doc.get("document_needs_review", False),
                }
            )

        facts_payload = {
            "tax_year": self.tax_year,
            "documents": clean_docs,
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
        system_prompt = f"""你是一位專業的美國稅務表單映射專家。
你的任務是讀取各資料來源提取出的 Facts，並依據 IRS Form 1040 欄位定義，將適用的事實映射至 IRS Form 1040 的對應行號 (target_line)。

【行號格式規範】
- `target_line` 必須為特定小寫底線格式，例如 `line_1a` (W-2 Wages), `line_2b` (Interest), `line_7` (Capital gain or loss), `line_8` (Other income), `line_25a` (Federal withholding) 等。
- 請精確映射至具體行號，不得使用大寫或非標準形式（例如 `Line 1a` 或 `1a` 均為錯誤，必須為 `line_1a`）。

【映射與處理規則】
1. 僅映射能明確對應至 IRS Form 1040 欄位行號的 Fact。其他無關或無法確定映射的事實，請放入 `unmapped_items`。
2. 每一筆可映射的 fact 必須保留為一筆獨立 mapped item，不要在 Mapper 內加總。
3. `taxpayer_name` 應嘗試取自該事實所屬資料的 employee name、taxpayer name 或納稅人姓名。若找不到，設為 null。
4. `source_category` 必須等於該筆 fact 原始所屬的分類鍵名（例如 w2_facts, prior_year_return_facts, rental_facts）。不得自行改名。
5. `source_fact_type` 必須保留輸入 fact 原始的 `fact_type` 值。
6. `source_filename` 必須取自對應輸入資料中的 `source_filename`。
7. 輸入 fact 的 needs_review=true 時，mapped item 也必須為 true，並保留原 review_reason。
8. 不要計算表單總額。總額由後續加總程序處理。
9. needs_review=false 時，review_reason 必須為 null。
10. needs_review=true 時的 review_reason 只能使用以下其中一項，絕不可自創：
    - "金額衝突"
    - "同一 fact 多筆且無法判斷"
    - "只能靠上下文猜測"
    - "歸屬或 activity scope 不明"
    - "文件只有總額，但需要拆分"
    - "欄位名稱模糊或模型信心不足"

【輸出 JSON Schema】
{{
  "items": [
    {{
      "target_form": "form_1040",
      "target_line": "line_1a",
      "value": 46000.0,
      "value_type": "float",
      "taxpayer_name": "Marcus Rivera",
      "source_category": "w2_facts",
      "source_fact_type": "w2_box_1_wages",
      "source_filename": "sample_1_marcus_w2.pdf",
      "needs_review": false,
      "review_reason": null
    }}
  ],
  "unmapped_items": [
    {{
      "value": 2000.0,
      "value_type": "float",
      "source_category": "w2_facts",
      "source_fact_type": "w2_box_12a_amount",
      "source_filename": "sample_1_marcus_w2.pdf",
      "needs_review": false,
      "review_reason": null
    }}
  ]
}}

直接返回乾淨的 JSON 字串，不要使用 markdown code block，也不要包含說明文字。"""

        user_prompt = (
            f"以下是提取出的事實清單，請進行 Form 1040 Line 1a 映射：\n\n{facts_payload_str}"
        )

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

        for item in items_list:
            if not isinstance(item, dict):
                continue

            target_form = str(item.get("target_form") or "form_1040").strip().lower()
            if target_form != "form_1040":
                continue
            target_line = str(item.get("target_line") or "line_1a").strip().lower()
            value = item.get("value")
            value_type = item.get("value_type") or "float"
            taxpayer_name = item.get("taxpayer_name")
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
                source_category = source_category or "w2_facts"
                source_fact_type = matched_fact.get("fact_type")
                source_filename = matched_doc.get("source_filename")
                if matched_fact.get("needs_review", False):
                    needs_review = True
                    review_reason = matched_fact.get("review_reason") or review_reason

            # 若仍無法解析則採取安全後備值
            if not source_category:
                source_category = "w2_facts"
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
            else:
                review_reason = None

            # taxpayer_name 型態保護
            if taxpayer_name is not None:
                taxpayer_name = str(taxpayer_name)

            processed_items.append(
                {
                    "target_form": target_form,
                    "target_line": target_line,
                    "value": value,
                    "value_type": "float",
                    "taxpayer_name": taxpayer_name,
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

            # 嘗試在輸入事實中進行動態匹配，以自動校正或填補事實來源資訊
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
                source_category = source_category or "w2_facts"
                source_fact_type = matched_fact.get("fact_type")
                source_filename = matched_doc.get("source_filename")
                if matched_fact.get("needs_review", False):
                    needs_review = True
                    review_reason = matched_fact.get("review_reason") or review_reason

            # 若仍無法解析則採取安全後備值
            if not source_category:
                source_category = "w2_facts"
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
            "debug_info": {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "raw_output": raw_output,
            },
        }


# ══════════════════════════════════════════════════════════════════════════════
# Rule-based Aggregator — 確定性加總函數
# ══════════════════════════════════════════════════════════════════════════════

def aggregate_form_1040_line_1a(
    mapped_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Rule-based 加總函數：對 Form1040WagesMapper 輸出的 mapped items 進行確定性加總。

    職責：
    1. 找出所有 target_form == "form_1040" 且 target_line == "line_1a" 的項目。
    2. 對 needs_review=False 的項目加總。
    3. 將 needs_review=True 的項目列入 excluded_review_items，不計入總額。
    4. 對同一 source_filename 出現多次的項目，標記為 review 並排除重複計算。
    5. 向上傳播 review 狀態，彙整所有 review_reasons。

    Args:
        mapped_items: list[Form1040MappedItem]

    Returns:
        Form1040LineResult:
        {
            "target_form": "form_1040",
            "target_line": "line_1a",
            "total_value": float,
            "value_type": "float",
            "calculation_status": "completed" | "completed_with_review",
            "source_items": list[Form1040MappedItem],
            "excluded_review_items": list[Form1040MappedItem],
            "needs_review": bool,
            "review_reasons": list[str],
        }
    """
    # ── Step 1: 過濾出 Line 1a 項目 ───────────────────────────────────────
    line_1a_items = [
        item
        for item in mapped_items
        if (
            str(item.get("target_form", "")).lower() == "form_1040"
            and str(item.get("target_line", "")).lower() == "line_1a"
        )
    ]

    # ── Step 2: 偵測重複 source_filename ─────────────────────────────────
    seen_filenames: Dict[str, int] = {}
    for item in line_1a_items:
        fname = item.get("source_filename") or ""
        seen_filenames[fname] = seen_filenames.get(fname, 0) + 1

    # ── Step 3: 分類每筆項目 ──────────────────────────────────────────────
    accepted_items: List[Dict[str, Any]] = []
    excluded_items: List[Dict[str, Any]] = []
    review_reasons_set: List[str] = []

    for item in line_1a_items:
        fname = item.get("source_filename") or ""
        is_dup = seen_filenames.get(fname, 0) > 1

        if is_dup:
            # 標記重複並排除
            flagged = dict(item)
            flagged["needs_review"] = True
            flagged["review_reason"] = "同一 fact 多筆且無法判斷"
            excluded_items.append(flagged)
            reason = "同一 fact 多筆且無法判斷"
            if reason not in review_reasons_set:
                review_reasons_set.append(reason)
        elif item.get("needs_review", False):
            excluded_items.append(item)
            reason = item.get("review_reason") or "欄位名稱模糊或模型信心不足"
            if reason not in review_reasons_set:
                review_reasons_set.append(reason)
        else:
            accepted_items.append(item)

    # ── Step 4: 加總 ──────────────────────────────────────────────────────
    total_value = 0.0
    for item in accepted_items:
        val = item.get("value")
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            total_value += float(val)

    # ── Step 5: 決定 calculation_status ──────────────────────────────────
    has_review = len(excluded_items) > 0
    calculation_status = "completed_with_review" if has_review else "completed"

    return {
        "target_form": "form_1040",
        "target_line": "line_1a",
        "total_value": total_value,
        "value_type": "float",
        "calculation_status": calculation_status,
        "source_items": accepted_items,
        "excluded_review_items": excluded_items,
        "needs_review": has_review,
        "review_reasons": review_reasons_set,
    }
