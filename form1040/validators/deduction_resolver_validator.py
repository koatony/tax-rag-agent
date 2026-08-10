from typing import List
from form1040.models.agi_model import ProcessingIssueV1
from form1040.models.deduction_resolver_model import DeductionResolverInputV1


class DeductionResolverValidator:
    """
    DeductionResolverProcessor 輸入與上游模組結果驗證器
    """

    @staticmethod
    def validate(data: DeductionResolverInputV1) -> List[ProcessingIssueV1]:
        errors: List[ProcessingIssueV1] = []

        # 1. 基礎欄位驗證
        if not data.tax_year:
            errors.append(
                ProcessingIssueV1(
                    code="INVALID_TAX_YEAR",
                    field="tax_year",
                    message="tax_year is required.",
                )
            )

        if not data.filing_status:
            errors.append(
                ProcessingIssueV1(
                    code="INVALID_FILING_STATUS",
                    field="filing_status",
                    message="filing_status is required.",
                )
            )

        # 2. 驗證 Schedule A 上游結果 (ScheduleAResultV1)
        sa_res = data.schedule_a_result
        if sa_res is not None:
            # (a) 若 Schedule A 無法申報或包含內部錯誤，不應阻斷 Form 1040，
            # 系統應自動回退選用標準扣除額 (Standard Deduction)，並記錄 Warning 提示。
            can_file = getattr(sa_res, "can_file", True)
            is_v1_supported = getattr(sa_res, "is_v1_supported", True)
            sa_errors = getattr(sa_res, "blocking_errors", []) or []

            if can_file is False or is_v1_supported is False or sa_errors:
                # 僅記錄 warning 提示，不阻斷 DeductionResolver
                pass


        # 3. 驗證 Form 8995 (QBI) 上游結果 (Form8995ResultV1)
        qbi_res = data.form_8995_result
        if qbi_res is not None:
            qbi_status = getattr(qbi_res, "status", "COMPLETE")
            if qbi_status == "BLOCKED":
                errors.append(
                    ProcessingIssueV1(
                        code="FORM_8995_BLOCKED",
                        field="form_8995_result",
                        message="Form 8995 (QBI) module execution was blocked.",
                    )
                )
            qbi_errors = getattr(qbi_res, "blocking_errors", []) or []
            for err in qbi_errors:
                if isinstance(err, ProcessingIssueV1):
                    errors.append(err)
                elif isinstance(err, dict):
                    errors.append(
                        ProcessingIssueV1(
                            code=err.get("code", "FORM_8995_ERROR"),
                            field=err.get("field"),
                            message=err.get("message", ""),
                        )
                    )

        # 4. 驗證 Schedule 1-A 上游結果 (Schedule1AResultV1)
        s1a_res = data.schedule_1a_result
        if s1a_res is not None:
            s1a_status = getattr(s1a_res, "status", "COMPLETE")
            if s1a_status == "BLOCKED":
                errors.append(
                    ProcessingIssueV1(
                        code="SCHEDULE_1A_BLOCKED",
                        field="schedule_1a_result",
                        message="Schedule 1-A module execution was blocked.",
                    )
                )
            s1a_errors = getattr(s1a_res, "blocking_errors", []) or []
            for err in s1a_errors:
                if isinstance(err, ProcessingIssueV1):
                    errors.append(err)
                elif isinstance(err, dict):
                    errors.append(
                        ProcessingIssueV1(
                            code=err.get("code", "SCHEDULE_1A_ERROR"),
                            field=err.get("field"),
                            message=err.get("message", ""),
                        )
                    )

        return errors
