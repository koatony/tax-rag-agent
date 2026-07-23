import json
import os
from typing import Dict, Any, Tuple
from dotenv import load_dotenv

from processors.models.schedule_c import ScheduleCInputsV1, ScheduleCResultV1
from processors.calculators.schedule_c import calculate_schedule_c_v1
from processors.parsers.schedule_c import ScheduleCLLMParser

load_dotenv()

SCHEMA_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "docs",
        "how_to_fill_forms_docs",
        "schedule_c",
        "schedule_c_schema.json",
    )
)


def load_schedule_c_schema() -> Dict[str, Any]:
    """載入外部的 Schedule C Schema 設定檔。"""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_schedule_c_inputs_with_logs(
    document_context: str, model_name: str = "gemini-2.5-pro"
) -> Tuple[Dict[str, Any], str, str]:
    """呼叫 LLM 進行欄位提取。"""
    parser = ScheduleCLLMParser(model_name=model_name)
    return parser.parse(document_context)


def calculate_schedule_c_dynamic(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """相容舊版接口之總入口，執行 V1 計算引擎。"""
    v1_inputs = ScheduleCInputsV1.from_dict(inputs)
    schema = load_schedule_c_schema()
    allowed_years = set(schema.get("supported_tax_years", []))
    res = calculate_schedule_c_v1(v1_inputs, allowed_years=allowed_years)
    return res.to_dict()


def extract_and_calculate_schedule_c(
    document_context: str, model_name: str = "gemini-2.5-pro"
) -> Dict[str, Any]:
    """E2E 入口：從文字憑證中提取欄位，並直接執行 V1 計算引擎，回傳結果與日誌。"""
    extracted_inputs, prompt_sent, llm_raw_out = extract_schedule_c_inputs_with_logs(
        document_context=document_context, model_name=model_name
    )
    final_state = calculate_schedule_c_dynamic(extracted_inputs)
    return {
        "extracted_inputs": extracted_inputs,
        "final_state": final_state,
        "prompt_sent": prompt_sent,
        "llm_raw_out": llm_raw_out,
    }
