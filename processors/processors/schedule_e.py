import json
import os
from typing import Dict, Any, Tuple
from decimal import Decimal
from dotenv import load_dotenv

# Import from modular OOP layers
from processors.models.schedule_e import (
    ScheduleEPart1InputsV1,
    ScheduleEPart1ResultV1,
)
from processors.calculators.schedule_e import (
    calculate_schedule_e_part1_v1,
)
from processors.parsers.schedule_e import ScheduleELLMParser

load_dotenv()

SCHEMA_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "docs",
        "how_to_fill_forms_docs",
        "schedule_e",
        "schedule_e_schema.json",
    )
)


def load_schedule_e_schema() -> Dict[str, Any]:
    """載入外部的 Schedule E 欄位與計算規則設定檔 (schedule_e_schema.json)。"""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_schedule_e_inputs_with_logs(
    document_context: str, model_name: str = "gemini-2.5-pro"
) -> Tuple[Dict[str, Any], str, str]:
    """呼叫 LLM 進行 Schedule E 數據提取，並回傳: (提取 JSON, 發送 Prompt, LLM 原始輸出)。"""
    parser = ScheduleELLMParser(model_name=model_name)
    return parser.parse(document_context)


def calculate_schedule_e_dynamic(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """相容舊版接口之總入口，執行 Schedule E V1 計算引擎。"""
    v1_inputs = ScheduleEPart1InputsV1.from_dict(inputs)
    try:
        schema = load_schedule_e_schema()
        allowed_years = set(schema.get("supported_tax_years", [2024, 2025]))
    except Exception:
        allowed_years = {2024, 2025}
    res = calculate_schedule_e_part1_v1(v1_inputs, allowed_years=allowed_years)
    res_dict = res.to_dict()
    return res_dict
