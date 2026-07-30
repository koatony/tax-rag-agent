# 量化風險評分 — 稽核風險模型（AICPA SAS No. 47, 1983），
# 從財報稽核改編應用到報稅風險評估。
#
#   IR（固有風險） = w1 * CategoryBaseRate + w2 * Materiality     (0-1)
#   CR（控制風險） = w3 * DocumentationGap                         (0-1)
#   DR（偵查風險） = LookupTable(RuleDeviationType)                (0-1)
#   風險分數 = IR * CR * DR，換算成 0-100
#
#   門檻：>=70 High，40-69 Medium，<40 Low
#
# IR/CR 拆解成子因子的做法參考 Hajiha (2011)「Fuzzy audit risk modeling
# algorithm」——IR 和 CR 都是由可量化的子因子、用固定權重組合而成，
# 而非整體憑感覺判斷。
#
# 依 SAS No. 47 本身的指引，小金額的項目仍可能具有重大性，因此違反明確
# 法定紅線（bright line）的項目完全不會進入這個乘法公式——直接鎖定為
# "high"，避免低重大性的紅線違規在乘法計算中被稀釋成低分。

RISK_WEIGHTS = {
    "w1": 0.6,  # weight on CategoryBaseRate within IR
    "w2": 0.4,  # weight on Materiality within IR
    "w3": 1.0,  # weight on DocumentationGap within CR
}

# CategoryBaseRate: fixed lookup table, NOT an LLM judgment. Reflects how
# often this category of issue results in an adjustment in general tax
# practice. Matched against tax_area + flag_title, same keyword-matching
# approach as REQUIRED_MISSING_DOCS in safety_nets.py; first match wins.
CATEGORY_BASE_RATE_TABLE = [
    (["entertainment", "season ticket"], 0.9),
    (["meals"], 0.6),
    (["travel", "conference", "trip", "itinerary"], 0.65),
    (["rental", "depreciation", "schedule e"], 0.55),
    (["charitable", "donation"], 0.45),
    (["ira contribution", "ira deduction", "retirement plan"], 0.5),
    (["mortgage interest"], 0.2),
    (["prior-year comparison", "prior year comparison"], 0.5),
]
CATEGORY_BASE_RATE_DEFAULT = 0.5


def _category_base_rate(flag: dict) -> float:
    # 用 flag 的 tax_area/flag_title 對 CATEGORY_BASE_RATE_TABLE 做關鍵字
    # 比對，查出固定的 CategoryBaseRate（第一個命中的為準）；都沒命中則
    # 回傳 CATEGORY_BASE_RATE_DEFAULT。
    # 為什麼：不同類型的稅務問題本身被國稅局調整的機率不同（例如娛樂費
    # 幾乎必被剔除，房貸利息很少出問題），這是稅務實務上的先驗機率，
    # 用固定表格查表而非讓 LLM 自己判斷，是為了讓風險分數可重現、
    # 不會因為 LLM 每次的主觀評分不同而使同類型問題得到不一致的風險等級。
    haystack = " ".join(
        str(flag.get(k, "")) for k in ("tax_area", "flag_title")
    ).lower()
    for keywords, rate in CATEGORY_BASE_RATE_TABLE:
        if any(kw in haystack for kw in keywords):
            return rate
    return CATEGORY_BASE_RATE_DEFAULT


# DR: only used for the two deviation types that actually reach the formula.
# "bright_line" never reaches this lookup — see compute_risk_score below.
RULE_DEVIATION_LOOKUP = {
    "safe_harbor_boundary": 0.6,
    "facts_and_circumstances": 1.0,
}
RULE_DEVIATION_DEFAULT = 1.0  # unknown/missing classification -> treat as highest DR

RISK_LEVEL_THRESHOLDS = [(70, "high"), (40, "medium")]  # else "low"


def _risk_level_from_score(score: float) -> str:
    # 依 RISK_LEVEL_THRESHOLDS（由高到低檢查，否則視為 "low"）把 0-100 的
    # 風險分數轉成 "high"/"medium"/"low" 標籤。
    # 為什麼：8.2 (Risk-Level Sorting) 需要一個離散的 High/Medium/Low 標籤
    # 給前端排序、篩選、上色用；但底層計算出來的是連續分數(0-100)，
    # 這裡用固定門檻切三段，讓分數與等級的對應關係透明、CPA 好稽核。
    for threshold, level in RISK_LEVEL_THRESHOLDS:
        if score >= threshold:
            return level
    return "low"


def compute_risk_score(flag: dict, max_amount_at_risk: float) -> tuple[float, str]:
    # 模型計算：Risk Score = IR x CR x DR。
    # max_amount_at_risk 是本次分析所有 flag 中最大的 amount_at_risk——
    # Materiality（重大性）是這個 flag 的金額相對於此的比例，不是 LLM
    # 判斷的分數，因為「跟這次找到的其他問題比起來有多重大」本質上就是
    # 跨 flag 的比較，只能在全部 flag 金額都知道之後才能算。

    # 為什麼：舊版讓 LLM 自己判斷 risk_level（"high"/"medium"/"low"），但
    # LLM 的判斷不穩定、同樣的問題不同次跑分析可能給不同等級，CPA 也很
    # 難稽核「為什麼這個是 high」。這裡改用 AICPA SAS No. 47 的稽核風險
    # 模型公式（IR x CR x DR），把風險拆成可解釋、可重現的子因子，讓
    # LLM 只負責判斷事實（rule_deviation_type），分數則是公式算出來的。
    
    if flag.get("rule_deviation_type") == "bright_line":
        return 100, "high"

    w1, w2, w3 = RISK_WEIGHTS["w1"], RISK_WEIGHTS["w2"], RISK_WEIGHTS["w3"]

    category_base_rate = _category_base_rate(flag)

    amount = float(flag.get("amount_at_risk") or 0)
    materiality = (amount / max_amount_at_risk) if max_amount_at_risk > 0 else 0.0

    documentation_gap = float(flag.get("_documentation_gap", 0.0))

    dr = RULE_DEVIATION_LOOKUP.get(flag.get("rule_deviation_type"), RULE_DEVIATION_DEFAULT)

    ir = w1 * category_base_rate + w2 * materiality
    cr = w3 * documentation_gap

    score = round(ir * cr * dr * 100)
    return score, _risk_level_from_score(score)
