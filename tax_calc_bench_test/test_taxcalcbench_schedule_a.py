import sys
import os
import json
import xml.etree.ElementTree as ET

# 將工作路徑加入系統中以載入專案模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from schedule_a_processor import extract_schedule_a_inputs_with_logs, calculate_schedule_a_dynamic

def format_column_tax_input_to_text(data):
    """
    將 Column Tax (TaxCalcBench) 的真實 input.json 格式轉換為 Schedule A 無結構敘述文字。
    """
    header = data["input"].get("return_header", {})
    ssn = header.get("tp_ssn", {}).get("value", "")
    
    return_data = data["input"].get("return_data", {})
    profile = return_data.get("irs1040", {})
    w2_list = return_data.get("w2", [])
    
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
        
    lines.append(f"Tax Year: 2024")
    
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
    
    return "\n".join(lines)

def run_test():
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    # 測試單一 benchmark 案例
    test_case_dir = os.path.join(workspace_dir, "tax_calc_bench_test", "schedule_a", "cases", "mfj-schedule-2-multiple-w2-excess-social-security-tax")
    
    input_path = os.path.join(test_case_dir, "input.json")
    output_xml_path = os.path.join(test_case_dir, "output_expected.xml")
    
    if not os.path.exists(input_path) or not os.path.exists(output_xml_path):
        print(f"❌ 找不到對應的測試檔案路徑，請確認檔案是否已正確複製。")
        sys.exit(1)
        
    print("=== Step 1: 讀取 Column Tax 真實測試案例 ===")
    with open(input_path, "r", encoding="utf-8") as f:
        input_json = json.load(f)
        
    print("\n=== Step 2: 轉換為文字 Context ===")
    text_context = format_column_tax_input_to_text(input_json)
    print("----- 轉換後文字內容 -----")
    print(text_context)
    print("--------------------------")
    
    print("\n=== Step 3: 呼叫 LLM 進行 Schedule A 欄位定性提取 ===")
    model_name = "gemini-2.5-flash"
    extracted_inputs, _, _ = extract_schedule_a_inputs_with_logs(text_context, model_name=model_name)
    
    print("LLM 提取之 JSON 輸入數據：")
    print(json.dumps(extracted_inputs, indent=2, ensure_ascii=False))
    
    print("\n=== Step 4: 執行 Python 計算引擎 ===")
    final_state = calculate_schedule_a_dynamic(extracted_inputs)
    print("實際計算結果:")
    print(f"  Itemized Deductions Total (Line 17): {final_state.get('line_17_total_itemized_deductions')}")
    print(f"  Standard Deduction Amount: {final_state.get('standard_deduction_amount')}")
    print(f"  Deduction Used: {final_state.get('final_deduction_used')}")
    print(f"  Is Itemizing: {final_state.get('is_itemizing')}")
    
    print("\n=== Step 5: 解析 output_expected.xml 標準 IRS 正解 ===")
    tree = ET.parse(output_xml_path)
    root = tree.getroot()
    
    expected_total_ded_str = root.find(".//TotalItemizedOrStandardDedAmt").text
    
    code_node = root.find(".//StandardOrNonStandardCd")
    if code_node is not None and code_node.text:
        expected_is_itemizing = (code_node.text.upper() == "I")
    else:
        expected_is_itemizing = False
        
    expected_total_ded = float(expected_total_ded_str)
    
    expected_data = {
        "final_deduction_used": expected_total_ded,
        "is_itemizing": expected_is_itemizing
    }
    
    print("\n=== Step 6: 實際比對我們的計算結果與 IRS XML 欄位 ===")
    all_passed = True
    for key, expected_val in expected_data.items():
        actual_val = final_state.get(key)
        
        # 進行比對
        if isinstance(expected_val, float) or isinstance(expected_val, int):
            actual_val_num = float(actual_val) if actual_val is not None else 0.0
            diff = abs(actual_val_num - float(expected_val))
            passed = diff < 1e-9
        else:
            actual_bool = bool(actual_val)
            passed = (actual_bool == expected_val)
            
        status = "✅ PASS" if passed else "❌ FAIL"
        if not passed:
            all_passed = False
        print(f"欄位 {key:35s} ➔ 實際值: {actual_val} | 預期值: {expected_val} | 狀態: {status}")
        
    if all_passed:
        print("\n🎉 恭喜！真實 TaxCalcBench Schedule A 對齊比對測試成功通過！")
    else:
        print("\n❌ 測試失敗，請檢查欄位計算與提取邏輯。")
        sys.exit(1)

if __name__ == "__main__":
    run_test()
