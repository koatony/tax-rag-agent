# 📋 IRS Schedule C (Form 1040) 完整填表與計算規則指南 (2025 年度標準版)
## —— 欄位類型定義、底層輸入變數與計算公式邏輯

本文件將國稅局 (IRS) **2025 年版 Schedule C (自營商損益表)** 的所有申報欄位進行完整梳理。本指南特別為**規則引擎開發**進行設計，將每個欄位解構為確定的資料類型、底層輸入變數與計算邏輯：

1. 📥 **Input (直接輸入)**：直接從記帳科目 (如 QuickBooks) 或 W-2/1099 提取的變數，**為 1-to-1 直接對應關係，無底層變數拆解與公式**。
2. 🧮 **Formula (公式加總)**：透過表單內部各行 (Lines) 的數學公式自動計算得出，其變數皆為標準的表單 Line 項目。
3. 🧠 **Conditional (規則條件)**：不能直接對應或簡單計算，必須由外部非標準變數、特定稅法邏輯或輔助表單計算後填入。

---

## 📂 標頭基本資訊 (General Information)

| 欄位編號 | 欄位名稱 (IRS Label) | 類型 | 底層輸入變數 (Underlying Inputs) | 計算/判定公式 (Formula / Logic) | 稅法規定與說明 (IRS Rules & Notes) |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **Name** | Name of proprietor | **Input** | — | — | 獨資經營者的法定姓名（必須與 Form 1040 上的名字一致）。 |
| **SSN** | Social Security Number | **Input** | — | — | 經營者的社會安全號碼或個人納稅人識別號碼 (ITIN)。 |
| **A** | Principal business or profession | **Input** | — | — | 描述主要業務或專業（例如："Retail Pet Supply Store"）。 |
| **B** | Principal Activity Code | **Conditional**| `business_profession` (str) | `NAICS_Lookup(business_profession)` | **業務活動代碼**：根據主營業務文字描述，比對官方行業分類代碼表，映射為 6 位數 NAICS 代碼。 |
| **C** | Business name | **Input** | — | — | 商號/店名。若無獨立商號（如僅個人接案），則留空。 |
| **D** | Employer ID Number (EIN) | **Input** | — | — | 雇主識別號。若無發放 W-2 且無特定申報需求，可留空。 |
| **E** | Business address | **Input** | — | — | 營業地址。如果與居住地址相同，且未申報家庭辦公室，則可留空。 |
| **F** | Accounting method | **Input** | — | — | 選擇會計方法：`"Cash"`（現金制）、`"Accrual"`（應計制）或 `"Other"`（其他）。 |
| **G** | Material participation | **Conditional**| `owner_annual_hours` (float)<br>`is_sole_participant` (bool)<br>`others_annual_hours` (float)<br>`prior_years_participated` (list of int)<br>`is_personal_service_business` (bool)<br>`is_regular_continuous` (bool)<br>`spa_activities_hours` (list of float) | `test1 = owner_annual_hours > 500`<br>`test2 = is_sole_participant`<br>`test3 = owner_annual_hours > 100 and owner_annual_hours >= others_annual_hours`<br>`test4 = sum(h for h in spa_activities_hours if h > 100) > 500`<br>`test5 = count(prior_years_participated in past 10) >= 5`<br>`test6 = is_personal_service_business and count(prior_years_participated) >= 3`<br>`test7 = is_regular_continuous and owner_annual_hours > 100`<br><br>`Line G = (test1 or test2 or test3 or test4 or test5 or test6 or test7)` | **實質參與判定**：勾選 `Yes` 或 `No`。納稅人必須符合 7 項測試之一才能勾選 `Yes`。<br>⚠️ *若勾選 `No`，則適用被動活動虧損規則 (PAL)，虧損需填寫 **Form 8582** 進行限制。* |
| **H** | Started or acquired in 2025 | **Input** | — | — | 如果是在 **2025 年期間**新成立或收購之業務，則勾選此欄。 |
| **I** | Payment requiring Form 1099 | **Conditional**| `contractor_payments` (list of float) | `any(payment >= 600 for payment in contractor_payments)` | **1099 申報義務確認**：年度內向單一獨立承包商/個人支付之累計服務費用是否大於等於 $600。 |
| **J** | Filed or will file Form 1099 | **Conditional**| `line_i_result` (bool)<br>`is_1099_filed` (bool) | `is_1099_filed if line_i_result == True else None` | 若 Line I 勾選 `Yes`，則此欄確認是否已經或將要提交 Form 1099。 |

---

## 📈 Part I: 營業收入 (Income)

> [!IMPORTANT]
> **銷售稅 (Sales Tax) 處理規則**：
> 商家向顧客收取的銷售稅屬於「代收代付」性質，**不應計入 Line 1 的毛收入 (Gross receipts)**，也**不可在 Line 23 作為費用扣除**。若地方政府允許商家保留部分銷售稅作為行政補貼，該保留部分必須列入 **Line 6 (Other income)**。

| 欄位編號 | 欄位名稱 (IRS Line Name) | 類型 | 底層輸入變數 (Underlying Inputs) | 計算/判定公式 (Formula / Logic) | 稅法規定與說明 (IRS Rules & Notes) |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **Line 1** | Gross receipts or sales | **Input** | — | — | 營業毛收入。包含現金、刷卡以及收到的 1099-NEC / 1099-K 等總收入（必須扣除代收銷售稅）。 |
| **Line 2** | Returns and allowances | **Input** | — | — | 退貨折讓與顧客退款（從毛收入中減除）。 |
| **Line 3** | **Net Receipts** | **Formula** | — | `Line 1 - Line 2` | 自動計算。 |
| **Line 4** | Cost of goods sold (COGS) | **Formula** | — | `Line 42` | 來自 **Part III Line 42** 的銷貨成本。 |
| **Line 5** | **Gross Profit** | **Formula** | — | `Line 3 - Line 4` | 自動計算。 |
| **Line 6** | Other income | **Input** | — | — | 其他營業相關雜項收入（例如：保留的銷售稅補貼、聯邦燃油稅抵免退款等）。 |
| **Line 7** | **Gross Income** | **Formula** | — | `Line 5 + Line 6` | 自動計算。 |

---

## 💸 Part II: 營業費用 (Expenses)

> [!WARNING]
> **Line 27a / 27b 跨年度結構對調（極重要）**：
> *   **📅 2025 年申報（本表標準）**：
>     *   **Line 27a** 變更為：**Energy efficient commercial buildings deduction, attach Form 7205**
>     *   **Line 27b** 變更為：**Other expenses from line 48**
> *   **📅 2024 年申報（舊版）**：
>     *   Line 27a 為：Other expenses (Part V Line 48)
>     *   Line 27b 為：Energy efficient commercial buildings deduction (§179D / Form 7205)
> 
> 在自動填寫或規則判定時，必須依據申報稅年度 (Tax Year) 切換 27a/27b 的映射 Key，否則將導致大額費用錯位。

| 欄位編號 | 欄位名稱 (IRS Line Name) | 類型 | 底層輸入變數 (Underlying Inputs) | 計算/判定公式 (Formula / Logic) | 稅法規定與說明 (IRS Rules & Notes) |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **Line 8** | Advertising | **Input** | — | — | 廣告費、宣傳單、網站建立、SEO、本地贊助等推廣費用。 |
| **Line 9** | Car and truck expenses | **Conditional**| `business_miles` (float)<br>`commuting_miles` (float)<br>`personal_miles` (float)<br>`actual_car_expenses` (float)<br>`parking_and_tolls` (float)<br>`selected_mileage_method` (str) | `total_miles = business_miles + commuting_miles + personal_miles`<br>`std_deduction = business_miles * 0.70 + parking_and_tolls`<br>`act_deduction = actual_car_expenses * (business_miles / total_miles)`<br><br>`Line 9 = std_deduction if selected_mileage_method == "standard" else act_deduction` | **車輛折抵費用**。標準里程率 2025 年為 `$0.70/mile`（2024 年為 `$0.67`）。<br>*(⚠️ 車輛資訊必須於 **Part IV** 填寫，前提是該業務不需申報 Form 4562；若需申報 Form 4562，車輛資訊則填寫於 Form 4562 Part V，此處 Part IV 留空*）。 |
| **Line 10** | Commissions and fees | **Input** | — | — | 支付給代理商的銷售佣金與平台服務規費。<br>⚠️ *路由注意：Stripe 手續費與銀行管理費必須被剔除並放到 Line 27b / Part V 中*。 |
| **Line 11** | Contract labor | **Input** | — | — | 支付給獨立承包商 (Independent Contractor) 的報酬（通常需發放 1099-NEC）。 |
| **Line 12** | Depletion | **Input** | — | — | 天然資源（如木材、礦產）的耗竭折舊費用。 |
| **Line 13** | Depreciation & Sec 179 | **Conditional**| `asset_cost` (float)<br>`asset_class_years` (int)<br>`business_use_ratio` (float)<br>`use_sec179` (bool)<br>`net_business_income` (float)<br>`macrs_rate` (float) | `macrs_depr = asset_cost * business_use_ratio * macrs_rate`<br>`sec179_limit = min(asset_cost * business_use_ratio, 1150000, net_business_income)`<br>`sec179_deduction = sec179_limit if use_sec179 else 0`<br><br>`Line 13 = macrs_depr + sec179_deduction` | **營業折舊與 Sec 179 扣除**（需填報 **Form 4562**）。依據 MACRS 折舊表計算，超額 Sec 179 需遞延扣除。 |
| **Line 14** | Employee benefit programs | **Input** | — | — | 員工福利支出（如團體人壽保險、健康保險），但不包括退休計劃。 |
| **Line 15** | Insurance (other than health) | **Input** | — | — | 商業責任險、財產險、員工補償險 (Workers' Comp) 等。不含個人健保。 |
| **Line 16a**| Mortgage Interest | **Input** | — | — | 支付給金融機構的商業不動產抵押貸款利息。 |
| **Line 16b**| Other Interest | **Input** | — | — | 商業信用貸款、信用卡商用利息、設備貸款利息等。 |
| **Line 17** | Legal & professional services | **Input** | — | — | 律師、CPA 會計師、稅務申報與商業諮詢等專業費用。 |
| **Line 18** | Office expense | **Input** | — | — | 辦公室耗材、文具與物流郵資。<br>⚠️ *路由注意：SaaS 訂閱與銀行管理費必須剔除轉至 Line 27b / Part V，不可在此申報*。 |
| **Line 19** | Pension & profit-sharing | **Input** | — | — | 為員工開設的退休金計劃提撥（如 SEP, SIMPLE IRA）。 |
| **Line 20a**| Rent: Vehicles/Equipment | **Input** | — | — | 租用商用車輛、機器、影印機或設備之租金。 |
| **Line 20b**| Rent: Other business property | **Input** | — | — | 實體辦公室、店鋪、倉庫的租金。 |
| **Line 21** | Repairs and maintenance | **Input** | — | — | 營業設備/硬體修繕費（如修冷氣、電腦）。不含大額資產改善。<br>⚠️ *路由注意：清潔費屬於日常開銷，必須剔除轉至 Line 27b / Part V*。 |
| **Line 22** | Supplies | **Input** | — | — | 營業直接耗材（如清潔工具、小零件），不包含在存貨 (COGS) 中。 |
| **Line 23** | Taxes and licenses | **Input** | — | — | **稅金與執照**：可扣商業登記費、商業房產稅、雇主薪資稅 (FICA)。<br>⚠️ *必須剔除聯邦所得稅、個人自營稅與代收的銷售稅*。 |
| **Line 24a**| Travel | **Conditional**| `travel_transit_cost` (float)<br>`travel_lodging_cost` (float)<br>`total_trip_days` (int)<br>`business_days` (int)<br>`is_international` (bool) | `primarily_business = business_days > (total_trip_days - business_days)`<br>`if not is_international:`<br>&nbsp;&nbsp;`transit = travel_transit_cost if primarily_business else 0`<br>&nbsp;&nbsp;`lodging = travel_lodging_cost * (business_days / total_trip_days)`<br>`else:`<br>&nbsp;&nbsp;`if total_trip_days <= 7 or ((total_trip_days - business_days)/total_trip_days) < 0.25:`<br>&nbsp;&nbsp;&nbsp;&nbsp;`transit = travel_transit_cost`<br>&nbsp;&nbsp;`else:`<br>&nbsp;&nbsp;&nbsp;&nbsp;`transit = travel_transit_cost * (business_days / total_trip_days)`<br>&nbsp;&nbsp;`lodging = travel_lodging_cost * (business_days / total_trip_days)`<br><br>`Line 24a = transit + lodging` | **商用差旅費（交通與住宿）**。國內交通費以主要商業目的判定，國外差旅交通費依 7 天 / 25% 個人時間規則判定是否全額扣除或比例分攤。 |
| **Line 24b**| Deductible meals | **Conditional**| `meals_50_pct` (float)<br>`meals_100_pct` (float)<br>`entertainment_cost` (float) | `(meals_50_pct * 0.50) + (meals_100_pct * 1.00) + (entertainment_cost * 0.00)` | **可扣除商務餐飲費**。一般餐飲扣除 50%，員工尾牙聚餐扣除 100%，娛樂活動完全不可扣除 (0%)。 |
| **Line 25** | Utilities | **Input** | — | — | 營業場所的水電瓦斯、網路及商業電話費。 |
| **Line 26** | Wages (less employment credits)| **Conditional**| `w2_gross_wages` (float)<br>`employment_credits` (float)<br>`owner_salary_or_draw` (float) | `w2_gross_wages - employment_credits`（剔除 `owner_salary_or_draw`，將其設為 0） | **員工薪資扣除**。給雇員發放的工資，必須減去適用的抵免額，且絕對不可包含獨資業主自己的薪資或提款。 |
| **Line 27a**| Energy efficient commercial buildings deduction | **Conditional**| `improved_building_sqft` (float)<br>`certified_deduction_rate` (float) | `improved_building_sqft * certified_deduction_rate` | **§179D 節能商業建築扣除額**（需檢附 **Form 7205**）。根據節能效率與 prevailing wage 條件計算扣除率（最高可達每平方英尺 $5.00+）。 |
| **Line 27b**| Other expenses from line 48 | **Formula** | — | `Line 48` | 來自 **Part V Line 48** 的其他費用總額。 |
| **Line 28** | **Total Expenses** | **Formula** | — | `Sum(Line 8 to Line 27b)` | 自動計算。 |
| **Line 29** | **Tentative Profit (Loss)**| **Formula** | — | `Line 7 - Line 28` | 自動計算。 |
| **Line 30** | Business use of home | **Conditional**| `home_office_sqft` (float)<br>`total_home_sqft` (float)<br>`allowable_home_expenses` (float)<br>`is_exclusive_and_regular` (bool)<br>`selected_home_method` (str) | `if not is_exclusive_and_regular: Line 30 = 0`<br>`simplified = min(300, home_office_sqft) * 5.0`<br>`actual = allowable_home_expenses * (home_office_sqft / total_home_sqft)`<br><br>`Line 30 = simplified if selected_home_method == "simplified" else actual` | **家庭辦公室空間折抵**。核心前提是該房屋空間必須為「專用且定期」用於業務，實際費用法需填報 **Form 8829**。 |
| **Line 31** | **Net Profit (Loss)** | **Formula** | — | `Line 29 - Line 30` | **自營利潤/虧損**。傳遞至 Form 1040 Schedule 1 Line 3、Schedule SE，若為信託或遺產則傳至 Form 1041 Line 3。 |
| **Line 32** | **At-Risk Checkboxes** | **Conditional**| `owner_net_loss` (float)<br>`nonrecourse_debt` (float)<br>`guaranteed_non_risk_funding` (float) | `is_fully_at_risk = nonrecourse_debt == 0 and guaranteed_non_risk_funding == 0`<br>`Line 32 = "32a" if is_fully_at_risk else "32b"` | **虧損限制判定**（僅在 Line 31 < 0 時處理）。若勾選 32b，**必須提交 Form 6198** 計算允許扣除額，若 Line G 為 No 還需套用被動活動限制。 |

---

## 🧠 虧損限制與自營稅連動說明 (Downstream Logic)

### 1. 超額業務虧損限制 (Excess Business Loss Limitation)
若 Line 31 計算出淨虧損 (Net Loss)，可能觸發 **Form 461**。在 2025 年度，若申報人業務虧損超過限制額度（**單身申報人超過 $313,000，夫妻聯合申報超過 $626,000**，此金額每年隨通膨調整），超額虧損**不會**反映在 Schedule C 本身，而是必須透過 Form 461 計算後，將超額限制虧損列入 **Form 1040 Schedule 1 (Line 8p)** 作為收入，並轉為下年度的淨營運虧損 (NOL) 結轉。

### 2. 虧損限制與 At-Risk / PAL 的先後順序
若有虧損，計算限制順序為：
$$\text{原始虧損} \xrightarrow{\text{At-Risk 限制 (Form 6198)}} \text{可允許虧損} \xrightarrow{\text{被動活動限制 (Form 8582)}} \text{最終填入 Line 31 的虧損}$$

### 3. 自營稅 (Self-Employment Tax) 的互動關係
Schedule C Line 31 的淨利會轉入 Schedule SE 用以計算自營稅（約 15.3%）。自營稅計算完成後，**自營稅的一半 (One-half of self-employment tax)** 可以在 **Form 1040 Schedule 1 (Line 15)** 作為調整後總所得 (AGI) 的「Above-the-line deduction（線上扣除額）」，**但該扣除額不會回頭減少 Schedule C Line 31 的數值**。

### 💡 2025 稅務新規定特別提醒 (What's New)
> [!NOTE]
> 2025 年新法中新增了關於合格小費 (Qualified Tips) 以及合格加班費 (Qualified Overtime) 的扣除指引。請注意，這些**合格小費與加班費的扣除額應申報於 Form 1040 專用的 Schedule 1-A 中，而非申報在 Schedule C**。系統在提取數據時應防範將其錯報至 Schedule C 營業費用中。

---

## 📦 Part III: 銷貨成本 (Cost of Goods Sold - COGS)

| 欄位編號 | 欄位名稱 (IRS Line Name) | 類型 | 底層輸入變數 (Underlying Inputs) | 計算/判定公式 (Formula / Logic) | 稅法規定與說明 (IRS Rules & Notes) |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **Line 33** | Inventory valuation method | **Input** | — | — | 選擇存貨計價方法：`(a) Cost`、`(b) Lower of cost or market` 或 `(c) Other`。 |
| **Line 34** | Change in valuation | **Input** | — | — | 年度内存貨計價方法是否有變更？若為 `Yes` 需檢附說明。 |
| **Line 35** | Inventory at beginning of year| **Conditional**| `book_beginning_inventory` (float)<br>`prior_year_ending_inventory` (float) | `Line 35 = prior_year_ending_inventory`<br>*(若 book_beginning_inventory != prior_year_ending_inventory，則拋出警告旗標)* | **期初存貨判定**：必須與上一申報年度的期末存貨一致，如果不一致必須檢附說明文件。 |
| **Line 36** | Purchases less personal items | **Input** | — | — | 本期進貨。須扣除業主自用/拿回家的商品成本。 |
| **Line 37** | Cost of labor | **Conditional**| `production_labor_wages` (float)<br>`owner_production_labor_pay` (float) | `production_labor_wages`（剔除 `owner_production_labor_pay`，將其設為 0） | **直接生產人工成本**（僅適用製造/手工業）。絕對不可包含支付給獨資業主自己的薪資。 |
| **Line 38** | Materials and supplies | **Input** | — | — | 直接用於生產、包裝產品的材料與零配件成本。 |
| **Line 39** | Other costs | **Input** | — | — | 其他直接生產成本（如工廠水電、產品運入費 Freight-In）。 |
| **Line 40** | **Total Cost of Goods** | **Formula** | — | `Line 35 + Line 36 + Line 37 + Line 38 + Line 39` | 自動計算。 |
| **Line 41** | Inventory at end of year | **Input** | — | — | 期末實地盤點存貨的成本金額。 |
| **Line 42** | **Cost of Goods Sold** | **Formula** | — | `Line 40 - Line 41` | 銷貨成本，該數值填入 **Part I Line 4**。 |

---

## 🚗 Part IV: 車輛資訊 (Information on Your Vehicle)

> [!IMPORTANT]
> **Part IV 填寫與 Form 4562 的互斥判定邏輯**：
> 1. **申報前提**：只有當您在 **Part II Line 9** 申報了車輛費用時，才需要填寫此部分。
> 2. **與 Form 4562 的關係**：
>    - 如果該業務**不需要**申報 **Form 4562（折舊與攤銷）**，則車輛資訊必須在此處（Schedule C Part IV）申報。
>    - 如果該業務**需要**申報 **Form 4562**（通常是由 **Line 13** 觸發，例如：當年度有購置需折舊的固定資產、申報 Section 179 扣除額、或申報折舊車輛等「列管財產 Listed Property」），則車輛資訊**必須填寫在 Form 4562 的 Part V**，此處（Schedule C Part IV）則留空。

| 欄位編號 | 欄位名稱 (IRS Line Name) | 類型 | 底層輸入變數 (Underlying Inputs) | 計算/判定公式 (Formula / Logic) | 說明與填寫規則 |
| :---: | :--- | :---: | :---: | :---: | :--- |
| **Line 43** | Date placed in service | **Input** | — | — | 車輛首次開始用於商業用途的日期 (MM/DD/YYYY)。 |
| **Line 44a**| Business miles | **Input** | — | — | 本年度商用里程數。 |
| **Line 44b**| Commuting miles | **Input** | — | — | 本年度通勤里程數（⚠️ *通勤里程在美國稅法中屬於個人支出，不能抵稅*）。 |
| **Line 44c**| Other miles | **Input** | — | — | 本年度其他個人/休閒里程數。 |
| **Line 45** | Available for personal use | **Input** | — | — | 在非工作時間，該車輛是否可用於個人用途？勾選 `Yes` 或 `No`。 |
| **Line 46** | Another vehicle available | **Input** | — | — | 您（或配偶）是否有其他車輛可用於個人用途？勾選 `Yes` 或 `No`。 |
| **Line 47a**| Evidence to support deduction | **Input** | — | — | 是否有相關憑證支持您的商用里程申報？勾選 `Yes` 或 `No`。 |
| **Line 47b**| If "Yes," is the evidence written?| **Input** | — | — | 該憑證是否為書面記錄（或電子化記錄）？勾選 `Yes` 或 `No`。 |

---

## 🔍 Part V: 其他營業費用 (Other Expenses)

| 欄位編號 | 欄位名稱 (IRS Line Name) | 類型 | 底層輸入變數 (Underlying Inputs) | 計算/判定公式 (Formula / Logic) | 稅法限制與規則 |
| :---: | :--- | :---: | :--- | :--- | :--- |
| **Line 48** | Total other expenses | **Conditional**| `stripe_merchant_fees` (float)<br>`software_subscriptions` (float)<br>`cleaning_services` (float)<br>`book_amortization` (float)<br>`book_bad_debts` (float)<br>`de_minimis_assets` (list of float)<br>`has_afs_report` (bool)<br>`government_fines` (float)<br>`political_contributions` (float)<br>`other_misc_receipts` (float) | `safe_harbor_limit = 5000 if has_afs_report == True else 2500`<br>`allowable_de_minimis = sum(asset for asset in de_minimis_assets if asset <= safe_harbor_limit)`<br><br>`Line 48 = stripe_merchant_fees + software_subscriptions + cleaning_services + book_amortization + book_bad_debts + allowable_de_minimis + other_misc_receipts`（⚠️ *政府罰金與政治捐贈均強制歸零，不可加總*） | **其他雜項費用總額**（加總轉填至 **Part II Line 27b**）。<br>1. 無 AFS 財務報表者，Tangible Property 安全港上限為單件 $2,500；有者上限為 $5,000。超出部分須移往 Line 13 資本化折舊。<br>2. ⚠️ *絕對不得扣除政府罰單與政治獻金*。 |

---

## 🛠️ LLM 數據提取與稽核方案 (LLM Data Extraction Methods)

為了從原始稅務單據與申報人資料中精準填寫 Schedule C，本系統提供並測試了以下三種 LLM 數據提取架構，並於 UI 分別提供專屬頁面：

### 1. 全部提取法 (Method 1 — All-in-One Box)
*   **檔案名稱**：[pages/schedule_c_box_test.py](file:///home/metaya/tax-rag-agent/pages/schedule_c_box_test.py)
*   **提取邏輯**：將整個 Schedule C 表單的所有 Input 欄位（共 70+ 個）視為單一盒子（Single Box），透過單一 Prompt 與單次 API 呼叫，讓 LLM 一次性提取出所有數值。
*   **優缺點**：
    *   *優點*：呼叫次數最少（僅 1 次 API 請求），耗時極短（通常為 10-20 秒）。
    *   *缺點*：由於欄位數量過多，容易導致 LLM 注意力分散、漏提取，或者對微小數字產生幻覺污染，在超大資料集下精準度較低。

### 2. 逐欄併發提取法 (Method 2 — Line-by-Line Concurrency)
*   **檔案名稱**：[pages/schedule_c_box_test2.py](file:///home/metaya/tax-rag-agent/pages/schedule_c_box_test2.py)
*   **提取邏輯**：將表單中的每個 Input 欄位各自拆分為一個獨立的 LLM 任務，利用 Python `ThreadPoolExecutor` 併發發送。每次呼叫時，LLM 只需專注提取那一個特定欄位。
*   **優缺點**：
    *   *優點*：LLM 專注度達到最高，完全消除了欄位間的注意力干擾，防漏提取與定性分類效果最佳。
    *   *缺點*：API 呼叫次數極多（70+ 次），對 API Rate Limit 壓力巨大，且雖然是併發，但整體流量消耗與平均耗時較高。

### 3. 語意分組併發提取法 (Method 3 — Semantic Grouping Concurrency)
*   **檔案名稱**：[pages/schedule_c_box_test3.py](file:///home/metaya/tax-rag-agent/pages/schedule_c_box_test3.py)
*   **提取邏輯**：將 70+ 個欄位依據稅務語意，精心歸納為 **5 個高關聯性的「語意籃子 (Semantic Baskets)」**：
    1.  *基本資訊與業務屬性組 (General Info & Profile)*
    2.  *營業收入與銷貨成本組 (Revenue & COGS)*
    3.  *營運費用與薪資組 (Operating Expenses & Wages)*
    4.  *車輛、差旅與膳食費組 (Vehicle, Travel & Meals)*
    5.  *折舊、家庭辦公室與雜項費用組 (Depreciation, Home & Other)*
    *   針對每個籃子分別編寫 System Prompt，利用**組內對比注意力**（例如將 Meals 50% 與 100% 放在同組，強制 LLM 做互斥檢查），僅需 5 次併發 API 呼叫即可收斂。
*   **優缺點**：
    *   *優點*：兼顧了「逐欄檢查的高精準度」與「全部提取的低請求數」，大幅降低了 API 額度消耗（僅 5 次請求），同時藉由語意對比有效防範科目錯置（如差旅費與餐飲費誤裝），為目前最推薦之生產環境架構。

