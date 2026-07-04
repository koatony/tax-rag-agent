# IRS W-2 Box 12 Codes Mapping
BOX_12_CODES = {
    "A": "Uncollected social security or RRTA tax on tips",
    "B": "Uncollected Medicare tax on tips",
    "C": "Comfortable group-term life insurance (over $50,000)",
    "D": "Elective deferrals to a 401(k) cash or deferred arrangement",
    "E": "Elective deferrals under a section 403(b) salary reduction agreement",
    "F": "Elective deferrals under a section 408(k)(6) salary reduction SEP",
    "G": "Elective deferrals and employer contributions to a section 457(b) deferred compensation plan",
    "H": "Elective deferrals to a section 501(c)(18)(D) tax-exempt organization plan",
    "J": "Nontaxable sick pay",
    "K": "20% excise tax on excess golden parachute payments",
    "L": "Substantiated employee business expense reimbursements",
    "M": "Uncollected social security or RRTA tax on taxable cost of group-term life insurance over $50,000",
    "N": "Uncollected Medicare tax on taxable cost of group-term life insurance over $50,000",
    "P": "Excludable moving expense reimbursements paid directly to a member of the U.S. Armed Forces",
    "Q": "Nontaxable combat pay",
    "R": "Employer contributions to an Archer MSA",
    "S": "Employee salary reduction contributions under a section 408(p) SIMPLE plan",
    "T": "Adoption benefits",
    "V": "Income from exercise of nonstatutory stock option(s)",
    "W": "Employer contributions to a health savings account (HSA)",
    "Y": "Deferrals under a section 409A nonqualified deferred compensation plan",
    "Z": "Income under a section 409A nonqualified deferred compensation plan",
    "AA": "Designated Roth contributions under a 401(k) plan",
    "BB": "Designated Roth contributions under a 403(b) plan",
    "DD": "Cost of employer-sponsored health coverage",
    "EE": "Designated Roth contributions under a governmental section 457(b) plan"
}

def clean_json(data: dict) -> dict:
    """去除空值並進行基本的數值轉換"""
    cleaned = {}
    for k, v in data.items():
        if v is None or v == "":
            continue
        # 嘗試轉換為數字，但保留原始字串以防萬一
        cleaned[k] = v
    return cleaned

def json_to_markdown(data: dict) -> str:
    """將 JSON 轉換為結構化的 Markdown 列表，並包含代碼翻譯"""
    form_type = data.get("form_type", "Unknown Form")
    year = data.get("year", "Unknown Year")
    
    md_lines = [f"## {year} {form_type} Tax Document"]
    md_lines.append(f"Source: OCR Extracted Data\n")
    
    # 這裡可以根據不同的表單類型做更細緻的排序，目前先通用處理
    for k, v in data.items():
        if k in ["form_type", "year"]:
            continue
            
        display_name = k.replace("_", " ").title()
        
        # 針對 Box 12 代碼進行翻譯擴充
        translation = ""
        if "box_12" in k.lower() and "code" in k.lower() and v in BOX_12_CODES:
            translation = f" ({BOX_12_CODES[v]})"
            
        md_lines.append(f"- **{display_name}**: {v}{translation}")
        
    return "\n".join(md_lines)
