import os
import json
import time
import sys
import random
import argparse
import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load Environment
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))
load_dotenv(dotenv_path=root_dir / ".env")

from retriever import IRACRetriever

DATA_DIR = Path(__file__).resolve().parent / "data"
RAW_DIR = Path(__file__).resolve().parent / "raw_results"

# Global retriever cache
RETRIEVERS = {}

def get_retriever(kg_name=None, full_db=False):
    key = "FULL_DB" if full_db else kg_name
    if key not in RETRIEVERS:
        if full_db:
            print("\n[RAG] Initializing FULL DATABASE retriever (loading all KGs)...")
            # Discover all KGs in data/tax_kg_v1
            kg_root = root_dir / "data" / "tax_kg_v1"
            all_kgs = []
            for item in kg_root.iterdir():
                if item.is_dir() and item.name.startswith("pub_"):
                    all_kgs.append(f"tax_kg_v1/{item.name}")
            active_kgs_str = ",".join(all_kgs)
            os.environ["ACTIVE_KGS"] = active_kgs_str
            print(f"      Active KGs: {active_kgs_str}")
        else:
            print(f"\n[RAG] Initializing retriever for {kg_name}...")
            os.environ["ACTIVE_KGS"] = kg_name
        
        RETRIEVERS[key] = IRACRetriever.from_active_kgs()
    return RETRIEVERS[key]

def run_rag(qa_pairs, output_name, full_db=False):
    print(f"\n[RAG] Processing {len(qa_pairs)} questions...")
    from concurrent.futures import ThreadPoolExecutor
    from langchain_core.messages import HumanMessage

    results = [None] * len(qa_pairs)
    
    def process_one(idx, qa):
        print(f"  [{idx+1}/{len(qa_pairs)}] Starting: {qa['question'][:60]}...")
        source_kg = qa.get("source_kg") or "Unknown"
        retriever = get_retriever(full_db=full_db, kg_name=source_kg if not full_db else None)
        question = qa["question"]

        # Track 1: KG RAG (Full)
        retriever.config.mode = "irac"
        retriever.config.enable_hyde = True
        retriever.config.enable_kg_subgraph = True
        retriever.config.enable_dual_track = True
        start_t = time.time()
        try:
            res_kg = retriever.retrieve(question, use_source_text=True)
            kg_ans, kg_ctx = res_kg["answer"], res_kg["context"]
        except Exception as e:
            print(f"    ! KG-RAG Error: {e}"); kg_ans, kg_ctx = f"Error: {e}", ""
        kg_lat = time.time() - start_t
        
        # Track 2: True Naive RAG (Top-5, No Graph)
        retriever.config.mode = "naive"
        retriever.config.enable_hyde = False
        retriever.config.enable_dual_track = False
        retriever.config.enable_kg_subgraph = False
        # Adjust top_k to 5 for true naive
        original_top_k = retriever.config.multi_query_top_k
        retriever.config.multi_query_top_k = 5
        
        start_t = time.time()
        try:
            res_naive = retriever.retrieve(question, use_source_text=True)
            naive_ans, naive_ctx = res_naive["answer"], res_naive["context"]
        except Exception as e:
            print(f"    ! Naive-RAG Error: {e}"); naive_ans, naive_ctx = f"Error: {e}", ""
        naive_lat = time.time() - start_t
        retriever.config.multi_query_top_k = original_top_k # Restore

        # Track 3: Pure LLM (Zero-shot) - Same model
        start_t = time.time()
        try:
            llm_resp = retriever.llm.invoke([HumanMessage(content=question)])
            llm_ans = llm_resp.content
        except Exception as e:
            print(f"    ! Pure-LLM Error: {e}"); llm_ans = f"Error: {e}"
        llm_lat = time.time() - start_t

        results[idx] = {
            "id": qa["id"],
            "type": qa.get("path_type", "A"),
            "category": qa.get("category", "Unknown"),
            "question": question,
            "ground_truth": qa.get("ground_truth", ""),
            "source_kg": source_kg,
            "res_kg": {"answer": kg_ans, "context": kg_ctx, "latency": kg_lat},
            "res_naive": {"answer": naive_ans, "context": naive_ctx, "latency": naive_lat},
            "res_llm": {"answer": llm_ans, "context": "", "latency": llm_lat}
        }
        print(f"  [{idx+1}/{len(qa_pairs)}] Done: {question[:30]}...")

    if full_db: get_retriever(full_db=True)

    with ThreadPoolExecutor(max_workers=4) as executor:
        for i, qa in enumerate(qa_pairs):
            executor.submit(process_one, i, qa)
    
    final_results = [r for r in results if r is not None]
    out_file = RAW_DIR / output_name
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(final_results, f, indent=2, ensure_ascii=False)
    print(f"\n[RAG] Saved results to {out_file.name}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", help="Input dataset file (JSON)")
    parser.add_argument("--full-db", action="store_true", help="Load all KGs for retrieval")
    parser.add_argument("--sample", type=int, help="Number of questions to sample from all available datasets")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    pooled_qa = []
    output_filename = ""

    if args.sample:
        print(f"[RAG] Mode: SAMPLING {args.sample} questions from all data files...")
        all_json = list(DATA_DIR.glob("qa_*.json")) + list(DATA_DIR.glob("FINAL_QA_*.json"))
        for f_path in all_json:
            with open(f_path, "r", encoding="utf-8") as f:
                d = json.load(f)
                source_kg = d["metadata"]["source_kg"]
                for qa in d["qa_pairs"]:
                    qa["source_kg"] = source_kg
                    pooled_qa.append(qa)
        
        sample_size = min(args.sample, len(pooled_qa))
        pooled_qa = random.sample(pooled_qa, sample_size)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        db_tag = "full_db" if args.full_db else "orig_db"
        output_filename = f"raw_sampled_{sample_size}_{db_tag}_{ts}.json"
        
    elif args.input:
        input_path = Path(args.input)
        print(f"[RAG] Mode: SINGLE FILE {input_path.name}")
        with open(input_path, "r", encoding="utf-8") as f:
            d = json.load(f)
            source_kg = d["metadata"]["source_kg"]
            for qa in d["qa_pairs"]:
                qa["source_kg"] = source_kg
                pooled_qa.append(qa)
        output_filename = f"raw_{input_path.name}"
    else:
        print("Please provide an input file or use --sample.")
        return

    run_rag(pooled_qa, output_filename, full_db=args.full_db)

if __name__ == "__main__":
    main()
