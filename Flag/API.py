"""
Standalone FastAPI service for Flag Metaya.

Run (from the project root, one level above Flag/):
    source .venv/bin/activate
    uvicorn Flag.API:app --reload --port 8000

GET  /         serves the self-contained UI (static/index.html), which posts to /analyze.
POST /analyze  runs the PLANNER -> MAP tax audit pipeline and returns the flags result.
"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .analyzer_core_v2 import analyze

ALLOWED_MODELS = {"gemini-2.5-flash", "gemini-2.5-pro", "gemma4:31b"}
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Flag Metaya — Tax Audit Analyzer")


class AnalyzeRequest(BaseModel):
    model: str
    financial_data: dict
    source_filename: str = "web_input.json"
    use_kg: bool = False
    think: bool = False


@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/analyze")
async def analyze_endpoint(req: AnalyzeRequest):
    if req.model not in ALLOWED_MODELS:
        raise HTTPException(status_code=400, detail=f"Unsupported model: {req.model}")
    if req.model in ("gemini-2.5-flash", "gemini-2.5-pro") and not os.environ.get("GEMINI_API_KEY"):
        raise HTTPException(status_code=400, detail="GEMINI_API_KEY is not configured on the server")

    try:
        return await analyze(
            extracted_data=req.financial_data,
            source_filename=req.source_filename,
            model=req.model,
            use_kg=req.use_kg,
            think=req.think,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
