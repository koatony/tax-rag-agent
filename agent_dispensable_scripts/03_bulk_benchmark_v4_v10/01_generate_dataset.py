import os
import json
import time
import random
import datetime
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))
load_dotenv(dotenv_path=root_dir / ".env")

from llm_wrappers import GeminiLLM, HumanMessage, SystemMessage

# Settings
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
# Use Flash for generation to be fast/cheap
MODEL_NAME = "gemini-2.5-flash"
KGS = [
    "tax_kg_v1/pub_525_04_employee_compensation",
    "tax_kg_v1/pub_525_05_miscellaneous_compensation",
    "tax_kg_v1/pub_525_06_fringe_benefits",
    "tax_kg_v1/pub_525_07_special_rules_for_certain_employees",
    "tax_kg_v1/pub_525_08_business_and_investment_income",
    "tax_kg_v1/pub_525_09_sickness_and_injury_benefits",
    "tax_kg_v1/pub_525_10_miscellaneous_income",
]
OUTPUT_DIR = Path(__file__).resolve().parent / "data"

PROMPT_TEMPLATE = """You are an expert in US federal tax law. Based on the following tax document excerpt, generate a realistic and specific question that a taxpayer might ask, along with a precise ground truth answer.

**Requirements:**
- The question must be answerable using ONLY the provided excerpt.
- The ground truth answer must be accurate, concise (2-4 sentences), and directly cite the key rule.
- Classify the question into one of: Numerical, Conditional, Calculative, Procedural.
- Assign difficulty: Easy, Medium, Hard.
- Do NOT ask generic questions.

**Tax Document Excerpt:**
{excerpt}❓ 輸入問題 > Can a corrective distribution of excess deferrals be rolled over into another retirement plan?

🔄 正在檢索，請稍候...
   ⏱ 耗時: 21.50s

------------------------------------------------------------------------
  🔍 Step 1: Query Enhancement (Multi-Query Fusion)
------------------------------------------------------------------------
  [Original Query ]: Can a corrective distribution of excess deferrals be rolled over into another retirement plan?
  [Step-Back (Law)]: This scenario involves the general tax rule that **corrective distributions of excess deferrals are not considered eligible rollover distributions**. This is because they represent amounts that exceeded statutory contribution limits and were never intended to receive tax-deferred treatment within the qualified plan system.

  [Path Hits] Track A (Rule): 18 | Track B (Fact): 30

------------------------------------------------------------------------
  📋 Step 2: Rule Candidates (Count: 15) (LLM Reranked)
------------------------------------------------------------------------
    [🔥R] [0.0496] [Src: A_ORI,A_STE] Excess Deferral Corrective Distribution Ineligibility Rule
            └ Rule: A corrective distribution of excess deferrals, although reported on Form 1099-R, is not treate...
  ✦ [🔥R] [0.0662] [Src: A_ORI,A_STE,B_FAC] Corrective Distribution of Excess Contributions Ineligibility Rule
            └ Rule: A corrective distribution of excess contributions is not treated as a regular distribution fro...
  ✦ [🔥R] [0.0661] [Src: A_ORI,A_STE,B_FAC] Corrective Distribution of Excess Annual Additions Ineligibility Rule
            └ Rule: A corrective distribution of excess annual additions is not treated as a regular distribution...
    [🔥R] [0.0437] [Src: A_ORI,A_STE] Excess Contribution Corrective Distribution Ineligibility Rule
            └ Rule: A corrective distribution of excess contributions, although reported on Form 1099-R, is not ot...
  ✦ [🔥R] [0.0607] [Src: A_ORI,A_STE,B_FAC] Taxation Timing Rule for Corrective Distributions
            └ Rule: A corrective distribution of excess deferral principal received by April 15 of the following y...
    [🔥R] [0.0439] [Src: A_ORI,A_STE] Proportional Allocation Rule for Excess Deferral and Income
            └ Rule: A corrective distribution must be allocated proportionately between the principal excess defer...
  ✦ [🔥R] [0.0435] [Src: A_STE,B_FAC] Corrective Distribution Form 1099-R Reporting Rule
            └ Rule: A Form 1099-R should be issued for the year an excess deferral is distributed, and a distribut...
  ✦ [🔥R] [0.0647] [Src: A_ORI,A_STE,B_FAC] Excess Deferral Corrective Distribution Income Reporting Rule
            └ Rule: Income from a corrective distribution of an excess deferral must be added to wages on the inco...
  ✦ [🔥R] [0.0573] [Src: A_ORI,B_FAC] Reporting Rule for 2024 Non-Roth Excess Deferral Distribution
            └ Rule: The amount of a corrective distribution for a 2024 excess deferral must be added to wages on t...
    [🔥R] [0.0286] [Src: A_STE] Form 1099-R Issuance Rule for Corrective Distributions
            └ Rule: A taxpayer should receive a Form 1099-R for the year in which an excess deferral is distribute...
    [🔥R] [0.0420] [Src: A_ORI,A_STE] Taxation of Earnings on Corrective Distributions Rule
            └ Rule: Any income earned on an excess deferral is taxable in the tax year in which the distribution i...
    [🔥R] [0.0272] [Src: B_FAC] Excess Contribution Corrective Distribution Reporting Rule
            └ Rule: A Form 1099-R is issued for the year of a corrective distribution of excess contributions, and...
  ✦ [🔥R] [0.0641] [Src: A_ORI,A_STE,B_FAC] Excess Deferral Correction Process Rule
            └ Rule: A participant with excess deferrals must notify the plan, which then must distribute the exces...
    [🔥R] [0.0244] [Src: B_FAC] Reporting Rule for Prior-Year (2023) Excess Deferral Distribution
            └ Rule: A corrective distribution for a 2023 excess deferral requires filing an amended 2023 return if...
  ✦ [🔥R] [0.0389] [Src: A_STE,B_FAC] Qualified Plan Lump-Sum Survivor Distribution Rule
            └ Rule: Lump-sum distributions from qualified employee retirement plans are subject to special tax tre...

************************************************************************
  🤖 Step 3: Final Answer
************************************************************************
根據提供的資訊，**不能**將超額遞延的更正性分配滾存（rollover）到另一個退休計畫。

【核心法規 Rule】: A corrective distribution of excess deferrals, although reported on Form 1099-R, is not treated as a plan distribution and cannot be rolled over or be subject to the additional tax on early distributions.

Output ONLY valid JSON:
{{
  "question": "...",
  "ground_truth": "...",
  "category": "...",
  "difficulty": "..."
}}"""

def generate_one(llm, excerpt, path_type):
    prompt = PROMPT_TEMPLATE.format(excerpt=excerpt[:3000])
    for _ in range(3):
        try:
            resp = llm.invoke([HumanMessage(content=prompt)])
            text = resp.content.strip().replace("```json", "").replace("```", "").strip()
            data = json.loads(text)
            data["path_type"] = path_type
            return data
        except Exception as e:
            print(f"      [Retry] Generation failed: {e}")
            time.sleep(2)
    return None

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    llm = GeminiLLM(model_name=MODEL_NAME, api_key=GEMINI_KEY)
    
    for kg in KGS:
        print(f"\n>>> Processing KG: {kg}")
        kg_path = root_dir / "data" / kg
        
        # Path A: Text Chunks
        chunk_file = kg_path / "kv_store_text_chunks.json"
        with open(chunk_file, "r") as f:
            chunks = json.load(f)
        if isinstance(chunks, dict): chunks = list(chunks.values())
        valid_chunks = [c for c in chunks if len(c.get("content", "")) > 150]
        sampled_chunks = random.sample(valid_chunks, min(10, len(valid_chunks)))

        
        # Path B: Rule nodes
        nodes_file = kg_path / "vdb_entities.json"
        with open(nodes_file, "r") as f:
            nodes = json.load(f).get("data", [])
        rules = [n for n in nodes if n.get("entity_type") == "rule" or "rule" in n.get("entity_name", "").lower()]
        if len(rules) < 5: 
            rules = [n for n in nodes if len(n.get("description", n.get("content", ""))) > 150]
        sampled_rules = random.sample(rules, min(10, len(rules)))

        
        qa_pairs = []
        # Generate A
        print(f"    Generating 10 Type A questions...")
        for i, c in enumerate(sampled_chunks):
            qa = generate_one(llm, c.get("content", ""), "A")
            if qa: 
                qa["id"] = f"{kg.split('/')[-1]}_A_{i+1}"
                qa_pairs.append(qa)
                print(f"      OK: {qa['question'][:50]}...")
        
        # Generate B
        print(f"    Generating 10 Type B questions...")
        for i, n in enumerate(sampled_rules):
            qa = generate_one(llm, n.get("content", n.get("description", "")), "B")
            if qa:
                qa["id"] = f"{kg.split('/')[-1]}_B_{i+1}"
                qa_pairs.append(qa)
                print(f"      OK: {qa['question'][:50]}...")
        
        ts = datetime.datetime.now().strftime("%H%M%S")
        out_file = OUTPUT_DIR / f"qa_{kg.split('/')[-1]}_{ts}.json"
        with open(out_file, "w") as f:
            json.dump({
                "metadata": {"source_kg": kg},
                "qa_pairs": qa_pairs
            }, f, indent=2, ensure_ascii=False)
        print(f"    Saved {len(qa_pairs)} questions to {out_file.name}")

if __name__ == "__main__":
    main()
