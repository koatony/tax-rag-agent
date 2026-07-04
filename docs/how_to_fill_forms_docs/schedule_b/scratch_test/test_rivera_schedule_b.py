import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))
from schedule_b_processor import calculate_schedule_b_dynamic

def test_rivera():
    rivera_inputs = {
        'taxpayer_name': 'MARCUS & ELENA RIVERA',
        'ssn': '123-45-6789',
        'tax_year': 2025,
        'interest_items': [
            {'payer_name': 'CHASE', 'amount': 150.0}
        ],
        'dividend_items': [
            {'payer_name': 'VANGUARD', 'ordinary_dividends': 405.0}
        ],
        'foreign_accounts_interest': False,
        'fbar_required': False,
        'foreign_countries_list': [],
        'foreign_trust_distribution': False
    }
    
    result = calculate_schedule_b_dynamic(rivera_inputs)
    print("=== Rivera Case Schedule B Test Output ===")
    print(f"Name shown on return: {result['taxpayer_name']}")
    print(f"Line 2 (Total Interest): {result['line_2_total_interest']}")
    print(f"Line 4 (Taxable Interest): {result['line_4_taxable_interest']}")
    print(f"Line 6 (Ordinary Dividends): {result['line_6_total_ordinary_dividends']}")
    print(f"Line 7a Part 1 Checkbox (Foreign Account): {result['line_7a_foreign_account_authority']}")
    print(f"Line 7a Part 2 Checkbox (FBAR Required): {result['line_7a_fbar_required']}")
    print(f"Line 7b Country List: '{result['line_7b_foreign_countries']}'")
    print(f"Line 8 Checkbox (Foreign Trust): {result.get('line_8_foreign_trust_distribution')}")
    print(f"Seller Financed Mortgage Interest Helper: {result.get('has_seller_financed_mortgage')}")
    print(f"Is Schedule B required (filing threshold etc.): {result['is_schedule_b_required']}")

if __name__ == "__main__":
    test_rivera()
