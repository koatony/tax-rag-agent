import os
import sys
import zipfile
import unittest
import xml.etree.ElementTree as ET
from decimal import Decimal
from dotenv import load_dotenv

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from form1040.parsers.form_1040_income import Form1040IncomeLLMParser
from form1040.processors.income_aggregator_processor import IncomeAggregatorProcessor
from form1040.models.income_aggregator_model import (
    IncomeAggregatorInputV1,
    ScheduleBResultV1,
    ScheduleDResultV1,
    Schedule1ResultV1,
)


def _extract_text_from_docx(docx_path: str) -> str:
    """從 .docx 檔案中提取純文字"""
    try:
        with zipfile.ZipFile(docx_path) as z:
            xml_content = z.read("word/document.xml")
            root = ET.fromstring(xml_content)
            namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            text_elements = root.findall(".//w:t", namespaces)
            return " ".join([el.text for el in text_elements if el.text])
    except Exception:
        return ""


def load_0622_raw_docx_documents() -> str:
    """讀取 Sample Data Pack v2 0622 的真實 Word (.docx) 憑證文字"""
    src_dir = os.path.join(PROJECT_ROOT, "docs", "Sample Data Pack v2 0622", "src_data")
    docx_files = [
        "Sample 01 - W-2 Marcus.docx",
        "Sample 02 - W-2 Elena.docx",
        "Sample 04 - 1099-DIV & 1099-INT & IRA & Charity.docx",
    ]
    combined_texts = []
    for f in docx_files:
        path = os.path.join(src_dir, f)
        if os.path.exists(path):
            text = _extract_text_from_docx(path)
            combined_texts.append(f"--- Document: {f} ---\n{text}\n")
        else:
            combined_texts.append(f"--- Document: {f} (File Not Found) ---\n")
    return "\n".join(combined_texts)


class TestLLMIncomeAggregator(unittest.TestCase):
    """
    專門測試 IncomeAggregatorProcessor 搭配真實 LLM (Gemini API) 的數據提取與 Lines 1–9 彙整
    """

    @unittest.skipUnless(os.environ.get("GEMINI_API_KEY"), "需要 GEMINI_API_KEY 執行真實 LLM 測試")
    def test_income_aggregator_with_real_llm_0622(self):
        doc_context = load_0622_raw_docx_documents()
        self.assertIn("Marcus Rivera", doc_context)
        self.assertIn("Elena Rivera", doc_context)

        model_name = os.environ.get("LLM_MODEL_NAME", "gemini-2.5-flash")
        print(f"\n🤖 [IncomeAggregator LLM Test] 正在呼叫 Gemini API ({model_name})...")

        parser = Form1040IncomeLLMParser(model_name=model_name)
        extracted_data, prompt_log, raw_output = parser.parse(doc_context)

        print("=== IncomeAggregator LLM Extracted Data ===")
        print(extracted_data)

        # 模擬上游 Schedule 試算結果
        sb_result = ScheduleBResultV1(
            form_1040_line_2a=Decimal("0.00"),
            line_4_surface_value=Decimal("150.00"),            # Line 2b Taxable Interest
            total_qualified_dividends=Decimal("0.00"),
            line_6_total_ordinary_dividends=Decimal("405.00"), # Line 3b Ordinary Dividends
            status="COMPLETE",
        )

        sd_result = ScheduleDResultV1(
            line_7_capital_gain_or_loss=Decimal("0.00"),     # Line 7a Capital Loss
            status="COMPLETE",
        )

        s1_result = Schedule1ResultV1(
            line_10_additional_income=Decimal("0.00"),           # Line 8 Additional Income
            line_26_adjustments_to_income=Decimal("7000.00"),     # Line 10 Adjustments
            status="COMPLETE",
        )

        inp = IncomeAggregatorInputV1(
            tax_year=2025,
            filing_status="MFJ",
            direct_income_input=extracted_data,
            schedule_b_result=sb_result,
            schedule_d_result=sd_result,
            schedule_1_result=s1_result,
        )
        result = IncomeAggregatorProcessor.process(inp)

        self.assertEqual(result.status, "COMPLETE")
        self.assertTrue(result.can_continue)
        self.assertEqual(len(result.blocking_errors), 0)

        # 驗證 Lines 1–9
        self.assertEqual(result.line_1a, Decimal("100000.00"))
        self.assertEqual(result.line_1z, Decimal("100000.00"))
        self.assertEqual(result.line_2b, Decimal("150.00"))
        self.assertEqual(result.line_3b, Decimal("405.00"))
        self.assertEqual(result.line_7a, Decimal("0.00"))
        self.assertEqual(result.line_8, Decimal("0.00"))
        self.assertEqual(result.line_9, Decimal("100555.00"))
        print(f"✅ IncomeAggregator LLM 測試成功！Line 9 Total Income = {result.line_9}")


if __name__ == "__main__":
    unittest.main()
