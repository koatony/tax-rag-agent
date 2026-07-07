import os
import sys
import json
import xml.etree.ElementTree as ET
import shutil
import time
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# 將工作路徑加入系統中以載入專案模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from schedule_a_processor import extract_schedule_a_inputs_with_logs, calculate_schedule_a_dynamic

# 定義 2025 年測試案例目錄
target_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "schedule_a"))
cases_target_dir = os.path.join(target_dir, "cases_itemize")
if os.path.exists(cases_target_dir):
    SCH_A_CASES = sorted([d for d in os.listdir(cases_target_dir) if os.path.isdir(os.path.join(cases_target_dir, d))])
else:
    SCH_A_CASES = []

def format_column_tax_input_to_text(data):
    """
    將 Column Tax (TaxCalcBench) 的真實 input.json 格式轉換為 Schedule A 無結構敘述文字。
    全面支援：申報人資訊、W-2、房貸利息、醫療支出、慈善捐贈、銷售稅、財產稅。
    """
    header = data["input"].get("return_header", {})
    ssn = header.get("tp_ssn", {}).get("value", "")
    
    return_data = data["input"].get("return_data", {})
    profile = return_data.get("irs1040", {})
    w2_list = return_data.get("w2", [])
    
    # 預設為 2025 年
    tax_yr = 2025
    
    lines = []
    lines.append(f"Taxpayer: {profile.get('tp_first_name', {}).get('value')} {profile.get('tp_last_name', {}).get('value')}")
    lines.append(f"SSN: {ssn}")
    lines.append(f"Filing Status: {profile.get('filing_status', {}).get('value')}")
    lines.append(f"Date of Birth: {profile.get('tp_date_of_birth', {}).get('value')}")
    lines.append(f"Taxpayer Legally Blind: {profile.get('tp_blind', {}).get('value') or False}")
    
    if profile.get('sp_first_name', {}).get('value'):
        lines.append(f"Spouse: {profile.get('sp_first_name', {}).get('value')} {profile.get('sp_last_name', {}).get('value')}")
        lines.append(f"Spouse Date of Birth: {profile.get('sp_date_of_birth', {}).get('value')}")
        lines.append(f"Spouse Legally Blind: {profile.get('sp_blind', {}).get('value') or False}")
        
    lines.append(f"Tax Year: {tax_yr}")
    
    # 載入所有 W-2 及其 state_income_tax
    for idx, w2 in enumerate(w2_list):
        emp_name = w2.get("employer_name", {}).get("value", f"Employer {idx}")
        wages = w2.get("wages", {}).get("value", 0.0)
        lines.append(f"W-2 {idx+1} Employer: {emp_name}, Box 1 Wages: ${wages:.2f}")
        
        # 州與地方稅
        state_grp = w2.get("w2_state_local_tax_grp", [])
        for s_idx, state_item in enumerate(state_grp):
            state_code = state_item.get("state", {}).get("value", "")
            state_tax = state_item.get("state_income_tax", {}).get("value", 0.0)
            local_tax = state_item.get("local_income_tax", {}).get("value", 0.0)
            lines.append(f"  W-2 {idx+1} State/Local Record {s_idx+1}: State: {state_code}, Box 17 State Income Tax: ${state_tax:.2f}, Box 19 Local Income Tax: ${local_tax:.2f}")
            
    # Marketplace 問卷
    received_1095a = return_data.get("irs8962", {}).get("received_1095a", {}).get("value", False)
    lines.append(f"Question: Did you purchase health insurance through a state or federal marketplace? Answer: {received_1095a}")
    
    # 載入列舉項目 (房貸、捐款、自住房地產稅)
    sch_a = return_data.get("irs1040_schedulea", {})
    if sch_a:
        mortgage = sch_a.get("home_mortgage_interest_1098", {}).get("value")
        if mortgage is not None and mortgage > 0:
            lines.append(f"Home Mortgage Interest Paid (reported on Form 1098 Box 1): ${mortgage:.2f}. This is confirmed to be a simple mortgage (CONFIRMED_SIMPLE) with no limitations required.")
        charity = sch_a.get("cash_charitable_contributions", {}).get("value")
        if charity is not None and charity > 0:
            lines.append(f"Cash Charitable Contributions (with bank record and acknowledgment): ${charity:.2f} to a verified qualified organization (VERIFIED) on 2025-12-01. A bank record is available and contemporaneous written acknowledgment (CWA) has been received.")
        re_tax = sch_a.get("real_estate_taxes", {}).get("value")
        if re_tax is not None and re_tax > 0:
            lines.append(f"State and Local Real Estate Taxes Paid (for personal use): ${re_tax:.2f}")
        pp_tax = sch_a.get("personal_property_taxes", {}).get("value")
        if pp_tax is not None and pp_tax > 0:
            lines.append(f"Personal Property Taxes Paid: ${pp_tax:.2f}")
        sales_tax = sch_a.get("general_sales_taxes", {}).get("value")
        if sales_tax is not None and sales_tax > 0:
            lines.append(f"General Sales Taxes Paid: ${sales_tax:.2f}")
        sales_tax_elec = sch_a.get("sales_tax_election", {}).get("value")
        if sales_tax_elec is not None:
            lines.append(f"Taxpayer elects to deduct state and local general sales taxes: {sales_tax_elec == 'GENERAL_SALES_TAX'}")
            
    # 載入醫療支出項目
    med_list = return_data.get("medical_expense_items", []) or return_data.get("medical_items", [])
    for idx, item in enumerate(med_list):
        desc = item.get("description", "Medical expense")
        amt = item.get("taxpayer_paid_amount", 0.0)
        lines.append(f"Medical Expense {idx+1}: Description: {desc}, Amount Paid: ${amt:.2f}, Reimbursement Received: $0.00, Paid by HSA/FSA: $0.00, Paid for eligible taxpayer/spouse: Yes, Qualified Simple category: Yes")
        
    # Check if they elect to itemize even if less than standard deduction
    std_ref = return_data.get("standard_deduction_reference", {})
    if std_ref.get("elect_itemize_even_if_less"):
        lines.append("Question: Do you elect to itemize your deductions even if they are less than your standard deduction? Answer: True")
        
    return "\n".join(lines)

def parse_xml_ground_truth(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    expected_total_ded_str = root.find(".//TotalItemizedOrStandardDedAmt").text
    
    sch_a_node = root.find(".//IRS1040ScheduleA")
    if sch_a_node is not None:
        expected_is_itemizing = True
        code_node = sch_a_node.find(".//StandardOrNonStandardCd")
        if code_node is not None and code_node.text:
            expected_is_itemizing = (code_node.text.upper() == "I")
    else:
        expected_is_itemizing = False
        
    expected_total_ded = float(expected_total_ded_str)
    
    return {
        "final_deduction_used": expected_total_ded,
        "is_itemizing": expected_is_itemizing
    }

def main():
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    # 依使用者要求，使用 gemini-2.5-pro 進行分析
    model_name = "gemini-2.5-pro"
    print(f"使用的 LLM 評估模型: {model_name}")
    
    print(f"=== 開始執行 Schedule A 逐項扣除 (Itemize) 自動化對齊測試 (總共 {len(SCH_A_CASES)} 個案例) ===")
    
    results_summary = []
    
    for case in SCH_A_CASES:
        print(f"\n👉 測試案例: {case} ...")
        case_save_dir = os.path.join(cases_target_dir, case)
        input_git_path = os.path.join(case_save_dir, "input.json")
        output_git_path = os.path.join(case_save_dir, "output_expected.xml")
        
        if not os.path.exists(input_git_path) or not os.path.exists(output_git_path):
            print(f"❌ 找不到案例檔案，跳過: {case}")
            continue
            
        t_start = time.time()
        try:
            with open(input_git_path, "r", encoding="utf-8") as f:
                input_data = json.load(f)
                
            text_context = format_column_tax_input_to_text(input_data)
            print("----- Text Context -----")
            print(text_context)
            print("------------------------")
            
            # 呼叫 LLM 進行提取
            extracted_inputs, _, _ = extract_schedule_a_inputs_with_logs(text_context, model_name=model_name)
            
            print("LLM 提取之 JSON 輸入數據：")
            print(json.dumps(extracted_inputs, indent=2, ensure_ascii=False))
            
            final_state = calculate_schedule_a_dynamic(extracted_inputs)
            latency = time.time() - t_start
            
            # 將 Decimal 序列化為 float
            def decimal_to_float(obj):
                from decimal import Decimal
                if isinstance(obj, Decimal):
                    return float(obj)
                if isinstance(obj, dict):
                    return {k: decimal_to_float(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [decimal_to_float(i) for i in obj]
                return obj
            
            serializable_state = decimal_to_float(final_state)
            
            # 儲存輸出結果
            with open(os.path.join(case_save_dir, "output_actual.json"), "w", encoding="utf-8") as f:
                json.dump(serializable_state, f, indent=2, ensure_ascii=False)
                
            # 解析正解
            expected = parse_xml_ground_truth(output_git_path)
            
            # 比對
            actual_ded = float(final_state.get("final_deduction_used", 0.0) or 0.0)
            actual_is_itemizing = bool(final_state.get("is_itemizing", False))
            
            ded_ok = abs(actual_ded - expected["final_deduction_used"]) < 1e-9
            item_ok = (actual_is_itemizing == expected["is_itemizing"])
            
            case_passed = ded_ok and item_ok
            
            results_summary.append({
                "case": case,
                "passed": case_passed,
                "latency": latency,
                "metrics": {
                    "deduction": {"actual": actual_ded, "expected": expected["final_deduction_used"], "ok": ded_ok},
                    "is_itemizing": {"actual": actual_is_itemizing, "expected": expected["is_itemizing"], "ok": item_ok}
                }
            })
            print(f"   ➔ {'✅ PASS' if case_passed else '❌ FAIL'} (耗時 {latency:.2f}s)")
            
        except Exception as ex:
            print(f"   ➔ ❌ 發生例外錯誤: {ex}")
            results_summary.append({
                "case": case,
                "passed": False,
                "error": str(ex),
                "metrics": {}
            })
            
    # 產生 Markdown Log 報告
    passed_count = sum(1 for r in results_summary if r["passed"])
    total_count = len(results_summary)
    accuracy_rate = (passed_count / total_count) * 100 if total_count > 0 else 0
    
    md_lines = []
    md_lines.append("# 📋 TaxCalcBench Schedule A 逐項扣除 (Itemize) 對齊測試報告")
    md_lines.append(f"\n- **測試執行時間**: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    md_lines.append(f"- **評估 LLM 模型**: {model_name}")
    md_lines.append(f"- **總測試案例數**: {total_count}")
    md_lines.append(f"- **成功通過件數**: {passed_count} / {total_count}")
    md_lines.append(f"- **整體對齊精確度 (Accuracy)**: **{accuracy_rate:.2f}%**")
    md_lines.append(f"\n## 📊 各測試案例對齊明細")
    md_lines.append("| 測試案例名稱 | 是否通過 | 扣除金額 (實際/預期) | 是否逐項扣除 (實際/預期) | 耗時 (秒) |")
    md_lines.append("| :--- | :---: | :---: | :---: | :---: |")
    
    for r in results_summary:
        case_name = r["case"]
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        
        if "error" in r:
            md_lines.append(f"| {case_name} | {status} | *(執行錯誤: {r['error']})* | | - |")
            continue
            
        m = r["metrics"]
        ded_str = f"{m['deduction']['actual']} / {m['deduction']['expected']} {'(OK)' if m['deduction']['ok'] else '(X)'}"
        item_str = f"{m['is_itemizing']['actual']} / {m['is_itemizing']['expected']} {'(OK)' if m['is_itemizing']['ok'] else '(X)'}"
        
        md_lines.append(f"| [{case_name}](cases_itemize/{case_name}/) | {status} | {ded_str} | {item_str} | {r['latency']:.2f} |")
        
    md_lines.append("\n## 📂 檔案目錄說明")
    md_lines.append("- 各案例的來源與輸出保存在 `cases_itemize/` 資料夾中。")
    md_lines.append("  - `input.json`: 原始申報人財務欄位。")
    md_lines.append("  - `output_expected.xml`: 預期標準 IRS MeF XML（`is_itemizing = True`）。")
    md_lines.append("  - `output_actual.json`: 本專案 Schedule A 引擎計算出來的實際輸出。")
    
    report_content = "\n".join(md_lines)
    
    # 寫入 log_itemize.md
    report_path = os.path.join(target_dir, "log_itemize.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    print(f"\n🎉 批次測試完成！報告已產生並寫入 {report_path}")

if __name__ == "__main__":
    main()
