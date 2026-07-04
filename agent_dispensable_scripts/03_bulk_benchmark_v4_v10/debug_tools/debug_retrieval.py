import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
root_dir = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(root_dir))
load_dotenv(dotenv_path=root_dir / ".env")

from retriever import IRACRetriever

def debug_retrieval():
    source_kg = "tax_kg_v1/pub_525_06_fringe_benefits"
    os.environ["ACTIVE_KGS"] = source_kg
    
    print(f"\n>>> Debugging Retrieval for: {source_kg}")
    retriever = IRACRetriever.from_active_kgs()
    
    query = "Is the value of an employer-provided software license included in my taxable income?"
    print(f"\nQuery: {query}")
    
    # 1. Test Vector Search
    print("\n--- Vector Search ---")
    results = retriever.rule_index.search(query, top_k=5)
    for i, (node, score) in enumerate(results):
        print(f"[{i+1}] Score: {score:.4f} | Content: {node.content[:100]}...")
    
    # 2. Test Full Retrieval
    print("\n--- IRAC Retrieve ---")
    final_results = retriever.retrieve(query)
    print(f"Total Results: {len(final_results)}")
    for i, res in enumerate(final_results):
        print(f"[{i+1}] Type: {res.metadata.get('type')} | Content: {res.page_content[:100]}...")

if __name__ == "__main__":
    debug_retrieval()
