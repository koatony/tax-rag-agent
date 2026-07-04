import os
import time
import json
import re
import asyncio
import random
from typing import List, Dict, Any, Tuple, Optional
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from llm_wrappers import GeminiLLM, OllamaLLM

import rule_evaluator

from prompts import (
    PLANNER_SYSTEM_INSTRUCTION, PLANNER_HUMAN_PROMPT_TEMPLATE,
    MAP_SYSTEM_INSTRUCTION, MAP_HUMAN_PROMPT_TEMPLATE,
    LOOP_SYSTEM_INSTRUCTION, LOOP_HUMAN_PROMPT_TEMPLATE,
    LOOP_HUMAN_FOLLOWUP_TEMPLATE
)

def format_input_data(user_input_str: str) -> str:
    """
    【功能】將使用者傳進來的原始輸入字串，轉換為 LLM 容易閱讀的純文字格式。

    【為什麼需要這個？】
    使用者輸入可能是 JSON 字串（包含 taxpayer_profile + uploaded_documents），
    也可能是純文字。這裡統一做格式化，讓後續 LLM 收到的 input 格式一致。

    【處理邏輯】
    1. 嘗試把輸入當 JSON 解析。
    2. 如果是 dict 且含有 taxpayer_profile / uploaded_documents：
       - taxpayer_profile: dict 轉成 "- key: value" 條列格式
       - uploaded_documents: 若是 list of {"file_name": ..., "content": ...}，
         每個檔案展開成 "[檔名]\n內容" 的區塊
    3. 如果 JSON 解析失敗或格式不符，直接回傳原始字串。

    Args:
        user_input_str: 原始輸入字串（JSON 格式或純文字）

    Returns:
        已格式化的純文字字串，供 LLM Prompt 使用
    """
    try:
        data = json.loads(user_input_str)
        if isinstance(data, dict):
            profile = data.get("taxpayer_profile", "")
            docs = data.get("uploaded_documents", "")
            if profile or docs:
                parts = []
                if profile:
                    if isinstance(profile, str):
                        parts.append(f"Taxpayer Profile:\n{profile}")
                    else:
                        # dict 型態的 profile → 轉成 "- key: value" 條列
                        profile_str = "\n".join([f"- {k}: {v}" for k, v in profile.items()])
                        parts.append(f"Taxpayer Profile:\n{profile_str}")
                if docs:
                    parts.append("Uploaded Documents:")
                    if isinstance(docs, str):
                        parts.append(docs)
                    elif isinstance(docs, list):
                        docs_parts = []
                        for d in docs:
                            if isinstance(d, dict) and "file_name" in d and "content" in d:
                                # 標準格式：每個文件展開成 [檔名]\n內容
                                docs_parts.append(f"[{d['file_name']}]\n{d['content']}")
                            elif isinstance(d, dict):
                                docs_parts.append(json.dumps(d, ensure_ascii=False))
                            else:
                                docs_parts.append(str(d))
                        parts.append("\n\n".join(docs_parts))
                    else:
                        parts.append(json.dumps(docs, indent=2, ensure_ascii=False))
                return "\n\n".join(parts)
            else:
                return json.dumps(data, indent=2, ensure_ascii=False)
        elif isinstance(data, list):
            return json.dumps(data, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return user_input_str

def extract_relevant_context(formatted_input: str, source_docs: list) -> str:
    """
    【功能】依據 Planner 指定的 source_docs 檔案清單，
    從全量格式化輸入中物理隔離出「只包含相關檔案」的精簡版本，
    傳給 Map 或 Loop 任務使用。

    【為什麼需要這個？】
    Planner 掃描全部文件後，會告訴我們每個 issue 只跟哪幾個檔案有關。
    如果每個 Map 任務都收到全量文件，Context 過長會浪費 token 並增加幻覺風險。
    這裡做「物理隔離」，讓每個 Map/Loop 任務只看自己需要的檔案。

    【處理邏輯】
    1. 從 formatted_input 中先抽出 "Taxpayer Profile:" 段落（始終保留）。
    2. 解析所有 [檔名] ... 區塊，建立 {檔名: 內容} 的字典。
    3. 依 source_docs 清單精確比對（先完全匹配，再模糊匹配）。
    4. 若完全沒配對到任何檔案，退回回傳全量輸入（保守策略）。

    Args:
        formatted_input: format_input_data() 的輸出
        source_docs: Planner 回傳的 issue.source_docs 清單

    Returns:
        精簡後的上下文字串（profile + 相關檔案）
    """
    if not source_docs:
        return formatted_input
        
    lines = formatted_input.split("\n")
    profile_lines = []
    in_profile = False
    
    # Step 1: 提取 Taxpayer Profile 段落
    for line in lines:
        if line.startswith("Taxpayer Profile:"):
            in_profile = True
            profile_lines.append(line)
            continue
        if line.startswith("Uploaded Documents:"):
            break
        if in_profile:
            profile_lines.append(line)
            
    profile_text = "\n".join(profile_lines)
    
    # Step 2: 解析所有 [檔名] 區塊，建立 {檔名: 內容} 字典
    document_blocks = {}
    current_file = None
    current_block = []
    
    for line in lines:
        if line.startswith("[") and line.endswith("]"):
            # 遇到新的 [檔名] 標頭 → 儲存上一個區塊
            if current_file and current_block:
                document_blocks[current_file] = "\n".join(current_block)
            current_file = line[1:-1].strip()
            current_block = []
            continue
        if current_file is not None:
            current_block.append(line)
            
    if current_file and current_block:
        document_blocks[current_file] = "\n".join(current_block)
        
    # Step 3: 依 source_docs 拼接相關檔案（精確匹配 → 模糊匹配）
    relevant_docs = []
    for doc in source_docs:
        doc = doc.strip()
        if doc in document_blocks:
            # 精確匹配
            relevant_docs.append(f"[{doc}]\n{document_blocks[doc]}")
        else:
            # 模糊匹配：只要其中一方包含另一方的名稱即算匹配
            matched = False
            for k, v in document_blocks.items():
                if doc.lower() in k.lower() or k.lower() in doc.lower():
                    relevant_docs.append(f"[{k}]\n{v}")
                    matched = True
                    break
            if not matched:
                pass  # 找不到就略過，不中斷
                
    if not relevant_docs:
        # 完全沒配對到任何檔案時，保守退回全量，防止漏看資料
        return formatted_input
        
    return f"{profile_text}\n\nUploaded Documents:\n" + "\n\n".join(relevant_docs)

def is_rule_covered(rule: dict, issues: list) -> bool:
    """
    【功能】判斷某條 Neo4j 確定性規則 (rule) 是否已被 Planner 的 LLM 偵測結果
    (detected_issues) 所覆蓋，避免重複加入。

    【為什麼需要這個？】
    Planner LLM 和 Neo4j 規則庫是兩個獨立偵測系統。
    如果 LLM 已經偵測到某個問題（例如 Schedule C 缺失），
    Neo4j 也確認了同一條規則違反，就不需要重複加入這個 issue，
    否則最終報告會出現重複內容。

    【比對策略】
    1. 拿 rule 的 id、message、category（轉小寫）跟 issue 的 issue_name、target_component 比對。
    2. 先用 rule_id 做字串包含比對（精確）。
    3. 再用 forms 白名單（如 "schedule c"、"1099" 等）交叉比對（模糊）。

    Args:
        rule: Neo4j 查到的單條違反規則 dict
        issues: Planner LLM 回傳的 detected_issues 清單

    Returns:
        True 表示已被覆蓋（不需重複加入），False 表示需要新增
    """
    rule_msg = rule["message"].lower()
    rule_id = rule["id"].lower()
    rule_cat = rule.get("category", "").lower()
    for issue in issues:
        issue_name = issue.get("issue_name", "").lower()
        target_comp = issue.get("target_component", "").lower()
        if rule_id in issue_name or rule_id in target_comp:
            return True
        # 用常見表單名稱做模糊交叉比對
        forms = ["schedule a", "schedule b", "schedule c", "schedule d", "schedule e", "schedule f",
                 "w-2", "1099", "1098", "5498", "8863", "2441", "5695", "8936", "8962",
                 "8812", "8995", "8606", "8824", "6252", "8582", "6251", "5329", "8960",
                 "8615", "6198", "8938"]
        for form in forms:
            if form in rule_msg or form in rule_cat:
                if form in issue_name or form in target_comp:
                    return True
    return False

async def run_map_task(llm: GeminiLLM, issue_name: str, target_component: str, input_data: str, violated_rules: list, delay: float) -> dict:
    """
    【功能】Map-Reduce 流程中的「Map 任務」—— 針對單一 issue 做深度合規稽核。

    【在整體流程中的位置】
    Planner 輸出 N 個 issue → 同時並發啟動 N 個 run_map_task coroutine →
    每個任務各自打一次 LLM → 結果再由 Reduce 拼接成最終報告。

    【設計重點】
    - delay 參數：Gemini 並發時為避免 rate limit，各任務之間加入隨機延遲。
    - Ollama 模型因本地執行無 rate limit 問題，delay 固定為 0.0。
    - 輸入使用 extract_relevant_context() 後的精簡版本（物理隔離）。
    - 傳入 violated_rules 讓 LLM 能整合確定性規則結論。

    Args:
        llm: GeminiLLM 或 OllamaLLM 實例
        issue_name: Planner 識別出的問題名稱
        target_component: 受影響的表單或科目
        input_data: 已物理隔離的相關上下文
        violated_rules: Neo4j 確定性規則評估結果
        delay: 啟動前等待的秒數（避免 Gemini rate limit）

    Returns:
        dict 包含 issue_name, target_component, success, reason(稽核分析文字),
        latency, tokens, prompt（供 debug 用）
    """
    if delay > 0:
        await asyncio.sleep(delay)
    
    if violated_rules:
        violated_rules_str = "\n".join([
            f"- {r['id']} ({r['severity']}): {r['message']}"
            for r in violated_rules
        ])
    else:
        violated_rules_str = "（無偵測到相關的確定性違反規則）"
    
    human_content = MAP_HUMAN_PROMPT_TEMPLATE.format(
        input_data=input_data,
        issue_name=issue_name,
        target_component=target_component,
        violated_rules=violated_rules_str
    )
    
    messages = [
        SystemMessage(content=MAP_SYSTEM_INSTRUCTION),
        HumanMessage(content=human_content)
    ]
    
    t0 = time.time()
    try:
        # run_in_executor 讓同步的 llm.invoke() 在 thread pool 跑，不阻塞 event loop
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, lambda: llm.invoke(messages))
        latency = time.time() - t0
        return {
            "issue_name": issue_name,
            "target_component": target_component,
            "success": True,
            "reason": response.content.strip(),
            "latency": latency,
            "tokens": response.usage,
            "prompt": {
                "system": MAP_SYSTEM_INSTRUCTION,
                "user": human_content
            }
        }
    except Exception as e:
        latency = time.time() - t0
        return {
            "issue_name": issue_name,
            "target_component": target_component,
            "success": False,
            "reason": None,
            "latency": latency,
            "tokens": {},
            "error": str(e),
            "prompt": {
                "system": MAP_SYSTEM_INSTRUCTION,
                "user": human_content
            }
        }

async def run_map_reduce_flow(input_data: str, model_name: str, api_key: str) -> dict:
    """
    【功能】主診斷流程 A：Map-Reduce 架構（無狀態、並發）。

    【整體三階段流程】
    ┌─────────────────────────────────────────────────────┐
    │ Phase 1: Planner                                    │
    │  → LLM 掃描全量文件，輸出 N 個 detected_issues JSON  │
    │  → Neo4j 確定性規則評估，補充未覆蓋的違反規則         │
    ├─────────────────────────────────────────────────────┤
    │ Phase 2: Map (並發)                                 │
    │  → 對每個 issue 啟動一個獨立 coroutine               │
    │  → 每個 coroutine 打一次 LLM 做深度稽核分析          │
    │  → Gemini: asyncio.gather 並發；Ollama: 順序執行     │
    ├─────────────────────────────────────────────────────┤
    │ Phase 3: Reduce                                     │
    │  → 把所有 Map 任務的 Markdown 稽核卡片拼接成最終報告  │
    │  → 統計總 token 消耗                                 │
    └─────────────────────────────────────────────────────┘

    【vs Looping Flow 的差異】
    - Map-Reduce: 每個 issue 是獨立 LLM call，無狀態、可並發
    - Looping: 同一個 conversation history 中連續問多個 issue，有狀態

    Args:
        input_data: 原始使用者輸入（JSON 字串）
        model_name: LLM 模型名稱（"gemini-*" 或 "模型名:版本"）
        api_key: Gemini API Key

    Returns:
        dict 包含 success, content(最終報告), latency, tokens,
        error, raw_json(Planner 輸出), debug_steps
    """
    t0 = time.time()
    formatted_input = format_input_data(input_data)

    # 判斷使用 Gemini 還是 Ollama（本地模型）
    llm_provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    is_ollama = False
    if model_name and "gemini" in model_name.lower():
        is_ollama = False
    elif model_name and ":" in model_name:
        is_ollama = True
    else:
        is_ollama = (llm_provider == "ollama")

    if is_ollama:
        llm = OllamaLLM(model_name=model_name, temperature=0.0, timeout=1800.0)
    else:
        llm = GeminiLLM(model_name=model_name, api_key=api_key, temperature=0.0)
    
    debug_steps = []
    
    # ─── Phase 1: Planner ───────────────────────────────────────────
    # LLM 閱讀全量文件，輸出潛在問題清單（JSON 格式）
    planner_messages = [
        SystemMessage(content=PLANNER_SYSTEM_INSTRUCTION),
        HumanMessage(content=PLANNER_HUMAN_PROMPT_TEMPLATE.format(input_data=formatted_input))
    ]
    
    try:
        loop = asyncio.get_running_loop()
        if is_ollama:
            planner_resp = await loop.run_in_executor(
                None, 
                lambda: llm.invoke(planner_messages)
            )
        else:
            # Gemini 可以要求 JSON 格式輸出，減少解析失敗率
            planner_resp = await loop.run_in_executor(
                None, 
                lambda: llm.invoke(planner_messages, response_mime_type="application/json")
            )
        planner_content = planner_resp.content.strip()
        
        # 移除 gemma4/qwen3 等 thinking 模型的 <think>...</think> 推理區塊
        import rule_evaluator as _re_mod
        content = _re_mod._strip_think_tags(planner_content)
        match = re.search(r"\{.*\}", content, re.DOTALL)
        try:
            from json_repair import repair_json
            # json_repair 處理 LLM 輸出的不完整或格式錯誤 JSON
            repaired_content = repair_json(content)
            planner_data = json.loads(repaired_content)
        except Exception as json_err:
            raise ValueError(f"JSON 格式解析失敗: {str(json_err)}。LLM 原始回應內容: {planner_content}")
        if not isinstance(planner_data, dict):
            raise ValueError(f"Planner returned invalid type: {planner_content}")
            
        detected_issues = planner_data.get("detected_issues", [])
        
        # ─── Phase 1.5: 確定性規則評估（Neo4j）──────────────────────
        # 呼叫 rule_evaluator 模組：
        # 1. extract_taxpayer_context: LLM 提取結構化上下文（filing_status, fields, docs）
        # 2. evaluate_compliance_rules: 連線 Neo4j，執行 TaxRuleEvaluator 評估所有 ValidationRule 節點
        try:
            context = rule_evaluator.extract_taxpayer_context(formatted_input, model_name, api_key)
            violated_rules, neo4j_debug = rule_evaluator.evaluate_compliance_rules(context, return_debug=True)
        except Exception as re_err:
            print(f"[missing_form_detector] 規則評估異常: {re_err}。跳過規則庫。")
            violated_rules = []
            neo4j_debug = {"neo4j_query": "", "neo4j_raw_result": []}

        # 把 Neo4j 發現但 Planner LLM 沒覆蓋的規則違反，補充為新的 mock issue
        for rule in violated_rules:
            if not is_rule_covered(rule, detected_issues):
                detected_issues.append({
                    "id": f"RULE_{rule['id']}",
                    "issue_name": f"確定性規則違反：{rule['message']}",
                    "target_component": rule.get("category", "Tax Compliance"),
                    "source_docs": []
                })
        
        # 紀錄 Debug 資訊
        debug_steps.append({
            "phase": "Planner Phase (第一階段)",
            "prompts": [
                {"role": "system", "content": PLANNER_SYSTEM_INSTRUCTION},
                {"role": "user", "content": PLANNER_HUMAN_PROMPT_TEMPLATE.format(input_data=formatted_input)}
            ],
            "output": planner_content
        })
        debug_steps.append({
            "phase": "Neo4j Rules Evaluation (確定性規則評估)",
            "neo4j_query": neo4j_debug.get("neo4j_query", ""),
            "neo4j_raw_result": neo4j_debug.get("neo4j_raw_result", []),
            "violated_rules": violated_rules,
            "extracted_context": context
        })
    except Exception as e:
        return {
            "success": False,
            "content": None,
            "latency": time.time() - t0,
            "tokens": {},
            "error": f"Planner 階段失敗: {str(e)}"
        }

    # ─── Phase 2: Map（並發深度稽核）───────────────────────────────
    is_ollama = isinstance(llm, OllamaLLM)
    
    map_tasks = []
    for i, issue in enumerate(detected_issues):
        issue_name = issue.get("issue_name", "")
        target_component = issue.get("target_component", "")
        source_docs = issue.get("source_docs", [])
        
        # 物理隔離：只傳給這個 issue 相關的文件
        isolated_input = extract_relevant_context(formatted_input, source_docs)
        
        # Gemini 並發時加入隨機延遲（0.1~0.3s per task）避免 rate limit
        delay = i * random.uniform(0.1, 0.3) if not is_ollama else 0.0
        map_tasks.append((issue_name, target_component, isolated_input, violated_rules, delay))

    if is_ollama:
        # Ollama 本地模型不支援並發，逐一執行
        print(f"[missing_form_detector] Ollama model detected. Running Map tasks sequentially...")
        map_results = []
        for issue_name, target_comp, isolated_in, v_rules, delay in map_tasks:
            res = await run_map_task(llm, issue_name, target_comp, isolated_in, v_rules, 0.0)
            map_results.append(res)
            await asyncio.sleep(0.5)
    else:
        # Gemini：asyncio.gather 同時並發所有 Map 任務
        tasks = [run_map_task(llm, t[0], t[1], t[2], t[3], t[4]) for t in map_tasks]
        map_results = await asyncio.gather(*tasks)
    
    # 若有任何 Map 任務失敗，整體回傳 failure
    failed_maps = [r for r in map_results if not r["success"]]
    if failed_maps:
        return {
            "success": False,
            "content": None,
            "latency": time.time() - t0,
            "tokens": {},
            "error": f"部分分析任務失敗: {failed_maps[0]['error']}"
        }
        
    # 紀錄 Map Phase Debug 資訊
    map_tasks_debug = []
    for r in map_results:
        map_tasks_debug.append({
            "form_name": r["issue_name"],
            "prompt_system": r.get("prompt", {}).get("system"),
            "prompt_user": r.get("prompt", {}).get("user"),
            "output": r.get("reason")
        })
    debug_steps.append({
        "phase": "Map Phase (第二階段)",
        "tasks": map_tasks_debug
    })
    
    # ─── Phase 3: Reduce（拼接成最終報告）───────────────────────────
    # 直接把所有 Map 任務的 Markdown 稽核卡片文字用換行拼接
    final_content = "\n\n".join([r["reason"] for r in map_results if r["success"]])
    latency = time.time() - t0
    
    # 統計總 token 消耗（Planner + 所有 Map 任務）
    total_tokens = {
        "promptTokenCount": planner_resp.usage.get("promptTokenCount", 0),
        "candidatesTokenCount": planner_resp.usage.get("candidatesTokenCount", 0),
        "totalTokenCount": planner_resp.usage.get("totalTokenCount", 0)
    }
    for r in map_results:
        u = r.get("tokens", {})
        total_tokens["promptTokenCount"] += u.get("promptTokenCount", 0)
        total_tokens["candidatesTokenCount"] += u.get("candidatesTokenCount", 0)
        total_tokens["totalTokenCount"] += u.get("totalTokenCount", 0)

    return {
        "success": True,
        "content": final_content,
        "latency": latency,
        "tokens": total_tokens,
        "error": None,
        "raw_json": planner_data,
        "debug_steps": debug_steps
    }

async def run_looping_flow(input_data: str, model_name: str, api_key: str) -> dict:
    """
    【功能】主診斷流程 B：Stateful Looping 架構（有狀態、同一 conversation 中連續問答）。

    【整體三階段流程】
    ┌─────────────────────────────────────────────────────────────┐
    │ Phase 1: Scanner（等同 Map-Reduce 的 Planner）               │
    │  → LLM 掃描全量文件，輸出 N 個 detected_issues JSON          │
    │  → Neo4j 確定性規則評估，補充未覆蓋的違反規則                 │
    ├─────────────────────────────────────────────────────────────┤
    │ Phase 2: Stateful Looping（有狀態連續對話）                  │
    │  → 初始化一個 LangChain conversation history                  │
    │  → 第一個 issue：發送完整的 input_data + issue 資訊           │
    │  → 第 2、3...N 個 issue：只發送 issue_name（LLM 記得上下文）  │
    │  → 每次 LLM 回答後，把 AI 回覆加入 history（保持對話狀態）   │
    ├─────────────────────────────────────────────────────────────┤
    │ Phase 3: Reduce（同 Map-Reduce）                            │
    │  → 拼接所有 issue 的稽核分析文字                             │
    └─────────────────────────────────────────────────────────────┘

    【vs Map-Reduce Flow 的差異】
    - 有狀態：LLM 在同一個 conversation 中處理所有 issue，可能利用前面的分析結果
    - 無並發：必須順序執行（後一個問題依賴前一個的 history）
    - Token 消耗較高：history 會隨 issue 數量增長
    - 適合需要 LLM 跨 issue 互相參照的情境

    Args:
        input_data: 原始使用者輸入（JSON 字串）
        model_name: LLM 模型名稱
        api_key: Gemini API Key

    Returns:
        dict 包含 success, content, latency, tokens, error, raw_json, debug_steps
    """
    t0 = time.time()
    formatted_input = format_input_data(input_data)

    # 判斷使用 Gemini 還是 Ollama
    llm_provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    is_ollama = False
    if model_name and "gemini" in model_name.lower():
        is_ollama = False
    elif model_name and ":" in model_name:
        is_ollama = True
    else:
        is_ollama = (llm_provider == "ollama")

    if is_ollama:
        llm = OllamaLLM(model_name=model_name, temperature=0.0, timeout=1800.0)
    else:
        llm = GeminiLLM(model_name=model_name, api_key=api_key, temperature=0.0)
    
    debug_steps = []
    
    # ─── Phase 1: Scanner（同 Planner）────────────────────────────
    scanner_messages = [
        SystemMessage(content=PLANNER_SYSTEM_INSTRUCTION),
        HumanMessage(content=PLANNER_HUMAN_PROMPT_TEMPLATE.format(input_data=formatted_input))
    ]
    
    try:
        loop = asyncio.get_running_loop()
        if is_ollama:
            scanner_resp = await loop.run_in_executor(
                None, 
                lambda: llm.invoke(scanner_messages)
            )
        else:
            scanner_resp = await loop.run_in_executor(
                None, 
                lambda: llm.invoke(scanner_messages, response_mime_type="application/json")
            )
        scanner_content = scanner_resp.content.strip()
        
        # 移除 thinking 模型的推理標籤
        import rule_evaluator as _re_mod
        content = _re_mod._strip_think_tags(scanner_content)
        match = re.search(r"\{.*\}", content, re.DOTALL)
        try:
            from json_repair import repair_json
            repaired_content = repair_json(content)
            scanner_data = json.loads(repaired_content)
        except Exception as json_err:
            raise ValueError(f"JSON 格式解析失敗: {str(json_err)}。LLM 原始回應內容: {scanner_content}")
        if not isinstance(scanner_data, dict):
            raise ValueError(f"Scanner returned invalid type: {scanner_content}")
            
        detected_issues = scanner_data.get("detected_issues", [])
        
        # ─── Phase 1.5: 確定性規則評估（Neo4j）──────────────────────
        try:
            context = rule_evaluator.extract_taxpayer_context(formatted_input, model_name, api_key)
            violated_rules, neo4j_debug = rule_evaluator.evaluate_compliance_rules(context, return_debug=True)
        except Exception as re_err:
            print(f"[missing_form_detector] 規則評估異常: {re_err}。跳過規則庫。")
            violated_rules = []
            neo4j_debug = {"neo4j_query": "", "neo4j_raw_result": []}

        # 補充 Planner 未覆蓋的規則違反
        for rule in violated_rules:
            if not is_rule_covered(rule, detected_issues):
                detected_issues.append({
                    "id": f"RULE_{rule['id']}",
                    "issue_name": f"確定性規則違反：{rule['message']}",
                    "target_component": rule.get("category", "Tax Compliance"),
                    "source_docs": []
                })
        
        # 準備確定性規則的文字描述，供 Loop 中的 LLM 參考
        if violated_rules:
            violated_rules_str = "\n".join([
                f"- {r['id']} ({r['severity']}): {r['message']}"
                for r in violated_rules
            ])
        else:
            violated_rules_str = "（無偵測到相關的確定性違反規則）"

        # 紀錄 Debug 資訊
        debug_steps.append({
            "phase": "Scanner Phase (第一階段)",
            "prompts": [
                {"role": "system", "content": PLANNER_SYSTEM_INSTRUCTION},
                {"role": "user", "content": PLANNER_HUMAN_PROMPT_TEMPLATE.format(input_data=formatted_input)}
            ],
            "output": scanner_content
        })
        debug_steps.append({
            "phase": "Neo4j Rules Evaluation (確定性規則評估)",
            "neo4j_query": neo4j_debug.get("neo4j_query", ""),
            "neo4j_raw_result": neo4j_debug.get("neo4j_raw_result", []),
            "violated_rules": violated_rules,
            "extracted_context": context
        })
    except Exception as e:
        return {
            "success": False,
            "content": None,
            "latency": time.time() - t0,
            "tokens": {},
            "error": f"Scanner 階段失敗: {str(e)}"
        }

    total_tokens = {
        "promptTokenCount": scanner_resp.usage.get("promptTokenCount", 0),
        "candidatesTokenCount": scanner_resp.usage.get("candidatesTokenCount", 0),
        "totalTokenCount": scanner_resp.usage.get("totalTokenCount", 0)
    }

    issue_items = []
    
    # ─── Phase 2: Stateful Looping ──────────────────────────────────
    # 初始化 conversation history（只有 System 指令）
    history = [SystemMessage(content=LOOP_SYSTEM_INSTRUCTION)]
    loop_history = [{"role": "system", "content": LOOP_SYSTEM_INSTRUCTION}]
    loop = asyncio.get_running_loop()
    
    for i, issue in enumerate(detected_issues):
        issue_name = issue.get("issue_name", "")
        target_component = issue.get("target_component", "")
        source_docs = issue.get("source_docs", [])
        
        # 對每個 issue 做物理隔離
        isolated_input = extract_relevant_context(formatted_input, source_docs)
        
        if len(history) == 1:
            # 第一個 issue：發完整的 input_data + issue + 規則
            human_content = LOOP_HUMAN_PROMPT_TEMPLATE.format(
                input_data=isolated_input,
                issue_name=issue_name,
                target_component=target_component,
                violated_rules=violated_rules_str
            )
        else:
            # 後續 issue：只發 issue_name（LLM 從 history 記得原始文件）
            human_content = LOOP_HUMAN_FOLLOWUP_TEMPLATE.format(
                issue_name=issue_name,
                violated_rules=violated_rules_str
            )
            
        history.append(HumanMessage(content=human_content))
        loop_history.append({"role": "user", "content": human_content})
        
        try:
            await asyncio.sleep(0.2)  # 輕微延遲避免 API 過載
            resp = await loop.run_in_executor(None, lambda: llm.invoke(history))
            reason = resp.content.strip()
            issue_items.append(reason)
            
            # 把 AI 回覆加入 history，維持對話狀態
            history.append(AIMessage(content=resp.content))
            loop_history.append({"role": "assistant", "content": resp.content})
            
            u = resp.usage
            total_tokens["promptTokenCount"] += u.get("promptTokenCount", 0)
            total_tokens["candidatesTokenCount"] += u.get("candidatesTokenCount", 0)
            total_tokens["totalTokenCount"] += u.get("totalTokenCount", 0)
        except Exception as e:
            return {
                "success": False,
                "content": None,
                "latency": time.time() - t0,
                "tokens": {},
                "error": f"Stateful loop 失敗於 {issue_name}: {str(e)}"
            }

    # 紀錄整個 Loop 的對話歷史
    debug_steps.append({
        "phase": "Stateful Looping Session (第二階段)",
        "history": loop_history
    })

    # ─── Phase 3: Reduce ────────────────────────────────────────────
    final_content = "\n\n".join(issue_items)
    latency = time.time() - t0
    
    return {
        "success": True,
        "content": final_content,
        "latency": latency,
        "tokens": total_tokens,
        "error": None,
        "raw_json": scanner_data,
        "debug_steps": debug_steps
    }

def get_michael_chen_mock_data() -> str:
    """
    【功能】回傳 Michael Chen 的測試用假資料（JSON 字串）。

    Michael Chen 的情境包含：
    - W-2 雇員 + 自雇副業（Schedule C）
    - 股票交易（Brokerage → 可能缺 1099-B）
    - 房貸 1098（可能需要 Schedule A）
    - 托兒費（可能需要 Form 2441 Child Care Credit）
    - 學費（可能需要 Form 1098-T 教育抵免）
    - 前年度 capital loss carryover

    用途：開發與回歸測試，不用每次手動準備測試資料。
    """
    data = {
        "taxpayer_profile": {
            "Name": "Michael Chen",
            "Filing Status": "Married Filing Jointly",
            "Dependents": "1 child",
            "Occupation": "Software consultant (self-employed side business)",
            "Primary Job": "W-2 employee",
            "State": "California",
            "Tax Year": "2025"
        },
        "uploaded_documents": [
            {"file_name": "Form_W2.pdf", "content": "Employer: ABC Tech Inc., Wages: $148,000, Federal & State withholding present"},
            {"file_name": "Form_1099_INT.pdf", "content": "Interest income: $420"},
            {"file_name": "Form_1099_DIV.pdf", "content": "Ordinary dividends: $1,260, Qualified dividends: $980"},
            {"file_name": "Brokerage_Summary.pdf", "content": "Shows stock sales occurred during the year, Mentions 'see attached Form 1099-B for transaction details'"},
            {"file_name": "Mortgage_Form_1098.pdf", "content": "Mortgage interest paid: $18,400, Property taxes paid: $7,200"},
            {"file_name": "Childcare_Statement.pdf", "content": "Daycare provider name and EIN included, Total paid: $9,600"},
            {"file_name": "Tuition_Statement.pdf", "content": "University billing statement for spouse, Tuition paid: $6,200"},
            {"file_name": "Business_Expense_Spreadsheet.xlsx", "content": "Sole proprietor consulting activity, software subscriptions, mileage, home office, Total: $12,450"},
            {"file_name": "Bank_Statement.pdf", "content": "Shows several incoming payments from Stripe payout, Consulting payment, Client ACH, Total side business: $21,300"},
            {"file_name": "Prior_Year_Return_2024.pdf", "content": "Shows capital loss carryover, Schedule C business, Child Care Credit, education credit"}
        ]
    }
    return json.dumps(data, indent=2, ensure_ascii=False)

def get_rivera_mock_data() -> str:
    """
    【功能】回傳 Marcus and Elena Rivera 的測試用假資料（JSON 字串）。

    Rivera 夫婦的情境更複雜，包含：
    - Elena W-2（City Firefighter，有 Retirement Plan Box 13）
    - Marcus W-2 + QuickBooks P&L（自有寵物店，Schedule C）
    - 混合餐費/娛樂費用（Rivera Cats Stadium 可能不可扣）
    - Las Vegas 商務+旅遊混合行程（需比例分攤）
    - 政府罰款 $300（IRC §162(f) 明確不可扣除）
    - Form 1098 房貸利息（Schedule A）
    - 政治獻金 $250（不可扣除）
    - 傳統 IRA 供款 $7,000（可能觸發 IRA deductibility 限制）
    - 前年度資本損失 carryover + 未申報折舊的租賃房產（Schedule E）

    用途：回歸測試，驗證系統是否能正確識別多元複雜的稅務風險。
    """
    data = {
        "taxpayer_profile": {
            "Name": "Marcus and Elena Rivera",
            "Filing Status": "Married Filing Jointly",
            "Dependents": "2 children",
            "State": "California (Sacramento)",
            "Tax Year": "2024",
            "Elena Primary Job": "City Firefighter",
            "Marcus Business Owner": "Creature Comforts (Pet Supply Store)"
        },
        "uploaded_documents": [
            {
                "file_name": "Elena_W2.pdf",
                "content": "Form W-2 Wage and Tax Statement 2024. Employee: Elena Rivera. Employer: City of Sacramento. Box 1: Wages, tips, other comp: $54,000. Box 2: Federal income tax withheld: $5,200. Box 13: Retirement plan checked. Box 15: State: CA, State wages: $54,000, State tax withheld: $2,100."
            },
            {
                "file_name": "Marcus_W2.pdf",
                "content": "Form W-2 Wage and Tax Statement 2024. Employee: Marcus Rivera. Employer: Creature Comforts LLC. Box 1: Wages, tips, other comp: $46,000. Box 2: Federal income tax withheld: $3,800. Box 13: Retirement plan NOT checked. Box 15: State: CA, State wages: $46,000, State tax withheld: $1,400."
            },
            {
                "file_name": "Creature_Comforts_QuickBooks_PL.json",
                "content": "Creature Comforts Profit and Loss Statement. Period: Jan 1 - Dec 31, 2024. Gross Profit / Gross Revenue: $191,400. Expenses: Cost of Goods Sold / Inventory: $68,000; Employee Staff Wages: $32,000; Rent and Utilities: $14,000; Insurance: $3,500; Meals and Entertainment: $1,800; Business Travel: $1,900; Miscellaneous Expense: $300; Net Income: $70,800."
            },
            {
                "file_name": "Receipts_Meals_Entertainment_Travel.zip",
                "content": "Receipt Bundle Details: \n1. Receipt from Golden State Grill: Business travel dinner with vendor, Date: 4/12/2024, Amount: $550.\n2. Receipt from River Cats Stadium: Minor league team season tickets, Date: 5/1/2024, Amount: $700.\n3. Receipt from Sacramento Catering: Employee annual holiday party, Date: 12/20/2024, Amount: $400.\n4. Receipt from Pizza Depot: Overtime meals for staff during inventory check, Date: 10/15/2024, Amount: $150.\n5. National Pet Retail Conference Travel Log: Marcus attended conference in Las Vegas. Conference dates: Oct 20-21 (2 days). Sightseeing/vacation dates: Oct 22-24 (3 days). Total expenses in bundle: Airfare: $500, Lodging: 5 nights at $200/night = $1,000, Meals: $400. Total trip expenses of $1,900 included in QuickBooks travel expenses."
            },
            {
                "file_name": "Receipt_City_Fine.pdf",
                "content": "City of Sacramento Code Enforcement Department. Notice of Violation Penalty. Business Entity: Creature Comforts. Violation: Failure to post a valid city business license on premises. Citation Fine Paid: $300. Payment date: 8/14/2024. Included in QuickBooks Miscellaneous Expenses."
            },
            {
                "file_name": "Mortgage_Form_1098.pdf",
                "content": "Form 1098 Mortgage Interest Statement 2024. Payer: Marcus and Elena Rivera. Lender: Golden West Bank. Box 1: Mortgage interest: $9,800. Box 10: Real estate taxes paid on primary residence: $2,600."
            },
            {
                "file_name": "Donation_Receipts.pdf",
                "content": "Sacramento Grace Church. Annual Contribution Statement 2024. Donor: Marcus and Elena Rivera. Total deductible charitable donations received: $5,400."
            },
            {
                "file_name": "Political_Contribution.pdf",
                "content": "Friends of Assemblymember Elena Rivera Campaign. Campaign Contribution Receipt. Contributor: Marcus Rivera. Contribution Amount: $250. Payment Method: Credit Card."
            },
            {
                "file_name": "Traditional_IRA_Receipt.pdf",
                "content": "Fidelity Investments. Traditional IRA Contribution Statement 2024. Account Owner: Marcus Rivera. Traditional IRA contribution amount: $7,000. Contribution date: 4/10/2024."
            },
            {
                "file_name": "Prior_Year_Return_2023.pdf",
                "content": "Prior Year Federal Income Tax Return Form 1040 (Tax Year 2023). Schedule D Capital Gains and Losses: Shows long-term capital loss carryover of $990 to 2024. Schedule E Supplemental Income and Loss (Part I): Rental Condo Location: 1200 K St, Sacramento, CA 95814. Gross Rent Received: $16,650. Rental Expenses: Insurance: $900, Mortgage Interest: $4,800, Property Taxes: $2,400, Maintenance/Misc: $550. Depreciation Expense: $0 (Depreciation was never claimed or filed on previous tax returns for this property)."
            }
        ]
    }
    return json.dumps(data, indent=2, ensure_ascii=False)
