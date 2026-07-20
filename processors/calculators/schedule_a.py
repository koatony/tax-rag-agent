# =====================================================================
# REVIEW 重點 1: 單一職責原則 (Single Responsibility Principle - SRP)
# =====================================================================
# 【為什麼核心計算要獨立於 I/O 或 LLM 之外？】
# 1. 職責分離：在一個健全的微服務或模組化系統中，業務邏輯的計算（計算 AGI 7.5% 門檻、比較標準扣除額與列舉扣除額）
#    不應該與「資料是怎麼來的（例如 LLM 提取、DB 讀取）」綁定。
# 2. 提高可測試性（Testability）：當計算邏輯被獨立為一個 pure function (calculate_schedule_a_v1) 時，
#    我們在單元測試 (Unit Test) 中不需要 Mock 任何 API 或資料庫，只需傳入 Inputs 物件即可。
# =====================================================================

import re
from typing import List, Dict, Any, Set, Optional
from decimal import Decimal
from processors.models.schedule_a import (
    ScheduleAInputsV1,
    ScheduleAResultV1,
    ValidationIssue,
    MedicalExpenseItemV1,
    TaxPaymentItemV1,
    MortgageInterestItemV1,
    CashCharityItemV1,
    SpecialCaseFlagsV1,
    load_tax_rates,
)
from processors.validators.schedule_a import (
    validate_identity,
    validate_tax_year,
    validate_nonnegative_amounts,
    detect_unsupported_cases,
    validate_paid_year,
)

def sum_decimal(iterable):
    """將可迭代項目加總為 Decimal 類型的金額。"""
    s = Decimal("0.00")
    for x in iterable:
        if x is not None:
            s += Decimal(str(x))
    return s

def is_over_65(dob_str: str, tax_year: int) -> bool:
    if not dob_str or not isinstance(dob_str, str):
        return False
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", dob_str.strip())
    if not m:
        return False
    by, bm, bd = int(m.group(1)), int(m.group(2)), int(m.group(3))
    cutoff_year = tax_year - 64
    if by < cutoff_year:
        return True
    if by == cutoff_year and bm == 1 and bd == 1:
        return True
    return False

def calculate_additional_standard_deduction(inputs: ScheduleAInputsV1) -> Decimal:
    """
    計算申報人（及配偶）適用的「加計標準扣除額」（Additional Standard Deduction）。
    
    扣除規則：
    1. 申報人（與配偶，若為聯申/分申）如果「滿 65 歲」或「法定盲人」，可獲得額外的扣除額度。
    2. 統計申報人與配偶符合上述條件的總個數 (conditions_count，最多 4 個)。
    3. 根據申報身份乘上對應的加計額度：
       - 單身 / 戶主 (SINGLE/HOH) 適用單身加計額率（如 2025 年為 $2,000/項）。
       - 聯申 / 分申 / 合格孀婦 (MFJ/MFS/QSS) 適用聯申加計額率（如 2025 年為 $1,600/項）。
    """
    ZERO = Decimal("0.00")
    try:
        rates = load_tax_rates(inputs.tax_year)
        std_cfg = rates.get("standard_deduction", {})
    except Exception:
        return ZERO
        
    single_hoh_rate = Decimal(str(std_cfg.get("additional_deduction_single_hoh", 1950.0)))
    joint_mfs_qss_rate = Decimal(str(std_cfg.get("additional_deduction_joint_mfs_qss", 1550.0)))
    
    status = str(inputs.filing_status or "SINGLE").upper()
    is_joint_or_mfs = status in ("MFJ", "MFS", "QSS")
    rate = joint_mfs_qss_rate if is_joint_or_mfs else single_hoh_rate
    
    conditions_count = 0
    if is_over_65(inputs.taxpayer_date_of_birth, inputs.tax_year):
        conditions_count += 1
    if inputs.taxpayer_blind:
        conditions_count += 1
        
    if is_joint_or_mfs:
        if is_over_65(inputs.spouse_date_of_birth, inputs.tax_year):
            conditions_count += 1
        if inputs.spouse_blind:
            conditions_count += 1
            
    return Decimal(conditions_count) * rate

def calculate_salt_limit_v1(tax_year: int, filing_status: str, agi: Decimal, line_5d: Decimal, has_foreign_adjustment: bool, errors: List[ValidationIssue]) -> Decimal:
    """
    計算州與地方稅 (SALT) 的扣除上限 (Line 5e)。
    
    扣除規則：
    - 2024 年：上限為 $10,000 (夫妻分申 MFS 為 $5,000)。
    - 2025 年：
      1. 若總 SALT (line_5d) <= $10,000 (MFS 為 $5,000)，可全額扣除。
      2. 若總 SALT 超過 $10,000，且 AGI <= $500,000 (MFS 為 $250,000) 且無國外所得調整，上限為 $40,000 (MFS 為 $20,000)。
      3. 高收入或有國外調整之複雜情境，須使用專用 SALT 工作表（V1 引擎不支援）。
    """
    rates = load_tax_rates(tax_year)
    salt_cfg = rates.get("salt_cap", {})
    if not salt_cfg:
        raise ValueError(f"SALT configuration not found for tax year {tax_year}")

    is_mfs = filing_status == "MFS"
    
    # Extract values from config
    floor = Decimal(str(salt_cfg.get("mfs_floor" if is_mfs else "floor") or (5000.0 if is_mfs else 10000.0)))
    base_cap = Decimal(str(salt_cfg.get("mfs_cap" if is_mfs else "base_cap") or (5000.0 if is_mfs else 10000.0)))
    agi_limit_val = salt_cfg.get("mfs_phaseout_threshold" if is_mfs else "phaseout_threshold")
    
    if tax_year == 2024:
        return min(line_5d, base_cap)
    elif tax_year == 2025:
        if line_5d <= floor:
            return line_5d
        
        if agi_limit_val is None:
            # If config has no phaseout threshold, default to 2025 base logic
            agi_limit_val = 250000.0 if is_mfs else 500000.0
            
        agi_limit = Decimal(str(agi_limit_val))
        if agi <= agi_limit and not has_foreign_adjustment:
            return min(line_5d, base_cap)
        else:
            errors.append(ValidationIssue("UNSUPPORTED_2025_SALT_WORKSHEET", field="line_5e_salt_deduction", message="2025 high-income or foreign-income SALT worksheet is not supported in V1."))
            return None
    else:
        errors.append(ValidationIssue("UNSUPPORTED_TAX_YEAR", field="tax_year", message=f"Tax year {tax_year} is not supported."))
        return None

def calculate_simple_form_1098(mortgage_interest_items: List[MortgageInterestItemV1], errors: List[ValidationIssue], warnings: List[ValidationIssue]) -> Decimal:
    ZERO = Decimal("0.00")
    if not mortgage_interest_items:
        return ZERO
    if len(mortgage_interest_items) > 1:
        errors.append(ValidationIssue("UNSUPPORTED_MULTIPLE_MORTGAGES", field="mortgage_interest_items", message="Multiple mortgages not supported in V1."))
        
    total_deductible = ZERO
    for item in mortgage_interest_items:
        validate_paid_year(item, errors)

        # 防禦層：依 property_use_context 阻斷非自用房產利息
        ctx = item.property_use_context  # None / MAIN_HOME / SECOND_HOME / RENTAL_PROPERTY / BUSINESS_PROPERTY / UNKNOWN
        if ctx in MortgageInterestItemV1.NON_DEDUCTIBLE_CONTEXTS:
            warnings.append(ValidationIssue(
                "MORTGAGE_INTEREST_NON_PERSONAL_USE",
                field="property_use_context",
                item_id=item.item_id,
                source_document_id=item.source_document_id,
                message=f"Mortgage interest excluded from Schedule A: property_use_context={ctx}. "
                        f"Rental property interest belongs on Schedule E; business property interest on Schedule C."
            ))
            continue
        elif ctx not in MortgageInterestItemV1.DEDUCTIBLE_CONTEXTS:
            # None 或 UNKNOWN：警告但仍依 simple_mortgage_status 繼續處理
            warnings.append(ValidationIssue(
                "MORTGAGE_INTEREST_USE_CONTEXT_UNKNOWN",
                field="property_use_context",
                item_id=item.item_id,
                source_document_id=item.source_document_id,
                message=f"property_use_context is '{ctx}'; cannot confirm this is a personal-use home. "
                        f"Proceeding based on simple_mortgage_status."
            ))

        if item.simple_mortgage_status == "UNKNOWN":
            errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="simple_mortgage_status", item_id=item.item_id, source_document_id=item.source_document_id, message="Unknown mortgage status."))
            continue
            
        if item.paid_in_tax_year is True:
            total_deductible += item.form_1098_box_1_mortgage_interest + item.deductible_points_reported_on_1098
            
    return total_deductible


def calculate_cash_charity(cash_charity_items: List[CashCharityItemV1], errors: List[ValidationIssue], warnings: List[ValidationIssue], tax_year: int = 2024) -> Decimal:
    total = Decimal("0.00")
    ZERO = Decimal("0.00")
    for item in cash_charity_items:
        validate_paid_year(item, errors)
        
        if item.qualified_organization_status == "UNKNOWN":
            errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="qualified_organization_status", item_id=item.item_id, source_document_id=item.source_document_id, message="Unknown charity organization qualification status."))
            continue
        elif item.qualified_organization_status == "NOT_QUALIFIED":
            warnings.append(ValidationIssue("CHARITY_ORGANIZATION_NOT_QUALIFIED", field="qualified_organization_status", item_id=item.item_id, source_document_id=item.source_document_id, message="Charity organization is not qualified; excluded."))
            continue
            
        has_date_error = False
        if not item.contribution_date:
            errors.append(ValidationIssue(
                "CHARITY_CONTRIBUTION_DATE_MISSING",
                field="contribution_date",
                item_id=item.item_id,
                source_document_id=item.source_document_id,
                message=f"The contribution record identifies tax year {tax_year} but does not provide the actual contribution date."
            ))
            has_date_error = True
            
        has_ack_error = False
        net_contrib = item.gross_contribution_amount - item.goods_or_services_value
        if net_contrib >= Decimal("250.00"):
            if item.contemporaneous_acknowledgment_received is None or item.contemporaneous_acknowledgment_received is False:
                errors.append(ValidationIssue(
                    "MISSING_250_ACKNOWLEDGMENT",
                    field="contemporaneous_acknowledgment_received",
                    item_id=item.item_id,
                    source_document_id=item.source_document_id,
                    message=f"The ${int(item.gross_contribution_amount):,} contribution record does not state whether goods or services were provided in exchange."
                ))
                has_ack_error = True

        if has_date_error or has_ack_error:
            continue
            
        if item.bank_or_written_record_available is None:
            errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="bank_or_written_record_available", item_id=item.item_id, source_document_id=item.source_document_id, message="Bank or written record availability is unknown/null."))
            continue
            
        if item.goods_or_services_value > item.gross_contribution_amount:
            errors.append(ValidationIssue("ADJUSTMENT_EXCEEDS_GROSS_AMOUNT", field="goods_or_services_value", item_id=item.item_id, source_document_id=item.source_document_id, message="Goods/services value exceeds gross contribution amount."))
            continue
            
        if item.paid_in_tax_year is True and item.qualified_organization_status == "VERIFIED" and item.bank_or_written_record_available is True:
            total += net_contrib
            
    return total

def any_unsupported_case(flags: SpecialCaseFlagsV1) -> bool:
    unsupported_attributes = [
        "has_marketplace_medical_premium",
        "has_ltc_premium",
        "has_self_employed_health_insurance_overlap",
        "has_prior_year_medical_recovery",
        "sales_tax_amount_requires_calculation",
        "has_tax_refund_or_rebate_adjustment",
        "has_other_tax_line_6",
        "has_multiple_mortgages",
        "mortgage_proceeds_not_all_qualified",
        "mortgage_limitation_required",
        "has_shared_mortgage",
        "has_non_1098_mortgage_interest",
        "has_non_1098_points",
        "has_seller_financed_mortgage",
        "has_form_8396_credit",
        "has_investment_interest",
        "has_noncash_charity",
        "has_charity_carryover",
        "has_charitable_agi_limitation",
        "has_casualty_or_theft_loss",
        "has_net_qualified_disaster_loss",
        "has_line_16_item",
        "has_unresolved_mfs_joint_expense_allocation"
    ]
    for attr in unsupported_attributes:
        if getattr(flags, attr, False):
            return True
    return False

class TaxPools:
    def __init__(self):
        self.income_tax = []
        self.sales_tax = []
        self.real_estate_tax = []
        self.personal_property_tax = []

def classify_tax_items(tax_items: List[TaxPaymentItemV1], errors: List[ValidationIssue], warnings: List[ValidationIssue]) -> TaxPools:
    pools = TaxPools()
    for item in tax_items:
        validate_paid_year(item, errors)
        
        if item.tax_category == "UNKNOWN":
            errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="tax_category", item_id=item.item_id, source_document_id=item.source_document_id, message="Unknown tax category."))
            continue
            
        if item.tax_category == "FEDERAL_OR_NONDEDUCTIBLE_TAX":
            warnings.append(ValidationIssue("FEDERAL_OR_NONDEDUCTIBLE_TAX_EXCLUDED", field="tax_category", item_id=item.item_id, source_document_id=item.source_document_id, message="Federal or nondeductible tax excluded."))
            continue
            
        if item.tax_category == "BUSINESS_OR_RENTAL_TAX":
            warnings.append(ValidationIssue("BUSINESS_OR_RENTAL_TAX_EXCLUDED", field="tax_category", item_id=item.item_id, source_document_id=item.source_document_id, message="Business or rental tax excluded from Schedule A."))
            continue
            
        if item.separately_stated_nondeductible_charge > item.amount_paid:
            errors.append(ValidationIssue("ADJUSTMENT_EXCEEDS_GROSS_AMOUNT", field="separately_stated_nondeductible_charge", item_id=item.item_id, source_document_id=item.source_document_id, message="Nondeductible charge exceeds amount paid."))
            continue
        
        '''
        可納入 Schedule A 的稅款
        = 文件上的總金額 - 明確列出的不可扣費用
        separately_stated_nondeductible_charge 全靠LLM判斷
        '''
        eligible_amt = item.amount_paid - item.separately_stated_nondeductible_charge
        



        if item.tax_category == "STATE_LOCAL_INCOME_TAX":
            if item.paid_in_tax_year is True:
                pools.income_tax.append(eligible_amt)
        elif item.tax_category == "GENERAL_SALES_TAX":
            if item.paid_in_tax_year is True:
                pools.sales_tax.append(eligible_amt)
        # 區分是否為自用
        elif item.tax_category == "PERSONAL_REAL_ESTATE_TAX":
            #實價登錄檢查
            if item.personal_use_confirmed is None:
                errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="personal_use_confirmed", item_id=item.item_id, source_document_id=item.source_document_id, message="Real estate tax personal use confirmation is missing or unknown."))
                continue
            if item.personal_use_confirmed is False:
                warnings.append(ValidationIssue("PERSONAL_USE_NOT_CONFIRMED", field="personal_use_confirmed", item_id=item.item_id, source_document_id=item.source_document_id, message="Real estate is not for personal use; excluded."))
                continue
            if item.actual_paid_to_taxing_authority_confirmed is None or item.actual_paid_to_taxing_authority_confirmed is False:
                # Excluded from deductible pool
                continue
            if item.personal_use_confirmed is True and item.actual_paid_to_taxing_authority_confirmed is True:
                if item.paid_in_tax_year is True:
                    pools.real_estate_tax.append(eligible_amt)
        elif item.tax_category == "PERSONAL_PROPERTY_TAX":
            if item.personal_use_confirmed is None or item.value_based_and_annual_confirmed is None:
                errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="property_confirmations", item_id=item.item_id, source_document_id=item.source_document_id, message="Personal property tax confirmations are missing or unknown."))
                continue
            if item.personal_use_confirmed is True and item.value_based_and_annual_confirmed is True:
                if item.paid_in_tax_year is True:
                    pools.personal_property_tax.append(eligible_amt)
    return pools



# 需要手動輸入agi 後續再想辦法結合1040
def calculate_schedule_a_v1(inputs: ScheduleAInputsV1, allowed_years: Optional[Set[int]] = None) -> ScheduleAResultV1:



    errors = []
    warnings = []
    ZERO = Decimal("0.00")
    MEDICAL_RATE = Decimal("0.075")

    if allowed_years is None:
        try:
            import os
            import json
            current_dir = os.path.dirname(os.path.abspath(__file__))
            schema_path = os.path.abspath(os.path.join(current_dir, "..", "..", "docs", "how_to_fill_forms_docs", "schedule_a", "schedule_a_schema.json"))
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_data = json.load(f)
            allowed_years = set(schema_data.get("supported_tax_years", [2024, 2025]))
        except Exception:
            allowed_years = {2024, 2025}

    # 1. 校驗基本與阻斷規則
    validate_identity(inputs, errors)
    validate_tax_year(inputs.tax_year, allowed=allowed_years, errors=errors)
    validate_nonnegative_amounts(inputs, errors)

    if any(e.code == "UNSUPPORTED_TAX_YEAR" for e in errors):
        raw_ssn = str(inputs.taxpayer_ssn or "")
        ssn_masked = f"***-**-{raw_ssn[-4:]}" if len(raw_ssn) >= 4 else "***-**-XXXX"
        return ScheduleAResultV1(
            taxpayer_name=inputs.taxpayer_name,
            taxpayer_ssn_masked=ssn_masked,
            tax_year=inputs.tax_year,
            filing_status=inputs.filing_status,
            blocking_errors=errors,
            review_warnings=warnings,
            can_file=False
        )


    # 抓目前input看出的問題，丟回不支援的解釋
    detect_unsupported_cases(inputs.special_case_flags, errors)

    # 2. Medical Expense (Lines 1-4)
    medical_total = ZERO
    for item in inputs.medical_items:
        # 每一項都要檢查年分
        validate_paid_year(item, errors)

        if item.medical_qualification_status == "UNKNOWN":
            errors.append(ValidationIssue("UNKNOWN_MEDICAL_QUALIFICATION", field="medical_qualification_status", item_id=item.item_id, source_document_id=item.source_document_id, message="Unknown medical qualification status."))
            continue

        if item.eligible_person_status == "UNKNOWN":
            errors.append(ValidationIssue("UNKNOWN_MEDICAL_PERSON_ELIGIBILITY", field="eligible_person_status", item_id=item.item_id, source_document_id=item.source_document_id, message="Unknown medical eligible person status."))
            continue

        if (
            item.medical_qualification_status == "NOT_DEDUCTIBLE"
            or item.eligible_person_status == "NOT_ELIGIBLE"
            or item.paid_in_tax_year is False
        ):
            warnings.append(ValidationIssue("MEDICAL_ITEM_EXCLUDED", field="medical_items", item_id=item.item_id, source_document_id=item.source_document_id, message=f"Medical item {item.item_id} excluded."))
            continue

        # line 1~4公式
        adjustments = item.reimbursement_amount + item.tax_free_medical_account_payment

        if adjustments > item.taxpayer_paid_amount:
            errors.append(ValidationIssue("ADJUSTMENT_EXCEEDS_GROSS_AMOUNT", field="reimbursement_amount", item_id=item.item_id, source_document_id=item.source_document_id, message="Medical reimbursement and HSA/FSA offset exceeds gross taxpayer paid amount."))
            continue

        medical_total += item.taxpayer_paid_amount - adjustments

    line_1 = medical_total
    line_2 = inputs.adjusted_gross_income
    line_3 = (line_2 * MEDICAL_RATE).quantize(Decimal("0.01"))
    line_4 = max(ZERO, line_1 - line_3)

    # 3. Taxes Paid (Lines 5-7)
    
    # 將扣除項目分類為四種州與地方稅 (SALT)：
    # - income_tax: 州與地方個人所得稅（與 sales_tax 互斥，二選一申報）
    # - sales_tax: 州與地方一般銷售稅（與 income_tax 互斥，二選一申報）
    # - real_estate_tax: 個人自用不動產稅（房產稅，須確認實際繳納）
    # - personal_property_tax: 按價值計徵且每年收取的個人動產稅（如車輛價值登記費）
    tax_pools = classify_tax_items(inputs.tax_items, errors=errors, warnings=warnings)

    if inputs.line_5a_election == "INCOME_TAX":
        line_5a = sum_decimal(tax_pools.income_tax)
        sales_tax_checkbox = False
    elif inputs.line_5a_election == "GENERAL_SALES_TAX":
        line_5a = sum_decimal(tax_pools.sales_tax)
        sales_tax_checkbox = True
    elif inputs.line_5a_election is None:
        line_5a = ZERO
        sales_tax_checkbox = False
        if tax_pools.income_tax or tax_pools.sales_tax:
            errors.append(ValidationIssue("TAX_ELECTION_MISSING", field="line_5a_election", message="Tax election (income tax vs sales tax) is missing."))
    else:
        line_5a = ZERO
        sales_tax_checkbox = False
        errors.append(ValidationIssue("TAX_ELECTION_MISSING", field="line_5a_election", message="Invalid tax election value."))

    # 檢查是否有未確認實際支付的房產稅項目
    # （依照 IRS 規定，只有「實際繳納給稅務機關」的房產稅可扣抵；若僅是存入房屋貸款代管帳戶 Escrow 的預估金額則不可扣抵，
    # 因此若 actual_paid_to_taxing_authority_confirmed 不是 True（即為 None 或 False），會觸發阻斷性錯誤並剔除該金額）
    has_unconfirmed_real_estate_tax = False
    for item in inputs.tax_items:
        if item.tax_category == "PERSONAL_REAL_ESTATE_TAX" and item.actual_paid_to_taxing_authority_confirmed is not True:
            has_unconfirmed_real_estate_tax = True
            errors.append(ValidationIssue(
                "REAL_ESTATE_TAX_PAYMENT_NOT_CONFIRMED",
                field="line_5b_real_estate_taxes",
                item_id=item.item_id,
                source_document_id=item.source_document_id,
                message=f"The source reports an escrow amount but does not confirm the amount actually paid to the taxing authority during {inputs.tax_year}."
            ))

    line_5b_val = sum_decimal(tax_pools.real_estate_tax)
    line_5b = None if has_unconfirmed_real_estate_tax else line_5b_val
    line_5c = sum_decimal(tax_pools.personal_property_tax)
    line_5d = line_5a + line_5b_val + line_5c

    line_5e = calculate_salt_limit_v1(
        tax_year=inputs.tax_year,
        filing_status=inputs.filing_status,
        agi=inputs.adjusted_gross_income,
        line_5d=line_5d,
        has_foreign_adjustment=inputs.special_case_flags.has_form_2555_or_4563_or_puerto_rico_exclusion,
        errors=errors
    )

    line_6 = ZERO
    line_7 = None if line_5e is None else line_5e + line_6

    # 4. Interest Paid (Lines 8-10)
    # V1 引擎僅支援單一房貸之常規簡單利息扣除 (Line 8a)。以下情境均不支援：
    # - Line 8b: 未申報於 Form 1098 的房貸利息 (設為 0)
    # - Line 8c: 未申報於 Form 1098 的點數 (設為 0)
    # - Line 9: 投資利息支出 / Form 4952 (設為 0)
    # - 多筆房貸、房貸本金超額限額計算、共享利息、賣方融資房貸等 (由特別 Flag 阻斷)
    line_8a = calculate_simple_form_1098(inputs.mortgage_interest_items, errors=errors, warnings=warnings)
    line_8b = ZERO
    line_8c = ZERO
    line_8e = line_8a + line_8b + line_8c
    line_9 = ZERO
    line_10 = line_8e + line_9

    # 5. Charitable Contributions (Lines 11-14)
    # V1 引擎僅支援現金捐款 (Line 11)，以下情況均不支援：
    # - 非現金捐款、股票或資產捐贈（設為 0）
    # - 捐給非 501(c)(3) 機構的捐款（設為 0）
    # - 總額超過 AGI 60% 的特殊情況（設為 0）
    line_11 = calculate_cash_charity(inputs.cash_charity_items, errors=errors, warnings=warnings, tax_year=inputs.tax_year)
    line_12 = ZERO
    line_13 = ZERO
    line_14 = line_11 + line_12 + line_13

    # 6. Casualty and Theft Losses & Other Itemized Deductions (Lines 15-16)
    # V1 引擎不支援自然災害損失申報（Line 15），設為 0。
    line_15 = ZERO
    # V1 引擎不支援其他扣除項目（如 Gambing Losses、Form 8803、Form 4952 等）（Line 16），設為 0。
    line_16 = ZERO

    # 7. Total Itemized Deductions (Line 17)
    if line_7 is None:
        line_17 = None
    else:
        line_17 = line_4 + line_7 + line_10 + line_14 + line_15 + line_16

    # 8. Determine if Itemizing (Lines 18-19)
    # 計算「是否申報單項扣除額」：當計算結果無誤且有總額，則與標準扣除額比較。
    is_v1_supported = not any_unsupported_case(inputs.special_case_flags)
    can_file = is_v1_supported and len(errors) == 0 and line_17 is not None

    standard_amount = inputs.standard_deduction_reference.standard_deduction_amount
    if standard_amount is not None:
        standard_amount = Decimal(str(standard_amount)) + calculate_additional_standard_deduction(inputs)
        
    if standard_amount is None or line_17 is None:
        is_itemizing = None
        if standard_amount is None:
            errors.append(ValidationIssue("STANDARD_DEDUCTION_REFERENCE_MISSING", field="standard_deduction_amount", message="Standard deduction amount is missing."))
    else:
        # 決定是否使用列舉扣除額 (Itemized Deduction)：
        # 符合以下任一情況即為 True：
        # 1. 夫妻分申 (MFS) 且配偶已選擇列舉扣除，依法本申報人也「強制必須列舉」。
        # 2. 申報人主動選擇列舉扣除（即使列舉總額小於標準扣除額）。
        # 3. 列舉扣除總額 (Line 17) 大於標準扣除額 (standard_amount)（常規最優選擇）。
        is_itemizing = (
            inputs.standard_deduction_reference.must_itemize_due_to_mfs_spouse is True
            or inputs.standard_deduction_reference.elect_itemize_even_if_less is True
            or line_17 > standard_amount
        )

    should_attach = can_file and (is_itemizing is True)

    line_18_surface = None
    if inputs.tax_year == 2025:
        line_18_surface = inputs.standard_deduction_reference.elect_itemize_even_if_less is True

    # Mask SSN
    raw_ssn = str(inputs.taxpayer_ssn or "")
    if len(raw_ssn) >= 4:
        ssn_masked = f"***-**-{raw_ssn[-4:]}"
    else:
        ssn_masked = "***-**-XXXX"

    return ScheduleAResultV1(
        taxpayer_name=inputs.taxpayer_name,
        taxpayer_ssn_masked=ssn_masked,
        tax_year=inputs.tax_year,
        filing_status=inputs.filing_status,
        line_1_medical_and_dental_expenses=line_1,
        line_2_agi=line_2,
        line_3_medical_threshold=line_3,
        line_4_deductible_medical_expenses=line_4,
        line_5a_amount=line_5a,
        line_5a_sales_tax_checkbox=sales_tax_checkbox,
        line_5b_real_estate_taxes=line_5b,
        line_5c_personal_property_taxes=line_5c,
        line_5d_salt_before_limit=line_5d,
        line_5e_salt_deduction=line_5e,
        line_6_other_taxes=line_6,
        line_7_total_taxes=line_7,
        line_8_qualifying_proceeds_checkbox=False,
        line_8a_home_mortgage_interest=line_8a,
        line_8b_non_1098_interest=line_8b,
        line_8c_non_1098_points=line_8c,
        line_8e_total_mortgage_interest=line_8e,
        line_9_investment_interest=line_9,
        line_10_total_interest_paid=line_10,
        line_11_cash_contributions=line_11,
        line_12_noncash_contributions=line_12,
        line_13_charity_carryover=line_13,
        line_14_total_charity=line_14,
        line_15_casualty_theft_loss=line_15,
        line_16_other_itemized_deductions=line_16,
        line_17_total_itemized_deductions=line_17,
        line_18_elect_itemize_surface=line_18_surface,
        standard_deduction_amount=standard_amount,
        is_itemizing=is_itemizing,
        is_v1_supported=is_v1_supported,
        should_attach_schedule_a=should_attach,
        can_file=can_file,
        blocking_errors=errors,
        review_warnings=warnings
    )
