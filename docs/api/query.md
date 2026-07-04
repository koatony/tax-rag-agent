# RAG 查詢 API

提供互動式混合檢索功能（跨 Neo4j 知識圖譜與 Qdrant 向量資料庫），運用 IRAC（問題、法規、應用、結論）邏輯或傳統 Naive RAG 來回答納稅人的稅務問題。

* **端點**：`POST /query`
* **驗證方式**：必須在 Request Header 中夾帶 `X-API-Token`。

---

## 請求參數 (Request Body)

| 參數名稱 | 類型 | 必填 | 說明 |
| :--- | :--- | :--- | :--- |
| `question` | string | **是** | 要諮詢的稅務相關問題。 |
| `active_kgs` | list[str] | 否 | 指定檢索的子集合/工作區名稱。未填時使用伺服器端預設環境變數。 |
| `force_english` | boolean | 否 | 是否強制 LLM 以英文回答。預設為 `false`。 |
| `mode` | string | 否 | 檢索模式：`"irac"` (預設，啟用圖譜推理與規則對齊) 或 `"naive"` (傳統向量相似度檢索)。 |

### 高階檢索策略開關 (可動態覆蓋參數)
您可以在請求 Payload 中夾帶以下布林值，以動態覆蓋伺服器端的預設 RAG 檢索配置：

| 參數名稱 | 類型 | 說明 |
| :--- | :--- | :--- |
| `enable_hyde` | boolean | 啟用/禁用 HyDE (假設性文件嵌入檢索)。 |
| `enable_step_back` | boolean | 啟用/禁用 Step-back (法律問題抽象化改寫檢索)。 |
| `enable_multi_query` | boolean | 啟用/禁用多重查詢擴展變體。 |
| `enable_dual_track` | boolean | 啟用/禁用雙軌檢索 (以事實要件反向檢索法規)。 |
| `enable_bm25` | boolean | 啟用/禁用 BM25 詞頻特徵檢索。 |
| `enable_kg_subgraph` | boolean | 啟用/禁用 Neo4j 知識圖譜子圖鄰居擴展。 |
| `enable_recomp` | boolean | 啟用/禁用節點內容重組 (Recomposition)。 |
| `enable_sg_pruning` | boolean | 啟用/禁用子圖動態剪枝。 |
| `use_jina_rerank` | boolean | 啟用/禁用 Jina AI Rerank 二次排序。 |
| `context_strategy` | string | 上下文截斷策略：`"fixed"` (固定數量) 或 `"threshold"` (分數門檻)。 |
| `context_threshold` | float | `"threshold"` 策略下的最低相關分數門檻 (例如 `0.8`)。 |
| `context_fixed_full_count`| integer | 保留完整區段 (Full Chunk) 的固定數量上限。 |
| `context_fixed_sub_count` | integer | 保留子圖結構 (Subgraph) 的固定數量上限。 |
| `max_subgraphs` | integer | 限制檢索的最大 Neo4j 子圖數量。 |
| `vector_threshold` | float | 向量相似度的過濾門檻。 |
| `dual_track_boost` | float | 雙軌檢索命中的加權乘數。 |

---

## 回應欄位說明 (Response Structure)

| 欄位名稱 | 類型 | 說明 |
| :--- | :--- | :--- |
| `answer` | string | LLM 產生的最終稅務解答。 |
| `context` | string | 最終餵給 LLM 作為 Prompt Context 的原始段落文字。 |
| `latency` | float | 本次 API 呼叫的總耗時（秒）。 |
| `token_usage` | object | LLM Token 耗用量，含 `input_tokens` 與 `output_tokens`。 |
| `rule_candidates`| list[object] | 檢索出的法規候選清單，包含分數、分層與檢索路徑。 |
| `debug_info` | object | 後台核心診斷數據。 |

### 法規候選物件 (Rule Candidate Details)
* **`tier`**：分層層級 (`1` = 完整子圖+壓縮原始文字, `2` = 僅子圖結構, `3` = 僅法規名稱與摘要)。
* **`rule_id`**：法規在 Neo4j 中的節點名稱。
* **`rule_description`**：法規文字描述或條文內容。
* **`final_score`**：經二次排序 (Rerank) 後的最終相關得分。
* **`initial_score`**：進行 Rerank 前的原始加權得分。
* **`sources`**：觸發此法規的檢索路徑來源清單 (例如 `"Law_Original"`, `"Law_StepBack"`, `"Law_HyDE"`, `"Fact_Reverse"`)。
* **`is_dual_hit`**：是否同時經由「法規搜尋+事實反查」雙軌命中。

---

## 使用範例

### cURL 指令
```bash
curl -X POST "http://localhost:8088/query" \
     -H "Content-Type: application/json" \
     -H "X-API-Token: tax-rag-secret-token" \
     -d '{
       "question": "公司提供的病假工資需要申報個人所得稅嗎？",
       "mode": "irac",
       "use_jina_rerank": true
     }'
```

### Python 程式碼
```python
import requests

url = "http://localhost:8088/query"
headers = {
    "Content-Type": "application/json",
    "X-API-Token": "tax-rag-secret-token"
}
payload = {
    "question": "Is sick pay taxable?",
    "mode": "irac",
    "force_english": True
}

response = requests.post(url, headers=headers, json=payload)
print(response.json())
```
