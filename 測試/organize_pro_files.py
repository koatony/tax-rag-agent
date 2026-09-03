import os
import shutil
import glob

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PRO_DIR = os.path.join(SCRIPT_DIR, "2.5pro")
os.makedirs(PRO_DIR, exist_ok=True)

# 1. Move existing 2.5pro test cases into 測試/2.5pro/
for i in range(1, 11):
    case = f"ty25-us-{i:03d}"
    src_case = os.path.join(SCRIPT_DIR, case)
    dst_case = os.path.join(PRO_DIR, case)
    if os.path.exists(src_case) and os.path.isdir(src_case):
        if os.path.exists(dst_case):
            shutil.rmtree(dst_case)
        shutil.move(src_case, dst_case)
        print(f"Moved {case} -> 2.5pro/{case}")

# 2. Move existing summary reports into 測試/2.5pro/
summary_files = [
    "00_field_level_report.md",
    "00_field_level_summary.json",
    "00_final_pro_benchmark_report.md",
    "00_final_pro_benchmark_summary.json",
    "00_batch_summary.json"
]
for sf in summary_files:
    src_f = os.path.join(SCRIPT_DIR, sf)
    dst_f = os.path.join(PRO_DIR, sf)
    if os.path.exists(src_f):
        shutil.move(src_f, dst_f)
        print(f"Moved {sf} -> 2.5pro/{sf}")

print("✅ Successfully moved 2.5pro files into 測試/2.5pro/!")
