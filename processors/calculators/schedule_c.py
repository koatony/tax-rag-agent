from decimal import Decimal
from typing import Dict, Any, List
from processors.models.schedule_a import ValidationIssue
from processors.models.schedule_c import ScheduleCInputsV1, ScheduleCResultV1
from processors.validators.schedule_c import validate_identity, validate_nonnegative_amounts

# =====================================================================
# REVIEW 重點 1: 單一職責原則 (Single Responsibility Principle)
# =====================================================================
# 【為什麼要把計算邏輯單獨抽成一個模組？】
# 1. 職責分離：在軟體工程中，I/O（網路呼叫、LLM 解析）與「業務邏輯（計算）」應當嚴格分離。
#    這使得我們在單元測試 (Unit Test) 此計算邏輯時，不需要 Mock LLM 網路連線，只需傳入模擬物件，即可進行純代數比對。
# 2. 本模組不關心資料如何被讀取（資料庫、CSV、網頁或 LLM 萃取），它只負責給定輸入 inputs，並回傳確定性的 outputs。
# =====================================================================

def calculate_schedule_c_v1(inputs: ScheduleCInputsV1) -> ScheduleCResultV1:
    errors: List[ValidationIssue] = []
    
    # 執行校驗 (這屬於資料提取後的業務規則過濾，與資料格式驗證分開)
    validate_identity(inputs, errors)
    validate_nonnegative_amounts(inputs, errors)
    
    # 1. 基礎宣告
    line_b_principal_activity_code_val = inputs.line_b_principal_activity_code
    
    # 是否實質參與判定
    if inputs.owner_annual_hours > 500 or inputs.is_sole_participant:
        line_g_material_participation = True
    elif inputs.owner_annual_hours > 100 and inputs.owner_annual_hours >= inputs.others_annual_hours:
        line_g_material_participation = True
    elif inputs.owner_annual_hours == Decimal("0.00") and inputs.others_annual_hours == Decimal("0.00"):
        line_g_material_participation = True
    else:
        line_g_material_participation = False
        
    line_i_payment_requiring_1099 = inputs.any_contractor_paid_600_or_more
    line_j_filed_1099 = inputs.is_1099_filed if line_i_payment_requiring_1099 else False
    
    # =====================================================================
    # REVIEW 重點 2: 預防 ZeroDivisionError 除以零的邊界防守
    # =====================================================================
    # 【如何優雅地預防除以零？】
    # 1. 當 total_miles 為 0 時，直接除以它會拋出 ZeroDivisionError 造成整個服務崩潰。
    # 2. 我們在此處透過檢查 `if total_miles > 0:` 來保護除法運算，若無里程則比率預設為 0.00。
    # 3. ⚠️ 面試提點：在任何涉及比例、除法的系統中，防堵除以零都是安全審查的必看指標。
    # =====================================================================
    if inputs.selected_mileage_method == 'standard':
        line_9_car_truck_expenses = inputs.line_44a_business_miles * Decimal('0.70') + inputs.parking_and_tolls
    else:
        total_miles = inputs.line_44a_business_miles + inputs.line_44b_commuting_miles + inputs.line_44c_other_miles
        if total_miles > 0:
            ratio = inputs.line_44a_business_miles / total_miles
        else:
            ratio = Decimal("0.00")
        line_9_car_truck_expenses = inputs.actual_car_expenses * ratio + inputs.parking_and_tolls
        
    # 差旅大交通與住宿費用分配
    if not inputs.is_international:
        if inputs.business_days > inputs.total_trip_days / 2:
            transit = inputs.travel_transit_cost
        else:
            transit = Decimal("0.00")
        if inputs.total_trip_days > 0:
            lodging = inputs.travel_lodging_cost * (inputs.business_days / inputs.total_trip_days)
        else:
            lodging = Decimal("0.00")
        line_24a_travel = transit + lodging
    else:
        if inputs.total_trip_days <= 7 or (inputs.total_trip_days - inputs.business_days) / inputs.total_trip_days < Decimal("0.25"):
            transit = inputs.travel_transit_cost
        else:
            transit = inputs.travel_transit_cost * (inputs.business_days / inputs.total_trip_days)
        if inputs.total_trip_days > 0:
            lodging = inputs.travel_lodging_cost * (inputs.business_days / inputs.total_trip_days)
        else:
            lodging = Decimal("0.00")
        line_24a_travel = transit + lodging
        
    # 餐飲限制 (一般 50%, 全額 100%, 娛樂 0%)
    line_24b_deductible_meals = inputs.meals_50_pct * Decimal('0.50') + inputs.meals_100_pct * Decimal('1.00') + inputs.entertainment_cost * Decimal('0.00')
    
    # 扣除抵免之雇員工資
    line_26_wages = inputs.w2_gross_wages - inputs.employment_credits
    
    # 節能建築扣除
    line_27a_energy_efficient_deduction = inputs.improved_building_sqft * inputs.certified_deduction_rate
    
    # 銷貨成本 (Part III COGS)
    line_35_beginning_inventory = inputs.prior_year_ending_inventory
    line_37_cost_of_labor = inputs.production_labor_wages
    
    # 雜項費用加總
    other_list_sum = sum(item.value for item in inputs.other_misc_expenses_list)
    line_48_other_expenses_total = (
        inputs.stripe_merchant_fees +
        inputs.software_subscriptions +
        inputs.cleaning_services +
        inputs.book_amortization +
        inputs.book_bad_debts +
        inputs.de_minimis_safe_harbor_cost +
        other_list_sum
    )
    
    line_40_total_cost_of_goods = line_35_beginning_inventory + inputs.line_36_purchases_less_personal + line_37_cost_of_labor + inputs.line_38_materials_supplies + inputs.line_39_other_costs
    line_42_cogs = line_40_total_cost_of_goods - inputs.line_41_ending_inventory
    
    # 毛利計算 (Gross Profit)
    line_3_net_receipts = inputs.line_1_gross_receipts - inputs.line_2_returns_allowances
    line_4_cogs = line_42_cogs
    line_5_gross_profit = line_3_net_receipts - line_4_cogs
    line_6_other_income = inputs.line_6_other_income
    line_7_gross_income = line_5_gross_profit + line_6_other_income
    
    line_27b_other_expenses = line_48_other_expenses_total
    
    # 扣除折舊與 Section 179 之前的淨利
    expenses_excluding_deprec_sec179 = (
        inputs.line_8_advertising +
        line_9_car_truck_expenses +
        inputs.line_10_commissions_fees +
        inputs.line_11_contract_labor +
        inputs.line_12_depletion +
        inputs.line_14_employee_benefit_programs +
        inputs.line_15_insurance +
        inputs.line_16a_mortgage_interest +
        inputs.line_16b_other_interest +
        inputs.line_17_legal_professional +
        inputs.line_18_office_expense +
        inputs.line_19_pension_profit_sharing +
        inputs.line_20a_rent_machinery_equipment +
        inputs.line_20b_rent_other_property +
        inputs.line_21_repairs_maintenance +
        inputs.line_22_supplies +
        inputs.line_23_taxes_licenses +
        line_24a_travel +
        line_24b_deductible_meals +
        inputs.line_25_utilities +
        line_26_wages +
        line_27a_energy_efficient_deduction +
        line_27b_other_expenses
    )
    net_income_before_sec179 = line_7_gross_income - expenses_excluding_deprec_sec179
    
    # Section 179 一次性費用折舊上限 (不可使淨利為負值)
    sec179_deduction = Decimal("0.00")
    if inputs.use_sec179:
        sec179_deduction = min(inputs.sec179_asset_cost, Decimal('1150000.00'), max(Decimal('0.00'), net_income_before_sec179))
        
    line_13_depreciation_sec179 = inputs.macrs_depreciation + sec179_deduction
    
    line_28_total_expenses = expenses_excluding_deprec_sec179 + line_13_depreciation_sec179
    line_29_tentative_profit = line_7_gross_income - line_28_total_expenses
    
    # 家庭辦公室扣抵 (Home Office)
    if not inputs.is_exclusive_and_regular:
        line_30_business_use_of_home = Decimal("0.00")
    else:
        if inputs.selected_home_method == 'simplified':
            line_30_business_use_of_home = min(Decimal('300.00'), inputs.home_office_sqft) * Decimal('5.00')
        else:
            denom = inputs.total_home_sqft + Decimal('0.0001') # 防禦性加上小數防止除以零
            line_30_business_use_of_home = inputs.allowable_home_expenses * (inputs.home_office_sqft / denom)
            
    line_31_net_profit = line_29_tentative_profit - line_30_business_use_of_home
    
    # At-risk 風險狀態判定
    if inputs.nonrecourse_debt == Decimal("0.00") and inputs.guaranteed_non_risk_funding == Decimal("0.00"):
        line_32_at_risk = '32a'
    else:
        line_32_at_risk = '32b'
        
    return ScheduleCResultV1(
        proprietor_name=inputs.proprietor_name,
        ssn=inputs.ssn,
        line_b_principal_activity_code_val=line_b_principal_activity_code_val,
        line_g_material_participation=line_g_material_participation,
        line_i_payment_requiring_1099=line_i_payment_requiring_1099,
        line_j_filed_1099=line_j_filed_1099,
        line_9_car_truck_expenses=line_9_car_truck_expenses,
        line_24a_travel=line_24a_travel,
        line_24b_deductible_meals=line_24b_deductible_meals,
        line_26_wages=line_26_wages,
        line_27a_energy_efficient_deduction=line_27a_energy_efficient_deduction,
        line_35_beginning_inventory=line_35_beginning_inventory,
        line_37_cost_of_labor=line_37_cost_of_labor,
        line_48_other_expenses_total=line_48_other_expenses_total,
        line_40_total_cost_of_goods=line_40_total_cost_of_goods,
        line_42_cogs=line_42_cogs,
        line_3_net_receipts=line_3_net_receipts,
        line_4_cogs=line_4_cogs,
        line_5_gross_profit=line_5_gross_profit,
        line_6_other_income=line_6_other_income,
        line_7_gross_income=line_7_gross_income,
        line_27b_other_expenses=line_27b_other_expenses,
        net_income_before_sec179=net_income_before_sec179,
        sec179_deduction=sec179_deduction,
        line_13_depreciation_sec179=line_13_depreciation_sec179,
        line_28_total_expenses=line_28_total_expenses,
        line_29_tentative_profit=line_29_tentative_profit,
        line_30_business_use_of_home=line_30_business_use_of_home,
        line_31_net_profit=line_31_net_profit,
        line_32_at_risk=line_32_at_risk,
        blocking_errors=errors,
        review_warnings=[]
    )
