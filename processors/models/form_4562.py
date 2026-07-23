# =====================================================================
# 說明: 本檔案定義 Form 4562 (Depreciation and Amortization) V1 引擎之
# Layer 1 (原始輸入模型) 與 Layer 3 (表面結果模型)，格式參考 processors/models/schedule_b.py。
# 依據 docs/how_to_fill_forms_docs/Form4562/form4562_complete.md 撰寫。
# =====================================================================

from decimal import Decimal
from typing import Dict, Any, List, Optional


class Section179ItemV1:
    """
    [Layer 1] Part I Line 6 Section 179 財產項目模型 (Section 179 Property Item Model)
    """
    def __init__(self, **kwargs):
        self.item_id = str(kwargs.get("item_id", ""))
        self.description = kwargs.get("description")

        cost_val = kwargs.get("cost_business_use_only")
        self.cost_business_use_only = Decimal(str(cost_val)) if cost_val is not None else Decimal("0.00")

        elected_val = kwargs.get("elected_cost")
        self.elected_cost = Decimal(str(elected_val)) if elected_val is not None else Decimal("0.00")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "description": self.description,
            "cost_business_use_only": float(self.cost_business_use_only),
            "elected_cost": float(self.elected_cost),
        }


class MACRSItemV1:
    """
    [Layer 1] Part III Section B/C MACRS 資產折舊項目模型 (MACRS Item Model)

    V1 僅接收已計算完成之 depreciation_deduction 最終值，不自行依 MACRS 折舊率表推算。
    """
    def __init__(self, **kwargs):
        self.item_id = str(kwargs.get("item_id", ""))
        self.line_code = kwargs.get("line_code")  # "19a"-"19j" (GDS) | "20a"-"20e" (ADS)
        self.classification = kwargs.get("classification")
        self.month_year_placed_in_service = kwargs.get("month_year_placed_in_service")

        basis_val = kwargs.get("depreciation_basis")
        self.depreciation_basis = Decimal(str(basis_val)) if basis_val is not None else None

        self.recovery_period = kwargs.get("recovery_period")
        self.convention = kwargs.get("convention")
        self.method = kwargs.get("method")

        dep_val = kwargs.get("depreciation_deduction")
        self.depreciation_deduction = Decimal(str(dep_val)) if dep_val is not None else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "line_code": self.line_code,
            "classification": self.classification,
            "month_year_placed_in_service": self.month_year_placed_in_service,
            "depreciation_basis": float(self.depreciation_basis) if self.depreciation_basis is not None else None,
            "recovery_period": self.recovery_period,
            "convention": self.convention,
            "method": self.method,
            "depreciation_deduction": float(self.depreciation_deduction) if self.depreciation_deduction is not None else None,
        }


class SpecialCaseFlags4562V1:
    """
    [Layer 1] 特殊案件標籤模型 (Special Case Flags)

    定義 V1 引擎不支援的各類 Form 4562 特殊申報情況。
    若任一旗標為 True，核心引擎將會拋出阻斷錯誤 (blocking error)。
    """
    def __init__(self, **kwargs):
        self.has_listed_property = bool(kwargs.get("has_listed_property", False))                                          # Part V Lines 24-29
        self.has_vehicle_business_use_questions = bool(kwargs.get("has_vehicle_business_use_questions", False))            # Part V Section B (Lines 30-36)
        self.has_employer_vehicle_exemption_questions = bool(kwargs.get("has_employer_vehicle_exemption_questions", False))  # Part V Section C (Lines 37-41)
        self.has_amortization = bool(kwargs.get("has_amortization", False))                                                 # Part VI (Lines 42-44)
        self.has_263a_capitalization_calculation_needed = bool(kwargs.get("has_263a_capitalization_calculation_needed", False))  # Line 23a/23b
        self.has_unquantified_prior_year_depreciation = bool(kwargs.get("has_unquantified_prior_year_depreciation", False))  # 偵測到折舊資產（基礎/投入使用日期）但缺已計算完成之折舊金額

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_listed_property": self.has_listed_property,
            "has_vehicle_business_use_questions": self.has_vehicle_business_use_questions,
            "has_employer_vehicle_exemption_questions": self.has_employer_vehicle_exemption_questions,
            "has_amortization": self.has_amortization,
            "has_263a_capitalization_calculation_needed": self.has_263a_capitalization_calculation_needed,
            "has_unquantified_prior_year_depreciation": self.has_unquantified_prior_year_depreciation,
        }


class Form4562InputsV1:
    """
    [Layer 1] Form 4562 總體輸入模型

    將 LLM 從文件抽取的結果進行強型別映射與封裝。它是 Layer 2 計算引擎接收的唯一輸入參數型別。
    """
    def __init__(self, **kwargs):
        self.taxpayer_name = str(kwargs.get("taxpayer_name", ""))
        self.taxpayer_ssn = str(kwargs.get("taxpayer_ssn", ""))
        self.business_activity_name = str(kwargs.get("business_activity_name", ""))
        ty = kwargs.get("tax_year")
        try:
            self.tax_year = int(float(ty)) if ty is not None else None
        except (ValueError, TypeError):
            self.tax_year = None

        self.line_1_section_179_max_amount = Decimal(str(kwargs.get("line_1_section_179_max_amount", "0.00")))
        self.line_2_section_179_property_cost = Decimal(str(kwargs.get("line_2_section_179_property_cost", "0.00")))
        self.line_3_section_179_threshold_cost = Decimal(str(kwargs.get("line_3_section_179_threshold_cost", "0.00")))

        # 映射 Line 6 Section 179 財產明細列表 (若缺失 item_id 則以 index 自動生成)
        section_179_items = []
        for idx, x in enumerate(kwargs.get("section_179_property_items", [])):
            if isinstance(x, dict):
                if not x.get("item_id"):
                    x = dict(x)
                    x["item_id"] = f"section_179_{idx}"
                section_179_items.append(Section179ItemV1(**x))
            else:
                section_179_items.append(x)
        self.section_179_property_items = section_179_items

        line7_val = kwargs.get("line_7_listed_property_section_179_cost")
        self.line_7_listed_property_section_179_cost = Decimal(str(line7_val)) if line7_val is not None else None

        self.line_10_carryover_disallowed_deduction = Decimal(str(kwargs.get("line_10_carryover_disallowed_deduction", "0.00")))
        self.line_11_business_income_limitation = Decimal(str(kwargs.get("line_11_business_income_limitation", "0.00")))

        self.line_14_special_depreciation_allowance = Decimal(str(kwargs.get("line_14_special_depreciation_allowance", "0.00")))
        self.line_15_section_168f1_election = Decimal(str(kwargs.get("line_15_section_168f1_election", "0.00")))
        self.line_16_other_depreciation = Decimal(str(kwargs.get("line_16_other_depreciation", "0.00")))

        self.line_17_macrs_prior_years = Decimal(str(kwargs.get("line_17_macrs_prior_years", "0.00")))
        self.line_18_general_asset_account_election = bool(kwargs.get("line_18_general_asset_account_election", False))

        # 映射 Part III Section B (GDS) MACRS 資產明細列表 (若缺失 item_id 則以 index 自動生成)
        macrs_gds_items = []
        for idx, x in enumerate(kwargs.get("macrs_gds_items", [])):
            if isinstance(x, dict):
                if not x.get("item_id"):
                    x = dict(x)
                    x["item_id"] = f"macrs_gds_{idx}"
                macrs_gds_items.append(MACRSItemV1(**x))
            else:
                macrs_gds_items.append(x)
        self.macrs_gds_items = macrs_gds_items

        # 映射 Part III Section C (ADS) MACRS 資產明細列表 (若缺失 item_id 則以 index 自動生成)
        macrs_ads_items = []
        for idx, x in enumerate(kwargs.get("macrs_ads_items", [])):
            if isinstance(x, dict):
                if not x.get("item_id"):
                    x = dict(x)
                    x["item_id"] = f"macrs_ads_{idx}"
                macrs_ads_items.append(MACRSItemV1(**x))
            else:
                macrs_ads_items.append(x)
        self.macrs_ads_items = macrs_ads_items

        interest_val = kwargs.get("amortization_costs_263a_interest")
        self.amortization_costs_263a_interest = Decimal(str(interest_val)) if interest_val is not None else None

        other_val = kwargs.get("amortization_costs_263a_other")
        self.amortization_costs_263a_other = Decimal(str(other_val)) if other_val is not None else None

        # 映射不支援特殊案件的 flag 控制
        flags = kwargs.get("special_case_flags")
        self.special_case_flags = SpecialCaseFlags4562V1(**flags) if isinstance(flags, dict) else flags if flags else SpecialCaseFlags4562V1()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Form4562InputsV1":
        """
        [工廠方法] 將來自 LLM 解析的原始 Dict / JSON 直接加載轉換成 Form4562InputsV1 物件。
        """
        return cls(**data)


class Form4562ResultV1:
    """
    [Layer 3] Form 4562 最終申報結果模型 (Surface Output Model)

    封裝核心計算完成後的輸出資料。每個屬性在意義上皆高度對齊 IRS 實體 Form 4562 表單上的指定位置與申報檢驗旗標。
    """
    def __init__(self, **kwargs):
        self.taxpayer_name = kwargs.get("taxpayer_name", "")
        self.taxpayer_ssn_masked = kwargs.get("taxpayer_ssn_masked", "")
        self.business_activity_name = kwargs.get("business_activity_name", "")
        ty = kwargs.get("tax_year")
        try:
            self.tax_year = int(float(ty)) if ty is not None else None
        except (ValueError, TypeError):
            self.tax_year = None

        # --- Part I: Election To Expense Certain Property Under Section 179 ---
        self.line_1_section_179_max_amount = kwargs.get("line_1_section_179_max_amount", Decimal("0.00"))
        self.line_2_section_179_property_cost = kwargs.get("line_2_section_179_property_cost", Decimal("0.00"))
        self.line_3_section_179_threshold_cost = kwargs.get("line_3_section_179_threshold_cost", Decimal("0.00"))
        self.line_4_reduction_in_limitation = kwargs.get("line_4_reduction_in_limitation", Decimal("0.00"))
        self.line_5_dollar_limitation = kwargs.get("line_5_dollar_limitation", Decimal("0.00"))
        self.section_179_entries = kwargs.get("section_179_entries") or []
        self.line_6_elected_cost_subtotal = kwargs.get("line_6_elected_cost_subtotal", Decimal("0.00"))
        self.line_7_listed_property_section_179_cost = kwargs.get("line_7_listed_property_section_179_cost", Decimal("0.00"))
        self.line_8_total_elected_cost = kwargs.get("line_8_total_elected_cost", Decimal("0.00"))
        self.line_9_tentative_deduction = kwargs.get("line_9_tentative_deduction", Decimal("0.00"))
        self.line_10_carryover_disallowed_deduction = kwargs.get("line_10_carryover_disallowed_deduction", Decimal("0.00"))
        self.line_11_surface_value = kwargs.get("line_11_surface_value", Decimal("0.00"))
        self.line_12_section_179_expense_deduction = kwargs.get("line_12_section_179_expense_deduction", Decimal("0.00"))
        self.line_13_carryover_to_next_year = kwargs.get("line_13_carryover_to_next_year", Decimal("0.00"))

        # --- Part II: Special Depreciation Allowance and Other Depreciation ---
        self.line_14_special_depreciation_allowance = kwargs.get("line_14_special_depreciation_allowance", Decimal("0.00"))
        self.line_15_section_168f1_election = kwargs.get("line_15_section_168f1_election", Decimal("0.00"))
        self.line_16_other_depreciation = kwargs.get("line_16_other_depreciation", Decimal("0.00"))

        # --- Part III: MACRS Depreciation ---
        self.line_17_macrs_prior_years = kwargs.get("line_17_macrs_prior_years", Decimal("0.00"))
        self.line_18_general_asset_account_election = bool(kwargs.get("line_18_general_asset_account_election", False))
        self.macrs_gds_entries = kwargs.get("macrs_gds_entries") or []
        self.line_19_gds_total = kwargs.get("line_19_gds_total", Decimal("0.00"))
        self.macrs_ads_entries = kwargs.get("macrs_ads_entries") or []
        self.line_20_ads_total = kwargs.get("line_20_ads_total", Decimal("0.00"))

        # --- Part IV: Summary ---
        self.line_21_listed_property_summary = kwargs.get("line_21_listed_property_summary", Decimal("0.00"))
        self.line_22_total_depreciation_and_amortization = kwargs.get("line_22_total_depreciation_and_amortization", Decimal("0.00"))
        self.line_23a_263a_interest = kwargs.get("line_23a_263a_interest")
        self.line_23b_263a_other = kwargs.get("line_23b_263a_other")

        # --- 申報判定旗標 ---
        self.is_form_4562_required = bool(kwargs.get("is_form_4562_required", False))

        # --- 引擎執行狀態與錯誤元數據 ---
        self.blocking_errors = kwargs.get("blocking_errors") or []
        self.review_warnings = kwargs.get("review_warnings") or []
        self.blocking_validation_error = bool(kwargs.get("blocking_validation_error", False))
        self.is_v1_supported = bool(kwargs.get("is_v1_supported", True))
        self.can_file = bool(kwargs.get("can_file", True))
        self.should_attach_form_4562 = bool(kwargs.get("should_attach_form_4562", False))

    def to_dict(self) -> Dict[str, Any]:
        def to_float(val):
            if isinstance(val, Decimal):
                return float(val)
            return val

        def convert_item(item):
            if hasattr(item, "to_dict"):
                return item.to_dict()
            return item

        return {
            "taxpayer_name": self.taxpayer_name,
            "taxpayer_ssn_masked": self.taxpayer_ssn_masked,
            "business_activity_name": self.business_activity_name,
            "tax_year": self.tax_year,
            "line_1_section_179_max_amount": to_float(self.line_1_section_179_max_amount),
            "line_2_section_179_property_cost": to_float(self.line_2_section_179_property_cost),
            "line_3_section_179_threshold_cost": to_float(self.line_3_section_179_threshold_cost),
            "line_4_reduction_in_limitation": to_float(self.line_4_reduction_in_limitation),
            "line_5_dollar_limitation": to_float(self.line_5_dollar_limitation),
            "section_179_entries": [convert_item(x) for x in self.section_179_entries],
            "line_6_elected_cost_subtotal": to_float(self.line_6_elected_cost_subtotal),
            "line_7_listed_property_section_179_cost": to_float(self.line_7_listed_property_section_179_cost),
            "line_8_total_elected_cost": to_float(self.line_8_total_elected_cost),
            "line_9_tentative_deduction": to_float(self.line_9_tentative_deduction),
            "line_10_carryover_disallowed_deduction": to_float(self.line_10_carryover_disallowed_deduction),
            "line_11_surface_value": to_float(self.line_11_surface_value),
            "line_12_section_179_expense_deduction": to_float(self.line_12_section_179_expense_deduction),
            "line_13_carryover_to_next_year": to_float(self.line_13_carryover_to_next_year),
            "line_14_special_depreciation_allowance": to_float(self.line_14_special_depreciation_allowance),
            "line_15_section_168f1_election": to_float(self.line_15_section_168f1_election),
            "line_16_other_depreciation": to_float(self.line_16_other_depreciation),
            "line_17_macrs_prior_years": to_float(self.line_17_macrs_prior_years),
            "line_18_general_asset_account_election": self.line_18_general_asset_account_election,
            "macrs_gds_entries": [convert_item(x) for x in self.macrs_gds_entries],
            "line_19_gds_total": to_float(self.line_19_gds_total),
            "macrs_ads_entries": [convert_item(x) for x in self.macrs_ads_entries],
            "line_20_ads_total": to_float(self.line_20_ads_total),
            "line_21_listed_property_summary": to_float(self.line_21_listed_property_summary),
            "line_22_total_depreciation_and_amortization": to_float(self.line_22_total_depreciation_and_amortization),
            "line_23a_263a_interest": to_float(self.line_23a_263a_interest),
            "line_23b_263a_other": to_float(self.line_23b_263a_other),
            "is_form_4562_required": self.is_form_4562_required,
            "blocking_errors": [err.to_dict() if hasattr(err, "to_dict") else err for err in self.blocking_errors],
            "review_warnings": [warn.to_dict() if hasattr(warn, "to_dict") else warn for warn in self.review_warnings],
            "blocking_validation_error": self.blocking_validation_error,
            "is_v1_supported": self.is_v1_supported,
            "can_file": self.can_file,
            "should_attach_form_4562": self.should_attach_form_4562,
        }
