import os
import sys
import json
import xml.etree.ElementTree as ET
import shutil
import time
from decimal import Decimal

# 將工作路徑加入系統中以載入專案模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from schedule_c_processor import extract_schedule_c_inputs_with_logs, calculate_schedule_c_dynamic

def normalize_name(name):
    """標準化姓名格式以進行精確比對"""
    if not name:
        return ""
    # 去除 XML 中的特殊字符如 < 或 &
    cleaned = name.replace("<", " ").replace("&", " ").replace(";", " ")
    # 合併多餘空格並轉小寫
    return " ".join(cleaned.lower().split())

def format_column_tax_input_to_text(biz, tp_profile):
    """
    將 Column Tax (TaxCalcBench) 的單個 Schedule C 結構化 JSON 轉換為無結構文本。
    """
    lines = []
    lines.append(f"Proprietor Legal Name: {tp_profile.get('name', '')}")
    lines.append(f"Proprietor SSN: {tp_profile.get('ssn', '')}")
    lines.append("Tax Year: 2024")
    
    # 業務基本資訊
    lines.append(f"Business Activity Description: {biz.get('business_act', {}).get('value', '')}")
    lines.append(f"Principal Activity Code: {biz.get('business_code', {}).get('value', '')}")
    lines.append(f"Business Name: {biz.get('business_name', {}).get('value', '')}")
    lines.append(f"Employer ID Number (EIN): {biz.get('business_ein', {}).get('value', '')}")
    
    address = biz.get('street_address', {}).get('value', '')
    city = biz.get('city', {}).get('value', '')
    state = biz.get('state', {}).get('value', '')
    zip_code = biz.get('zip', {}).get('value', '')
    if address:
        lines.append(f"Business Address: {address}, {city}, {state} {zip_code}")
    else:
        lines.append("Business Address: null")
        
    method = biz.get('method_accounting', {}).get('value', 'cash')
    lines.append(f"Accounting Method: {method.capitalize()}")
    lines.append(f"Started or acquired business in 2024: {biz.get('new_business', {}).get('value', False)}")
    
    # 參與度與 1099 判定
    lines.append(f"Material participation in this business: {biz.get('material_participate', {}).get('value', True)}")
    lines.append(f"Paid any contractor $600 or more: {biz.get('payment_require_1099', {}).get('value', False)}")
    lines.append(f"Filed or will file required Forms 1099: {biz.get('filed_1099', {}).get('value', False)}")
    
    # 收入項目
    gross_receipts = biz.get('gross_receipts_cash', {}).get('value', 0.0)
    returns = biz.get('returns_allowances', {}).get('value', 0.0)
    other_inc = biz.get('other_income', {}).get('value', 0.0)
    lines.append(f"Gross receipts or sales: ${gross_receipts:.2f}")
    lines.append(f"Returns and allowances: ${returns:.2f}")
    lines.append(f"Total other income: ${other_inc:.2f}")
    
    # 費用項目
    lines.append(f"Advertising: ${biz.get('advertising', {}).get('value', 0.0):.2f}")
    lines.append(f"Commissions and fees: ${biz.get('commissions_fees', {}).get('value', 0.0):.2f}")
    lines.append(f"Contract labor: ${biz.get('contract_labor', {}).get('value', 0.0):.2f}")
    lines.append(f"Depletion: ${biz.get('depletion', {}).get('value', 0.0):.2f}")
    lines.append(f"Employee benefit programs: ${biz.get('employee_benefit', {}).get('value', 0.0):.2f}")
    lines.append(f"Insurance (other than health): ${biz.get('insurance', {}).get('value', 0.0):.2f}")
    lines.append(f"Mortgage interest: ${biz.get('mortgage_interest', {}).get('value', 0.0):.2f}")
    lines.append(f"Other business interest: ${biz.get('other_interest', {}).get('value', 0.0):.2f}")
    lines.append(f"Legal and professional services: ${biz.get('legal_professional', {}).get('value', 0.0):.2f}")
    lines.append(f"Office expenses: ${biz.get('office_expense', {}).get('value', 0.0):.2f}")
    lines.append(f"Pension and profit-sharing plans: ${biz.get('pension_psp', {}).get('value', 0.0):.2f}")
    lines.append(f"Rent of machinery and equipment: ${biz.get('machinery_equip_rent', {}).get('value', 0.0):.2f}")
    lines.append(f"Rent of other business property: ${biz.get('other_rent', {}).get('value', 0.0):.2f}")
    lines.append(f"Repairs and maintenance: ${biz.get('repairs_maintenance', {}).get('value', 0.0):.2f}")
    lines.append(f"Supplies: ${biz.get('supplies', {}).get('value', 0.0):.2f}")
    lines.append(f"Taxes and licenses: ${biz.get('tax_licenses', {}).get('value', 0.0):.2f}")
    lines.append(f"Utilities: ${biz.get('utilities', {}).get('value', 0.0):.2f}")
    lines.append(f"Wages paid to employees: ${biz.get('wages_expense', {}).get('value', 0.0):.2f}")
    
    # 家庭辦公室 (Home Office)
    home_area = biz.get('total_home_area', {}).get('value', 0.0)
    biz_area = biz.get('business_home_area', {}).get('value', 0.0)
    lines.append(f"Total home area: {home_area} sq ft")
    lines.append(f"Business use of home area: {biz_area} sq ft")
    lines.append(f"Home office used exclusively and regularly for business: {biz_area > 0}")
    lines.append("Home office deduction method: simplified")
    
    # 風險申報 (At-risk)
    lines.append(f"All investment in this business is at risk: {biz.get('schc_at_risk', {}).get('value', True)}")
    
    # 車輛費用 (Vehicle info)
    v_list = biz.get('vehicle_info_group', [])
    if v_list:
        v = v_list[0]
        lines.append("Vehicle information:")
        lines.append(f"  Always used standard mileage rate: {v.get('vehicle_standard_mileage', {}).get('value', True)}")
        lines.append(f"  Date first used for business: {v.get('vehicle_service_date', {}).get('value', '')}")
        lines.append(f"  Business miles: {v.get('vehicle_business_miles', {}).get('value', 0.0)}")
        lines.append(f"  Commuting miles: {v.get('vehicle_commuting_miles', {}).get('value', 0.0)}")
        lines.append(f"  Other personal miles: {v.get('vehicle_other_miles', {}).get('value', 0.0)}")
        lines.append(f"  Available for personal use: {v.get('vehicle_off_duty', {}).get('value', False)}")
        lines.append(f"  Another vehicle available for personal use: {v.get('vehicle_another_avail', {}).get('value', False)}")
        lines.append(f"  Has supporting evidence: {v.get('vehicle_evidence_support', {}).get('value', False)}")
        lines.append(f"  Evidence is written: {v.get('vehicle_evidence_written', {}).get('value', False)}")
        lines.append(f"  Parking fees: ${v.get('car_truck_expense_parking', {}).get('value', 0.0):.2f}")
        lines.append(f"  Tolls: ${v.get('car_truck_expense_tolls', {}).get('value', 0.0):.2f}")
        
    # 其他雜費
    other_list = biz.get('other_expense_detail', [])
    if other_list:
        lines.append("Other miscellaneous business expenses:")
        for item in other_list:
            desc = item.get('other_expense_detail_desc', {}).get('value', '')
            amt = item.get('other_expense_detail_amt', {}).get('value', 0.0)
            if desc and amt > 0:
                lines.append(f"  - Description: {desc}, Amount: ${amt:.2f}")
                
    return "\n".join(lines)

def parse_xml_schedule_c_ground_truth(xml_path):
    """
    從 IRS MeF XML 檔案中讀取所有 Schedule C 的預期對齊數值
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    sch_c_nodes = root.findall(".//IRS1040ScheduleC")
    results = []
    
    for node in sch_c_nodes:
        def get_float(tag):
            elem = node.find(f".//{tag}")
            if elem is not None and elem.text:
                try:
                    return float(elem.text)
                except ValueError:
                    return 0.0
            return 0.0
            
        def get_text(tag):
            elem = node.find(f".//{tag}")
            if elem is not None:
                return elem.text
            return ""
            
        results.append({
            "proprietor_name": get_text("ProprietorNm"),
            "ssn": get_text("SSN"),
            "business_name": get_text("BusinessNameLine1Txt"),
            "expected_line_1": get_float("TotalGrossReceiptsAmt"),
            "expected_line_5": get_float("GrossProfitAmt"),
            "expected_line_7": get_float("GrossIncomeAmt"),
            "expected_line_28": get_float("TotalExpensesAmt"),
            "expected_line_31": get_float("NetProfitOrLossAmt")
        })
        
    return results

def main():
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    target_dir = os.path.join(workspace_dir, "tax_calc_bench_test", "schedule_c")
    cases_dir = os.path.join(target_dir, "cases")
    
    if not os.path.exists(cases_dir):
        print(f"❌ 找不到 cases 目錄: {cases_dir}")
        return
        
    cases = sorted([d for d in os.listdir(cases_dir) if os.path.isdir(os.path.join(cases_dir, d))])
    
    print(f"=== 開始執行 Schedule C 批次對齊測試 (總共 {len(cases)} 個案例) ===")
    
    results_summary = []
    
    for case in cases:
        print(f"\n👉 測試案例: {case} ...")
        case_path = os.path.join(cases_dir, case)
        input_path = os.path.join(case_path, "input.json")
        output_xml_path = os.path.join(case_path, "output_expected.xml")
        
        if not os.path.exists(input_path) or not os.path.exists(output_xml_path):
            print(f"  ❌ 檔案不全，跳過")
            continue
            
        with open(input_path, "r", encoding="utf-8") as f:
            input_data = json.load(f)
            
        # 讀取 taxpayer profiles
        return_data = input_data["input"].get("return_data", {})
        profile_1040 = return_data.get("irs1040", {})
        tp_name = f"{profile_1040.get('tp_first_name', {}).get('value', '')} {profile_1040.get('tp_last_name', {}).get('value', '')}".strip()
        sp_name = f"{profile_1040.get('sp_first_name', {}).get('value', '')} {profile_1040.get('sp_last_name', {}).get('value', '')}".strip()
        
        tp_ssn = input_data["input"].get("return_header", {}).get("tp_ssn", {}).get("value", "")
        sp_ssn = input_data["input"].get("return_header", {}).get("sp_ssn", {}).get("value", "")
        
        biz_list = return_data.get("irs1040_schedulec", [])
        if not biz_list:
            print(f"  ⚠️ 此案例中沒有 Schedule C 填表數據")
            continue
            
        # 解析預期結果
        expected_results = parse_xml_schedule_c_ground_truth(output_xml_path)
        actual_results = []
        
        for idx, biz in enumerate(biz_list):
            who = biz.get("who_applies_to", {}).get("value", "taxpayer")
            p_name = tp_name if who == "taxpayer" else sp_name
            p_ssn = tp_ssn if who == "taxpayer" else sp_ssn
            
            tp_profile = {"name": p_name, "ssn": p_ssn}
            
            print(f"  🔄 執行子業務 {idx + 1}/{len(biz_list)}: {p_name} ({biz.get('business_act', {}).get('value', 'N/A')}) ...")
            
            text_context = format_column_tax_input_to_text(biz, tp_profile)
            
            t_start = time.time()
            try:
                # 呼叫 LLM 進行提取 (使用 Flash 模型進行測試)
                extracted_inputs, _, _ = extract_schedule_c_inputs_with_logs(text_context, model_name="gemini-2.5-flash")
                final_state = calculate_schedule_c_dynamic(extracted_inputs)
                latency = time.time() - t_start
                
                # 查找對應的預期結果
                # 先比對標準化姓名，若無法精確匹配則以順序比對
                matched_expected = None
                norm_p_name = normalize_name(p_name)
                for exp in expected_results:
                    if normalize_name(exp["proprietor_name"]) == norm_p_name:
                        matched_expected = exp
                        break
                        
                if matched_expected is None:
                    # 依 index 兜底
                    if idx < len(expected_results):
                        matched_expected = expected_results[idx]
                        
                if matched_expected is None:
                    print(f"    ❌ 無法找到與子業務相符的 XML 預期結果")
                    actual_results.append({
                        "proprietor_name": p_name,
                        "passed": False,
                        "error": "Cannot find expected XML node",
                        "metrics": {}
                    })
                    continue
                    
                # 取得實際金額與預期金額
                act_line_1 = float(final_state.get("line_1_gross_receipts", 0.0) or 0.0)
                act_line_5 = float(final_state.get("line_5_gross_profit", 0.0) or 0.0)
                act_line_7 = float(final_state.get("line_7_gross_income", 0.0) or 0.0)
                act_line_28 = float(final_state.get("line_28_total_expenses", 0.0) or 0.0)
                act_line_31 = float(final_state.get("line_31_net_profit", 0.0) or 0.0)
                
                exp_line_1 = matched_expected["expected_line_1"]
                exp_line_5 = matched_expected["expected_line_5"]
                exp_line_7 = matched_expected["expected_line_7"]
                exp_line_28 = matched_expected["expected_line_28"]
                exp_line_31 = matched_expected["expected_line_31"]
                
                # 金額精確比對
                line1_ok = abs(act_line_1 - exp_line_1) < 1e-9
                line5_ok = abs(act_line_5 - exp_line_5) < 1e-9
                line7_ok = abs(act_line_7 - exp_line_7) < 1e-9
                line28_ok = abs(act_line_28 - exp_line_28) < 1e-9
                line31_ok = abs(act_line_31 - exp_line_31) < 1e-9
                
                biz_passed = line1_ok and line5_ok and line7_ok and line28_ok and line31_ok
                
                actual_results.append({
                    "proprietor_name": p_name,
                    "passed": biz_passed,
                    "latency": latency,
                    "metrics": {
                        "line_1": {"actual": act_line_1, "expected": exp_line_1, "ok": line1_ok},
                        "line_5": {"actual": act_line_5, "expected": exp_line_5, "ok": line5_ok},
                        "line_7": {"actual": act_line_7, "expected": exp_line_7, "ok": line7_ok},
                        "line_28": {"actual": act_line_28, "expected": exp_line_28, "ok": line28_ok},
                        "line_31": {"actual": act_line_31, "expected": exp_line_31, "ok": line31_ok}
                    }
                })
                print(f"    ➔ {'✅ PASS' if biz_passed else '❌ FAIL'} (耗時 {latency:.2f}s)")
                
            except Exception as ex:
                print(f"    ❌ 發生錯誤: {ex}")
                actual_results.append({
                    "proprietor_name": p_name,
                    "passed": False,
                    "error": str(ex),
                    "metrics": {}
                })
            time.sleep(0.5) # 防止 Rate Limit
            
        case_passed = all(res["passed"] for res in actual_results)
        results_summary.append({
            "case_name": case,
            "passed": case_passed,
            "businesses": actual_results
        })
        
    # ==========================================
    # 產生 Markdown Log 報告
    # ==========================================
    total_cases = len(results_summary)
    passed_cases = sum(1 for r in results_summary if r["passed"])
    accuracy = (passed_cases / total_cases * 100) if total_cases > 0 else 0.0
    
    md_lines = []
    md_lines.append("# 📋 TaxCalcBench (TY24) Schedule C 完整自動化對齊測試報告")
    md_lines.append(f"\n- **測試執行時間**: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    md_lines.append(f"- **總測試案例數**: {total_cases}")
    md_lines.append(f"- **成功通過件數**: {passed_cases} / {total_cases}")
    md_lines.append(f"- **整體對齊精確度 (Accuracy)**: **{accuracy:.2f}%**")
    md_lines.append(f"\n## 📊 各測試案例對齊明細")
    md_lines.append("| 測試案例名稱 | 是否通過 | 業務子項對齊細節 |")
    md_lines.append("| :--- | :---: | :--- |")
    
    for r in results_summary:
        case_name = r["case_name"]
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        
        detail_strs = []
        for b in r["businesses"]:
            p_name = b["proprietor_name"]
            if "error" in b:
                detail_strs.append(f"👤 {p_name}: ❌ 錯誤 ({b['error']})")
                continue
                
            b_status = "✅" if b["passed"] else "❌"
            m = b["metrics"]
            
            line1_str = f"L1: {m['line_1']['actual']}/{m['line_1']['expected']}"
            line28_str = f"L28: {m['line_28']['actual']}/{m['line_28']['expected']}"
            line31_str = f"L31: {m['line_31']['actual']}/{m['line_31']['expected']}"
            
            detail_strs.append(f"👤 {p_name} {b_status} ({line1_str} | {line28_str} | {line31_str})")
            
        md_lines.append(f"| {case_name} | {status} | {'<br>'.join(detail_strs)} |")
        
    report_path = os.path.join(target_dir, "log.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
        
    print(f"\n🎉 Schedule C 批次測試完成！報告已產生並寫入 {report_path}")

if __name__ == "__main__":
    main()
