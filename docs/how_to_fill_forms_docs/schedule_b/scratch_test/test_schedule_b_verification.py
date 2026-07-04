import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))
from schedule_b_processor import calculate_schedule_b_dynamic

def run_tests():
    # 測試案例 1：複雜的申報案例 (超過門檻、包含各項減除、賣方融資利息與海外帳戶)
    test_inputs_1 = {
        'taxpayer_name': 'John & Jane Smith',
        'ssn': '999-88-7777',
        'tax_year': 2025,
        
        # 利息項目
        'interest_items': [
            # 1. 普通應稅利息
            {'payer_name': 'Chase Bank', 'amount': 200.0},
            # 2. 免稅利息 (不應計入 Line 2)
            {'payer_name': 'Wells Fargo (Municipal Bond)', 'amount': 500.0, 'is_tax_exempt': True},
            # 3. 賣方融資利息 (應稅利息，且應計入 Line 8)
            {
                'payer_name': 'Alice Smith (Buyer)', 
                'amount': 1000.0, 
                'is_seller_financed': True, 
                'buyer_ssn': '111-22-3333', 
                'buyer_address': '123 Main St, Springfield'
            },
            # 4. 包含 Nominee / Accrued Interest / OID / ABP 調整的利息
            {
                'payer_name': 'Bond Account X', 
                'amount': 1200.0,
                'nominee_amount': 100.0,
                'accrued_interest': 50.0,
                'oid_adjustment': 30.0,
                'bond_premium_adjustment': 20.0,
                'source_document_type': '1099-INT'
            }
        ],
        
        # 股利項目
        'dividend_items': [
            # 1. 普通股利
            {'payer_name': 'Apple Inc.', 'ordinary_dividends': 1000.0, 'qualified_dividends': 800.0},
            # 2. 包含 Nominee 轉付的股利
            {'payer_name': 'Brokerage Nominee Y', 'ordinary_dividends': 800.0, 'nominee_amount': 300.0}
        ],
        
        # Form 8815 排除
        'excludable_savings_bond_interest': 150.0,
        
        # Part III 海外帳戶與信託
        'foreign_accounts_interest': True,
        'fbar_required': True,
        'foreign_countries_list': ['Taiwan', 'Japan'],
        'foreign_trust_distribution': False
    }

    print("=== 執行測試案例 1: 複雜申報案例 ===")
    result_1 = calculate_schedule_b_dynamic(test_inputs_1)
    
    # 期望值計算:
    # Line 2 (利息合計) = Chase (200) + Municipal (0) + Seller-Financed (1000) + Bond X (1200 - 100 - 50 - 30 - 20 = 1000) = 2200.0
    # Line 3 (儲蓄債券免稅) = 150.0
    # Line 4 (最終應稅利息) = 2200 - 150 = 2050.0
    # Line 6 (普通股利合計) = Apple (1000) + Nominee Y (800 - 300 = 500) = 1500.0
    # Line 7a/7b/8 Checkboxes = True, True, False, True (因為有 seller_financed)
    # is_schedule_b_required = True (利息 2050 > 1500)
    
    print(f"Line 2 利息合計: ${result_1['line_2_total_interest']:,.2f}  (期望: $2,200.00)")
    print(f"Line 3 免稅債券扣除: ${result_1['line_3_excludable_savings_bond_interest']:,.2f}  (期望: $150.00)")
    print(f"Line 4 應稅利息淨額: ${result_1['line_4_taxable_interest']:,.2f}  (期望: $2,050.00)")
    print(f"Line 6 普通股利總額: ${result_1['line_6_total_ordinary_dividends']:,.2f}  (期望: $1,500.00)")
    
    print(f"Line 7a (1) 海外帳戶利益: {result_1['line_7a_foreign_account_authority']}  (期望: True)")
    print(f"Line 7a (2) FBAR 申報義務: {result_1['line_7a_fbar_required']}  (期望: True)")
    print(f"Line 7b 海外國家: '{result_1['line_7b_foreign_countries']}'  (期望: 'Taiwan, Japan')")
    print(f"Line 8 海外信託分配: {result_1['line_8_foreign_trust_distribution']}  (期望: False)")
    print(f"賣方融資利息標記: {result_1['has_seller_financed_mortgage']}  (期望: True)")
    print(f"是否需要申報 Schedule B: {result_1['is_schedule_b_required']}  (期望: True)")
    
    # 進行斷言檢查
    assert result_1['line_2_total_interest'] == 2200.0, "Line 2 計算錯誤"
    assert result_1['line_3_excludable_savings_bond_interest'] == 150.0, "Line 3 讀取錯誤"
    assert result_1['line_4_taxable_interest'] == 2050.0, "Line 4 計算錯誤"
    assert result_1['line_6_total_ordinary_dividends'] == 1500.0, "Line 6 計算錯誤"
    assert result_1['line_7b_foreign_countries'] == "Taiwan, Japan", "Line 7b 國家格式錯誤"
    assert result_1['has_seller_financed_mortgage'] is True, "has_seller_financed_mortgage 判定錯誤"
    assert result_1['is_schedule_b_required'] is True, "Filing requirement 判定錯誤"
    print("✅ 測試案例 1 通過！\n")

    # 測試案例 2：低於門檻且無海外權限 (不需要申報 Schedule B)
    test_inputs_2 = {
        'taxpayer_name': 'Mini Doe',
        'ssn': '000-11-2222',
        'tax_year': 2025,
        'interest_items': [
            {'payer_name': 'Bank A', 'amount': 150.0}
        ],
        'dividend_items': [
            {'payer_name': 'Stock B', 'ordinary_dividends': 200.0}
        ],
        'foreign_accounts_interest': False,
        'foreign_trust_distribution': False
    }
    
    print("=== 執行測試案例 2: 低於申報門檻案例 ===")
    result_2 = calculate_schedule_b_dynamic(test_inputs_2)
    print(f"Line 4 應稅利息淨額: ${result_2['line_4_taxable_interest']:,.2f}  (期望: $150.00)")
    print(f"Line 6 普通股利總額: ${result_2['line_6_total_ordinary_dividends']:,.2f}  (期望: $200.00)")
    print(f"是否需要申報 Schedule B: {result_2['is_schedule_b_required']}  (期望: False)")
    
    assert result_2['line_4_taxable_interest'] == 150.0
    assert result_2['line_6_total_ordinary_dividends'] == 200.0
    assert result_2['is_schedule_b_required'] is False, "不需要申報 Schedule B 的情況下被判定為 True"
    print("✅ 測試案例 2 通過！\n")

    # 測試案例 3：異常資料與保護機制測試
    test_inputs_3 = {
        'interest_items': [
            # 調整金額超過利息本金 (應截斷為 0 並回傳 review flag)
            {'payer_name': 'Bad Bond', 'amount': 100.0, 'nominee_amount': 200.0}
        ],
        'dividend_items': [
            # 合格股利大於普通股利 (資料異常，應回傳 review flag)
            {'payer_name': 'Bad Dividends', 'ordinary_dividends': 100.0, 'qualified_dividends': 200.0}
        ]
    }
    print("=== 執行測試案例 3: 異常資料保護檢測 ===")
    result_3 = calculate_schedule_b_dynamic(test_inputs_3)
    
    processed_int = result_3['processed_interest_items'][0]
    processed_div = result_3['processed_dividend_items'][0]
    
    print(f"異常利息金額: ${processed_int['eligible_taxable_amount']:.2f} (期望: $0.00)")
    print(f"異常利息審查標籤 (needs_human_review): {processed_int['needs_human_review']} (期望: True)")
    print(f"異常股利審查標籤 (needs_human_review): {processed_div['needs_human_review']} (期望: True)")
    
    assert processed_int['eligible_taxable_amount'] == 0.0
    assert processed_int['needs_human_review'] is True
    assert processed_div['needs_human_review'] is True
    print("✅ 測試案例 3 通過！\n")

    # 測試案例 4：一般案例 - 總利息超過 $1,500，但因儲蓄債券免稅額 (Line 3) 扣除後低於 $1,500 (依然需要申報)
    test_inputs_4 = {
        'taxpayer_name': 'Deductible Savings Bond Case',
        'interest_items': [
            {'payer_name': 'Chase Bank', 'amount': 1600.0}
        ],
        'dividend_items': [],
        'excludable_savings_bond_interest': 200.0,
        'foreign_accounts_interest': False,
        'foreign_trust_distribution': False
    }
    print("=== 執行測試案例 4: 總利息超額但應稅低於門檻案例 ===")
    result_4 = calculate_schedule_b_dynamic(test_inputs_4)
    print(f"Line 2 總利息: ${result_4['line_2_total_interest']:,.2f}")
    print(f"Line 3 免稅儲蓄債券: ${result_4['line_3_excludable_savings_bond_interest']:,.2f}")
    print(f"Line 4 應稅利息: ${result_4['line_4_taxable_interest']:,.2f}")
    print(f"是否需要申報 Schedule B: {result_4['is_schedule_b_required']}  (期望: True)")
    assert result_4['line_2_total_interest'] == 1600.0
    assert result_4['line_4_taxable_interest'] == 1400.0
    assert result_4['is_schedule_b_required'] is True
    print("✅ 測試案例 4 通過！\n")

    # 測試案例 5：邊界案例 - 總利息剛好等於 $1,500.0 (不需要申報)
    test_inputs_5 = {
        'taxpayer_name': 'Boundary Case Exactly 1500',
        'interest_items': [
            {'payer_name': 'Chase Bank', 'amount': 1500.0}
        ],
        'dividend_items': [],
        'foreign_accounts_interest': False,
        'foreign_trust_distribution': False
    }
    print("=== 執行測試案例 5: 總利息剛好等於 $1,500 邊界案例 ===")
    result_5 = calculate_schedule_b_dynamic(test_inputs_5)
    print(f"Line 2 總利息: ${result_5['line_2_total_interest']:,.2f}")
    print(f"是否需要申報 Schedule B: {result_5['is_schedule_b_required']}  (期望: False)")
    assert result_5['line_2_total_interest'] == 1500.0
    assert result_5['is_schedule_b_required'] is False
    print("✅ 測試案例 5 通過！\n")

    # 測試案例 6：反例/相鄰案例 - 總利息為 $1,500.01 (需要申報)
    test_inputs_6 = {
        'taxpayer_name': 'Boundary Case Over 1500',
        'interest_items': [
            {'payer_name': 'Chase Bank', 'amount': 1500.01}
        ],
        'dividend_items': [],
        'foreign_accounts_interest': False,
        'foreign_trust_distribution': False
    }
    print("=== 執行測試案例 6: 總利息微幅超額 $1500.01 案例 ===")
    result_6 = calculate_schedule_b_dynamic(test_inputs_6)
    print(f"Line 2 總利息: ${result_6['line_2_total_interest']:,.2f}")
    print(f"是否需要申報 Schedule B: {result_6['is_schedule_b_required']}  (期望: True)")
    assert result_6['line_2_total_interest'] == 1500.01
    assert result_6['is_schedule_b_required'] is True
    print("✅ 測試案例 6 通過！\n")

    print("🎉 所有 Schedule B 規則引擎計算測試成功通過！")

if __name__ == "__main__":
    run_tests()
