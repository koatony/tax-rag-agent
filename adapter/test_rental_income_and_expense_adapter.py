import unittest
from unittest.mock import MagicMock, patch
from adapter.rental_income_and_expense_adapter import RentalIncomeAndExpenseAdapter

class TestRentalIncomeAndExpenseAdapter(unittest.TestCase):

    def test_extract_fallback_empty_content(self):
        """測試空白內容是否能安全返回 Needs Review 狀態。"""
        result = RentalIncomeAndExpenseAdapter.extract(
            filename="Empty_Rental.pdf",
            content=""
        )
        self.assertEqual(result["source_filename"], "Empty_Rental.pdf")
        self.assertTrue(result["document_needs_review"])
        self.assertEqual(result["facts"], [])

    @patch("adapter.rental_income_and_expense_adapter.GeminiLLM")
    def test_extract_success_all_clean(self, mock_gemini_class):
        """測試無任何 review 項目時的成功提取。"""
        mock_response = MagicMock()
        mock_response.content = """
        {
          "facts": [
            {
              "fact_type": "rental_income",
              "value": 15000.0,
              "value_type": "float",
              "status": "found",
              "needs_review": false,
              "review_reason": null
            },
            {
              "fact_type": "rental_insurance_expense",
              "value": "$1,200",
              "value_type": "float",
              "status": "found",
              "needs_review": false,
              "review_reason": null
            }
          ]
        }
        """
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        mock_gemini_class.return_value = mock_instance

        with patch.dict("os.environ", {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "fake_key"}):
            result = RentalIncomeAndExpenseAdapter.extract(
                filename="rental_report.pdf",
                content="Dummy text"
            )

        self.assertEqual(result["source_filename"], "rental_report.pdf")
        self.assertEqual(result["document_needs_review"], False)
        self.assertEqual(len(result["facts"]), 2)
        
        self.assertEqual(result["facts"][0]["fact_type"], "rental_income")
        self.assertEqual(result["facts"][0]["value"], 15000.0)
        self.assertEqual(result["facts"][0]["value_type"], "float")

        self.assertEqual(result["facts"][1]["fact_type"], "rental_insurance_expense")
        self.assertEqual(result["facts"][1]["value"], 12000.0 if result["facts"][1]["value"] == 12000 else 1200.0) # wait, $1,200 is 1200.0
        self.assertEqual(result["facts"][1]["value"], 1200.0)
        self.assertEqual(result["facts"][1]["value_type"], "float")

    @patch("adapter.rental_income_and_expense_adapter.GeminiLLM")
    def test_extract_depreciation_not_in_document(self, mock_gemini_class):
        """測試折舊費用未出現在文件時，不提取該 fact。"""
        mock_response = MagicMock()
        mock_response.content = """
        {
          "facts": []
        }
        """
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        mock_gemini_class.return_value = mock_instance

        with patch.dict("os.environ", {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "fake_key"}):
            result = RentalIncomeAndExpenseAdapter.extract(
                filename="depreciation_missing.pdf",
                content="Dummy text with no depreciation mentioned"
            )

        self.assertEqual(result["facts"], [])

    @patch("adapter.rental_income_and_expense_adapter.GeminiLLM")
    def test_extract_mortgage_interest_clean_and_unknown_catchall(self, mock_gemini_class):
        """測試房貸利息單純提取金額，且不知名出租項目歸入 unknown_rental_fact。"""
        mock_response = MagicMock()
        mock_response.content = """
        {
          "facts": [
            {
              "fact_type": "rental_mortgage_interest_expense",
              "value": 5400.0,
              "value_type": "float",
              "status": "found",
              "needs_review": false,
              "review_reason": null
            },
            {
              "fact_type": "unknown_rental_fact",
              "value": "Cleaning expense: $300",
              "value_type": "string",
              "status": "found",
              "needs_review": false,
              "review_reason": null
            }
          ]
        }
        """
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        mock_gemini_class.return_value = mock_instance

        with patch.dict("os.environ", {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "fake_key"}):
            result = RentalIncomeAndExpenseAdapter.extract(
                filename="interest_statement.pdf",
                content="Dummy text"
            )

        self.assertEqual(result["facts"][0]["fact_type"], "rental_mortgage_interest_expense")
        self.assertEqual(result["facts"][0]["value"], 5400.0)
        self.assertEqual(result["facts"][0]["value_type"], "float")

        self.assertEqual(result["facts"][1]["fact_type"], "unknown_rental_fact")
        self.assertEqual(result["facts"][1]["value"], "Cleaning expense: $300")
        self.assertEqual(result["facts"][1]["value_type"], "string")

    @patch("adapter.rental_income_and_expense_adapter.GeminiLLM")
    def test_extract_invalid_review_reason_corrected(self, mock_gemini_class):
        """測試非預定義之 review_reason 是否會被強制歸為預設值。"""
        mock_response = MagicMock()
        mock_response.content = """
        {
          "facts": [
            {
              "fact_type": "rental_income",
              "value": 12000.0,
              "value_type": "float",
              "status": "ambiguous",
              "needs_review": true,
              "review_reason": "我隨便編寫的原因"
            }
          ]
        }
        """
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        mock_gemini_class.return_value = mock_instance

        with patch.dict("os.environ", {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "fake_key"}):
            result = RentalIncomeAndExpenseAdapter.extract(
                filename="rental.pdf",
                content="Dummy text"
            )

        self.assertEqual(result["facts"][0]["review_reason"], "欄位名稱模糊或模型信心不足")
        self.assertEqual(result["document_needs_review"], True)

    @patch("adapter.rental_income_and_expense_adapter.GeminiLLM")
    def test_extract_non_registry_fact_type_mapped_to_unknown(self, mock_gemini_class):
        """測試非註冊清單之 fact_type 是否被歸為 unknown_rental_fact。"""
        mock_response = MagicMock()
        mock_response.content = """
        {
          "facts": [
            {
              "fact_type": "some_invalid_key",
              "value": "extra info",
              "value_type": "string",
              "status": "found",
              "needs_review": false,
              "review_reason": null
            }
          ]
        }
        """
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        mock_gemini_class.return_value = mock_instance

        with patch.dict("os.environ", {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "fake_key"}):
            result = RentalIncomeAndExpenseAdapter.extract(
                filename="rental.pdf",
                content="Dummy text"
            )

        self.assertEqual(result["facts"][0]["fact_type"], "unknown_rental_fact")

if __name__ == "__main__":
    unittest.main()
