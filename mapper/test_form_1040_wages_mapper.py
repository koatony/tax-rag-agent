import unittest
from unittest.mock import MagicMock, patch
from mapper.form_1040_wages_mapper import Form1040WagesMapper, aggregate_form_1040_line_1a

class TestForm1040WagesMapper(unittest.TestCase):

    @patch("mapper.form_1040_wages_mapper.GeminiLLM")
    def test_map_success_w2(self, mock_gemini_class):
        """測試成功映射 W-2 Box 1 wages 至 Form 1040 Line 1a。"""
        mock_response = MagicMock()
        mock_response.content = """
        {
          "items": [
            {
              "target_form": "form_1040",
              "target_line": "line_1a",
              "value": 46000.0,
              "value_type": "float",
              "taxpayer_name": "Marcus Rivera",
              "source_category": "w2_facts",
              "source_fact_type": "w2_box_1_wages",
              "source_filename": "sample_1_marcus_w2.pdf",
              "needs_review": false,
              "review_reason": null
            }
          ],
          "unmapped_items": [
            {
              "value": 2000.0,
              "value_type": "float",
              "source_category": "w2_facts",
              "source_fact_type": "w2_box_12a_amount",
              "source_filename": "sample_1_marcus_w2.pdf",
              "needs_review": false,
              "review_reason": null
            }
          ]
        }
        """
        mock_instance = MagicMock()
        mock_instance.invoke.return_value = mock_response
        mock_gemini_class.return_value = mock_instance

        mapper = Form1040WagesMapper(tax_year=2024)
        mapper_input = {
            "tax_year": 2024,
            "w2_documents": [
                {
                    "source_filename": "sample_1_marcus_w2.pdf",
                    "facts": [
                        {
                            "fact_type": "w2_box_1_wages",
                            "value": 46000.0,
                            "value_type": "float",
                            "status": "found",
                            "needs_review": False,
                            "review_reason": None
                        },
                        {
                            "fact_type": "w2_box_12a_amount",
                            "value": 2000.0,
                            "value_type": "float",
                            "status": "found",
                            "needs_review": False,
                            "review_reason": None
                        }
                    ],
                    "document_needs_review": False
                }
            ]
        }

        with patch.dict("os.environ", {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "fake_key"}):
            result = mapper.map(mapper_input)

        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["target_line"], "line_1a")
        self.assertEqual(result["items"][0]["value"], 46000.0)
        self.assertEqual(len(result["unmapped_items"]), 1)
        self.assertEqual(result["unmapped_items"][0]["source_fact_type"], "w2_box_12a_amount")

    def test_aggregate_success(self):
        """測試對多筆 mapped items 進行確定性加總。"""
        mapped_items = [
            {
                "target_form": "form_1040",
                "target_line": "line_1a",
                "value": 50000.0,
                "value_type": "float",
                "taxpayer_name": "Alice",
                "source_category": "w2_facts",
                "source_fact_type": "w2_box_1_wages",
                "source_filename": "alice_w2.pdf",
                "needs_review": False,
                "review_reason": None
            },
            {
                "target_form": "form_1040",
                "target_line": "line_1a",
                "value": 60000.0,
                "value_type": "float",
                "taxpayer_name": "Bob",
                "source_category": "w2_facts",
                "source_fact_type": "w2_box_1_wages",
                "source_filename": "bob_w2.pdf",
                "needs_review": False,
                "review_reason": None
            }
        ]

        result = aggregate_form_1040_line_1a(mapped_items)
        self.assertEqual(result["total_value"], 110000.0)
        self.assertEqual(result["needs_review"], False)
        self.assertEqual(result["calculation_status"], "completed")

    def test_aggregate_with_review_on_duplicate(self):
        """測試同一檔案重複時，會排除該重複檔案並標記 needs_review。"""
        mapped_items = [
            {
                "target_form": "form_1040",
                "target_line": "line_1a",
                "value": 50000.0,
                "value_type": "float",
                "taxpayer_name": "Alice",
                "source_category": "w2_facts",
                "source_fact_type": "w2_box_1_wages",
                "source_filename": "alice_w2.pdf",
                "needs_review": False,
                "review_reason": None
            },
            {
                "target_form": "form_1040",
                "target_line": "line_1a",
                "value": 50000.0,
                "value_type": "float",
                "taxpayer_name": "Alice Duplicate",
                "source_category": "w2_facts",
                "source_fact_type": "w2_box_1_wages",
                "source_filename": "alice_w2.pdf",
                "needs_review": False,
                "review_reason": None
            }
        ]

        result = aggregate_form_1040_line_1a(mapped_items)
        self.assertEqual(result["total_value"], 0.0)
        self.assertEqual(result["needs_review"], True)
        self.assertIn("同一 fact 多筆且無法判斷", result["review_reasons"])
        self.assertEqual(result["calculation_status"], "completed_with_review")

if __name__ == "__main__":
    unittest.main()
