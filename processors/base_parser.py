import os
import re
import json
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage
from llm_wrappers import GeminiLLM, OllamaLLM

# 載入環境變數
load_dotenv()

class BaseLLMParser(ABC):
    """
    通用 LLM 數據提取基底類別。
    封裝了 Prompt 生成、LLM 初始化、回傳字串清理與 JSON 修復等共用工作流。
    """
    def __init__(self, model_name: str = None):
        # 預設採用 gemini-2.5-pro，如果傳入 None
        self.model_name = model_name or "gemini-2.5-pro"
        self.llm_provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
        self.api_key = os.environ.get("GEMINI_API_KEY")
        
        # 判斷是否為 Ollama
        if "gemini" in self.model_name.lower():
            self.is_ollama = False
        elif ":" in self.model_name:
            self.is_ollama = True
        else:
            self.is_ollama = (self.llm_provider == "ollama")

    @abstractmethod
    def get_schema_path(self) -> str:
        """子類別必須實作：回傳表單 Schema 設定檔 (json) 的絕對路徑。"""
        pass

    @abstractmethod
    def get_form_name(self) -> str:
        """子類別必須實作：回傳表單的展示名稱，如 'Schedule A (Form 1040)'。"""
        pass

    @abstractmethod
    def get_custom_rules(self) -> List[str]:
        """子類別必須實作：回傳該表單特有的 LLM 數據提取與防呆規則說明 (Option A)。"""
        pass

    @abstractmethod
    def get_example_json(self) -> Dict[str, Any]:
        """子類別必須實作：回傳符合該表單 Schema 的標準輸出 JSON 範例。"""
        pass

    def load_schema(self) -> Dict[str, Any]:
        """載入子類別所指定的 Schema。"""
        path = self.get_schema_path()
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def generate_extraction_prompt(self, schema: Dict[str, Any]) -> str:
        """
        根據通用範本，並結合子類別提供的 custom rules 與 example json，
        動態生成系統提示詞 (System Prompt)。
        """
        # 1. 整理 Input 欄位定義
        inputs_def = []
        for field in schema.get("inputs", []):
            inputs_def.append(f'- `{field["id"]}` ({field["type"]}): {field["description"]}')
        inputs_str = "\n".join(inputs_def)

        # 2. 格式化自訂規則
        custom_rules_list = self.get_custom_rules()
        custom_rules_str = ""
        if custom_rules_list:
            custom_rules_str = "\n".join(
                f"{idx + 4}. {rule}" for idx, rule in enumerate(custom_rules_list)
            )
            # 加個換行以利美觀
            custom_rules_str = "\n" + custom_rules_str

        # 3. 格式化範例 JSON
        example_json_str = json.dumps(self.get_example_json(), indent=2, ensure_ascii=False)

        # 4. 組裝最終系統提示詞
        prompt = f"""你是一位專業的美國稅務申報與數據提取專家。
你的任務是從申報人基本資料以及上傳的文件內容中，精準提取出國稅局 {self.get_form_name()} 中所有「直接輸入型 (Input)」的欄位值。

【提取規範】
1. 只需提取以下列出的「直接輸入 (Input)」欄位。不要包含任何「公式計算 (Formula)」欄位。
2. 對於數值欄位，若沒有相關資訊，則填寫 0.00；對於布林值，若無資訊則填寫 null 或 false；對於陣列欄位，若無資訊則填寫 []。
3. 數值必須是純數值，不能包含貨幣符號 ($) 或分節逗號 (,)。{custom_rules_str}

【預期提取的欄位列表】
{inputs_str}

【輸出格式】
你必須精確返回一個符合上述欄位的 JSON 對象，例如：
{example_json_str}
直接返回乾淨的 JSON 字串，不要使用 markdown 區塊，也不要包含 any 說明文字。
"""
        return prompt

    def parse(self, document_context: str) -> Tuple[Dict[str, Any], str, str]:
        """
        呼叫 LLM 執行數據提取與結構化。
        回傳 Tuple: (解析後的 dict, 完整的 Prompt 日誌, LLM 的原始輸出字串)
        """
        schema = self.load_schema()
        system_instruction = self.generate_extraction_prompt(schema)
        
        # 初始化 LLM 實例
        if self.is_ollama:
            llm = OllamaLLM(model_name=self.model_name, temperature=0.0, timeout=600.0)
        else:
            if not self.api_key:
                raise ValueError("環境變數 GEMINI_API_KEY 未設定")
            # 針對思考模型（如 gemini-2.5-pro），調大 max_tokens 以確保 JSON 完整輸出
            is_thinking_model = "pro" in self.model_name.lower()
            max_tokens = 65536 if is_thinking_model else 8192
            llm = GeminiLLM(model_name=self.model_name, api_key=self.api_key, temperature=0.0, max_tokens=max_tokens)
            
        messages = [
            SystemMessage(content=system_instruction),
            HumanMessage(content=f"以下是申報人與上傳文件的相關內容，請提取 {self.get_form_name()} 的 Input 欄位：\n\n{document_context}")
        ]
        
        full_prompt_log = f"=== SYSTEM INSTRUCTION ===\n{system_instruction}\n\n=== USER PROMPT ===\n以下是申報人與上傳文件的相關內容，請提取 {self.get_form_name()} 的 Input 欄位：\n\n{document_context}"
        
        if self.is_ollama:
            resp = llm.invoke(messages)
        else:
            resp = llm.invoke(messages, response_mime_type="application/json")
            
        raw_output = resp.content.strip()
        
        # 移除 LLM 回應中的 think 標籤內容 (針對 DeepSeek 等思考模型)
        clean_output = re.sub(r"<think>.*?</think>", "", raw_output, flags=re.DOTALL).strip()
        
        # 提取 JSON 子字串
        match = re.search(r"\{.*\}", clean_output, re.DOTALL)
        if match:
            clean_output = match.group(0)
            
        try:
            from json_repair import repair_json
            repaired_output = repair_json(clean_output)
            extracted_data = json.loads(repaired_output)
            return extracted_data, full_prompt_log, raw_output
        except Exception as e:
            raise ValueError(f"JSON 解析與修復失敗: {e}\nLLM 原始回應: {raw_output}")
