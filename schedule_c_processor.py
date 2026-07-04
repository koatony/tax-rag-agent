import json
import os
import re
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage
from llm_wrappers import GeminiLLM, OllamaLLM

# 載入環境變數以讀取 API 金鑰與模型設定
load_dotenv()

SCHEMA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "docs", "how_to_fill_forms_docs", "schedule_c", "schedule_c_schema.json"))

def load_schedule_c_schema() -> Dict[str, Any]:
    """
    載入 Schedule C 的 Schema 設定檔，包含所有輸入欄位與計算公式。
    """
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def generate_extraction_prompt(schema: Dict[str, Any]) -> str:
    """
    依據 Schema 定義，動態組裝供 LLM 使用的系統提示詞，規範提取欄位與輸出格式。
    """
    inputs_def = []
    for field in schema.get("inputs", []):
        inputs_def.append(f'- `{field["id"]}` ({field["type"]}): {field["description"]}')
        
    inputs_str = "\n".join(inputs_def)
    
    prompt = f"""你是一位專業的美國稅務申報與數據提取專家。
你的任務是從申報人基本資料以及上傳的文件內容中，精準提取出國稅局 Schedule C (Form 1040) 中所有直接輸入型的欄位值。

【提取規範】
1. 只需提取以下列出的直接輸入欄位。不要包含任何公式計算或規則條件欄位。
2. 對於數值欄位，若沒有相關資訊，則填寫 0.0；對於布林值，若無資訊則填寫 false；對於字串或日期欄位，若無資訊則填寫 null。
3. 數值必須是純浮點數或整數，不能包含貨幣符號或分節逗號。
4. 絕對不要自行計算任何毛利或總費用公式，保持原始金額。例如不要對餐飲費折半，直接提取收據或損益表中的原始總額。
5. 絕對不要根據任何商務用途比例、個人使用比例或出差天數比例進行折算，必須提取文件中最原始的總金額。所有比例折算與公式計算均由下游系統自動處理。

【預期提取的欄位列表】
{inputs_str}

【輸出格式】
你必須精確返回一個符合上述欄位的 JSON 對象，例如：
{{
  "proprietor_name": "...",
  "line_1_gross_receipts": 12000.0,
  ...
}}
直接返回乾淨的 JSON 字串，不要使用 markdown 程式碼區塊，也不要包含任何說明文字。
"""
    return prompt

def extract_schedule_c_inputs_with_logs(
    document_context: str, 
    model_name: str = "gemma4:31b"
) -> Tuple[Dict[str, Any], str, str]:
    """
    呼叫 LLM 進行欄位提取，並回傳提取後的字典、發送的完整提示詞以及 LLM 原始輸出字串。
    """
    llm_provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    is_ollama = False
    if model_name and "gemini" in model_name.lower():
        is_ollama = False
    elif model_name and ":" in model_name:
        is_ollama = True
    else:
        is_ollama = (llm_provider == "ollama")

    schema = load_schedule_c_schema()
    system_instruction = generate_extraction_prompt(schema)
    
    if is_ollama:
        llm = OllamaLLM(model_name=model_name, temperature=0.0, timeout=600.0)
    else:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("環境變數 GEMINI_API_KEY 未設定")
        
        # 針對思考模型（如 gemini-2.5-pro），為避免思考歷程佔用輸出長度限制，調大 max_tokens 以確保 JSON 完整輸出
        is_thinking_model = "pro" in model_name.lower()
        max_tokens = 65536 if is_thinking_model else 8192
        llm = GeminiLLM(model_name=model_name, api_key=api_key, temperature=0.0, max_tokens=max_tokens)
    
    messages = [
        SystemMessage(content=system_instruction),
        HumanMessage(content=f"以下是申報人與上傳文件的相關內容，請提取 Schedule C 的 Input 欄位：\n\n{document_context}")
    ]
    
    # 組合系統與使用者提示詞，用於紀錄完整對話日誌
    full_prompt_log = f"=== SYSTEM INSTRUCTION ===\n{system_instruction}\n\n=== USER PROMPT ===\n以下是申報人與上傳文件的相關內容，請提取 Schedule C 的 Input 欄位：\n\n{document_context}"
    
    if is_ollama:
        resp = llm.invoke(messages)
    else:
        resp = llm.invoke(messages, response_mime_type="application/json")
        
    raw_output = resp.content.strip()
    
    # 移除 LLM 回應中的 think 標籤內容
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
    """
    對公式的依賴關係進行拓撲排序，以確定正確的計算順序。
    若公式間存在循環依賴，則拋出 ValueError 異常。
    
    參數:
        formula_deps: 鍵為目標欄位，值為該欄位所依賴之其他欄位列表的字典。
        
    回傳:
        無衝突的欄位計算順序列表。
    """
    # 記錄各節點的拜訪狀態：0 表示未拜訪，1 表示拜訪中（用於偵測環），2 表示拜訪完成
    visited = {}
    order = []
    
    def dfs(node):
        # 如果節點拜訪狀態為 1，代表在同一條深度搜尋路徑上重複拜訪，即存在循環依賴
        if visited.get(node, 0) == 1:
            raise ValueError(f"偵測到公式間存在循環依賴，無法完成計算。衝突節點: {node}")
        # 如果節點已完成拜訪，直接返回
        if visited.get(node, 0) == 2:
            return
            
        visited[node] = 1  # 標記為拜訪中
        for dep in formula_deps.get(node, []):
            if dep in formula_deps:  # 僅處理存在於依賴圖中的子公式節點
                dfs(dep)
        visited[node] = 2  # 標記為拜訪完成
        order.append(node)  # 將節點加入執行順序
        
    for node in formula_deps:
        if visited.get(node, 0) == 0:
            dfs(node)
            
    return order

def calculate_schedule_c_dynamic(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    根據 Schema 定義的計算公式與輸入數據，動態且安全地執行 Schedule C 稅務計算。
    計算過程會解析依賴關係並透過拓撲排序決定順序，再使用 eval 執行公式計算。
    """
    schema = load_schedule_c_schema()
    
    # 步驟 1：依據 Schema 定義的輸入欄位及其型態，初始化預設狀態
    state = {}
    for field in schema.get("inputs", []):
        field_id = field["id"]
        field_type = field["type"]
        
        if field_type == "float":
            state[field_id] = 0.0
        elif field_type == "boolean":
            state[field_id] = False
        elif field_type == "array":
            state[field_id] = []
        else:
            state[field_id] = None
            
    # 設定特定業務欄位的預設值
    state["selected_mileage_method"] = "standard"
    state["selected_home_method"] = "simplified"
    state["accounting_method"] = "Cash"
    
    # 將 LLM 提取或外部傳入的實際資料合併至狀態中
    for k, v in inputs.items():
        if v is not None:
            state[k] = v
            
    # 進行資料型態防禦性對齊，確保資料格式正確以避免計算時發生異常
    for field in schema.get("inputs", []):
        field_id = field["id"]
        field_type = field["type"]
        val = state.get(field_id)
        if field_type == "array":
            if not isinstance(val, list):
                state[field_id] = []
        elif field_type == "float":
            try:
                state[field_id] = float(val) if val is not None else 0.0
            except (ValueError, TypeError):
                state[field_id] = 0.0
        elif field_type == "boolean":
            if isinstance(val, str):
                state[field_id] = val.lower() in ("true", "1", "yes")
            else:
                state[field_id] = bool(val)
            
    # 確保數值型變數皆為浮點數型態（排除布林值，因其為整數的子類）
    for k, v in state.items():
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            state[k] = float(v)
            
    # 步驟 2：建構公式的有向無環圖
    formulas_def = schema.get("formulas", [])
    formula_deps = {}
    expr_map = {}
    
    # 解析各公式中引用的變數，建立依賴關係
    for f in formulas_def:
        field_id = f["id"]
        expr = f["expr"]
        expr_map[field_id] = expr
        
        # 尋找表達式中所有的變數名稱
        variables = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', expr)
        # 過濾出屬於公式定義或當前狀態中的有效依賴項
        dependencies = [var for var in variables if var in expr_map or var in state]
        formula_deps[field_id] = dependencies
        
    # 步驟 3：執行拓撲排序，決定各公式的計算順序
    calc_order = topological_sort(formula_deps)
    
    # 步驟 4：依排序結果依序安全地求值
    for field_id in calc_order:
        if field_id in expr_map:
            expr = expr_map[field_id]
            # 建立安全沙箱執行環境，僅開放受信任的內建函式及數學計算函式
            globals_env = {
                "__builtins__": {},
                "min": min,
                "max": max,
                "sum": sum
            }
            locals_env = {k: v for k, v in state.items() if isinstance(v, (int, float, bool, str, list)) or v is None}
            try:
                # 執行公式求值
                val = eval(expr, globals_env, locals_env)
                if isinstance(val, bool):
                    state[field_id] = val
                else:
                    state[field_id] = float(val) if isinstance(val, (int, float)) else val
            except Exception as eval_err:
                state[field_id] = 0.0
                print(f"[計算引擎錯誤] 計算欄位 {field_id} 失敗，公式為 {expr}，錯誤原因: {eval_err}")
                
    return state
