# 兩階段 PLANNER -> MAP 的協調器，並串接確定性安全網檢查。

import asyncio

from .llm_backends import _gemini_map, _gemini_planner, _gemma_map, _gemma_planner
from .preprocess import preprocess
from .risk_scoring import compute_risk_score
from .safety_nets import (
    RENTAL_ACTIVITY_KEYWORDS,
    check_prior_year_comparison,
    check_rental_depreciation_omission,
    check_rental_documentation_completeness,
    enforce_required_missing_docs,
)


async def analyze(
    extracted_data: dict,
    source_filename: str,
    model: str,          # "gemini-2.5-flash" | "gemini-2.5-pro" | "gemma4:31b"
    use_kg: bool = False,
    think: bool = False, # only for gemma
) -> dict:
    # 整個 v2 分析流程唯一的對外入口：正規化輸入 -> PLANNER 找問題 -> MAP
    # 逐一分析 -> 疊加確定性安全網（S07/S07b/S07c/S07d）補齊 LLM 可能漏掉
    # 的已知問題類型 -> 用固定公式算每個 flag 的風險分數 -> 依風險排序、
    # 編號 -> 組出最終結果 dict（client、tax_year、risk_summary、flags、
    # needs_from_client、_errors）。呼叫端（API.py、Streamlit 頁面）只需要
    # 呼叫 analyze() 一次，不用知道底層是兩階段 LLM 呼叫加上好幾個安全網
    # 檢查。
    extracted_data = preprocess(extracted_data)
    is_gemma = model == "gemma4:31b"

    if is_gemma:
        detected_issues = await _gemma_planner(extracted_data, source_filename, think)
        raw_flags = await asyncio.gather(
            *[_gemma_map(issue, extracted_data, source_filename, think, use_kg) for issue in detected_issues],
            return_exceptions=True,
        )
    else:
        detected_issues = await _gemini_planner(model, extracted_data, source_filename)
        raw_flags = await asyncio.gather(
            *[_gemini_map(model, issue, extracted_data, source_filename, use_kg) for issue in detected_issues],
            return_exceptions=True,
        )

    flags = []
    errors = []
    for i, flag in enumerate(raw_flags):
        if isinstance(flag, Exception):
            errors.append(f"Issue {i + 1}: {flag}")
            continue
        flag = enforce_required_missing_docs(flag)
        flags.append(flag)

    already_has_rental_flag = any(
        any(kw in str(f.get("tax_area", "")).lower() + str(f.get("flag_title", "")).lower()
            for kw in RENTAL_ACTIVITY_KEYWORDS)
        for f in flags
    )
    if not already_has_rental_flag:
        rental_doc_gap = check_rental_documentation_completeness(extracted_data)
        if rental_doc_gap is not None:
            flags.append(rental_doc_gap)

        rental_depreciation_gap = check_rental_depreciation_omission(extracted_data)
        if rental_depreciation_gap is not None:
            flags.append(rental_depreciation_gap)

    prior_year_gap = check_prior_year_comparison(extracted_data)
    if prior_year_gap is not None:
        flags.append(prior_year_gap)

    # Materiality is relative to the largest amount_at_risk in THIS run, so
    # it can only be computed once every flag's amount is known.
    max_amount_at_risk = max((float(f.get("amount_at_risk") or 0) for f in flags), default=0.0)

    for flag in flags:
        flag["risk_score"], flag["risk_level"] = compute_risk_score(flag, max_amount_at_risk)
        flag.pop("_documentation_gap", None)

    # Highest-priority flags first (see analyzer_core.py's User Story 8.2 note).
    flags.sort(key=lambda f: f["risk_score"], reverse=True)
    for i, flag in enumerate(flags):
        flag["flag_id"] = f"FLAG-{i + 1:03d}"

    summary = {"high": 0, "medium": 0, "low": 0, "total": len(flags)}
    for f in flags:
        lvl = f.get("risk_level", "").lower()
        if lvl in summary:
            summary[lvl] += 1

    needs_from_client = [
        f["cpa_action"]
        for f in flags
        if f.get("requires_cpa_review") and f.get("cpa_action")
    ]

    result = {
        "client": extracted_data.get("client", "N/A"),
        "tax_year": extracted_data.get("tax_year", "N/A"),
        "risk_summary": summary,
        "flags": flags,
        "needs_from_client": needs_from_client,
    }
    if errors:
        result["_errors"] = errors
    return result
