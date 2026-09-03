import sys
import os
import json
import time
from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
os.environ["LLM_PROVIDER"] = "gemini"

import batch_federal_runner
batch_federal_runner.MODEL_NAME = "gemini-2.5-pro"

print("==================================================")
print("🚀 Re-running ty25-us-001 with Gemini 2.5 Pro")
print("📌 Model Specified: gemini-2.5-pro")
print("📌 0 = NA Matching Rule: Active")
print("==================================================")

start_t = time.time()
comp = batch_federal_runner.process_single_test_case("ty25-us-001")
elapsed = time.time() - start_t

m = comp["metrics"]
matches_cnt = sum(1 for v in m.values() if v.get("is_match"))
total_cnt = len(m)

print(f"\n✅ Completed ty25-us-001 in {elapsed:.1f}s")
print(f"📊 Full Line Match Rate: {matches_cnt}/{total_cnt} ({matches_cnt/total_cnt*100:.1f}%)\n")

print(f"{'Form 1040 Line':<35} | {'API (Gemini 2.5 Pro)':<18} | {'Ground Truth (XML)':<18} | {'Status':<10}")
print("-" * 88)
for line_name, data in m.items():
    api_v = str(data["api_value"]) if data["api_value"] is not None else "None"
    gt_v = str(data["ground_truth_xml"]) if data["ground_truth_xml"] is not None else "N/A"
    st = "✅ MATCH" if data["is_match"] else "❌ MISMATCH"
    print(f"{line_name:<35} | {api_v:<18} | {gt_v:<18} | {st:<10}")

print("==================================================")
