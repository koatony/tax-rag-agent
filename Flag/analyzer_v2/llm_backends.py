# 對 Gemini 和 Gemma（Ollama）兩種後端發出 PLANNER/MAP 呼叫。

import json
import re

from .prompts import MAP_SYSTEM_PROMPT, PLANNER_SYSTEM_PROMPT, REINFORCE


def _parse_json(raw: str) -> dict:
    # 去除 LLM 回應中的 markdown code-fence，並解析第一個完整的 {...} 物件；
    # 找不到合法 JSON 物件時丟出 ValueError。
    # 為什麼：LLM 常常會在 JSON 外面包一層 ```json ... ``` 或加解釋文字，
    # 即使 prompt 已要求「純 JSON」，仍不保證每次都乖乖照做；用尋找第一個
    # `{` 到最後一個 `}` 的方式，比嚴格 json.loads(resp.text) 更能容錯。
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No valid JSON object in response:\n{raw[:300]}")
    return json.loads(cleaned[start: end + 1])


def _kg_context(issue: dict, use_kg: bool) -> str:
    # 針對單一 issue 查詢知識圖譜（Neo4j + bge-m3，透過 kg_retriever_v2）
    # 取得相關法規上下文，格式化後準備注入 MAP prompt；use_kg 為 False 時
    # 回傳空字串，查詢失敗則回傳 "[KG unavailable]" 提示文字。
    # 為什麼：use_kg 是使用者可選的加值功能，不是核心流程的必要條件；
    # 若 Neo4j/Ollama 連線失敗，分析仍要能跑完（只是少了 KG 補充資訊），
    # 所以這裡用 try/except 吞掉例外，而不是往外拋出中斷整個 MAP 呼叫。
    if not use_kg:
        return ""
    try:
        from ..kg_retriever_v2 import query_kg_for_issue
        # 為什麼要傳 target_component：
        # target_component 提供了稅務申報書表格/科目的具體上下文（例如 "Schedule C / Travel Expense"），
        # 與較簡短的 issue_name 組合起來（"issue_name target_component"）作為向量查詢語句，
        # 能大幅提高與知識圖譜中 IRS 法規節點（Rule nodes）比對時的語意檢索精確度。
        ctx = query_kg_for_issue(
            issue.get("issue_name", ""),
            issue.get("target_component", ""),
        )
        return f"\n\n{ctx}\n" if ctx else ""
    except Exception as e:
        return f"\n\n[KG unavailable: {e}]\n"


# ---------------------------------------------------------------------------
# Gemini backend
# ---------------------------------------------------------------------------

async def _gemini_planner(model_name: str, extracted_data: dict, source_filename: str) -> list[dict]:
    # Gemini backend 的 PLANNER 階段：呼叫一次，掃過完整財務資料，
    # 回傳 detected_issues 清單交給後續 MAP 階段逐一處理。
    # 為什麼：先用一次呼叫掃過全部財務資料列出「有哪些問題」，而不是一次
    # 就叫 LLM 把每個問題都分析到底——這樣可以把「找問題」和「深入分析
    # 單一問題」拆開，讓後續 MAP 階段可以平行處理、且每個問題的分析不會
    # 被其他問題的內容互相干擾（context 較乾淨、輸出也較穩定）。
    import os
    import google.generativeai as genai
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
    model = genai.GenerativeModel(model_name=model_name, system_instruction=PLANNER_SYSTEM_PROMPT)
    msg = (
        f"Source file: {source_filename}\n\n"
        f"Financial data:\n{json.dumps(extracted_data, ensure_ascii=False, indent=2)}\n\n"
        f"Identify all potential tax compliance issues.\n\n{REINFORCE}"
    )
    resp = await model.generate_content_async(msg, generation_config={"temperature": 0})
    return _parse_json(resp.text).get("detected_issues", [])


async def _gemini_map(model_name: str, issue: dict, extracted_data: dict, source_filename: str, use_kg: bool) -> dict:
    # Gemini backend 的 MAP 階段：每個 detected issue 各呼叫一次，
    # 產出單一 flag JSON 物件，可選擇性地附加 KG 上下文。
    # 為什麼：每個 issue 各自呼叫一次 LLM（而非一次分析全部），是為了讓
    # orchestrator.py 可以用 asyncio.gather 平行送出所有 MAP 呼叫，加速整體
    # 分析時間；同時單一 issue 分析失敗時，只會讓那一個 flag 出錯
    # （被 orchestrator 收進 _errors），不會拖垮其他 issue 的分析結果。
    import os
    import google.generativeai as genai
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
    kg_block = _kg_context(issue, use_kg)
    model = genai.GenerativeModel(model_name=model_name, system_instruction=MAP_SYSTEM_PROMPT)
    msg = (
        f"Target issue:\n{json.dumps(issue, ensure_ascii=False, indent=2)}\n\n"
        f"Full financial context (source file: {source_filename}):\n"
        f"{json.dumps(extracted_data, ensure_ascii=False, indent=2)}"
        f"{kg_block}"
        f"\n\nReturn a single flag JSON object.\n\n{REINFORCE}"
    )
    resp = await model.generate_content_async(msg, generation_config={"temperature": 0})
    return _parse_json(resp.text)


# ---------------------------------------------------------------------------
# Gemma (Ollama) backend
# ---------------------------------------------------------------------------

OLLAMA_HOST = "http://140.115.54.89:11434"


async def _gemma_planner(extracted_data: dict, source_filename: str, think: bool) -> list[dict]:
    # Gemma (Ollama) backend 的 PLANNER 階段，與 _gemini_planner 角色相同，
    # 改打自架的 gemma4:31b 模型。
    # 為什麼：獨立出 Gemma 版本而非共用 Gemini 那支函式，是因為呼叫介面
    # 不同（Ollama AsyncClient.chat 用 messages 列表 + think 參數，而非
    # google-generativeai 的 GenerativeModel），且 Gemma 是內部自架、免費
    # 的選項，方便沒有 GEMINI_API_KEY 或想省 cloud 成本時使用。
    from ollama import AsyncClient
    client = AsyncClient(host=OLLAMA_HOST)
    msg = (
        f"Source file: {source_filename}\n\n"
        f"Financial data:\n{json.dumps(extracted_data, ensure_ascii=False, indent=2)}\n\n"
        f"Identify all potential tax compliance issues.\n\n{REINFORCE}"
    )
    resp = await client.chat(
        model="gemma4:31b",
        messages=[
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": msg},
            {"role": "system", "content": REINFORCE},
        ],
        options={"temperature": 0, "repeat_penalty": 1.2, "num_ctx": 32768},
        think=think,
    )
    return _parse_json(resp.message.content).get("detected_issues", [])


async def _gemma_map(issue: dict, extracted_data: dict, source_filename: str, think: bool, use_kg: bool) -> dict:
    # Gemma (Ollama) backend 的 MAP 階段，與 _gemini_map 角色相同，
    # 改打自架的 gemma4:31b 模型。
    # 為什麼：think 參數讓 Gemma 可以開啟「延伸推理」模式（較慢但可能較準），
    # 這是 Gemini 沒有對應選項的功能，所以獨立成一支函式而非參數化共用。
    from ollama import AsyncClient
    kg_block = _kg_context(issue, use_kg)
    client = AsyncClient(host=OLLAMA_HOST)
    msg = (
        f"Target issue:\n{json.dumps(issue, ensure_ascii=False, indent=2)}\n\n"
        f"Full financial context (source file: {source_filename}):\n"
        f"{json.dumps(extracted_data, ensure_ascii=False, indent=2)}"
        f"{kg_block}"
        f"\n\nReturn a single flag JSON object.\n\n{REINFORCE}"
    )
    resp = await client.chat(
        model="gemma4:31b",
        messages=[
            {"role": "system", "content": MAP_SYSTEM_PROMPT},
            {"role": "user", "content": msg},
            {"role": "system", "content": REINFORCE},
        ],
        options={"temperature": 0, "repeat_penalty": 1.2, "num_ctx": 32768},
        think=think,
    )
    return _parse_json(resp.message.content)
