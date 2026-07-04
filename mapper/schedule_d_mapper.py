import json
import os
import re
from typing import Dict, Any, List, Optional

from langchain_core.messages import SystemMessage, HumanMessage
from llm_wrappers import GeminiLLM, OllamaLLM

class ScheduleDMapper:
    """
    Mapper: 負責接收來自各資料源的事實 (Facts)，根據報稅年度 (tax_year) 對齊映射至 Schedule D 表單的實際行號上。
    """

    def __init__(self, tax_year: int):
        self.tax_year = tax_year

    def map(
        self, 
        mapper_input: Dict[str, Any], 
        model_name: str = "gemini-2.5-pro",
        api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        執行對應年度的 Schedule D 欄位行號對齊。
        
        Args:
            mapper_input: 包含 facts 的字典，結構如：
              {
                "tax_year": int,
                "prior_year_facts": list[PriorYearFact],
                "brokerage_facts": list[BrokerageFact],
                "form_8949_facts": list[Form8949Fact]
              }
            model_name: 要使用的 LLM 模型名稱 (預設為 gemini-2.5-pro)
            api_key: 可選的 Gemini API 金鑰
            
        Returns:
            Dict[str, Any]: 包含對齊後的 Mapping items 以及 debug_info。
              {
                "items": list[ScheduleDMappingItem],
                "debug_info": {
                  "system_prompt": str,
                  "user_prompt": str,
                  "raw_output": str
                }
              }
        """
        # 1. 整理輸入事實
        prior_year_facts = mapper_input.get("prior_year_facts") or []
        brokerage_facts = mapper_input.get("brokerage_facts") or []
        form_8949_facts = mapper_input.get("form_8949_facts") or []

        facts_payload = {
            "prior_year_facts": prior_year_facts,
            "brokerage_facts": brokerage_facts,
            "form_8949_facts": form_8949_facts
        }
        facts_payload_str = json.dumps(facts_payload, ensure_ascii=False, indent=2)

        # 2. 載入對應年份的對照規則說明
        # 我們將常見的 Schedule D 行號規則整理為指引，注入至 Prompt 中
        line_guidelines = f"""【IRS Schedule D (Form 1040) 行號定義參考 - 適用申報年度：{self.tax_year}】
- `line_1a` (Short-term transactions, Box A): Totals for all short-term transactions reported on Form 1099-B for which basis was reported to the IRS and for which you have no adjustments (Form 8949 Part I with Box A checked and no adjustments).
- `line_1b` (Short-term transactions, Form 8949 Box A): Totals for all short-term transactions reported on Form(s) 8949 with Box A checked (basis reported to the IRS).
- `line_2` (Short-term transactions, Form 8949 Box B): Totals for all short-term transactions reported on Form(s) 8949 with Box B checked (basis not reported to the IRS).
- `line_3` (Short-term transactions, Form 8949 Box C): Totals for all short-term transactions reported on Form(s) 8949 with Box C checked (not reported on Form 1099-B).
- `line_4` (Short-term gain/loss from other forms): Short-term gain from Form 6252 and short-term gain or loss from Forms 4684, 6781, and 8824.
- `line_5` (Short-term gain/loss from partnerships/S-corps/trusts): Net short-term gain or loss from partnerships, S corporations, estates, and trusts from Schedule(s) K-1.
- `line_6` (Short-term capital loss carryover): Short-term capital loss carryover from prior years.
- `line_7` (Net short-term capital gain or loss): Combine lines 1a through 6.
- `line_8a` (Long-term transactions, Box D): Totals for all long-term transactions reported on Form 1099-B for which basis was reported to the IRS and for which you have no adjustments (Form 8949 Part II with Box D checked and no adjustments).
- `line_8b` (Long-term transactions, Form 8949 Box D): Totals for all long-term transactions reported on Form(s) 8949 with Box D checked (basis reported to the IRS).
- `line_9` (Long-term transactions, Form 8949 Box E): Totals for all long-term transactions reported on Form(s) 8949 with Box E checked (basis not reported to the IRS).
- `line_10` (Long-term transactions, Form 8949 Box F): Totals for all long-term transactions reported on Form(s) 8949 with Box F checked (not reported on Form 1099-B).
- `line_11` (Long-term gain/loss from other forms): Gain from Form 4797, Part I; long-term gain from Forms 2439 and 6252; and long-term gain or loss from Forms 4684, 6781, and 8824.
- `line_12` (Long-term gain/loss from partnerships/S-corps/trusts): Net long-term gain or loss from partnerships, S corporations, estates, and trusts from Schedule(s) K-1.
- `line_13` (Capital gain distributions): Capital gain distributions.
- `line_14` (Long-term capital loss carryover): Long-term capital loss carryover from prior years.
- `line_15` (Net long-term capital gain or loss): Combine lines 8a through 14.
- `line_16` (Net capital gain or loss): Combine lines 7 and 15.
"""

        # 3. 決定 LLM 類型與初始化
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
                raise ValueError("環境變數 GEMINI_API_KEY 未設定，且未傳入 api_key")
            llm = GeminiLLM(model_name=model_name, api_key=api_key_to_use, temperature=0.0)

        # 4. 構造系統提示詞 (System Prompt)
        system_prompt = f"""你是一位專業的美國稅務表單映射專家。
你的任務是讀取各個資料源提取出的 Facts 事實清單，並依據指定的報稅年度 ({self.tax_year}) 與 IRS Schedule D 欄位與行號定義，將適用的 Facts 映射對齊至 IRS Schedule D 的實際行號上。

{line_guidelines}

【映射限制與規範】
1. 能夠明確對齊至上述 Schedule D 行號的事實映射至 `items`。如果該事實與 Schedule D 有關但無法明確判定映射行號（例如 `capital_loss_carryover` 沒有區分 short-term 或 long-term 結轉，屬於「歸屬或 activity scope 不明」或「文件只有總額，但需要拆分」），請將其放入 `unmapped_items`，並將 `needs_review` 設為 true 且寫明合法 `review_reason`。如果某項事實依法不屬於 Schedule D，請直接忽略，不要進行映射。
2. 輸出中的 needs_review 與 review_reason 必須與來源 Facts 保持同步；此外，若你在映射時發現資料不明確、矛盾或對照關係模糊，也必須強制將 needs_review 設為 true。
3. 嚴格限定： needs_review 為 true 時的 review_reason 必須是以下其中一項，絕不可自創：
   - "金額衝突"
   - "同一 fact 多筆且無法判斷"
   - "只能靠上下文猜測"
   - "歸屬或 activity scope 不明"
   - "文件只有總額，但需要拆分"
   - "欄位名稱模糊或模型信心不足"
4. 對齊結果中的 source_category 必須等於輸入的 facts 分類鍵名（如 "prior_year_facts", "brokerage_facts", "form_8949_facts"）。
5. 對齊結果中的 source_fact_type 必須等於該筆事實原始的 fact_type。
6. 對齊結果中的 source_filename 必須等於該 fact 來源的 source_filename 值。

【輸出 JSON Schema】
你必須精確返回一個 JSON 對象，結構如下：
{{
  "items": [
    {{
      "target_line": "line_14",
      "value": 990.0,
      "value_type": "float",
      "source_category": "prior_year_facts",
      "source_fact_type": "long_term_capital_loss_carryover",
      "source_filename": "Rivera_2023.pdf",
      "needs_review": false,
      "review_reason": null
    }}
  ],
  "unmapped_items": [
    {{
      "value": 3000.0,
      "value_type": "float",
      "source_category": "prior_year_facts",
      "source_fact_type": "capital_loss_carryover",
      "source_filename": "Rivera_2023.pdf",
      "needs_review": true,
      "review_reason": "歸屬或 activity scope 不明"
    }}
  ]
}}

直接返回乾淨的 JSON 字串，不要使用 markdown 區塊 (```json)，也不要包含任何說明文字。"""

        user_prompt = f"以下是提取出的事實清單，請進行對齊映射：\n\n{facts_payload_str}"

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

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
                    "raw_output": f"LLM 呼叫異常: {str(e)}"
                }
            }

        # 清理推理區塊
        clean_output = re.sub(r"<think>.*?</think>", "", raw_output, flags=re.DOTALL).strip()
        
        # 提取 JSON
        match = re.search(r"\{.*\}", clean_output, re.DOTALL)
        if match:
            clean_output = match.group(0)

        # 語法修復與解析
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
                    "raw_output": f"無法解析 JSON: {str(e)}\n原始回傳: {raw_output}"
                }
            }

        # 後處理校驗
        items_list = raw_result.get("items") or []
        unmapped_items_list = raw_result.get("unmapped_items") or []
        processed_items = []
        processed_unmapped = []
        
        for item in items_list:
            if not isinstance(item, dict):
                continue
            
            target_line = item.get("target_line")
            value = item.get("value")
            value_type = item.get("value_type") or "float"
            source_category = item.get("source_category")
            source_fact_type = item.get("source_fact_type")
            source_filename = item.get("source_filename")

            # 嘗試在輸入事實中進行動態匹配，以自動校正或填補事實來源資訊
            matched_fact = None
            matched_category = None
            if value is not None:
                try:
                    target_val = float(str(value).replace("$", "").replace(",", "").strip())
                except (ValueError, TypeError):
                    target_val = None

                if target_val is not None:
                    # 比對 prior_year_facts
                    for fact in prior_year_facts:
                        f_val = fact.get("value")
                        try:
                            f_val_float = float(str(f_val).replace("$", "").replace(",", "").strip())
                        except (ValueError, TypeError):
                            f_val_float = None

                        if f_val_float is not None and abs(f_val_float - target_val) < 0.01:
                            matched_fact = fact
                            matched_category = "prior_year_facts"
                            break

                    # 比對 brokerage_facts
                    if not matched_fact:
                        for fact in brokerage_facts:
                            f_val = fact.get("value")
                            try:
                                f_val_float = float(str(f_val).replace("$", "").replace(",", "").strip())
                            except (ValueError, TypeError):
                                f_val_float = None

                            if f_val_float is not None and abs(f_val_float - target_val) < 0.01:
                                matched_fact = fact
                                matched_category = "brokerage_facts"
                                break

                    # 比對 form_8949_facts
                    if not matched_fact:
                        for fact in form_8949_facts:
                            f_val = fact.get("value")
                            try:
                                f_val_float = float(str(f_val).replace("$", "").replace(",", "").strip())
                            except (ValueError, TypeError):
                                f_val_float = None

                            if f_val_float is not None and abs(f_val_float - target_val) < 0.01:
                                matched_fact = fact
                                matched_category = "form_8949_facts"
                                break

            needs_review = bool(item.get("needs_review", False))
            review_reason = item.get("review_reason")

            if matched_fact and matched_category:
                source_category = matched_category
                source_fact_type = matched_fact.get("fact_type")
                source_filename = matched_fact.get("source_filename")
                if matched_fact.get("needs_review", False):
                    needs_review = True
                    review_reason = matched_fact.get("review_reason") or review_reason

            # 若仍無法解析則採取安全後備值
            if not source_category:
                source_category = "prior_year_facts"
            if not source_fact_type:
                source_fact_type = ""
            if not source_filename:
                source_filename = ""

            # 確保 target_line 格式為小寫且移除空格
            if target_line:
                target_line = str(target_line).strip().lower().replace(" ", "_")

            # 確保值轉換
            if value is not None:
                if value_type == "float":
                    try:
                        clean_val = str(value).replace("$", "").replace(",", "").strip()
                        value = float(clean_val)
                    except (ValueError, TypeError):
                        value = 0.0
                        needs_review = True
                        review_reason = "金額衝突"
                elif value_type == "boolean":
                    if str(value).lower() in ("true", "1", "yes"):
                        value = True
                    elif str(value).lower() in ("false", "0", "no"):
                        value = False
                    else:
                        value = bool(value)
                else:
                    value = str(value)

            # 檢驗 review_reason
            if needs_review:
                valid_reasons = {
                    "金額衝突",
                    "同一 fact 多筆且無法判斷",
                    "只能靠上下文猜測",
                    "歸屬或 activity scope 不明",
                    "文件只有總額，但需要拆分",
                    "欄位名稱模糊或模型信心不足"
                }
                if review_reason not in valid_reasons:
                    review_reason = "欄位名稱模糊或模型信心不足"
            else:
                review_reason = None

            processed_items.append({
                "target_line": target_line,
                "value": value,
                "value_type": value_type,
                "source_category": source_category,
                "source_fact_type": source_fact_type,
                "source_filename": source_filename,
                "needs_review": needs_review,
                "review_reason": review_reason
            })

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
            matched_fact = None
            matched_category = None
            if value is not None:
                try:
                    target_val = float(str(value).replace("$", "").replace(",", "").strip())
                except (ValueError, TypeError):
                    target_val = None

                if target_val is not None:
                    # 比對 prior_year_facts
                    for fact in prior_year_facts:
                        f_val = fact.get("value")
                        try:
                            f_val_float = float(str(f_val).replace("$", "").replace(",", "").strip())
                        except (ValueError, TypeError):
                            f_val_float = None

                        if f_val_float is not None and abs(f_val_float - target_val) < 0.01:
                            matched_fact = fact
                            matched_category = "prior_year_facts"
                            break

                    # 比對 brokerage_facts
                    if not matched_fact:
                        for fact in brokerage_facts:
                            f_val = fact.get("value")
                            try:
                                f_val_float = float(str(f_val).replace("$", "").replace(",", "").strip())
                            except (ValueError, TypeError):
                                f_val_float = None

                            if f_val_float is not None and abs(f_val_float - target_val) < 0.01:
                                matched_fact = fact
                                matched_category = "brokerage_facts"
                                break

                    # 比對 form_8949_facts
                    if not matched_fact:
                        for fact in form_8949_facts:
                            f_val = fact.get("value")
                            try:
                                f_val_float = float(str(f_val).replace("$", "").replace(",", "").strip())
                            except (ValueError, TypeError):
                                f_val_float = None

                            if f_val_float is not None and abs(f_val_float - target_val) < 0.01:
                                matched_fact = fact
                                matched_category = "form_8949_facts"
                                break

            needs_review = bool(item.get("needs_review", False))
            review_reason = item.get("review_reason")

            if matched_fact and matched_category:
                source_category = matched_category
                source_fact_type = matched_fact.get("fact_type")
                source_filename = matched_fact.get("source_filename")
                if matched_fact.get("needs_review", False):
                    needs_review = True
                    review_reason = matched_fact.get("review_reason") or review_reason

            # 若仍無法解析則採取安全後備值
            if not source_category:
                source_category = "prior_year_facts"
            if not source_fact_type:
                source_fact_type = ""
            if not source_filename:
                source_filename = ""

            # 確保值轉換
            if value is not None:
                if value_type == "float":
                    try:
                        clean_val = str(value).replace("$", "").replace(",", "").strip()
                        value = float(clean_val)
                    except (ValueError, TypeError):
                        value = 0.0
                        needs_review = True
                        review_reason = "金額衝突"
                elif value_type == "boolean":
                    if str(value).lower() in ("true", "1", "yes"):
                        value = True
                    elif str(value).lower() in ("false", "0", "no"):
                        value = False
                    else:
                        value = bool(value)
                else:
                    value = str(value)

            # 檢驗 review_reason
            if needs_review:
                valid_reasons = {
                    "金額衝突",
                    "同一 fact 多筆且無法判斷",
                    "只能靠上下文猜測",
                    "歸屬或 activity scope 不明",
                    "文件只有總額，但需要拆分",
                    "欄位名稱模糊或模型信心不足"
                }
                if review_reason not in valid_reasons:
                    review_reason = "欄位名稱模糊或模型信心不足"
            else:
                if not review_reason:
                    review_reason = None

            processed_unmapped.append({
                "value": value,
                "value_type": value_type,
                "source_category": source_category,
                "source_fact_type": source_fact_type,
                "source_filename": source_filename,
                "needs_review": needs_review,
                "review_reason": review_reason
            })

        return {
            "items": processed_items,
            "unmapped_items": processed_unmapped,
            "debug_info": {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "raw_output": raw_output
            }
        }
