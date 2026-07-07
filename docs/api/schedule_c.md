# Schedule C (自營職業利潤與虧損) API

提供從上傳的自營職業憑證（如損益表、商業收據紀錄等）中自動提取財務事實，並自動進行 Schedule C 利潤與虧損試算的 API 服務。

---

## 1. 提取並試算 API

傳入納稅人檔案與未結構化的文件內容，系統將使用 LLM 自動識別並提取 Schedule C 相關數值，隨後自動帶入 V1 確定性計算引擎完成試算。

* **端點**：`POST /schedule-c/extract-and-calculate`
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
* `state` (object)：試算最終欄位數值，包括：
  * `gross_receipts`
  * `cost_of_goods_sold`
  * `gross_profit`
  * `advertising`
  * `car_and_truck_expenses`
  * `total_expenses`
  * `net_profit_or_loss`
  * `blocking_errors` (list[object])：阻斷錯誤清單。每個錯誤物件包含以下屬性：
    * `code` (string)：錯誤代碼（例如 `UNSUPPORTED_CASE`）。
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
  * ...（其餘 Schedule C V1 欄位）
* `debug_info` (object)：除錯與日誌資訊物件。包含以下屬性：
  * `model_name` (string)：執行此次提取所使用的 LLM 模型名稱（例如 `gemini-2.5-pro`）。
  * `prompt_log` (string)：發送給 LLM 的完整提示詞（Prompt）內容，包含注入的上下文。
  * `raw_output` (string)：LLM 回傳的原始文字（JSON 格式字串）。

---

## 使用範例

### cURL 指令
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
