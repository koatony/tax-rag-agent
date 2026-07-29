# Schedule 1 (額外所得與收入調整) API

從上傳的憑證（如 1099-K、Traditional IRA 存款收據、Schedule C/E 計算結果等）自動提取財務事實，
並透過 V1 確定性計算引擎完成 Schedule 1 試算。

---

## POST `/schedule-1/extract-and-calculate`

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
    "tax_year": 2025,
    "filing_status": "MFJ"
  },
  "uploaded_documents": [
    {
      "file_name": "State_Tax_Refund_2025.txt",
      "content": "State income tax refund received in 2025: $800.00. Prior year itemized deduction claimed."
    },
    {
      "file_name": "Traditional_IRA_Contribution.txt",
      "content": "Fidelity Investments Traditional IRA Contribution Confirmation. Contribution Amount: $7,000. Tax Year: 2025."
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
| `form_1099k_error_or_personal_loss_amount` | float | 表頭 1099-K 揭露金額（僅供揭露，不計入加總） |
| `line_1_state_local_tax_refund` | float | Line 1：州及地方所得稅退稅 |
| `line_2a_alimony_received` | float | Line 2a：收到之贍養費 |
| `line_2b_original_agreement_date` | string \| null | Line 2b：原始協議日期 |
| `line_3_business_income` | float | Line 3：引用已完成 Schedule C Line 31 |
| `line_4_other_gains_or_losses` | float | Line 4：Form 4797/4684 其他利得或虧損 |
| `line_5_rental_royalty_income` | float | Line 5：引用已完成 Schedule E Line 41 |
| `line_6_farm_income` | float | Line 6：Schedule F 農場所得或虧損 |
| `line_7_unemployment_compensation` | float | Line 7：失業補償 |
| `other_income_entries` | list[object] | Line 8a-8z 其他所得明細 |
| `line_9_total_other_income` | float | Line 9：Line 8a-8z 加總 |
| `line_10_additional_income` | float | Line 10：額外所得總額（→ Form 1040 Line 8） |
| `line_19b_recipient_ssn` | string \| null | Line 19b：贍養費受領人 SSN |
| `line_19c_original_agreement_date` | string \| null | Line 19c：原始協議日期 |
| `adjustment_entries` | list[object] | Line 11-23、24a-24z 收入調整明細 |
| `line_25_total_other_adjustments` | float | Line 25：Line 24a-24z 加總 |
| `line_26_adjustments_to_income` | float | Line 26：調整總額（→ Form 1040 Line 10） |
| `is_schedule_1_required` | boolean | 是否符合申報 Schedule 1 之條件 |
| `is_v1_supported` | boolean | 本案件是否在 V1 支援範圍內 |
| `can_file` | boolean | 是否已具備申報條件（無阻斷錯誤） |
| `should_attach_schedule_1` | boolean | 是否應檢附 Schedule 1（`is_schedule_1_required` 且 `can_file`） |
| `blocking_errors` | list[object] | 阻斷錯誤清單（見下） |
| `review_warnings` | list[object] | 警告與人工審核清單（見下） |

#### `blocking_errors` / `review_warnings` 物件結構

```json
{
  "code": "UNSUPPORTED_SCHEDULE_SE_DEDUCTION",
  "field": "line_15",
  "item_id": null,
  "source_document_id": null,
  "message": "Deductible part of self-employment tax is not supported in V1."
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
curl -X POST "http://localhost:8088/schedule-1/extract-and-calculate" \
     -H "Content-Type: application/json" \
     -H "X-API-Token: tax-rag-secret-token" \
     -d '{
       "taxpayer_profile": {
         "name": "Marcus Rivera",
         "tax_year": 2025,
         "filing_status": "MFJ"
       },
       "uploaded_documents": [
         {
           "file_name": "State_Tax_Refund_2025.txt",
           "content": "State income tax refund received in 2025: $800.00."
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
    "taxpayer_ssn_masked": "***-**-1234",
    "tax_year": 2025,
    "line_1_state_local_tax_refund": 800.0,
    "line_3_business_income": 15000.0,
    "line_10_additional_income": 15800.0,
    "line_26_adjustments_to_income": 0.0,
    "is_schedule_1_required": true,
    "is_v1_supported": true,
    "can_file": true,
    "should_attach_schedule_1": true,
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
| Line 1 州稅退稅、Line 2a 贍養費收入 | Schedule F 農場所得 → `UNSUPPORTED_SCHEDULE_F` |
| Line 3／Line 5 引用已完成 Schedule C／Schedule E 結果 | Form 4797/4684 其他利得或虧損 → `UNSUPPORTED_FORM_4797_4684` |
| Line 7 失業補償、Line 8a-8v/8z 常見其他所得項目 | Schedule SE 自雇稅可扣除部分 → `UNSUPPORTED_SCHEDULE_SE_DEDUCTION` |
| Line 11/16/17/18/19a/20/21、24a/24c/24e-24i/24z 常見收入調整 | Form 2106、Form 3903、Form 8889、Form 8853、Archer MSA、Form 2555 → 對應 `UNSUPPORTED_FORM_*` |
| — | 數位資產所得、非合格遞延補償、服刑期間工資、ABLE 帳戶分配、Medicaid waiver 調整、Section 951(a)/951A(a) inclusion、Section 461(l) 超額營業虧損調整、K-1 Section 67(e) 超額扣除 → 對應 `UNSUPPORTED_*` |
| — | Line 4／Line 6 有金額但未標記對應特殊案件旗標 → `UNFLAGGED_FORM_4797_4684_AMOUNT` / `UNFLAGGED_SCHEDULE_F_AMOUNT` |
