import sys
import os
import json
import xml.etree.ElementTree as ET

# 將工作路徑加入系統中以載入專案模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from schedule_b_processor import extract_schedule_b_inputs_with_logs, calculate_schedule_b_dynamic

def format_column_tax_input_to_text(data):
    """
    將 Column Tax (TaxCalcBench) 的真實 input.json 格式轉換為無結構敘述文字。
    """
    return_data = data["input"]["return_data"]
    profile = return_data.get("irs1040", {})
    sch_b_data = return_data.get("irs1040_scheduleb", {})
    int_list = sch_b_data.get("irs1099_int", [])
    div_list = sch_b_data.get("irs1099_div", [])
    
    lines = []
    lines.append(f"Taxpayer: {profile.get('tp_first_name', {}).get('value')} {profile.get('tp_last_name', {}).get('value')}")
    lines.append(f"Filing Status: {profile.get('filing_status', {}).get('value')}")
    lines.append(f"Date of Birth: {profile.get('tp_date_of_birth', {}).get('value')}")
    
    # 載入所有 1099-INT
    for idx, item in enumerate(int_list):
        payer = item.get("interest_1099int_payer", {}).get("value", f"Payer {idx}")
        amount = item.get("interest_1099int_interest", {}).get("value", 0)
        ein = item.get("interest_1099int_payer_ein", {}).get("value", "")
        lines.append(f"Form 1099-INT {idx+1} Payer Name: {payer}, TIN/EIN: {ein}, Box 1 Interest Income: ${amount:.2f}")
        
    # 載入所有 1099-DIV
    for idx, item in enumerate(div_list):
        payer = item.get("dividend_1099div_payer_name", {}).get("value", f"Payer {idx}")
        ord_div = item.get("dividend_1099div_ordinary_dividends", {}).get("value", 0)
        qual_div = item.get("dividend_1099div_qualified_dividends", {}).get("value", 0)
        lines.append(f"Form 1099-DIV {idx+1} Payer Name: {payer}, Box 1a Ordinary Dividends: ${ord_div:.2f}, Box 1b Qualified Dividends: ${qual_div:.2f}")
        
    # 海外帳戶問卷
    has_foreign = sch_b_data.get("foreign_accounts_input", {}).get("value", False)
    has_trust = sch_b_data.get("foreign_trust_input", {}).get("value", False)
    
    lines.append(f"Question: At any point in the year, did you have any financial accounts outside the U.S.? Answer: {has_foreign}")
    lines.append(f"Question: Did you receive a distribution from, were the grantor of, or transferor to a foreign trust? Answer: {has_trust}")
    
    return "\n".join(lines)

def run_test():
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    # 指向真實 Git 複製下來的 Test Case
    test_case_dir = os.path.join(workspace_dir, "scratch", "tax-calc-bench", "tax_calc_bench", "ty24", "test_data", "single-w2-multiple-1099int-withholding-schedule-b")
    
    input_path = os.path.join(test_case_dir, "input.json")
    output_xml_path = os.path.join(test_case_dir, "output.xml")
    
    if not os.path.exists(input_path) or not os.path.exists(output_xml_path):
        print(f"❌ 找不到對應的測試檔案路徑，請確認 git clone 是否成功。")
        sys.exit(1)
        
    print("=== Step 1: 讀取 Column Tax 真實 Git 測試案例 ===")
    with open(input_path, "r", encoding="utf-8") as f:
        input_json = json.load(f)
        
    print("\n=== Step 2: 轉換為文字 Context ===")
    text_context = format_column_tax_input_to_text(input_json)
    print("----- 轉換後文字內容 -----")
    print(text_context)
    print("--------------------------")
    
    print("\n=== Step 3: 呼叫 LLM 進行 Schedule B 欄位定性提取 ===")
    # 預設使用 gemini-2.5-flash 來快速測試
    model_name = "gemini-2.5-flash"
    extracted_inputs, _, _ = extract_schedule_b_inputs_with_logs(text_context, model_name=model_name)
    
    print("LLM 提取之 JSON 輸入數據：")
    print(json.dumps(extracted_inputs, indent=2, ensure_ascii=False))
    
    print("\n=== Step 4: 執行 Python 圖論計算引擎 ===")
    final_state = calculate_schedule_b_dynamic(extracted_inputs)
    
    print("\n=== Step 5: 解析 output.xml 標準 IRS 正解 ===")
    tree = ET.parse(output_xml_path)
    root = tree.getroot()
    
    # 尋找 XML 中預期的正解數值
    expected_total_interest_str = root.find(".//CalculatedTotalTaxableIntAmt").text
    expected_foreign_accounts_str = root.find(".//ForeignAccountsQuestionInd").text
    expected_foreign_trust_str = root.find(".//ForeignTrustQuestionInd").text
    
    expected_total_interest = float(expected_total_interest_str)
    expected_foreign_accounts = (expected_foreign_accounts_str.lower() == "true")
    expected_foreign_trust = (expected_foreign_trust_str.lower() == "true")
    expected_schedule_b_required = expected_total_interest > 1500.0
    
    expected_data = {
        "line_2_total_interest": expected_total_interest,
        "line_4_surface_value": expected_total_interest,
        "line_7a_q1_surface": expected_foreign_accounts,
        "line_8_surface": expected_foreign_trust,
        "is_schedule_b_required": expected_schedule_b_required
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
            # 布林值比對，若為 None 則轉為 False 以跟 XML default 對齊
            actual_bool = bool(actual_val)
            passed = (actual_bool == expected_val)
            
        status = "✅ PASS" if passed else "❌ FAIL"
        if not passed:
            all_passed = False
        print(f"欄位 {key:35s} ➔ 實際值: {actual_val} | 預期值: {expected_val} | 狀態: {status}")
        
    if all_passed:
        print("\n🎉 恭喜！真實 TaxCalcBench (Git 來源) 對齊比對測試成功通過！所有數值皆符合預期正解！")
    else:
        print("\n❌ 測試失敗，請檢查欄位計算與提取邏輯。")
        sys.exit(1)

if __name__ == "__main__":
    run_test()
