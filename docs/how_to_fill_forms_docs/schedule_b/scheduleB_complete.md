# IRS Schedule B (Form 1040) 填表與計算規則指南
## 2025／2024 年度標準版 — V1 一般案件填表器

> **版本定位**
>
> 本文件定義 Schedule B V1 規則引擎的最小可行範圍。V1 專注於一般利息、普通股利、已完成的 Form 8815 引用，以及 Part III 海外帳戶／海外信託問卷。
>
> 遇到 Nominee、Accrued Interest、OID、ABP、Seller-Financed Mortgage、Form 8814 等特殊案件時，V1 必須辨識並停止自動申報，不得自行猜測或套用簡化公式。

---

## 1. V1 設計目標

V1 必須做到：

1. 正確列出一般應稅利息付款人與金額。
2. 正確列出普通股利付款人與金額。
3. 正確計算 Schedule B Lines 2、3、4、6。
4. 正確將 Line 4 連動至 Form 1040 Line 2b。
5. 正確將 Line 6 連動至 Form 1040 Line 3b。
6. 正確判定是否需要檢附 Schedule B。
7. 正確判定是否需要完成 Part III。
8. 對不支援的特殊案件產生明確的阻斷錯誤。
9. 不以 `0`、`False` 或其他預設值掩蓋未知資料。

V1 不以完整支援所有投資所得規則為目標。

---

## 2. V1 支援範圍

### 2.1 支援的利息

V1 支援下列已由來源文件或上游模組明確分類的金額：

- Form 1099-INT Box 1 一般應稅利息。
- Form 1099-INT Box 3 美國儲蓄債券及 Treasury obligations 利息。
- 銀行或券商 substitute statement 上已明確標示的應稅利息。
- 已明確標示為免稅利息的金額，可保留供 Form 1040 Line 2a 使用，但不得計入 Schedule B Line 1。

V1 不自行計算 market discount、OID、bond premium 或其他債務工具調整。

### 2.2 支援的股利

V1 支援：

- Form 1099-DIV Box 1a ordinary dividends。
- Form 1099-DIV Box 1b qualified dividends，僅供 Form 1040 Line 3a 使用。
- 券商 substitute statement 上已明確分類的普通股利與合格股利。

Schedule B Line 5／6 使用普通股利，不因其中包含 qualified dividends 而減少。

### 2.3 支援的跨表引用

V1 可引用已完成的：

- Form 8815 Line 14，填入 Schedule B Line 3。

V1 不負責計算 Form 8815 本身。

### 2.4 支援的 Part III

V1 直接接收下列問卷答案：

- Line 7a 第一問：是否對海外金融帳戶具有 financial interest 或 signature authority。
- Line 7a 第二問：是否需要申報 FinCEN Form 114（FBAR）。
- Line 7b：需要申報 FBAR 時的海外帳戶國家名稱。
- Line 8：是否收到海外信託分配，或為海外信託的 grantor／transferor。

V1 不自行計算 FBAR 門檻，也不自行判斷 Form 3520、Form 8938 或其他國際申報義務。

---

## 3. V1 不支援的特殊案件

若偵測到下列任一情況，V1 必須設定：

```text
is_v1_supported = false
can_file = false
blocking_validation_error = true
```

並產生對應錯誤代碼：

| 特殊案件 | 建議錯誤代碼 |
|---|---|
| Nominee interest／dividends | `UNSUPPORTED_NOMINEE_DISTRIBUTION` |
| Accrued interest | `UNSUPPORTED_ACCRUED_INTEREST` |
| Form 1099-OID 或 OID adjustment | `UNSUPPORTED_OID` |
| Amortizable bond premium | `UNSUPPORTED_ABP_ADJUSTMENT` |
| Seller-financed mortgage interest | `UNSUPPORTED_SELLER_FINANCED_MORTGAGE` |
| Form 8814 | `UNSUPPORTED_FORM_8814` |
| Tax-exempt bond premium | `UNSUPPORTED_TAX_EXEMPT_BOND_PREMIUM` |
| Contingent payment debt instrument | `UNSUPPORTED_CONTINGENT_PAYMENT_DEBT` |
| 無法確定利息或股利的聯邦稅務性質 | `UNKNOWN_TAX_CHARACTER` |
| Form 8815 尚未完成但要求 Line 3 排除額 | `FORM_8815_NOT_COMPLETED` |
| Part III 問卷答案不足 | `PART_III_ANSWER_MISSING` |
| 輸入金額為負數 | `NEGATIVE_AMOUNT` |

> **安全原則**：特殊案件即使 Schedule B 必須申報，也不代表 V1 可以自動完成。`is_schedule_b_required` 與 `is_v1_supported` 必須分開判定。

---

## 4. 資料型別原則

### 4.1 金額

正式引擎不得使用 binary `float` 作為稅務計算的主要型別。

建議使用：

```text
Decimal
```

或：

```text
integer cents
```

所有金額 must 滿足：

```text
amount >= 0
```

內部計算保留 cents；輸出至紙本 PDF 或電子申報資料時，再依整份 Form 1040 的統一 rounding policy 處理。

### 4.2 未知值

`null` 表示未知或尚未回答，不等同於 `0` 或 `False`。

例如：

```text
foreign_account_q1 = null
```

表示尚未取得答案，不可自動當作 `No`。

---

## 5. Layer 1 — 原始輸入模型

```text
ScheduleBInputsV1 = {
  taxpayer_name: str
  taxpayer_ssn: str
  tax_year: int                    # 2024 | 2025

  interest_items: InterestItemV1[]
  dividend_items: DividendItemV1[]
  market_discount_items: MarketDiscountItemV1[]

  form_8815: Form8815ReferenceV1 | null
  
  foreign_account_q1: bool | null
  fbar_q2: bool | null
  foreign_countries: str[] | null
  foreign_trust_q8: bool | null

  special_case_flags: SpecialCaseFlagsV1
}
```

### 5.1 InterestItemV1

```text
InterestItemV1 = {
  item_id: str
  source_statement_id: str | null
  statement_issuer_name: str | null
  source_document_type: str        # 1099-INT | SUBSTITUTE_STATEMENT | OTHER
  source_box: str | null           # 1 | 3 | 8 | null

  payer_name: str
  payer_reported_amount: Decimal

  tax_character:
    TAXABLE_INTEREST
    | TAX_EXEMPT_INTEREST
    | UNKNOWN

  is_series_ee_or_i_interest: bool | null
}
```

規則：

- `TAXABLE_INTEREST`：可列入 Schedule B Line 1。
- `TAX_EXEMPT_INTEREST`：不得列入 Schedule B Line 1；可交由 Form 1040 Line 2a 模組處理。
- `UNKNOWN`：阻止自動申報。
- `payer_reported_amount` 指付款人或券商在適用表單／statement 上報告的金額，不使用含義不清的 `gross_amount`。

### 5.2 DividendItemV1

```text
DividendItemV1 = {
  item_id: str
  source_statement_id: str | null
  statement_issuer_name: str | null
  source_document_type: str        # 1099-DIV | SUBSTITUTE_STATEMENT | OTHER

  payer_name: str
  ordinary_dividends: Decimal      # Form 1099-DIV Box 1a
  qualified_dividends: Decimal     # Form 1099-DIV Box 1b
  exempt_interest_dividends: Decimal # Form 1099-DIV Box 12
}
```

驗證：

```text
0 <= qualified_dividends <= ordinary_dividends
```

若不成立：

```text
blocking_error_code = QUALIFIED_DIVIDENDS_EXCEED_ORDINARY
```

### 5.3 Form8815ReferenceV1

```text
Form8815ReferenceV1 = {
  is_completed: bool
  line_14_excludable_interest: Decimal
  eligible_series_ee_i_interest_included_in_line_2: Decimal
}
```

V1 只引用已完成的 Form 8815，不計算其教育費用、收入限制或其他欄位。

驗證：

```text
if line_14_excludable_interest > 0:
    require is_completed == true

0 <= line_14_excludable_interest

line_14_excludable_interest
    <= eligible_series_ee_i_interest_included_in_line_2
```

### 5.4 SpecialCaseFlagsV1

```text
SpecialCaseFlagsV1 = {
  has_nominee_distribution: bool
  has_accrued_interest: bool
  has_oid: bool
  has_abp_adjustment: bool
  has_market_discount: bool
  has_seller_financed_mortgage: bool
  has_form_8814: bool
  has_tax_exempt_bond_premium: bool
  has_contingent_payment_debt: bool
}
```

任一旗標為 `true` 時（排除 `has_market_discount`），V1 不得產生可送出的申報結果。

### 5.5 MarketDiscountItemV1

```text
MarketDiscountItemV1 = {
  item_id: str
  payer_name: str
  proceeds: Decimal
  cost_basis: Decimal
  accrued_market_discount: Decimal
}
```

規則：
- 應計市場折價在處分時認列為應稅利息，金額受實際 Gain 限制：`min(accrued_market_discount, max(0, proceeds - cost_basis))`。

---

## 6. Layer 2 — 正規化與中間計算

### 6.1 利息項目分類

```text
schedule_b_taxable_interest_items =
  (interest_items where tax_character == TAXABLE_INTEREST)
  + (for item in market_discount_items:
       taxable_interest = min(item.accrued_market_discount, max(0, item.proceeds - item.cost_basis))
       if taxable_interest > 0, extract as TAXABLE_INTEREST)
```

```text
excluded_tax_exempt_interest_items =
  interest_items where tax_character == TAX_EXEMPT_INTEREST
```

若有任何：

```text
tax_character == UNKNOWN
```

則：

```text
blocking_validation_error = true
```

### 6.2 券商 statement 聚合

對同一張券商 statement 上的多筆已分類利息或股利，Schedule B 表面可按以下 key 聚合：

```text
(source_statement_id, display_name, income_category)
```

其中：
* `display_name`：若項目之 `source_document_type` 為 `"SUBSTITUTE_STATEMENT"` 且提供 `statement_issuer_name`，則 `display_name` 為 `statement_issuer_name`（即券商名稱）；否則使用其項目的 `payer_name`。
* `income_category` 為邏輯分類，在輸入模型（Layer 1）中並非實體欄位，而是依據項目所屬陣列隱含確定：
  * 若項目位於 `interest_items` 陣列，則邏輯類別為 `INTEREST`。
  * 若項目位於 `dividend_items` 陣列，則邏輯類別為 `ORDINARY_DIVIDEND`。
  * 程式實作上，應透過分開處理利息與股利明細，確保兩者不會跨類別合併。

若 `source_statement_id` 為 `null`，不得僅因付款人名稱相同就跨文件合併。

### 6.3 利息中間值

```text
interest_subtotal =
  SUM(item.payer_reported_amount
      for item in schedule_b_taxable_interest_items)
```

V1 不支援 Line 1 下方的 Nominee、Accrued Interest、OID Adjustment 或 ABP Adjustment，因此：

```text
line_2_total_interest = interest_subtotal
```

### 6.4 Form 8815 引用

```text
line_3_excludable_savings_bond_interest =
  form_8815.line_14_excludable_interest
  if form_8815 is not null and form_8815.is_completed
  else Decimal("0.00")
```

若 Form 8815 物件存在但 `is_completed == false`，不得靜默將 Line 3 當作零後繼續申報；應產生阻斷錯誤。

### 6.5 最終應稅利息

```text
line_4_raw_calculation =
  line_2_total_interest
  - line_3_excludable_savings_bond_interest
```

不得使用：

```text
max(0, line_2 - line_3)
```

若：

```text
line_4_raw_calculation < 0
```

則：

```text
line_4_surface_value = null
blocking_validation_error = true
error_code = NEGATIVE_TAXABLE_INTEREST
```

否則：

```text
line_4_surface_value = line_4_raw_calculation
```

### 6.6 股利中間值

```text
dividend_subtotal =
  SUM(item.ordinary_dividends for item in dividend_items)
```

V1 不支援 nominee dividend adjustments，因此：

```text
line_6_total_ordinary_dividends = dividend_subtotal
```

另外供 Form 1040 Line 3a 使用：

```text
total_qualified_dividends =
  SUM(item.qualified_dividends for item in dividend_items)
```

---

## 7. Layer 3 — Schedule B 表面欄位

## Part I — Interest

| 欄位 | V1 輸出 | 規則 |
|---|---|---|
| Header Name | `taxpayer_name` | 與 Form 1040 一致 |
| Header SSN | `taxpayer_ssn` | 與 Form 1040 一致 |
| Line 1 | `line_1_payer_entries` | 列出應稅利息付款人與付款人申報金額 |
| Line 2 | `line_2_total_interest` | Line 1 金額合計 |
| Line 3 | `line_3_excludable_savings_bond_interest` | 引用完成的 Form 8815 Line 14 |
| Line 4 | `line_4_surface_value` | Line 2 減 Line 3 |

### Line 1 表面項目

```text
Line1PayerEntryV1 = {
  payer_name: str
  reported_amount: Decimal
  source_statement_id: str | null
}
```

券商 statement 可顯示券商名稱與該 statement 的應稅利息總額，不需在 Schedule B 表面逐一列出每一底層證券。

## Part II — Ordinary Dividends

| 欄位 | V1 輸出 | 規則 |
|---|---|---|
| Line 5 | `line_5_payer_entries` | 列出普通股利付款人與 Box 1a 金額 |
| Line 6 | `line_6_total_ordinary_dividends` | Line 5 金額合計 |

### Line 5 表面項目

```text
Line5PayerEntryV1 = {
  payer_name: str
  reported_amount: Decimal
  source_statement_id: str | null
}
```

券商 statement 可顯示券商名稱與該 statement 的 ordinary dividends 總額。

---

## 8. Schedule B 申報判定

### 8.1 特殊案件觸發

IRS 可能因特殊情況要求 Schedule B，即使 Line 4 或 Line 6 未超過 $1,500。V1 仍應判斷 Schedule B 可能是 required，但因特殊計算尚未支援，必須阻止自動申報。

```text
has_schedule_b_special_case =
  any(SpecialCaseFlagsV1 == true)
```

### 8.2 Schedule B 是否需要檢附

```text
is_schedule_b_required =
    line_4_raw_calculation > Decimal("1500.00")
    OR line_6_total_ordinary_dividends > Decimal("1500.00")
    OR foreign_account_q1 is True
    OR foreign_trust_q8 is True
    OR has_schedule_b_special_case
    OR line_3_excludable_savings_bond_interest > Decimal("0.00")
```

注意：

- 利息門檻使用最終 taxable interest，也就是 **Line 4**。
- 股利門檻使用 **Line 6**。
- 規則是 `>`，不是 `>=`。

### 8.3 V1 是否可完成申報

```text
is_v1_supported =
  NOT has_schedule_b_special_case
```

```text
can_file =
    is_v1_supported
    AND blocking_errors is empty
```

```text
should_attach_schedule_b =
    is_schedule_b_required
    AND can_file
```

若 Schedule B 不需要檢附，仍可把：

```text
line_4_surface_value -> Form 1040 Line 2b
line_6_total_ordinary_dividends -> Form 1040 Line 3b
```

---

## 9. Part III 判定與表面留白

### 9.1 Part III 是否必須完成

```text
is_part_iii_required =
    line_4_raw_calculation > Decimal("1500.00")
    OR line_6_total_ordinary_dividends > Decimal("1500.00")
    OR foreign_account_q1 is True
    OR foreign_trust_q8 is True
```

### 9.2 Part III 非必要時

V1 採用以下 renderer policy：

```text
if is_part_iii_required == false:
    line_7a_q1_surface = null
    line_7a_q2_surface = null
    line_7b_surface = null
    line_8_surface = null
```

這代表表面留白，不代表將答案改寫為 `No`。

原始問卷答案仍可保留在輸入層，不應因表面留白而遺失。

### 9.3 Part III 填寫完整度驗證與篩選問題

以下兩大海外篩選問題（Screening Questions）在任何情況下都**必須明確回答**，且不得為 `null`：
* `foreign_account_q1` 必須為 `True` 或 `False`
* `foreign_trust_q8` 必須為 `True` 或 `False`

這是因為此兩大問題本身即為決定「是否必須填寫 Part III」的核心篩選條件，故必須明確回答。若其為 `null`，則規則引擎會立刻拋出阻斷錯誤：
```text
blocking_validation_error = true
error_code = PART_III_ANSWER_MISSING
```

當已明確回答且 `is_part_iii_required` 為 `true` 時，則需進一步依據以下相依關係進行驗證：

#### Line 7a 第二問 (FBAR 申報義務)

只有 Line 7a 第一問回答 `True` 時才強制作答：

```text
if foreign_account_q1 is True:
    require fbar_q2 is bool
else:
    line_7a_q2_surface = null
```

#### Line 7b (海外國家清單)

只有 FBAR 申報義務 `fbar_q2` 為 `True` 時才填國家：

```text
if fbar_q2 is True:
    require foreign_countries is not empty
    line_7b_surface = join(unique_normalized_countries, ", ")
else:
    line_7b_surface = null
```

---

## 10. 跨表連動

```text
Form 1040 Line 2a =
  SUM(TAX_EXEMPT_INTEREST items) + SUM(exempt_interest_dividends items)
```

```text
Form 1040 Line 2b =
  line_4_surface_value
```

```text
Form 1040 Line 3a =
  total_qualified_dividends
```

```text
Form 1040 Line 3b =
  line_6_total_ordinary_dividends
```

Schedule B V1 不計算所得稅稅率，也不計算 Qualified Dividends and Capital Gain Tax Worksheet。

---

## 11. 輸出模型

```text
ScheduleBResultV1 = {
  taxpayer_name: str
  taxpayer_ssn_masked: str
  tax_year: int

  line_1_payer_entries: Line1PayerEntryV1[]
  line_2_total_interest: Decimal
  line_3_excludable_savings_bond_interest: Decimal
  line_4_raw_calculation: Decimal
  line_4_surface_value: Decimal | null

  line_5_payer_entries: Line5PayerEntryV1[]
  line_6_total_ordinary_dividends: Decimal

  total_tax_exempt_interest: Decimal
  total_qualified_dividends: Decimal

  is_schedule_b_required: bool
  is_part_iii_required: bool
  is_v1_supported: bool
  should_attach_schedule_b: bool
  can_file: bool

  line_7a_q1_surface: bool | null
  line_7a_q2_surface: bool | null
  line_7b_surface: str | null
  line_8_surface: bool | null

  blocking_errors: ValidationIssue[]
  review_warnings: ValidationIssue[]
}
```

```text
ValidationIssue = {
  code: str
  field: str | null
  item_id: str | null
  message: str
}
```

`taxpayer_ssn` 不應出現在一般 log、debug output 或測試 snapshot 中。輸出可使用遮罩格式，例如：

```text
***-**-6789
```

---

## 12. 核心計算偽代碼

```python
from decimal import Decimal

ZERO = Decimal("0.00")
THRESHOLD = Decimal("1500.00")


def calculate_schedule_b_v1(inputs):
    errors = []
    warnings = []

    validate_identity(inputs, errors)
    validate_tax_year(inputs, errors)
    validate_amounts(inputs, errors)
    validate_dividends(inputs.dividend_items, errors)
    detect_unsupported_cases(inputs.special_case_flags, errors)

    taxable_interest_items = []
    tax_exempt_interest_items = []

    for item in inputs.interest_items:
        if item.tax_character == "TAXABLE_INTEREST":
            taxable_interest_items.append(item)
        elif item.tax_character == "TAX_EXEMPT_INTEREST":
            tax_exempt_interest_items.append(item)
        else:
            errors.append(issue("UNKNOWN_TAX_CHARACTER", item.item_id))

    line_1_entries = aggregate_interest_for_surface(taxable_interest_items)
    line_2 = sum_decimal(e.reported_amount for e in line_1_entries)

    line_3 = calculate_form_8815_reference(inputs.form_8815, line_2, errors)
    line_4_raw = line_2 - line_3

    if line_4_raw < ZERO:
        line_4_surface = None
        errors.append(issue("NEGATIVE_TAXABLE_INTEREST", "line_4"))
    else:
        line_4_surface = line_4_raw

    line_5_entries = aggregate_dividends_for_surface(inputs.dividend_items)
    line_6 = sum_decimal(e.reported_amount for e in line_5_entries)

    total_qualified = sum_decimal(
        item.qualified_dividends for item in inputs.dividend_items
    )

    total_tax_exempt = sum_decimal(
        item.payer_reported_amount for item in tax_exempt_interest_items
    )

    has_special_case = any_special_case(inputs.special_case_flags)

    is_schedule_b_required = (
        line_4_raw > THRESHOLD
        or line_6 > THRESHOLD
        or inputs.foreign_account_q1 is True
        or inputs.foreign_trust_q8 is True
        or has_special_case
        or line_3 > ZERO
    )

    is_part_iii_required = (
        line_4_raw > THRESHOLD
        or line_6 > THRESHOLD
        or inputs.foreign_account_q1 is True
        or inputs.foreign_trust_q8 is True
    )

    part_iii = render_part_iii(
        inputs=inputs,
        required=is_part_iii_required,
        errors=errors,
    )

    is_v1_supported = not has_special_case
    can_file = is_v1_supported and len(errors) == 0

    return ScheduleBResultV1(
        line_1_payer_entries=line_1_entries,
        line_2_total_interest=line_2,
        line_3_excludable_savings_bond_interest=line_3,
        line_4_raw_calculation=line_4_raw,
        line_4_surface_value=line_4_surface,
        line_5_payer_entries=line_5_entries,
        line_6_total_ordinary_dividends=line_6,
        total_tax_exempt_interest=total_tax_exempt,
        total_qualified_dividends=total_qualified,
        is_schedule_b_required=is_schedule_b_required,
        is_part_iii_required=is_part_iii_required,
        is_v1_supported=is_v1_supported,
        should_attach_schedule_b=is_schedule_b_required and can_file,
        can_file=can_file,
        blocking_errors=errors,
        review_warnings=warnings,
        **part_iii,
    )
```

---

## 13. 最低必要測試案例

### Test 1 — 低於門檻，不需 Schedule B

```json
{
  "interest": 150.00,
  "ordinary_dividends": 405.00,
  "foreign_account_q1": false,
  "foreign_trust_q8": false
}
```

預期：

```text
Line 4 = 150.00
Line 6 = 405.00
is_schedule_b_required = false
is_part_iii_required = false
Part III surface fields = null
```

### Test 2 — Line 4 超過門檻

```text
Line 2 = 2000.00
Line 3 = 0.00
Line 4 = 2000.00
```

預期：

```text
is_schedule_b_required = true
is_part_iii_required = true
Part III answers required
```

### Test 3 — Line 4 正好等於門檻

```text
Line 4 = 1500.00
```

預期：

```text
金額門檻本身不觸發 Schedule B／Part III
```

### Test 4 — 普通股利超過門檻

```text
Line 6 = 1500.01
```

預期：

```text
is_schedule_b_required = true
is_part_iii_required = true
```

### Test 5 — Form 8815 引用

```text
Line 2 = 1000.00
Eligible EE/I interest = 600.00
Form 8815 Line 14 = 400.00
```

預期：

```text
Line 3 = 400.00
Line 4 = 600.00
is_schedule_b_required = true
is_part_iii_required = false
```

### Test 6 — Form 8815 排除額過高

```text
Eligible EE/I interest = 200.00
Form 8815 Line 14 = 250.00
```

預期：

```text
blocking error = FORM8815_EXCLUSION_EXCEEDS_ELIGIBLE_INTEREST
can_file = false
```

### Test 7 — Qualified dividends 異常

```text
ordinary_dividends = 100.00
qualified_dividends = 120.00
```

預期：

```text
blocking error = QUALIFIED_DIVIDENDS_EXCEED_ORDINARY
```

### Test 8 — 海外帳戶 Yes、FBAR 狀態未知

```text
foreign_account_q1 = true
fbar_q2 = null
```

預期：

```text
is_schedule_b_required = true
is_part_iii_required = true
blocking error = PART_III_ANSWER_MISSING
```

### Test 9 — FBAR Yes、國家缺失

```text
foreign_account_q1 = true
fbar_q2 = true
foreign_countries = []
```

預期：

```text
blocking error = FBAR_COUNTRY_MISSING
```

### Test 10 — 偵測到 ABP

```text
has_abp_adjustment = true
```

預期：

```text
is_schedule_b_required = true
is_v1_supported = false
can_file = false
blocking error = UNSUPPORTED_ABP_ADJUSTMENT
```

---

## 14. V1 完成條件

V1 可視為完成，必須同時滿足：

- 一般 1099-INT taxable interest 可正確進入 Lines 1、2、4。
- 一般 1099-DIV ordinary dividends 可正確進入 Lines 5、6。
- Qualified dividends 可正確提供給 Form 1040 Line 3a。
- Tax-exempt interest 不會誤入 Schedule B Line 1。
- 已完成的 Form 8815 Line 14 可正確引用至 Line 3。
- Line 4 與 Line 6 的 `$1,500` 邊界測試正確。
- Part III 的必要答案與條件留白正確。
- 所有特殊案件都能可靠阻斷，不會使用錯誤的錯誤公式繼續申報。
- 所有正式金額均使用 `Decimal` 或 integer cents。
- 所有 blocking error 均具有可測試的錯誤代碼。

---

## 15. V2 以後再處理

下列功能不屬於 V1：

- Nominee interest／dividend adjustments。
- Accrued interest。
- OID 與 acquisition premium。
- Amortizable bond premium 與 Section 171 election。
- Market discount。
- Seller-financed mortgage。
- Form 8814。
- Form 6251 private activity bond AMT 處理。
- Schedule A Line 16 ABP excess。
- Form 3520、Form 8938 與 FBAR 門檻計算。

---

## 16. 官方參考資料

- 2025 Schedule B (Form 1040):  
  https://www.irs.gov/pub/irs-prior/f1040sb--2025.pdf

- 2025 Instructions for Schedule B (Form 1040):  
  https://www.irs.gov/pub/irs-prior/i1040sb--2025.pdf

- 2024 Schedule B (Form 1040):  
  https://www.irs.gov/pub/irs-prior/f1040sb--2024.pdf

- 2024 Instructions for Schedule B (Form 1040):  
  https://www.irs.gov/pub/irs-prior/i1040sb--2024.pdf

> 稅法、表單及電子申報規格可能更新。正式申報前，應依對應年度 IRS 最新表單、說明及適用的電子申報 schema 再次驗證。
