import json
import os
import re
from typing import Dict, Any, List, Tuple
from decimal import Decimal
from dotenv import load_dotenv

from processors.models.schedule_c import ScheduleCInputsV1, ScheduleCResultV1
from processors.calculators.schedule_c import calculate_schedule_c_v1
from processors.parsers.schedule_c import ScheduleCLLMParser

# 載入環境變數
load_dotenv()

SCHEMA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "docs", "how_to_fill_forms_docs", "schedule_c", "schedule_c_schema.json"))

def load_schedule_c_schema() -> Dict[str, Any]:
    """載入外部的 Schedule C Schema 設定檔。"""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_schedule_c_inputs_with_logs(
    document_context: str, 
    model_name: str = "gemma4:31b"
) -> Tuple[Dict[str, Any], str, str]:
    """呼叫 LLM 進行欄位提取。"""
    parser = ScheduleCLLMParser(model_name=model_name)
    return parser.parse(document_context)

# =====================================================================
# REVIEW 重點 1: 經典圖論演算法應用 —— 拓撲排序 (Topological Sort)
# =====================================================================
# 【為什麼拓撲排序是後端與大廠面試必考？】
# 1. 概念：當你有一組任務，其中某些任務必須在其他任務之前完成（如：選修課擋修、套件相依性安裝、試算表公式計算），
#    這就是「有向無環圖 (DAG)」，必須用拓撲排序來安排執行順序。
# 2. 演算法實作：這裡採用深度優先搜尋 (DFS)。
#    - 我們用 visited 標記狀態：1 代表「拜訪中」(Visiting)，2 代表「已拜訪」(Visited)。
#    - 如果在 DFS 遍歷過程中遇到一個狀態為 1 的節點，代表有「環」(Cycle)，即循環依賴，這時必須拋出異常。
# 3. ⚠️ 面試提點：無論是否去金融業，拓撲排序與環偵測 (Cycle Detection) 都是系統設計與演算法面試的高頻重點。
# =====================================================================
def topological_sort(formula_deps: Dict[str, List[str]]) -> List[str]:
    """對公式的依賴關係進行拓撲排序，保持相容性。"""
    visited = {}
    order = []
    
    def dfs(node):
        if visited.get(node, 0) == 1:
            raise ValueError(f"偵測到公式間存在循環依賴，無法完成計算。衝突節點: {node}")
        if visited.get(node, 0) == 2:
            return
            
        visited[node] = 1 # 標記為拜訪中 (開始探索其子節點)
        for dep in formula_deps.get(node, []):
            if dep in formula_deps:
                dfs(dep)
        visited[node] = 2 # 子節點探索完畢，標記為已拜訪
        order.append(node) # 將該節點放入排序順序中
        
    for node in formula_deps:
        if visited.get(node, 0) == 0:
            dfs(node)
            
    return order

# =====================================================================
# REVIEW 重點 2: 設計模式 —— 適配器模式 (Adapter Pattern)
# =====================================================================
# 【什麼是適配器模式，它在重構中的妙用？】
# 1. 舊接口定義為 calculate_schedule_c_dynamic(inputs: Dict[str, Any])，使用弱型別 dict。
# 2. 為了引入物件導向與強型別的 calculate_schedule_c_v1，我們不直接改動前端 UI / 測試調用，
#    而是建立這個適配器（Adapter）相容層：
#    - 輸入適配：將弱型別 dict 通過 ScheduleCInputsV1.from_dict(...) 轉換為 OOP Model 物件。
#    - 核心處理：交給新版的 calculator 運算。
#    - 輸出適配：將計算結果 res.to_dict() 轉回 dict 供舊接口消費者使用。
# 3. ⚠️ 面試提點：這是日常開發最常用的重構技巧，能保證新舊架構平滑過渡，不需要一次性重寫整個系統。
# =====================================================================
def calculate_schedule_c_dynamic(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """相容舊版接口之總入口，執行 V1 計算引擎。"""
    inputs_copied = dict(inputs)
    
    # 合併預設值
    if "selected_mileage_method" not in inputs_copied:
        inputs_copied["selected_mileage_method"] = "standard"
    if "selected_home_method" not in inputs_copied:
        inputs_copied["selected_home_method"] = "simplified"
    if "accounting_method" not in inputs_copied:
        inputs_copied["accounting_method"] = "Cash"
        
    v1_inputs = ScheduleCInputsV1.from_dict(inputs_copied)
    res = calculate_schedule_c_v1(v1_inputs)
    res_dict = res.to_dict()
    
    # 為了對齊前端 UI 與測試 runner，將 v1_inputs 中的原始屬性併入 res_dict
    for k, val in v1_inputs.__dict__.items():
        if k not in res_dict:
            if isinstance(val, Decimal):
                res_dict[k] = float(val)
            else:
                res_dict[k] = val
                
    return res_dict
