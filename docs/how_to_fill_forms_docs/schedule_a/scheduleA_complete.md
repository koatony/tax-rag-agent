# IRS Schedule A (Form 1040) 填表與計算規則指南
## 2025／2024 年度標準版 — V1 一般案件填表器

> **版本定位**
>
> 本文件定義 Schedule A V1 規則引擎的最小可行範圍。V1 專注於一般納稅人的簡單醫療費用、州與地方稅、單一簡單 Form 1098 房貸利息，以及有完整紀錄的現金類慈善捐贈。
>
> 遇到 Marketplace 保費、LTC 保費、SALT 高所得 worksheet、複雜房貸、投資利息、非現金捐贈、慈善 carryover、Form 4684、Line 16 特殊扣除等案件時，V1 必須辨識並停止自動申報，不得自行猜測或以 `0` 載入尚未完成的計算。

---

## 1. V1 設計目標

V1 必須做到：

1. 正確計算 Schedule A Lines 1–4 的簡單醫療費用扣除。
2. 正確計算 Lines 5a–7 的一般州與地方稅扣除。
3. 正確套用 2024 與 2025 不同的 SALT cap。
4. 正確將單一簡單 Form 1098 的合格房貸利息與 points 填入 Line 8a。
5. 正確將有完整文件的現金、支票、信用卡及 payroll 慈善捐贈填入 Line 11。
6. 正確計算 Lines 4、7、10、14、17。
7. 正確將 Line 17 連動至 Form 1040 對應欄位。
8. 正確比較外部提供的標準扣除額與 Line 17。
9. 對不支援的特殊案件產生明確的阻斷錯誤。
10. 不以 `0`、`False` 或其他預設值掩蓋未知資料。
11. 保留每筆輸入的來源識別碼，以供 audit trail 與測試使用。

V1 不以完整支援所有逐項扣除規則為目標。

---

## 2. V1 支援範圍

### 2.1 支援的醫療費用

V1 支援已由來源文件或上游模組明確確認為下列狀態的簡單醫療費用：

- 支出在目前報稅年度實際支付。
- 支出對象已確認為 taxpayer、spouse 或 eligible dependent。
- 支出已確認為可列入 Schedule A 的一般醫療或牙醫費用。
- 已知納稅人實際支付金額。
- 已知保險或其他第三方補償金額。
- 已知 HSA、MSA、FSA、HRA 或其他免稅醫療帳戶支付金額。
- 不涉及 Marketplace／Form 8962。
- 不涉及 LTC 保費年齡限額。
- 不涉及自僱健康保險重複扣除。
- 不涉及前年度醫療費回收或 tax benefit rule。

V1 不自行判定高度模糊的醫療項目是否符合 Pub. 502。

### 2.2 支援的州與地方稅

V1 支援已明確分類的：

- 州與地方所得稅。
- 已由外部工具或使用者完成計算的一般銷售稅金額。
- 個人用途不動產的州與地方房地產稅。
- 依財產價值課徵且按年度課徵的個人動產稅。

Line 5a 只能選擇：

```text
州與地方所得稅
或
州與地方一般銷售稅
```

不得同時使用兩者。

V1 不自行執行 IRS Optional State Sales Tax Tables 或 Sales Tax Deduction Calculator。

### 2.3 支援的 SALT cap

V1 支援：

#### 2024

```text
非 MFS：$10,000
MFS：$5,000
```

#### 2025 一般案件

```text
非 MFS：$40,000
MFS：$20,000
```

2025 年若符合以下任一條件，且 Line 5d 超過一般 floor，V1 不自行計算高所得 SALT worksheet：

- Form 1040／1040-SR AGI 超過 $500,000。
- MFS 的 AGI 超過 $250,000。
- 完成 Form 2555。
- 完成 Form 4563。
- 排除 Puerto Rico income。

這些案件必須交由完整 SALT worksheet 模組處理。

### 2.4 支援的房貸利息

V1 支援單一簡單 Form 1098：

- 房貸由 taxpayer 或 joint-return spouse 負擔。
- 房屋為個人主要住宅或第二住宅。
- 所有貸款 proceeds 均用於 buy、build 或 substantially improve 該住宅。
- 已確認不需 Pub. 936 limitation worksheet。
- 不涉及 shared mortgage。
- 不涉及非 Form 1098 利息。
- 不涉及 seller-financed mortgage。
- 不涉及 Form 8396 mortgage interest credit。
- 不涉及 refinance points 攤提。
- Form 1098 上的 points 已由上游確認為本年度可扣金額。

V1 Line 8a使用：

```text
Form 1098 Box 1 mortgage interest
+
已確認可扣的 Form 1098 points
```

### 2.5 支援的慈善捐贈

V1 支援：

- 當年度支付。
- 給已確認的 qualified organization。
- 現金、支票、信用卡、debit card 或 payroll deduction。
- 每筆 item 代表一筆獨立付款。
- 有銀行紀錄或慈善組織書面紀錄。
- 單筆淨捐贈達 $250 時，有 contemporaneous written acknowledgment。
- 若收到 goods or services，可明確取得其價值並從捐贈額中扣除。
- 已確認不會觸發完整 charitable AGI limitation 計算。

V1 不支援 Line 12 非現金捐贈或 Line 13 carryover。

### 2.6 V1 預設為零的欄位

在確認沒有相關特殊案件時：

```text
Line 6  = 0.00
Line 8b = 0.00
Line 8c = 0.00
Line 9  = 0.00
Line 12 = 0.00
Line 13 = 0.00
Line 15 = 0.00
Line 16 = 0.00
```

若偵測到相關資料，不能繼續使用預設零值，必須產生阻斷錯誤。

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
| Marketplace／Form 1095-A／Form 8962 保費 | `UNSUPPORTED_MARKETPLACE_MEDICAL_PREMIUM` |
| Qualified LTC insurance premium | `UNSUPPORTED_LTC_PREMIUM` |
| 自僱健康保險重複扣除判定 | `UNSUPPORTED_SELF_EMPLOYED_HEALTH_INSURANCE` |
| 前年度醫療費 reimbursement／tax benefit rule | `UNSUPPORTED_PRIOR_YEAR_MEDICAL_RECOVERY` |
| 一般銷售稅尚未完成計算 | `SALES_TAX_AMOUNT_NOT_RESOLVED` |
| 稅款 refund／rebate adjustment | `UNSUPPORTED_TAX_REFUND_ADJUSTMENT` |
| 2025 高所得或 foreign-income SALT worksheet | `UNSUPPORTED_2025_SALT_WORKSHEET` |
| Schedule A Line 6 other taxes | `UNSUPPORTED_OTHER_TAX_LINE_6` |
| 多筆房貸或多個抵押房產 | `UNSUPPORTED_MULTIPLE_MORTGAGES` |
| 貸款 proceeds 非全部用於 buy/build/improve | `UNSUPPORTED_MORTGAGE_PROCEEDS_ALLOCATION` |
| 房貸本金限額或 FMV 限額 | `UNSUPPORTED_MORTGAGE_LIMITATION` |
| Shared mortgage interest | `UNSUPPORTED_SHARED_MORTGAGE` |
| 未在 Form 1098 報告的房貸利息 | `UNSUPPORTED_NON_1098_MORTGAGE_INTEREST` |
| 未在 Form 1098 報告的 points | `UNSUPPORTED_NON_1098_POINTS` |
| Seller-financed mortgage | `UNSUPPORTED_SELLER_FINANCED_MORTGAGE` |
| Form 8396 mortgage interest credit | `UNSUPPORTED_FORM_8396` |
| Investment interest／Form 4952 | `UNSUPPORTED_INVESTMENT_INTEREST` |
| 非現金慈善捐贈／Form 8283 | `UNSUPPORTED_NONCASH_CHARITY` |
| 慈善捐贈 carryover | `UNSUPPORTED_CHARITY_CARRYOVER` |
| 完整 charitable AGI limitation | `UNSUPPORTED_CHARITABLE_AGI_LIMITATION` |
| Casualty／theft loss／Form 4684 | `UNSUPPORTED_FORM_4684` |
| Net qualified disaster loss | `UNSUPPORTED_NET_QUALIFIED_DISASTER_LOSS` |
| Schedule A Line 16 特殊扣除 | `UNSUPPORTED_LINE_16_ITEM` |
| MFS 共同支付費用尚未分攤 | `UNSUPPORTED_MFS_JOINT_EXPENSE_ALLOCATION` |
| 輸入金額為負數 | `NEGATIVE_AMOUNT` |
| 調整金額超過原始支付金額 | `ADJUSTMENT_EXCEEDS_GROSS_AMOUNT` |
| 無法確定項目資格或稅務性質 | `UNKNOWN_TAX_CHARACTER` |

> **安全原則**：偵測到特殊項目不代表 Schedule A 不需要申報，而是代表 V1 無法安全完成。`should_attach_schedule_a` 與 `is_v1_supported` 必須分開判定。

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

所有金額必須滿足：

```text
amount >= 0
```

內部計算保留 cents；輸出至紙本 PDF 或電子申報資料時，再依整份 Form 1040 的統一 rounding policy 處理。

### 4.2 未知值

`null` 表示未知或尚未確認，不等同於 `0` 或 `False`。

例如：

```text
paid_in_tax_year = null
```

表示付款年度未知，不可自動當作未支付，也不可自動當作已支付。

### 4.3 日期與年度

來源文件可保留完整日期，但 V1 Processor 最少需要一個已正規化狀態：

```text
paid_in_tax_year: bool | null
```

上游若無法確認，必須傳入 `null`，由 V1 產生阻斷錯誤。

---

## 5. Layer 1 — 原始輸入模型

```text
ScheduleAInputsV1 = {
  taxpayer_name: str
  taxpayer_ssn: str
  tax_year: int                    # 2024 | 2025
  filing_status:
    SINGLE | MFJ | MFS | HOH | QSS

  adjusted_gross_income: Decimal

  medical_items: MedicalExpenseItemV1[]
  tax_items: TaxPaymentItemV1[]
  line_5a_election:
    INCOME_TAX | GENERAL_SALES_TAX | null

  mortgage_interest_items: MortgageInterestItemV1[]
  cash_charity_items: CashCharityItemV1[]

  standard_deduction_reference: StandardDeductionReferenceV1
  special_case_flags: SpecialCaseFlagsV1
}
```

### 5.1 MedicalExpenseItemV1

```text
MedicalExpenseItemV1 = {
  item_id: str
  source_document_id: str | null
  description: str | null

  paid_in_tax_year: bool | null

  taxpayer_paid_amount: Decimal
  reimbursement_amount: Decimal
  tax_free_medical_account_payment: Decimal

  eligible_person_status:
    ELIGIBLE | NOT_ELIGIBLE | UNKNOWN

  medical_qualification_status:
    QUALIFIED_SIMPLE | NOT_DEDUCTIBLE | UNKNOWN
}
```

規則：

- `QUALIFIED_SIMPLE` 且 `eligible_person_status == ELIGIBLE`：可進入 Line 1 計算池。
- `NOT_DEDUCTIBLE` 或 `NOT_ELIGIBLE`：排除，保留 warning。
- 任一資格為 `UNKNOWN`：阻止自動申報。
- `reimbursement_amount` 包含保險或其他第三方針對該筆費用的補償。
- `tax_free_medical_account_payment` 包含 HSA、MSA、FSA、HRA 或其他免稅醫療帳戶支付額。

### 5.2 TaxPaymentItemV1

```text
TaxPaymentItemV1 = {
  item_id: str
  source_document_id: str | null
  description: str | null

  paid_in_tax_year: bool | null
  amount_paid: Decimal
  separately_stated_nondeductible_charge: Decimal

  tax_category:
    STATE_LOCAL_INCOME_TAX
    | GENERAL_SALES_TAX
    | PERSONAL_REAL_ESTATE_TAX
    | PERSONAL_PROPERTY_TAX
    | FEDERAL_OR_NONDEDUCTIBLE_TAX
    | BUSINESS_OR_RENTAL_TAX
    | UNKNOWN

  personal_use_confirmed: bool | null
  actual_paid_to_taxing_authority_confirmed: bool | null
  value_based_and_annual_confirmed: bool | null
}
```

規則：

- `STATE_LOCAL_INCOME_TAX`：可進 Line 5a income-tax pool。
- `GENERAL_SALES_TAX`：可進 Line 5a sales-tax pool，但其金額必須已由外部完成。
- `PERSONAL_REAL_ESTATE_TAX`：
  - `personal_use_confirmed == true`
  - `actual_paid_to_taxing_authority_confirmed == true`
  - 才可進 Line 5b。
- `PERSONAL_PROPERTY_TAX`：
  - `personal_use_confirmed == true`
  - `value_based_and_annual_confirmed == true`
  - 才可進 Line 5c。
- `FEDERAL_OR_NONDEDUCTIBLE_TAX`：排除並產生 warning。
- `BUSINESS_OR_RENTAL_TAX`：排除並產生 routing warning，不得進入 Schedule A。
- `UNKNOWN`：阻止自動申報。

`separately_stated_nondeductible_charge` 可用於排除明確列示的服務費或財產改善 assessment。

### 5.3 MortgageInterestItemV1

```text
MortgageInterestItemV1 = {
  item_id: str
  source_document_id: str | null
  lender_name: str | null

  source_document_type: FORM_1098
  form_1098_box_1_mortgage_interest: Decimal
  deductible_points_reported_on_1098: Decimal

  paid_in_tax_year: bool | null

  simple_mortgage_status:
    CONFIRMED_SIMPLE
    | UNKNOWN
}
```

`deductible_points_reported_on_1098` 不是盲目複製 Box 6，而是上游已確認本年度可扣的 points 金額。

規則：

- 若有多個 `MortgageInterestItemV1`，會將其利息加總，但會拋出 `UNSUPPORTED_MULTIPLE_MORTGAGES` 阻斷自動申報。
- `CONFIRMED_SIMPLE` 才可計入 Line 8a。
- `UNKNOWN` 必須阻止自動申報，且該項目不計入金額。
- 若沒有 Form 1098，V1 不自動填 Line 8b 或 8c。

### 5.4 CashCharityItemV1

```text
CashCharityItemV1 = {
  item_id: str
  source_document_id: str | null

  contribution_date: str | null
  paid_in_tax_year: bool | null

  organization_name: str | null
  qualified_organization_status:
    VERIFIED | NOT_QUALIFIED | UNKNOWN

  contribution_method:
    CASH | CHECK | CREDIT_CARD | DEBIT_CARD | PAYROLL_DEDUCTION

  gross_contribution_amount: Decimal
  goods_or_services_value: Decimal

  bank_or_written_record_available: bool | null
  contemporaneous_acknowledgment_received: bool | null
}
```

規則：

- 每筆 item 必須代表一筆獨立付款，不得把多筆付款先聚合後再測試 `$250` 門檻。
- `VERIFIED` 才可納入 Line 11。
- `NOT_QUALIFIED` 排除並產生 warning。
- `UNKNOWN` 阻止自動申報。
- 所有 cash-type contribution 都必須有 bank record 或 charity written record。
- 單筆淨捐贈 `>= $250` 時，`contemporaneous_acknowledgment_received` 必須為 `true`。

### 5.5 StandardDeductionReferenceV1

```text
StandardDeductionReferenceV1 = {
  standard_deduction_amount: Decimal | null

  must_itemize_due_to_mfs_spouse: bool | null
  elect_itemize_even_if_less: bool | null
}
```

此物件由 Form 1040／taxpayer profile／deduction selector 提供。如果提取出的標準扣除額為無效值（例如 0.0 或更低），系統會自動回退（Fallback）至從 `schedule_a_tax_rates.json` 讀取的基礎標準扣除額。

此外，Schedule A V1 支持以下加成計算：
- **年齡與失明額外加成**：系統會自動根據 taxpayer 與 spouse 的出生年月日（判定稅務年度是否滿 65 歲，即該年底前滿 65 歲，實務上判定為生日在 `tax_year - 64` 年 1 月 1 日或之前）以及 legally blind 失明狀態標記，讀取並累加額外標準扣除額（2024 年 MFJ 每項加 $1,550，Single/HOH 每項加 $1,950；2025 年 MFJ 每項加 $1,600，Single/HOH 每項加 $2,000）。

Schedule A V1 不自行計算：
- 被扶養人的特殊標準扣除額。
- MFS 配偶選擇 itemize 的完整判斷。
- qualified disaster increased standard deduction。

若要產生最終 `should_attach_schedule_a`，`standard_deduction_amount` 不得為 `null`。

### 5.6 SpecialCaseFlagsV1

```text
SpecialCaseFlagsV1 = {
  has_marketplace_medical_premium: bool
  has_ltc_premium: bool
  has_self_employed_health_insurance_overlap: bool
  has_prior_year_medical_recovery: bool

  sales_tax_amount_requires_calculation: bool
  has_tax_refund_or_rebate_adjustment: bool
  has_form_2555_or_4563_or_puerto_rico_exclusion: bool
  has_other_tax_line_6: bool

  has_multiple_mortgages: bool
  mortgage_proceeds_not_all_qualified: bool
  mortgage_limitation_required: bool
  has_shared_mortgage: bool
  has_non_1098_mortgage_interest: bool
  has_non_1098_points: bool
  has_seller_financed_mortgage: bool
  has_form_8396_credit: bool
  has_investment_interest: bool

  has_noncash_charity: bool
  has_charity_carryover: bool
  has_charitable_agi_limitation: bool

  has_casualty_or_theft_loss: bool
  has_net_qualified_disaster_loss: bool
  has_line_16_item: bool

  has_unresolved_mfs_joint_expense_allocation: bool
}
```

任一不支援旗標為 `true` 時，V1 不得產生可送出的 Schedule A。

---

## 6. Layer 2 — 正規化與中間計算

### 6.1 醫療費用項目

對每筆可支援的醫療費用：

```text
gross_paid = taxpayer_paid_amount

adjustments =
    reimbursement_amount
    + tax_free_medical_account_payment
```

驗證：

```text
gross_paid >= 0
adjustments >= 0
adjustments <= gross_paid
```

若調整額超過自付額：

```text
blocking_error_code = ADJUSTMENT_EXCEEDS_GROSS_AMOUNT
```

若符合所有資格：

```text
eligible_medical_amount =
    gross_paid
    - reimbursement_amount
    - tax_free_medical_account_payment
```

```text
medical_expense_total =
  SUM(eligible_medical_amount)
```

不得使用 `max(0, ...)` 隱藏輸入矛盾。

### 6.2 Lines 1–4 中間值

```text
line_1_medical_and_dental_expenses =
  medical_expense_total
```

```text
line_2_agi =
  adjusted_gross_income
```

2024：

```text
Line 2 reference = Form 1040 or 1040-SR Line 11
```

2025：

```text
Line 2 reference = Form 1040 or 1040-SR Line 11b
```

```text
line_3_medical_threshold =
  line_2_agi * Decimal("0.075")
```

```text
line_4_deductible_medical_expenses =
  max(
    Decimal("0.00"),
    line_1_medical_and_dental_expenses
    - line_3_medical_threshold
  )
```

Line 4 使用 `max(0, ...)` 是表單明確要求，不屬於掩蓋輸入錯誤。

### 6.3 稅款項目

對每筆已確認可扣的稅款：

```text
eligible_tax_amount =
    amount_paid
    - separately_stated_nondeductible_charge
```

驗證：

```text
0 <= separately_stated_nondeductible_charge <= amount_paid
```

依 `tax_category` 分配至：

```text
income_tax_pool
sales_tax_pool
real_estate_tax_pool
personal_property_tax_pool
```

### 6.4 Line 5a election

若：

```text
line_5a_election == INCOME_TAX
```

則：

```text
line_5a_amount = SUM(income_tax_pool)
line_5a_sales_tax_checkbox = false
```

若：

```text
line_5a_election == GENERAL_SALES_TAX
```

則：

```text
line_5a_amount = SUM(sales_tax_pool)
line_5a_sales_tax_checkbox = true
```

若 election 為 `null`：

```text
blocking_error_code = TAX_ELECTION_MISSING
```

V1 不得自行選擇兩者中較高者。

### 6.5 Lines 5b–5d

```text
line_5b_real_estate_taxes =
  SUM(real_estate_tax_pool)
```

```text
line_5c_personal_property_taxes =
  SUM(personal_property_tax_pool)
```

```text
line_5d_salt_before_limit =
    line_5a_amount
    + line_5b_real_estate_taxes
    + line_5c_personal_property_taxes
```

### 6.6 2024 Line 5e

```text
salt_cap_2024 =
  Decimal("5000.00")
  if filing_status == MFS
  else Decimal("10000.00")
```

```text
line_5e_salt_deduction =
  min(line_5d_salt_before_limit, salt_cap_2024)
```

### 6.7 2025 Line 5e — V1 一般案件

先定義：

```text
floor_2025 =
  Decimal("5000.00")
  if filing_status == MFS
  else Decimal("10000.00")
```

```text
base_cap_2025 =
  Decimal("20000.00")
  if filing_status == MFS
  else Decimal("40000.00")
```

若：

```text
line_5d_salt_before_limit <= floor_2025
```

則不需 worksheet：

```text
line_5e_salt_deduction = line_5d_salt_before_limit
```

若 Line 5d 超過 floor，且：

```text
adjusted_gross_income <= 250000  # MFS
或
adjusted_gross_income <= 500000  # 非 MFS
```

並且沒有 Form 2555、Form 4563 或 Puerto Rico excluded income：

```text
line_5e_salt_deduction =
  min(line_5d_salt_before_limit, base_cap_2025)
```

否則：

```text
blocking_error_code = UNSUPPORTED_2025_SALT_WORKSHEET
line_5e_salt_deduction = null
```

V1 不實作 2025 SALT cap 的 30% phaseout worksheet。

### 6.8 Lines 6–7

V1 不支援 Line 6 other taxes。

確認沒有 Line 6 特殊項目後：

```text
line_6_other_taxes = Decimal("0.00")
```

```text
line_7_total_taxes =
    line_5e_salt_deduction
    + line_6_other_taxes
```

### 6.9 房貸利息

V1 最多接受一筆 simple Form 1098。

```text
line_8a_home_mortgage_interest =
    form_1098_box_1_mortgage_interest
    + deductible_points_reported_on_1098
```

確認沒有 Line 8b、8c 或 investment interest 特殊案件後：

```text
line_8b_non_1098_interest = Decimal("0.00")
line_8c_non_1098_points = Decimal("0.00")
line_9_investment_interest = Decimal("0.00")
```

```text
line_8e_total_mortgage_interest =
    line_8a_home_mortgage_interest
    + line_8b_non_1098_interest
    + line_8c_non_1098_points
```

```text
line_10_total_interest_paid =
    line_8e_total_mortgage_interest
    + line_9_investment_interest
```

### 6.10 現金慈善捐贈

每筆 contribution：

```text
net_contribution =
    gross_contribution_amount
    - goods_or_services_value
```

驗證：

```text
0 <= goods_or_services_value <= gross_contribution_amount
```

所有可納入項目必須：

```text
paid_in_tax_year == true
qualified_organization_status == VERIFIED
bank_or_written_record_available == true
```

若：

```text
net_contribution >= Decimal("250.00")
```

則：

```text
contemporaneous_acknowledgment_received == true
```

否則產生：

```text
blocking_error_code = MISSING_250_ACKNOWLEDGMENT
```

```text
line_11_cash_contributions =
  SUM(net_contribution for eligible items)
```

確認沒有非現金捐贈或 carryover 後：

```text
line_12_noncash_contributions = Decimal("0.00")
line_13_charity_carryover = Decimal("0.00")
```

```text
line_14_total_charity =
    line_11_cash_contributions
    + line_12_noncash_contributions
    + line_13_charity_carryover
```

### 6.11 Lines 15–16

確認沒有 Form 4684、net qualified disaster loss 或其他 Line 16 item 後：

```text
line_15_casualty_theft_loss = Decimal("0.00")
line_16_other_itemized_deductions = Decimal("0.00")
```

### 6.12 Line 17

```text
line_17_total_itemized_deductions =
    line_4_deductible_medical_expenses
    + line_7_total_taxes
    + line_10_total_interest_paid
    + line_14_total_charity
    + line_15_casualty_theft_loss
    + line_16_other_itemized_deductions
```

---

## 7. Layer 3 — Schedule A 表面欄位

| 欄位 | V1 輸出 | 規則 |
|---|---|---|
| Header Name | `taxpayer_name` | 與 Form 1040 一致 |
| Header SSN | `taxpayer_ssn` | 與 Form 1040 一致 |
| Line 1 | `line_1_medical_and_dental_expenses` | 合格醫療費淨額 |
| Line 2 | `line_2_agi` | 2024 引用 1040 Line 11；2025 引用 Line 11b |
| Line 3 | `line_3_medical_threshold` | Line 2 × 7.5% |
| Line 4 | `line_4_deductible_medical_expenses` | max(0, Line 1 − Line 3) |
| Line 5a | `line_5a_amount` | 所得稅或一般銷售稅擇一 |
| Line 5a checkbox | `line_5a_sales_tax_checkbox` | 選 general sales tax 時為 true |
| Line 5b | `line_5b_real_estate_taxes` | 個人不動產稅 |
| Line 5c | `line_5c_personal_property_taxes` | 合格個人動產稅 |
| Line 5d | `line_5d_salt_before_limit` | Lines 5a–5c 合計 |
| Line 5e | `line_5e_salt_deduction` | 套用年度 SALT limit |
| Line 6 | `line_6_other_taxes` | V1 固定 0，偵測到資料即阻斷 |
| Line 7 | `line_7_total_taxes` | Line 5e + Line 6 |
| Line 8 checkbox | `false` | V1 不支援非全部 qualifying proceeds |
| Line 8a | `line_8a_home_mortgage_interest` | simple Form 1098 passthrough |
| Line 8b | `line_8b_non_1098_interest` | V1 固定 0 |
| Line 8c | `line_8c_non_1098_points` | V1 固定 0 |
| Line 8d | `null` | Reserved for future use |
| Line 8e | `line_8e_total_mortgage_interest` | Lines 8a–8c 合計 |
| Line 9 | `line_9_investment_interest` | V1 固定 0 |
| Line 10 | `line_10_total_interest_paid` | Line 8e + Line 9 |
| Line 11 | `line_11_cash_contributions` | 合格 cash-type charity |
| Line 12 | `line_12_noncash_contributions` | V1 固定 0 |
| Line 13 | `line_13_charity_carryover` | V1 固定 0 |
| Line 14 | `line_14_total_charity` | Lines 11–13 合計 |
| Line 15 | `line_15_casualty_theft_loss` | V1 固定 0 |
| Line 16 | `line_16_other_itemized_deductions` | V1 固定 0 |
| Line 17 | `line_17_total_itemized_deductions` | Lines 4、7、10、14、15、16 合計 |
| Line 18 | `line_18_elect_itemize_surface` | 只存在於 2025 renderer |

---

## 8. Schedule A 使用與檢附判定

### 8.1 V1 是否支援

```text
has_unsupported_case =
  any(unsupported SpecialCaseFlagsV1 == true)
```

```text
is_v1_supported =
  NOT has_unsupported_case
```

### 8.2 是否選擇逐項扣除

`standard_deduction_amount` 由外部模組提供。

```text
is_itemizing =
    must_itemize_due_to_mfs_spouse is True
    OR elect_itemize_even_if_less is True
    OR line_17_total_itemized_deductions
       > standard_deduction_amount
```

若 Line 17 正好等於標準扣除額，V1 預設使用標準扣除額；除非有強制或明確 election。

### 8.3 是否可送出

```text
can_file =
    is_v1_supported
    AND blocking_errors is empty
```

```text
should_attach_schedule_a =
    is_itemizing
    AND can_file
```

### 8.4 2025 Line 18

2025：

```text
line_18_elect_itemize_surface =
  true
  if elect_itemize_even_if_less is True
  else false
```

2024 Schedule A 沒有 Line 18：

```text
line_18_elect_itemize_surface = null
```

Election 仍保留在內部 Deduction Selector，不因表面沒有欄位而遺失。

---

## 9. 跨表連動

### 9.1 Form 1040 AGI

```text
2024 Schedule A Line 2
  <- Form 1040 or 1040-SR Line 11
```

```text
2025 Schedule A Line 2
  <- Form 1040 or 1040-SR Line 11b
```

### 9.2 Itemized deduction

```text
2024 Form 1040 or 1040-SR Line 12
  <- Schedule A Line 17
  if is_itemizing
```

```text
2025 Form 1040 or 1040-SR Line 12e
  <- Schedule A Line 17
  if is_itemizing
```

### 9.3 不屬於 Schedule A 的項目

V1 必須產生 routing warning，避免錯填：

- Business or rental taxes → Schedule C、E、F 或其他 business module。
- Form 1098 Box 4 refund of overpaid interest → Schedule 1 對應規則。
- Mortgage escrow 顯示的 property tax → 必須確認 taxing authority 實際支付額後再進 Line 5b。
- Political contribution → 不得進 Line 11。
- Federal income tax、Social Security tax、Medicare tax → 不得進 Lines 5a–6。
- Student loan interest → Schedule 1，而非 Schedule A mortgage interest。

---

## 10. 驗證與表面留白原則

### 10.1 未知資料

下列欄位若應作答卻為 `null`，必須阻斷：

- `paid_in_tax_year`
- medical eligibility statuses
- `line_5a_election`
- real estate tax qualification confirmations
- personal property tax qualification confirmations
- mortgage simple status
- qualified organization status
- charity record availability
- `$250` acknowledgement when applicable
- `standard_deduction_amount` when final attachment decision is requested

### 10.2 不適用與未知必須分開

例如沒有房貸：

```text
mortgage_interest_items = []
line_8a = 0.00
```

這是「不適用」。

若有 Form 1098，但無法確認是否受 Pub. 936 限制：

```text
simple_mortgage_status = UNKNOWN
```

這是「未知」，必須阻斷，不可把 Line 8a 設為零後繼續。

### 10.3 表面欄位與內部狀態

若 `can_file == false`，計算引擎可保留已完成的中間結果供 debug，但 renderer 不得產生看似可送出的完整 Schedule A。

---

## 11. 輸出模型

```text
ScheduleAResultV1 = {
  taxpayer_name: str
  taxpayer_ssn_masked: str
  tax_year: int
  filing_status: str

  line_1_medical_and_dental_expenses: Decimal
  line_2_agi: Decimal
  line_3_medical_threshold: Decimal
  line_4_deductible_medical_expenses: Decimal

  line_5a_amount: Decimal
  line_5a_sales_tax_checkbox: bool
  line_5b_real_estate_taxes: Decimal
  line_5c_personal_property_taxes: Decimal
  line_5d_salt_before_limit: Decimal
  line_5e_salt_deduction: Decimal | null
  line_6_other_taxes: Decimal
  line_7_total_taxes: Decimal | null

  line_8_qualifying_proceeds_checkbox: bool
  line_8a_home_mortgage_interest: Decimal
  line_8b_non_1098_interest: Decimal
  line_8c_non_1098_points: Decimal
  line_8d_reserved: null
  line_8e_total_mortgage_interest: Decimal
  line_9_investment_interest: Decimal
  line_10_total_interest_paid: Decimal

  line_11_cash_contributions: Decimal
  line_12_noncash_contributions: Decimal
  line_13_charity_carryover: Decimal
  line_14_total_charity: Decimal

  line_15_casualty_theft_loss: Decimal
  line_16_other_itemized_deductions: Decimal
  line_17_total_itemized_deductions: Decimal | null
  line_18_elect_itemize_surface: bool | null

  standard_deduction_amount: Decimal | null
  is_itemizing: bool | null
  is_v1_supported: bool
  should_attach_schedule_a: bool
  can_file: bool

  blocking_errors: ValidationIssue[]
  review_warnings: ValidationIssue[]
}
```

```text
ValidationIssue = {
  code: str
  field: str | null
  item_id: str | null
  source_document_id: str | null
  message: str
}
```

`taxpayer_ssn` 不應出現在一般 log、debug output 或測試 snapshot 中。

輸出可使用遮罩格式：

```text
***-**-6789
```

---

## 12. 核心計算偽代碼

```python
from decimal import Decimal

ZERO = Decimal("0.00")
MEDICAL_RATE = Decimal("0.075")


def calculate_schedule_a_v1(inputs):
    errors = []
    warnings = []

    validate_identity(inputs, errors)
    validate_tax_year(inputs.tax_year, allowed={2024, 2025}, errors=errors)
    validate_nonnegative_amounts(inputs, errors)
    detect_unsupported_cases(inputs.special_case_flags, errors)

    medical_total = ZERO

    for item in inputs.medical_items:
        validate_paid_year(item, errors)

        if item.medical_qualification_status == "UNKNOWN":
            errors.append(issue(
                "UNKNOWN_MEDICAL_QUALIFICATION",
                item_id=item.item_id,
            ))
            continue

        if item.eligible_person_status == "UNKNOWN":
            errors.append(issue(
                "UNKNOWN_MEDICAL_PERSON_ELIGIBILITY",
                item_id=item.item_id,
            ))
            continue

        if (
            item.medical_qualification_status == "NOT_DEDUCTIBLE"
            or item.eligible_person_status == "NOT_ELIGIBLE"
            or item.paid_in_tax_year is False
        ):
            warnings.append(issue(
                "MEDICAL_ITEM_EXCLUDED",
                item_id=item.item_id,
            ))
            continue

        adjustments = (
            item.reimbursement_amount
            + item.tax_free_medical_account_payment
        )

        if adjustments > item.taxpayer_paid_amount:
            errors.append(issue(
                "ADJUSTMENT_EXCEEDS_GROSS_AMOUNT",
                item_id=item.item_id,
            ))
            continue

        medical_total += item.taxpayer_paid_amount - adjustments

    line_1 = medical_total
    line_2 = inputs.adjusted_gross_income
    line_3 = line_2 * MEDICAL_RATE
    line_4 = max(ZERO, line_1 - line_3)

    tax_pools = classify_tax_items(
        inputs.tax_items,
        errors=errors,
        warnings=warnings,
    )

    if inputs.line_5a_election == "INCOME_TAX":
        line_5a = sum_decimal(tax_pools.income_tax)
        sales_tax_checkbox = False
    elif inputs.line_5a_election == "GENERAL_SALES_TAX":
        line_5a = sum_decimal(tax_pools.sales_tax)
        sales_tax_checkbox = True
    else:
        line_5a = ZERO
        sales_tax_checkbox = False
        errors.append(issue("TAX_ELECTION_MISSING", "line_5a_election"))

    line_5b = sum_decimal(tax_pools.real_estate_tax)
    line_5c = sum_decimal(tax_pools.personal_property_tax)
    line_5d = line_5a + line_5b + line_5c

    line_5e = calculate_salt_limit_v1(
        tax_year=inputs.tax_year,
        filing_status=inputs.filing_status,
        agi=inputs.adjusted_gross_income,
        line_5d=line_5d,
        has_foreign_adjustment=(
            inputs.special_case_flags
            .has_form_2555_or_4563_or_puerto_rico_exclusion
        ),
        errors=errors,
    )

    line_6 = ZERO
    line_7 = None if line_5e is None else line_5e + line_6

    line_8a = calculate_simple_form_1098(
        inputs.mortgage_interest_items,
        errors=errors,
    )

    line_8b = ZERO
    line_8c = ZERO
    line_8e = line_8a + line_8b + line_8c
    line_9 = ZERO
    line_10 = line_8e + line_9

    line_11 = calculate_cash_charity(
        inputs.cash_charity_items,
        errors=errors,
        warnings=warnings,
    )

    line_12 = ZERO
    line_13 = ZERO
    line_14 = line_11 + line_12 + line_13

    line_15 = ZERO
    line_16 = ZERO

    if line_7 is None:
        line_17 = None
    else:
        line_17 = (
            line_4
            + line_7
            + line_10
            + line_14
            + line_15
            + line_16
        )

    is_v1_supported = not any_unsupported_case(
        inputs.special_case_flags
    )

    can_file = (
        is_v1_supported
        and len(errors) == 0
        and line_17 is not None
    )

    standard_amount = (
        inputs.standard_deduction_reference
        .standard_deduction_amount
    )

    if standard_amount is None or line_17 is None:
        is_itemizing = None
        if standard_amount is None:
            errors.append(issue(
                "STANDARD_DEDUCTION_REFERENCE_MISSING",
                "standard_deduction_amount",
            ))
    else:
        is_itemizing = (
            inputs.standard_deduction_reference
                .must_itemize_due_to_mfs_spouse is True
            or inputs.standard_deduction_reference
                .elect_itemize_even_if_less is True
            or line_17 > standard_amount
        )

    should_attach = (
        can_file
        and is_itemizing is True
    )

    line_18_surface = (
        inputs.standard_deduction_reference
            .elect_itemize_even_if_less is True
        if inputs.tax_year == 2025
        else None
    )

    return ScheduleAResultV1(
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
        is_itemizing=is_itemizing,
        is_v1_supported=is_v1_supported,
        should_attach_schedule_a=should_attach,
        can_file=can_file,
        blocking_errors=errors,
        review_warnings=warnings,
    )
```

---

## 13. 最低必要測試案例

### Test 1 — 一般 2025 MFJ，標準扣除額較高

```text
AGI = 145,000
Line 1 medical = 8,000
State income tax = 5,400
Real estate tax = 2,600
Form 1098 interest = 9,800
Cash charity = 5,400
Standard deduction reference = 31,500
```

預期：

```text
Line 3 = 10,875
Line 4 = 0
Line 5d = 8,000
Line 5e = 8,000
Line 7 = 8,000
Line 10 = 9,800
Line 14 = 5,400
Line 17 = 23,200
is_itemizing = false
should_attach_schedule_a = false
```

### Test 2 — Line 17 高於標準扣除額

```text
Line 17 = 35,000
standard_deduction_amount = 31,500
```

預期：

```text
is_itemizing = true
should_attach_schedule_a = true
```

### Test 3 — 醫療費剛好等於 7.5% AGI

```text
AGI = 100,000
Line 1 = 7,500
```

預期：

```text
Line 3 = 7,500
Line 4 = 0
```

### Test 4 — 醫療調整額超過自付額

```text
taxpayer_paid_amount = 1,000
reimbursement_amount = 800
tax_free_medical_account_payment = 300
```

預期：

```text
blocking error = ADJUSTMENT_EXCEEDS_GROSS_AMOUNT
can_file = false
```

不得以 `max(0, 1000 - 800 - 300)` 靜默變成零。

### Test 5 — Line 5a 選擇所得稅

```text
income tax pool = 6,000
sales tax pool = 7,000
line_5a_election = INCOME_TAX
```

預期：

```text
Line 5a = 6,000
sales-tax checkbox = false
```

V1 不自行改選較高的 sales tax。

### Test 6 — Line 5a election 缺失

```text
line_5a_election = null
```

預期：

```text
blocking error = TAX_ELECTION_MISSING
can_file = false
```

### Test 7 — 2024 SALT cap

```text
tax_year = 2024
filing_status = MFJ
Line 5d = 14,000
```

預期：

```text
Line 5e = 10,000
```

### Test 8 — 2025 一般 SALT cap

```text
tax_year = 2025
filing_status = MFJ
AGI = 300,000
Line 5d = 45,000
```

預期：

```text
Line 5e = 40,000
```

### Test 9 — 2025 高所得 SALT worksheet

```text
tax_year = 2025
filing_status = MFJ
AGI = 550,000
Line 5d = 30,000
```

預期：

```text
blocking error = UNSUPPORTED_2025_SALT_WORKSHEET
Line 5e = null
Line 17 = null
can_file = false
```

### Test 10 — 2025 高所得但 Line 5d 未超過 floor

```text
tax_year = 2025
filing_status = MFJ
AGI = 550,000
Line 5d = 9,000
```

預期：

```text
Line 5e = 9,000
不需 SALT worksheet
```

### Test 11 — Simple Form 1098

```text
Box 1 mortgage interest = 9,800
deductible points reported on 1098 = 500
simple_mortgage_status = CONFIRMED_SIMPLE
```

預期：

```text
Line 8a = 10,300
Line 8e = 10,300
Line 10 = 10,300
```

### Test 12 — 複雜房貸

```text
mortgage_limitation_required = true
```

預期：

```text
is_v1_supported = false
blocking error = UNSUPPORTED_MORTGAGE_LIMITATION
can_file = false
```

### Test 13 — 現金捐贈收到 benefit

```text
gross contribution = 300
goods or services value = 80
record available = true
acknowledgment received = false
```

預期：

```text
net contribution = 220
不因 gross amount 300 自動要求 $250 acknowledgment
Line 11 includes 220
```

### Test 14 — 單筆淨捐贈達 $250，缺 acknowledgment

```text
gross contribution = 300
goods or services value = 0
record available = true
acknowledgment received = false
```

預期：

```text
blocking error = MISSING_250_ACKNOWLEDGMENT
can_file = false
```

### Test 15 — 多筆小額捐贈不可合併測試門檻

```text
52 items × 25 each
```

預期：

```text
每筆均低於 $250
不因全年合計 $1,300 而要求單筆 $250 acknowledgment
```

每筆仍必須有適用的銀行或書面紀錄。

### Test 16 — 非現金捐贈

```text
has_noncash_charity = true
```

預期：

```text
is_v1_supported = false
blocking error = UNSUPPORTED_NONCASH_CHARITY
Line 12 不得使用 0 繼續送出
```

### Test 17 — Line 17 等於標準扣除額

```text
Line 17 = 31,500
standard deduction = 31,500
elect_itemize_even_if_less = false
```

預期：

```text
is_itemizing = false
```

### Test 18 — 2025 主動選擇較低的 itemized deduction

```text
tax_year = 2025
Line 17 = 25,000
standard deduction = 31,500
elect_itemize_even_if_less = true
```

預期：

```text
is_itemizing = true
Line 18 surface = true
should_attach_schedule_a = true
```

---

## 14. V1 完成條件

V1 可視為完成，必須同時滿足：

- 一般合格醫療費可正確進入 Lines 1–4。
- Reimbursement 與 tax-free medical account payment 不會造成 double benefit。
- 未知醫療資格不會被當作可扣或不可扣。
- Line 5a 所得稅／一般銷售稅 election 正確。
- 2024 與 2025 SALT cap 邊界正確。
- 2025 高所得 SALT worksheet 案件能可靠阻斷。
- 個人房地產稅與動產稅不會混入商業或出租用途項目。
- 單一 simple Form 1098 可正確進入 Lines 8a、8e、10。
- 複雜房貸不會以 Box 1 金額直接送出。
- 現金類慈善捐贈可正確扣除 goods/services value。
- `$250` 文件規則按每筆 contribution 判定，而非全年合計。
- Noncash、carryover、Form 4684、Line 16 等特殊案件能可靠阻斷。
- Line 17 可正確連動 Form 1040。
- 標準扣除額由外部 reference 提供，不在 Schedule A Processor 內重算。
- 所有正式金額均使用 `Decimal` 或 integer cents。
- 所有 blocking error 均具有可測試的錯誤代碼。
- SSN 不會出現在一般 log 或測試 snapshot。

---

## 15. V2 以後再處理

下列功能不屬於 V1：

- 完整 Pub. 502 醫療資格引擎。
- Marketplace premium／Form 8962 整合。
- LTC premium 年齡限額。
- 自雇健康保險重複扣除協調。
- IRS Optional State Sales Tax Tables。
- 2025 SALT phaseout worksheet。
- Line 6 foreign income tax 與 GST tax。
- Pub. 936 mortgage limitation worksheet。
- Multiple mortgages、refinance、home equity 與 shared mortgage。
- Line 8b、8c 非 Form 1098 利息與 points。
- Form 8396。
- Form 4952 investment interest。
- Noncash contribution valuation。
- Form 8283、Form 1098-C、qualified appraisal。
- Charitable AGI limitation ordering。
- Charitable contribution carryover。
- Form 4684 casualty and theft losses。
- Net qualified disaster loss 與 increased standard deduction。
- Line 16 whitelist items。
- dependent 等特殊標準扣除額計算（年齡與失明已由 V1 支援）。

---

## 16. 官方參考資料

- 2025 Schedule A (Form 1040):  
  https://www.irs.gov/pub/irs-pdf/f1040sa.pdf

- 2025 Instructions for Schedule A (Form 1040):  
  https://www.irs.gov/pub/irs-pdf/i1040sca.pdf

- 2024 Schedule A (Form 1040):  
  https://www.irs.gov/pub/irs-prior/f1040sa--2024.pdf

- 2024 Instructions for Schedule A (Form 1040):  
  https://www.irs.gov/pub/irs-prior/i1040sca--2024.pdf

- IRS Credits and Deductions for Individuals:  
  https://www.irs.gov/credits-and-deductions-for-individuals

- IRS Topic No. 503, Deductible Taxes:  
  https://www.irs.gov/taxtopics/tc503

> 稅法、表單及電子申報規格可能更新。正式申報前，應依對應年度 IRS 最新表單、說明及適用的電子申報 schema 再次驗證。
