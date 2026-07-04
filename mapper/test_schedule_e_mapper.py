import unittest
from unittest.mock import MagicMock, patch
from mapper.schedule_e_mapper import ScheduleEMapper

class TestScheduleEMapper(unittest.TestCase):

    @patch("mapper.schedule_e_mapper.GeminiLLM")
    def test_map_success_all_clean(self, mock_gemini_class):
        """測試成功映射所有清潔的出租收支 facts 到對應行號。"""
        mock_response = MagicMock()
        mock_response.content = """
        {
          "items": [
            {
              "target_form": "schedule_e",
              "target_line": "line_3",
              "value": 16650.0,
              "value_type": "float",
              "source_category": "rental_facts",
              "source_fact_type": "rental_income",
              "source_filename": "rental_statement.pdf",
              "needs_review": false,
              "review_reason": null
            },
            {
              "target_form": "schedule_e",
              "target_line": "line_9",
              "value": 900.0,
              "value_type": "float",
              "source_category": "rental_facts",
              "source_fact_type": "rental_insurance_expense",
              "source_filename": "rental_statement.pdf",
              "needs_review": false,
              "review_reason": null
            },
            {
              "target_form": "schedule_e",
              "target_line": "line_12",
              "value": 4800.0,
              "value_type": "float",
              "source_category": "rental_facts",
              "source_fact_type": "rental_mortgage_interest_expense",
              "source_filename": "rental_statement.pdf",
              "needs_review": false,
              "review_reason": null
            },
            {
              "target_form": "schedule_e",
              "target_line": "line_13",
              "value": 500.0,
              "value_type": "float",
              "source_category": "rental_facts",
              "source_fact_type": "rental_other_interest_expense",
              "source_filename": "rental_statement.pdf",
              "needs_review": false,
              "review_reason": null
            }
          ]
        }
        """
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        mock_gemini_class.return_value = mock_instance

        mapper = ScheduleEMapper(tax_year=2024)
        mapper_input = {
            "documents": [
                {
                    "source_filename": "rental_statement.pdf",
                    "facts": [
                        {
                            "fact_type": "rental_income",
                            "value": 16650.0,
                            "value_type": "float",
                            "status": "found",
                            "needs_review": False,
                            "review_reason": None
                        },
                        {
                            "fact_type": "rental_insurance_expense",
                            "value": 900.0,
                            "value_type": "float",
                            "status": "found",
                            "needs_review": False,
                            "review_reason": None
                        },
                        {
                            "fact_type": "rental_mortgage_interest_expense",
                            "value": 4800.0,
                            "value_type": "float",
                            "status": "found",
                            "needs_review": False,
                            "review_reason": None
                        },
                        {
                            "fact_type": "rental_other_interest_expense",
                            "value": 500.0,
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

        self.assertEqual(len(result["items"]), 4)
        self.assertEqual(result["items"][0]["target_line"], "line_3")
        self.assertEqual(result["items"][0]["value"], 16650.0)
        self.assertEqual(result["items"][1]["target_line"], "line_9")
        self.assertEqual(result["items"][1]["value"], 900.0)
        self.assertEqual(result["items"][2]["target_line"], "line_12")
        self.assertEqual(result["items"][2]["value"], 4800.0)
        self.assertEqual(result["items"][3]["target_line"], "line_13")
        self.assertEqual(result["items"][3]["value"], 500.0)

    @patch("mapper.schedule_e_mapper.GeminiLLM")
    def test_map_propagates_needs_review(self, mock_gemini_class):
        """測試輸入 facts 的 needs_review 狀態會正確傳播到映射項目。"""
        mock_response = MagicMock()
        mock_response.content = """
        {
          "items": [
            {
              "target_form": "schedule_e",
              "target_line": "line_19",
              "value": 550.0,
              "value_type": "float",
              "source_category": "rental_facts",
              "source_fact_type": "rental_miscellaneous_expense",
              "source_filename": "rental_statement.pdf",
              "needs_review": true,
              "review_reason": "欄位名稱模糊或模型信心不足"
            }
          ]
        }
        """
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        mock_gemini_class.return_value = mock_instance

        mapper = ScheduleEMapper(tax_year=2024)
        mapper_input = {
            "documents": [
                {
                    "source_filename": "rental_statement.pdf",
                    "facts": [
                        {
                            "fact_type": "rental_miscellaneous_expense",
                            "value": 550.0,
                            "value_type": "float",
                            "status": "ambiguous",
                            "needs_review": True,
                            "review_reason": "欄位名稱模糊或模型信心不足"
                        }
                    ]
                }
            ]
        }

        with patch.dict("os.environ", {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "fake_key"}):
            result = mapper.map(mapper_input)

        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertEqual(item["target_line"], "line_19")
        self.assertEqual(item["value"], 550.0)
        self.assertEqual(item["needs_review"], True)
        self.assertEqual(item["review_reason"], "欄位名稱模糊或模型信心不足")

    @patch("mapper.schedule_e_mapper.GeminiLLM")
    def test_map_filters_missing_depreciation(self, mock_gemini_class):
        """測試缺失的折舊 (value為 missing) 不會傳給 LLM 或產生映射項目。"""
        mock_response = MagicMock()
        mock_response.content = """
        {
          "items": []
        }
        """
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        mock_gemini_class.return_value = mock_instance

        mapper = ScheduleEMapper(tax_year=2024)
        mapper_input = {
            "documents": [
                {
                    "source_filename": "rental_statement.pdf",
                    "facts": [
                        {
                            "fact_type": "rental_depreciation_expense",
                            "value": "missing",
                            "value_type": "string",
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

        # 由於 "missing" 值在 input 整理時就被過濾掉了，對應 clean_facts 將是空的，LLM 也不應輸出任何映射項目
        self.assertEqual(len(result["items"]), 0)

if __name__ == "__main__":
    unittest.main()
