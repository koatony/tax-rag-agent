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

from form1040.parsers.income_aggregator_direct_income_parser import IncomeAggregatorDirectIncomeParser
from processors.processors import (
    extract_schedule_a_inputs_with_logs,
    extract_schedule_b_inputs_with_logs,
    extract_schedule_1_inputs_with_logs,
)
from form1040.orchestrator import Form1040Orchestrator, _make_json_safe

MODEL_NAME = "gemini-2.5-flash"
BENCHMARK_BASE_DIR = "/home/wmlab/tax-calc-bench/tax_calc_bench/ty25/test_data"
FEDERAL_TEST_CASES = [f"ty25-us-{i:03d}" for i in range(1, 11)]

FILING_STATUS_MAP = {
    "1": "SINGLE",
    "2": "MARRIED_FILING_JOINTLY",
    "3": "MARRIED_FILING_SEPARATELY",
    "4": "HEAD_OF_HOUSEHOLD",
    "5": "QUALIFYING_SURVIVING_SPOUSE",
}

def safe_float_match(v1, v2):
    def parse_val(v):
        if v is None:
            return 0.0
        try:
            s = str(v).strip()
            if s == "" or s.upper() in ("NONE", "N/A", "NA", "NULL"):
                return 0.0
            return float(s)
        except Exception:
            return None

    f1 = parse_val(v1)
    f2 = parse_val(v2)

    if f1 is not None and f2 is not None:
        return abs(f1 - f2) < 0.01

    return str(v1).strip() == str(v2).strip()

def extract_pdf_text_safe(pdf_path: str) -> str:
    try:
        from pdfminer.high_level import extract_text
        text = extract_text(pdf_path, laparams=None)
        if text and len(text.strip()) > 0:
            return text.strip()
    except Exception:
        pass
    try:
        import pypdf
        reader = pypdf.PdfReader(pdf_path)
        pages_text = [p.extract_text() or "" for p in reader.pages]
        return "\n".join(pages_text).strip()
    except Exception:
        return ""

def parse_ground_truth_xml(xml_path: str):
    fields = {}
    filing_status_cd = "1"
    primary_ssn = "000000000"
    if os.path.exists(xml_path):
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "IRS1040":
                for child in elem:
                    child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if child.text:
                        fields[child_tag] = child.text
                        if child_tag == "IndividualReturnFilingStatusCd":
                            filing_status_cd = child.text
            elif tag == "PrimarySSN":
                if elem.text:
                    primary_ssn = elem.text
    return fields, FILING_STATUS_MAP.get(filing_status_cd, "SINGLE"), primary_ssn

def build_full_line_metrics(form_1040_lines: dict, gt_fields: dict) -> dict:
    line_mappings = [
        ("Line 1a (Wages)", "line_1a", ["WagesAmt", "WagesSalariesAndTipsAmt"]),
        ("Line 2b (Taxable Interest)", "line_2b", ["TaxableInterestAmt"]),
        ("Line 3b (Ordinary Dividends)", "line_3b", ["OrdinaryDividendsAmt"]),
        ("Line 4b (Taxable IRA)", "line_4b", ["TaxableIRAAmt", "TotalIRADistribTaxableAmt", "IRADistributionsTaxableAmt"]),
        ("Line 5b (Taxable Pensions)", "line_5b", ["TotalTaxablePensionsAmt", "PensionsAnnuitiesTaxableAmt"]),
        ("Line 6b (Taxable Social Security)", "line_6b", ["TaxableSocSecAmt", "SocSecBenefitsTaxableAmt"]),
        ("Line 7 (Capital Gain/Loss)", "line_7a", ["CapitalGainLossAmt"]),
        ("Line 8 (Schedule 1 Income)", "line_8", ["TotalAdditionalIncomeAmt"]),
        ("Line 9 (Total Income)", "line_9", ["TotalIncomeAmt"]),
        ("Line 10 (Schedule 1 Adjustments)", "line_10", ["TotalAdjustmentsAmt", "TotalAdjustmentsToIncomeAmt"]),
        ("Line 11 (AGI)", "line_11", ["AdjustedGrossIncomeAmt"]),
        ("Line 12 (Deductions)", "line_14", ["TotalItemizedOrStandardDedAmt"]),
        ("Line 13a (QBI Deduction)", "line_13a", ["QualifiedBusinessIncomeDedAmt"]),
        ("Line 15 (Taxable Income)", "line_15", ["TaxableIncomeAmt"]),
        ("Line 16 (Tax)", "line_16", ["TaxAmt"]),
        ("Line 17 (Schedule 2 AMT/Tax)", "line_17", ["AdditionalTaxAmt", "AlternativeMinimumTaxAmt"]),
        ("Line 18 (Tax Before Credits)", "line_18", ["TotalTaxBeforeCrAndOthTaxesAmt", "TaxLessCreditsAmt"]),
        ("Line 24 (Total Tax)", "line_24", ["TotalTaxAmt"]),
        ("Line 25a (W-2 Withholding)", "line_25a", ["FormW2WithheldTaxAmt"]),
        ("Line 25d (Total Withholding)", "line_25d", ["WithholdingTaxAmt"]),
        ("Line 33 (Total Payments)", "line_33", ["TotalPaymentsAmt"]),
        ("Line 34 (Refund Amount)", "line_34", ["RefundAmt", "OverpaidAmt"]),
        ("Line 37 (Amount You Owe)", "line_37", ["OwedAmt"]),
    ]

    metrics = {}
    for display_name, api_key, xml_tags in line_mappings:
        api_val = form_1040_lines.get(api_key)
        gt_val = None
        for tag in xml_tags:
            if tag in gt_fields:
                gt_val = gt_fields[tag]
                break

        is_match = safe_float_match(api_val, gt_val)
        metrics[display_name] = {
            "api_value": api_val,
            "ground_truth_xml": gt_val,
            "is_match": is_match,
        }
    return metrics

def generate_reasons_and_markdown(test_case: str, filing_status: str, json_safe_result: dict, metrics_full: dict, output_dir: str):
    income_sec = json_safe_result.get("income_section", {})
    agi_sec = json_safe_result.get("agi_section", {})
    ded_sec = json_safe_result.get("deduction_section", {})
    tax_comp_sec = json_safe_result.get("tax_computation_section", {})

    reasons = []

    if income_sec.get("status") == "BLOCKED":
        errs = income_sec.get("blocking_errors", [])
        for e in errs:
            reasons.append(f"❌ **Income Section 阻斷代碼 `{e.get('code')}`**: {e.get('message')}")

    if agi_sec.get("status") == "BLOCKED":
        errs = agi_sec.get("blocking_errors", [])
        for e in errs:
            reasons.append(f"❌ **AGI Section 阻斷代碼 `{e.get('code')}`**: {e.get('message')}")

    if ded_sec.get("review_warnings"):
        warns = ded_sec.get("review_warnings", [])
        for w in warns:
            reasons.append(f"⚠️ **Deduction Section 警告/退回`: {w.get('message')}")

    if tax_comp_sec.get("blocking_errors"):
        errs = tax_comp_sec.get("blocking_errors", [])
        for e in errs:
            reasons.append(f"❌ **Tax Computation 阻斷代碼 `{e.get('code')}`**: {e.get('message')}")

    md_lines = []
    md_lines.append(f"# Form 1040 全欄位對照與原因分析 - {test_case}")
    md_lines.append(f"- **報稅身份 (Filing Status)**: `{filing_status}`")
    md_lines.append(f"- **分析時間**: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    md_lines.append("\n## 📊 Form 1040 逐行詳細對照表 (Full Line-by-Line Comparison)\n")
    md_lines.append("| 表單行數 (Form 1040 Line) | API 計算值 (LLM+Orchestrator) | 正確解答 (Ground Truth XML) | 比對結果 |")
    md_lines.append("| :--- | :--- | :--- | :---: |")

    match_count = 0
    total_count = len(metrics_full)

    for line_name, data in metrics_full.items():
        api_v = str(data["api_value"]) if data["api_value"] is not None else "None"
        gt_v = str(data["ground_truth_xml"]) if data["ground_truth_xml"] is not None else "N/A"
        if data["is_match"]:
            match_count += 1
            status_str = "✅ MATCH"
        else:
            status_str = "❌ MISMATCH"
        md_lines.append(f"| {line_name} | `{api_v}` | `{gt_v}` | {status_str} |")

    md_lines.append(f"\n**精確匹配率**: `{match_count} / {total_count}` ({match_count/total_count*100:.1f}%)\n")
    md_lines.append("\n## 🔍 欄位不符之原因與阻斷日誌 (Reasoning & Log Analysis)\n")
    if reasons:
        for r in reasons:
            md_lines.append(f"- {r}")
    else:
        md_lines.append("- ✅ 所有模組順利完成計算，未觸發驗證阻斷。")

    md_content = "\n".join(md_lines)
    with open(os.path.join(output_dir, "05_comparison_analysis.md"), "w", encoding="utf-8") as f:
        f.write(md_content)

def process_single_test_case(test_case: str) -> dict:
    test_dir = os.path.join(BENCHMARK_BASE_DIR, test_case)
    input_dir = os.path.join(test_dir, "input")
    xml_path = os.path.join(test_dir, "output.xml")
    
    output_dir = os.path.join(SCRIPT_DIR, test_case)
    os.makedirs(output_dir, exist_ok=True)

    gt_fields, filing_status, taxpayer_ssn = parse_ground_truth_xml(xml_path)

    # 1. Transcribe documents into document_context
    context_blocks = []
    for pdf_path in sorted(glob.glob(f"{input_dir}/*.pdf")):
        filename = os.path.basename(pdf_path)
        if "1040_2024" in filename:
            continue
        pdf_text = extract_pdf_text_safe(pdf_path)
        context_blocks.append(f"=== ATTACHED DOCUMENT: {filename} ===\n{pdf_text}\n")

    json_path = os.path.join(input_dir, "remaining_data.json")
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            context_blocks.append(f"=== ATTACHED DATA: remaining_data.json ===\n{f.read()}\n")

    doc_context = "\n".join(context_blocks)
    with open(os.path.join(output_dir, "01_document_context.txt"), "w", encoding="utf-8") as f:
        f.write(doc_context)

    # 2. Invoke LLM Parsers
    direct_income_dto, _, _ = IncomeAggregatorDirectIncomeParser.extract_and_parse(doc_context, model_name=MODEL_NAME)
    raw_direct_income_kv = direct_income_dto.to_dict() if hasattr(direct_income_dto, "to_dict") else direct_income_dto

    raw_schedule_a_kv, _, _ = extract_schedule_a_inputs_with_logs(doc_context, model_name=MODEL_NAME)
    raw_schedule_b_kv, _, _ = extract_schedule_b_inputs_with_logs(doc_context, model_name=MODEL_NAME)
    raw_schedule_1_kv, _, _ = extract_schedule_1_inputs_with_logs(doc_context, model_name=MODEL_NAME)

    llm_extracted_kv = {
        "model_name": MODEL_NAME,
        "test_case": test_case,
        "filing_status": filing_status,
        "taxpayer_ssn": taxpayer_ssn,
        "raw_llm_direct_income": _make_json_safe(raw_direct_income_kv),
        "raw_schedule_a_input": _make_json_safe(raw_schedule_a_kv),
        "raw_schedule_b_input": _make_json_safe(raw_schedule_b_kv),
        "raw_schedule_1_input": _make_json_safe(raw_schedule_1_kv),
    }
    with open(os.path.join(output_dir, "02_llm_extracted_kv.json"), "w", encoding="utf-8") as f:
        json.dump(llm_extracted_kv, f, indent=2, ensure_ascii=False)

    # 3. Execute Orchestrator
    orchestrator_result = Form1040Orchestrator.assemble(
        tax_year=2025,
        filing_status=filing_status,
        taxpayer_ssn=taxpayer_ssn,
        raw_llm_direct_income=llm_extracted_kv["raw_llm_direct_income"],
        raw_schedule_a_input=llm_extracted_kv["raw_schedule_a_input"],
        raw_schedule_b_input=llm_extracted_kv["raw_schedule_b_input"],
        raw_schedule_1_input=llm_extracted_kv["raw_schedule_1_input"],
    )
    json_safe_result = _make_json_safe(orchestrator_result)
    with open(os.path.join(output_dir, "03_form1040_llm_result.json"), "w", encoding="utf-8") as f:
        json.dump(json_safe_result, f, indent=2, ensure_ascii=False)

    # 4. Compare & Report (Full Line-by-Line)
    form_1040_lines = json_safe_result.get("form_1040_lines", {})
    metrics_full = build_full_line_metrics(form_1040_lines, gt_fields)

    comparison = {
        "test_case": test_case,
        "filing_status": filing_status,
        "metrics": metrics_full
    }
    with open(os.path.join(output_dir, "04_full_line_comparison.json"), "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)

    # 5. Generate Markdown Report with Reasons
    generate_reasons_and_markdown(test_case, filing_status, json_safe_result, metrics_full, output_dir)

    return comparison

def run_batch():
    print("==================================================")
    print("🚀 Full Line-by-Line Federal Tax Benchmark (10 Cases)")
    print(f"📌 LLM Model: {MODEL_NAME}")
    print("==================================================")

    batch_summary = []
    for idx, test_case in enumerate(FEDERAL_TEST_CASES, 1):
        print(f"\n[{idx}/10] Processing {test_case}...")
        start_t = time.time()
        try:
            comp = process_single_test_case(test_case)
            elapsed = time.time() - start_t
            
            m = comp["metrics"]
            wages_match = m.get("Line 1a (Wages)", {}).get("is_match")
            agi_match = m.get("Line 11 (AGI)", {}).get("is_match")
            withholding_match = m.get("Line 25d (Total Withholding)", {}).get("is_match")

            matches_cnt = sum(1 for v in m.values() if v.get("is_match"))
            total_cnt = len(m)

            print(f"   ✅ Completed in {elapsed:.1f}s | Full Line Match Rate: {matches_cnt}/{total_cnt} ({matches_cnt/total_cnt*100:.1f}%)")
            batch_summary.append({
                "test_case": test_case,
                "status": "SUCCESS",
                "elapsed_seconds": round(elapsed, 2),
                "match_rate": f"{matches_cnt}/{total_cnt}",
                "wages_match": wages_match,
                "agi_match": agi_match,
                "withholding_match": withholding_match,
                "metrics": m
            })
        except Exception as e:
            print(f"   ❌ Error processing {test_case}: {e}")
            batch_summary.append({
                "test_case": test_case,
                "status": "ERROR",
                "error": str(e)
            })

    summary_file = os.path.join(SCRIPT_DIR, "00_batch_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(batch_summary, f, indent=2, ensure_ascii=False)

    print("\n==========================================================================")
    print("📊 BATCH BENCHMARK FULL LINE-BY-LINE SUMMARY (10 Federal Cases)")
    print("==========================================================================")
    print(f"{'Test Case':<15} | {'Line Match Rate':<18} | {'Wages':<10} | {'AGI':<10} | {'Withholding':<12}")
    print("-" * 75)
    for s in batch_summary:
        if s["status"] == "SUCCESS":
            wm = "✅ PASS" if s["wages_match"] else "❌ FAIL"
            am = "✅ PASS" if s["agi_match"] else "❌ FAIL"
            whm = "✅ PASS" if s.get("withholding_match") else "❌ FAIL"
            mr = s["match_rate"]
            print(f"{s['test_case']:<15} | {mr:<18} | {wm:<10} | {am:<10} | {whm:<12}")
        else:
            print(f"{s['test_case']:<15} | ERROR: {s['error']}")
    print("==========================================================================")

if __name__ == "__main__":
    run_batch()
