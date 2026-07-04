import os
import subprocess
import json
import time
from pathlib import Path

# 配置
KGS = [
    "tax_kg_v1/pub_525_04_employee_compensation",
    "tax_kg_v1/pub_525_05_miscellaneous_compensation",
    "tax_kg_v1/pub_525_06_fringe_benefits",
    "tax_kg_v1/pub_525_07_special_rules_for_certain_employees",
    "tax_kg_v1/pub_525_08_business_and_investment_income",
    "tax_kg_v1/pub_525_09_sickness_and_injury_benefits",
    "tax_kg_v1/pub_525_10_miscellaneous_income",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent if "__file__" in locals() else Path("/home/wmlab/projects/Retrieve")
TEST_SUITE_DIR = PROJECT_ROOT / "tests" / "eval_suite"
QA_GENERATOR_PY = TEST_SUITE_DIR / "qa_generator.py"
OUTPUT_DIR = PROJECT_ROOT / "experiments" / "bulk_benchmark_v4_v10" / "data"

def run_gen(kg_name, n, path_type):
    print(f"\n>>> Generating {n} Type {path_type} QAs for {kg_name}...")
    env = os.environ.copy()
    env["ACTIVE_KGS"] = kg_name
    
    cmd = [
        "python3", "-u", str(QA_GENERATOR_PY),
        "--n", str(n),
        "--path", path_type,
        "--output_dir", str(OUTPUT_DIR)
    ]
    
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running generator for {kg_name}:\n{result.stderr}")
    else:
        print(result.stdout)

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    for kg in KGS:
        section_id = kg.split("/")[-1]
        print(f"\n{'='*80}")
        print(f" Processing Section: {section_id}")
        print(f"{'='*80}")
        
        # Type A
        run_gen(kg, 10, "A")
        
        # Type B
        run_gen(kg, 10, "B")

if __name__ == "__main__":
    main()
