import os
import sys
import json
import time
from pathlib import Path

# Add project root to path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))

from dotenv import load_dotenv
load_dotenv(dotenv_path=root_dir / ".env")

# Force specific ACTIVE_KGS for full coverage
os.environ["ACTIVE_KGS"] = ",".join([
    "tax_kg_v1/pub_525_04_employee_compensation",
    "tax_kg_v1/pub_525_05_miscellaneous_compensation",
    "tax_kg_v1/pub_525_06_fringe_benefits",
    "tax_kg_v1/pub_525_07_special_rules_for_certain_employees",
    "tax_kg_v1/pub_525_08_business_and_investment_income",
    "tax_kg_v1/pub_525_09_sickness_and_injury_benefits",
    "tax_kg_v1/pub_525_10_miscellaneous_income",
])
os.environ["ENABLE_TABLE_CONTEXT"] = "0"

from retriever import IRACRetriever, RetrieverConfig

def analyze_all():
    # Load target questions
    targets_file = "/tmp/target_questions.json"
    if not os.path.exists(targets_file):
        print(f"Error: {targets_file} not found.")
        return

    with open(targets_file, "r", encoding="utf-8") as f:
        targets = json.load(f)

    print(f"Initializing IRACRetriever with KGs: {os.environ['ACTIVE_KGS']}...")
    retriever = IRACRetriever.from_active_kgs()
    
    report_md = "# KG RAG 深度失敗分析報告 (10 題精選)\n\n"
    report_md += "本報告方針：針對 10 個 KG 表現不佳的案例進行「檢索路徑」追蹤，找出檢索或推理的斷點。\n\n"

    for i, target in enumerate(targets, 1):
        q_id = target["id"]
        query = target["question"]
        gt = target["ground_truth"]
        
        print(f"[{i}/10] Processing {q_id}...")
        
        t0 = time.time()
        try:
            result = retriever.retrieve(query, use_source_text=True)
            latency = time.time() - t0
            
            debug = result.get("debug_info", {})
            rewrite = debug.get("rewritten_query") or debug.get("abstract_query") or debug.get("hyde_query", "N/A")
            candidates = result.get("rule_candidates", [])
            is_reranked = debug.get("reranked", False)
            top_15_ids = debug.get("top_15_ids", [])
            answer = result.get("answer", "N/A")
            
            # Formatting the report entry
            report_md += f"## 案例 {i}: {q_id}\n"
            report_md += f"- **耗時**: {latency:.2f}s\n"
            report_md += f"### 1. 原始問題\n{query}\n\n"
            report_md += f"### 2. 正確答案 (Ground Truth)\n{gt}\n\n"
            report_md += "### 3. 檢索路徑追蹤\n"
            report_md += f"- **問題重寫 (Step-Back)**: {rewrite}\n"
            report_md += f"- **命中 Rule 數量**: {len(candidates)}\n"
            report_md += f"- **是否執行 Rerank**: {'是' if is_reranked else '否'}\n"
            
            report_md += "- **候選規則列表 (含 Rerank 結果)**:\n"
            for j, cand in enumerate(candidates, 1):
                rule_id = cand["rule_id"]
                is_dual = " (雙軌命中)" if cand.get("is_dual_hit") else ""
                rerank_mark = " [🔥 TOP 15 Reranked]" if is_reranked and rule_id in top_15_ids else ""
                report_md += f"    {j}. **{rule_id}** (Score: {cand['final_score']:.4f}){is_dual}{rerank_mark}\n"
                report_md += f"       > {cand.get('rule_description', 'N/A')[:300]}...\n"
            
            if not candidates:
                report_md += "    (無候選規則)\n"

            report_md += f"\n### 4. KG RAG 最終回答\n{answer}\n\n"
            
            # Custom Analysis/Evaluation (The "Guess")
            eval_text = "分析結論："
            if not candidates:
                eval_text += "檢索鏈條在庫中斷掉。Vector/BM25 均未能在 Top-K 中抓到相關規則，可能是 Step-Back 重寫偏離了原始法律用語。"
            elif "cannot determine" in answer.lower() or "無法判斷" in answer:
                eval_text += "檢索到了 Rule，但 Context 可能不包含答案所需的特定事實 (Material Fact)。檢索子圖 (Subgraph) 擴展不足或該規則節點的內容不夠完整。"
            elif len(result.get("context", "")) < 100:
                eval_text += "Context 太過稀疏。雖然有 Rule 節點，但相關事實節點 (A) 或議題節點 (I) 缺失，導致 LLM 判定資訊不足。"
            else:
                eval_text += "Context 存在但答案錯誤。可能是 Reranker 排序了不相關的規則排在前面，或 LLM 的推理出現偏差。"
            
            report_md += f"### 5. 專家評估與優化建議\n{eval_text}\n\n"
            report_md += "---\n\n"
            
        except Exception as e:
            print(f"      [!] Failed to process {q_id}: {e}")
            report_md += f"## 案例 {i}: {q_id}\n"
            report_md += f"**處理失敗**: {e}\n\n---\n\n"

    output_path = root_dir / "tests" / "KG_FAILURE_REPORT.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_md)
    print(f"Report generated: {output_path}")

if __name__ == "__main__":
    analyze_all()
