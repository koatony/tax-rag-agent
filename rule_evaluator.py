import os
import re
import json
import time
from typing import Dict, List, Any, Set
from langchain_core.messages import SystemMessage, HumanMessage
from llm_wrappers import GeminiLLM, OllamaLLM
from neo4j import GraphDatabase

EXTRACTION_SYSTEM_INSTRUCTION = """你是一位專業的美國稅務數據提取專家。
你的任務是從申報人基本資料（Taxpayer Profile）與已上傳檔案的 OCR 文字內容中，精準提取出規則引擎所需的「申報狀態」、「數值欄位與金額」以及「已上傳的文件/表單名稱」。

請將提取結果以 JSON 格式輸出。

【輸出 JSON 結構格式示意】（注意：fields 底下的 keys 與數值僅為示意，請根據輸入資料動態提取所有出現在文字中的相關稅務數據欄位，欄位多寡與名稱完全不固定）：
{
  "filing_status": "MFJ" | "Single" | "HOH" | "MFS" | "QW",
  "fields": {
    "1040.Line_1a": 0.0,
    "SchC.NetProfit": 0.0,
    "W2.RetirementPlanActive": true,
    "has_spouse_ssn": false
  },
  "docs": [
    "Form W-2",
    "Schedule C"
  ]
}

【提取規範】：
1. filing_status：必須對齊為 "MFJ" (Married Filing Jointly), "Single", "HOH" (Head of Household), "MFS" (Married Filing Separately), 或 "QW" (Qualifying Widow/er)。
2. fields：比對 OCR 文字中出現的金額與欄位，動態且精準地提取所有有提到的標準 IRS 欄位與數值（以標準的命名空間，例如 1040.Line_X, SchA.Line_Y, SchE.GrossRents 等）。常見的欄位包括但不限於：
   - W-2 wages 應提取為 "1040.Line_1a"
   - QuickBooks 中的 Net Income/Profit 應提取為 "SchC.NetProfit"
   - 房貸利息 1098 應提取為 "1098.Line_1"
   - 房地產稅 1098 應提取為 "1098.Line_10"
   - 傳統 IRA 退休帳戶供款金額應提取為 "Sch1.Line_20" 與 "IRA.TraditionalContribution"
   - "1040.AGI": 調整後總所得。如果文件中沒有寫明 AGI，則根據薪資、自營業淨利與租金淨收益累加估算所得總和。
   - "W2.RetirementPlanActive": 布林值，若報稅資料中任何一份 W-2 表單的 Box 13 "Retirement Plan" 有被勾選，則提取為 true；否則為 false。
   - 特別注意：如果資料中「有明確提到/出現」配偶的 SSN/ITIN，請在 fields 中將 "has_spouse_ssn" 設為 true；若有提到扶養人/合格申報人的 SSN，請將對應的 "has_qualifying_person_ssn" 或 "has_dependent_child_ssn" 設為 true。
   - 請根據輸入資料，動態擴增或調整 fields 中的 key-value 對，僅填入您有高度把握且文字中有明確提及的金額或布林。數值必須是純數字（float）或布林值（boolean）。
3. docs：列出所有已被確認上傳的表單與憑證名稱，請對齊標準名稱（例如 "Form W-2", "Form 1099-INT", "Form 1099-DIV", "Form 1098", "Schedule C", "Schedule E", "Schedule D" 等）。

請直接輸出 JSON 內容，不要包含任何說明或 markdown codeblock（````json`）。
"""

class TaxRuleEvaluator:
    def __init__(self, filing_status: str, extracted_fields: Dict[str, Any], uploaded_docs: Set[str]):
        self.context = {
            "filing_status": filing_status,
            "fields": extracted_fields,
            "docs": set(uploaded_docs)
        }
        
    def get_filing_status(self) -> str:
        return self.context["filing_status"]

    def get_value(self, field_name: str) -> Any:
        val = self.context["fields"].get(field_name, 0.0)
        if isinstance(val, str):
            try:
                return float(val.replace("$", "").replace(",", "").strip())
            except ValueError:
                if val.lower() == "true":
                    return True
                if val.lower() == "false":
                    return False
                return val
        return val

    def has_document(self, doc_name: str) -> bool:
        return doc_name in self.context["docs"]

    def has_form(self, form_name: str) -> bool:
        return form_name in self.context["docs"]

    def has_spouse_ssn(self) -> bool:
        return self.get_value("has_spouse_ssn") is True or self.get_value("has_spouse_ssn") == 1.0 or self.get_value("1040.Spouse_SSN") != 0.0

    def has_qualifying_person_ssn(self) -> bool:
        return self.get_value("has_qualifying_person_ssn") is True or self.get_value("has_qualifying_person_ssn") == 1.0

    def has_dependent_child_ssn(self) -> bool:
        return self.get_value("has_dependent_child_ssn") is True or self.get_value("has_dependent_child_ssn") == 1.0

    def evaluate(self, expr_str: str) -> bool:
        safe_env = {
            "get_filing_status": self.get_filing_status,
            "get_value": self.get_value,
            "has_document": self.has_document,
            "has_form": self.has_form,
            "has_spouse_ssn": self.has_spouse_ssn,
            "has_qualifying_person_ssn": self.has_qualifying_person_ssn,
            "has_dependent_child_ssn": self.has_dependent_child_ssn,
        }
        try:
            return eval(expr_str, {"__builtins__": None}, safe_env)
        except Exception as e:
            # Silence evaluation errors
            return False

    def validate_bundle(self, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        reports = []
        for rule in rules:
            # 1. Check if triggered
            if self.evaluate(rule["trigger_expr"]):
                # 2. Check if valid/compliant
                if not self.evaluate(rule["validate_expr"]):
                    reports.append({
                        "id": rule["id"],
                        "category": rule.get("category", ""),
                        "severity": rule["severity"],
                        "message": rule["message"],
                        "trigger_expr": rule["trigger_expr"],
                        "validate_expr": rule["validate_expr"]
                    })
        return reports


def _strip_think_tags(text: str) -> str:
    """移除 gemma4/qwen 等 thinking 模型輸出的 <think>...</think> 推理過程區塊"""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def extract_taxpayer_context(formatted_input: str, model_name: str, api_key: str) -> Dict[str, Any]:
    """呼叫 LLM 提取結構化的報稅資料上下文"""
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
        llm = GeminiLLM(model_name=model_name, api_key=api_key, temperature=0.0)

    messages = [
        SystemMessage(content=EXTRACTION_SYSTEM_INSTRUCTION),
        HumanMessage(content=f"請分析以下申報資料並提取欄位金額與文件列表：\n\n{formatted_input}")
    ]

    try:
        if not is_ollama:
            resp = llm.invoke(messages, response_mime_type="application/json")
        else:
            resp = llm.invoke(messages)
        
        content = resp.content.strip()
        # 移除 thinking 模型的推理標籤（如 gemma4, qwen3）
        content = _strip_think_tags(content)
        match = re.search(r"\{.*\}", content, re.DOTALL)
        from json_repair import repair_json
        repaired_content = repair_json(content)
        data = json.loads(repaired_content)
        return {
            "filing_status": data.get("filing_status", "Single"),
            "fields": data.get("fields", {}),
            "docs": data.get("docs", [])
        }
    except Exception as e:
        print(f"[rule_evaluator] 警告: 結構化上下文提取失敗: {e}")
        return {
            "filing_status": "Single",
            "fields": {},
            "docs": []
        }


def evaluate_compliance_rules(context: Dict[str, Any], return_debug: bool = False) -> Any:
    """連線至 Stage3 Neo4j (7688) 並執行確定性規則判定。若抓不到或發生異常則直接回傳空。"""
    neo4j_uri = os.environ.get("NEO4J_STAGE3_URI")
    neo4j_user = os.environ.get("NEO4J_STAGE3_USER")
    neo4j_password = os.environ.get("NEO4J_STAGE3_PASSWORD")
    neo4j_database = os.environ.get("NEO4J_STAGE3_DATABASE", "neo4j")

    if not neo4j_uri:
        print("[rule_evaluator] 警告: 未設定 NEO4J_STAGE3_URI，跳過確定性驗證。")
        if return_debug:
            return [], {"neo4j_query": "", "neo4j_raw_result": []}
        return []

    print(f"[rule_evaluator] 連線 Stage3 Neo4j at {neo4j_uri} 進行驗證...")
    driver = None
    try:
        driver = GraphDatabase.driver(
            neo4j_uri, 
            auth=(neo4j_user, neo4j_password),
            connection_timeout=5.0,
            max_connection_lifetime=30.0
        )
        driver.verify_connectivity()
    except Exception as e:
        print(f"[rule_evaluator] 錯誤: 無法連線至 Stage3 Neo4j: {e}。直接回傳空規則。")
        if driver:
            try:
                driver.close()
            except:
                pass
        if return_debug:
            return [], {"neo4j_query": "", "neo4j_raw_result": []}
        return []

    query = """
    MATCH (r:ValidationRule)
    RETURN r.id AS id, 
           r.category AS category, 
           r.severity AS severity, 
           r.trigger_expr AS trigger_expr, 
           r.validate_expr AS validate_expr, 
           r.message AS message
    """

    print(f"[rule_evaluator] Neo4j 查詢語法 (Cypher Code):\n{query.strip()}")

    rules = []
    try:
        with driver.session(database=neo4j_database) as session:
            result = session.run(query)
            for record in result:
                rules.append(dict(record))
        print(f"[rule_evaluator] Neo4j 查詢結果 (Raw Return - 共 {len(rules)} 筆記錄):")
        for sample in rules[:3]:
            print(f"  - {sample}")
        if len(rules) > 3:
            print("  - ...")
    except Exception as e:
        print(f"[rule_evaluator] 錯誤: 查詢 Neo4j 失敗: {e}。直接回傳空規則。")
        if return_debug:
            return [], {"neo4j_query": query.strip(), "neo4j_raw_result": []}
        return []
    finally:
        try:
            driver.close()
        except:
            pass

    # 執行 Python 本地評估
    try:
        evaluator = TaxRuleEvaluator(
            filing_status=context.get("filing_status", "Single"),
            extracted_fields=context.get("fields", {}),
            uploaded_docs=context.get("docs", [])
        )
        violated = evaluator.validate_bundle(rules)
        print(f"[rule_evaluator] 規則評估完成。共評估 {len(rules)} 條規則，發現 {len(violated)} 條違反規則。")
        if return_debug:
            return violated, {"neo4j_query": query.strip(), "neo4j_raw_result": rules}
        return violated
    except Exception as e:
        print(f"[rule_evaluator] 錯誤: 執行規則評估器失敗: {e}。直接回傳空。")
        if return_debug:
            return [], {"neo4j_query": query.strip(), "neo4j_raw_result": rules}
        return []
