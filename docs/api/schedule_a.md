# Schedule A (逐項扣除額) API

提供從上傳的憑證（如 Form 1098、醫療收據、慈善捐贈證明等）中自動提取財務事實，並結合納稅人檔案進行 Schedule A 逐項扣除額試算的 API 服務。

---

## 1. 提取並試算 API

傳入納稅人檔案與未結構化的文件內容，系統將使用 LLM 自動識別並提取 Schedule A 相關數值，隨後自動帶入 V1 確定性計算引擎完成試算。

* **端點**：`POST /schedule-a/extract-and-calculate`
* **驗證方式**：必須在 Request Header 中夾帶 `X-API-Token`。

### 請求參數 (Request Body)

| 參數名稱 | 類型 | 必填 | 說明 |
| :--- | :--- | :--- | :--- |
| `taxpayer_profile` | object | **是** | 納稅人一般資訊（如 AGI 調整後總收入，這是計算醫療扣除限額的關鍵）。 |
| `uploaded_documents` | list[object] | **是** | 已上傳的文件列表。每個物件包含 `file_name` (檔名) 與 `content` (文字內容)。 |
| `model_name` | string | 否 | 指定使用的 LLM 模型名稱 (預設為 `"gemini-2.5-pro"`)。 |

#### 請求 Payload 範例
```json
{
  "taxpayer_profile": {
    "name": "Marcus and Elena Rivera",
    "taxpayer_ssn": "555-12-3456",
    "tax_year": 2025,
    "filing_status": "MFJ",
    "adjusted_gross_income": 140185.0
  },
  "uploaded_documents": [
    {
      "file_name": "Sample Donation.json",
      "content": "Charitable Donation Receipt: Donor Marcus & Elena Rivera. Amount: $5,400.0 to First Baptist Church."
    },
    {
      "file_name": "Sample Mortgage.json",
      "content": "Form 1098 Mortgage Interest Statement: Mortgage interest received: $9,800.0. Property taxes: $2,600.0."
    }
  ]
}
```

### 回應欄位 (Response Body)

* `success` (boolean)：`true`。
* `state` (object)：試算最終欄位數值，其結構完全對齊最新 V1 計算結果：
  * `taxpayer_name` (string)
  * `taxpayer_ssn_masked` (string)
  * `tax_year` (int)
  * `filing_status` (string)
  * `line_1_medical_and_dental_expenses` (float)
  * `line_2_agi` (float)
  * `line_3_medical_threshold` (float)
  * `line_4_deductible_medical_expenses` (float)
  * `line_5a_amount` (float)
  * `line_5a_sales_tax_checkbox` (boolean)
  * `line_5b_real_estate_taxes` (float)
  * `line_5c_personal_property_taxes` (float)
  * `line_5d_salt_before_limit` (float)
  * `line_5e_salt_deduction` (float)
  * `line_6_other_taxes` (float)
  * `line_7_total_taxes` (float)
  * `line_8a_home_mortgage_interest` (float)
  * `line_8b_non_1098_interest` (float)
  * `line_8c_non_1098_points` (float)
  * `line_8e_total_mortgage_interest` (float)
  * `line_9_investment_interest` (float)
  * `line_10_total_interest_paid` (float)
  * `line_11_cash_contributions` (float)
  * `line_12_noncash_contributions` (float)
  * `line_13_charity_carryover` (float)
  * `line_14_total_charity` (float)
  * `line_15_casualty_theft_loss` (float)
  * `line_16_other_itemized_deductions` (float)
  * `line_17_total_itemized_deductions` (float)
  * `standard_deduction_amount` (float)：加計額外扣除額後的總標準扣除額。
  * `is_itemizing` (boolean)：是否採用列舉扣除。
  * `is_v1_supported` (boolean)：是否在 V1 支援範圍內。
  * `should_attach_schedule_a` (boolean)：是否應附加 Schedule A。
  * `can_file` (boolean)：是否符合電子申報條件。
  * `blocking_errors` (list[object])：阻斷錯誤清單。每個錯誤物件包含以下屬性：
    * `code` (string)：錯誤代碼（例如 `UNSUPPORTED_MULTIPLE_MORTGAGES`）。
    * `field` (string | null)：關聯的欄位名稱。
    * `item_id` (string | null)：關聯的明細項目 ID。
    * `source_document_id` (string | null)：關聯的來源憑證/檔案名稱。
    * `message` (string)：詳細的中文錯誤說明。
  * `review_warnings` (list[object])：警告與人工審核清單。每個警告物件包含以下屬性：
    * `code` (string)：警告代碼（例如 `MISSING_250_ACKNOWLEDGMENT`）。
    * `field` (string | null)：關聯的欄位名稱。
    * `item_id` (string | null)：關聯的明細項目 ID。
    * `source_document_id` (string | null)：關聯的來源憑證/檔案名稱。
    * `message` (string)：詳細的中文警告說明。
* `debug_info` (object)：除錯與日誌資訊物件。包含以下屬性：
  * `model_name` (string)：執行此次提取所使用的 LLM 模型名稱（例如 `gemini-2.5-pro`）。
  * `prompt_log` (string)：發送給 LLM 的完整提示詞（Prompt）內容，包含注入的上下文。
  * `raw_output` (string)：LLM 回傳的原始文字（JSON 格式字串）。

---

## 使用範例

### cURL 指令
```bash
curl -X POST "http://localhost:8088/schedule-a/extract-and-calculate" \
     -H "Content-Type: application/json" \
     -H "X-API-Token: tax-rag-secret-token" \
     -d '{
       "taxpayer_profile": {
         "name": "Marcus and Elena Rivera",
         "taxpayer_ssn": "555-12-3456",
         "tax_year": 2025,
         "filing_status": "MFJ",
         "adjusted_gross_income": 140185.0
       },
       "uploaded_documents": [
         {
           "file_name": "donation.txt",
           "content": "Gave 5400 dollars to First Baptist Church."
         }
       ]
     }'
```
