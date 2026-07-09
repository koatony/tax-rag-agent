import json
from decimal import Decimal
from typing import Dict, Any, List, Optional
from processors.models.schedule_a import ValidationIssue

class OtherExpenseItemV1:
    """
    其他費用明細（Part V Other Expenses）資料結構。
    包含單筆項目的 ID、名稱、金額、來源文件 ID 以及置信度。
    """
    def __init__(self, **kwargs):
        self.item_id = str(kwargs.get("item_id", ""))
        self.name = str(kwargs.get("name", ""))
        self.amount = Decimal(str(kwargs.get("amount", "0.00")))
        self.source_document_id = kwargs.get("source_document_id")
        self.confidence = str(kwargs.get("confidence", "HIGH")).upper()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "amount": float(self.amount),
            "source_document_id": self.source_document_id,
            "confidence": self.confidence
        }

class ScheduleCIncomeV1:
    """
    Part I 營業收入輸入資料。
    包含 Line 1 毛收入、Line 2 退貨折讓及 Line 6 其他收入。
    """
    def __init__(self, **kwargs):
        self.line_1_gross_receipts = Decimal(str(kwargs.get("line_1_gross_receipts"))) if kwargs.get("line_1_gross_receipts") is not None else None
        self.line_2_returns_allowances = Decimal(str(kwargs.get("line_2_returns_allowances", "0.00")))
        self.line_6_other_income = Decimal(str(kwargs.get("line_6_other_income", "0.00")))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "line_1_gross_receipts": float(self.line_1_gross_receipts) if self.line_1_gross_receipts is not None else None,
            "line_2_returns_allowances": float(self.line_2_returns_allowances),
            "line_6_other_income": float(self.line_6_other_income)
        }

class ScheduleCExpenseInputsV1:
    """
    Part II 營業費用輸入資料（包含 Lines 8-27 的原始申報金額、
    餐飲與娛樂來源總額，以及由外部模組計算完成傳入的特別科目數據如 COGS、折舊、家庭辦公室等）。
    """
    def __init__(self, **kwargs):
        self.line_8_advertising = Decimal(str(kwargs.get("line_8_advertising", "0.00")))
        self.line_9_car_truck_expenses_final = Decimal(str(kwargs.get("line_9_car_truck_expenses_final"))) if kwargs.get("line_9_car_truck_expenses_final") is not None else None
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
        self.line_24a_travel_final = Decimal(str(kwargs.get("line_24a_travel_final"))) if kwargs.get("line_24a_travel_final") is not None else None
        
        self.meals_50_percent_source_amount = Decimal(str(kwargs.get("meals_50_percent_source_amount", "0.00")))
        self.meals_100_percent_source_amount = Decimal(str(kwargs.get("meals_100_percent_source_amount", "0.00")))
        self.entertainment_source_amount = Decimal(str(kwargs.get("entertainment_source_amount", "0.00")))
        
        self.line_25_utilities = Decimal(str(kwargs.get("line_25_utilities", "0.00")))
        self.line_26_wages_final = Decimal(str(kwargs.get("line_26_wages_final"))) if kwargs.get("line_26_wages_final") is not None else None
        
        self.line_13_depreciation_from_form4562 = Decimal(str(kwargs.get("line_13_depreciation_from_form4562"))) if kwargs.get("line_13_depreciation_from_form4562") is not None else None
        self.line_30_home_office_from_module = Decimal(str(kwargs.get("line_30_home_office_from_module"))) if kwargs.get("line_30_home_office_from_module") is not None else None
        self.line_4_cogs_from_module = Decimal(str(kwargs.get("line_4_cogs_from_module"))) if kwargs.get("line_4_cogs_from_module") is not None else None

    def to_dict(self) -> Dict[str, Any]:
        def to_float(val):
            return float(val) if isinstance(val, Decimal) else val
        return {
            "line_8_advertising": to_float(self.line_8_advertising),
            "line_9_car_truck_expenses_final": to_float(self.line_9_car_truck_expenses_final),
            "line_10_commissions_fees": to_float(self.line_10_commissions_fees),
            "line_11_contract_labor": to_float(self.line_11_contract_labor),
            "line_12_depletion": to_float(self.line_12_depletion),
            "line_14_employee_benefit_programs": to_float(self.line_14_employee_benefit_programs),
            "line_15_insurance": to_float(self.line_15_insurance),
            "line_16a_mortgage_interest": to_float(self.line_16a_mortgage_interest),
            "line_16b_other_interest": to_float(self.line_16b_other_interest),
            "line_17_legal_professional": to_float(self.line_17_legal_professional),
            "line_18_office_expense": to_float(self.line_18_office_expense),
            "line_19_pension_profit_sharing": to_float(self.line_19_pension_profit_sharing),
            "line_20a_rent_machinery_equipment": to_float(self.line_20a_rent_machinery_equipment),
            "line_20b_rent_other_property": to_float(self.line_20b_rent_other_property),
            "line_21_repairs_maintenance": to_float(self.line_21_repairs_maintenance),
            "line_22_supplies": to_float(self.line_22_supplies),
            "line_23_taxes_licenses": to_float(self.line_23_taxes_licenses),
            "line_24a_travel_final": to_float(self.line_24a_travel_final),
            "meals_50_percent_source_amount": to_float(self.meals_50_percent_source_amount),
            "meals_100_percent_source_amount": to_float(self.meals_100_percent_source_amount),
            "entertainment_source_amount": to_float(self.entertainment_source_amount),
            "line_25_utilities": to_float(self.line_25_utilities),
            "line_26_wages_final": to_float(self.line_26_wages_final),
            "line_13_depreciation_from_form4562": to_float(self.line_13_depreciation_from_form4562),
            "line_30_home_office_from_module": to_float(self.line_30_home_office_from_module),
            "line_4_cogs_from_module": to_float(self.line_4_cogs_from_module),
        }

class ScheduleCSpecialCaseFlagsV1:
    """
    V1 特殊案件偵測旗標（Boolean flags）。
    用於判斷是否含有 V1 引擎未支援的進階稅務計算情境（如車輛里程、折舊 Form 4562、
    家庭辦公室 Form 8829、COGS 庫存等），以決定是否阻斷申報或提示人工審查。
    """
    def __init__(self, **kwargs):
        self.has_inventory_or_cogs = bool(kwargs.get("has_inventory_or_cogs", False))
        self.has_vehicle_expense_requiring_calculation = bool(kwargs.get("has_vehicle_expense_requiring_calculation", False))
        self.has_depreciation_or_section179 = bool(kwargs.get("has_depreciation_or_section179", False))
        self.has_home_office = bool(kwargs.get("has_home_office", False))
        self.has_mixed_travel = bool(kwargs.get("has_mixed_travel", False))
        self.has_uncertain_meals_or_entertainment = bool(kwargs.get("has_uncertain_meals_or_entertainment", False))
        self.has_employee_wages_or_payroll_credit = bool(kwargs.get("has_employee_wages_or_payroll_credit", False))
        self.has_owner_draw_in_expenses = bool(kwargs.get("has_owner_draw_in_expenses", False))
        self.has_uncertain_expense_category = bool(kwargs.get("has_uncertain_expense_category", False))
        self.has_rental_or_royalty_activity = bool(kwargs.get("has_rental_or_royalty_activity", False))
        self.has_farm_activity = bool(kwargs.get("has_farm_activity", False))
        self.has_business_asset_sale = bool(kwargs.get("has_business_asset_sale", False))
        self.has_passive_activity_issue = bool(kwargs.get("has_passive_activity_issue", False))
        self.has_at_risk_limitation_issue = bool(kwargs.get("has_at_risk_limitation_issue", False))
        self.has_qbi_request = bool(kwargs.get("has_qbi_request", False))
        self.has_schedule_se_request = bool(kwargs.get("has_schedule_se_request", False))

    def to_dict(self) -> Dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dict__}

class ScheduleCInputsV1:
    """
    Schedule C 完整輸入模型。
    封裝基本身份、問卷選項、營業收入（Income）、營業費用（Expenses）、
    其他費用列表（Other Expenses）與特殊案件偵測旗標（Flags）。
    """
    def __init__(self, **kwargs):
        self.proprietor_name = str(kwargs.get("proprietor_name", ""))
        self.taxpayer_ssn = str(kwargs.get("taxpayer_ssn", ""))
        self.tax_year = int(kwargs.get("tax_year", 2025))

        self.principal_business = kwargs.get("principal_business")
        self.principal_activity_code = kwargs.get("principal_activity_code")
        self.business_name = kwargs.get("business_name")
        self.ein = kwargs.get("ein")
        self.business_address = kwargs.get("business_address")

        raw_method = kwargs.get("accounting_method")
        self.accounting_method = str(raw_method).upper() if raw_method else None

        self.line_g_material_participation = kwargs.get("line_g_material_participation")
        if self.line_g_material_participation is None:
            if "material_participation" in kwargs:
                self.line_g_material_participation = bool(kwargs["material_participation"])

        self.line_h_started_or_acquired = kwargs.get("line_h_started_or_acquired")
        self.line_i_payment_requiring_1099 = kwargs.get("line_i_payment_requiring_1099")
        self.line_j_filed_required_1099 = kwargs.get("line_j_filed_required_1099")

        # Parse nested models (resilient to both nested and flat dictionaries)
        inc_data = kwargs.get("income") or kwargs
        self.income = ScheduleCIncomeV1(**inc_data) if isinstance(inc_data, dict) else inc_data

        exp_data = kwargs.get("expenses") or kwargs
        self.expenses = ScheduleCExpenseInputsV1(**exp_data) if isinstance(exp_data, dict) else exp_data

        other_items = kwargs.get("other_expense_items") or []
        self.other_expense_items = [
            OtherExpenseItemV1(**x) if isinstance(x, dict) else x for x in other_items
        ]

        self.loss_at_risk_answer = kwargs.get("loss_at_risk_answer")

        flags_data = kwargs.get("special_case_flags") or kwargs
        self.special_case_flags = ScheduleCSpecialCaseFlagsV1(**flags_data) if isinstance(flags_data, dict) else flags_data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduleCInputsV1":
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proprietor_name": self.proprietor_name,
            "taxpayer_ssn": self.taxpayer_ssn,
            "tax_year": self.tax_year,
            "principal_business": self.principal_business,
            "principal_activity_code": self.principal_activity_code,
            "business_name": self.business_name,
            "ein": self.ein,
            "business_address": self.business_address,
            "accounting_method": self.accounting_method,
            "line_g_material_participation": self.line_g_material_participation,
            "line_h_started_or_acquired": self.line_h_started_or_acquired,
            "line_i_payment_requiring_1099": self.line_i_payment_requiring_1099,
            "line_j_filed_required_1099": self.line_j_filed_required_1099,
            "income": self.income.to_dict() if hasattr(self.income, "to_dict") else self.income,
            "expenses": self.expenses.to_dict() if hasattr(self.expenses, "to_dict") else self.expenses,
            "other_expense_items": [x.to_dict() if hasattr(x, "to_dict") else x for x in self.other_expense_items],
            "loss_at_risk_answer": self.loss_at_risk_answer,
            "special_case_flags": self.special_case_flags.to_dict() if hasattr(self.special_case_flags, "to_dict") else self.special_case_flags
        }

class ScheduleCResultV1:
    """
    Schedule C 計算與校驗結果模型。
    包含所有算出的表單表面欄位（Lines 1-31）、總計數值、
    身分掩碼資料、校驗阻斷錯誤（blocking_errors）與審查警告（review_warnings）。
    """
    def __init__(self, **kwargs):
        self.proprietor_name = kwargs.get("proprietor_name", "")
        self.taxpayer_ssn_masked = kwargs.get("taxpayer_ssn_masked", "")
        self.tax_year = kwargs.get("tax_year", 2025)

        self.principal_business = kwargs.get("principal_business")
        self.principal_activity_code = kwargs.get("principal_activity_code")
        self.business_name = kwargs.get("business_name")
        self.ein = kwargs.get("ein")
        self.business_address = kwargs.get("business_address")
        self.accounting_method = kwargs.get("accounting_method")

        self.line_g_material_participation = kwargs.get("line_g_material_participation")
        self.line_h_started_or_acquired = kwargs.get("line_h_started_or_acquired")
        self.line_i_payment_requiring_1099 = kwargs.get("line_i_payment_requiring_1099")
        self.line_j_filed_required_1099 = kwargs.get("line_j_filed_required_1099")

        self.line_1_gross_receipts = kwargs.get("line_1_gross_receipts", Decimal("0.00"))
        self.line_2_returns_allowances = kwargs.get("line_2_returns_allowances", Decimal("0.00"))
        self.line_3_net_receipts = kwargs.get("line_3_net_receipts", Decimal("0.00"))
        self.line_4_cogs = kwargs.get("line_4_cogs", Decimal("0.00"))
        self.line_5_gross_profit = kwargs.get("line_5_gross_profit", Decimal("0.00"))
        self.line_6_other_income = kwargs.get("line_6_other_income", Decimal("0.00"))
        self.line_7_gross_income = kwargs.get("line_7_gross_income", Decimal("0.00"))

        self.line_8_advertising = kwargs.get("line_8_advertising", Decimal("0.00"))
        self.line_9_car_truck_expenses = kwargs.get("line_9_car_truck_expenses", Decimal("0.00"))
        self.line_10_commissions_fees = kwargs.get("line_10_commissions_fees", Decimal("0.00"))
        self.line_11_contract_labor = kwargs.get("line_11_contract_labor", Decimal("0.00"))
        self.line_12_depletion = kwargs.get("line_12_depletion", Decimal("0.00"))
        self.line_13_depreciation = kwargs.get("line_13_depreciation", Decimal("0.00"))
        self.line_14_employee_benefit_programs = kwargs.get("line_14_employee_benefit_programs", Decimal("0.00"))
        self.line_15_insurance = kwargs.get("line_15_insurance", Decimal("0.00"))
        self.line_16a_mortgage_interest = kwargs.get("line_16a_mortgage_interest", Decimal("0.00"))
        self.line_16b_other_interest = kwargs.get("line_16b_other_interest", Decimal("0.00"))
        self.line_17_legal_professional = kwargs.get("line_17_legal_professional", Decimal("0.00"))
        self.line_18_office_expense = kwargs.get("line_18_office_expense", Decimal("0.00"))
        self.line_19_pension_profit_sharing = kwargs.get("line_19_pension_profit_sharing", Decimal("0.00"))
        self.line_20a_rent_machinery_equipment = kwargs.get("line_20a_rent_machinery_equipment", Decimal("0.00"))
        self.line_20b_rent_other_property = kwargs.get("line_20b_rent_other_property", Decimal("0.00"))
        self.line_21_repairs_maintenance = kwargs.get("line_21_repairs_maintenance", Decimal("0.00"))
        self.line_22_supplies = kwargs.get("line_22_supplies", Decimal("0.00"))
        self.line_23_taxes_licenses = kwargs.get("line_23_taxes_licenses", Decimal("0.00"))
        self.line_24a_travel = kwargs.get("line_24a_travel", Decimal("0.00"))
        self.line_24b_deductible_meals = kwargs.get("line_24b_deductible_meals", Decimal("0.00"))
        self.line_25_utilities = kwargs.get("line_25_utilities", Decimal("0.00"))
        self.line_26_wages = kwargs.get("line_26_wages", Decimal("0.00"))
        self.line_27a_energy_efficient_building_deduction = kwargs.get("line_27a_energy_efficient_building_deduction", Decimal("0.00"))
        self.line_27b_other_expenses = kwargs.get("line_27b_other_expenses", Decimal("0.00"))

        self.line_28_total_expenses = kwargs.get("line_28_total_expenses", Decimal("0.00"))
        self.line_29_tentative_profit_or_loss = kwargs.get("line_29_tentative_profit_or_loss", Decimal("0.00"))
        self.line_30_home_office = kwargs.get("line_30_home_office", Decimal("0.00"))
        self.line_31_net_profit_or_loss = kwargs.get("line_31_net_profit_or_loss", Decimal("0.00"))
        self.line_32_at_risk_surface = kwargs.get("line_32_at_risk_surface")

        self.line_48_total_other_expenses = kwargs.get("line_48_total_other_expenses", Decimal("0.00"))
        self.other_expense_items = kwargs.get("other_expense_items") or []

        self.can_map = bool(kwargs.get("can_map", True))
        self.is_v1_supported = bool(kwargs.get("is_v1_supported", True))
        self.can_file = bool(kwargs.get("can_file", True))
        self.needs_review = bool(kwargs.get("needs_review", False))

        self.blocking_errors = kwargs.get("blocking_errors") or []
        self.review_warnings = kwargs.get("review_warnings") or []

    def to_dict(self) -> Dict[str, Any]:
        def to_float(val):
            return float(val) if isinstance(val, Decimal) else val
        
        res = {}
        for k, v in self.__dict__.items():
            if k in ["blocking_errors", "review_warnings"]:
                res[k] = [x.to_dict() if hasattr(x, "to_dict") else x for x in v]
            elif k == "other_expense_items":
                res[k] = [x.to_dict() if hasattr(x, "to_dict") else x for x in v]
            else:
                res[k] = to_float(v)
        return res
