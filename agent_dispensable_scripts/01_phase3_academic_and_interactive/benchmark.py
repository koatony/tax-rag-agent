"""
Academic Benchmark Suite for Tax RAG Retrieval
Metrics: MRR (Mean Reciprocal Rank), Hit@1, Hit@3, Hit@5
Comparison: Baseline Vector vs. Baseline BM25 vs. Hybrid (Stemming)
"""

import sys
from pathlib import Path

# 將專案根目錄加入路徑，以便導入 retriever
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))

import os
import json
import time
from dotenv import load_dotenv
import numpy as np
from retriever import IRACRetriever

# 載入 .env 檔案中的環境變數
load_dotenv(dotenv_path=root_dir / ".env")

# 1. Define Ground Truth
# Query -> Target Rule ID
BENCHMARK_DATA = [
    {
        "query": "I play fantasy football for money. I won $5,000 but lost $6,000 on sports apps. Can I report a net loss?",
        "target_rule": "Gambling Loss Deduction Limitation Rule",
        "category": "Lexical Gap (Stemming)"
    },
    {
        "query": "My beach house in Florida was severely damaged by a hurricane. Insurance only paid a portion.",
        "target_rule": "Casualty Loss Reporting Rule",
        "category": "Lexical Gap (Synonym)"
    },
    {
        "query": "Is the money I receive from a Health Savings Account for my surgery taxable?",
        "target_rule": "HSA Tax Treatment Rule",
        "category": "Standard Tax Case"
    },
    {
        "query": "I am a volunteer firefighter. The city gave me a $50 monthly rebate. Is this income?",
        "target_rule": "Volunteer Firefighter and Emergency Medical Responder Income Exclusion Rule",
        "category": "Stemming (Firefighter/Firefighters)"
    },
    {
        "query": "I enjoy collecting stamps and lost money selling some this year. Can I deduct the loss offset my salary?",
        "target_rule": "Hobby Loss Non-Deductibility Rule",
        "category": "Semantic Context"
    },
    {
        "query": "How do I fix a leaky faucet in my bathroom? My plumber is charging me $500.",
        "target_rule": "OOD",
        "category": "OOD Detection"
    }
]

def calculate_mrr(ranks):
    return np.mean([1.0 / r if r > 0 else 0 for r in ranks])

def calculate_hit_rate(ranks, k):
    return np.mean([1 if 0 < r <= k else 0 for r in ranks])

def run_benchmark():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not found.")
        return

    # 初始化檢索器 (Phase 3 預設就是 Hybrid + Stemming)
    # 初始化 IRAC 檢索器（自動從 .env 讀取 ACTIVE_KGS）
    retriever = IRACRetriever.from_active_kgs(
        // openai_api_key removed - no longer needed
        top_k_rule     = 30,
        top_k_fact     = 30,
        top_n_subgraph = 3,
    )

    results = []
    
    print(f"\n{'='*70}")
    print(f"{'Query':<50} | {'Target Rule':<30} | {'Rank'}")
    print("-" * 90)

    ranks = []
    for item in BENCHMARK_DATA:
        query = item["query"]
        target = item["target_rule"]
        
        if target == "OOD":
            # 專門測試 OOD 攔截
            retrieval_res = retriever.retrieve(query)
            if "非屬美國稅法領域" in retrieval_res.get("answer", ""):
                print(f"{query[:50]:<50} | {'N/A (OOD)':<30} | {'PASS'}")
            else:
                print(f"{query[:50]:<50} | {'N/A (OOD)':<30} | {'FAIL'}")
            continue

        # 執行檢索
        # 為了模擬實驗，我們直接讀取 retriever 的中間狀態或最終評分
        # 我們強制執行一輪 retrieve 並觀察 rule_candidates
        state = retriever.retrieve(query)
        candidates = state.get("rule_candidates", [])
        
        # 尋找目標 Rank
        rank = 0
        for i, cand in enumerate(candidates):
            if cand["rule_id"] == target:
                rank = i + 1
                break
        
        ranks.append(rank)
        print(f"{query[:50]:<50} | {target[:30]:<30} | {rank if rank > 0 else 'MISS'}")
        
    # 統計
    mrr = calculate_mrr(ranks)
    h1 = calculate_hit_rate(ranks, 1)
    h3 = calculate_hit_rate(ranks, 3)
    h5 = calculate_hit_rate(ranks, 5)

    print("-" * 90)
    print(f"MRR: {mrr:.4f} | Hit@1: {h1:.4f} | Hit@3: {h3:.4f} | Hit@5: {h5:.4f}")
    
    # 保存數據
    benchmark_res = {
        "metrics": {"mrr": mrr, "hit@1": h1, "hit@3": h3, "hit@5": h5},
        "raw_ranks": ranks,
        "timestamp": time.time()
    }
    with open("benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(benchmark_res, f, indent=2)

if __name__ == "__main__":
    run_benchmark()
