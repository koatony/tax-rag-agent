# =====================================================================
# 說明: 本檔案定義 Schedule 1 (Form 1040) V1 引擎之 Layer 1 (原始輸入模型)
# 與 Layer 3 (表面結果模型)，格式參考 processors/models/schedule_b.py。
# 依據 docs/how_to_fill_forms_docs/schedule_1/schedule1_complete.md 撰寫。
# =====================================================================

from decimal import Decimal
from typing import Dict, Any, List, Optional


class OtherIncomeItemV1:
    """
    [Layer 1] Part I Line 8a-8z 其他所得項目模型 (Other Income Item Model)
    """
    def __init__(self, **kwargs):
        self.item_id = str(kwargs.get("item_id", ""))
        self.line_code = kwargs.get("line_code")
        self.description = kwargs.get("description")

        amt_val = kwargs.get("amount")
        self.amount = Decimal(str(amt_val)) if amt_val is not None else Decimal("0.00")

        self.is_negative_adjustment = bool(kwargs.get("is_negative_adjustment", False))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "line_code": self.line_code,
            "description": self.description,
            "amount": float(self.amount),
            "is_negative_adjustment": self.is_negative_adjustment,
        }


class AdjustmentItemV1:
    """
    [Layer 1] Part II Line 11-23、24a-24z 收入調整項目模型 (Adjustment Item Model)
    """
    def __init__(self, **kwargs):
        self.item_id = str(kwargs.get("item_id", ""))
        self.line_code = kwargs.get("line_code")
        self.description = kwargs.get("description")

        amt_val = kwargs.get("amount")
        self.amount = Decimal(str(amt_val)) if amt_val is not None else Decimal("0.00")

        # 扣除資格是否已驗證確認（預設為 True；若憑證僅提供存入/支出金額未驗證資格，寫入 False）
        deduct_val = kwargs.get("is_deductibility_confirmed")
        self.is_deductibility_confirmed = bool(deduct_val) if deduct_val is not None else True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "line_code": self.line_code,
            "description": self.description,
            "amount": float(self.amount),
            "is_deductibility_confirmed": self.is_deductibility_confirmed,
        }


class SpecialCaseFlags1V1:
    """
    [Layer 1] 特殊案件標籤模型 (Special Case Flags)

    定義 V1 引擎不支援的各類 Schedule 1 特殊申報情況（需另行計算之附屬表單）。
    若任一旗標為 True，核心引擎將會拋出阻斷錯誤 (blocking error)。
    """
    def __init__(self, **kwargs):
        self.has_schedule_f_income = bool(kwargs.get("has_schedule_f_income", False))                          # Line 6 農場所得
        self.has_form_4797_or_4684 = bool(kwargs.get("has_form_4797_or_4684", False))                          # Line 4 其他利得或虧損
        self.has_schedule_se_deduction = bool(kwargs.get("has_schedule_se_deduction", False))                  # Line 15 自雇稅可扣除部分
        self.has_form_2106 = bool(kwargs.get("has_form_2106", False))                                          # Line 12
        self.has_form_3903 = bool(kwargs.get("has_form_3903", False))                                          # Line 14
        self.has_form_8889 = bool(kwargs.get("has_form_8889", False))                                          # Line 13 / 8f
        self.has_form_8853 = bool(kwargs.get("has_form_8853", False))                                          # Line 8e
        self.has_archer_msa_deduction = bool(kwargs.get("has_archer_msa_deduction", False))                    # Line 23
        self.has_form_2555 = bool(kwargs.get("has_form_2555", False))                                          # Line 8d / 24j
        self.has_digital_assets_income = bool(kwargs.get("has_digital_assets_income", False))                  # Line 8v
        self.has_nonqualified_deferred_comp = bool(kwargs.get("has_nonqualified_deferred_comp", False))        # Line 8t
        self.has_incarcerated_wages = bool(kwargs.get("has_incarcerated_wages", False))                        # Line 8u
        self.has_able_account_distribution = bool(kwargs.get("has_able_account_distribution", False))          # Line 8q
        self.has_medicaid_waiver_adjustment = bool(kwargs.get("has_medicaid_waiver_adjustment", False))        # Line 8s
        self.has_section_951_inclusion = bool(kwargs.get("has_section_951_inclusion", False))                  # Line 8n / 8o
        self.has_excess_business_loss_adjustment = bool(kwargs.get("has_excess_business_loss_adjustment", False))  # Line 8p
        self.has_k1_section_67e_deduction = bool(kwargs.get("has_k1_section_67e_deduction", False))            # Line 24k

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_schedule_f_income": self.has_schedule_f_income,
            "has_form_4797_or_4684": self.has_form_4797_or_4684,
            "has_schedule_se_deduction": self.has_schedule_se_deduction,
            "has_form_2106": self.has_form_2106,
            "has_form_3903": self.has_form_3903,
            "has_form_8889": self.has_form_8889,
            "has_form_8853": self.has_form_8853,
            "has_archer_msa_deduction": self.has_archer_msa_deduction,
            "has_form_2555": self.has_form_2555,
            "has_digital_assets_income": self.has_digital_assets_income,
            "has_nonqualified_deferred_comp": self.has_nonqualified_deferred_comp,
            "has_incarcerated_wages": self.has_incarcerated_wages,
            "has_able_account_distribution": self.has_able_account_distribution,
            "has_medicaid_waiver_adjustment": self.has_medicaid_waiver_adjustment,
            "has_section_951_inclusion": self.has_section_951_inclusion,
            "has_excess_business_loss_adjustment": self.has_excess_business_loss_adjustment,
            "has_k1_section_67e_deduction": self.has_k1_section_67e_deduction,
        }


class Schedule1InputsV1:
    """
    [Layer 1] Schedule 1 總體輸入模型

    將 LLM 從文件抽取的結果進行強型別映射與封裝。它是 Layer 2 計算引擎接收的唯一輸入參數型別。
    """
    def __init__(self, **kwargs):
        self.taxpayer_name = str(kwargs.get("taxpayer_name", ""))
        self.taxpayer_ssn = str(kwargs.get("taxpayer_ssn", ""))
        ty = kwargs.get("tax_year")
        try:
            self.tax_year = int(float(ty)) if ty is not None else None
        except (ValueError, TypeError):
            self.tax_year = None

        fk_val = kwargs.get("form_1099k_error_or_personal_loss_amount")
        self.form_1099k_error_or_personal_loss_amount = Decimal(str(fk_val)) if fk_val is not None else Decimal("0.00")

        self.line_1_state_local_tax_refund = Decimal(str(kwargs.get("line_1_state_local_tax_refund", "0.00")))
        self.line_2a_alimony_received = Decimal(str(kwargs.get("line_2a_alimony_received", "0.00")))
        self.line_2b_original_agreement_date = kwargs.get("line_2b_original_agreement_date")

        sc_val = kwargs.get("schedule_c_line_31")
        self.schedule_c_line_31 = Decimal(str(sc_val)) if sc_val is not None else None

        self.line_4_other_gains_or_losses = Decimal(str(kwargs.get("line_4_other_gains_or_losses", "0.00")))

        se_val = kwargs.get("schedule_e_line_41")
        self.schedule_e_line_41 = Decimal(str(se_val)) if se_val is not None else None

        self.line_6_farm_income = Decimal(str(kwargs.get("line_6_farm_income", "0.00")))

        self.line_7_unemployment_compensation = Decimal(str(kwargs.get("line_7_unemployment_compensation", "0.00")))
        self.line_7_repaid_overpayment_flag = bool(kwargs.get("line_7_repaid_overpayment_flag", False))
        repaid_val = kwargs.get("line_7_repaid_overpayment_amount")
        self.line_7_repaid_overpayment_amount = Decimal(str(repaid_val)) if repaid_val is not None else None

        # 映射 Part I Line 8a-8z 其他所得明細項目列表 (若缺失 item_id 則以 index 自動生成)
        other_income_items = []
        for idx, x in enumerate(kwargs.get("other_income_items", [])):
            if isinstance(x, dict):
                if not x.get("item_id"):
                    x = dict(x)
                    x["item_id"] = f"other_income_{idx}"
                other_income_items.append(OtherIncomeItemV1(**x))
            else:
                other_income_items.append(x)
        self.other_income_items = other_income_items

        # 注意：Line 19a (Alimony paid)、Line 20 (IRA deduction)、Line 21 (Student loan interest
        # deduction) 的金額一律透過 adjustment_items（line_code = "19a"/"20"/"21"）表達，不再提供
        # 獨立的 scalar 欄位，避免出現「兩處資料來源、只有一處被計算引擎讀取」的不一致風險。
        self.line_19b_recipient_ssn = kwargs.get("line_19b_recipient_ssn")
        self.line_19c_original_agreement_date = kwargs.get("line_19c_original_agreement_date")
        self.line_20_mfs_lived_apart_flag = bool(kwargs.get("line_20_mfs_lived_apart_flag", False))

        # 映射 Part II Line 11-23、24a-24z 收入調整明細項目列表 (若缺失 item_id 則以 index 自動生成)
        adjustment_items = []
        for idx, x in enumerate(kwargs.get("adjustment_items", [])):
            if isinstance(x, dict):
                if not x.get("item_id"):
                    x = dict(x)
                    x["item_id"] = f"adjustment_{idx}"
                adjustment_items.append(AdjustmentItemV1(**x))
            else:
                adjustment_items.append(x)
        self.adjustment_items = adjustment_items

        # 映射不支援特殊案件的 flag 控制
        flags = kwargs.get("special_case_flags")
        self.special_case_flags = SpecialCaseFlags1V1(**flags) if isinstance(flags, dict) else flags if flags else SpecialCaseFlags1V1()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Schedule1InputsV1":
        """
        [工廠方法] 將來自 LLM 解析的原始 Dict / JSON 直接加載轉換成 Schedule1InputsV1 物件。
        """
        return cls(**data)


class Schedule1ResultV1:
    """
    [Layer 3] Schedule 1 最終申報結果模型 (Surface Output Model)

    封裝核心計算完成後的輸出資料。每個屬性在意義上皆高度對齊 IRS 實體 Schedule 1 表單上的指定位置與申報檢驗旗標。
    """
    def __init__(self, **kwargs):
        self.taxpayer_name = kwargs.get("taxpayer_name", "")
        self.taxpayer_ssn_masked = kwargs.get("taxpayer_ssn_masked", "")
        ty = kwargs.get("tax_year")
        try:
            self.tax_year = int(float(ty)) if ty is not None else None
        except (ValueError, TypeError):
            self.tax_year = None

        # --- 表頭揭露欄位 (僅供揭露，不計入任何加總) ---
        self.form_1099k_error_or_personal_loss_amount = kwargs.get("form_1099k_error_or_personal_loss_amount", Decimal("0.00"))

        # --- Part I: Additional Income ---
        self.line_1_state_local_tax_refund = kwargs.get("line_1_state_local_tax_refund", Decimal("0.00"))
        self.line_2a_alimony_received = kwargs.get("line_2a_alimony_received", Decimal("0.00"))
        self.line_2b_original_agreement_date = kwargs.get("line_2b_original_agreement_date")
        self.line_3_business_income = kwargs.get("line_3_business_income", Decimal("0.00"))       # 引用已完成 Schedule C Line 31
        self.line_4_other_gains_or_losses = kwargs.get("line_4_other_gains_or_losses", Decimal("0.00"))
        self.line_5_rental_royalty_income = kwargs.get("line_5_rental_royalty_income", Decimal("0.00"))  # 引用已完成 Schedule E Line 41
        self.line_6_farm_income = kwargs.get("line_6_farm_income", Decimal("0.00"))
        self.line_7_unemployment_compensation = kwargs.get("line_7_unemployment_compensation", Decimal("0.00"))

        self.other_income_entries = kwargs.get("other_income_entries") or []  # Line 8a-8z 明細
        self.line_9_total_other_income = kwargs.get("line_9_total_other_income", Decimal("0.00"))  # Line 9
        self.line_10_additional_income = kwargs.get("line_10_additional_income", Decimal("0.00"))  # Line 10 -> Form 1040 Line 8

        # --- Part II: Adjustments to Income ---
        self.line_19b_recipient_ssn = kwargs.get("line_19b_recipient_ssn")
        self.line_19c_original_agreement_date = kwargs.get("line_19c_original_agreement_date")
        self.adjustment_entries = kwargs.get("adjustment_entries") or []      # Line 11-23、24a-24z 明細
        self.line_25_total_other_adjustments = kwargs.get("line_25_total_other_adjustments", Decimal("0.00"))  # Line 25
        self.line_26_adjustments_to_income = kwargs.get("line_26_adjustments_to_income", Decimal("0.00"))      # Line 26 -> Form 1040 Line 10

        # --- 申報判定旗標 ---
        self.is_schedule_1_required = bool(kwargs.get("is_schedule_1_required", False))

        # --- 引擎執行狀態與錯誤元數據 ---
        self.blocking_errors = kwargs.get("blocking_errors") or []
        self.review_warnings = kwargs.get("review_warnings") or []
        self.blocking_validation_error = bool(kwargs.get("blocking_validation_error", False))
        self.is_v1_supported = bool(kwargs.get("is_v1_supported", True))
        self.can_file = bool(kwargs.get("can_file", True))
        self.should_attach_schedule_1 = bool(kwargs.get("should_attach_schedule_1", False))

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
            "tax_year": self.tax_year,
            "form_1099k_error_or_personal_loss_amount": to_float(self.form_1099k_error_or_personal_loss_amount),
            "line_1_state_local_tax_refund": to_float(self.line_1_state_local_tax_refund),
            "line_2a_alimony_received": to_float(self.line_2a_alimony_received),
            "line_2b_original_agreement_date": self.line_2b_original_agreement_date,
            "line_3_business_income": to_float(self.line_3_business_income),
            "line_4_other_gains_or_losses": to_float(self.line_4_other_gains_or_losses),
            "line_5_rental_royalty_income": to_float(self.line_5_rental_royalty_income),
            "line_6_farm_income": to_float(self.line_6_farm_income),
            "line_7_unemployment_compensation": to_float(self.line_7_unemployment_compensation),
            "other_income_entries": [convert_item(x) for x in self.other_income_entries],
            "line_9_total_other_income": to_float(self.line_9_total_other_income),
            "line_10_additional_income": to_float(self.line_10_additional_income),
            "line_19b_recipient_ssn": self.line_19b_recipient_ssn,
            "line_19c_original_agreement_date": self.line_19c_original_agreement_date,
            "adjustment_entries": [convert_item(x) for x in self.adjustment_entries],
            "line_25_total_other_adjustments": to_float(self.line_25_total_other_adjustments),
            "line_26_adjustments_to_income": to_float(self.line_26_adjustments_to_income),
            "is_schedule_1_required": self.is_schedule_1_required,
            "blocking_errors": [err.to_dict() if hasattr(err, "to_dict") else err for err in self.blocking_errors],
            "review_warnings": [warn.to_dict() if hasattr(warn, "to_dict") else warn for warn in self.review_warnings],
            "blocking_validation_error": self.blocking_validation_error,
            "is_v1_supported": self.is_v1_supported,
            "can_file": self.can_file,
            "should_attach_schedule_1": self.should_attach_schedule_1,
        }
