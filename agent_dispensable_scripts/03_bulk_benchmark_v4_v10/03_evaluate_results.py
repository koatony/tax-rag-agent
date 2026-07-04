"""
Judge Runner - Gemini-based Evaluation for KG-RAG vs Naive-RAG Benchmark
=========================================================================
Improvement #4: RAGAS-style M3 Faithfulness Probe
  M3 is now "does every claim in the answer derive from the retrieved context?"
  (Was previously: "is there a matching rule in the KG candidate list?" - wrong!)

Improvement #6: Few-Shot Judge Calibration for M1 (G-Eval, Liu et al. EMNLP 2023)
  Added rubric examples to prevent score inflation.
"""

import os
import json
import time
import sys
import httpx
from dotenv import load_dotenv
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Load Environment
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))
load_dotenv(dotenv_path=root_dir / ".env", override=True)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
JUDGE_MODEL_NAME = os.environ.get("GEMINI_JUDGE_MODEL", "gemini-2.5-pro")

RAW_DIR = Path(__file__).resolve().parent / "raw_results"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

# ==============================================================================
# M1: Correctness Judge
# [Improvement #6 - G-Eval / MT-Bench]: Few-shot calibration to prevent score inflation.
#   Score 5: Completely correct, includes all necessary conditions and exceptions.
#   Score 3: Correct direction but missing key conditions (e.g. forgot "Notice 2006-83").
#   Score 1: Wrong direction or referenced an incorrect rule.
# ==============================================================================
M1_PROMPT = """You are a strict U.S. Tax Law Expert Evaluator. Compare the System Answer to the Ground Truth.

**Scoring Rubric (use ONLY integers 1-5):**
- **Score 5**: Answer is completely correct and covers all material conditions, exceptions, and required forms mentioned in the Ground Truth.
- **Score 4**: Answer is mostly correct, with only minor omissions (e.g., missing a specific form number that was clearly implied).
- **Score 3**: Answer gives the right direction but misses at least one important condition, exception, or required action from the Ground Truth.
- **Score 2**: Answer contains partially correct information but mixes it with incorrect claims or significant omissions.
- **Score 1**: Answer is wrong, gives harmful advice, or references entirely inapplicable rules.

**Calibration Examples:**
- If Ground Truth says "you must file Form 8919 AND report on line 1g" and Answer says "you must file Form 8919" (missing the line): Score = 4.
- If Answer correctly identifies the rule AND states the exception AND names the form: Score = 5.
- If Answer talks about a related but different rule (e.g., bankruptcy estate income vs self-employment tax rule): Score = 2.

---
**Question:** {question}
**Ground Truth:** {ground_truth}
**System Answer:** {system_answer}

Output ONLY a JSON object with no other text:
{{"score": <integer 1-5>, "reasoning": "<one sentence explaining the score>"}}"""

# ==============================================================================
# M2: Context Recall
# ==============================================================================
M2_PROMPT = """You are a U.S. Tax Law Expert. Assess whether the key information in the Ground Truth
is present in the Retrieved Context (the system's information source).

**Ground Truth:** {ground_truth}
**Retrieved Context:** {context}

Task: Identify which key facts, rules, conditions, and exceptions from the Ground Truth are covered
in the Retrieved Context, and what percentage is covered.

Output ONLY a JSON object:
{{"context_recall": <float 0.0 to 1.0>, "reasoning": "<key items covered vs missing>"}}"""

# ==============================================================================
# M3: Faithfulness (RAGAS-style)
# [Improvement #4 - RAGAS, Es et al. EACL 2024]
# CORRECT definition: does every claim in the Answer derive from the Context?
# (Previous version measured: "is the correct rule in the KG candidate list?" - WRONG!)
# ==============================================================================
M3_PROMPT = """You are a U.S. Tax Law Expert evaluating answer faithfulness.

**Definition**: A faithful answer ONLY makes claims that can be directly derived or inferred from the provided Context.
An unfaithful answer adds information not present in the Context, or contradicts it.

**Context (what the system retrieved):**
{context}

**System Answer:**
{answer}

**Task:**
1. List the main factual claims made in the System Answer.
2. For each claim, determine if it is SUPPORTED by the Context or NOT.
3. Calculate faithfulness = (supported claims) / (total claims).

Note: If the Context is empty or totally irrelevant, the answer is unfaithful by default.

Output ONLY a JSON object:
{{
  "claims": ["claim1", "claim2", ...],
  "supported": ["claim1", ...],
  "faithfulness_score": <float 0.0 to 1.0>,
  "faithfulness": "faithful",
  "reasoning": "<brief explanation>"
}}

Set "faithfulness" to "faithful" if faithfulness_score >= 0.7, otherwise "unfaithful"."""


def call_gemini_api(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{JUDGE_MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }

    import random
    for attempt in range(5):
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 429:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    # print(f"  [QUOTA] Rate limited. Waiting {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    continue
                resp.raise_for_status()
                data = resp.json()
                text = data['candidates'][0]['content']['parts'][0]['text'].strip()
                return json.loads(text)
        except Exception as e:
            if attempt == 4:
                return {"error": str(e), "score": 1, "context_recall": 0,
                        "faithfulness": "unfaithful", "faithfulness_score": 0.0,
                        "reasoning": f"API Error: {e}"}
            time.sleep(2)
    return {"error": "All attempts failed"}


def run_judge(raw_file):
    with open(raw_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    output_file = RESULTS_DIR / raw_file.name.replace("raw_qa_", "eval_qa_")
    if output_file.exists():
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                content = f.read()
                # If the file contains failure indicators, we force re-evaluation
                if "All attempts failed" not in content and "API Error" not in content:
                    print(f"[JUDGE] Skipping {raw_file.name} (already evaluated and healthy)")
                    return
                else:
                    print(f"[JUDGE] Re-evaluating {raw_file.name} due to previous failures...")
        except Exception:
            pass

    final_results = [None] * len(data)
    print(f"\n[JUDGE] Evaluating {len(data)} questions from {raw_file.name}...")

    with ThreadPoolExecutor(max_workers=5) as executor:
        def process_one(idx, item):
            print(f"  [{idx+1}/{len(data)}] Starting: {item['question'][:60]}...")
            question = item["question"]
            gt = item["ground_truth"]

            # === 1. KG RAG Judging ===
            res_kg = item["res_kg"]
            r1 = call_gemini_api(M1_PROMPT.format(question=question, ground_truth=gt, system_answer=res_kg["answer"]))
            r2 = call_gemini_api(M2_PROMPT.format(ground_truth=gt, context=res_kg["context"]))
            r3 = call_gemini_api(M3_PROMPT.format(context=res_kg["context"], answer=res_kg["answer"]))

            # === 2. Naive RAG Judging ===
            res_nv = item["res_naive"]
            nr1 = call_gemini_api(M1_PROMPT.format(question=question, ground_truth=gt, system_answer=res_nv["answer"]))
            nr2 = call_gemini_api(M2_PROMPT.format(ground_truth=gt, context=res_nv["context"]))
            nr3 = call_gemini_api(M3_PROMPT.format(context=res_nv["context"], answer=res_nv["answer"]))

            # === 3. Pure LLM Judging ===
            res_llm = item["res_llm"]
            lr1 = call_gemini_api(M1_PROMPT.format(question=question, ground_truth=gt, system_answer=res_llm["answer"]))

            # Normalization
            def get_s(r): return min(max(r.get("score", 1), 1), 5)

            final_results[idx] = {
                "id": item["id"],
                "type": item["type"],
                "category": item["category"],
                "question": question,
                "ground_truth": gt,
                "rag_kg": {
                    "answer": res_kg["answer"], "score": get_s(r1), "reasoning": r1.get("reasoning", ""),
                    "recall": r2, "faithfulness": r3, "latency": res_kg["latency"]
                },
                "rag_naive": {
                    "answer": res_nv["answer"], "score": get_s(nr1), "reasoning": nr1.get("reasoning", ""),
                    "recall": nr2, "faithfulness": nr3, "latency": res_nv["latency"]
                },
                "pure_llm": {
                    "answer": res_llm["answer"], "score": get_s(lr1), "reasoning": lr1.get("reasoning", ""),
                    "recall": {"context_recall": 0, "reasoning": "Zero-shot"},
                    "faithfulness": {"faithfulness_score": 0, "faithfulness": "N/A"},
                    "latency": res_llm["latency"]
                }
            }
            print(f"  [{idx+1}/{len(data)}] Done: {question[:30]}...")

        futures = [executor.submit(process_one, idx, item) for idx, item in enumerate(data)]
        for f in futures:
            try:
                f.result(timeout=400)
            except Exception as e:
                print(f"    ! Question timed out: {e}")

    out_file = RESULTS_DIR / f"eval_{raw_file.name.replace('raw_', '')}"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump([r for r in final_results if r is not None], f, indent=2, ensure_ascii=False)
    print(f"[JUDGE] Saved final results to {out_file.name}")


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 1:
        all_raws = [Path(sys.argv[1])]
    else:
        all_raws = sorted(list(RAW_DIR.glob("raw_*.json")))
    for raw_file in all_raws:
        out_name = f"eval_{raw_file.name.replace('raw_', '')}"
        if (RESULTS_DIR / out_name).exists():
            print(f"[JUDGE] Skipping {raw_file.name} (already evaluated)")
            continue
        run_judge(raw_file)


if __name__ == "__main__":
    main()
