# Schedule E 租賃收入與支出提取與映射 API

從租賃房產收支明細單（Rental Property Statement）、房東收支紀錄文件中提取租賃財務指標（毛租金收入與各類營運現金支出），並將其自動映射至 IRS Schedule E 表單對應行號。

* **端點**：`POST /schedule-e/rental/extract-and-map`
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
      "Tax Year": 2024
    },
    "uploaded_documents": [
      {
        "file_name": "Sample 05 - Rental Property Income.json",
        "content": {
          "document_type": "Rental Property Income Statement",
          "tax_year": 2024,
          "taxpayer": {
            "name": "Marcus & Elena Rivera"
          },
          "rental_income": {
            "total_rental_income": 16650,
            "line_items": [
              {
                "account": "Monthly Rent Income",
                "amount": 16200
              }
            ]
          },
          "operating_expenses": {
            "total_cash_expenses": 8650,
            "subgroups": [
              {
                "subgroup": "Financing",
                "line_items": [
                  {
                    "account": "Mortgage Interest",
                    "amount": 4800
                  }
                ]
              }
            ]
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
| `adapter_results` | object | 由 `RentalIncomeAndExpenseAdapter` 解析出的原始事實 (Facts)。 |
| `mapper_result` | object | 由 `ScheduleEMapper` 計算後的對齊映射結果。 |
| `latency` | float | API 執行耗時（秒）。 |

### 回應 Payload 範例 (Response JSON Example)
```json
{
  "success": true,
  "adapter_results": {
    "Sample 05 - Rental Property Income.json": {
      "source_filename": "Sample 05 - Rental Property Income.json",
      "facts": [
        {
          "fact_type": "gross_rents",
          "value": 16200.0,
          "needs_review": false,
          "review_reason": null
        },
        {
          "fact_type": "mortgage_interest",
          "value": 4800.0,
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
        "target_form": "schedule_e",
        "target_line": "line_3",
        "value": 16200.0,
        "value_type": "float",
        "source_category": "rental_facts",
        "source_fact_type": "gross_rents",
        "source_filename": "Sample 05 - Rental Property Income.json",
        "needs_review": false,
        "review_reason": null
      },
      {
        "target_form": "schedule_e",
        "target_line": "line_12",
        "value": 4800.0,
        "value_type": "float",
        "source_category": "rental_facts",
        "source_fact_type": "mortgage_interest",
        "source_filename": "Sample 05 - Rental Property Income.json",
        "needs_review": false,
        "review_reason": null
      }
    ],
    "unmapped_items": [
      {
        "value": 1500.0,
        "value_type": "float",
        "source_category": "rental_facts",
        "source_fact_type": "capital_improvement",
        "source_filename": "Sample 05 - Rental Property Income.json",
        "needs_review": true,
        "review_reason": "歸屬 or activity scope 不明"
      }
    ],
    "needs_review": true
  },
  "latency": 1.78
}
```

### 映射項目結構 (mapped_item)
* `target_line`：對應的 Schedule E 表單行號（例如，毛租金收入對應 `"line_3"`、房貸利息支出對應 `"line_12"`、房產稅支出對應 `"line_16"`）。
* `value`：提取出的浮點數金額。
* `source_fact_type`：事實的原分類鍵名。
* `source_category`：資料事實的分類類型（例如 `"rental_facts"`）。
* `source_filename`：檔案名稱。
* `needs_review`：是否需要審查。
* `review_reason`：審查原因說明。

---

## 使用範例

### cURL 指令 (推薦：以 question 傳入完整 JSON 欄位呼叫範例)
```bash
curl -X POST "http://localhost:8088/schedule-e/rental/extract-and-map" \
     -H "Content-Type: application/json" \
     -H "X-API-Token: tax-rag-secret-token" \
     -d '{
       "question": {
         "taxpayer_profile": {
           "Name": "Marcus and Elena Rivera",
           "Tax Year": 2024
         },
         "uploaded_documents": [
           {
             "file_name": "Sample 05 - Rental Property Income.json",
             "content": {
               "document_type": "Rental Property Income Statement",
               "tax_year": 2024,
               "taxpayer": {
                 "name": "Marcus & Elena Rivera"
               },
               "rental_income": {
                 "total_rental_income": 16650,
                 "line_items": [
                   {
                     "account": "Monthly Rent Income",
                     "amount": 16200
                   }
                 ]
               },
               "operating_expenses": {
                 "total_cash_expenses": 8650,
                 "subgroups": [
                   {
                     "subgroup": "Financing",
                     "line_items": [
                       {
                         "account": "Mortgage Interest",
                         "amount": 4800
                       }
                     ]
                   }
                 ]
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

*   **`mapper_result.items`**：已被自動分類並映射至 Form Schedule E 對應行號的項目清單。每個項目包含以下屬性：
    *   `target_line` (string) ：映射的 Schedule E 表單行號：
        *   `"line_3"`：毛租金收入總額 (Rents received) — **注意：依 LLM 映射判定，此金額可能對齊至每月租金 `16200.0` 或租金加總 `16650.0`，兩者皆為合理的報稅表示。**
        *   `"line_12"`：支付給銀行的房貸利息 (Mortgage interest paid to banks)
        *   `"line_16"`：房產稅支出 (Taxes)
    *   `value` (float)：提取出的申報金額。
    *   `source_fact_type` (string)：來源事實分類鍵（例如 `rental_income`, `mortgage_interest`）。
    *   `source_filename` (string)：此項目的來源憑證檔案名稱，可用於關聯原始上傳文件。
    *   `needs_review` (boolean)：標記此項目是否需要人工核對或審查。
    *   `review_reason` (string / null)：當 `needs_review` 為 `true` 時，此欄位會給出具體原因說明。
*   **`mapper_result.unmapped_items`**：無法自動映射至表單行號的的租賃異常或潛在收支項目。欄位結構與上述項目相同，但 `target_line` 通常為 `null`，且其 `needs_review` 常設為 `true`，`review_reason` 會說明無法對齊的原因。

### 2. 前端資料繫結建議
*   **金額填入**：根據 `items[].target_line` 值，將 `items[].value` 自動填入前端稅表中對應的行號輸入框。
*   **審查標記**：檢查 `items` 與 `unmapped_items` 中所有項目的 `needs_review`。若為 `true`，則應當在該數據或表單行號旁標記異常，並將 `review_reason` 的內容作提示訊息顯示給審查人員。
*   **溯源連結**：利用 `source_filename` 提供檔案比對關聯，允許使用者隨時查看該資料點的原始上傳凭證檔案。


