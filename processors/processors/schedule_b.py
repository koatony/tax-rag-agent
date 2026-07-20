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
    process_market_discount_items,
    aggregate_interest_entries,
    aggregate_dividend_entries,
    any_special_case,
    calculate_schedule_b_v1,
)
from processors.parsers.schedule_b import ScheduleBLLMParser

load_dotenv()

SCHEMA_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "docs",
        "how_to_fill_forms_docs",
        "schedule_b",
        "schedule_b_schema.json",
    )
)


def load_schedule_b_schema() -> Dict[str, Any]:
    """載入外部的 Schedule B V1 欄位與計算規則設定檔 (schedule_b_schema.json)。"""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_schedule_b_inputs_with_logs(
    document_context: str, model_name: str = "gemini-2.5-pro"
) -> Tuple[Dict[str, Any], str, str]:
    """呼叫 LLM 進行 Schedule B 數據提取，並回傳: (提取 JSON, 發送 Prompt, LLM 原始輸出)。"""
    parser = ScheduleBLLMParser(model_name=model_name)
    return parser.parse(document_context)


def calculate_schedule_b_dynamic(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """執行 Schedule B V1 計算引擎，回傳強型別 V1 計算結果字典。"""
    inputs_copied = dict(inputs)

    if not inputs_copied.get("form_8815"):
        config_path = os.path.join(os.path.dirname(SCHEMA_PATH), "form_8815_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                if "form_8815" in config_data:
                    inputs_copied["form_8815"] = config_data["form_8815"]
                else:
                    inputs_copied["form_8815"] = config_data
            except Exception:
                pass

    v1_inputs = ScheduleBInputsV1.from_dict(inputs_copied)
    try:
        schema = load_schedule_b_schema()
        allowed_years = set(schema.get("supported_tax_years", [2024, 2025]))
    except Exception:
        allowed_years = {2024, 2025}
    res = calculate_schedule_b_v1(v1_inputs, allowed_years=allowed_years)
    return res.to_dict()


def extract_and_calculate_schedule_b(
    document_context: str, model_name: str = "gemini-2.5-pro"
) -> Dict[str, Any]:
    """E2E 入口：從文字憑證中提取欄位，並直接執行 V1 計算引擎，回傳結果與日誌。"""
    extracted_inputs, prompt_sent, llm_raw_out = extract_schedule_b_inputs_with_logs(
        document_context=document_context, model_name=model_name
    )
    final_state = calculate_schedule_b_dynamic(extracted_inputs)
    return {
        "extracted_inputs": extracted_inputs,
        "final_state": final_state,
        "prompt_sent": prompt_sent,
        "llm_raw_out": llm_raw_out,
    }
