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

from processors.parsers.form_1040_income import Form1040IncomeLLMParser
from form1040.orchestrator import Form1040Orchestrator
from form1040.models.income_aggregator_model import (
    ScheduleBResultV1,
    ScheduleDResultV1,
    Schedule1ResultV1,
)


def _extract_text_from_docx(docx_path: str) -> str:
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


class TestLLMForm1040E2E(unittest.TestCase):
    """
    Form 1040 全流程端到端整合測試 (包含真實 LLM 數據提取 -> Income Aggregator -> AGI)
    """

    @unittest.skipUnless(os.environ.get("GEMINI_API_KEY"), "需要 GEMINI_API_KEY 執行真實 LLM 測試")
    def test_full_form1040_e2e_with_real_llm_0622(self):
        doc_context = load_0622_raw_docx_documents()
        self.assertIn("Marcus Rivera", doc_context)

        model_name = os.environ.get("LLM_MODEL_NAME", "gemini-2.5-flash")
        print(f"\n🤖 [Form 1040 E2E LLM Test] 正在呼叫 Gemini API ({model_name})...")

        parser = Form1040IncomeLLMParser(model_name=model_name)
        extracted_data, prompt_log, raw_output = parser.parse(doc_context)

        sb_result = ScheduleBResultV1(
            form_1040_line_2a=Decimal("0.00"),
            line_4_surface_value=Decimal("150.00"),
            total_qualified_dividends=Decimal("0.00"),
            line_6_total_ordinary_dividends=Decimal("405.00"),
            status="COMPLETE",
        )

        sd_result = ScheduleDResultV1(
            line_7_capital_gain_or_loss=Decimal("-990.00"),
            status="COMPLETE",
        )

        s1_result = Schedule1ResultV1(
            line_10_additional_income=Decimal("0.00"),
            line_26_adjustments_to_income=Decimal("7000.00"),
            status="COMPLETE",
        )

        assembly_result = Form1040Orchestrator.assemble_0622_case(
            raw_llm_direct_income=extracted_data,
            schedule_b_result=sb_result,
            schedule_d_result=sd_result,
            schedule_1_result=s1_result,
        )

        self.assertEqual(assembly_result["status"], "COMPLETE")
        self.assertEqual(assembly_result["income_section"]["line_9"], "99565.00")
        self.assertEqual(assembly_result["agi_section"]["line_11_adjusted_gross_income"], "92565.00")
        print(f"✅ Form 1040 E2E LLM 測試成功！Line 9={assembly_result['income_section']['line_9']}, Line 11={assembly_result['agi_section']['line_11_adjusted_gross_income']}")


if __name__ == "__main__":
    unittest.main()
