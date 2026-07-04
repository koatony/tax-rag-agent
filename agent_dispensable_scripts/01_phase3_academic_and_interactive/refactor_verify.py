#!/usr/bin/env python3
import sys
import os
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))

from dotenv import load_dotenv
load_dotenv(dotenv_path=root_dir / ".env")

from retriever import IRACRetriever

def test_refactor():
    print("Testing modularized IRACRetriever...")
    try:
        # 使用預設的 KG (ACTIVE_KGS=tax_kg_v1)
        retriever = IRACRetriever.from_active_kgs()
        
        # Diagnostic dimensions
        print(f"Rule Index Matrix shape: {retriever.rule_index._matrix.shape}")
        
        query = "How to calculate self-employment tax?"
        
        # Test embedding dimension directly
        q_emb = retriever.rule_index.model.embed_query(query)
        print(f"Query embedding dimension: {len(q_emb)}")
        
        print(f"Running query: {query}")
        
        result = retriever.retrieve(query)
        
        print("\n--- Result ---")
        debug = result.get("debug_info", {})
        print(f"Track A Hits: {debug.get('track_a_hits')}")
        print(f"Track B Hits: {debug.get('track_b_hits')}")
        print(f"Track A Hits by Query: {list(debug.get('track_a_hits_by_query', {}).keys())}")
        print(f"Track B Rules: {len(debug.get('track_b_rules_by_query', {}).get('fact_track', []))}")
        
        print(f"Answer: {result.get('answer')[:100]}...")
        
        if result.get("answer") and len(result.get("rule_candidates", [])) > 0:
            print("\n✅ Verification SUCCESSFUL!")
        else:
            print("\n❌ Verification FAILED: Missing answer or candidates.")
            
    except Exception as e:
        print(f"\n❌ Error during verification: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    test_refactor()
