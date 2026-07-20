import json
import os
import re
from typing import Dict, Any, List, Tuple
from decimal import Decimal
from dotenv import load_dotenv

# Import from modular OOP layers
from processors.models.schedule_a import (
    MedicalExpenseItemV1,
    TaxPaymentItemV1,
    MortgageInterestItemV1,
    CashCharityItemV1,
    StandardDeductionReferenceV1,
    SpecialCaseFlagsV1,
    ScheduleAInputsV1,
    ValidationIssue,
    ScheduleAResultV1,
    load_tax_rates,
)
from processors.validators.schedule_a import (
    validate_identity,
    validate_tax_year,
    validate_nonnegative_amounts,
    detect_unsupported_cases,
    validate_paid_year,
)
from processors.calculators.schedule_a import (
    sum_decimal,
    is_over_65,
    calculate_additional_standard_deduction,
    calculate_salt_limit_v1,
    calculate_simple_form_1098,
    calculate_cash_charity,
    any_unsupported_case,
    calculate_schedule_a_v1,
)
from processors.parsers.schedule_a import ScheduleALLMParser

load_dotenv()

SCHEMA_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "docs",
        "how_to_fill_forms_docs",
        "schedule_a",
        "schedule_a_schema.json",
    )
)


def load_schedule_a_schema() -> Dict[str, Any]:
    """載入外部的 Schedule A 欄位與計算規則設定檔 (schedule_a_schema.json)。"""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_schedule_a_inputs_with_logs(
    document_context: str, model_name: str = "gemini-2.5-pro"
) -> Tuple[Dict[str, Any], str, str]:
    """呼叫 LLM 進行 Schedule A 數據提取，並回傳: (提取 JSON, 發送 Prompt, LLM 原始輸出)。"""
    parser = ScheduleALLMParser(model_name=model_name)
    return parser.parse(document_context)


def coalesce_decimal(*args):
    """回傳第一個非 None 的 Decimal 項目，否則回傳 Decimal('0.00')。"""
    for arg in args:
        if arg is not None:
            return Decimal(str(arg))
    return Decimal("0.00")


def dict_to_v1_inputs(inputs_dict: Dict[str, Any]) -> ScheduleAInputsV1:
    config_path = os.path.join(os.path.dirname(SCHEMA_PATH), "agi_config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            if "adjusted_gross_income" in config_data:
                inputs_dict["adjusted_gross_income"] = config_data["adjusted_gross_income"]
        except Exception:
            pass
    return ScheduleAInputsV1.from_dict(inputs_dict)


def calculate_schedule_a_dynamic(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """主動態執行接口，將傳入字典轉為 V1 結構並執行 Python 確定性計算，保證相容性。"""
    v1_inputs = dict_to_v1_inputs(inputs)
    try:
        schema = load_schedule_a_schema()
        allowed_years = set(schema.get("supported_tax_years", [2024, 2025]))
    except Exception:
        allowed_years = {2024, 2025}
    res = calculate_schedule_a_v1(v1_inputs, allowed_years=allowed_years)
    res_dict = res.to_dict()

    compat_mapping = {
        "line_1_medical_and_dental_expenses_net": res.line_1_medical_and_dental_expenses,
        "line_3_agi_threshold_7_5_percent": res.line_3_medical_threshold,
        "line_5a_general_sales_tax_elected": res.line_5a_sales_tax_checkbox,
        "line_5b_amount": res.line_5b_real_estate_taxes,
        "line_5c_amount": res.line_5c_personal_property_taxes,
        "line_5d_amount": res.line_5d_salt_before_limit,
        "line_5e_amount": res.line_5e_salt_deduction,
        "line_6_amount": res.line_6_other_taxes,
        "line_7_amount": res.line_7_total_taxes,
        "line_8a": res.line_8a_home_mortgage_interest,
        "line_8b": res.line_8b_non_1098_interest,
        "line_8c": res.line_8c_non_1098_points,
        "line_8e": res.line_8e_total_mortgage_interest,
        "line_9": res.line_9_investment_interest,
        "line_10_interest": res.line_10_total_interest_paid,
        "line_11": res.line_11_cash_contributions,
        "line_12": res.line_12_noncash_contributions,
        "line_13": res.line_13_charity_carryover,
        "line_14_charity": res.line_14_total_charity,
        "line_15": res.line_15_casualty_theft_loss,
        "line_16": res.line_16_other_itemized_deductions,
        "line_17_total_itemized": res.line_17_total_itemized_deductions,
        "should_itemize": res.is_itemizing,
        "taxpayer_name": res.taxpayer_name,
        "ssn": res.taxpayer_ssn_masked,
        "tax_year": res.tax_year,
        "filing_status": res.filing_status,
        "agi": res.line_2_agi,
    }

    for old_k, val in compat_mapping.items():
        if isinstance(val, Decimal):
            res_dict[old_k] = float(val)
        else:
            res_dict[old_k] = val

    if res.is_itemizing is True:
        res_dict["final_deduction_used"] = (
            float(res.line_17_total_itemized_deductions)
            if res.line_17_total_itemized_deductions is not None
            else 0.0
        )
    elif res.is_itemizing is False:
        res_dict["final_deduction_used"] = (
            float(res.standard_deduction_amount)
            if res.standard_deduction_amount is not None
            else 0.0
        )
    else:
        res_dict["final_deduction_used"] = 0.0

    has_charity_pending = any(
        isinstance(err, dict)
        and err.get("code") in ("MISSING_250_ACKNOWLEDGMENT", "CHARITY_CONTRIBUTION_DATE_MISSING")
        for err in res_dict.get("blocking_errors", [])
    )
    if has_charity_pending:
        res_dict["line_11_cash_contributions_status"] = "excluded_pending_documentation"

    return res_dict
