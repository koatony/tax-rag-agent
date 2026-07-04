import sys
from pathlib import Path
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))

from retriever import IRACRetriever

def test():
    print("[1] 正在初始化 Retriever (Qdrant + Neo4j)...")
    try:
        retriever = IRACRetriever.from_active_kgs()
        print("[2] 初始化成功！")
        
        query = "Are alimony payments tax deductible after 2019?"
        print(f"[3] 開始測試查詢: {query}")
        
        # 執行檢索 (同步呼叫)
        state = retriever.retrieve(query)
        
        # 檢查結果
        print("\n=== 檢索結果 ===")
        print(f"提取到的 Subgraphs 數量: {len(state.get('subgraphs', []))}")
        
        debug_info = state.get("debug_info", {})
        print("\n=== Debug Info ===")
        print(f"Track A (Rule Search) 找到的候選數: {len(debug_info.get('track_a_candidates', []))}")
        print(f"Track B (Fact Search) 找到的候選數: {len(debug_info.get('track_b_candidates', []))}")
        
        source_chunks = state.get("source_chunks", [])
        print(f"\n=== 文本來源 (Text Chunks) ===")
        print(f"找到 {len(source_chunks)} 個原始段落")
        if source_chunks:
            print(f"範例段落 ID: {source_chunks[0].get('id')}")
            print(f"範例段落內容預覽: {source_chunks[0].get('content', '')[:100]}...")
            
        print("\n✅ 測試完成！")
        
    except Exception as e:
        import traceback
        print(f"\n❌ 測試失敗: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test()
