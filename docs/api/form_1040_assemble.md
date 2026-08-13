# Form 1040 E2E Assembly API

從上傳的原始文件憑證中，自動識別、提取並計算 Form 1040 申報所需的薪資、利息、股利及各項調整，並自動產出最終的 Form 1040 總收入 (Line 9) 與調整後總收入 AGI (Line 11)。

---

## POST `/form-1040/assemble`

**驗證方式**：無需強繳 `X-API-Token` (可選填)。

### 參數必填性說明 (Required vs Optional)

* **必填欄位 (Required)**：
  * `taxpayer_profile`：基本資料物件。其中 **`tax_year`**（稅務年度，如 `2025`）與 **`filing_status`**（申報身分，如 `MFJ`）是**計算引擎的核心必填參數**，直接決定了計稅級距與標準扣除額。
  * `uploaded_documents`：上傳的文件列表（不可為空），列表中每個文件物件須包含 `file_name`（檔案名稱）與 `content`（文件純文字內容）。
* **選填欄位 (Optional)**：
  * `taxpayer_profile.name`：申報人姓名（僅供表頭揭露，不影響計算）。
  * `taxpayer_profile.ssn`：社會安全號碼（僅供表頭揭露，不影響計算）。
  * `model_name`：指定採用的 LLM 抽取模型（預設為 `gemini-2.5-pro`）。

### Request Body 格式

| 參數 | 類型 | 必填 | 說明 |
|---|---|---|---|
| `taxpayer_profile` | object | ✅ | 申報人基本資料物件 |
| `taxpayer_profile.tax_year` | integer | ✅ | **核心計算必填**：申報的稅務年度（例如：`2025`），用於比對適用之稅率表與標準扣除額 |
| `taxpayer_profile.filing_status` | string | ✅ | **核心計算必填**：申報身分（`"SINGLE"`, `"MFJ"`, `"HOH"`, `"MFS"`, `"QSS"`），直接決定標準扣除額與應納稅額級距 |
| `taxpayer_profile.name` | string | ❌ | 申報人姓名（選填，用於表頭渲染與 PDF 產出） |
| `taxpayer_profile.ssn` | string | ❌ | 申報人社會安全號碼（選填，用於表頭渲染與 PDF 產出） |
| `uploaded_documents` | list[object] | ✅ | 上傳的文件列表，每個物件含 `file_name` 與 `content`（文件純文字內容） |
| `model_name` | string | ❌ | 指定採用的 LLM 模型名稱（預設採用 `gemini-2.5-pro`，亦支援 `gemini-2.5-flash`） |

---

## 完整 Case 0622 測試指令 (複製貼上即可測試)

以下為 Marcus & Elena Rivera (Case 0622) 對齊來源文件的測試資料，包含了兩個 W-2 檔案、一個 1098 房屋扣除額檔案、一個整合利息/股利/IRA 的 1099 檔案，以及兩個租賃與折舊相關檔案：

> [!IMPORTANT]
> **Line 7a (Capital Gain or Loss) 說明**：目前 V1 系統尚未實作 Schedule D (資本損益) 提取與計算模組。因此此處的 `-990.00` 係由系統中 Hardcoded 之預設 Placeholder Fixture 帶入，而非從這 6 份文件資料中計算抽出。

```bash
curl -X POST http://localhost:8088/form-1040/assemble \
  -H "Content-Type: application/json" \
  -d '{
  "taxpayer_profile": {
    "name": "Marcus & Elena Rivera",
    "ssn": "555-12-3456",
    "tax_year": 2025,
    "filing_status": "MFJ"
  },
  "uploaded_documents": [
    {
      "file_name": "Sample 01 - W-2 Marcus.txt",
      "content": "Form W-2 Wage and Tax Statement 2025. Employer: Creature Comforts Pets Supply. Employer EIN: 94-7654321. Employee: Marcus Rivera. Employee SSN: 555-12-3456. Box 1 Wages, tips, other compensation: $46,000. Box 2 Federal income tax withheld: $3,800. Box 12 Code D: $2,000. Box 13 Retirement Plan checked. Box 17 State income tax: $1,450."
    },
    {
      "file_name": "Sample 02 - W-2 Elena.txt",
      "content": "Form W-2 Wage and Tax Statement 2025. Employer: City of Sacramento Fire Department. Employer EIN: 94-6000414. Employee: Elena Rivera. Employee SSN: 555-23-4567. Box 1 Wages, tips, other compensation: $54,000. Box 2 Federal income tax withheld: $5,200. Box 12 Code DD: $14,800. Box 12 Code D: $3,000. Box 13 Retirement Plan checked. Box 17 State income tax: $2,150."
    },
    {
      "file_name": "Sample 03 - Rivera 1098.txt",
      "content": "Form 1098 Mortgage Interest Statement 2025. Lender: Golden State Home Mortgage, LLC. Lender TIN: 94-8765432. Borrowers: Marcus and Elena Rivera. Borrower TIN: 555-12-3456. Box 1 Mortgage interest received: $9,800. Box 2 Outstanding mortgage principal: $412,500. Box 3 Mortgage origination date: 06/15/2020. Box 4 Refund of overpaid interest: $0. Box 5 Mortgage insurance premiums: $1,080. Box 6 Points paid: $0. Box 9 Number of properties securing the mortgage: 1. Box 10 Other: Property Tax $2,600. Property securing mortgage: 2785 River Oak Drive, Sacramento, CA 95833. Box 11 Mortgage acquisition date: 06/15/2020."
    },
    {
      "file_name": "Sample 04 - 1099-DIV & 1099-INT & IRA & Charity.txt",
      "content": "Form 1099-INT for tax year 2025. Payer: JPMorgan Chase Bank, N.A. Box 1 Interest Income: $150. Box 2 Early Withdrawal Penalty: $0. Box 3 U.S. Savings Bond Interest: $0. Box 4 Federal Tax Withheld: $0. Box 8 Tax-Exempt Interest: $0. Box 9 Private Activity Bond Interest: $0. Form 1099-DIV for tax year 2025. Payer: Vanguard Brokerage Services. Box 1a Total Ordinary Dividends: $405. Box 1b Qualified Dividends: $0. Box 2a Capital Gain Distributions: $0. Box 2b Unrecaptured Section 1250 Gain: $0. Box 3 Nondividend Distributions: $0. Box 4 Federal Tax Withheld: $0. Box 7 Foreign Tax Paid: $0. Traditional IRA Contribution Record: Marcus Rivera contributed $7,000 to a Traditional IRA at Fidelity Investments on 12/15/2025 for tax year 2025. Deductibility requires determination under applicable IRA deduction rules. Charitable Contribution Receipt: Marcus and Elena Rivera made $5,400 of cash charitable contributions to Sacramento Community Church during 2025. No goods or services were provided in exchange for the contributions."
    },
    {
      "file_name": "Sample 05 - Rental Property Income_.txt",
      "content": "Rental Property Income Information for Marcus & Elena Rivera, tax year 2025. Property type: Single Family Residential Rental Property. Property address: 5200 Green Valley Dr., Unit 200, Sacramento, CA 95841. Fair rental days: 365. Personal use days: 0. Gross rental income received: $16,650. Rental expenses: Insurance $900; Mortgage Interest $4,800; Property Taxes $2,400; Repairs and Maintenance $550; Depreciation Expense $8,000. Total rental expenses: $16,650. Net Rental Income (Loss): $0. The property was purchased and placed into rental service in July 2023. Depreciable basis: $220,000. Recovery period: 27.5 years. Depreciation method: Straight-Line. Annual depreciation deduction for 2025: $8,000. The depreciation deduction is reported on Form 4562 and carried to Schedule E."
    },
    {
      "file_name": "Sample 06 - Depreciation Information.txt",
      "content": "Depreciation Information for Marcus & Elena Rivera, tax year 2025. Business activity: Rental Real Estate. Property address: 5200 Green Valley Dr., Unit 200, Sacramento, CA 95841. Property classification: Residential Rental Property. Date placed in service: July 2023. Depreciable basis: $220,000. Recovery period: 27.5 years. Convention: Mid-Month Convention. Depreciation method: Straight-Line. Annual depreciation deduction for tax year 2025: $8,000. Form 4562 depreciation deduction: $8,000. This $8,000 depreciation deduction flows from Form 4562 to Schedule E."
    }
  ]
}'
```

---

## 目前 V1 API 預期 Response

> [!NOTE]
> **`status: COMPLETE` 的定義說明**：此處的 `COMPLETE` 僅代表「目前 V1 已支援之業務範圍」已成功運算完畢。由於許多進階表單 (如 Schedule 8812, Schedule 2/3, Form 8863/8839 等) 目前在 V1 尚未實作，故其回傳結構中會包含 Placeholder 預設值。本 Response 不等同於完整稅務申報之 ground truth (例如 Line 19 CTC 顯示為 `0`、Refund 顯示為 `1308` 等)。

```json
{
  "form_1040_lines": {
    "line_1a": "100000.00",
    "line_1z": "100000.00",
    "line_2a": "0.00",
    "line_2b": "150.00",
    "line_3a": "0.00",
    "line_3b": "405.00",
    "line_4a": "0.00",
    "line_4b": "0.00",
    "line_5a": "0.00",
    "line_5b": "0.00",
    "line_6a": "0.00",
    "line_6b": "0.00",
    "line_7a": "-990.00",
    "line_8": "0.00",
    "line_9": "99565.00",
    "line_10": "0.00",
    "line_11": "99565.00",
    "line_12e": "31500.00",
    "line_13a": "0.00",
    "line_13b": "0.00",
    "line_14": "31500.00",
    "line_15": "68065.00",
    "line_16": "7692.00",
    "line_17": "0.00",
    "line_18": "7692.00",
    "line_19": "0.00",
    "line_20": "0.00",
    "line_21": "0.00",
    "line_22": "7692.00",
    "line_23": "0.00",
    "line_24": "7692.00",
    "line_25a": "9000.00",
    "line_25b": "0.00",
    "line_25c": "0.00",
    "line_25d": "9000.00",
    "line_26": "0.00",
    "line_27": "0.00",
    "line_28": "0.00",
    "line_29": "0.00",
    "line_30": "0.00",
    "line_31": "0.00",
    "line_32": "0.00",
    "line_33": "9000.00",
    "line_34": "1308.00",
    "line_35a": "1308.00",
    "line_36": "0.00",
    "line_37": null,
    "line_38": "0.00"
  },
  "income_section": {
    "tax_year": 2025,
    "filing_status": "MFJ",
    "line_1a": "100000.0",
    "line_1z": "100000.0",
    "line_2a": "0.00",
    "line_2b": "150.00",
    "line_3a": "0.00",
    "line_3b": "405.00",
    "line_4a": "0.0",
    "line_4b": "0.0",
    "line_5a": "0.0",
    "line_5b": "0.0",
    "line_6a": "0.0",
    "line_6b": "0.0",
    "line_7a": "-990.00",
    "line_8": "0.00",
    "line_9": "99565.00",
    "status": "COMPLETE",
    "can_continue": true,
    "blocking_errors": [],
    "review_warnings": []
  },
  "agi_section": {
    "line_9_total_income": "99565.00",
    "line_10_adjustments_to_income": "0.00",
    "line_11_adjusted_gross_income": "99565.00",
    "status": "COMPLETE",
    "can_continue": true,
    "blocking_errors": []
  },
  "deduction_section": {
    "tax_year": 2025,
    "filing_status": "MFJ",
    "line_12e_deduction": 31500.0,
    "line_13a_qbi_deduction": 0.0,
    "line_13b_schedule_1a_deductions": 0.0,
    "line_14_total_deductions": 31500.0,
    "is_itemizing": false,
    "deduction_type_used": "STANDARD",
    "should_attach_schedule_a": false,
    "status": "COMPLETE",
    "can_continue": true,
    "blocking_errors": [],
    "review_warnings": [
      {
        "code": "SCHEDULE_A_FALLBACK_TO_STANDARD",
        "field": "schedule_a_result",
        "message": "Schedule A 檢驗未通過，系統已安全回退選用標準扣除額供人工審核。 (原因：{'code': 'UNKNOWN_AGE_STATUS', 'field': 'taxpayer_date_of_birth', 'item_id': None, 'source_document_id': None, 'message': 'Taxpayer date of birth is missing; cannot determine if over 65.'}; {'code': 'UNKNOWN_AGE_STATUS', 'field': 'spouse_date_of_birth', 'item_id': None, 'source_document_id': None, 'message': 'Spouse date of birth is missing; cannot determine if over 65.'}; {'code': 'UNSUPPORTED_MULTIPLE_MORTGAGES', 'field': 'has_multiple_mortgages', 'item_id': None, 'source_document_id': None, 'message': 'Multiple mortgages or multiple properties are not supported in V1.'}; {'code': 'TAX_ELECTION_MISSING', 'field': 'line_5a_election', 'item_id': None, 'source_document_id': None, 'message': 'Tax election (income tax vs sales tax) is missing.'}; {'code': 'REAL_ESTATE_TAX_PAYMENT_NOT_CONFIRMED', 'field': 'line_5b_real_estate_taxes', 'item_id': 'tax_03', 'source_document_id': 'Sample 03 - Rivera 1098.txt', 'message': 'The source reports an escrow amount but does not confirm the amount actually paid to the taxing authority during 2025.'}; {'code': 'UNKNOWN_TAX_CHARACTER', 'field': 'qualified_organization_status', 'item_id': 'charity_01', 'source_document_id': 'Sample 04 - 1099-DIV & 1099-INT & IRA & Charity.txt', 'message': 'Unknown charity organization qualification status.'})"
      }
    ]
  },
  "taxable_income_section": {
    "tax_year": 2025,
    "line_11b_agi": "99565.00",
    "line_14_total_deductions": "31500.00",
    "line_15_taxable_income": "68065.00",
    "is_v1_supported": true,
    "can_file": true,
    "status": "COMPLETE",
    "can_continue": true,
    "blocking_errors": [],
    "review_warnings": []
  },
  "tax_computation_section": {
    "tax_year": 2025,
    "filing_status": "MFJ",
    "line_15_taxable_income": "68065.00",
    "line_16_tax": "7692",
    "line_17_schedule_2_line_3": "0.00",
    "line_18_tax_before_credits": "7692.00",
    "computation_method": "TAX_TABLE",
    "tax_rule_version": "2025-final-v1",
    "is_v1_supported": true,
    "can_file": true,
    "source_trace": {
      "line_15": "TAXABLE_INCOME_PROCESSOR",
      "line_16": "TAX_TABLE",
      "line_17": "SCHEDULE_2_NOT_APPLICABLE",
      "line_18": "LINE_16_PLUS_LINE_17"
    },
    "status": "COMPLETE",
    "can_continue": true,
    "blocking_errors": [],
    "review_warnings": []
  },
  "credits_section": {
    "line_18_tax_before_credits": "7692.00",
    "line_19_ctc_odc": "0.00",
    "line_20_schedule3_credits": "0.00",
    "line_21_total_credits": "0.00",
    "line_22_tax_after_credits": "7692.00",
    "line_23_other_taxes": "0.00",
    "line_24_total_tax": "7692.00",
    "status": "COMPLETE",
    "can_continue": true,
    "blocking_errors": []
  },
  "payments_refund_section": {
    "line_24_total_tax": "7692.00",
    "line_25a_w2_withholding": "9000.0",
    "line_25b_1099_withholding": "0.00",
    "line_25c_other_withholding": "0.00",
    "line_25d_total_withholding": "9000.00",
    "line_26_estimated_payments": "0.00",
    "line_27a_eic": "0.00",
    "line_28_actc": "0.00",
    "line_29_aoc": "0.00",
    "line_30_refundable_adoption_credit": "0.00",
    "line_31_schedule3_total": "0.00",
    "line_32_other_payments_credits": "0.00",
    "line_33_total_payments": "9000.00",
    "line_34_overpayment": "1308.00",
    "line_35a_refund_amount": "1308.00",
    "line_36_applied_to_next_year": "0.00",
    "line_37_amount_owed": null,
    "line_38_estimated_tax_penalty": "0.00",
    "status": "COMPLETE",
    "can_continue": true,
    "blocking_errors": []
  },
  "schedule_e_section": {
    "line_26_total_rental_income_or_loss": 0.0,
    "schedule_1_line_5_transfer_amount": 0.0,
    "status": "COMPLETE",
    "blocking_errors": [],
    "review_warnings": []
  },
  "status": "COMPLETE",
  "blocking_errors": [],
  "review_warnings": [
    {
      "code": "SCHEDULE_A_FALLBACK_TO_STANDARD",
      "field": "schedule_a_result",
      "message": "Schedule A 檢驗未通過，系統已安全回退選用標準扣除額供人工審核。 (原因：{'code': 'UNKNOWN_AGE_STATUS', 'field': 'taxpayer_date_of_birth', 'item_id': None, 'source_document_id': None, 'message': 'Taxpayer date of birth is missing; cannot determine if over 65.'}; {'code': 'UNKNOWN_AGE_STATUS', 'field': 'spouse_date_of_birth', 'item_id': None, 'source_document_id': None, 'message': 'Spouse date of birth is missing; cannot determine if over 65.'}; {'code': 'UNSUPPORTED_MULTIPLE_MORTGAGES', 'field': 'has_multiple_mortgages', 'item_id': None, 'source_document_id': None, 'message': 'Multiple mortgages or multiple properties are not supported in V1.'}; {'code': 'TAX_ELECTION_MISSING', 'field': 'line_5a_election', 'item_id': None, 'source_document_id': None, 'message': 'Tax election (income tax vs sales tax) is missing.'}; {'code': 'REAL_ESTATE_TAX_PAYMENT_NOT_CONFIRMED', 'field': 'line_5b_real_estate_taxes', 'item_id': 'tax_03', 'source_document_id': 'Sample 03 - Rivera 1098.txt', 'message': 'The source reports an escrow amount but does not confirm the amount actually paid to the taxing authority during 2025.'}; {'code': 'UNKNOWN_TAX_CHARACTER', 'field': 'qualified_organization_status', 'item_id': 'charity_01', 'source_document_id': 'Sample 04 - 1099-DIV & 1099-INT & IRA & Charity.txt', 'message': 'Unknown charity organization qualification status.'})"
    },
    {
      "code": "UNIMPLEMENTED_MODULE_PLACEHOLDER",
      "field": "schedule_8812",
      "message": "Schedule 8812 (Child Tax Credit / ACTC) 模組尚未建立，目前採用 Placeholder 預設值 (0.00)"
    },
    {
      "code": "UNIMPLEMENTED_MODULE_PLACEHOLDER",
      "field": "schedule_2",
      "message": "Schedule 2 模組尚未建立，目前採用 Placeholder 預設值 (0.00)"
    },
    {
      "code": "UNIMPLEMENTED_MODULE_PLACEHOLDER",
      "field": "schedule_3",
      "message": "Schedule 3 模組尚未建立，目前採用 Placeholder 預設值 (0.00)"
    },
    {
      "code": "UNIMPLEMENTED_MODULE_PLACEHOLDER",
      "field": "form_8863",
      "message": "Form 8863 (AOC) 模組尚未建立，目前採用 Placeholder 預設值 (0.00)"
    },
    {
      "code": "UNIMPLEMENTED_MODULE_PLACEHOLDER",
      "field": "form_8839",
      "message": "Form 8839 (Adoption Credit) 模組尚未建立，目前採用 Placeholder 預設值 (0.00)"
    }
  ]
}
```
