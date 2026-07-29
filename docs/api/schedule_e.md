# Schedule E (租賃及合夥權益) API

提供從上傳的租賃憑證（如租賃房產收支明細單、1099-MISC等）中自動提取財務事實，並自動進行 Schedule E Part I 租賃房地產收入與支出試算的 API 服務。

---

## 1. 提取並試算 API

傳入納稅人檔案與未結構化的文件內容，系統將使用 LLM 自動識別並提取 Schedule E 相關數值，隨後自動帶入 V1 確定性計算引擎完成試算。

* **端點**：`POST /schedule-e/extract-and-calculate`
* **驗證方式**：必須在 Request Header 中夾帶 `X-API-Token`。

### 請求參數 (Request Body)

| 參數名稱 | 類型 | 必填 | 說明 |
| :--- | :--- | :--- | :--- |
| `taxpayer_profile` | object | **是** | 納稅人一般資訊與配置（如姓名、報稅年度等）。 |
| `uploaded_documents` | list[object] | **是** | 已上傳的文件列表。每個物件包含 `file_name` (檔名) 與 `content` (文字內容)。 |
| `model_name` | string | 否 | 指定使用的 LLM 模型名稱 (預設為 `"gemini-2.5-pro"`)。 |

#### 請求 Payload 範例
```json
{
  "taxpayer_profile": {
    "name": "Marcus and Elena Rivera",
    "tax_year": 2024
  },
  "uploaded_documents": [
    {
      "file_name": "Sample Rental Statement.json",
      "content": "Monthly Rent Income: $16,200. Mortgage Interest: $4,800. Property Taxes: $2,600."
    }
  ]
}
```

### 回應欄位 (Response Body)

* `success` (boolean)：`true`。
* `state` (object)：試算最終欄位數值，其結構完全對齊最新 V1 計算結果與 IRS 實體表單格線：
  * `taxpayer_name` (string)：納稅人姓名。
  * `taxpayer_ssn_masked` (string)：遮蔽後的 SSN。
  * `tax_year` (int)：報稅年度。
  * `filing_status` (string)：申報身份。
  * `line_a_form_1099_required` (boolean)：Line A 是否有需發送 1099 的款項。
  * `line_b_forms_1099_filed_or_will_file` (boolean)：Line B 是否已申報或將申報 1099。
  * `properties` (list[object])：包含各房產的明細計算（欄位與表單格線對齊，詳見下方對照表）。
  * `line_23a_total_rents` (float)：Line 23a 租金總額小計。
  * `line_23b_total_royalties` (float)：Line 23b 權利金總額小計。
  * `line_23c_total_mortgage_interest` (float)：Line 23c 房貸利息小計。
  * `line_23d_total_depreciation` (float)：Line 23d 折舊總額小計。
  * `line_23e_total_expenses` (float)：Line 23e 總費用小計。
  * `line_24_income` (float)：Line 24 總房產淨利潤小計。
  * `line_25_losses` (float)：Line 25 總房產淨虧損小計。
  * `line_26_total_rental_income_or_loss` (float)：Line 26 租賃與權利金最終損益總計。
  * `schedule_1_line_5_transfer_amount` (float)：需結轉至 Schedule 1 Line 5 的金額。
  * `requires_form_4562_attachment` (boolean)：是否需要附送 Form 4562 折舊表。
  * `requires_form_6198_attachment` (boolean)：是否需要附送 Form 6198 在險限制表。
  * `requires_form_8582_attachment` (boolean)：是否需要附送 Form 8582 被動損失限制表。
  * `requires_form_461_review` (boolean)：是否需要進行 Form 461 超額營業損失審查。
  * `is_v1_supported` (boolean)：本案是否在 V1 計算引擎支援範圍內。
  * `can_file` (boolean)：是否已無阻斷錯誤，可進行電子申報。
  * `blocking_errors` (list[object])：阻斷錯誤清單。每個錯誤物件包含以下屬性：
    * `code` (string)：錯誤代碼（例如 `UNSUPPORTED_PERSONAL_USE_PROPERTY`）。
    * `field` (string | null)：關聯的欄位名稱。
    * `item_id` (string | null)：關聯的明細項目 ID。
    * `source_document_id` (string | null)：關聯的來源憑證/檔案名稱。
    * `message` (string)：詳細的中文錯誤說明。
  * `review_warnings` (list[object])：警告與人工審核清單。每個警告物件包含以下屬性：
    * `code` (string)：警告代碼。
    * `field` (string | null)：關聯的欄位名稱。
    * `item_id` (string | null)：關聯的明細項目 ID。
    * `source_document_id` (string | null)：關聯的來源憑證/檔案名稱。
    * `message` (string)：詳細的中文警告說明。

#### `properties` 陣列內部單個房產物件欄位明細

| 欄位名稱 | 類型 | 說明 / 對應 IRS 表單位置 |
| :--- | :--- | :--- |
| `property_id` | string | 房產唯一識別 ID。 |
| `property_column` | string | 申報欄位（`A`、`B` 或 `C`）。 |
| `line_1a_physical_address` | string | Line 1a：房產實體地址。 |
| `line_1b_property_type_code` | int | Line 1b：房產類型代碼 (例如：1=Single Family, 2=Multi-Family 等)。 |
| `line_2_fair_rental_days` | int | Line 2：出租天數 (Fair Rental Days)。 |
| `line_2_personal_use_days` | int | Line 2：自住天數 (Personal Use Days)。 |
| `line_2_qjv_checkbox` | boolean | Line 2：是否屬於合格共同事業 (QJV)。 |
| `line_3_rents_received` | float | Line 3：收到的租金。 |
| `line_4_royalties_received` | float | Line 4：收到的權利金。 |
| `line_5_advertising` | float | Line 5：廣告費用。 |
| `line_6_auto_and_travel` | float | Line 6：汽車與差旅費。 |
| `line_7_cleaning_and_maintenance` | float | Line 7：清潔與維護費。 |
| `line_8_commissions` | float | Line 8：佣金。 |
| `line_9_insurance` | float | Line 9：保險費。 |
| `line_10_legal_and_professional_fees` | float | Line 10：法律與專業顧問費。 |
| `line_11_management_fees` | float | Line 11：物業管理費。 |
| `line_12_mortgage_interest` | float | Line 12：給付銀行的抵押貸款利息。 |
| `line_13_other_interest` | float | Line 13：其他利息。 |
| `line_14_repairs` | float | Line 14：修繕費。 |
| `line_15_supplies` | float | Line 15：辦公/清潔耗材費。 |
| `line_16_taxes` | float | Line 16：房產相關稅額。 |
| `line_17_utilities` | float | Line 17：水電瓦斯費。 |
| `line_18_depreciation` | float | Line 18：折舊扣除額 (由 Form 4562 結轉)。 |
| `line_19_other_expenses_total` | float | Line 19：其他非標準分類費用總計。 |
| `line_20_total_expenses` | float | Line 20：該房產總支出費用 (Lines 5–19 的總和)。 |
| `pre_at_risk_net_income_or_loss` | float | 扣除在險與被動限制前的淨利潤或虧損。 |
| `line_21_income_or_loss` | float | Line 21：房產淨利潤 (若為虧損則可能受 At-Risk 限制)。 |
| `line_22_deductible_rental_loss` | float | Line 22：可扣除的房產淨虧損 (由 Form 8582 計算後所得之允許扣除值)。 |
* `debug_info` (object)：除錯與日誌資訊物件。包含以下屬性：
  * `model_name` (string)：執行此次提取所使用的 LLM 模型名稱（例如 `gemini-2.5-pro`）。
  * `prompt_log` (string)：發送給 LLM 的完整提示詞（Prompt）內容，包含注入的上下文。
  * `raw_output` (string)：LLM 回傳的原始文字（JSON 格式字串）。

---

## 使用範例

### cURL 指令 (簡易範例)
```bash
curl -X POST "http://localhost:8088/schedule-e/extract-and-calculate" \
     -H "Content-Type: application/json" \
     -H "X-API-Token: tax_rag_p9k2_Lz7v_Xm4q_Secure_9103" \
     -d '{
       "taxpayer_profile": {
         "name": "Marcus and Elena Rivera",
         "tax_year": 2024
       },
       "uploaded_documents": [
         {
           "file_name": "rental.txt",
           "content": "Monthly Rent Income: $16200. Mortgage Interest: $4800."
         }
       ]
     }'
```

### 完整 Case 0622 測試指令 (包含全部 6 個 Sample 憑證，複製貼上即可測試)

以下為 Marcus & Elena Rivera (Case 0622) 的真實資料，包含了兩個 W-2 檔案、一個 1098 房屋扣除額檔案、一個整合利息/股利/IRA 的 1099 檔案，以及兩個租賃與折舊相關檔案，直接呼叫 Schedule E 提取並試算 API：

```bash
curl -X POST "http://localhost:8088/schedule-e/extract-and-calculate" \
  -H "Content-Type: application/json" \
  -H "X-API-Token: tax_rag_p9k2_Lz7v_Xm4q_Secure_9103" \
  -d '{
    "taxpayer_profile": {
      "name": "Marcus & Elena Rivera",
      "ssn": "123-45-6789",
      "tax_year": 2025,
      "filing_status": "MFJ"
    },
    "uploaded_documents": [
      {
        "file_name": "Sample 01 - W-2 Marcus.txt",
        "content": "Form W-2 Wage and Tax Statement 2025. Employer: Creature Comforts Pet Supply EIN 94-1234567. Employee: Marcus Rivera SSN 123-45-6789. Box 1 Wages, tips, other compensation: $46,000. Box 2 Federal income tax withheld: $4,200. Box 13 Retirement Plan checked."
      },
      {
        "file_name": "Sample 02 - W-2 Elena.txt",
        "content": "Form W-2 Wage and Tax Statement 2025. Employer: City of Sacramento EIN 94-7654321. Employee: Elena Rivera SSN 987-65-4321. Box 1 Wages, tips, other compensation: $54,000. Box 2 Federal income tax withheld: $5,200. Box 13 Retirement Plan checked."
      },
      {
        "file_name": "Sample 03 - Rivera 1098.txt",
        "content": "Form 1098 Mortgage Interest Statement 2025. Payer: Marcus and Elena Rivera. Lender: Golden West Bank. Box 1: Mortgage interest: $9,800. Box 10: Real estate taxes paid on primary residence: $2,600."
      },
      {
        "file_name": "Sample 04 - 1099-DIV & 1099-INT & IRA & Charity.txt",
        "content": "Form 1099-INT. Payer: Chase Bank NA. Box 1 Interest Income: $150.00. Form 1099-DIV. Payer: Vanguard. Box 1a Total Ordinary Dividends: $405.00. Traditional IRA Contribution: Taxpayer Elena Rivera made a traditional IRA contribution of $7,000.00 for tax year 2025."
      },
      {
        "file_name": "Sample 05 - Rental Property Income_.txt",
        "content": "Rental Property Income Statement 2025. Property Address: 5200 Green Valley Drive, Unit 208, Sacramento, CA 95841. Gross Rental Income: $16,650. Expenses: Mortgage Interest: $4,800, County Property Tax: $2,400, Landlord Insurance: $900, Repairs and Maintenance: $550."
      },
      {
        "file_name": "Sample 06 - Depreciation Information.txt",
        "content": "Depreciation Information for 5200 Green Valley Drive Condo. Placed in service: 07/01/2022. Original Purchase Price: $275,000 (Land: $55,000, Building: $220,000). Total depreciation deduction claimed in prior years: $12,000."
      }
    ]
  }'
```

### 預期 Response JSON 範例

```json
{
  "success": true,
  "state": {
    "taxpayer_name": "Marcus & Elena Rivera",
    "taxpayer_ssn_masked": "***-**-6789",
    "tax_year": 2025,
    "filing_status": "MFJ",
    "line_a_form_1099_required": true,
    "line_b_forms_1099_filed_or_will_file": true,
    "properties": [
      {
        "property_id": "prop_001",
        "property_column": "A",
        "line_1a_physical_address": "5200 Green Valley Dr., Unit 200, Sacramento, CA, 95841, US",
        "line_1b_property_type_code": 1,
        "line_2_fair_rental_days": 365,
        "line_2_personal_use_days": 0,
        "line_2_qjv_checkbox": false,
        "line_3_rents_received": 16650.0,
        "line_4_royalties_received": 0.0,
        "line_5_advertising": 0.0,
        "line_6_auto_and_travel": 0.0,
        "line_7_cleaning_and_maintenance": 0.0,
        "line_8_commissions": 0.0,
        "line_9_insurance": 900.0,
        "line_10_legal_and_professional_fees": 0.0,
        "line_11_management_fees": 0.0,
        "line_12_mortgage_interest": 4800.0,
        "line_13_other_interest": 0.0,
        "line_14_repairs": 550.0,
        "line_15_supplies": 0.0,
        "line_16_taxes": 2400.0,
        "line_17_utilities": 0.0,
        "line_18_depreciation": 8000.0,
        "line_19_other_expense_items": [],
        "line_19_other_expenses_total": 0.0,
        "line_20_total_expenses": 16650.0,
        "pre_at_risk_net_income_or_loss": 0.0,
        "line_21_income_or_loss": 0.0,
        "line_22_deductible_rental_loss": null,
        "depreciation_source_result_id": "processor_4562",
        "at_risk_source_result_id": null,
        "passive_loss_source_result_id": null,
        "blocking_errors": [],
        "review_warnings": []
      }
    ],
    "line_23a_total_rents": 16650.0,
    "line_23b_total_royalties": 0.0,
    "line_23c_total_mortgage_interest": 4800.0,
    "line_23d_total_depreciation": 8000.0,
    "line_23e_total_expenses": 16650.0,
    "line_24_income": 0.0,
    "line_25_losses": 0.0,
    "line_26_total_rental_income_or_loss": 0.0,
    "schedule_1_line_5_transfer_amount": 0.0,
    "requires_form_4562_attachment": true,
    "requires_form_6198_attachment": false,
    "requires_form_8582_attachment": false,
    "requires_form_461_review": false,
    "is_v1_supported": true,
    "can_file": true,
    "blocking_errors": [],
    "review_warnings": []
  }
}
```

