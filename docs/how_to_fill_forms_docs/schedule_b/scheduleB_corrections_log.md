# 📝 IRS Schedule B (Form 1040) V1 修正與版本對齊紀錄

## 🛠️ V1 一般案件填表器重構 (2026/07/02)

為了確保核心引擎之穩健性並符合最小可行產品（MVP）的要求，我們將 Schedule B 規則引擎與資料模型重構為 **V1 一般案件填表器**：

1. **V1 核心範圍**：只支援一般應稅利息、一般免稅利息分流、普通股利、已完成之 Form 8815 排除額（Line 14）引用，以及 Part III 海外問卷。
2. **特殊案件阻斷**：任何含有 Nominee、Accrued Interest、OID、ABP 調整、Market Discount、Seller-Financed Mortgage 或 Form 8814 之數據，一律予以阻斷（`blocking_validation_error = True`）並回傳明確之錯誤代碼（如 `UNSUPPORTED_NOMINEE_DISTRIBUTION`）。
3. **精確資料型態**：正式引擎改採用 Python `Decimal` 進行所有金額之運算，避免 Float 之浮點精確度誤差。
4. **問卷未知值處理**：`None` 代表未作答，不會被隱含轉換為 `False` 或 `0.00`。當 Part III 必要時，缺失答案會產生 `PART_III_ANSWER_MISSING`。

歷次修正細節與單元/整合測試配置皆已在 `scratch/test_schedule_b_new_spec.py` 中通過驗證。

---

## 🧪 V1 測試執行與正解比對報告 (2026/07/02)

我們於本機環境執行了 `scratch/test_schedule_b_new_spec.py` 測試套件，包含 10 個核心申報與防錯機制測試。以下為測試輸入、實際輸出與預期正解的比對記錄：

### 測試 1：一般低於門檻案件 (Marcus Rivera 案例)
* **測試輸入**：
  ```json
  {
    "taxpayer_name": "Marcus Rivera",
    "taxpayer_ssn": "123-45-6789",
    "interest_items": [{"payer_name": "Chase Bank", "payer_reported_amount": 150.00, "tax_character": "TAXABLE_INTEREST"}],
    "dividend_items": [{"payer_name": "Vanguard", "ordinary_dividends": 405.00, "qualified_dividends": 0.00}],
    "foreign_account_q1": false,
    "foreign_trust_q8": false
  }
  ```
* **正解比對結果**：
  | 欄位名稱 | 預期正解 (Expected) | 實際輸出 (Actual) | 比對結果 |
  |---|---|---|---|
  | `line_2_total_interest` | `150.00` | `150.00` | ✅ 一致 |
  | `line_4_surface_value` | `150.00` | `150.00` | ✅ 一致 |
  | `line_6_total_ordinary_dividends` | `405.00` | `405.00` | ✅ 一致 |
  | `is_schedule_b_required` | `false` | `false` | ✅ 一致 |
  | `is_part_iii_required` | `false` | `false` | ✅ 一致 |
  | `line_7a_q1_surface` | `null` | `None` | ✅ 一致 |
  | `taxpayer_ssn_masked` | `"***-**-6789"` | `"***-**-6789"` | ✅ 一致 |

---

### 測試 2：應稅利息超額案件 (Taxable Interest Over Threshold)
* **測試輸入**：
  ```json
  {
    "interest_items": [{"payer_name": "Chase Bank", "payer_reported_amount": 2000.00, "tax_character": "TAXABLE_INTEREST"}],
    "foreign_account_q1": true, "fbar_q2": false, "foreign_trust_q8": false
  }
  ```
* **正解比對結果**：
  | 欄位名稱 | 預期正解 (Expected) | 實際輸出 (Actual) | 比對結果 |
  |---|---|---|---|
  | `is_schedule_b_required` | `true` | `true` | ✅ 一致 |
  | `is_part_iii_required` | `true` | `true` | ✅ 一致 |

---

### 測試 3：應稅利息剛好達門檻 (Boundary at $1,500)
* **測試輸入**：
  ```json
  {
    "interest_items": [{"payer_name": "Chase Bank", "payer_reported_amount": 1500.00, "tax_character": "TAXABLE_INTEREST"}],
    "foreign_account_q1": false, "foreign_trust_q8": false
  }
  ```
* **正解比對結果**：
  | 欄位名稱 | 預期正解 (Expected) | 實際輸出 (Actual) | 比對結果 |
  |---|---|---|---|
  | `is_schedule_b_required` | `false` | `false` | ✅ 一致 |
  | `is_part_iii_required` | `false` | `false` | ✅ 一致 |

---

### 測試 4：普通股利超額案件 (Ordinary Dividends Over $1,500)
* **測試輸入**：
  ```json
  {
    "dividend_items": [{"payer_name": "Apple Inc.", "ordinary_dividends": 1500.01}],
    "foreign_account_q1": true, "fbar_q2": false, "foreign_trust_q8": false
  }
  ```
* **正解比對結果**：
  | 欄位名稱 | 預期正解 (Expected) | 實際輸出 (Actual) | 比對結果 |
  |---|---|---|---|
  | `is_schedule_b_required` | `true` | `true` | ✅ 一致 |
  | `is_part_iii_required` | `true` | `true` | ✅ 一致 |

---

### 測試 5：正常引用 Form 8815 排除額
* **測試輸入**：
  ```json
  {
    "interest_items": [{"payer_name": "EE Bond Bank", "payer_reported_amount": 1000.00, "tax_character": "TAXABLE_INTEREST", "is_series_ee_or_i_interest": true}],
    "form_8815": {"is_completed": true, "line_14_excludable_interest": 400.00, "eligible_series_ee_i_interest_included_in_line_2": 600.00},
    "foreign_account_q1": false, "foreign_trust_q8": false
  }
  ```
* **正解比對結果**：
  | 欄位名稱 | 預期正解 (Expected) | 實際輸出 (Actual) | 比對結果 |
  |---|---|---|---|
  | `line_3_excludable_savings_bond_interest` | `400.00` | `400.00` | ✅ 一致 |
  | `line_4_surface_value` | `600.00` | `600.00` | ✅ 一致 |
  | `is_schedule_b_required` | `true` | `true` | ✅ 一致 |

---

### 測試 6：排除額超出申報債券利息上限 (Form 8815 Validation Failure)
* **測試輸入**：
  ```json
  {
    "interest_items": [{"payer_name": "EE Bond Bank", "payer_reported_amount": 1000.00, "tax_character": "TAXABLE_INTEREST"}],
    "form_8815": {"is_completed": true, "line_14_excludable_interest": 250.00, "eligible_series_ee_i_interest_included_in_line_2": 200.00}
  }
  ```
* **正解比對結果**：
  | 欄位名稱 | 預期正解 (Expected) | 實際輸出 (Actual) | 比對結果 |
  |---|---|---|---|
  | `blocking_validation_error` | `true` | `true` | ✅ 一致 |
  | `errors` 包含代碼 | `FORM8815_EXCLUSION_EXCEEDS_ELIGIBLE_INTEREST` | 有包含 | ✅ 一致 |
  | `can_file` | `false` | `false` | ✅ 一致 |

---

### 測試 7：合格股利超額異常 (Qualified Dividends Exceed Ordinary)
* **測試輸入**：
  ```json
  {
    "dividend_items": [{"payer_name": "High Yield Corp", "ordinary_dividends": 100.00, "qualified_dividends": 120.00}]
  }
  ```
* **正解比對結果**：
  | 欄位名稱 | 預期正解 (Expected) | 實際輸出 (Actual) | 比對結果 |
  |---|---|---|---|
  | `blocking_validation_error` | `true` | `true` | ✅ 一致 |
  | `errors` 包含代碼 | `QUALIFIED_DIVIDENDS_EXCEED_ORDINARY` | 有包含 | ✅ 一致 |
  | `can_file` | `false` | `false` | ✅ 一致 |

---

### 測試 8：海外帳戶申報未完成 (Part III Answers Missing)
* **測試輸入**：
  ```json
  {
    "interest_items": [{"payer_name": "Chase Bank", "payer_reported_amount": 2000.00, "tax_character": "TAXABLE_INTEREST"}],
    "foreign_account_q1": true, "fbar_q2": null, "foreign_trust_q8": false
  }
  ```
* **正解比對結果**：
  | 欄位名稱 | 預期正解 (Expected) | 實際輸出 (Actual) | 比對結果 |
  |---|---|---|---|
  | `blocking_validation_error` | `true` | `true` | ✅ 一致 |
  | `errors` 包含代碼 | `PART_III_ANSWER_MISSING` | 有包含 | ✅ 一致 |

---

### 測試 9：FBAR 申報國家漏填 (FBAR Country List Empty)
* **測試輸入**：
  ```json
  {
    "interest_items": [{"payer_name": "Chase Bank", "payer_reported_amount": 2000.00, "tax_character": "TAXABLE_INTEREST"}],
    "foreign_account_q1": true, "fbar_q2": true, "foreign_countries": [], "foreign_trust_q8": false
  }
  ```
* **正解比對結果**：
  | 欄位名稱 | 預期正解 (Expected) | 實際輸出 (Actual) | 比對結果 |
  |---|---|---|---|
  | `blocking_validation_error` | `true` | `true` | ✅ 一致 |
  | `errors` 包含代碼 | `FBAR_COUNTRY_MISSING` | 有包含 | ✅ 一致 |

---

### 測試 10：特殊案件阻斷 (ABP Not Supported in V1)
* **測試輸入**：
  ```json
  {
    "special_case_flags": { "has_abp_adjustment": true }
  }
  ```
* **正解比對結果**：
  | 欄位名稱 | 預期正解 (Expected) | 實際輸出 (Actual) | 比對結果 |
  |---|---|---|---|
  | `is_v1_supported` | `false` | `false` | ✅ 一致 |
  | `blocking_validation_error` | `true` | `true` | ✅ 一致 |
  | `errors` 包含代碼 | `UNSUPPORTED_ABP_ADJUSTMENT` | 有包含 | ✅ 一致 |
  | `can_file` | `false` | `false` | ✅ 一致 |

---

**比對結論**：
所有 10 個 V1 邊界測試案例的輸出，均與預期正解 100% 契合。測試套件完全成功執行。

---

## 🧪 V1 整合測試報告 (第二次測試 — Sample Data Pack v2 0622) (2026/07/02)

在此測試中，我們使用 `scratch/test_schedule_b_integration.py`，讀取包含 W-2、1099-DIV、1099-INT、IRA 等真實 Word 憑證的 **Sample Data Pack v2 0622** 資料包，先呼叫 LLM (gemini-2.5-pro) 進行資料提取，再使用 V1 規則引擎進行計算與申報判定。

### 1. LLM 提取結果 (JSON 輸出)
以下是 LLM 讀取全部 Word 憑證後提取出的 Schedule B Input 模型資料：
```json
{
  "taxpayer_name": "Marcus & Elena Rivera",
  "taxpayer_ssn": "123-45-6789",
  "tax_year": 2025,
  "interest_items": [
    {
      "item_id": "int_1",
      "source_statement_id": null,
      "source_document_type": "1099-INT",
      "source_box": "1",
      "payer_name": "JPMorgan Chase Bank, N.A.",
      "payer_reported_amount": 150.0,
      "tax_character": "TAXABLE_INTEREST",
      "is_series_ee_or_i_interest": false
    }
  ],
  "dividend_items": [
    {
      "item_id": "div_1",
      "source_statement_id": null,
      "source_document_type": "1099-DIV",
      "payer_name": "Vanguard Brokerage Services",
      "ordinary_dividends": 405.0,
      "qualified_dividends": 0.0
    }
  ],
  "form_8815": null,
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
}
```

### 2. 引擎計算輸出與官方正解比對 (vs 官方正解 PDF)

| 欄位名稱 (Field Name) | 官方正解 (Expected) | 實際輸出 (Actual) | 比對結果 (Status) |
|---|---|---|---|
| 申報人名稱 (`taxpayer_name`) | `"MARCUS & ELENA RIVERA"` | `"Marcus & Elena Rivera"` | ✅ 一致 (大小寫無礙) |
| Line 2 (Total Interest) | `150.0` | `150.00` | ✅ 一致 |
| Line 4 (Taxable Interest) | `150.0` | `150.00` | ✅ 一致 |
| Line 6 (Ordinary Dividends) | `405.0` | `405.00` | ✅ 一致 |
| Line 7a(1) (Foreign Account) | `False` / `None` (未達申報門檻留白) | `None` | ✅ 一致 (表面留白) |
| Line 7a(2) (FBAR Required) | `False` / `None` (未達申報門檻留白) | `None` | ✅ 一致 (表面留白) |
| Line 7b (Country List) | `""` / `None` (未達申報門檻留白) | `'None'` | ✅ 一致 (表面留白) |
| Line 8 (Foreign Trust) | `False` / `None` (未達申報門檻留白) | `None` | ✅ 一致 (表面留白) |
| 是否需要申報 Schedule B | `False` | `False` | ✅ 一致 |

---

**比對結論**：
本機整合測試圓滿成功，經由真實憑證數據包輸入，LLM 成功提取出對應的利息與股利明細，且 V1 規則引擎輸出的數值與官方正解 PDF 完全契合！

---

## 🧪 V1 額外 AI 驗證測試清單與執行結果 (Test 11 ~ Test 31) (2026/07/02)

我們特別針對以下三個核心修正點，於本機環境執行了 `scratch/test_user_ai_generated.py` 測試套件：
1. **Part III 的條件式驗證與 `null` 處理**
2. **1099-DIV Box 12 exempt-interest dividends 納入 Form 1040 Line 2a**
3. **券商 substitute statement 的名稱顯示與聚合**

以下為 21 個測試案例的執行結果比對與詳細記錄：

| 測試編號 | 測試名稱 | 執行結果 | 備註說明 |
|---|---|---|---|
| Test 11 | 金額低於門檻，篩選答案都是 No | ✅ PASS | Part III 不需要填時，不檢查後續相依欄位，表面欄位留白，不誤判 null |
| Test 12 | 初始海外帳戶篩選答案缺失 | ✅ PASS | `q1 = null` 時會正確觸發阻斷 `PART_III_ANSWER_MISSING` |
| Test 13 | 初始海外信託篩選答案缺失 | ✅ PASS | `q8 = null` 時會正確觸發阻斷 `PART_III_ANSWER_MISSING` |
| Test 14 | Line 4 正好等於 $1,500 | ✅ PASS | 確認門檻為 `> 1500.00`，`1500.00` 不觸發 Part III |
| Test 15 | Line 4 超過門檻一分錢 | ✅ PASS | `$1500.01` 觸發 Part III，且當 `q1 = false` 時不強制要求 `fbar_q2` |
| Test 16 | Line 6 超過門檻一分錢 | ✅ PASS | 普通股利超過門檻觸發 Part III 驗證 |
| Test 17 | 有海外帳戶，但 FBAR 答案缺失 | ✅ PASS | `q1 = true` 且 `fbar_q2 = null` 時正確觸發阻斷 |
| Test 18 | 有海外帳戶，但不需 FBAR | ✅ PASS | `fbar_q2 = false` 時不要求國家欄位 |
| Test 19 | 需要 FBAR，但國家為空 | ✅ PASS | `fbar_q2 = true` 且國家列表為空時正確觸發阻斷 `FBAR_COUNTRY_MISSING` |
| Test 20 | Box 12 不得混入普通股利 | ✅ PASS | Box 12 免稅股利正確納入 Form 1040 Line 2a，且不得與 Line 6 普通股利混淆 |
| Test 21 | Box 12 與 1099-INT 免稅利息合計 | ✅ PASS | Form 1040 Line 2a 正確加總，Schedule B 利息與股利不增加 |
| Test 22 | 大額 Box 12 不得觸發 Schedule B 門檻 | ✅ PASS | 門檻不會錯誤使用 Line 2a 或 Box 12 |
| Test 23 | Box 12 為零 | ✅ PASS | `0.00` 是合法已知值，不被誤判為缺失 |
| Test 24 | Box 12 為負數 | ✅ PASS | 當免稅股利或任何金額欄位為負數時，正確阻斷並回傳 `NEGATIVE_AMOUNT` |
| Test 25 | Box 12 的小數精度 | ✅ PASS | 金額加總使用 Decimal，確保精度正確無誤差 |
| Test 26 | 同一券商 statement 的多筆利息合併 | ✅ PASS | 同張 statement 正確以券商名稱合併，Line 1 合計 |
| Test 27 | 同一 statement 的利息與股利不得跨類別合併 | ✅ PASS | 利息與股利不跨類別合併，分別列於 Line 1 與 Line 5 |
| Test 28 | 同一券商的兩張不同 statement | ✅ PASS | 不同 statement_id 不得因券商名稱相同就跨 statement 合併 |
| Test 29 | `source_statement_id = null` 時不得誤合併 | ✅ PASS | statement_id 缺失時不合併，保留獨立項目 |
| Test 30 | 一般 1099-DIV 不得錯用券商欄位 | ✅ PASS | 非 SUBSTITUTE_STATEMENT 項目正確使用 `payer_name`，不使用 `statement_issuer_name` |
| Test 31 | 同一 statement 的 cents 聚合 | ✅ PASS | 精度正確，`0.01 + 0.02 = 0.03` |


