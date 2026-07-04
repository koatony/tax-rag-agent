"""
RAG 流程節點 (LangGraph Nodes)
==============================
將檢索流程中的每個處理階段封裝為獨立函數，並加入詳細的中文註解。
"""

import os
import json
import re
import numpy as np
import httpx
from typing import Any, Dict, List
from langchain_core.messages import HumanMessage, SystemMessage
from data_models import RetrievalState, RetrieverConfig, RuleCandidate, IRACSubgraph, NodeInfo
from kg_manager import KGIndex, VectorIndex
from graph_builder import SubgraphBuilder
import prompts as P

def _extract_usage(response: Any) -> dict:
    """提取 LLM 響應中的 token 使用量資訊"""
    usage = getattr(response, "usage", {})
    return {
        "input_tokens": usage.get("promptTokenCount", 0),
        "output_tokens": usage.get("candidatesTokenCount", 0)
    }

def translate_and_decompose_query(state: RetrievalState, llm: Any) -> Dict:
    """
    [查詢預處理] 
    1. 進行領域偵測 (OOD Gatekeeper): 判斷問題是否與美國稅法相關。
    2. 概念翻譯 (Semantic Translation): 將口語化的描述轉換為 IRS 專業法律術語，提升檢索精準度。
    """
    query = state["query"]
    prompt = P.DECOMPOSE_QUERY_PROMPT.format(query=query)
    try:
        resp = llm.invoke([HumanMessage(content=prompt)], response_mime_type="application/json")
        usage = _extract_usage(resp)
        text = resp.content
        # 尋找 JSON 區塊
        content = text
        if "```json" in text:
            content = text.split("```json")[-1].split("```")[0]
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1:
            content = content[start:end+1]
        
        res = json.loads(content)
        return {
            "is_tax_related": res.get("is_tax_related", True),
            "reject_reason": res.get("reject_reason") or P.REJECT_REASON_ZH,
            "rule_query": res.get("rule_query", query),
            "fact_query": res.get("fact_query", query),
            "keywords": res.get("keywords", []),
            "debug_info": {
                "query_decomposed": True,
                "rule_query": res.get("rule_query", query),
                "fact_query": res.get("fact_query", query),
                "keywords": res.get("keywords", [])
            },
            "token_usage": usage
        }
    except Exception as e:
        print(f"[Warning] 查詢拆解失敗: {e}")
        return {"is_tax_related": True, "rule_query": query, "fact_query": query, "keywords": query.split()}

def hyde_generate(state: RetrievalState, llm: Any, config: RetrieverConfig) -> Dict:
    """
    [增強查詢] 
    透過 Step-Back Prompting 生成抽象的法律概念，或透過 HyDE 生成假設性答案。
    這有助於在知識圖譜中定位到正確的法規層級。
    """
    if not state.get("is_tax_related", True): return {}
    query, bundle = state["query"], {"original": state["query"]}
    debug_info = {}

    cumulative_usage = {"input_tokens": 0, "output_tokens": 0}

    enable_step_back = state.get("enable_step_back") if state.get("enable_step_back") is not None else config.enable_step_back
    enable_hyde = state.get("enable_hyde") if state.get("enable_hyde") is not None else config.enable_hyde
    enable_multi_query = state.get("enable_multi_query") if state.get("enable_multi_query") is not None else config.enable_multi_query

    if enable_step_back or enable_multi_query:
        prompt = P.STEP_BACK_PROMPT.format(query=query)
        try:
            resp = llm.invoke([HumanMessage(content=prompt)])
            usage = _extract_usage(resp)
            cumulative_usage["input_tokens"] += usage["input_tokens"]
            cumulative_usage["output_tokens"] += usage["output_tokens"]
            bundle["step_back"] = resp.content.strip()
            debug_info["step_back_generated"] = True
        except: pass

    if enable_hyde or enable_multi_query:
        prompt = P.HYDE_PROMPT.format(query=query)
        try:
            resp = llm.invoke([HumanMessage(content=prompt)])
            usage = _extract_usage(resp)
            cumulative_usage["input_tokens"] += usage["input_tokens"]
            cumulative_usage["output_tokens"] += usage["output_tokens"]
            bundle["hyde"] = resp.content.strip()
            debug_info["hyde_generated"] = True
        except: pass
    
    # 根據配置決定主查詢句
    debug_info["query_bundle"] = bundle
    updates = {"query_bundle": bundle, "debug_info": debug_info}
    if not enable_multi_query and "step_back" in bundle:
        updates["rule_query"] = bundle["step_back"]
        updates["fact_query"] = bundle["step_back"]
        
    updates["token_usage"] = cumulative_usage
    return updates

def track_a_rule_search(state: RetrievalState, rule_index: VectorIndex, config: RetrieverConfig) -> Dict:
    """
    [路徑 A: 法規搜尋] 
    直接在法規 (Rule) 節點庫中搜尋最接近的條款。
    支援多重查詢融合 (Multi-Query Fusion)。
    """
    if not state.get("is_tax_related", True): return {"rule_track_hits": []}
    
    enable_multi_query = state.get("enable_multi_query") if state.get("enable_multi_query") is not None else config.enable_multi_query
    queries = state.get("query_bundle", {"default": state.get("rule_query", state["query"])})
    top_k = config.multi_query_top_k if enable_multi_query else 30
    
    # all_hits: 最終合併後的結果。格式為 { "法規ID": 最高加權分數 }
    # 用於將多個查詢版本的結果「去重 (Deduplicate)」並取「最高分」作為最終排序依據。
    all_hits = {}

    # track_a_hits_by_query: 追蹤用的紀錄。格式為 { "查詢類型": [法規ID, 法規ID, ...] }
    # 專門用來記錄「Original 搜到了誰」、「HyDE 搜到了誰」，方便後續 debug 與前端顯示來源。
    track_a_hits_by_query = {}

    for q_type, q_text in queries.items():
        # 執行混合搜尋 (向量 + 關鍵字)
        # hits 的格式是 List[Tuple[ID, 分數]]，例如: [("rule_1", 0.85), ("rule_2", 0.72)]
        hits = rule_index.search(q_text, keywords=state.get("keywords"), top_k=top_k)
        
        # 1. 紀錄此查詢版本搜到的所有 ID (用於 debug_info)
        rids = [h[0] for h in hits]
        track_a_hits_by_query[q_type] = rids
        
        # 2. 進行「分數融合 (Fusion)」：將不同版本搜到的同一條法規進行合併
        # 給予原始提問 (original) 較高的加權權重 (1.5倍)
        weight = 1.5 if q_type == "original" else 1.0
        for rid, score in hits:
            # 如果這條法規在不同版本中都有出現，我們保留加權後的「最高分」
            all_hits[rid] = max(all_hits.get(rid, 0), score * weight)

    # 將統計資訊塞進 debug_info 中，方便 API 調試
    debug_info = state.get("debug_info", {})
    debug_info["rule_search_hit_count"] = len(all_hits)
    debug_info["rule_hits_by_query"] = track_a_hits_by_query

    # 回傳格式化後的結果給 LangGraph 狀態
    return {"rule_track_hits": [{"id": rid, "score": s} for rid, s in all_hits.items()], "debug_info": debug_info}

def track_b_fact_search(state: RetrievalState, fact_index: VectorIndex, kg: KGIndex, config: RetrieverConfig) -> Dict:
    """
    [路徑 B: 事實反查] 
    搜尋與使用者情境相似的「事實要件」(Material Fact)，再透過圖譜關係反查該事實適用的法規。
    """
    enable_dual_track = state.get("enable_dual_track") if state.get("enable_dual_track") is not None else config.enable_dual_track
    if not state.get("is_tax_related", True) or not enable_dual_track:
        return {"fact_track_hits": []}
        
    q = state.get("fact_query", state["query"])
    hits = fact_index.search(q, keywords=state.get("keywords"), top_k=30)
    
    fact_hits = []
    track_b_rules_by_query = {"fact_track": []}
    for fid, score in hits:
        # 🔑 解析事實 ID (雜湊 -> 名稱)
        resolved_fid = fact_index.get_name(fid)
        
        # 取得與此事實相連的法規
        rules = []
        # 注意：如果是 Local 模式使用 _adj_undirected，Neo4j 模式則需另外處理或統一使用 get_neighbors
        neighbors = kg.get_neighbors(resolved_fid, direction="both")
        for nb, rel in neighbors:
            if nb.entity_type == "rule":
                rules.append({"rule_id": nb.entity_id, "score": score})
                if nb.entity_id not in track_b_rules_by_query["fact_track"]:
                    track_b_rules_by_query["fact_track"].append(nb.entity_id)
        
        fact_hits.append({"fact_id": fid, "resolved_id": resolved_fid, "fact_score": score, "connected_rules": rules})
    
    debug_info = state.get("debug_info", {})
    debug_info["fact_search_hit_count"] = len(fact_hits)
    debug_info["fact_mapped_rules_by_query"] = track_b_rules_by_query

    return {"fact_track_hits": fact_hits, "debug_info": debug_info}

def merge_candidates(state: RetrievalState, kg: KGIndex, config: RetrieverConfig) -> Dict:
    """
    [合併與加權] 
    融合 A、B 兩條軌道的結果。
    """
    candidates = {}
    boost = config.dual_track_boost
    
    # 這裡的 rid 可能是雜湊 (Track A 來自 rule_index)
    for h in state["rule_track_hits"]:
        rid = h["id"]
        # 嘗試直接拿 ID 或透過名稱拿節點
        # 注意：IRACRetriever 已經確保 VectorIndex.build() 時載入了名稱對照
        node = kg.get_node(rid) 
        if not node:
            # Fallback: 如果是雜湊，嘗試解析名稱後再拿一次
            # 這裡需要傳入 index，但 merge_candidates 的簽名沒給。
            # 不過如果 kg.get_node 本身就支援名稱 (Neo4j)，那就沒問題。
            pass
            
        if node:
            actual_rid = node.entity_id
            if actual_rid not in candidates: 
                candidates[actual_rid] = RuleCandidate(actual_rid, node, dual_track_boost=boost)
            candidates[actual_rid].score_from_rule_track = h["score"]
    
    for h in state["fact_track_hits"]:
        for r in h["connected_rules"]:
            rid = r["rule_id"]
            node = kg.get_node(rid)
            if node:
                actual_rid = node.entity_id
                if actual_rid not in candidates: 
                    candidates[actual_rid] = RuleCandidate(actual_rid, node, dual_track_boost=boost)
                candidates[actual_rid].score_from_fact_track = max(candidates[actual_rid].score_from_fact_track, h["fact_score"])
                if h["fact_id"] not in candidates[actual_rid].matched_fact_ids: 
                    candidates[actual_rid].matched_fact_ids.append(h["fact_id"])
    
    sorted_c = sorted(candidates.values(), key=lambda x: x.final_score, reverse=True)
    
    # 計算來源標記 (為了追蹤每一條候選法規是從哪個搜尋路徑來的)
    # track_a_hits 格式: { "original": [id1, id2], "hyde": [id3] }
    track_a_hits = state.get("debug_info", {}).get("rule_hits_by_query", {})
    # track_b_rules 格式: { "fact_track": [id1, id4] }
    track_b_rules = state.get("debug_info", {}).get("fact_mapped_rules_by_query", {})
    
    # 將物件清單轉換為字典清單，並標註每條法規的搜尋來源 (Source Tagging)
    output_candidates = []
    for c in sorted_c:
        rid = c.rule_id
        sources = []
        # 對應問題類型與前端顯示標籤
        name_map = {"original": "Law_Original", "step_back": "Law_StepBack", "hyde": "Law_HyDE"}
        
        # 1. 檢查是否來自路徑 A (直接搜尋) 的某個查詢版本
        for q_type, rids in track_a_hits.items():
            if rid in rids: 
                sources.append(name_map.get(q_type, f"Law_{q_type.upper()}"))
        
        # 2. 檢查是否來自路徑 B (事實反查)
        for q_type, rids in track_b_rules.items():
            if rid in rids: 
                sources.append("Fact_Reverse")
        
        # 3. 執行格式轉換與資訊補強
        c_dict = c.to_dict()
        c_dict["sources"] = sources             # 注入剛才打好的來源標籤
        c_dict["initial_score"] = c.final_score # 紀錄融合後的初始分數
        c_dict["_candidate_obj"] = c            # 保留原始物件供後續節點 (如建構子圖) 使用
        output_candidates.append(c_dict)

    return {"rule_candidates": output_candidates}

def rerank_candidates(state: RetrievalState, llm: Any, embed_model: Any, config: RetrieverConfig) -> Dict:
    """
    [精準重排序] 
    使用 Jina Reranker v3 或 LLM 做為 Cross-Encoder，對 Top 候選進行二次排序。
    新增：P1-4 負分過濾與 P1-3 主題一致性過濾。
    """
    if not state.get("is_tax_related", True) or not state["rule_candidates"]: return {}
    candidates = state["rule_candidates"][:45]
    query = state["query"]
    
    debug_info = state.get("debug_info", {})
    if config.use_jina_rerank and config.jina_api_key:
        try:
            url = "https://api.jina.ai/v1/rerank"
            headers = {"Authorization": f"Bearer {config.jina_api_key}", "Content-Type": "application/json"}
            data = {"model": "jina-reranker-v3", "query": query, "top_n": 15, "documents": [c["rule_description"] for c in candidates]}
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(url, headers=headers, json=data)
                resp.raise_for_status()
                rank_res = resp.json().get("results", [])
                reranked = []
                for item in rank_res:
                    if item["relevance_score"] < 0.0:
                        continue # P1-4: 強化負分過濾
                    cand = candidates[item["index"]]
                    # 保留原始分數，並記錄 Rerank 分數
                    cand["rerank_score"] = item["relevance_score"]
                    cand["final_score"] = item["relevance_score"] # 用於最終排序
                    reranked.append(cand)
                
                # P1-3: 主題一致性過濾 (Topic Coherence Filter)
                try:
                    q_vec = np.array(embed_model.embed_query(state.get("rule_query", query)))
                    q_vec /= (np.linalg.norm(q_vec) + 1e-9)
                    
                    topic_filtered = []
                    for cand in reranked:
                        c_vec = np.array(embed_model.embed_query(cand["rule_description"]))
                        c_vec /= (np.linalg.norm(c_vec) + 1e-9)
                        sim = float(q_vec @ c_vec)
                        
                        # 若相似度過低，代表可能被某些關鍵字（如 Clergy）磁吸，但主題完全不符
                        if sim >= 0.40:
                            cand["topic_coherence"] = sim
                            topic_filtered.append(cand)
                        else:
                            print(f"  [TopicFilter] 剔除低關聯節點: {cand['rule_id']} (sim: {sim:.3f})")
                    
                    reranked = topic_filtered
                except Exception as e:
                    print(f"  [TopicFilter] Failed: {e}")

                debug_info["rerank_method"] = "jina-v3"
                debug_info["reranked"] = True
                debug_info["top_15_ids"] = [c["rule_id"] for c in reranked]
                
                return {"rule_candidates": reranked, "debug_info": debug_info}
        except Exception as e:
            print(f"  [JinaRerank] Failed: {e}")
            pass
    
    return {"rule_candidates": candidates, "debug_info": debug_info}

def build_subgraphs(state: RetrievalState, builder: SubgraphBuilder, config: RetrieverConfig) -> Dict:
    """
    [推理子圖建構] 
    為排序後的法規建構 IRAC 子圖。現在數量由 config.max_subgraphs 控制。
    """
    # 從排序後的候選人中取前 N 名建立子圖
    cands = state["rule_candidates"][:config.max_subgraphs]
    
    # 優先使用 state 中的設定，若無則使用全域 config
    current_mode = state.get("mode", config.mode)
    
    if current_mode == "naive":
        # [True Naive] 不進行圖譜走訪，僅保留核心法規節點資訊
        sgs = [{"rule": c["_candidate_obj"].rule_info.to_dict(), "issues": [], "facts": [], "conclusions": [], "regulations": []} 
               for c in cands if "_candidate_obj" in c]
    else:
        # [IRAC Mode] 正常進行圖譜關係擴展，建構結構化的推理子圖
        sgs = [builder.build(c["_candidate_obj"]).to_dict() for c in cands if "_candidate_obj" in c]
        
    return {"subgraphs": sgs, "debug_info": {"subgraphs_built": len(sgs)}}

def fetch_source_text(state: RetrievalState, kg: KGIndex, config: RetrieverConfig) -> Dict:
    """
    [原始文本檢索] 
    從 kv_store 獲取 PDF 原始文本，供「Sniper Injection」細節比對使用。
    """
    sids = {sg["rule"]["source_id"] for sg in state["subgraphs"] if sg["rule"]["source_id"]}
    text_db = getattr(kg, "text_chunks", {})
    chunks = [{"id": sid, "content": text_db[sid]["content"]} for sid in sids if sid in text_db]
    return {"source_chunks": chunks}

def _recomp_compress(text: str, query: str, embed_model: Any, max_sentences: int = 6) -> str:
    """[RECOMP] 句子級文本壓縮：僅保留與問題最相關的句子。"""
    raw_sentences = re.split(r'(?<=[.!?])\s+|\n{2,}', text.strip())
    sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 20]
    if not sentences: return text[:1000]
    try:
        q_vec = np.array(embed_model.embed_query(query))
        q_vec /= (np.linalg.norm(q_vec) + 1e-9)
        scored = []
        for s in sentences:
            s_vec = np.array(embed_model.embed_query(s))
            s_vec /= (np.linalg.norm(s_vec) + 1e-9)
            scored.append((float(q_vec @ s_vec), s))
        scored.sort(reverse=True)
        return " ".join([s for _, s in scored[:max_sentences]])
    except: return text[:1000]

def assemble_context(state: RetrievalState, config: RetrieverConfig, embed_model: Any) -> Dict:
    """
    [上下文組裝] 
    融合 IRAC 子圖結構與壓縮後的原始文本。
    採用分層策略 (Tiered Context) 以優化 Token 使用與回答品質。
    """
    force_en = state.get("force_english", config.force_english_answer)
    if not state.get("is_tax_related", True): 
        msg = P.EMPTY_CONTEXT_EN if force_en else P.EMPTY_CONTEXT_ZH
        return {"context": msg}

    parts = []
    source_map = {c["id"]: c["content"] for c in state.get("source_chunks", [])}
    query = state["query"]
    candidates = state["rule_candidates"]
    # 建立子圖查找表，方便快速匹配
    subgraph_map = {sg["rule"]["entity_id"]: sg for sg in state.get("subgraphs", [])}
    
    # 用於 Debug 的分層統計
    tier_stats = {"tier1": 0, "tier2": 0, "tier3": 0}

    for i, c in enumerate(candidates):
        rid = c["rule_id"]
        # Jina Rerank 傳回的分數 (如果是 naive 模式可能沒有分數，預設為 1.0)
        score = c.get("final_score", 1.0 if i == 0 else 0.0) 
        
        # --- 判定分層 (Tier Detection) ---
        tier = 3 # 預設為最低層級 (僅標題摘要)
        
        # 獲取動態策略參數
        c_strategy = state.get("context_strategy") or config.context_strategy
        c_threshold = state.get("context_threshold") if state.get("context_threshold") is not None else config.context_threshold
        c_full_count = state.get("context_fixed_full_count") if state.get("context_fixed_full_count") is not None else config.context_fixed_full_count
        c_sub_count = state.get("context_fixed_sub_count") if state.get("context_fixed_sub_count") is not None else config.context_fixed_sub_count

        if c_strategy == "threshold":
            # [模式 A] 門檻模式：根據 Rerank 分數決定是否給予最高火力
            if score >= c_threshold:
                tier = 1
            elif rid in subgraph_map:
                tier = 2
        else:
            # [模式 B] 固定數量模式：根據排名 Index 決定分層
            if i < c_full_count:
                tier = 1
            elif i < (c_full_count + c_sub_count):
                tier = 2
            else:
                tier = 3
        
        # 將判定結果直接寫回 candidate，方便 API 串接
        c["tier"] = tier
        
        # --- 根據分層組裝內容 ---
        if tier == 1 and rid in subgraph_map:
            # Tier 1: 完整 IRAC 子圖 + RECOMP 壓縮原文 (資訊最豐富)
            sg_obj = IRACSubgraph.from_dict(subgraph_map[rid])
            text = sg_obj.to_context_text()
            if config.enable_recomp and sg_obj.rule.source_id in source_map:
                compressed = _recomp_compress(source_map[sg_obj.rule.source_id], query, embed_model)
                text += P.DETAILED_SOURCE_TEXT_TEMPLATE.format(compressed=compressed)
            parts.append(P.CANDIDATE_FULL_TEMPLATE.format(index=i+1, text=text))
            tier_stats["tier1"] += 1
        elif tier <= 2 and rid in subgraph_map:
            # Tier 2: 僅顯示圖譜邏輯結構 (不含原文片段，精簡 Token)
            sg_obj = IRACSubgraph.from_dict(subgraph_map[rid])
            text = sg_obj.to_context_text()
            parts.append(P.CANDIDATE_SUBGRAPH_TEMPLATE.format(index=i+1, text=text))
            tier_stats["tier2"] += 1
        else:
            # Tier 3: 僅提供參考用的標題與摘要 (確保 LLM 知道有這條法規)
            parts.append(P.CANDIDATE_REFERENCE_TEMPLATE.format(
                index=i+1, rule_id=rid, description=c["rule_description"]
            ))
            tier_stats["tier3"] += 1

    if not parts:
        msg = P.EMPTY_CONTEXT_EN if force_en else P.EMPTY_CONTEXT_ZH
        return {"context": msg}

    # 將所有策略與統計資訊統一匯總到一個結構化欄位中
    debug_info = state.get("debug_info", {})
    retrieval_summary = {
        "strategy": config.context_strategy,
        "mode": config.mode,
        "rerank_method": debug_info.get("rerank_method", "None"),
        "tier_stats": tier_stats,
        "subgraphs_built": len(state.get("subgraphs", []))
    }
    debug_info["retrieval_summary"] = retrieval_summary

    return {"context": "\n\n".join(parts), "debug_info": debug_info}

def fetch_table_data(state: RetrievalState) -> Dict:
    """[表格獲取] 模擬或是真實從 OCR 模組取得表格資料。"""
    mock_table = {"note": "OCR Table Context for calculation rules."}
    return {"table_context": json.dumps(mock_table, ensure_ascii=False)}

def generate_answer(state: RetrievalState, llm: Any, config: RetrieverConfig) -> Dict:
    """
    [模型回答] 
    根據最終組裝出的 Context 向使用者提供詳細的稅務建議。
    """
    # 優先使用 state 中的設定，若無則使用全域 config
    force_en = state.get("force_english", config.force_english_answer)
    print(f"  [DEBUG] Generate Answer: force_english={force_en}")

    if not state.get("is_tax_related", True): 
        default_reject = P.REJECT_REASON_EN if force_en else P.REJECT_REASON_ZH
        return {"answer": state.get("reject_reason") or default_reject}
    
    if force_en:
        system_prompt = P.ANSWER_SYSTEM_PROMPT_EN
        prompt = f"Context:\n{state['context']}\n\nQuestion: {state['query']}"
    else:
        system_prompt = P.ANSWER_SYSTEM_PROMPT
        prompt = f"Context:\n{state['context']}\n\nQuestion: {state['query']}"
    
    # 將最終完整送出的 Prompt 記錄在 debug_info 中 (包含 System 與 Human 內容)
    debug_info = state.get("debug_info", {})
    debug_info["full_prompt_sent"] = (
        f"--- SYSTEM PROMPT ---\n{system_prompt}\n\n"
        f"--- HUMAN PROMPT (Questions + Context) ---\n{prompt}"
    )

    resp = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=prompt)])
    usage = _extract_usage(resp)
    
    return {"answer": resp.content, "debug_info": debug_info, "token_usage": usage}
