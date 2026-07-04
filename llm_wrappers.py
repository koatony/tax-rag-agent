"""
LLM 與 Embedding 的 API 封裝
==============================
包含：
1. OllamaEmbeddings: 使用本地 Ollama 伺服器進行向量化 (BGE-M3)。
2. GeminiLLM: 串接 Google Gemini API 做為推理與評估引擎。
"""

import os
import httpx
import time as _time
from typing import Any, List
from langchain_core.messages import SystemMessage, HumanMessage

class OllamaEmbeddings:
    """
    使用 Ollama 上的 BGE-M3 模型進行向量化。
    BGE-M3 輸出 1024 維向量，與現有 VDB 維度一致。
    """
    def __init__(self, model_name: str = "bge-m3", base_url: str = None):
        self.model_name = model_name
        self.base_url = (base_url
                         or os.environ.get("OLLAMA_BASE_URL", "http://140.115.54.89:11434")).rstrip("/")

    def _embed_single(self, text: str) -> List[float]:
        url = f"{self.base_url}/api/embed"
        payload = {"model": self.model_name, "input": text}
        last_err = None
        for attempt in range(3):
            try:
                with httpx.Client(timeout=180.0) as client:
                    resp = client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    return data["embeddings"][0]
            except Exception as e:
                last_err = e
                print(f"  [OllamaEmb] Attempt {attempt+1} failed: {e}")
                _time.sleep(1 + attempt)
        raise last_err

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批次向量化"""
        url = f"{self.base_url}/api/embed"
        batch_size = 32
        all_vecs = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i: i + batch_size]
            payload = {"model": self.model_name, "input": batch}
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                all_vecs.extend(data["embeddings"])
            print(f"  [OllamaEmb] Embedded {min(i+batch_size, len(texts))}/{len(texts)}")
        return all_vecs

    def embed_query(self, text: str) -> List[float]:
        return self._embed_single(text)

class GeminiLLM:
    """
    簡單封裝 Gemini API，模仿 ChatOpenAI 的 invoke 方法。
    支援 gemini-1.5-pro, gemini-2.0-flash 等。
    """
    def __init__(self, model_name: str, api_key: str, temperature: float = 0, max_tokens: int = 8192):
        self.model_name = model_name
        self.api_key = api_key
        if not self.api_key:
            print("[Warning] Gemini API Key is missing! LLM calls will fail.")
        self.temperature = temperature
        self.max_tokens = max_tokens

    def invoke(self, messages: List, response_mime_type: str = None) -> Any:
        contents = []
        system_instruction = None
        for m in messages:
            if isinstance(m, SystemMessage):
                system_instruction = m.content
            else:
                role = "user" if isinstance(m, HumanMessage) else "model"
                contents.append({"role": role, "parts": [{"text": m.content}]})

        payload = {
            "contents": contents,
            "generationConfig": {"temperature": self.temperature, "maxOutputTokens": self.max_tokens}
        }
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }
        if response_mime_type:
            payload["generationConfig"]["response_mime_type"] = response_mime_type

        # 備援模型清單 (防止主模型故障或限額)
        models_to_try = [self.model_name]
        if "pro" in self.model_name.lower():
            models_to_try += ["gemini-2.5-flash", "gemini-1.5-flash"]
        
        last_error = None
        for model in models_to_try:
            current_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            for attempt in range(3):
                try:
                    # 使用 90 秒作為超時時間，避免大型 pro 模型或 API 擁堵時超時
                    with httpx.Client(timeout=90.0) as client:
                        resp = client.post(current_url, json=payload)
                        
                        # 針對 404 (找不到模型) 立即跳出，嘗試備援模型
                        if resp.status_code == 404:
                            print(f"  [Gemini] 模型 '{model}' 不存在 (404)。嘗試備援模型...")
                            break
                        
                        # 針對 429 或 5xx 伺服器短暫異常，進行指數退避重試
                        if resp.status_code in (429, 500, 503):
                            sleep_time = (2 ** attempt) + 1
                            print(f"  [Gemini] 遇到狀態碼 {resp.status_code}。重試中 ({attempt+1}/3)，將在 {sleep_time} 秒後重試...")
                            _time.sleep(sleep_time)
                            continue
                        
                        # 對於其他非成功狀態碼 (例如 400 格式錯誤, 401 認證錯誤, 403 權限錯誤)，直接拋出異常不重試
                        resp.raise_for_status()
                        
                        data = resp.json()
                        candidate = data['candidates'][0]
                        text = candidate['content']['parts'][0]['text']
                        
                        class Response:
                            def __init__(self, content, usage=None):
                                            self.content = content
                                            self.usage = usage or {}
                        
                        usage = data.get("usageMetadata", {})
                        return Response(text, usage=usage)
                except httpx.HTTPStatusError as e:
                    # 永久性 Client 端錯誤直接拋出，不進行無效重試
                    print(f"  [Gemini] HTTP 錯誤 {e.response.status_code}: {e.response.text}")
                    raise e
                except Exception as e:
                    last_error = e
                    print(f"  [Gemini] 呼叫模型 '{model}' 失敗，錯誤: {e}。進行下一次嘗試...")
                    _time.sleep(1)
        
        raise last_error or Exception("Gemini API call failed")


class OllamaLLM:
    """
    簡單封裝 Ollama API，模仿 ChatOpenAI 的 invoke 方法。
    支援 qwen3.5:27b, gemma4:31b 等。
    """
    def __init__(self, model_name: str, base_url: str = None, temperature: float = 0.0, timeout: float = 1800.0):
        self.model_name = model_name
        self.base_url = (base_url
                         or os.environ.get("OLLAMA_BASE_URL", "http://140.115.54.89:11434")).rstrip("/")
        self.temperature = temperature
        self.timeout = timeout

    def invoke(self, messages: List, response_mime_type: str = None) -> Any:
        url = f"{self.base_url}/api/chat"
        contents = []
        for m in messages:
            if isinstance(m, SystemMessage):
                role = "system"
            elif isinstance(m, HumanMessage):
                role = "user"
            else:
                role = "assistant"
            contents.append({"role": role, "content": m.content})

        payload = {
            "model": self.model_name,
            "messages": contents,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": 8192
            }
        }
        # Note: We do NOT pass format="json" to Ollama because it causes infinite token rejection loops
        # and timeouts with reasoning models (like gemma4:31b) and certain other models (like qwen3.5:27b).
        # Our parsers in rag_nodes.py and missing_form_detector.py are robust enough to parse JSON from raw text.

        last_error = None
        for attempt in range(3):
            try:
                # 這裡設定 300.0 秒以避免連線卡死
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    
                    class Response:
                        def __init__(self, content, usage=None):
                            self.content = content
                            self.usage = usage or {}

                    prompt_tokens = data.get("prompt_eval_count", 0)
                    eval_tokens = data.get("eval_count", 0)
                    usage = {
                        "promptTokenCount": prompt_tokens,
                        "candidatesTokenCount": eval_tokens,
                        "totalTokenCount": prompt_tokens + eval_tokens
                    }
                    return Response(data["message"]["content"], usage=usage)
            except Exception as e:
                last_error = e
                print(f"  [OllamaLLM] 呼叫模型 '{self.model_name}' 失敗 (重試 {attempt+1}/3)，錯誤: {e}")
                _time.sleep(2)
        raise last_error or Exception("Ollama LLM call failed")


