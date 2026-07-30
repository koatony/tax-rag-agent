"""
Backward-compatible shim — the implementation now lives in the analyzer_v2/
package (split into preprocess.py, prompts.py, llm_backends.py,
safety_nets.py, risk_scoring.py, orchestrator.py for readability).

Existing callers (e.g. pages/flag_metaya_page2.py) import from this module
path, so it stays in place as a thin re-export.
"""

from .analyzer_v2 import analyze, compute_risk_score, preprocess

__all__ = ["analyze", "preprocess", "compute_risk_score"]
