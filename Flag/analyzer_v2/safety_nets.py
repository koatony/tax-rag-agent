# 確定性安全網（S07 / S07b / S07c / S07d）。
#
# PLANNER/MAP 是 LLM，輸出不保證完整、每次跑也不保證一致。這些檢查獨立於
# LLM 之外執行，要嘛補強既有的 flag，要嘛在需要時合成一個全新的 flag，
# 確保幾個已知、理解透徹的問題類別，不會只因為 LLM 這次剛好沒提到就消失。

import json

# ---------------------------------------------------------------------------
# S07 — Missing document detection (deterministic fallback)
# ---------------------------------------------------------------------------

REQUIRED_MISSING_DOCS = {
    "rental_depreciation": {
        "keywords": ["rental", "depreciation", "schedule e", "land/building", "land building"],
        "docs": [
            "Rental purchase document",
            "Land/building value allocation",
            "Prior depreciation schedule",
        ],
    },
    "travel": {
        "keywords": ["travel", "conference", "trip", "itinerary"],
        "docs": [
            "Conference agenda",
            "Travel itinerary",
            "Business purpose documentation",
        ],
    },
    "charitable_deduction": {
        "keywords": ["charitable", "donation"],
        "docs": [
            "Charitable contribution acknowledgment letter",
            "Receipt with purpose notes",
        ],
    },
    "ira_deduction": {
        "keywords": ["ira contribution", "ira deduction", "retirement plan"],
        "docs": [
            "IRA workplace retirement plan coverage information",
        ],
    },
}


def _matched_doc_categories(flag: dict) -> list[dict]:
    # 回傳所有關鍵字有出現在這個 flag 的 tax_area/flag_title 裡的
    # REQUIRED_MISSING_DOCS 類別（一個 flag 可能同時符合多個類別）。
    # 為什麼：只比對 tax_area/flag_title 而非 ai_finding 等自由文字欄位，
    # 是因為自由文字裡常會「提到」相鄰的法律概念（例如解釋「這不是慈善
    # 捐款」時會出現 "charitable" 這個字），若拿來比對關鍵字會造成
    # 誤判——明明不屬於這類問題，卻被錯誤加上該類別要求的文件清單。
    haystack = " ".join(
        str(flag.get(k, "")) for k in ("tax_area", "flag_title")
    ).lower()
    return [
        category for category in REQUIRED_MISSING_DOCS.values()
        if any(kw in haystack for kw in category["keywords"])
    ]


def enforce_required_missing_docs(flag: dict) -> dict:
    # S07 安全網：missing_docs 完全由 LLM 產生的話不可靠——LLM 有時會漏列
    # 某類問題法定該要求的文件（例如房租折舊一定要有購買文件/土地建物
    # 分攤/前期折舊表）。這裡不管 LLM 有沒有列出，只要 flag 符合已知類別，
    # 就強制把該類別要求的文件補進 missing_docs，確保 CPA 一定會看到
    # 完整的缺件清單。
    #
    # 同時記錄 `_documentation_gap`（0~1）—— 也就是 CR（Control Risk）的
    # 輸入值：在下面強制合併「之前」，符合類別的必要文件裡還缺多少比例
    # （若合併後才算，缺口永遠會變 0，沒有意義）。這是對照固定清單做的
    # 確定性計數，不是 LLM 的主觀判斷，符合本評分所依據的稽核風險模型
    # 對 CR 的定義。
    matched = _matched_doc_categories(flag)
    existing = flag.get("missing_docs") or []

    if matched:
        required_docs = {doc for category in matched for doc in category["docs"]}
        already_had = required_docs - (required_docs - set(existing))
        flag["_documentation_gap"] = 1 - (len(already_had) / len(required_docs))
    else:
        # No fixed checklist applies to this issue category; fall back to
        # whether the LLM itself flagged any missing_docs at all.
        flag["_documentation_gap"] = 1.0 if existing else 0.0

    merged = list(existing)
    for category in matched:
        for doc in category["docs"]:
            if doc not in merged:
                merged.append(doc)

    flag["missing_docs"] = merged
    return flag


# ---------------------------------------------------------------------------
# S07b — Standalone rental documentation completeness check (deterministic)
# ---------------------------------------------------------------------------
# Unlike S07 above, this doesn't wait for PLANNER/MAP to raise a flag first
# — see check_rental_documentation_completeness()'s docstring for why.

RENTAL_ACTIVITY_KEYWORDS = ["rental", "schedule e"]

RENTAL_DOCUMENTATION_REQUIREMENTS = [
    {
        "label": "Rental purchase document (closing/settlement statement)",
        "detect_keywords": ["purchase", "closing statement", "settlement statement", "hud-1"],
    },
    {
        "label": "Land/building value allocation",
        "detect_keywords": ["land/building", "land building", "land value", "assessor"],
    },
    {
        "label": "Prior depreciation schedule",
        "detect_keywords": ["form 4562", "depreciation schedule", "prior depreciation"],
    },
]


def check_rental_documentation_completeness(extracted_data: dict) -> dict | None:
    # 只要上傳文件裡任何地方出現房租活動，就檢查標準支持文件是否齊全——
    # 不管 PLANNER 有沒有提出任何房租相關問題。回傳一個合成的 flag dict
    # （尚未評分，需跟其他 flag 一樣送進 compute_risk_score），若沒有缺口
    # 則回傳 None。
    # 為什麼：S07（enforce_required_missing_docs）只能「補強」LLM 已經
    # 決定要提出的 flag；但如果這一年的房租數字看起來完全正常，PLANNER
    # 可能根本不會提出任何房租相關問題，這種情況下即使文件真的缺齊，
    # 也永遠不會被發現。這支函式獨立於 LLM 之外主動掃描，只要偵測到房租
    # 活動就檢查標準文件清單是否齊全，避免「數字合理但文件不齊」被忽略。
    documents = extracted_data.get("uploaded_documents", [])
    texts = []
    for doc in documents:
        content = doc.get("content", "")
        blob = json.dumps(content, ensure_ascii=False) if isinstance(content, (dict, list)) else str(content)
        texts.append(f"{doc.get('file_name', '')} {blob}".lower())

    if not any(kw in t for t in texts for kw in RENTAL_ACTIVITY_KEYWORDS):
        return None

    missing = [
        req["label"]
        for req in RENTAL_DOCUMENTATION_REQUIREMENTS
        if not any(kw in t for t in texts for kw in req["detect_keywords"])
    ]
    if not missing:
        return None

    return {
        "tax_area": "Schedule E",
        "flag_title": "Rental Property Documentation Gap",
        "ai_finding": (
            "Rental property activity is reported, but standard supporting "
            "documentation for acquisition/basis was not found among the "
            "uploaded documents."
        ),
        "why_it_matters": (
            "Without basis/acquisition records, depreciation claimed on this "
            "property cannot be substantiated on audit, risking disallowance "
            "of the deduction plus penalties and interest."
        ),
        "rule_deviation_type": "facts_and_circumstances",
        "requires_cpa_review": True,
        "cpa_action": "Request missing rental property documentation from client",
        "irc_reference": "Treas. Reg. §1.6001-1",
        "amount_at_risk": 0,
        "confidence_score": 1.0,
        "missing_docs": missing,
        "source_document": None,
        "status": "open",
        "cpa_note": "Auto-generated by deterministic documentation completeness check (not LLM-derived).",
        "_documentation_gap": 1.0,
    }


# ---------------------------------------------------------------------------
# S07c — Prior-year comparison (deterministic analytical procedure)
# ---------------------------------------------------------------------------
# Unlike S07/S07b (documentation completeness), this compares numbers across
# years rather than within one — see check_prior_year_comparison()'s
# docstring for why. No-op if no prior-year document is present.

PRIOR_YEAR_INCONSISTENCY_THRESHOLD = 0.30  # >=30% year-over-year delta

# Each entry maps a comparable line item to:
#   - a prior-year dict key (as found in the prior-year document's content)
#   - a function that pulls the equivalent current-year total out of
#     extracted_data's uploaded_documents
PRIOR_YEAR_COMPARISON_FIELDS = [
    ("Wages", "wages"),
    ("Interest income", "interest_income"),
    ("Dividend income", "dividend_income"),
    ("IRA contribution", "ira_contribution"),
    ("Rental income", "rental_income"),
    ("Depreciation", "depreciation"),
]


def _find_prior_year_document(documents: list[dict]) -> dict | None:
    # 依 category/document_type 標籤，找出代表去年申報資料的上傳文件；
    # 找不到就回傳 None。
    # 為什麼：後面的年度比對邏輯需要知道「哪一份文件是去年的申報資料」，
    # 才能把它跟今年其他文件算出來的總額做比較；用 category/document_type
    # 標籤辨識，而不是檔名，是因為檔名格式不受控、標籤是資料結構裡較
    # 穩定的欄位。
    for doc in documents:
        content = doc.get("content")
        if not isinstance(content, dict):
            continue
        category = str(content.get("category", "")).lower()
        doc_type = str(content.get("document_type", "")).lower()
        if "comparison engine" in category or "prior-year" in doc_type or "prior year" in doc_type:
            return content
    return None


def _current_year_totals(documents: list[dict], prior_doc: dict) -> dict:
    # 盡力從其他上傳文件的 document_type/category 標籤，抓出跟去年文件
    # 所報告的相同項目在「今年」的總額。只查去年文件本身有報告的欄位——
    # 若去年沒有該欄位的資料，也就沒有東西可比。
    # 為什麼：用 document_type/欄位存在與否來分類加總（而非用 category
    # 文字關鍵字比對），是因為某些文件的 category 標籤會互相衝突——例如
    # Form 4562 的 category 是「Schedule E / Depreciation」，如果拿
    # "rental" 這種關鍵字去配，可能會跟真正的房租收入文件搞混。改用
    # doc_type 精確比對 + 欄位是否存在，可以避免這種誤分類。
    totals: dict[str, float] = {}

    for doc in documents:
        content = doc.get("content")
        if not isinstance(content, dict) or content is prior_doc:
            continue
        doc_type = str(content.get("document_type", "")).lower()

        # Field-presence based, not doc_type/category text matching — a
        # Form 4562's category ("Schedule E / Depreciation") would otherwise
        # collide with the rental-income keyword match below.
        if doc_type == "w-2":
            totals["wages"] = totals.get("wages", 0.0) + float(content.get("wages") or 0)
        elif doc_type == "form 1099-int":
            totals["interest_income"] = totals.get("interest_income", 0.0) + float(content.get("amount") or 0)
        elif doc_type == "form 1099-div":
            totals["dividend_income"] = totals.get("dividend_income", 0.0) + float(content.get("amount") or 0)
        elif "ira" in doc_type:
            totals["ira_contribution"] = totals.get("ira_contribution", 0.0) + float(content.get("amount") or 0)
        elif content.get("annual_depreciation") is not None:
            totals["depreciation"] = totals.get("depreciation", 0.0) + float(content.get("annual_depreciation") or 0)
        elif content.get("rental_income") is not None:
            totals["rental_income"] = totals.get("rental_income", 0.0) + float(content.get("rental_income") or 0)

    return totals


def _prior_year_value(prior_doc: dict, key: str) -> float | None:
    # 從去年文件讀出單一比對欄位的值；若值是以每人分開記錄的 dict
    # （例如 {"marcus": ..., "elena": ...}），則加總成一個數字。
    # 為什麼：夫妻合併申報（Married Filing Jointly）時，某些項目在原始
    # 文件裡會分開記兩人的數字（例如各自的薪資），但比較年度差異時要用
    # 家庭總額，所以這裡統一把 dict 形式的值加總成單一數字。
    value = prior_doc.get(key)
    if value is None:
        return None
    if isinstance(value, dict):
        # e.g. {"marcus": 44000.0, "elena": 52000.0} -> sum
        return sum(float(v) for v in value.values())
    return float(value)


def check_prior_year_comparison(extracted_data: dict) -> dict | None:
    # 把今年的總額跟去年申報資料比較，標出消失不見或變動幅度超過
    # PRIOR_YEAR_INCONSISTENCY_THRESHOLD 的項目。回傳一個彙整所有異常的
    # 合成 flag；若沒有去年文件或沒有異常，則回傳 None。
    # 為什麼：這是 AICPA SAS No. 47 標準的「分析性程序」——把今年數字跟
    # 去年比較，異常的年度波動本身就是一種稽核風險訊號（可能代表漏報
    # 所得或資料有誤），跟單一年度內部數字是否合理是完全不同的風險
    # 來源，所以獨立成一個安全網檢查，而不是併入其他檢查裡。
    documents = extracted_data.get("uploaded_documents", [])
    prior_doc = _find_prior_year_document(documents)
    if prior_doc is None:
        return None

    current = _current_year_totals(documents, prior_doc)

    anomalies = []
    max_delta = 0.0
    for label, key in PRIOR_YEAR_COMPARISON_FIELDS:
        prior_value = _prior_year_value(prior_doc, key)
        if prior_value is None:
            continue  # prior-year document doesn't report this line item
        current_value = current.get(key)

        if current_value is None or current_value == 0:
            if prior_value != 0:
                anomalies.append(
                    f"{label}: reported ${prior_value:,.0f} last year, absent this year"
                )
                max_delta = max(max_delta, prior_value)
            continue

        if prior_value == 0:
            continue  # new this year, no baseline to compare against

        pct_change = (current_value - prior_value) / prior_value
        if abs(pct_change) >= PRIOR_YEAR_INCONSISTENCY_THRESHOLD:
            anomalies.append(
                f"{label}: ${prior_value:,.0f} last year -> ${current_value:,.0f} this year "
                f"({pct_change:+.0%})"
            )
            max_delta = max(max_delta, abs(current_value - prior_value))

    if not anomalies:
        return None

    return {
        "tax_area": "Prior-Year Comparison",
        "flag_title": "Year-over-Year Inconsistency",
        "ai_finding": (
            "Analytical comparison against the prior-year return found the "
            "following inconsistencies: " + "; ".join(anomalies) + "."
        ),
        "why_it_matters": (
            "Unexplained year-over-year swings are a common audit trigger and, "
            "if not reconciled and confirmed with the client, could indicate "
            "unreported income or an error carried onto the current return."
        ),
        "rule_deviation_type": "facts_and_circumstances",
        "requires_cpa_review": True,
        "cpa_action": "Confirm with client whether these year-over-year changes are legitimate and fully reported",
        "irc_reference": "N/A (analytical procedure, not a specific IRC provision)",
        "amount_at_risk": round(max_delta, 2),
        "confidence_score": 1.0,
        "missing_docs": [],
        "source_document": None,
        "status": "open",
        "cpa_note": "Auto-generated by deterministic prior-year comparison check (not LLM-derived).",
        "_documentation_gap": 1.0,
    }


# ---------------------------------------------------------------------------
# S07d — Rental depreciation omission check (deterministic)
# ---------------------------------------------------------------------------
# A numeric cross-check PLANNER/MAP sometimes misses — see
# check_rental_depreciation_omission()'s docstring for why.

def _find_rental_summary_and_depreciation(documents: list[dict]) -> tuple[dict | None, float | None]:
    # 在上傳文件裡分別找出今年的 Schedule E 房租摘要，以及 Form 4562
    # 申報的年度折舊金額，讓呼叫端可以把兩者拿來交叉比對。
    # 為什麼：折舊金額和房租收支摘要通常是兩份不同文件（Form 4562 vs.
    # Schedule E 摘要），要先各自找出來才能做下面的數字交叉比對；跳過
    # 上一年度的文件是因為那些數字不代表「今年」的狀況，混進來比對會
    # 產生錯誤結論。
    rental_doc = None
    depreciation_amount = None
    for doc in documents:
        content = doc.get("content")
        if not isinstance(content, dict):
            continue
        category = str(content.get("category", "")).lower()
        doc_type = str(content.get("document_type", "")).lower()
        if "comparison engine" in category or "prior-year" in doc_type or "prior year" in doc_type:
            continue  # prior-year document, not this year's Schedule E summary
        if content.get("rental_income") is not None:
            rental_doc = content
        if content.get("annual_depreciation") is not None:
            depreciation_amount = float(content.get("annual_depreciation") or 0)
    return rental_doc, depreciation_amount


def check_rental_depreciation_omission(extracted_data: dict) -> dict | None:
    # 若 Form 4562 申報了非零的房租折舊金額，但 Schedule E 房租摘要的
    # 費用明細沒有把折舊列進去，就合成一個 flag。若沒有東西可比對
    # （沒有房租摘要、沒有 Form 4562）或折舊已經有列，則回傳 None。
    # 為什麼：這是純數字層面的交叉核對（Form 4562 有折舊金額，但 Schedule
    # E 摘要沒把它列進費用），事實明確、不需要判斷力，理論上 LLM 應該
    # 抓得到，但實際上時有時無；用固定邏輯做這種「數字對不對得起來」的
    # 檢查，比依賴 LLM 每次都注意到更可靠，且執行成本趨近於零。
    documents = extracted_data.get("uploaded_documents", [])
    rental_doc, depreciation_amount = _find_rental_summary_and_depreciation(documents)

    if rental_doc is None or not depreciation_amount:
        return None

    expenses = rental_doc.get("expenses")
    included = isinstance(expenses, dict) and any(
        "depreciation" in str(k).lower() and float(v or 0) > 0
        for k, v in expenses.items()
    )
    if not included:
        included = bool(rental_doc.get("depreciation"))

    if included:
        return None

    return {
        "tax_area": "Schedule E",
        "flag_title": "Rental Property Depreciation Omitted",
        "ai_finding": (
            f"Form 4562 reports an annual depreciation deduction of "
            f"${depreciation_amount:,.0f}, but the Schedule E rental "
            f"property expense breakdown does not include a depreciation "
            f"line item."
        ),
        "why_it_matters": (
            f"Omitting this depreciation deduction overstates taxable rental "
            f"income by ${depreciation_amount:,.0f} and understates the "
            f"return; an amended return would be needed to recover it."
        ),
        "rule_deviation_type": "bright_line",
        "requires_cpa_review": False,
        "cpa_action": f"Direct adjustment to include ${depreciation_amount:,.0f} of depreciation expense on Schedule E",
        "irc_reference": "IRC §167, IRC §168",
        "amount_at_risk": round(depreciation_amount, 2),
        "confidence_score": 1.0,
        "missing_docs": [],
        "source_document": None,
        "status": "open",
        "cpa_note": "Auto-generated by deterministic rental depreciation omission check (not LLM-derived).",
        "_documentation_gap": 1.0,
    }


# ---------------------------------------------------------------------------
# S07e — W-2 retirement deferral / wage box reconciliation (deterministic)
# ---------------------------------------------------------------------------
# A numeric cross-check within a single W-2 that the PLANNER's business-
# expense-oriented prompt (Schedule C/A/E/SE/D patterns) has no reason to
# think to look for — see check_w2_retirement_wage_reconciliation()'s
# docstring for why.

W2_RETIREMENT_KEYWORDS = ["box 12", "elective deferral", "401(k)", "403(b)", "retirement wage reconciliation"]

# Pre-tax elective deferral codes: excluded from Box 1 but generally still
# included in Box 3 (Social Security wages) and Box 5 (Medicare wages).
# Roth variants (AA/BB/EE) are after-tax and already in Box 1, so they're
# deliberately excluded from this list.
PRETAX_DEFERRAL_CODES = {"D", "E", "F", "G", "H", "S"}

W2_BOX_RECONCILIATION_TOLERANCE = 1.00  # dollars; absorbs rounding noise only


def check_w2_retirement_wage_reconciliation(extracted_data: dict) -> list[dict]:
    # 逐一檢查每份 W-2 文件：若 Box 12 有稅前遞延提撥的 code（D/E/F/G/H/S），
    # 就比對 Box 1 加上遞延金額，是否等於 Box 3 / Box 5 申報值；不一致就
    # 合成一個 flag。回傳 list（一個報稅案件可能有多份 W-2）。
    # 為什麼：這是單一 W-2 內部的數字勾稽（Box 12 Code D 是否已經反映在
    # Box 3/Box 5），事實明確、不需要判斷力，但 PLANNER 的 prompt 目前只
    # 列出 Schedule C/A/E/SE/D 的一般商業費用型風險模式，沒有涵蓋 W-2
    # 薪資盒位之間的勾稽，實測 LLM 一次都沒有主動抓到過這個問題（即使
    # Box 14 缺標籤這種同一份文件裡的問題它能穩定抓到）。用固定邏輯做這種
    # 「數字對不對得起來」的檢查，比依賴 LLM 每次都注意到更可靠。
    documents = extracted_data.get("uploaded_documents", [])
    findings = []

    for doc in documents:
        content = doc.get("content")
        if not isinstance(content, dict):
            continue
        if str(content.get("document_type", "")).lower() != "w-2":
            continue

        box_12_items = content.get("box_12_items") or []
        deferral_amount = sum(
            float(item.get("amount") or 0)
            for item in box_12_items
            if isinstance(item, dict) and str(item.get("code", "")).upper() in PRETAX_DEFERRAL_CODES
        )
        if not deferral_amount:
            continue

        box_1 = content.get("wages_tips_other_compensation")
        box_3 = content.get("social_security_wages")
        box_5 = content.get("medicare_wages_and_tips")
        if box_1 is None or box_3 is None or box_5 is None:
            continue  # not enough of the box structure present to reconcile

        box_1, box_3, box_5 = float(box_1), float(box_3), float(box_5)
        expected_box_3 = box_1 + deferral_amount
        expected_box_5 = box_1 + deferral_amount

        mismatch_3 = abs(box_3 - expected_box_3) > W2_BOX_RECONCILIATION_TOLERANCE
        mismatch_5 = abs(box_5 - expected_box_5) > W2_BOX_RECONCILIATION_TOLERANCE
        if not (mismatch_3 or mismatch_5):
            continue

        codes = sorted({
            str(item.get("code", "")).upper()
            for item in box_12_items
            if isinstance(item, dict) and str(item.get("code", "")).upper() in PRETAX_DEFERRAL_CODES
        })

        findings.append({
            "tax_area": "Form W-2 / Wages",
            "flag_title": "Retirement Deferral (Box 12) vs. Wage Box Reconciliation",
            "ai_finding": (
                f"Box 12 reports a pre-tax elective deferral of ${deferral_amount:,.2f} "
                f"(code(s) {', '.join(codes)}), which is generally excluded from Box 1 but "
                f"included in Box 3 and Box 5. Reported values are Box 1: ${box_1:,.2f}, "
                f"Box 3: ${box_3:,.2f}, Box 5: ${box_5:,.2f}. If Box 1 already reflects the "
                f"deferral being excluded, Box 3 and Box 5 would be expected to equal "
                f"${expected_box_3:,.2f}, not the reported amount(s)."
            ),
            "why_it_matters": (
                "An inconsistency between Box 1, Box 3/5, and the Box 12 deferral means "
                "either the W-2 was issued with an error, or the wage figures were "
                "transcribed incorrectly — either way, Social Security/Medicare wage "
                "bases and taxable wages could be misstated on the return."
            ),
            "rule_deviation_type": "facts_and_circumstances",
            "requires_cpa_review": True,
            "cpa_action": (
                "Confirm with the client/employer whether Box 3 and Box 5 should include "
                "the Box 12 deferral amount, or request a corrected W-2 (Form W-2c) if the "
                "originally issued form is in error. Do not alter the reported box values "
                "without source confirmation."
            ),
            "irc_reference": "IRC §402(g); IRS Form W-2 Instructions (Box 12 Code D)",
            "amount_at_risk": round(deferral_amount, 2),
            "confidence_score": 1.0,
            "missing_docs": [],
            "source_document": doc.get("file_name"),
            "status": "open",
            "cpa_note": "Auto-generated by deterministic W-2 box reconciliation check (not LLM-derived).",
            "_documentation_gap": 1.0,
        })

    return findings


# ---------------------------------------------------------------------------
# S07f — W-2 Social Security / Medicare tax math checks (deterministic)
# ---------------------------------------------------------------------------
# Pure arithmetic re-derivation of Box 4 / Box 6 from Box 3 / Box 5 — the LLM
# has no reason to reliably re-multiply these every run, so this is done in
# code instead of relying on it noticing a math error.

SOCIAL_SECURITY_TAX_RATE = 0.062
MEDICARE_TAX_RATE = 0.0145
W2_TAX_MATH_TOLERANCE = 1.00  # dollars; absorbs rounding noise only


def check_w2_payroll_tax_math(extracted_data: dict) -> list[dict]:
    # 逐一檢查每份 W-2：Box 3 x 6.2% 是否等於 Box 4，Box 5 x 1.45% 是否
    # 等於 Box 6。金額完全吻合時不產生任何 flag（純數學驗證通過，無需
    # 提報）；只有算不起來時才合成 bright_line flag，因為稅率是法定
    # 固定值，算錯代表資料有誤，不需要人工判斷力。
    documents = extracted_data.get("uploaded_documents", [])
    findings = []

    for doc in documents:
        content = doc.get("content")
        if not isinstance(content, dict):
            continue
        if str(content.get("document_type", "")).lower() != "w-2":
            continue

        box_3 = content.get("social_security_wages")
        box_4 = content.get("social_security_tax_withheld")
        box_5 = content.get("medicare_wages_and_tips")
        box_6 = content.get("medicare_tax_withheld")

        mismatches = []
        if box_3 is not None and box_4 is not None:
            expected_ss = float(box_3) * SOCIAL_SECURITY_TAX_RATE
            if abs(float(box_4) - expected_ss) > W2_TAX_MATH_TOLERANCE:
                mismatches.append(
                    f"Social Security tax: Box 3 (${float(box_3):,.2f}) x 6.2% = "
                    f"${expected_ss:,.2f}, but Box 4 reports ${float(box_4):,.2f}"
                )
        if box_5 is not None and box_6 is not None:
            expected_medicare = float(box_5) * MEDICARE_TAX_RATE
            if abs(float(box_6) - expected_medicare) > W2_TAX_MATH_TOLERANCE:
                mismatches.append(
                    f"Medicare tax: Box 5 (${float(box_5):,.2f}) x 1.45% = "
                    f"${expected_medicare:,.2f}, but Box 6 reports ${float(box_6):,.2f}"
                )

        if not mismatches:
            continue

        findings.append({
            "tax_area": "Form W-2 / Payroll Tax Math",
            "flag_title": "Social Security/Medicare Tax Recalculation Mismatch",
            "ai_finding": "; ".join(mismatches) + ".",
            "why_it_matters": (
                "Social Security and Medicare tax withholding are fixed statutory "
                "percentages of the corresponding wage box. A mismatch indicates "
                "either a transcription error or an error on the original W-2, and "
                "should be resolved before the return is filed."
            ),
            "rule_deviation_type": "bright_line",
            "requires_cpa_review": True,
            "cpa_action": "Confirm the correct withholding amounts with the client/employer or request a corrected W-2 (Form W-2c).",
            "irc_reference": "IRC §3101 (FICA); IRC §3121",
            "amount_at_risk": 0,
            "confidence_score": 1.0,
            "missing_docs": [],
            "source_document": doc.get("file_name"),
            "status": "open",
            "cpa_note": "Auto-generated by deterministic payroll tax math check (not LLM-derived).",
            "_documentation_gap": 1.0,
        })

    return findings


# ---------------------------------------------------------------------------
# S07g — W-2 Box 12 retirement code vs. Box 13 checkbox consistency
# ---------------------------------------------------------------------------

def check_w2_box12_box13_consistency(extracted_data: dict) -> list[dict]:
    # 若 Box 12 有稅前遞延提撥 code（同 S07e 的 PRETAX_DEFERRAL_CODES），
    # 但 Box 13 的 Retirement Plan 核取方塊未勾選（或反過來），兩者互相
    # 矛盾，合成一個 flag。兩者一致（都有/都沒有）時不產生 flag。
    documents = extracted_data.get("uploaded_documents", [])
    findings = []

    for doc in documents:
        content = doc.get("content")
        if not isinstance(content, dict):
            continue
        if str(content.get("document_type", "")).lower() != "w-2":
            continue

        box_12_items = content.get("box_12_items") or []
        has_retirement_code = any(
            isinstance(item, dict) and str(item.get("code", "")).upper() in PRETAX_DEFERRAL_CODES
            for item in box_12_items
        )
        box_13 = content.get("box_13") or {}
        retirement_plan_checked = bool(box_13.get("retirement_plan"))

        if has_retirement_code == retirement_plan_checked:
            continue  # consistent either way

        findings.append({
            "tax_area": "Form W-2 / Box 12-13 Consistency",
            "flag_title": "Box 12 Retirement Code vs. Box 13 Retirement Plan Checkbox Mismatch",
            "ai_finding": (
                f"Box 12 {'reports' if has_retirement_code else 'does not report'} a "
                f"pre-tax retirement deferral code, but Box 13 Retirement Plan is "
                f"{'checked' if retirement_plan_checked else 'not checked'}."
            ),
            "why_it_matters": (
                "These two fields should agree — a retirement deferral in Box 12 "
                "implies employer plan coverage that Box 13 should reflect, since "
                "this coverage affects the employee's IRA deduction phase-out "
                "eligibility."
            ),
            "rule_deviation_type": "facts_and_circumstances",
            "requires_cpa_review": True,
            "cpa_action": "Confirm with the client/employer whether Box 13 Retirement Plan should be checked, or request a corrected W-2 (Form W-2c).",
            "irc_reference": "IRS Form W-2 Instructions (Box 12, Box 13)",
            "amount_at_risk": 0,
            "confidence_score": 1.0,
            "missing_docs": [],
            "source_document": doc.get("file_name"),
            "status": "open",
            "cpa_note": "Auto-generated by deterministic Box 12/13 consistency check (not LLM-derived).",
            "_documentation_gap": 1.0,
        })

    return findings


# ---------------------------------------------------------------------------
# S07h — W-2 federal vs. state wage reconciliation (informational)
# ---------------------------------------------------------------------------

W2_STATE_WAGE_RECONCILIATION_THRESHOLD = 0.05  # 5% relative difference


def check_w2_federal_state_wage_reconciliation(extracted_data: dict) -> list[dict]:
    # 比對 Box 1（聯邦工資）與各州 Box 16（州工資）差額。這是分析性
    # reconciliation，不是絕對錯誤判定——州工資本來就可能因為州別扣除
    # 項目不同而與聯邦工資不完全相同，所以只在差異超過門檻時才提示，
    # 且一律標記為 informational，不阻擋自動核准。
    documents = extracted_data.get("uploaded_documents", [])
    findings = []

    for doc in documents:
        content = doc.get("content")
        if not isinstance(content, dict):
            continue
        if str(content.get("document_type", "")).lower() != "w-2":
            continue

        box_1 = content.get("wages_tips_other_compensation")
        if box_1 is None:
            continue
        box_1 = float(box_1)

        for state_item in content.get("state_and_local") or []:
            if not isinstance(state_item, dict):
                continue
            state_wages = state_item.get("state_wages")
            if state_wages is None:
                continue
            state_wages = float(state_wages)
            if box_1 == 0:
                continue
            pct_diff = abs(state_wages - box_1) / box_1
            if pct_diff < W2_STATE_WAGE_RECONCILIATION_THRESHOLD:
                continue

            findings.append({
                "tax_area": "Form W-2 / Federal-State Wage Reconciliation",
                "flag_title": "Federal vs. State Wage Reconciliation Note",
                "ai_finding": (
                    f"Box 1 federal wages (${box_1:,.2f}) and Box 16 "
                    f"{state_item.get('state', '')} state wages (${state_wages:,.2f}) "
                    f"differ by {pct_diff:.1%}, which exceeds the "
                    f"{W2_STATE_WAGE_RECONCILIATION_THRESHOLD:.0%} analytical review threshold."
                ),
                "why_it_matters": (
                    "Federal and state wages are not required to match exactly, but a "
                    "large gap should be reconciled to confirm it reflects a legitimate "
                    "state adjustment rather than a transcription error."
                ),
                "rule_deviation_type": "informational",
                "requires_cpa_review": False,
                "cpa_action": "Confirm the wage difference is expected (e.g. state-specific pre-tax adjustments) rather than a data entry error.",
                "irc_reference": "N/A (analytical procedure)",
                "amount_at_risk": round(abs(state_wages - box_1), 2),
                "confidence_score": 1.0,
                "missing_docs": [],
                "source_document": doc.get("file_name"),
                "status": "open",
                "cpa_note": "Auto-generated by deterministic federal/state wage reconciliation check (not LLM-derived).",
                "_documentation_gap": 0.0,
            })

    return findings


# ---------------------------------------------------------------------------
# S07i — Form 1098 Box 5 (Mortgage Insurance Premiums) 2025 non-deductibility
# ---------------------------------------------------------------------------

def check_form1098_mip_nondeductible(extracted_data: dict) -> list[dict]:
    # 2025 年 mortgage insurance premiums 的列舉扣除已失效，這是固定
    # 稅法事實，不需要 LLM 判斷。Box 5 有金額且稅務年度為 2025 時，
    # 產生 informational flag，確保金額不會被誤映射到 Schedule A。
    documents = extracted_data.get("uploaded_documents", [])
    findings = []

    for doc in documents:
        content = doc.get("content")
        if not isinstance(content, dict):
            continue
        if str(content.get("document_type", "")).lower() != "1098":
            continue
        if str(content.get("tax_year", "")) != "2025":
            continue

        mortgage = content.get("mortgage") or {}
        mip_amount = mortgage.get("box_5_mortgage_insurance_premiums")
        if not mip_amount:
            continue
        mip_amount = float(mip_amount)

        findings.append({
            "tax_area": "Form 1098 / Mortgage Insurance Premiums",
            "flag_title": "Mortgage Insurance Premiums Not Deductible for 2025",
            "ai_finding": (
                f"Box 5 reports Mortgage Insurance Premiums of ${mip_amount:,.2f}. "
                f"The itemized deduction for mortgage insurance premiums has expired "
                f"for tax year 2025 and does not apply."
            ),
            "why_it_matters": (
                "If this amount were combined with Box 1 mortgage interest and "
                "mapped to Schedule A, the return would overstate the itemized "
                "deduction."
            ),
            "rule_deviation_type": "informational",
            "requires_cpa_review": False,
            "cpa_action": "No action needed — retain the amount for the record, but do not map it to Schedule A Line 8a.",
            "irc_reference": "Former IRC §163(h)(3)(E) (expired for tax years after 2021 per current law as extended)",
            "amount_at_risk": 0,
            "confidence_score": 1.0,
            "missing_docs": [],
            "source_document": doc.get("file_name"),
            "status": "open",
            "cpa_note": "Auto-generated by deterministic 2025 MIP deductibility check (not LLM-derived).",
            "_documentation_gap": 0.0,
        })

    return findings


# ---------------------------------------------------------------------------
# S07j — Rental property depreciation arithmetic check (deterministic)
# ---------------------------------------------------------------------------

RENTAL_DEPRECIATION_MATH_TOLERANCE = 1.00  # dollars; absorbs rounding noise only


def check_rental_depreciation_arithmetic(extracted_data: dict) -> dict | None:
    # 若房租摘要同時提供 depreciable_basis、recovery_period_years 與
    # annual_depreciation，重新計算 basis / recovery_period 是否等於
    # 申報的年折舊金額。這是純數學驗證，跟 S07d（檢查折舊有沒有被遺漏）
    # 不同——這裡假設折舊「有」列出，只驗證金額算得對不對。
    documents = extracted_data.get("uploaded_documents", [])

    for doc in documents:
        content = doc.get("content")
        if not isinstance(content, dict):
            continue
        basis = content.get("depreciable_basis")
        recovery_years = content.get("recovery_period_years")
        annual_depreciation = content.get("annual_depreciation")
        if basis is None or not recovery_years or annual_depreciation is None:
            continue

        basis, recovery_years, annual_depreciation = float(basis), float(recovery_years), float(annual_depreciation)
        expected = basis / recovery_years
        if abs(expected - annual_depreciation) <= RENTAL_DEPRECIATION_MATH_TOLERANCE:
            continue

        return {
            "tax_area": "Schedule E / Depreciation Math",
            "flag_title": "Rental Depreciation Arithmetic Mismatch",
            "ai_finding": (
                f"Depreciable basis (${basis:,.2f}) / recovery period "
                f"({recovery_years:g} years) = ${expected:,.2f} expected annual "
                f"depreciation, but ${annual_depreciation:,.2f} was reported."
            ),
            "why_it_matters": (
                "An incorrect depreciation calculation misstates rental expenses "
                "and, if left uncorrected, would need to be fixed via an amended "
                "return or Form 3115 change in accounting method."
            ),
            "rule_deviation_type": "bright_line",
            "requires_cpa_review": True,
            "cpa_action": "Recompute the depreciation schedule and confirm the correct annual amount with the client's records (Form 4562).",
            "irc_reference": "IRC §168 (MACRS)",
            "amount_at_risk": round(abs(expected - annual_depreciation), 2),
            "confidence_score": 1.0,
            "missing_docs": [],
            "source_document": doc.get("file_name"),
            "status": "open",
            "cpa_note": "Auto-generated by deterministic rental depreciation arithmetic check (not LLM-derived).",
            "_documentation_gap": 1.0,
        }

    return None


# ---------------------------------------------------------------------------
# S07k — Rental repair vs. capital improvement classification (informational)
# ---------------------------------------------------------------------------

REPAIR_CLASSIFICATION_AMOUNT_THRESHOLD = 2500  # de minimis safe harbor-style reference point


def check_rental_repair_classification(extracted_data: dict) -> dict | None:
    # 房租費用明細裡的 repairs_and_maintenance 金額低於門檻時，傾向視為
    # 當年度可費用化的 repair；金額較高時無法只憑金額判斷，需要人工確認
    # 是 repair 還是應資本化攤提的 improvement。兩種情況都不自動下最終
    # 結論，只給建議分類、一律要求人工確認實際施工內容。
    documents = extracted_data.get("uploaded_documents", [])

    for doc in documents:
        content = doc.get("content")
        if not isinstance(content, dict):
            continue
        expenses = content.get("expenses")
        if not isinstance(expenses, dict):
            continue
        repair_amount = expenses.get("repairs_and_maintenance")
        if not repair_amount:
            continue
        repair_amount = float(repair_amount)

        suggested = (
            "repair (deductible as a current-year Schedule E expense)"
            if repair_amount < REPAIR_CLASSIFICATION_AMOUNT_THRESHOLD
            else "possible capital improvement (may require capitalization and depreciation)"
        )

        return {
            "tax_area": "Schedule E / Repair vs. Improvement Classification",
            "flag_title": "Repairs and Maintenance Classification Requires Confirmation",
            "ai_finding": (
                f"${repair_amount:,.2f} was reported under Repairs and Maintenance. "
                f"Based on amount alone, this tentatively looks like a {suggested}, "
                f"but the nature of the work (routine repair vs. betterment/"
                f"restoration/adaptation) determines the correct tax treatment and "
                f"cannot be determined from the amount alone."
            ),
            "why_it_matters": (
                "Repairs are deductible in the year paid, while capital improvements "
                "must be capitalized and depreciated over the asset's recovery "
                "period — misclassifying one as the other misstates current-year "
                "rental income."
            ),
            "rule_deviation_type": "informational",
            "requires_cpa_review": True,
            "cpa_action": "Confirm with the client what work was performed to determine repair vs. capitalized improvement treatment (IRC §1.263(a)-3 tangible property regulations).",
            "irc_reference": "Treas. Reg. §1.263(a)-3",
            "amount_at_risk": 0,
            "confidence_score": 0.5,
            "missing_docs": [],
            "source_document": doc.get("file_name"),
            "status": "open",
            "cpa_note": "Auto-generated by deterministic repair/improvement classification heuristic (not LLM-derived); amount-based suggestion only.",
            "_documentation_gap": 0.0,
        }

    return None


# ---------------------------------------------------------------------------
# S07l — Charitable contribution written acknowledgment validation
# ---------------------------------------------------------------------------

CHARITY_ACKNOWLEDGMENT_THRESHOLD = 250  # IRC §170(f)(8) written acknowledgment requirement


def check_charity_acknowledgment(extracted_data: dict) -> dict | None:
    # 捐款超過 $250 依法需要書面收據（written acknowledgment）且確認未
    # 取得對價的商品或服務，才能列舉扣除。收據資料裡若已明確標示
    # written_acknowledgment=true 且 goods_or_services_received=false，
    # 視為驗證通過，不產生 flag；反之則產生需人工審查的 flag。
    documents = extracted_data.get("uploaded_documents", [])

    for doc in documents:
        content = doc.get("content")
        if not isinstance(content, dict):
            continue
        if "charit" not in str(content.get("document_type", "")).lower():
            continue

        amount = content.get("amount")
        if amount is None or float(amount) < CHARITY_ACKNOWLEDGMENT_THRESHOLD:
            continue

        has_acknowledgment = content.get("written_acknowledgment")
        received_goods = content.get("goods_or_services_received")

        if has_acknowledgment is True and received_goods is False:
            continue  # validated, no issue to raise

        return {
            "tax_area": "Schedule A / Charitable Contribution Substantiation",
            "flag_title": "Charitable Contribution Acknowledgment Requires Confirmation",
            "ai_finding": (
                f"Contribution of ${float(amount):,.2f} exceeds the $250 written "
                f"acknowledgment threshold, but written_acknowledgment="
                f"{has_acknowledgment!r} and goods_or_services_received="
                f"{received_goods!r} could not be confirmed as compliant."
            ),
            "why_it_matters": (
                "Contributions over $250 without a compliant contemporaneous "
                "written acknowledgment are not deductible, regardless of whether "
                "the donation was actually made."
            ),
            "rule_deviation_type": "facts_and_circumstances",
            "requires_cpa_review": True,
            "cpa_action": "Obtain a compliant written acknowledgment from the organization confirming the amount and whether any goods/services were received in exchange.",
            "irc_reference": "IRC §170(f)(8)",
            "amount_at_risk": round(float(amount), 2),
            "confidence_score": 1.0,
            "missing_docs": ["Written acknowledgment letter from donee organization"],
            "source_document": doc.get("file_name"),
            "status": "open",
            "cpa_note": "Auto-generated by deterministic charitable acknowledgment check (not LLM-derived).",
            "_documentation_gap": 1.0,
        }

    return None


# ---------------------------------------------------------------------------
# S07m — Schedule B threshold note (informational)
# ---------------------------------------------------------------------------

IRS_SCHEDULE_B_THRESHOLD = 1500  # IRS: Schedule B required if interest or dividends exceed this


def check_schedule_b_threshold_note(extracted_data: dict) -> dict | None:
    # 加總所有 1099-INT 利息 + 1099-DIV 股利，跟 IRS 強制附 Schedule B
    # 的 $1,500 門檻比較。低於門檻時附上 informational 提示，避免误認為
    # 「這個案例有出現 Schedule B 相關資料，所以 IRS 強制要求」——這只是
    # 案例設計需要，不是法定義務。
    documents = extracted_data.get("uploaded_documents", [])
    interest_total = 0.0
    dividend_total = 0.0
    has_schedule_b_candidate = False

    for doc in documents:
        content = doc.get("content")
        if not isinstance(content, dict):
            continue
        doc_type = str(content.get("document_type", "")).lower()
        if doc_type == "form 1099-int":
            interest_total += float(content.get("interest_income") or 0)
            has_schedule_b_candidate = True
        elif doc_type == "form 1099-div":
            dividend_total += float(content.get("dividend_income") or 0)
            has_schedule_b_candidate = True

    if not has_schedule_b_candidate:
        return None

    combined = interest_total + dividend_total
    if combined >= IRS_SCHEDULE_B_THRESHOLD:
        return None  # IRS does require Schedule B here — nothing to clarify

    return {
        "tax_area": "Schedule B / Filing Requirement",
        "flag_title": "Schedule B Not IRS-Required at Current Combined Total",
        "ai_finding": (
            f"Combined taxable interest (${interest_total:,.2f}) and ordinary "
            f"dividends (${dividend_total:,.2f}) total ${combined:,.2f}, which is "
            f"below the IRS ${IRS_SCHEDULE_B_THRESHOLD:,.0f} threshold that "
            f"requires Schedule B to be filed."
        ),
        "why_it_matters": (
            "Schedule B may still be prepared for recordkeeping or case-specific "
            "reasons, but it should not be represented to the client as an IRS "
            "filing requirement at this combined amount."
        ),
        "rule_deviation_type": "informational",
        "requires_cpa_review": False,
        "cpa_action": "No action needed — note that Schedule B is not mandatory at this income level.",
        "irc_reference": "IRS Schedule B Instructions",
        "amount_at_risk": 0,
        "confidence_score": 1.0,
        "missing_docs": [],
        "source_document": None,
        "status": "open",
        "cpa_note": "Auto-generated by deterministic Schedule B threshold check (not LLM-derived).",
        "_documentation_gap": 0.0,
    }
