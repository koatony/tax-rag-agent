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
from typing import Dict, Any, List, Tuple, Set, Optional
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


def process_market_discount_items(market_discount_items: List[MarketDiscountItemV1]) -> List[InterestItemV1]:
    processed = []
    for item in market_discount_items:
        # 稅法規則 (IRC § 1276(a)(1))：
        # 1. 應稅之折價利息，以該交易的「實際獲利 (Gain)」為上限，故虧損時（獲利為負）以 0 計算。
        # 2. 最終應申報利息為「已累積折價」與「實際獲利」兩者取小者：min(accrued_market_discount, gain)。
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


def aggregate_interest_entries(processed_interest_items: List[InterestItemV1]) -> List[Dict[str, Any]]:
    """
    將所有「應稅利息」依同一付款人/券商對帳單進行合併與金額加總。
    用意：合併同來源之利息明細，產生最終填入 Schedule B Line 1 的付款人清單。

    防禦性 Fallback 機制：
    1. 若未捕獲付款人名稱 (payer_name 為空/None)，預設替換為 "Unnamed Payer" 作為醒目標記。
    2. 若未提供對帳單 ID (source_statement_id 為空)，則安全降級為 ""，此時所有同名的項目會自動依名稱合併。
    3. 若同時缺失對帳單 ID 與付款人名稱，則透過獨立計數器 (standalone_counter) 確保它們不會被錯誤地合併在同一個 "Unnamed Payer"，而是維持獨立行項目。
    """
    taxable_items = [item for item in processed_interest_items if item.tax_character == 'TAXABLE_INTEREST']
    grouped = {}
    standalone_counter = 0
    
    for item in taxable_items:
        stmt_id = item.source_statement_id or ""
        doc_type = item.source_document_type or ""
        issuer = item.statement_issuer_name
        payer = item.payer_name or "Unnamed Payer"
        
        # 決定申報時顯示的付款人名稱：
        # 如果是券商綜合對帳單 (SUBSTITUTE_STATEMENT)，優先以券商名稱 (issuer) 作為合併與申報主體（以對齊綜合對帳單申報）；
        # 若是獨立的 1099-INT 表單，則直接使用個別付款人名稱 (payer)。
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
    """
    將所有「股利明細」依同一付款人/券商對帳單進行合併與金額加總。
    用意：合併同來源之股利明細，產生最終填入 Schedule B Line 5 的付款人清單。

    防禦性 Fallback 機制：
    1. 若未捕獲付款人名稱 (payer_name 為空/None)，預設替換為 "Unnamed Payer" 作為醒目標記。
    2. 若未提供對帳單 ID (source_statement_id 為空)，則安全降級為 ""，此時所有同名的項目會自動依名稱合併。
    3. 若同時缺失對帳單 ID 與付款人名稱，則透過獨立計數器 (standalone_counter) 確保它們不會被錯誤地合併在同一個 "Unnamed Payer"，而是維持獨立行項目。
    """
    grouped = {}
    standalone_counter = 0
    
    for item in processed_dividend_items:
        stmt_id = item.source_statement_id or ""
        doc_type = item.source_document_type or ""
        issuer = item.statement_issuer_name
        payer = item.payer_name or "Unnamed Payer"
        
        # 決定申報時顯示的付款人名稱：
        # 如果是券商綜合對帳單 (SUBSTITUTE_STATEMENT)，優先以券商名稱 (issuer) 作為合併與申報主體（以對齊綜合對帳單申報）；
        # 若是獨立的 1099-DIV 表單，則直接使用個別付款人名稱 (payer)。
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
    return False

def calculate_schedule_b_v1(inputs: ScheduleBInputsV1, allowed_years: Optional[Set[int]] = None) -> ScheduleBResultV1:
    errors: List[ValidationIssue] = []
    
    if allowed_years is None:
        try:
            import os
            import json
            current_dir = os.path.dirname(os.path.abspath(__file__))
            schema_path = os.path.abspath(os.path.join(current_dir, "..", "..", "docs", "how_to_fill_forms_docs", "schedule_b", "schedule_b_schema.json"))
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_data = json.load(f)
            allowed_years = set(schema_data.get("supported_tax_years", []))
        except Exception:
            allowed_years = {}

    # 1. Validation identity & tax year
    # 檢測是否符合基本資料與稅務年度
    validate_identity(inputs, errors)
    validate_tax_year(inputs.tax_year, allowed_years, errors)

    if any(e.code == "UNSUPPORTED_TAX_YEAR" for e in errors):
        raw_ssn = str(inputs.taxpayer_ssn or "")
        ssn_masked = f"***-**-{raw_ssn[-4:]}" if len(raw_ssn) >= 4 else "***-**-XXXX"
        return ScheduleBResultV1(
            taxpayer_name=inputs.taxpayer_name,
            taxpayer_ssn_masked=ssn_masked,
            tax_year=inputs.tax_year,
            blocking_errors=errors,
            can_file=False
        )
    
    # 2. Process interest and dividend items
    # 先計算出扣除accrued_market_discount的利息收入
    processed_interest = inputs.interest_items + process_market_discount_items(inputs.market_discount_items)
    processed_dividend = inputs.dividend_items
    
    
    # 填表 Line 1：將來自同一個銀行或券商的利息合併加總（免得報稅表寫不下，比如把 Chase 的多個帳戶利息合算成一行）
    line_1_payer_entries = aggregate_interest_entries(processed_interest)

    
    # 填表 Line 2：把上面各家合併後的利息「通通加總起來」，這就是您今年所有銀行利息的總和
    interest_subtotal = sum_decimal(entry['payer_reported_amount'] for entry in line_1_payer_entries)
    line_2_total_interest = interest_subtotal
    
    # Line 3 Form 8815 Exclusion (教育儲蓄債券利息排除額)
    # 若有填寫 Form 8815，則直接扣除其計算完畢的可排除金額 (Line 14)
    line_3_excludable_savings_bond_interest = Decimal("0.00")
    if inputs.form_8815.is_completed:
        line_3_excludable_savings_bond_interest = inputs.form_8815.line_14_excludable_interest
            
    # 填表 Line 4：將總利息 (Line 2) 減去教育債券排除額 (Line 3)，得出最終的「應稅利息總額」
    # 這是最後要填入實體 Schedule B Line 4 以及 Form 1040 Line 2b 的申報數值 (若小於 0 則設為 None/空白)
    line_4_raw_calculation = line_2_total_interest - line_3_excludable_savings_bond_interest
    line_4_surface_value = line_4_raw_calculation if line_4_raw_calculation >= Decimal("0.00") else None
    
    # 填表 Line 5：將來自同一個地方發的股利合併加總（比如把 Vanguard 的多筆股利合併成一行）
    line_5_payer_entries = aggregate_dividend_entries(processed_dividend)
    
    # 填表 Line 6：把上面各家合併後的股利「通通加總起來」，這就是您今年所有普通股利的總和
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
    
    # 填表 Part III：海外帳戶與信託問卷（只有在利息或股利合計超過 $1,500，或本身有海外帳戶時才需要回答，否則實體表單一律留空 None）
    # - Line 7a Q1: 是否擁有海外金融帳戶
    # - Line 7a Q2: 是否需要申報海外資產 FBAR (只有在 Q1 為 Yes 時才需要回答)
    # - Line 7b: 填入海外國家的名稱 (只有在 Q1 與 Q2 皆為 Yes 且有資料時才填寫)
    # - Line 8: 是否與海外信託有資金往來
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
