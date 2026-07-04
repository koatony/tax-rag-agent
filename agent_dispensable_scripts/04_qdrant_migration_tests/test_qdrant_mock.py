import sys
from pathlib import Path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))

from data_models import RetrieverConfig
from kg_manager import QdrantVectorIndex

class MockEmbeddings:
    def embed_query(self, query):
        return [0.1] * 1024

def test():
    print("[1] 初始化配置...")
    cfg = RetrieverConfig.from_env()
    cfg.qdrant_url = "http://127.0.0.1:7333"
    
    print("[2] 建立 QdrantVectorIndex...")
    idx = QdrantVectorIndex(MockEmbeddings(), cfg)
    
    print("[3] 執行檢索...")
    try:
        hits = idx.search("test query", top_k=5)
        print(f"✅ 檢索成功！找到 {len(hits)} 筆資料:")
        for name, score in hits:
            print(f" - {name} (score: {score})")
    except Exception as e:
        print(f"❌ 錯誤: {e}")

test()
