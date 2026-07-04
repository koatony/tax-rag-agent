import streamlit as st
import json
import time
import os
import sys
import concurrent.futures

# 將工作路徑加入系統中以正確載入專案模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 載入共享 UI 輔助模組
import schedule_a_ui_helper

# ─── 安全性：密碼驗證 ─────────────────────────────────────────────────────
schedule_a_ui_helper.verify_login()

# ─── 頁面配置 ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Form 1040 Line 1a — W-2 Adapter & Mapper 測試",
    layout="wide",
)

# ─── 自訂 CSS ─────────────────────────────────────────────────────────────
schedule_a_ui_helper.inject_custom_css()

# 額外補充本頁面專用樣式
st.markdown(
    """
    <style>
    .line-1a-card {
        background: linear-gradient(135deg, rgba(99,102,241,0.15) 0%, rgba(16,185,129,0.10) 100%);
        border: 1px solid rgba(99,102,241,0.35);
        border-radius: 14px;
        padding: 22px 28px;
        margin-bottom: 18px;
    }
    .total-badge {
        display: inline-block;
        background: linear-gradient(90deg, #6366f1, #10b981);
        color: white;
        font-size: 1.5rem;
        font-weight: 800;
        padding: 6px 20px;
        border-radius: 8px;
        letter-spacing: 0.5px;
    }
    .taxpayer-chip {
        display: inline-block;
        background: rgba(59,130,246,0.18);
        color: #93c5fd;
        border: 1px solid rgba(59,130,246,0.35);
        border-radius: 20px;
        padding: 2px 12px;
        font-size: 0.82rem;
        font-weight: 600;
        margin-right: 4px;
    }
    .step-badge {
        display: inline-block;
        background: rgba(168,85,247,0.2);
        color: #c084fc;
        border: 1px solid rgba(168,85,247,0.35);
        border-radius: 6px;
        padding: 2px 10px;
        font-size: 0.78rem;
        font-weight: 700;
        margin-right: 6px;
    }
    .review-warning-box {
        background: rgba(234,179,8,0.10);
        border: 1px solid rgba(234,179,8,0.35);
        border-radius: 10px;
        padding: 14px 18px;
        margin-top: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── 載入模組 ─────────────────────────────────────────────────────────────
from adapter import W2Adapter
from mapper import Form1040WagesMapper, aggregate_form_1040_line_1a

# ─── 預設 Rivera W-2 測試資料 ─────────────────────────────────────────────
DEFAULT_W2_INPUT = {
  "taxpayer_profile": {
    "Name": "Marcus and Elena Rivera",
    "Filing Status": "Married Filing Jointly",
    "State": "California (Sacramento)",
    "Tax Year": 2024
  },
  "uploaded_documents": [
    {
      "file_name": "Sample 01 - Marcus Rivera W-2 Data.json",
      "content": "{\"document_type\": \"W-2 Wage and Tax Statement\", \"tax_year\": 2024, \"form_type\": \"W-2\", \"employee\": {\"name\": \"Marcus Rivera\", \"ssn\": \"555-12-3456\", \"address\": \"2785 River Oak Drive, Sacramento, CA 95833\"}, \"employer\": {\"name\": \"Creature Comforts Pet Supply\", \"ein\": \"94-7654321\", \"address\": \"1450 Arden Way, Sacramento, CA 95815\"}, \"boxes\": {\"box_1_wages_tips_other_compensation\": 46000.0, \"box_2_federal_income_tax_withheld\": 3800.0, \"box_3_social_security_wages\": 46000.0, \"box_4_social_security_tax_withheld\": 2852.0, \"box_5_medicare_wages_and_tips\": 46000.0, \"box_6_medicare_tax_withheld\": 667.0, \"box_7_social_security_tips\": 0.0, \"box_8_allocated_tips\": 0.0, \"box_10_dependent_care_benefits\": 0.0, \"box_11_nonqualified_plans\": 0.0, \"box_12a_code\": \"D\", \"box_12a_amount_401k_elective_deferral\": 2000.0, \"box_13_retirement_plan\": true, \"box_13_statutory_employee\": false, \"box_13_third_party_sick_pay\": false, \"box_15_state\": \"CA\", \"box_16_state_wages\": 46000.0, \"box_17_state_income_tax_withheld\": 1450.0, \"box_18_local_wages\": null, \"box_19_local_income_tax\": null, \"box_20_locality_name\": null}}"
    },
    {
      "file_name": "Sample 02 - Elena Rivera W-2 Data.json",
      "content": "{\"document_type\": \"W-2 Wage and Tax Statement\", \"tax_year\": 2024, \"form_type\": \"W-2\", \"employee\": {\"name\": \"Elena Rivera\", \"ssn\": \"555-23-4567\", \"address\": \"2785 River Oak Drive, Sacramento, CA 95833\"}, \"employer\": {\"name\": \"City of Sacramento Fire Department\", \"ein\": \"94-6000414\", \"address\": \"5770 Freeport Blvd, Sacramento, CA 95822\"}, \"boxes\": {\"box_1_wages_tips_other_compensation\": 54000.0, \"box_2_federal_income_tax_withheld\": 5200.0, \"box_3_social_security_wages\": 54000.0, \"box_4_social_security_tax_withheld\": 3348.0, \"box_5_medicare_wages_and_tips\": 54000.0, \"box_6_medicare_tax_withheld\": 783.0, \"box_12a_code\": \"DD\", \"box_12a_amount_employer_health_coverage\": 14800.0, \"box_12b_code\": \"D\", \"box_12b_amount_457_401k_contribution\": 3000.0, \"box_13_retirement_plan\": true, \"box_13_statutory_employee\": false, \"box_13_third_party_sick_pay\": false, \"box_14_other_union_dues\": 720.0, \"box_15_state\": \"CA\", \"box_16_state_wages\": 54000.0, \"box_17_state_income_tax_withheld\": 2150.0, \"box_18_local_wages\": null, \"box_19_local_income_tax\": null, \"box_20_locality_name\": null}}"
    },
    {
      "file_name": "Sample 03 - 1098 Mortgage Interest.json",
      "content": "{\"document_type\": \"Form 1098 Mortgage Interest Statement\", \"tax_year\": 2024, \"form_type\": \"1098\", \"borrowers\": [\"Marcus Rivera\", \"Elena Rivera\"], \"property\": {\"address\": \"2785 River Oak Drive, Sacramento, CA 95833\", \"same_as_borrower_address\": true}, \"lender\": {\"name\": \"Golden State Home Mortgage, LLC\", \"ein\": \"94-8765432\", \"address\": \"100 Capitol Mall, Suite 800, Sacramento, CA 95814\"}, \"boxes\": {\"box_1_mortgage_interest_received\": 9800.0, \"box_2_outstanding_mortgage_principal\": 412500.0, \"box_3_mortgage_origination_date\": \"2020-06-15\", \"box_4_refund_of_overpaid_interest\": 0.0, \"box_5_mortgage_insurance_premiums\": 1080.0, \"box_6_points_paid_on_purchase\": 0.0, \"box_7_property_address_same_as_borrower\": true, \"box_8_mortgage_acquisition_date\": \"2020-06-15\", \"box_9_number_of_mortgaged_properties\": 1, \"box_10_property_taxes_collected_via_escrow\": 2600.0}, \"target_form_mapping\": {\"box_1_mortgage_interest\": \"Schedule A Line 8a\", \"box_10_property_taxes\": \"Schedule A Line 5b (SALT)\"}}"
    },
    {
      "file_name": "Sample 04 - QuickBook PnL Sample Data.json",
      "content": "{\"document_type\": \"QuickBooks Profit & Loss Statement\", \"tax_year\": 2024, \"taxpayer\": {\"name\": \"Marcus Rivera\", \"business_name\": \"Creature Comforts Pet Supply\", \"business_type\": \"Retail Pet Supply Store\", \"entity_type\": \"Sole Proprietorship\"}, \"income\": {\"group\": \"INCOME\", \"line_items\": [{\"account\": \"Pet Food Sales\", \"amount\": 102500}, {\"account\": \"Pet Toy Sales\", \"amount\": 36800}, {\"account\": \"Pet Grooming Products\", \"amount\": 21400}, {\"account\": \"Aquarium Supplies\", \"amount\": 18700}, {\"account\": \"Training Supplies & Accessories\", \"amount\": 12000}], \"total_gross_revenue\": 191400}, \"cost_of_goods_sold\": {\"group\": \"COST OF GOODS SOLD (COGS)\", \"line_items\": [{\"account\": \"Beginning Inventory\", \"amount\": 22000}, {\"account\": \"Purchases\", \"amount\": 61000}, {\"account\": \"Freight & Shipping In\", \"amount\": 2800}, {\"account\": \"Less Ending Inventory\", \"amount\": -19500}], \"total_cogs\": 66300}, \"gross_profit\": {\"group\": \"GROSS PROFIT\", \"gross_revenue\": 191400, \"less_cogs\": -66300, \"gross_profit\": 125100}, \"operating_expenses\": {\"group\": \"OPERATING EXPENSES\", \"subgroups\": [{\"subgroup\": \"Payroll & Labor\", \"line_items\": [{\"account\": \"Employee Wages\", \"amount\": 24000}, {\"account\": \"Payroll Taxes\", \"amount\": 2000}, {\"account\": \"Contract Labor\", \"amount\": 3000}], \"subtotal\": 29000}, {\"subgroup\": \"Occupancy\", \"line_items\": [{\"account\": \"Rent Expense\", \"amount\": 18000}, {\"account\": \"Utilities\", \"amount\": 3600}, {\"account\": \"Internet & Phone\", \"amount\": 1200}, {\"account\": \"Security Monitoring\", \"amount\": 720}], \"subtotal\": 23520}, {\"subgroup\": \"Insurance\", \"line_items\": [{\"account\": \"General Liability Insurance\", \"amount\": 1500}, {\"account\": \"Business Property Insurance\", \"amount\": 1000}, {\"account\": \"Workers Compensation Insurance\", \"amount\": 1100}], \"subtotal\": 3600}, {\"subgroup\": \"Office & Administrative\", \"line_items\": [{\"account\": \"Office Supplies\", \"amount\": 850}, {\"account\": \"Software Subscriptions\", \"amount\": 900}, {\"account\": \"Bank Charges\", \"amount\": 420}, {\"account\": \"Professional Fees\", \"amount\": 1800}, {\"account\": \"Postage & Shipping\", \"amount\": 480}], \"subtotal\": 4450}, {\"subgroup\": \"Advertising & Marketing\", \"line_items\": [{\"account\": \"Facebook Advertising\", \"amount\": 2400}, {\"account\": \"Google Advertising\", \"amount\": 1600}, {\"account\": \"Local Community Sponsorships\", \"amount\": 1000}, {\"account\": \"Printed Flyers\", \"amount\": 600}], \"subtotal\": 5600}, {\"subgroup\": \"Vehicle & Travel\", \"line_items\": [{\"account\": \"Vehicle Mileage Reimbursement\", \"amount\": 1250}, {\"account\": \"Parking & Tolls\", \"amount\": 150}, {\"account\": \"Las Vegas Conference Airfare\", \"amount\": 500}, {\"account\": \"Conference Lodging\", \"amount\": 1000}], \"subtotal\": 2900}, {\"subgroup\": \"Meals & Entertainment\", \"review_required\": true, \"line_items\": [{\"account\": \"Business Travel Meals\", \"amount\": 550}, {\"account\": \"Employee Holiday Party\", \"amount\": 400}, {\"account\": \"Employee Overtime Meals\", \"amount\": 150}, {\"account\": \"Minor League Baseball Season Tickets\", \"amount\": 700}], \"subtotal\": 1800}, {\"subgroup\": \"Miscellaneous Expenses\", \"line_items\": [{\"account\": \"Cleaning Services\", \"amount\": 1200}, {\"account\": \"Equipment Repairs\", \"amount\": 1000}, {\"account\": \"Small Tools & Equipment\", \"amount\": 1200}, {\"account\": \"Merchant Processing Fees\", \"amount\": 1600}, {\"account\": \"City Business License Fine\", \"amount\": 300}], \"subtotal\": 5300}], \"total_operating_expenses_by_subgroup\": {\"Payroll & Labor\": 29000, \"Occupancy\": 23520, \"Insurance\": 3600, \"Office & Administrative\": 4450, \"Advertising & Marketing\": 5600, \"Vehicle & Travel\": 2900, \"Meals & Entertainment\": 1800, \"Miscellaneous\": 5300}, \"total_operating_expenses\": 76170}, \"net_business_income\": {\"group\": \"NET BUSINESS INCOME\", \"gross_profit\": 125100, \"less_operating_expenses\": -76170, \"net_profit\": 48930}}"
    },
    {
      "file_name": "Sample 05 - Rental Property Income.json",
      "content": "{\"document_type\": \"Rental Property Income Statement\", \"tax_year\": 2024, \"taxpayer\": {\"name\": \"Marcus & Elena Rivera\"}, \"property_info\": {\"property_address\": \"5200 Green Valley Drive, Unit 208, Sacramento, CA 95841\", \"property_type\": \"Residential Condo\", \"rental_status\": \"Full-Year Rental\", \"date_placed_in_service\": \"07/01/2022\", \"days_rented_at_fair_rental\": 365, \"personal_use_days\": 0, \"purchase_price\": 275000, \"land_value\": 55000, \"building_value\": 220000}, \"rental_income\": {\"group\": \"RENTAL INCOME\", \"line_items\": [{\"account\": \"Monthly Rent Income\", \"amount\": 16200}, {\"account\": \"Laundry Facility Reimbursement\", \"amount\": 150}, {\"account\": \"Pet Deposit Retained\", \"amount\": 300}, {\"account\": \"Less Tenant Refund\", \"amount\": 0}], \"total_rental_income\": 16650}, \"operating_expenses\": {\"group\": \"OPERATING EXPENSES\", \"subgroups\": [{\"subgroup\": \"Financing\", \"line_items\": [{\"account\": \"Mortgage Interest\", \"amount\": 4800}, {\"account\": \"Bank Loan Fees\", \"amount\": 0}], \"subtotal\": 4800}, {\"subgroup\": \"Property Taxes\", \"line_items\": [{\"account\": \"County Property Tax\", \"amount\": 2400}], \"subtotal\": 2400}, {\"subgroup\": \"Insurance\", \"line_items\": [{\"account\": \"Landlord Insurance Policy\", \"amount\": 900}], \"subtotal\": 900}, {\"subgroup\": \"Repairs & Maintenance\", \"line_items\": [{\"account\": \"Plumbing Repair\", \"amount\": 220}, {\"account\": \"Appliance Repair\", \"amount\": 180}, {\"account\": \"General Maintenance\", \"amount\": 150}], \"subtotal\": 550}], \"total_cash_expenses\": 8650}, \"cash_flow\": {\"group\": \"CASH FLOW\", \"total_rental_income\": 16650, \"less_total_expenses\": -8650, \"cash_profit_before_depreciation\": 8000}}"
    },
    {
      "file_name": "Sample 06 - Meals & Entertainment Receipt Bundle.json",
      "content": "{\"document_type\": \"Meals & Entertainment Receipt Bundle\", \"tax_year\": 2024, \"taxpayer\": {\"business_name\": \"Creature Comforts Pet Supply\", \"owner\": \"Marcus Rivera\"}, \"receipts\": [{\"receipt_id\": 1, \"vendor\": \"Starbucks\", \"date\": \"2024-02-15\", \"amount\": 24.5, \"description\": \"Coffee meeting with local pet shelter director regarding adoption event sponsorship.\"}, {\"receipt_id\": 2, \"vendor\": \"Panera Bread\", \"date\": \"2024-03-08\", \"amount\": 38.75, \"description\": \"Lunch meeting with dog food supplier representative.\"}, {\"receipt_id\": 3, \"vendor\": \"Pet Industry Leadership Conference\", \"date\": \"2024-05-12\", \"amount\": 112.0, \"description\": \"Conference dinner during National Pet Retail Conference.\"}, {\"receipt_id\": 4, \"vendor\": \"Maggiano's Little Italy\", \"date\": \"2024-05-13\", \"amount\": 168.5, \"description\": \"Dinner with conference vendors discussing new product lines.\"}, {\"receipt_id\": 5, \"vendor\": \"Airport Bistro\", \"date\": \"2024-05-14\", \"amount\": 72.25, \"description\": \"Travel meal while returning from conference.\"}, {\"receipt_id\": 6, \"vendor\": \"Subway\", \"date\": \"2024-11-18\", \"amount\": 31.4, \"description\": \"Store employees worked late preparing Black Friday inventory.\"}, {\"receipt_id\": 7, \"vendor\": \"Round Table Pizza\", \"date\": \"2024-11-22\", \"amount\": 56.3, \"description\": \"Pizza provided to staff during inventory count.\"}, {\"receipt_id\": \"7b\", \"vendor\": \"Various (small receipts)\", \"date\": \"2024-11\", \"amount\": 62.3, \"description\": \"Additional small staff meal receipts during inventory period.\"}, {\"receipt_id\": 8, \"vendor\": \"Costco Wholesale\", \"date\": \"2024-12-20\", \"amount\": 248.65, \"description\": \"Food and beverages purchased for annual employee holiday party.\"}, {\"receipt_id\": 9, \"vendor\": \"Party City\", \"date\": \"2024-12-20\", \"amount\": 151.35, \"description\": \"Holiday party decorations and supplies.\"}, {\"receipt_id\": 10, \"vendor\": \"Sacramento River Cats\", \"date\": \"2024-01-15\", \"amount\": 350.0, \"description\": \"Season ticket package (First Half Season).\"}, {\"receipt_id\": 11, \"vendor\": \"Sacramento River Cats\", \"date\": \"2024-07-01\", \"amount\": 350.0, \"description\": \"Season ticket package (Second Half Season).\"}]}"
    },
    {
      "file_name": "Sample 07 - Las Vegas Conference Receipt Package.json",
      "content": "{\"document_type\": \"Business Travel Receipt Package\", \"tax_year\": 2024, \"taxpayer\": {\"name\": \"Marcus Rivera\", \"business_name\": \"Creature Comforts Pet Supply\"}, \"trip\": {\"destination\": \"Las Vegas, Nevada\", \"purpose\": \"National Pet Retail Conference 2024\", \"itinerary\": [{\"date\": \"2024-05-12\", \"activity\": \"Travel to Las Vegas\"}, {\"date\": \"2024-05-13\", \"activity\": \"Conference Day 1\"}, {\"date\": \"2024-05-14\", \"activity\": \"Conference Day 2\"}, {\"date\": \"2024-05-15\", \"activity\": \"Personal Sightseeing\"}, {\"date\": \"2024-05-16\", \"activity\": \"Personal Sightseeing\"}, {\"date\": \"2024-05-17\", \"activity\": \"Personal Sightseeing / Return Flight\"}], \"total_days\": 6, \"business_days\": 2, \"personal_days\": 3, \"conference_sessions\": {\"day_1_2024-05-13\": [\"Retail Inventory Management\", \"Pet Nutrition Trends\", \"Vendor Expo\"], \"day_2_2024-05-14\": [\"AI in Pet Retail Operations\", \"Customer Loyalty Programs\", \"Emerging Product Trends\"]}}, \"receipts\": [{\"receipt_id\": 1, \"category\": \"Conference Registration\", \"vendor\": \"National Pet Retail Association\", \"receipt_number\": \"NPRA-2024-11872\", \"date\": \"2024-04-15\", \"amount\": 795.0, \"description\": \"2024 National Pet Retail Conference Registration\"}, {\"receipt_id\": 2, \"category\": \"Airfare\", \"vendor\": \"Southwest Airlines\", \"confirmation\": \"SWA-8L4M92\", \"date\": \"2024-05-12\", \"amount\": 500.0, \"route\": \"Sacramento → Las Vegas → Sacramento\", \"description\": \"Round-trip airfare for conference travel\"}, {\"receipt_id\": 3, \"category\": \"Hotel\", \"vendor\": \"MGM Grand Hotel\", \"reservation\": \"MGM-553821\", \"check_in\": \"2024-05-12\", \"check_out\": \"2024-05-17\", \"nights\": 5, \"rate_per_night\": 200.0, \"amount\": 1000.0, \"description\": \"Hotel stay spanning conference and personal days\"}, {\"receipt_id\": 4, \"category\": \"Transportation\", \"vendor\": \"Uber\", \"date\": \"2024-05-12\", \"amount\": 28.5, \"description\": \"Airport to MGM Grand\"}, {\"receipt_id\": 5, \"category\": \"Transportation\", \"vendor\": \"Uber\", \"date\": \"2024-05-13\", \"amount\": 16.75, \"description\": \"Hotel to Convention Center\"}, {\"receipt_id\": 6, \"category\": \"Transportation\", \"vendor\": \"Uber\", \"date\": \"2024-05-14\", \"amount\": 17.25, \"description\": \"Convention Center to Hotel\"}, {\"receipt_id\": 7, \"category\": \"Transportation\", \"vendor\": \"Uber\", \"date\": \"2024-05-15\", \"amount\": 31.6, \"description\": \"Hotel to Bellagio Fountains\"}, {\"receipt_id\": 8, \"category\": \"Transportation\", \"vendor\": \"Uber\", \"date\": \"2024-05-16\", \"amount\": 36.9, \"description\": \"Hotel to Hoover Dam Tour\"}, {\"receipt_id\": 9, \"category\": \"Conference Materials\", \"vendor\": \"National Pet Retail Association\", \"amount\": 85.0, \"description\": \"Workshop Materials and Industry Reports\"}, {\"receipt_id\": 10, \"category\": \"Networking Event\", \"vendor\": \"NPRA Networking Reception\", \"amount\": 125.0, \"description\": \"Industry networking event admission\"}, {\"receipt_id\": 11, \"category\": \"Personal Entertainment\", \"vendor\": \"SkyView Helicopters\", \"date\": \"2024-05-16\", \"amount\": 389.0, \"description\": \"Grand Canyon Helicopter Tour (tourist activity during personal days)\"}, {\"receipt_id\": 12, \"category\": \"Personal Entertainment\", \"vendor\": \"Ticketmaster\", \"amount\": 225.0, \"description\": \"Cirque du Soleil show tickets\"}]}"
    },
    {
      "file_name": "Sample 08 - Prior Year 1040 Summary.json",
      "content": "{\"document_type\": \"Prior Year Tax Return Summary\", \"tax_year\": 2023, \"form_type\": \"Form 1040 Summary\", \"filing_info\": {\"filing_status\": \"Married Filing Jointly\", \"address\": \"2785 River Oak Drive, Sacramento, CA 95833\"}, \"dependents\": [{\"name\": \"Sophia Rivera\", \"age\": 8}, {\"name\": \"Ethan Rivera\", \"age\": 5}], \"income\": {\"w2_income\": {\"line_items\": [{\"taxpayer\": \"Marcus Rivera\", \"employer\": \"Creature Comforts Pet Supply\", \"wages\": 44000}, {\"taxpayer\": \"Elena Rivera\", \"employer\": \"City of Sacramento Fire Department\", \"wages\": 52000}], \"total_w2_income\": 96000}, \"schedule_c\": {\"business\": \"Creature Comforts Pet Supply\", \"gross_receipts\": 182500, \"cost_of_goods_sold\": -63200, \"expenses\": -72800, \"net_profit\": 46500}, \"schedule_e\": {\"property_address\": \"5200 Green Valley Drive, Unit 208, Sacramento, CA 95841\", \"rental_income\": 15600, \"mortgage_interest\": -4900, \"property_taxes\": -2350, \"insurance\": -900, \"repairs_and_maintenance\": -450, \"depreciation_claimed\": false, \"net_rental_income_reported\": 7000, \"form_4562_attached\": false, \"depreciation_schedule_attached\": false}, \"interest_and_dividends\": {\"line_items\": [{\"source\": \"Chase Savings Interest\", \"amount\": 120}, {\"source\": \"Vanguard Dividend Income\", \"amount\": 350}], \"total\": 470}, \"schedule_d\": {\"capital_gains_and_losses\": [{\"description\": \"Stock Gains\", \"amount\": 1200}, {\"description\": \"Stock Losses\", \"amount\": -5190}], \"net_capital_loss\": -3990, \"allowed_deduction_in_2023\": -3000, \"capital_loss_carryforward_to_2024\": -990}}, \"adjustments_to_income\": {\"self_employment_tax_deduction\": -3285, \"traditional_ira_contribution\": -6500, \"total_adjustments\": -9785}, \"adjusted_gross_income\": {\"total_income\": 149970, \"adjustments\": -9785, \"agi\": 140185}, \"deductions\": {\"itemized_deductions_schedule_a\": {\"mortgage_interest\": 9950, \"property_taxes\": 2550, \"charitable_contributions\": 4800, \"total_itemized\": 17300}, \"standard_deduction_mfj_2023\": 27700, \"deduction_elected\": \"Standard Deduction\"}, \"credits\": {\"child_tax_credit\": 4000}, \"tax_payments\": {\"federal_withholding\": 8650, \"estimated_tax_payments\": 1000, \"total_payments\": 9650}, \"tax_summary\": {\"total_tax\": 8420, \"total_payments\": 9650, \"federal_refund\": 1230}}"
    },
    {
      "file_name": "Sample 09 - Church Donation Receipt.json",
      "content": "{\"document_type\": \"Charitable Donation Receipt\", \"tax_year\": 2024, \"organization\": \"First Baptist Church of Sacramento\", \"donor\": \"Marcus & Elena Rivera\", \"contribution_type\": \"cash\", \"amount\": 5400.0}"
    },
    {
      "file_name": "Sample 10 - Political Contribution Receipt.json",
      "content": "{\"document_type\": \"Political Campaign Contribution Receipt\", \"tax_year\": 2024, \"organization\": \"Committee to Elect John Doe\", \"donor\": \"Elena Rivera\", \"amount\": 250.0}"
    }
  ]
}

# ─── 單一文件 Adapter 提取輔助函數 (執行緒並發) ───────────────────────────
def extract_single_w2(doc: dict, api_key: str, model_name: str) -> tuple:
    t0 = time.time()
    fname = doc.get("file_name", "Unknown")
    content = doc.get("content", "")
    try:
        res = W2Adapter.extract(
            filename=fname,
            content=content,
            model_name=model_name,
            api_key=api_key,
        )
        latency = time.time() - t0
        return fname, res, latency, None
    except Exception as e:
        latency = time.time() - t0
        return (
            fname,
            {
                "source_filename": fname,
                "facts": [],
                "document_needs_review": True,
                "debug_info": {
                    "system_prompt": "N/A",
                    "user_prompt": "N/A",
                    "raw_output": f"錯誤: {e}",
                },
            },
            latency,
            str(e),
        )


# ─── 側邊欄 ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 執行參數設定")

    selected_model = st.selectbox(
        "選擇分析模型",
        options=["gemini-2.5-pro", "gemini-2.5-flash"],
        index=0,
    )

    app_mode = st.radio("界面模式", ["Normal", "Debug"], index=1)
    is_debug = app_mode == "Debug"

    st.divider()
    st.markdown(
        """
        **📐 架構說明**

        ```
        W-2 文件
           ↓  W2Adapter (LLM)
        W2Facts
           ↓  Form1040WagesMapper (LLM)
        Mapped Items
           ↓  aggregate_form_1040_line_1a()
        Line 1a 總額
        ```

        - **W2Adapter**：提取原子事實
        - **Mapper**：映射至 Line 1a
        - **Aggregator**：Rule-based 加總
        """
    )

# ─── 主畫面標題 ──────────────────────────────────────────────────────────
st.title("📋 Form 1040 Line 1a — W-2 Adapter & Mapper 測試")
st.markdown(
    "此頁面測試 **User Story 5.1 — Map Wages to Form 1040**：\n"
    "從 W-2 文件提取 Box 1 wages，映射至 Form 1040 Line 1a，並以 Rule-based 加總。"
)

# ─── Session State 初始化 ─────────────────────────────────────────────────
if "form_1040_input_json" not in st.session_state:
    st.session_state.form_1040_input_json = ""

if "form_1040_result" not in st.session_state:
    st.session_state.form_1040_result = None

# ─── 載入測試資料按鈕 ─────────────────────────────────────────────────────
col_btn, _ = st.columns([2, 5])
with col_btn:
    if st.button("📥 載入 Rivera 夫婦 W-2 測試資料", use_container_width=True):
        val_str = json.dumps(
            DEFAULT_W2_INPUT, indent=2, ensure_ascii=False
        )
        st.session_state.form_1040_input_json = val_str
        st.session_state.form_1040_text_area = val_str
        st.rerun()

# ─── 輸入區 ───────────────────────────────────────────────────────────────
prompt_input = st.text_area(
    "請輸入 W-2 文件清單 JSON：",
    value=st.session_state.form_1040_input_json,
    height=260,
    placeholder="點擊上方按鈕載入 Rivera 夫婦測試資料，或自行貼入 W-2 JSON...",
    key="form_1040_text_area",
)
st.session_state.form_1040_input_json = prompt_input

# ─── 執行按鈕 ────────────────────────────────────────────────────────────
run_btn = st.button(
    "🚀 開始提取 → 映射 → 加總",
    type="primary",
    use_container_width=True,
    key="run_form_1040",
)

if run_btn:
    if not prompt_input.strip():
        st.error("輸入內容不可為空！")
    else:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            st.error("環境變數 GEMINI_API_KEY 未設定，無法呼叫 Gemini API。")
        else:
            t_start = time.time()
            try:
                parsed_data = json.loads(prompt_input)
                taxpayer_profile = parsed_data.get("taxpayer_profile") or {}
                tax_year = int(taxpayer_profile.get("Tax Year") or parsed_data.get("tax_year") or 2024)
                w2_docs = parsed_data.get("uploaded_documents") or parsed_data.get("w2_documents") or []

                total_docs = len(w2_docs)
                if total_docs == 0:
                    st.error("未找到任何 W-2 文件 (w2_documents)！")
                else:
                    # ── Step 1: 並發呼叫 W2Adapter ────────────────────────
                    progress_container = st.container()
                    with progress_container:
                        st.markdown(
                            '<span class="step-badge">Step 1</span> W2Adapter — 並發提取 W-2 原子事實',
                            unsafe_allow_html=True,
                        )
                        progress_bar = st.progress(0.0)
                        status_text = st.empty()

                    adapter_results: dict = {}
                    completed_count = 0

                    with concurrent.futures.ThreadPoolExecutor(
                        max_workers=max(1, min(total_docs, 8))
                    ) as executor:
                        futures = {
                            executor.submit(
                                extract_single_w2, doc, api_key, selected_model
                            ): doc
                            for doc in w2_docs
                        }
                        for future in concurrent.futures.as_completed(futures):
                            fname, a_res, latency, err = future.result()
                            adapter_results[fname] = a_res
                            completed_count += 1
                            progress_bar.progress(completed_count / total_docs)
                            status_text.text(
                                f"已完成 {completed_count}/{total_docs}：{fname}（{latency:.2f}s）"
                            )

                    # ── Step 2: 呼叫 Form1040WagesMapper ──────────────────
                    status_text.text("W2Adapter 提取完成，正在呼叫 Form1040WagesMapper...")
                    st.markdown(
                        '<span class="step-badge">Step 2</span> Form1040WagesMapper — 映射至 Line 1a',
                        unsafe_allow_html=True,
                    )

                    # 組裝 mapper_input（去除 debug_info）
                    w2_docs_for_mapper = []
                    for doc in w2_docs:
                        fname = doc.get("file_name", "")
                        a_res = adapter_results.get(fname, {})
                        w2_docs_for_mapper.append(
                            {
                                "source_filename": a_res.get("source_filename", fname),
                                "facts": a_res.get("facts") or [],
                                "document_needs_review": a_res.get(
                                    "document_needs_review", False
                                ),
                            }
                        )

                    mapper = Form1040WagesMapper(tax_year=tax_year)
                    mapper_input_payload = {
                        "tax_year": tax_year,
                        "w2_documents": w2_docs_for_mapper,
                        "other_fact_categories": {},
                    }
                    mapper_result = mapper.map(
                        mapper_input=mapper_input_payload,
                        model_name=selected_model,
                        api_key=api_key,
                    )

                    # ── Step 3: aggregate_form_1040_line_1a() ──────────────
                    st.markdown(
                        '<span class="step-badge">Step 3</span> aggregate_form_1040_line_1a() — Rule-based 加總',
                        unsafe_allow_html=True,
                    )
                    mapped_items = mapper_result.get("items") or []
                    line_1a_result = aggregate_form_1040_line_1a(mapped_items)

                    total_latency = time.time() - t_start

                    # 儲存結果
                    st.session_state.form_1040_result = {
                        "tax_year": tax_year,
                        "adapter_results": adapter_results,
                        "mapper_result": mapper_result,
                        "line_1a_result": line_1a_result,
                        "latency": total_latency,
                    }
                    st.success(
                        f"✅ 完成！三階段流程執行完畢，總耗時 {total_latency:.2f} 秒。"
                    )
                    st.rerun()

            except json.JSONDecodeError as je:
                st.error(f"輸入的 JSON 格式錯誤：{je}")
            except Exception as e:
                st.error(f"處理過程中發生錯誤：{e}")


# ─── 顯示結果 ─────────────────────────────────────────────────────────────
if st.session_state.form_1040_result:
    res = st.session_state.form_1040_result
    adapter_results = res["adapter_results"]
    mapper_result = res["mapper_result"]
    line_1a_result = res["line_1a_result"]
    latency = res["latency"]
    tax_year = res["tax_year"]

    st.divider()
    st.subheader("📊 執行結果報告")
    st.metric("總執行耗時", f"{latency:.2f} 秒")

    # ─── Form 1040 Line 1a 最終結果卡片 ───────────────────────────────
    st.markdown("### 🧾 Form 1040 Line 1a — 最終結果")

    total_val = line_1a_result.get("total_value", 0.0)
    calc_status = line_1a_result.get("calculation_status", "")
    needs_review = line_1a_result.get("needs_review", False)
    review_reasons = line_1a_result.get("review_reasons") or []
    source_items = line_1a_result.get("source_items") or []
    excluded_items = line_1a_result.get("excluded_review_items") or []

    # 計算狀態徽章
    if calc_status == "completed":
        status_badge = '<span style="background:#10b981;color:white;padding:2px 10px;border-radius:5px;font-size:0.85rem;font-weight:700;">✅ completed</span>'
    else:
        status_badge = '<span style="background:#f59e0b;color:white;padding:2px 10px;border-radius:5px;font-size:0.85rem;font-weight:700;">⚠️ completed_with_review</span>'

    # 組合 taxpayer chips
    taxpayer_chips = "".join(
        [
            f'<span class="taxpayer-chip">{item.get("taxpayer_name") or "Unknown"}: ${item.get("value", 0.0):,.2f}</span>'
            for item in source_items
        ]
    )

    st.markdown(
        f"""
        <div class="line-1a-card">
            <div style="margin-bottom:10px; color:#94a3b8; font-size:0.9rem; font-weight:600;">
                Form 1040 ({tax_year}) &nbsp;›&nbsp; <span style="color:#a5b4fc;">Line 1a — Wages, salaries, tips, etc.</span>
                &nbsp;&nbsp;{status_badge}
            </div>
            <div class="total-badge">${total_val:,.2f}</div>
            <div style="margin-top:14px;">{taxpayer_chips}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if needs_review and review_reasons:
        st.markdown(
            f"""
            <div class="review-warning-box">
                <b>⚠️ 部分項目需要人工 Review</b><br>
                原因：{", ".join(review_reasons)}
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ─── 映射明細表格 ──────────────────────────────────────────────────
    st.markdown("#### 📋 Line 1a 映射明細 (source_items)")

    if not source_items:
        st.warning("沒有通過自動採用的映射項目。")
    else:
        html_rows = []
        for item in source_items:
            tname = item.get("taxpayer_name") or "—"
            val = item.get("value", 0.0)
            fname = item.get("source_filename") or "—"
            html_rows.append(
                f"<tr>"
                f'<td style="font-weight:bold; color:#93c5fd;">{tname}</td>'
                f'<td style="font-family:monospace; color:#a5b4fc;">form_1040 → line_1a</td>'
                f'<td style="font-weight:bold; color:#a3e635; text-align:right;">${val:,.2f}</td>'
                f'<td style="color:#94a3b8; font-size:0.85rem;">{fname}</td>'
                f"</tr>"
            )

        table_html = (
            '<table class="field-table">'
            "<thead><tr>"
            "<th>納稅人 (taxpayer_name)</th>"
            "<th>映射目標 (target)</th>"
            '<th style="text-align:right;">金額 (value)</th>'
            "<th>來源文件 (source_filename)</th>"
            "</tr></thead>"
            f"<tbody>{''.join(html_rows)}</tbody>"
            "</table>"
        )
        st.markdown(table_html, unsafe_allow_html=True)

    # ─── 排除項目 ──────────────────────────────────────────────────────
    if excluded_items:
        st.markdown("#### ⚠️ 排除項目 (excluded_review_items)")
        with st.expander("查看需要 Review 的排除項目", expanded=True):
            for item in excluded_items:
                st.json(item)

    # ─── 未映射項目 ────────────────────────────────────────────────────
    unmapped_items = mapper_result.get("unmapped_items") or []
    st.markdown("#### 🚫 未映射項目 (unmapped_items)")
    if not unmapped_items:
        st.info("沒有未映射的項目。")
    else:
        html_rows_unmapped = []
        for item in unmapped_items:
            val = item.get("value", 0.0)
            fname = item.get("source_filename") or "—"
            ftype = item.get("source_fact_type") or "—"
            status = "⚠️ 需要審查" if item.get("needs_review") else "✅ 正常排除"
            reason = item.get("review_reason") or "—"
            rev_badge = "🔴" if item.get("needs_review") else "🟢"
            html_rows_unmapped.append(
                f"<tr>"
                f'<td>{rev_badge}</td>'
                f'<td style="font-weight:bold; color:#f87171; text-align:right;">${val:,.2f}</td>'
                f'<td style="font-family:monospace; font-size:0.85rem; color:#93c5fd;">{ftype}</td>'
                f'<td style="color:#fb7185;">{status}</td>'
                f'<td style="color:#cbd5e1; font-size:0.85rem;">{reason}</td>'
                f'<td style="color:#94a3b8; font-size:0.85rem;">{fname}</td>'
                f"</tr>"
            )

        table_html_unmapped = (
            '<table class="field-table">'
            "<thead><tr>"
            '<th style="width:50px;">審查</th>'
            '<th style="text-align:right;">金額 (value)</th>'
            "<th>事實型態 (fact_type)</th>"
            "<th>審查狀態</th>"
            "<th>未映射原因</th>"
            "<th>來源文件 (source_filename)</th>"
            "</tr></thead>"
            f"<tbody>{''.join(html_rows_unmapped)}</tbody>"
            "</table>"
        )
        st.markdown(table_html_unmapped, unsafe_allow_html=True)


    # ─── Acceptance Criteria 驗證 ──────────────────────────────────────
    st.markdown("#### ✅ Acceptance Criteria 驗證")

    ac_rows = []

    # AC1: Marcus wages 出現在 Line 1a
    marcus_item = next(
        (i for i in source_items if "marcus" in str(i.get("taxpayer_name") or "").lower()),
        None,
    )
    ac1_pass = marcus_item is not None
    ac_rows.append(
        (
            "Marcus wages → Form 1040 Line 1a",
            f"✅ ${marcus_item['value']:,.2f}" if ac1_pass else "❌ 未找到",
            ac1_pass,
        )
    )

    # AC2: Elena wages 出現在 Line 1a
    elena_item = next(
        (i for i in source_items if "elena" in str(i.get("taxpayer_name") or "").lower()),
        None,
    )
    ac2_pass = elena_item is not None
    ac_rows.append(
        (
            "Elena wages → Form 1040 Line 1a",
            f"✅ ${elena_item['value']:,.2f}" if ac2_pass else "❌ 未找到",
            ac2_pass,
        )
    )

    # AC3: 系統加總所有映射至 Line 1a 的 wages
    ac3_pass = calc_status in ("completed", "completed_with_review")
    ac_rows.append(("系統自動加總 Line 1a wages", "✅ aggregate_form_1040_line_1a() 執行完成" if ac3_pass else "❌ 未執行", ac3_pass))

    # AC4: Line 1a 總額 = $100,000
    ac4_pass = abs(total_val - 100000.0) < 0.01
    ac_rows.append(
        (
            "Rivera 測試案例 Line 1a 總額 = $100,000",
            f"✅ ${total_val:,.2f}" if ac4_pass else f"❌ 實際值 ${total_val:,.2f}",
            ac4_pass,
        )
    )

    ac_html_rows = []
    for criterion, result_str, passed in ac_rows:
        icon = "✅" if passed else "❌"
        row_color = "rgba(16,185,129,0.08)" if passed else "rgba(239,68,68,0.08)"
        ac_html_rows.append(
            f'<tr style="background:{row_color};">'
            f'<td style="font-size:1.1rem; text-align:center;">{icon}</td>'
            f"<td>{criterion}</td>"
            f'<td style="font-weight:bold; color:#a3e635;">{result_str}</td>'
            f"</tr>"
        )

    ac_table = (
        '<table class="field-table">'
        "<thead><tr>"
        '<th style="text-align:center; width:50px;">狀態</th>'
        "<th>Acceptance Criteria</th>"
        "<th>驗證結果</th>"
        "</tr></thead>"
        f"<tbody>{''.join(ac_html_rows)}</tbody>"
        "</table>"
    )
    st.markdown(ac_table, unsafe_allow_html=True)

    # ─── Debug 偵錯控制台 ──────────────────────────────────────────────
    if is_debug:
        st.divider()
        st.markdown("### 🔍 Debug 偵錯控制台")

        tab_adapter, tab_mapper, tab_aggregator = st.tabs(
            [
                "1. W2Adapter 偵錯",
                "2. Form1040WagesMapper 偵錯",
                "3. Aggregator 結果 JSON",
            ]
        )

        # Tab 1 — W2Adapter
        with tab_adapter:
            st.markdown("#### 📂 各 W-2 文件 Facts 提取日誌")
            for fname, a_res in adapter_results.items():
                needs_rev = a_res.get("document_needs_review", False)
                badge = "🟡" if needs_rev else "🟢"
                with st.expander(f"{badge} {fname}", expanded=not needs_rev):
                    st.json(
                        {
                            "source_filename": a_res.get("source_filename"),
                            "document_needs_review": a_res.get("document_needs_review"),
                            "facts": a_res.get("facts"),
                        }
                    )
                    st.divider()
                    a_debug = a_res.get("debug_info") or {}
                    col_l, col_r = st.columns(2)
                    with col_l:
                        st.markdown(f"**📡 System Prompt**")
                        st.text_area(
                            "System Prompt",
                            a_debug.get("system_prompt", "N/A"),
                            height=220,
                            key=f"w2_sys_{fname}",
                        )
                    with col_r:
                        st.markdown(f"**📥 LLM 原始回應**")
                        st.text_area(
                            "Raw Output",
                            a_debug.get("raw_output", "N/A"),
                            height=220,
                            key=f"w2_raw_{fname}",
                        )

        # Tab 2 — Mapper
        with tab_mapper:
            st.markdown("#### 📋 Form1040WagesMapper 映射結果 JSON")
            st.json(mapper_result.get("items") or [])
            st.divider()
            m_debug = mapper_result.get("debug_info") or {}
            col_ml, col_mr = st.columns(2)
            with col_ml:
                st.markdown("**📡 Mapper System Prompt**")
                st.text_area(
                    "Mapper System Prompt",
                    m_debug.get("system_prompt", "N/A"),
                    height=250,
                    key="m1040_sys_prompt",
                )
                st.markdown("**📨 Mapper User Prompt**")
                st.text_area(
                    "Mapper User Prompt",
                    m_debug.get("user_prompt", "N/A"),
                    height=150,
                    key="m1040_user_prompt",
                )
            with col_mr:
                st.markdown("**📥 Mapper LLM 原始回應**")
                st.text_area(
                    "Mapper LLM Raw Output",
                    m_debug.get("raw_output", "N/A"),
                    height=430,
                    key="m1040_raw_output",
                )

        # Tab 3 — Aggregator
        with tab_aggregator:
            st.markdown("#### 🧮 aggregate_form_1040_line_1a() 完整 JSON 輸出")
            st.json(line_1a_result)
