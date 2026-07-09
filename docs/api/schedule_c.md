# Schedule C (自營職業利潤與虧損) API

從上傳的自營職業憑證（損益表、商業收據、發票等）自動提取財務事實，
並透過 V1 確定性計算引擎完成 Schedule C 試算。

---

## POST `/schedule-c/extract-and-calculate`

**驗證**：Request Header 需夾帶 `X-API-Token`。

### Request Body

| 參數 | 類型 | 必填 | 說明 |
|---|---|---|---|
| `taxpayer_profile` | object | ✅ | 納稅人基本資料（姓名、報稅年度、事業類型等） |
| `uploaded_documents` | list[object] | ✅ | 文件列表，每個物件含 `file_name`（檔名）與 `content`（文字內容） |
| `model_name` | string | ❌ | 指定 LLM 模型（預設 `gemini-2.5-pro`） |

#### Request 範例

```json
{
  "taxpayer_profile": {
    "name": "Jane Smith",
    "ssn": "XXX-XX-5678",
    "tax_year": 2024,
    "business_name": "Smith Consulting",
    "business_code": "541600"
  },
  "uploaded_documents": [
    {
      "file_name": "PnL_2024.txt",
      "content": "Gross receipts: $182,500. COGS: $63,200. Advertising: $5,000. Office supplies: $1,200. Software subscriptions: $2,400."
    },
    {
      "file_name": "Vehicle_Log_2024.txt",
      "content": "Business mileage: 8,240 miles. Total mileage: 12,000 miles. Vehicle: 2021 Toyota Camry."
    }
  ]
}
```

---

### Response Body

| 欄位 | 類型 | 說明 |
|---|---|---|
| `success` | boolean | 成功時為 `true` |
| `state` | object | 計算結果，詳見下表 |
| `debug_info` | object | LLM 模型名稱、完整 prompt、原始輸出 |

#### `state` 欄位明細（V1 計算結果）

**表頭資訊**

| 欄位 | 類型 | 說明 |
|---|---|---|
| `taxpayer_name` | string | 納稅人姓名 |
| `taxpayer_ssn_masked` | string | 遮蔽後的 SSN |
| `tax_year` | int | 報稅年度 |
| `business_name` | string | 事業名稱 |
| `business_code` | string | 主要業務代碼（Business Activity Code） |
| `accounting_method` | string | 會計方法（CASH / ACCRUAL） |

**Part I — 收入**

| 欄位 | 類型 | 說明 |
|---|---|---|
| `line_1_gross_receipts_or_sales` | float \| null | Line 1：總收入／銷售額 |
| `line_2_returns_and_allowances` | float \| null | Line 2：退貨與折讓 |
| `line_3_net_receipts` | float \| null | Line 3：淨收入（Line 1 − Line 2） |
| `line_4_cost_of_goods_sold` | float \| null | Line 4：商品銷售成本（COGS） |
| `line_5_gross_profit` | float \| null | Line 5：毛利（Line 3 − Line 4） |
| `line_6_other_income` | float \| null | Line 6：其他收入 |
| `line_7_gross_income` | float \| null | Line 7：總毛利（Line 5 + Line 6） |

**Part II — 費用（Lines 8–27）**

| 欄位 | 類型 | 說明 |
|---|---|---|
| `line_8_advertising` | float \| null | 廣告費 |
| `line_9_car_and_truck_expenses` | float \| null | 汽車費用 |
| `line_10_commissions_and_fees` | float \| null | 佣金與費用 |
| `line_11_contract_labor` | float \| null | 合約勞工費 |
| `line_12_depletion` | float \| null | 耗竭費 |
| `line_13_depreciation` | float \| null | 折舊 / Section 179（需 Form 4562） |
| `line_14_employee_benefit_programs` | float \| null | 員工福利計畫（非自有） |
| `line_15_insurance` | float \| null | 保險費（非健保） |
| `line_16a_mortgage_interest` | float \| null | 抵押貸款利息（Line 16a） |
| `line_16b_other_interest` | float \| null | 其他利息（Line 16b） |
| `line_17_legal_and_professional` | float \| null | 法律與專業服務費 |
| `line_18_office_expense` | float \| null | 辦公室費用 |
| `line_19_pension_and_profit_sharing` | float \| null | 退休金計畫 |
| `line_20a_rent_or_lease_vehicles` | float \| null | 機具租賃（Line 20a） |
| `line_20b_rent_or_lease_other` | float \| null | 其他租賃（Line 20b） |
| `line_21_repairs_and_maintenance` | float \| null | 修繕與維護 |
| `line_22_supplies` | float \| null | 耗材 |
| `line_23_taxes_and_licenses` | float \| null | 稅與執照費 |
| `line_24a_travel` | float \| null | 差旅費（Line 24a） |
| `line_24b_deductible_meals` | float \| null | 可扣除餐費 50%（Line 24b） |
| `line_25_utilities` | float \| null | 水電費 |
| `line_26_wages` | float \| null | 薪資（扣除就業機會稅額抵免後） |
| `line_27a_other_expenses_total` | float \| null | 其他費用小計（Part V Line 48 結轉） |
| `line_27b_reserved` | float \| null | 保留欄位（目前為 0） |
| `line_28_total_expenses` | float \| null | 費用合計（Lines 8–27a） |
| `line_29_tentative_profit_or_loss` | float \| null | 試算利潤或虧損（Line 7 − Line 28） |
| `line_30_home_office_deduction` | float \| null | 家庭辦公室扣除（Form 8829 結轉） |
| `line_31_net_profit_or_loss` | float \| null | 淨利潤或虧損（Line 29 − Line 30） |

**Part V — Other Expenses 明細**

| 欄位 | 類型 | 說明 |
|---|---|---|
| `other_expense_items` | list[object] | Part V 其他費用明細清單（含 `name`、`amount`、`part_v_category`、`confidence` 等欄位） |

**申報狀態**

| 欄位 | 類型 | 說明 |
|---|---|---|
| `is_v1_supported` | boolean | 本案件是否在 V1 支援範圍內 |
| `can_file` | boolean | 是否已具備申報條件（無阻斷錯誤） |
| `blocking_errors` | list[object] | 阻斷錯誤清單（見下） |
| `review_warnings` | list[object] | 警告與人工審核清單（見下） |

#### `blocking_errors` / `review_warnings` 物件結構

```json
{
  "code": "HOME_OFFICE_DEDUCTION",
  "field": "line_30_home_office_deduction",
  "item_id": null,
  "source_document_id": "PnL_2024.txt",
  "message": "Home office deduction detected; Form 8829 calculation is required and not supported in V1."
}
```

#### `debug_info` 物件結構

```json
{
  "model_name": "gemini-2.5-pro",
  "prompt_log": "...",
  "raw_output": "..."
}
```

---

### cURL 範例

```bash
curl -X POST "http://localhost:8088/schedule-c/extract-and-calculate" \
     -H "Content-Type: application/json" \
     -H "X-API-Token: tax-rag-secret-token" \
     -d '{
       "taxpayer_profile": {
         "name": "Jane Smith",
         "tax_year": 2024,
         "business_name": "Smith Consulting"
       },
       "uploaded_documents": [
         {
           "file_name": "PnL_2024.txt",
           "content": "Gross receipts: $182,500. Advertising: $5,000. Office supplies: $1,200."
         }
       ]
     }'
```

### 成功 Response 範例

```json
{
  "success": true,
  "state": {
    "taxpayer_name": "Jane Smith",
    "tax_year": 2024,
    "business_name": "Smith Consulting",
    "line_1_gross_receipts_or_sales": 182500.0,
    "line_4_cost_of_goods_sold": 0.0,
    "line_7_gross_income": 182500.0,
    "line_8_advertising": 5000.0,
    "line_18_office_expense": 1200.0,
    "line_28_total_expenses": 6200.0,
    "line_31_net_profit_or_loss": 176300.0,
    "is_v1_supported": true,
    "can_file": true,
    "blocking_errors": [],
    "review_warnings": []
  },
  "debug_info": {
    "model_name": "gemini-2.5-pro",
    "prompt_log": "...",
    "raw_output": "..."
  }
}
```

---

## V1 引擎支援範圍與限制

| 支援 ✅ | 不支援 ❌（Blocking Error） |
|---|---|
| 一般自營收入與費用提取（Lines 1–28） | 折舊 / Section 179（Form 4562）→ `DEPRECIATION_REQUIRED` |
| 商品銷售成本（COGS，Part III） | 家庭辦公室扣除（Form 8829）→ `HOME_OFFICE_DEDUCTION` |
| Part V 其他費用（Other Expenses，Lines 48/27a） | 被動活動損失限制（Form 8582）→ `PASSIVE_ACTIVITY_LIMITATION` |
| 標準里程費率（車輛費用） | At-Risk 限制（Form 6198）→ `AT_RISK_LIMITATION` |
| SE Tax 自僱稅計算（Part IV） | QBI 扣除額（Form 8995/8995-A）→ `QBI_DEDUCTION_REQUIRED` |
| Special Case Flags 自動標記 | Prior Year 損失結轉（NOL Carryforward）→ `PRIOR_YEAR_NOL` |
