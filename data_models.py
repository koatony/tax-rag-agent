"""
RAG 系統的資料模型與全域配置
==============================
包含：
1. RetrieverConfig: 全域功能開關
2. NodeInfo/EdgeInfo: 知識圖譜基礎結構
3. RuleCandidate: 檢索候選規則
4. IRACSubgraph: 推理子圖結構
5. RetrievalState: LangGraph 的狀態定義
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Annotated, List, Dict, Union
from typing_extensions import TypedDict
import os

def merge_dicts(left: dict, right: dict) -> dict: 
    """用於字典狀態鍵的 MERGE 合併函數"""
    return {**left, **right}

def merge_usage(left: dict, right: dict) -> dict:
    """累加 Token 使用量"""
    new_usage = left.copy()
    if not right: return new_usage
    for k, v in right.items():
        new_usage[k] = new_usage.get(k, 0) + v
    return new_usage

@dataclass
class RetrieverConfig:
    """
    所有功能開關集中在此，對應 .env 中的設定。
    """
    enable_bm25:         bool = True   # 是否啟用 BM25 關鍵字搜尋
    enable_stemming:     bool = True   # 是否啟用詞幹提取 (僅限 BM25)
    enable_dual_track:   bool = True   # 是否啟用雙軌檢索 (Fact -> Rule)
    enable_hyde:         bool = False  # 是否啟用 HyDE (假設性文件嵌入)
    enable_step_back:    bool = True   # 是否啟用 Step-Back Prompting
    enable_kg_subgraph:  bool = True   # 是否啟用知識圖譜子圖擴充

    enable_source_text:  bool = False  # 是否加入原始 PDF 段落文本
    enable_table_context: bool = False  # 是否加入 OCR 表格上下文
    
    debug_prompt:        bool = False  # 是否在終端機列印 Debug Prompt
    enable_recomp:       bool = True   # 是否啟用 RECOMP 句子級壓縮
    enable_sg_pruning:   bool = True   # 是否啟用語義子圖剪枝 (防止雜訊)
    use_jina_rerank:     bool = False  # 是否使用 Jina Reranker API
    jina_api_key:        str = ""
    enable_multi_query:  bool = False  # 是否啟用多重查詢融合 (Fusion)
    multi_query_top_k:   int = 15      # 多重查詢模式下的每條查詢 Top-K
    vector_threshold:    float = 0.0   # 向量相似度門檻 (低於此值則排除)
    active_kgs:         List[str] = field(default_factory=lambda: ["tax_kg_v1"])
    mode:               str = "irac"   # 檢索模式: irac (知識圖譜) 或 naive (傳統 RAG)
    force_english_answer: bool = False  # 是否強制全英文回答
    dual_track_boost:   float = 1.4    # 雙軌命中加成倍率
    max_subgraphs:      int = 10       # 最大建立子圖的數量
    max_output_tokens:  int = 8192     # LLM 單次輸出 Token 上限

    # --- Neo4j 設定 ---
    neo4j_uri:          str = "bolt://localhost:7687"
    neo4j_user:         str = "neo4j"
    neo4j_password:     str = "password"
    neo4j_database:     str = "neo4j"
    neo4j_workspace:    str = ""  # Neo4j 中用來篩選 workspace 的 label 名稱（直接使用，不再加 ws_ 前綴）

    # --- Qdrant 向量資料庫設定 ---
    qdrant_url:                 str = ""    # Qdrant 伺服器位址，例如 http://localhost:6333
    qdrant_api_key:             str = ""    # Qdrant API Key（無密碼時留空）
    # LightRAG 三個獨立 collection 名稱
    qdrant_collection_ent:      str = "lightrag_vdb_entities_bge_m3_1024d"       # 實體 collection
    qdrant_collection_rel:      str = "lightrag_vdb_relationships_bge_m3_1024d"  # 關係 collection
    qdrant_collection_chunks:   str = "lightrag_vdb_chunks_bge_m3_1024d"         # 段落 collection
    qdrant_workspace:           str = ""    # 用於 Qdrant payload 中 workspace_id 篩選

    # --- LightRAG JSON 儲存路徑 ---
    lightrag_path:              str = ""    # 指向 kv_store_*.json 所在的資料夾路徑

    # --- 分層 Context 設定 (NEW) ---
    # 策略開關: 'fixed' (固定數量) 或 'threshold' (分數門檻)
    context_strategy:   str = "fixed" 
    # 門檻模式下的分數門檻 (用於 Jina Rerank 分數)
    context_threshold:  float = 0.8
    # 固定模式下的 Tier 1 數量 (完整子圖 + 原文)
    context_fixed_full_count: int = 3
    # 固定模式下的 Tier 2 數量 (僅子圖結構)
    context_fixed_sub_count: int = 7

    @classmethod
    def from_env(cls) -> "RetrieverConfig":
        """從環境變數讀取設定，若環境變數未設定則沿用 dataclass 的預設值"""
        # 建立一個包含預設值的實例作為參考源
        ref = cls()

        def env_bool(key: str, default: bool) -> bool:
            # 使用 ref 裡面的值作為預設
            val = os.environ.get(key, "1" if default else "0").strip().lower()
            return val in ("1", "true", "yes")
        
        # 處理清單類型的環境變數
        active_kgs_str = os.environ.get("ACTIVE_KGS", ",".join(ref.active_kgs))
        active_kgs = [kg.strip() for kg in active_kgs_str.split(",") if kg.strip()]
        
        return cls(
            enable_bm25          = env_bool("ENABLE_BM25",          ref.enable_bm25),
            enable_stemming      = env_bool("ENABLE_STEMMING",      ref.enable_stemming),
            enable_dual_track    = env_bool("ENABLE_DUAL_TRACK",    ref.enable_dual_track),
            enable_hyde          = env_bool("ENABLE_HYDE",          ref.enable_hyde),
            enable_step_back     = env_bool("ENABLE_STEP_BACK",     ref.enable_step_back),
            enable_kg_subgraph   = env_bool("ENABLE_KG_SUBGRAPH",   ref.enable_kg_subgraph),
            enable_source_text   = env_bool("ENABLE_SOURCE_TEXT",   ref.enable_source_text),
            enable_table_context = env_bool("ENABLE_TABLE_CONTEXT", ref.enable_table_context),
            debug_prompt         = env_bool("DEBUG_PROMPT",         ref.debug_prompt),
            enable_recomp        = env_bool("ENABLE_RECOMP",        ref.enable_recomp),
            enable_sg_pruning    = env_bool("ENABLE_SG_PRUNING",    ref.enable_sg_pruning),
            use_jina_rerank      = env_bool("USE_JINA_RERANK",      ref.use_jina_rerank),
            
            jina_api_key         = os.environ.get("JINA_API_KEY", ref.jina_api_key),
            enable_multi_query   = env_bool("ENABLE_MULTI_QUERY",   ref.enable_multi_query),
            multi_query_top_k    = int(os.environ.get("MULTI_QUERY_TOP_K", str(ref.multi_query_top_k))),
            vector_threshold     = float(os.environ.get("VECTOR_THRESHOLD", str(ref.vector_threshold))),
            active_kgs           = active_kgs,
            mode                 = os.environ.get("RETR_MODE", ref.mode).strip().lower(),
            force_english_answer = env_bool("FORCE_ENGLISH_ANSWER", ref.force_english_answer),
            dual_track_boost     = float(os.environ.get("DUAL_TRACK_BOOST", str(ref.dual_track_boost))),
            max_subgraphs        = int(os.environ.get("MAX_SUBGRAPHS", str(ref.max_subgraphs))),
            context_strategy     = os.environ.get("CONTEXT_STRATEGY", ref.context_strategy),
            context_threshold    = float(os.environ.get("CONTEXT_THRESHOLD", str(ref.context_threshold))),
            context_fixed_full_count = int(os.environ.get("CONTEXT_FIXED_FULL_COUNT", str(ref.context_fixed_full_count))),
            context_fixed_sub_count  = int(os.environ.get("CONTEXT_FIXED_SUB_COUNT", str(ref.context_fixed_sub_count))),
            max_output_tokens        = int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", str(ref.max_output_tokens))),
            
            # --- Neo4j ---
            neo4j_uri                = os.environ.get("NEO4J_URI", ref.neo4j_uri),
            neo4j_user               = os.environ.get("NEO4J_USERNAME", ref.neo4j_user),
            neo4j_password           = os.environ.get("NEO4J_PASSWORD", ref.neo4j_password),
            neo4j_database           = os.environ.get("NEO4J_DATABASE", ref.neo4j_database),
            neo4j_workspace          = os.environ.get("NEO4J_WORKSPACE", ref.neo4j_workspace),

            # --- Qdrant ---
            qdrant_url               = os.environ.get("QDRANT_URL", ref.qdrant_url),
            qdrant_api_key           = os.environ.get("QDRANT_API_KEY", ref.qdrant_api_key),
            qdrant_collection_ent    = os.environ.get("QDRANT_COLLECTION_ENT",    ref.qdrant_collection_ent),
            qdrant_collection_rel    = os.environ.get("QDRANT_COLLECTION_REL",    ref.qdrant_collection_rel),
            qdrant_collection_chunks = os.environ.get("QDRANT_COLLECTION_CHUNKS", ref.qdrant_collection_chunks),
            qdrant_workspace         = os.environ.get("QDRANT_WORKSPACE", ref.qdrant_workspace),

            # --- LightRAG JSON ---
            lightrag_path            = os.environ.get("LIGHTRAG_PATH", ref.lightrag_path),
        )

    def summary(self) -> str:
        flags = {
            "BM25":         self.enable_bm25,
            "Stemming":     self.enable_stemming,
            "DualTrack":    self.enable_dual_track,
            "StepBack":     self.enable_step_back,
            "HyDE":         self.enable_hyde,
            "KGSubgraph":   self.enable_kg_subgraph,
            "SourceText":   self.enable_source_text,
            "TableContext": self.enable_table_context,
            "RECOMP":       self.enable_recomp,
            "SGPruning":    self.enable_sg_pruning,
            "JinaRerank":   self.use_jina_rerank,
            "MultiQuery":   self.enable_multi_query,
            "EngAnswer":    self.force_english_answer,
            "CtxStrat":     self.context_strategy
        }
        return "|".join(f"{k}={'ON' if v else 'OFF'}" for k, v in flags.items())

    def to_dict(self) -> dict:
        """轉化為字典格式，方便 API 回傳"""
        return {
            "enable_bm25": self.enable_bm25,
            "enable_stemming": self.enable_stemming,
            "enable_dual_track": self.enable_dual_track,
            "enable_hyde": self.enable_hyde,
            "enable_step_back": self.enable_step_back,
            "enable_kg_subgraph": self.enable_kg_subgraph,
            "enable_source_text": self.enable_source_text,
            "enable_table_context": self.enable_table_context,
            "enable_recomp": self.enable_recomp,
            "enable_sg_pruning": self.enable_sg_pruning,
            "use_jina_rerank": self.use_jina_rerank,
            "enable_multi_query": self.enable_multi_query,
            "multi_query_top_k": self.multi_query_top_k,
            "vector_threshold": self.vector_threshold,
            "active_kgs": self.active_kgs,
            "mode": self.mode,
            "force_english_answer": self.force_english_answer,
            "dual_track_boost": self.dual_track_boost,
            "max_subgraphs": self.max_subgraphs,
            "context_strategy": self.context_strategy,
            "context_threshold": self.context_threshold,
            "context_fixed_full_count": self.context_fixed_full_count,
            "context_fixed_sub_count": self.context_fixed_sub_count,
            "max_output_tokens": self.max_output_tokens,
        }

@dataclass
class NodeInfo:
    """KG 節點的資料結構"""
    entity_id: str          # 節點名稱
    entity_type: str        # 類型: rule, materialfact, conclusion 等
    description: str        # 節點描述
    source_id: str          # 來源段落 ID
    file_path: str          # 原始檔案路徑

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "description": self.description,
            "source_id": self.source_id,
            "file_path": self.file_path,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "NodeInfo":
        return cls(**d)

@dataclass
class EdgeInfo:
    """KG 邊的資料結構"""
    source: str             # 來源節點
    target: str             # 目標節點
    relation: str           # 關係類型
    weight: float           # 權重
    description: str        # 關係描述
    source_id: str          # 來源 ID

@dataclass
class RuleCandidate:
    """檢索候選規則，記錄來自不同路徑的分數"""
    rule_id: str
    rule_info: NodeInfo
    score_from_rule_track: float = 0.0      # 直接搜尋 Rule 的分數 (Track A)
    score_from_fact_track: float = 0.0      # 從 Fact 反查回來的分數 (Track B)
    matched_fact_ids: List[str] = field(default_factory=list) 

    dual_track_boost: float = 1.4

    @property
    def final_score(self) -> float:
        """計算最後分數，若雙軌同時命中則加權"""
        base = max(self.score_from_rule_track, self.score_from_fact_track)
        if self.score_from_rule_track > 0 and self.score_from_fact_track > 0:
            return base * self.dual_track_boost
        return base

    @property
    def is_dual_hit(self) -> bool:
        return self.score_from_rule_track > 0 and self.score_from_fact_track > 0

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_description": self.rule_info.description,
            "final_score": self.final_score,
            "is_dual_hit": self.is_dual_hit,
            "score_from_rule_track": self.score_from_rule_track,
            "score_from_fact_track": self.score_from_fact_track,
            "matched_fact_ids": self.matched_fact_ids,
        }

@dataclass
class IRACSubgraph:
    """IRAC 推理子圖"""
    rule: NodeInfo
    issues: List[NodeInfo] = field(default_factory=list)
    facts: List[NodeInfo] = field(default_factory=list)
    conclusions: List[NodeInfo] = field(default_factory=list)
    regulations: List[NodeInfo] = field(default_factory=list)
    final_score: float = 0.0
    is_dual_hit: bool = False

    @property
    def completeness_score(self) -> float:
        """計算子圖完整性"""
        score = 1.0
        if self.issues:       score += 0.5
        if self.facts:        score += 1.0
        if self.conclusions:  score += 1.5
        if self.is_dual_hit:  score *= 1.2
        return score

    def to_dict(self) -> dict:
        return {
            "rule": self.rule.to_dict(),
            "issues": [n.to_dict() for n in self.issues],
            "facts": [n.to_dict() for n in self.facts],
            "conclusions": [n.to_dict() for n in self.conclusions],
            "regulations": [n.to_dict() for n in self.regulations],
            "final_score": self.final_score,
            "is_dual_hit": self.is_dual_hit,
        }

    def to_context_text(self) -> str:
        """轉換為 Prompt 用的文本格式 (全英化結構)"""
        source_name = os.path.basename(self.rule.file_path) if self.rule.file_path else "Unknown Source"
        lines = [f"[Rule Segment]: {self.rule.description} (Source: {source_name}, ID: {self.rule.source_id})"]
        if self.issues:
            lines.append("  - Issues Covered:")
            for node in self.issues: lines.append(f"    * {node.description}")
        if self.facts:
            lines.append("  - Conditions/Material Facts:")
            for node in self.facts: lines.append(f"    * {node.entity_id}: {node.description}")
        if self.conclusions:
            lines.append("  - Expected Conclusions:")
            for node in self.conclusions: lines.append(f"    * {node.description}")
        if self.regulations:
            lines.append("  - Legal References/Statutes:")
            for node in self.regulations: lines.append(f"    * {node.description}")
        return "\n".join(lines)

    @classmethod
    def from_dict(cls, d: dict) -> "IRACSubgraph":
        return cls(
            rule=NodeInfo.from_dict(d["rule"]),
            issues=[NodeInfo.from_dict(n) for n in d["issues"]],
            facts=[NodeInfo.from_dict(n) for n in d["facts"]],
            conclusions=[NodeInfo.from_dict(n) for n in d["conclusions"]],
            regulations=[NodeInfo.from_dict(n) for n in d["regulations"]],
            final_score=d.get("final_score", 0.0),
            is_dual_hit=d.get("is_dual_hit", False),
        )

class RetrievalState(TypedDict):
    """LangGraph 狀態定義"""
    query: str
    query_bundle: Dict[str, str]
    is_tax_related: bool
    reject_reason: str
    rule_query: str
    fact_query: str
    keywords: List[str]
    rule_track_hits: List[Dict]
    fact_track_hits: List[Dict]
    rule_candidates: List[Dict]
    subgraphs: List[Dict]
    source_chunks: List[Dict]
    context: str
    use_kg: bool
    use_source_text: bool
    force_english: bool
    mode: str
    table_context: str
    answer: str
    token_usage: Annotated[dict, merge_usage]
    debug_info: Annotated[dict, merge_dicts]
    
    # --- 動態注入的配置項 (NEW) ---
    enable_hyde: Optional[bool]
    enable_step_back: Optional[bool]
    enable_multi_query: Optional[bool]
    enable_dual_track: Optional[bool]
    enable_bm25: Optional[bool]
    enable_kg_subgraph: Optional[bool]
    enable_recomp: Optional[bool]
    enable_sg_pruning: Optional[bool]
    use_jina_rerank: Optional[bool]
    context_strategy: Optional[str]
    context_threshold: Optional[float]
    context_fixed_full_count: Optional[int]
    context_fixed_sub_count: Optional[int]
    max_subgraphs: Optional[int]
    max_output_tokens: Optional[int]
    vector_threshold: Optional[float]
    dual_track_boost: Optional[float]
