"""
IRAC 檢索框架 (模組化版本)
==============================
此檔案現在做為框架入口與 Facade，匯集所有模組化組件。
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

# 從模組化組件匯入 (Re-export 以維持向下相容)
from data_models import (
    RetrieverConfig, NodeInfo, EdgeInfo, RuleCandidate, 
    IRACSubgraph, RetrievalState, merge_dicts
)
from llm_wrappers import OllamaEmbeddings, GeminiLLM, OllamaLLM
from kg_manager import KGIndex, VectorIndex, QdrantVectorIndex
from graph_builder import SubgraphBuilder
from rag_nodes import (
    translate_and_decompose_query, hyde_generate, track_a_rule_search,
    track_b_fact_search, merge_candidates, rerank_candidates,
    build_subgraphs, fetch_source_text, assemble_context,
    fetch_table_data, generate_answer
)

from langgraph.graph import StateGraph, END

# 路徑配置
# __file__: 代表目前這個檔案 (retriever.py) 的路徑
# .resolve(): 將路徑轉為「絕對路徑」(從最頂層 / 開始，並解析所有符號連結)
# .parent: 取得該檔案所在的「資料夾」(即專案根目錄)
root_dir = Path(__file__).resolve().parent
# 在專案根目錄下尋找名為 "data" 的資料夾
data_dir = root_dir / "data"

def make_retrieval_graph(
    kg: KGIndex,
    rule_index: VectorIndex,
    fact_index: VectorIndex,
    subgraph_builder: SubgraphBuilder,
    llm: Any,
    embedding_model: Any,
    config: RetrieverConfig = None,
    utility_llm: Any = None,
    **kwargs
):
    """建立 RAG 的 LangGraph 狀態機"""
    import time
    cfg = config or RetrieverConfig()
    util_llm = utility_llm or llm
    builder = StateGraph(RetrievalState)

    # 輔助計時器：包裝節點函數，計算執行時間並存入 debug_info
    def timed_node(name, func):
        def wrapper(state):
            t0 = time.time()
            res = func(state) or {}
            latency = time.time() - t0
            
            # 確保有 debug_info 字典
            if "debug_info" not in res:
                res["debug_info"] = {}
            
            # 記錄該節點的耗時 (單位：秒)
            res["debug_info"][f"latency_{name}"] = round(latency, 3)
            return res
        return wrapper

    # 註冊節點 (Nodes) - 全部包裝計時器
    builder.add_node("decompose_query",      timed_node("decompose", lambda s: translate_and_decompose_query(s, util_llm)))
    builder.add_node("hyde_generate",        timed_node("hyde", lambda s: hyde_generate(s, util_llm, cfg)))
    builder.add_node("track_a_rule_search",  timed_node("rule_search", lambda s: track_a_rule_search(s, rule_index, cfg)))
    builder.add_node("track_b_fact_search",  timed_node("fact_search", lambda s: track_b_fact_search(s, fact_index, kg, cfg)))
    builder.add_node("merge_candidates",     timed_node("merge", lambda s: merge_candidates(s, kg, cfg)))
    builder.add_node("rerank_candidates",    timed_node("rerank", lambda s: rerank_candidates(s, util_llm, embedding_model, cfg)))
    builder.add_node("build_subgraphs",      timed_node("build_sg", lambda s: build_subgraphs(s, subgraph_builder, cfg)))
    builder.add_node("fetch_source_text",    timed_node("fetch_text", lambda s: fetch_source_text(s, kg, cfg)))
    builder.add_node("assemble_context",     timed_node("assemble", lambda s: assemble_context(s, cfg, embedding_model)))
    builder.add_node("fetch_table_data",     timed_node("fetch_table", fetch_table_data))
    builder.add_node("generate_answer",      timed_node("generate", lambda s: generate_answer(s, llm, cfg)))

    # 設定連線流程
    builder.set_entry_point("decompose_query")
    builder.add_edge("decompose_query",      "hyde_generate")
    builder.add_edge("hyde_generate",        "track_a_rule_search")
    builder.add_edge("hyde_generate",        "track_b_fact_search")
    builder.add_edge("track_a_rule_search",  "merge_candidates")
    builder.add_edge("track_b_fact_search",  "merge_candidates")
    builder.add_edge("merge_candidates",     "rerank_candidates")
    builder.add_edge("rerank_candidates",    "build_subgraphs")
    builder.add_edge("build_subgraphs",      "fetch_source_text")
    builder.add_edge("fetch_source_text",    "assemble_context")
    builder.add_edge("assemble_context",     "fetch_table_data")
    builder.add_edge("fetch_table_data",     "generate_answer")
    builder.add_edge("generate_answer",      END)

    return builder.compile()

class IRACRetriever:
    """RAG 系統的外部介面"""
    def __init__(self, kg, rule_index, fact_index, graph, config, llm=None):
        self.kg = kg
        self.rule_index = rule_index
        self.fact_index = fact_index
        self._graph = graph
        self.config = config
        self.llm = llm # 儲存 LLM 實例供直接呼叫

    @classmethod
    def from_active_kgs(cls, llm_model: str = None, **kwargs) -> "IRACRetriever":
        load_dotenv()
        cfg = RetrieverConfig.from_env()
        kg_dirs = [str(data_dir / n.strip()) for n in cfg.active_kgs]

        # 🔑 動態選擇 KG 模式
        kg_mode = os.environ.get("KG_MODE", "local").lower()
        if kg_mode == "neo4j":
            from kg_manager import Neo4jKGIndex
            kg = Neo4jKGIndex(cfg)
        else:
            from kg_manager import LocalKGIndex
            kg = LocalKGIndex(kg_dirs)

        # 🔑 動態選擇向量資料庫模式
        vdb_mode = os.environ.get("VDB_MODE", "local").lower()

        # 建立 Embeddings 與 LLM
        emb = OllamaEmbeddings()
        llm_provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
        llm_model_name = llm_model or os.environ.get("LLM_MODEL_NAME", "gemini-2.0-flash")
        gemini_key = os.environ.get("GEMINI_API_KEY")

        if llm_provider == "ollama":
            llm = OllamaLLM(
                model_name=llm_model_name,
                temperature=0.0,
                timeout=1800.0
            )
        else:
            llm = GeminiLLM(
                model_name=llm_model_name,
                api_key=gemini_key,
                max_tokens=cfg.max_output_tokens
            )

        # 建立 utility_llm 用於非生成的輔助任務 (如查詢分解、Step-Back等) 以加速
        if gemini_key:
            utility_llm = GeminiLLM(
                model_name="gemini-2.5-flash",
                api_key=gemini_key,
                max_tokens=512
            )
        else:
            utility_llm = llm

        if vdb_mode == "qdrant":
            # ====== Qdrant 向量資料庫模式 ======
            # 跡跡共用同一個 QdrantVectorIndex 實例，
            # Neo4j 的 get_node() 會負責確認實體類型 (rule / materialfact)。
            print(f"[IRACRetriever] 使用 Qdrant 向量資料庫 ")
            print(f"  URL: {cfg.qdrant_url}")
            print(f"  實體 Collection: {cfg.qdrant_collection_ent}")
            print(f"  Workspace: {cfg.qdrant_workspace or '(未篩選)'}") 

            rule_idx = QdrantVectorIndex(emb, cfg)
            fact_idx = QdrantVectorIndex(emb, cfg)
            # Qdrant 模式不需要先 build()，呼召 build() 會被忽略
        else:
            # ====== 本地向量矩陣模式 (Legacy) ======
            # 取得向量庫路徑 (遞迴搜尋所有子目錄中的 vdb_entities.json)
            vdb_paths = []
            for d in kg_dirs:
                if not os.path.exists(d): continue
                for root, _, files in os.walk(d):
                    if "vdb_entities.json" in files:
                        vdb_paths.append(os.path.join(root, "vdb_entities.json"))

            rule_idx = VectorIndex(emb, vdb_path=vdb_paths, config=cfg)
            rule_idx.build(kg.get_nodes_of_type("rule"))

            fact_idx = VectorIndex(emb, vdb_path=vdb_paths, config=cfg)
            fact_idx.build(kg.get_nodes_of_type("materialfact"))

        # 建立圖與門戶
        # 🔑 傳遞向量索引供 SubgraphBuilder 進行名稱橋接 (用於 Neo4j)
        sb = SubgraphBuilder(kg, rule_index=rule_idx, fact_index=fact_idx)
        graph = make_retrieval_graph(kg, rule_idx, fact_idx, sb, llm, emb, config=cfg, utility_llm=utility_llm, **kwargs)

        return cls(kg, rule_idx, fact_idx, graph, cfg, llm=llm)

    @classmethod
    def from_graphml(cls, *args, **kwargs):
        return cls.from_active_kgs()

    def retrieve(self, query: str, **kwargs):
        # 建立初始狀態，並從全域 config 獲取預設值
        initial_state = {
            "query": query, 
            "query_bundle": {}, 
            "is_tax_related": True,
            "rule_query": "", 
            "fact_query": "", 
            "keywords": [],
            "rule_track_hits": [], 
            "fact_track_hits": [], 
            "rule_candidates": [],
            "subgraphs": [], 
            "source_chunks": [], 
            "context": "",
            "use_kg": self.config.mode == "irac",
            "use_source_text": self.config.enable_source_text,
            "force_english": self.config.force_english_answer,
            "mode": self.config.mode,
            "table_context": "", 
            "answer": "", 
            "token_usage": {"input_tokens": 0, "output_tokens": 0},
            "debug_info": {},
            # --- 新增動態參數初始化 ---
            "enable_hyde": self.config.enable_hyde,
            "enable_step_back": self.config.enable_step_back,
            "enable_multi_query": self.config.enable_multi_query,
            "enable_dual_track": self.config.enable_dual_track,
            "enable_bm25": self.config.enable_bm25,
            "enable_kg_subgraph": self.config.enable_kg_subgraph,
            "enable_recomp": self.config.enable_recomp,
            "enable_sg_pruning": self.config.enable_sg_pruning,
            "use_jina_rerank": self.config.use_jina_rerank,
            "context_strategy": self.config.context_strategy,
            "context_threshold": self.config.context_threshold,
            "context_fixed_full_count": self.config.context_fixed_full_count,
            "context_fixed_sub_count": self.config.context_fixed_sub_count,
            "max_subgraphs": self.config.max_subgraphs,
            "max_output_tokens": self.config.max_output_tokens,
            "vector_threshold": self.config.vector_threshold,
            "dual_track_boost": self.config.dual_track_boost
        }
        
        # 使用傳入的參數覆蓋預設值 (排除 None)
        for k, v in kwargs.items():
            if v is not None and k in initial_state:
                initial_state[k] = v
                
        return self._graph.invoke(initial_state)
