"""
IRAC KG 檢索框架 Demo 測試腳本
執行方式：
    export OPENAI_API_KEY=sk-...
    python demo.py
"""

import sys
from pathlib import Path

# 將專案根目錄加入路徑，以便導入 retriever
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))

import os
import json
from dotenv import load_dotenv
from retriever import IRACRetriever

# 載入 .env 檔案中的環境變數
load_dotenv(dotenv_path=root_dir / ".env")

GRAPHML_PATH = str(root_dir / "data" / "graph_chunk_entity_relation.graphml")

# 測試問題清單（研究實驗：測試 OOD 拒絕功能與 Lexical Gap 翻譯能力）
TEST_QUERIES = [
    # --- OOD (Out-of-Domain) 測試題 ---
    "How do I fix a leaky faucet in my bathroom? My plumber is charging me $500.",
    "What is the best roster strategy for winning my fantasy football league this year?",

    # --- Lexical Gap 嚴苛稅務題 ---
    # 情境 1：未直接提及 Gambling 但涉及 Fantasy Football 與賭博抵稅限制 (Gambling Loss Deduction)
    "I play fantasy football for money with my coworkers. Last year I won $5,000 but lost $6,000 placing bets on other sports apps. Can I report a net loss of $1,000 to the IRS?",
    
    # 情境 2：醫療支出與資產增值相減的複雜案例 (Capital Expense for Medical Care)
    "To help my disabled spouse get around, I installed a special elevator in our home. It cost me $25,000, and my appraiser said it increased the house's value by $10,000. How much of this can I claim as a deductible medical expense?",
    
    # 情境 3：自然災害與保險理賠的混合情形 (Federally Declared Disaster Casualty Loss)
    "My beach house in Florida was severely damaged by a hurricane that the President later declared a federal disaster. The repair cost was $50,000, and my insurance only reimbursed me $30,000. Can I deduct the remaining $20,000?",
]


def run_demo():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("請設定 OPENAI_API_KEY 環境變數")
        return

    print("=" * 60)
    print("初始化 IRAC 檢索器（載入 KG + 建立向量索引）")
    print("注意：第一次執行需要呼叫 OpenAI Embeddings API，需要一點時間")
    print("=" * 60)

    # 初始化 IRAC 檢索器（自動從 .env 讀取 ACTIVE_KGS）
    retriever = IRACRetriever.from_active_kgs(
        // openai_api_key removed - no longer needed
        top_k_rule     = 30,
        top_k_fact     = 30,
        top_n_subgraph = 3,
    )

    for i, query in enumerate(TEST_QUERIES, start=1):
        print(f"\n{'='*60}")
        print(f"測試問題 {i}：{query}")
        print("=" * 60)

        result = retriever.retrieve(query)

        # Debug 資訊
        print(f"\n[Debug]")
        debug = result.get("debug_info", {})
        print(f"  rule_query:       {result['rule_query']}")
        print(f"  fact_query:       {result['fact_query']}")
        print(f"  Track A 命中數:   {debug.get('track_a_hits', 0)}")
        print(f"  Track B fact 數:  {debug.get('track_b_fact_hits', 0)}")
        print(f"  合併後候選數:     {debug.get('total_candidates', 0)}")
        print(f"  雙軌命中數:       {debug.get('dual_hit_count', 0)}")
        print(f"  最終子圖數:       {debug.get('subgraphs_built', 0)}")

        # 印出每個子圖的摘要
        print("\n[子圖摘要]")
        for j, sg in enumerate(result["subgraphs"], start=1):
            dual = "✓ 雙軌" if sg["is_dual_hit"] else "  單軌"
            print(f"  子圖{j} {dual} | score={sg['final_score']:.3f} | "
                  f"completeness={sg['completeness_score']:.1f} | "
                  f"I={sg['issue_count']} R=1 A={sg['fact_count']} C={sg['conclusion_count']}")
            print(f"    rule: {sg['rule_id'][:70]}")

        # 印出最終 context（這是會送給 LLM 的內容）
        print("\n[最終 Context]")
        print(result["context"])

        # 印出 Mock 表格內容
        print("\n[當前表格 (OCR Mock)]")
        print(result["table_context"])

        # 印出 LLM 生成的回答
        print(f"\n{'-'*60}")
        print("💡 LLM 生成回答：")
        print(f"{'-'*60}")
        print(result["answer"])
        print(f"{'-'*60}")


if __name__ == "__main__":
    run_demo()
