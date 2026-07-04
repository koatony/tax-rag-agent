# Schedule C (自營職業利潤與虧損) APIs

提供申報自營職業（Sole Proprietorship）之 Schedule C 表單淨利與虧損計算功能。支援直接帶入數值計算，以及文件內容 facts 提取後計算。

---

## 1. 直接試算 API

接收已整理的業務收支數值，利用後端確定性公式規則計算出 Schedule C 各欄位的最終申報金額。

* **端點**：`POST /schedule-c/calculate`
* **驗證方式**：必須在 Request Header 中夾帶 `X-API-Token`。

### 請求參數 (Request Body)
* `inputs` (object, 必填)：包含 Schedule C 行號對應數值的鍵值對字典（例如 `"gross_receipts"`、`"cost_of_goods_sold"`、`"advertising"`、`"car_and_truck_expenses"`、`"depreciation_allowable"` 等）。

#### 請求 Payload 範例
```json
{
  "inputs": {
    "gross_receipts": 150000.0,
    "cost_of_goods_sold": 45000.0,
    "advertising": 3000.0,
    "car_and_truck_expenses": 2500.0,
    "depreciation_allowable": 5000.0
  }
}
```

### 回應欄位 (Response Body)
* `success` (boolean)：若計算成功則為 `true`。
* `state` (object)：計算結果狀態（例如 `"gross_income"`、`"total_expenses"`、`"net_profit_or_loss"` 等）。

---

## 2. 提取並試算 API

傳入納稅人檔案與未結構化的文件內容，系統將使用 LLM 自動識別並提取 Schedule C 相關數值，隨後自動帶入公式完成試算。

* **端點**：`POST /schedule-c/extract-and-calculate`
* **驗證方式**：必須在 Request Header 中夾帶 `X-API-Token`。

### 請求參數 (Request Body)
* `taxpayer_profile` (object, 必填)：納稅人一般資訊與配置。
* `uploaded_documents` (list[object], 必填)：已上傳的文件，包含 `file_name` 與 `content` (文字內容)。
* `model_name` (string, 選填)：指定使用的 LLM 模型名稱 (預設為 `"gemini-2.5-pro"`)。

#### 請求 Payload 範例
```json
{
  "taxpayer_profile": {
    "name": "John Doe",
    "tax_year": 2024
  },
  "uploaded_documents": [
    {
      "file_name": "Sample Business Summary.json",
      "content": "Gross receipts: $182,500. COGS: $63,200. General business advertising expenses: $5,000."
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
curl -X POST "http://localhost:8088/schedule-c/extract-and-calculate" \
     -H "Content-Type: application/json" \
     -H "X-API-Token: tax-rag-secret-token" \
     -d '{
       "taxpayer_profile": {"name": "John Doe"},
       "uploaded_documents": [
         {
           "file_name": "summary.txt",
           "content": "Gross receipts are 150000 dollars, and we spent 3000 on ads."
         }
       ]
     }'
```
