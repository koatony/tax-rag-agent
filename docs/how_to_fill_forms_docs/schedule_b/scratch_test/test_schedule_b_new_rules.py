import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))
from schedule_b_processor import calculate_schedule_b_dynamic

def run_tests():
    print("=== STARTING SCHEDULE B NEW RULES TESTS ===")

    # 1. 測試：Line 1 & Line 5 必須列出 payer reported amount (原始毛額)，而不是每筆淨額
    #    且調整項目（Nominee, Accrued, OID, ABP）是在計算 Line 2/6 時才扣除
    test_1 = {
        'taxpayer_name': 'Test Payer Entries',
        'interest_items': [
            {
                'payer_name': 'Chase Bank',
                'reported_amount': 1000.0,
                'nominee_amount': 100.0,
                'accrued_interest': 50.0,
                'oid_taxpayer_computed_adjustment': 30.0,
                'abp_taxpayer_computed_adjustment': 20.0
            }
        ],
        'dividend_items': [
            {
                'payer_name': 'Vanguard Ordinary',
                'ordinary_dividends': 500.0,
                'nominee_ordinary_amount': 50.0
            }
        ]
    }
    res_1 = calculate_schedule_b_dynamic(test_1)
    
    # 驗證 Line 1 申報的是原始毛額 1000.0，而不是淨額 800.0
    line_1_entries = res_1['line_1_payer_entries']
    assert len(line_1_entries) == 1, "Line 1 should have exactly one entry"
    assert line_1_entries[0]['reported_amount'] == 1000.0, f"Line 1 entry should show gross 1000.0, got {line_1_entries[0]['reported_amount']}"
    
    # 驗證 Line 2 計算為 1000 - 100 - 50 - 30 - 20 = 800.0
    assert res_1['interest_subtotal'] == 1000.0
    assert res_1['nominee_interest_adjustment'] == 100.0
    assert res_1['accrued_interest_adjustment'] == 50.0
    assert res_1['oid_interest_adjustment'] == 30.0
    assert res_1['abp_interest_adjustment'] == 20.0
    assert res_1['line_2_total_interest'] == 800.0, f"Line 2 calculation mismatch, got {res_1['line_2_total_interest']}"

    # 驗證 Line 5 申報的是原始毛額 500.0
    line_5_entries = res_1['line_5_payer_entries']
    assert len(line_5_entries) == 1
    assert line_5_entries[0]['reported_amount'] == 500.0
    assert res_1['dividend_subtotal'] == 500.0
    assert res_1['nominee_ordinary_dividend_adjustment'] == 50.0
    assert res_1['line_6_total_ordinary_dividends'] == 450.0
    print("✅ Test 1 (Payer Entries structure) passed!")

    # 2. 測試：預防重複扣除 (Double Deduction Prevention)
    #    Case A: Broker 已經在 reported amount 中淨額申報 (reported_amount_is_net is True) -> 調整值為 0
    #    Case B: Broker 有提供 adjustment box (adjustment_box_present is True) -> 使用 broker adjustment
    #    Case C: 以上皆否 -> 使用 taxpayer computed adjustment
    test_2 = {
        'taxpayer_name': 'Double Deduction Test',
        'interest_items': [
            # Case A: Net reported
            {
                'payer_name': 'Broker Net',
                'reported_amount': 500.0,
                'oid_reported_amount_is_net': True,
                'oid_taxpayer_computed_adjustment': 50.0
            },
            # Case B: Box present
            {
                'payer_name': 'Broker Box Present',
                'reported_amount': 600.0,
                'abp_reported_adjustment_box_present': True,
                'abp_broker_adjustment_amount': 30.0,
                'abp_taxpayer_computed_adjustment': 100.0
            },
            # Case C: Regular taxpayer computed
            {
                'payer_name': 'Taxpayer Computed',
                'reported_amount': 700.0,
                'oid_taxpayer_computed_adjustment': 40.0
            }
        ]
    }
    res_2 = calculate_schedule_b_dynamic(test_2)
    processed_int_2 = res_2['processed_interest_items']
    
    # Broker Net: OID adjustment should be 0.0, net = 500.0
    assert processed_int_2[0]['oid_applied'] == 0.0
    assert processed_int_2[0]['eligible_taxable_amount'] == 500.0
    
    # Broker Box Present: ABP adjustment should be 30.0, net = 600.0 - 30.0 = 570.0
    assert processed_int_2[1]['abp_applied'] == 30.0
    assert processed_int_2[1]['eligible_taxable_amount'] == 570.0
    
    # Taxpayer Computed: OID adjustment should be 40.0, net = 700.0 - 40.0 = 660.0
    assert processed_int_2[2]['oid_applied'] == 40.0
    assert processed_int_2[2]['eligible_taxable_amount'] == 660.0
    print("✅ Test 2 (Double Deduction Prevention) passed!")

    # 3. 測試：不一律使用 MAX(0, ...)，如果 Line 4 < 0.0 或 Line 3 合理性有問題 -> blocking_validation_error = True
    test_3a = {
        'taxpayer_name': 'Negative Line 4 Test',
        'interest_items': [{'payer_name': 'Chase', 'reported_amount': 100.0}],
        'excludable_savings_bond_interest': 150.0  # Line 3 exceeds Line 2
    }
    res_3a = calculate_schedule_b_dynamic(test_3a)
    assert res_3a['line_4_taxable_interest'] == -50.0, "Line 4 should not be clamped to 0"
    assert res_3a['blocking_validation_error'] is True, "Should raise blocking validation error when Line 4 is negative"
    
    # Form 8815 Line 14 <= Series EE/I interest check
    test_3b = {
        'taxpayer_name': 'Form 8815 Validation Test',
        'interest_items': [
            {
                'payer_name': 'Chase Savings Bond',
                'reported_amount': 200.0,
                'is_series_ee_i_savings_bond': True
            },
            {
                'payer_name': 'Other Payer',
                'reported_amount': 500.0
            }
        ],
        'excludable_savings_bond_interest': 250.0  # Exceeds the EE/I bond interest (200.0)
    }
    res_3b = calculate_schedule_b_dynamic(test_3b)
    assert res_3b['blocking_validation_error'] is True, "Form 8815 Line 14 cannot exceed EE/I savings bond interest in Line 2"
    print("✅ Test 3 (No Max(0) & Form 8815 validation) passed!")

    # 4. 測試：ABP 超額處理 (ABP Excess)
    #    ABP adjustment 超過剩餘利息部分不應直接使 net_taxable 歸零，而是應該被 cap，且超額部分記入 abp_excess_schedule_a，並設 needs_human_review = True
    test_4 = {
        'taxpayer_name': 'ABP Excess Test',
        'interest_items': [
            {
                'payer_name': 'High Premium Bond',
                'reported_amount': 100.0,
                'nominee_amount': 20.0,
                'abp_taxpayer_computed_adjustment': 120.0  # exceeds remaining 80.0
            }
        ]
    }
    res_4 = calculate_schedule_b_dynamic(test_4)
    processed_int_4 = res_4['processed_interest_items'][0]
    # ABP should be capped at 80.0, excess is 40.0
    assert processed_int_4['abp_applied'] == 80.0
    assert processed_int_4['abp_excess_schedule_a'] == 40.0
    assert processed_int_4['eligible_taxable_amount'] == 0.0
    assert processed_int_4['needs_human_review'] is True
    assert res_4['needs_human_review'] is True
    print("✅ Test 4 (ABP Excess Handling) passed!")

    # 5. 測試：Form 8814 支援
    #    包含 Form 8814 的股利應列在 Line 5，且名稱為 "Form 8814"
    test_5 = {
        'taxpayer_name': 'Form 8814 Test',
        'dividend_items': [
            {
                'payer_name': 'Form 8814',
                'form_type': '8814',
                'ordinary_dividends': 600.0,
                'qualified_dividends': 400.0
            },
            {
                'payer_name': 'Apple Inc.',
                'ordinary_dividends': 100.0
            }
        ]
    }
    res_5 = calculate_schedule_b_dynamic(test_5)
    line_5_entries = res_5['line_5_payer_entries']
    # 應有兩筆
    assert len(line_5_entries) == 2
    names = [e['payer_name'] for e in line_5_entries]
    assert "Form 8814" in names
    assert res_5['line_6_total_ordinary_dividends'] == 700.0
    print("✅ Test 5 (Form 8814 support) passed!")

    # 6. 測試：Filing Triggers & Part III validation
    #    is_schedule_b_required 應包含多個條件：Line 4 > 1500, nominee, ABP, FBAR, etc.
    #    is_part_iii_required = Line 4 > 1500 or Line 6 > 1500 or Q1 or Trust
    test_6 = {
        'taxpayer_name': 'Filing Triggers Test',
        'interest_items': [
            {
                'payer_name': 'Chase',
                'reported_amount': 200.0,
                'nominee_amount': 10.0  # triggers Schedule B but not Part III directly (unless Line 4/6 > 1500)
            }
        ],
        'dividend_items': []
    }
    res_6 = calculate_schedule_b_dynamic(test_6)
    assert res_6['is_schedule_b_required'] is True, "Nominee should trigger Schedule B"
    assert res_6['is_part_iii_required'] is False, "Part III shouldn't be required for low amount and no foreign triggers"
    assert res_6['line_7a_foreign_account_authority'] is None, "Line 7a Part 1 should be None if Part III not required"
    assert res_6['line_7a_fbar_required'] is None, "Line 7a Part 2 should be None if Part III not required"
    assert res_6['line_7b_foreign_countries'] is None, "Line 7b should be None if Part III not required"
    assert res_6['line_8_foreign_trust_distribution'] is None, "Line 8 should be None if Part III not required"
    
    # 測試 Part III required 且資料缺失的警告
    test_6b = {
        'taxpayer_name': 'Part III Validation Error Test',
        'interest_items': [{'payer_name': 'Chase', 'reported_amount': 2000.0}],  # > 1500, requires Part III
        'has_foreign_financial_account_interest_or_signature_authority': None,  # Missing answer
        'foreign_trust_received_distribution': None
    }
    res_6b = calculate_schedule_b_dynamic(test_6b)
    assert res_6b['is_part_iii_required'] is True
    assert res_6b['needs_human_review'] is True, "Missing answers for Part III should trigger review"
    
    # 測試 FBAR required 但沒給國家列表
    test_6c = {
        'taxpayer_name': 'FBAR Missing Countries Test',
        'interest_items': [{'payer_name': 'Chase', 'reported_amount': 2000.0}],
        'has_foreign_financial_account_interest_or_signature_authority': True,
        'fbar_required': True,
        'foreign_countries_list': [],  # Empty country list
        'foreign_trust_received_distribution': False,
        'foreign_trust_received_deemed_distribution_or_loan': False,
        'foreign_trust_was_grantor': False,
        'foreign_trust_was_transferor': False
    }
    res_6c = calculate_schedule_b_dynamic(test_6c)
    assert res_6c['needs_human_review'] is True, "Empty country list when FBAR required should trigger review"
    print("✅ Test 6 (Filing Triggers & Part III Validation) passed!")

    print("🎉 ALL NEW SCHEDULE B RULES TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
