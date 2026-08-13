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
