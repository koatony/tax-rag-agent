import os
import re
import json
import base64
import zlib
import xml.etree.ElementTree as ET
import numpy as np
import networkx as nx
from collections import defaultdict
from typing import Any, List, Dict, Tuple, Union, Optional
from abc import ABC, abstractmethod
from nltk.stem import PorterStemmer
from rank_bm25 import BM25Okapi
from neo4j import GraphDatabase

from data_models import NodeInfo, RetrieverConfig
import re
import json
import base64
import zlib
import xml.etree.ElementTree as ET
import numpy as np
import networkx as nx
from collections import defaultdict
from typing import Any, List, Dict, Tuple, Union, Optional
from abc import ABC, abstractmethod
from nltk.stem import PorterStemmer
from rank_bm25 import BM25Okapi
from neo4j import GraphDatabase

from data_models import NodeInfo, RetrieverConfig

def decode_vector(v_str: str) -> np.ndarray:
    """解碼 LightRAG 的向量格式"""
    v_bytes = base64.b64decode(v_str)
    try:
        decompressed = zlib.decompress(v_bytes)
        if len(decompressed) % 8 != 0 or len(decompressed) % 4 == 0:
            try:
                vec_f16 = np.frombuffer(decompressed, dtype=np.float16)
                return vec_f16.astype(np.float32)
            except:
                return np.frombuffer(decompressed, dtype=np.float32)
        else:
            return np.frombuffer(decompressed, dtype=np.float32)
    except:
        return np.frombuffer(v_bytes, dtype=np.float32)

class KGIndex(ABC):
    @abstractmethod
    def get_nodes_of_type(self, entity_type: str) -> List[Dict[str, Any]]: pass
    @abstractmethod
    def get_node(self, entity_id: str) -> Optional[NodeInfo]: pass
    @abstractmethod
    def get_neighbors(self, entity_id: str, relation: str = None, direction: str = "out") -> List[Tuple[NodeInfo, str]]: pass
    @abstractmethod
    def get_text_chunk(self, source_id: str) -> Optional[dict]: pass
    @abstractmethod
    def close(self): pass

class LocalKGIndex(KGIndex):
    def __init__(self, kg_dirs: List[str]):
        self.kg_dirs = kg_dirs
        self.nodes: Dict[str, NodeInfo] = {}
        self.graph = nx.DiGraph()
        self._nodes_by_type = defaultdict(list)
        self._adj_undirected = defaultdict(list)
        self.text_chunks: Dict[str, dict] = {}
        self._load_all()

    def _load_all(self):
        for kg_dir in self.kg_dirs:
            if not os.path.exists(kg_dir): continue
            for root, _, files in os.walk(kg_dir):
                for f in files:
                    if f.endswith(".graphml"):
                        self._load_single_graphml(os.path.join(root, f))
                text_chunks_path = os.path.join(root, "kv_store_text_chunks.json")
                if os.path.exists(text_chunks_path):
                    try:
                        with open(text_chunks_path, "r", encoding="utf-8") as f:
                            self.text_chunks.update(json.load(f))
                    except Exception as e:
                        print(f"[LocalKGIndex] 警告: 無法讀取文字庫 {text_chunks_path}: {e}")
        print(f"[LocalKGIndex] 載入完成: {len(self.nodes)} 節點, {self.graph.number_of_edges()} 條邊")

    def _load_single_graphml(self, path: str):
        NS = "http://graphml.graphdrawing.org/xmlns"
        try:
            tree = ET.parse(path)
            root = tree.getroot()
        except: return
        for node_el in root.iter(f"{{{NS}}}node"):
            props = {d.get("key"): (d.text or "") for d in node_el.iter(f"{{{NS}}}data")}
            nid = node_el.get("id")
            if nid in self.nodes: continue
            info = NodeInfo(
                entity_id   = props.get("d0", nid),
                entity_type = props.get("d1", "UNKNOWN").lower(),
                description = props.get("d2", ""),
                source_id   = props.get("d3", ""),
                file_path   = props.get("d4", ""),
            )
            self.nodes[nid] = info
            self._nodes_by_type[info.entity_type].append(nid)
            self.graph.add_node(nid, **info.__dict__)
        for edge_el in root.iter(f"{{{NS}}}edge"):
            props = {d.get("key"): (d.text or "") for d in edge_el.iter(f"{{{NS}}}data")}
            src, tgt = edge_el.get("source"), edge_el.get("target")
            if src in self.nodes and tgt in self.nodes:
                self.graph.add_edge(src, tgt, relation=props.get("d9", ""), weight=float(props.get("d7", 1.0) or 1.0))
                self._adj_undirected[src].append((tgt, props.get("d9", "")))
                self._adj_undirected[tgt].append((src, props.get("d9", "")))

    def get_nodes_of_type(self, entity_type: str):
        return [{"id": n, **d} for n, d in self.graph.nodes(data=True) if d.get("entity_type") == entity_type]

    def get_node(self, entity_id: str) -> Optional[NodeInfo]:
        return self.nodes.get(entity_id)

    def get_neighbors(self, entity_id: str, relation: str = None, direction: str = "out") -> List[Tuple[NodeInfo, str]]:
        results = []
        if direction in ("out", "both"):
            for _, tgt, data in self.graph.out_edges(entity_id, data=True):
                rel = data.get("relation", "")
                if (relation is None or rel == relation) and tgt in self.nodes:
                    results.append((self.nodes[tgt], rel))
        if direction in ("in", "both"):
            for src, _, data in self.graph.in_edges(entity_id, data=True):
                rel = data.get("relation", "")
                if (relation is None or rel == relation) and src in self.nodes:
                    results.append((self.nodes[src], rel))
        return results

    def get_text_chunk(self, source_id: str) -> Optional[dict]:
        return self.text_chunks.get(source_id)

    def close(self): pass

class Neo4jKGIndex(KGIndex):
    def __init__(self, config: RetrieverConfig):
        self.config = config
        # 原始文本映射表，由 LightRAG JSON 載入
        self.text_chunks: Dict[str, dict] = {}
        try:
            self.driver = GraphDatabase.driver(
                config.neo4j_uri, auth=(config.neo4j_user, config.neo4j_password)
            )
            self.driver.verify_connectivity()
            print(f"[Neo4jKGIndex] 已連綫至 {config.neo4j_uri}")
        except Exception as e:
            print(f"[Neo4jKGIndex] 連綫失敗: {e}")
            raise e

        # 若有指定 LightRAG 路徑，則自動載入 kv_store_text_chunks.json
        if config.lightrag_path and os.path.isdir(config.lightrag_path):
            chunks_path = os.path.join(config.lightrag_path, "kv_store_text_chunks.json")
            if os.path.exists(chunks_path):
                try:
                    with open(chunks_path, "r", encoding="utf-8") as f:
                        self.text_chunks = json.load(f)
                    print(f"[Neo4jKGIndex] 已載入文本儲存庫: {len(self.text_chunks)} 筆資料 (路徑: {chunks_path})")
                except Exception as e:
                    print(f"[Neo4jKGIndex] 警告: 無法讀取文本儲存庫 {chunks_path}: {e}")
            else:
                print(f"[Neo4jKGIndex] 警告: 在 {config.lightrag_path} 中找不到 kv_store_text_chunks.json")
        else:
            print(f"[Neo4jKGIndex] 提示: 未設定 LIGHTRAG_PATH，將無法提供原始文本 (ENABLE_SOURCE_TEXT 將失效)。")

    def _get_ws_label(self) -> str:
        """取得 workspace 的 Cypher Label。
        直接使用使用者在 env 設定的完整 label 名稱，不再加 ws_ 前綴。
        """
        ws = self.config.neo4j_workspace
        if not ws:
            return ""
        # 直接使用完整名稱，加上 Cypher Label 语法的冒號
        return f":{ws}"

    def get_nodes_of_type(self, entity_type: str) -> List[Dict[str, Any]]:
        ws_label = self._get_ws_label()
        query = f"MATCH (n{ws_label}) WHERE n.entity_type = $etype RETURN n"
        nodes = []
        with self.driver.session(database=self.config.neo4j_database) as session:
            result = session.run(query, etype=entity_type)
            for record in result:
                node = record["n"]
                nodes.append({"id": node.get("entity_id") or node.get("id"), **dict(node)})
        return nodes

    def get_node(self, entity_id: str) -> Optional[NodeInfo]:
        ws_label = self._get_ws_label()
        query = f"MATCH (n{ws_label} {{entity_id: $eid}}) RETURN n LIMIT 1"
        with self.driver.session(database=self.config.neo4j_database) as session:
            result = session.run(query, eid=entity_id)
            record = result.single()
            if record:
                n = dict(record["n"])
                return NodeInfo(
                    entity_id=n.get("entity_id"),
                    entity_type=n.get("entity_type", "unknown").lower(),
                    description=n.get("description", ""),
                    source_id=n.get("source_id", ""),
                    file_path=n.get("file_path", "")
                )
        return None

    def get_neighbors(self, entity_id: str, relation: str = None, direction: str = "out") -> List[Tuple[NodeInfo, str]]:
        ws_label = self._get_ws_label()
        if direction == "out": dir_clause = "-[r:DIRECTED]->"
        elif direction == "in": dir_clause = "<-[r:DIRECTED]-"
        else: dir_clause = "-[r:DIRECTED]-"
        
        rel_filter = "WHERE r.keywords = $relation" if relation else ""
        query = f"""
        MATCH (n {{entity_id: $eid}}){dir_clause}(m{ws_label})
        {rel_filter}
        RETURN m, r.keywords as rel_type
        """
        results = []
        with self.driver.session(database=self.config.neo4j_database) as session:
            result = session.run(query, eid=entity_id, relation=relation)
            for record in result:
                m = dict(record["m"])
                results.append((NodeInfo(
                    entity_id=m.get("entity_id"),
                    entity_type=m.get("entity_type", "unknown").lower(),
                    description=m.get("description", ""),
                    source_id=m.get("source_id", ""),
                    file_path=m.get("file_path", "")
                ), record["rel_type"]))
        return results

    def get_text_chunk(self, source_id: str) -> Optional[dict]:
        """Neo4j 本身不儲存原始文本，由初始化時自 JSON 載入的 text_chunks 提供。"""
        return self.text_chunks.get(source_id)

    def close(self):
        self.driver.close()

class VectorIndex:
    """
    向量索引類別：負責管理與執行「語意搜尋」與「關鍵字搜尋」。
    它將知識圖譜中的節點 (Nodes) 轉換為數值矩陣，以便進行高速的比對。
    """
    def __init__(self, model, vdb_path: Union[str, List[str]] = None, config: RetrieverConfig = None):
        """
        初始化搜尋引擎。
        :param model: 嵌入模型 (Embedding Model)，負責將文字轉為向量。
        :param vdb_path: 本地向量資料庫 (vdb_entities.json) 的路徑。
        :param config: 全域配置項。
        """
        self.model = model
        self.vdb_path = vdb_path
        self.config = config or RetrieverConfig()
        self._matrix = None   # 儲存所有節點向量的矩陣
        self._ids = []      # 儲存對應的 ID 清單
        self._id_to_name: Dict[str, str] = {} # 雜湊 ID 到名稱的對照表 (用於 Neo4j)
        self.bm25 = None      # BM25 關鍵字搜尋實例
        self.stemmer = PorterStemmer() # 詞幹提取器 (例如把 taxes 轉為 tax)

    def get_name(self, entity_id: str) -> str:
        """
        將雜湊 ID (如 f1a2b3) 轉換為實體名稱 (如 Standard_Deduction)。
        這在處理從 LightRAG 或 Neo4j 匯出的資料時非常重要，因為圖譜通常使用名稱作為鍵。
        """
        return self._id_to_name.get(entity_id, entity_id)

    def _tokenize(self, text: str) -> List[str]:
        clean_text = re.sub(r'[^\w\s]', '', text).lower()
        tokens = clean_text.split()
        return [self.stemmer.stem(t) for t in tokens] if self.config.enable_stemming else tokens

    def build(self, nodes: List[Any], index_name: str = "default_index"):
        """
        建立索引：將圖譜中的節點轉換為可搜尋的向量矩陣。
        :param nodes: 從 KG 抓出來的節點清單 (例如 kg.get_nodes_of_type("rule"))。
        """
        # 1. 統一資料格式：確保所有的 node 都是 NodeInfo 物件
        node_infos = []
        for n in nodes:
            if isinstance(n, dict):
                node_infos.append(NodeInfo(
                    entity_id=n.get("id") or n.get("entity_id", "unknown"),
                    entity_type=n.get("entity_type", "unknown"),
                    description=n.get("description", ""),
                    source_id=n.get("source_id", ""),
                    file_path=n.get("file_path", "")
                ))
            else: node_infos.append(n)
        
        # 2. 建立 ID 索引：記住每個位置對應到哪一個法規 ID
        self._ids = [n.entity_id for n in node_infos]
        id_to_node = {n.entity_id: n for n in node_infos}

        # 3. 嘗試從本地 vdb_entities.json 載入預算好的向量 (加速啟動)
        paths = self.vdb_path if isinstance(self.vdb_path, list) else ([self.vdb_path] if self.vdb_path else [])
        precomputed_map = {}
        for path in paths:
            if not os.path.exists(path): continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    vdb_data = json.load(f)
                    for item in vdb_data.get("data", []):
                        # name: 實體名稱, v_str: 向量數據, hash_id: 雜湊 ID
                        name, v_str, hash_id = item.get("entity_name"), item.get("vector"), item.get("__id__")
                        if hash_id: self._id_to_name[hash_id] = name
                        
                        if v_str:
                            # 使用解碼函數處理向量數據
                            vec = decode_vector(v_str)
                            # 將 ID 或名稱映射到向量
                            if hash_id: precomputed_map[hash_id] = vec
                            if name: precomputed_map[name] = vec
            except: pass
        
        # 4. 準備最終向量清單
        all_embeddings = []
        texts_to_embed = []
        for n in node_infos:
            # 如果本地 JSON 已經有這筆向量了，直接用
            if n.entity_id in precomputed_map: all_embeddings.append(precomputed_map[n.entity_id])
            # 如果沒有，就記下來，等一下要現場呼叫 LLM 轉向量
            else: texts_to_embed.append(n.description)

        # 5. 現場呼叫 Embedding Model (將剩餘的文字轉為向量)
        if texts_to_embed:
            all_embeddings.extend(self.model.embed_documents(texts_to_embed))

        # 6. 建立搜尋矩陣
        if all_embeddings:
            self._matrix = np.array(all_embeddings, dtype=np.float32)
            if self._matrix.ndim == 1: self._matrix = self._matrix.reshape(1, -1)
            # 正規化 (Normalization)：確保計算 Cosine Similarity 時速度最快
            norms = np.linalg.norm(self._matrix, axis=1, keepdims=True)
            self._matrix = self._matrix / (norms + 1e-9)

        # 7. 初始化 BM25 搜尋引擎 (針對所有法規文字進行斷詞索引)
        self._texts = [n.description for n in node_infos]
        if self.config.enable_bm25 and self._texts:
            self.bm25 = BM25Okapi([self._tokenize(doc) for doc in self._texts])

    def search(self, query: str, keywords: List[str] = None, top_k: int = 10) -> List[Tuple[str, float]]:
        """
        混合搜尋核心邏輯：結合向量語意搜尋與 BM25 關鍵字搜尋。
        """
        # --- 步驟 1：向量語意搜尋 (Vector Search) ---
        # 將問題轉為向量並進行正規化
        q_vec = np.array(self.model.embed_query(query), dtype=np.float32)
        q_vec = q_vec / (np.linalg.norm(q_vec) + 1e-9)
        
        # 計算矩陣乘法，得到所有節點與問題的相似度分數 (Cosine Similarity)
        vec_scores = self._matrix @ q_vec
        
        # 如果有設定門檻，低於門檻的分數設為 -1 (排除)
        if self.config.vector_threshold > 0.0:
            vec_scores = np.where(vec_scores >= self.config.vector_threshold, vec_scores, -1.0)
        
        # --- 步驟 2：關鍵字搜尋 (BM25 Search) ---
        bm25_scores = np.zeros(len(self._ids))
        if keywords and self.bm25:
            # 將關鍵字進行斷詞與詞幹提取 (如: taxes -> tax)
            stemmed = []
            
            for k in keywords: stemmed.extend(self._tokenize(k))
            if stemmed: 
                # 使用 BM25 演算法計算關鍵字匹配分數
                bm25_scores = np.array(self.bm25.get_scores(stemmed))
        
        # --- 步驟 3：RRF 排名融合 (Reciprocal Rank Fusion) ---
        # 分別計算向量與關鍵字的排名 (由高到低)
        v_ranks = {idx: r for r, idx in enumerate(np.argsort(vec_scores)[::-1])}
        b_ranks = {idx: r for r, idx in enumerate(np.argsort(bm25_scores)[::-1])}
        
        # 使用 RRF 公式融合兩者排名：Score = 1/(60+rank_v) + 1/(60+rank_b)
        # 這能確保同時在兩邊都排名靠前者會獲得極高權重
        rrf = [(1.0/(60+v_ranks[i])) + (1.0/(60+b_ranks[i])) for i in range(len(self._ids))]
        
        # 取出前 Top-K 名的索引
        top_idx = np.argsort(rrf)[::-1][:top_k]
        
        # 回傳 ID 與對應的 RRF 分數
        return [(self._ids[i], rrf[i]) for i in top_idx]


class QdrantVectorIndex:
    """
    Qdrant 向量資料庫索引，取代原來的本地矩陣式搜尋 (VectorIndex)。
    與 VectorIndex 提供相同的 search() 介面，可在 retriever.py 中無縫切換。

    LightRAG 儲存三個獨立 collection：
      - ent (entities):        entity_name, content, source_id, file_path, workspace_id
      - rel (relationships):   src_id, tgt_id, content, source_id, file_path, workspace_id
      - chunks:                content, original_id, file_path, workspace_id

    Track A (rule search) 與 Track B (fact search) 均搜尋 ent collection，
    entity_type 的篩選依賴 Neo4j（回傳 entity_name 後交給 kg.get_node 驗證類型）。
    """

    def __init__(self, model, config: RetrieverConfig):
        """
        :param model:  嵌入模型 (OllamaEmbeddings)，負責將查詢文字轉為向量。
        :param config: 全域配置，包含 Qdrant 連線資訊與 collection 名稱。
        """
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        self.model = model
        self.config = config
        self._Filter = Filter
        self._FieldCondition = FieldCondition
        self._MatchValue = MatchValue

        # 建立 Qdrant 連線（無密碼時 api_key 傳 None）
        # 注意：Docker 只開放了 7333->6333 (REST)，沒有開放 gRPC(6334)，
        # 所以必須加上 prefer_grpc=False，否則 client 預設嘗試 gRPC 會導致卡死。
        api_key = config.qdrant_api_key if config.qdrant_api_key else None
        self.client = QdrantClient(url=config.qdrant_url, api_key=api_key, prefer_grpc=False, timeout=10, check_compatibility=False)
        print(f"[QdrantVectorIndex] 已連線至 {config.qdrant_url} (REST 模式)")

        # 實體 collection 名稱（Track A / B 主要來源）
        self.collection_ent = config.qdrant_collection_ent
        # workspace 篩選值（若設定則對每次查詢加上 payload filter）
        self.workspace = config.qdrant_workspace

        # 相容性屬性（舊程式碼可能讀取 _id_to_name，Qdrant 模式直接回傳 entity_name 無需轉換）
        self._id_to_name: Dict[str, str] = {}

    def get_name(self, entity_id: str) -> str:
        """相容 VectorIndex 介面；Qdrant 模式直接回傳原值（已是 entity_name）。"""
        return self._id_to_name.get(entity_id, entity_id)

    def build(self, nodes: List[Any], index_name: str = "default_index"):
        """相容 VectorIndex 介面；Qdrant 模式不需要預先建立本地矩陣。"""
        print(f"[QdrantVectorIndex] build() 被呼叫但跳過，向量搜尋將直接對接 Qdrant API。")

    def _build_workspace_filter(self) -> Optional[Any]:
        """建立 workspace_id 的 Qdrant payload 篩選器。"""
        if not self.workspace:
            return None
        return self._Filter(
            must=[
                self._FieldCondition(
                    key="workspace_id",
                    match=self._MatchValue(value=self.workspace)
                )
            ]
        )

    def search(
        self,
        query: str,
        keywords: Optional[List[str]] = None,
        top_k: int = 10
    ) -> List[Tuple[str, float]]:
        """
        向 Qdrant ent collection 進行向量語意搜尋。

        :param query:    查詢文字（由 embed_query 轉為向量後送出）
        :param keywords: BM25 關鍵字（Qdrant 模式忽略，保留介面相容）
        :param top_k:    回傳前 N 筆結果
        :return:         List of (entity_name, score)
        """
        # 1. 將查詢文字轉為向量
        q_vec = self.model.embed_query(query)

        # 2. 建立 workspace 篩選器（若有設定）
        ws_filter = self._build_workspace_filter()

        # 3. 呼叫 Qdrant 搜尋 API (1.17+ 推薦使用 query_points)
        res = self.client.query_points(
            collection_name=self.collection_ent,
            query=q_vec,
            query_filter=ws_filter,
            limit=top_k,
            with_payload=True,
        )

        # 4. 解析回傳結果：entity_name 作為 entity_id
        hits = []
        for point in res.points:
            payload = point.payload or {}
            entity_name = payload.get("entity_name", str(point.id))
            score = float(point.score)
            hits.append((entity_name, score))

        return hits
