# Schedule D 資本損失結轉提取與映射 API

從上年度申報書摘要（Prior Year Tax Summary）等歷史報稅文件中，提取資本損失結轉事實，並將其自動映射至當年度的 IRS Schedule D 表單對應行號。

* **端點**：`POST /schedule-d/carryover/extract-and-map`
* **驗證方式**：必須在 Request Header 中夾帶 `X-API-Token`。

---

## 請求參數 (Request Body)

| 參數名稱 | 類型 | 必填 | 說明 |
| :--- | :--- | :--- | :--- |
| `question` | object 或 string | **是** | 納稅申報上下文內容。支援直接傳入完整結構化 JSON 物件（含 `taxpayer_profile` 與 `uploaded_documents`）。 |
| `model_name` | string | 否 | 指定使用的 LLM 模型名稱 (預設為 `"gemini-2.5-pro"`)。 |

### 請求 Payload 範例
```json
{
  "question": {
    "taxpayer_profile": {
      "Tax Year": 2024
    },
    "uploaded_documents": [
      {
        "file_name": "Sample 08 - Prior Year 1040 Summary.json",
        "content": {
          "document_type": "Prior Year Tax Return Summary",
          "tax_year": 2023,
          "income": {
            "schedule_d": {
              "capital_loss_carryforward_to_2024": -990.0
            }
          }
        }
      }
    ]
  }
}
```

---

## 回應欄位說明 (Response Structure)

| 欄位名稱 | 類型 | 說明 |
| :--- | :--- | :--- |
| `success` | boolean | 若處理成功則為 `true`。 |
| `adapter_results` | object | 由 `PriorYearReturnAdapter` 從各份歷史文件中解析出的原始事實 (Facts)。 |
| `mapper_result` | object | 由 `ScheduleDMapper` 計算後的對齊映射結果，包含 `items` (已映射) 與 `unmapped_items` (未映射項目)。 |
| `latency` | float | API 執行耗時（秒）。 |

### 回應 Payload 範例 (Response JSON Example)
```json
{
  "success": true,
  "adapter_results": {
    "Sample 08 - Prior Year 1040 Summary.json": {
      "source_filename": "Sample 08 - Prior Year 1040 Summary.json",
      "facts": [
        {
          "fact_type": "capital_loss_carryover",
          "value": -990.0,
          "needs_review": false,
          "review_reason": null
        }
      ],
      "document_needs_review": false,
      "debug_info": {
        "system_prompt": "...",
        "user_prompt": "...",
        "raw_output": "..."
      }
    }
  },
  "mapper_result": {
    "items": [
      {
        "target_form": "schedule_d",
        "target_line": "line_6",
        "value": -990.0,
        "value_type": "float",
        "source_category": "prior_year_return_facts",
        "source_fact_type": "capital_loss_carryover",
        "source_filename": "Sample 08 - Prior Year 1040 Summary.json",
        "needs_review": false,
        "review_reason": null
      }
    ],
    "unmapped_items": [
      {
        "value": -500.0,
        "value_type": "float",
        "source_category": "prior_year_return_facts",
        "source_fact_type": "net_operating_loss",
        "source_filename": "Sample 08 - Prior Year 1040 Summary.json",
        "needs_review": true,
        "review_reason": "欄位名稱模糊或模型信心不足"
      }
    ],
    "needs_review": true
  },
  "latency": 1.23
}
```

### 映射項目結構 (mapped_item)
* `target_line`：對應的 Schedule D 表單行號（例如，短期損失結轉對應 `"line_6"`，長期損失結轉對應 `"line_14"`）。
* `value`：結轉金額（損失結轉在映射中通常表示為負值）。
* `source_fact_type`：事實的原分類鍵名（如 `capital_loss_carryover`、`short_term_capital_loss_carryover`、`long_term_capital_loss_carryover`）。
* `source_category`：資料事實的分類類型（例如 `"prior_year_return_facts"`）。
* `source_filename`：來源檔案名稱。
* `needs_review`：是否需要審查。
* `review_reason`：審查原因說明。

---

## 使用範例

### cURL 指令 (推薦：以 question 傳入完整 JSON 欄位呼叫範例)
```bash
curl -X POST "http://localhost:8088/schedule-d/carryover/extract-and-map" \
     -H "Content-Type: application/json" \
     -H "X-API-Token: tax-rag-secret-token" \
     -d '{
       "question": {
         "taxpayer_profile": {
           "Tax Year": 2024
         },
         "uploaded_documents": [
           {
             "file_name": "Sample 08 - Prior Year 1040 Summary.json",
             "content": {
               "document_type": "Prior Year Tax Return Summary",
               "tax_year": 2023,
               "income": {
                 "schedule_d": {
                   "capital_loss_carryforward_to_2024": -990.0
                 }
               }
             }
           }
         ]
       }
     }'
```

---

## 最終對齊結果回傳值解讀指引

API 的映射結果封裝在回應的 `mapper_result` 物件中，前端開發與資料繫結應遵循以下結構說明與欄位對應規則。

### 1. 欄位結構定義

*   **`mapper_result.items`**：已被自動分類並映射至 Form Schedule D 對應行號的項目清單。每個項目包含以下屬性：
    *   `target_line` (string)：映射的 Schedule D 表單行號：
        *   `"line_6"`：短期資本損失結轉 (Short-term capital loss carryover)
        *   `"line_14"`：長期資本損失結轉 (Long-term capital loss carryover)
    *   `value` (float)：結轉金額。**注意：在資本損失結轉中，此數值通常為負數（例如 `-990.0`），代表可扣抵的損失。**
    *   `source_fact_type` (string)：來源事實分類鍵（例如 `capital_loss_carryover`, `short_term_capital_loss_carryover`）。
    *   `source_filename` (string)：此項目的來源憑證檔案名稱，可用於關聯原始上傳文件。
    *   `needs_review` (boolean)：標記此項目是否需要人工核對或審查。
    *   `review_reason` (string / null)：當 `needs_review` 為 `true` 時，此欄位會給出具體原因說明（例如 `"歸屬或 activity scope 不明"` 代表上年度只寫了結轉金額，但未指明是長期還是短期損失結轉，系統預設映射至 `line_6` 供會計師確認）。
*   **`mapper_result.unmapped_items`**：無法自動映射至表單行號的異常或無效項目。欄位結構與上述項目相同，但 `target_line` 通常為 `null`，且其 `needs_review` 常設為 `true`，`review_reason` 會說明無法對齊的原因。

### 2. 前端資料繫結建議
*   **金額填入**：根據 `items[].target_line` 值，將 `items[].value` 自動填入前端稅表中對應的行號輸入框。請保留負值以符合美國稅表的損失申報規則。
*   **審查標記**：檢查 `items` 與 `unmapped_items` 中所有項目的 `needs_review`。若為 `true`，則應當在該數據或表單行號旁標記異常，並將 `review_reason` 的內容作提示訊息顯示給審查人員。
*   **溯源連結**：利用 `source_filename` 提供檔案比對關聯，允許使用者隨時查看該資料點的原始上傳凭證檔案。


