import xml.etree.ElementTree as ET
import os
import json

line_tags = {
    "Line 1a (Wages)": ["WagesAmt", "WagesSalariesAndTipsAmt"],
    "Line 2b (Taxable Interest)": ["TaxableInterestAmt"],
    "Line 3b (Ordinary Dividends)": ["OrdinaryDividendsAmt"],
    "Line 4b (Taxable IRA)": ["TaxableIRAAmt", "TotalIRADistribTaxableAmt"],
    "Line 5b (Taxable Pensions)": ["TotalTaxablePensionsAmt", "PensionsAnnuitiesTaxableAmt"],
    "Line 6b (Taxable Social Security)": ["TaxableSocSecAmt", "SocSecBenefitsTaxableAmt"],
    "Line 7 (Capital Gain/Loss)": ["CapitalGainLossAmt"],
    "Line 8 (Schedule 1 Income)": ["TotalAdditionalIncomeAmt"],
    "Line 9 (Total Income)": ["TotalIncomeAmt"],
    "Line 10 (Schedule 1 Adjustments)": ["TotalAdjustmentsAmt", "TotalAdjustmentsToIncomeAmt"],
    "Line 11 (AGI)": ["AdjustedGrossIncomeAmt"],
    "Line 12 (Deductions)": ["TotalItemizedOrStandardDedAmt"],
    "Line 13a (QBI Deduction)": ["QualifiedBusinessIncomeDedAmt"],
    "Line 15 (Taxable Income)": ["TaxableIncomeAmt"],
    "Line 16 (Tax)": ["TaxAmt"],
    "Line 17 (Schedule 2 AMT/Tax)": ["AdditionalTaxAmt", "AlternativeMinimumTaxAmt"],
    "Line 18 (Tax Before Credits)": ["TotalTaxBeforeCrAndOthTaxesAmt"],
    "Line 24 (Total Tax)": ["TotalTaxAmt"],
    "Line 25a (W-2 Withholding)": ["FormW2WithheldTaxAmt"],
    "Line 25d (Total Withholding)": ["WithholdingTaxAmt"],
    "Line 33 (Total Payments)": ["TotalPaymentsAmt"],
    "Line 34 (Refund Amount)": ["OverpaidAmt", "RefundAmt"],
    "Line 37 (Amount You Owe)": ["OwedAmt"]
}

differences = []

for i in range(1, 11):
    case = f"ty25-us-{i:03d}"
    xml_p = f"/home/wmlab/tax-calc-bench/tax_calc_bench/ty25/test_data/{case}/output.xml"
    comp_p = f"/home/wmlab/tax_agent/tax-rag-agent/測試/{case}/04_full_line_comparison.json"
    
    if not os.path.exists(xml_p) or not os.path.exists(comp_p):
        continue

    tree = ET.parse(xml_p)
    irs1040 = None
    for elem in tree.getroot().iter():
        if elem.tag.endswith("IRS1040"):
            irs1040 = elem
            break

    xml_dict = {}
    for c in irs1040:
        tag = c.tag.split("}")[-1]
        if c.text and c.text.strip():
            xml_dict[tag] = c.text.strip()

    with open(comp_p) as f:
        comp_data = json.load(f)

    metrics = comp_data.get("metrics", {})

    print(f"\n==================== {case} ====================")
    for line_name, tags in line_tags.items():
        correct_gt = None
        for t in tags:
            if t in xml_dict:
                correct_gt = xml_dict[t]
                break
        
        old_gt = metrics.get(line_name, {}).get("ground_truth_xml")
        api_v = metrics.get(line_name, {}).get("api_value")

        # Compare old_gt vs correct_gt
        old_gt_str = str(old_gt) if old_gt is not None else "None"
        correct_gt_str = str(correct_gt) if correct_gt is not None else "None"

        if old_gt_str != correct_gt_str:
            print(f"❌ GT 抓錯: {line_name:<30} | 舊抓取 GT: {old_gt_str:<12} | 正確 XML GT: {correct_gt_str:<12} (API值: {api_v})")
            differences.append((case, line_name, old_gt_str, correct_gt_str, api_v))
        else:
            # GT was same
            pass

print(f"\n總共修正了 {len(differences)} 處 XML Ground Truth 抓取偏差！")
