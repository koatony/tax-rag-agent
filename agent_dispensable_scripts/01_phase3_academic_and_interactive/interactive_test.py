#!/usr/bin/env python3
"""
interactive_test.py — 互動式檢索測試工具
============================================
直接輸入問題 → 查看 Retrieved Context、Rule Candidates 和最終答案。

使用方式：
    cd /home/wmlab/projects/Retrieve
    python3 tests/interactive_test.py

進階選項：
    # 選擇特定 KG（覆蓋 .env 的 ACTIVE_KGS）
    ACTIVE_KGS=tax_kg_v1/pub_525_09_sickness_and_injury_benefits python3 tests/interactive_test.py

    # 切換 naive 模式（純向量）
    RETR_MODE=naive python3 tests/interactive_test.py
"""

import sys
import os
import json
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))

from dotenv import load_dotenv
load_dotenv(dotenv_path=root_dir / ".env")

from retriever import IRACRetriever, RetrieverConfig

# 初始化配置以供全域使用
cfg = RetrieverConfig.from_env()


def print_section(title: str, char: str = "=", width: int = 72):
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}")


def print_result(result: dict):
    """格式化顯示檢索結果"""
    rule_candidates = result.get("rule_candidates", [])
    answer = result.get("answer", "")
    debug = result.get("debug_info", {})

    # --- 1. Query Enhancement (Multi-Query / Step-Back) ---
    bundle = result.get("query_bundle", {})
    if bundle:
        print_section("🔍 Step 1: Query Enhancement (Multi-Query Fusion)", char="-")
        for q_type, q_text in bundle.items():
            display_name = {
                "original": "Original Query ",
                "step_back": "Step-Back (Law)",
                "hyde": "HyDE (Simulated)"
            }.get(q_type, q_type.capitalize())
            print(f"  [{display_name}]: {q_text}")
        
        # Show Path Hits Summary
        print(f"\n  [Path Hits] Rule Search: {debug.get('rule_search_hit_count', 0)} | Fact Search: {debug.get('fact_search_hit_count', 0)}")
    else:
        rewrite_q = debug.get("rewritten_query") or debug.get("abstract_query") or debug.get("hyde_query")
        if rewrite_q:
            print_section("🔍 Step 1: Query Enhancement (Step-Back)", char="-")
            print(f"  Abstract Rule Concept: {rewrite_q}")

    # --- 2. Rule Candidates (Retrieval & Rerank) ---
    summary = debug.get("retrieval_summary", {})
    is_reranked = summary.get("rerank_method") != "None"
    method = summary.get("rerank_method", "LLM").capitalize()
    rerank_text = f" ({method} Reranked)" if is_reranked else ""
    
    tier_info = ""
    stats = summary.get("tier_stats")
    if stats:
        tier_info = f" [T1:{stats['tier1']} T2:{stats['tier2']} T3:{stats['tier3']}]"
    
    strategy = summary.get("strategy", "N/A")
    print_section(f"📋 Step 2: Rule Candidates (Count: {len(rule_candidates)}){rerank_text} | Strat: {strategy}{tier_info}", char="-")
    
    top_15_ids = debug.get("top_15_ids", [])
    track_a_hits = debug.get("track_a_hits_by_query", {})
    track_b_rules = debug.get("track_b_rules_by_query", {})
    
    # Display all items
    for i, cand in enumerate(rule_candidates, start=1):
        rule_id = cand.get("rule_id", "N/A")
        score = cand.get("final_score", 0.0)
        is_dual = "✦" if cand.get("is_dual_hit") else " "
        
        # Determine sources (直接使用後端傳回的語意化標籤)
        src_str = ",".join(cand.get("sources", []))
        if not src_str: src_str = "Unknown"
        
        # Mark if it was in Top-15 after rerank
        rerank_mark = "[🔥R]" if is_reranked and rule_id in top_15_ids else "    "
        
        # --- 獲取 Tier (直接由後端判定) ---
        assigned_tier = f"T{cand.get('tier', 3)}"
        score_val = cand.get("final_score", 0.0)
        init_score = cand.get("initial_score", 0.0)

        desc = cand.get("rule_description", "").strip()
        score_display = f"{score_val:.4f} (Init: {init_score:.4f})" if is_reranked else f"{score_val:.4f}"
        print(f"  {is_dual} {rerank_mark} [{assigned_tier}] [{score_display}] [Src: {src_str}] {rule_id}")
        print(f"            └ {desc}")

    if not rule_candidates:
        print("  (無候選規則)")

    # --- 2.5 Final Combined Prompt (Sent to LLM) ---
    print_section("📝 Step 2.5: Full RAG Prompt (System + Instructions + Context)", char="-")
    full_prompt = debug.get("full_prompt_sent", "")
    if full_prompt:
        # 展示完整的 Prompt，包含 System Prompt 的細節規範
        print(full_prompt)
    else:
        # Fallback to pure context if full_prompt is missing
        assembled_context = result.get("context", "")
        print(assembled_context if assembled_context else "  (無內容)")

    # --- 3. Final Answer ---
    print_section("🤖 Step 3: Final Answer", char="*")
    print(answer)
    
    # --- 4. Token Usage Statistics ---
    usage = result.get("token_usage", {})
    in_tokens = usage.get("input_tokens", 0)
    out_tokens = usage.get("output_tokens", 0)
    total_tokens = in_tokens + out_tokens
    
    print("\n" + "-" * 72)
    print(f"  📊 Token 消耗統計 (Cumulative Usage):")
    print(f"     📥 Input  : {in_tokens:<8} tokens")
    print(f"     📤 Output : {out_tokens:<8} tokens")
    print(f"     📈 Total  : {total_tokens:<8} tokens")
    print("*" * 72)


def main():
    # 顯示目前設定
    cfg = RetrieverConfig.from_env()
    active_kgs = os.environ.get("ACTIVE_KGS", "tax_kg_v1")
    mode = os.environ.get("RETR_MODE", "irac")

    print("=" * 72)
    print("  🔎 IRAC RAG 互動式測試工具")
    print("=" * 72)
    print(f"  Active KGs   : {active_kgs}")
    print(f"  Mode         : {mode.upper()}")
    print(f"  LLM          : {os.environ.get('LLM_MODEL_NAME', 'gemini-2.5-flash')}")
    print(f"  Embed        : Ollama {os.environ.get('OLLAMA_EMBED_MODEL', 'bge-m3')} @ {os.environ.get('OLLAMA_BASE_URL', 'http://140.115.54.89:11434')}")
    print(f"  Config       : {cfg.summary()}")
    print("=" * 72)
    print("  輸入問題後按 Enter 執行；輸入 'quit' 或 Ctrl+C 結束。")
    print("=" * 72)

    # 初始化（只做一次）
    print("\n⏳ 正在初始化 IRACRetriever（首次需建立向量索引，需要幾秒）...")
    try:
        retriever = IRACRetriever.from_active_kgs()
    except Exception as e:
        print(f"\n❌ 初始化失敗: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    print("✅ 初始化完成！\n")

    while True:
        try:
            query = input("❓ 輸入問題 > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 結束測試。")
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            print("👋 結束測試。")
            break

        try:
            print(f"\n🔄 正在檢索，請稍候...")
            import time
            t0 = time.time()
            result = retriever.retrieve(query, use_source_text=True)
            latency = time.time() - t0
            print(f"   ⏱ 耗時: {latency:.2f}s")
            print_result(result)
        except Exception as e:
            print(f"\n❌ 檢索失敗: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
