import os
import json
import time
import sys
import google.generativeai as genai
from dotenv import load_dotenv
from pathlib import Path

# Load Environment
root_dir = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(root_dir))
load_dotenv(dotenv_path=root_dir / ".env")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
JUDGE_MODEL_NAME = os.environ.get("GEMINI_JUDGE_MODEL", "gemini-flash-latest")

M1_PROMPT = """You are an expert US tax law evaluator. Compare the System Answer against the Ground Truth.
Output ONLY a JSON object: {{"score": <int>, "reasoning": "<str>"}}, where score is an integer from 1 to 5."""

def call_gemini(prompt):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(JUDGE_MODEL_NAME)
    start_t = time.time()
    try:
        response = model.generate_content(prompt)
        print(f"    - Gemini call took {time.time() - start_t:.2f}s")
        return response.text
    except Exception as e:
        print(f"    ! Gemini Error: {e}")
        return str(e)

if __name__ == "__main__":
    p = M1_PROMPT.format(question="Test", ground_truth="Test", system_answer="Test")
    print("[DEBUG] Calling Gemini...")
    for i in range(3):
        call_gemini(p)
