import sys
import os
import json
import xml.etree.ElementTree as ET

# Ensure project root is in sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from form1040.orchestrator import Form1040Orchestrator, _make_json_safe

def run_test():
    print("==================================================")
    print("🚀 Running Form 1040 Benchmark Test Pipeline")
    print(f"📌 Working Directory: {SCRIPT_DIR}")
    print("==================================================")

    # 1. Read input KV
    input_kv_path = os.path.join(SCRIPT_DIR, "01_input_kv.json")
    with open(input_kv_path, "r", encoding="utf-8") as f:
        input_kv = json.load(f)

    test_case = input_kv.get("test_case", "ty25-us-001")
    model_name = input_kv.get("model_name", "gemini-2.5-flash")
    tax_year = input_kv.get("tax_year", 2025)
    filing_status = input_kv.get("filing_status", "HEAD_OF_HOUSEHOLD")
    taxpayer_ssn = input_kv.get("taxpayer_ssn", "900456789")

    print(f"\n📥 [1/4] Input KV loaded ({test_case})")
    print(f"   Model Specified: {model_name}")
    print(f"   Filing Status: {filing_status}")
    print(f"   W-2 Items Count: {len(input_kv.get('raw_llm_direct_income', {}).get('w2_items', []))}")

    # 2. Invoke Form 1040 Orchestrator
    print("\n⚙️ [2/4] Executing Form1040Orchestrator.assemble...")
    orchestrator_result = Form1040Orchestrator.assemble(
        tax_year=tax_year,
        filing_status=filing_status,
        taxpayer_ssn=taxpayer_ssn,
        raw_llm_direct_income=input_kv.get("raw_llm_direct_income", {}),
        raw_schedule_d_input=input_kv.get("raw_schedule_d_input"),
        raw_schedule_a_input=input_kv.get("raw_schedule_a_input"),
    )

    json_safe_result = _make_json_safe(orchestrator_result)
    output_result_path = os.path.join(SCRIPT_DIR, "02_form1040_result.json")
    with open(output_result_path, "w", encoding="utf-8") as f:
        json.dump(json_safe_result, f, indent=2, ensure_ascii=False)
    print(f"   ✅ Form 1040 calculation completed. Saved to: 02_form1040_result.json")

    # 3. Read Ground Truth XML
    print("\n📄 [3/4] Loading Ground Truth output.xml...")
    xml_path = f"/home/wmlab/tax-calc-bench/tax_calc_bench/ty25/test_data/{test_case}/output.xml"
    
    ground_truth_fields = {}
    if os.path.exists(xml_path):
        tree = ET.parse(xml_path)
        root = tree.getroot()
        # Find IRS1040 node specifically to avoid child schedule tag overwrites
        for elem in root.iter():
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            if tag == "IRS1040":
                for child in elem:
                    child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if child.text:
                        ground_truth_fields[child_tag] = child.text
                break
    else:
        print(f"   ⚠️ Ground truth XML not found at {xml_path}")

    # 4. Compare results
    print("\n🔍 [4/4] Comparing Form 1040 API output with Ground Truth...")
    form_1040_lines = json_safe_result.get("form_1040_lines", {})
    
    comparison = {
        "test_case": test_case,
        "model_used": model_name,
        "comparison_metrics": {
            "Line 1a (Wages)": {
                "api_value": form_1040_lines.get("line_1a"),
                "ground_truth_xml": ground_truth_fields.get("WagesAmt")
            },
            "Line 7 (Capital Gain/Loss)": {
                "api_value": form_1040_lines.get("line_7"),
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
                "api_value": form_1040_lines.get("line_12"),
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

    comparison_path = os.path.join(SCRIPT_DIR, "03_comparison_report.json")
    with open(comparison_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)

    print(f"   ✅ Comparison report generated. Saved to: 03_comparison_report.json\n")
    print("==================================================")
    print("📊 Form 1040 Comparison Summary Table")
    print("==================================================")
    print(f"{'Line Description':<30} | {'Form1040 API':<15} | {'Ground Truth (XML)':<15}")
    print("-" * 65)
    for line_name, vals in comparison["comparison_metrics"].items():
        api_val = str(vals['api_value'])
        gt_val = str(vals['ground_truth_xml'])
        print(f"{line_name:<30} | {api_val:<15} | {gt_val:<15}")
    print("==================================================")

if __name__ == "__main__":
    run_test()
