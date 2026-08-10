"""表單狀態分析器的協調器（Orchestrator）。"""

import asyncio
from .llm_backends import (
    _gemini_form_planner,
    _gemini_form_map,
    _gemma_form_planner,
    _gemma_form_map
)

# 目前支援的 6 種表單對應的計算 API 端點與 Method
FORM_API_MAPPING = {
    "Schedule A": {
        "url": "/schedule-a/extract-and-calculate",
        "method": "POST"
    },
    "Schedule B": {
        "url": "/schedule-b/extract-and-calculate",
        "method": "POST"
    },
    "Schedule C": {
        "url": "/schedule-c/extract-and-calculate",
        "method": "POST"
    },
    "Schedule E": {
        "url": "/schedule-e/extract-and-calculate",
        "method": "POST"
    },
    "Schedule 1": {
        "url": "/schedule-1/extract-and-calculate",
        "method": "POST"
    },
    "Form 4562": {
        "url": "/form-4562/extract-and-calculate",
        "method": "POST"
    }
}

async def analyze_form_status(
    extracted_data: dict,
    source_filename: str = "upload.json",
    model: str = "gemini-2.5-pro",
    use_kg: bool = True,
    think: bool = False
) -> dict:
    """
    分析納稅人表單填寫狀態的主進入點。
    
    1. 第一階段 (Planner)：識別出需要申報的表單清單及其初步狀態標籤。
    2. 第二階段 (Map)：平行評估每個表單的詳細狀態，確認或校正狀態，並填寫具體原因與缺失明細。
    """
    is_gemma = model == "gemma4:31b"

    # 步驟 1：Planner 階段 - 找出納稅人今年需要評估的表單與初步狀態
    if is_gemma:
        detected_forms = await _gemma_form_planner(extracted_data, source_filename, think)
    else:
        detected_forms = await _gemini_form_planner(model, extracted_data, source_filename)

    # 步驟 2：Map 階段 - 平行深入評估各個表單的詳細狀態
    if is_gemma:
        raw_results = await asyncio.gather(
            *[_gemma_form_map(
                form_name=str(f.get("form_name") or ""),
                proposed_status=str(f.get("status") or ""),
                extracted_data=extracted_data,
                source_filename=source_filename,
                think=think,
                use_kg=use_kg
             ) for f in detected_forms if f.get("form_name")],
            return_exceptions=True,
        )
    else:
        raw_results = await asyncio.gather(
            *[_gemini_form_map(
                model_name=model,
                form_name=str(f.get("form_name") or ""),
                proposed_status=str(f.get("status") or ""),
                extracted_data=extracted_data,
                source_filename=source_filename,
                use_kg=use_kg
             ) for f in detected_forms if f.get("form_name")],
            return_exceptions=True,
        )

    # 彙整分析結果與異常錯誤
    forms = []
    errors = []
    available_extract_calculate = []
    
    for i, res in enumerate(raw_results):
        if isinstance(res, Exception):
            errors.append(f"表單 {i + 1} 分析失敗: {res}")
            continue
        
        # 動態注入 actions
        actions = {}
        if isinstance(res, dict):
            status = res.get("status")
            form_name = res.get("form_name")
            if status in ("completable", "calculable_with_review", "calculable_with_confirmation", "waiting_for_dependency") and form_name in FORM_API_MAPPING:
                api = FORM_API_MAPPING[form_name]

                actions["calculate"] = FORM_API_MAPPING[form_name]
                if status == "completable":
                    available_extract_calculate.append({
                        "form_name": form_name,
                        "endpoint": api["url"],
                        "method": api["method"]
                    })
            res["actions"] = actions

        forms.append(res)

    result = {
        "forms": forms,
        "available_extract_calculate": available_extract_calculate
    }
    if errors:
        result["_errors"] = errors
        
    return result

