# IRS Schedule C (Form 1040) 填表與計算規則指南
## 2025／2024 年度標準版 — V1 一般 P&L 案件填表器

> **版本定位**
>
> 本文件定義 Schedule C V1 規則引擎的最小可行且可防守範圍。V1 不是完整 Schedule C tax engine
>
> V1 的目標是支援大多數「簡單 P&L 型」sole proprietor／single-member LLC／freelancer／小型服務業案件：能把營業收入放到 Schedule C，能把一般營業費用依 Schedule C 類別列出，並能計算 Line 31 net profit or loss。
>
> 遇到庫存、完整 COGS、車輛里程法、折舊、Section 179、家庭辦公室、複雜差旅分攤、員工薪資抵免、at-risk 限制、passive activity、QBI、Schedule SE 等超出 V1 的案件時，V1 必須產生明確 flag，不得用不完整公式硬算。

---

## 1. V1 設計目標

V1 必須做到：

1. 正確將一般 business gross receipts 映射至 Schedule C Line 1。
2. 正確將 returns and allowances 映射至 Schedule C Line 2。
3. 正確計算 Line 3 net receipts。
4. 在沒有 COGS 的簡單 P&L 案件中，正確將 Line 4 設為 0，並計算 Lines 5、6、7。
5. 正確將一般營業費用依 Schedule C 類別顯示於 Lines 8–27b。
6. 正確列出 Part V other expenses，並將 Line 48 合計帶入 Line 27b。
7. 正確計算 Line 28 total expenses。
8. 正確計算 Line 29 tentative profit or loss。
9. 在沒有家庭辦公室扣除的 V1 案件中，正確將 Line 30 設為 0。
10. 正確計算 Line 31 net profit or loss。
11. 若 Line 31 為 loss，要求 Line 32 at-risk 問卷答案；若涉及 Form 6198，V1 阻斷。
12. 對不支援的 Schedule C 複雜案件產生明確 blocking error。
13. 不以 `0`、`False` 或其他預設值掩蓋未知資料。
14. 明確區分：
    - `can_map = true`：可以產生 draft mapping。
    - `can_file = true`：V1 可以產生可送出的 Schedule C 結果。
15. 內部金額使用 `Decimal` 或 integer cents，不使用 binary `float` 作為正式計算型別。

V1 不以完整支援所有 Schedule C 稅務規則為目標。

---

## 2. V1 支援範圍

### 2.1 支援的納稅人與業務型態

V1 支援：

- Sole proprietor。
- 未選擇以 corporation 課稅的 single-member LLC。
- Freelancer、consultant、designer、developer、creator、teacher、small service business。
- Cash-basis 或 P&L 已經給出明確可用金額的簡單小型業務。
- 來源資料已經能辨識為 business income / business expense，而非 hobby、rental、investment、employee reimbursement 或 personal expense。

V1 不自行判斷複雜 entity classification。若來源資料顯示 partnership、S corporation、C corporation、multi-member LLC，V1 必須阻斷。

### 2.2 支援的收入

V1 支援下列收入輸入：

- Line 1 gross receipts or sales。
- Line 2 returns and allowances。
- Line 6 other business income。

V1 允許收入來源包含：

- 1099-NEC。
- 1099-K。
- 1099-MISC business income。
- 平台收入 summary。
- Bookkeeping P&L revenue。
- Invoice / receipt summary。
- Cash sales summary。

V1 不支援自行判斷下列特殊收入處理：

- Statutory employee W-2 income。
- Not-for-profit / hobby income。
- Rental real estate income 應走 Schedule E 的情況。
- Farm income 應走 Schedule F 的情況。
- Cancellation of debt、installment sale、business asset sale、like-kind exchange。
- Nontaxable Medicaid waiver payments 的特殊 offset。
- 需要 Form 4797、6252、8824、4684、8594 等表單的收入。

### 2.3 支援的一般費用分類

V1 支援「可直接從 P&L 或來源文件分類」的一般 Schedule C 費用：

| Schedule C 行號 | V1 欄位 | 說明 |
|---|---|---|
| Line 8 | `line_8_advertising` | Advertising |
| Line 9 | `line_9_car_truck_expenses_final` | 已由上游或人工確認的最終 car/truck expense；V1 不計算 mileage |
| Line 10 | `line_10_commissions_fees` | Commissions and fees |
| Line 11 | `line_11_contract_labor` | Contract labor |
| Line 12 | `line_12_depletion` | Depletion；通常 V1 為 0，若非 0 建議 review |
| Line 14 | `line_14_employee_benefit_programs` | Employee benefit programs；不含 owner benefit |
| Line 15 | `line_15_insurance` | Insurance other than health |
| Line 16a | `line_16a_mortgage_interest` | Business mortgage interest paid to banks |
| Line 16b | `line_16b_other_interest` | Other business interest |
| Line 17 | `line_17_legal_professional` | Legal and professional services |
| Line 18 | `line_18_office_expense` | Office expense |
| Line 19 | `line_19_pension_profit_sharing` | Employee pension/profit-sharing plans |
| Line 20a | `line_20a_rent_machinery_equipment` | Rent/lease vehicles, machinery, equipment |
| Line 20b | `line_20b_rent_other_property` | Rent/lease other business property |
| Line 21 | `line_21_repairs_maintenance` | Repairs and maintenance |
| Line 22 | `line_22_supplies` | Supplies not included in COGS |
| Line 23 | `line_23_taxes_licenses` | Business taxes and licenses |
| Line 24a | `line_24a_travel_final` | 已確認為 business travel 的最終金額；V1 不做 mixed-trip 分攤 |
| Line 24b | `line_24b_deductible_meals` | deductible meals amount；可由 V1 對一般商務餐飲做 50% 限制 |
| Line 25 | `line_25_utilities` | Utilities |
| Line 26 | `line_26_wages_final` | 已由 payroll module 或來源文件確認的 wages less employment credits |
| Line 27b | `line_27b_other_expenses` | Part V Line 48 total other expenses |

> **重要原則**
>
> V1 可以把 P&L 中明確分類的費用放到對應 Schedule C 類別。  
> V1 不負責把個人/商用混合費用自行按比例分攤。若資料需要比例分攤但沒有上游結果，必須 flag。

### 2.4 支援的 Part V Other Expenses

V1 支援把一般行政或業務雜費列入 Part V：

```text
OtherExpenseItemV1 = {
  item_id: str
  name: str
  amount: Decimal
  source_document_id: str | null
  confidence:
    HIGH
    | MEDIUM
    | LOW
}
```

典型可接受項目：

- Bank charges。
- Merchant processing fees / Stripe / PayPal fees。
- Software subscriptions。
- Cloud hosting。
- Security monitoring。
- Professional membership dues。
- Business conference fees。
- Business education / training。
- Postage and shipping，若政策選擇不放 Line 18。
- Cleaning services，若不歸入 repairs/maintenance。

不得放入 Part V：

- 個人生活支出。
- 罰金、罰款、政治捐款。
- 已經放入 Lines 8–26 的費用。
- Home office expenses。
- COGS / inventory costs。
- Depreciation / amortization / Section 179，除非由 Form 4562 模組輸出。
- 需要專門表單或限制計算的項目。

### 2.5 支援的簡單問卷欄位

V1 可直接接收使用者或上游問卷答案：

- Line G：是否 materially participated。
- Line H：是否今年 started or acquired business。
- Line I：是否有需要申報 Form 1099 的付款。
- Line J：若 Line I 為 Yes，是否已經或將會申報 Form 1099。
- Line 32：若 Line 31 為 loss，是否 all investment is at risk。

V1 不自行根據工時計算 material participation，也不自行判斷 1099 義務或 at-risk 金額。

---

## 3. V1 不支援的特殊案件

若偵測到下列任一情況，V1 必須設定：

```text
is_v1_supported = false
can_file = false
blocking_validation_error = true
```

但可視情況保留：

```text
can_map = true
```

讓 UI 顯示 draft mapping 與需要人工處理的原因。

| 特殊案件 | 建議錯誤代碼 | V1 行為 |
|---|---|---|
| 無法確認是否為 trade or business | `UNKNOWN_BUSINESS_ACTIVITY` | 阻斷 |
| 明顯是 hobby / not-for-profit | `NOT_TRADE_OR_BUSINESS` | 阻斷 |
| 應走 Schedule E 的 rental / royalty | `WRONG_FORM_RENTAL_OR_ROYALTY` | 阻斷 |
| 應走 Schedule F 的 farming | `WRONG_FORM_FARM_INCOME` | 阻斷 |
| Partnership / corporation / multi-member LLC | `UNSUPPORTED_ENTITY_TYPE` | 阻斷 |
| 有 inventory 或 COGS 需要 Part III 完整計算 | `UNSUPPORTED_COGS_IN_V1` | 阻斷，除非上游 COGS module 已完成 |
| 車輛費用需要 mileage/actual method 計算 | `UNSUPPORTED_VEHICLE_CALCULATION_IN_V1` | 阻斷，除非已有 final line 9 amount |
| 需要 Form 4562 折舊、amortization 或 Section 179 | `FORM_4562_REQUIRED` | 阻斷，除非上游 Form 4562 module 已完成 |
| Home office deduction | `FORM_8829_OR_SIMPLIFIED_HOME_OFFICE_REQUIRED` | 阻斷，除非上游 home office module 已完成 |
| 國內/國外 mixed travel 需天數比例分攤 | `UNSUPPORTED_TRAVEL_ALLOCATION_IN_V1` | 阻斷 |
| meals/entertainment 分類不清 | `UNCERTAIN_MEALS_ENTERTAINMENT_CLASSIFICATION` | 阻斷 |
| 員工薪資、payroll tax credit、owner draw 混在一起 | `PAYROLL_OR_OWNER_DRAW_REVIEW_REQUIRED` | 阻斷 |
| Owner salary/draw 被放入 business expense | `OWNER_DRAW_INCLUDED_IN_EXPENSES` | 阻斷 |
| Line 31 loss 且 at-risk answer 未知 | `AT_RISK_ANSWER_MISSING` | 阻斷 |
| Line 31 loss 且 some investment not at risk | `FORM_6198_REQUIRED` | 阻斷 |
| Line G 為 No 且有 loss，可能 passive loss limitation | `PASSIVE_ACTIVITY_REVIEW_REQUIRED` | 阻斷 |
| Energy efficient commercial buildings deduction | `FORM_7205_REQUIRED` | 阻斷 |
| Excess business loss limitation | `FORM_461_REVIEW_REQUIRED` | 阻斷 |
| QBI deduction | `QBI_NOT_COMPUTED_BY_SCHEDULE_C_V1` | 不阻斷 Schedule C，但不計算 QBI |
| Self-employment tax | `SCHEDULE_SE_NOT_COMPUTED_BY_SCHEDULE_C_V1` | 不阻斷 Schedule C，但不計算 SE tax |
| 費用類別不確定 | `UNCERTAIN_EXPENSE_CLASSIFICATION` | 阻斷或人工 review |
| 金額為負數 | `NEGATIVE_AMOUNT` | 阻斷 |
| 必要欄位缺失 | `REQUIRED_FIELD_MISSING` | 阻斷 |

> **安全原則**
>
> 不支援的案件不是忽略，也不是預設為 0。  
> V1 必須明確 flag，並在結果中顯示為 `can_file = false`。

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

所有輸入金額 must 滿足：

```text
amount >= 0
```

內部計算保留 cents；輸出至 PDF 或電子申報資料時，再依整份 Form 1040 的統一 rounding policy 處理。

### 4.2 未知值

`null` 表示未知或尚未回答，不等同於 `0` 或 `False`。

例如：

```text
line_g_material_participation = null
```

表示尚未取得 Line G 答案，不可自動當作 `Yes` 或 `No`。

### 4.3 P&L 原始金額與 deductible amount

V1 必須區分：

```text
source_amount
```

與：

```text
deductible_amount
```

例如一般 business meals 來源金額為 1,000，但 deductible meals 可能為 500。  
LLM parser 只應提取來源文件的原始金額與分類，不應自行做 50% 計算。50% 計算由 deterministic rule engine 執行。

---

## 5. Layer 1 — 原始輸入模型

```text
ScheduleCInputsV1 = {
  proprietor_name: str
  taxpayer_ssn: str
  tax_year: int                    # 2024 | 2025

  principal_business: str | null
  principal_activity_code: str | null
  business_name: str | null
  ein: str | null
  business_address: str | null

  accounting_method:
    CASH
    | ACCRUAL
    | OTHER
    | null

  line_g_material_participation: bool | null
  line_h_started_or_acquired: bool | null
  line_i_payment_requiring_1099: bool | null
  line_j_filed_required_1099: bool | null

  income: ScheduleCIncomeV1
  expenses: ScheduleCExpenseInputsV1
  other_expense_items: OtherExpenseItemV1[]

  loss_at_risk_answer:
    ALL_AT_RISK
    | SOME_NOT_AT_RISK
    | null

  special_case_flags: ScheduleCSpecialCaseFlagsV1
}
```

### 5.1 ScheduleCIncomeV1

```text
ScheduleCIncomeV1 = {
  line_1_gross_receipts: Decimal
  line_2_returns_allowances: Decimal
  line_6_other_income: Decimal
}
```

規則：

- `line_1_gross_receipts` 必須是 business gross receipts，不含代收銷售稅。
- `line_2_returns_allowances` 只包含退貨、折讓、退款。
- `line_6_other_income` 只包含與該 business 相關的 other income。
- 若來源收入性質不明，必須 flag `UNKNOWN_BUSINESS_INCOME_CHARACTER`。

### 5.2 ScheduleCExpenseInputsV1

```text
ScheduleCExpenseInputsV1 = {
  line_8_advertising: Decimal
  line_9_car_truck_expenses_final: Decimal | null
  line_10_commissions_fees: Decimal
  line_11_contract_labor: Decimal
  line_12_depletion: Decimal
  line_14_employee_benefit_programs: Decimal
  line_15_insurance: Decimal
  line_16a_mortgage_interest: Decimal
  line_16b_other_interest: Decimal
  line_17_legal_professional: Decimal
  line_18_office_expense: Decimal
  line_19_pension_profit_sharing: Decimal
  line_20a_rent_machinery_equipment: Decimal
  line_20b_rent_other_property: Decimal
  line_21_repairs_maintenance: Decimal
  line_22_supplies: Decimal
  line_23_taxes_licenses: Decimal
  line_24a_travel_final: Decimal | null

  meals_50_percent_source_amount: Decimal
  meals_100_percent_source_amount: Decimal
  entertainment_source_amount: Decimal

  line_25_utilities: Decimal
  line_26_wages_final: Decimal | null

  line_13_depreciation_from_form4562: Decimal | null
  line_30_home_office_from_module: Decimal | null
  line_4_cogs_from_module: Decimal | null
}
```

V1 支援三種輸入模式：

#### Mode A — 純簡單 P&L，無特殊項目

```text
line_4_cogs_from_module = null
line_13_depreciation_from_form4562 = null
line_30_home_office_from_module = null
line_9_car_truck_expenses_final = null
line_24a_travel_final = null
line_26_wages_final = null
```

系統將這些 line 視為 0，但前提是 special flags 未顯示有這些項目。

#### Mode B — P&L 已有 final deductible amount

若來源資料或上游模組已經提供 final deductible amount，V1 可直接引用：

```text
line_9_car_truck_expenses_final
line_24a_travel_final
line_26_wages_final
```

V1 不反推公式。

#### Mode C — 由其他模組輸出

若其他模組已完成，V1 可引用：

```text
line_4_cogs_from_module
line_13_depreciation_from_form4562
line_30_home_office_from_module
```

但 Schedule C V1 本身不計算 COGS、Form 4562 或 home office。

### 5.3 OtherExpenseItemV1

```text
OtherExpenseItemV1 = {
  item_id: str
  name: str
  amount: Decimal
  source_document_id: str | null
  confidence:
    HIGH
    | MEDIUM
    | LOW
}
```

若 `confidence == LOW`，V1 應產生 review warning；若分類影響重大，應產生 blocking error。

### 5.4 ScheduleCSpecialCaseFlagsV1

```text
ScheduleCSpecialCaseFlagsV1 = {
  has_inventory_or_cogs: bool
  has_vehicle_expense_requiring_calculation: bool
  has_depreciation_or_section179: bool
  has_home_office: bool
  has_mixed_travel: bool
  has_uncertain_meals_or_entertainment: bool
  has_employee_wages_or_payroll_credit: bool
  has_owner_draw_in_expenses: bool
  has_uncertain_expense_category: bool
  has_rental_or_royalty_activity: bool
  has_farm_activity: bool
  has_business_asset_sale: bool
  has_passive_activity_issue: bool
  has_at_risk_limitation_issue: bool
  has_qbi_request: bool
  has_schedule_se_request: bool
}
```

任一 blocking flag 為 `true` 時，V1 不得產生 `can_file = true`，除非該項已由明確上游模組完成且 V1 只做引用。

---

## 6. Layer 2 — 正規化與中間計算

### 6.1 身分與業務欄位驗證

必填：

```text
proprietor_name
taxpayer_ssn
tax_year
line_1_gross_receipts
```

建議但可 nullable：

```text
principal_business
principal_activity_code
business_name
ein
business_address
```

`tax_year` 僅支援：

```text
2024 | 2025
```

### 6.2 問卷欄位驗證

Line G、H、I 為 Schedule C 表面問卷欄位，V1 應盡量要求明確答案：

```text
line_g_material_participation is bool
line_h_started_or_acquired is bool
line_i_payment_requiring_1099 is bool
```

Line J 只有在 Line I 為 `true` 時才要求：

```text
if line_i_payment_requiring_1099 is true:
    require line_j_filed_required_1099 is bool
else:
    line_j_filed_required_1099_surface = null
```

V1 不從工時或付款明細自動推論 G/I/J；只接受問卷或上游判定結果。

### 6.3 收入計算

```text
line_1_gross_receipts = income.line_1_gross_receipts
line_2_returns_allowances = income.line_2_returns_allowances
line_3_net_receipts = line_1_gross_receipts - line_2_returns_allowances
```

若：

```text
line_3_net_receipts < 0
```

則：

```text
blocking_error = NEGATIVE_NET_RECEIPTS
```

### 6.4 COGS 處理

V1 預設不計算 Part III COGS。

```text
if special_case_flags.has_inventory_or_cogs is false:
    line_4_cogs = 0
elif line_4_cogs_from_module is not null:
    line_4_cogs = line_4_cogs_from_module
else:
    blocking_error = UNSUPPORTED_COGS_IN_V1
```

```text
line_5_gross_profit = line_3_net_receipts - line_4_cogs
line_7_gross_income = line_5_gross_profit + line_6_other_income
```

### 6.5 一般費用分類

所有 expense line 預設以明確分類的來源資料進行加總。

```text
line_8 = expenses.line_8_advertising
line_10 = expenses.line_10_commissions_fees
...
line_25 = expenses.line_25_utilities
```

不得將不確定項目直接塞入 `other_expense_items` 以避免 blocking error。

### 6.6 車輛、差旅、薪資 final amount 引用

```text
line_9 =
  line_9_car_truck_expenses_final
  if line_9_car_truck_expenses_final is not null
  else 0
```

若 `has_vehicle_expense_requiring_calculation == true` 且無 final amount：

```text
blocking_error = UNSUPPORTED_VEHICLE_CALCULATION_IN_V1
```

```text
line_24a =
  line_24a_travel_final
  if line_24a_travel_final is not null
  else 0
```

若 `has_mixed_travel == true` 且無 final amount：

```text
blocking_error = UNSUPPORTED_TRAVEL_ALLOCATION_IN_V1
```

```text
line_26 =
  line_26_wages_final
  if line_26_wages_final is not null
  else 0
```

若 `has_employee_wages_or_payroll_credit == true` 且無 final amount：

```text
blocking_error = PAYROLL_OR_OWNER_DRAW_REVIEW_REQUIRED
```

### 6.7 Meals and entertainment

V1 支援一般 business meals 50% 限制：

```text
line_24b_deductible_meals =
  meals_50_percent_source_amount * Decimal("0.50")
  + meals_100_percent_source_amount
```

Entertainment 不可扣除：

```text
entertainment_deductible_amount = 0
```

若無法區分 meals 與 entertainment：

```text
blocking_error = UNCERTAIN_MEALS_ENTERTAINMENT_CLASSIFICATION
```

### 6.8 Other expenses

```text
line_48_total_other_expenses =
  SUM(item.amount for item in other_expense_items)
```

```text
line_27b_other_expenses = line_48_total_other_expenses
```

若任一 item confidence 過低或 name 顯示可能為 personal/non-deductible：

```text
blocking_error = UNCERTAIN_EXPENSE_CLASSIFICATION
```

或：

```text
review_warning = LOW_CONFIDENCE_OTHER_EXPENSE
```

### 6.9 Depreciation and home office

V1 不計算 depreciation、Section 179 或 home office。

```text
line_13 =
  line_13_depreciation_from_form4562
  if line_13_depreciation_from_form4562 is not null
  else 0
```

若 `has_depreciation_or_section179 == true` 且無上游 Form 4562 結果：

```text
blocking_error = FORM_4562_REQUIRED
```

```text
line_30 =
  line_30_home_office_from_module
  if line_30_home_office_from_module is not null
  else 0
```

若 `has_home_office == true` 且無上游 home office module 結果：

```text
blocking_error = FORM_8829_OR_SIMPLIFIED_HOME_OFFICE_REQUIRED
```

### 6.10 Line 28、29、31

```text
line_28_total_expenses =
  line_8
  + line_9
  + line_10
  + line_11
  + line_12
  + line_13
  + line_14
  + line_15
  + line_16a
  + line_16b
  + line_17
  + line_18
  + line_19
  + line_20a
  + line_20b
  + line_21
  + line_22
  + line_23
  + line_24a
  + line_24b
  + line_25
  + line_26
  + line_27a
  + line_27b
```

V1 中：

```text
line_27a_energy_efficient_building_deduction = 0
```

除非上游 Form 7205 module 完成；否則遇到 179D 就 flag。

```text
line_29_tentative_profit_or_loss = line_7_gross_income - line_28_total_expenses
line_31_net_profit_or_loss = line_29_tentative_profit_or_loss - line_30_home_office
```

### 6.11 Loss and at-risk handling

若：

```text
line_31_net_profit_or_loss >= 0
```

則 Line 32 表面留白：

```text
line_32_surface = null
```

若：

```text
line_31_net_profit_or_loss < 0
```

則要求：

```text
loss_at_risk_answer
```

規則：

```text
if loss_at_risk_answer == ALL_AT_RISK:
    line_32_surface = "32a"
elif loss_at_risk_answer == SOME_NOT_AT_RISK:
    line_32_surface = "32b"
    blocking_error = FORM_6198_REQUIRED
else:
    blocking_error = AT_RISK_ANSWER_MISSING
```

若 Line G material participation 為 `false` 且有 loss：

```text
blocking_error = PASSIVE_ACTIVITY_REVIEW_REQUIRED
```

---

## 7. Layer 3 — Schedule C 表面欄位

## Header

| 欄位 | V1 輸出 | 規則 |
|---|---|---|
| Name of proprietor | `proprietor_name` | 與 Form 1040 一致 |
| SSN | `taxpayer_ssn_masked` for logs / full SSN only for filing payload | 不可在 debug output 直接暴露 |
| Field A | `principal_business` | 若未知，review warning |
| Field B | `principal_activity_code` | 若未知，review warning |
| Field C | `business_name` | 無商號可留白 |
| Field D | `ein` | 無 EIN 可留白 |
| Field E | `business_address` | 無獨立營業地址可留白 |
| Field F | `accounting_method` | Cash / Accrual / Other |
| Line G | `line_g_material_participation` | 直接問卷答案 |
| Line H | `line_h_started_or_acquired` | 直接問卷答案 |
| Line I | `line_i_payment_requiring_1099` | 直接問卷答案 |
| Line J | `line_j_filed_required_1099` | 只有 Line I Yes 時填 |

## Part I — Income

| 欄位 | V1 輸出 | 規則 |
|---|---|---|
| Line 1 | `line_1_gross_receipts` | Gross receipts or sales |
| Line 2 | `line_2_returns_allowances` | Returns and allowances |
| Line 3 | `line_3_net_receipts` | Line 1 - Line 2 |
| Line 4 | `line_4_cogs` | V1 無 COGS 則 0；若由 COGS module 完成可引用 |
| Line 5 | `line_5_gross_profit` | Line 3 - Line 4 |
| Line 6 | `line_6_other_income` | Other business income |
| Line 7 | `line_7_gross_income` | Line 5 + Line 6 |

## Part II — Expenses

| 欄位 | V1 輸出 | 規則 |
|---|---|---|
| Line 8 | `line_8_advertising` | Direct mapping |
| Line 9 | `line_9_car_truck_expenses` | Final amount only；V1 不算 mileage |
| Line 10 | `line_10_commissions_fees` | Direct mapping |
| Line 11 | `line_11_contract_labor` | Direct mapping |
| Line 12 | `line_12_depletion` | Direct mapping；通常需 review |
| Line 13 | `line_13_depreciation` | Form 4562 module only；否則 0 或 flag |
| Line 14 | `line_14_employee_benefit_programs` | Direct mapping |
| Line 15 | `line_15_insurance` | Direct mapping |
| Line 16a | `line_16a_mortgage_interest` | Direct mapping |
| Line 16b | `line_16b_other_interest` | Direct mapping |
| Line 17 | `line_17_legal_professional` | Direct mapping |
| Line 18 | `line_18_office_expense` | Direct mapping |
| Line 19 | `line_19_pension_profit_sharing` | Direct mapping |
| Line 20a | `line_20a_rent_machinery_equipment` | Direct mapping |
| Line 20b | `line_20b_rent_other_property` | Direct mapping |
| Line 21 | `line_21_repairs_maintenance` | Direct mapping |
| Line 22 | `line_22_supplies` | Direct mapping |
| Line 23 | `line_23_taxes_licenses` | Direct mapping |
| Line 24a | `line_24a_travel` | Final business travel amount only |
| Line 24b | `line_24b_deductible_meals` | V1 supports ordinary 50% meals |
| Line 25 | `line_25_utilities` | Direct mapping |
| Line 26 | `line_26_wages` | Final payroll amount only |
| Line 27a | `line_27a_energy_efficient_building_deduction` | V1 default 0；Form 7205 required if claimed |
| Line 27b | `line_27b_other_expenses` | From Part V Line 48 |
| Line 28 | `line_28_total_expenses` | Sum Lines 8–27b |
| Line 29 | `line_29_tentative_profit_or_loss` | Line 7 - Line 28 |
| Line 30 | `line_30_home_office` | V1 default 0；home office module only |
| Line 31 | `line_31_net_profit_or_loss` | Line 29 - Line 30 |
| Line 32 | `line_32_at_risk_surface` | Required only if Line 31 loss |

## Part III — Cost of Goods Sold

V1 不計算 Part III。若沒有 inventory/COGS：

```text
Part III fields = null
line_4_cogs = 0
```

若有 inventory/COGS：

```text
blocking_error = UNSUPPORTED_COGS_IN_V1
```

除非 COGS module 已完成並提供 `line_4_cogs_from_module` 與 Part III surface fields。

## Part IV — Vehicle

V1 不計算 Part IV。若 Line 9 使用 final amount 且不需要 Part IV surface，可繼續。若需要填 Part IV 或判斷 mileage：

```text
blocking_error = UNSUPPORTED_VEHICLE_CALCULATION_IN_V1
```

## Part V — Other Expenses

| 欄位 | V1 輸出 | 規則 |
|---|---|---|
| Line 48 item list | `other_expense_items` | 列出每個 name + amount |
| Line 48 total | `line_48_total_other_expenses` | Other expenses 合計 |
| Line 27b | `line_27b_other_expenses` | 等於 Line 48 |

---

## 8. V1 申報判定

### 8.1 是否可以產生 draft mapping

```text
can_map =
  required identity fields present
  AND at least one business income or expense field present
```

即使有 unsupported flag，也可以 `can_map = true`，用於 UI 顯示 mapping 與缺口。

### 8.2 V1 是否支援

```text
is_v1_supported =
  no blocking unsupported special cases
  OR unsupported item has completed upstream module result
```

### 8.3 是否可以送出 Schedule C

```text
can_file =
  is_v1_supported
  AND blocking_errors is empty
```

### 8.4 是否需要人工審查

```text
needs_review =
  review_warnings is not empty
  OR confidence below threshold
  OR optional header fields are missing
```

`needs_review = true` 不一定代表不能 file；`blocking_errors` 才會讓 `can_file = false`。

---

## 9. 跨表連動

Schedule C V1 只輸出可供其他模組使用的中間結果，不計算其他表單。

```text
Schedule 1 (Form 1040) Line 3 =
  line_31_net_profit_or_loss
  if can_file == true
```

```text
Schedule SE Line 2 =
  line_31_net_profit_or_loss
  if profit and Schedule SE module enabled
```

V1 不計算：

- Self-employment tax。
- QBI deduction。
- Form 8995 / 8995-A。
- Form 461 excess business loss。
- Form 8582 passive activity loss limitation。
- Form 6198 at-risk limitation。
- State tax consequences。

---

## 10. 輸出模型

```text
ScheduleCResultV1 = {
  proprietor_name: str
  taxpayer_ssn_masked: str
  tax_year: int

  principal_business: str | null
  principal_activity_code: str | null
  business_name: str | null
  ein: str | null
  business_address: str | null
  accounting_method: str | null

  line_g_material_participation: bool | null
  line_h_started_or_acquired: bool | null
  line_i_payment_requiring_1099: bool | null
  line_j_filed_required_1099: bool | null

  line_1_gross_receipts: Decimal
  line_2_returns_allowances: Decimal
  line_3_net_receipts: Decimal
  line_4_cogs: Decimal
  line_5_gross_profit: Decimal
  line_6_other_income: Decimal
  line_7_gross_income: Decimal

  line_8_advertising: Decimal
  line_9_car_truck_expenses: Decimal
  line_10_commissions_fees: Decimal
  line_11_contract_labor: Decimal
  line_12_depletion: Decimal
  line_13_depreciation: Decimal
  line_14_employee_benefit_programs: Decimal
  line_15_insurance: Decimal
  line_16a_mortgage_interest: Decimal
  line_16b_other_interest: Decimal
  line_17_legal_professional: Decimal
  line_18_office_expense: Decimal
  line_19_pension_profit_sharing: Decimal
  line_20a_rent_machinery_equipment: Decimal
  line_20b_rent_other_property: Decimal
  line_21_repairs_maintenance: Decimal
  line_22_supplies: Decimal
  line_23_taxes_licenses: Decimal
  line_24a_travel: Decimal
  line_24b_deductible_meals: Decimal
  line_25_utilities: Decimal
  line_26_wages: Decimal
  line_27a_energy_efficient_building_deduction: Decimal
  line_27b_other_expenses: Decimal

  line_28_total_expenses: Decimal
  line_29_tentative_profit_or_loss: Decimal
  line_30_home_office: Decimal
  line_31_net_profit_or_loss: Decimal
  line_32_at_risk_surface: "32a" | "32b" | null

  part_v_other_expense_items: OtherExpenseItemV1[]
  line_48_total_other_expenses: Decimal

  can_map: bool
  is_v1_supported: bool
  can_file: bool
  needs_review: bool

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

## 11. 核心計算偽代碼

```python
from decimal import Decimal

ZERO = Decimal("0.00")


def calculate_schedule_c_v1(inputs):
    errors = []
    warnings = []

    validate_identity(inputs, errors)
    validate_tax_year(inputs.tax_year, allowed={2024, 2025}, errors=errors)
    validate_required_questionnaire(inputs, errors, warnings)
    validate_nonnegative_amounts(inputs, errors)
    detect_unsupported_cases(inputs, errors)

    # Part I
    line_1 = inputs.income.line_1_gross_receipts
    line_2 = inputs.income.line_2_returns_allowances
    line_3 = line_1 - line_2

    if line_3 < ZERO:
        errors.append(issue("NEGATIVE_NET_RECEIPTS", "line_3"))

    # COGS
    if inputs.special_case_flags.has_inventory_or_cogs:
        if inputs.expenses.line_4_cogs_from_module is not None:
            line_4 = inputs.expenses.line_4_cogs_from_module
        else:
            errors.append(issue("UNSUPPORTED_COGS_IN_V1", "line_4"))
            line_4 = ZERO
    else:
        line_4 = ZERO

    line_5 = line_3 - line_4
    line_6 = inputs.income.line_6_other_income
    line_7 = line_5 + line_6

    # Expenses
    line_8 = inputs.expenses.line_8_advertising

    if inputs.special_case_flags.has_vehicle_expense_requiring_calculation:
        if inputs.expenses.line_9_car_truck_expenses_final is None:
            errors.append(issue("UNSUPPORTED_VEHICLE_CALCULATION_IN_V1", "line_9"))
    line_9 = inputs.expenses.line_9_car_truck_expenses_final or ZERO

    line_10 = inputs.expenses.line_10_commissions_fees
    line_11 = inputs.expenses.line_11_contract_labor
    line_12 = inputs.expenses.line_12_depletion

    if inputs.special_case_flags.has_depreciation_or_section179:
        if inputs.expenses.line_13_depreciation_from_form4562 is None:
            errors.append(issue("FORM_4562_REQUIRED", "line_13"))
    line_13 = inputs.expenses.line_13_depreciation_from_form4562 or ZERO

    line_14 = inputs.expenses.line_14_employee_benefit_programs
    line_15 = inputs.expenses.line_15_insurance
    line_16a = inputs.expenses.line_16a_mortgage_interest
    line_16b = inputs.expenses.line_16b_other_interest
    line_17 = inputs.expenses.line_17_legal_professional
    line_18 = inputs.expenses.line_18_office_expense
    line_19 = inputs.expenses.line_19_pension_profit_sharing
    line_20a = inputs.expenses.line_20a_rent_machinery_equipment
    line_20b = inputs.expenses.line_20b_rent_other_property
    line_21 = inputs.expenses.line_21_repairs_maintenance
    line_22 = inputs.expenses.line_22_supplies
    line_23 = inputs.expenses.line_23_taxes_licenses

    if inputs.special_case_flags.has_mixed_travel:
        if inputs.expenses.line_24a_travel_final is None:
            errors.append(issue("UNSUPPORTED_TRAVEL_ALLOCATION_IN_V1", "line_24a"))
    line_24a = inputs.expenses.line_24a_travel_final or ZERO

    if inputs.special_case_flags.has_uncertain_meals_or_entertainment:
        errors.append(issue("UNCERTAIN_MEALS_ENTERTAINMENT_CLASSIFICATION", "line_24b"))

    line_24b = (
        inputs.expenses.meals_50_percent_source_amount * Decimal("0.50")
        + inputs.expenses.meals_100_percent_source_amount
    )

    line_25 = inputs.expenses.line_25_utilities

    if inputs.special_case_flags.has_employee_wages_or_payroll_credit:
        if inputs.expenses.line_26_wages_final is None:
            errors.append(issue("PAYROLL_OR_OWNER_DRAW_REVIEW_REQUIRED", "line_26"))
    line_26 = inputs.expenses.line_26_wages_final or ZERO

    # 179D/Form 7205 not supported in V1
    line_27a = ZERO
    if inputs.special_case_flags.has_179d_or_form7205:
        errors.append(issue("FORM_7205_REQUIRED", "line_27a"))

    line_48 = sum_decimal(item.amount for item in inputs.other_expense_items)
    line_27b = line_48

    line_28 = sum_decimal([
        line_8, line_9, line_10, line_11, line_12, line_13,
        line_14, line_15, line_16a, line_16b, line_17, line_18,
        line_19, line_20a, line_20b, line_21, line_22, line_23,
        line_24a, line_24b, line_25, line_26, line_27a, line_27b,
    ])

    line_29 = line_7 - line_28

    if inputs.special_case_flags.has_home_office:
        if inputs.expenses.line_30_home_office_from_module is None:
            errors.append(issue("FORM_8829_OR_SIMPLIFIED_HOME_OFFICE_REQUIRED", "line_30"))
    line_30 = inputs.expenses.line_30_home_office_from_module or ZERO

    line_31 = line_29 - line_30

    # Line 32 only for loss
    line_32 = None
    if line_31 < ZERO:
        if inputs.loss_at_risk_answer == "ALL_AT_RISK":
            line_32 = "32a"
        elif inputs.loss_at_risk_answer == "SOME_NOT_AT_RISK":
            line_32 = "32b"
            errors.append(issue("FORM_6198_REQUIRED", "line_32"))
        else:
            errors.append(issue("AT_RISK_ANSWER_MISSING", "line_32"))

        if inputs.line_g_material_participation is False:
            errors.append(issue("PASSIVE_ACTIVITY_REVIEW_REQUIRED", "line_g"))

    can_map = has_any_schedule_c_mapping(inputs)
    is_v1_supported = len([e for e in errors if e.is_unsupported_case]) == 0
    can_file = is_v1_supported and len(errors) == 0

    return ScheduleCResultV1(
        line_1_gross_receipts=line_1,
        line_2_returns_allowances=line_2,
        line_3_net_receipts=line_3,
        line_4_cogs=line_4,
        line_5_gross_profit=line_5,
        line_6_other_income=line_6,
        line_7_gross_income=line_7,
        line_8_advertising=line_8,
        line_9_car_truck_expenses=line_9,
        line_10_commissions_fees=line_10,
        line_11_contract_labor=line_11,
        line_12_depletion=line_12,
        line_13_depreciation=line_13,
        line_14_employee_benefit_programs=line_14,
        line_15_insurance=line_15,
        line_16a_mortgage_interest=line_16a,
        line_16b_other_interest=line_16b,
        line_17_legal_professional=line_17,
        line_18_office_expense=line_18,
        line_19_pension_profit_sharing=line_19,
        line_20a_rent_machinery_equipment=line_20a,
        line_20b_rent_other_property=line_20b,
        line_21_repairs_maintenance=line_21,
        line_22_supplies=line_22,
        line_23_taxes_licenses=line_23,
        line_24a_travel=line_24a,
        line_24b_deductible_meals=line_24b,
        line_25_utilities=line_25,
        line_26_wages=line_26,
        line_27a_energy_efficient_building_deduction=line_27a,
        line_27b_other_expenses=line_27b,
        line_28_total_expenses=line_28,
        line_29_tentative_profit_or_loss=line_29,
        line_30_home_office=line_30,
        line_31_net_profit_or_loss=line_31,
        line_32_at_risk_surface=line_32,
        line_48_total_other_expenses=line_48,
        can_map=can_map,
        is_v1_supported=is_v1_supported,
        can_file=can_file,
        blocking_errors=errors,
        review_warnings=warnings,
    )
```

---

## 12. 最低必要測試案例

### Test 1 — 最基本服務業 P&L

```json
{
  "line_1_gross_receipts": 12000.00,
  "line_2_returns_allowances": 0.00,
  "line_6_other_income": 0.00,
  "line_8_advertising": 150.00,
  "line_17_legal_professional": 300.00,
  "line_25_utilities": 600.00,
  "other_expense_items": []
}
```

預期：

```text
Line 1 = 12000.00
Line 3 = 12000.00
Line 7 = 12000.00
Line 28 = 1050.00
Line 31 = 10950.00
can_file = true
```

### Test 2 — 有 returns and allowances

```text
Line 1 = 20000.00
Line 2 = 500.00
```

預期：

```text
Line 3 = 19500.00
```

### Test 3 — Expenses appear by category

```json
{
  "line_8_advertising": 100.00,
  "line_10_commissions_fees": 250.00,
  "line_11_contract_labor": 1000.00,
  "line_18_office_expense": 80.00,
  "line_25_utilities": 120.00
}
```

預期：

```text
Schedule C surface shows each expense on its own category line.
Line 28 includes all supported categories.
```

### Test 4 — Other expenses Part V

```json
{
  "other_expense_items": [
    {"name": "Bank Charges", "amount": 40.00},
    {"name": "Software Subscription", "amount": 300.00}
  ]
}
```

預期：

```text
Part V lists both items.
Line 48 = 340.00
Line 27b = 340.00
```

### Test 5 — 一般商務餐飲 50%

```json
{
  "meals_50_percent_source_amount": 1000.00,
  "meals_100_percent_source_amount": 0.00,
  "entertainment_source_amount": 0.00
}
```

預期：

```text
Line 24b = 500.00
```

### Test 6 — Meals / entertainment 分類不清

```text
has_uncertain_meals_or_entertainment = true
```

預期：

```text
blocking error = UNCERTAIN_MEALS_ENTERTAINMENT_CLASSIFICATION
can_file = false
```

### Test 7 — COGS 出現但沒有 COGS module

```text
has_inventory_or_cogs = true
line_4_cogs_from_module = null
```

預期：

```text
blocking error = UNSUPPORTED_COGS_IN_V1
can_file = false
can_map = true
```

### Test 8 — COGS 由上游 module 完成

```text
has_inventory_or_cogs = true
line_4_cogs_from_module = 2000.00
```

預期：

```text
Line 4 = 2000.00
can_file 可繼續依其他錯誤判定
```

### Test 9 — 車輛需要 mileage 計算

```text
has_vehicle_expense_requiring_calculation = true
line_9_car_truck_expenses_final = null
```

預期：

```text
blocking error = UNSUPPORTED_VEHICLE_CALCULATION_IN_V1
```

### Test 10 — 車輛 final amount 已由上游提供

```text
line_9_car_truck_expenses_final = 850.00
```

預期：

```text
Line 9 = 850.00
```

### Test 11 — Home office 出現但沒有 module

```text
has_home_office = true
line_30_home_office_from_module = null
```

預期：

```text
blocking error = FORM_8829_OR_SIMPLIFIED_HOME_OFFICE_REQUIRED
```

### Test 12 — Profit case 不需要 Line 32

```text
Line 31 = 5000.00
```

預期：

```text
line_32_at_risk_surface = null
can_file 不因 Line 32 缺失而失敗
```

### Test 13 — Loss case，all at risk

```text
Line 31 = -1000.00
loss_at_risk_answer = ALL_AT_RISK
```

預期：

```text
line_32_at_risk_surface = 32a
can_file 可繼續依其他錯誤判定
```

### Test 14 — Loss case，some not at risk

```text
Line 31 = -1000.00
loss_at_risk_answer = SOME_NOT_AT_RISK
```

預期：

```text
line_32_at_risk_surface = 32b
blocking error = FORM_6198_REQUIRED
can_file = false
```

### Test 15 — Owner draw 混入費用

```text
has_owner_draw_in_expenses = true
```

預期：

```text
blocking error = OWNER_DRAW_INCLUDED_IN_EXPENSES
can_file = false
```

---

## 13. V1 完成條件

V1 可視為完成，必須同時滿足：

- Business gross receipts 可正確進入 Schedule C Line 1。
- Returns and allowances 可正確進入 Line 2。
- Line 3、5、7 可正確計算。
- 無 COGS 的簡單 P&L 可正確將 Line 4 設為 0。
- 一般費用可依 Schedule C Lines 8–27b 類別顯示。
- Other expenses 可列入 Part V，並合計至 Line 48 / Line 27b。
- Line 28 total expenses 可正確計算。
- Line 29 tentative profit or loss 可正確計算。
- 無 home office 的簡單 P&L 可正確將 Line 30 設為 0。
- Line 31 net profit or loss 可正確計算。
- Loss case 可正確要求 Line 32 at-risk answer。
- 不支援項目均以 blocking error 明確阻斷。
- `can_map`、`is_v1_supported`、`can_file` 三者語意清楚且可測試。
- 所有金額內部均使用 `Decimal` 或 integer cents。
- 所有 blocking error 均具有固定且可測試的錯誤代碼。
- LLM parser 不自行計算公式、不自行做 business/personal 比例分攤。
- Calculator 不依賴 LLM，也不依賴外部 I/O，可獨立單元測試。

---

## 14. V2 以後再處理

下列功能不屬於 V1：

- 完整 Part III COGS / inventory valuation。
- Part IV vehicle mileage / actual expense method。
- Form 4562 depreciation、amortization、Section 179。
- Form 8829 或 simplified home office worksheet。
- Mixed domestic / international travel allocation。
- 完整 meals / entertainment substantiation rules。
- Employee payroll credits 與完整 payroll return reconciliation。
- Owner draw / guaranteed payment / reasonable compensation 判斷。
- Form 6198 at-risk limitation。
- Form 8582 passive activity limitation。
- Form 461 excess business loss limitation。
- Form 7205 / IRC §179D。
- Form 4797 business asset sale。
- Form 6252 installment sale。
- Form 8824 like-kind exchange。
- Form 8995 / 8995-A QBI deduction。
- Schedule SE self-employment tax。
- State and local tax treatment。
- E-file schema generation。

---

## 15. 建議 schema 收斂

如果要把現有 Schedule C schema 改成 V1，建議：

### 15.1 保留

```text
proprietor_name
taxpayer_ssn
tax_year
principal_business
principal_activity_code
business_name
ein
business_address
accounting_method
line_g_material_participation
line_h_started_or_acquired
line_i_payment_requiring_1099
line_j_filed_required_1099

line_1_gross_receipts
line_2_returns_allowances
line_6_other_income

line_8_advertising
line_9_car_truck_expenses_final
line_10_commissions_fees
line_11_contract_labor
line_12_depletion
line_14_employee_benefit_programs
line_15_insurance
line_16a_mortgage_interest
line_16b_other_interest
line_17_legal_professional
line_18_office_expense
line_19_pension_profit_sharing
line_20a_rent_machinery_equipment
line_20b_rent_other_property
line_21_repairs_maintenance
line_22_supplies
line_23_taxes_licenses
line_24a_travel_final
meals_50_percent_source_amount
meals_100_percent_source_amount
entertainment_source_amount
line_25_utilities
line_26_wages_final
other_expense_items

line_4_cogs_from_module
line_13_depreciation_from_form4562
line_30_home_office_from_module

loss_at_risk_answer
special_case_flags
```

### 15.2 移除或改成 flags

```text
line_33_inventory_valuation_method
line_34_change_in_valuation
line_35_beginning_inventory
line_36_purchases_less_personal
line_37_cost_of_labor
line_38_materials_supplies
line_39_other_costs
line_40_total_cost_of_goods
line_41_ending_inventory
line_42_cogs

line_43_date_placed_in_service
line_44a_business_miles
line_44b_commuting_miles
line_44c_other_miles
line_45_available_for_personal_use
line_46_another_vehicle_available
line_47a_evidence_to_support
line_47b_evidence_written

owner_annual_hours
others_annual_hours
is_sole_participant

actual_car_expenses
parking_and_tolls
selected_mileage_method

macrs_depreciation
sec179_asset_cost
use_sec179

travel_transit_cost
travel_lodging_cost
total_trip_days
business_days
is_international

w2_gross_wages
employment_credits
owner_salary_or_draw

improved_building_sqft
certified_deduction_rate

home_office_sqft
total_home_sqft
allowable_home_expenses
is_exclusive_and_regular
selected_home_method

nonrecourse_debt
guaranteed_non_risk_funding
prior_year_ending_inventory
book_beginning_inventory
production_labor_wages
owner_production_labor_pay

book_amortization
book_bad_debts
de_minimis_safe_harbor_cost
```

這些欄位不是永遠不能做，而是不該放在 Schedule C V1 主 schema 裡讓 reviewer 以為已經完整支援。  
若需要，可由其他 module 或 future V2 提供 final line amount。

---

## 16. 官方參考資料

- 2025 Schedule C (Form 1040):  
  https://www.irs.gov/pub/irs-prior/f1040sc--2025.pdf

- 2025 Instructions for Schedule C (Form 1040):  
  https://www.irs.gov/instructions/i1040sc

- 2024 Schedule C (Form 1040):  
  https://www.irs.gov/pub/irs-prior/f1040sc--2024.pdf

- IRS About Schedule C (Form 1040):  
  https://www.irs.gov/forms-pubs/about-schedule-c-form-1040

> 稅法、表單及電子申報規格可能更新。正式申報前，應依對應年度 IRS 最新表單、說明及適用的電子申報 schema 再次驗證。
