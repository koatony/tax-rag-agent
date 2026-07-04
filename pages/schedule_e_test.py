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
    page_title="Schedule E — Rental Income and Expense Adapter & Mapper 測試",
    layout="wide",
)

# ─── 自訂 CSS ─────────────────────────────────────────────────────────────
schedule_a_ui_helper.inject_custom_css()

# 額外補充本頁面專用樣式
st.markdown(
    """
    <style>
    .schedule-e-card {
        background: linear-gradient(135deg, rgba(59,130,246,0.15) 0%, rgba(16,185,129,0.10) 100%);
        border: 1px solid rgba(59,130,246,0.35);
        border-radius: 14px;
        padding: 22px 28px;
        margin-bottom: 18px;
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
from adapter import RentalIncomeAndExpenseAdapter
from mapper import ScheduleEMapper

# ─── 預設 Rivera 出租收支測試資料 ─────────────────────────────────────────
DEFAULT_RENTAL_INPUT = {
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
      "content": "{\"document_type\": \"W-2 Wage and Tax Statement\", \"tax_year\": 2024, \"form_type\": \"W-2\", \"employee\": {\"name\": \"Elena Rivera\", \"ssn\": \"555-23-4567\", \"address\": \"2785 River Oak Drive, Sacramento, CA 95833\"}, \"employer\": {\"name\": \"City of Sacramento Fire Department\", \"ein\": \"94-6000414\", \"address\": \"5770 Freeport Blvd, Sacramento, CA 95822\"}, \"boxes\": {\"box_1_wages_tips_other_compensation\": 54000.0, \"box_2_federal_income_tax_withheld\": 5200.0, \"box_3_social_security_wages\": 54000.0, \"box_4_social_security_tax_withheld\": 3348.0, \"box_5_medicare_wages_and_tips\": 54000.0, \"box_6_medicare_tax_withheld\": 783.0, \"box_7_social_security_tips\": 0.0, \"box_8_allocated_tips\": 0.0, \"box_10_dependent_care_benefits\": 0.0, \"box_11_nonqualified_plans\": 0.0, \"box_12a_code\": \"DD\", \"box_12a_amount_employer_health_coverage\": 14800.0, \"box_12b_code\": \"D\", \"box_12b_amount_457_401k_contribution\": 3000.0, \"box_13_retirement_plan\": true, \"box_13_statutory_employee\": false, \"box_13_third_party_sick_pay\": false, \"box_14_other_union_dues\": 720.0, \"box_15_state\": \"CA\", \"box_16_state_wages\": 54000.0, \"box_17_state_income_tax_withheld\": 2150.0, \"box_18_local_wages\": null, \"box_19_local_income_tax\": null, \"box_20_locality_name\": null}}"
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
def extract_single_doc(doc: dict, api_key: str, model_name: str) -> tuple:
    t0 = time.time()
    fname = doc.get("file_name", "Unknown")
    content = doc.get("content", "")
    try:
        res = RentalIncomeAndExpenseAdapter.extract(
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
        出租文件 (租金明細 / Form 1098 / 支出表)
           ↓  RentalIncomeAndExpenseAdapter (LLM)
        Rental Facts
           ↓  ScheduleEMapper (LLM)
        Mapped Items
        ```

        - **RentalIncomeAndExpenseAdapter**：提取租金與出租物業相關費用事实
        - **ScheduleEMapper**：映射至 Schedule E Part I 欄位行號 (Line 3, 7, 9, 12, 16, 19 等)
        """
    )

# ─── 主畫面標題 ──────────────────────────────────────────────────────────
st.title("📋 Schedule E — Rental Income and Expense Adapter & Mapper 測試")
st.markdown(
    "此頁面測試 **User Story 5.4 — Map Rental Income and Expenses to Schedule E**：\n"
    "從出租不動產文件中提取事實並映射至 Schedule E Part I 行號（Line 3, Line 9, Line 12, Line 14, Line 16 等）。"
)

# ─── Session State 初始化 ─────────────────────────────────────────────────
if "schedule_e_input_json" not in st.session_state:
    st.session_state.schedule_e_input_json = ""

if "schedule_e_result" not in st.session_state:
    st.session_state.schedule_e_result = None

# ─── 載入測試資料按鈕 ─────────────────────────────────────────────────────
col_btn, _ = st.columns([2, 5])
with col_btn:
    if st.button("📥 載入 Rivera 夫婦出租房產測試資料", use_container_width=True, key="load_rivera_rental_btn"):
        val_str = json.dumps(
            DEFAULT_RENTAL_INPUT, indent=2, ensure_ascii=False
        )
        st.session_state.schedule_e_input_json = val_str
        st.session_state.schedule_e_text_area = val_str
        st.rerun()

# ─── 輸入區 ───────────────────────────────────────────────────────────────
prompt_input = st.text_area(
    "請輸入出租文件清單 JSON：",
    value=st.session_state.schedule_e_input_json,
    height=260,
    placeholder="點擊上方按鈕載入 Rivera 出租測試資料，或自行貼入 JSON...",
    key="schedule_e_text_area",
)
st.session_state.schedule_e_input_json = prompt_input

# ─── 執行按鈕 ────────────────────────────────────────────────────────────
run_btn = st.button(
    "🚀 開始提取 → 映射",
    type="primary",
    use_container_width=True,
    key="run_schedule_e_btn",
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
                docs = parsed_data.get("uploaded_documents") or parsed_data.get("documents") or []

                total_docs = len(docs)
                if total_docs == 0:
                    st.error("未找到任何出租文件 (documents)！")
                else:
                    # ── Step 1: 並發呼叫 RentalIncomeAndExpenseAdapter ────
                    progress_container = st.container()
                    with progress_container:
                        st.markdown(
                            '<span class="step-badge">Step 1</span> RentalIncomeAndExpenseAdapter — 並發提取原子事實',
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
                                extract_single_doc, doc, api_key, selected_model
                            ): doc
                            for doc in docs
                        }
                        for future in concurrent.futures.as_completed(futures):
                            fname, a_res, latency, err = future.result()
                            adapter_results[fname] = a_res
                            completed_count += 1
                            progress_bar.progress(completed_count / total_docs)
                            status_text.text(
                                f"已完成 {completed_count}/{total_docs}：{fname}（{latency:.2f}s）"
                            )

                    # ── Step 2: 呼叫 ScheduleEMapper ──────────────────────
                    status_text.text("Adapter 提取完成，正在呼叫 ScheduleEMapper...")
                    st.markdown(
                        '<span class="step-badge">Step 2</span> ScheduleEMapper — 映射至 Schedule E 行號',
                        unsafe_allow_html=True,
                    )

                    # 組裝 mapper_input（去除 debug_info）
                    docs_for_mapper = []
                    for doc in docs:
                        fname = doc.get("file_name", "")
                        a_res = adapter_results.get(fname, {})
                        docs_for_mapper.append(
                            {
                                "source_filename": a_res.get("source_filename", fname),
                                "facts": a_res.get("facts") or [],
                                "document_needs_review": a_res.get(
                                    "document_needs_review", False
                                ),
                            }
                        )

                    mapper = ScheduleEMapper()
                    mapper_input_payload = {
                        "documents": docs_for_mapper,
                    }
                    mapper_result = mapper.map(
                        mapper_input=mapper_input_payload,
                        model_name=selected_model,
                        api_key=api_key,
                    )

                    total_latency = time.time() - t_start

                    # 儲存結果
                    st.session_state.schedule_e_result = {
                        "adapter_results": adapter_results,
                        "mapper_result": mapper_result,
                        "latency": total_latency,
                    }
                    st.success(
                        f"✅ 完成！兩階段流程執行完畢，總耗時 {total_latency:.2f} 秒。"
                    )
                    st.rerun()

            except json.JSONDecodeError as je:
                st.error(f"輸入的 JSON 格式錯誤：{je}")
            except Exception as e:
                st.error(f"處理過程中發生錯誤：{e}")


# ─── 顯示結果 ─────────────────────────────────────────────────────────────
if st.session_state.schedule_e_result:
    res = st.session_state.schedule_e_result
    adapter_results = res["adapter_results"]
    mapper_result = res["mapper_result"]
    latency = res["latency"]

    st.divider()
    st.subheader("📊 執行結果報告")
    st.metric("總執行耗時", f"{latency:.2f} 秒")

    # ─── Form 1040 Schedule E 最終結果卡片 ──────────────────────────────
    st.markdown("### 🧾 Schedule E — 映射明細")

    source_items = mapper_result.get("items") or []

    st.markdown(
        f"""
        <div class="schedule-e-card">
            <div style="margin-bottom:10px; color:#94a3b8; font-size:0.9rem; font-weight:600;">
                IRS Schedule E &nbsp;›&nbsp; <span style="color:#a5b4fc;">Supplemental Income and Loss (Part I)</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ─── 映射明細表格 ──────────────────────────────────────────────────
    st.markdown("#### 📋 Schedule E 映射明細 (items)")

    if not source_items:
        st.warning("沒有成功映射的 Schedule E 項目。")
    else:
        html_rows = []
        for item in source_items:
            tline = item.get("target_line") or "—"
            val = item.get("value", 0.0)
            fname = item.get("source_filename") or "—"
            ftype = item.get("source_fact_type") or "—"
            rev_badge = "🔴" if item.get("needs_review") else "🟢"
            html_rows.append(
                f"<tr>"
                f"<td>{rev_badge}</td>"
                f'<td style="font-family:monospace; color:#a5b4fc;">{tline}</td>'
                f'<td style="font-weight:bold; color:#a3e635; text-align:right;">${val:,.2f}</td>'
                f'<td style="font-family:monospace; font-size:0.85rem; color:#93c5fd;">{ftype}</td>'
                f'<td style="color:#94a3b8; font-size:0.85rem;">{fname}</td>'
                f"</tr>"
            )

        table_html = (
            '<table class="field-table">'
            "<thead><tr>"
            '<th style="width:50px;">審查</th>'
            "<th>Schedule E 行號</th>"
            '<th style="text-align:right;">金額 (value)</th>'
            "<th>事實型態 (fact_type)</th>"
            "<th>來源文件 (source_filename)</th>"
            "</tr></thead>"
            f"<tbody>{''.join(html_rows)}</tbody>"
            "</table>"
        )
        st.markdown(table_html, unsafe_allow_html=True)



    # ─── Debug 偵錯控制台 ──────────────────────────────────────────────
    if is_debug:
        st.divider()
        st.markdown("### 🔍 Debug 偵錯控制台")

        tab_adapter, tab_mapper = st.tabs(
            [
                "1. RentalIncomeAndExpenseAdapter 偵錯",
                "2. ScheduleEMapper 偵錯",
            ]
        )

        # Tab 1 — Adapter
        with tab_adapter:
            st.markdown("#### 📂 各文件 Facts 提取日誌")
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
                            key=f"adapter_sys_{fname}",
                        )
                    with col_r:
                        st.markdown(f"**📥 LLM 原始回應**")
                        st.text_area(
                            "Raw Output",
                            a_debug.get("raw_output", "N/A"),
                            height=220,
                            key=f"adapter_raw_{fname}",
                        )

        # Tab 2 — Mapper
        with tab_mapper:
            st.markdown("#### 📋 ScheduleEMapper 映射結果 JSON")
            st.json(mapper_result)
            st.divider()
            m_debug = mapper_result.get("debug_info") or {}
            col_ml, col_mr = st.columns(2)
            with col_ml:
                st.markdown("**📡 Mapper System Prompt**")
                st.text_area(
                    "Mapper System Prompt",
                    m_debug.get("system_prompt", "N/A"),
                    height=250,
                    key="mapper_sys_prompt",
                )
                st.markdown("**📨 Mapper User Prompt**")
                st.text_area(
                    "Mapper User Prompt",
                    m_debug.get("user_prompt", "N/A"),
                    height=150,
                    key="mapper_user_prompt",
                )
            with col_mr:
                st.markdown("**📥 Mapper LLM 原始回應**")
                st.text_area(
                    "Mapper LLM Raw Output",
                    m_debug.get("raw_output", "N/A"),
                    height=430,
                    key="mapper_raw_output",
                )
