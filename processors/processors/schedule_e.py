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


def extract_and_calculate_schedule_e(
    document_context: str, model_name: str = "gemini-2.5-pro"
) -> Dict[str, Any]:
    """E2E 入口：從文字憑證中提取欄位，整合 Form 4562 計算，並直接執行 V1 計算引擎，回傳結果與日誌。"""
    # 1. 執行 Schedule E 提取
    extracted_inputs, prompt_sent, llm_raw_out = extract_schedule_e_inputs_with_logs(
        document_context=document_context, model_name=model_name
    )

    # 2. 執行 Form 4562 提取與計算（若有缺失身份元數據，則共享 Schedule E 的提取結果）
    from form_4562_processor import extract_form_4562_inputs_with_logs, calculate_form_4562_dynamic
    form_4562_state = {}
    try:
        f4562_inputs, f4562_prompt, f4562_raw = extract_form_4562_inputs_with_logs(
            document_context, model_name=model_name
        )
        
        # 共享注入身分資訊，避免因缺少 SSN 造成 Form 4562 計算阻斷
        if not f4562_inputs.get("taxpayer_ssn") and extracted_inputs.get("taxpayer_ssn"):
            f4562_inputs["taxpayer_ssn"] = extracted_inputs["taxpayer_ssn"]
        if not f4562_inputs.get("taxpayer_name") and extracted_inputs.get("taxpayer_name"):
            f4562_inputs["taxpayer_name"] = extracted_inputs["taxpayer_name"]
            
        form_4562_state = calculate_form_4562_dynamic(f4562_inputs)
    except Exception as e:
        # Fallback if Form 4562 execution fails
        pass

    # 3. 將 Form 4562 結果注入對應的 property 中
    # (提示: matched_prop 是 properties 列表內的字典引用，修改它會原地 (in-place) 變更 extracted_inputs，
    # 讓接下來的 calculate_schedule_e_dynamic 可以直接讀取到已注入的 depreciation_result)
    if form_4562_state and "properties" in extracted_inputs:
        properties = extracted_inputs["properties"]
        if properties:
            # 檢查 Form 4562 的計算是否包含阻斷錯誤（例如：不支援的稅務年度、特殊的折舊申報情況等）
            has_blocking = form_4562_state.get("blocking_validation_error") or len(form_4562_state.get("blocking_errors", [])) > 0
            # 若有阻斷錯誤則狀態設為 BLOCKED，否則設為 CALCULATED 以供 Schedule E 正確採用折舊金額
            calc_status = "BLOCKED" if has_blocking else "CALCULATED"
            
            ban = form_4562_state.get("business_activity_name", "").strip().lower()
            
            # 尋找與 Form 4562 計算結果（透過 business_activity_name）匹配的 Schedule E 房產 (Property)
            matched_prop = None
            if len(properties) == 1:
                # 只有一間房產時直接匹配，免去比對邏輯
                matched_prop = properties[0]
            else:
                for prop in properties:
                    addr = prop.get("physical_address") or {}
                    street = str(addr.get("street") or "").strip().lower()
                    # 情況一：街道地址與 Form 4562 業務名稱直接包含（例如 5200 Green Valley 匹配 5200 Green Valley Dr.）
                    if street and (street in ban or ban in street):
                        matched_prop = prop
                        break
                    
                    # 情況二：提取街道名稱中長度 > 3 的字詞（如 green, valley）進行關鍵字模糊匹配
                    street_words = [w for w in street.replace(",", " ").split() if len(w) > 3]
                    if street_words and any(w in ban for w in street_words):
                        matched_prop = prop
                        break
                
                # 情況三：若都沒有匹配成功，則安全回退，預設注入到第一間房產
                if not matched_prop:
                    matched_prop = properties[0]
            
            if matched_prop:
                dep_res = {
                    "property_id": matched_prop.get("property_id"),
                    "tax_year": form_4562_state.get("tax_year") or extracted_inputs.get("tax_year") or 2025,
                    "calculation_status": calc_status,
                    "depreciation_amount": form_4562_state.get("line_22_total_depreciation_and_amortization", 0.0),
                    "line_22_total_depreciation_and_amortization": form_4562_state.get("line_22_total_depreciation_and_amortization"),
                    "form_4562_attachment_required": form_4562_state.get("should_attach_form_4562", False),
                    "source_result_id": "processor_4562",
                    "blocking_errors": form_4562_state.get("blocking_errors", []),
                    "review_warnings": form_4562_state.get("review_warnings", [])
                }
                matched_prop["depreciation_result"] = dep_res

    # 4. 執行 Schedule E 計算
    final_state = calculate_schedule_e_dynamic(extracted_inputs)

    return {
        "extracted_inputs": extracted_inputs,
        "final_state": final_state,
        "prompt_sent": prompt_sent,
        "llm_raw_out": llm_raw_out,
    }

