import os
import json
import glob
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models
import httpx
from langchain_core.messages import HumanMessage
from utils import clean_json, json_to_markdown

# 載入環境變數 (目前在父目錄)
load_dotenv(dotenv_path="../.env")

# Qdrant 配置
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "tax_forms_v1")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://140.115.54.89:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "bge-m3")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gemini-2.0-flash")


def ollama_embed(text: str) -> list[float]:
    """BGE-M3 via Ollama (1024 dim)"""
    url = f"{OLLAMA_BASE_URL}/api/embed"
    resp = httpx.post(url, json={"model": OLLAMA_EMBED_MODEL, "input": text}, timeout=120)
    resp.raise_for_status()
    return resp.json()["embeddings"][0]


def gemini_invoke(prompt: str) -> str:
    """Gemini LLM 呼叫 (含 fallback)"""
    api_key = GEMINI_API_KEY
    models_to_try = [LLM_MODEL_NAME, "gemini-2.0-flash", "gemini-1.5-flash"]
    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 512},
        }
        try:
            resp = httpx.post(url, json=payload, timeout=60)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            print(f"[OCR/LLM] {model} failed: {e}")
            continue
    return "摘要生成失敗。"

class OCRProcessor:
    def __init__(self):
        print(f"初始化 Qdrant Client: {QDRANT_HOST}:{QDRANT_PORT}")
        self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

        self._ensure_collection()

    def _ensure_collection(self):
        """確保 Qdrant Collection 存在"""
        collections = self.client.get_collections().collections
        exists = any(c.name == COLLECTION_NAME for c in collections)
        
        if not exists:
            print(f"建立新的 Collection: {COLLECTION_NAME}")
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(size=1024, distance=models.Distance.COSINE),
            )
        else:
            print(f"使用現有 Collection: {COLLECTION_NAME}")

    def generate_summary(self, json_data: dict) -> str:
        """呼叫 Gemini LLM 產生語意摘要"""
        prompt = f"""This is JSON data extracted from a tax form via OCR.
Please write a concise semantic summary (100-150 words) describing the document's year, type, taxpayer identity, and key financial details (wages, contribution codes, taxes etc).
Do NOT output JSON. Output summary text only.

JSON Data:
{json.dumps(json_data, indent=2)}
"""
        return gemini_invoke(prompt)

    def process_file(self, file_path: str):
        """處理單一 JSON 檔案並儲存至 Qdrant"""
        print(f"\n正在處理: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        # 1. 數據清洗
        cleaned_data = clean_json(raw_data)
        
        # 2. 產出 Markdown 表格
        md_content = json_to_markdown(cleaned_data)
        
        # 3. 產出 LLM 語意摘要
        print("  正在呼叫 LLM 生成語意摘要...")
        summary = self.generate_summary(cleaned_data)
        
        # 4. 合併為最終的索引索引文字
        # 格式：[摘要] \n\n [Markdown 表格]
        final_text = f"{summary}\n\n{md_content}"
        
        print("  正在忟量化...")
        vector = ollama_embed(final_text)
        
        # 6. Upsert 到 Qdrant
        doc_id = os.path.basename(file_path).replace(".json", "")
        print(f"  正在儲存到 Qdrant (ID: {doc_id})...")
        self.client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                models.PointStruct(
                    id=abs(hash(doc_id)) % (10**10), # 簡單的 int ID 轉換，生產環境建議用 UUID
                    vector=vector,
                    payload={
                        "doc_id": doc_id,
                        "content": final_text,
                        "raw_json": cleaned_data,
                        "summary": summary,
                        "year": cleaned_data.get("year"),
                        "form_type": cleaned_data.get("form_type")
                    }
                )
            ]
        )
        print(f"  完成！")

    def run_all(self, data_dir: str):
        """處理資料夾下所有 JSON"""
        files = glob.glob(os.path.join(data_dir, "*.json"))
        print(f"找到 {len(files)} 個檔案...")
        for f in files:
            self.process_file(f)

if __name__ == "__main__":
    processor = OCRProcessor()
    processor.run_all("data")
