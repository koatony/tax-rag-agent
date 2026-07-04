"""
================================================================================
Academic Ablation Benchmark: Tax IRAC RAG Retrieval System
================================================================================
Experiment Design Reference:
  - Metrics:   MRR (Mean Reciprocal Rank), Hit@1, Hit@3, Hit@5, Hit@10
  - Test Set:  13 queries covering 5 dimensions of retrieval difficulty
  - Ablation:  Run with different .env configs; compare all conditions
  - Output:    JSON raw data + Markdown report suitable for academic submission

How to Run (Ablation Study):
  1. Edit .env (ENABLE_BM25, ENABLE_STEMMING, ENABLE_HYDE, ENABLE_DUAL_TRACK)
  2. python ablation_benchmark.py
  3. Results saved to ablation_results/ folder under a timestamped filename
================================================================================
"""

import sys
from pathlib import Path
import datetime

# 將專案根目錄加入路徑，以便導入 retriever
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))

import os
import json
import time
import numpy as np
from dotenv import load_dotenv

# 載入 .env 檔案中的環境變數
load_dotenv(dotenv_path=root_dir / ".env")

from retriever import IRACRetriever, RetrieverConfig

# ==============================================================================
# Ground Truth Dataset (13 queries, 5 categories)
# Each entry verified against actual GraphML node IDs
# ==============================================================================
GROUND_TRUTH = [
    # ── Category 1: Stemming / Lexical Form Variation (詞彙形態差異) ─────────
    {
        "id": "Q01",
        "category": "Stemming",
        "difficulty": "Hard",
        "query": "I play fantasy football for money. I won $5,000 but lost $6,000. Can I report a net loss to the IRS?",
        "target_rule": "Gambling Loss Deduction Limitation Rule",
        "notes": "User says 'lost / loss' (singular); KG stores 'losses' (plural). Stemming bridges this gap."
    },
    {
        "id": "Q02",
        "category": "Stemming",
        "difficulty": "Medium",
        "query": "I collect stamps as a hobby and sold some at a loss this year. Can I write off that loss against my salary?",
        "target_rule": "Hobby Loss Non-Deductibility Rule",
        "notes": "User says 'loss' (singular). Tests stemmer on 'deductib*' family."
    },
    {
        "id": "Q03",
        "category": "Stemming",
        "difficulty": "Medium",
        "query": "I am a volunteer firefighter. My city gives me a $50 monthly payment. Is that considered income?",
        "target_rule": "Volunteer Firefighter and Emergency Medical Responder Income Exclusion Rule",
        "notes": "User says 'firefighter' (singular); KG node uses the plural form in a compound noun."
    },

    # ── Category 2: Ontology / Synonym Gap (概念映射鴻溝) ────────────────────
    {
        "id": "Q04",
        "category": "Ontology Gap",
        "difficulty": "Very Hard",
        "query": "My beach house in Florida was wiped out by a hurricane. The insurance company paid $30k but the repairs cost $50k. What can I deduct?",
        "target_rule": "Casualty Loss Reporting Rule",
        "notes": "User: 'hurricane'. KG: 'casualty'. No lexical overlap; tests semantic vector distance."
    },
    {
        "id": "Q05",
        "category": "Ontology Gap",
        "difficulty": "Very Hard",
        "query": "I installed a special elevator in my house for my disabled spouse. It cost $25,000, but the appraiser says it only added $10,000 in home value.",
        "target_rule": "Capital Improvement Medical Expense Deduction Rule",
        "notes": "User: 'elevator / disabled'. KG: 'Capital Expense / Medical Improvement'. Semantic jump required."
    },
    {
        "id": "Q06",
        "category": "Ontology Gap",
        "difficulty": "Hard",
        "query": "I received stock options from my company as a bonus. I exercised them this year. How much tax do I owe?",
        "target_rule": "Nonstatutory Stock Option Income Inclusion Rule",
        "notes": "User: 'stock options / bonus'. Tests domain-specific concept matching."
    },

    # ── Category 3: Multi-Condition / Numerical Boundary (多條件數值邊界) ─────
    {
        "id": "Q07",
        "category": "Multi-Condition",
        "difficulty": "Hard",
        "query": "I paid state income tax of $8,000 and property tax of $6,000 last year. How much of this can I deduct on my federal return?",
        "target_rule": "SALT Deduction Limitation Rule",
        "notes": "Tests retrieval of rules with explicit dollar-limit conditions ($10,000 SALT cap)."
    },
    {
        "id": "Q08",
        "category": "Multi-Condition",
        "difficulty": "Hard",
        "query": "My employer paid for my graduate school tuition. Is any portion of that tax-free, or must I include all of it in income?",
        "target_rule": "Educational Assistance Exclusion Rule",
        "notes": "Tests retrieval of benefit cap ($5,250) rule with employer-provided condition."
    },

    # ── Category 4: Standard IRS Rules (標準稅務規則，should be easy) ─────────
    {
        "id": "Q09",
        "category": "Standard",
        "difficulty": "Easy",
        "query": "I received gambling winnings from a casino. What form do I use to report this, and where on my tax return does it go?",
        "target_rule": "Gambling Winnings Income Inclusion Rule",
        "notes": "Straightforward keyword overlap. Should be Rank 1 for any configuration."
    },
    {
        "id": "Q10",
        "category": "Standard",
        "difficulty": "Easy",
        "query": "I received a Form W-2G from the casino for $2,000. Where do I report this on my Form 1040?",
        "target_rule": "Form W-2G Reporting Rule",
        "notes": "Specific form-based query. Strong BM25 signal expected."
    },
    {
        "id": "Q11",
        "category": "Standard",
        "difficulty": "Medium",
        "query": "I withdrew money from my Health Savings Account to pay for surgery. Is that withdrawal taxable?",
        "target_rule": "HSA Tax Treatment Rule",
        "notes": "HSA is a well-known IRS term. Tests vector search for specific account types."
    },

    # ── Category 5: OOD Detection (領域外問題拒答，accuracy = PASS/FAIL) ─────
    {
        "id": "Q12",
        "category": "OOD",
        "difficulty": "OOD",
        "query": "How do I fix a leaky faucet in my bathroom? My plumber charges $500.",
        "target_rule": "OOD",
        "notes": "Clear non-tax question. LLM Gatekeeper must reject."
    },
    {
        "id": "Q13",
        "category": "OOD",
        "difficulty": "OOD",
        "query": "What is the best diet plan to lose 10 pounds in a month?",
        "target_rule": "OOD",
        "notes": "Health/lifestyle question. Tests for hallucination (wrongly classified as tax query)."
    },
]


# ==============================================================================
# Metric Calculations
# ==============================================================================
def mrr(ranks: list) -> float:
    return float(np.mean([1.0 / r if r > 0 else 0.0 for r in ranks]))

def hit_at_k(ranks: list, k: int) -> float:
    return float(np.mean([1.0 if 0 < r <= k else 0.0 for r in ranks]))


# ==============================================================================
# Main Benchmark Runner
# ==============================================================================
def run_ablation_benchmark():
    if not os.environ.get("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY not set in .env")
        return

    # Read current config from .env
    cfg = RetrieverConfig.from_env()
    print(f"\n{'='*72}")
    print(f"  ABLATION BENCHMARK — Tax IRAC RAG Retrieval System")
    print(f"  Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Config: {cfg.summary()}")
    print(f"{'='*72}\n")

    # 初始化 IRAC 檢索器（自動從 .env 讀取 ACTIVE_KGS）
    retriever = IRACRetriever.from_active_kgs(
        top_k_rule=30,
        top_k_fact=30,
        top_n_subgraph=3
    )

    rows = []
    tax_ranks = []   # only for non-OOD queries
    ood_results = [] # for OOD queries

    print(f"{'ID':<5} {'Category':<16} {'Difficulty':<10} {'Target Rule':<42} {'Rank':>5}  {'Status'}")
    print("-" * 90)

    for item in GROUND_TRUTH:
        qid       = item["id"]
        category  = item["category"]
        difficulty= item["difficulty"]
        query     = item["query"]
        target    = item["target_rule"]

        # ── OOD queries ──
        if target == "OOD":
            state = retriever.retrieve(query)
            answer = state.get("answer", "")
            passed = "非屬美國稅法領域" in answer or "OOD" in answer.upper()
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{qid:<5} {category:<16} {difficulty:<10} {'N/A (OOD)':<42} {'N/A':>5}  {status}")
            ood_results.append({"id": qid, "passed": passed})
            rows.append({"id": qid, "category": category, "difficulty": difficulty,
                         "target": target, "rank": None, "ood_pass": passed, "notes": item["notes"]})
            continue

        # ── Retrieval queries ──
        state = retriever.retrieve(query)
        candidates = state.get("rule_candidates", [])

        rank = 0
        for i, cand in enumerate(candidates, start=1):
            if cand["rule_id"] == target:
                rank = i
                break

        tax_ranks.append(rank)
        status_icon = "✅" if rank == 1 else ("🟢" if 0 < rank <= 3 else ("🟡" if 0 < rank <= 10 else "❌"))
        rank_str = str(rank) if rank > 0 else "MISS"
        print(f"{qid:<5} {category:<16} {difficulty:<10} {target[:42]:<42} {rank_str:>5}  {status_icon}")
        rows.append({"id": qid, "category": category, "difficulty": difficulty,
                     "target": target, "rank": rank, "ood_pass": None, "notes": item["notes"]})

    # ── Aggregate Metrics ──
    print("-" * 90)
    ood_pass_rate = sum(r["passed"] for r in ood_results) / len(ood_results) if ood_results else 0
    print(f"\n{'Metric':<20} {'Value':>10}")
    print("-" * 32)
    print(f"{'MRR':<20} {mrr(tax_ranks):>10.4f}")
    print(f"{'Hit@1':<20} {hit_at_k(tax_ranks, 1):>10.4f}")
    print(f"{'Hit@3':<20} {hit_at_k(tax_ranks, 3):>10.4f}")
    print(f"{'Hit@5':<20} {hit_at_k(tax_ranks, 5):>10.4f}")
    print(f"{'Hit@10':<20} {hit_at_k(tax_ranks, 10):>10.4f}")
    print(f"{'OOD Pass Rate':<20} {ood_pass_rate:>10.4f}")

    # ── Save Results ──
    results_dir = root_dir / "results" / "ablation_benchmark"
    os.makedirs(results_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_cfg = cfg.summary().replace("|", "_").replace("=", "-")
    filename = results_dir / f"run_{ts}_{clean_cfg}.json"

    output = {
        "timestamp": ts,
        "config": {
            "enable_bm25":        cfg.enable_bm25,
            "enable_stemming":    cfg.enable_stemming,
            "enable_dual_track":  cfg.enable_dual_track,
            "enable_hyde":        cfg.enable_hyde,
            "enable_kg_subgraph": cfg.enable_kg_subgraph,
        },
        "metrics": {
            "mrr":           mrr(tax_ranks),
            "hit@1":         hit_at_k(tax_ranks, 1),
            "hit@3":         hit_at_k(tax_ranks, 3),
            "hit@5":         hit_at_k(tax_ranks, 5),
            "hit@10":        hit_at_k(tax_ranks, 10),
            "ood_pass_rate": ood_pass_rate,
        },
        "per_query": rows,
    }

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[Saved] Results → {filename}")
    return output


if __name__ == "__main__":
    run_ablation_benchmark()
