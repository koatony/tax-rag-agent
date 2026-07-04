import json
import os
import sys
from pathlib import Path

RESULTS_DIR = Path("/home/wmlab/projects/Retrieve/experiments/bulk_benchmark_v4_v10/results")
REPORT_PATH = Path("/home/wmlab/projects/Retrieve/experiments/bulk_benchmark_v4_v10/FINAL_BENCHMARK_REPORT_CH.md")

def aggregate(results_dir=RESULTS_DIR):
    all_data = []
    # Support recursive search in subdirectories
    files = list(results_dir.rglob("eval_*.json")) + list(results_dir.rglob("EVAL_*.json"))
    files = list(set(files))
    
    for f in files:
        if f.is_dir(): continue
        
        # Exclude datasets 08, 09, 10 as requested by the user
        if any(x in f.name for x in ["_08_", "_09_", "_10_"]):
            # print(f"[AGGREGATE] Skipping excluded file: {f.name}")
            continue
            
        if f.stat().st_size < 100:
            continue
        try:
            with open(f, "r", encoding="utf-8") as jf:
                data = json.load(jf)
                if not isinstance(data, list): continue
                for item in data:
                    section = f.stem.replace("EVAL_", "").replace("eval_qa_", "")
                    # 支援新的 rag_kg/rag_naive/pure_llm 結構
                    kg_data = item.get("rag_kg") or item.get("rag") or {}
                    naive_data = item.get("rag_naive") or {}
                    llm_data = item.get("pure_llm") or item.get("pure_llm") or {}
                    
                    all_data.append({
                        "id": item.get("id", "UNK"),
                        "type": item.get("type", "X"),
                        "category": item.get("category", "Unknown"),
                        "section": section,
                        "question": item.get("question", ""),
                        "kg": kg_data,
                        "naive": naive_data,
                        "llm": llm_data,
                        "is_new_benchmark": "rag_kg" in item
                    })
        except Exception as e:
            print(f"Error parsing {f}: {e}")

    if not all_data:
        print("No valid evaluation data found in:", results_dir)
        return

    # Metrics (Filtered)
    kg_m1_list = [d["kg"].get("score", 0) for d in all_data if "error" not in d["kg"]]
    nv_m1_list = [d["naive"].get("score", 0) for d in all_data if "error" not in d["naive"]]
    llm_m1_list = [d["llm"].get("score", 0) for d in all_data if "error" not in d["llm"]]
    
    kg_m2_list = [d["kg"]["recall"].get("context_recall", 0) for d in all_data if "recall" in d["kg"] and "error" not in d["kg"]["recall"]]
    nv_m2_list = [d["naive"]["recall"].get("context_recall", 0) for d in all_data if "recall" in d["naive"] and "error" not in d["naive"]["recall"]]

    kg_m3_list = [1 if d["kg"]["faithfulness"].get("faithfulness") == "faithful" else 0 
                  for d in all_data if "faithfulness" in d["kg"] and "error" not in d["kg"]["faithfulness"]]
    nv_m3_list = [1 if d["naive"]["faithfulness"].get("faithfulness") == "faithful" else 0 
                    for d in all_data if "faithfulness" in d["naive"] and "error" not in d["naive"]["faithfulness"]]
    
    kg_lat_list = [d["kg"].get("latency", 0) for d in all_data if d["kg"].get("latency", 0) > 0]
    nv_lat_list = [d["naive"].get("latency", 0) for d in all_data if d["naive"].get("latency", 0) > 0]
    llm_lat_list = [d["llm"].get("latency", 0) for d in all_data if d["llm"].get("latency", 0) > 0]

    def safe_avg(lst):
        return sum(lst) / len(lst) if lst else 0

    kg_m1_avg, nv_m1_avg, llm_m1_avg = safe_avg(kg_m1_list), safe_avg(nv_m1_list), safe_avg(llm_m1_list)
    kg_m2_avg, nv_m2_avg = safe_avg(kg_m2_list), safe_avg(nv_m2_list)
    kg_m3_avg, nv_m3_avg = safe_avg(kg_m3_list), safe_avg(nv_m3_list)
    kg_lat_avg, nv_lat_avg, llm_lat_avg = safe_avg(kg_lat_list), safe_avg(nv_lat_list), safe_avg(llm_lat_list)

    # 1. Stats by Type (A/B)
    type_stats = {}
    for d in all_data:
        t = d["type"]
        if t not in type_stats: type_stats[t] = {"kg": [], "naive": [], "llm": []}
        if "error" not in d["kg"]: type_stats[t]["kg"].append(d["kg"].get("score", 0))
        if "error" not in d["naive"]: type_stats[t]["naive"].append(d["naive"].get("score", 0))
        if "error" not in d["llm"]: type_stats[t]["llm"].append(d["llm"].get("score", 0))

    type_md = "| 類型 | 數量 | KG RAG (M1) | Naive (M1) | Pure LLM (M1) | 獲勝 |\n| :--- | :---: | :---: | :---: | :---: | :---: |\n"
    for t, s in sorted(type_stats.items()):
        kg_avg, nv_avg, llm_avg = safe_avg(s["kg"]), safe_avg(s["naive"]), safe_avg(s["llm"])
        winner = "KG" if kg_avg >= max(nv_avg, llm_avg) else ("Naive" if nv_avg >= llm_avg else "LLM")
        type_md += f"| {t} | {len(s['kg'])} | {kg_avg:.2f} | {nv_avg:.2f} | {llm_avg:.2f} | {winner} |\n"

    # 2. Stats by MECE Category
    cat_stats = {}
    for d in all_data:
        c = d["category"]
        if c not in cat_stats: cat_stats[c] = {"kg": [], "kg_recall": []}
        if "error" not in d["kg"]: cat_stats[c]["kg"].append(d["kg"].get("score", 0))
        if "recall" in d["kg"] and "error" not in d["kg"]["recall"]: cat_stats[c]["kg_recall"].append(d["kg"]["recall"].get("context_recall", 0))

    cat_md = "| MECE 分類 | 數量 | KG 正確性 (M1) | KG 召回率 (M2) |\n| :--- | :---: | :---: | :---: |\n"
    for c, s in sorted(cat_stats.items()):
        ravg = safe_avg(s["kg"])
        m2avg = safe_avg(s["kg_recall"])
        cat_md += f"| {c} | {len(s['kg'])} | {ravg:.2f} | {m2avg:.1%} |\n"

    # Per-Question Details
    details_md = ""
    for d in all_data:
        k_r, k_f = d['kg'].get('recall', {}).get('context_recall', 0), d['kg'].get('faithfulness', {}).get('faithfulness', 'N/A')
        n_r, n_f = d['naive'].get('recall', {}).get('context_recall', 0), d['naive'].get('faithfulness', {}).get('faithfulness', 'N/A')

        details_md += f"### {d['id']} [{d['section']}] - {d['category']} ({d['type']})\n"
        details_md += f"**問題**: {d['question']}\n\n"
        details_md += f"| 模式 | 分數 (M1) | 延遲 | 關鍵指標 |\n| :--- | :---: | :---: | :--- |\n"
        details_md += f"| **KG RAG** | {d['kg'].get('score', 0)}/5 | {d['kg'].get('latency', 0):.2f}s | Recall: {k_r:.1%}, Faith: {k_f} |\n"
        details_md += f"| Naive RAG | {d['naive'].get('score', 0)}/5 | {d['naive'].get('latency', 0):.2f}s | Recall: {n_r:.1%}, Faith: {n_f} |\n"
        details_md += f"| Pure LLM | {d['llm'].get('score', 0)}/5 | {d['llm'].get('latency', 0):.2f}s | (Zero-shot) |\n\n"
        details_md += f"**KG RAG 推理**: {d['kg'].get('reasoning', '無')}\n\n"
        details_md += "---\n\n"

    report = f"""# 稅務 RAG 系統基準測試報告 (KG vs Naive vs Pure LLM)

## 1. 執行總結 (Executive Summary)
本測試評估 **Knowledge Graph (IRAC)**、**Naive RAG (Vector only)** 與 **Pure LLM (Zero-shot)** 的表現。

| 指標 | KG RAG | Naive RAG | Pure LLM |
| :--- | :---: | :---: | :---: |
| **平均正確性 (M1)** | {kg_m1_avg:.2f} | {nv_m1_avg:.2f} | {llm_m1_avg:.2f} |
| **平均召回率 (M2)** | {kg_m2_avg:.1%} | {nv_m2_avg:.1%} | 0.0% |
| **推理忠實度 (M3)** | {kg_m3_avg:.1%} | {nv_m3_avg:.1%} | N/A |
| **平均延遲** | {kg_lat_avg:.2f}s | {nv_lat_avg:.2f}s | {llm_lat_avg:.2f}s |

## 2. 細分分析 (Breakdown)

### 2.1 依問題來源類型分析
{type_md}

### 2.2 依 MECE 分類分析 (僅限 KG RAG)
{cat_md}

## 3. 逐題詳細資料 (Per-Question Analysis)
{details_md}
"""
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"繁體中文報告已更新：{REPORT_PATH}")

if __name__ == "__main__":
    search_dir = RESULTS_DIR
    if len(sys.argv) > 1:
        search_dir = Path(sys.argv[1])
    aggregate(search_dir)
