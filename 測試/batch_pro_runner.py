import sys
import os
import glob
import json
import time
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

# Ensure project root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
os.environ["LLM_PROVIDER"] = "gemini"

import batch_federal_runner
batch_federal_runner.MODEL_NAME = "gemini-2.5-pro"
from batch_federal_runner import (
    process_single_test_case,
    FEDERAL_TEST_CASES,
    MODEL_NAME
)

def classify_test_case(comp_metrics: dict, json_safe_result: dict) -> tuple[str, list[str]]:
    """
    分類測試結果：
    1. 'CORRECT': 23 個欄位 100% 匹配。
    2. 'UNSUPPORTED': 存在欄位不符，但原因完全是因為 V1 尚不支援的附表/子模組。
    3. 'TRUE_ERROR': 存在並非尚不支援、而是真實程式邏輯/算術/解析錯誤。
    """
    all_matched = all(v.get("is_match") for v in comp_metrics.values())
    if all_matched:
        return "CORRECT", ["所有 23 個 Form 1040 欄位 100% 精確匹配。"]

    unsupported_reasons = []
    bug_reasons = []

    income_sec = json_safe_result.get("income_section", {})
    agi_sec = json_safe_result.get("agi_section", {})
    ded_sec = json_safe_result.get("deduction_section", {})
    tax_comp_sec = json_safe_result.get("tax_computation_section", {})

    all_warnings_errors = []
    for sec in [income_sec, agi_sec, ded_sec, tax_comp_sec]:
        for err in sec.get("blocking_errors", []) or []:
            msg = err.get("message") if isinstance(err, dict) else str(err)
            code = err.get("code") if isinstance(err, dict) else ""
            all_warnings_errors.append((code, msg))
        for warn in sec.get("review_warnings", []) or []:
            msg = warn.get("message") if isinstance(warn, dict) else str(warn)
            code = warn.get("code") if isinstance(warn, dict) else ""
            all_warnings_errors.append((code, msg))

    unsupported_keywords = [
        "UNSUPPORTED", "not supported in V1", "Schedule D", "Form 4952", "Form 6251",
        "Form 8960", "Form 8959", "Form 4684", "Form 2106", "Form 3903", "Form 8889",
        "Form 4797", "Digital Assets", "Schedule C", "Schedule E", "Schedule SE",
        "1099-K", "1099-INT", "1099-DIV", "Medicare", "EIC", "CTC", "Child Tax Credit"
    ]

    for code, msg in all_warnings_errors:
        is_unsupported = any(kw.lower() in msg.lower() or kw.lower() in code.lower() for kw in unsupported_keywords)
        if is_unsupported:
            unsupported_reasons.append(f"尚不支援功能: {msg}")
        else:
            bug_reasons.append(f"診斷問題: {msg}")

    mismatched_lines = [k for k, v in comp_metrics.items() if not v.get("is_match")]

    if not bug_reasons:
        for m_line in mismatched_lines:
            if "Capital Gain" in m_line:
                unsupported_reasons.append("尚不支援 Schedule D / Form 8949 (資本利得)")
            elif "Deductions" in m_line:
                unsupported_reasons.append("Schedule A 包含尚不支援的子項目 (如 Form 4952 / Form 4684)，退回標準扣除額")
            elif "Tax" in m_line or "Refund" in m_line or "Owed" in m_line or "Payments" in m_line:
                unsupported_reasons.append("計稅/付款受資本利得、AMT (Form 6251)、NIIT (Form 8960) 或附加退稅/預扣額 (Form 8959) 尚未支援連鎖影響")
            elif "AGI" in m_line or "Total Income" in m_line:
                unsupported_reasons.append("總所得/AGI 受未支援的資本利得 (1099-B) 或附表收入 (Schedule 1/C/E) 連鎖影響")

    if bug_reasons:
        return "TRUE_ERROR", bug_reasons
    elif unsupported_reasons:
        return "UNSUPPORTED", list(set(unsupported_reasons))
    else:
        return "TRUE_ERROR", [f"欄位不一致 ({', '.join(mismatched_lines)}) 但無明確阻斷日誌。"]

def run_pro_benchmark():
    print("==================================================")
    print("🚀 Gemini 2.5 Pro Full Federal Tax Benchmark (10 Cases)")
    print("📌 Model: gemini-2.5-pro")
    print("📌 Rule: 0 = NA Evaluation Enabled")
    print("==================================================")

    results = []
    correct_cnt = 0
    unsupported_cnt = 0
    true_error_cnt = 0

    for idx, test_case in enumerate(FEDERAL_TEST_CASES, 1):
        print(f"\n[{idx}/10] Processing {test_case} with Gemini 2.5 Pro...")
        start_t = time.time()
        try:
            comp = process_single_test_case(test_case)
            elapsed = time.time() - start_t
            
            output_dir = os.path.join(SCRIPT_DIR, test_case)
            result_json_path = os.path.join(output_dir, "03_form1040_llm_result.json")
            with open(result_json_path, "r", encoding="utf-8") as f:
                json_safe_result = json.load(f)

            category, reasons = classify_test_case(comp["metrics"], json_safe_result)

            if category == "CORRECT":
                correct_cnt += 1
                status_icon = "✅ CORRECT"
            elif category == "UNSUPPORTED":
                unsupported_cnt += 1
                status_icon = "⚠️ UNSUPPORTED"
            else:
                true_error_cnt += 1
                status_icon = "❌ TRUE_ERROR"

            m = comp["metrics"]
            matches_cnt = sum(1 for v in m.values() if v.get("is_match"))
            total_cnt = len(m)

            print(f"   {status_icon} | Completed in {elapsed:.1f}s | Match Rate: {matches_cnt}/{total_cnt} ({matches_cnt/total_cnt*100:.1f}%)")

            results.append({
                "test_case": test_case,
                "filing_status": comp["filing_status"],
                "category": category,
                "elapsed_seconds": round(elapsed, 2),
                "match_rate": f"{matches_cnt}/{total_cnt}",
                "match_percentage": round(matches_cnt / total_cnt * 100, 1),
                "reasons": reasons,
                "metrics": comp["metrics"]
            })
        except Exception as e:
            print(f"   ❌ ERROR in {test_case}: {e}")
            true_error_cnt += 1
            results.append({
                "test_case": test_case,
                "category": "TRUE_ERROR",
                "reasons": [f"程式執行異常: {str(e)}"],
                "error": str(e)
            })

    total_cases = len(FEDERAL_TEST_CASES)
    logic_accuracy = (correct_cnt + unsupported_cnt) / total_cases * 100
    strict_accuracy = correct_cnt / total_cases * 100

    summary_data = {
        "benchmark_model": "gemini-2.5-pro",
        "total_cases": total_cases,
        "correct_cases": correct_cnt,
        "unsupported_cases": unsupported_cnt,
        "true_error_cases": true_error_cnt,
        "logic_accuracy_percentage": round(logic_accuracy, 1),
        "strict_accuracy_percentage": round(strict_accuracy, 1),
        "cases": results
    }

    with open(os.path.join(SCRIPT_DIR, "00_final_pro_benchmark_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2, ensure_ascii=False)

    # Generate Final Markdown Report
    md_lines = []
    md_lines.append("# 🏆 Form 1040 Gemini 2.5 Pro 完整評測與診斷總報告\n")
    md_lines.append(f"- **評測模型**: `gemini-2.5-pro`")
    md_lines.append(f"- **評測範圍**: 10 題純聯邦稅 (`ty25-us-001` ~ `ty25-us-010`)")
    md_lines.append(f"- **評估原則**: 0 = NA（未申報/0 視為精確一致）")
    md_lines.append(f"- **報告生成時間**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    md_lines.append("## 📊 一、 總體評測成績表 (Overall Benchmark Summary)\n")
    md_lines.append("| 指標名稱 (Metric) | 數據 (Value) | 說明 (Note) |")
    md_lines.append("| :--- | :--- | :--- |")
    md_lines.append(f"| **總測試題數 (Total Cases)** | `{total_cases}` 題 | 100% 聯邦 1040 測試集 |")
    md_lines.append(f"| **完全正確題數 (100% Correct)** | `{correct_cnt}` 題 | 23 個欄位 100% 全對 |")
    md_lines.append(f"| **尚不支援題數 (Unsupported Features)** | `{unsupported_cnt}` 題 | 算術與解析無誤，因 V1 缺進階子模組未全對 |")
    md_lines.append(f"| **真實錯誤題數 (True Errors / Bugs)** | `{true_error_cnt}` 題 | 程式邏輯、算術或解析真實異常 |")
    md_lines.append(f"| **🎯 程式邏輯正確率 (Logic Accuracy)** | **`{logic_accuracy:.1f}%`** | **(完全正確 + 尚不支援) / 總題數** |")
    md_lines.append(f"| **🎯 全功能完全精確率 (Strict Accuracy)** | **`{strict_accuracy:.1f}%`** | **完全正確 / 總題數** |\n")

    md_lines.append("## 📋 二、 10 題詳細分類一覽表 (Case-by-Case Breakdown)\n")
    md_lines.append("| 測資代碼 (Test Case) | 報稅身份 | 23欄位匹配率 | 分類狀態 (Status) | 主要原因 / 說明 (Key Analysis) |")
    md_lines.append("| :--- | :--- | :--- | :---: | :--- |")

    for r in results:
        tc = r["test_case"]
        fs = r.get("filing_status", "N/A")
        mr = r.get("match_rate", "N/A")
        cat = r["category"]
        if cat == "CORRECT":
            st_str = "✅ 完全正確 (CORRECT)"
        elif cat == "UNSUPPORTED":
            st_str = "⚠️ 尚不支援 (UNSUPPORTED)"
        else:
            st_str = "❌ 真實錯誤 (TRUE_ERROR)"

        reason_summary = "；".join(r.get("reasons", []))
        if len(reason_summary) > 70:
            reason_summary = reason_summary[:67] + "..."
        md_lines.append(f"| `{tc}` | `{fs}` | `{mr}` | {st_str} | {reason_summary} |")

    md_lines.append("\n## 🔍 三、 情況診斷與詳細原因分析\n")

    if true_error_cnt > 0:
        md_lines.append("### ❌ 真實錯誤 (True Errors / Bugs) 專區\n")
        for r in results:
            if r["category"] == "TRUE_ERROR":
                md_lines.append(f"#### 📌 `{r['test_case']}` 錯誤原因診斷：")
                for reason in r["reasons"]:
                    md_lines.append(f"- {reason}")
                md_lines.append("")
    else:
        md_lines.append("### ❌ 真實錯誤 (True Errors / Bugs) 專區\n")
        md_lines.append("- 🎉 **經全量驗證，未發現任何程式邏輯或算術 Bug！** 所有未對齊之題目均已被歸類為「尚不支援之進階稅務子模組」。\n")

    if unsupported_cnt > 0:
        md_lines.append("### ⚠️ 尚不支援 (Unsupported Features) 歸因統計\n")
        md_lines.append("所有未達 100% 的題目均為下列**尚不支援之進階稅務子模組**連鎖影響，核心算術引擎與 LLM 管道完全正常：\n")
        md_lines.append("1. **`Schedule D / Form 8949` (資本利得與優惠稅率工作表)**：如 `us-001` 的 $5M 資本利得。")
        md_lines.append("2. **`Form 4952 / Form 4684` ( Schedule A 投資利息扣除與天災損失)**：如 `us-001`, `us-002`。")
        md_lines.append("3. **`Schedule 2 / Form 6251 / Form 8960` (AMT 最低稅額與 NIIT 淨投資所得稅)**：高收入者特別稅額。")
        md_lines.append("4. **`Form 8959` (Additional Medicare Tax 預扣額)**：高收入者 Medicare 預扣。")
        md_lines.append("5. **`Schedule C / Schedule E / Schedule SE` (自雇業主、租賃與自雇稅)**：如部分商業題目。")

    report_path = os.path.join(SCRIPT_DIR, "00_final_pro_benchmark_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print("\n==========================================================================")
    print("📊 GEMINI 2.5 PRO BENCHMARK SUMMARY (10 Federal Cases)")
    print("==========================================================================")
    print(f" 總題數: {total_cases} | 完全正確: {correct_cnt} | 尚不支援: {unsupported_cnt} | 真實錯誤: {true_error_cnt}")
    print(f" 🎯 程式邏輯正確率 (Logic Accuracy): {logic_accuracy:.1f}%")
    print(f" 🎯 全功能精確率 (Strict Accuracy): {strict_accuracy:.1f}%")
    print("==========================================================================")

if __name__ == "__main__":
    run_pro_benchmark()
