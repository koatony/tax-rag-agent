"""
evaluator.py — Gemini-as-a-Judge 評估引擎
====================================================
對一份 QA 测试集 JSON 逐題執行：
  1. 呼叫 IRACRetriever.retrieve() 取得系統回答
  2. 呼叫 Gemini 評分（M1–M3）
  3. 記錄延遲（M5）
  最後輸出 JSON 結果檔與 Markdown 報告

執行方式：
    python tests/eval_suite/evaluator.py --qa tests/eval_suite/qa_dataset/qa_YYYYMMDD.json

輸出：
    tests/eval_suite/eval_results/eval_<ts>.json
    tests/eval_suite/eval_results/report_<ts>.md
"""

import sys
import os
import json
import time
import argparse
import datetime
from pathlib import Path

# 專案根目錄
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))

from dotenv import load_dotenv
load_dotenv(dotenv_path=root_dir / ".env")

import google.generativeai as genai
from retriever import IRACRetriever

# ==============================================================================
# 設定
# ==============================================================================
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY")
GEMINI_JUDGE_MODEL = os.environ.get("GEMINI_JUDGE_MODEL", "gemini-2.5-pro")

OUTPUT_DIR = Path(__file__).resolve().parent / "eval_results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# Judge Prompts
# ==============================================================================

M1_PROMPT = """You are an expert US tax law evaluator. Your task is to score the correctness of a system's answer.

**Question:** {question}
**Ground Truth Answer:** {ground_truth}
**System Answer:** {system_answer}

**Scoring Criteria (Answer Correctness):**
- 5: Fully correct, accurate, and covers all key points from ground truth.
- 4: Mostly correct with minor omissions or slightly imprecise wording.
- 3: Partially correct; captures the main idea but misses important details or has minor errors.
- 2: Mostly incorrect, but contains a small relevant element.
- 1: Completely wrong, irrelevant, or the system refused to answer an answerable question.

Output ONLY a JSON object, no markdown:
{{"score": <1-5>, "reasoning": "<1-2 sentence explanation>"}}"""

M2_PROMPT = """You are an expert US tax law evaluator. Your task is to assess Context Recall.

**Question:** {question}
**Ground Truth Answer:** {ground_truth}
**Retrieved Context (what was given to the system):** {context}

**Task:** 
1. Identify all key atomic facts in the Ground Truth Answer (e.g., dates, dollar amounts, specific conditions, rule names, form numbers).
2. Scan the entire Retrieved Context (it contains multiple candidates). 
3. Check if each atomic fact from the Ground Truth is present ANYWHERE in the context (either in the structured IRAC description or in the [Detailed Source Text] blocks).
4. Calculate the ratio: (Facts Found) / (Total Facts in Ground Truth).

Output ONLY a JSON object, no markdown:
{{"atomic_facts_in_ground_truth": <int>, "atomic_facts_in_context": <int>, "context_recall": <0.0-1.0>, "reasoning": "<1-2 sentences explaining which facts were found/missed>"}}"""

M3_PROMPT = """You are an expert US tax law evaluator. Your task is to assess Reasoning Path Faithfulness.

**Question:** {question}
**Ground Truth Answer refers to rule:** {ground_truth}
**KG Reasoning Paths used by system (rule_candidates top 5):** {rule_candidates}

Did the system use the correct rule or a closely related rule in its reasoning path?

- faithful: The correct or directly relevant rule appears in the top 5 candidates.
- unfaithful: The correct rule is absent; the system reasoned from a wrong path.
- lucky_hit: The rule is NOT in top candidates, but the answer was coincidentally correct.

Output ONLY a JSON object, no markdown:
{{"faithfulness": "faithful|unfaithful|lucky_hit", "top_rule_found": "<rule_id or null>", "reasoning": "<1-2 sentences>"}}"""

# ==============================================================================
# Gemini 呼叫
# ==============================================================================
def call_gemini_judge(prompt: str) -> dict:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(GEMINI_JUDGE_MODEL)
    response = model.generate_content(prompt)
    raw = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)

# ==============================================================================
# 主評估流程
# ==============================================================================
def run_evaluation(qa_paths: list[str]):
    if not GEMINI_API_KEY:
        print("❌ 請設定 GEMINI_API_KEY")
        return

    # 1. 收集所有的 JSON 檔案
    final_files = []
    for p in qa_paths:
        path_obj = Path(p)
        if path_obj.is_dir():
            # 找目錄下的所有 json (排除帶有 eval_ 或 report_ 前綴的)
            found = list(path_obj.glob("*.json"))
            final_files.extend([f for f in found if not f.name.startswith(("eval_", "report_"))])
        elif path_obj.is_file():
            final_files.append(path_obj)

    if not final_files:
        print(f"❌ 找不到有效的 QA JSON 檔案於: {qa_paths}")
        return

    # 2. 載入並合併 QA pairs
    all_qa_pairs = []
    sources_info = []
    for f_path in final_files:
        try:
            with open(f_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                pairs = data.get("qa_pairs", [])
                all_qa_pairs.extend(pairs)
                sources_info.append({
                    "file": f_path.name,
                    "count": len(pairs),
                    "path_type": data.get("metadata", {}).get("path_type", "unknown")
                })
        except Exception as e:
            print(f"  [Warning] 無法讀取檔案 {f_path}: {e}")

    n = len(all_qa_pairs)
    if n == 0:
        print("❌ 載入的 QA 總數為 0")
        return

    print(f"\n{'='*65}")
    print(f"  Evaluation Suite — 合計 {n} 題 | Judge: {GEMINI_JUDGE_MODEL}")
    print(f"  QA 來源 ({len(final_files)} 個檔案):")
    for s in sources_info:
        print(f"    - {s['file']} ({s['count']} 題, Type: {s['path_type']})")
    print(f"{'='*65}\n")

    # 初始化 IRACRetriever（一次性，避免重複載入）
    print("⏳ 正在初始化 IRACRetriever（首次需建立向量索引）...")
    retriever = IRACRetriever.from_active_kgs()
    print("✅ 初始化完成\n")

    from tqdm import tqdm

    per_query_results = []

    # 使用 tqdm 建立進度條
    pbar = tqdm(all_qa_pairs, desc="評估進度", unit="題")
    for i, qa in enumerate(pbar, start=1):
        qid        = qa.get("id", f"Q{i:03d}")
        question   = qa.get("question", "")
        ground_truth = qa.get("ground_truth", "")
        category   = qa.get("category", "Unknown")
        difficulty = qa.get("difficulty", "Unknown")

        pbar.set_description(f"正在評估 {qid} [{category}]")
        
        # 使用 tqdm.write 代替 print 以免破壞進度條佈局
        tqdm.write(f"\n[{i}/{n}] {qid} [{category}/{difficulty}]")
        tqdm.write(f"  Q: {question[:90]}...")

        # ── Step 1: 呼叫 RAG ──
        t0 = time.time()
        state = retriever.retrieve(question)
        latency_ms = (time.time() - t0) * 1000

        system_answer = state.get("answer", "")
        context       = state.get("context", "")
        rule_candidates = [c.get("rule_id", "") for c in state.get("rule_candidates", [])[:5]]

        tqdm.write(f"  ⏱️  延遲: {latency_ms:.0f}ms | 候選規則: {rule_candidates[:3]}")

        # ── Step 2: M1 Answer Correctness ──
        try:
            m1 = call_gemini_judge(M1_PROMPT.format(
                question=question,
                ground_truth=ground_truth,
                system_answer=system_answer
            ))
        except Exception as e:
            tqdm.write(f"  [⚠️ M1 評分失敗] {e}")
            m1 = {"score": -1, "reasoning": str(e)}

        # ── Step 3: M2 Context Recall ──
        try:
            m2 = call_gemini_judge(M2_PROMPT.format(
                question=question,
                ground_truth=ground_truth,
                context=context[:3000]
            ))
        except Exception as e:
            tqdm.write(f"  [⚠️ M2 評分失敗] {e}")
            m2 = {"atomic_facts_in_ground_truth": -1, "atomic_facts_in_context": -1, "context_recall": -1, "reasoning": str(e)}

        # ── Step 4: M3 Faithfulness ──
        try:
            m3 = call_gemini_judge(M3_PROMPT.format(
                question=question,
                ground_truth=ground_truth,
                rule_candidates=", ".join(rule_candidates)
            ))
        except Exception as e:
            tqdm.write(f"  [⚠️ M3 評分失敗] {e}")
            m3 = {"faithfulness": "unknown", "top_rule_found": None, "reasoning": str(e)}

        m1_score = m1.get("score", -1)
        m2_recall = m2.get("context_recall", -1)
        m3_faith  = m3.get("faithfulness", "unknown")

        tqdm.write(f"  ✅ M1={m1_score}/5 | M2={m2_recall:.2f} | M3={m3_faith} | M5={latency_ms:.0f}ms")

        per_query_results.append({
            "id": qid,
            "category": category,
            "difficulty": difficulty,
            "question": question,
            "ground_truth": ground_truth,
            "system_answer": system_answer,
            "rule_candidates_top5": rule_candidates,
            "m1_correctness": m1,
            "m2_context_recall": m2,
            "m3_faithfulness": m3,
            "m5_latency_ms": round(latency_ms, 1),
        })

    # ── 彙整指標 ──
    valid_m1 = [r["m1_correctness"].get("score", -1) for r in per_query_results if r["m1_correctness"].get("score", -1) > 0]
    valid_m2 = [r["m2_context_recall"].get("context_recall", -1) for r in per_query_results if r["m2_context_recall"].get("context_recall", -1) >= 0]
    valid_m5 = [r["m5_latency_ms"] for r in per_query_results if r["m5_latency_ms"] > 0]
    m3_counts = {"faithful": 0, "unfaithful": 0, "lucky_hit": 0, "unknown": 0}
    for r in per_query_results:
        k = r["m3_faithfulness"].get("faithfulness", "unknown")
        m3_counts[k] = m3_counts.get(k, 0) + 1

    avg_m1  = sum(valid_m1) / len(valid_m1) if valid_m1 else 0
    avg_m2  = sum(valid_m2) / len(valid_m2) if valid_m2 else 0
    avg_m5  = sum(valid_m5) / len(valid_m5) if valid_m5 else 0
    m3_faith_rate = m3_counts["faithful"] / n if n > 0 else 0

    summary_metrics = {
        "n_questions": n,
        "avg_m1_answer_correctness": round(avg_m1, 3),
        "avg_m2_context_recall": round(avg_m2, 3),
        "m3_faithfulness_rate": round(m3_faith_rate, 3),
        "m3_breakdown": m3_counts,
        "avg_m5_latency_ms": round(avg_m5, 1),
    }

    # ── 儲存 JSON ──
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = OUTPUT_DIR / f"eval_{ts}.json"
    output = {
        "metadata": {
            "evaluated_at": ts,
            "qa_sources": sources_info,
            "judge_model": GEMINI_JUDGE_MODEL,
        },
        "summary_metrics": summary_metrics,
        "per_query_results": per_query_results,
    }
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # ── 生成 Markdown 報告 ──
    report_path = OUTPUT_DIR / f"report_{ts}.md"
    _write_markdown_report(report_path, output, ts)

    print(f"\n{'='*65}")
    print(f"  📊 評估摘要")
    print(f"{'='*65}")
    print(f"  M1 平均答案正確性 : {avg_m1:.3f} / 5.0")
    print(f"  M2 平均上下文召回 : {avg_m2:.3f}")
    print(f"  M3 推理忠實度     : {m3_faith_rate:.1%} ({m3_counts})")
    print(f"  M5 平均延遲       : {avg_m5:.0f} ms")
    print(f"\n  📁 結果：{result_path}")
    print(f"  📄 報告：{report_path}")
    return str(result_path)


def _write_markdown_report(path: Path, output: dict, ts: str):
    meta = output["metadata"]
    sources_str = ", ".join([s["file"] for s in meta["qa_sources"]])
    metrics = output["summary_metrics"]
    rows = output["per_query_results"]

    lines = [
        f"# 評估報告 — {ts}",
        f"",
        f"**QA 來源**: `{sources_str}`  ",
        f"**評估模型**: `{meta['judge_model']}`  ",
        f"**題數**: {metrics['n_questions']}",
        f"",
        f"## 摘要指標",
        f"",
        f"| 指標 | 數值 |",
        f"|------|------|",
        f"| M1 答案正確性（avg） | {metrics['avg_m1_answer_correctness']:.3f} / 5.0 |",
        f"| M2 上下文召回（avg） | {metrics['avg_m2_context_recall']:.3f} |",
        f"| M3 推理忠實度 | {metrics['m3_faithfulness_rate']:.1%} |",
        f"| M5 平均延遲 (ms) | {metrics['avg_m5_latency_ms']:.0f} |",
        f"",
        f"**M3 分類明細**: {metrics['m3_breakdown']}",
        f"",
        f"## 逐題明細",
        f"",
        f"| ID | Category | Difficulty | M1 | M2 | M3 | M5 (ms) |",
        f"|----|----------|-----------|----|----|-----|---------|",
    ]
    for r in rows:
        m1s = r["m1_correctness"].get("score", "N/A")
        m2r = r["m2_context_recall"].get("context_recall", -1)
        m2s = f"{m2r:.2f}" if m2r >= 0 else "N/A"
        m3f = r["m3_faithfulness"].get("faithfulness", "N/A")
        lines.append(f"| {r['id']} | {r['category']} | {r['difficulty']} | {m1s} | {m2s} | {m3f} | {r['m5_latency_ms']:.0f} |")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gemini-as-a-Judge 評估引擎")
    parser.add_argument("--qa", type=str, required=True, nargs="+", help="QA dataset JSON 路徑或目錄 (支援多個)")
    args = parser.parse_args()
    run_evaluation(qa_paths=args.qa)
