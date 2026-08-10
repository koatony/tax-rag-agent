# 表單狀態分析器 (Form Status Analyzer) API 說明文件

此文件說明 **表單狀態分析器 (Form Status Analyzer)** 的 API 介面與資料結構。

---

## POST `/flag/form-status`

評估納稅人今年需要申報哪些表單，以及各表單目前的資料完整度狀態。

### 認證方式
在 Request Header 中夾帶 `X-API-Token`。
- `X-API-Token`: `tax_rag_p9k2_Lz7v_Xm4q_Secure_9103` (依實際部署環境配置)

### Request Body 格式

| 參數 | 類型 | 必填 | 預設值 | 說明 |
|---|---|---|---|---|
| `question` | object \| string | ✅ | - | 納稅人資料物件 (JSON) 或其 JSON 字串。結構需包含 `taxpayer_profile` 與 `uploaded_documents`。 |
| `model_name` | string | ❌ | `gemini-2.5-pro` | 指定採用的 LLM 模型。可選：`gemini-2.5-flash`、`gemini-2.5-pro`、`gemma4:31b` |
| `use_kg` | boolean | ❌ | `false` | 是否啟用 Neo4j 稅務知識庫增強檢索。 |
| `think` | boolean | ❌ | `false` | 是否啟用推理思維 (僅適用於 Gemma 模型)。 |
| `source_filename` | string | ❌ | `"upload.json"` | 來源檔案名稱。 |

#### `question` 物件內部結構
- `client`: string (客戶名稱，可選)
- `tax_year`: integer (稅務年度，可選)
- `uploaded_documents`: list[object] (上傳憑證列表)
  - `file_name`: string (檔案名稱)
  - `content`: string \| dict (檔案文字內容或結構化資訊)

---

### Response Body 格式

| 欄位名 | 類型 | 說明 |
|---|---|---|
| `success` | boolean | API 執行狀態標記 (`true`/`false`) |
| `latency` | float | 後端分析耗時 (秒) |
| `forms` | list[object] | 所有需要評估的表單狀態清單 |
| `_errors` | list[string] | 部分項目分析失敗的錯誤訊息 (可選) |

#### `forms` 列表內物件欄位說明

| 欄位名 | 類型 | 說明 |
|---|---|---|
| `form_name` | string | 表單名稱。支援以下 6 種：<br>`Schedule A` / `Schedule B` / `Schedule C` / `Schedule E` / `Schedule 1` / `Form 4562` |
| `status` | string | 表單完整度狀態，為以下三者之一：<br>1. `attached`: 用戶已直接上傳此表單的填寫結果。<br>2. `incomplete`: 表單需要填寫，但上傳的憑證有資料缺口，無法完成。<br>3. `completable`: 表單需要填寫，且現有憑證資料完整，可以進行計算。 |
| `reason` | string | 判定為此狀態的分析原因與依據。 |
| `missing_details` | list[string] | 若狀態為 `incomplete`，此欄位會列出缺少的具體欄位、數據或文件細項。若為其他狀態則為空陣列 `[]`。 |
| `actions` | object | 後續操作的連結物件。當狀態為 `completable` 時，後端會自動注入此欄位，例如：<br>`"calculate": { "url": "/schedule-c/extract-and-calculate", "method": "POST" }` |

---

## Case 0622 測試範例 (Rivera 2024 完整資料組)

### cURL 請求範例

```bash
curl -X POST http://localhost:8088/flag/form-status \
  -H "Content-Type: application/json" \
  -H "X-API-Token: tax_rag_p9k2_Lz7v_Xm4q_Secure_9103" \
  -d '{
    "question": {
      "client": "Marcus and Elena Rivera",
      "tax_year": 2024,
      "uploaded_documents": [
        {
          "file_name": "Sample 01 - W-2 Marcus.txt",
          "content": "Form W-2 Wage and Tax Statement 2024. Employer: Creature Comforts Pet Supply. Employee: Marcus Rivera. Box 1 Wages, tips: $46,000. Box 13 Retirement Plan checked."
        },
        {
          "file_name": "Sample 02 - W-2 Elena.txt",
          "content": "Form W-2 Wage and Tax Statement 2024. Employer: City of Sacramento. Employee: Elena Rivera. Box 1 Wages, tips: $54,000. Box 13 Retirement Plan checked."
        },
        {
          "file_name": "Sample 02 - Rivera Meals & Entertainment Statement.json",
          "content": {
            "document_type": "Meals & Entertainment Expense Statement",
            "category": "Schedule C",
            "total_amount": 1800.0,
            "breakdown": [
              {"item": "Season tickets", "amount": 700.0},
              {"item": "Business travel meals", "amount": 550.0},
              {"item": "Employee holiday party", "amount": 400.0},
              {"item": "Overtime meals", "amount": 150.0}
            ],
            "note": "mixed bundle, receipts available"
          }
        },
        {
          "file_name": "Sample 03 - Rivera Las Vegas Conference Trip Receipt.json",
          "content": {
            "document_type": "Travel Expense Receipt",
            "category": "Schedule C",
            "description": "Las Vegas conference trip",
            "amount": 3200.0,
            "note": "2 business days (conference) + 3 personal days (sightseeing)"
          }
        },
        {
          "file_name": "Sample 04 - Rivera City Fine Notice.json",
          "content": {
            "document_type": "Government Fine Notice",
            "category": "Schedule C",
            "description": "City fine",
            "amount": 300.0,
            "note": "fine paid to government agency"
          }
        },
        {
          "file_name": "Sample 05 - Rivera Political Contribution Receipt.json",
          "content": {
            "document_type": "Contribution Receipt",
            "category": "Schedule A",
            "description": "Political contribution",
            "amount": 250.0,
            "note": "political donation, not charitable"
          }
        },
        {
          "file_name": "Sample 06 - Rivera Church Donation Acknowledgment.json",
          "content": {
            "document_type": "Charitable Contribution Acknowledgment",
            "category": "Schedule A",
            "description": "Church donation",
            "amount": 5400.0,
            "note": "written acknowledgment available"
          }
        },
        {
          "file_name": "Sample 07 - Rivera Schedule E Rental Property Summary.json",
          "content": {
            "document_type": "Rental Property Summary",
            "category": "Schedule E",
            "description": "Rental property - no depreciation schedule",
            "amount": 0.0,
            "note": "no depreciation claimed in prior year or current year"
          }
        }
      ]
    },
    "model_name": "gemini-2.5-pro",
    "use_kg": false
  }'
```

### 預期 Response JSON 範例

```json
{
  "forms": [
    {
      "form_name": "Schedule C",
      "status": "incomplete",
      "reason": "Business expenses are provided (meals, travel, fines), but taxpayer has not uploaded gross self-employment business income (such as Form 1099-NEC).",
      "missing_details": [
        "Form 1099-NEC Nonemployee Compensation"
      ],
      "actions": {}
    },
    {
      "form_name": "Schedule A",
      "status": "completable",
      "reason": "Church donation acknowledgment is available for the large charitable deduction; political contribution is noted as non-deductible but information is sufficient to fill Schedule A.",
      "missing_details": [],
      "actions": {
        "calculate": {
          "url": "/schedule-a/extract-and-calculate",
          "method": "POST"
        }
      }
    },
    {
      "form_name": "Schedule E",
      "status": "incomplete",
      "reason": "Rental property summary is uploaded, but a depreciation schedule is missing to claim depreciation expense for the rental building.",
      "missing_details": [
        "Depreciation Schedule or Form 4562 for rental assets"
      ],
      "actions": {}
    },
    {
      "form_name": "Form 4562",
      "status": "incomplete",
      "reason": "Depreciation must be claimed for the Schedule E rental property, but depreciation schedule or assets details are missing.",
      "missing_details": [
        "Depreciation Schedule or prior year asset depreciation details"
      ],
      "actions": {}
    },
    {
      "form_name": "Schedule 1",
      "status": "incomplete",
      "reason": "Schedule 1 depends on the final calculated business income from Schedule C and rental income from Schedule E, which are currently incomplete.",
      "missing_details": [
        "Completed Schedule C net business income",
        "Completed Schedule E net rental income"
      ],
      "actions": {}
    }
  ],
  "success": true,
  "latency": 8.423
}
```
