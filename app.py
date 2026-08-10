import os
import time
from typing import List, Optional, Dict, Any, Union, Tuple
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from dotenv import load_dotenv

# 讀取環境變數
load_dotenv()

from retriever import IRACRetriever
import missing_form_detector
from processors.processors.schedule_c import (
    extract_schedule_c_inputs_with_logs,
    calculate_schedule_c_dynamic,
    extract_and_calculate_schedule_c as run_extract_and_calculate_schedule_c
)
from processors.processors.schedule_a import (
    extract_schedule_a_inputs_with_logs,
    calculate_schedule_a_dynamic
)
from processors.processors.schedule_b import (
    extract_schedule_b_inputs_with_logs,
    calculate_schedule_b_dynamic,
    extract_and_calculate_schedule_b as run_extract_and_calculate_schedule_b
)
from processors.processors.schedule_e import (
    extract_schedule_e_inputs_with_logs,
    calculate_schedule_e_dynamic,
    extract_and_calculate_schedule_e as run_extract_and_calculate_schedule_e
)
from processors.processors.schedule_1 import (
    extract_schedule_1_inputs_with_logs,
    calculate_schedule_1_dynamic,
    extract_and_calculate_schedule_1 as run_extract_and_calculate_schedule_1
)
from processors.processors.form_4562 import (
    extract_form_4562_inputs_with_logs,
    calculate_form_4562_dynamic,
    extract_and_calculate_form_4562 as run_extract_and_calculate_form_4562
)
import concurrent.futures
from adapter import (
    W2Adapter,
    ItemizedDeductionAdapter,
    RentalIncomeAndExpenseAdapter,
    PriorYearReturnAdapter
)
from mapper import (
    Form1040WagesMapper,
    ScheduleADeductionMapper,
    ScheduleDMapper,
    ScheduleEMapper,
    aggregate_form_1040_line_1a
)
from Flag.analyzer_core_v2 import analyze as flag_analyze
from Flag.form_status_analyzer import analyze_form_status as form_status_analyze



app = FastAPI(
    title="IRAC Tax RAG API",
    description="Expose the IRAC-based Knowledge Graph RAG as a REST API.",
    version="1.0.0"
)

# --- 模型名稱統一解析 ---
def resolve_model_name(requested: Optional[str]) -> str:
    """
    統一模型名稱解析邏輯：
    - 若 caller 明確傳入 model_name，直接使用。
    - 若環境變數 LLM_PROVIDER=ollama，使用 LLM_MODEL_NAME（預設 gemma4:31b）。
    - 其餘情況（包含未設定任何環境變數），一律回傳 gemini-2.5-pro。
    """
    if requested:
        return requested
    if os.environ.get("LLM_PROVIDER", "").lower() == "ollama":
        return os.environ.get("LLM_MODEL_NAME", "gemma4:31b")
    return "gemini-2.5-pro"

# --- 快取機制 ---
retriever_cache = {}

def get_retriever(kg_list: List[str]) -> IRACRetriever:
    vdb_mode = os.environ.get("VDB_MODE", "local").lower()
    kg_mode = os.environ.get("KG_MODE", "local").lower()
    
    # 根據不同的資料庫模式，決定快取金鑰 (Log 顯示名稱)
    if vdb_mode == "qdrant" and kg_mode == "neo4j":
        ws = os.environ.get("QDRANT_WORKSPACE", "default_ws")
        kg_key = f"Qdrant+Neo4j({ws})"
    else:
        kg_key = ",".join(sorted(kg_list)) or "default_local"

    if kg_key in retriever_cache:
        print(f"[API] Using cached retriever for: {kg_key}")
        return retriever_cache[kg_key]
    
    print(f"[API] Initializing new retriever for: {kg_key}...")
    os.environ["ACTIVE_KGS"] = kg_key
    
    retriever = IRACRetriever.from_active_kgs()
    retriever_cache[kg_key] = retriever
    return retriever

# --- 資料模型 ---
class QueryRequest(BaseModel):
    question: str
    active_kgs: Optional[List[str]] = None
    force_english: bool = False
    
    # --- 動態參數 (Dynamic Parameters) ---
    mode: Optional[str] = None
    use_source_text: Optional[bool] = None
    enable_hyde: Optional[bool] = None
    enable_step_back: Optional[bool] = None
    enable_multi_query: Optional[bool] = None
    enable_dual_track: Optional[bool] = None
    enable_bm25: Optional[bool] = None
    enable_kg_subgraph: Optional[bool] = None
    enable_recomp: Optional[bool] = None
    enable_sg_pruning: Optional[bool] = None
    use_jina_rerank: Optional[bool] = None
    context_strategy: Optional[str] = None
    context_threshold: Optional[float] = None
    context_fixed_full_count: Optional[int] = None
    context_fixed_sub_count: Optional[int] = None
    max_subgraphs: Optional[int] = None
    max_output_tokens: Optional[int] = None
    vector_threshold: Optional[float] = None
    dual_track_boost: Optional[float] = None

class QueryResponse(BaseModel):
    answer: str
    context: str
    latency: float
    debug_info: dict
    token_usage: Optional[dict] = None
    rule_candidates: Optional[List[dict]] = None

class MissingFormsRequest(BaseModel):
    question: Union[str, Dict[str, Any], List[Any]]
    strategy: Optional[str] = None
    model_name: Optional[str] = None

class MissingFormsResponse(BaseModel):
    answer: str
    latency: float
    token_usage: Optional[dict] = None
    debug_info: Optional[dict] = None

# --- API 路由 ---
@app.post("/query", response_model=QueryResponse)
async def query_rag(request: QueryRequest):
    if not request.question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    kg_list = request.active_kgs
    if not kg_list:
        kgs_env = os.environ.get("ACTIVE_KGS", "tax_kg_v1")
        kg_list = [k.strip() for k in kgs_env.split(",") if k.strip()]

    try:
        t0 = time.time()
        retriever = get_retriever(kg_list)
        
        # 執行檢索 (傳遞所有動態參數)
        result = retriever.retrieve(
            request.question, 
            force_english=request.force_english,
            mode=request.mode,
            use_source_text=request.use_source_text,
            enable_hyde=request.enable_hyde,
            enable_step_back=request.enable_step_back,
            enable_multi_query=request.enable_multi_query,
            enable_dual_track=request.enable_dual_track,
            enable_bm25=request.enable_bm25,
            enable_kg_subgraph=request.enable_kg_subgraph,
            enable_recomp=request.enable_recomp,
            enable_sg_pruning=request.enable_sg_pruning,
            use_jina_rerank=request.use_jina_rerank,
            context_strategy=request.context_strategy,
            context_threshold=request.context_threshold,
            context_fixed_full_count=request.context_fixed_full_count,
            context_fixed_sub_count=request.context_fixed_sub_count,
            max_subgraphs=request.max_subgraphs,
            max_output_tokens=request.max_output_tokens,
            vector_threshold=request.vector_threshold,
            dual_track_boost=request.dual_track_boost
        )
        
        latency = time.time() - t0
        
        # 清理內部欄位
        clean_candidates = []
        for c in result.get("rule_candidates", []):
            clean_candidates.append({k: v for k, v in c.items() if not k.startswith("_")})
        
        return QueryResponse(
            answer=result.get("answer", ""),
            context=result.get("context", ""),
            latency=latency,
            debug_info=result.get("debug_info", {}),
            token_usage=result.get("token_usage", {}),
            rule_candidates=clean_candidates
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"RAG Error: {str(e)}")

@app.post("/detect-missing-forms", response_model=MissingFormsResponse)
async def detect_missing_forms(request: MissingFormsRequest):
    
    question_data = request.question
    if not question_data:
        raise HTTPException(status_code=400, detail="Input content cannot be empty")
        
    if isinstance(question_data, (dict, list)):
        import json
        question_str = json.dumps(question_data, ensure_ascii=False)
    else:
        question_str = str(question_data)
        
    if not question_str.strip():
        raise HTTPException(status_code=400, detail="Input content cannot be empty")
        
    model_name = resolve_model_name(request.model_name)
        
    strategy = request.strategy
    if not strategy:
        strategy = os.environ.get("MISSING_FORM_STRATEGY", "Map-Reduce")
        
    api_key = os.environ.get("GEMINI_API_KEY")
    is_ollama = ":" in model_name
    if not is_ollama and not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY environment variable is not set")
        
    try:
        if strategy.lower() in ("map-reduce", "map_reduce"):
            result = await missing_form_detector.run_map_reduce_flow(question_str, model_name, api_key)
        else:
            result = await missing_form_detector.run_looping_flow(question_str, model_name, api_key)
            
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error in detection flow"))
            
        return MissingFormsResponse(
            answer=result["content"],
            latency=result["latency"],
            token_usage={
                "input_tokens": result["tokens"].get("promptTokenCount", 0),
                "output_tokens": result["tokens"].get("candidatesTokenCount", 0)
            },
            debug_info={
                "raw_json": result.get("raw_json"), 
                "strategy": strategy, 
                "model_name": model_name,
                "debug_steps": result.get("debug_steps")
            }
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Missing Forms Detection Error: {str(e)}")

@app.get("/health")
async def health_check():
    return {"status": "ok", "cached_retrievers": list(retriever_cache.keys())}

@app.get("/config")
async def get_config():
    from data_models import RetrieverConfig
    cfg = RetrieverConfig.from_env()
    return cfg.to_dict()


class ScheduleCExtractRequest(BaseModel):
    taxpayer_profile: Dict[str, Any]
    uploaded_documents: List[Dict[str, Any]]
    model_name: Optional[str] = None

class ScheduleAExtractRequest(BaseModel):
    taxpayer_profile: Dict[str, Any]
    uploaded_documents: List[Dict[str, Any]]
    model_name: Optional[str] = None

class ScheduleBExtractRequest(BaseModel):
    taxpayer_profile: Dict[str, Any]
    uploaded_documents: List[Dict[str, Any]]
    model_name: Optional[str] = None

class ScheduleEExtractRequest(BaseModel):
    taxpayer_profile: Dict[str, Any]
    uploaded_documents: List[Dict[str, Any]]
    model_name: Optional[str] = None

class Schedule1ExtractRequest(BaseModel):
    taxpayer_profile: Dict[str, Any]
    uploaded_documents: List[Dict[str, Any]]
    model_name: Optional[str] = None

class Form4562ExtractRequest(BaseModel):
    taxpayer_profile: Dict[str, Any]
    uploaded_documents: List[Dict[str, Any]]
    model_name: Optional[str] = None


class ExtractMapRequest(BaseModel):
    question: Union[str, Dict[str, Any], List[Any]]
    model_name: Optional[str] = None


class FlagAnalyzeRequest(BaseModel):
    question: Union[str, Dict[str, Any], List[Any]]
    model_name: Optional[str] = None
    use_kg: bool = False
    think: bool = False
    source_filename: Optional[str] = "upload.json"



@app.post("/schedule-c/extract-and-calculate")
def extract_and_calculate_schedule_c(
    request: ScheduleCExtractRequest
):
    
    # 統一使用結構化的 taxpayer_profile 與 uploaded_documents 格式
    import json
    payload = {
        "taxpayer_profile": request.taxpayer_profile,
        "uploaded_documents": request.uploaded_documents
    }
    
    # 將其轉換為 RAG 與 LLM 容易閱讀的文字排版格式
    doc_ctx_str = missing_form_detector.format_input_data(json.dumps(payload, ensure_ascii=False))

    if not doc_ctx_str.strip():
        raise HTTPException(
            status_code=400, 
            detail="文件內容不能為空，請提供有效的 taxpayer_profile 與 uploaded_documents 內容"
        )
        
    try:
        model_name = resolve_model_name(request.model_name)

        e2e_res = run_extract_and_calculate_schedule_c(
            document_context=doc_ctx_str,
            model_name=model_name
        )
        
        return {
            "success": True,
            "state": e2e_res["final_state"],
            "debug_info": {
                "model_name": model_name,
                "prompt_log": e2e_res["prompt_sent"],
                "raw_output": e2e_res["llm_raw_out"]
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"提取或計算失敗: {str(e)}")


@app.post("/schedule-a/extract-and-calculate")
def extract_and_calculate_schedule_a(
    request: ScheduleAExtractRequest
):
    
    import json
    payload = {
        "taxpayer_profile": request.taxpayer_profile,
        "uploaded_documents": request.uploaded_documents
    }
    
    doc_ctx_str = missing_form_detector.format_input_data(json.dumps(payload, ensure_ascii=False))

    if not doc_ctx_str.strip():
        raise HTTPException(
            status_code=400, 
            detail="文件內容不能為空，請提供有效的 taxpayer_profile 與 uploaded_documents 內容"
        )
        
    try:
        model_name = resolve_model_name(request.model_name)

        extracted_inputs, prompt_log, raw_output = extract_schedule_a_inputs_with_logs(
            document_context=doc_ctx_str,
            model_name=model_name
        )
        
        final_state = calculate_schedule_a_dynamic(extracted_inputs)
        
        return {
            "success": True,
            "state": final_state,
            "debug_info": {
                "model_name": model_name,
                "prompt_log": prompt_log,
                "raw_output": raw_output
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"提取或計算失敗: {str(e)}")


@app.post("/schedule-b/extract-and-calculate")
def extract_and_calculate_schedule_b(
    request: ScheduleBExtractRequest
):
    
    import json
    payload = {
        "taxpayer_profile": request.taxpayer_profile,
        "uploaded_documents": request.uploaded_documents
    }
    
    doc_ctx_str = missing_form_detector.format_input_data(json.dumps(payload, ensure_ascii=False))

    if not doc_ctx_str.strip():
        raise HTTPException(
            status_code=400, 
            detail="文件內容不能為空，請提供有效的 taxpayer_profile 與 uploaded_documents 內容"
        )
        
    try:
        model_name = resolve_model_name(request.model_name)

        e2e_res = run_extract_and_calculate_schedule_b(
            document_context=doc_ctx_str,
            model_name=model_name
        )
        
        return {
            "success": True,
            "state": e2e_res["final_state"],
            "debug_info": {
                "model_name": model_name,
                "prompt_log": e2e_res["prompt_sent"],
                "raw_output": e2e_res["llm_raw_out"]
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"提取或計算失敗: {str(e)}")


@app.post("/schedule-e/extract-and-calculate")
def extract_and_calculate_schedule_e(
    request: ScheduleEExtractRequest
):
    
    import json
    payload = {
        "taxpayer_profile": request.taxpayer_profile,
        "uploaded_documents": request.uploaded_documents
    }
    
    doc_ctx_str = missing_form_detector.format_input_data(json.dumps(payload, ensure_ascii=False))

    if not doc_ctx_str.strip():
        raise HTTPException(
            status_code=400, 
            detail="文件內容不能為空，請提供有效的 taxpayer_profile 與 uploaded_documents 內容"
        )
        
    try:
        model_name = resolve_model_name(request.model_name)

        e2e_res = run_extract_and_calculate_schedule_e(
            document_context=doc_ctx_str,
            model_name=model_name
        )
        
        return {
            "success": True,
            "state": e2e_res["final_state"],
            "debug_info": {
                "model_name": model_name,
                "prompt_log": e2e_res["prompt_sent"],
                "raw_output": e2e_res["llm_raw_out"]
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"提取或計算失敗: {str(e)}")


@app.post("/schedule-1/extract-and-calculate")
def extract_and_calculate_schedule_1(
    request: Schedule1ExtractRequest
):

    import json
    payload = {
        "taxpayer_profile": request.taxpayer_profile,
        "uploaded_documents": request.uploaded_documents
    }

    doc_ctx_str = missing_form_detector.format_input_data(json.dumps(payload, ensure_ascii=False))

    if not doc_ctx_str.strip():
        raise HTTPException(
            status_code=400,
            detail="文件內容不能為空，請提供有效的 taxpayer_profile 與 uploaded_documents 內容"
        )

    try:
        model_name = resolve_model_name(request.model_name)

        e2e_res = run_extract_and_calculate_schedule_1(
            document_context=doc_ctx_str,
            model_name=model_name
        )

        return {
            "success": True,
            "state": e2e_res["final_state"],
            "debug_info": {
                "model_name": model_name,
                "prompt_log": e2e_res["prompt_sent"],
                "raw_output": e2e_res["llm_raw_out"]
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"提取或計算失敗: {str(e)}")


@app.post("/form-4562/extract-and-calculate")
def extract_and_calculate_form_4562(
    request: Form4562ExtractRequest
):

    import json
    payload = {
        "taxpayer_profile": request.taxpayer_profile,
        "uploaded_documents": request.uploaded_documents
    }

    doc_ctx_str = missing_form_detector.format_input_data(json.dumps(payload, ensure_ascii=False))

    if not doc_ctx_str.strip():
        raise HTTPException(
            status_code=400,
            detail="文件內容不能為空，請提供有效的 taxpayer_profile 與 uploaded_documents 內容"
        )

    try:
        model_name = resolve_model_name(request.model_name)

        e2e_res = run_extract_and_calculate_form_4562(
            document_context=doc_ctx_str,
            model_name=model_name
        )

        return {
            "success": True,
            "state": e2e_res["final_state"],
            "debug_info": {
                "model_name": model_name,
                "prompt_log": e2e_res["prompt_sent"],
                "raw_output": e2e_res["llm_raw_out"]
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"提取或計算失敗: {str(e)}")





FLAG_ALLOWED_MODELS = {"gemini-2.5-flash", "gemini-2.5-pro", "gemma4:31b"}


@app.post("/flag/analyze")
async def flag_analyze_endpoint(
    request: FlagAnalyzeRequest
):

    q_data = request.question
    if isinstance(q_data, str):
        import json
        try:
            q_data = json.loads(q_data)
        except Exception:
            raise HTTPException(status_code=400, detail="question 不是有效的 JSON")
    if not isinstance(q_data, dict):
        raise HTTPException(status_code=400, detail="question 必須是 JSON 物件（taxpayer_profile/uploaded_documents 或舊版扁平格式）")

    model_name = request.model_name or os.environ.get("LLM_MODEL_NAME", "gemini-2.5-pro")
    if model_name not in FLAG_ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model_name}")
    if model_name.startswith("gemini") and not os.environ.get("GEMINI_API_KEY"):
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY environment variable is not set")

    t_start = time.time()
    try:
        result = await flag_analyze(
            extracted_data=q_data,
            source_filename=request.source_filename or "upload.json",
            model=model_name,
            use_kg=request.use_kg,
            think=request.think,
        )
        result["success"] = True
        result["latency"] = time.time() - t_start
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Flag Analyze Failed: {str(e)}")


@app.post("/flag/form-status")
async def flag_form_status_endpoint(
    request: FlagAnalyzeRequest
):

    q_data = request.question
    if isinstance(q_data, str):
        import json
        try:
            q_data = json.loads(q_data)
        except Exception:
            raise HTTPException(status_code=400, detail="question 不是有效的 JSON")
    if not isinstance(q_data, dict):
        raise HTTPException(status_code=400, detail="question 必須是 JSON 物件（taxpayer_profile/uploaded_documents 或舊版扁平格式）")

    # 預設為 gemini-2.5-pro
    model_name = request.model_name or os.environ.get("LLM_MODEL_NAME", "gemini-2.5-pro")
    if model_name not in FLAG_ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown model: {model_name}")
    if model_name.startswith("gemini") and not os.environ.get("GEMINI_API_KEY"):
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY environment variable is not set")

    t_start = time.time()
    try:
        result = await form_status_analyze(
            extracted_data=q_data,
            source_filename=request.source_filename or "upload.json",
            model=model_name,
            use_kg=request.use_kg,
            think=request.think,
        )
        result["success"] = True
        result["latency"] = time.time() - t_start
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Form Status Analyze Failed: {str(e)}")


class Form1040AssembleRequest(BaseModel):
    taxpayer_profile: Dict[str, Any]
    uploaded_documents: List[Dict[str, Any]]
    model_name: Optional[str] = None


@app.post("/form-1040/assemble")
async def assemble_form_1040(
    request: Form1040AssembleRequest
):
    from form1040.orchestrator import Form1040Orchestrator
    
    t_start = time.time()
    try:
        res = Form1040Orchestrator.extract_and_assemble(
            taxpayer_profile=request.taxpayer_profile,
            uploaded_documents=request.uploaded_documents,
            model_name=request.model_name
        )
        res["success"] = True
        res["latency"] = time.time() - t_start
        return res
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Form 1040 Assembly Failed: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    # 移除預先初始化 retriever，改為 lazy load（第一次 API 請求時才連線）
    # 這樣即使 Neo4j 7687 暫時不可用，API server 也能正常啟動
    port = int(os.environ.get("PORT", 8088))
    uvicorn.run(app, host="0.0.0.0", port=port)
