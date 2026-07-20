import sys
import os
import json
import shutil
from typing import Dict, Any

# Add workspace dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from processors.models.schedule_a import ScheduleAInputsV1
from processors.calculators.schedule_a import calculate_schedule_a_v1
from processors.models.schedule_b import ScheduleBInputsV1
from processors.calculators.schedule_b import calculate_schedule_b_v1
from processors.models.schedule_c import ScheduleCInputsV1
from processors.calculators.schedule_c import calculate_schedule_c_v1
from processors.models.schedule_e import ScheduleEPart1InputsV1
from processors.calculators.schedule_e import calculate_schedule_e_part1_v1

def test_schedule_a():
    print("Testing Schedule A tax year validations...")
    
    # Case 1: Missing tax year
    inputs_missing = ScheduleAInputsV1.from_dict({
        "taxpayer_name": "Test User",
        "taxpayer_ssn": "123-45-6789"
    })
    res_missing = calculate_schedule_a_v1(inputs_missing)
    errors_missing = [e.code for e in res_missing.blocking_errors]
    assert "UNSUPPORTED_TAX_YEAR" in errors_missing, f"Expected UNSUPPORTED_TAX_YEAR for missing tax year, got {errors_missing}"
    print("  ✅ Missing tax year triggers UNSUPPORTED_TAX_YEAR")
    
    # Case 2: Unsupported tax year (e.g. 2023)
    inputs_2023 = ScheduleAInputsV1.from_dict({
        "taxpayer_name": "Test User",
        "taxpayer_ssn": "123-45-6789",
        "tax_year": 2023
    })
    res_2023 = calculate_schedule_a_v1(inputs_2023)
    errors_2023 = [e.code for e in res_2023.blocking_errors]
    assert "UNSUPPORTED_TAX_YEAR" in errors_2023, f"Expected UNSUPPORTED_TAX_YEAR for 2023, got {errors_2023}"
    print("  ✅ Unsupported tax year (2023) triggers UNSUPPORTED_TAX_YEAR")
    
    # Case 3: Supported tax year (2024)
    inputs_2024 = ScheduleAInputsV1.from_dict({
        "taxpayer_name": "Test User",
        "taxpayer_ssn": "123-45-6789",
        "tax_year": 2024
    })
    res_2024 = calculate_schedule_a_v1(inputs_2024)
    errors_2024 = [e.code for e in res_2024.blocking_errors]
    assert "UNSUPPORTED_TAX_YEAR" not in errors_2024, f"Did not expect UNSUPPORTED_TAX_YEAR for 2024, got {errors_2024}"
    print("  ✅ Supported tax year (2024) is allowed")
    
    # Case 4: Dynamically limit allowed years to only {2025}
    res_limit = calculate_schedule_a_v1(inputs_2024, allowed_years={2025})
    errors_limit = [e.code for e in res_limit.blocking_errors]
    assert "UNSUPPORTED_TAX_YEAR" in errors_limit, f"Expected UNSUPPORTED_TAX_YEAR for 2024 when only 2025 is allowed, got {errors_limit}"
    print("  ✅ Dynamically provided allowed_years works")


def test_schedule_b():
    print("Testing Schedule B tax year validations...")
    
    # Case 1: Missing tax year
    inputs_missing = ScheduleBInputsV1.from_dict({
        "taxpayer_name": "Test User",
        "taxpayer_ssn": "123-45-6789"
    })
    res_missing = calculate_schedule_b_v1(inputs_missing)
    errors_missing = [e.code for e in res_missing.blocking_errors]
    assert "UNSUPPORTED_TAX_YEAR" in errors_missing, f"Expected UNSUPPORTED_TAX_YEAR for missing tax year, got {errors_missing}"
    print("  ✅ Missing tax year triggers UNSUPPORTED_TAX_YEAR")
    
    # Case 2: Unsupported tax year (e.g. 2023)
    inputs_2023 = ScheduleBInputsV1.from_dict({
        "taxpayer_name": "Test User",
        "taxpayer_ssn": "123-45-6789",
        "tax_year": 2023
    })
    res_2023 = calculate_schedule_b_v1(inputs_2023)
    errors_2023 = [e.code for e in res_2023.blocking_errors]
    assert "UNSUPPORTED_TAX_YEAR" in errors_2023, f"Expected UNSUPPORTED_TAX_YEAR for 2023, got {errors_2023}"
    print("  ✅ Unsupported tax year (2023) triggers UNSUPPORTED_TAX_YEAR")
    
    # Case 3: Supported tax year (2024)
    inputs_2024 = ScheduleBInputsV1.from_dict({
        "taxpayer_name": "Test User",
        "taxpayer_ssn": "123-45-6789",
        "tax_year": 2024
    })
    res_2024 = calculate_schedule_b_v1(inputs_2024)
    errors_2024 = [e.code for e in res_2024.blocking_errors]
    assert "UNSUPPORTED_TAX_YEAR" not in errors_2024, f"Did not expect UNSUPPORTED_TAX_YEAR for 2024, got {errors_2024}"
    print("  ✅ Supported tax year (2024) is allowed")
    
    # Case 4: Dynamically limit allowed years to only {2025}
    res_limit = calculate_schedule_b_v1(inputs_2024, allowed_years={2025})
    errors_limit = [e.code for e in res_limit.blocking_errors]
    assert "UNSUPPORTED_TAX_YEAR" in errors_limit, f"Expected UNSUPPORTED_TAX_YEAR for 2024 when only 2025 is allowed, got {errors_limit}"
    print("  ✅ Dynamically provided allowed_years works")


def test_schedule_c():
    print("Testing Schedule C tax year validations...")
    
    # Case 1: Missing tax year
    inputs_missing = ScheduleCInputsV1.from_dict({
        "proprietor_name": "Test User",
        "taxpayer_ssn": "123-45-6789",
        "income": {"line_1_gross_receipts": 1000.0}
    })
    res_missing = calculate_schedule_c_v1(inputs_missing)
    errors_missing = [e.code for e in res_missing.blocking_errors]
    assert "UNSUPPORTED_TAX_YEAR" in errors_missing, f"Expected UNSUPPORTED_TAX_YEAR for missing tax year, got {errors_missing}"
    print("  ✅ Missing tax year triggers UNSUPPORTED_TAX_YEAR")
    
    # Case 2: Unsupported tax year (e.g. 2023)
    inputs_2023 = ScheduleCInputsV1.from_dict({
        "proprietor_name": "Test User",
        "taxpayer_ssn": "123-45-6789",
        "tax_year": 2023,
        "income": {"line_1_gross_receipts": 1000.0}
    })
    res_2023 = calculate_schedule_c_v1(inputs_2023)
    errors_2023 = [e.code for e in res_2023.blocking_errors]
    assert "UNSUPPORTED_TAX_YEAR" in errors_2023, f"Expected UNSUPPORTED_TAX_YEAR for 2023, got {errors_2023}"
    print("  ✅ Unsupported tax year (2023) triggers UNSUPPORTED_TAX_YEAR")
    
    # Case 3: Supported tax year (2024)
    inputs_2024 = ScheduleCInputsV1.from_dict({
        "proprietor_name": "Test User",
        "taxpayer_ssn": "123-45-6789",
        "tax_year": 2024,
        "income": {"line_1_gross_receipts": 1000.0}
    })
    res_2024 = calculate_schedule_c_v1(inputs_2024)
    errors_2024 = [e.code for e in res_2024.blocking_errors]
    assert "UNSUPPORTED_TAX_YEAR" not in errors_2024, f"Did not expect UNSUPPORTED_TAX_YEAR for 2024, got {errors_2024}"
    print("  ✅ Supported tax year (2024) is allowed")
    
    # Case 4: Dynamically limit allowed years to only {2025}
    res_limit = calculate_schedule_c_v1(inputs_2024, allowed_years={2025})
    errors_limit = [e.code for e in res_limit.blocking_errors]
    assert "UNSUPPORTED_TAX_YEAR" in errors_limit, f"Expected UNSUPPORTED_TAX_YEAR for 2024 when only 2025 is allowed, got {errors_limit}"
    print("  ✅ Dynamically provided allowed_years works")


def test_schedule_e():
    print("Testing Schedule E tax year validations...")
    
    # Case 1: Missing tax year
    inputs_missing = ScheduleEPart1InputsV1.from_dict({
        "taxpayer_name": "Test User",
        "taxpayer_ssn": "123-45-6789",
        "properties": []
    })
    res_missing = calculate_schedule_e_part1_v1(inputs_missing)
    errors_missing = [e.code for e in res_missing.blocking_errors]
    assert "UNSUPPORTED_TAX_YEAR" in errors_missing, f"Expected UNSUPPORTED_TAX_YEAR for missing tax year, got {errors_missing}"
    print("  ✅ Missing tax year triggers UNSUPPORTED_TAX_YEAR")
    
    # Case 2: Unsupported tax year (e.g. 2023)
    inputs_2023 = ScheduleEPart1InputsV1.from_dict({
        "taxpayer_name": "Test User",
        "taxpayer_ssn": "123-45-6789",
        "tax_year": 2023,
        "properties": []
    })
    res_2023 = calculate_schedule_e_part1_v1(inputs_2023)
    errors_2023 = [e.code for e in res_2023.blocking_errors]
    assert "UNSUPPORTED_TAX_YEAR" in errors_2023, f"Expected UNSUPPORTED_TAX_YEAR for 2023, got {errors_2023}"
    print("  ✅ Unsupported tax year (2023) triggers UNSUPPORTED_TAX_YEAR")
    
    # Case 3: Supported tax year (2024)
    inputs_2024 = ScheduleEPart1InputsV1.from_dict({
        "taxpayer_name": "Test User",
        "taxpayer_ssn": "123-45-6789",
        "tax_year": 2024,
        "properties": []
    })
    res_2024 = calculate_schedule_e_part1_v1(inputs_2024)
    errors_2024 = [e.code for e in res_2024.blocking_errors]
    assert "UNSUPPORTED_TAX_YEAR" not in errors_2024, f"Did not expect UNSUPPORTED_TAX_YEAR for 2024, got {errors_2024}"
    print("  ✅ Supported tax year (2024) is allowed")
    
    # Case 4: Dynamically limit allowed years to only {2025}
    res_limit = calculate_schedule_e_part1_v1(inputs_2024, allowed_years={2025})
    errors_limit = [e.code for e in res_limit.blocking_errors]
    assert "UNSUPPORTED_TAX_YEAR" in errors_limit, f"Expected UNSUPPORTED_TAX_YEAR for 2024 when only 2025 is allowed, got {errors_limit}"
    print("  ✅ Dynamically provided allowed_years works")


def test_robust_parsing():
    print("Testing robust tax year parsing and type conversions...")

    # Case 1: Float string "2024.0" (valid but float representation)
    inputs_float = ScheduleAInputsV1.from_dict({
        "taxpayer_name": "Test User",
        "taxpayer_ssn": "123-45-6789",
        "tax_year": "2024.0"
    })
    assert inputs_float.tax_year == 2024
    res_float = calculate_schedule_a_v1(inputs_float)
    assert "UNSUPPORTED_TAX_YEAR" not in [e.code for e in res_float.blocking_errors]
    print("  ✅ Float string '2024.0' is successfully parsed as 2024")

    # Case 2: Non-numeric string "not-a-year"
    inputs_invalid_str = ScheduleBInputsV1.from_dict({
        "taxpayer_name": "Test User",
        "taxpayer_ssn": "123-45-6789",
        "tax_year": "not-a-year"
    })
    assert inputs_invalid_str.tax_year is None
    res_invalid_str = calculate_schedule_b_v1(inputs_invalid_str)
    assert "UNSUPPORTED_TAX_YEAR" in [e.code for e in res_invalid_str.blocking_errors]
    print("  ✅ Non-numeric string 'not-a-year' is parsed as None and triggers UNSUPPORTED_TAX_YEAR")

    # Case 3: Invalid type (list)
    inputs_list = ScheduleCInputsV1.from_dict({
        "proprietor_name": "Test User",
        "taxpayer_ssn": "123-45-6789",
        "tax_year": [2024]
    })
    assert inputs_list.tax_year is None
    res_list = calculate_schedule_c_v1(inputs_list)
    assert "UNSUPPORTED_TAX_YEAR" in [e.code for e in res_list.blocking_errors]
    print("  ✅ Invalid type list '[2024]' is parsed as None and triggers UNSUPPORTED_TAX_YEAR")

    # Case 4: Invalid type (dict)
    inputs_dict = ScheduleEPart1InputsV1.from_dict({
        "taxpayer_name": "Test User",
        "taxpayer_ssn": "123-45-6789",
        "tax_year": {"year": 2024}
    })
    assert inputs_dict.tax_year is None
    res_dict = calculate_schedule_e_part1_v1(inputs_dict)
    assert "UNSUPPORTED_TAX_YEAR" in [e.code for e in res_dict.blocking_errors]
    print("  ✅ Invalid type dict '{\"year\": 2024}' is parsed as None and triggers UNSUPPORTED_TAX_YEAR")


if __name__ == "__main__":
    test_schedule_a()
    test_schedule_b()
    test_schedule_c()
    test_schedule_e()
    test_robust_parsing()
    print("\n🎉 ALL DYNAMIC TAX YEAR TESTS PASSED SUCCESSFULLY!")
