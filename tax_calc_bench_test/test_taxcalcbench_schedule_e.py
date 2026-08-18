import sys
import os
import json
from decimal import Decimal

# 將工作路徑加入系統中以載入專案模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from schedule_e_processor import calculate_schedule_e_dynamic

def run_benchmark_tests():
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ty25_dir = os.path.join(workspace_dir, "scratch", "tax-calc-bench", "tax_calc_bench", "ty25", "test_data")
    
    if not os.path.exists(ty25_dir):
        print("❌ 找不到 TY25 測試資料庫路徑，請確認 scratch/tax-calc-bench 是否正確存在。")
        sys.exit(1)
        
    print("=== Step 1: 掃描 Column Tax 測試資料庫以尋找 Schedule E 案例 ===")
    
    cases_found = []
    for case_name in os.listdir(ty25_dir):
        case_path = os.path.join(ty25_dir, case_name)
        remaining_json_path = os.path.join(case_path, "input", "remaining_data.json")
        if os.path.exists(remaining_json_path):
            with open(remaining_json_path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    return_data = data.get("input", {}).get("return_data", {})
                    if "scherentslist" in return_data or "sche_gen" in return_data:
                        cases_found.append((case_name, remaining_json_path, return_data))
                except Exception as e:
                    pass
                    
    print(f"找到 {len(cases_found)} 個包含 Schedule E 資訊的測試案例: {[c[0] for c in cases_found]}\n")
    
    all_passed = True
    
    for case_name, file_path, return_data in cases_found:
        print(f"--- 測試案例: {case_name} ---")
        
        # 1. 取得全域 Schedule E 設定 (sche_gen)
        sche_gen = return_data.get("sche_gen", {})
        is_re_prof = sche_gen.get("REProfessional", {}).get("value", False)
        req_1099 = sche_gen.get("require1099", {}).get("value", False)
        filed_1099 = sche_gen.get("require1099filed", {}).get("value", "N")
        
        # 2. 轉換為我們 DTO 接受的格式
        profile = return_data.get("irs1040", {})
        tp_name = f"{profile.get('tp_first_name', {}).get('value', 'Test')} {profile.get('tp_last_name', {}).get('value', 'Taxpayer')}"
        tp_ssn = "123-45-6789"  # 測試用遮蔽 SSN
        
        # 轉換 1099 狀態
        compliance_status = "NOT_REQUIRED"
        filed_status = None
        if req_1099:
            compliance_status = "REQUIRED"
            filed_status = (filed_1099 == "Y" or filed_1099 is True)
            
        # 建立 properties 清單
        raw_properties = []
        rents_list = return_data.get("scherentslist", [])
        
        has_royalty = False
        has_self_rental = False
        
        for idx, item in enumerate(rents_list):
            prop_type_val = item.get("propertyType", {}).get("value", "Single-family residence")
            
            # 對齊 DTO property_type
            mapped_type = "SINGLE_FAMILY_RESIDENCE"
            if "multi-family" in prop_type_val.lower():
                mapped_type = "MULTI_FAMILY_RESIDENCE"
            elif "royalties" in prop_type_val.lower():
                mapped_type = "ROYALTIES"
                has_royalty = True
            elif "self-rental" in prop_type_val.lower():
                mapped_type = "SELF_RENTAL"
                has_self_rental = True
                
            # 租金收入 (otherIncome 包含總租金)
            income_val = float(item.get("otherIncome", {}).get("value", 0.0))
            rental_income_items = []
            if income_val > 0:
                rental_income_items.append({
                    "item_id": f"inc_{idx}",
                    "source_document_id": "doc_rent",
                    "gross_amount_received": income_val,
                    "refunded_or_returned_amount": 0.0,
                    "income_character_status": "REPORTABLE_SIMPLE_RENTAL_INCOME",
                    "received_in_tax_year": True
                })
                
            # 費用處理
            rental_expense_items = []
            # 廣告費
            adv_val = float(item.get("advertising", {}).get("value", 0.0))
            if adv_val > 0:
                rental_expense_items.append({
                    "item_id": f"exp_adv_{idx}",
                    "expense_category": "ADVERTISING",
                    "gross_amount": adv_val,
                    "reimbursement_amount": 0.0,
                    "nonrental_allocated_amount": 0.0,
                    "deductibility_status": "DEDUCTIBLE_CURRENT",
                    "allocation_status": "TAXPAYER_SHARE_CONFIRMED",
                    "paid_or_incurred_in_tax_year": True
                })
            # 法律費
            legal_val = float(item.get("legal", {}).get("value", 0.0))
            if legal_val > 0:
                rental_expense_items.append({
                    "item_id": f"exp_legal_{idx}",
                    "expense_category": "LEGAL_AND_PROFESSIONAL_FEES",
                    "gross_amount": legal_val,
                    "reimbursement_amount": 0.0,
                    "nonrental_allocated_amount": 0.0,
                    "deductibility_status": "DEDUCTIBLE_CURRENT",
                    "allocation_status": "TAXPAYER_SHARE_CONFIRMED",
                    "paid_or_incurred_in_tax_year": True
                })
                
            # 折舊折抵
            dep_val = float(item.get("noFormDepreciation", {}).get("value", 0.0))
            dep_result = None
            if dep_val > 0:
                dep_result = {
                    "property_id": f"prop_{idx}",
                    "tax_year": 2024,
                    "calculation_status": "CALCULATED",
                    "depreciation_amount": dep_val,
                    "source_result_id": "dep_mod_01"
                }
                
            raw_properties.append({
                "property_id": f"prop_{idx}",
                "physical_address": {
                    "street": item.get("addrUSAddressLine1", {}).get("value", "1 Address"),
                    "city": item.get("addrUSCity", {}).get("value", "City"),
                    "state": item.get("addrUSState", {}).get("value", "FL"),
                    "zip_code": item.get("addrUSZIPCode", {}).get("value", "33755"),
                    "country": "US"
                },
                "property_type": mapped_type,
                "reporting_route_status": "SCHEDULE_E_CONFIRMED",
                "fair_rental_days": int(item.get("rentalDays", {}).get("value", 365)),
                "personal_use_days": int(item.get("personalUseDays", {}).get("value", 0)),
                "qjv_status": False,
                "ownership_allocation_status": "TAXPAYER_SHARE_CONFIRMED",
                "rental_income_items": rental_income_items,
                "rental_expense_items": rental_expense_items,
                "depreciation_result": dep_result
            })
            
        # 3. 組裝全域 Inputs DTO payload
        inputs_payload = {
            "taxpayer_name": tp_name,
            "taxpayer_ssn": tp_ssn,
            "tax_year": 2024,
            "filing_status": "MFJ",
            "accounting_method": "CASH",
            "form_1099_compliance": {
                "requirement_status": compliance_status,
                "filed_or_will_file_required_forms": filed_status,
                "source_result_id": "res_1099"
            },
            "special_case_flags": {
                "has_real_estate_professional_case": is_re_prof
            },
            "properties": raw_properties
        }
        
        # 4. 執行 V1 計算引擎
        result = calculate_schedule_e_dynamic(inputs_payload)
        
        print(f"  V1 支援狀態: {result.get('is_v1_supported')}")
        print(f"  可否完成 Part I 申報: {result.get('can_finalize_part1')}")
        print(f"  攔截到的阻斷錯誤:")
        err_codes = [err.get("code") for err in result.get("blocking_errors", []) + result.get("review_warnings", [])]
        for err in result.get("blocking_errors", []):
            print(f"    - [BLOCKING][{err.get('code')}]: {err.get('message')}")
        for warn in result.get("review_warnings", []):
            print(f"    - [WARNING][{warn.get('code')}]: {warn.get('message')}")
            
        # 5. 驗證阻斷是否符合安全防禦預期
        expected_errors = []
        if is_re_prof:
            expected_errors.append("UNSUPPORTED_REAL_ESTATE_PROFESSIONAL_CASE")
        if has_royalty:
            expected_errors.append("UNSUPPORTED_ROYALTY_PROPERTY")
        if has_self_rental:
            expected_errors.append("UNSUPPORTED_SELF_RENTAL")
        if len(raw_properties) == 0:
            expected_errors.append("NO_REPORTABLE_RENTAL_PROPERTY")
            
        case_passed = True
        for exp_err in expected_errors:
            if exp_err not in err_codes:
                print(f"  ❌ 錯誤：預期應攔截到 {exp_err}，但引擎未正確觸發。")
                case_passed = False
                all_passed = False
                
        if case_passed:
            print("  ✅ 測試通過：結果與預期完全一致！")
        else:
            print("  ❌ 測試未通過。")
            all_passed = False
                
    if all_passed:
        print("\n🎉 恭喜！真實 TaxCalcBench (TY25 測試庫) 中的 Schedule E 案例安全防範比對測試全部通過！")
    else:
        sys.exit(1)

if __name__ == "__main__":
    run_benchmark_tests()
