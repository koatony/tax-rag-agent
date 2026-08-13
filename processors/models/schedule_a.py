# =====================================================================
# REVIEW 重點 1: 金融與非金融領域之「精確度防禦」 (Precision Defense)
# =====================================================================
# 【為什麼一定要用 Decimal 運算，而非 float？】
# 1. 浮點數精度損失（Floating-Point Precision Loss）：在電腦底層中，二進制浮點數無法精確表示
#    十進位的小數（例如 0.1 + 0.2 在 float 計算下會得到 0.30000000000000004）。
# 2. 如果系統涉及計費（Billing）、購物車金額結算、點數折抵、甚至統計報表，累積誤差會造成帳目不對。
# 3. 解決方案：Python 中的 `Decimal` 類別能精確模擬人類的手算十進位。
# 4. ⚠️ 坑點：直接寫 `Decimal(0.1)` 仍然是錯的，因為 0.1 已經先被 Python 解析為不精確的 float。
#    必須寫成字串形式 `Decimal("0.1")`，這也是本檔案中 `Decimal(str(...))` 轉換的原理。
# =====================================================================

import os
import json
from typing import Dict, Any, List, Optional
from decimal import Decimal

# 動態解析相對路徑，確保不論在哪個路徑下執行均正確
current_dir = os.path.dirname(os.path.abspath(__file__))
TAX_RATES_PATH = os.path.abspath(os.path.join(current_dir, "..", "..", "docs", "how_to_fill_forms_docs", "schedule_a", "schedule_a_tax_rates.json"))

def load_tax_rates(tax_year: int) -> Dict[str, Any]:
    """根據申報年度 (tax_year) 動態載入對應年份的稅率與限制常數。"""
    with open(TAX_RATES_PATH, "r", encoding="utf-8") as f:
        all_rates = json.load(f)
    year_key = str(int(tax_year))
    if year_key not in all_rates:
        return all_rates["2025"]
    return all_rates[year_key]


class MedicalExpenseItemV1:
    """
    醫療費用明細模型 (Medical Expense Item).
    用於申報人填報或從憑證中提取的單筆醫療/牙醫支出。
    計算時會加總所有合規項目並扣除補償(Reimbursement)，最後在 Line 1 進行 AGI 7.5% 的門檻計算。
    """
    def __init__(
        self,
        item_id: str = "",
        source_document_id: Optional[str] = None,
        description: Optional[str] = None,
        paid_in_tax_year: Optional[bool] = None,
        taxpayer_paid_amount: Decimal = Decimal("0.00"),
        reimbursement_amount: Decimal = Decimal("0.00"),
        tax_free_medical_account_payment: Decimal = Decimal("0.00"),
        eligible_person_status: str = "UNKNOWN",
        medical_qualification_status: str = "UNKNOWN"
    ):
        self.item_id = item_id
        self.source_document_id = source_document_id
        self.description = description
        self.paid_in_tax_year = paid_in_tax_year
        self.taxpayer_paid_amount = taxpayer_paid_amount
        self.reimbursement_amount = reimbursement_amount
        self.tax_free_medical_account_payment = tax_free_medical_account_payment
        self.eligible_person_status = eligible_person_status
        self.medical_qualification_status = medical_qualification_status

    @classmethod
    def from_dict(cls, m: Dict[str, Any], tax_year: int) -> "MedicalExpenseItemV1":
        item_id = str(m.get("item_id") or "")
        paid_amt = Decimal(str(m.get("taxpayer_paid_amount") or m.get("patient_paid_amount") or "0.00"))
        reimb = Decimal(str(m.get("reimbursement_amount") or m.get("reimbursement_received") or "0.00"))
        
        hsa_fsa = Decimal(str(m.get("tax_free_medical_account_payment") or 
                              m.get("paid_by_hsa_msa_fsa_hra_cafeteria_plan_amount") or 
                              m.get("paid_by_hsa_msa_fsa_hra_cafeteria_plan") or 
                              m.get("paid_by_hsa_msa_fsa_cafeteria_plan_amount") or 
                              m.get("paid_by_hsa_msa_fsa_cafeteria_plan") or "0.00"))
        
        paid_in_year = m.get("paid_in_tax_year")
        if paid_in_year is None:
            date_str = str(m.get("expense_paid_date") or "")
            if date_str:
                paid_in_year = date_str.startswith(str(tax_year))
            else:
                paid_in_year = True
                
        person = str(m.get("expense_person") or m.get("eligible_person_status") or "UNKNOWN").upper()
        if person in ("TAXPAYER", "SPOUSE", "DEPENDENT"):
            person_status = "ELIGIBLE"
        elif person == "NOT_ELIGIBLE":
            person_status = "NOT_ELIGIBLE"
        elif person == "ELIGIBLE":
            person_status = "ELIGIBLE"
        else:
            person_status = "UNKNOWN"
            
        cat = str(m.get("expense_category") or m.get("medical_qualification_status") or "UNKNOWN").upper()
        if cat in ("MEDICAL", "DENTAL", "PRESCRIPTION_DRUGS", "OTHER_ELIGIBLE_MEDICAL_EXPENSE", 
                   "MEDICAL_INSURANCE", "MEDICAL_INSURANCE_PREMIUM", "DENTAL_INSURANCE_PREMIUM", 
                   "VISION_INSURANCE_PREMIUM", "QUALIFIED_SIMPLE"):
            qual_status = "QUALIFIED_SIMPLE"
        elif cat == "NOT_DEDUCTIBLE":
            qual_status = "NOT_DEDUCTIBLE"
        else:
            qual_status = "UNKNOWN"

        return cls(
            item_id=item_id,
            source_document_id=m.get("source_document_id") or m.get("source_document_reference"),
            description=m.get("description") or m.get("raw_description"),
            paid_in_tax_year=paid_in_year,
            taxpayer_paid_amount=paid_amt,
            reimbursement_amount=reimb,
            tax_free_medical_account_payment=hsa_fsa,
            eligible_person_status=person_status,
            medical_qualification_status=qual_status
        )


class TaxPaymentItemV1:
    """
    稅金支出明細模型 (Tax Payment Item).
    用於申報人已繳納的州稅與地方稅 (SALT)。
    會歸入對應的池中 (TaxPools)，最後加總並受限於 $10,000 / $5,000 (MFS) 的 SALT 上限限制。
    """
    def __init__(
        self,
        item_id: str = "",
        source_document_id: Optional[str] = None,
        description: Optional[str] = None,
        paid_in_tax_year: Optional[bool] = None,
        amount_paid: Decimal = Decimal("0.00"),
        separately_stated_nondeductible_charge: Decimal = Decimal("0.00"),
        tax_category: str = "UNKNOWN",
        personal_use_confirmed: Optional[bool] = None,
        actual_paid_to_taxing_authority_confirmed: Optional[bool] = None,
        value_based_and_annual_confirmed: Optional[bool] = None
    ):
        self.item_id = item_id
        self.source_document_id = source_document_id
        self.description = description
        self.paid_in_tax_year = paid_in_tax_year
        self.amount_paid = amount_paid
        self.separately_stated_nondeductible_charge = separately_stated_nondeductible_charge
        self.tax_category = tax_category
        self.personal_use_confirmed = personal_use_confirmed
        self.actual_paid_to_taxing_authority_confirmed = actual_paid_to_taxing_authority_confirmed
        self.value_based_and_annual_confirmed = value_based_and_annual_confirmed

    @classmethod
    def from_dict(cls, t: Dict[str, Any], tax_year: int) -> "TaxPaymentItemV1":
        item_id = str(t.get("item_id") or "")
        amt = Decimal(str(t.get("amount_paid") or "0.00"))
        
        sep_charge = Decimal(str(t.get("separately_stated_nondeductible_charge") or "0.00"))
        if "separately_stated_service_charge" in t or "separately_stated_improvement_assessment" in t:
            sep_charge += Decimal(str(t.get("separately_stated_service_charge") or "0.00"))
            sep_charge += Decimal(str(t.get("separately_stated_improvement_assessment") or "0.00"))
            
        paid_in_year = t.get("paid_in_tax_year")
        if paid_in_year is None:
            date_str = str(t.get("tax_paid_date") or "")
            if date_str:
                paid_in_year = date_str.startswith(str(tax_year))
            else:
                paid_in_year = True
                
        raw_cat = str(t.get("tax_category") or t.get("raw_tax_category_hint") or t.get("schedule_a_line_target") or "UNKNOWN").upper()
        if raw_cat in ("STATE_LOCAL_INCOME_TAX", "5A_INCOME_TAX", "STATE_INCOME_TAX", "LOCAL_INCOME_TAX"):
            cat = "STATE_LOCAL_INCOME_TAX"
        elif raw_cat in ("GENERAL_SALES_TAX", "5A_GENERAL_SALES_TAX"):
            cat = "GENERAL_SALES_TAX"
        elif raw_cat in ("PERSONAL_REAL_ESTATE_TAX", "5B_REAL_ESTATE_TAX", "REAL_ESTATE_TAX", "PROPERTY_TAX"):
            cat = "PERSONAL_REAL_ESTATE_TAX"
        elif raw_cat in ("PERSONAL_PROPERTY_TAX", "5C_PERSONAL_PROPERTY_TAX", "VEHICLE_VALUE_BASED_TAX"):
            cat = "PERSONAL_PROPERTY_TAX"
        elif raw_cat in ("FEDERAL_TAX", "FEDERAL_INCOME_TAX", "SOCIAL_SECURITY_TAX", "MEDICARE_TAX", "FEDERAL_OR_NONDEDUCTIBLE_TAX"):
            cat = "FEDERAL_OR_NONDEDUCTIBLE_TAX"
        elif raw_cat in ("BUSINESS_OR_RENTAL_TAX", "BUSINESS_TAX", "RENTAL_TAX"):
            cat = "BUSINESS_OR_RENTAL_TAX"
        else:
            cat = "UNKNOWN"
            
        pers_use = t.get("personal_use_confirmed")
        if pers_use is None:
            pers_use = t.get("tax_scope") == "personal" if "tax_scope" in t else True
            
        paid_authority = t.get("actual_paid_to_taxing_authority_confirmed")
        if paid_authority is None:
            desc_lower = (t.get("description") or "").lower()
            doc_id_lower = (t.get("source_document_id") or t.get("source_document_reference") or "").lower()
            if "escrow" in desc_lower or "1098" in desc_lower or "1098" in doc_id_lower:
                paid_authority = False
            else:
                paid_authority = True
            
        val_based = t.get("value_based_and_annual_confirmed")
        if val_based is None:
            val_based = True

        return cls(
            item_id=item_id,
            source_document_id=t.get("source_document_id") or t.get("source_document_reference"),
            description=t.get("description") or t.get("raw_description") or t.get("tax_name"),
            paid_in_tax_year=paid_in_year,
            amount_paid=amt,
            separately_stated_nondeductible_charge=sep_charge,
            tax_category=cat,
            personal_use_confirmed=pers_use,
            actual_paid_to_taxing_authority_confirmed=paid_authority,
            value_based_and_annual_confirmed=val_based
        )


class MortgageInterestItemV1:
    """
    自住房貸利息模型 (Mortgage Interest Item).
    代表 Form 1098 或是符合扣除條件的購屋貸款利息支出。
    目前 V1 只支援單筆且無超額限制的簡單房貸 (CONFIRMED_SIMPLE)。

    property_use_context 合法值：
        MAIN_HOME        - 納稅人主要住宅（可扣除）
        SECOND_HOME      - 第二自住宅（可扣除）
        RENTAL_PROPERTY  - 出租房產（不可列入 Schedule A，應走 Schedule E）
        BUSINESS_PROPERTY- 商業地產（不可列入 Schedule A，應走 Schedule C）
        UNKNOWN          - 不明，由 calculator 觸發警告
    """
    DEDUCTIBLE_CONTEXTS = {"MAIN_HOME", "SECOND_HOME"}
    NON_DEDUCTIBLE_CONTEXTS = {"RENTAL_PROPERTY", "BUSINESS_PROPERTY"}

    def __init__(
        self,
        item_id: str = "",
        source_document_id: Optional[str] = None,
        lender_name: Optional[str] = None,
        source_document_type: str = "FORM_1098",
        form_1098_box_1_mortgage_interest: Decimal = Decimal("0.00"),
        deductible_points_reported_on_1098: Decimal = Decimal("0.00"),
        paid_in_tax_year: Optional[bool] = None,
        simple_mortgage_status: str = "UNKNOWN",
        property_use_context: Optional[str] = None
    ):
        self.item_id = item_id
        self.source_document_id = source_document_id
        self.lender_name = lender_name
        self.source_document_type = source_document_type
        self.form_1098_box_1_mortgage_interest = form_1098_box_1_mortgage_interest
        self.deductible_points_reported_on_1098 = deductible_points_reported_on_1098
        self.paid_in_tax_year = paid_in_tax_year
        self.simple_mortgage_status = simple_mortgage_status
        # None 表示 LLM 未提供此欄位（視為 UNKNOWN，由 calculator 決策）
        self.property_use_context: Optional[str] = property_use_context

    @classmethod
    def from_dict(cls, mo: Dict[str, Any]) -> "MortgageInterestItemV1":
        item_id = str(mo.get("item_id") or "")
        paid_in_year = mo.get("paid_in_tax_year")
        if paid_in_year is None:
            paid_in_year = True
        status = mo.get("simple_mortgage_status") or "CONFIRMED_SIMPLE"
        raw_ctx = mo.get("property_use_context")
        property_use_context = str(raw_ctx).upper() if raw_ctx else None

        return cls(
            item_id=item_id,
            source_document_id=mo.get("source_document_id"),
            lender_name=mo.get("lender_name"),
            source_document_type=mo.get("source_document_type", "FORM_1098"),
            form_1098_box_1_mortgage_interest=Decimal(str(mo.get("form_1098_box_1_mortgage_interest") or "0.00")),
            deductible_points_reported_on_1098=Decimal(str(mo.get("deductible_points_reported_on_1098") or "0.00")),
            paid_in_tax_year=paid_in_year,
            simple_mortgage_status=status,
            property_use_context=property_use_context
        )


class CashCharityItemV1:
    """
    現金慈善捐贈模型 (Cash Charity Item).
    記錄向合格慈善機構的現金、支票或刷卡捐贈支出。
    校驗重點：
    1. 超過或等於 $250 時必須取得受贈機構出具的 Contemporaneous Written Acknowledgment。
    2. 必須確認組織合規狀態為 VERIFIED。
    3. 必須扣除取得的商品或服務價值 (Goods or Services Value)。
    """
    def __init__(
        self,
        item_id: str = "",
        source_document_id: Optional[str] = None,
        contribution_date: Optional[str] = None,
        paid_in_tax_year: Optional[bool] = None,
        organization_name: Optional[str] = None,
        qualified_organization_status: str = "UNKNOWN",
        contribution_method: str = "CASH",
        gross_contribution_amount: Decimal = Decimal("0.00"),
        goods_or_services_value: Decimal = Decimal("0.00"),
        bank_or_written_record_available: Optional[bool] = None,
        contemporaneous_acknowledgment_received: Optional[bool] = None
    ):
        self.item_id = item_id
        self.source_document_id = source_document_id
        self.contribution_date = contribution_date
        self.paid_in_tax_year = paid_in_tax_year
        self.organization_name = organization_name
        self.qualified_organization_status = qualified_organization_status
        self.contribution_method = contribution_method
        self.gross_contribution_amount = gross_contribution_amount
        self.goods_or_services_value = goods_or_services_value
        self.bank_or_written_record_available = bank_or_written_record_available
        self.contemporaneous_acknowledgment_received = contemporaneous_acknowledgment_received

    @classmethod
    def from_dict(cls, ch: Dict[str, Any]) -> "CashCharityItemV1":
        item_id = str(ch.get("item_id") or "")
        paid_in_year = ch.get("paid_in_tax_year")
        if paid_in_year is None:
            paid_in_year = True
        org_status = ch.get("qualified_organization_status") or "VERIFIED"
        
        return cls(
            item_id=item_id,
            source_document_id=ch.get("source_document_id"),
            contribution_date=ch.get("contribution_date"),
            paid_in_tax_year=paid_in_year,
            organization_name=ch.get("organization_name"),
            qualified_organization_status=org_status,
            contribution_method=ch.get("contribution_method", "CASH"),
            gross_contribution_amount=Decimal(str(ch.get("gross_contribution_amount") or "0.00")),
            goods_or_services_value=Decimal(str(ch.get("goods_or_services_value") or "0.00")),
            bank_or_written_record_available=ch.get("bank_or_written_record_available"),
            contemporaneous_acknowledgment_received=ch.get("contemporaneous_acknowledgment_received")
        )


class StandardDeductionReferenceV1:
    """
    標準扣除額參考配置 (Standard Deduction Reference).
    用於決定該申報人適用的標準扣除額基準，以及是否因特殊申報身份而強制列舉扣除。
    標準扣除額後面會動態載入
    """
    def __init__(
        self,
        standard_deduction_amount: Optional[Decimal] = None,
        must_itemize_due_to_mfs_spouse: Optional[bool] = None,
        elect_itemize_even_if_less: Optional[bool] = None
    ):
        self.standard_deduction_amount = standard_deduction_amount
        self.must_itemize_due_to_mfs_spouse = must_itemize_due_to_mfs_spouse
        self.elect_itemize_even_if_less = elect_itemize_even_if_less

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StandardDeductionReferenceV1":
        return cls(
            standard_deduction_amount=Decimal(str(data.get("standard_deduction_amount"))) if data.get("standard_deduction_amount") is not None else None,
            must_itemize_due_to_mfs_spouse=data.get("must_itemize_due_to_mfs_spouse"),
            elect_itemize_even_if_less=data.get("elect_itemize_even_if_less")
        )


class SpecialCaseFlagsV1:
    """
    特殊/複雜稅務場景標記 (Special Case Flags).
    由於 V1 引擎僅支援常規簡單列舉扣除，本類別包含多個布林標記，
    如果其中任何一項為 True，則會被視為不支援 (Unsupported) 的複雜情境並產生阻斷性錯誤 (Blocking Error)，
    以防止引擎產出錯誤的稅務計算。
    """
    def __init__(
        self,
        has_marketplace_medical_premium: bool = False,
        has_ltc_premium: bool = False,
        has_self_employed_health_insurance_overlap: bool = False,
        has_prior_year_medical_recovery: bool = False,
        sales_tax_amount_requires_calculation: bool = False,
        has_tax_refund_or_rebate_adjustment: bool = False,
        has_form_2555_or_4563_or_puerto_rico_exclusion: bool = False,
        has_other_tax_line_6: bool = False,
        has_multiple_mortgages: bool = False,
        mortgage_proceeds_not_all_qualified: bool = False,
        mortgage_limitation_required: bool = False,
        has_shared_mortgage: bool = False,
        has_non_1098_mortgage_interest: bool = False,
        has_non_1098_points: bool = False,
        has_seller_financed_mortgage: bool = False,
        has_form_8396_credit: bool = False,
        has_investment_interest: bool = False,
        has_noncash_charity: bool = False,
        has_charity_carryover: bool = False,
        has_charitable_agi_limitation: bool = False,
        has_casualty_or_theft_loss: bool = False,
        has_net_qualified_disaster_loss: bool = False,
        has_line_16_item: bool = False,
        has_unresolved_mfs_joint_expense_allocation: bool = False
    ):
        self.has_marketplace_medical_premium = has_marketplace_medical_premium
        self.has_ltc_premium = has_ltc_premium
        self.has_self_employed_health_insurance_overlap = has_self_employed_health_insurance_overlap
        self.has_prior_year_medical_recovery = has_prior_year_medical_recovery
        self.sales_tax_amount_requires_calculation = sales_tax_amount_requires_calculation
        self.has_tax_refund_or_rebate_adjustment = has_tax_refund_or_rebate_adjustment
        self.has_form_2555_or_4563_or_puerto_rico_exclusion = has_form_2555_or_4563_or_puerto_rico_exclusion
        self.has_other_tax_line_6 = has_other_tax_line_6
        self.has_multiple_mortgages = has_multiple_mortgages
        self.mortgage_proceeds_not_all_qualified = mortgage_proceeds_not_all_qualified
        self.mortgage_limitation_required = mortgage_limitation_required
        self.has_shared_mortgage = has_shared_mortgage
        self.has_non_1098_mortgage_interest = has_non_1098_mortgage_interest
        self.has_non_1098_points = has_non_1098_points
        self.has_seller_financed_mortgage = has_seller_financed_mortgage
        self.has_form_8396_credit = has_form_8396_credit
        self.has_investment_interest = has_investment_interest
        self.has_noncash_charity = has_noncash_charity
        self.has_charity_carryover = has_charity_carryover
        self.has_charitable_agi_limitation = has_charitable_agi_limitation
        self.has_casualty_or_theft_loss = has_casualty_or_theft_loss
        self.has_net_qualified_disaster_loss = has_net_qualified_disaster_loss
        self.has_line_16_item = has_line_16_item
        self.has_unresolved_mfs_joint_expense_allocation = has_unresolved_mfs_joint_expense_allocation

    @classmethod
    def from_dict(cls, raw_flags: Dict[str, Any]) -> "SpecialCaseFlagsV1":
        return cls(
            has_marketplace_medical_premium=bool(raw_flags.get("has_marketplace_medical_premium", False)),
            has_ltc_premium=bool(raw_flags.get("has_ltc_premium", False)),
            has_self_employed_health_insurance_overlap=bool(raw_flags.get("has_self_employed_health_insurance_overlap", False)),
            has_prior_year_medical_recovery=bool(raw_flags.get("has_prior_year_medical_recovery", False)),
            sales_tax_amount_requires_calculation=bool(raw_flags.get("sales_tax_amount_requires_calculation", False)),
            has_tax_refund_or_rebate_adjustment=bool(raw_flags.get("has_tax_refund_or_rebate_adjustment", False)),
            has_form_2555_or_4563_or_puerto_rico_exclusion=bool(raw_flags.get("has_form_2555_or_4563_or_puerto_rico_exclusion", False)),
            has_other_tax_line_6=bool(raw_flags.get("has_other_tax_line_6", False)),
            has_multiple_mortgages=bool(raw_flags.get("has_multiple_mortgages", False)),
            mortgage_proceeds_not_all_qualified=bool(raw_flags.get("mortgage_proceeds_not_all_qualified", False)),
            mortgage_limitation_required=bool(raw_flags.get("mortgage_limitation_required", False)),
            has_shared_mortgage=bool(raw_flags.get("has_shared_mortgage", False)),
            has_non_1098_mortgage_interest=bool(raw_flags.get("has_non_1098_mortgage_interest", False)),
            has_non_1098_points=bool(raw_flags.get("has_non_1098_points", False)),
            has_seller_financed_mortgage=bool(raw_flags.get("has_seller_financed_mortgage", False)),
            has_form_8396_credit=bool(raw_flags.get("has_form_8396_credit", False)),
            has_investment_interest=bool(raw_flags.get("has_investment_interest", False)),
            has_noncash_charity=bool(raw_flags.get("has_noncash_charity", False)),
            has_charity_carryover=bool(raw_flags.get("has_charity_carryover", False)),
            has_charitable_agi_limitation=bool(raw_flags.get("has_charitable_agi_limitation", False)),
            has_casualty_or_theft_loss=bool(raw_flags.get("has_casualty_or_theft_loss", False)),
            has_net_qualified_disaster_loss=bool(raw_flags.get("has_net_qualified_disaster_loss", False)),
            has_line_16_item=bool(raw_flags.get("has_line_16_item", False)),
            has_unresolved_mfs_joint_expense_allocation=bool(raw_flags.get("has_unresolved_mfs_joint_expense_allocation", False))
        )


class ScheduleAInputsV1:
    """
    Schedule A 完整輸入模型 (Schedule A Inputs).
    封裝了進行列舉扣除計算所需的申報人基本資料、年度、AGI，以及醫療、稅務、房貸、慈善等明細列表。
    """
    def __init__(
        self,
        taxpayer_name: str = "",
        taxpayer_ssn: str = "",
        taxpayer_date_of_birth: Optional[str] = None,
        taxpayer_blind: bool = False,
        spouse_date_of_birth: Optional[str] = None,
        spouse_blind: bool = False,
        tax_year: Optional[int] = None,
        filing_status: str = "SINGLE",
        adjusted_gross_income: Optional[Decimal] = Decimal("0.00"),
        medical_items: Optional[List[MedicalExpenseItemV1]] = None,
        tax_items: Optional[List[TaxPaymentItemV1]] = None,
        line_5a_election: Optional[str] = None,
        mortgage_interest_items: Optional[List[MortgageInterestItemV1]] = None,
        cash_charity_items: Optional[List[CashCharityItemV1]] = None,
        standard_deduction_reference: Optional[StandardDeductionReferenceV1] = None,
        special_case_flags: Optional[SpecialCaseFlagsV1] = None
    ):
        self.taxpayer_name = taxpayer_name
        self.taxpayer_ssn = taxpayer_ssn
        self.taxpayer_date_of_birth = taxpayer_date_of_birth
        self.taxpayer_blind = taxpayer_blind
        self.spouse_date_of_birth = spouse_date_of_birth
        self.spouse_blind = spouse_blind
        self.tax_year = tax_year
        self.filing_status = filing_status
        self.adjusted_gross_income = adjusted_gross_income
        self.medical_items = medical_items if medical_items is not None else []
        self.tax_items = tax_items if tax_items is not None else []
        self.line_5a_election = line_5a_election
        self.mortgage_interest_items = mortgage_interest_items if mortgage_interest_items is not None else []
        self.cash_charity_items = cash_charity_items if cash_charity_items is not None else []
        self.standard_deduction_reference = standard_deduction_reference if standard_deduction_reference is not None else StandardDeductionReferenceV1()
        self.special_case_flags = special_case_flags if special_case_flags is not None else SpecialCaseFlagsV1()

    @classmethod
    def from_dict(cls, inputs_dict: Dict[str, Any]) -> "ScheduleAInputsV1":
        taxpayer_name = inputs_dict.get("taxpayer_name") or ""
        taxpayer_ssn = inputs_dict.get("taxpayer_ssn") or inputs_dict.get("ssn") or ""
        taxpayer_blind = bool(inputs_dict.get("taxpayer_blind", False))
        spouse_blind = bool(inputs_dict.get("spouse_blind", False))
        taxpayer_date_of_birth = inputs_dict.get("taxpayer_date_of_birth")
        spouse_date_of_birth = inputs_dict.get("spouse_date_of_birth")
        raw_year = inputs_dict.get("tax_year")
        try:
            tax_year = int(float(raw_year)) if raw_year is not None else None
        except (ValueError, TypeError):
            tax_year = None
        filing_status = str(inputs_dict.get("filing_status") or "SINGLE").upper()
        
        has_agi = "adjusted_gross_income" in inputs_dict or "agi" in inputs_dict
        if not has_agi:
            adjusted_gross_income = None
        else:
            val = inputs_dict.get("adjusted_gross_income") or inputs_dict.get("agi")
            adjusted_gross_income = Decimal(str(val)) if val is not None else Decimal("0.00")
        
        # Medical items
        # 把已經傳盛medical item的物件加上item_id
        medical_items = []
        raw_med = inputs_dict.get("medical_items") or inputs_dict.get("medical_expense_items") or []
        for idx, m in enumerate(raw_med):
            if not isinstance(m, dict):
                continue
            if not m.get("item_id"):
                m = dict(m)
                m["item_id"] = f"med_{idx}"
            medical_items.append(MedicalExpenseItemV1.from_dict(m, tax_year))
            
        # Tax items
        # 把已經傳盛tax item的物件加上item_id
        tax_items = []
        raw_tax = inputs_dict.get("tax_items") or inputs_dict.get("tax_payment_items") or []
        for idx, t in enumerate(raw_tax):
            if not isinstance(t, dict):
                continue
            if not t.get("item_id"):
                t = dict(t)
                t["item_id"] = f"tax_{idx}"
            tax_items.append(TaxPaymentItemV1.from_dict(t, tax_year))
            
        line_5a_election = inputs_dict.get("line_5a_election")
        

        # Mortgage items
        mortgage_interest_items = []
        raw_mort = inputs_dict.get("mortgage_interest_items") or []
        for idx, mo in enumerate(raw_mort):
            if not isinstance(mo, dict):
                continue
            if not mo.get("item_id"):
                mo = dict(mo)
                mo["item_id"] = f"mort_{idx}"
            mortgage_interest_items.append(MortgageInterestItemV1.from_dict(mo))

        # Charity items
        cash_charity_items = []
        raw_charity = inputs_dict.get("cash_charity_items") or []
        
        for idx, ch in enumerate(raw_charity):
            if not isinstance(ch, dict):
                continue
            if not ch.get("item_id"):
                ch = dict(ch)
                ch["item_id"] = f"charity_{idx}"
            cash_charity_items.append(CashCharityItemV1.from_dict(ch))

        # Standard Deduction Reference
        try:
            rates = load_tax_rates(tax_year)
            std_cfg = rates.get("standard_deduction", {})
            std_ded_amt = std_cfg.get(filing_status)
        except Exception:
            std_ded_amt = 15000.0

        std_ref = inputs_dict.get("standard_deduction_reference")
        spouse_itemizes = False
        elect_itemize = False
        if isinstance(std_ref, dict):
            spouse_itemizes = std_ref.get("must_itemize_due_to_mfs_spouse") 
            elect_itemize = std_ref.get("elect_itemize_even_if_less") 
        

        std_deduction_reference = StandardDeductionReferenceV1(
            standard_deduction_amount=Decimal(str(std_ded_amt)) if std_ded_amt is not None else None,
            must_itemize_due_to_mfs_spouse=spouse_itemizes,
            elect_itemize_even_if_less=elect_itemize
        )

        # Special Case Flags
        raw_flags = inputs_dict.get("special_case_flags")
        if not isinstance(raw_flags, dict):
            raw_flags = {}
            if inputs_dict.get("requires_form_8962_for_marketplace_premiums") is True:
                raw_flags["has_marketplace_medical_premium"] = True
                
            for m in inputs_dict.get("medical_expense_items") or []:
                if isinstance(m, dict):
                    cat = str(m.get("expense_category") or "").lower()
                    if "marketplace" in cat or m.get("covered_by_ptc_or_aptc") is True:
                        raw_flags["has_marketplace_medical_premium"] = True
                    if "ltc" in cat or cat == "qualified_ltc_insurance_premium":
                        raw_flags["has_ltc_premium"] = True
                        
            if inputs_dict.get("noncash_charitable_contributions", 0.0) > 0.0:
                raw_flags["has_noncash_charity"] = True
            if inputs_dict.get("charitable_carryover", 0.0) > 0.0:
                raw_flags["has_charity_carryover"] = True
        
        special_case_flags = SpecialCaseFlagsV1.from_dict(raw_flags)

        return cls(
            taxpayer_name=taxpayer_name,
            taxpayer_ssn=taxpayer_ssn,
            taxpayer_date_of_birth=taxpayer_date_of_birth,
            taxpayer_blind=taxpayer_blind,
            spouse_date_of_birth=spouse_date_of_birth,
            spouse_blind=spouse_blind,
            tax_year=tax_year,
            filing_status=filing_status,
            adjusted_gross_income=adjusted_gross_income,
            medical_items=medical_items,
            tax_items=tax_items,
            line_5a_election=line_5a_election,
            mortgage_interest_items=mortgage_interest_items,
            cash_charity_items=cash_charity_items,
            standard_deduction_reference=std_deduction_reference,
            special_case_flags=special_case_flags
        )


class ValidationIssue:
    """
    防呆與合規性檢驗結果 (Validation Issue).
    用於記錄阻斷性錯誤 (Blocking Error) 或提示性警告 (Review Warning)。
    例如 `MISSING_250_ACKNOWLEDGMENT`、`REAL_ESTATE_TAX_PAYMENT_NOT_CONFIRMED` 等。
    """
    def __init__(self, code: str, field: Optional[str] = None, item_id: Optional[str] = None, source_document_id: Optional[str] = None, message: str = ""):
        self.code = code  # 錯誤或警告代碼
        self.field = field  # 出錯的欄位名稱
        self.item_id = item_id  # 關聯的明細項目 ID
        self.source_document_id = source_document_id  # 關聯的來源憑證/檔案名稱
        self.message = message  # 詳細錯誤訊息

    def to_dict(self):
        return {
            "code": self.code,
            "field": self.field,
            "item_id": self.item_id,
            "source_document_id": self.source_document_id,
            "message": self.message
        }


class ScheduleAResultV1:
    """
    Schedule A 完整計算結果模型 (Schedule A Calculation Result).
    包含 Schedule A 所有對應申報表單線頭 (Lines 1-18) 的計算金額，
    以及此筆申報是否建議列舉扣除 (is_itemizing)、最終抵扣金額 (standard_deduction_amount 與 line_17_total_itemized_deductions)，
    以及合規檢驗發現的所有錯誤 (blocking_errors) 與警告 (review_warnings)。
    """
    def __init__(self, **kwargs):
        self.taxpayer_name = kwargs.get("taxpayer_name", "")
        self.taxpayer_ssn_masked = kwargs.get("taxpayer_ssn_masked", "")
        raw_year = kwargs.get("tax_year")
        if raw_year is not None:
            try:
                self.tax_year = int(float(raw_year))
            except (ValueError, TypeError):
                self.tax_year = None
        else:
            self.tax_year = None
        self.filing_status = kwargs.get("filing_status", "SINGLE")

        self.line_1_medical_and_dental_expenses = kwargs.get("line_1_medical_and_dental_expenses", Decimal("0.00"))
        self.line_2_agi = kwargs.get("line_2_agi", Decimal("0.00"))
        self.line_3_medical_threshold = kwargs.get("line_3_medical_threshold", Decimal("0.00"))
        self.line_4_deductible_medical_expenses = kwargs.get("line_4_deductible_medical_expenses", Decimal("0.00"))

        self.line_5a_amount = kwargs.get("line_5a_amount", Decimal("0.00"))
        self.line_5a_sales_tax_checkbox = kwargs.get("line_5a_sales_tax_checkbox", False)
        self.line_5b_real_estate_taxes = kwargs.get("line_5b_real_estate_taxes", Decimal("0.00"))
        self.line_5c_personal_property_taxes = kwargs.get("line_5c_personal_property_taxes", Decimal("0.00"))
        self.line_5d_salt_before_limit = kwargs.get("line_5d_salt_before_limit", Decimal("0.00"))
        self.line_5e_salt_deduction = kwargs.get("line_5e_salt_deduction")
        self.line_6_other_taxes = kwargs.get("line_6_other_taxes", Decimal("0.00"))
        self.line_7_total_taxes = kwargs.get("line_7_total_taxes")

        self.line_8_qualifying_proceeds_checkbox = kwargs.get("line_8_qualifying_proceeds_checkbox", False)
        self.line_8a_home_mortgage_interest = kwargs.get("line_8a_home_mortgage_interest", Decimal("0.00"))
        self.line_8b_non_1098_interest = kwargs.get("line_8b_non_1098_interest", Decimal("0.00"))
        self.line_8c_non_1098_points = kwargs.get("line_8c_non_1098_points", Decimal("0.00"))
        self.line_8d_reserved = kwargs.get("line_8d_reserved")
        self.line_8e_total_mortgage_interest = kwargs.get("line_8e_total_mortgage_interest", Decimal("0.00"))
        self.line_9_investment_interest = kwargs.get("line_9_investment_interest", Decimal("0.00"))
        self.line_10_total_interest_paid = kwargs.get("line_10_total_interest_paid", Decimal("0.00"))

        self.line_11_cash_contributions = kwargs.get("line_11_cash_contributions", Decimal("0.00"))
        self.line_12_noncash_contributions = kwargs.get("line_12_noncash_contributions", Decimal("0.00"))
        self.line_13_charity_carryover = kwargs.get("line_13_charity_carryover", Decimal("0.00"))
        self.line_14_total_charity = kwargs.get("line_14_total_charity", Decimal("0.00"))

        self.line_15_casualty_theft_loss = kwargs.get("line_15_casualty_theft_loss", Decimal("0.00"))
        self.line_16_other_itemized_deductions = kwargs.get("line_16_other_itemized_deductions", Decimal("0.00"))
        self.line_17_total_itemized_deductions = kwargs.get("line_17_total_itemized_deductions")
        self.line_18_elect_itemize_surface = kwargs.get("line_18_elect_itemize_surface")



        self.standard_deduction_amount = kwargs.get("standard_deduction_amount")
        self.is_itemizing = kwargs.get("is_itemizing")
        self.is_v1_supported = kwargs.get("is_v1_supported", True)
        self.should_attach_schedule_a = kwargs.get("should_attach_schedule_a", False)
        self.can_file = kwargs.get("can_file", True)

        self.blocking_errors = kwargs.get("blocking_errors", [])
        self.review_warnings = kwargs.get("review_warnings", [])

    def to_dict(self):
        def to_float(val):
            if isinstance(val, Decimal):
                return float(val)
            return val
        return {
            "taxpayer_name": self.taxpayer_name,
            "taxpayer_ssn_masked": self.taxpayer_ssn_masked,
            "tax_year": self.tax_year,
            "filing_status": self.filing_status,
            "line_1_medical_and_dental_expenses": to_float(self.line_1_medical_and_dental_expenses),
            "line_2_agi": to_float(self.line_2_agi),
            "line_3_medical_threshold": to_float(self.line_3_medical_threshold),
            "line_4_deductible_medical_expenses": to_float(self.line_4_deductible_medical_expenses),
            "line_5a_amount": to_float(self.line_5a_amount),
            "line_5a_sales_tax_checkbox": self.line_5a_sales_tax_checkbox,
            "line_5b_real_estate_taxes": to_float(self.line_5b_real_estate_taxes),
            "line_5c_personal_property_taxes": to_float(self.line_5c_personal_property_taxes),
            "line_5d_salt_before_limit": to_float(self.line_5d_salt_before_limit),
            "line_5e_salt_deduction": to_float(self.line_5e_salt_deduction),
            "line_6_other_taxes": to_float(self.line_6_other_taxes),
            "line_7_total_taxes": to_float(self.line_7_total_taxes),
            "line_8_qualifying_proceeds_checkbox": self.line_8_qualifying_proceeds_checkbox,
            "line_8a_home_mortgage_interest": to_float(self.line_8a_home_mortgage_interest),
            "line_8b_non_1098_interest": to_float(self.line_8b_non_1098_interest),
            "line_8c_non_1098_points": to_float(self.line_8c_non_1098_points),
            "line_8e_total_mortgage_interest": to_float(self.line_8e_total_mortgage_interest),
            "line_9_investment_interest": to_float(self.line_9_investment_interest),
            "line_10_total_interest_paid": to_float(self.line_10_total_interest_paid),
            "line_11_cash_contributions": to_float(self.line_11_cash_contributions),
            "line_12_noncash_contributions": to_float(self.line_12_noncash_contributions),
            "line_13_charity_carryover": to_float(self.line_13_charity_carryover),
            "line_14_total_charity": to_float(self.line_14_total_charity),
            "line_15_casualty_theft_loss": to_float(self.line_15_casualty_theft_loss),
            "line_16_other_itemized_deductions": to_float(self.line_16_other_itemized_deductions),
            "line_17_total_itemized_deductions": to_float(self.line_17_total_itemized_deductions),
            "line_18_elect_itemize_surface": self.line_18_elect_itemize_surface,
            "standard_deduction_amount": to_float(self.standard_deduction_amount),
            "is_itemizing": self.is_itemizing,
            "is_v1_supported": self.is_v1_supported,
            "should_attach_schedule_a": self.should_attach_schedule_a,
            "can_file": self.can_file,
            "blocking_errors": [err.to_dict() if hasattr(err, "to_dict") else err for err in self.blocking_errors],
            "review_warnings": [warn.to_dict() if hasattr(warn, "to_dict") else warn for warn in self.review_warnings],
        }
