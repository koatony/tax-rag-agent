import json
import os
import re
from typing import List, Optional, Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage
from llm_wrappers import GeminiLLM, OllamaLLM

# ── 合法常數 ──────────────────────────────────────────────────────────────────
VALID_STATUSES = {"found", "ambiguous", "conflicting"}
VALID_VALUE_TYPES = {"float", "string"}
VALID_REVIEW_REASONS = {
    "金額衝突",
    "同一 fact 多筆且無法判斷",
    "只能靠上下文猜測",
    "歸屬或 activity scope 不明",
    "文件只有總額，但需要拆分",
    "欄位名稱模糊或模型信心不足",
}

# ── Registry 路徑 ─────────────────────────────────────────────────────────────
REGISTRY_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "rental_income_and_expense_fact_registry.json")
)


def load_rental_fact_registry() -> Dict[str, Any]:
    """載入外部的標準事實類型註冊表 (rental_income_and_expense_fact_registry.json)。"""
    if not os.path.exists(REGISTRY_PATH):
        return {}
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class RentalIncomeAndExpenseAdapter:
    """
    轉接器：負責讀取單份出租物件文件原始文字，
    呼叫 LLM 進行理解提取，並將結果標準化包裝為 RentalExtractionResult。

    每次呼叫 extract() 只處理一份文件。
    source_filename 由呼叫方在 LLM 回傳後加入，不要求 LLM 輸出。
    """

    @classmethod
    def extract(
        cls,
        filename: str,
        content: str,
        model_name: str = "gemini-2.5-pro",
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        將原始文字轉換為標準的 RentalExtractionResult。

        Args:
            filename: 原始檔案名稱 (用於 trace，不傳給 LLM)
            content:  原始出租物件文件文字
            model_name: LLM 模型名稱 (預設 gemini-2.5-pro)
            api_key:  可選的 Gemini API 金鑰

        Returns:
            RentalExtractionResult 字典：
            {
                "source_filename": str,
                "facts": list[RentalFact],
                "document_needs_review": bool,
                "debug_info": { ... }
            }
        """
        # ── 空白文件快速失敗 ───────────────────────────────────────────────
        if not content or not content.strip():
            return {
                "source_filename": filename,
                "facts": [],
                "document_needs_review": True,
                "debug_info": {
                    "system_prompt": "N/A",
                    "user_prompt": "N/A",
                    "raw_output": "檔案內容為空或無法讀取",
                },
            }

        # ── 1. 載入 Fact Registry ─────────────────────────────────────────
        registry = load_rental_fact_registry()
        registry_str = json.dumps(registry, ensure_ascii=False, indent=2)

        # ── 2. 決定 LLM 類型並初始化 ─────────────────────────────────────
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

        # ── 3. 構造 System Prompt ─────────────────────────────────────────
        system_prompt = f"""你是一位專業的美國 Schedule E 出租物業事實提取專家。
你的任務是從提供的出租物件文件內容中，提取完成 Schedule E 申報所需的原子事實。

【標準 Fact Type Registry】
所有 fact_type 必須從以下清單選擇，不可自行創造 key：
{registry_str}

【提取與處理規則】
1. 僅抽取文件中明確存在的資料，不得根據測試案例預期答案補值。
2. 不要決定 Schedule E 行號；行號映射屬於 Mapper 責任。
3. 任何無法歸入 Registry 中既有 standard key 但明確與出租活動相關之事實，標記為 `unknown_rental_fact`。
4. 不要輸出 source_filename；系統程式會直接帶入。
5. needs_review=true 時，review_reason 只能使用以下其中一項：
   - "金額衝突"
   - "同一 fact 多筆且無法判斷"
   - "只能靠上下文猜測"
   - "歸屬或 activity scope 不明"
   - "文件只有總額，但需要拆分"
   - "欄位名稱模糊或模型信心不足"
6. needs_review=false 時，review_reason 必須為 null。
7. 只有文件明確顯示該收入或費用與出租不動產活動有關時，才可輸出 rental fact。若文件顯示房產地址與納稅人居住地址相同，或明確指向 Schedule A／個人住宅用途，不得輸出 rental fact，也不得僅因文件包含房貸利息、房貸保險費或房產稅，就推測其屬於出租活動。

【輸出 JSON Schema】
{{
  "facts": [
    {{
      "fact_type": "rental_income",
      "value": 12000.0,
      "value_type": "float",
      "status": "found",
      "needs_review": false,
      "review_reason": null
    }}
  ]
}}

直接返回乾淨的 JSON 字串，不要使用 markdown code block，也不要包含說明文字。"""

        user_prompt = f"以下是文件內容：\n{content}"

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        # ── 4. 呼叫 LLM ───────────────────────────────────────────────────
        try:
            if is_ollama:
                resp = llm.invoke(messages)
            else:
                resp = llm.invoke(messages, response_mime_type="application/json")
            raw_output = resp.content.strip()
        except Exception as e:
            return {
                "source_filename": filename,
                "facts": [],
                "document_needs_review": True,
                "debug_info": {
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "raw_output": f"LLM 呼叫失敗: {str(e)}",
                },
            }

        # ── 5. 清理推理標籤並提取 JSON ───────────────────────────────────
        clean_output = re.sub(
            r"<think>.*?</think>", "", raw_output, flags=re.DOTALL
        ).strip()
        match = re.search(r"\{.*\}", clean_output, re.DOTALL)
        if match:
            clean_output = match.group(0)

        # ── 6. JSON 修復與解析 ─────────────────────────────────────────────
        try:
            from json_repair import repair_json

            repaired_output = repair_json(clean_output)
            raw_result = json.loads(repaired_output)
        except Exception as e:
            return {
                "source_filename": filename,
                "facts": [],
                "document_needs_review": True,
                "debug_info": {
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "raw_output": f"無法解析 JSON: {str(e)}\n原始: {raw_output}",
                },
            }

        # ── 7. 後處理：校驗與清洗每筆 Fact ───────────────────────────────
        facts_list = raw_result.get("facts") or []
        processed_facts: List[Dict[str, Any]] = []
        any_needs_review = False

        for item in facts_list:
            if not isinstance(item, dict):
                continue

            fact_type = item.get("fact_type")
            value = item.get("value")
            value_type = item.get("value_type") or "float"
            status = item.get("status")
            needs_review = bool(item.get("needs_review", False))
            review_reason = item.get("review_reason")

            # fact_type 標準化：不在 registry 且非 unknown，歸入 unknown_rental_fact
            if fact_type not in registry and fact_type != "unknown_rental_fact":
                fact_type = "unknown_rental_fact"

            # status 校驗
            if status not in VALID_STATUSES:
                status = "ambiguous"

            # value_type 校驗
            if value_type not in VALID_VALUE_TYPES:
                value_type = "float"

            # 值型態轉換與清洗
            if value is not None:
                if value_type == "float" or (isinstance(value, (int, float)) and fact_type != "unknown_rental_fact"):
                    try:
                        clean_val = (
                            str(value).replace("$", "").replace(",", "").strip()
                        )
                        value = float(clean_val)
                        value_type = "float"
                    except (ValueError, TypeError):
                        needs_review = True
                        review_reason = (
                            "金額衝突" if not review_reason else review_reason
                        )
                else:
                    value = str(value)
                    value_type = "string"

            # review_reason 標準化
            if needs_review:
                if review_reason not in VALID_REVIEW_REASONS:
                    review_reason = "欄位名稱模糊或模型信心不足"
                any_needs_review = True
            else:
                review_reason = None

            processed_facts.append(
                {
                    "fact_type": fact_type,
                    "value": value,
                    "value_type": value_type,
                    "status": status,
                    "needs_review": needs_review,
                    "review_reason": review_reason,
                }
            )

        # ── 8. 衍生 document_needs_review ────────────────────────────────
        document_needs_review = any_needs_review

        return {
            "source_filename": filename,
            "facts": processed_facts,
            "document_needs_review": document_needs_review,
            "debug_info": {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "raw_output": raw_output,
            },
        }
