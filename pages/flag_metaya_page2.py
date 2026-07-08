import asyncio
import json
from pathlib import Path

import streamlit as st

if not st.session_state.get("password_correct", False):
    st.error("請先回到主頁面登入")
    st.stop()

from Flag.analyzer_core_v2 import analyze

st.title(" Flag v2 — Tax Risk Analyzer (量化 Risk Scoring)")


# ── Model & Options ────────────────────────────────────────────────────────
st.subheader("Model")
model = st.radio(
    "選擇模型",
    options=["gemini-2.5-flash", "gemini-2.5-pro", "gemma4:31b"],
    captions=["Fast · Google · Cloud", "Most capable · Google · Cloud", "Local · Ollama · Self-hosted"],
    horizontal=True,
    label_visibility="collapsed",
    key="_fm2_model",
)

opt1, opt2 = st.columns(2)
use_kg = opt1.toggle("Knowledge Graph", help="Semantic KG retrieval (Neo4j + bge-m3)", key="_fm2_kg")
think  = opt2.toggle(
    "Thinking Mode",
    disabled=(model != "gemma4:31b"),
    help="Gemma extended reasoning (slower) — Gemma only",
    key="_fm2_think",
)

st.divider()

# ── Input ──────────────────────────────────────────────────────────────────
EXAMPLE = {
    "taxpayer_profile": {
        "Name": "Marcus and Elena Rivera",
        "Filing Status": "Married Filing Jointly",
        "State": "California (Sacramento)",
        "Tax Year": 2024,
    },
    "uploaded_documents": [
        {
            "file_name": "Sample 02 - Rivera Meals & Entertainment Statement.json",
            "content": json.dumps({
                "document_type": "Meals & Entertainment Expense Statement",
                "category": "Schedule C",
                "total_amount": 1800.0,
                "breakdown": [
                    {"item": "Season tickets", "amount": 700.0},
                    {"item": "Business travel meals", "amount": 550.0},
                    {"item": "Employee holiday party", "amount": 400.0},
                    {"item": "Overtime meals", "amount": 150.0},
                ],
                "note": "mixed bundle, receipts available",
            }),
        },
        {
            "file_name": "Sample 03 - Rivera Las Vegas Conference Trip Receipt.json",
            "content": json.dumps({
                "document_type": "Travel Expense Receipt",
                "category": "Schedule C",
                "description": "Las Vegas conference trip",
                "amount": 3200.0,
                "note": "2 business days (conference) + 3 personal days (sightseeing)",
            }),
        },
        {
            "file_name": "Sample 04 - Rivera City Fine Notice.json",
            "content": json.dumps({
                "document_type": "Government Fine Notice",
                "category": "Schedule C",
                "description": "City fine",
                "amount": 300.0,
                "note": "fine paid to government agency",
            }),
        },
        {
            "file_name": "Sample 05 - Rivera Political Contribution Receipt.json",
            "content": json.dumps({
                "document_type": "Contribution Receipt",
                "category": "Schedule A",
                "description": "Political contribution",
                "amount": 250.0,
                "note": "political donation, not charitable",
            }),
        },
        {
            "file_name": "Sample 06 - Rivera Church Donation Acknowledgment.json",
            "content": json.dumps({
                "document_type": "Charitable Contribution Acknowledgment",
                "category": "Schedule A",
                "description": "Church donation",
                "amount": 5400.0,
                "note": "written acknowledgment available",
            }),
        },
        {
            "file_name": "Sample 07 - Rivera Schedule E Rental Property Summary.json",
            "content": json.dumps({
                "document_type": "Rental Property Summary",
                "category": "Schedule E",
                "description": "Rental property - no depreciation schedule",
                "amount": 0.0,
                "note": "no depreciation claimed in prior year or current year",
            }),
        },
    ],
}

EXAMPLE_IRA = {
    "taxpayer_profile": {
        "Name": "Wei-Ling Chen",
        "Filing Status": "Single",
        "State": "California (Sacramento)",
        "Tax Year": 2024,
    },
    "uploaded_documents": [
        {
            "file_name": "Sample 01 - Wei-Ling Chen Form 5498 IRA Contribution.json",
            "content": json.dumps({
                "document_type": "Form 5498 IRA Contribution Information",
                "tax_year": 2024,
                "form_type": "5498",
                "participant": {
                    "name": "Wei-Ling Chen",
                    "ssn": "555-98-7654",
                    "address": "118 Glenwood Ave, Sacramento, CA 95816",
                },
                "trustee": {
                    "name": "Pacific Crest Investment Trust Co.",
                    "ein": "94-1122334",
                },
                "boxes": {
                    "box_1_ira_contributions": 6500.0,
                    "box_7_ira_type": "Traditional IRA",
                },
                "note": "Taxpayer claimed a $6,500 Traditional IRA contribution deduction on Schedule 1. "
                        "W-2 for the same year shows Box 13 'Retirement plan' checked, indicating active "
                        "participation in an employer-sponsored plan. Workplace retirement plan coverage "
                        "and income-based phase-out have not yet been confirmed with the client.",
            }),
        },
        {
            "file_name": "Sample 02 - Wei-Ling Chen Charitable Donation Receipt.json",
            "content": json.dumps({
                "document_type": "Charitable Contribution Receipt",
                "category": "Schedule A",
                "description": "Donation to local food bank",
                "amount": 800.0,
                "note": "No contemporaneous written acknowledgment received from the organization; "
                        "donation amount exceeds the $250 threshold requiring a written acknowledgment "
                        "under IRC §170(f)(8) before the deduction can be claimed.",
            }),
        },
    ],
}

EXAMPLE2_PATH = Path(__file__).resolve().parent.parent / "Flag" / "example" / "example2.json"

col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
with col1:
    st.caption("Financial data (JSON)")
with col2:
    if st.button("Load example Rivera2024", use_container_width=True, key="_fm2_load_rivera"):
        st.session_state["_fm2_json_text"] = json.dumps(EXAMPLE, indent=2)
with col3:
    if st.button("Load example IRA", use_container_width=True, key="_fm2_load_ira"):
        st.session_state["_fm2_json_text"] = json.dumps(EXAMPLE_IRA, indent=2)
with col4:
    if st.button("Load example2", use_container_width=True, key="_fm2_load_example2"):
        st.session_state["_fm2_json_text"] = EXAMPLE2_PATH.read_text(encoding="utf-8")

json_input = st.text_area(
    "json_input",
    height=320,
    placeholder="Paste financial data JSON here…",
    label_visibility="collapsed",
    key="_fm2_json_text",
)

run = st.button("▶ Analyze", type="primary", use_container_width=True, key="_fm2_run")

# ── Run ────────────────────────────────────────────────────────────────────
if run:
    raw = json_input.strip()
    if not raw:
        st.warning("請先貼上 Financial data JSON")
        st.stop()

    try:
        financial_data = json.loads(raw)
    except json.JSONDecodeError as e:
        st.error(f"Invalid JSON: {e}")
        st.stop()

    with st.spinner(f"Analyzing with {model}{' + KG' if use_kg else ''}{' (thinking)' if think else ''}…"):
        result = asyncio.run(
            analyze(
                extracted_data=financial_data,
                source_filename="web_input.json",
                model=model,
                use_kg=use_kg,
                think=think,
            )
        )

    st.session_state["_fm2_last_result"] = result

# ── Results ────────────────────────────────────────────────────────────────
result = st.session_state.get("_fm2_last_result")
if not result:
    st.stop()

summary = result.get("risk_summary", {})
flags   = result.get("flags", [])
needs   = result.get("needs_from_client", [])

st.divider()
st.subheader(f"Results — {result.get('client', '')}  ({result.get('tax_year', '')})")

c1, c2, c3, c4 = st.columns(4)
c1.metric("🔴 HIGH",   summary.get("high",   0))
c2.metric("🟡 MEDIUM", summary.get("medium", 0))
c3.metric("🟢 LOW",    summary.get("low",    0))
c4.metric("📋 TOTAL",  summary.get("total",  len(flags)))

RISK_COLOR = {"high": "🔴", "medium": "🟡", "low": "🟢"}

for f in flags:
    risk  = (f.get("risk_level") or "").lower()
    icon  = RISK_COLOR.get(risk, "⚪")
    conf  = f"{round(f['confidence_score'] * 100)}%" if f.get("confidence_score") is not None else "N/A"
    amt   = f"${f['amount_at_risk']:,.0f}" if f.get("amount_at_risk") is not None else "N/A"
    docs  = ", ".join(f.get("missing_docs") or []) or "None"
    score = f.get("risk_score", "N/A")

    with st.expander(
        f"{icon} [{f.get('flag_id','')}] {f.get('flag_title','')}  —  {risk.upper()} (score={score})",
        expanded=(risk == "high"),
    ):
        mc1, mc2 = st.columns(2)
        mc1.markdown(f"**Area:** {f.get('tax_area','')}")
        mc1.markdown(f"**IRC:** {f.get('irc_reference','')}")
        mc1.markdown(f"**Amount at risk:** {amt}")
        mc1.markdown(f"**Rule deviation type:** {f.get('rule_deviation_type', 'N/A')}")
        mc2.markdown(f"**Risk score:** {score} → **{risk.upper()}**")
        mc2.markdown(f"**Confidence:** {conf}")
        mc2.markdown(f"**Missing docs:** {docs}")
        mc2.markdown(f"**Source:** {f.get('source_document') or 'N/A'}")
        st.info(f.get("ai_finding", ""))
        st.caption(f"CPA Action: {f.get('cpa_action','')}")

if needs:
    st.subheader(f"Needs from client ({len(needs)})")
    for n in needs:
        st.markdown(f"- {n}")

if result.get("_errors"):
    with st.expander("⚠️ Partial errors"):
        for e in result["_errors"]:
            st.warning(e)

with st.expander("Raw JSON"):
    st.json(result)
