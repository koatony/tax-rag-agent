import os
import json
import time
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load Environment
root_dir = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(root_dir))
load_dotenv(dotenv_path=root_dir / ".env")

from retriever import IRACRetriever

def debug_q5():
    question = "I filed for Chapter 11 bankruptcy earlier this year. Do I need to include the forgiven debt as income?"
    print(f"\n[DEBUG] Question: {question}")
    
    os.environ["ACTIVE_KGS"] = "tax_kg_v1"
    retriever = IRACRetriever.from_active_kgs()
    retriever.config.mode = "irac"
    
    start_t = time.time()
    print("  - Starting retrieve...")
    res = retriever.retrieve(question, use_source_text=True)
    print(f"  - Finished in {time.time() - start_t:.2f}s")
    print(f"  - Answer: {res['answer'][:100]}...")

if __name__ == "__main__":
    debug_q5()
