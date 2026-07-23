# =====================================================================
# REVIEW 重點 1: 設計模式 —— 適配器模式 (Adapter Pattern)
# =====================================================================
# 【為什麼需要適配器（相容層）？】
# 1. 系統重構過程中，最忌諱一次性將前後端、資料庫、測試系統全部重寫（Big Bang Rewrite），這極易引發線上災難。
# 2. 我們在此處保留原本弱型別 `calculate_schedule_1_dynamic(inputs: Dict[str, Any])` 接口作為「適配器」。
# 3. 在其內部，將輸入轉化為新版的強型別 Inputs 物件，執行核心計算後再轉回舊版期望的輸出格式。
# 4. 這使得我們能平滑過渡到新架構，而對上層系統零干擾。
# =====================================================================

import json
import os
from typing import Dict, Any, Tuple
from dotenv import load_dotenv

# Import from modular OOP layers
from processors.models.schedule_1 import (
    OtherIncomeItemV1,
    AdjustmentItemV1,
    SpecialCaseFlags1V1,
    Schedule1InputsV1,
    Schedule1ResultV1,
)
from processors.validators.schedule_1 import (
    validate_identity,
    validate_tax_year,
    detect_unsupported_cases,
    validate_amounts,
)
from processors.calculators.schedule_1 import (
    sum_decimal,
    signed_amount,
    any_special_case,
    calculate_schedule_1_v1,
)
from processors.parsers.schedule_1 import Schedule1LLMParser

# 載入環境變數
load_dotenv()

SCHEMA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "docs", "how_to_fill_forms_docs", "schedule_1", "schedule_1_schema.json"))

def load_schedule_1_schema() -> Dict[str, Any]:
    """載入外部的 Schedule 1 V1 欄位與計算規則設定檔 (schedule_1_schema.json)。"""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_schedule_1_inputs_with_logs(
    document_context: str,
    model_name: str = "gemini-2.5-pro"
) -> Tuple[Dict[str, Any], str, str]:
    """呼叫 LLM 進行 Schedule 1 數據提取，並回傳: (提取 JSON, 發送 Prompt, LLM 原始輸出)。"""
    parser = Schedule1LLMParser(model_name=model_name)
    return parser.parse(document_context)

def calculate_schedule_1_dynamic(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """執行 Schedule 1 V1 計算引擎，回傳強型別 V1 計算結果字典。"""
    inputs_copied = dict(inputs)

    v1_inputs = Schedule1InputsV1.from_dict(inputs_copied)
    schema = load_schedule_1_schema()
    allowed_years = set(schema.get("supported_tax_years", []))
    res = calculate_schedule_1_v1(v1_inputs, allowed_years=allowed_years)
    return res.to_dict()

def extract_and_calculate_schedule_1(
    document_context: str,
    model_name: str = "gemini-2.5-pro"
) -> Dict[str, Any]:
    """E2E 入口：從文字憑證中提取欄位，並直接執行 V1 計算引擎，回傳結果與日誌。"""
    extracted_inputs, prompt_sent, llm_raw_out = extract_schedule_1_inputs_with_logs(
        document_context=document_context,
        model_name=model_name
    )
    final_state = calculate_schedule_1_dynamic(extracted_inputs)
    return {
        "extracted_inputs": extracted_inputs,
        "final_state": final_state,
        "prompt_sent": prompt_sent,
        "llm_raw_out": llm_raw_out
    }
