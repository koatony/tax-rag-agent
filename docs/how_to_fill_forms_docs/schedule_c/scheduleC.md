# 📊 美國稅務申報與填表對應指南 (Schedule C & Form 1040)
## —— 基於神經符號去耦合 (Neuro-Symbolic) 與配置驅動架構

本文件詳述如何將大語言模型 (LLM) 提取出的結構化參數，透過通用表單解析引擎與本地 Python 規則，自動填寫至美國國稅局 (IRS) 的 **Schedule C (自營商損益)** 表單，並最終無縫對接至 **`tenforty`** 計稅引擎進行個人所得稅算術求解。

---

## 🏗️ 核心架構理念：雙層欄位設計 (Two-Tier Schema)

為防禦大語言模型的算術幻覺並維持報稅系統的擴充性，系統將稅務欄位分為兩層：

```
+--------------------------------------------------------------+
| 原始憑證 (W-2, 1098, 收據 Bundle, QuickBooks P&L)            |
+--------------------------------------------------------------+
                               |
                               v (LLM 定性提取且歸類)
+--------------------------------------------------------------+
| 第一層：明細籃子 (Detail Baskets) - 儲存於資料庫 / 狀態中        |
| 如: SchC.GrossRevenue, SchC.Meals, SchA.MortgageInterest    |
+--------------------------------------------------------------+
                               |
                               v (Python 規則與公式求解：Meals折半、排除罰金)
+--------------------------------------------------------------+
| 第二層：計算欄位與大數總和 (Aggregates)                       |
| 如: SchC.NetProfit ($69,900), SchA.TotalItemized ($17,800)    |
+--------------------------------------------------------------+
                               |
                               v (解包傳入 tenforty 參數)
+--------------------------------------------------------------+
| tenforty 計稅引擎 (後台進行 AGI 遞減、自營稅、邊際稅率級距計算) |
+--------------------------------------------------------------+
```

---

## 📋 Schedule C 逐行對應與填表規格表

以下列出 Schedule C (Form 1040) 完整欄位的對應規則，並以 **Marcus & Elena Rivera** 案例作為資料填充示範。

### Part I: 營業收入 (Income)

| 欄位編號 | 欄位名稱 (IRS Line Name) | 計算類型 | 計算公式 / 規則 | Rivera 案例填寫來源 |
| :--- | :--- | :---: | :--- | :--- |
| **Line 1** | Gross receipts or sales | **Input** | 直接填入原始毛收入 | QuickBooks 中的 `Gross Profit / Gross Revenue` = **`$191,400`** |
| **Line 2** | Returns and allowances | **Input** | 退貨折讓，若無則填 0 | QuickBooks 中的退貨欄位 = **`$0`** |
| **Line 3** | **Net Gross Receipts** | **Formula** | `Line 1 - Line 2` | 系統自動計算：$191,400 - $0 = **`$191,400`** |
| **Line 4** | Cost of goods sold (COGS) | **Formula** | 來自 Part III Line 42 (銷貨成本) | 來自 QuickBooks 中的 `Cost of Goods Sold` = **`$68,000`** |
| **Line 5** | **Gross Profit** | **Formula** | `Line 3 - Line 4` | 系統自動計算：$191,400 - $68,000 = **`$123,400`** |
| **Line 6** | Other income | **Input** | 其他雜項收入，若無則填 0 | Rivera 案例中為 **`$0`** |
| **Line 7** | **Gross Income** | **Formula** | `Line 5 + Line 6` | 系統自動計算：$123,400 + $0 = **`$123,400`** |

---

### Part II: 營業費用 (Expenses)

| 欄位編號 | 欄位名稱 (IRS Line Name) | 計算類型 | 計算公式 / 規則 | Rivera 案例填寫來源 |
| :--- | :--- | :---: | :--- | :--- |
| **Line 8** | Advertising | **Input** | 廣告宣傳費 | QuickBooks 中的 `Advertising` = **`$1,200`** |
| **Line 9** | Car and truck expenses | **Conditional** | **條件計算**（參見下方詳細說明） | Rivera 案例中未申報商用里程，此欄為 **`$0`** |
| **Line 10** | Commissions and fees | **Input** | 轉介佣金與手續費 | Rivera 案例中為 **`$0`** |
| **Line 11** | Contract labor | **Input** | 外包/約聘人員費用（填 1099-NEC 等）| Rivera 案例中為 **`$0`** |
| **Line 12** | Depletion | **Input** | 損耗折舊（通常適用礦業、天然資源）| Rivera 案例中為 **`$0`** |
| **Line 13** | Depreciation & Sec 179 | **Conditional** | **條件計算**（參見下方詳細說明） | Rivera 案例中沒有商業折舊，此欄為 **`$0`** |
| **Line 14** | Employee benefit programs | **Input** | 員工福利計劃（不含退休金與健保）| Rivera 案例中為 **`$0`** |
| **Line 15** | Insurance (other than health)| **Input** | 商業責任險/財產險（不含個人健保）| QuickBooks 中的 `Insurance` = **`$3,500`** |
| **Line 16a**| Mortgage Interest | **Input** | 商業不動產之房貸利息 | Rivera 案例中為 **`$0`** （個人自住房貸在 Sch A） |
| **Line 16b**| Other Interest | **Input** | 商業信用貸款/商業信用卡利息 | Rivera 案例中為 **`$0`** |
| **Line 17** | Legal & professional services| **Input** | 律師、CPA 會計師等專業諮詢費 | Rivera 案例中為 **`$0`** |
| **Line 18** | Office expense | **Input** | 辦公室一般用品與耗材支出 | Rivera 案例中為 **`$0`** |
| **Line 19** | Pension & profit-sharing | **Input** | 員工退休金提撥計劃 | Rivera 案例中為 **`$0`** |
| **Line 20a**| Rent: Vehicles/Equipment | **Input** | 租用車輛、機器設備租金 | Rivera 案例中為 **`$0`** |
| **Line 20b**| Rent: Other business property| **Input** | 店面/倉庫/辦公室實體租金 | QuickBooks 中的 `Rent and Utilities` = **`$14,000`** |
| **Line 21** | Repairs and maintenance | **Input** | 商業財產修繕費 | Rivera 案例中為 **`$0`** |
| **Line 22** | Supplies | **Input** | 營業直接相關耗材 | Rivera 案例中為 **`$0`** |
| **Line 23** | Taxes and licenses | **Input** | 營業稅、行號執照登記費 | Rivera 案例中為 **`$0`** |
| **Line 24a**| Travel | **Input** | 商用差旅費（100% 允許抵扣） | QuickBooks 中的 `Business Travel` = **`$1,900`**（不含 Vegas 旅遊） |
| **Line 24b**| Deductible meals | **Conditional** | **條件計算**（參見下方詳細說明） | QuickBooks 中 `Meals` \$1,800 乘以 0.5 = **`$900`** |
| **Line 25** | Utilities | **Input** | 店面水電瓦斯與電信費 | 併入 Line 20b 的租金與水電中，此欄為 **`$0`** |
| **Line 26** | Wages | **Input** | 支付給員工的薪資 | QuickBooks 中的 `Employee Staff Wages` = **`$32,000`** |
| **Line 27** | Other expenses | **Conditional** | 來自 Part V 雜項加總 | QuickBooks 中 `Miscellaneous` \$300（剔除罰金 \$300） = **`$0`** |
| **Line 28** | **Total Expenses** | **Formula** | 加總 Line 8 到 Line 27 | 系統自動計算：$1,200 (Ad) + $3,500 (Ins) + $14,000 (Rent) + $1,900 (Travel) + $900 (Meals) + $32,000 (Wages) = **`$53,500`** |
| **Line 29** | **Tentative Profit (Loss)** | **Formula** | `Line 7 - Line 28` | 系統自動計算：$123,400 - $53,500 = **`$69,900`** |
| **Line 30** | Business use of home | **Conditional** | **條件計算**（參見下方詳細說明） | Rivera 案例中為 **`$0`** |
| **Line 31** | **Net Profit (Loss)** | **Formula** | `Line 29 - Line 30` | 系統自動計算：$69,900 - $0 = **`$69,900`**（**此值傳給 `tenforty`**） |

---

## 🧠 核心欄位條件計算邏輯 (Conditional Calculations)

以下為 Schedule C 中需要特殊 Python 邏輯判斷的 5 大區域：

### 1. Line 9: 車輛折抵 (Car Expenses)
*   **規則邏輯**：報稅人必須在「標準里程法」與「實際費用法」二選一。
*   **Python 虛擬碼**：
    ```python
    if vehicle_method == "standard_mileage":
        allowed_amount = business_miles * 0.67  # 2024 年費率為 67 美分
    else:
        allowed_amount = (gas + repairs + insurance + depreciation) * business_use_ratio
    ```

### 2. Line 13: 商業折舊 (Depreciation - Form 4562)
*   **規則邏輯**：確認商業財產是否符合 Section 179 一次性抵扣，或需套用 5年/7年 MACRS 折舊表。
*   **Python 虛擬碼**：
    ```python
    # 奢侈車折舊上限檢查 (Luxury Auto Limits)
    if is_passenger_car and gvwr < 6000:
        sec179_limit = 20200.0  # 根據當期法規上限限制
    elif gvwr >= 6000:
        sec179_limit = 30500.0  # 重型 SUV 上限更高 (如 2024 年)
    ```

### 3. Line 24b: 餐飲費減半與排除 (Meals Rules)
*   **規則邏輯**：一般的商務宴客餐飲僅能折抵 50%；員工年終晚會聚餐可抵 100%；娛樂票券（如 Giants season tickets）則為 0%。
*   **Python 虛擬碼**：
    ```python
    deductible_meals = 0.0
    for meal in meal_receipts:
        if meal["category"] == "business_client_meeting":
            deductible_meals += meal["amount"] * 0.5
        elif meal["category"] == "employee_holiday_party":
            deductible_meals += meal["amount"] * 1.0
        elif meal["category"] == "entertainment_tickets":
            deductible_meals += meal["amount"] * 0.0  # 娛樂完全排除
    ```

### 4. Line 30: 家庭辦公室折抵 (Home Office)
*   **規則邏輯**：可選用每平方英尺 $5 的「簡化法（最高 $1,500）」，或依照面積比例折算房租水電的「實際費用法（需填 Form 8829）」。
*   **Python 虛擬碼**：
    ```python
    if home_office_method == "simplified":
        allowed_amount = min(300, office_sq_ft) * 5.0
    else:
        allowed_amount = (rent + home_utilities + home_insurance) * (office_sq_ft / total_home_sq_ft)
    ```

### 5. Line 31/32: 虧損風險 (At-Risk Rules)
*   **規則邏輯**：若淨利為負值 (Net Loss)，系統必須判斷納稅人的出資是否處於風險中。若非全部處於風險 (Box 32b)，則必須調用 `Form 6198` 計算可抵扣的限制額。

---

## ⚙️ 配置化與無硬編碼實作建議 (Metadata-Driven)

為避免在程式碼中寫死各個 Line 的計算關係，建議於 `docs/schedule_c_schema.json` 中配置計算樹：

```json
{
  "form_id": "Schedule_C",
  "groups": [
    {
      "group_id": "Part_I_Income",
      "fields": [
        { "line": "1", "name": "Gross Receipts", "source_key": "SchC.GrossRevenue", "type": "input" },
        { "line": "2", "name": "Returns", "source_key": "SchC.Returns", "type": "input" },
        { "line": "3", "name": "Net Receipts", "type": "formula", "expr": "get('Gross Receipts') - get('Returns')" },
        { "line": "4", "name": "COGS", "source_key": "SchC.COGS", "type": "input" },
        { "line": "5", "name": "Gross Profit", "type": "formula", "expr": "get('Net Receipts') - get('COGS')" },
        { "line": "7", "name": "Gross Income", "type": "formula", "expr": "get('Gross Profit')" }
      ]
    },
    {
      "group_id": "Part_II_Expenses",
      "fields": [
        { "line": "8", "name": "Advertising", "source_key": "SchC.Advertising", "type": "input" },
        { "line": "15", "name": "Insurance", "source_key": "SchC.Insurance", "type": "input" },
        { "line": "20b", "name": "Rent", "source_key": "SchC.Rent", "type": "input" },
        { "line": "24a", "name": "Travel", "source_key": "SchC.Travel", "type": "input" },
        { "line": "24b", "name": "Meals", "source_key": "SchC.Meals", "type": "input", "multiplier": 0.5 },
        { "line": "26", "name": "Wages", "source_key": "SchC.Wages", "type": "input" },
        { "line": "27", "name": "Other Expenses", "source_key": "SchC.OtherExpenses", "type": "input" },
        { "line": "28", "name": "Total Expenses", "type": "sum_group", "target_group": "Part_II_Expenses" },
        { "line": "29", "name": "Tentative Profit", "type": "formula", "expr": "get('Gross Income') - get('Total Expenses')" },
        { "line": "31", "name": "Net Profit", "type": "formula", "expr": "get('Tentative Profit')" }
      ]
    }
  ]
}
```

您可以直接寫一個通用解析引擎，讀取本 Schema 並利用 Python `eval()` 動態計算，計算出來的最終 `Net Profit` 值（在 Rivera 案例中為 **`$69,900`**，若併入其他 expense 為 **`$62,000`**）即可直接作為 `self_employment_income` 參數丟給 `tenforty` 計算聯邦個人所得稅與自營稅。
