# Form 1040 E2E Assembly API

從上傳的原始文件憑證中，自動識別、提取並計算 Form 1040 申報所需的薪資、利息、股利及各項調整，並自動產出最終的 Form 1040 總收入 (Line 9) 與調整後總收入 AGI (Line 11)。

---

## POST `/form-1040/assemble`

**驗證方式**：無需強繳 `X-API-Token` (可選填)。

### Request Body 格式

| 參數 | 類型 | 必填 | 說明 |
|---|---|---|---|
| `taxpayer_profile` | object | ✅ | 申報人基本資料 |
| `taxpayer_profile.name` | string | ✅ | 申報人姓名 |
| `taxpayer_profile.ssn` | string | ✅ | 申報人社會安全號碼 |
| `taxpayer_profile.tax_year` | integer | ✅ | 申報的稅務年度 (例: 2025) |
| `taxpayer_profile.filing_status` | string | ✅ | 申報狀態（例如：`MFJ` 代表夫妻合併申報、`SINGLE` 代表單身） |
| `uploaded_documents` | list[object] | ✅ | 上傳的文件列表，每個物件含 `file_name` 與 `content`（文件純文字內容） |
| `model_name` | string | ❌ | 指定採用的 LLM 模型名稱（預設採用 `gemini-2.5-pro`，亦支援 `gemini-2.5-flash`） |

---

## 完整 Case 0622 測試指令 (複製貼上即可測試)

以下為 Marcus & Elena Rivera (Case 0622) 的真實資料，包含了兩個 W-2 檔案、一個 1098 房屋扣除額檔案、一個整合利息/股利/IRA 的 1099 檔案，以及兩個租賃與折舊相關檔案：

```bash
curl -X POST http://localhost:8088/form-1040/assemble \
  -H "Content-Type: application/json" \
  -d '{
    "taxpayer_profile": {
      "name": "Marcus & Elena Rivera",
      "ssn": "123-45-6789",
      "tax_year": 2025,
      "filing_status": "MFJ"
    },
    "uploaded_documents": [
      {
        "file_name": "Sample 01 - W-2 Marcus.txt",
        "content": "Form W-2 Wage and Tax Statement 2025. Employer: Creature Comforts Pet Supply EIN 94-1234567. Employee: Marcus Rivera SSN 123-45-6789. Box 1 Wages, tips, other compensation: $46,000. Box 2 Federal income tax withheld: $4,200. Box 13 Retirement Plan checked."
      },
      {
        "file_name": "Sample 02 - W-2 Elena.txt",
        "content": "Form W-2 Wage and Tax Statement 2025. Employer: City of Sacramento EIN 94-7654321. Employee: Elena Rivera SSN 987-65-4321. Box 1 Wages, tips, other compensation: $54,000. Box 2 Federal income tax withheld: $5,200. Box 13 Retirement Plan checked."
      },
      {
        "file_name": "Sample 03 - Rivera 1098.txt",
        "content": "Form 1098 Mortgage Interest Statement 2025. Payer: Marcus and Elena Rivera. Lender: Golden West Bank. Box 1: Mortgage interest: $9,800. Box 10: Real estate taxes paid on primary residence: $2,600."
      },
      {
        "file_name": "Sample 04 - 1099-DIV & 1099-INT & IRA & Charity.txt",
        "content": "Form 1099-INT. Payer: Chase Bank NA. Box 1 Interest Income: $150.00. Form 1099-DIV. Payer: Vanguard. Box 1a Total Ordinary Dividends: $405.00. Traditional IRA Contribution: Taxpayer Elena Rivera made a traditional IRA contribution of $7,000.00 for tax year 2025."
      },
      {
        "file_name": "Sample 05 - Rental Property Income_.txt",
        "content": "Rental Property Income Statement 2025. Property Address: 5200 Green Valley Drive, Unit 208, Sacramento, CA 95841. Gross Rental Income: $16,650. Expenses: Mortgage Interest: $4,800, County Property Tax: $2,400, Landlord Insurance: $900, Repairs and Maintenance: $550."
      },
      {
        "file_name": "Sample 06 - Depreciation Information.txt",
        "content": "Depreciation Information for 5200 Green Valley Drive Condo. Placed in service: 07/01/2022. Original Purchase Price: $275,000 (Land: $55,000, Building: $220,000). Total depreciation deduction claimed in prior years: $12,000."
      }
    ]
  }'
```

---

## 預期 Response JSON 範例

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
    "line_10": "7000.00",
    "line_11": "92565.00",
    "line_12e": "31500.00",
    "line_13a": "0.00",
    "line_14": "31500.00",
    "line_15": "61065.00",
    "line_16": "6852.00",
    "line_18": "6852.00",
    "line_19": "0.00",
    "line_21": "0.00",
    "line_22": "6852.00",
    "line_24": "6852.00",
    "line_25a": "11300.00",
    "line_25d": "11300.00",
    "line_33": "11300.00",
    "line_34": "4448.00",
    "line_35a": "4448.00",
    "line_37": null
  },
  "income_section": {
    "tax_year": 2025,
    "filing_status": "MFJ",
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
    "status": "COMPLETE",
    "can_continue": true,
    "blocking_errors": [],
    "review_warnings": []
  },
  "agi_section": {
    "line_9_total_income": "99565.00",
    "line_10_adjustments_to_income": "7000.00",
    "line_11_adjusted_gross_income": "92565.00",
    "status": "COMPLETE",
    "can_continue": true,
    "blocking_errors": []
  },
  "deduction_section": {
    "line_12e_deduction_applied": 31500.0,
    "line_13a_qbi_deduction": 0.0,
    "line_14_total_deductions": 31500.0,
    "deduction_type": "STANDARD",
    "status": "COMPLETE",
    "blocking_errors": []
  },
  "taxable_income_section": {
    "line_11_agi": "92565.00",
    "line_14_deductions": "31500.00",
    "line_15_taxable_income": "61065.00",
    "status": "COMPLETE",
    "blocking_errors": []
  },
  "tax_computation_section": {
    "line_15_taxable_income": "61065.00",
    "line_16_tax": "6852.00",
    "line_18_tax_before_credits": "6852.00",
    "status": "COMPLETE",
    "blocking_errors": []
  },
  "credits_section": {
    "line_18_tax_before_credits": "6852.00",
    "line_19_ctc_odc": "0.00",
    "line_21_total_credits": "0.00",
    "line_22_tax_after_credits": "6852.00",
    "line_24_total_tax": "6852.00",
    "status": "COMPLETE",
    "blocking_errors": []
  },
  "payments_refund_section": {
    "line_24_total_tax": "6852.00",
    "line_25a_w2_withholding": "11300.00",
    "line_25d_total_withholding": "11300.00",
    "line_33_total_payments": "11300.00",
    "line_34_overpayment": "4448.00",
    "line_35a_refund_amount": "4448.00",
    "status": "COMPLETE",
    "blocking_errors": []
  },
  "review_warnings": [
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
  ],
  "status": "COMPLETE",
  "blocking_errors": [],
  "success": true,
  "latency": 16.423,
  "debug_info": {
    "extracted_direct_income": {
      "w2_items": [
        {
          "employee_name": "Marcus Rivera",
          "employer_name": "Creature Comforts Pet Supply",
          "box_1_wages": 46000.0,
          "box_2_federal_withholding": 4200.0,
          "tax_year": 2025
        },
        {
          "employee_name": "Elena Rivera",
          "employer_name": "City of Sacramento",
          "box_1_wages": 54000.0,
          "box_2_federal_withholding": 5200.0,
          "tax_year": 2025
        }
      ],
      "ira_distribution": {
        "gross_amount": 0.0,
        "taxable_amount": 0.0
      },
      "pension_annuity": {
        "gross_amount": 0.0,
        "taxable_amount": 0.0
      },
      "social_security": {
        "gross_amount": 0.0,
        "taxable_amount": 0.0
      }
    },
    "extracted_schedule_b": {
      "taxpayer_name": "Marcus & Elena Rivera",
      "taxpayer_ssn": "123-45-6789",
      "tax_year": 2025,
      "interest_items": [
        {
          "statement_issuer_name": null,
          "source_document_type": "1099-INT",
          "source_box": "1",
          "payer_name": "Chase Bank NA",
          "payer_reported_amount": 150.0,
          "tax_character": "TAXABLE_INTEREST",
          "is_series_ee_or_i_interest": false
        }
      ],
      "dividend_items": [
        {
          "statement_issuer_name": null,
          "source_document_type": "1099-DIV",
          "payer_name": "Vanguard",
          "ordinary_dividends": 405.0,
          "qualified_dividends": 0.0,
          "exempt_interest_dividends": 0.0
        }
      ],
      "market_discount_items": [],
      "foreign_account_q1": false,
      "fbar_q2": false,
      "foreign_countries": [],
      "foreign_trust_q8": false,
      "special_case_flags": {
        "has_nominee_distribution": false,
        "has_accrued_interest": false,
        "has_oid": false,
        "has_abp_adjustment": false,
        "has_market_discount": false,
        "has_seller_financed_mortgage": false,
        "has_form_8814": false,
        "has_tax_exempt_bond_premium": false,
        "has_contingent_payment_debt": false
      }
    },
    "extracted_schedule_1": {
      "taxpayer_name": "Marcus & Elena Rivera",
      "taxpayer_ssn": "123-45-6789",
      "tax_year": 2025,
      "form_1099k_error_or_personal_loss_amount": 0.0,
      "line_1_state_local_tax_refund": 0.0,
      "line_2a_alimony_received": 0.0,
      "line_2b_original_agreement_date": null,
      "schedule_c_line_31": null,
      "line_4_other_gains_or_losses": 0.0,
      "schedule_e_line_41": null,
      "line_6_farm_income": 0.0,
      "line_7_unemployment_compensation": 0.0,
      "line_7_repaid_overpayment_flag": false,
      "line_7_repaid_overpayment_amount": null,
      "other_income_items": [],
      "line_19b_recipient_ssn": null,
      "line_19c_original_agreement_date": null,
      "line_20_mfs_lived_apart_flag": false,
      "adjustment_items": [
        {
          "line_code": "20",
          "description": "存入金額 $7000.00，扣除額尚待確認",
          "amount": 0.0
        }
      ],
      "special_case_flags": {
        "has_schedule_f_income": false,
        "has_form_4797_or_4684": false,
        "has_schedule_se_deduction": false,
        "has_form_2106": false,
        "has_form_3903": false,
        "has_form_8889": false,
        "has_form_8853": false,
        "has_archer_msa_deduction": false,
        "has_form_2555": false,
        "has_digital_assets_income": false,
        "has_nonqualified_deferred_comp": false,
        "has_incarcerated_wages": false,
        "has_able_account_distribution": false,
        "has_medicaid_waiver_adjustment": false,
        "has_section_951_inclusion": false,
        "has_excess_business_loss_adjustment": false,
        "has_k1_section_67e_deduction": false
      }
    }
  }
}
```
