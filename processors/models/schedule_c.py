import json
from decimal import Decimal
from typing import Dict, Any, List, Optional

# =====================================================================
# REVIEW 重點 1: 金融與精確計算必考題 —— 浮點數誤差防範
# =====================================================================
# 【為什麼要用 Decimal 而不用 float？】
# 1. 電腦以二進位儲存小數，會導致有些十進位小數（如 0.1, 0.2）無法精確表示，產生如 0.30000000000000004 的微小誤差。
# 2. 在非金融業（如電商購物車金額、計費系統、物理引擎等），精確的數值計算同樣至關重要。使用 Decimal(str(val)) 
#    能保證十進制小數運算的絕對精確。
# 3. ⚠️ 注意：傳入 Decimal() 時一定要先轉為 str 類型（如 Decimal("0.10")），否則直接傳入 float 依然會帶入浮點數本身的誤差。
# =====================================================================

class OtherMiscExpenseItemV1:
    def __init__(self, **kwargs):
        self.name = str(kwargs.get("name", ""))
        self.value = Decimal(str(kwargs.get("value", "0.00")))

    # =====================================================================
    # REVIEW 重點 2: 邊界轉換（Boundary Conversion）模式
    # =====================================================================
    # 【為什麼內部用 Decimal，對外輸出又轉回 float？】
    # 1. 內部運算（Core Loop）：使用 Decimal 進行累加與比例折算，確保乘除運算不會累積精度誤差。
    # 2. 外部輸出（Boundary）：因為標準 JSON 格式不支持 Decimal 類型，且後續的 Web API、前端 UI 
    #    一般僅接受 float。因此，我們在 to_dict() 當中統一轉回 float。這叫「內部高精確，外部高相容」。
    # =====================================================================
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": float(self.value)
        }

# =====================================================================
# REVIEW 重點 3: 資料夾解耦 (Decoupling) 與強型別合約 (Type Contract)
# =====================================================================
# 【為什麼不用單純的 dict，而要特別宣告一個 InputsV1 類別？】
# 1. 職責分離 (Single Responsibility)：若把 LLM 提取的 JSON 直接拿去運算，一但 schema 欄位異動，
#    所有計算邏輯都會壞掉。定義 Inputs 類別作為「資料保護層（DTO/Data Transfer Object）」，
#    可以過濾掉無用欄位，確保資料格式符合預期。
# 2. 強型別檢查：Python 在執行期 (Runtime) 是動態的，但寫成 Class 可以享受 IDE 的自動補完 (Autocomplete)、
#    靜態程式檢查（Mypy/Linting），避免把 "gross_receipts" 拼錯成 "gross_receipt"。
# =====================================================================
class ScheduleCInputsV1:
    def __init__(self, **kwargs):
        self.proprietor_name = str(kwargs.get("proprietor_name", ""))
        self.ssn = str(kwargs.get("ssn", ""))
        self.principal_business = kwargs.get("principal_business")
        self.line_b_principal_activity_code = kwargs.get("line_b_principal_activity_code")
        self.business_name = kwargs.get("business_name")
        self.ein = kwargs.get("ein")
        self.business_address = kwargs.get("business_address")
        
        self.accounting_method = kwargs.get("accounting_method", "Cash")
        self.started_acquired_2025 = bool(kwargs.get("started_acquired_2025", False))
        
        # 數值輸入項目，全部使用 Decimal 進行防禦性轉換
        self.line_1_gross_receipts = Decimal(str(kwargs.get("line_1_gross_receipts", "0.00")))
        self.line_2_returns_allowances = Decimal(str(kwargs.get("line_2_returns_allowances", "0.00")))
        self.line_6_other_income = Decimal(str(kwargs.get("line_6_other_income", "0.00")))
        self.line_8_advertising = Decimal(str(kwargs.get("line_8_advertising", "0.00")))
        self.line_10_commissions_fees = Decimal(str(kwargs.get("line_10_commissions_fees", "0.00")))
        self.line_11_contract_labor = Decimal(str(kwargs.get("line_11_contract_labor", "0.00")))
        self.line_12_depletion = Decimal(str(kwargs.get("line_12_depletion", "0.00")))
        self.line_14_employee_benefit_programs = Decimal(str(kwargs.get("line_14_employee_benefit_programs", "0.00")))
        self.line_15_insurance = Decimal(str(kwargs.get("line_15_insurance", "0.00")))
        self.line_16a_mortgage_interest = Decimal(str(kwargs.get("line_16a_mortgage_interest", "0.00")))
        self.line_16b_other_interest = Decimal(str(kwargs.get("line_16b_other_interest", "0.00")))
        self.line_17_legal_professional = Decimal(str(kwargs.get("line_17_legal_professional", "0.00")))
        self.line_18_office_expense = Decimal(str(kwargs.get("line_18_office_expense", "0.00")))
        self.line_19_pension_profit_sharing = Decimal(str(kwargs.get("line_19_pension_profit_sharing", "0.00")))
        self.line_20a_rent_machinery_equipment = Decimal(str(kwargs.get("line_20a_rent_machinery_equipment", "0.00")))
        self.line_20b_rent_other_property = Decimal(str(kwargs.get("line_20b_rent_other_property", "0.00")))
        self.line_21_repairs_maintenance = Decimal(str(kwargs.get("line_21_repairs_maintenance", "0.00")))
        self.line_22_supplies = Decimal(str(kwargs.get("line_22_supplies", "0.00")))
        self.line_23_taxes_licenses = Decimal(str(kwargs.get("line_23_taxes_licenses", "0.00")))
        self.line_25_utilities = Decimal(str(kwargs.get("line_25_utilities", "0.00")))
        
        self.line_33_inventory_valuation_method = kwargs.get("line_33_inventory_valuation_method")
        self.line_34_change_in_valuation = bool(kwargs.get("line_34_change_in_valuation", False))
        self.line_36_purchases_less_personal = Decimal(str(kwargs.get("line_36_purchases_less_personal", "0.00")))
        self.line_38_materials_supplies = Decimal(str(kwargs.get("line_38_materials_supplies", "0.00")))
        self.line_39_other_costs = Decimal(str(kwargs.get("line_39_other_costs", "0.00")))
        self.line_41_ending_inventory = Decimal(str(kwargs.get("line_41_ending_inventory", "0.00")))
        
        self.line_43_date_placed_in_service = kwargs.get("line_43_date_placed_in_service")
        self.line_44a_business_miles = Decimal(str(kwargs.get("line_44a_business_miles", "0.00")))
        self.line_44b_commuting_miles = Decimal(str(kwargs.get("line_44b_commuting_miles", "0.00")))
        self.line_44c_other_miles = Decimal(str(kwargs.get("line_44c_other_miles", "0.00")))
        self.line_45_available_for_personal_use = bool(kwargs.get("line_45_available_for_personal_use", False))
        self.line_46_another_vehicle_available = bool(kwargs.get("line_46_another_vehicle_available", False))
        self.line_47a_evidence_to_support = bool(kwargs.get("line_47a_evidence_to_support", False))
        self.line_47b_evidence_written = bool(kwargs.get("line_47b_evidence_written", False))
        
        self.owner_annual_hours = Decimal(str(kwargs.get("owner_annual_hours", "0.00")))
        self.is_sole_participant = bool(kwargs.get("is_sole_participant", False))
        self.others_annual_hours = Decimal(str(kwargs.get("others_annual_hours", "0.00")))
        self.any_contractor_paid_600_or_more = bool(kwargs.get("any_contractor_paid_600_or_more", False))
        self.is_1099_filed = bool(kwargs.get("is_1099_filed", False))
        
        self.actual_car_expenses = Decimal(str(kwargs.get("actual_car_expenses", "0.00")))
        self.parking_and_tolls = Decimal(str(kwargs.get("parking_and_tolls", "0.00")))
        self.selected_mileage_method = kwargs.get("selected_mileage_method", "standard")
        
        self.macrs_depreciation = Decimal(str(kwargs.get("macrs_depreciation", "0.00")))
        self.sec179_asset_cost = Decimal(str(kwargs.get("sec179_asset_cost", "0.00")))
        self.use_sec179 = bool(kwargs.get("use_sec179", False))
        
        self.travel_transit_cost = Decimal(str(kwargs.get("travel_transit_cost", "0.00")))
        self.travel_lodging_cost = Decimal(str(kwargs.get("travel_lodging_cost", "0.00")))
        self.total_trip_days = Decimal(str(kwargs.get("total_trip_days", "0.00")))
        self.business_days = Decimal(str(kwargs.get("business_days", "0.00")))
        self.is_international = bool(kwargs.get("is_international", False))
        
        self.meals_50_pct = Decimal(str(kwargs.get("meals_50_pct", "0.00")))
        self.meals_100_pct = Decimal(str(kwargs.get("meals_100_pct", "0.00")))
        self.entertainment_cost = Decimal(str(kwargs.get("entertainment_cost", "0.00")))
        
        self.w2_gross_wages = Decimal(str(kwargs.get("w2_gross_wages", "0.00")))
        self.employment_credits = Decimal(str(kwargs.get("employment_credits", "0.00")))
        self.owner_salary_or_draw = Decimal(str(kwargs.get("owner_salary_or_draw", "0.00")))
        
        self.improved_building_sqft = Decimal(str(kwargs.get("improved_building_sqft", "0.00")))
        self.certified_deduction_rate = Decimal(str(kwargs.get("certified_deduction_rate", "0.00")))
        
        self.home_office_sqft = Decimal(str(kwargs.get("home_office_sqft", "0.00")))
        self.total_home_sqft = Decimal(str(kwargs.get("total_home_sqft", "0.00")))
        self.allowable_home_expenses = Decimal(str(kwargs.get("allowable_home_expenses", "0.00")))
        self.is_exclusive_and_regular = bool(kwargs.get("is_exclusive_and_regular", False))
        self.selected_home_method = kwargs.get("selected_home_method", "simplified")
        
        self.nonrecourse_debt = Decimal(str(kwargs.get("nonrecourse_debt", "0.00")))
        self.guaranteed_non_risk_funding = Decimal(str(kwargs.get("guaranteed_non_risk_funding", "0.00")))
        self.prior_year_ending_inventory = Decimal(str(kwargs.get("prior_year_ending_inventory", "0.00")))
        self.book_beginning_inventory = Decimal(str(kwargs.get("book_beginning_inventory", "0.00")))
        
        self.production_labor_wages = Decimal(str(kwargs.get("production_labor_wages", "0.00")))
        self.owner_production_labor_pay = Decimal(str(kwargs.get("owner_production_labor_pay", "0.00")))
        self.stripe_merchant_fees = Decimal(str(kwargs.get("stripe_merchant_fees", "0.00")))
        self.software_subscriptions = Decimal(str(kwargs.get("software_subscriptions", "0.00")))
        self.cleaning_services = Decimal(str(kwargs.get("cleaning_services", "0.00")))
        self.book_amortization = Decimal(str(kwargs.get("book_amortization", "0.00")))
        self.book_bad_debts = Decimal(str(kwargs.get("book_bad_debts", "0.00")))
        self.de_minimis_safe_harbor_cost = Decimal(str(kwargs.get("de_minimis_safe_harbor_cost", "0.00")))
        
        self.other_misc_expenses_list = [
            OtherMiscExpenseItemV1(**x) if isinstance(x, dict) else x for x in kwargs.get("other_misc_expenses_list", [])
        ]

    # 工廠方法模式 (Factory Method)
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduleCInputsV1":
        return cls(**data)

class ScheduleCResultV1:
    def __init__(self, **kwargs):
        self.proprietor_name = kwargs.get("proprietor_name", "")
        self.ssn = kwargs.get("ssn", "")
        
        # calculated variables
        self.line_b_principal_activity_code_val = kwargs.get("line_b_principal_activity_code_val")
        self.line_g_material_participation = bool(kwargs.get("line_g_material_participation", False))
        self.line_i_payment_requiring_1099 = bool(kwargs.get("line_i_payment_requiring_1099", False))
        self.line_j_filed_1099 = bool(kwargs.get("line_j_filed_1099", False))
        
        self.line_9_car_truck_expenses = kwargs.get("line_9_car_truck_expenses", Decimal("0.00"))
        self.line_24a_travel = kwargs.get("line_24a_travel", Decimal("0.00"))
        self.line_24b_deductible_meals = kwargs.get("line_24b_deductible_meals", Decimal("0.00"))
        self.line_26_wages = kwargs.get("line_26_wages", Decimal("0.00"))
        self.line_27a_energy_efficient_deduction = kwargs.get("line_27a_energy_efficient_deduction", Decimal("0.00"))
        
        self.line_35_beginning_inventory = kwargs.get("line_35_beginning_inventory", Decimal("0.00"))
        self.line_37_cost_of_labor = kwargs.get("line_37_cost_of_labor", Decimal("0.00"))
        self.line_48_other_expenses_total = kwargs.get("line_48_other_expenses_total", Decimal("0.00"))
        self.line_40_total_cost_of_goods = kwargs.get("line_40_total_cost_of_goods", Decimal("0.00"))
        self.line_42_cogs = kwargs.get("line_42_cogs", Decimal("0.00"))
        
        self.line_3_net_receipts = kwargs.get("line_3_net_receipts", Decimal("0.00"))
        self.line_4_cogs = kwargs.get("line_4_cogs", Decimal("0.00"))
        self.line_5_gross_profit = kwargs.get("line_5_gross_profit", Decimal("0.00"))
        self.line_6_other_income = kwargs.get("line_6_other_income", Decimal("0.00"))
        self.line_7_gross_income = kwargs.get("line_7_gross_income", Decimal("0.00"))
        self.line_27b_other_expenses = kwargs.get("line_27b_other_expenses", Decimal("0.00"))
        
        self.net_income_before_sec179 = kwargs.get("net_income_before_sec179", Decimal("0.00"))
        self.sec179_deduction = kwargs.get("sec179_deduction", Decimal("0.00"))
        self.line_13_depreciation_sec179 = kwargs.get("line_13_depreciation_sec179", Decimal("0.00"))
        self.line_28_total_expenses = kwargs.get("line_28_total_expenses", Decimal("0.00"))
        self.line_29_tentative_profit = kwargs.get("line_29_tentative_profit", Decimal("0.00"))
        self.line_30_business_use_of_home = kwargs.get("line_30_business_use_of_home", Decimal("0.00"))
        self.line_31_net_profit = kwargs.get("line_31_net_profit", Decimal("0.00"))
        self.line_32_at_risk = kwargs.get("line_32_at_risk", "32a")
        
        self.blocking_errors = kwargs.get("blocking_errors") or []
        self.review_warnings = kwargs.get("review_warnings") or []

    # 當呼叫 to_dict() 時，利用 recursive 的方式確保內部的 Decimal 回退成標準型態，避免 serialization 錯誤。
    def to_dict(self) -> Dict[str, Any]:
        def to_float(val):
            if isinstance(val, Decimal):
                return float(val)
            return val
            
        res = {}
        for k, v in self.__dict__.items():
            if k in ["blocking_errors", "review_warnings"]:
                res[k] = [x.to_dict() if hasattr(x, "to_dict") else x for x in v]
            else:
                res[k] = to_float(v)
        return res
