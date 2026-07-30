"""表單狀態分析器的 LLM 後端模組（包含 Gemini 與 Gemma）。"""

import json
import re
import os
import google.generativeai as genai
from ollama import AsyncClient
from .prompts import FORM_PLANNER_SYSTEM_PROMPT, FORM_MAP_SYSTEM_PROMPT, REINFORCE

OLLAMA_HOST = "http://140.115.54.89:11434"

def _parse_json(raw: str) -> dict:
    """從 LLM 回應中擷取並解析第一個合法的 JSON 物件。"""
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"回應中沒有合法的 JSON 物件：\n{raw[:300]}")
    return json.loads(cleaned[start: end + 1])


def _kg_form_context(form_name: str, use_kg: bool) -> str:
    """透過 Neo4j 知識圖譜檢索特定稅表相關的 IRS 申報規章上下文。"""
    if not use_kg:
        return ""
    try:
        from ..kg_retriever_v2 import query_kg_for_issue
        # 為什麼要傳 "tax form filing requirements"：
        # 提供表單屬性上下文，結合表單名稱，協助 bge-m3 檢索出該申報表對應的 IRS 規章節點。
        ctx = query_kg_for_issue(
            form_name,
            "tax form filing requirements",
        )
        return f"\n\n[KG RETRIEVED RULES]\n{ctx}\n" if ctx else ""
    except Exception as e:
        return f"\n\n[KG 暫時無法連線: {e}]\n"


# ---------------------------------------------------------------------------
# Gemini 後端
# ---------------------------------------------------------------------------

async def _gemini_form_planner(model_name: str, extracted_data: dict, source_filename: str) -> list[dict]:
    """Gemini Planner：掃描資料，識別出所需申報的表單及其初步狀態標籤。"""
    # 預設使用 gemini-2.5-pro
    actual_model = model_name or "gemini-2.5-pro"
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
    model = genai.GenerativeModel(model_name=actual_model, system_instruction=FORM_PLANNER_SYSTEM_PROMPT)
    msg = (
        f"Source file: {source_filename}\n\n"
        f"Taxpayer financial data:\n{json.dumps(extracted_data, ensure_ascii=False, indent=2)}\n\n"
        f"Identify all relevant forms and their status tags.\n\n{REINFORCE}"
    )
    resp = await model.generate_content_async(msg, generation_config={"temperature": 0})
    return _parse_json(resp.text or "").get("detected_forms", [])


async def _gemini_form_map(
    model_name: str,
    form_name: str,
    proposed_status: str,
    extracted_data: dict,
    source_filename: str,
    use_kg: bool
) -> dict:
    """Gemini Map：深入評估單一表單的狀態，撰寫詳細原因並列出缺漏項目。"""
    actual_model = model_name or "gemini-2.5-pro"
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))
    kg_block = _kg_form_context(form_name, use_kg)
    model = genai.GenerativeModel(model_name=actual_model, system_instruction=FORM_MAP_SYSTEM_PROMPT)
    
    target_info = {
        "form_name": form_name,
        "proposed_status": proposed_status
    }
    msg = (
        f"Target Form to evaluate:\n{json.dumps(target_info, ensure_ascii=False, indent=2)}\n\n"
        f"Full tax context (source file: {source_filename}):\n"
        f"{json.dumps(extracted_data, ensure_ascii=False, indent=2)}"
        f"{kg_block}"
        f"\n\nReturn a single form evaluation JSON object.\n\n{REINFORCE}"
    )
    resp = await model.generate_content_async(msg, generation_config={"temperature": 0})
    return _parse_json(resp.text or "")


# ---------------------------------------------------------------------------
# Gemma (Ollama) 後端
# ---------------------------------------------------------------------------

async def _gemma_form_planner(extracted_data: dict, source_filename: str, think: bool) -> list[dict]:
    """Gemma Planner：掃描資料，識別出所需申報的表單及其初步狀態標籤。"""
    client = AsyncClient(host=OLLAMA_HOST)
    msg = (
        f"Source file: {source_filename}\n\n"
        f"Taxpayer financial data:\n{json.dumps(extracted_data, ensure_ascii=False, indent=2)}\n\n"
        f"Identify all relevant forms and their status tags.\n\n{REINFORCE}"
    )
    resp = await client.chat(
        model="gemma4:31b",
        messages=[
            {"role": "system", "content": FORM_PLANNER_SYSTEM_PROMPT},
            {"role": "user", "content": msg},
            {"role": "system", "content": REINFORCE},
        ],
        options={"temperature": 0, "repeat_penalty": 1.2, "num_ctx": 32768},
        think=think,
    )
    return _parse_json(resp.message.content or "").get("detected_forms", [])


async def _gemma_form_map(
    form_name: str,
    proposed_status: str,
    extracted_data: dict,
    source_filename: str,
    think: bool,
    use_kg: bool
) -> dict:
    """Gemma Map：深入評估單一表單的狀態，撰寫詳細原因並列出缺漏項目。"""
    kg_block = _kg_form_context(form_name, use_kg)
    client = AsyncClient(host=OLLAMA_HOST)
    target_info = {
        "form_name": form_name,
        "proposed_status": proposed_status
    }
    msg = (
        f"Target Form to evaluate:\n{json.dumps(target_info, ensure_ascii=False, indent=2)}\n\n"
        f"Full tax context (source file: {source_filename}):\n"
        f"{json.dumps(extracted_data, ensure_ascii=False, indent=2)}"
        f"{kg_block}"
        f"\n\nReturn a single form evaluation JSON object.\n\n{REINFORCE}"
    )
    resp = await client.chat(
        model="gemma4:31b",
        messages=[
            {"role": "system", "content": FORM_MAP_SYSTEM_PROMPT},
            {"role": "user", "content": msg},
            {"role": "system", "content": REINFORCE},
        ],
        options={"temperature": 0, "repeat_penalty": 1.2, "num_ctx": 32768},
        think=think,
    )
    return _parse_json(resp.message.content or "")
