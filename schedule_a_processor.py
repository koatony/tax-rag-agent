import json
import os
import re
from typing import Dict, Any, List, Tuple
from decimal import Decimal
from dotenv import load_dotenv
from llm_wrappers import GeminiLLM, OllamaLLM
from langchain_core.messages import SystemMessage, HumanMessage

# 載入環境變數
load_dotenv()

SCHEMA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "docs", "how_to_fill_forms_docs", "schedule_a", "schedule_a_schema.json"))
TAX_RATES_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "docs", "how_to_fill_forms_docs", "schedule_a", "schedule_a_tax_rates.json"))
REFERENCES_DEFAULT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "docs", "how_to_fill_forms_docs", "schedule_a", "schedule_a_references_default.json"))

def load_schedule_a_schema() -> Dict[str, Any]:
    """載入外部的 Schedule A 欄位與計算規則設定檔 (schedule_a_schema.json)。"""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def load_schedule_a_references_default() -> Dict[str, Any]:
    """載入外部的 Schedule A 參考資料預設值設定檔 (schedule_a_references_default.json)。"""
    with open(REFERENCES_DEFAULT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def load_tax_rates(tax_year: int) -> Dict[str, Any]:
    """根據申報年度 (tax_year) 動態載入對應年份的稅率與限制常數 (schedule_a_tax_rates.json)。"""
    with open(TAX_RATES_PATH, "r", encoding="utf-8") as f:
        all_rates = json.load(f)
    year_key = str(int(tax_year))
    if year_key not in all_rates:
        return all_rates["2025"]
    return all_rates[year_key]

def generate_extraction_prompt(schema: Dict[str, Any]) -> str:
    """根據 schema 動態組裝 LLM 的 prompt。"""
    inputs_def = []
    for field in schema.get("inputs", []):
        inputs_def.append(f'- `{field["id"]}` ({field["type"]}): {field["description"]}')
        
    inputs_str = "\n".join(inputs_def)
    
    prompt = f"""你是一位專業的美國稅務申報與數據提取專家。
你的任務是從申報人基本資料以及上傳的憑證中，精準提取出國稅局 (IRS) Schedule A (Form 1040) V1 中所有「直接輸入型 (Input)」的欄位值。

【提取規範】
1. 只需提取以下列出的「直接輸入 (Input)」欄位。不要包含任何「公式計算 (Formula)」欄位。
2. 對於數值欄位，若沒有相關資訊，則填寫 0.00；對於布林值，若無資訊則填寫 false 或 null。
3. 數值必須是純數值，不能包含貨幣符號 ($) 或分節逗號 (,)。

【預期提取的欄位列表】
{inputs_str}

【輸出格式】
你必須精確返回一個符合上述欄位的 JSON 對象，例如：
{{
  "taxpayer_name": "Marcus Rivera",
  "taxpayer_ssn": "123-45-6789",
  "tax_year": 2025,
  "filing_status": "MFJ",
  "adjusted_gross_income": 125000.00,
  "medical_items": [],
  "tax_items": [],
  "line_5a_election": "INCOME_TAX",
  "mortgage_interest_items": [],
  "cash_charity_items": [],
  "special_case_flags": {{
    "has_marketplace_medical_premium": false,
    "has_ltc_premium": false
  }}
}}
直接返回乾淨的 JSON 字串，不要使用 markdown 區塊，也不要包含 any 說明文字。
"""
    return prompt

def extract_schedule_a_inputs_with_logs(
    document_context: str, 
    model_name: str = "gemini-2.5-pro"
) -> Tuple[Dict[str, Any], str, str]:
    """呼叫 LLM 進行 Schedule A 數據提取，並回傳: (提取 JSON, 發送 Prompt, LLM 原始輸出)。"""
    llm_provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    is_ollama = False
    if model_name and "gemini" in model_name.lower():
        is_ollama = False
    elif model_name and ":" in model_name:
        is_ollama = True
    else:
        is_ollama = (llm_provider == "ollama")

    schema = load_schedule_a_schema()
    system_instruction = generate_extraction_prompt(schema)
    
    if is_ollama:
        llm = OllamaLLM(model_name=model_name, temperature=0.0, timeout=600.0)
    else:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("環境變數 GEMINI_API_KEY 未設定")
        llm = GeminiLLM(model_name=model_name, api_key=api_key, temperature=0.0)
    
    messages = [
        SystemMessage(content=system_instruction),
        HumanMessage(content=f"以下是申報人與上傳文件的相關內容，請提取 Schedule A 的 Input 欄位：\n\n{document_context}")
    ]
    
    full_prompt_log = f"=== SYSTEM INSTRUCTION ===\n{system_instruction}\n\n=== USER PROMPT ===\n以下是申報人與上傳文件的相關內容，請提取 Schedule A 的 Input 欄位：\n\n{document_context}"
    
    if is_ollama:
        resp = llm.invoke(messages)
    else:
        resp = llm.invoke(messages, response_mime_type="application/json")
        
    raw_output = resp.content.strip()
    clean_output = re.sub(r"<think>.*?</think>", "", raw_output, flags=re.DOTALL).strip()
    
    match = re.search(r"\{.*\}", clean_output, re.DOTALL)
    if match:
        clean_output = match.group(0)
        
    try:
        from json_repair import repair_json
        repaired_output = repair_json(clean_output)
        extracted_data = json.loads(repaired_output)
        return extracted_data, full_prompt_log, raw_output
    except Exception as e:
        raise ValueError(f"JSON 解析與修復失敗: {e}\nLLM 原始回應: {raw_output}")

def topological_sort(formula_deps: Dict[str, List[str]]) -> List[str]:
    """使用 DFS 演算法對公式依賴樹進行拓撲排序，排除循環引用。"""
    visited = {}  # 0: unvisited, 1: visiting, 2: visited
    order = []
    
    def dfs(node):
        if visited.get(node, 0) == 1:
            raise ValueError(f"公式依賴檢測到循環引用 (Cycle detected at node): {node}")
        if visited.get(node, 0) == 2:
            return
            
        visited[node] = 1  # visiting
        for dep in formula_deps.get(node, []):
            if dep in formula_deps:
                dfs(dep)
        visited[node] = 2  # visited
        order.append(node)
        
    for node in formula_deps:
        if visited.get(node, 0) == 0:
            dfs(node)
            
    return order

def sum_decimal(iterable):
    """將可迭代項目加總為 Decimal 類型的金額。"""
    s = Decimal("0.00")
    for x in iterable:
        if x is not None:
            s += Decimal(str(x))
    return s

def coalesce_decimal(*args):
    """回傳第一個非 None 的 Decimal 項目，否則回傳 Decimal('0.00')。"""
    for arg in args:
        if arg is not None:
            return Decimal(str(arg))
    return Decimal("0.00")

# =====================================================================
# V1 數據模型定義 (V1 Data Model Definitions)
# =====================================================================
# 這些模型定義了 Schedule A 稅務引擎的結構化輸入與輸出。
# 運作流程：
# 1. API 接收到 JSON 原始輸入後，透過 `dict_to_v1_inputs()` 將其轉換為 `ScheduleAInputsV1`。
# 2. 轉換過程中，各子欄位列表（例如醫療、稅金、房貸利息、慈善捐贈）會被分別實例化為對應的子 Model。
# 3. 核心稅務引擎 `calculate_schedule_a_v1(inputs)` 接收 `ScheduleAInputsV1` 並進行確定性的稅務計算與防呆校驗。
# 4. 計算結束後返回 `ScheduleAResultV1`，最後透過 `to_dict()` 轉回相容舊版 UI 的字典格式。

class MedicalExpenseItemV1:
    """
    醫療費用明細模型 (Medical Expense Item).
    用於申報人填報或從憑證中提取的單筆醫療/牙醫支出。
    計算時會加總所有合規項目並扣除補償(Reimbursement)，最後在 Line 1 進行 AGI 7.5% 的門檻計算。
    """
    def __init__(self, **kwargs):
        self.item_id = str(kwargs.get("item_id", ""))
        self.source_document_id = kwargs.get("source_document_id")  # 來源文件 ID (如收據檔名)
        self.description = kwargs.get("description")
        self.paid_in_tax_year = kwargs.get("paid_in_tax_year")  # 是否在該報稅年度支付 (bool | None)
        self.taxpayer_paid_amount = Decimal(str(kwargs.get("taxpayer_paid_amount", "0.00")))  # 申報人支付總額
        self.reimbursement_amount = Decimal(str(kwargs.get("reimbursement_amount", "0.00")))  # 保險或第三方補償金額
        self.tax_free_medical_account_payment = Decimal(str(kwargs.get("tax_free_medical_account_payment", "0.00")))  # HSA/FSA 免稅帳戶支付額 (需扣除以防雙重得利)
        self.eligible_person_status = kwargs.get("eligible_person_status", "UNKNOWN")  # 扶養人/申報人資格 (ELIGIBLE | NOT_ELIGIBLE | UNKNOWN)
        self.medical_qualification_status = kwargs.get("medical_qualification_status", "UNKNOWN")  # 醫療支出合規狀態 (QUALIFIED_SIMPLE | NOT_DEDUCTIBLE | UNKNOWN)

class TaxPaymentItemV1:
    """
    稅金支出明細模型 (Tax Payment Item).
    用於申報人已繳納的州稅與地方稅 (SALT)。
    會歸入對應的池中 (TaxPools)，最後加總並受限於 $10,000 / $5,000 (MFS) 的 SALT 上限限制。
    """
    def __init__(self, **kwargs):
        self.item_id = str(kwargs.get("item_id", ""))
        self.source_document_id = kwargs.get("source_document_id")
        self.description = kwargs.get("description")
        self.paid_in_tax_year = kwargs.get("paid_in_tax_year")  # bool | None
        self.amount_paid = Decimal(str(kwargs.get("amount_paid", "0.00")))
        self.separately_stated_nondeductible_charge = Decimal(str(kwargs.get("separately_stated_nondeductible_charge", "0.00")))  # 另行列出的非扣除費用 (如罰鍰、服務費)
        self.tax_category = kwargs.get("tax_category", "UNKNOWN")  # 稅種 (如 STATE_LOCAL_INCOME_TAX, GENERAL_SALES_TAX, PERSONAL_REAL_ESTATE_TAX, PERSONAL_PROPERTY_TAX)
        self.personal_use_confirmed = kwargs.get("personal_use_confirmed")  # 房地產/財產是否確為個人用途 (不合規者會被剔除)
        self.actual_paid_to_taxing_authority_confirmed = kwargs.get("actual_paid_to_taxing_authority_confirmed")  # (針對房地產稅) 是否已實際繳納給稅務機關 (非僅託管帳戶 Escrow)
        self.value_based_and_annual_confirmed = kwargs.get("value_based_and_annual_confirmed")  # (針對個人財產稅) 是否根據價值計算且每年徵收

class MortgageInterestItemV1:
    """
    自住房貸利息模型 (Mortgage Interest Item).
    代表 Form 1098 或是符合扣除條件的購屋貸款利息支出。
    目前 V1 只支援單筆且無超額限制的簡單房貸 (CONFIRMED_SIMPLE)。
    """
    def __init__(self, **kwargs):
        self.item_id = str(kwargs.get("item_id", ""))
        self.source_document_id = kwargs.get("source_document_id")
        self.lender_name = kwargs.get("lender_name")
        self.source_document_type = kwargs.get("source_document_type", "FORM_1098")
        self.form_1098_box_1_mortgage_interest = Decimal(str(kwargs.get("form_1098_box_1_mortgage_interest", "0.00")))
        self.deductible_points_reported_on_1098 = Decimal(str(kwargs.get("deductible_points_reported_on_1098", "0.00")))  # Form 1098 Box 3 的點數支出
        self.paid_in_tax_year = kwargs.get("paid_in_tax_year")  # bool | None
        self.simple_mortgage_status = kwargs.get("simple_mortgage_status", "UNKNOWN")  # 房貸性質 (CONFIRMED_SIMPLE | LIMITATION_OR_WORKSHEET_REQUIRED | UNKNOWN)

class CashCharityItemV1:
    """
    現金慈善捐贈模型 (Cash Charity Item).
    記錄向合格慈善機構的現金、支票或刷卡捐贈支出。
    校驗重點：
    1. 超過或等於 $250 時必須取得受贈機構出具的 Contemporaneous Written Acknowledgment。
    2. 必須確認組織合規狀態為 VERIFIED。
    3. 必須扣除取得的商品或服務價值 (Goods or Services Value)。
    """
    def __init__(self, **kwargs):
        self.item_id = str(kwargs.get("item_id", ""))
        self.source_document_id = kwargs.get("source_document_id")
        self.contribution_date = kwargs.get("contribution_date")
        self.paid_in_tax_year = kwargs.get("paid_in_tax_year")  # bool | None
        self.organization_name = kwargs.get("organization_name")
        self.qualified_organization_status = kwargs.get("qualified_organization_status", "UNKNOWN")  # VERIFIED | NOT_QUALIFIED | UNKNOWN
        self.contribution_method = kwargs.get("contribution_method", "CASH")
        self.gross_contribution_amount = Decimal(str(kwargs.get("gross_contribution_amount", "0.00")))  # 總捐贈金額
        self.goods_or_services_value = Decimal(str(kwargs.get("goods_or_services_value", "0.00")))  # 獲得的回報對價價值
        self.bank_or_written_record_available = kwargs.get("bank_or_written_record_available")  # 是否有銀行帳單或書面紀錄
        self.contemporaneous_acknowledgment_received = kwargs.get("contemporaneous_acknowledgment_received")  # 是否有及時書面收據 (針對 >= $250)

class StandardDeductionReferenceV1:
    """
    標準扣除額參考配置 (Standard Deduction Reference).
    用於決定該申報人適用的標準扣除額基準，以及是否因特殊申報身份而強制列舉扣除。
    """
    def __init__(self, **kwargs):
        self.standard_deduction_amount = Decimal(str(kwargs.get("standard_deduction_amount"))) if kwargs.get("standard_deduction_amount") is not None else None
        self.must_itemize_due_to_mfs_spouse = kwargs.get("must_itemize_due_to_mfs_spouse")  # 夫妻分開申報且配偶選擇列舉時，自身是否強制列舉
        self.elect_itemize_even_if_less = kwargs.get("elect_itemize_even_if_less")  # 即使列舉總額小於標準扣除額，仍主動選擇列舉扣除

class SpecialCaseFlagsV1:
    """
    特殊/複雜稅務場景標記 (Special Case Flags).
    由於 V1 引擎僅支援常規簡單列舉扣除，本類別包含多個布林標記，
    如果其中任何一項為 True，則會被視為不支援 (Unsupported) 的複雜情境並產生阻斷性錯誤 (Blocking Error)，
    以防止引擎產出錯誤的稅務計算。
    """
    def __init__(self, **kwargs):
        self.has_marketplace_medical_premium = kwargs.get("has_marketplace_medical_premium", False)
        self.has_ltc_premium = kwargs.get("has_ltc_premium", False)
        self.has_self_employed_health_insurance_overlap = kwargs.get("has_self_employed_health_insurance_overlap", False)
        self.has_prior_year_medical_recovery = kwargs.get("has_prior_year_medical_recovery", False)
        self.sales_tax_amount_requires_calculation = kwargs.get("sales_tax_amount_requires_calculation", False)
        self.has_tax_refund_or_rebate_adjustment = kwargs.get("has_tax_refund_or_rebate_adjustment", False)
        self.has_form_2555_or_4563_or_puerto_rico_exclusion = kwargs.get("has_form_2555_or_4563_or_puerto_rico_exclusion", False)
        self.has_other_tax_line_6 = kwargs.get("has_other_tax_line_6", False)
        self.has_multiple_mortgages = kwargs.get("has_multiple_mortgages", False)
        self.mortgage_proceeds_not_all_qualified = kwargs.get("mortgage_proceeds_not_all_qualified", False)
        self.mortgage_limitation_required = kwargs.get("mortgage_limitation_required", False)
        self.has_shared_mortgage = kwargs.get("has_shared_mortgage", False)
        self.has_non_1098_mortgage_interest = kwargs.get("has_non_1098_mortgage_interest", False)
        self.has_non_1098_points = kwargs.get("has_non_1098_points", False)
        self.has_seller_financed_mortgage = kwargs.get("has_seller_financed_mortgage", False)
        self.has_form_8396_credit = kwargs.get("has_form_8396_credit", False)
        self.has_investment_interest = kwargs.get("has_investment_interest", False)
        self.has_noncash_charity = kwargs.get("has_noncash_charity", False)
        self.has_charity_carryover = kwargs.get("has_charity_carryover", False)
        self.has_charitable_agi_limitation = kwargs.get("has_charitable_agi_limitation", False)
        self.has_casualty_or_theft_loss = kwargs.get("has_casualty_or_theft_loss", False)
        self.has_net_qualified_disaster_loss = kwargs.get("has_net_qualified_disaster_loss", False)
        self.has_line_16_item = kwargs.get("has_line_16_item", False)
        self.has_unresolved_mfs_joint_expense_allocation = kwargs.get("has_unresolved_mfs_joint_expense_allocation", False)

class ScheduleAInputsV1:
    """
    Schedule A 完整輸入模型 (Schedule A Inputs).
    封裝了進行列舉扣除計算所需的申報人基本資料、年度、AGI，以及醫療、稅務、房貸、慈善等明細列表。
    """
    def __init__(self, **kwargs):
        self.taxpayer_name = str(kwargs.get("taxpayer_name", ""))
        self.taxpayer_ssn = str(kwargs.get("taxpayer_ssn", ""))
        self.taxpayer_date_of_birth = kwargs.get("taxpayer_date_of_birth")
        self.taxpayer_blind = bool(kwargs.get("taxpayer_blind", False))
        self.spouse_date_of_birth = kwargs.get("spouse_date_of_birth")
        self.spouse_blind = bool(kwargs.get("spouse_blind", False))
        self.tax_year = int(kwargs.get("tax_year", 2025))
        self.filing_status = str(kwargs.get("filing_status", "SINGLE"))
        self.adjusted_gross_income = Decimal(str(kwargs.get("adjusted_gross_income", "0.00")))
        self.medical_items = [MedicalExpenseItemV1(**x) if isinstance(x, dict) else x for x in kwargs.get("medical_items", [])]
        self.tax_items = [TaxPaymentItemV1(**x) if isinstance(x, dict) else x for x in kwargs.get("tax_items", [])]
        self.line_5a_election = kwargs.get("line_5a_election")  # 選擇申報所得稅或銷售稅 (INCOME_TAX | GENERAL_SALES_TAX | None)
        self.mortgage_interest_items = [MortgageInterestItemV1(**x) if isinstance(x, dict) else x for x in kwargs.get("mortgage_interest_items", [])]
        self.cash_charity_items = [CashCharityItemV1(**x) if isinstance(x, dict) else x for x in kwargs.get("cash_charity_items", [])]
        
        ref = kwargs.get("standard_deduction_reference")
        self.standard_deduction_reference = StandardDeductionReferenceV1(**ref) if isinstance(ref, dict) else ref if ref else StandardDeductionReferenceV1()
        
        flags = kwargs.get("special_case_flags")
        self.special_case_flags = SpecialCaseFlagsV1(**flags) if isinstance(flags, dict) else flags if flags else SpecialCaseFlagsV1()

class ValidationIssue:
    """
    防呆與合規性檢驗結果 (Validation Issue).
    用於記錄阻斷性錯誤 (Blocking Error) 或提示性警告 (Review Warning)。
    例如 `MISSING_250_ACKNOWLEDGMENT`、`REAL_ESTATE_TAX_PAYMENT_NOT_CONFIRMED` 等。
    """
    def __init__(self, code: str, field: str = None, item_id: str = None, source_document_id: str = None, message: str = ""):
        self.code = code  # 錯誤或警告代碼
        self.field = field  # 出錯的欄位名稱
        self.item_id = item_id  # 關聯的明細項目 ID
        self.source_document_id = source_document_id  # 關聯的來源憑證/檔案名稱
        self.message = message  # 詳細錯誤訊息

    def to_dict(self):
        return {
            "code": self.code,
            "field": self.field,
            "item_id": self.item_id,
            "source_document_id": self.source_document_id,
            "message": self.message
        }

class ScheduleAResultV1:
    """
    Schedule A 完整計算結果模型 (Schedule A Calculation Result).
    包含 Schedule A 所有對應申報表單線頭 (Lines 1-18) 的計算金額，
    以及此筆申報是否建議列舉扣除 (is_itemizing)、最終抵扣金額 (standard_deduction_amount 與 line_17_total_itemized_deductions)，
    以及合規檢驗發現的所有錯誤 (blocking_errors) 與警告 (review_warnings)。
    """
    def __init__(self, **kwargs):
        self.taxpayer_name = kwargs.get("taxpayer_name", "")
        self.taxpayer_ssn_masked = kwargs.get("taxpayer_ssn_masked", "")
        self.tax_year = kwargs.get("tax_year", 2025)
        self.filing_status = kwargs.get("filing_status", "SINGLE")

        self.line_1_medical_and_dental_expenses = kwargs.get("line_1_medical_and_dental_expenses", Decimal("0.00"))
        self.line_2_agi = kwargs.get("line_2_agi", Decimal("0.00"))
        self.line_3_medical_threshold = kwargs.get("line_3_medical_threshold", Decimal("0.00"))
        self.line_4_deductible_medical_expenses = kwargs.get("line_4_deductible_medical_expenses", Decimal("0.00"))

        self.line_5a_amount = kwargs.get("line_5a_amount", Decimal("0.00"))
        self.line_5a_sales_tax_checkbox = kwargs.get("line_5a_sales_tax_checkbox", False)
        self.line_5b_real_estate_taxes = kwargs.get("line_5b_real_estate_taxes", Decimal("0.00"))
        self.line_5c_personal_property_taxes = kwargs.get("line_5c_personal_property_taxes", Decimal("0.00"))
        self.line_5d_salt_before_limit = kwargs.get("line_5d_salt_before_limit", Decimal("0.00"))
        self.line_5e_salt_deduction = kwargs.get("line_5e_salt_deduction")
        self.line_6_other_taxes = kwargs.get("line_6_other_taxes", Decimal("0.00"))
        self.line_7_total_taxes = kwargs.get("line_7_total_taxes")

        self.line_8_qualifying_proceeds_checkbox = kwargs.get("line_8_qualifying_proceeds_checkbox", False)
        self.line_8a_home_mortgage_interest = kwargs.get("line_8a_home_mortgage_interest", Decimal("0.00"))
        self.line_8b_non_1098_interest = kwargs.get("line_8b_non_1098_interest", Decimal("0.00"))
        self.line_8c_non_1098_points = kwargs.get("line_8c_non_1098_points", Decimal("0.00"))
        self.line_8d_reserved = kwargs.get("line_8d_reserved")
        self.line_8e_total_mortgage_interest = kwargs.get("line_8e_total_mortgage_interest", Decimal("0.00"))
        self.line_9_investment_interest = kwargs.get("line_9_investment_interest", Decimal("0.00"))
        self.line_10_total_interest_paid = kwargs.get("line_10_total_interest_paid", Decimal("0.00"))

        self.line_11_cash_contributions = kwargs.get("line_11_cash_contributions", Decimal("0.00"))
        self.line_12_noncash_contributions = kwargs.get("line_12_noncash_contributions", Decimal("0.00"))
        self.line_13_charity_carryover = kwargs.get("line_13_charity_carryover", Decimal("0.00"))
        self.line_14_total_charity = kwargs.get("line_14_total_charity", Decimal("0.00"))

        self.line_15_casualty_theft_loss = kwargs.get("line_15_casualty_theft_loss", Decimal("0.00"))
        self.line_16_other_itemized_deductions = kwargs.get("line_16_other_itemized_deductions", Decimal("0.00"))
        self.line_17_total_itemized_deductions = kwargs.get("line_17_total_itemized_deductions")
        self.line_18_elect_itemize_surface = kwargs.get("line_18_elect_itemize_surface")

        self.standard_deduction_amount = kwargs.get("standard_deduction_amount")
        self.is_itemizing = kwargs.get("is_itemizing")
        self.is_v1_supported = kwargs.get("is_v1_supported", True)
        self.should_attach_schedule_a = kwargs.get("should_attach_schedule_a", False)
        self.can_file = kwargs.get("can_file", True)

        self.blocking_errors = kwargs.get("blocking_errors", [])
        self.review_warnings = kwargs.get("review_warnings", [])

    def to_dict(self):
        def to_float(val):
            if isinstance(val, Decimal):
                return float(val)
            return val
        return {
            "taxpayer_name": self.taxpayer_name,
            "taxpayer_ssn_masked": self.taxpayer_ssn_masked,
            "tax_year": self.tax_year,
            "filing_status": self.filing_status,
            "line_1_medical_and_dental_expenses": to_float(self.line_1_medical_and_dental_expenses),
            "line_2_agi": to_float(self.line_2_agi),
            "line_3_medical_threshold": to_float(self.line_3_medical_threshold),
            "line_4_deductible_medical_expenses": to_float(self.line_4_deductible_medical_expenses),
            "line_5a_amount": to_float(self.line_5a_amount),
            "line_5a_sales_tax_checkbox": self.line_5a_sales_tax_checkbox,
            "line_5b_real_estate_taxes": to_float(self.line_5b_real_estate_taxes),
            "line_5c_personal_property_taxes": to_float(self.line_5c_personal_property_taxes),
            "line_5d_salt_before_limit": to_float(self.line_5d_salt_before_limit),
            "line_5e_salt_deduction": to_float(self.line_5e_salt_deduction),
            "line_6_other_taxes": to_float(self.line_6_other_taxes),
            "line_7_total_taxes": to_float(self.line_7_total_taxes),
            "line_8_qualifying_proceeds_checkbox": self.line_8_qualifying_proceeds_checkbox,
            "line_8a_home_mortgage_interest": to_float(self.line_8a_home_mortgage_interest),
            "line_8b_non_1098_interest": to_float(self.line_8b_non_1098_interest),
            "line_8c_non_1098_points": to_float(self.line_8c_non_1098_points),
            "line_8e_total_mortgage_interest": to_float(self.line_8e_total_mortgage_interest),
            "line_9_investment_interest": to_float(self.line_9_investment_interest),
            "line_10_total_interest_paid": to_float(self.line_10_total_interest_paid),
            "line_11_cash_contributions": to_float(self.line_11_cash_contributions),
            "line_12_noncash_contributions": to_float(self.line_12_noncash_contributions),
            "line_13_charity_carryover": to_float(self.line_13_charity_carryover),
            "line_14_total_charity": to_float(self.line_14_total_charity),
            "line_15_casualty_theft_loss": to_float(self.line_15_casualty_theft_loss),
            "line_16_other_itemized_deductions": to_float(self.line_16_other_itemized_deductions),
            "line_17_total_itemized_deductions": to_float(self.line_17_total_itemized_deductions),
            "line_18_elect_itemize_surface": self.line_18_elect_itemize_surface,
            "standard_deduction_amount": to_float(self.standard_deduction_amount),
            "is_itemizing": self.is_itemizing,
            "is_v1_supported": self.is_v1_supported,
            "should_attach_schedule_a": self.should_attach_schedule_a,
            "can_file": self.can_file,
            "blocking_errors": [err.to_dict() if hasattr(err, "to_dict") else err for err in self.blocking_errors],
            "review_warnings": [warn.to_dict() if hasattr(warn, "to_dict") else warn for warn in self.review_warnings],
        }

# =====================================================================
# V1 計算與校驗邏輯
# =====================================================================

def validate_identity(inputs: ScheduleAInputsV1, errors: List[ValidationIssue]):
    if not inputs.taxpayer_name.strip():
        errors.append(ValidationIssue("MISSING_TAXPAYER_NAME", "taxpayer_name", message="Taxpayer name is missing."))
    if not inputs.taxpayer_ssn.strip():
        errors.append(ValidationIssue("MISSING_TAXPAYER_SSN", "taxpayer_ssn", message="Taxpayer SSN is missing."))

def validate_tax_year(tax_year: int, allowed: set, errors: List[ValidationIssue]):
    if tax_year not in allowed:
        errors.append(ValidationIssue("UNSUPPORTED_TAX_YEAR", "tax_year", message=f"Tax year {tax_year} is not supported."))

def validate_nonnegative_amounts(inputs: ScheduleAInputsV1, errors: List[ValidationIssue]):
    ZERO = Decimal("0.00")
    if inputs.adjusted_gross_income < ZERO:
        errors.append(ValidationIssue("NEGATIVE_AMOUNT", "adjusted_gross_income", message="Adjusted Gross Income cannot be negative."))
        
    for item in inputs.medical_items:
        if item.taxpayer_paid_amount < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "taxpayer_paid_amount", item.item_id, item.source_document_id, "Taxpayer paid amount cannot be negative."))
        if item.reimbursement_amount < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "reimbursement_amount", item.item_id, item.source_document_id, "Reimbursement amount cannot be negative."))
        if item.tax_free_medical_account_payment < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "tax_free_medical_account_payment", item.item_id, item.source_document_id, "Tax free medical account payment cannot be negative."))
            
    for item in inputs.tax_items:
        if item.amount_paid < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "amount_paid", item.item_id, item.source_document_id, "Amount paid cannot be negative."))
        if item.separately_stated_nondeductible_charge < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "separately_stated_nondeductible_charge", item.item_id, item.source_document_id, "Separately stated nondeductible charge cannot be negative."))
            
    for item in inputs.mortgage_interest_items:
        if item.form_1098_box_1_mortgage_interest < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "form_1098_box_1_mortgage_interest", item.item_id, item.source_document_id, "Mortgage interest cannot be negative."))
        if item.deductible_points_reported_on_1098 < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "deductible_points_reported_on_1098", item.item_id, item.source_document_id, "Mortgage points cannot be negative."))
            
    for item in inputs.cash_charity_items:
        if item.gross_contribution_amount < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "gross_contribution_amount", item.item_id, item.source_document_id, "Gross contribution amount cannot be negative."))
        if item.goods_or_services_value < ZERO:
            errors.append(ValidationIssue("NEGATIVE_AMOUNT", "goods_or_services_value", item.item_id, item.source_document_id, "Goods or services value cannot be negative."))

def detect_unsupported_cases(flags: SpecialCaseFlagsV1, errors: List[ValidationIssue]):
    mapping = {
        "has_marketplace_medical_premium": ("UNSUPPORTED_MARKETPLACE_MEDICAL_PREMIUM", "Marketplace/Form 1095-A/Form 8962 premium is not supported in V1."),
        "has_ltc_premium": ("UNSUPPORTED_LTC_PREMIUM", "LTC insurance premium is not supported in V1."),
        "has_self_employed_health_insurance_overlap": ("UNSUPPORTED_SELF_EMPLOYED_HEALTH_INSURANCE", "Self-employed health insurance deduction coordination is not supported in V1."),
        "has_prior_year_medical_recovery": ("UNSUPPORTED_PRIOR_YEAR_MEDICAL_RECOVERY", "Prior year medical reimbursement/tax benefit rule is not supported in V1."),
        "sales_tax_amount_requires_calculation": ("SALES_TAX_AMOUNT_NOT_RESOLVED", "General sales tax amount requires calculation/tables which is not supported in V1."),
        "has_tax_refund_or_rebate_adjustment": ("UNSUPPORTED_TAX_REFUND_ADJUSTMENT", "Tax refund or rebate adjustment is not supported in V1."),
        "has_other_tax_line_6": ("UNSUPPORTED_OTHER_TAX_LINE_6", "Schedule A Line 6 other taxes are not supported in V1."),
        "has_multiple_mortgages": ("UNSUPPORTED_MULTIPLE_MORTGAGES", "Multiple mortgages or multiple properties are not supported in V1."),
        "mortgage_proceeds_not_all_qualified": ("UNSUPPORTED_MORTGAGE_PROCEEDS_ALLOCATION", "Mortgage proceeds not fully used for buy/build/improve is not supported in V1."),
        "mortgage_limitation_required": ("UNSUPPORTED_MORTGAGE_LIMITATION", "Mortgage principal limit or FMV limit calculation is not supported in V1."),
        "has_shared_mortgage": ("UNSUPPORTED_SHARED_MORTGAGE", "Shared mortgage interest is not supported in V1."),
        "has_non_1098_mortgage_interest": ("UNSUPPORTED_NON_1098_MORTGAGE_INTEREST", "Mortgage interest not reported on Form 1098 is not supported in V1."),
        "has_non_1098_points": ("UNSUPPORTED_NON_1098_POINTS", "Points not reported on Form 1098 is not supported in V1."),
        "has_seller_financed_mortgage": ("UNSUPPORTED_SELLER_FINANCED_MORTGAGE", "Seller-financed mortgage is not supported in V1."),
        "has_form_8396_credit": ("UNSUPPORTED_FORM_8396", "Form 8396 mortgage interest credit is not supported in V1."),
        "has_investment_interest": ("UNSUPPORTED_INVESTMENT_INTEREST", "Investment interest/Form 4952 is not supported in V1."),
        "has_noncash_charity": ("UNSUPPORTED_NONCASH_CHARITY", "Noncash charity/Form 8283 is not supported in V1."),
        "has_charity_carryover": ("UNSUPPORTED_CHARITY_CARRYOVER", "Charitable contribution carryover is not supported in V1."),
        "has_charitable_agi_limitation": ("UNSUPPORTED_CHARITABLE_AGI_LIMITATION", "Charitable AGI limitation calculation is not supported in V1."),
        "has_casualty_or_theft_loss": ("UNSUPPORTED_FORM_4684", "Casualty or theft loss/Form 4684 is not supported in V1."),
        "has_net_qualified_disaster_loss": ("UNSUPPORTED_NET_QUALIFIED_DISASTER_LOSS", "Net qualified disaster loss is not supported in V1."),
        "has_line_16_item": ("UNSUPPORTED_LINE_16_ITEM", "Schedule A Line 16 other itemized deductions are not supported in V1."),
        "has_unresolved_mfs_joint_expense_allocation": ("UNSUPPORTED_MFS_JOINT_EXPENSE_ALLOCATION", "MFS joint expense allocation is not supported in V1.")
    }
    for attr, (code, msg) in mapping.items():
        if getattr(flags, attr, False):
            errors.append(ValidationIssue(code, field=attr, message=msg))

def validate_paid_year(item, errors: List[ValidationIssue]):
    if item.paid_in_tax_year is None:
        errors.append(ValidationIssue(
            "UNKNOWN_PAID_IN_TAX_YEAR",
            field="paid_in_tax_year",
            item_id=item.item_id,
            source_document_id=item.source_document_id,
            message="Payment year is unknown."
        ))

class TaxPools:
    def __init__(self):
        self.income_tax = []
        self.sales_tax = []
        self.real_estate_tax = []
        self.personal_property_tax = []

def classify_tax_items(tax_items: List[TaxPaymentItemV1], errors: List[ValidationIssue], warnings: List[ValidationIssue]) -> TaxPools:
    pools = TaxPools()
    ZERO = Decimal("0.00")
    for item in tax_items:
        validate_paid_year(item, errors)
        
        if item.tax_category == "UNKNOWN":
            errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="tax_category", item_id=item.item_id, source_document_id=item.source_document_id, message="Unknown tax category."))
            continue
            
        if item.tax_category == "FEDERAL_OR_NONDEDUCTIBLE_TAX":
            warnings.append(ValidationIssue("FEDERAL_OR_NONDEDUCTIBLE_TAX_EXCLUDED", field="tax_category", item_id=item.item_id, source_document_id=item.source_document_id, message="Federal or nondeductible tax excluded."))
            continue
            
        if item.tax_category == "BUSINESS_OR_RENTAL_TAX":
            warnings.append(ValidationIssue("BUSINESS_OR_RENTAL_TAX_EXCLUDED", field="tax_category", item_id=item.item_id, source_document_id=item.source_document_id, message="Business or rental tax excluded from Schedule A."))
            continue
            
        if item.separately_stated_nondeductible_charge > item.amount_paid:
            errors.append(ValidationIssue("ADJUSTMENT_EXCEEDS_GROSS_AMOUNT", field="separately_stated_nondeductible_charge", item_id=item.item_id, source_document_id=item.source_document_id, message="Nondeductible charge exceeds amount paid."))
            continue
            
        eligible_amt = item.amount_paid - item.separately_stated_nondeductible_charge
        
        if item.tax_category == "STATE_LOCAL_INCOME_TAX":
            if item.paid_in_tax_year is True:
                pools.income_tax.append(eligible_amt)
        elif item.tax_category == "GENERAL_SALES_TAX":
            if item.paid_in_tax_year is True:
                pools.sales_tax.append(eligible_amt)
        elif item.tax_category == "PERSONAL_REAL_ESTATE_TAX":
            if item.personal_use_confirmed is None:
                errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="personal_use_confirmed", item_id=item.item_id, source_document_id=item.source_document_id, message="Real estate tax personal use confirmation is missing or unknown."))
                continue
            if item.personal_use_confirmed is False:
                warnings.append(ValidationIssue("PERSONAL_USE_NOT_CONFIRMED", field="personal_use_confirmed", item_id=item.item_id, source_document_id=item.source_document_id, message="Real estate is not for personal use; excluded."))
                continue
            if item.actual_paid_to_taxing_authority_confirmed is None or item.actual_paid_to_taxing_authority_confirmed is False:
                # Excluded from deductible pool; specific error is raised at main calculation level
                continue
            if item.personal_use_confirmed is True and item.actual_paid_to_taxing_authority_confirmed is True:
                if item.paid_in_tax_year is True:
                    pools.real_estate_tax.append(eligible_amt)
        elif item.tax_category == "PERSONAL_PROPERTY_TAX":
            if item.personal_use_confirmed is None or item.value_based_and_annual_confirmed is None:
                errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="property_confirmations", item_id=item.item_id, source_document_id=item.source_document_id, message="Personal property tax confirmations are missing or unknown."))
                continue
            if item.personal_use_confirmed is True and item.value_based_and_annual_confirmed is True:
                if item.paid_in_tax_year is True:
                    pools.personal_property_tax.append(eligible_amt)
    return pools

def is_over_65(dob_str: str, tax_year: int) -> bool:
    if not dob_str or not isinstance(dob_str, str):
        return False
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", dob_str.strip())
    if not m:
        return False
    by, bm, bd = int(m.group(1)), int(m.group(2)), int(m.group(3))
    cutoff_year = tax_year - 64
    if by < cutoff_year:
        return True
    if by == cutoff_year and bm == 1 and bd == 1:
        return True
    return False

def calculate_additional_standard_deduction(inputs: ScheduleAInputsV1) -> Decimal:
    ZERO = Decimal("0.00")
    try:
        rates = load_tax_rates(inputs.tax_year)
        std_cfg = rates.get("standard_deduction", {})
    except Exception:
        return ZERO
        
    single_hoh_rate = Decimal(str(std_cfg.get("additional_deduction_single_hoh", 1950.0)))
    joint_mfs_qss_rate = Decimal(str(std_cfg.get("additional_deduction_joint_mfs_qss", 1550.0)))
    
    status = str(inputs.filing_status or "SINGLE").upper()
    is_joint_or_mfs = status in ("MFJ", "MFS", "QSS")
    rate = joint_mfs_qss_rate if is_joint_or_mfs else single_hoh_rate
    
    conditions_count = 0
    if is_over_65(inputs.taxpayer_date_of_birth, inputs.tax_year):
        conditions_count += 1
    if inputs.taxpayer_blind:
        conditions_count += 1
        
    if is_joint_or_mfs:
        if is_over_65(inputs.spouse_date_of_birth, inputs.tax_year):
            conditions_count += 1
        if inputs.spouse_blind:
            conditions_count += 1
            
    return Decimal(conditions_count) * rate

def calculate_salt_limit_v1(tax_year: int, filing_status: str, agi: Decimal, line_5d: Decimal, has_foreign_adjustment: bool, errors: List[ValidationIssue]) -> Decimal:
    if tax_year == 2024:
        cap = Decimal("5000.00") if filing_status == "MFS" else Decimal("10000.00")
        return min(line_5d, cap)
    elif tax_year == 2025:
        floor_2025 = Decimal("5000.00") if filing_status == "MFS" else Decimal("10000.00")
        base_cap_2025 = Decimal("20000.00") if filing_status == "MFS" else Decimal("40000.00")
        
        if line_5d <= floor_2025:
            return line_5d
            
        agi_limit = Decimal("250000.00") if filing_status == "MFS" else Decimal("500000.00")
        if agi <= agi_limit and not has_foreign_adjustment:
            return min(line_5d, base_cap_2025)
        else:
            errors.append(ValidationIssue("UNSUPPORTED_2025_SALT_WORKSHEET", field="line_5e_salt_deduction", message="2025 high-income or foreign-income SALT worksheet is not supported in V1."))
            return None
    else:
        errors.append(ValidationIssue("UNSUPPORTED_TAX_YEAR", field="tax_year", message=f"Tax year {tax_year} is not supported."))
        return None

def calculate_simple_form_1098(mortgage_interest_items: List[MortgageInterestItemV1], errors: List[ValidationIssue]) -> Decimal:
    ZERO = Decimal("0.00")
    if not mortgage_interest_items:
        return ZERO
    if len(mortgage_interest_items) > 1:
        errors.append(ValidationIssue("UNSUPPORTED_MULTIPLE_MORTGAGES", field="mortgage_interest_items", message="Multiple mortgages not supported in V1."))
        return ZERO
        
    item = mortgage_interest_items[0]
    validate_paid_year(item, errors)
    
    if item.simple_mortgage_status == "UNKNOWN":
        errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="simple_mortgage_status", item_id=item.item_id, source_document_id=item.source_document_id, message="Unknown mortgage status."))
        return ZERO
    elif item.simple_mortgage_status == "LIMITATION_OR_WORKSHEET_REQUIRED":
        errors.append(ValidationIssue("UNSUPPORTED_MORTGAGE_LIMITATION", field="simple_mortgage_status", item_id=item.item_id, source_document_id=item.source_document_id, message="Mortgage limitation or worksheet required is not supported in V1."))
        return ZERO
        
    if item.paid_in_tax_year is True:
        return item.form_1098_box_1_mortgage_interest + item.deductible_points_reported_on_1098
    return ZERO

def calculate_cash_charity(cash_charity_items: List[CashCharityItemV1], errors: List[ValidationIssue], warnings: List[ValidationIssue], tax_year: int = 2024) -> Decimal:
    total = Decimal("0.00")
    ZERO = Decimal("0.00")
    for item in cash_charity_items:
        validate_paid_year(item, errors)
        
        if item.qualified_organization_status == "UNKNOWN":
            errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="qualified_organization_status", item_id=item.item_id, source_document_id=item.source_document_id, message="Unknown charity organization qualification status."))
            continue
        elif item.qualified_organization_status == "NOT_QUALIFIED":
            warnings.append(ValidationIssue("CHARITY_ORGANIZATION_NOT_QUALIFIED", field="qualified_organization_status", item_id=item.item_id, source_document_id=item.source_document_id, message="Charity organization is not qualified; excluded."))
            continue
            
        has_date_error = False
        if not item.contribution_date:
            errors.append(ValidationIssue(
                "CHARITY_CONTRIBUTION_DATE_MISSING",
                field="contribution_date",
                item_id=item.item_id,
                source_document_id=item.source_document_id,
                message=f"The contribution record identifies tax year {tax_year} but does not provide the actual contribution date."
            ))
            has_date_error = True
            
        has_ack_error = False
        net_contrib = item.gross_contribution_amount - item.goods_or_services_value
        if net_contrib >= Decimal("250.00"):
            if item.contemporaneous_acknowledgment_received is None or item.contemporaneous_acknowledgment_received is False:
                errors.append(ValidationIssue(
                    "MISSING_250_ACKNOWLEDGMENT",
                    field="contemporaneous_acknowledgment_received",
                    item_id=item.item_id,
                    source_document_id=item.source_document_id,
                    message=f"The ${int(item.gross_contribution_amount):,} contribution record does not state whether goods or services were provided in exchange."
                ))
                has_ack_error = True

        if has_date_error or has_ack_error:
            continue
            
        if item.bank_or_written_record_available is None:
            errors.append(ValidationIssue("UNKNOWN_TAX_CHARACTER", field="bank_or_written_record_available", item_id=item.item_id, source_document_id=item.source_document_id, message="Bank or written record availability is unknown/null."))
            continue
            
        if item.goods_or_services_value > item.gross_contribution_amount:
            errors.append(ValidationIssue("ADJUSTMENT_EXCEEDS_GROSS_AMOUNT", field="goods_or_services_value", item_id=item.item_id, source_document_id=item.source_document_id, message="Goods/services value exceeds gross contribution amount."))
            continue
            
        if item.paid_in_tax_year is True and item.qualified_organization_status == "VERIFIED" and item.bank_or_written_record_available is True:
            total += net_contrib
            
    return total

def any_unsupported_case(flags: SpecialCaseFlagsV1) -> bool:
    unsupported_attributes = [
        "has_marketplace_medical_premium",
        "has_ltc_premium",
        "has_self_employed_health_insurance_overlap",
        "has_prior_year_medical_recovery",
        "sales_tax_amount_requires_calculation",
        "has_tax_refund_or_rebate_adjustment",
        "has_other_tax_line_6",
        "has_multiple_mortgages",
        "mortgage_proceeds_not_all_qualified",
        "mortgage_limitation_required",
        "has_shared_mortgage",
        "has_non_1098_mortgage_interest",
        "has_non_1098_points",
        "has_seller_financed_mortgage",
        "has_form_8396_credit",
        "has_investment_interest",
        "has_noncash_charity",
        "has_charity_carryover",
        "has_charitable_agi_limitation",
        "has_casualty_or_theft_loss",
        "has_net_qualified_disaster_loss",
        "has_line_16_item",
        "has_unresolved_mfs_joint_expense_allocation"
    ]
    for attr in unsupported_attributes:
        if getattr(flags, attr, False):
            return True
    return False

def calculate_schedule_a_v1(inputs: ScheduleAInputsV1) -> ScheduleAResultV1:
    errors = []
    warnings = []
    ZERO = Decimal("0.00")
    MEDICAL_RATE = Decimal("0.075")

    # 1. 校驗基本與阻斷規則
    validate_identity(inputs, errors)
    validate_tax_year(inputs.tax_year, allowed={2024, 2025}, errors=errors)
    validate_nonnegative_amounts(inputs, errors)
    detect_unsupported_cases(inputs.special_case_flags, errors)

    # 2. Medical Expense (Lines 1-4)
    medical_total = ZERO
    for item in inputs.medical_items:
        validate_paid_year(item, errors)

        if item.medical_qualification_status == "UNKNOWN":
            errors.append(ValidationIssue("UNKNOWN_MEDICAL_QUALIFICATION", field="medical_qualification_status", item_id=item.item_id, source_document_id=item.source_document_id, message="Unknown medical qualification status."))
            continue

        if item.eligible_person_status == "UNKNOWN":
            errors.append(ValidationIssue("UNKNOWN_MEDICAL_PERSON_ELIGIBILITY", field="eligible_person_status", item_id=item.item_id, source_document_id=item.source_document_id, message="Unknown medical eligible person status."))
            continue

        if (
            item.medical_qualification_status == "NOT_DEDUCTIBLE"
            or item.eligible_person_status == "NOT_ELIGIBLE"
            or item.paid_in_tax_year is False
        ):
            warnings.append(ValidationIssue("MEDICAL_ITEM_EXCLUDED", field="medical_items", item_id=item.item_id, source_document_id=item.source_document_id, message=f"Medical item {item.item_id} excluded."))
            continue

        adjustments = item.reimbursement_amount + item.tax_free_medical_account_payment

        if adjustments > item.taxpayer_paid_amount:
            errors.append(ValidationIssue("ADJUSTMENT_EXCEEDS_GROSS_AMOUNT", field="reimbursement_amount", item_id=item.item_id, source_document_id=item.source_document_id, message="Medical reimbursement and HSA/FSA offset exceeds gross taxpayer paid amount."))
            continue

        medical_total += item.taxpayer_paid_amount - adjustments

    line_1 = medical_total
    line_2 = inputs.adjusted_gross_income
    line_3 = (line_2 * MEDICAL_RATE).quantize(Decimal("0.01"))
    line_4 = max(ZERO, line_1 - line_3)

    # 3. Taxes Paid (Lines 5-7)
    tax_pools = classify_tax_items(inputs.tax_items, errors=errors, warnings=warnings)

    if inputs.line_5a_election == "INCOME_TAX":
        line_5a = sum_decimal(tax_pools.income_tax)
        sales_tax_checkbox = False
    elif inputs.line_5a_election == "GENERAL_SALES_TAX":
        line_5a = sum_decimal(tax_pools.sales_tax)
        sales_tax_checkbox = True
    elif inputs.line_5a_election is None:
        line_5a = ZERO
        sales_tax_checkbox = False
        # Do not block if no tax paid items are present, but if we have taxes we need an election.
        if tax_pools.income_tax or tax_pools.sales_tax:
            errors.append(ValidationIssue("TAX_ELECTION_MISSING", field="line_5a_election", message="Tax election (income tax vs sales tax) is missing."))
    else:
        line_5a = ZERO
        sales_tax_checkbox = False
        errors.append(ValidationIssue("TAX_ELECTION_MISSING", field="line_5a_election", message="Invalid tax election value."))

    has_unconfirmed_real_estate_tax = False
    for item in inputs.tax_items:
        if item.tax_category == "PERSONAL_REAL_ESTATE_TAX" and item.actual_paid_to_taxing_authority_confirmed is not True:
            has_unconfirmed_real_estate_tax = True
            errors.append(ValidationIssue(
                "REAL_ESTATE_TAX_PAYMENT_NOT_CONFIRMED",
                field="line_5b_real_estate_taxes",
                item_id=item.item_id,
                source_document_id=item.source_document_id,
                message=f"The source reports an escrow amount but does not confirm the amount actually paid to the taxing authority during {inputs.tax_year}."
            ))

    line_5b_val = sum_decimal(tax_pools.real_estate_tax)
    line_5b = None if has_unconfirmed_real_estate_tax else line_5b_val
    line_5c = sum_decimal(tax_pools.personal_property_tax)
    line_5d = line_5a + line_5b_val + line_5c

    line_5e = calculate_salt_limit_v1(
        tax_year=inputs.tax_year,
        filing_status=inputs.filing_status,
        agi=inputs.adjusted_gross_income,
        line_5d=line_5d,
        has_foreign_adjustment=inputs.special_case_flags.has_form_2555_or_4563_or_puerto_rico_exclusion,
        errors=errors
    )

    line_6 = ZERO
    line_7 = None if line_5e is None else line_5e + line_6

    # 4. Interest Paid (Lines 8-10)
    line_8a = calculate_simple_form_1098(inputs.mortgage_interest_items, errors=errors)
    line_8b = ZERO
    line_8c = ZERO
    line_8e = line_8a + line_8b + line_8c
    line_9 = ZERO
    line_10 = line_8e + line_9

    # 5. Charitable Contributions (Lines 11-14)
    line_11 = calculate_cash_charity(inputs.cash_charity_items, errors=errors, warnings=warnings, tax_year=inputs.tax_year)
    line_12 = ZERO
    line_13 = ZERO
    line_14 = line_11 + line_12 + line_13

    # 6. Casualty and Theft Losses & Other Itemized Deductions (Lines 15-16)
    line_15 = ZERO
    line_16 = ZERO

    # 7. Total Itemized Deductions (Line 17)
    if line_7 is None:
        line_17 = None
    else:
        line_17 = line_4 + line_7 + line_10 + line_14 + line_15 + line_16

    is_v1_supported = not any_unsupported_case(inputs.special_case_flags)
    can_file = is_v1_supported and len(errors) == 0 and line_17 is not None

    standard_amount = inputs.standard_deduction_reference.standard_deduction_amount
    if standard_amount is not None:
        standard_amount = Decimal(str(standard_amount)) + calculate_additional_standard_deduction(inputs)
        
    if standard_amount is None or line_17 is None:
        is_itemizing = None
        if standard_amount is None:
            errors.append(ValidationIssue("STANDARD_DEDUCTION_REFERENCE_MISSING", field="standard_deduction_amount", message="Standard deduction amount is missing."))
    else:
        is_itemizing = (
            inputs.standard_deduction_reference.must_itemize_due_to_mfs_spouse is True
            or inputs.standard_deduction_reference.elect_itemize_even_if_less is True
            or line_17 > standard_amount
        )

    should_attach = can_file and (is_itemizing is True)

    line_18_surface = None
    if inputs.tax_year == 2025:
        line_18_surface = inputs.standard_deduction_reference.elect_itemize_even_if_less is True

    # Mask SSN
    raw_ssn = str(inputs.taxpayer_ssn or "")
    if len(raw_ssn) >= 4:
        ssn_masked = f"***-**-{raw_ssn[-4:]}"
    else:
        ssn_masked = "***-**-XXXX"

    return ScheduleAResultV1(
        taxpayer_name=inputs.taxpayer_name,
        taxpayer_ssn_masked=ssn_masked,
        tax_year=inputs.tax_year,
        filing_status=inputs.filing_status,
        line_1_medical_and_dental_expenses=line_1,
        line_2_agi=line_2,
        line_3_medical_threshold=line_3,
        line_4_deductible_medical_expenses=line_4,
        line_5a_amount=line_5a,
        line_5a_sales_tax_checkbox=sales_tax_checkbox,
        line_5b_real_estate_taxes=line_5b,
        line_5c_personal_property_taxes=line_5c,
        line_5d_salt_before_limit=line_5d,
        line_5e_salt_deduction=line_5e,
        line_6_other_taxes=line_6,
        line_7_total_taxes=line_7,
        line_8_qualifying_proceeds_checkbox=False,
        line_8a_home_mortgage_interest=line_8a,
        line_8b_non_1098_interest=line_8b,
        line_8c_non_1098_points=line_8c,
        line_8e_total_mortgage_interest=line_8e,
        line_9_investment_interest=line_9,
        line_10_total_interest_paid=line_10,
        line_11_cash_contributions=line_11,
        line_12_noncash_contributions=line_12,
        line_13_charity_carryover=line_13,
        line_14_total_charity=line_14,
        line_15_casualty_theft_loss=line_15,
        line_16_other_itemized_deductions=line_16,
        line_17_total_itemized_deductions=line_17,
        line_18_elect_itemize_surface=line_18_surface,
        standard_deduction_amount=standard_amount,
        is_itemizing=is_itemizing,
        is_v1_supported=is_v1_supported,
        should_attach_schedule_a=should_attach,
        can_file=can_file,
        blocking_errors=errors,
        review_warnings=warnings
    )

# =====================================================================
# 相容性轉換層 (calculate_schedule_a_dynamic)
# =====================================================================

def dict_to_v1_inputs(inputs_dict: Dict[str, Any]) -> ScheduleAInputsV1:
    taxpayer_name = inputs_dict.get("taxpayer_name") or ""
    taxpayer_ssn = inputs_dict.get("taxpayer_ssn") or inputs_dict.get("ssn") or ""
    tax_year = int(inputs_dict.get("tax_year") or 2025)
    filing_status = str(inputs_dict.get("filing_status") or "SINGLE").upper()
    adjusted_gross_income = Decimal(str(inputs_dict.get("adjusted_gross_income") or inputs_dict.get("agi") or "0.00"))
    
    medical_items = []
    raw_med = inputs_dict.get("medical_items") or inputs_dict.get("medical_expense_items") or []
    for idx, m in enumerate(raw_med):
        if not isinstance(m, dict):
            continue
        item_id = str(m.get("item_id") or f"med_{idx}")
        paid_amt = Decimal(str(m.get("taxpayer_paid_amount") or m.get("patient_paid_amount") or "0.00"))
        reimb = Decimal(str(m.get("reimbursement_amount") or m.get("reimbursement_received") or "0.00"))
        
        hsa_fsa = Decimal(str(m.get("tax_free_medical_account_payment") or 
                              m.get("paid_by_hsa_msa_fsa_hra_cafeteria_plan_amount") or 
                              m.get("paid_by_hsa_msa_fsa_hra_cafeteria_plan") or 
                              m.get("paid_by_hsa_msa_fsa_cafeteria_plan_amount") or 
                              m.get("paid_by_hsa_msa_fsa_cafeteria_plan") or "0.00"))
        
        paid_in_year = m.get("paid_in_tax_year")
        if paid_in_year is None:
            date_str = str(m.get("expense_paid_date") or "")
            if date_str:
                paid_in_year = date_str.startswith(str(tax_year))
            else:
                paid_in_year = True
                
        person = str(m.get("expense_person") or m.get("eligible_person_status") or "UNKNOWN").upper()
        if person in ("TAXPAYER", "SPOUSE", "DEPENDENT"):
            person_status = "ELIGIBLE"
        elif person == "NOT_ELIGIBLE":
            person_status = "NOT_ELIGIBLE"
        elif person == "ELIGIBLE":
            person_status = "ELIGIBLE"
        else:
            person_status = "UNKNOWN"
            
        cat = str(m.get("expense_category") or m.get("medical_qualification_status") or "UNKNOWN").upper()
        if cat in ("MEDICAL", "DENTAL", "PRESCRIPTION_DRUGS", "OTHER_ELIGIBLE_MEDICAL_EXPENSE", 
                   "MEDICAL_INSURANCE", "MEDICAL_INSURANCE_PREMIUM", "DENTAL_INSURANCE_PREMIUM", 
                   "VISION_INSURANCE_PREMIUM", "QUALIFIED_SIMPLE"):
            qual_status = "QUALIFIED_SIMPLE"
        elif cat == "NOT_DEDUCTIBLE":
            qual_status = "NOT_DEDUCTIBLE"
        else:
            qual_status = "UNKNOWN"
            
        medical_items.append(MedicalExpenseItemV1(
            item_id=item_id,
            source_document_id=m.get("source_document_id") or m.get("source_document_reference"),
            description=m.get("description") or m.get("raw_description"),
            paid_in_tax_year=paid_in_year,
            taxpayer_paid_amount=paid_amt,
            reimbursement_amount=reimb,
            tax_free_medical_account_payment=hsa_fsa,
            eligible_person_status=person_status,
            medical_qualification_status=qual_status
        ))

    tax_items = []
    raw_tax = inputs_dict.get("tax_items") or inputs_dict.get("tax_payment_items") or []
    for idx, t in enumerate(raw_tax):
        if not isinstance(t, dict):
            continue
        item_id = str(t.get("item_id") or f"tax_{idx}")
        amt = Decimal(str(t.get("amount_paid") or "0.00"))
        
        sep_charge = Decimal(str(t.get("separately_stated_nondeductible_charge") or "0.00"))
        if "separately_stated_service_charge" in t or "separately_stated_improvement_assessment" in t:
            sep_charge += Decimal(str(t.get("separately_stated_service_charge") or "0.00"))
            sep_charge += Decimal(str(t.get("separately_stated_improvement_assessment") or "0.00"))
            
        paid_in_year = t.get("paid_in_tax_year")
        if paid_in_year is None:
            date_str = str(t.get("tax_paid_date") or "")
            if date_str:
                paid_in_year = date_str.startswith(str(tax_year))
            else:
                paid_in_year = True
                
        raw_cat = str(t.get("tax_category") or t.get("raw_tax_category_hint") or t.get("schedule_a_line_target") or "UNKNOWN").upper()
        if raw_cat in ("STATE_LOCAL_INCOME_TAX", "5A_INCOME_TAX", "STATE_INCOME_TAX", "LOCAL_INCOME_TAX"):
            cat = "STATE_LOCAL_INCOME_TAX"
        elif raw_cat in ("GENERAL_SALES_TAX", "5A_GENERAL_SALES_TAX"):
            cat = "GENERAL_SALES_TAX"
        elif raw_cat in ("PERSONAL_REAL_ESTATE_TAX", "5B_REAL_ESTATE_TAX", "REAL_ESTATE_TAX", "PROPERTY_TAX"):
            cat = "PERSONAL_REAL_ESTATE_TAX"
        elif raw_cat in ("PERSONAL_PROPERTY_TAX", "5C_PERSONAL_PROPERTY_TAX", "VEHICLE_VALUE_BASED_TAX"):
            cat = "PERSONAL_PROPERTY_TAX"
        elif raw_cat in ("FEDERAL_TAX", "FEDERAL_INCOME_TAX", "SOCIAL_SECURITY_TAX", "MEDICARE_TAX", "FEDERAL_OR_NONDEDUCTIBLE_TAX"):
            cat = "FEDERAL_OR_NONDEDUCTIBLE_TAX"
        elif raw_cat in ("BUSINESS_OR_RENTAL_TAX", "BUSINESS_TAX", "RENTAL_TAX"):
            cat = "BUSINESS_OR_RENTAL_TAX"
        else:
            cat = "UNKNOWN"
            
        pers_use = t.get("personal_use_confirmed")
        if pers_use is None:
            pers_use = t.get("tax_scope") == "personal" if "tax_scope" in t else True
            
        paid_authority = t.get("actual_paid_to_taxing_authority_confirmed")
        if paid_authority is None:
            desc_lower = (t.get("description") or "").lower()
            doc_id_lower = (t.get("source_document_id") or t.get("source_document_reference") or "").lower()
            if "escrow" in desc_lower or "1098" in desc_lower or "1098" in doc_id_lower:
                paid_authority = False
            else:
                paid_authority = True
            
        val_based = t.get("value_based_and_annual_confirmed")
        if val_based is None:
            val_based = True
            
        tax_items.append(TaxPaymentItemV1(
            item_id=item_id,
            source_document_id=t.get("source_document_id") or t.get("source_document_reference"),
            description=t.get("description") or t.get("raw_description") or t.get("tax_name"),
            paid_in_tax_year=paid_in_year,
            amount_paid=amt,
            separately_stated_nondeductible_charge=sep_charge,
            tax_category=cat,
            personal_use_confirmed=pers_use,
            actual_paid_to_taxing_authority_confirmed=paid_authority,
            value_based_and_annual_confirmed=val_based
        ))

    line_5a_elect = inputs_dict.get("line_5a_election")
    if line_5a_elect is None:
        use_sales = inputs_dict.get("use_sales_tax_instead_of_income_tax") or inputs_dict.get("use_sales_tax_instead")
        if use_sales is True:
            line_5a_elect = "GENERAL_SALES_TAX"
        elif use_sales is False:
            line_5a_elect = "INCOME_TAX"

    mortgage_interest_items = []
    raw_mort = inputs_dict.get("mortgage_interest_items") or []
    if not raw_mort and ("home_mortgage_interest_1098" in inputs_dict or "points_reported_on_1098" in inputs_dict):
        box1 = Decimal(str(inputs_dict.get("home_mortgage_interest_1098") or "0.00"))
        pts = Decimal(str(inputs_dict.get("points_reported_on_1098") or "0.00"))
        mortgage_interest_items.append(MortgageInterestItemV1(
            item_id="mortgage_1",
            form_1098_box_1_mortgage_interest=box1,
            deductible_points_reported_on_1098=pts,
            paid_in_tax_year=True,
            simple_mortgage_status="CONFIRMED_SIMPLE"
        ))
    else:
        for idx, mo in enumerate(raw_mort):
            if not isinstance(mo, dict):
                continue
            item_id = str(mo.get("item_id") or f"mort_{idx}")
            paid_in_year = mo.get("paid_in_tax_year")
            if paid_in_year is None:
                paid_in_year = True
            status = mo.get("simple_mortgage_status") or "CONFIRMED_SIMPLE"
            
            mortgage_interest_items.append(MortgageInterestItemV1(
                item_id=item_id,
                source_document_id=mo.get("source_document_id"),
                lender_name=mo.get("lender_name"),
                source_document_type=mo.get("source_document_type", "FORM_1098"),
                form_1098_box_1_mortgage_interest=Decimal(str(mo.get("form_1098_box_1_mortgage_interest") or "0.00")),
                deductible_points_reported_on_1098=Decimal(str(mo.get("deductible_points_reported_on_1098") or "0.00")),
                paid_in_tax_year=paid_in_year,
                simple_mortgage_status=status
            ))

    cash_charity_items = []
    raw_charity = inputs_dict.get("cash_charity_items") or []
    if not raw_charity and "cash_charitable_contributions" in inputs_dict:
        amt = Decimal(str(inputs_dict.get("cash_charitable_contributions") or "0.00"))
        cash_charity_items.append(CashCharityItemV1(
            item_id="charity_1",
            gross_contribution_amount=amt,
            paid_in_tax_year=True,
            qualified_organization_status="VERIFIED",
            bank_or_written_record_available=True,
            contemporaneous_acknowledgment_received=True
        ))
    else:
        for idx, ch in enumerate(raw_charity):
            if not isinstance(ch, dict):
                continue
            item_id = str(ch.get("item_id") or f"charity_{idx}")
            paid_in_year = ch.get("paid_in_tax_year")
            if paid_in_year is None:
                paid_in_year = True
            org_status = ch.get("qualified_organization_status") or "VERIFIED"
            
            cash_charity_items.append(CashCharityItemV1(
                item_id=item_id,
                source_document_id=ch.get("source_document_id"),
                contribution_date=ch.get("contribution_date"),
                paid_in_tax_year=paid_in_year,
                organization_name=ch.get("organization_name"),
                qualified_organization_status=org_status,
                contribution_method=ch.get("contribution_method", "CASH"),
                gross_contribution_amount=Decimal(str(ch.get("gross_contribution_amount") or "0.00")),
                goods_or_services_value=Decimal(str(ch.get("goods_or_services_value") or "0.00")),
                bank_or_written_record_available=ch.get("bank_or_written_record_available"),
                contemporaneous_acknowledgment_received=ch.get("contemporaneous_acknowledgment_received")
            ))

    std_ref = inputs_dict.get("standard_deduction_reference")
    std_ded_amt = None
    if isinstance(std_ref, dict):
        std_ded_amt = std_ref.get("standard_deduction_amount")
    if std_ded_amt is None:
        std_ded_amt = inputs_dict.get("standard_deduction_amount")
        
    try:
        is_invalid_amt = std_ded_amt is None or float(std_ded_amt) <= 0.0
    except (ValueError, TypeError):
        is_invalid_amt = True

    if not isinstance(std_ref, dict) or not std_ref or is_invalid_amt:
        if is_invalid_amt:
            try:
                rates = load_tax_rates(tax_year)
                std_cfg = rates.get("standard_deduction", {})
                std_ded_amt = std_cfg.get(filing_status)
            except Exception:
                std_ded_amt = 15000.0
                
        spouse_itemizes = False
        elect_itemize = False
        if isinstance(std_ref, dict):
            spouse_itemizes = std_ref.get("must_itemize_due_to_mfs_spouse") or std_ref.get("spouse_itemizes_on_separate_return") or False
            elect_itemize = std_ref.get("elect_itemize_even_if_less") or std_ref.get("elect_itemize_even_if_less_than_standard") or False
        else:
            spouse_itemizes = inputs_dict.get("spouse_itemizes_on_separate_return") or False
            elect_itemize = inputs_dict.get("elect_itemize_even_if_less_than_standard") or False
            
        std_ref = {
            "standard_deduction_amount": std_ded_amt,
            "must_itemize_due_to_mfs_spouse": spouse_itemizes,
            "elect_itemize_even_if_less": elect_itemize
        }
    
    raw_flags = inputs_dict.get("special_case_flags")
    if not isinstance(raw_flags, dict):
        raw_flags = {}
        if inputs_dict.get("requires_form_8962_for_marketplace_premiums") is True:
            raw_flags["has_marketplace_medical_premium"] = True
            
        for m in inputs_dict.get("medical_expense_items") or []:
            if isinstance(m, dict):
                cat = str(m.get("expense_category") or "").lower()
                if "marketplace" in cat or m.get("covered_by_ptc_or_aptc") is True:
                    raw_flags["has_marketplace_medical_premium"] = True
                if "ltc" in cat or cat == "qualified_ltc_insurance_premium":
                    raw_flags["has_ltc_premium"] = True
                    
        if inputs_dict.get("noncash_charitable_contributions", 0.0) > 0.0:
            raw_flags["has_noncash_charity"] = True
        if inputs_dict.get("charitable_carryover", 0.0) > 0.0:
            raw_flags["has_charity_carryover"] = True

    flags = SpecialCaseFlagsV1(
        has_marketplace_medical_premium=bool(raw_flags.get("has_marketplace_medical_premium", False)),
        has_ltc_premium=bool(raw_flags.get("has_ltc_premium", False)),
        has_self_employed_health_insurance_overlap=bool(raw_flags.get("has_self_employed_health_insurance_overlap", False)),
        has_prior_year_medical_recovery=bool(raw_flags.get("has_prior_year_medical_recovery", False)),
        sales_tax_amount_requires_calculation=bool(raw_flags.get("sales_tax_amount_requires_calculation", False)),
        has_tax_refund_or_rebate_adjustment=bool(raw_flags.get("has_tax_refund_or_rebate_adjustment", False)),
        has_form_2555_or_4563_or_puerto_rico_exclusion=bool(raw_flags.get("has_form_2555_or_4563_or_puerto_rico_exclusion", False)),
        has_other_tax_line_6=bool(raw_flags.get("has_other_tax_line_6", False)),
        has_multiple_mortgages=bool(raw_flags.get("has_multiple_mortgages", False)),
        mortgage_proceeds_not_all_qualified=bool(raw_flags.get("mortgage_proceeds_not_all_qualified", False)),
        mortgage_limitation_required=bool(raw_flags.get("mortgage_limitation_required", False)),
        has_shared_mortgage=bool(raw_flags.get("has_shared_mortgage", False)),
        has_non_1098_mortgage_interest=bool(raw_flags.get("has_non_1098_mortgage_interest", False)),
        has_non_1098_points=bool(raw_flags.get("has_non_1098_points", False)),
        has_seller_financed_mortgage=bool(raw_flags.get("has_seller_financed_mortgage", False)),
        has_form_8396_credit=bool(raw_flags.get("has_form_8396_credit", False)),
        has_investment_interest=bool(raw_flags.get("has_investment_interest", False)),
        has_noncash_charity=bool(raw_flags.get("has_noncash_charity", False)),
        has_charity_carryover=bool(raw_flags.get("has_charity_carryover", False)),
        has_charitable_agi_limitation=bool(raw_flags.get("has_charitable_agi_limitation", False)),
        has_casualty_or_theft_loss=bool(raw_flags.get("has_casualty_or_theft_loss", False)),
        has_net_qualified_disaster_loss=bool(raw_flags.get("has_net_qualified_disaster_loss", False)),
        has_line_16_item=bool(raw_flags.get("has_line_16_item", False)),
        has_unresolved_mfs_joint_expense_allocation=bool(raw_flags.get("has_unresolved_mfs_joint_expense_allocation", False))
    )

    raw_facts = inputs_dict.get("facts") or []
    if raw_facts:
        medical_groups = {}
        for f in raw_facts:
            ftype = f.get("fact_type")
            fname = f.get("source_filename") or "unknown_medical"
            if ftype in ("qualified_medical_expense_paid", "medical_reimbursement", "medical_tax_free_account_payment"):
                if fname not in medical_groups:
                    medical_groups[fname] = []
                medical_groups[fname].append(f)
                
        for fname, flist in medical_groups.items():
            paid_amt = Decimal("0.00")
            reimb_amt = Decimal("0.00")
            hsa_fsa = Decimal("0.00")
            needs_rev = False
            for f in flist:
                ftype = f.get("fact_type")
                amt = Decimal(str(f.get("amount") or "0.00"))
                if ftype == "qualified_medical_expense_paid":
                    paid_amt += amt
                elif ftype == "medical_reimbursement":
                    reimb_amt += amt
                elif ftype == "medical_tax_free_account_payment":
                    hsa_fsa += amt
                if f.get("needs_review") is True:
                    needs_rev = True
                    
            medical_items.append(MedicalExpenseItemV1(
                item_id=f"med_{fname}",
                source_document_id=fname,
                description=f"Medical expenses from {fname}",
                paid_in_tax_year=True,
                taxpayer_paid_amount=paid_amt,
                reimbursement_amount=reimb_amt,
                tax_free_medical_account_payment=hsa_fsa,
                eligible_person_status="UNKNOWN" if needs_rev else "ELIGIBLE",
                medical_qualification_status="UNKNOWN" if needs_rev else "QUALIFIED_SIMPLE"
            ))

        tax_fact_count = 0
        mortgage_groups = {}
        for f in raw_facts:
            ftype = f.get("fact_type")
            amt = Decimal(str(f.get("amount") or "0.00"))
            fname = f.get("source_filename") or "unknown_doc"
            needs_rev = f.get("needs_review") is True
            
            if ftype == "state_local_income_tax_paid":
                tax_items.append(TaxPaymentItemV1(
                    item_id=f"tax_{tax_fact_count}",
                    source_document_id=fname,
                    description=f"State/local income tax from {fname}",
                    paid_in_tax_year=True,
                    amount_paid=amt,
                    tax_category="STATE_LOCAL_INCOME_TAX",
                    personal_use_confirmed=True,
                    actual_paid_to_taxing_authority_confirmed=True
                ))
                tax_fact_count += 1
            elif ftype == "general_sales_tax_amount":
                tax_items.append(TaxPaymentItemV1(
                    item_id=f"tax_{tax_fact_count}",
                    source_document_id=fname,
                    description=f"General sales tax from {fname}",
                    paid_in_tax_year=True,
                    amount_paid=amt,
                    tax_category="GENERAL_SALES_TAX",
                    personal_use_confirmed=True,
                    actual_paid_to_taxing_authority_confirmed=True
                ))
                tax_fact_count += 1
            elif ftype == "personal_real_estate_tax_paid":
                tax_items.append(TaxPaymentItemV1(
                    item_id=f"tax_{tax_fact_count}",
                    source_document_id=fname,
                    description=f"Real estate tax from {fname}",
                    paid_in_tax_year=True,
                    amount_paid=amt,
                    tax_category="PERSONAL_REAL_ESTATE_TAX",
                    personal_use_confirmed=None if needs_rev else True,
                    actual_paid_to_taxing_authority_confirmed=None if needs_rev else True
                ))
                tax_fact_count += 1
            elif ftype == "personal_property_tax_paid":
                tax_items.append(TaxPaymentItemV1(
                    item_id=f"tax_{tax_fact_count}",
                    source_document_id=fname,
                    description=f"Personal property tax from {fname}",
                    paid_in_tax_year=True,
                    amount_paid=amt,
                    tax_category="PERSONAL_PROPERTY_TAX",
                    personal_use_confirmed=None if needs_rev else True,
                    value_based_and_annual_confirmed=None if needs_rev else True
                ))
                tax_fact_count += 1
            elif ftype in ("mortgage_interest_reported_on_1098", "points_reported_on_1098"):
                if fname not in mortgage_groups:
                    mortgage_groups[fname] = []
                mortgage_groups[fname].append(f)
            elif ftype == "cash_charitable_contribution":
                cash_charity_items.append(CashCharityItemV1(
                    item_id=f"charity_{len(cash_charity_items)}",
                    source_document_id=fname,
                    contribution_date=f.get("date"),
                    paid_in_tax_year=True,
                    organization_name=f.get("payee"),
                    qualified_organization_status="UNKNOWN" if needs_rev else "VERIFIED",
                    gross_contribution_amount=amt,
                    goods_or_services_value=Decimal("0.00"),
                    bank_or_written_record_available=None if needs_rev else True,
                    contemporaneous_acknowledgment_received=None if needs_rev else True
                ))
            elif ftype == "marketplace_health_insurance_premium":
                flags.has_marketplace_medical_premium = True
            elif ftype in ("ltc_premium", "qualified_ltc_insurance_premium"):
                flags.has_ltc_premium = True
            elif ftype == "noncash_charitable_contribution":
                flags.has_noncash_charity = True
            elif ftype == "charity_carryover":
                flags.has_charity_carryover = True
            elif ftype == "casualty_loss":
                flags.has_casualty_or_theft_loss = True
            elif ftype == "investment_interest_paid":
                flags.has_investment_interest = True
                
        if len(mortgage_groups) > 1:
            flags.has_multiple_mortgages = True
        for fname, flist in mortgage_groups.items():
            box1 = Decimal("0.00")
            pts = Decimal("0.00")
            needs_rev = False
            for f in flist:
                ftype = f.get("fact_type")
                amt = Decimal(str(f.get("amount") or "0.00"))
                if ftype == "mortgage_interest_reported_on_1098":
                    box1 += amt
                elif ftype == "points_reported_on_1098":
                    pts += amt
                if f.get("needs_review") is True:
                    needs_rev = True
            mortgage_interest_items.append(MortgageInterestItemV1(
                item_id=f"mort_{fname}",
                source_document_id=fname,
                lender_name=flist[0].get("payee") or "Lender",
                form_1098_box_1_mortgage_interest=box1,
                deductible_points_reported_on_1098=pts,
                paid_in_tax_year=True,
                simple_mortgage_status="UNKNOWN" if needs_rev else "CONFIRMED_SIMPLE"
            ))

    taxpayer_date_of_birth = inputs_dict.get("taxpayer_date_of_birth")
    taxpayer_blind = bool(inputs_dict.get("taxpayer_blind") or False)
    spouse_date_of_birth = inputs_dict.get("spouse_date_of_birth")
    spouse_blind = bool(inputs_dict.get("spouse_blind") or False)

    return ScheduleAInputsV1(
        taxpayer_name=taxpayer_name,
        taxpayer_ssn=taxpayer_ssn,
        taxpayer_date_of_birth=taxpayer_date_of_birth,
        taxpayer_blind=taxpayer_blind,
        spouse_date_of_birth=spouse_date_of_birth,
        spouse_blind=spouse_blind,
        tax_year=tax_year,
        filing_status=filing_status,
        adjusted_gross_income=adjusted_gross_income,
        medical_items=medical_items,
        tax_items=tax_items,
        line_5a_election=line_5a_elect,
        mortgage_interest_items=mortgage_interest_items,
        cash_charity_items=cash_charity_items,
        standard_deduction_reference=std_ref,
        special_case_flags=flags
    )

def calculate_schedule_a_dynamic(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """主動態執行接口，將傳入字典轉為 V1 結構並執行 Python 確定性計算，保證相容性。"""
    v1_inputs = dict_to_v1_inputs(inputs)
    res = calculate_schedule_a_v1(v1_inputs)
    res_dict = res.to_dict()
    
    # 建立舊版 Schema / UI 對應的扁平欄位映射
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
        "agi": res.line_2_agi
    }
    
    for old_k, val in compat_mapping.items():
        if isinstance(val, Decimal):
            res_dict[old_k] = float(val)
        else:
            res_dict[old_k] = val
            
    if res.is_itemizing is True:
        res_dict["final_deduction_used"] = float(res.line_17_total_itemized_deductions) if res.line_17_total_itemized_deductions is not None else 0.0
    elif res.is_itemizing is False:
        res_dict["final_deduction_used"] = float(res.standard_deduction_amount) if res.standard_deduction_amount is not None else 0.0
    else:
        res_dict["final_deduction_used"] = 0.0
        
    has_charity_pending = any(
        isinstance(err, dict) and err.get("code") in ("MISSING_250_ACKNOWLEDGMENT", "CHARITY_CONTRIBUTION_DATE_MISSING")
        for err in res_dict.get("blocking_errors", [])
    )
    if has_charity_pending:
        res_dict["line_11_cash_contributions_status"] = "excluded_pending_documentation"
        
    return res_dict
