"""
Unified analyzer core for the web UI.
Supports: gemini-2.5-flash, gemini-2.5-pro, gemma4:31b (think/no-think), each ±KG.
Architecture: two-stage PLANNER → MAP.
"""

import asyncio
import json
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


# ---------------------------------------------------------------------------
# Input normalizer
# ---------------------------------------------------------------------------

def preprocess(raw: dict) -> dict:
    """
    Accept either:
      (a) legacy flat format  — {client, tax_year, expenses, ...}
      (b) new upload format   — {taxpayer_profile: {...}, uploaded_documents: [...]}
    Returns a normalized dict suitable for the PLANNER prompt.
    """
    if "taxpayer_profile" not in raw:
        return raw  # already legacy format

    profile = raw["taxpayer_profile"]
    docs_raw = raw.get("uploaded_documents", [])

    # Parse stringified content fields
    documents = []
    for doc in docs_raw:
        entry = {"file_name": doc.get("file_name", "")}
        content = doc.get("content", "")
        if isinstance(content, str):
            try:
                entry["content"] = json.loads(content)
            except json.JSONDecodeError:
                entry["content"] = content  # leave as string if unparseable
        else:
            entry["content"] = content
        documents.append(entry)

    return {
        "client": profile.get("Name", "N/A"),
        "tax_year": profile.get("Tax Year", "N/A"),
        "filing_status": profile.get("Filing Status", ""),
        "state": profile.get("State", ""),
        "uploaded_documents": documents,
    }

# ---------------------------------------------------------------------------
# Prompts (shared across all models)
# ---------------------------------------------------------------------------

PLANNER_SYSTEM_PROMPT = """You are a U.S. tax audit planning specialist.

Your task: scan the taxpayer's financial data and identify ALL potential compliance issues across Form 1040 and Schedules C, A, E, SE, and D.

[COMMON RISK PATTERNS — for reference only, not exhaustive]
- Mixed personal and business expenses in a single transaction
- Expenses with no clear or documented business purpose
- Fines, penalties, or punitive payments to government entities
- Assets placed in service with no depreciation recorded
- Political or lobbying expenses claimed as business deductions
- Charitable contributions lacking required documentation
- Retirement or investment deductions subject to income-based phase-outs

[GENERAL REVIEW]
- Flag any item where the amount seems disproportionate to the stated business purpose
- Flag any item where documentation is absent or insufficient for audit defense
- For items not matching a known pattern, apply the ordinary, necessary, directly-related-to-business test

Output a JSON object listing every detected issue. Output pure JSON only. Do NOT use markdown code blocks. Do NOT include any explanatory text.

Output schema:
{
  "detected_issues": [
    {
      "id": "ISSUE_001",
      "issue_name": "short issue name",
      "target_component": "Schedule C / Miscellaneous Expense",
      "source_docs": []
    }
  ]
}"""

MAP_SYSTEM_PROMPT = """You are a U.S. tax audit expert and licensed CPA with full discretionary authority to make adjustments.

Your task: perform a deep analysis of a single identified tax issue within the context of the full financial data.

Analysis framework (apply in order):
1. What is the legal nature of this item under the IRC?
2. Is there a clear, documented business purpose?
3. Are there non-deductible portions or is allocation required?
4. What is the risk level based on the likelihood of an adjustment being required?
5. Does this require CPA judgment, or is it a clear-cut error?

Risk level:
- high: adjustment very likely required; item as reported is probably incorrect or incomplete
- medium: adjustment may be required depending on additional information not yet available
- low: item appears correct but has a documentation requirement that must be verified

requires_cpa_review:
- false: tax law explicitly prohibits the deduction; no discretion needed; direct adjustment, no client confirmation required
- true: involves factual judgment, proportional allocation, missing documentation, or client confirmation is needed

Identify any documentation gaps needed to substantiate this item for audit
defense, and list them in missing_docs.

Output a single flag JSON object. Output pure JSON only. Do NOT use markdown code blocks. Do NOT include any explanatory text.

Output schema:
{
  "flag_id": "FLAG-001",
  "risk_level": "high|medium|low",
  "tax_area": "Schedule C",
  "flag_title": "short title",
  "ai_finding": "specific finding with IRC citation",
  "requires_cpa_review": true,
  "cpa_action": "direct adjustment OR client confirmation steps",
  "irc_reference": "IRC §162(f)",
  "amount_at_risk": 300,
  "confidence_score": 0.95,
  "missing_docs": [],
  "source_document": "filename or None",
  "status": "open",
  "cpa_note": null
}"""

REINFORCE = "Output pure JSON only. No markdown formatting. No explanatory text."

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json(raw: str) -> dict:
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No valid JSON object in response:\n{raw[:300]}")
    return json.loads(cleaned[start: end + 1])


def _kg_context(issue: dict, use_kg: bool) -> str:
    if not use_kg:
        return ""
    try:
        from .kg_retriever_v2 import query_kg_for_issue
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


# ---------------------------------------------------------------------------
# S07 — Missing document detection (deterministic fallback)
# ---------------------------------------------------------------------------

REQUIRED_MISSING_DOCS = {
    "rental_depreciation": {
        "keywords": ["rental", "depreciation", "schedule e", "land/building", "land building"],
        "docs": [
            "Rental purchase document",
            "Land/building value allocation",
            "Prior depreciation schedule",
        ],
    },
    "travel": {
        "keywords": ["travel", "conference", "trip", "itinerary"],
        "docs": [
            "Conference agenda",
            "Travel itinerary",
            "Business purpose documentation",
        ],
    },
    "charitable_deduction": {
        "keywords": ["charitable", "donation"],
        "docs": [
            "Charitable contribution acknowledgment letter",
            "Receipt with purpose notes",
        ],
    },
    "ira_deduction": {
        "keywords": ["ira contribution", "ira deduction", "retirement plan"],
        "docs": [
            "IRA workplace retirement plan coverage information",
        ],
    },
}


def _enforce_required_missing_docs(flag: dict) -> dict:
    """
    Safety net for S07: regardless of what the LLM produced, guarantee that
    flags matching a known category (rental depreciation / travel / deduction
    support) list their required supporting documents in missing_docs.
    """
    # Only match against the issue's own classification (title/area), not the
    # free-form ai_finding/irc_reference explanation text — those often mention
    # neighboring legal concepts (e.g. "not a charitable deduction") that would
    # otherwise cause false-positive category matches.
    haystack = " ".join(
        str(flag.get(k, "")) for k in ("tax_area", "flag_title")
    ).lower()

    existing = flag.get("missing_docs") or []
    merged = list(existing)

    for category in REQUIRED_MISSING_DOCS.values():
        if any(kw in haystack for kw in category["keywords"]):
            for doc in category["docs"]:
                if doc not in merged:
                    merged.append(doc)

    flag["missing_docs"] = merged
    return flag


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def analyze(
    extracted_data: dict,
    source_filename: str,
    model: str,          # "gemini-2.5-flash" | "gemini-2.5-pro" | "gemma4:31b"
    use_kg: bool = False,
    think: bool = False, # only for gemma
) -> dict:
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
        flag["flag_id"] = f"FLAG-{len(flags) + 1:03d}"
        flags.append(_enforce_required_missing_docs(flag))

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
