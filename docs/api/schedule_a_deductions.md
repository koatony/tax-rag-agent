# Schedule A 扣除額提取與映射 API

從多種財務凭證文件（捐贈收據、1098 貸款表單等）中提取事實，並將其直接映射至 IRS Schedule A 申報行號。

* **端點**：`POST /schedule-a/deductions/extract-and-map`
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
      "Name": "Marcus and Elena Rivera",
      "Filing Status": "Married Filing Jointly",
      "State": "California (Sacramento)",
      "Tax Year": 2024
    },
    "uploaded_documents": [
      {
        "file_name": "Sample 09 - Church Donation Receipt.json",
        "content": {
          "document_type": "Charitable Donation Receipt",
          "tax_year": 2024,
          "organization": "First Baptist Church of Sacramento",
          "donor": "Marcus & Elena Rivera",
          "contribution_type": "cash",
          "amount": 5400.0
        }
      },
      {
        "file_name": "Sample 03 - 1098 Mortgage Interest.json",
        "content": {
          "document_type": "Form 1098 Mortgage Interest Statement",
          "tax_year": 2024,
          "boxes": {
            "box_1_mortgage_interest_received": 9800.0,
            "box_10_property_taxes_collected_via_escrow": 2600.0
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
| `adapter_results` | object | 由 `ItemizedDeductionAdapter` 從各份文件中解析出的原始事實 (Facts)。 |
| `mapper_result` | object | 由 `ScheduleADeductionMapper` 計算後的對齊映射結果，包含 `items` (已映射) 與 `unmapped_items` (未映射項目)。 |
| `latency` | float | API 執行耗時（秒）。 |

### 回應 Payload 範例 (Response JSON Example)
```json
{
  "success": true,
  "adapter_results": {
    "Sample 09 - Church Donation Receipt.json": {
      "source_filename": "Sample 09 - Church Donation Receipt.json",
      "facts": [
        {
          "fact_type": "charitable_cash_contribution",
          "value": 5400.0,
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
    },
    "Sample 03 - 1098 Mortgage Interest.json": {
      "source_filename": "Sample 03 - 1098 Mortgage Interest.json",
      "facts": [
        {
          "fact_type": "mortgage_interest",
          "value": 9800.0,
          "needs_review": false,
          "review_reason": null
        },
        {
          "fact_type": "real_estate_taxes",
          "value": 2600.0,
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
        "target_form": "schedule_a",
        "target_line": "line_11",
        "value": 5400.0,
        "value_type": "float",
        "source_category": "itemized_deduction_facts",
        "source_fact_type": "charitable_cash_contribution",
        "source_filename": "Sample 09 - Church Donation Receipt.json",
        "needs_review": false,
        "review_reason": null
      },
      {
        "target_form": "schedule_a",
        "target_line": "line_8a",
        "value": 9800.0,
        "value_type": "float",
        "source_category": "itemized_deduction_facts",
        "source_fact_type": "mortgage_interest",
        "source_filename": "Sample 03 - 1098 Mortgage Interest.json",
        "needs_review": false,
        "review_reason": null
      },
      {
        "target_form": "schedule_a",
        "target_line": "line_5b",
        "value": 2600.0,
        "value_type": "float",
        "source_category": "itemized_deduction_facts",
        "source_fact_type": "real_estate_taxes",
        "source_filename": "Sample 03 - 1098 Mortgage Interest.json",
        "needs_review": false,
        "review_reason": null
      }
    ],
    "unmapped_items": [
      {
        "value": 250.0,
        "value_type": "float",
        "source_category": "itemized_deduction_facts",
        "source_fact_type": "political_contribution",
        "source_filename": "Sample 10 - Political Contribution Receipt.json",
        "needs_review": false,
        "review_reason": "political_contribution_non_deductible"
      }
    ],
    "needs_review": false
  },
  "latency": 2.45
}
```

### 映射項目結構 (mapped_item)
* `target_line`：對應的 Schedule A 表單行號（例如，依據事實動態對應至 `line_1` 到 `line_17` 的標準行號。常見對應例如：`"line_5b"` 不動產稅、`"line_8a"` 房貸利息、`"line_11"` 現金慈善捐贈 等）。
* `value`：提取出的浮點數金額。
* `source_fact_type`：事實的原分類鍵名。
* `source_category`：來源類型。
* `source_filename`：檔案名稱。
* `needs_review`：是否需要人工審查。
* `review_reason`：審查原因說明。

---

## 使用範例

### cURL 指令 (推薦：以 question 傳入完整 JSON 欄位呼叫範例)
```bash
curl -X POST "http://localhost:8088/schedule-a/deductions/extract-and-map" \
     -H "Content-Type: application/json" \
     -H "X-API-Token: tax-rag-secret-token" \
     -d '{
       "question": {
         "taxpayer_profile": {
           "Name": "Marcus and Elena Rivera",
           "Filing Status": "Married Filing Jointly",
           "State": "California (Sacramento)",
           "Tax Year": 2024
         },
         "uploaded_documents": [
           {
             "file_name": "Sample 09 - Church Donation Receipt.json",
             "content": {
               "document_type": "Charitable Donation Receipt",
               "tax_year": 2024,
               "organization": "First Baptist Church of Sacramento",
               "donor": "Marcus & Elena Rivera",
               "contribution_type": "cash",
               "amount": 5400.0
             }
           },
           {
             "file_name": "Sample 03 - 1098 Mortgage Interest.json",
             "content": {
               "document_type": "Form 1098 Mortgage Interest Statement",
               "tax_year": 2024,
               "boxes": {
                 "box_1_mortgage_interest_received": 9800.0,
                 "box_10_property_taxes_collected_via_escrow": 2600.0
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

*   **`mapper_result.items`**：已被自動分類並映射至 Form Schedule A 對應行號的項目清單。每個項目包含以下屬性：
    *   `target_line` (string)：映射的 Schedule A 表單行號（例如，依據事實動態對應至 `line_1` 到 `line_17` 的標準行號。常見對應例如：`"line_5b"` 不動產稅、`"line_8a"` 房貸利息、`"line_11"` 現金慈善捐贈 等）。
    *   `value` (float)：提取出的申報金額。
    *   `source_fact_type` (string)：來源事實分類鍵（例如 `cash_contributions`, `mortgage_interest`）。
    *   `source_filename` (string)：此項目的來源憑證檔案名稱，可用於關聯原始上傳文件。
    *   `needs_review` (boolean)：標記此項目是否需要人工核對或審查。
    *   `review_reason` (string / null)：當 `needs_review` 為 `true` 時，此欄位會給出具體原因說明（例如 `"金額衝突"` 或 `"歸屬或 activity scope 不明"`）。
*   **`mapper_result.unmapped_items`**：無法自動映射至表單行號的異常或潛在扣除額項目。欄位結構與上述項目相同，但 `target_line` 通常為 `null`，且其 `needs_review` 常設為 `true`，`review_reason` 會說明無法映射的原因（例如非可扣除項目的政治捐款）。

### 2. 前端資料繫結建議
*   **金額填入**：根據 `items[].target_line` 值，將 `items[].value` 自動填入前端稅表中對應的行號輸入框。
*   **審查標記**：檢查 `items` 與 `unmapped_items` 中所有項目的 `needs_review`。若為 `true`，則應當在該數據或表單行號旁標記異常，並將 `review_reason` 的內容作提示訊息顯示給審查人員。
*   **溯源連結**：利用 `source_filename` 提供檔案比對關聯，允許使用者隨時查看該資料點的原始上傳凭證檔案。


