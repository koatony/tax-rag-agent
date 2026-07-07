# =====================================================================
# REVIEW 重點 1: 設計模式 —— 適配器模式 (Adapter Pattern)
# =====================================================================
# 【為什麼需要適配器（相容層）？】
# 1. 系統重構過程中，最忌諱一次性將前後端、資料庫、測試系統全部重寫（Big Bang Rewrite），這極易引發線上災難。
# 2. 我們在此處保留原本弱型別 `calculate_schedule_b_dynamic(inputs: Dict[str, Any])` 接口作為「適配器」。
# 3. 在其內部，將輸入轉化為新版的強型別 Inputs 物件，執行核心計算後再轉回舊版期望的輸出格式。
# 4. 這使得我們能平滑過渡到新架構，而對上層系統零干擾。
# =====================================================================

import json
import os
import re
from typing import Dict, Any, List, Tuple
from decimal import Decimal
from dotenv import load_dotenv

# Import from modular OOP layers
from processors.models.schedule_b import (
    InterestItemV1,
    DividendItemV1,
    MarketDiscountItemV1,
    Form8815V1,
    SpecialCaseFlagsBV1,
    ScheduleBInputsV1,
    ScheduleBResultV1,
)
from processors.validators.schedule_b import (
    validate_identity,
    validate_tax_year,
    detect_unsupported_cases,
    validate_amounts,
    validate_form_8815,
    validate_part_iii,
)
from processors.calculators.schedule_b import (
    sum_decimal,
    coalesce_decimal,
    process_interest_items,
    process_market_discount_items,
    process_dividend_items,
    aggregate_interest_entries,
    aggregate_dividend_entries,
    any_special_case,
    calculate_schedule_b_v1,
)
from processors.parsers.schedule_b import ScheduleBLLMParser

# 載入環境變數
load_dotenv()

SCHEMA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "docs", "how_to_fill_forms_docs", "schedule_b", "schedule_b_schema.json"))

def load_schedule_b_schema() -> Dict[str, Any]:
    """載入外部的 Schedule B V1 欄位與計算規則設定檔 (schedule_b_schema.json)。"""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_schedule_b_inputs_with_logs(
    document_context: str, 
    model_name: str = "gemini-2.5-pro"
) -> Tuple[Dict[str, Any], str, str]:
    """呼叫 LLM 進行 Schedule B 數據提取，並回傳: (提取 JSON, 發送 Prompt, LLM 原始輸出)。"""
    parser = ScheduleBLLMParser(model_name=model_name)
    return parser.parse(document_context)

def topological_sort(formula_deps: Dict[str, List[str]]) -> List[str]:
    """使用 DFS 演算法對公式依賴樹進行拓撲排序，排除循環引用。"""
    visited = {}  # 0: unvisited, 1: visiting, 2: visited
    order = []
    
    def dfs(node):
        if visited.get(node, 0) == 1:
            raise ValueError(f"公式依賴檢測到循環引用 (Cycle detected at node): {node}")
        if visited.get(node, 0) == 2:
            return
            
        visited[node] = 1  # visiting
        for dep in formula_deps.get(node, []):
            if dep in formula_deps:
                dfs(dep)
        visited[node] = 2  # visited
        order.append(node)
        
    for node in formula_deps:
        if visited.get(node, 0) == 0:
            dfs(node)
            
    return order

def calculate_schedule_b_dynamic(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """相容舊版接口之總入口，執行 V1 計算引擎。"""
    # 歷史變數對齊 (相容舊名)
    inputs_copied = dict(inputs)
    if 'foreign_accounts_interest' in inputs_copied and 'foreign_account_q1' not in inputs_copied:
        inputs_copied['foreign_account_q1'] = inputs_copied['foreign_accounts_interest']
    if 'foreign_trust_distribution' in inputs_copied and 'foreign_trust_q8' not in inputs_copied:
        inputs_copied['foreign_trust_q8'] = inputs_copied['foreign_trust_distribution']
        
    # No external defaults merging; defaults are resolved via strong-typed data models or validators.
        
    v1_inputs = ScheduleBInputsV1.from_dict(inputs_copied)
    res = calculate_schedule_b_v1(v1_inputs)
    res_dict = res.to_dict()
    
    # 舊屬性回退相容 (對齊前端 UI/測試屬性)
    res_dict['line_4_taxable_interest'] = res_dict.get('line_4_surface_value')
    res_dict['needs_human_review'] = not res.can_file
    res_dict['foreign_accounts_interest'] = res.line_7a_q1_surface if res.line_7a_q1_surface is not None else inputs_copied.get('foreign_account_q1')
    res_dict['foreign_trust_distribution'] = res.line_8_surface if res.line_8_surface is not None else inputs_copied.get('foreign_trust_q8')
    res_dict['line_7a_foreign_account_authority'] = res.line_7a_q1_surface
    res_dict['line_7a_fbar_required'] = res.line_7a_q2_surface
    res_dict['line_7b_foreign_countries'] = res.line_7b_surface
    res_dict['line_8_foreign_trust_distribution'] = res.line_8_surface
    res_dict['has_seller_financed_mortgage'] = not res.is_v1_supported and bool(v1_inputs.special_case_flags.has_seller_financed_mortgage)
    res_dict['taxpayer_ssn_masked'] = res.taxpayer_ssn_masked
    res_dict['ssn'] = res.taxpayer_ssn_masked
    res_dict['agi'] = float(inputs_copied.get('adjusted_gross_income', 0.0))
    
    return res_dict
