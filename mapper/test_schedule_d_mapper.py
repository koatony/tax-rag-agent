import unittest
from unittest.mock import MagicMock, patch
from mapper.schedule_d_mapper import ScheduleDMapper

class TestScheduleDMapper(unittest.TestCase):

    @patch("mapper.schedule_d_mapper.GeminiLLM")
    def test_map_success_long_term_loss(self, mock_gemini_class):
        """測試成功映射長期資本損失結轉。"""
        mock_response = MagicMock()
        mock_response.content = """
        {
          "items": [
            {
              "target_line": "line_14",
              "value": 990.0,
              "value_type": "float",
              "source_category": "prior_year_facts",
              "source_fact_type": "long_term_capital_loss_carryover",
              "needs_review": false,
              "review_reason": null
            }
          ],
          "unmapped_items": []
        }
        """
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        mock_gemini_class.return_value = mock_instance

        mapper = ScheduleDMapper(tax_year=2025)
        mapper_input = {
            "tax_year": 2025,
            "prior_year_facts": [
                {
                    "fact_type": "long_term_capital_loss_carryover",
                    "value": 990.0,
                    "value_type": "float",
                    "status": "found",
                    "needs_review": False,
                    "review_reason": None
                }
            ],
            "brokerage_facts": [],
            "form_8949_facts": []
        }

        with patch.dict("os.environ", {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "fake_key"}):
            result = mapper.map(mapper_input)

        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertEqual(item["target_line"], "line_14")
        self.assertEqual(item["value"], 990.0)
        self.assertEqual(item["source_category"], "prior_year_facts")
        self.assertEqual(item["source_fact_type"], "long_term_capital_loss_carryover")
        self.assertEqual(item["needs_review"], False)

    @patch("mapper.schedule_d_mapper.GeminiLLM")
    def test_map_unsupported_review_reason_corrected(self, mock_gemini_class):
        """測試不合規的 review_reason 是否會被強制歸為標準預設值。"""
        mock_response = MagicMock()
        mock_response.content = """
        {
          "items": [
            {
              "target_line": "line_6",
              "value": 500.0,
              "value_type": "float",
              "source_category": "prior_year_facts",
              "source_fact_type": "short_term_capital_loss_carryover",
              "needs_review": true,
              "review_reason": "我自行填寫的理由"
            }
          ],
          "unmapped_items": []
        }
        """
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        mock_gemini_class.return_value = mock_instance

        mapper = ScheduleDMapper(tax_year=2025)
        mapper_input = {
            "tax_year": 2025,
            "prior_year_facts": [
                {
                    "fact_type": "short_term_capital_loss_carryover",
                    "value": 500.0,
                    "value_type": "float",
                    "status": "ambiguous",
                    "needs_review": True,
                    "review_reason": "欄位名稱模糊或模型信心不足"
                }
            ]
        }

        with patch.dict("os.environ", {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "fake_key"}):
            result = mapper.map(mapper_input)

        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertEqual(item["target_line"], "line_6")
        self.assertEqual(item["source_fact_type"], "short_term_capital_loss_carryover")
        self.assertEqual(item["needs_review"], True)
        self.assertEqual(item["review_reason"], "欄位名稱模糊或模型信心不足")

    @patch("mapper.schedule_d_mapper.GeminiLLM")
    def test_map_unresolved_loss_carryover(self, mock_gemini_class):
        """測試無區分 ST/LT 的 capital_loss_carryover 被正確放入 unmapped_items。"""
        mock_response = MagicMock()
        mock_response.content = """
        {
          "items": [],
          "unmapped_items": [
            {
              "value": 3000.0,
              "value_type": "float",
              "source_category": "prior_year_facts",
              "source_fact_type": "capital_loss_carryover",
              "needs_review": true,
              "review_reason": "歸屬或 activity scope 不明"
            }
          ]
        }
        """
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        mock_gemini_class.return_value = mock_instance

        mapper = ScheduleDMapper(tax_year=2025)
        mapper_input = {
            "tax_year": 2025,
            "prior_year_facts": [
                {
                    "fact_type": "capital_loss_carryover",
                    "value": 3000.0,
                    "value_type": "float",
                    "status": "unresolved",
                    "needs_review": True,
                    "review_reason": "歸屬或 activity scope 不明"
                }
            ],
            "brokerage_facts": [],
            "form_8949_facts": []
        }

        with patch.dict("os.environ", {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "fake_key"}):
            result = mapper.map(mapper_input)

        self.assertEqual(len(result["items"]), 0)
        self.assertEqual(len(result["unmapped_items"]), 1)
        item = result["unmapped_items"][0]
        self.assertEqual(item["source_fact_type"], "capital_loss_carryover")
        self.assertEqual(item["value"], 3000.0)
        self.assertEqual(item["needs_review"], True)
        self.assertEqual(item["review_reason"], "歸屬或 activity scope 不明")

if __name__ == "__main__":
    unittest.main()
