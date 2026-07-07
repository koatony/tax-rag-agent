# =====================================================================
# REVIEW 重點 1: 單一職責原則 (Single Responsibility Principle - SRP)
# =====================================================================
# 【為什麼核心計算要獨立於 I/O 或 LLM 之外？】
# 1. 職責分離：在一個健全的微服務或模組化系統中，業務邏輯的計算（例如：過濾應稅利息、折減 Savings Bond 利息）
#    不應該與「資料是怎麼來的」綁定。
# 2. 提高可測試性（Testability）：當計算邏輯被獨立為一個 pure function (calculate_schedule_b_v1) 時，
#    我們在單元測試中不需要 Mock 任何 API 或資料庫，只需傳入 Inputs 物件即可。
# =====================================================================
# REVIEW 重點 2: 三層式資料模型架構中的 Layer 2 — 正規化與中間計算
# =====================================================================
# 【本檔案 (calculators/schedule_b.py) 與 Layer 的對應關係】
# 1. 本檔案主要實現了 Layer 2 (正規化與中間計算) 的邏輯：
#    - 核心計算入口為 `calculate_schedule_b_v1(inputs: ScheduleBInputsV1) -> ScheduleBResultV1`。
#    - 它接收 Layer 1 (原始輸入模型) 物件，執行以下工作：
#      * 利息與股利項目的過濾與分類（如應稅/免稅）。
#      * 同一券商/付款人之項目的聚合處理（比對 source_statement_id 進行合併）。
#      * 執行 Form 8815 與 Part III 邏輯計算，產生中間值與各 Surface Line 數值。
#      * 調用 validator 進行防禦性驗證，以回傳包含 `errors` 狀態的結果。
#    - 最終產生並回傳 Layer 3 (Schedule B 表面欄位) 的結果模型 `ScheduleBResultV1`。
# =====================================================================

import re
from decimal import Decimal
from typing import Dict, Any, List, Tuple
from processors.models.schedule_a import ValidationIssue
from processors.models.schedule_b import (
    InterestItemV1,
    DividendItemV1,
    MarketDiscountItemV1,
    ScheduleBInputsV1,
    ScheduleBResultV1,
)
from processors.validators.schedule_b import (
    validate_identity,
    validate_tax_year,
    detect_unsupported_cases,
    validate_amounts,
    validate_form_8815,
    validate_part_iii,
)

def sum_decimal(iterable) -> Decimal:
    """將可迭代項目加總為 Decimal 類型的金額。"""
    s = Decimal("0.00")
    for x in iterable:
        if x is not None:
            s += Decimal(str(x))
    return s

def coalesce_decimal(*args) -> Decimal:
    """回傳參數中第一個非 None 的 Decimal，若全為 None 則回傳 Decimal('0.00')。"""
    for arg in args:
        if arg is not None:
            return Decimal(str(arg))
    return Decimal("0.00")

def process_interest_items(interest_items: List[InterestItemV1], tax_year: int) -> List[InterestItemV1]:
    # Since they are already converted in InterestItemV1 init, we can just return them.
    # But wait, to match legacy output exactly (which returns dicts or objects), we keep them as InterestItemV1.
    return interest_items

def process_market_discount_items(market_discount_items: List[MarketDiscountItemV1]) -> List[InterestItemV1]:
    processed = []
    for item in market_discount_items:
        gain = max(Decimal("0.00"), item.proceeds - item.cost_basis)
        taxable_interest = min(item.accrued_market_discount, gain)
        
        if taxable_interest > Decimal("0.00"):
            processed.append(InterestItemV1(
                item_id=item.item_id or f"market_discount_{item.payer_name or 'unknown'}",
                source_statement_id=None,
                statement_issuer_name=item.payer_name,
                source_document_type="1099-B",
                source_box="Accrued Market Discount",
                payer_name=item.payer_name or "Unknown Brokerage",
                payer_reported_amount=taxable_interest,
                tax_character="TAXABLE_INTEREST",
                is_series_ee_or_i_interest=False
            ))
    return processed

def process_dividend_items(dividend_items: List[DividendItemV1], tax_year: int) -> List[DividendItemV1]:
    return dividend_items

def aggregate_interest_entries(processed_interest_items: List[InterestItemV1]) -> List[Dict[str, Any]]:
    taxable_items = [item for item in processed_interest_items if item.tax_character == 'TAXABLE_INTEREST']
    grouped = {}
    standalone_counter = 0
    
    for item in taxable_items:
        stmt_id = item.source_statement_id or ""
        doc_type = item.source_document_type or ""
        issuer = item.statement_issuer_name
        payer = item.payer_name or "Unnamed Payer"
        
        display_name = issuer if (doc_type == "SUBSTITUTE_STATEMENT" and issuer) else payer
        
        if not stmt_id and not item.payer_name:
            standalone_counter += 1
            key = (f"standalone_{standalone_counter}", display_name)
        else:
            key = (stmt_id, display_name)
            
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(item)
        
    aggregated = []
    for (stmt_id, display_name), items in grouped.items():
        total_amount = sum(item.payer_reported_amount for item in items)
        aggregated.append({
            'payer_name': display_name,
            'payer_reported_amount': total_amount,
            'source_statement_id': stmt_id if stmt_id else None
        })
    return aggregated

def aggregate_dividend_entries(processed_dividend_items: List[DividendItemV1]) -> List[Dict[str, Any]]:
    grouped = {}
    standalone_counter = 0
    
    for item in processed_dividend_items:
        stmt_id = item.source_statement_id or ""
        doc_type = item.source_document_type or ""
        issuer = item.statement_issuer_name
        payer = item.payer_name or "Unnamed Payer"
        
        display_name = issuer if (doc_type == "SUBSTITUTE_STATEMENT" and issuer) else payer
        
        if not stmt_id and not item.payer_name:
            standalone_counter += 1
            key = (f"standalone_{standalone_counter}", display_name)
        else:
            key = (stmt_id, display_name)
            
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(item)
        
    aggregated = []
    for (stmt_id, display_name), items in grouped.items():
        total_amount = sum(item.ordinary_dividends for item in items)
        aggregated.append({
            'payer_name': display_name,
            'payer_reported_amount': total_amount,
            'source_statement_id': stmt_id if stmt_id else None
        })
    return aggregated

def any_special_case(flags, interest_items: List[InterestItemV1] = None, dividend_items: List[DividendItemV1] = None) -> bool:
    if flags:
        for attr in ["has_nominee_distribution", "has_accrued_interest", "has_oid", "has_abp_adjustment", "has_seller_financed_mortgage", "has_form_8814", "has_tax_exempt_bond_premium", "has_contingent_payment_debt"]:
            if getattr(flags, attr, False) is True:
                return True
        
    if interest_items:
        for item in interest_items:
            if item.nominee_amount > Decimal("0.00"):
                return True
            if item.accrued_interest > Decimal("0.00"):
                return True
            if item.is_seller_financed:
                return True
            if item.oid_broker_adjustment_amount > Decimal("0.00") or item.oid_taxpayer_computed_adjustment > Decimal("0.00") or item.oid_adjustment > Decimal("0.00"):
                return True
            if item.abp_broker_adjustment_amount > Decimal("0.00") or item.abp_taxpayer_computed_adjustment > Decimal("0.00") or item.bond_premium_adjustment > Decimal("0.00"):
                return True
                
    if dividend_items:
        for item in dividend_items:
            if item.nominee_ordinary_amount > Decimal("0.00") or item.nominee_qualified_amount > Decimal("0.00") or item.nominee_amount > Decimal("0.00"):
                return True
                
    return False

def calculate_schedule_b_v1(inputs: ScheduleBInputsV1) -> ScheduleBResultV1:
    errors: List[ValidationIssue] = []
    
    # 1. Validation identity & tax year
    validate_identity(inputs, errors)
    validate_tax_year(inputs.tax_year, {2024, 2025}, errors)
    
    # 2. Process interest and dividend items
    processed_interest = process_interest_items(inputs.interest_items, inputs.tax_year) + process_market_discount_items(inputs.market_discount_items)
    processed_dividend = process_dividend_items(inputs.dividend_items, inputs.tax_year)
    
    line_1_payer_entries = aggregate_interest_entries(processed_interest)
    interest_subtotal = sum_decimal(entry['payer_reported_amount'] for entry in line_1_payer_entries)
    line_2_total_interest = interest_subtotal
    
    # Line 3 Form 8815 Exclusion
    line_3_excludable_savings_bond_interest = Decimal("0.00")
    if inputs.form_8815 is not None and inputs.form_8815.is_completed:
        # Note: in schema expression: Decimal(str(form_8815['line_14_excludable_interest']))
        # But wait! In the model, we mapped line_14_excludable_interest or is_completed.
        # Let's check how the form_8815 is represented or if it has line_14_excludable_interest in input.
        # Yes, we will check if it has line_14_excludable_interest. Let's make sure it handles both object attribute and dict-fallback safely.
        if hasattr(inputs.form_8815, "line_14_excludable_interest"):
            line_3_excludable_savings_bond_interest = Decimal(str(inputs.form_8815.line_14_excludable_interest))
        elif isinstance(inputs.form_8815, dict):
            line_3_excludable_savings_bond_interest = Decimal(str(inputs.form_8815.get("line_14_excludable_interest", "0.00")))
            
    line_4_raw_calculation = line_2_total_interest - line_3_excludable_savings_bond_interest
    line_4_surface_value = line_4_raw_calculation if line_4_raw_calculation >= Decimal("0.00") else None
    
    line_5_payer_entries = aggregate_dividend_entries(processed_dividend)
    dividend_subtotal = sum_decimal(entry['payer_reported_amount'] for entry in line_5_payer_entries)
    line_6_total_ordinary_dividends = dividend_subtotal
    
    total_tax_exempt_interest = sum_decimal(item.payer_reported_amount for item in processed_interest if item.tax_character == 'TAX_EXEMPT_INTEREST')
    total_qualified_dividends = sum_decimal(item.qualified_dividends for item in processed_dividend)
    total_exempt_interest_dividends = sum_decimal(item.exempt_interest_dividends for item in processed_dividend)
    
    form_1040_line_2a = total_tax_exempt_interest + total_exempt_interest_dividends
    
    is_part_iii_required = (
        line_4_raw_calculation > Decimal('1500.00') or 
        line_6_total_ordinary_dividends > Decimal('1500.00') or 
        inputs.foreign_account_q1 is True or 
        inputs.foreign_trust_q8 is True
    )
    
    is_schedule_b_required = (
        line_4_raw_calculation > Decimal('1500.00') or 
        line_6_total_ordinary_dividends > Decimal('1500.00') or 
        inputs.foreign_account_q1 is True or 
        inputs.foreign_trust_q8 is True or 
        line_3_excludable_savings_bond_interest > Decimal('0.00') or 
        any_special_case(inputs.special_case_flags, inputs.interest_items, inputs.dividend_items)
    )
    
    line_7a_q1_surface = inputs.foreign_account_q1 if is_part_iii_required else None
    line_7a_q2_surface = inputs.fbar_q2 if (is_part_iii_required and inputs.foreign_account_q1 is True) else None
    line_7b_surface = ', '.join(inputs.foreign_countries) if (is_part_iii_required and inputs.foreign_account_q1 is True and inputs.fbar_q2 is True and inputs.foreign_countries) else None
    line_8_surface = inputs.foreign_trust_q8 if is_part_iii_required else None
    
    # 3. Perform Validation
    detect_unsupported_cases(inputs, errors)
    validate_amounts(inputs, errors)
    validate_form_8815(inputs, line_3_excludable_savings_bond_interest, errors)
    validate_part_iii(inputs, is_part_iii_required, errors)
    
    if line_4_raw_calculation < Decimal("0.00"):
        errors.append(ValidationIssue("NEGATIVE_TAXABLE_INTEREST", "line_4_raw_calculation", message="Taxable interest cannot be negative."))
        
    # Mask taxpayer SSN
    raw_ssn = str(inputs.taxpayer_ssn or "")
    if len(raw_ssn) >= 4:
        taxpayer_ssn_masked = f"***-**-{raw_ssn[-4:]}"
    else:
        taxpayer_ssn_masked = "***-**-XXXX"
        
    is_v1_supported = not any_special_case(inputs.special_case_flags, inputs.interest_items, inputs.dividend_items)
    can_file = is_v1_supported and len(errors) == 0
    should_attach_schedule_b = is_schedule_b_required and can_file
    
    return ScheduleBResultV1(
        taxpayer_name=inputs.taxpayer_name,
        taxpayer_ssn_masked=taxpayer_ssn_masked,
        tax_year=inputs.tax_year,
        processed_interest_items=processed_interest,
        processed_dividend_items=processed_dividend,
        line_1_payer_entries=line_1_payer_entries,
        interest_subtotal=interest_subtotal,
        line_2_total_interest=line_2_total_interest,
        line_3_excludable_savings_bond_interest=line_3_excludable_savings_bond_interest,
        line_4_raw_calculation=line_4_raw_calculation,
        line_4_surface_value=line_4_surface_value,
        line_5_payer_entries=line_5_payer_entries,
        dividend_subtotal=dividend_subtotal,
        line_6_total_ordinary_dividends=line_6_total_ordinary_dividends,
        total_tax_exempt_interest=total_tax_exempt_interest,
        total_qualified_dividends=total_qualified_dividends,
        total_exempt_interest_dividends=total_exempt_interest_dividends,
        form_1040_line_2a=form_1040_line_2a,
        is_part_iii_required=is_part_iii_required,
        is_schedule_b_required=is_schedule_b_required,
        line_7a_q1_surface=line_7a_q1_surface,
        line_7a_q2_surface=line_7a_q2_surface,
        line_7b_surface=line_7b_surface,
        line_8_surface=line_8_surface,
        blocking_errors=errors,
        review_warnings=[],
        blocking_validation_error=(len(errors) > 0),
        is_v1_supported=is_v1_supported,
        can_file=can_file,
        should_attach_schedule_b=should_attach_schedule_b,
    )
