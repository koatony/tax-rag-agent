# Schedule B (利息與普通股利) API

從上傳的憑證（如 Form 1099-INT、Form 1099-DIV 等）自動提取財務事實，
並透過 V1 確定性計算引擎完成 Schedule B 試算。

---

## POST `/schedule-b/extract-and-calculate`

**驗證**：Request Header 需夾帶 `X-API-Token`。

### Request Body

| 參數 | 類型 | 必填 | 說明 |
|---|---|---|---|
| `taxpayer_profile` | object | ✅ | 納稅人基本資料（姓名、報稅年度等） |
| `uploaded_documents` | list[object] | ✅ | 文件列表，每個物件含 `file_name`（檔名）與 `content`（文字內容） |
| `model_name` | string | ❌ | 指定 LLM 模型（預設 `gemini-2.5-pro`） |

#### Request 範例

```json
{
  "taxpayer_profile": {
    "name": "Marcus Rivera",
    "ssn": "XXX-XX-1234",
    "tax_year": 2024,
    "filing_status": "MFJ"
  },
  "uploaded_documents": [
    {
      "file_name": "Chase_1099_INT_2024.txt",
      "content": "Form 1099-INT. Payer: Chase Bank NA. Box 1 Interest Income: $348.52. Box 11 Bond Premium: $0."
    },
    {
      "file_name": "Vanguard_1099_DIV_2024.txt",
      "content": "Form 1099-DIV. Payer: Vanguard. Box 1a Total Ordinary Dividends: $1,240.00. Box 1b Qualified Dividends: $1,050.00."
    }
  ]
}
```

---

### Response Body

| 欄位 | 類型 | 說明 |
|---|---|---|
| `success` | boolean | 成功時為 `true` |
| `state` | object | 計算結果，詳見下表 |
| `debug_info` | object | LLM 模型名稱、完整 prompt、原始輸出 |

#### `state` 欄位明細

| 欄位 | 類型 | 說明 |
|---|---|---|
| `taxpayer_name` | string | 納稅人姓名 |
| `taxpayer_ssn_masked` | string | 遮蔽後的 SSN |
| `tax_year` | int | 報稅年度 |
| `filing_status` | string | 申報身份（SINGLE / MFJ / MFS / HOH / QSS） |
| `line_1_interest_items` | list[object] | Part I 利息明細清單 |
| `line_1_subtotal` | float \| null | Part I 利息加總（Line 1） |
| `line_2_total_interest` | float \| null | 應申報總利息（Line 2） |
| `line_3_excludable_savings_bond_interest` | float \| null | 可排除的教育儲蓄債券利息（Line 3，需 Form 8815） |
| `line_4_taxable_interest` | float \| null | 應稅利息（Line 4 = Line 2 − Line 3） |
| `line_5_dividend_items` | list[object] | Part II 股利明細清單 |
| `line_6_total_dividends` | float \| null | 普通股利合計（Line 6） |
| `line_7a_foreign_account_authority` | boolean \| null | 是否持有境外金融帳戶（Line 7a） |
| `line_7a_fbar_required` | boolean \| null | 是否需申報 FinCEN 114（FBAR） |
| `line_7b_foreign_countries` | list[string] | 持有帳戶的國家清單（Line 7b） |
| `line_8_foreign_trust_distribution` | boolean \| null | 是否收到境外信託分配（Line 8） |
| `is_v1_supported` | boolean | 本案件是否在 V1 支援範圍內 |
| `can_file` | boolean | 是否已具備申報條件（無阻斷錯誤） |
| `blocking_errors` | list[object] | 阻斷錯誤清單（見下） |
| `review_warnings` | list[object] | 警告與人工審核清單（見下） |

#### `blocking_errors` / `review_warnings` 物件結構

```json
{
  "code": "UNSUPPORTED_CASE",
  "field": "line_3_savings_bond_interest",
  "item_id": "int_01",
  "source_document_id": "Chase_1099_INT_2024.txt",
  "message": "..."
}
```

#### `debug_info` 物件結構

```json
{
  "model_name": "gemini-2.5-pro",
  "prompt_log": "...",
  "raw_output": "..."
}
```

---

### cURL 範例

```bash
curl -X POST "http://localhost:8088/schedule-b/extract-and-calculate" \
     -H "Content-Type: application/json" \
     -H "X-API-Token: tax-rag-secret-token" \
     -d '{
       "taxpayer_profile": {
         "name": "Marcus Rivera",
         "tax_year": 2024,
         "filing_status": "MFJ"
       },
       "uploaded_documents": [
         {
           "file_name": "Chase_1099_INT_2024.txt",
           "content": "Chase Bank NA. Box 1 Interest Income: $348.52."
         }
       ]
     }'
```

### 成功 Response 範例

```json
{
  "success": true,
  "state": {
    "taxpayer_name": "Marcus Rivera",
    "tax_year": 2024,
    "filing_status": "MFJ",
    "line_1_subtotal": 348.52,
    "line_2_total_interest": 348.52,
    "line_3_excludable_savings_bond_interest": 0.0,
    "line_4_taxable_interest": 348.52,
    "line_6_total_dividends": 1240.0,
    "is_v1_supported": true,
    "can_file": true,
    "blocking_errors": [],
    "review_warnings": []
  },
  "debug_info": {
    "model_name": "gemini-2.5-pro",
    "prompt_log": "...",
    "raw_output": "..."
  }
}
```

---

## V1 引擎支援範圍與限制

| 支援 ✅ | 不支援 ❌（Blocking Error） |
|---|---|
| Form 1099-INT 利息收入 | OID (Original Issue Discount) Form 1099-OID |
| Form 1099-DIV 普通股利 | 儲蓄債券利息排除（Form 8815）→ `UNSUPPORTED_FORM_8815` |
| FBAR 揭露判斷（Line 7a/7b） | 境外稅額抵免（Form 1116）→ `UNSUPPORTED_FOREIGN_TAX_CREDIT` |
| 境外信託揭露判斷（Line 8） | ABP 調整（市場折溢價攤銷）→ `UNSUPPORTED_ABP_ADJUSTMENT` |
