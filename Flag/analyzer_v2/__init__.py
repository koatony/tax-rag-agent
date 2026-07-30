"""
Unified analyzer core for the web UI — v2, adds a quantified risk-scoring
model in place of pure LLM-judged risk_level.

Supports: gemini-2.5-flash, gemini-2.5-pro, gemma4:31b (think/no-think), each ±KG.
Architecture: two-stage PLANNER → MAP, plus deterministic safety-net checks
(S07 / S07b / S07c / S07d — see safety_nets.py) that catch what the LLM
sometimes misses.

Split across modules for readability:
  preprocess.py    — input normalizer
  prompts.py       — PLANNER/MAP system prompts
  llm_backends.py  — Gemini + Gemma (Ollama) calls
  safety_nets.py   — deterministic S07/S07b/S07c/S07d checks
  risk_scoring.py  — Audit Risk Model (AICPA SAS No. 47) scoring
  orchestrator.py  — analyze(), ties the above together
"""

from .orchestrator import analyze
from .preprocess import preprocess
from .risk_scoring import compute_risk_score

__all__ = ["analyze", "preprocess", "compute_risk_score"]
