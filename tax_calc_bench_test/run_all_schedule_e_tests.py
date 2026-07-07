import os
import sys
import unittest
from decimal import Decimal

# Add parent directory to sys.path to load project modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from schedule_e_processor import calculate_schedule_e_dynamic

class TestScheduleEProcessor(unittest.TestCase):
    def setUp(self):
        # Setup base inputs matching the official Marcus & Elena Rivera 2025 case exactly
        self.base_inputs = {
            "taxpayer_name": "Marcus Rivera",
            "taxpayer_ssn": "555-12-3456",
            "tax_year": 2025,
            "filing_status": "MFJ",
            "accounting_method": "CASH",
            "form_1099_compliance": {
                "requirement_status": "REQUIRED",
                "filed_or_will_file_required_forms": True,
                "source_result_id": "res_1099_01"
            },
            "special_case_flags": {},
            "properties": [
                {
                    "property_id": "prop_river_oak",
                    "physical_address": {
                        "street": "5200 Green Valley Dr., Unit 200",
                        "city": "Sacramento",
                        "state": "CA",
                        "zip_code": "95841",
                        "country": "US"
                    },
                    "property_type": "SINGLE_FAMILY_RESIDENCE",
                    "reporting_route_status": "SCHEDULE_E_CONFIRMED",
                    "fair_rental_days": 365,
                    "personal_use_days": 0,
                    "qjv_status": False,
                    "ownership_allocation_status": "TAXPAYER_SHARE_CONFIRMED",
                    "rental_income_items": [
                        {
                            "item_id": "inc_rent",
                            "gross_amount_received": 16200.0,
                            "refunded_or_returned_amount": 0.0,
                            "income_character_status": "REPORTABLE_SIMPLE_RENTAL_INCOME",
                            "received_in_tax_year": True
                        },
                        {
                            "item_id": "inc_laundry",
                            "gross_amount_received": 150.0,
                            "refunded_or_returned_amount": 0.0,
                            "income_character_status": "REPORTABLE_SIMPLE_RENTAL_INCOME",
                            "received_in_tax_year": True
                        },
                        {
                            "item_id": "inc_pet",
                            "gross_amount_received": 300.0,
                            "refunded_or_returned_amount": 0.0,
                            "income_character_status": "REPORTABLE_SIMPLE_RENTAL_INCOME",
                            "received_in_tax_year": True
                        }
                    ],
                    "rental_expense_items": [
                        {
                            "item_id": "exp_insurance",
                            "gross_amount": 900.0,
                            "reimbursement_amount": 0.0,
                            "nonrental_allocated_amount": 0.0,
                            "expense_category": "INSURANCE",
                            "deductibility_status": "DEDUCTIBLE_CURRENT",
                            "allocation_status": "PROPERTY_AND_TAXPAYER_SHARE_CONFIRMED",
                            "paid_or_incurred_in_tax_year": True
                        },
                        {
                            "item_id": "exp_interest",
                            "gross_amount": 4800.0,
                            "reimbursement_amount": 0.0,
                            "nonrental_allocated_amount": 0.0,
                            "expense_category": "MORTGAGE_INTEREST_FINANCIAL_INSTITUTION",
                            "deductibility_status": "DEDUCTIBLE_CURRENT",
                            "allocation_status": "PROPERTY_AND_TAXPAYER_SHARE_CONFIRMED",
                            "paid_or_incurred_in_tax_year": True
                        },
                        {
                            "item_id": "exp_repairs",
                            "gross_amount": 550.0,
                            "reimbursement_amount": 0.0,
                            "nonrental_allocated_amount": 0.0,
                            "expense_category": "REPAIRS",
                            "deductibility_status": "DEDUCTIBLE_CURRENT",
                            "allocation_status": "PROPERTY_AND_TAXPAYER_SHARE_CONFIRMED",
                            "paid_or_incurred_in_tax_year": True
                        },
                        {
                            "item_id": "exp_taxes",
                            "gross_amount": 2400.0,
                            "reimbursement_amount": 0.0,
                            "nonrental_allocated_amount": 0.0,
                            "expense_category": "TAXES",
                            "deductibility_status": "DEDUCTIBLE_CURRENT",
                            "allocation_status": "PROPERTY_AND_TAXPAYER_SHARE_CONFIRMED",
                            "paid_or_incurred_in_tax_year": True
                        }
                    ],
                    "depreciation_result": {
                        "property_id": "prop_river_oak",
                        "tax_year": 2025,
                        "calculation_status": "CALCULATED",
                        "depreciation_amount": 8000.0,
                        "form_4562_attachment_required": False,
                        "source_result_id": "dep_res_01"
                    }
                }
            ]
        }

    def test_rivera_rental_normal_flow(self):
        # 1. Normal flow: simple residential rental with matching income and expenses ($0 net profit)
        res = calculate_schedule_e_dynamic(self.base_inputs)
        
        # Verify Identity masking
        self.assertEqual(res["taxpayer_name"], "Marcus Rivera")
        self.assertEqual(res["taxpayer_ssn_masked"], "***-**-3456")
        self.assertEqual(res["tax_year"], 2025)
        
        # Verify Property result columns and mappings
        props = res["properties"]
        self.assertEqual(len(props), 1)
        prop = props[0]
        self.assertEqual(prop["property_column"], "A")
        self.assertEqual(prop["line_1b_property_type_code"], 1)
        
        # Line 3 = 16200 + 150 + 300 = 16650
        self.assertEqual(prop["line_3_rents_received"], 16650.0)
        # Line 4 = 0
        self.assertEqual(prop["line_4_royalties_received"], 0.0)
        
        # Expenses Insurance (900), Interest (4800), Repairs (550), Taxes (2400), Depreciation (8000)
        self.assertEqual(prop["line_9_insurance"], 900.0)
        self.assertEqual(prop["line_12_mortgage_interest"], 4800.0)
        self.assertEqual(prop["line_14_repairs"], 550.0)
        self.assertEqual(prop["line_16_taxes"], 2400.0)
        self.assertEqual(prop["line_18_depreciation"], 8000.0)
        
        # Total expenses = 900 + 4800 + 550 + 2400 + 8000 = 16650
        self.assertEqual(prop["line_20_total_expenses"], 16650.0)
        
        # Net income = 16650 - 16650 = 0
        self.assertEqual(prop["pre_at_risk_net_income_or_loss"], 0.0)
        self.assertEqual(prop["line_21_income_or_loss"], 0.0)
        self.assertIsNone(prop["line_22_deductible_rental_loss"])
        
        # Totals mapping
        self.assertEqual(res["line_23a_total_rents"], 16650.0)
        self.assertEqual(res["line_23b_total_royalties"], 0.0)
        self.assertEqual(res["line_23c_total_mortgage_interest"], 4800.0)
        self.assertEqual(res["line_23d_total_depreciation"], 8000.0)
        self.assertEqual(res["line_23e_total_expenses"], 16650.0)
        
        self.assertEqual(res["line_24_income"], 0.0)
        self.assertEqual(res["line_25_losses"], 0.0)
        self.assertEqual(res["line_26_total_rental_income_or_loss"], 0.0)
        self.assertEqual(res["schedule_1_line_5_transfer_amount"], 0.0)
        
        # Attachment coordinates
        self.assertFalse(res["requires_form_4562_attachment"])
        self.assertFalse(res["requires_form_6198_attachment"])
        self.assertFalse(res["requires_form_8582_attachment"])
        self.assertFalse(res["requires_form_461_review"])
        
        # V1 execution checks
        self.assertTrue(res["has_reportable_rental_property"])
        self.assertTrue(res["is_v1_supported"])
        self.assertTrue(res["should_attach_schedule_e"])
        self.assertTrue(res["can_finalize_part1"])
        self.assertTrue(res["can_transfer_line_26"])
        self.assertEqual(len(res["blocking_errors"]), 0)

    def test_negative_amounts_validation(self):
        # Set negative rent income
        inputs = dict(self.base_inputs)
        inputs["properties"] = [dict(inputs["properties"][0])]
        inputs["properties"][0]["rental_income_items"] = [
            {
                "item_id": "inc_rent",
                "gross_amount_received": -500.0,
                "refunded_or_returned_amount": 0.0,
                "income_character_status": "REPORTABLE_SIMPLE_RENTAL_INCOME",
                "received_in_tax_year": True
            }
        ]
        
        res = calculate_schedule_e_dynamic(inputs)
        self.assertFalse(res["can_finalize_part1"])
        
        # Check for NEGATIVE_AMOUNT error
        err_codes = [err["code"] for err in res["blocking_errors"]]
        self.assertIn("NEGATIVE_AMOUNT", err_codes)

    def test_unsupported_property_type(self):
        # Set property type to ROYALTY
        inputs = dict(self.base_inputs)
        inputs["properties"] = [dict(inputs["properties"][0])]
        inputs["properties"][0]["property_type"] = "ROYALTIES"
        
        res = calculate_schedule_e_dynamic(inputs)
        self.assertFalse(res["is_v1_supported"])
        self.assertFalse(res["can_finalize_part1"])
        
        err_codes = [err["code"] for err in res["blocking_errors"]]
        self.assertIn("UNSUPPORTED_ROYALTY_PROPERTY", err_codes)

    def test_1099_compliance_validation(self):
        # Set 1099 compliance status to REQUIRED but filed to null
        inputs = dict(self.base_inputs)
        inputs["form_1099_compliance"] = {
            "requirement_status": "REQUIRED",
            "filed_or_will_file_required_forms": None,
            "source_result_id": "res_1099_01"
        }
        
        res = calculate_schedule_e_dynamic(inputs)
        self.assertFalse(res["can_finalize_part1"])
        
        err_codes = [err["code"] for err in res["blocking_errors"]]
        self.assertIn("FORM_1099_FILING_STATUS_UNKNOWN", err_codes)

    def test_loss_rental_missing_results(self):
        # Generate loss by reducing rental income to $5,000, which results in loss of 5000 - 16650 = -11650
        inputs = dict(self.base_inputs)
        inputs["properties"] = [dict(inputs["properties"][0])]
        inputs["properties"][0]["rental_income_items"] = [
            {
                "item_id": "inc_rent",
                "gross_amount_received": 5000.0,
                "refunded_or_returned_amount": 0.0,
                "income_character_status": "REPORTABLE_SIMPLE_RENTAL_INCOME",
                "received_in_tax_year": True
            }
        ]
        
        # At-risk result and passive loss result are both missing
        res = calculate_schedule_e_dynamic(inputs)
        self.assertFalse(res["can_finalize_part1"])
        
        err_codes = [err["code"] for err in res["blocking_errors"]]
        self.assertIn("AT_RISK_RESULT_MISSING", err_codes)
        self.assertIn("PASSIVE_LOSS_RESULT_MISSING", err_codes)

    def test_loss_rental_with_completed_limitations(self):
        inputs = dict(self.base_inputs)
        inputs["properties"] = [dict(inputs["properties"][0])]
        inputs["properties"][0]["rental_income_items"] = [
            {
                "item_id": "inc_rent",
                "gross_amount_received": 5000.0,
                "refunded_or_returned_amount": 0.0,
                "income_character_status": "REPORTABLE_SIMPLE_RENTAL_INCOME",
                "received_in_tax_year": True
            }
        ]
        
        # Loss of 11650
        # Provide external results: fully at risk, passive loss allowed up to $3,000
        inputs["properties"][0]["at_risk_result"] = {
            "property_id": "prop_river_oak",
            "tax_year": 2025,
            "status": "NOT_REQUIRED_FULLY_AT_RISK",
            "source_result_id": "atrisk_res_01"
        }
        inputs["properties"][0]["passive_loss_result"] = {
            "property_id": "prop_river_oak",
            "tax_year": 2025,
            "status": "CALCULATED_BY_FORM_8582",
            "line_22_deductible_rental_loss": -3000.0,
            "form_8582_attachment_required": True,
            "source_result_id": "passive_res_01"
        }
        
        res = calculate_schedule_e_dynamic(inputs)
        
        self.assertTrue(res["can_finalize_part1"])
        self.assertEqual(len(res["blocking_errors"]), 0)
        
        prop = res["properties"][0]
        self.assertEqual(prop["line_21_income_or_loss"], -11650.0)
        self.assertEqual(prop["line_22_deductible_rental_loss"], -3000.0)
        
        self.assertEqual(res["line_24_income"], 0.0)
        self.assertEqual(res["line_25_losses"], -3000.0)
        self.assertEqual(res["line_26_total_rental_income_or_loss"], -3000.0)
        self.assertEqual(res["schedule_1_line_5_transfer_amount"], -3000.0)
        
        self.assertFalse(res["requires_form_6198_attachment"])
        self.assertTrue(res["requires_form_8582_attachment"])
        self.assertTrue(res["requires_form_461_review"])

if __name__ == "__main__":
    unittest.main()
