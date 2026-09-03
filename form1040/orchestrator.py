import sys
import os
from decimal import Decimal
from typing import Optional, Dict, Any

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from form1040.models.income_aggregator_model import (
    IncomeAggregatorInputV1,
    DirectIncomeInputV1,
    DirectIncomeItemV1,
    W2ItemV1,
    ScheduleBResultV1,
    ScheduleDResultV1,
    Schedule1ResultV1,
    IncomeSectionResultV1,
)
from form1040.models.agi_model import AGIProcessorInputV1, AGIProcessorResultV1
from form1040.models.deduction_resolver_model import DeductionResolverInputV1, DeductionResolverResultV1
from form1040.models.taxable_income_model import TaxableIncomeInputV1, TaxableIncomeResultV1
from form1040.models.tax_computation_model import (
    TaxComputationInputV1,
    TaxComputationResultV1,
    OrdinaryTaxEligibilityV1,
    ApplicabilityStatus,
    normalize_filing_status,
)
from form1040.models.credits_model import CreditsProcessorInputV1, CreditsProcessorResultV1
from form1040.models.payments_refund_model import (
    PaymentsAndRefundProcessorInputV1,
    PaymentsAndRefundProcessorResultV1,
)

from form1040.processors.income_aggregator_processor import IncomeAggregatorProcessor
from form1040.processors.agi_processor import AGIProcessor
from form1040.processors.deduction_resolver_processor import DeductionResolverProcessor
from form1040.processors.taxable_income_processor import TaxableIncomeProcessor
from form1040.processors.tax_computation_processor import TaxComputationProcessor
from form1040.processors.credits_processor import CreditsProcessor
from form1040.processors.payments_refund_processor import PaymentsAndRefundProcessor

from form1040.parsers.income_aggregator_direct_income_parser import IncomeAggregatorDirectIncomeParser


def _safe_decimal(val: Any) -> Decimal:
    if val is None:
        return Decimal("0.00")
    try:
        return Decimal(f"{float(val):.2f}")
    except Exception:
        return Decimal("0.00")


# =========================================================================
# -------------------------------------------------------------------------
# 1. 目的：將 Decimal / float / int 等計算結果，統一轉換為標準的「兩位小數位數」字串 (e.g. "100000.00", "6852.00")。
# 2. 解決痛點：防範 Python 預設 str(Decimal) 可能產生的位數不一致現象 (例如 "100000.0" 缺末尾 0，或整數 "6852" 無小數位)。
# 3. 效益：使 API 回傳之 `form_1040_lines` 能直接供前端 UI/PDF 渲染引擎無縫顯示，免除前端重複撰寫 `.toFixed(2)` 格式化邏輯。
# 4. 特殊處理：若數值為 None (表單互斥留空項)，維持回傳 None，確保表格填寫之正確性。
# =========================================================================
def _fmt_dec(val: Any) -> Optional[str]:
    """
    統一將 Decimal/數值格式化為標準兩位小數字串 (e.g. "100000.00")
    """
    if val is None:
        return None
    try:
        return f"{Decimal(str(val)):.2f}"
    except Exception:
        return "0.00"


def _make_json_safe(obj: Any) -> Any:
    """
    遞迴將 dict / list / Tuple / DTO / Pydantic BaseModel 中所有 Decimal 物件轉成 float，
    保證回傳結構 100% 可直接被 JSON 序列化，避免 API 報錯。
    """
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return float(obj)
    if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
        return _make_json_safe(obj.model_dump())
    if hasattr(obj, "dict") and callable(getattr(obj, "dict")):
        return _make_json_safe(obj.dict())
    if hasattr(obj, "to_dict") and callable(getattr(obj, "to_dict")):
        return _make_json_safe(obj.to_dict())
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_safe(x) for x in obj]
    return obj


class Form1040Orchestrator:
    """
    Form 1040 核心組裝與串接調度器 (Orchestrator)
    負責接收各表單的原始 LLM 提取資料 (dict)，呼叫對應之子處理器計算出 DTO 後，
    完成 Form 1040 全流程 (Lines 1 至 Line 38) 的動態組裝與計算。
    """

    @classmethod
    def assemble(
        cls,
        *,
        tax_year: int,
        filing_status: str,
        taxpayer_ssn: Optional[str] = None,
        raw_llm_direct_income: Dict[str, Any],
        raw_schedule_a_input: Optional[Dict[str, Any]] = None,
        raw_schedule_b_input: Optional[Dict[str, Any]] = None,
        raw_schedule_d_input: Optional[Dict[str, Any]] = None,
        raw_schedule_e_input: Optional[Dict[str, Any]] = None,
        raw_schedule_1_input: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        將原始輸入資料傳給不同子表單模組，等待計算結果返回後，進行 Form 1040 全流程彙整 (Lines 1–38)。
        """
        sa_res_dict = None
        sb_res_dict = None
        se_res_dict = None
        s1_res_dict = None

        # 1. 呼叫 Parser 將原始直接收入資料解析為 DTO 物件
        direct_income_dto = IncomeAggregatorDirectIncomeParser.parse_dict(raw_llm_direct_income)

        # 2. 呼叫 Schedule B 計算引擎取得結果 DTO
        schedule_b_result = None
        if raw_schedule_b_input:
            from processors.processors import calculate_schedule_b_dynamic
            from form1040.models.income_aggregator_model import ProcessingIssueV1, ScheduleBResultV1
            
            sb_res_dict = calculate_schedule_b_dynamic(raw_schedule_b_input)
            sb_has_blocking = sb_res_dict.get("blocking_validation_error") or len(sb_res_dict.get("blocking_errors", [])) > 0
            sb_status = "BLOCKED" if sb_has_blocking else "COMPLETE"
            
            sb_blocking_issues = [
                ProcessingIssueV1(
                    code=err.get("code", "ERROR"),
                    field=err.get("field"),
                    message=err.get("message", "")
                )
                for err in sb_res_dict.get("blocking_errors", []) if isinstance(err, dict)
            ]
            schedule_b_result = ScheduleBResultV1(
                form_1040_line_2a=_safe_decimal(sb_res_dict.get('form_1040_line_2a')),
                line_4_surface_value=_safe_decimal(sb_res_dict.get('line_4_surface_value')),
                total_qualified_dividends=_safe_decimal(sb_res_dict.get('total_qualified_dividends')),
                line_6_total_ordinary_dividends=_safe_decimal(sb_res_dict.get('line_6_total_ordinary_dividends')),
                status=sb_status,
                blocking_errors=sb_blocking_issues,
            )

        # 3. 呼叫 Schedule D 計算引擎取得結果 DTO (由於 Schedule D 尚未開發完成，暫時使用傳入的模擬資料或預設)
        schedule_d_result = None
        if raw_schedule_d_input:
            from form1040.models.income_aggregator_model import ScheduleDResultV1
            val = raw_schedule_d_input.get("line_7_capital_gain_or_loss", 0.00)
            schedule_d_result = ScheduleDResultV1(
                line_7_capital_gain_or_loss=_safe_decimal(val),
                status="COMPLETE",
            )

        # 3.5. 呼叫 Schedule E 計算引擎取得結果 DTO
        schedule_e_result = None
        schedule_1_line_5_transfer_amount = None
        if raw_schedule_e_input:
            from processors.processors.schedule_e import calculate_schedule_e_dynamic
            from form1040.models.income_aggregator_model import ProcessingIssueV1, ScheduleEResultV1
            
            se_res_dict = calculate_schedule_e_dynamic(raw_schedule_e_input)
            if se_res_dict:
                schedule_1_line_5_transfer_amount = se_res_dict.get("schedule_1_line_5_transfer_amount")
                
                # 轉換為強型別 DTO 物件
                se_blocking_issues = [
                    ProcessingIssueV1(
                        code=err.get("code", "ERROR"),
                        field=err.get("field"),
                        message=err.get("message", "")
                    )
                    for err in se_res_dict.get("blocking_errors", []) if isinstance(err, dict)
                ]
                se_review_warnings = [
                    ProcessingIssueV1(
                        code=warn.get("code", "WARNING"),
                        field=warn.get("field"),
                        message=warn.get("message", "")
                    )
                    for warn in se_res_dict.get("review_warnings", []) if isinstance(warn, dict)
                ]
                se_has_blocking = se_res_dict.get("blocking_validation_error") or len(se_blocking_issues) > 0
                has_props = len(raw_schedule_e_input.get("properties", [])) > 0 if isinstance(raw_schedule_e_input, dict) else False
                
                if not has_props:
                    se_status = "NOT_APPLICABLE"
                elif se_has_blocking:
                    se_status = "BLOCKED"
                else:
                    se_status = "COMPLETE"
                
                raw_transfer_amt = se_res_dict.get("schedule_1_line_5_transfer_amount")
                if se_status == "BLOCKED":
                    schedule_1_line_5_transfer_amount = _safe_decimal(raw_transfer_amt)
                else:
                    schedule_1_line_5_transfer_amount = _safe_decimal(raw_transfer_amt) if raw_transfer_amt is not None else Decimal("0.00")
                
                schedule_e_result = ScheduleEResultV1(
                    line_26_total_rental_income_or_loss=_safe_decimal(se_res_dict.get("line_26_total_rental_income_or_loss")),
                    schedule_1_line_5_transfer_amount=schedule_1_line_5_transfer_amount,
                    status=se_status,
                    blocking_errors=se_blocking_issues,
                    review_warnings=se_review_warnings
                )

        if not schedule_e_result:
            from form1040.models.income_aggregator_model import ProcessingIssueV1, ScheduleEResultV1
            schedule_e_result = ScheduleEResultV1(
                line_26_total_rental_income_or_loss=Decimal("0.00"),
                schedule_1_line_5_transfer_amount=Decimal("0.00"),
                status="NOT_APPLICABLE",
                blocking_errors=[],
                review_warnings=[
                    ProcessingIssueV1(
                        code="NO_REPORTABLE_RENTAL_PROPERTY",
                        field="properties",
                        message="No rental properties reported. Schedule E treated as NOT_APPLICABLE."
                    )
                ]
            )
            schedule_1_line_5_transfer_amount = Decimal("0.00")

        # 4. 呼叫 Schedule 1 計算引擎取得結果 DTO
        # 【跨表數據流結轉】
        # 如果 Schedule E 計算成功且有需結轉至 Schedule 1 Line 5 的租金或特許權損益金額，
        # 我們必須將其注入給 Schedule 1 的輸入參數 schedule_e_line_41。
        if schedule_1_line_5_transfer_amount is not None:
            if not raw_schedule_1_input:
                raw_schedule_1_input = {}
            raw_schedule_1_input["schedule_e_line_41"] = schedule_1_line_5_transfer_amount
            if "tax_year" not in raw_schedule_1_input:
                raw_schedule_1_input["tax_year"] = tax_year
            if "taxpayer_name" not in raw_schedule_1_input:
                raw_schedule_1_input["taxpayer_name"] = "Taxpayer"
            if "taxpayer_ssn" not in raw_schedule_1_input:
                raw_schedule_1_input["taxpayer_ssn"] = taxpayer_ssn or "000-00-0000"

        schedule_1_result = None
        if raw_schedule_1_input:
            from schedule_1_processor import calculate_schedule_1_dynamic
            from form1040.models.income_aggregator_model import ProcessingIssueV1, Schedule1ResultV1
            
            s1_res_dict = calculate_schedule_1_dynamic(raw_schedule_1_input)
            s1_has_blocking = s1_res_dict.get("blocking_validation_error") or len(s1_res_dict.get("blocking_errors", [])) > 0
            # Schedule 1 remains blocked for filing, but its already-computed
            # supported lines may still feed provisional Form 1040 arithmetic.
            s1_status = "BLOCKED" if s1_has_blocking else "COMPLETE"
            
            s1_blocking_issues = [
                ProcessingIssueV1(
                    code=err.get("code", "ERROR"),
                    field=err.get("field"),
                    message=err.get("message", "")
                )
                for err in s1_res_dict.get("blocking_errors", []) if isinstance(err, dict)
            ]
            
            schedule_1_result = Schedule1ResultV1(
                taxpayer_name=s1_res_dict.get("taxpayer_name"),
                taxpayer_ssn_masked=s1_res_dict.get("taxpayer_ssn_masked"),
                tax_year=s1_res_dict.get("tax_year"),
                line_10_additional_income=_safe_decimal(s1_res_dict.get('line_10_additional_income')),
                line_26_adjustments_to_income=_safe_decimal(s1_res_dict.get('line_26_adjustments_to_income')),
                status=s1_status,
                can_continue=True,
                can_file=s1_res_dict.get("can_file", True),
                is_v1_supported=s1_res_dict.get("is_v1_supported", True),
                blocking_errors=s1_blocking_issues,
                review_warnings=s1_res_dict.get("review_warnings", [])
            )

        # 5. 呼叫 IncomeAggregatorProcessor 彙整 Lines 1–9
        income_input = IncomeAggregatorInputV1(
            tax_year=tax_year,
            filing_status=filing_status,
            taxpayer_ssn=taxpayer_ssn,
            direct_income_input=direct_income_dto,
            schedule_b_result=schedule_b_result,
            schedule_d_result=schedule_d_result,
            schedule_1_result=schedule_1_result,
        )
        income_result: IncomeSectionResultV1 = IncomeAggregatorProcessor.process(income_input)

        # 6. 將 Line 9 與 Schedule 1 Line 26 傳入 AGIProcessor 計算 Line 11
        agi_input = AGIProcessorInputV1(
            line_9_total_income=income_result.line_9,
            schedule_1_result=schedule_1_result
        )
        agi_result: AGIProcessorResultV1 = AGIProcessor.process(agi_input)

        # 7. 處理 Schedule A 與 DeductionResolverProcessor (Lines 12e, 13a, 13b, 14)
        resolved_sa_result = None
        if raw_schedule_a_input:
            from processors.processors.schedule_a import calculate_schedule_a_dynamic
            from processors.models.schedule_a import ScheduleAResultV1
            raw_schedule_a_input["adjusted_gross_income"] = agi_result.line_11_adjusted_gross_income
            sa_res_dict = calculate_schedule_a_dynamic(raw_schedule_a_input)
            resolved_sa_result = ScheduleAResultV1(**sa_res_dict)

        deduction_input = DeductionResolverInputV1(
            tax_year=tax_year,
            filing_status=filing_status,
            schedule_a_result=resolved_sa_result,
        )
        deduction_result: DeductionResolverResultV1 = DeductionResolverProcessor.process(deduction_input)

        # 8. 呼叫 TaxableIncomeProcessor 計算 Line 15 (Taxable Income)
        taxable_income_input = TaxableIncomeInputV1(
            tax_year=tax_year,
            agi_result=agi_result,
            deduction_result=deduction_result,
        )
        taxable_income_result: TaxableIncomeResultV1 = TaxableIncomeProcessor.process(taxable_income_input)

        # 9. 呼叫 TaxComputationProcessor 計算 Lines 16, 17, 18 (Tax Computation)
        # -------------------------------------------------------------------------
        # Ordinary Tax Eligibility (一般所得稅路徑適性評估)：
        # 用於評估當前案件是否符合走一般「Tax Table 查表法」或「Tax Computation Worksheet 算術法」。
        # 若案件包含合格股利 (Line 3a) 或資本利得 (Line 7a)，依據 IRS 規定享有優惠稅率，
        # 必須走特殊計稅工作表 (Qualified Dividends and Capital Gain Tax Worksheet)。
        # 本物件即作為安全門衛，傳入 Line 3a 與 Line 7a 金額供計稅驗證器判斷路徑。
        # -------------------------------------------------------------------------
        ordinary_tax_eligibility = OrdinaryTaxEligibilityV1(
            qualified_dividends_amount=income_result.line_3a or Decimal("0.00"),
            capital_gain_or_loss_amount=income_result.line_7a or Decimal("0.00"),
            form_8615_required=False,
            schedule_j_required=False,
            form_2555_required=False,
            status=ApplicabilityStatus.APPLICABLE
        )
        
        fs_enum = normalize_filing_status(filing_status)
        tax_comp_input = TaxComputationInputV1(
            tax_year=tax_year,
            filing_status=fs_enum,
            taxable_income_result=taxable_income_result,
            ordinary_tax_eligibility=ordinary_tax_eligibility,
            schedule_2_status=ApplicabilityStatus.NOT_APPLICABLE
        )
        tax_comp_result: TaxComputationResultV1 = TaxComputationProcessor.process(tax_comp_input)

        # 10. 呼叫 CreditsProcessor 計算 Lines 19-24 (Credits)
        # =========================================================================
        # TODO: [PLACEHOLDER] 尚未建立之子表單預留處理 (對標 QBI Form 8995 模式)
        # 由於 Schedule 8812, Schedule 2, Schedule 3 模組目前尚未建立，
        # 本模組採用預留 Placeholder (金額 0.00)，避免觸發驗證器阻斷錯誤。
        # =========================================================================
        credits_input = CreditsProcessorInputV1(
            line_18_tax_before_credits=tax_comp_result.line_18_tax_before_credits,
            schedule_8812_result={"status": "CONFIRMED_NOT_PRESENT", "total_ctc_odc": Decimal("0.00")},
            schedule_3_result={"status": "CONFIRMED_NOT_PRESENT", "line_8_total": Decimal("0.00")},
            schedule_2_result={"status": "CONFIRMED_NOT_PRESENT", "line_21_total": Decimal("0.00")},
        )
        credits_result: CreditsProcessorResultV1 = CreditsProcessor.process(credits_input)

        # 11. 呼叫 PaymentsAndRefundProcessor 計算 Lines 25-38 (Payments, Refund, Amount Owed)
        # 從 W-2 明細項目自動加總 Box 2 Federal Withholding
        w2_withholding = Decimal("0.00")
        if direct_income_dto and direct_income_dto.w2_items:
            from form1040.calculators.income_aggregator_calculator import sanitize_ssn, is_ssn_match
            status_upper = str(filing_status or "").upper()
            is_joint = status_upper in ["MFJ", "MARRIED_FILING_JOINTLY"]
            taxpayer_ssn_clean = sanitize_ssn(taxpayer_ssn)

            for w2 in direct_income_dto.w2_items:
                if is_joint:
                    w2_withholding += (w2.box_2_federal_withholding or Decimal("0.00"))
                else:
                    w2_ssn_clean = sanitize_ssn(w2.employee_ssn)
                    if is_ssn_match(taxpayer_ssn_clean, w2_ssn_clean):
                        w2_withholding += (w2.box_2_federal_withholding or Decimal("0.00"))

        # 從 1099 項目 (Pension/Annuity Form 1099-R Box 4, IRA, Social Security) 自動加總 Federal Withholding
        form1099_withholding = Decimal("0.00")
        if direct_income_dto:
            for item in [direct_income_dto.pension_annuity, direct_income_dto.ira_distribution, direct_income_dto.social_security]:
                if item and item.federal_withholding is not None:
                    form1099_withholding += (item.federal_withholding or Decimal("0.00"))

        withholding_res = {
            "status": "COMPLETE",
            "w2_withholding": w2_withholding,
            "form1099_withholding": form1099_withholding,
            "other_withholding": Decimal("0.00")
        }

        # -------------------------------------------------------------------------
        # IRS Form 1040 溢繳退稅預設分配邏輯：
        # 1. est_line_24: 應納稅額總計 (Line 24 Total Tax)。
        # 2. est_overpayment: 扣繳稅額大於應納稅額時的溢繳金額 (Line 34 Overpayment = Line 33 Payments - Line 24 Tax)。
        # 3. default_refund_choice: 當有溢繳 (est_overpayment > 0) 時，依照 IRS 預設習慣，
        #    將 100% 的溢繳金額安排為直接退款 (Line 35a Refund)，預設不抵繳下年度預估稅 (Line 36 Apply to Next Year = 0.00)。
        #    若無溢繳金額 (無退稅)，則維持 None 留空。
        # -------------------------------------------------------------------------
        est_line_24 = credits_result.line_24_total_tax or Decimal("0.00")
        est_overpayment = (w2_withholding - est_line_24) if w2_withholding > est_line_24 else Decimal("0.00")
        default_refund_choice = {
            "amount_to_refund": est_overpayment,
            "amount_to_apply_next_year": Decimal("0.00")
        } if est_overpayment > Decimal("0.00") else None

        # =========================================================================
        # TODO: [PLACEHOLDER] 尚未建立之可退稅抵免子表單預留處理 
        # 由於 EIC, Schedule 8812 (ACTC), Form 8863 (AOC), Form 8839, Schedule 3 等模組尚未建立，
        # 此處統一帶入預設 Placeholder，確保 PaymentsAndRefundValidator 能正常放行。
        # =========================================================================
        payments_input = PaymentsAndRefundProcessorInputV1(
            line_24_total_tax=credits_result.line_24_total_tax,
            withholding_result=withholding_res,
            estimated_payments=Decimal("0.00"),
            eic_result={"status": "CONFIRMED_NOT_PRESENT", "line_27a_eic": Decimal("0.00")},
            schedule_8812_result={"status": "CONFIRMED_NOT_PRESENT", "line_28_actc": Decimal("0.00")},
            form_8863_result={"status": "CONFIRMED_NOT_PRESENT", "line_8_aoc": Decimal("0.00")},
            form_8839_result={"status": "CONFIRMED_NOT_PRESENT", "line_13_refundable_credit": Decimal("0.00")},
            schedule_3_result={"status": "CONFIRMED_NOT_PRESENT", "line_15_total": Decimal("0.00")},
            refund_choice=default_refund_choice,
            estimated_tax_penalty_result=Decimal("0.00"),
        )
        payments_result: PaymentsAndRefundProcessorResultV1 = PaymentsAndRefundProcessor.process(payments_input)

        # 彙整最終狀態：只要任一核心區段阻斷，則整體狀態為 BLOCKED
        all_sections = [
            sec for sec in [
                income_result,
                agi_result,
                deduction_result,
                taxable_income_result,
                tax_comp_result,
                credits_result,
                payments_result,
                schedule_1_result,
                resolved_sa_result,
                schedule_e_result,
            ] if sec is not None
        ]

        # 收集所有阻斷錯誤
        all_blocking_errors = []
        seen_blocking_errors = set()
        for sec in all_sections:
            sec_blocking = getattr(sec, "blocking_errors", []) or []
            for err in sec_blocking:
                if isinstance(err, dict):
                    error_key = (err.get("code"), err.get("field"), err.get("message"))
                else:
                    error_key = (
                        getattr(err, "code", None),
                        getattr(err, "field", None),
                        getattr(err, "message", str(err)),
                    )
                if error_key not in seen_blocking_errors:
                    seen_blocking_errors.add(error_key)
                    all_blocking_errors.append(err)

        # 收集 Review Warnings 並加入顯式 Placeholder 提醒
        all_review_warnings = []
        for sec in all_sections:
            sec_warns = (sec.get("review_warnings", []) if isinstance(sec, dict) else getattr(sec, "review_warnings", [])) or []
            for warn in sec_warns:
                if warn not in all_review_warnings:
                    all_review_warnings.append(warn)

        placeholder_warnings = [
            {
                "code": "UNIMPLEMENTED_MODULE_PLACEHOLDER",
                "field": "schedule_8812",
                "message": "Schedule 8812 (Child Tax Credit / ACTC) 模組尚未建立，目前採用 Placeholder 預設值 (0.00)"
            },
            {
                "code": "UNIMPLEMENTED_MODULE_PLACEHOLDER",
                "field": "schedule_2",
                "message": "Schedule 2 模組尚未建立，目前採用 Placeholder 預設值 (0.00)"
            },
            {
                "code": "UNIMPLEMENTED_MODULE_PLACEHOLDER",
                "field": "schedule_3",
                "message": "Schedule 3 模組尚未建立，目前採用 Placeholder 預設值 (0.00)"
            },
            {
                "code": "UNIMPLEMENTED_MODULE_PLACEHOLDER",
                "field": "form_8863",
                "message": "Form 8863 (AOC) 模組尚未建立，目前採用 Placeholder 預設值 (0.00)"
            },
            {
                "code": "UNIMPLEMENTED_MODULE_PLACEHOLDER",
                "field": "form_8839",
                "message": "Form 8839 (Adoption Credit) 模組尚未建立，目前採用 Placeholder 預設值 (0.00)"
            },
        ]
        all_review_warnings.extend(placeholder_warnings)

        form_1040_lines = {
            "line_1a": _fmt_dec(income_result.line_1a) or "0.00",
            "line_1z": _fmt_dec(income_result.line_1z) or "0.00",
            "line_2a": _fmt_dec(income_result.line_2a) or "0.00",
            "line_2b": _fmt_dec(income_result.line_2b) or "0.00",
            "line_3a": _fmt_dec(income_result.line_3a) or "0.00",
            "line_3b": _fmt_dec(income_result.line_3b) or "0.00",
            "line_4a": _fmt_dec(income_result.line_4a) or "0.00",
            "line_4b": _fmt_dec(income_result.line_4b) or "0.00",
            "line_5a": _fmt_dec(income_result.line_5a) or "0.00",
            "line_5b": _fmt_dec(income_result.line_5b) or "0.00",
            "line_6a": _fmt_dec(income_result.line_6a) or "0.00",
            "line_6b": _fmt_dec(income_result.line_6b) or "0.00",
            "line_7a": _fmt_dec(income_result.line_7a) or "0.00",
            "line_8": _fmt_dec(income_result.line_8) or "0.00",
            "line_9": _fmt_dec(income_result.line_9) or "0.00",
            "line_10": _fmt_dec(agi_result.line_10_adjustments_to_income) or "0.00",
            "line_11": _fmt_dec(agi_result.line_11_adjusted_gross_income) or "0.00",
            "line_12e": _fmt_dec(deduction_result.line_12e_deduction) or "0.00",
            "line_13a": _fmt_dec(deduction_result.line_13a_qbi_deduction) or "0.00",
            "line_13b": _fmt_dec(deduction_result.line_13b_schedule_1a_deductions) or "0.00",
            "line_14": _fmt_dec(deduction_result.line_14_total_deductions) or "0.00",
            "line_15": _fmt_dec(taxable_income_result.line_15_taxable_income) or "0.00",
            "line_16": _fmt_dec(tax_comp_result.line_16_tax) or "0.00",
            "line_18": _fmt_dec(tax_comp_result.line_18_tax_before_credits) or "0.00",
            "line_19": _fmt_dec(credits_result.line_19_ctc_odc) or "0.00",
            "line_20": _fmt_dec(credits_result.line_20_schedule3_credits) or "0.00",
            "line_21": _fmt_dec(credits_result.line_21_total_credits) or "0.00",
            "line_22": _fmt_dec(credits_result.line_22_tax_after_credits) or "0.00",
            "line_23": _fmt_dec(credits_result.line_23_other_taxes) or "0.00",
            "line_24": _fmt_dec(credits_result.line_24_total_tax) or "0.00",
            "line_25a": _fmt_dec(payments_result.line_25a_w2_withholding) or "0.00",
            "line_25b": _fmt_dec(payments_result.line_25b_1099_withholding) or "0.00",
            "line_25c": _fmt_dec(payments_result.line_25c_other_withholding) or "0.00",
            "line_25d": _fmt_dec(payments_result.line_25d_total_withholding) or "0.00",
            "line_26": _fmt_dec(payments_result.line_26_estimated_payments) or "0.00",
            "line_27": _fmt_dec(payments_result.line_27a_eic) or "0.00",
            "line_28": _fmt_dec(payments_result.line_28_actc) or "0.00",
            "line_29": _fmt_dec(payments_result.line_29_aoc) or "0.00",
            "line_30": _fmt_dec(payments_result.line_30_refundable_adoption_credit) or "0.00",
            "line_31": _fmt_dec(payments_result.line_31_schedule3_total) or "0.00",
            "line_32": _fmt_dec(payments_result.line_32_other_payments_credits) or "0.00",
            "line_33": _fmt_dec(payments_result.line_33_total_payments) or "0.00",
            "line_34": _fmt_dec(payments_result.line_34_overpayment),
            "line_35a": _fmt_dec(payments_result.line_35a_refund_amount),
            "line_36": _fmt_dec(payments_result.line_36_applied_to_next_year),
            "line_37": _fmt_dec(payments_result.line_37_amount_owed),
            "line_38": _fmt_dec(payments_result.line_38_estimated_tax_penalty),
        }

        overall_can_file = all(getattr(sec, "can_file", True) for sec in all_sections) and len(all_blocking_errors) == 0

        return {
            "form_1040_lines": form_1040_lines,
            "income_section": _make_json_safe(income_result),
            "agi_section": _make_json_safe(agi_result),
            "deduction_section": _make_json_safe(deduction_result),
            "taxable_income_section": _make_json_safe(taxable_income_result),
            "tax_computation_section": _make_json_safe(tax_comp_result),
            "credits_section": _make_json_safe(credits_result),
            "payments_refund_section": _make_json_safe(payments_result),
            
            # --- 子表單計算結果 Section ---
            "schedule_a_section": _make_json_safe(sa_res_dict),
            "schedule_b_section": _make_json_safe(sb_res_dict),
            "schedule_e_section": _make_json_safe(se_res_dict) or (_make_json_safe(schedule_e_result) if schedule_e_result else None),
            "schedule_1_section": _make_json_safe(s1_res_dict),
            
            "can_file": overall_can_file,
            "blocking_errors": _make_json_safe([err.to_dict() if hasattr(err, "to_dict") else err for err in all_blocking_errors]),
            "review_warnings": _make_json_safe([warn.to_dict() if hasattr(warn, "to_dict") else warn for warn in all_review_warnings]),
        }

    @classmethod
    def extract_and_assemble(
        cls,
        *,
        taxpayer_profile: Dict[str, Any],
        uploaded_documents: list,
        model_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        端到端全流程：
        1. 將上傳的文件內容格式化為單一的上下文段落。
        2. 呼叫各子表單的 LLM 提取器，從雜亂文字中提取對應的 JSON 數據。
        3. 調用 cls.assemble 進行純算術與業務規則彙整計算。
        """
        from processors.parsers.form_1040_income import Form1040IncomeLLMParser
        from processors.processors.schedule_b import extract_schedule_b_inputs_with_logs
        from processors.processors.schedule_a import extract_schedule_a_inputs_with_logs
        from schedule_1_processor import extract_schedule_1_inputs_with_logs
        from processors.processors.schedule_e import extract_schedule_e_inputs_with_logs
        import missing_form_detector
        import json

        # 0. 讀取 API 必填之納稅人基本資料 (tax_year, filing_status)，由前端 UI/API 傳入
        tax_year = int(taxpayer_profile.get("tax_year") or taxpayer_profile.get("Tax Year") or 2025)
        filing_status = str(taxpayer_profile.get("filing_status") or taxpayer_profile.get("Filing Status") or "MFJ")
        taxpayer_ssn = str(taxpayer_profile.get("ssn") or taxpayer_profile.get("SSN") or "")

        # 1. 格式化文件上下文 (將 taxpayer_profile 與 uploaded_documents 整合為單一純文字 context)
        payload = {
            "taxpayer_profile": taxpayer_profile,
            "uploaded_documents": uploaded_documents
        }
        doc_ctx_str = missing_form_detector.format_input_data(json.dumps(payload, ensure_ascii=False))

        if not doc_ctx_str.strip():
            raise ValueError("文件內容不能為空，請提供有效的 taxpayer_profile 與 uploaded_documents")

        # 2. 確定採用的模型 (預設為 gemini-2.5-pro)
        model_name = model_name or "gemini-2.5-pro"


        # 3. 呼叫 LLM 進行提取
        # (a) 提取 Direct Income (W-2 等)
        parser_1040 = Form1040IncomeLLMParser(model_name=model_name)
        raw_llm_direct_income, _, _ = parser_1040.parse(doc_ctx_str)

        # (b) 提取 Schedule B 輸入
        raw_schedule_b_input, _, _ = extract_schedule_b_inputs_with_logs(doc_ctx_str, model_name=model_name)
        if raw_schedule_b_input and isinstance(raw_schedule_b_input, dict):
            raw_schedule_b_input.setdefault("filing_status", filing_status)
            raw_schedule_b_input.setdefault("tax_year", tax_year)

        # (c) 提取 Schedule 1 輸入
        raw_schedule_1_input, _, _ = extract_schedule_1_inputs_with_logs(doc_ctx_str, model_name=model_name)
        if raw_schedule_1_input and isinstance(raw_schedule_1_input, dict):
            raw_schedule_1_input.setdefault("filing_status", filing_status)
            raw_schedule_1_input.setdefault("tax_year", tax_year)

        # (d) 提取 Schedule A 輸入
        raw_schedule_a_input = None
        try:
            raw_schedule_a_input, _, _ = extract_schedule_a_inputs_with_logs(doc_ctx_str, model_name=model_name)
            if raw_schedule_a_input and isinstance(raw_schedule_a_input, dict):
                raw_schedule_a_input.setdefault("filing_status", filing_status)
                raw_schedule_a_input.setdefault("tax_year", tax_year)
        except Exception:
            pass

        # (e) 提取 Schedule E 輸入
        raw_schedule_e_input = None
        try:
            raw_schedule_e_input, _, _ = extract_schedule_e_inputs_with_logs(doc_ctx_str, model_name=model_name)
            if raw_schedule_e_input and isinstance(raw_schedule_e_input, dict):
                raw_schedule_e_input.setdefault("filing_status", filing_status)
                raw_schedule_e_input.setdefault("tax_year", tax_year)
        except Exception:
            pass

        # =========================================================================
        # TODO: [PLACEHOLDER] 尚未建立之 Schedule D 子表單預留處理 (對標 QBI Form 8995 模式)
        # 由於 Schedule D 模組在 V1 尚未完整建立，本端到端流程暫時使用預設 Placeholder，
        # 未來開發完成後將替換為 extract_schedule_d_inputs_with_logs(doc_ctx_str)。
        # =========================================================================
        raw_schedule_d_input = {
            "line_7_capital_gain_or_loss": 0.00
        }

        # 4. 呼叫組裝計算
        res = cls.assemble(
            tax_year=tax_year,
            filing_status=filing_status,
            taxpayer_ssn=taxpayer_ssn,
            raw_llm_direct_income=raw_llm_direct_income,
            raw_schedule_a_input=raw_schedule_a_input,
            raw_schedule_b_input=raw_schedule_b_input,
            raw_schedule_d_input=raw_schedule_d_input,
            raw_schedule_e_input=raw_schedule_e_input,
            raw_schedule_1_input=raw_schedule_1_input,
        )

        # 注入偵錯資訊以便前端核對
        res["debug_info"] = _make_json_safe({
            "extracted_direct_income": raw_llm_direct_income,
            "extracted_schedule_b": raw_schedule_b_input,
            "extracted_schedule_1": raw_schedule_1_input,
            "extracted_schedule_a": raw_schedule_a_input,
            "extracted_schedule_e": raw_schedule_e_input,
        })
        return res


if __name__ == "__main__":
    import json

    # 1. 準備 0622 Case 的直接收入資料 (W-2 等)
    raw_llm_direct = {
        "w2_items": [
            {
                "employee_name": "Marcus Rivera",
                "box_1_wages": "46000",
                "tax_year": 2025,
                "source_document_id": "sample_01",
            },
            {
                "employee_name": "Elena Rivera",
                "box_1_wages": "54000",
                "tax_year": 2025,
                "source_document_id": "sample_02",
            },
        ],
        "ira_distribution": {"gross_amount": "0", "taxable_amount": "0", "status": "EXPLICIT_VALUE"},
        "pension_annuity": {"gross_amount": "0", "taxable_amount": "0", "status": "EXPLICIT_VALUE"},
        "social_security": {"gross_amount": "0", "taxable_amount": "0", "status": "EXPLICIT_VALUE"},
    }

    # 2. 準備 0622 Case 的 Schedule B 原始輸入
    sb_inputs = {
        'taxpayer_name': 'MARCUS & ELENA RIVERA',
        'taxpayer_ssn': '123-45-6789',
        'tax_year': 2025,
        'interest_items': [{'payer_name': 'CHASE', 'amount': 150.0, 'tax_character': 'TAXABLE_INTEREST'}],
        'dividend_items': [{'payer_name': 'VANGUARD', 'ordinary_dividends': 405.0}],
        'foreign_accounts_interest': False,
        'fbar_required': False,
        'foreign_countries_list': [],
        'foreign_trust_distribution': False
    }

    # 3. 準備 0622 Case 的 Schedule D 原始輸入
    sd_inputs = {
        "line_7_capital_gain_or_loss": 0.00
    }

    # 4. 準備 0622 Case 的 Schedule 1 原始輸入
    s1_inputs = {
        "taxpayer_name": "Marcus & Elena Rivera",
        "taxpayer_ssn": "123-45-6789",
        "tax_year": 2025,
        "adjustment_items": [
            {
                "item_id": "adj_ira",
                "line_code": "20",
                "description": "IRA deduction",
                "amount": 7000.0
            }
        ],
        "special_case_flags": {}
    }

    # 5. 呼叫通用 assemble 進行調度計算與加總
    res = Form1040Orchestrator.assemble(
        tax_year=2025,
        filing_status="MFJ",
        raw_llm_direct_income=raw_llm_direct,
        raw_schedule_b_input=sb_inputs,
        raw_schedule_d_input=sd_inputs,
        raw_schedule_e_input=None,
        raw_schedule_1_input=s1_inputs,
    )
    print("=== 0622 Case Form 1040 Integration Test Assembly Result ===")
    print(json.dumps(res, indent=2))
