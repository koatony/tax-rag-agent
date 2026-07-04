import unittest
from unittest.mock import MagicMock, patch
from mapper.schedule_a_deduction_mapper import ScheduleADeductionMapper

class TestScheduleADeductionMapper(unittest.TestCase):

    @patch("mapper.schedule_a_deduction_mapper.GeminiLLM")
    def test_map_success_all_clean(self, mock_gemini_class):
        """測試成功映射所有合法的列舉扣除額 facts 到對應行號。"""
        mock_response = MagicMock()
        mock_response.content = """
        {
          "items": [
            {
              "target_form": "schedule_a",
              "target_line": "line_11",
              "value": 5400.0,
              "value_type": "float",
              "source_category": "itemized_deduction_facts",
              "source_fact_type": "charitable_cash_contribution",
              "source_filename": "church_donation_receipt.pdf",
              "needs_review": false,
              "review_reason": null
            },
            {
              "target_form": "schedule_a",
              "target_line": "line_8a",
              "value": 9800.0,
              "value_type": "float",
              "source_category": "itemized_deduction_facts",
              "source_fact_type": "home_mortgage_interest_reported_on_form_1098",
              "source_filename": "mortgage_1098.pdf",
              "needs_review": false,
              "review_reason": null
            },
            {
              "target_form": "schedule_a",
              "target_line": "line_5b",
              "value": 2600.0,
              "value_type": "float",
              "source_category": "itemized_deduction_facts",
              "source_fact_type": "personal_real_estate_tax",
              "source_filename": "tax_bill.pdf",
              "needs_review": false,
              "review_reason": null
            }
          ],
          "unmapped_items": [],
          "needs_review": false
        }
        """
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        mock_gemini_class.return_value = mock_instance

        mapper = ScheduleADeductionMapper(tax_year=2024)
        mapper_input = {
            "documents": [
                {
                    "source_filename": "church_donation_receipt.pdf",
                    "facts": [
                        {
                            "fact_type": "charitable_cash_contribution",
                            "value": 5400.0,
                            "value_type": "float",
                            "status": "found",
                            "needs_review": False,
                            "review_reason": None
                        }
                    ]
                },
                {
                    "source_filename": "mortgage_1098.pdf",
                    "facts": [
                        {
                            "fact_type": "home_mortgage_interest_reported_on_form_1098",
                            "value": 9800.0,
                            "value_type": "float",
                            "status": "found",
                            "needs_review": False,
                            "review_reason": None
                        }
                    ]
                },
                {
                    "source_filename": "tax_bill.pdf",
                    "facts": [
                        {
                            "fact_type": "personal_real_estate_tax",
                            "value": 2600.0,
                            "value_type": "float",
                            "status": "found",
                            "needs_review": False,
                            "review_reason": None
                        }
                    ]
                }
            ]
        }

        with patch.dict("os.environ", {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "fake_key"}):
            result = mapper.map(mapper_input)

        self.assertEqual(len(result["items"]), 3)
        self.assertEqual(result["items"][0]["target_line"], "line_11")
        self.assertEqual(result["items"][0]["value"], 5400.0)
        self.assertEqual(result["items"][1]["target_line"], "line_8a")
        self.assertEqual(result["items"][1]["value"], 9800.0)
        self.assertEqual(result["items"][2]["target_line"], "line_5b")
        self.assertEqual(result["items"][2]["value"], 2600.0)

    @patch("mapper.schedule_a_deduction_mapper.GeminiLLM")
    def test_map_political_contribution(self, mock_gemini_class):
        """測試政治捐款被正確置入 unmapped_items 並設置對應 review_reason。"""
        mock_response = MagicMock()
        mock_response.content = """
        {
          "items": [],
          "unmapped_items": [
            {
              "value": 250.0,
              "value_type": "float",
              "source_category": "itemized_deduction_facts",
              "source_fact_type": "political_contribution",
              "source_filename": "political_contribution_receipt.pdf",
              "needs_review": false,
              "review_reason": "political_contribution_non_deductible"
            }
          ],
          "needs_review": false
        }
        """
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        mock_gemini_class.return_value = mock_instance

        mapper = ScheduleADeductionMapper(tax_year=2024)
        mapper_input = {
            "documents": [
                {
                    "source_filename": "political_contribution_receipt.pdf",
                    "facts": [
                        {
                            "fact_type": "political_contribution",
                            "value": 250.0,
                            "value_type": "float",
                            "status": "found",
                            "needs_review": False,
                            "review_reason": None
                        }
                    ]
                }
            ]
        }

        with patch.dict("os.environ", {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "fake_key"}):
            result = mapper.map(mapper_input)

        self.assertEqual(len(result["items"]), 0)
        self.assertEqual(len(result["unmapped_items"]), 1)
        unmapped = result["unmapped_items"][0]
        self.assertEqual(unmapped["value"], 250.0)
        self.assertEqual(unmapped["needs_review"], False)
        self.assertEqual(unmapped["review_reason"], "political_contribution_non_deductible")

if __name__ == "__main__":
    unittest.main()
