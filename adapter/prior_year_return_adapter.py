import json
import os
import re
from typing import List, Optional, Union, Dict, Any

from langchain_core.messages import SystemMessage, HumanMessage
from llm_wrappers import GeminiLLM, OllamaLLM

# 定義事實的型別別名與狀態 Literal 對應常數
VALID_STATUSES = {"found", "ambiguous", "conflicting", "not_applicable"}
VALID_VALUE_TYPES = {"string", "float", "boolean"}
VALID_REVIEW_REASONS = {
    "金額衝突",
    "同一 fact 多筆且無法判斷",
    "只能靠上下文猜測",
    "歸屬或 activity scope 不明",
    "文件只有總額，但需要拆分",
    "欄位名稱模糊或模型信心不足"
}

# 取得註冊表 JSON 路徑
REGISTRY_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "prior_year_fact_registry.json")
)

def load_fact_registry() -> Dict[str, Any]:
    """載入外部的標準事實類型註冊表 (prior_year_fact_registry.json)。"""
    if not os.path.exists(REGISTRY_PATH):
        # 降級預防手段
        return {}
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

class PriorYearReturnAdapter:
    """
    轉接器：負責讀取不同格式的上一年度報稅資料，呼叫 LLM 進行理解提取，
    並將結果標準化包裝為 PriorYearExtractionResult。
    """

    @classmethod
    def extract(
        cls, 
        filename: str, 
        content: str, 
        model_name: str = "gemini-2.5-pro",
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        將上一年度報稅原始文字，轉換為標準的 PriorYearExtractionResult。
        
        Args:
            filename: 原始檔案名稱 (用於 trace)
            content: 原始檔案文字或 OCR 內容
            model_name: 要使用的 LLM 模型名稱 (預設為 gemini-2.5-pro)
            api_key: 可選的 Gemini API 金鑰
            
        Returns:
            Dict[str, Any]: 符合 PriorYearExtractionResult 的字典結構。
        """
        if not content or not content.strip():
            return {
                "source_filename": filename,
                "detected_tax_year": None,
                "extraction_status": "failed",
                "facts": [],
                "document_needs_review": True,
                "document_review_reasons": ["檔案內容為空或無法讀取"]
            }

        # 1. 載入標準註冊表
        registry = load_fact_registry()
        registry_str = json.dumps(registry, ensure_ascii=False, indent=2)

        # 2. 決定 LLM 類型與初始化
        llm_provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
        is_ollama = False
        if model_name and "gemini" in model_name.lower():
            is_ollama = False
        elif model_name and ":" in model_name:
            is_ollama = True
        else:
            is_ollama = (llm_provider == "ollama")

        if is_ollama:
            llm = OllamaLLM(model_name=model_name, temperature=0.0, timeout=600.0)
        else:
            api_key_to_use = api_key or os.environ.get("GEMINI_API_KEY")
            if not api_key_to_use:
                # 降級或拋錯
                raise ValueError("環境變數 GEMINI_API_KEY 未設定，且未傳入 api_key")
            llm = GeminiLLM(model_name=model_name, api_key=api_key_to_use, temperature=0.0)

        # 3. 構造系統提示詞 (System Prompt)
        system_prompt = f"""你是一位專業的美國稅務數據提取專家。
你的任務是從提供的上一年度 (Prior Year) 報稅資料或 Summary 文件內容中，提取出所有明確且具下游稅務價值的原子事實 (Facts)。

【標準 Fact Type 註冊清單 (Registry)】
所有的 fact_type 必須從以下清單中選擇。不可任意創造不存在的 key：
{registry_str}

【提取與判斷責任限制 (必須嚴格遵守)】
1. 判斷文件是否屬於 prior-year tax return 或 summary。如果不是，請將 extraction_status 設為 "failed" 並在原因中說明。
2. 只要有任何一筆 fact 判定需要 review（即 needs_review 為 true），或在資料不明確、矛盾、缺少重要修飾條件 (qualifier) 時，必須將 needs_review 設為 true，且 review_reason 必須限定為以下其中一項，絕不可使用其他自創字眼：
   - "金額衝突"
   - "同一 fact 多筆且無法判斷"
   - "只能靠上下文猜測"
   - "歸屬或 activity scope 不明"
   - "文件只有總額，但需要拆分"
   - "欄位名稱模糊或模型信心不足"
3. 如果 needs_review 為 false，則 review_reason 必須設為 null。
4. 禁止行為：
   - 不要輸出 source_filename，由系統程式直接帶入。
   - 不直接決定 Form 或 Schedule line。
   - 不重新計算完整稅額。
   - 不根據 User Story 預期答案捏造資料。
   - 不把缺少的值當成 0。若文件中沒有該項， status 設為 "not_applicable" 或是不要提取該事實。
   - 不從金額大小推測 short-term 或 long-term 損失。
   - 不自行推論一筆支出依法是否可扣除。
   - 如果資料無法歸入 Registry 中既有的 standard key，但明確存在且具下游價值，請將 fact_type 標記為 "unknown_prior_year_fact"。

【輸出 JSON Schema】
你必須精確返回一個 JSON 對象，結構如下：
{{
  "detected_tax_year": 2023,
  "extraction_status": "completed", 
  "facts": [
    {{
      "fact_type": "long_term_capital_loss_carryover",
      "value": 990.0,
      "value_type": "float",
      "status": "found",
      "needs_review": false,
      "review_reason": null
    }}
  ],
  "document_needs_review": false,
  "document_review_reasons": []
}}
注意：extraction_status 只能是 "completed" 或 "completed_with_review" 或 "failed"。

直接返回乾淨的 JSON 字串，不要使用 markdown 區塊 (```json)，也不要包含任何說明文字。"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"以下是上一年度報稅文件的相關內容，請提取事實：\n\n{content}")
        ]

        try:
            if is_ollama:
                resp = llm.invoke(messages)
            else:
                resp = llm.invoke(messages, response_mime_type="application/json")
            
            raw_output = resp.content.strip()
        except Exception as e:
            return {
                "source_filename": filename,
                "detected_tax_year": None,
                "extraction_status": "failed",
                "facts": [],
                "document_needs_review": True,
                "document_review_reasons": [f"LLM 呼叫失敗: {str(e)}"],
                "debug_info": {
                    "system_prompt": system_prompt,
                    "user_prompt": f"以下是上一年度報稅文件的相關內容，請提取事實：\n\n{content}",
                    "raw_output": f"錯誤: {str(e)}"
                }
            }

        # 清理推理標籤
        clean_output = re.sub(r"<think>.*?</think>", "", raw_output, flags=re.DOTALL).strip()
        
        # 提取 JSON 區塊
        match = re.search(r"\{.*\}", clean_output, re.DOTALL)
        if match:
            clean_output = match.group(0)

        # 語法修復
        try:
            from json_repair import repair_json
            repaired_output = repair_json(clean_output)
            raw_result = json.loads(repaired_output)
        except Exception as e:
            return {
                "source_filename": filename,
                "detected_tax_year": None,
                "extraction_status": "failed",
                "facts": [],
                "document_needs_review": True,
                "document_review_reasons": [f"無法解析與修復 JSON 回應: {str(e)}", f"原始輸出: {raw_output}"],
                "debug_info": {
                    "system_prompt": system_prompt,
                    "user_prompt": f"以下是上一年度報稅文件的相關內容，請提取事實：\n\n{content}",
                    "raw_output": raw_output
                }
            }

        # 4. 封裝與後處理 (Deterministic Validation & Deduplication & Aggregation)
        # 4.1 確保外層基礎欄位
        detected_tax_year = raw_result.get("detected_tax_year")
        if detected_tax_year is not None:
            try:
                # 確保轉為 int 或 None
                if "." in str(detected_tax_year):
                    detected_tax_year = int(float(detected_tax_year))
                else:
                    detected_tax_year = int(detected_tax_year)
            except (ValueError, TypeError):
                detected_tax_year = None

        facts_list = raw_result.get("facts") or []
        processed_facts = []
        any_item_needs_review = False
        document_review_reasons = raw_result.get("document_review_reasons") or []
        if not isinstance(document_review_reasons, list):
            document_review_reasons = [str(document_review_reasons)]

        # 4.2 處裡並校驗事實項目
        for item in facts_list:
            if not isinstance(item, dict):
                continue
            
            fact_type = item.get("fact_type")
            value = item.get("value")
            value_type = item.get("value_type")
            status = item.get("status")
            needs_review = bool(item.get("needs_review", False))
            review_reason = item.get("review_reason")

            # 標準化檢驗
            # 若 fact_type 不在 registry 中，且不是預設的 unknown，則強制歸為 unknown_prior_year_fact
            if fact_type not in registry and fact_type != "unknown_prior_year_fact":
                fact_type = "unknown_prior_year_fact"

            # 檢驗 status
            if status not in VALID_STATUSES:
                status = "ambiguous"

            # 檢驗 value_type
            if value_type not in VALID_VALUE_TYPES:
                # 自動判斷型別
                if isinstance(value, bool):
                    value_type = "boolean"
                elif isinstance(value, (int, float)):
                    value_type = "float"
                else:
                    value_type = "string"

            # 值之型態清洗與標準化轉換
            if value is not None:
                if value_type == "float":
                    try:
                        # 處理貨幣與分節符號
                        clean_val = str(value).replace("$", "").replace(",", "").strip()
                        value = float(clean_val)
                    except (ValueError, TypeError):
                        needs_review = True
                        review_reason = "金額衝突" if not review_reason else review_reason
                elif value_type == "boolean":
                    if str(value).lower() in ("true", "1", "yes"):
                        value = True
                    elif str(value).lower() in ("false", "0", "no"):
                        value = False
                    else:
                        value = bool(value)
                else:
                    value = str(value)

            # 檢驗 review_reason 是否為標準值，避免 LLM 自創字眼
            if needs_review:
                if review_reason not in VALID_REVIEW_REASONS:
                    review_reason = "欄位名稱模糊或模型信心不足"
            else:
                review_reason = None

            # 只要有一個 item 需要 review，全域就是需要 review
            if needs_review:
                any_item_needs_review = True

            processed_facts.append({
                "fact_type": fact_type,
                "value": value,
                "value_type": value_type,
                "status": status,
                "needs_review": needs_review,
                "review_reason": review_reason
            })

        # 4.3 決定全域的 document_needs_review 與 extraction_status
        document_needs_review = bool(raw_result.get("document_needs_review", False))
        if any_item_needs_review:
            document_needs_review = True

        extraction_status = raw_result.get("extraction_status")
        if extraction_status not in ("completed", "completed_with_review", "failed"):
            extraction_status = "completed"

        if document_needs_review and extraction_status == "completed":
            extraction_status = "completed_with_review"


        return {
            "source_filename": filename,
            "detected_tax_year": detected_tax_year,
            "extraction_status": extraction_status,
            "facts": processed_facts,
            "document_needs_review": document_needs_review,
            "document_review_reasons": document_review_reasons,
            "debug_info": {
                "system_prompt": system_prompt,
                "user_prompt": f"以下是上一年度報稅文件的相關內容，請提取事實：\n\n{content}",
                "raw_output": raw_output
            }
        }
