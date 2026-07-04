import os
import sys
import json
import xml.etree.ElementTree as ET
import shutil
import time

# 將工作路徑加入系統中以載入專案模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from schedule_b_processor import extract_schedule_b_inputs_with_logs, calculate_schedule_b_dynamic

# 13 個 Schedule B 相關的真實案例清單
SCH_B_CASES = [
    "hoh-schedule-b-ssa1099-unemployment",
    "mfj-capital-gains-losses-wash-sale-dependent",
    "mfj-dependent-claimed-2441-exclusion",
    "mfj-multiple-1099int-schedule-b-w2",
    "mfj-schedule-c-1099-misc-nec-k-ssa-1099-int-g",
    "mfj-w2-box12-codes-a-b-1099int-schedulec",
    "mfj-w2-capital-gains-wash-sales-dividends-dependent",
    "single-1099int-interest-income-schedule-b",
    "single-schedulec-1099misc-nec-k-loss",
    "single-senior-blind-over-65",
    "single-w2-multiple-1099int-dividend",
    "single-w2-multiple-1099int-federal-withholding",
    "single-w2-multiple-1099int-withholding-schedule-b"
]

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
    lines.append(f"Taxpayer: {profile.get('tp_first_name', {}).get('value', '')} {profile.get('tp_last_name', {}).get('value', '')}")
    lines.append(f"Filing Status: {profile.get('filing_status', {}).get('value', '')}")
    
    # 載入所有 1099-INT
    for idx, item in enumerate(int_list):
        payer = item.get("interest_1099int_payer", {}).get("value")
        if not payer:
            payer = item.get("interest_1099int_payer_name", {}).get("value", f"Payer {idx}")
        amount = item.get("interest_1099int_interest", {}).get("value", 0)
        ein = item.get("interest_1099int_payer_ein", {}).get("value", "")
        lines.append(f"Form 1099-INT {idx+1} Payer Name: {payer}, TIN/EIN: {ein}, Box 1 Interest Income: ${amount:.2f}")
        
    # 載入所有 1099-DIV
    for idx, item in enumerate(div_list):
        payer = item.get("dividend_1099div_payer", {}).get("value")
        if not payer:
            payer = item.get("dividend_1099div_payer_name", {}).get("value", f"Payer {idx}")
            
        ord_div = item.get("dividend_1099div_ordinary_div", {}).get("value")
        if ord_div is None:
            ord_div = item.get("dividend_1099div_ordinary_dividends", {}).get("value", 0)
            
        qual_div = item.get("dividend_1099div_qualified_div", {}).get("value")
        if qual_div is None:
            qual_div = item.get("dividend_1099div_qualified_dividends", {}).get("value", 0)
            
        lines.append(f"Form 1099-DIV {idx+1} Payer Name: {payer}, Box 1a Ordinary Dividends: ${ord_div:.2f}, Box 1b Qualified Dividends: ${qual_div:.2f}")
        
    # 載入所有 Form 1099-B (Form 8949) 交易（包含 accrued market discount 資訊）
    irs8949 = return_data.get("irs8949", {})
    b_groups = irs8949.get("irs1099_b_grp", [])
    for grp_idx, grp in enumerate(b_groups):
        payer = grp.get("payer_name", {}).get("value", f"Brokerage {grp_idx+1}")
        b_list = grp.get("irs1099_b", [])
        for idx, item in enumerate(b_list):
            desc = item.get("desc_of_prop", {}).get("value", "")
            proceeds = item.get("proceeds", {}).get("value", 0.0)
            cost = item.get("cost_basis", {}).get("value", 0.0)
            amd = item.get("accrued_market_discount", {}).get("value", 0.0)
            term = item.get("input_sale_term", {}).get("value", "")
            
            # 如果有 accrued market discount，則格式化進去，但拿掉任何規則提示
            if amd > 0:
                lines.append(
                    f"Form 1099-B Transaction {idx+1} from {payer}: "
                    f"Description: {desc}, "
                    f"Proceeds: ${proceeds:.2f}, "
                    f"Cost Basis: ${cost:.2f}, "
                    f"Accrued Market Discount: ${amd:.2f}, "
                    f"Sale Term: {term}."
                )

    # 海外帳戶問卷
    has_foreign = sch_b_data.get("foreign_accounts_input", {}).get("value", False)
    has_trust = sch_b_data.get("foreign_trust_input", {}).get("value", False)
    
    lines.append(f"Question: At any point in the year, did you have any financial accounts outside the U.S.? Answer: {has_foreign}")
    lines.append(f"Question: Did you receive a distribution from, were the grantor of, or transferor to a foreign trust? Answer: {has_trust}")
    
    return "\n".join(lines)

def parse_xml_ground_truth(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    # 1. Total taxable interest
    taxable_interest = 0.0
    int_elem = root.find(".//TaxableInterestAmt")
    if int_elem is not None:
        taxable_interest = float(int_elem.text)
    else:
        int_elem_schb = root.find(".//CalculatedTotalTaxableIntAmt")
        if int_elem_schb is not None:
            taxable_interest = float(int_elem_schb.text)
            
    # 2. Total ordinary dividends
    ordinary_dividends = 0.0
    div_elem = root.find(".//OrdinaryDividendsAmt")
    if div_elem is not None:
        ordinary_dividends = float(div_elem.text)
    else:
        div_elem_schb = root.find(".//CalculatedTotalOrdDivAmt")
        if div_elem_schb is not None:
            ordinary_dividends = float(div_elem_schb.text)
            
    # 3. Schedule B required
    schb_required = root.find(".//IRS1040ScheduleB") is not None
    
    # 4. Foreign Accounts
    foreign_accounts = False
    fa_elem = root.find(".//ForeignAccountsQuestionInd")
    if fa_elem is not None:
        foreign_accounts = fa_elem.text.lower() == "true"
        
    # 5. Foreign Trust
    foreign_trust = False
    ft_elem = root.find(".//ForeignTrustQuestionInd")
    if ft_elem is not None:
        foreign_trust = ft_elem.text.lower() == "true"
        
    return {
        "taxable_interest": taxable_interest,
        "ordinary_dividends": ordinary_dividends,
        "is_schedule_b_required": schb_required,
        "foreign_account": foreign_accounts,
        "foreign_trust": foreign_trust
    }

def main():
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    # 目標紀錄資料夾
    target_dir = os.path.join(workspace_dir, "tax_calc_bench_test", "schedule_b")
    cases_target_dir = os.path.join(target_dir, "cases")
    
    os.makedirs(cases_target_dir, exist_ok=True)
    
    git_test_data_dir = os.path.join(workspace_dir, "scratch", "tax-calc-bench", "tax_calc_bench", "ty24", "test_data")
    
    print(f"=== 開始執行 Schedule B 批次對齊測試 (總共 {len(SCH_B_CASES)} 個案例) ===")
    
    results_summary = []
    
    for case in SCH_B_CASES:
        print(f"\n👉 測試案例: {case} ...")
        case_git_dir = os.path.join(git_test_data_dir, case)
        input_git_path = os.path.join(case_git_dir, "input.json")
        output_git_path = os.path.join(case_git_dir, "output.xml")
        
        if not os.path.exists(input_git_path) or not os.path.exists(output_git_path):
            print(f"❌ 找不到案例檔案，跳過: {case}")
            continue
            
        # 建立此案例在 target_dir 下的專屬資料夾
        case_save_dir = os.path.join(cases_target_dir, case)
        os.makedirs(case_save_dir, exist_ok=True)
        
        # 複製來源檔案
        shutil.copy2(input_git_path, os.path.join(case_save_dir, "input.json"))
        shutil.copy2(output_git_path, os.path.join(case_save_dir, "output_expected.xml"))
        
        # 讀取 JSON 並處理
        with open(input_git_path, "r", encoding="utf-8") as f:
            input_data = json.load(f)
            
        text_context = format_column_tax_input_to_text(input_data)
        
        # 呼叫 LLM 進行提取 (使用 Flash 模型以求高效率)
        t_start = time.time()
        try:
            extracted_inputs, _, _ = extract_schedule_b_inputs_with_logs(text_context, model_name="gemini-2.5-flash")
            final_state = calculate_schedule_b_dynamic(extracted_inputs)
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
                
            # 解析 IRS 正解
            expected = parse_xml_ground_truth(output_git_path)
            
            # 比對欄位值
            actual_taxable_interest = float(final_state.get("line_4_surface_value", 0.0) or 0.0)
            actual_ordinary_dividends = float(final_state.get("line_6_total_ordinary_dividends", 0.0) or 0.0)
            actual_schb_required = bool(final_state.get("is_schedule_b_required", False))
            actual_foreign_accounts = bool(final_state.get("line_7a_foreign_account_authority", False))
            actual_foreign_trust = bool(final_state.get("line_8_foreign_trust_distribution", False))
            
            # 利息/股利數值比對
            int_ok = abs(actual_taxable_interest - expected["taxable_interest"]) < 1e-9
            div_ok = abs(actual_ordinary_dividends - expected["ordinary_dividends"]) < 1e-9
            req_ok = (actual_schb_required == expected["is_schedule_b_required"])
            fa_ok = (actual_foreign_accounts == expected["foreign_account"])
            ft_ok = (actual_foreign_trust == expected["foreign_trust"])
            
            case_passed = int_ok and div_ok and req_ok and fa_ok and ft_ok
            
            results_summary.append({
                "case": case,
                "passed": case_passed,
                "latency": latency,
                "metrics": {
                    "interest": {"actual": actual_taxable_interest, "expected": expected["taxable_interest"], "ok": int_ok},
                    "dividends": {"actual": actual_ordinary_dividends, "expected": expected["ordinary_dividends"], "ok": div_ok},
                    "schb_required": {"actual": actual_schb_required, "expected": expected["is_schedule_b_required"], "ok": req_ok},
                    "foreign_accounts": {"actual": actual_foreign_accounts, "expected": expected["foreign_account"], "ok": fa_ok},
                    "foreign_trust": {"actual": actual_foreign_trust, "expected": expected["foreign_trust"], "ok": ft_ok}
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
    md_lines.append("# 📋 TaxCalcBench (TY24) Schedule B 完整自動化對齊測試報告")
    md_lines.append(f"\n- **測試執行時間**: 2026-07-03")
    md_lines.append(f"- **總測試案例數**: {total_count}")
    md_lines.append(f"- **成功通過件數**: {passed_count} / {total_count}")
    md_lines.append(f"- **整體對齊精確度 (Accuracy)**: **{accuracy_rate:.2f}%**")
    md_lines.append(f"\n## 📊 各測試案例對齊明細")
    md_lines.append("| 測試案例名稱 | 是否通過 | 利息 (實際/預期) | 股利 (實際/預期) | 需 Schedule B (實際/預期) | 海外帳戶 (實際/預期) | 海外信託 (實際/預期) | 耗時 (秒) |")
    md_lines.append("| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |")
    
    for r in results_summary:
        case_name = r["case"]
        status = "✅ PASS" if r["passed"] else "❌ FAIL"
        
        if "error" in r:
            md_lines.append(f"| {case_name} | {status} | *(執行錯誤: {r['error']})* | | | | | - |")
            continue
            
        m = r["metrics"]
        int_str = f"{m['interest']['actual']} / {m['interest']['expected']} {'(OK)' if m['interest']['ok'] else '(X)'}"
        div_str = f"{m['dividends']['actual']} / {m['dividends']['expected']} {'(OK)' if m['dividends']['ok'] else '(X)'}"
        req_str = f"{m['schb_required']['actual']} / {m['schb_required']['expected']} {'(OK)' if m['schb_required']['ok'] else '(X)'}"
        fa_str = f"{m['foreign_accounts']['actual']} / {m['foreign_accounts']['expected']} {'(OK)' if m['foreign_accounts']['ok'] else '(X)'}"
        ft_str = f"{m['foreign_trust']['actual']} / {m['foreign_trust']['expected']} {'(OK)' if m['foreign_trust']['ok'] else '(X)'}"
        
        md_lines.append(f"| [{case_name}](cases/{case_name}/) | {status} | {int_str} | {div_str} | {req_str} | {fa_str} | {ft_str} | {r['latency']:.2f} |")
        
    md_lines.append("\n## 📂 檔案目錄說明")
    md_lines.append("- 各案例的來源與輸出保存在 `cases/` 資料夾中。")
    md_lines.append("  - `input.json`: 來自 TaxCalcBench 的原始申報人財務欄位。")
    md_lines.append("  - `output_expected.xml`: 來自 TaxCalcBench 的預期標準 IRS MeF XML。")
    md_lines.append("  - `output_actual.json`: 本專案 Schedule B 引擎計算出來的實際輸出。")
    
    report_content = "\n".join(md_lines)
    
    # 寫入 log.md
    report_path = os.path.join(target_dir, "log.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    print(f"\n🎉 批次測試完成！報告已產生並寫入 {report_path}")

if __name__ == "__main__":
    main()
