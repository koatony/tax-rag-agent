import streamlit as st
import json
import time
import re
import os
import sys
import concurrent.futures

# 將工作路徑加入系統中以正確載入專案模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 載入共享 UI 輔助模組
import schedule_a_ui_helper

# --- 安全性：密碼驗證狀態檢查 ---
schedule_a_ui_helper.verify_login()

# --- 頁面配置 ---
st.set_page_config(
    page_title="Schedule D Adapter & Mapper 測試與對齊",
    layout="wide"
)

# 載入自訂 CSS 樣式以符合 Premium 設計質感
schedule_a_ui_helper.inject_custom_css()

try:
    from adapter import PriorYearReturnAdapter
    from mapper import ScheduleDMapper
except ImportError:
    PriorYearReturnAdapter = None
    ScheduleDMapper = None

# --- 預設測試資料 (Marcus and Elena Rivera 完整實驗資料) ---
DEFAULT_RIVERA_DATA = {
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

# --- 單一檔案事實提取輔助函數 (執行緒並發執行) ---
def extract_single_document_facts(doc: dict, api_key: str, model_name: str) -> tuple:
    t0 = time.time()
    fname = doc.get("file_name", "Unknown File")
    content = doc.get("content", "")
    try:
        res = PriorYearReturnAdapter.extract(
            filename=fname,
            content=content,
            model_name=model_name,
            api_key=api_key
        )
        latency = time.time() - t0
        return fname, res, latency, None
    except Exception as e:
        latency = time.time() - t0
        return fname, {
            "source_filename": fname,
            "detected_tax_year": None,
            "extraction_status": "failed",
            "facts": [],
            "document_needs_review": True,
            "document_review_reasons": [str(e)],
            "debug_info": {
                "system_prompt": "N/A",
                "user_prompt": "N/A",
                "raw_output": f"錯誤: {e}"
            }
        }, latency, str(e)

# --- 側邊欄控制與模型選擇 ---
with st.sidebar:
    st.header("⚙️ 執行參數設定")
    
    selected_model = st.selectbox(
        "選擇分析模型",
        options=["gemini-2.5-pro", "gemini-2.5-flash"],
        index=0
    )
    
    app_mode = st.radio("界面模式", ["Normal", "Debug"], index=1)
    is_debug = (app_mode == "Debug")
    
    st.divider()
    st.info("💡 說明：\n1. 此頁面將對**所有上傳文件**逐一呼叫 `PriorYearReturnAdapter` 以判斷並提取前年度事實，排除了對 filename (Sample 08) 的 Hardcode 依賴。\n2. 合法提取出的 facts 會被彙整併傳給 `ScheduleDMapper` 映射至 Schedule D 當年度行號。")

# --- 主畫面標題 ---
st.title("📋 IRS Schedule D Carryover 提取與映射測試 (多檔並發)")
st.write("此測試頁面將遍歷所有上載檔案，調用 `PriorYearReturnAdapter` 判定並提取 facts，最後將所有提取事實彙整並交給 `ScheduleDMapper`。")

# 初始化 Session 狀態
if "rivera_input_json_d" not in st.session_state:
    st.session_state.rivera_input_json_d = ""

if "schedule_d_execution_result" not in st.session_state:
    st.session_state.schedule_d_execution_result = None

# --- 載入模擬資料控制按鈕 ---
col_actions, _ = st.columns([2, 5])
with col_actions:
    if st.button("📥 載入 Rivera 夫婦完整實驗資料", use_container_width=True):
        st.session_state.rivera_input_json_d = json.dumps(DEFAULT_RIVERA_DATA, indent=2, ensure_ascii=False)
        st.rerun()

# 顯示輸入框
prompt_input = st.text_area(
    "請輸入原始報稅資料 JSON：",
    value=st.session_state.rivera_input_json_d,
    height=280,
    placeholder="在此輸入或點擊上方按鈕載入模擬的 Rivera 夫婦實驗資料..."
)
st.session_state.rivera_input_json_d = prompt_input

# --- 執行按鈕 ---
run_btn = st.button("🚀 開始多檔並發提取與對齊映射", type="primary", use_container_width=True)

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
                # 1. 解析輸入的 JSON 資料
                parsed_data = json.loads(prompt_input)
                uploaded_docs = parsed_data.get("uploaded_documents") or []
                profile = parsed_data.get("taxpayer_profile") or {}
                target_tax_year = int(profile.get("Tax Year") or 2024)

                total_docs = len(uploaded_docs)
                if total_docs == 0:
                    st.error("未找到任何上傳文件 (uploaded_documents)！")
                else:
                    # 建立動態進度顯示器
                    progress_container = st.container()
                    with progress_container:
                        st.write("### ⏳ 多檔事實提取進度")
                        progress_bar = st.progress(0.0)
                        status_text = st.empty()
                        status_text.text("開始分配並發提取任務 ...")

                    # 2. 併發提取所有檔案
                    adapter_results = {}
                    all_prior_year_facts = []
                    completed_count = 0

                    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(total_docs, 8))) as executor:
                        futures = {
                            executor.submit(extract_single_document_facts, doc, api_key, selected_model): doc
                            for doc in uploaded_docs
                        }
                        
                        for future in concurrent.futures.as_completed(futures):
                            doc = futures[future]
                            fname, a_res, latency, err = future.result()
                            adapter_results[fname] = a_res
                            
                            # 收集成功（未 failed）提取的 facts，並注入 source_filename 欄位
                            if a_res["extraction_status"] != "failed":
                                for fact in a_res["facts"] or []:
                                    fact["source_filename"] = fname
                                all_prior_year_facts.extend(a_res["facts"])
                            
                            completed_count += 1
                            progress_bar.progress(completed_count / total_docs)
                            status_text.text(f"已完成 {completed_count} / {total_docs} 檔案 ({fname} | 耗時: {latency:.2f}s)...")

                    # 3. 呼叫 ScheduleDMapper
                    st.info(f"多檔 facts 提取與過濾完成 (成功 facts 數: {len(all_prior_year_facts)})，開始對齊行號...")
                    mapper = ScheduleDMapper(tax_year=target_tax_year)
                    mapper_input = {
                        "tax_year": target_tax_year,
                        "prior_year_facts": all_prior_year_facts,
                        "brokerage_facts": [],
                        "form_8949_facts": []
                    }
                    mapper_result = mapper.map(
                        mapper_input=mapper_input,
                        model_name=selected_model,
                        api_key=api_key
                    )

                    total_latency = time.time() - t_start

                    # 儲存結果
                    st.session_state.schedule_d_execution_result = {
                        "adapter_results": adapter_results,
                        "mapper_result": mapper_result,
                        "latency": total_latency
                    }
                    st.success(f"完成！多檔提取與對齊映射順利執行完畢，總共耗時 {total_latency:.2f} 秒！")
                    st.rerun()

            except json.JSONDecodeError as je:
                st.error(f"輸入的 JSON 格式錯誤：{je}")
            except Exception as e:
                st.error(f"處理過程中發生錯誤：{e}")

# --- 顯示結果分頁 ---
if st.session_state.schedule_d_execution_result:
    res = st.session_state.schedule_d_execution_result
    adapter_results = res["adapter_results"]
    mapper_result = res["mapper_result"]
    latency = res["latency"]

    st.divider()
    st.subheader("📊 執行結果分析報告")
    st.metric("總執行耗時", f"{latency:.2f} 秒")

    # 1. 預設介面：顯示最後 mapped 之後 Schedule D 欄位 (target_line) 的 kv
    st.markdown("### 📋 Schedule D 對齊映射結果")
    
    mapping_items = mapper_result.get("items") or []
    
    if not mapping_items:
        st.warning("⚠️ 沒有映射到任何 Schedule D 的行號。")
    else:
        # 繪製標準行號對齊表格
        html_rows = []
        for item in mapping_items:
            target_line = item["target_line"]
            val = item["value"]
            val_display = val
            if isinstance(val, float):
                val_display = f"${val:,.2f}"
            elif isinstance(val, bool):
                val_display = "✅ Yes" if val else "❌ No"
                
            needs_review_badge = ""
            if item.get("needs_review"):
                needs_review_badge = f'<span class="badge-flag" style="margin-left: 10px;">⚠️ Review: {item.get("review_reason")}</span>'
                
            html_rows.append(
                f'<tr>'
                f'<td style="font-weight:bold; font-family:monospace; color:#3b82f6;">{target_line}</td>'
                f'<td style="font-weight:bold; color:#a3e635; text-align:right;">{val_display}{needs_review_badge}</td>'
                f'<td>{item["source_fact_type"]}</td>'
                f'<td>{item["source_category"]}</td>'
                f'<td style="color:#94a3b8; font-size:0.85rem;">{item.get("source_filename") or "—"}</td>'
                f'</tr>'
            )
            
        table_html = (
            f'<table class="field-table">'
            f'<thead><tr>'
            f'<th>Schedule D 行號 (target_line)</th>'
            f'<th style="text-align:right;">對齊數值 (value)</th>'
            f'<th>來源事實名稱 (source_fact_type)</th>'
            f'<th>資料來源類別 (source_category)</th>'
            f'<th>來源文件 (source_filename)</th>'
            f'</tr></thead>'
            f'<tbody>{"".join(html_rows)}</tbody>'
            f'</table>'
        )
        st.markdown(table_html, unsafe_allow_html=True)

    # 3. 顯示未映射項目 (unmapped_items)
    unmapped_items = mapper_result.get("unmapped_items") or []
    st.markdown("### 🚫 Schedule D 未映射與待審查項目")
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
            "<th>排除/未映射原因</th>"
            "<th>來源文件 (source_filename)</th>"
            "</tr></thead>"
            f"<tbody>{''.join(html_rows_unmapped)}</tbody>"
            "</table>"
        )
        st.markdown(table_html_unmapped, unsafe_allow_html=True)


    # 2. Debug 介面
    if is_debug:
        st.divider()
        st.markdown("### 🔍 Debug 偵錯控制台 (Prompts & LLM Trace)")
        
        tab_adapter, tab_mapper = st.tabs([
            "1. PriorYearReturnAdapter 偵錯",
            "2. ScheduleDMapper 偵錯"
        ])
        
        with tab_adapter:
            st.markdown("#### 📂 各上傳檔案之 Facts 提取與 LLM 日誌")
            
            # 使用手風琴選單顯示每一個檔案的狀態
            for fname, a_res in adapter_results.items():
                status = a_res["extraction_status"]
                badge_style = "🔴" if status == "failed" else ("🟡" if status == "completed_with_review" else "🟢")
                
                with st.expander(f"{badge_style} 檔案: {fname} (狀態: {status})", expanded=(status != "failed")):
                    st.json({
                        "detected_tax_year": a_res["detected_tax_year"],
                        "extraction_status": a_res["extraction_status"],
                        "document_needs_review": a_res["document_needs_review"],
                        "document_review_reasons": a_res["document_review_reasons"],
                        "facts": a_res["facts"]
                    })
                    
                    st.divider()
                    
                    a_debug = a_res.get("debug_info") or {}
                    col_al, col_ar = st.columns(2)
                    with col_al:
                        st.markdown(f"**📡 System Prompt ({fname})**")
                        st.text_area("System Prompt", a_debug.get("system_prompt", "N/A"), height=250, key=f"a_sys_prompt_{fname}")
                    with col_ar:
                        st.markdown(f"**📥 LLM 原始回應 ({fname})**")
                        st.text_area("LLM Raw Response", a_debug.get("raw_output", "N/A"), height=250, key=f"a_raw_output_{fname}")
                
        with tab_mapper:
            st.markdown("#### 📋 Mapper 映射結果 JSON")
            st.json(mapping_items)
            
            st.divider()
            
            m_debug = mapper_result.get("debug_info") or {}
            col_ml, col_mr = st.columns(2)
            with col_ml:
                st.markdown("**📡 Mapper System Prompt**")
                st.text_area("Mapper System Prompt", m_debug.get("system_prompt", "N/A"), height=250, key="m_sys_prompt")
                st.markdown("**📨 Mapper User Prompt**")
                st.text_area("Mapper User Prompt", m_debug.get("user_prompt", "N/A"), height=150, key="m_user_prompt")
            with col_mr:
                st.markdown("**📥 Mapper LLM 原始回應**")
                st.text_area("Mapper LLM Raw Output", m_debug.get("raw_output", "N/A"), height=430, key="m_raw_output")
