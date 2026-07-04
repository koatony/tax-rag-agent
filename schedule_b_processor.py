import json
import os
import re
from typing import Dict, Any, List, Tuple
from decimal import Decimal
from dotenv import load_dotenv
from llm_wrappers import GeminiLLM, OllamaLLM
from langchain_core.messages import SystemMessage, HumanMessage

# 載入環境變數
load_dotenv()

SCHEMA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "docs", "how_to_fill_forms_docs", "schedule_b", "schedule_b_schema.json"))
REFERENCES_DEFAULT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "docs", "how_to_fill_forms_docs", "schedule_b", "schedule_b_references_default.json"))

def load_schedule_b_schema() -> Dict[str, Any]:
    """載入外部的 Schedule B V1 欄位與計算規則設定檔 (schedule_b_schema.json)。"""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def load_schedule_b_references_default() -> Dict[str, Any]:
    """載入外部的 Schedule B 參考資料預設值設定檔 (schedule_b_references_default.json)。"""
    with open(REFERENCES_DEFAULT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def generate_extraction_prompt(schema: Dict[str, Any]) -> str:
    """根據 schema 動態組裝 LLM 的 prompt。"""
    inputs_def = []
    for field in schema.get("inputs", []):
        inputs_def.append(f'- `{field["id"]}` ({field["type"]}): {field["description"]}')
        
    inputs_str = "\n".join(inputs_def)
    
    prompt = f"""你是一位專業的美國稅務申報與數據提取專家。
你的任務是從申報人基本資料以及上傳的 Form 1099-INT、1099-DIV、1099-OID、1099-B、8949、K-1 等文件中，精準提取出國稅局 (IRS) Schedule B (Form 1040) V1 中所有「直接輸入型 (Input)」的欄位值。

【提取規範】
1. 只需提取以下列出的「直接輸入 (Input)」欄位。不要包含任何「公式計算 (Formula)」欄位。
2. 對於數值欄位，若沒有相關資訊，則填寫 0.00；對於布林值，若無資訊則填寫 null 或 false；對於陣列欄位，若無資訊則填寫 []。
3. 數值必須是純數值，不能包含貨幣符號 ($) 或分節逗號 (,)。
4. 遇到 Nominee、Accrued Interest、OID、ABP 調整等，請在 `special_case_flags` 中相應標示。
5. 若 Form 1099-B 或 Form 8949 交易明細中含有 accrued market discount (或市場折價)，請將該筆交易原始的 proceeds, cost_basis, 與 accrued_market_discount 數值提取並寫入 `market_discount_items` 陣列中，且 `special_case_flags.has_market_discount` 需標示為 true。

【預期提取的欄位列表】
{inputs_str}

【輸出格式】
你必須精確返回一個符合上述欄位的 JSON 對象，例如：
{{
  "taxpayer_name": "Marcus Rivera",
  "taxpayer_ssn": "123-45-6789",
  "tax_year": 2025,
  "interest_items": [
    {{
      "item_id": "item1",
      "source_statement_id": null,
      "statement_issuer_name": null,
      "source_document_type": "1099-INT",
      "source_box": "1",
      "payer_name": "Chase Bank",
      "payer_reported_amount": 150.00,
      "tax_character": "TAXABLE_INTEREST",
      "is_series_ee_or_i_interest": false
    }}
  ],
  "dividend_items": [
    {{
      "item_id": "div1",
      "source_statement_id": null,
      "statement_issuer_name": null,
      "source_document_type": "1099-DIV",
      "payer_name": "Vanguard Services",
      "ordinary_dividends": 405.00,
      "qualified_dividends": 0.00,
      "exempt_interest_dividends": 0.00
    }}
  ],
  "market_discount_items": [
    {{
      "item_id": "md1",
      "payer_name": "Chase Brokerage",
      "proceeds": 8000.00,
      "cost_basis": 7900.00,
      "accrued_market_discount": 200.00
    }}
  ],
  "form_8815": null,
  "foreign_account_q1": false,
  "fbar_q2": false,
  "foreign_countries": [],
  "foreign_trust_q8": false,
  "special_case_flags": {{
    "has_nominee_distribution": false,
    "has_accrued_interest": false,
    "has_oid": false,
    "has_abp_adjustment": false,
    "has_market_discount": true,
    "has_seller_financed_mortgage": false,
    "has_form_8814": false,
    "has_tax_exempt_bond_premium": false,
    "has_contingent_payment_debt": false
  }}
}}
直接返回乾淨的 JSON 字串，不要使用 markdown 區塊，也不要包含 any 說明文字。
"""
    return prompt

def extract_schedule_b_inputs_with_logs(
    document_context: str, 
    model_name: str = "gemini-2.5-pro"
) -> Tuple[Dict[str, Any], str, str]:
    """呼叫 LLM 進行 Schedule B 數據提取，並回傳: (提取 JSON, 發送 Prompt, LLM 原始輸出)。"""
    llm_provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    is_ollama = False
    if model_name and "gemini" in model_name.lower():
        is_ollama = False
    elif model_name and ":" in model_name:
        is_ollama = True
    else:
        is_ollama = (llm_provider == "ollama")

    schema = load_schedule_b_schema()
    system_instruction = generate_extraction_prompt(schema)
    
    if is_ollama:
        llm = OllamaLLM(model_name=model_name, temperature=0.0, timeout=600.0)
    else:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("環境變數 GEMINI_API_KEY 未設定")
        llm = GeminiLLM(model_name=model_name, api_key=api_key, temperature=0.0)
    
    messages = [
        SystemMessage(content=system_instruction),
        HumanMessage(content=f"以下是申報人與上傳文件的相關內容，請提取 Schedule B 的 Input 欄位：\n\n{document_context}")
    ]
    
    full_prompt_log = f"=== SYSTEM INSTRUCTION ===\n{system_instruction}\n\n=== USER PROMPT ===\n以下是申報人與上傳文件的相關內容，請提取 Schedule B 的 Input 欄位：\n\n{document_context}"
    
    if is_ollama:
        resp = llm.invoke(messages)
    else:
        resp = llm.invoke(messages, response_mime_type="application/json")
        
    raw_output = resp.content.strip()
    clean_output = re.sub(r"<think>.*?</think>", "", raw_output, flags=re.DOTALL).strip()
    
    match = re.search(r"\{.*\}", clean_output, re.DOTALL)
    if match:
        clean_output = match.group(0)
        
    try:
        from json_repair import repair_json
        repaired_output = repair_json(clean_output)
        extracted_data = json.loads(repaired_output)
        return extracted_data, full_prompt_log, raw_output
    except Exception as e:
        raise ValueError(f"JSON 解析與修復失敗: {e}\nLLM 原始回應: {raw_output}")

def topological_sort(formula_deps: Dict[str, List[str]]) -> List[str]:
    """使用 DFS 演算法對公式依賴樹進行拓撲排序，排除循環引用。"""
    visited = {}  # 0: unvisited, 1: visiting, 2: visited
    order = []
    
    def dfs(node):
        if visited.get(node, 0) == 1:
            raise ValueError(f"公式依賴檢測到循環引用 (Cycle detected at node): {node}")
        if visited.get(node, 0) == 2:
            return
            
        visited[node] = 1  # visiting
        for dep in formula_deps.get(node, []):
            if dep in formula_deps:
                dfs(dep)
        visited[node] = 2  # visited
        order.append(node)
        
    for node in formula_deps:
        if visited.get(node, 0) == 0:
            dfs(node)
            
    return order

def sum_decimal(iterable):
    """將可迭代項目加總為 Decimal 類型的金額。"""
    s = Decimal("0.00")
    for x in iterable:
        if x is not None:
            s += Decimal(str(x))
    return s

def coalesce_decimal(*args):
    """回傳參數中第一個非 None 的 Decimal，若全為 None 則回傳 Decimal('0.00')。"""
    for arg in args:
        if arg is not None:
            return Decimal(str(arg))
    return Decimal("0.00")

def process_interest_items(interest_items: List[Dict[str, Any]], tax_year: int) -> List[Dict[str, Any]]:
    """V1 利息項目分類處理：將金額轉換為 Decimal 並判定應稅/免稅。"""
    if not isinstance(interest_items, list):
        return []
        
    processed = []
    for raw_item in interest_items:
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        
        # 轉換申報金額為 Decimal
        amt_val = item.get('payer_reported_amount') if item.get('payer_reported_amount') is not None else item.get('reported_amount') if item.get('reported_amount') is not None else item.get('amount')
        payer_reported_amount = Decimal(str(amt_val)) if amt_val is not None else Decimal("0.00")
        item['payer_reported_amount'] = payer_reported_amount
        item['reported_amount'] = payer_reported_amount
        
        # 判斷/推導 tax_character
        tax_character = item.get('tax_character')
        if not tax_character:
            is_exempt = bool(item.get('is_tax_exempt', False))
            box_code = item.get('box_code')
            if is_exempt or box_code == "Box 8":
                tax_character = "TAX_EXEMPT_INTEREST"
            else:
                tax_character = "TAXABLE_INTEREST"
        item['tax_character'] = tax_character
        
        processed.append(item)
    return processed

def process_market_discount_items(market_discount_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """依據 IRS Section 1276(a)(1) 計算折價債券處分時之應稅利息並包裝。"""
    if not isinstance(market_discount_items, list):
        return []
        
    processed = []
    for raw_item in market_discount_items:
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        
        # 轉換數值為 Decimal
        proceeds = Decimal(str(item.get('proceeds') if item.get('proceeds') is not None else 0.0))
        cost_basis = Decimal(str(item.get('cost_basis') if item.get('cost_basis') is not None else 0.0))
        accrued_market_discount = Decimal(str(item.get('accrued_market_discount') if item.get('accrued_market_discount') is not None else 0.0))
        
        # 計算實現 Gain (若 Proceeds <= Cost Basis，則為 0)
        gain = max(Decimal("0.00"), proceeds - cost_basis)
        
        # 應稅折價利息為 min(accrued_market_discount, gain)
        taxable_interest = min(accrued_market_discount, gain)
        
        if taxable_interest > Decimal("0.00"):
            processed.append({
                "item_id": item.get("item_id") or f"market_discount_{item.get('payer_name') or 'unknown'}",
                "source_statement_id": None,
                "statement_issuer_name": item.get("payer_name"),
                "source_document_type": "1099-B",
                "source_box": "Accrued Market Discount",
                "payer_name": item.get("payer_name") or "Unknown Brokerage",
                "payer_reported_amount": taxable_interest,
                "reported_amount": taxable_interest,
                "tax_character": "TAXABLE_INTEREST",
                "is_series_ee_or_i_interest": False
            })
    return processed

def process_dividend_items(dividend_items: List[Dict[str, Any]], tax_year: int) -> List[Dict[str, Any]]:
    """V1 股利項目分類處理：將金額轉換為 Decimal。"""
    if not isinstance(dividend_items, list):
        return []
        
    processed = []
    for raw_item in dividend_items:
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        
        ord_val = item.get('ordinary_dividends')
        ordinary_dividends = Decimal(str(ord_val)) if ord_val is not None else Decimal("0.00")
        
        qual_val = item.get('qualified_dividends')
        qualified_dividends = Decimal(str(qual_val)) if qual_val is not None else Decimal("0.00")
        
        exempt_val = item.get('exempt_interest_dividends')
        exempt_interest_dividends = Decimal(str(exempt_val)) if exempt_val is not None else Decimal("0.00")
        
        item['ordinary_dividends'] = ordinary_dividends
        item['qualified_dividends'] = qualified_dividends
        item['exempt_interest_dividends'] = exempt_interest_dividends
        
        processed.append(item)
    return processed

def aggregate_interest_entries(processed_interest_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """依據 (source_statement_id, display_name) 進行利息項目表面聚合。"""
    taxable_items = [item for item in processed_interest_items if item.get('tax_character') == 'TAXABLE_INTEREST']
    grouped = {}
    standalone_counter = 0
    
    for item in taxable_items:
        stmt_id = item.get('source_statement_id') or ""
        doc_type = item.get('source_document_type') or ""
        issuer = item.get('statement_issuer_name')
        payer = item.get('payer_name') or "Unnamed Payer"
        
        display_name = issuer if (doc_type == "SUBSTITUTE_STATEMENT" and issuer) else payer
        
        if not stmt_id and not item.get('payer_name'):
            standalone_counter += 1
            key = (f"standalone_{standalone_counter}", display_name)
        else:
            key = (stmt_id, display_name)
            
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(item)
        
    aggregated = []
    for (stmt_id, display_name), items in grouped.items():
        total_amount = sum(item.get('payer_reported_amount', Decimal("0.00")) for item in items)
        aggregated.append({
            'payer_name': display_name,
            'payer_reported_amount': total_amount,
            'source_statement_id': stmt_id if stmt_id else None
        })
    return aggregated

def aggregate_dividend_entries(processed_dividend_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """依據 (source_statement_id, display_name) 進行股利項目表面聚合。"""
    grouped = {}
    standalone_counter = 0
    
    for item in processed_dividend_items:
        stmt_id = item.get('source_statement_id') or ""
        doc_type = item.get('source_document_type') or ""
        issuer = item.get('statement_issuer_name')
        payer = item.get('payer_name') or "Unnamed Payer"
        
        display_name = issuer if (doc_type == "SUBSTITUTE_STATEMENT" and issuer) else payer
        
        if not stmt_id and not item.get('payer_name'):
            standalone_counter += 1
            key = (f"standalone_{standalone_counter}", display_name)
        else:
            key = (stmt_id, display_name)
            
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(item)
        
    aggregated = []
    for (stmt_id, display_name), items in grouped.items():
        total_amount = sum(item.get('ordinary_dividends', Decimal("0.00")) for item in items)
        aggregated.append({
            'payer_name': display_name,
            'payer_reported_amount': total_amount,
            'source_statement_id': stmt_id if stmt_id else None
        })
    return aggregated

def any_special_case(special_case_flags: Dict[str, Any], interest_items: List[Dict[str, Any]] = None, dividend_items: List[Dict[str, Any]] = None) -> bool:
    """判定是否存在任何 V1 不支援的特殊案件。"""
    if special_case_flags:
        for k, v in special_case_flags.items():
            if k == "has_market_discount":
                continue
            if v is True:
                return True
        
    if interest_items:
        for item in interest_items:
            # 偵測 Nominee interest
            if float(item.get('nominee_amount') or 0.0) > 0.0:
                return True
            # 偵測 Accrued interest
            if float(item.get('accrued_interest') or 0.0) > 0.0:
                return True
            # 偵測 Seller financed
            if bool(item.get('is_seller_financed', False)):
                return True
            # 偵測 OID
            if float(item.get('oid_broker_adjustment_amount') or 0.0) > 0.0 or float(item.get('oid_taxpayer_computed_adjustment') or 0.0) > 0.0 or float(item.get('oid_adjustment') or 0.0) > 0.0:
                return True
            # 偵測 ABP
            if float(item.get('abp_broker_adjustment_amount') or 0.0) > 0.0 or float(item.get('abp_taxpayer_computed_adjustment') or 0.0) > 0.0 or float(item.get('bond_premium_adjustment') or 0.0) > 0.0:
                return True
                
    if dividend_items:
        for item in dividend_items:
            # 偵測 Nominee dividends
            if float(item.get('nominee_ordinary_amount') or 0.0) > 0.0 or float(item.get('nominee_qualified_amount') or 0.0) > 0.0 or float(item.get('nominee_amount') or 0.0) > 0.0:
                return True
                
    return False

def calculate_schedule_b_dynamic(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """相容舊版接口之總入口，執行 V1 計算引擎。"""
    schema = load_schedule_b_schema()
    state = {}
    
    # 1. 初始化預設狀態
    for field in schema.get("inputs", []):
        field_id = field["id"]
        field_type = field["type"]
        if field_type == "array":
            state[field_id] = []
        elif field_type == "object":
            state[field_id] = {}
        elif field_type == "boolean":
            state[field_id] = None
        else:
            state[field_id] = None
            
    # 載入外部預設參考值
    try:
        ref_defaults = load_schedule_b_references_default()
        for k, v in ref_defaults.items():
            state[k] = v
    except Exception:
        state["tax_year"] = 2024
        
    # 合併使用者輸入與歷史變數對齊 (相容舊名)
    inputs_copied = dict(inputs)
    if 'foreign_accounts_interest' in inputs_copied and 'foreign_account_q1' not in inputs_copied:
        inputs_copied['foreign_account_q1'] = inputs_copied['foreign_accounts_interest']
    if 'foreign_trust_distribution' in inputs_copied and 'foreign_trust_q8' not in inputs_copied:
        inputs_copied['foreign_trust_q8'] = inputs_copied['foreign_trust_distribution']
        
    for k, v in inputs_copied.items():
        if v is not None:
            state[k] = v
            
    # 2. 構建並解析拓撲排序公式
    formulas_def = schema.get("formulas", [])
    formula_deps = {}
    expr_map = {}
    
    for f in formulas_def:
        field_id = f["id"]
        expr = f["expr"]
        expr_map[field_id] = expr
        variables = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', expr)
        dependencies = [var for var in variables if var in expr_map or var in state]
        formula_deps[field_id] = dependencies
        
    calc_order = topological_sort(formula_deps)
    
    # 3. 執行拓撲求值 (在 Decimal 環境中)
    for field_id in calc_order:
        if field_id in expr_map:
            expr = expr_map[field_id]
            globals_env = {
                "__builtins__": {},
                "Decimal": Decimal,
                "str": str,
                "int": int,
                "bool": bool,
                "list": list,
                "isinstance": isinstance,
                "coalesce": coalesce_decimal,
                "sum_decimal": sum_decimal,
                "process_interest_items": process_interest_items,
                "process_dividend_items": process_dividend_items,
                "process_market_discount_items": process_market_discount_items,
                "aggregate_interest_entries": aggregate_interest_entries,
                "aggregate_dividend_entries": aggregate_dividend_entries,
                "any_special_case": any_special_case
            }
            # 將目前狀態注入 globals
            for k, v in state.items():
                globals_env[k] = v
                
            try:
                state[field_id] = eval(expr, globals_env)
            except Exception as e:
                state[field_id] = Decimal("0.00")
                print(f"[V1 Eval Error] {field_id}: {e}")
                
    # 4. 實質 V1 阻斷與合規驗證
    errors = []
    warnings = []
    
    def issue(code, field, item_id, message):
        return {"code": code, "field": field, "item_id": item_id, "message": message}
        
    # taxpayer_ssn 遮罩處理
    raw_ssn = str(state.get('taxpayer_ssn') or inputs.get('ssn') or "")
    if len(raw_ssn) >= 4:
        state['taxpayer_ssn_masked'] = f"***-**-{raw_ssn[-4:]}"
    else:
        state['taxpayer_ssn_masked'] = "***-**-XXXX"
        
    # 偵測特殊案件旗標
    flags = state.get('special_case_flags') or {}
    interest_items = state.get('interest_items') or []
    dividend_items = state.get('dividend_items') or []
    
    if flags.get('has_nominee_distribution') is True or any(float(item.get('nominee_amount') or 0.0) > 0.0 for item in interest_items) or any(float(item.get('nominee_ordinary_amount') or 0.0) > 0.0 or float(item.get('nominee_qualified_amount') or 0.0) > 0.0 or float(item.get('nominee_amount') or 0.0) > 0.0 for item in dividend_items):
        errors.append(issue("UNSUPPORTED_NOMINEE_DISTRIBUTION", "nominee", None, "Nominee interest/dividends not supported in V1."))
        
    if flags.get('has_accrued_interest') is True or any(float(item.get('accrued_interest') or 0.0) > 0.0 for item in interest_items):
        errors.append(issue("UNSUPPORTED_ACCRUED_INTEREST", "accrued_interest", None, "Accrued interest not supported in V1."))
        
    if flags.get('has_oid') is True or any(float(item.get('oid_broker_adjustment_amount') or 0.0) > 0.0 or float(item.get('oid_taxpayer_computed_adjustment') or 0.0) > 0.0 or float(item.get('oid_adjustment') or 0.0) > 0.0 for item in interest_items):
        errors.append(issue("UNSUPPORTED_OID", "oid", None, "Form 1099-OID or OID adjustment not supported in V1."))
        
    if flags.get('has_abp_adjustment') is True or any(float(item.get('abp_broker_adjustment_amount') or 0.0) > 0.0 or float(item.get('abp_taxpayer_computed_adjustment') or 0.0) > 0.0 or float(item.get('bond_premium_adjustment') or 0.0) > 0.0 for item in interest_items):
        errors.append(issue("UNSUPPORTED_ABP_ADJUSTMENT", "abp", None, "Amortizable bond premium not supported in V1."))
        

    if flags.get('has_seller_financed_mortgage') is True or any(bool(item.get('is_seller_financed', False)) for item in interest_items):
        errors.append(issue("UNSUPPORTED_SELLER_FINANCED_MORTGAGE", "seller_financed", None, "Seller-financed mortgage interest not supported in V1."))
        
    if flags.get('has_form_8814') is True or len(inputs.get('form_8814_children') or []) > 0:
        errors.append(issue("UNSUPPORTED_FORM_8814", "form_8814", None, "Form 8814 is not supported in V1."))
        
    if flags.get('has_tax_exempt_bond_premium') is True:
        errors.append(issue("UNSUPPORTED_TAX_EXEMPT_BOND_PREMIUM", "tax_exempt_bond_premium", None, "Tax-exempt bond premium not supported in V1."))
        
    if flags.get('has_contingent_payment_debt') is True:
        errors.append(issue("UNSUPPORTED_CONTINGENT_PAYMENT_DEBT", "contingent_payment_debt", None, "Contingent payment debt not supported in V1."))
        
    # 驗證利息稅務特徵與負數金額
    for item in state.get('processed_interest_items', []):
        if item.get('tax_character') == "UNKNOWN":
            errors.append(issue("UNKNOWN_TAX_CHARACTER", "tax_character", item.get('item_id'), "Unable to determine tax character of interest item."))
        amt = item.get('payer_reported_amount', Decimal("0.00"))
        if amt < Decimal("0.00"):
            errors.append(issue("NEGATIVE_AMOUNT", "payer_reported_amount", item.get('item_id'), "Payer reported amount cannot be negative."))
            
    # 驗證股利與負數金額
    for item in state.get('processed_dividend_items', []):
        ord_div = item.get('ordinary_dividends', Decimal("0.00"))
        qual_div = item.get('qualified_dividends', Decimal("0.00"))
        exempt_div = item.get('exempt_interest_dividends', Decimal("0.00"))
        
        if ord_div < Decimal("0.00"):
            errors.append(issue("NEGATIVE_AMOUNT", "ordinary_dividends", item.get('item_id'), "Ordinary dividends cannot be negative."))
        if qual_div < Decimal("0.00"):
            errors.append(issue("NEGATIVE_AMOUNT", "qualified_dividends", item.get('item_id'), "Qualified dividends cannot be negative."))
        if exempt_div < Decimal("0.00"):
            errors.append(issue("NEGATIVE_AMOUNT", "exempt_interest_dividends", item.get('item_id'), "Exempt interest dividends cannot be negative."))
            
        if qual_div > ord_div:
            errors.append(issue("QUALIFIED_DIVIDENDS_EXCEED_ORDINARY", "qualified_dividends", item.get('item_id'), "Qualified dividends exceed ordinary dividends."))
            
    # Form 8815 排除額度驗證
    form_8815 = state.get('form_8815') or {}
    line_3 = state.get('line_3_excludable_savings_bond_interest', Decimal("0.00"))
    if line_3 > Decimal("0.00") and not form_8815.get('is_completed'):
        errors.append(issue("FORM_8815_NOT_COMPLETED", "form_8815", None, "Form 8815 must be completed to claim exclusions."))
        
    eligible_series = Decimal(str(form_8815.get('eligible_series_ee_i_interest_included_in_line_2') or "0.00"))
    if line_3 > eligible_series:
        errors.append(issue("FORM8815_EXCLUSION_EXCEEDS_ELIGIBLE_INTEREST", "line_14_excludable_interest", None, "Line 14 exclusions exceed eligible EE/I interest included in Line 2."))
        
    # Line 4 負數阻斷
    line_4_raw = state.get('line_4_raw_calculation', Decimal("0.00"))
    if line_4_raw < Decimal("0.00"):
        errors.append(issue("NEGATIVE_TAXABLE_INTEREST", "line_4_raw_calculation", None, "Taxable interest cannot be negative."))
        
    # Part III 填寫完整度驗證
    q1 = state.get('foreign_account_q1')
    q8 = state.get('foreign_trust_q8')
    
    # 篩選問題 (Screening questions) 永遠不能是 null (必須明確為 True 或 False)
    if q1 is None:
        errors.append(issue("PART_III_ANSWER_MISSING", "foreign_account_q1", None, "Foreign account screening answer missing (must be True or False)."))
    if q8 is None:
        errors.append(issue("PART_III_ANSWER_MISSING", "foreign_trust_q8", None, "Foreign trust screening answer missing (must be True or False)."))
        
    is_part_iii_required = state.get('is_part_iii_required', False)
    if is_part_iii_required and q1 is not None and q8 is not None:
        if q1 is True:
            q2 = state.get('fbar_q2')
            if q2 is None:
                errors.append(issue("PART_III_ANSWER_MISSING", "fbar_q2", None, "FBAR requirement answer missing in Part III."))
            elif q2 is True:
                countries = state.get('foreign_countries') or []
                if not countries or len(countries) == 0:
                    errors.append(issue("FBAR_COUNTRY_MISSING", "foreign_countries", None, "FBAR countries list is empty."))
                    
    # 5. 回寫 V1 決策變數
    is_v1_supported = not any_special_case(flags, interest_items, dividend_items)
    can_file = is_v1_supported and len(errors) == 0
    
    state['blocking_errors'] = errors
    state['review_warnings'] = warnings
    state['blocking_validation_error'] = len(errors) > 0
    state['is_v1_supported'] = is_v1_supported
    state['can_file'] = can_file
    state['should_attach_schedule_b'] = state.get('is_schedule_b_required', False) and can_file
    
    # 舊屬性回退相容 (對齊前端 UI)
    state['line_4_taxable_interest'] = state.get('line_4_surface_value')
    state['needs_human_review'] = not can_file
    state['foreign_accounts_interest'] = state.get('foreign_account_q1')
    state['foreign_trust_distribution'] = state.get('foreign_trust_q8')
    state['line_7a_foreign_account_authority'] = state.get('line_7a_q1_surface')
    state['line_7a_fbar_required'] = state.get('line_7a_q2_surface')
    state['line_7b_foreign_countries'] = state.get('line_7b_surface')
    state['line_8_foreign_trust_distribution'] = state.get('line_8_surface')
    state['has_seller_financed_mortgage'] = not is_v1_supported and bool(flags.get('has_seller_financed_mortgage'))
    
    return state
