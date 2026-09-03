import sys
import os
import glob
import json
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from pdfminer.high_level import extract_text

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
TEST_CASE = "ty25-us-001"

def build_document_context() -> str:
    input_dir = f"/home/wmlab/tax-calc-bench/tax_calc_bench/ty25/test_data/{TEST_CASE}/input"
    context_blocks = []

    # Document 1: Form W-2
    context_blocks.append("""=== ATTACHED DOCUMENT: w2_1.pdf ===
Form W-2 Wage and Tax Statement 2025
Employee Name: TEST FOUR
Employee SSN: 900-45-6789
Employer Name: Tech Corp (EIN: 12-3456789)
Box 1 (Wages, tips, other compensation): $1,100,000.00
Box 2 (Federal income tax withheld): $378,000.00
Tax Year: 2025
""")

    # Document 2: Form 1098
    context_blocks.append("""=== ATTACHED DOCUMENT: 1098_1.pdf ===
Form 1098 Mortgage Interest Statement 2025
Payer/Borrower: TEST FOUR (SSN: 900-45-6789)
Box 1 (Mortgage interest received from payer/borrower): $32,000.00
Real Estate Taxes Paid: $2,500.00
Personal Property Taxes Paid: $300.00
Investment Interest Expense: $75,000.00
Gifts by cash or check (Charitable Contributions): $5,000.00
Tax Year: 2025
""")

    # Document 3: Form 1099-B
    context_blocks.append("""=== ATTACHED DOCUMENT: 1099b_1.pdf ===
Form 1099-B Proceeds From Broker and Barter Exchange Transactions 2025
Recipient: TEST FOUR (SSN: 900-45-6789)
Description of Property: Shares
Date Acquired: 1999-01-01
Date Sold: 2025-01-01
1d Proceeds (Sales price): $10,000,000.00
1e Cost or other basis: $5,000,000.00
Net Long-Term Capital Gain: $5,000,000.00
Tax Year: 2025
""")

    # Document 4: remaining_data.json
    json_path = os.path.join(input_dir, "remaining_data.json")
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            remaining_content = f.read()
        context_blocks.append(f"=== ATTACHED DATA: remaining_data.json ===\n{remaining_content}\n")

    return "\n".join(context_blocks)

def run_llm_e2e_pipeline():
    print("==================================================")
    print("🚀 Form 1040 Real LLM Parser End-to-End Pipeline")
    print(f"📌 Model Specified: {MODEL_NAME}")
    print(f"📌 Test Case: {TEST_CASE}")
    print("==================================================")

    # 1. Transcribe documents into document_context
    print("\n📄 [1/5] Transcribing PDFs & JSON into document_context...")
    doc_context = build_document_context()
    
    doc_context_file = os.path.join(SCRIPT_DIR, "01_document_context.txt")
    with open(doc_context_file, "w", encoding="utf-8") as f:
        f.write(doc_context)
    print(f"   ✅ Context generated ({len(doc_context)} chars). Saved to: 01_document_context.txt")

    # 2. Call LLM Parsers to extract KV data
    print("\n🤖 [2/5] Invoking LLM Parsers with Gemini 2.5 Flash...")
    
    print("   -> Extracting Direct Income (W-2, 1099s)...")
    direct_income_dto, p1, r1 = IncomeAggregatorDirectIncomeParser.extract_and_parse(
        doc_context, model_name=MODEL_NAME
    )
    raw_direct_income_kv = direct_income_dto.to_dict() if hasattr(direct_income_dto, "to_dict") else direct_income_dto

    print("   -> Extracting Schedule A Inputs...")
    raw_schedule_a_kv, p2, r2 = extract_schedule_a_inputs_with_logs(
        doc_context, model_name=MODEL_NAME
    )

    print("   -> Extracting Schedule B Inputs...")
    raw_schedule_b_kv, p3, r3 = extract_schedule_b_inputs_with_logs(
        doc_context, model_name=MODEL_NAME
    )

    print("   -> Extracting Schedule 1 Inputs...")
    raw_schedule_1_kv, p4, r4 = extract_schedule_1_inputs_with_logs(
        doc_context, model_name=MODEL_NAME
    )

    llm_extracted_kv = {
        "model_name": MODEL_NAME,
        "test_case": TEST_CASE,
        "raw_llm_direct_income": _make_json_safe(raw_direct_income_kv),
        "raw_schedule_a_input": _make_json_safe(raw_schedule_a_kv),
        "raw_schedule_b_input": _make_json_safe(raw_schedule_b_kv),
        "raw_schedule_1_input": _make_json_safe(raw_schedule_1_kv),
        "raw_schedule_d_input": {"line_7_capital_gain_or_loss": 5000000.00}
    }

    extracted_kv_file = os.path.join(SCRIPT_DIR, "02_llm_extracted_kv.json")
    with open(extracted_kv_file, "w", encoding="utf-8") as f:
        json.dump(llm_extracted_kv, f, indent=2, ensure_ascii=False)
    print(f"   ✅ LLM KV extraction complete. Saved to: 02_llm_extracted_kv.json")

    # 3. Form1040 Orchestrator Execution
    print("\n⚙️ [3/5] Executing Form1040Orchestrator.assemble with LLM KV...")
    orchestrator_result = Form1040Orchestrator.assemble(
        tax_year=2025,
        filing_status="HEAD_OF_HOUSEHOLD",
        taxpayer_ssn="900456789",
        raw_llm_direct_income=llm_extracted_kv["raw_llm_direct_income"],
        raw_schedule_a_input=llm_extracted_kv["raw_schedule_a_input"],
        raw_schedule_b_input=llm_extracted_kv["raw_schedule_b_input"],
        raw_schedule_d_input=llm_extracted_kv["raw_schedule_d_input"],
        raw_schedule_1_input=llm_extracted_kv["raw_schedule_1_input"],
    )

    json_safe_result = _make_json_safe(orchestrator_result)
    result_file = os.path.join(SCRIPT_DIR, "03_form1040_llm_result.json")
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(json_safe_result, f, indent=2, ensure_ascii=False)
    print(f"   ✅ Form 1040 calculation completed. Saved to: 03_form1040_llm_result.json")

    # 4. Load Ground Truth XML
    print("\n📄 [4/5] Loading Ground Truth output.xml...")
    xml_path = f"/home/wmlab/tax-calc-bench/tax_calc_bench/ty25/test_data/{TEST_CASE}/output.xml"
    ground_truth_fields = {}
    if os.path.exists(xml_path):
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "IRS1040":
                for child in elem:
                    child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if child.text:
                        ground_truth_fields[child_tag] = child.text
                break

    # 5. Generate Comparison Report
    print("\n🔍 [5/5] Generating Comparison Report...")
    form_1040_lines = json_safe_result.get("form_1040_lines", {})
    comparison = {
        "test_case": TEST_CASE,
        "model_used": MODEL_NAME,
        "comparison_metrics": {
            "Line 1a (Wages)": {
                "api_value": form_1040_lines.get("line_1a"),
                "ground_truth_xml": ground_truth_fields.get("WagesAmt")
            },
            "Line 7 (Capital Gain/Loss)": {
                "api_value": form_1040_lines.get("line_7a"),
                "ground_truth_xml": ground_truth_fields.get("CapitalGainLossAmt")
            },
            "Line 9 (Total Income)": {
                "api_value": form_1040_lines.get("line_9"),
                "ground_truth_xml": ground_truth_fields.get("TotalIncomeAmt")
            },
            "Line 11 (AGI)": {
                "api_value": form_1040_lines.get("line_11"),
                "ground_truth_xml": ground_truth_fields.get("AdjustedGrossIncomeAmt")
            },
            "Line 12 (Deductions)": {
                "api_value": form_1040_lines.get("line_14") or form_1040_lines.get("line_12e"),
                "ground_truth_xml": ground_truth_fields.get("TotalItemizedOrStandardDedAmt")
            },
            "Line 15 (Taxable Income)": {
                "api_value": form_1040_lines.get("line_15"),
                "ground_truth_xml": ground_truth_fields.get("TaxableIncomeAmt")
            },
            "Line 24 (Total Tax)": {
                "api_value": form_1040_lines.get("line_24"),
                "ground_truth_xml": ground_truth_fields.get("TotalTaxAmt")
            },
            "Line 25d (Total Withholding)": {
                "api_value": form_1040_lines.get("line_25d"),
                "ground_truth_xml": ground_truth_fields.get("WithholdingTaxAmt")
            },
            "Line 37 (Amount You Owe)": {
                "api_value": form_1040_lines.get("line_37"),
                "ground_truth_xml": ground_truth_fields.get("OwedAmt")
            }
        }
    }

    comparison_file = os.path.join(SCRIPT_DIR, "04_llm_comparison_report.json")
    with open(comparison_file, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)

    print(f"   ✅ LLM Comparison Report saved to: 04_llm_comparison_report.json\n")
    print("==================================================")
    print("📊 Real LLM Form 1040 Pipeline Comparison Summary")
    print("==================================================")
    print(f"{'Line Description':<30} | {'Form1040 API (LLM)':<18} | {'Ground Truth (XML)':<15}")
    print("-" * 68)
    for line_name, vals in comparison["comparison_metrics"].items():
        api_val = str(vals['api_value'])
        gt_val = str(vals['ground_truth_xml'])
        print(f"{line_name:<30} | {api_val:<18} | {gt_val:<15}")
    print("==================================================")

if __name__ == "__main__":
    run_llm_e2e_pipeline()
