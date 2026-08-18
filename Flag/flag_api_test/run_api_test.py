#!/usr/bin/env python3
"""Black-box HTTP test runner for the Flag Metaya /analyze endpoint.

Loads test_cases/*.json, POSTs each to {API_BASE_URL}/analyze, compares the
returned flags against expected_flags/*.json via keyword matching, and writes
a markdown report to report/api_flag_test_report.md.

See api_contract.md for the authoritative request/response schema this script
relies on, and for the documented interface gaps (no flag_code, no
blocks_auto_approval, no INFO severity) referenced in the report.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
import os

HERE = Path(__file__).resolve().parent
TEST_CASES_DIR = HERE / "test_cases"
EXPECTED_FLAGS_DIR = HERE / "expected_flags"
REPORT_DIR = HERE / "report"
RAW_RESPONSES_DIR = REPORT_DIR / "raw_responses"

SEVERITY_MAP = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}


def load_test_cases(filter_id: str | None) -> list[Path]:
    paths = sorted(TEST_CASES_DIR.glob("*.json"))
    if filter_id:
        filter_id = filter_id.lower()
        paths = [p for p in paths if filter_id in p.stem.lower()]
    return paths


def load_expected(test_case_stem: str) -> dict | None:
    # tc01_marcus_w2.json -> tc01_expected.json
    case_id = test_case_stem.split("_")[0]
    expected_path = EXPECTED_FLAGS_DIR / f"{case_id}_expected.json"
    if not expected_path.exists():
        return None
    with open(expected_path, "r", encoding="utf-8") as f:
        return json.load(f)


def flag_haystack(flag: dict) -> str:
    return " ".join(
        str(flag.get(k, "") or "") for k in ("tax_area", "flag_title", "ai_finding")
    ).lower()


def _keyword_hits(text: str, keywords: list[str]) -> bool:
    # Word-boundary match instead of plain substring containment, e.g. "fica"
    # must not match inside "classification". Each keyword (single word or
    # multi-word phrase) is matched as a whole unit via \b...\b, not as
    # individually-matchable component words.
    for kw in keywords:
        pattern = r"\b" + re.escape(kw.lower()) + r"\b"
        if re.search(pattern, text):
            return True
    return False


def match_expected_flag(check: dict, api_flags: list[dict]) -> dict | None:
    keywords = [kw.lower() for kw in check.get("match_keywords", [])]
    for flag in api_flags:
        haystack = flag_haystack(flag)
        if keywords and _keyword_hits(haystack, keywords):
            return flag
    return None


def compare(expected: dict, api_flags: list[dict]) -> list[dict]:
    """Return one result row per flag_checks[] entry.

    Each row: official_test_id, test_item, expected_result, actual_result,
    status, matched_flag (full API flag object or None).
    """
    rows = []

    for check in expected.get("flag_checks", []):
        official_test_id = check.get("official_test_id")
        test_item = check.get("test_item")
        expected_result = check.get("expected_result")
        check_type = check.get("check_type", "expect_flag")
        matched = match_expected_flag(check, api_flags)

        if check_type == "expect_no_flag":
            if matched is None:
                status = "PASS"
                actual_result = "未產生 flag（符合預期）"
            else:
                status = "FAIL - UNEXPECTED_FLAG"
                actual_result = (
                    f"{matched.get('flag_title')} (risk_level={matched.get('risk_level')})"
                )
        else:  # expect_flag
            if matched is None:
                status = "FAIL - NOT_DETECTED"
                actual_result = "未產生任何 flag"
            else:
                expected_sev = SEVERITY_MAP.get(
                    str(check.get("expected_severity", "")).upper()
                )
                actual_sev = str(matched.get("risk_level", "")).lower()
                if expected_sev and expected_sev != actual_sev:
                    status = "PARTIAL - SEVERITY_MISMATCH"
                    actual_result = f"severity={actual_sev} (預期 {expected_sev})"
                else:
                    status = "PASS"
                    actual_result = (
                        f"{matched.get('flag_title')} (risk_level={matched.get('risk_level')})"
                    )

        rows.append(
            {
                "official_test_id": official_test_id,
                "test_item": test_item,
                "expected_result": expected_result,
                "actual_result": actual_result,
                "status": status,
                "matched_flag": matched,
                "expected_blocks_auto_approval": check.get(
                    "expected_blocks_auto_approval"
                ),
                "check_type": check_type,
            }
        )

    return rows


def run_case(client: httpx.Client, path: Path, headers: dict) -> dict:
    case_id = path.stem.split("_")[0].upper()
    print(f"[{case_id}] POSTing to /analyze...")

    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    try:
        resp = client.post("/analyze", json=payload, headers=headers, timeout=120.0)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as exc:
        print(f"[{case_id}] ERROR: {exc}")
        return {"case_id": case_id, "status": "ERROR", "reason": str(exc)}

    if resp.status_code != 200:
        reason = f"HTTP {resp.status_code}: {resp.text[:500]}"
        print(f"[{case_id}] ERROR: {reason}")
        return {"case_id": case_id, "status": "ERROR", "reason": reason}

    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        reason = f"invalid JSON response: {exc}"
        print(f"[{case_id}] ERROR: {reason}")
        return {"case_id": case_id, "status": "ERROR", "reason": reason}

    RAW_RESPONSES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_RESPONSES_DIR / f"{path.stem.split('_')[0]}_response.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[{case_id}] saved raw response -> {out_path}")

    expected = load_expected(path.stem)
    if expected is None:
        print(f"[{case_id}] WARNING: no expected_flags file found, skipping comparison")
        return {
            "case_id": case_id,
            "status": "NO_EXPECTED",
            "response": data,
        }

    api_flags = data.get("flags", [])
    rows = compare(expected, api_flags)
    return {
        "case_id": case_id,
        "status": "OK",
        "api_flags": api_flags,
        "rows": rows,
    }


def render_report(results: list[dict], only_fails: bool = False) -> str:
    lines = ["# API Flag Test Report", ""]
    lines.append(
        "Generated by `run_api_test.py`. See `api_contract.md` for the authoritative "
        "API schema and interface-gap notes referenced below."
    )
    lines.append("")

    if only_fails:
        lines.append(
            "> **Filtered report (`--only-fails`):** only rows with status "
            "`FAIL*` or `PARTIAL*` are rendered below. All rows are still "
            "collected internally; this filter only affects what is printed."
        )
        lines.append("")

    total_pass = total_partial = total_fail = 0
    per_case_counts = {}

    lines.append("## Per-test-case checklists")
    lines.append("")

    for r in results:
        case_id = r["case_id"]
        lines.append(f"### {case_id}")
        lines.append("")

        if r["status"] == "ERROR":
            lines.append(f"ERROR: {r.get('reason', '')}")
            lines.append("")
            continue
        if r["status"] == "NO_EXPECTED":
            lines.append("No expected_flags file found for this test case.")
            lines.append("")
            continue

        rows = r.get("rows", [])
        n_pass = sum(1 for row in rows if row["status"] == "PASS")
        n_partial = sum(1 for row in rows if row["status"].startswith("PARTIAL"))
        n_fail = sum(1 for row in rows if row["status"].startswith("FAIL"))
        total_pass += n_pass
        total_partial += n_partial
        total_fail += n_fail
        per_case_counts[case_id] = (n_pass, n_partial, n_fail)

        display_rows = rows
        if only_fails:
            display_rows = [
                row for row in rows if not row["status"] == "PASS"
            ]

        lines.append("| 測試編號 | 測試項目 | 預期結果 | 實際結果 | 狀態 |")
        lines.append("|---|---|---|---|---|")
        for row in display_rows:
            note = ""
            if row.get("expected_blocks_auto_approval") is not None:
                note = " *(blocks_auto_approval: 無法驗證，API 無此欄位)*"
            lines.append(
                f"| {row['official_test_id']} | {row['test_item']} | "
                f"{row['expected_result']} | {row['actual_result']}{note} | "
                f"{row['status']} |"
            )
        if not display_rows:
            lines.append("| _(no FAIL/PARTIAL rows)_ | | | | |")
        lines.append("")
        lines.append(
            f"_TC summary: {n_pass} PASS / {n_partial} PARTIAL / {n_fail} FAIL "
            f"(of {len(rows)} checks)_"
        )
        lines.append("")

    lines.append("## Overall summary")
    lines.append("")
    lines.append("| Test Case | PASS | PARTIAL | FAIL |")
    lines.append("|---|---|---|---|")
    for case_id, (n_pass, n_partial, n_fail) in per_case_counts.items():
        lines.append(f"| {case_id} | {n_pass} | {n_partial} | {n_fail} |")
    total_checks = total_pass + total_partial + total_fail
    lines.append(f"| **TOTAL** | **{total_pass}** | **{total_partial}** | **{total_fail}** |")
    lines.append("")
    lines.append(f"Total checks: {total_checks}")
    lines.append("")

    lines.append("## API gaps vs PM requirements")
    lines.append("")
    lines.append(
        "From `api_contract.md` (confirmed from source, not re-derived here):"
    )
    lines.append("")
    lines.append(
        "- **No `flag_code` field.** Flags carry only free-text `tax_area` + "
        "`flag_title` and a positional, re-sorted `flag_id` (e.g. `FLAG-001`) with no "
        "semantic meaning across runs. This suite matches on keyword substrings against "
        "`tax_area`+`flag_title`+`ai_finding` instead, which is inherently fuzzier than a "
        "real code match."
    )
    lines.append(
        "- **No `blocks_auto_approval` field.** Not present anywhere in `analyzer_v2/`. "
        "Any PM acceptance criterion depending on this field (e.g. TC01's "
        "\"在重大問題解決前阻止自動核准\") cannot currently be verified against the live API."
    )
    lines.append(
        "- **`risk_level` is only `high`/`medium`/`low`** -- there is no `INFO` tier. "
        "PM-specified `INFO`-severity flags (e.g. `POSSIBLE_SYNTHETIC_TEST_DOCUMENT` in "
        "TC01) are marked `must_detect: false` in `expected_flags/*.json` and cannot be "
        "severity-checked against the live API."
    )
    lines.append(
        "- **No per-request session/state.** Multi-document cumulative test cases "
        "(TC03-05 needing prior test cases' documents) must resend the full cumulative "
        "`uploaded_documents` array client-side each time; exercised above for TC03-05."
    )
    lines.append(
        "- **Known test-harness limitation (not an API gap):** `match_expected_flag()` "
        "does not exclude an API flag once it has matched one row's `match_keywords`, "
        "so two rows with overlapping keywords could independently match the same "
        "underlying API flag. This suite disambiguates Marcus's vs Elena's identical-"
        "shaped `W2_RETIREMENT_WAGE_RECONCILIATION_*` checks (DI-W2-020 vs DI-EW2-021) "
        "by exact dollar figures (`$2,000.00`/`$48,000.00` vs `$3,000.00`/`$57,000.00`), "
        "which the API's own `ai_finding` text carries, so this is no longer ambiguous "
        "in practice -- still worth cross-checking against `report/raw_responses/` if "
        "a row's `actual_result` looks suspicious."
    )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run black-box tests against the Flag Metaya /analyze API.")
    parser.add_argument(
        "--test-case",
        default=None,
        help="Filter to a single test case, e.g. 'tc01' (matches against the filename stem).",
    )
    parser.add_argument(
        "--only-fails",
        action="store_true",
        help="Only render FAIL/PARTIAL rows in the printed report (all rows are still collected internally).",
    )
    args = parser.parse_args()

    load_dotenv(HERE / ".env")

    base_url = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
    api_key = os.environ.get("API_KEY", "").strip()
    headers = {"X-API-Key": api_key} if api_key else {}

    paths = load_test_cases(args.test_case)
    if not paths:
        print(f"No test cases found in {TEST_CASES_DIR} (filter={args.test_case!r})")
        return 1

    results = []
    with httpx.Client(base_url=base_url) as client:
        for path in paths:
            results.append(run_case(client, path, headers))

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_text = render_report(results, only_fails=args.only_fails)
    report_path = REPORT_DIR / "flag_checklist_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\nReport written to {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
