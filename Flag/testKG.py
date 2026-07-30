"""
KG 連線/檢索驗證腳本

直接呼叫 query_kg_for_issue()，繞過整個 LLM 分析流程，
確認 Neo4j 連線、bge-m3 embedding、cache 是否都正常運作，
並印出實際撈到的 KG context（如果是空字串，代表沒有真的撈到東西）。

Run: uv run python Flag/test_kg.py  (從專案根目錄執行)
"""

from Flag.kg_retriever_v2 import query_kg_for_issue, get_driver, CACHE_PATH


def run():
    print(f"[1] Cache 檔案路徑: {CACHE_PATH}")
    print(f"    存在: {CACHE_PATH.exists()}")
    print()

    print("[2] 測試 Neo4j 連線...")
    try:
        driver = get_driver()
        driver.verify_connectivity()
        print("    Neo4j 連線成功")
    except Exception as e:
        print(f"    Neo4j 連線失敗: {e}")
        print("    -> KG 一定沒有作用，所有 use_kg=True 的呼叫都只是在跑空的")
        return
    print()

    print("[3] 實際呼叫 query_kg_for_issue()...")
    ctx = query_kg_for_issue(
        issue_name="Rental property depreciation not claimed",
        target_component="Schedule E",
    )
    print(f"    回傳長度: {len(ctx)} 字元")
    print()
    if ctx:
        print("    撈到的 KG context 內容（前 800 字）：")
        print("    " + "-" * 60)
        print(ctx[:800])
        print("    " + "-" * 60)
        print()
        print("結論：KG 有真的撈到資料，運作正常。")
    else:
        print("結論：query_kg_for_issue() 回傳空字串，代表沒有撈到任何相關規則節點，"
              "KG 實質上沒有提供任何資訊給 LLM（可能是知識圖譜裡沒有對應資料，"
              "或語意比對 top_k 都不夠相關）。")


if __name__ == "__main__":
    run()
