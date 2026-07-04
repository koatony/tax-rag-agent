# Schedule A (逐項扣除額) APIs

提供申報個人所得稅之 Schedule A 表單各項扣除額計算功能。支援直接帶入數值計算，以及文件內容 facts 提取後計算。

---

## 1. 直接試算 API

接收已整理的各項支出扣除數值，利用後端確定性公式規則計算出 Schedule A 的最終申報總額及各分類扣除額（如醫療限額比例）。

* **端點**：`POST /schedule-a/calculate`
* **驗證方式**：必須在 Request Header 中夾帶 `X-API-Token`。

### 請求參數 (Request Body)
* `inputs` (object, 必填)：包含 Schedule A 行號對應數值的鍵值對字典（例如 `"medical_expenses"`、`"agi"`、`"real_estate_taxes"`、`"state_income_taxes"`、`"mortgage_interest"`、`"gifts_to_charity"` 等）。

#### 請求 Payload 範例
```json
{
  "inputs": {
    "medical_expenses": 12000.0,
    "agi": 80000.0,
    "real_estate_taxes": 4500.0,
    "state_income_taxes": 3500.0,
    "mortgage_interest": 9800.0,
    "gifts_to_charity": 5400.0
  }
}
```

### 回應欄位 (Response Body)
* `success` (boolean)：若計算成功則為 `true`。
* `state` (object)：計算結果狀態（例如 `"allowable_medical"`、`"limited_taxes"`、`"total_itemized_deductions"` 等）。

---

## 2. 提取並試算 API

傳入納稅人檔案與未結構化的文件內容，系統將使用 LLM 自動識別並提取 Schedule A 相關數值（如捐贈收據、房貸表單），隨後自動帶入公式完成試算。

* **端點**：`POST /schedule-a/extract-and-calculate`
* **驗證方式**：必須在 Request Header 中夾帶 `X-API-Token`。

### 請求參數 (Request Body)
* `taxpayer_profile` (object, 必填)：納稅人一般資訊（如 AGI 調整後總收入，這是計算醫療扣除限額的關鍵）。
* `uploaded_documents` (list[object], 必填)：已上傳的文件，包含 `file_name` 與 `content` (文字內容)。
* `model_name` (string, 選填)：指定使用的 LLM 模型名稱 (預設為 `"gemini-2.5-pro"`)。

#### 請求 Payload 範例
```json
{
  "taxpayer_profile": {
    "name": "Marcus and Elena Rivera",
    "agi": 140185.0
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
* `state` (object)：試算最終欄位數值。
* `debug_info` (object)：包含 LLM 提示詞日誌 `prompt_log` 與原始輸出 `raw_output`。

---

## 使用範例

### cURL 指令 (提取並試算)
```bash
curl -X POST "http://localhost:8088/schedule-a/extract-and-calculate" \
     -H "Content-Type: application/json" \
     -H "X-API-Token: tax-rag-secret-token" \
     -d '{
       "taxpayer_profile": {"agi": 140185.0},
       "uploaded_documents": [
         {
           "file_name": "donation.txt",
           "content": "Gave 5400 dollars to First Baptist Church."
         }
       ]
     }'
```
