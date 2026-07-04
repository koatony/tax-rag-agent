import unittest
from unittest.mock import MagicMock, patch
from adapter.prior_year_return_adapter import PriorYearReturnAdapter

class TestPriorYearReturnAdapter(unittest.TestCase):

    def test_extract_fallback_empty_content(self):
        """測試空白內容是否能安全返回 Failed 狀態。"""
        result = PriorYearReturnAdapter.extract(
            filename="Test_Return.pdf",
            content=""
        )
        self.assertEqual(result["source_filename"], "Test_Return.pdf")
        self.assertEqual(result["extraction_status"], "failed")
        self.assertTrue(result["document_needs_review"])
        self.assertIn("檔案內容為空", result["document_review_reasons"][0])

    @patch("adapter.prior_year_return_adapter.GeminiLLM")
    def test_extract_success_all_clean(self, mock_gemini_class):
        """測試無任何 review 項目時的成功提取。"""
        mock_response = MagicMock()
        mock_response.content = """
        {
          "detected_tax_year": 2023,
          "extraction_status": "completed",
          "facts": [
            {
              "fact_type": "capital_loss_carryover",
              "value": 990.0,
              "value_type": "float",
              "status": "found",
              "needs_review": false,
              "review_reason": null
            },
            {
              "fact_type": "filing_status",
              "value": "Married Filing Jointly",
              "value_type": "string",
              "status": "found",
              "needs_review": false,
              "review_reason": null
            }
          ],
          "document_needs_review": false,
          "document_review_reasons": []
        }
        """
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        mock_gemini_class.return_value = mock_instance

        with patch.dict("os.environ", {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "fake_key"}):
            result = PriorYearReturnAdapter.extract(
                filename="Rivera_2023.pdf",
                content="Dummy OCR text"
            )

        # 驗證外部帶入的檔名與事實項目
        self.assertEqual(result["source_filename"], "Rivera_2023.pdf")
        self.assertEqual(result["detected_tax_year"], 2023)
        self.assertEqual(result["extraction_status"], "completed")
        self.assertEqual(result["document_needs_review"], False)
        self.assertEqual(len(result["facts"]), 2)
        
        self.assertEqual(result["facts"][0]["fact_type"], "capital_loss_carryover")
        self.assertEqual(result["facts"][0]["value"], 990.0)
        self.assertEqual(result["facts"][0]["needs_review"], False)

    @patch("adapter.prior_year_return_adapter.GeminiLLM")
    def test_extract_aggregates_item_review(self, mock_gemini_class):
        """測試內部 item 只要有 needs_review=True，外層與狀態會自動被設為 review 狀態。"""
        mock_response = MagicMock()
        mock_response.content = """
        {
          "detected_tax_year": 2023,
          "extraction_status": "completed",
          "facts": [
            {
              "fact_type": "adjusted_gross_income",
              "value": "$145,000",
              "value_type": "float",
              "status": "ambiguous",
              "needs_review": true,
              "review_reason": "只能靠上下文猜測"
            }
          ],
          "document_needs_review": false,
          "document_review_reasons": []
        }
        """
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        mock_gemini_class.return_value = mock_instance

        with patch.dict("os.environ", {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "fake_key"}):
            result = PriorYearReturnAdapter.extract(
                filename="Rivera_2023.pdf",
                content="Dummy text"
            )

        # 檢驗值是否被正確清洗成 float
        self.assertEqual(result["facts"][0]["value"], 145000.0)
        self.assertEqual(result["facts"][0]["needs_review"], True)
        self.assertEqual(result["facts"][0]["review_reason"], "只能靠上下文猜測")

        # 檢驗外層 document_needs_review 是否被強制設為 True
        self.assertEqual(result["document_needs_review"], True)
        # 檢驗狀態是否被自動改為 completed_with_review
        self.assertEqual(result["extraction_status"], "completed_with_review")

    @patch("adapter.prior_year_return_adapter.GeminiLLM")
    def test_extract_invalid_review_reason_corrected(self, mock_gemini_class):
        """測試非預定義之 review_reason 是否會被強制歸為預設值。"""
        mock_response = MagicMock()
        mock_response.content = """
        {
          "detected_tax_year": 2023,
          "extraction_status": "completed",
          "facts": [
            {
              "fact_type": "standard_deduction_amount",
              "value": 13850.0,
              "value_type": "float",
              "status": "ambiguous",
              "needs_review": true,
              "review_reason": "我隨便編寫的原因"
            }
          ],
          "document_needs_review": true,
          "document_review_reasons": []
        }
        """
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        mock_gemini_class.return_value = mock_instance

        with patch.dict("os.environ", {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "fake_key"}):
            result = PriorYearReturnAdapter.extract(
                filename="Rivera_2023.pdf",
                content="Dummy text"
            )

        # 檢驗不合法之原因是否會被修正為預設
        self.assertEqual(result["facts"][0]["review_reason"], "欄位名稱模糊或模型信心不足")

    @patch("adapter.prior_year_return_adapter.GeminiLLM")
    def test_extract_non_registry_fact_type_mapped_to_unknown(self, mock_gemini_class):
        """測試非註冊清單之 fact_type 是否被歸為 unknown_prior_year_fact。"""
        mock_response = MagicMock()
        mock_response.content = """
        {
          "detected_tax_year": 2023,
          "extraction_status": "completed",
          "facts": [
            {
              "fact_type": "not_existing_key",
              "value": "some value",
              "value_type": "string",
              "status": "found",
              "needs_review": false,
              "review_reason": null
            }
          ],
          "document_needs_review": false,
          "document_review_reasons": []
        }
        """
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        mock_gemini_class.return_value = mock_instance

        with patch.dict("os.environ", {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "fake_key"}):
            result = PriorYearReturnAdapter.extract(
                filename="Rivera_2023.pdf",
                content="Dummy text"
            )

        self.assertEqual(result["facts"][0]["fact_type"], "unknown_prior_year_fact")

if __name__ == "__main__":
    unittest.main()
