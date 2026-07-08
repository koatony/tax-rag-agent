import streamlit as st
import json
import os
import glob
import re
import zipfile
import xml.etree.ElementTree as ET

def verify_login():
    """安全性：密碼驗證狀態檢查"""
    if not st.session_state.get("password_correct", False):
        st.error("請先回到主頁面登入")
        st.stop()

def inject_custom_css():
    """載入自訂 CSS 樣式，符合 Premium 設計質感"""
    st.markdown("""
        <style>
        .metric-card {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            padding: 15px;
            margin-bottom: 12px;
        }
        .field-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }
        .field-table th {
            background-color: rgba(255, 255, 255, 0.05);
            text-align: left;
            padding: 8px 12px;
            font-weight: 700;
            border-bottom: 2px solid rgba(255, 255, 255, 0.1);
        }
        .field-table td {
            padding: 8px 12px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }
        .badge-input {
            background-color: rgba(59, 130, 246, 0.15);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.3);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.78rem;
            font-weight: bold;
        }
        .badge-formula {
            background-color: rgba(168, 85, 247, 0.15);
            color: #c084fc;
            border: 1px solid rgba(168, 85, 247, 0.3);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.78rem;
            font-weight: bold;
        }
        .badge-flag {
            background-color: rgba(239, 68, 68, 0.15);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.3);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.78rem;
            font-weight: bold;
        }
        .badge-recommend {
            background-color: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.78rem;
            font-weight: bold;
        }
        </style>
    """, unsafe_allow_html=True)

def load_all_rivera_samples() -> str:
    """輔助函式：組合所有 Sample 1~10 作為 LLM 的輸入原始資料"""
    path_pattern = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "src_json_Marcus_and_Elena", "Sample *.json"))
    files = sorted(glob.glob(path_pattern))
    
    samples_data = {
        "taxpayer_profile": {
            "Name": "Marcus and Elena Rivera",
            "Filing Status": "Married Filing Jointly",
            "State": "California (Sacramento)",
            "Tax Year": 2024
        },
        "uploaded_documents": []
    }
    
    for fpath in files:
        fname = os.path.basename(fpath)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = json.load(f)
                samples_data["uploaded_documents"].append({
                    "file_name": fname,
                    "content": json.dumps(content, ensure_ascii=False)
                })
        except Exception as e:
            samples_data["uploaded_documents"].append({
                "file_name": fname,
                "content": f"載入錯誤: {e}"
            })
            
    return json.dumps(samples_data, indent=2, ensure_ascii=False)

def _extract_text_from_docx(docx_path: str) -> str:
    """從 .docx 檔案中提取純文字"""
    try:
        with zipfile.ZipFile(docx_path) as z:
            xml_content = z.read('word/document.xml')
            root = ET.fromstring(xml_content)
            namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            text_elements = root.findall('.//w:t', namespaces)
            return ' '.join([el.text for el in text_elements if el.text])
    except Exception:
        return ""

def load_sample_data_pack_v2() -> str:
    """輔助函式：從 Sample Data Pack v2 0622 的 .docx 原始憑證組合文字，作為 LLM 輸入"""
    src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "docs", "Sample Data Pack v2 0622", "src_data"))
    docx_files = [
        "Sample 01 - W-2 Marcus.docx",
        "Sample 02 - W-2 Elena.docx",
        "Sample 03 - Rivera 1098.docx",
        "Sample 04 - 1099-DIV & 1099-INT & IRA & Charity.docx",
        "Sample 05 - Rental Property Income_.docx",
        "Sample 06 - Depreciation Information.docx",
        "Tax Example v2 - The Pet Shop Employee and Rental Property Owner.docx"
    ]
    combined_texts = []
    for f in docx_files:
        path = os.path.join(src_dir, f)
        if os.path.exists(path):
            text = _extract_text_from_docx(path)
            combined_texts.append(f"--- Document: {f} ---\n{text}\n")
        else:
            combined_texts.append(f"--- Document: {f} (找不到檔案) ---\n")
    return "\n".join(combined_texts)

# ─── Schedule A 特有的欄位判斷 ───────────────────────────────────────

# Schedule A 的標準 IRS 表單行號欄位集合（不含中間計算輔助欄位）
_SCHEDULE_A_STANDARD_FIELD_IDS = {
    # Inputs (excluding general info keys like taxpayer_name, ssn, filing_status, agi which are shown separately)
    "elect_itemize_even_if_less_than_standard",
    "use_sales_tax_instead_of_income_tax",

    # ── Part I: Medical and Dental Expenses ──
    "line_1_medical_and_dental_expenses_net",
    "line_2_agi",
    "line_3_agi_threshold_7_5_percent",
    "line_4_deductible_medical_expenses",

    # ── Part II: Taxes You Paid ──
    "line_5a_amount",
    "line_5a_general_sales_tax_elected",
    "line_5b_amount",
    "line_5c_amount",
    "line_5d_amount",
    "line_5e_amount",
    "line_6_amount",
    "line_7_amount",

    # ── Part III: Interest You Paid ──
    "line_8a",
    "line_8b",
    "line_8c",
    "line_8e",
    "line_9",
    "line_10_interest",

    # ── Part IV: Gifts to Charity ──
    "line_11",
    "line_12",
    "line_13",
    "line_14_charity",

    # ── Part V / Part VI: Casualty / Other ──
    "line_15",
    "line_16",

    # ── Total & Advisory ──
    "line_17_total_itemized",
    "standard_deduction_amount",
    "should_itemize",
    "final_deduction_used"
}

# 需要在「基本資訊」區塊顯示的欄位
_GENERAL_INFO_KEYS = ["taxpayer_name", "ssn", "filing_status", "agi"]

# 需要 ⚠️ 旗標的欄位（不可扣除項目）
_FLAG_FIELDS = {"political_contributions"}

def is_standard_schedule_a_field(field_id: str) -> bool:
    """判斷是否為標準 Schedule A IRS 申報欄位（用於標準欄位表格過濾）"""
    return field_id in _SCHEDULE_A_STANDARD_FIELD_IDS

def render_general_info(final_state: dict, schema: dict):
    """顯示申報人基本資料"""
    with st.expander("📂 基本資訊 (General Information)", expanded=True):
        cols = st.columns(2)
        for idx, key in enumerate(_GENERAL_INFO_KEYS):
            val = final_state.get(key, "N/A")
            desc = key
            for item in schema["inputs"]:
                if item["id"] == key:
                    desc = item["description"]
                    break
            col_to_use = cols[idx % 2]
            col_to_use.markdown(f"**{desc}**: `{val}`")

def render_standard_fields_table(final_state: dict, schema: dict):
    """繪製標準欄位表格 (僅顯示標準 IRS 欄位，排除 General Info 欄位)"""
    all_table_fields = []
    
    # 加入 Inputs（過濾掉 General Info 和 Flag 欄位）
    for item in schema["inputs"]:
        fid = item["id"]
        if fid in _GENERAL_INFO_KEYS:
            continue
        if fid in _FLAG_FIELDS:
            # Flag 欄位也顯示，但用 badge-flag 標記
            all_table_fields.append({
                "id": fid,
                "type_badge": '<span class="badge-flag">⚠️ Non-Deductible</span>',
                "val": final_state.get(fid, 0.0),
                "desc": item["description"]
            })
            continue
        if not is_standard_schedule_a_field(fid):
            continue
        all_table_fields.append({
            "id": fid,
            "type_badge": '<span class="badge-input">Input</span>',
            "val": final_state.get(fid, 0.0),
            "desc": item["description"]
        })
        
    # 加入 Formulas（僅過濾標準）
    for item in schema["formulas"]:
        fid = item["id"]
        if not is_standard_schedule_a_field(fid):
            continue
        # 特殊標示：建議欄位
        if fid in ("should_itemize", "final_deduction_used"):
            badge = '<span class="badge-recommend">📊 Advisory</span>'
        else:
            badge = '<span class="badge-formula">Formula</span>'
        all_table_fields.append({
            "id": fid,
            "type_badge": badge,
            "val": final_state.get(fid, 0.0),
            "desc": item["description"]
        })
        
    # 依 ID 排序
    all_table_fields = sorted(all_table_fields, key=lambda x: x["id"])
        
    # 繪製表格
    html_rows = []
    for f in all_table_fields:
        val_display = f["val"]
        if f["id"] == "tax_year":
            val_display = f"{int(val_display)}" if isinstance(val_display, (int, float)) else str(val_display)
        elif isinstance(val_display, float):
            val_display = f"${val_display:,.2f}"
        elif isinstance(val_display, bool):
            val_display = "✅ Yes" if val_display else "❌ No"
        
        html_rows.append(
            f'<tr>'
            f'<td style="font-weight:bold; font-family:monospace;">{f["id"]}</td>'
            f'<td>{f["desc"]}</td>'
            f'<td>{f["type_badge"]}</td>'
            f'<td style="font-weight:bold; color:#a3e635; text-align:right;">{val_display}</td>'
            f'</tr>'
        )
        
    table_html = (
        f'<table class="field-table">'
        f'<thead><tr>'
        f'<th>欄位 ID</th>'
        f'<th>欄位描述 (Description)</th>'
        f'<th>填寫類型 (Type)</th>'
        f'<th style="text-align:right;">最終數值 (Value)</th>'
        f'</tr></thead>'
        f'<tbody>{"".join(html_rows)}</tbody>'
        f'</table>'
    )
    st.markdown(table_html, unsafe_allow_html=True)

def get_formula_variable_details(expr: str, state: dict) -> str:
    """輔助函式：提取公式中的變數當前數值"""
    vars_found = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', expr)
    details = []
    for var in vars_found:
        if var in ["min", "max", "True", "False", "None"]:
            continue
        if var in state:
            val = state[var]
            if var == "tax_year":
                val_str = f"{int(val)}" if isinstance(val, (int, float)) else str(val)
            elif isinstance(val, float):
                val_str = f"${val:,.2f}"
            else:
                val_str = str(val)
            details.append(f"{var} = {val_str}")
    return ", ".join(details) if details else "None"

def render_calculation_trace_table(final_state: dict, schema: dict, input_detail_desc: str):
    """繪製欄位計算與來源詳細追蹤表 (Calculation Trace Table)"""
    st.markdown("#### 🧮 欄位計算與來源詳細追蹤表 (Calculation Trace Table)")
    trace_rows = []
    
    # 收集 Inputs
    for item in schema["inputs"]:
        val = final_state.get(item["id"], "N/A")
        if item["id"] == "tax_year":
            val_display = f"{int(val)}" if isinstance(val, (int, float)) else str(val)
        else:
            val_display = f"${val:,.2f}" if isinstance(val, float) else str(val)
        
        # 政治捐款特別標記
        if item["id"] in _FLAG_FIELDS:
            type_badge = '<span class="badge-flag">⚠️ Non-Deductible</span>'
        else:
            type_badge = '<span class="badge-input">Input</span>'
            
        trace_rows.append({
            "id": item["id"],
            "desc": item["description"],
            "type": type_badge,
            "expr": "N/A (直接提取)",
            "details": input_detail_desc,
            "val": val_display
        })
        
    # 收集 Formulas 與中間計算
    for item in schema["formulas"]:
        expr = item["expr"]
        val = final_state.get(item["id"], "N/A")
        if isinstance(val, bool):
            val_display = "✅ Yes" if val else "❌ No"
        elif isinstance(val, float):
            if item["id"] == "tax_year":
                val_display = f"{int(val)}"
            else:
                val_display = f"${val:,.2f}"
        else:
            val_display = str(val)
        details = get_formula_variable_details(expr, final_state)
        
        trace_rows.append({
            "id": item["id"],
            "desc": item["description"],
            "type": '<span class="badge-formula">Formula / Calc</span>',
            "expr": f"<code>{expr}</code>",
            "details": details,
            "val": val_display
        })
        
    # 渲染 HTML 表格
    trace_html_rows = []
    for r in trace_rows:
        trace_html_rows.append(
            f'<tr>'
            f'<td style="font-family:monospace; font-weight:bold;">{r["id"]}</td>'
            f'<td>{r["desc"]}</td>'
            f'<td>{r["type"]}</td>'
            f'<td>{r["expr"]}</td>'
            f'<td style="font-size:0.85rem; color:#888;">{r["details"]}</td>'
            f'<td style="font-weight:bold; color:#a3e635; text-align:right;">{r["val"]}</td>'
            f'</tr>'
        )
        
    trace_table_html = (
        f'<table class="field-table">'
        f'<thead><tr>'
        f'<th>欄位 ID</th>'
        f'<th>描述</th>'
        f'<th>類型</th>'
        f'<th>運算公式/來源</th>'
        f'<th>依賴變數與當前值 (Trace)</th>'
        f'<th style="text-align:right;">計算結果</th>'
        f'</tr></thead>'
        f'<tbody>{"".join(trace_html_rows)}</tbody>'
        f'</table>'
    )
    st.markdown(trace_table_html, unsafe_allow_html=True)

def render_topological_chain(schema: dict, final_state: dict):
    """顯示依賴排序順序 (拓撲鏈)"""
    st.markdown("#### 🔄 Python 拓撲排序依賴鏈")
    st.write("公式在執行時是由 Python 自動根據依賴圖計算出排序鏈，以確保有依賴的欄位永遠最先計算。")
    
    # 提取表達式依賴並排序
    formulas_def = schema.get("formulas", [])
    formula_deps = {}
    for f in formulas_def:
        variables = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', f["expr"])
        dependencies = [var for var in variables if var in formula_deps or var in final_state]
        formula_deps[f["id"]] = dependencies
        
    def topological_sort(formula_deps: dict) -> list:
        visited = {}  # 0: unvisited, 1: visiting, 2: visited
        order = []
        def dfs(node):
            if visited.get(node, 0) == 1:
                raise ValueError(f"公式依賴檢測到循環引用: {node}")
            if visited.get(node, 0) == 2:
                return
            visited[node] = 1
            for dep in formula_deps.get(node, []):
                if dep in formula_deps:
                    dfs(dep)
            visited[node] = 2
            order.append(node)
        for node in formula_deps:
            if visited.get(node, 0) == 0:
                dfs(node)
        return order

    calc_order = topological_sort(formula_deps)
    
    st.code(" -> ".join(calc_order), language="text")

def render_itemize_comparison(final_state: dict):
    """顯示逐項扣除 vs 標準扣除額的比較面板"""
    st.markdown("#### 📊 逐項扣除 vs 標準扣除額比較")
    
    itemized = final_state.get("line_17_total_itemized", 0.0)
    standard = final_state.get("standard_deduction_amount", 0.0)
    should_itemize = final_state.get("should_itemize", False)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            label="📋 逐項扣除額合計 (Itemized)",
            value=f"${itemized:,.2f}"
        )
    with col2:
        st.metric(
            label="📄 標準扣除額 (Standard)",
            value=f"${standard:,.2f}"
        )
    with col3:
        advantage = itemized - standard
        if should_itemize:
            st.metric(
                label="✅ 建議選擇 Itemized",
                value=f"+${advantage:,.2f}",
                delta=f"逐項多扣 ${advantage:,.2f}",
                delta_color="normal"
            )
        else:
            st.metric(
                label="⚠️ 建議選擇 Standard",
                value=f"${abs(advantage):,.2f}",
                delta=f"標準扣額較多 ${abs(advantage):,.2f}",
                delta_color="inverse"
            )
    
    # 政治捐款警示
    political = final_state.get("political_contributions", 0.0)
    if isinstance(political, float) and political > 0:
        st.warning(
            f"⚠️ **政治捐款 ${political:,.2f} 已被標記為不可扣除 (Non-Deductible)**\n\n"
            "根據 IRC §162(e) 及 IRC §276，捐款給政治黨派、候選人或政治行動委員會 (PAC) "
            "的金額依法完全不可作為 Schedule A 逐項扣除額，已自動從慈善捐贈計算中排除。"
        )
