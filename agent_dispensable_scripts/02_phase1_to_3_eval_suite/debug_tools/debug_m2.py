
import os
import sys
import json
import asyncio
from dotenv import load_dotenv

# 加入專案根目錄
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
load_dotenv()

from retriever import IRACRetriever

async def check_q1():
    retriever = IRACRetriever.from_graphml(["tax_kg_v1"])
    q = "My husband was a firefighter who was killed in the line of duty last year, and I am now receiving a survivor annuity. Is this annuity payment considered taxable income for me?"
    state = retriever.retrieve(q)
    
    print("\n--- [System Answer] ---")
    print(state.get("answer"))
    
    print("\n--- [Retrieved Context] ---")
    print(state.get("context", "EMPTY!"))
    
    print("\n--- [Rule Candidates] ---")
    for c in state.get("rule_candidates", [])[:5]:
        print(f"- {c['rule_id']}")

if __name__ == "__main__":
    asyncio.run(check_q1())
