import os
import json
import sys
from dotenv import load_dotenv

# 新增路徑以便匯入 retriever
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
from retriever import IRACRetriever

load_dotenv()

def debug_query(retriever, query_id, query_text):
    print(f"\n{'='*60}")
    print(f"DEBUG: {query_id} | {query_text}")
    print(f"{'='*60}")
    
    # 執行檢索
    results = retriever.retrieve(query_text)
    
    print(f"\n[Reranked Top-5 Candidates]")
    for i, sub_dict in enumerate(results["subgraphs"][:5]):
        # Debug structure if error persists
        try:
            rule_name = sub_dict["rule"]["entity_id"]
            rule_score = sub_dict["rule"].get("score", 0.0)
            print(f"{i+1}. {rule_name} (Conf: {rule_score:.4f})")
        except Exception as e:
            print(f"{i+1}. ERROR parsing: {type(sub_dict)}")
            print(f"   Keys: {sub_dict.keys() if isinstance(sub_dict, dict) else 'N/A'}")
            if "rule" in sub_dict:
                print(f"   Rule Keys: {sub_dict['rule'].keys()}")
            raise e
    
    # 檢查最後組組合的 Context
    # 模擬 assemble_context (因為 retriever.py 中它是 generate_graph 的內閉包)
    from retriever import IRACSubgraph
    subgraphs = [IRACSubgraph.from_dict(d) for d in results["subgraphs"]]
    
    # 模擬 fetch_source_text
    source_map = {}
    use_source = True # ENABLE_SOURCE_TEXT=1
    
    source_ids = {sg.rule.source_id for sg in subgraphs if sg.rule.source_id}
    text_chunks_db = getattr(retriever.kg, "text_chunks", {})
    for sid in source_ids:
        chunk = text_chunks_db.get(sid)
        if chunk:
            source_map[sid] = chunk.get("content", "")

    context_parts = []
    for i, sg in enumerate(subgraphs):
        sg_text = sg.to_context_text()
        source_text_block = ""
        # 僅前 5 名注入全文
        if i < 5 and use_source and sg.rule.source_id in source_map:
            source_text_block = f"\n  [Detailed Source Text]: {source_map[sg.rule.source_id]}"
        context_parts.append(f"--- [Candidate {i+1}] ---\n{sg_text}{source_text_block}")

    context = "\n\n".join(context_parts)
    
    print(f"\n[Final Context Snapshot (First 2000 chars)]")
    print(context[:2000] + "...")
    
    # 檢查是否有特定關鍵字
    keywords = ["firefighter", "public safety officer", "alimony", "2018"]
    print(f"\n[Keyword Check in Context]")
    for kw in keywords:
        found = kw.lower() in context.lower()
        print(f" - '{kw}': {'FOUND' if found else 'NOT FOUND'}")

if __name__ == "__main__":
    retriever = IRACRetriever.from_graphml(
        graphml_path="data/tax_kg_v1/tax_kg_v1.graphml"
    )
    
    questions = [
        ("Q001", "My husband was a firefighter who was killed in the line of duty last year, and I am now receiving a survivor annuity. Is this annuity payment considered taxable income for me?"),
        ("Q005", "My divorce was finalized in 2021 and I receive alimony payments from my ex-spouse. Do I need to include these payments as taxable income on my federal return?")
    ]
    
    for qid, qtext in questions:
        debug_query(retriever, qid, qtext)
