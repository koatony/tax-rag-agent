# Form 1040 Wages 薪資提取與彙整 API

從多張 W-2 薪資扣繳憑單文件中提取薪資事實，並自動彙整計算出當年度 Form 1040 表單 Line 1a（薪資、小費及其他補償總額）的最終數值。

* **端點**：`POST /form-1040/wages/extract-and-map`
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
        "file_name": "Sample 01 - Marcus Rivera W-2 Data.json",
        "content": {
          "document_type": "W-2 Wage and Tax Statement",
          "tax_year": 2024,
          "employee": {
            "name": "Marcus Rivera"
          },
          "boxes": {
            "box_1_wages_tips_other_compensation": 46000.0
          }
        }
      },
      {
        "file_name": "Sample 02 - Elena Rivera W-2 Data.json",
        "content": {
          "document_type": "W-2 Wage and Tax Statement",
          "tax_year": 2024,
          "employee": {
            "name": "Elena Rivera"
          },
          "boxes": {
            "box_1_wages_tips_other_compensation": 54000.0
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
| `adapter_results` | object | 由 `W2Adapter` 解析出的原始事實 (Facts)。 |
| `mapper_result` | object | 由 `Form1040WagesMapper` 計算後的對齊映射結果。 |
| `line_1a_result` | object | 經由 `aggregate_form_1040_line_1a` 彙整後的 Line 1a 計算總額及相關審查細節。 |
| `latency` | float | API 執行耗時（秒）。 |

### 回應 Payload 範例 (Response JSON Example)
```json
{
  "success": true,
  "adapter_results": {
    "Sample 01 - Marcus Rivera W-2 Data.json": {
      "source_filename": "Sample 01 - Marcus Rivera W-2 Data.json",
      "facts": [
        {
          "fact_type": "wages_tips_compensation",
          "value": 46000.0,
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
    "Sample 02 - Elena Rivera W-2 Data.json": {
      "source_filename": "Sample 02 - Elena Rivera W-2 Data.json",
      "facts": [
        {
          "fact_type": "wages_tips_compensation",
          "value": 54000.0,
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
        "target_form": "form_1040",
        "target_line": "line_1a",
        "value": 46000.0,
        "value_type": "float",
        "source_category": "w2_facts",
        "source_fact_type": "wages_tips_compensation",
        "source_filename": "Sample 01 - Marcus Rivera W-2 Data.json",
        "needs_review": false,
        "review_reason": null
      },
      {
        "target_form": "form_1040",
        "target_line": "line_1a",
        "value": 54000.0,
        "value_type": "float",
        "source_category": "w2_facts",
        "source_fact_type": "wages_tips_compensation",
        "source_filename": "Sample 02 - Elena Rivera W-2 Data.json",
        "needs_review": false,
        "review_reason": null
      }
    ],
    "unmapped_items": [
      {
        "value": 12000.0,
        "value_type": "float",
        "source_category": "w2_facts",
        "source_fact_type": "nonemployee_compensation",
        "source_filename": "Sample 04 - Marcus Rivera 1099-NEC.json",
        "needs_review": true,
        "review_reason": "欄位名稱模糊或模型信心不足"
      }
    ],
    "needs_review": true
  },
  "line_1a_result": {
    "total_value": 100000.0,
    "items": [
      {
        "target_form": "form_1040",
        "target_line": "line_1a",
        "value": 46000.0,
        "value_type": "float",
        "source_category": "w2_facts",
        "source_fact_type": "wages_tips_compensation",
        "source_filename": "Sample 01 - Marcus Rivera W-2 Data.json",
        "needs_review": false,
        "review_reason": null
      },
      {
        "target_form": "form_1040",
        "target_line": "line_1a",
        "value": 54000.0,
        "value_type": "float",
        "source_category": "w2_facts",
        "source_fact_type": "wages_tips_compensation",
        "source_filename": "Sample 02 - Elena Rivera W-2 Data.json",
        "needs_review": false,
        "review_reason": null
      }
    ],
    "review_needed": false,
    "review_reasons": []
  },
  "latency": 2.12
}
```

### Line 1a 彙整結果結構 (line_1a_result)
* `total_value`：所有 W-2 薪資總額的加總（浮點數，例如 `100000.0`）。
* `items`：貢獻此總額之已映射項目清單。
* `review_needed`：是否需要審查。
* `review_reasons`：審查原因的說明列表。

---

## 使用範例

### cURL 指令 (推薦：以 question 傳入完整 JSON 欄位呼叫範例)
```bash
curl -X POST "http://localhost:8088/form-1040/wages/extract-and-map" \
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
             "file_name": "Sample 01 - Marcus Rivera W-2 Data.json",
             "content": {
               "document_type": "W-2 Wage and Tax Statement",
               "tax_year": 2024,
               "employee": {
                 "name": "Marcus Rivera"
               },
               "boxes": {
                 "box_1_wages_tips_other_compensation": 46000.0
               }
             }
           },
           {
             "file_name": "Sample 02 - Elena Rivera W-2 Data.json",
             "content": {
               "document_type": "W-2 Wage and Tax Statement",
               "tax_year": 2024,
               "employee": {
                 "name": "Elena Rivera"
               },
               "boxes": {
                 "box_1_wages_tips_other_compensation": 54000.0
               }
             }
           }
         ]
       }
     }'
```

---

## 最終對齊與彙整結果回傳值解讀指引

API 最終產出的加總結果封裝在回應的 `line_1a_result` 物件中，前端開發與資料繫結應遵循以下結構說明與欄位對應規則。

### 1. 欄位結構定義

*   **`line_1a_result.total_value`** (float)：已通過年度與文件類型校驗的各張 W-2 薪資 (Box 1) 的加總最終金額。此值可以直接填入 Form 1040 表單中 **Line 1a (Wages, salaries, tips, etc.)** 的主要數據欄位。
*   **`line_1a_result.items`**：貢獻此 `total_value` 的 W-2 明細項目清單。每個項目包含以下屬性：
    *   `value` (float)：該 W-2 檔案中 Box 1 的薪資數值。
    *   `employee_name` (string)：W-2 中對應的雇員姓名，可用於區分申報人與配偶的薪資來源。
    *   `source_filename` (string)：此明細來源憑證的檔案名稱，供前端進行文件關聯。
*   **`line_1a_result.review_needed`** (boolean)：標記整個 Line 1a 彙整或單一 W-2 是否存在異常，需要會計師人工審核。
*   **`line_1a_result.review_reasons`** (list[string])：當 `review_needed` 為 `true` 時，條列說明所有異常的具體原因。例如：
    *   `"W-2 稅務年度 (2023) 與申報年度 (2024) 不符"`：代表此 W-2 因年度不合已**被自動排除**，未併入 `total_value` 加總。
    *   `"W-2 box 1 金額缺失"`：表示解析該檔案時，未能成功取得 Box 1 薪資值。

### 2. 前端資料繫結建議
*   **金額填入**：將 `line_1a_result.total_value` 自動對齊填入 Form 1040 Line 1a 輸入框。
*   **明細關聯**：前端可基於 `line_1a_result.items` 列表渲染出 W-2 薪資明細表格，並使用 `source_filename` 關聯原始檔案以利追溯。
*   **異常與排除標記**：檢查 `review_needed` 狀態與 `review_reasons` 清單。凡是出現在 `review_reasons` 中指出年度不符的來源檔案，前端應將其標記為無效/排除，並將錯誤原因展示給審核人員。


