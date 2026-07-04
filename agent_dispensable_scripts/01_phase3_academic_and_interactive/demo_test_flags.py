import sys
from pathlib import Path

# 將專案根目錄加入路徑，以便導入 retriever
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))

import os
import json
from dotenv import load_dotenv
from retriever import IRACRetriever

# 載入環境變數
load_dotenv(dotenv_path=root_dir / ".env")

def main():
    # 1. 初始化檢索器
    # 預設路徑：data/graph_chunk_entity_relation.graphml
    print("--- 正在初始化 IRACRetriever ---")
    # 初始化 IRAC 檢索器（自動從 .env 讀取 ACTIVE_KGS）
    retriever = IRACRetriever.from_active_kgs()
    
    query = "我收到公司股票期權 (Employee Stock Options)，在行權時 (Exercise) 是否要課稅？"
    
    scenarios = [
        ("情境 A：Baseline (無 KG, 無全文)", {"use_kg": False, "use_source_text": False}),
        ("情境 B：標準 KG (啟用 IRAC 子圖)", {"use_kg": True, "use_source_text": False}),
        ("情境 C：Hybrid RAG (KG + 原始全文)", {"use_kg": True, "use_source_text": True}),
    ]
    
    for name, params in scenarios:
        print(f"\n{'='*60}\n{name}\n{'='*60}")
        # 執行檢索 (注意: retrieve 目前在 retriever.py 已修改為支援參數)
        result = retriever.retrieve(query, **params)
        
        # 顯示產出的 Context 結構摘要
        context = result["context"]
        print(f"Context 長度: {len(context)} 字元")
        
        if "### 面向一" in context:
            print("[V] 包含 KG 推理子圖")
        if "### 面向二" in context:
            print("[V] 包含原始出處段落")
            
        # 打印部分預覽，確認格式
        lines = context.split("\n")
        preview = "\n".join(lines[:20]) # 預覽前 20 行
        print("-" * 30)
        print(preview + "\n...")
        print("-" * 30)

if __name__ == "__main__":
    main()
