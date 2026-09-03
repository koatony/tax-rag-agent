import unittest

from form1040.models.tax_computation_model import FilingStatus, normalize_filing_status


class TestFilingStatusNormalization(unittest.TestCase):
    def test_head_of_household_aliases_normalize_to_hoh(self):
        for value in ("HOH", "HEAD_OF_HOUSEHOLD", "Head of Household", "head-of-household"):
            with self.subTest(value=value):
                self.assertEqual(normalize_filing_status(value), FilingStatus.HOH)

    def test_other_supported_long_names_are_normalized(self):
        self.assertEqual(normalize_filing_status("married filing jointly"), FilingStatus.MFJ)
        self.assertEqual(normalize_filing_status("MARRIED_FILING_SEPARATELY"), FilingStatus.MFS)
        self.assertEqual(normalize_filing_status("qualifying surviving spouse"), FilingStatus.QSS)

    def test_unknown_status_does_not_fall_back_to_single(self):
        with self.assertRaisesRegex(ValueError, "Unsupported filing status"):
            normalize_filing_status("UNKNOWN")


if __name__ == "__main__":
    unittest.main()
