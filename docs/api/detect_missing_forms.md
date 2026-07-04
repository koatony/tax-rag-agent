# 缺失表單偵測 API

根據納稅人申報檔案描述、已上傳文件清單和備註，識別缺失的稅務表單、支持性文件以及任何不一致之處。

* **端點**：`POST /detect-missing-forms`
* **驗證方式**：必須在 Request Header 中夾帶 `X-API-Token`。

---

## 請求參數 (Request Body)

| 參數名稱 | 類型 | 必填 | 說明 |
| :--- | :--- | :--- | :--- |
| `question` | string 或 object | **是** | 包含納稅人申報身份、已上傳文件清單與稅人狀況說明的內容（支援 **純文字** 或 **結構化 JSON 物件**）。 |
| `strategy` | string | 否 | 處理工作流：`"Map-Reduce"` (預設，分塊分析文件清單後彙整) 或 `"Looping"` (使用 Agent 循序推理以進行多輪檢索)。 |
| `model_name` | string | 否 | LLM 評判裁判模型。預設為環境變數 `GEMINI_JUDGE_MODEL` 或 `"gemini-2.5-pro"`。 |

---

## 回應欄位說明 (Response Structure)

| 欄位名稱 | 類型 | 說明 |
| :--- | :--- | :--- |
| `answer` | string | 最終分析報告，摘要所有偵測到的缺失表單與不一致申報項目。 |
| `latency` | float | API 執行耗時（秒）。 |
| `token_usage` | object | LLM Token 耗用量，含 `input_tokens` 與 `output_tokens`。 |
| `debug_info` | object | 詳細的工作流診斷數據，含解析後的 `raw_json`、執行 `strategy`、`model_name` 以及執行步驟紀錄 `debug_steps`。 |

---

## 使用範例

### cURL 指令 (結構化 JSON 物件傳參範例)
```bash
curl -X POST "http://localhost:8088/detect-missing-forms" \
     -H "Content-Type: application/json" \
     -H "X-API-Token: tax-rag-secret-token" \
     -d '{
       "question": {
         "taxpayer_profile": {
           "Name": "Marcus Rivera",
           "Filing Status": "Married Filing Jointly",
           "Tax Year": 2024
         },
         "uploaded_documents": [
           {
             "file_name": "Sample 01 - Marcus Rivera W-2 Data.json",
             "content": {
               "document_type": "W-2 Wage and Tax Statement",
               "boxes": {
                 "box_1_wages_tips_other_compensation": 46000.0
               }
             }
           }
         ]
       },
       "strategy": "Map-Reduce"
     }'
```

### Python 程式碼
```python
import requests

url = "http://localhost:8088/detect-missing-forms"
headers = {
    "Content-Type": "application/json",
    "X-API-Token": "tax-rag-secret-token"
}
payload = {
    "question": "Taxpayer reports Schedule E rental income but has not uploaded the rental statement.",
    "strategy": "Map-Reduce"
}

response = requests.post(url, headers=headers, json=payload)
print(response.json())
```
