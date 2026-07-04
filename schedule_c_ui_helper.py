import streamlit as st
import json
import os
import glob
import re

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
        .badge-conditional {
            background-color: rgba(245, 158, 11, 0.15);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.3);
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

def is_standard_schedule_c_field(field_id: str) -> bool:
    """判斷是否為標準 Schedule C 國稅局申報欄位"""
    general_info = [
        "proprietor_name", "ssn", "principal_business", 
        "line_b_principal_activity_code", "business_name", 
        "ein", "business_address", "accounting_method", 
        "started_acquired_2025"
    ]
    if field_id in general_info:
        return True
    if field_id.startswith("line_"):
        if field_id.endswith("_val") or "before_sec179" in field_id or field_id == "sec179_deduction":
            return False
        return True
    return False

def render_general_info(final_state: dict, schema: dict):
    """顯示申報人基本資料"""
    with st.expander("📂 基本資訊 (General Information)", expanded=True):
        cols = st.columns(2)
        general_show_keys = ["proprietor_name", "ssn", "principal_business", "line_b_principal_activity_code", "business_name", "ein", "business_address", "accounting_method", "started_acquired_2025"]
        for idx, key in enumerate(general_show_keys):
            val = final_state.get(key, "N/A")
            desc = key
            for item in schema["inputs"]:
                if item["id"] == key:
                    desc = item["description"]
                    break
            col_to_use = cols[idx % 2]
            col_to_use.markdown(f"**{desc}**: `{val}`")

def render_standard_fields_table(final_state: dict, schema: dict):
    """繪製標準欄位表格 (僅顯示標準 IRS 欄位)"""
    general_show_keys = ["proprietor_name", "ssn", "principal_business", "line_b_principal_activity_code", "business_name", "ein", "business_address", "accounting_method", "started_acquired_2025"]
    all_table_fields = []
    
    # 加入 Inputs (僅過濾標準)
    for item in schema["inputs"]:
        if item["id"] in general_show_keys:
            continue
        if not is_standard_schedule_c_field(item["id"]):
            continue
        all_table_fields.append({
            "id": item["id"],
            "type_badge": '<span class="badge-input">Input</span>',
            "val": final_state.get(item["id"], 0.0),
            "desc": item["description"]
        })
        
    # 加入 Formulas (僅過濾標準)
    for item in schema["formulas"]:
        if not is_standard_schedule_c_field(item["id"]):
            continue
        all_table_fields.append({
            "id": item["id"],
            "type_badge": '<span class="badge-formula">Formula</span>',
            "val": final_state.get(item["id"], 0.0),
            "desc": item["description"]
        })
        
    # 依 ID 排序使表單顯示更有條理
    all_table_fields = sorted(all_table_fields, key=lambda x: x["id"])
        
    # 繪製表格
    html_rows = []
    for f in all_table_fields:
        val_display = f["val"]
        if isinstance(val_display, float):
            val_display = f"${val_display:,.2f}"
        
        html_rows.append(f'<tr><td style="font-weight:bold; font-family:monospace;">{f["id"]}</td><td>{f["desc"]}</td><td>{f["type_badge"]}</td><td style="font-weight:bold; color:#a3e635; text-align:right;">{val_display}</td></tr>')
        
    table_html = f'<table class="field-table"><thead><tr><th>欄位 ID</th><th>欄位描述 (Description)</th><th>填寫類型 (Type)</th><th style="text-align:right;">最終數值 (Value)</th></tr></thead><tbody>{"".join(html_rows)}</tbody></table>'
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
            if isinstance(val, float):
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
        val_display = f"${val:,.2f}" if isinstance(val, float) else str(val)
        trace_rows.append({
            "id": item["id"],
            "desc": item["description"],
            "type": '<span class="badge-input">Input</span>',
            "expr": "N/A (直接提取)",
            "details": input_detail_desc,
            "val": val_display
        })
        
    # 收集 Formulas 與中間計算
    for item in schema["formulas"]:
        expr = item["expr"]
        val = final_state.get(item["id"], "N/A")
        val_display = f"${val:,.2f}" if isinstance(val, float) else str(val)
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
        trace_html_rows.append(f'<tr>'
                               f'<td style="font-family:monospace; font-weight:bold;">{r["id"]}</td>'
                               f'<td>{r["desc"]}</td>'
                               f'<td>{r["type"]}</td>'
                               f'<td>{r["expr"]}</td>'
                               f'<td style="font-size:0.85rem; color:#888;">{r["details"]}</td>'
                               f'<td style="font-weight:bold; color:#a3e635; text-align:right;">{r["val"]}</td>'
                               f'</tr>')
        
    trace_table_html = f'<table class="field-table"><thead><tr><th>欄位 ID</th><th>描述</th><th>類型</th><th>運算公式/來源</th><th>依賴變數與當前值 (Trace)</th><th style="text-align:right;">計算結果</th></tr></thead><tbody>{"".join(trace_html_rows)}</tbody></table>'
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
        
    from schedule_c_processor import topological_sort
    calc_order = topological_sort(formula_deps)
    
    st.code(" -> ".join(calc_order), language="text")
