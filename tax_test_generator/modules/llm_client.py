"""
llm_client.py
Wraps the Gemini API using raw HTTP requests (mimicking llm_wrappers.py)
to support OAuth Access Tokens (AQ.) which the official SDK rejects.
"""
import os
import time
import json
import httpx
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

# 自動往上層目錄尋找 .env 檔案
load_dotenv(find_dotenv())

class LLMClient:
    def __init__(self):
        # 讀取 API Key (可以是 AIza... 或 AQ....)
        self.api_key = os.getenv("GEMINI_API_KEY", "").strip("'\"")
        self.model_name = os.getenv("LLM_MODEL_NAME", "gemini-1.5-flash")
        
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in .env")
            
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.upload_url = "https://generativelanguage.googleapis.com/upload/v1beta"

    def upload_pdf(self, pdf_path: str) -> dict:
        """使用 REST API 上傳 PDF 到 Google File API"""
        print(f"[LLMClient] Uploading PDF via REST: {pdf_path}")
        path = Path(pdf_path)
        file_size = path.stat().st_size
        
        # 1. 啟動上傳
        headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(file_size),
            "X-Goog-Upload-Header-Content-Type": "application/pdf",
            "Content-Type": "application/json",
        }
        
        init_url = f"{self.upload_url}/files?key={self.api_key}"
        metadata = {"file": {"display_name": path.name}}
        
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(init_url, headers=headers, json=metadata)
            resp.raise_for_status()
            upload_url = resp.headers["X-Goog-Upload-URL"]
            
            # 2. 上傳檔案內容
            with open(path, "rb") as f:
                data = f.read()
            
            final_headers = {
                "X-Goog-Upload-Offset": "0",
                "X-Goog-Upload-Command": "upload, finalize",
            }
            resp = client.post(upload_url, headers=final_headers, content=data)
            resp.raise_for_status()
            file_data = resp.json()
            
        print(f"[LLMClient] Uploaded! File URI: {file_data['file']['uri']}")
        return file_data["file"]

    def generate_json(self, prompt: str, pdf_file: dict = None) -> dict:
        """模仿 llm_wrappers.py 使用 httpx 調用 generateContent"""
        url = f"{self.base_url}/models/{self.model_name}:generateContent?key={self.api_key}"
        
        parts = [{"text": prompt}]
        if pdf_file and "uri" in pdf_file:
            parts.insert(0, {
                "file_data": {
                    "mime_type": "application/pdf",
                    "file_uri": pdf_file["uri"]
                }
            })
            
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": 0.2,
                "response_mime_type": "application/json"
            }
        }
        
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code != 200:
                print(f"[LLMClient] ❌ API 錯誤狀態碼: {resp.status_code}")
                print(f"[LLMClient] ❌ 錯誤詳情: {resp.text}")
                resp.raise_for_status()
            
            data = resp.json()
            text_content = data['candidates'][0]['content']['parts'][0]['text']
            
            # 清理 Markdown 代碼塊
            if "```json" in text_content:
                text_content = text_content.split("```json")[1].split("```")[0].strip()
            elif "```" in text_content:
                text_content = text_content.split("```")[1].split("```")[0].strip()
                
            return json.loads(text_content)
