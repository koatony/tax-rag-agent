# Tax RAG API 文件目錄

歡迎使用 Tax RAG API 文件。本目錄包含系統公開之每個 API 端點的詳細說明、請求/回應模型以及使用範例。

## 基礎 URL
* **開發/測試環境**：`http://localhost:8088`

## 安全驗證
所有請求（`/health` 除外）皆必須在 HTTP Header 中夾帶自訂驗證憑證：
* **Header 名稱**：`X-API-Token`
* **Header 數值**：必須與 `.env` 設定檔中設定的 `INTERNAL_TOKEN` 一致（預設防禦回退值為 `tax-rag-secret-token`）。
* **未授權回應**：未夾帶此標頭或數值錯誤，將回傳 `403 Forbidden`。

---

## API 端點索引

### 🔍 核心檢索與缺失表單偵測
* [核心 RAG 查詢 API (`POST /query`)](query.md) — 支援動態檢索策略控制的稅務問答接口。
* [缺失表單偵測 API (`POST /detect-missing-forms`)](detect_missing_forms.md) — 藉由納稅人檔案與文件清單分析缺失表單及稅務申報不一致之接口。

### ⚙️ 系統運行配置
* [系統配置與健康檢查 (`GET /config`, `GET /health`)](config.md) — 獲取當前運行的特徵開關、資料庫模式與服務狀態。

### 🧮 互動式稅務提取並試算 (一鍵式處理)
* [Schedule A 提取並試算 API (`POST /schedule-a/extract-and-calculate`)](schedule_a.md) — 傳入未結構化文件與納稅人檔案，提取並試算逐項扣除額。
* [Schedule B 提取並試算 API (`POST /schedule-b/extract-and-calculate`)](schedule_b.md) — 傳入未結構化文件與納稅人檔案，提取並試算利息與普通股利。
* [Schedule C 提取並試算 API (`POST /schedule-c/extract-and-calculate`)](schedule_c.md) — 傳入未結構化文件與納稅人檔案，提取並試算自營職業利潤與虧損。
* [Schedule E 提取並試算 API (`POST /schedule-e/extract-and-calculate`)](schedule_e.md) — 傳入未結構化文件與納稅人檔案，提取並試算租賃房地產淨利潤與虧損。

### 📄 文件 Facts 提取與表單映射 (兩步驟處理)
* [Schedule A 扣除額映射 (`POST /schedule-a/deductions/extract-and-map`)](schedule_a_deductions.md) — 從捐贈收據、1098 房貸表單中提取事實並映射至 Schedule A 行號。
* [Schedule D 損失結轉映射 (`POST /schedule-d/carryover/extract-and-map`)](schedule_d_carryover.md) — 從上年度申報 summary 中提取資本損失結轉並映射至 Schedule D 行號。
* [Schedule E 租賃收入映射 (`POST /schedule-e/rental/extract-and-map`)](schedule_e_rental.md) — 從租賃房產收支單中提取事實並映射至 Schedule E 行號。
* [Form 1040 Wages 薪資映射 (`POST /form-1040/wages/extract-and-map`)](form_1040_wages.md) — 從 W-2 表單中提取薪資並彙整 Form 1040 Line 1a 總額。
