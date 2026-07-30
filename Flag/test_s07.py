"""
S07 — Missing Document Detection 驗證腳本

不呼叫任何 LLM，直接測試 enforce_required_missing_docs() 這個保險機制
是否真的能保證三個類別（租賃折舊 / 差旅 / 扣除額支持）的固定文件項目
一定出現在 missing_docs 裡。

Run: uv run python -m Flag.test_s07  (從專案根目錄執行；用 -m 是因為要以套件方式 import Flag.analyzer_v2)
"""

from Flag.analyzer_v2.safety_nets import enforce_required_missing_docs, REQUIRED_MISSING_DOCS

CASES = [
    {
        "name": "S07-01 租賃折舊",
        "flag": {
            "tax_area": "Schedule E",
            "flag_title": "Rental property depreciation not claimed",
            "ai_finding": "No depreciation schedule found for rental property.",
            "irc_reference": "IRC §167",
            "missing_docs": [],
        },
        "expected_docs": REQUIRED_MISSING_DOCS["rental_depreciation"]["docs"],
    },
    {
        "name": "S07-02 差旅支持",
        "flag": {
            "tax_area": "Schedule C",
            "flag_title": "Las Vegas conference trip mixed personal/business",
            "ai_finding": "Travel expense includes non-business days.",
            "irc_reference": "IRC §162(a)(2)",
            "missing_docs": [],
        },
        "expected_docs": REQUIRED_MISSING_DOCS["travel"]["docs"],
    },
    {
        "name": "S07-03 扣除額支持（慈善捐贈）",
        "flag": {
            "tax_area": "Schedule A",
            "flag_title": "Charitable donation documentation",
            "ai_finding": "Church donation lacks formal acknowledgment letter.",
            "irc_reference": "IRC §170",
            "missing_docs": [],
        },
        "expected_docs": REQUIRED_MISSING_DOCS["charitable_deduction"]["docs"],
    },
    {
        "name": "S07-03 扣除額支持（IRA）",
        "flag": {
            "tax_area": "Form 1040",
            "flag_title": "IRA contribution deduction",
            "ai_finding": "IRA deduction claimed without confirming workplace retirement plan coverage.",
            "irc_reference": "IRC §219",
            "missing_docs": [],
        },
        "expected_docs": REQUIRED_MISSING_DOCS["ira_deduction"]["docs"],
    },
    {
        "name": "迴歸測試：IRA 案子不該混入慈善捐款文件",
        "flag": {
            "tax_area": "Schedule 1",
            "flag_title": "IRA Deduction Limitation for Active Participant",
            "ai_finding": "IRA deduction subject to phase-out under IRC §219(g).",
            "irc_reference": "IRC §219(g)",
            "missing_docs": [],
        },
        "expected_docs": REQUIRED_MISSING_DOCS["ira_deduction"]["docs"],
    },
    {
        "name": "迴歸測試：慈善捐款案子不該混入 IRA 文件",
        "flag": {
            "tax_area": "Schedule A",
            "flag_title": "Missing Charitable Contribution Acknowledgment",
            "ai_finding": "Contemporaneous written acknowledgment required under IRC §170(f)(8).",
            "irc_reference": "IRC §170(f)(8)",
            "missing_docs": [],
        },
        "expected_docs": REQUIRED_MISSING_DOCS["charitable_deduction"]["docs"],
    },
    {
        "name": "不屬於任何 S07 類別（對照組，不應強加文件）",
        "flag": {
            "tax_area": "Schedule C",
            "flag_title": "City fine paid to government agency",
            "ai_finding": "Fines paid to a government entity are non-deductible.",
            "irc_reference": "IRC §162(f)",
            "missing_docs": [],
        },
        "expected_docs": [],
    },
    {
        "name": "迴歸測試：政治獻金，ai_finding 提到『charitable』字樣但不該誤判",
        "flag": {
            "tax_area": "Schedule A",
            "flag_title": "Non-deductible Political Contribution",
            "ai_finding": "Taxpayer categorized a political contribution as a charitable deduction. "
                          "Under IRC §170, political contributions are not deductible as charitable "
                          "contributions.",
            "irc_reference": "IRC §170(c)",
            "missing_docs": [],
        },
        "expected_docs": [],
    },
    {
        "name": "迴歸測試：娛樂費用，ai_finding 含『deduction』字樣但不該誤判",
        "flag": {
            "tax_area": "Schedule C",
            "flag_title": "Non-deductible Entertainment Expense",
            "ai_finding": "Under IRC §274(a), no deduction is allowed for expenses paid for entertainment.",
            "irc_reference": "IRC §274(a)",
            "missing_docs": [],
        },
        "expected_docs": [],
    },
    {
        "name": "迴歸測試：政府罰款，ai_finding 含『deduction』字樣但不該誤判",
        "flag": {
            "tax_area": "Schedule C",
            "flag_title": "Non-deductible Government Fine",
            "ai_finding": "Under IRC §162(f), no deduction is allowed for any fine or penalty paid to a government.",
            "irc_reference": "IRC §162(f)",
            "missing_docs": [],
        },
        "expected_docs": [],
    },
    {
        "name": "已有 missing_docs，應合併不覆蓋且不重複",
        "flag": {
            "tax_area": "Schedule E",
            "flag_title": "Rental property depreciation not claimed",
            "ai_finding": "No depreciation schedule found.",
            "irc_reference": "IRC §167",
            "missing_docs": ["Rental purchase document", "Some other custom doc"],
        },
        "expected_docs": REQUIRED_MISSING_DOCS["rental_depreciation"]["docs"] + ["Some other custom doc"],
    },
]


def run():
    failures = []
    for case in CASES:
        result = enforce_required_missing_docs(dict(case["flag"]))
        docs = result["missing_docs"]
        missing = [d for d in case["expected_docs"] if d not in docs]
        # Any doc from a REQUIRED_MISSING_DOCS category that showed up but wasn't
        # expected for this case — catches cross-contamination between categories
        # (e.g. an IRA flag pulling in charitable-donation docs), not just the
        # "no category should have matched at all" scenario.
        unexpected_required = [
            d for cat in REQUIRED_MISSING_DOCS.values() for d in cat["docs"]
            if d in docs and d not in case["expected_docs"]
        ]

        ok = not missing and not unexpected_required
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {case['name']}")
        print(f"       missing_docs = {docs}")
        if missing:
            print(f"       缺少應有的項目: {missing}")
        if unexpected_required:
            print(f"       不該出現卻出現的項目: {unexpected_required}")

        if not ok:
            failures.append(case["name"])

    print()
    if failures:
        print(f"結果：{len(failures)} / {len(CASES)} 個案例失敗 -> {failures}")
        raise SystemExit(1)
    else:
        print(f"結果：全部 {len(CASES)} 個案例通過，S07 保險機制運作正常。")


if __name__ == "__main__":
    run()
