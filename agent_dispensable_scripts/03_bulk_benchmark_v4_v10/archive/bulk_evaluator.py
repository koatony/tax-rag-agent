import os
import json
import time
import datetime
import sys
import google.generativeai as genai
from dotenv import load_dotenv
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# Load Environment
root_dir = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(root_dir))
load_dotenv(dotenv_path=root_dir / ".env")

from retriever import IRACRetriever

# Configuration
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
JUDGE_MODEL_NAME = os.environ.get("GEMINI_JUDGE_MODEL", "gemini-flash-latest")
DATA_DIR = Path(__file__).resolve().parent / "data"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

# Evaluation Prompts
M1_PROMPT = """You are an expert US tax law evaluator. Compare the System Answer against the Ground Truth.
**Question:** {question}
**Ground Truth:** {ground_truth}
**System Answer:** {system_answer}

**Scoring Criteria (1-5):**
1: Completely wrong or hallucinated.
2: Partially correct but misses major rules.
3: Correct on the main rule but missing specific conditions/details.
4: Correct and detailed, matches ground truth.
5: Perfect answer with precise reasoning and rule citation.

Output ONLY a JSON object, no markdown:
{{"score": <int>, "reasoning": "<1-2 sentences explaining the score>"}}"""

M2_PROMPT = """You are an expert evaluator for RAG (Retrieval-Augmented Generation) systems. 
Your task is to calculate Context Recall.

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

def call_gemini(prompt):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(JUDGE_MODEL_NAME)
    try:
        response = model.generate_content(prompt)
        text = response.text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(text)
    except Exception as e:
        print(f"Error calling Gemini: {e}")
        return {"score": 1, "reasoning": f"Error: {e}"}

def evaluate_dual_mode(qa_file):
    with open(qa_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    metadata = data["metadata"]
    source_kg = metadata["source_kg"]
    qa_pairs = data["qa_pairs"]
    
    print(f"\nEvaluating {len(qa_pairs)} questions from {qa_file.name}...")
    
    # Initialize Retriever once per KG chapter
    os.environ["ACTIVE_KGS"] = source_kg
    retriever = IRACRetriever.from_active_kgs()
    
    results = []
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        for i, qa in enumerate(qa_pairs, start=1):
            print(f"  [{i}/{len(qa_pairs)}] Question: {qa['question'][:60]}...")
            
            # --- Mode 1: KG RAG (Full IRAC + KG) ---
            print(f"    - Running KG-RAG...")
            retriever.config.mode = "irac"
            retriever.config.enable_hyde = True
            retriever.config.enable_kg_subgraph = True
            retriever.config.enable_dual_track = True
            
            start_t = time.time()
            res_kg = retriever.retrieve(qa["question"], use_source_text=True)
            kg_latency = time.time() - start_t
            print(f"    - KG-RAG Done ({kg_latency:.2f}s)")

            # Prepare KG candidates for judge
            kg_cands_top5 = [
                {"id": c.get("rule_id"), "desc": c.get("rule_description", "")[:200]}
                for c in res_kg.get("rule_candidates", [])[:5]
            ]

            # Evaluate KG in Parallel
            print(f"    - Judging KG metrics (Parallel)...")
            f1 = executor.submit(call_gemini, M1_PROMPT.format(question=qa["question"], ground_truth=qa["ground_truth"], system_answer=res_kg["answer"]))
            f2 = executor.submit(call_gemini, M2_PROMPT.format(ground_truth=qa["ground_truth"], context=res_kg["context"]))
            f3 = executor.submit(call_gemini, M3_PROMPT.format(question=qa["question"], ground_truth=qa["ground_truth"], rule_candidates=json.dumps(kg_cands_top5)))
            
            try:
                m1_kg = f1.result(timeout=60)
                m2_kg = f2.result(timeout=60)
                m3_kg = f3.result(timeout=60)
            except Exception as e:
                print(f"    ! KG Judging Timeout or Error: {e}")
                m1_kg = {"score": 1, "reasoning": f"Error: {e}"}
                m2_kg = {"context_recall": 0, "reasoning": f"Error: {e}"}
                m3_kg = {"faithfulness": "unfaithful", "reasoning": f"Error: {e}"}
            print(f"    - KG Judging Done")

            # --- Mode 2: Naive RAG (Vector Search Only) ---
            print(f"    - Running Naive-RAG...")
            retriever.config.mode = "naive"
            retriever.config.enable_hyde = False
            retriever.config.enable_kg_subgraph = False
            retriever.config.enable_dual_track = False
            
            start_t = time.time()
            res_naive = retriever.retrieve(qa["question"], use_source_text=True)
            naive_latency = time.time() - start_t
            print(f"    - Naive-RAG Done ({naive_latency:.2f}s)")
            
            # Prepare Naive candidates for naive judge
            naive_cands_top5 = [
                {"id": c.get("rule_id"), "desc": c.get("rule_description", "")[:200]}
                for c in res_naive.get("rule_candidates", [])[:5]
            ]

            # Evaluate Naive in Parallel
            print(f"    - Judging Naive metrics (Parallel)...")
            nf1 = executor.submit(call_gemini, M1_PROMPT.format(question=qa["question"], ground_truth=qa["ground_truth"], system_answer=res_naive["answer"]))
            nf2 = executor.submit(call_gemini, M2_PROMPT.format(ground_truth=qa["ground_truth"], context=res_naive["context"]))
            nf3 = executor.submit(call_gemini, M3_PROMPT.format(question=qa["question"], ground_truth=qa["ground_truth"], rule_candidates=json.dumps(naive_cands_top5)))
            
            try:
                m1_naive = nf1.result(timeout=60)
                m2_naive = nf2.result(timeout=60)
                m3_naive = nf3.result(timeout=60)
            except Exception as e:
                print(f"    ! Naive Judging Timeout or Error: {e}")
                m1_naive = {"score": 1, "reasoning": f"Error: {e}"}
                m2_naive = {"context_recall": 0, "reasoning": f"Error: {e}"}
                m3_naive = {"faithfulness": "unfaithful", "reasoning": f"Error: {e}"}
            print(f"    - Naive Judging Done")

            result_obj = {
                "id": qa["id"],
                "type": qa["path_type"],
                "category": qa.get("category", "Unknown"),
                "question": qa["question"],
                "ground_truth": qa["ground_truth"],
                "rag_kg": {
                    "answer": res_kg["answer"],
                    "score": m1_kg.get("score", 1),
                    "reasoning": m1_kg.get("reasoning", ""),
                    "recall": m2_kg,
                    "faithfulness": m3_kg,
                    "context": res_kg["context"],
                    "rule_candidates_all": [
                        {"id": c.get("rule_id"), "score": c.get("final_score"), "is_dual_hit": c.get("is_dual_hit")}
                        for c in res_kg.get("rule_candidates", [])
                    ],
                    "hyde_query": res_kg.get("hyde_query", ""),
                    "subgraphs": res_kg.get("subgraphs", []),
                    "latency": kg_latency or 0
                },
                "rag_naive": {
                    "answer": res_naive["answer"],
                    "score": m1_naive.get("score", 1),
                    "reasoning": m1_naive.get("reasoning", ""),
                    "recall": m2_naive,
                    "faithfulness": m3_naive,
                    "context": res_naive["context"],
                    "rule_candidates_all": [
                        {"id": c.get("rule_id"), "score": c.get("final_score")}
                        for c in res_naive.get("rule_candidates", [])
                    ],
                    "latency": naive_latency or 0
                }
            }
            results.append(result_obj)
            
            # Checkpoint
            temp_out = RESULTS_DIR / f"partial_{qa_file.stem}.json"
            with open(temp_out, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)

    return results

def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    all_files = sorted(list(DATA_DIR.glob("qa_*.json")))
    
    if not all_files:
        print(f"No QA files found in {DATA_DIR}.")
        return

    for qa_file in all_files:
        final_out = RESULTS_DIR / f"eval_{qa_file.name}"
        if final_out.exists():
            print(f"Skipping already finished file: {qa_file.name}")
            continue
            
        results = evaluate_dual_mode(qa_file)
        with open(final_out, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        partial_file = RESULTS_DIR / f"partial_{qa_file.stem}.json"
        if partial_file.exists():
            partial_file.unlink()
        print(f"Finished {qa_file.name}")

if __name__ == "__main__":
    main()
