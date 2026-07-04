"""
chapter_indexer.py
Step 1: Ask Gemini to extract the chapter structure from the uploaded PDF.
"""
import json
from modules.llm_client import LLMClient
from prompts.prompts import CHAPTER_INDEX_PROMPT


class ChapterIndexer:
    def __init__(self, client: LLMClient):
        self.client = client

    def extract_chapters(self, pdf_file) -> list[dict]:
        """
        Returns a list of chapter dicts:
        [{ chapter_id, title, topic_summary, target_taxpayer }, ...]
        """
        print("[ChapterIndexer] Extracting chapter index from PDF...")
        result = self.client.generate_json(CHAPTER_INDEX_PROMPT, pdf_file)

        if not isinstance(result, list):
            raise ValueError(f"Expected list of chapters, got: {type(result)}")

        print(f"[ChapterIndexer] Found {len(result)} chapters.")
        return result
