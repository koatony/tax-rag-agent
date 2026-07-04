# 系統配置與健康檢查 APIs

提供讀取當前後端配置策略、檢索設定、資料庫連線模式，以及檢查服務健康狀態的端點。

---

## 1. 獲取系統配置 API

返回當前伺服器運行的檢索特徵開關、門檻限制、連線資料庫設定以及活動知識圖譜詳情。

* **端點**：`GET /config`
* **驗證方式**：必須在 Request Header 中夾帶 `X-API-Token`。

### 回應 JSON 範例
```json
{
  "enable_bm25": true,
  "enable_stemming": true,
  "enable_dual_track": true,
  "enable_hyde": true,
  "enable_step_back": true,
  "enable_kg_subgraph": true,
  "enable_source_text": true,
  "enable_table_context": false,
  "enable_recomp": true,
  "enable_sg_pruning": true,
  "use_jina_rerank": true,
  "enable_multi_query": true,
  "multi_query_top_k": 15,
  "vector_threshold": 0.3,
  "active_kgs": [
    "Qdrant+Neo4j(FullP525_0502_600_200)"
  ],
  "mode": "irac",
  "force_english_answer": false,
  "dual_track_boost": 1.4,
  "max_subgraphs": 10,
  "context_strategy": "fixed",
  "context_threshold": 0.8,
  "context_fixed_full_count": 3,
  "context_fixed_sub_count": 7,
  "max_output_tokens": 8192
}
```

---

## 2. 健康檢查 API

快速驗證 FastAPI 伺服器是否正常運行中。

* **端點**：`GET /health`
* **驗證方式**：**無**（公開存取）。

### 回應 JSON 結構
```json
{
  "status": "ok",
  "time": 1719672049.208154
}
```

---

## 使用範例

### cURL 指令 (獲取配置)
```bash
curl -X GET "http://localhost:8088/config" \
     -H "X-API-Token: tax-rag-secret-token"
```

### cURL 指令 (健康檢查)
```bash
curl -X GET "http://localhost:8088/health"
```
