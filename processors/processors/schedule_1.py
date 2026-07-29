import json
import os
from typing import Dict, Any, Tuple
from dotenv import load_dotenv

# Import from modular OOP layers
from processors.models.schedule_1 import Schedule1InputsV1
from processors.calculators.schedule_1 import calculate_schedule_1_v1
from processors.parsers.schedule_1 import Schedule1LLMParser

load_dotenv()

SCHEMA_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "docs",
        "how_to_fill_forms_docs",
        "schedule_1",
        "schedule_1_schema.json",
    )
)


def load_schedule_1_schema() -> Dict[str, Any]:
    """載入外部的 Schedule 1 V1 欄位與計算規則設定檔 (schedule_1_schema.json)。"""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_schedule_1_inputs_with_logs(
    document_context: str, model_name: str = "gemini-2.5-pro"
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
    document_context: str, model_name: str = "gemini-2.5-pro"
) -> Dict[str, Any]:
    """E2E 入口：從文字憑證中提取欄位，並直接執行 V1 計算引擎，回傳結果與日誌。"""
    extracted_inputs, prompt_sent, llm_raw_out = extract_schedule_1_inputs_with_logs(
        document_context=document_context, model_name=model_name
    )
    final_state = calculate_schedule_1_dynamic(extracted_inputs)
    return {
        "extracted_inputs": extracted_inputs,
        "final_state": final_state,
        "prompt_sent": prompt_sent,
        "llm_raw_out": llm_raw_out,
    }
