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

def extract_text_from_docx(docx_path):
    try:
        with zipfile.ZipFile(docx_path) as z:
            xml_content = z.read('word/document.xml')
            root = ET.fromstring(xml_content)
            namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            text_elements = root.findall('.//w:t', namespaces)
            return ' '.join([el.text for el in text_elements if el.text])
    except Exception as e:
        return ""

def load_sample_data_pack_v2():
    src_dir = os.path.join("docs", "Sample Data Pack v2 0622", "src_data")
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
            text = extract_text_from_docx(path)
            combined_texts.append(f"--- Document: {f} ---\n{text}\n")
        else:
            combined_texts.append(f"--- Document: {f} (找不到檔案) ---\n")
            
    return "\n".join(combined_texts)

def render_general_info(final_state: dict, schema: dict):
    """顯示申報人基本資料"""
    with st.expander("📂 基本資訊 (General Information)", expanded=True):
        cols = st.columns(2)
        general_show_keys = [
            "proprietor_name", "taxpayer_ssn_masked", "tax_year", 
            "principal_business", "principal_activity_code", "business_name", 
            "ein", "business_address", "accounting_method"
        ]
        for idx, key in enumerate(general_show_keys):
            val = final_state.get(key, "N/A")
            desc = key
            for item in schema.get("inputs", []):
                if item["id"] == key:
                    desc = item["description"]
                    break
            col_to_use = cols[idx % 2]
            col_to_use.markdown(f"**{desc}**: `{val}`")

def render_standard_fields_table(final_state: dict, schema: dict):
    """抄自 Schedule B 的動態欄位顯示表格，對齊所有 Key-Value 輸出。"""
    
    def serialize_decimal(obj):
        from decimal import Decimal
        if isinstance(obj, Decimal):
            return float(obj)
        raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

    GENERAL_KEYS = {
        "proprietor_name", "taxpayer_ssn_masked", "tax_year", "principal_business",
        "principal_activity_code", "business_name", "ein", "business_address",
        "accounting_method"
    }

    html_rows = []
    for key, val in sorted(final_state.items()):
        if key in GENERAL_KEYS:
            continue
        
        if isinstance(val, (dict, list)):
            val_display = f"<code>{json.dumps(val, default=serialize_decimal, ensure_ascii=False)}</code>"
        elif isinstance(val, float) or hasattr(val, "as_tuple"): # Decimal
            val_display = f"<strong style='color:#a3e635;'>{val}</strong>"
        elif isinstance(val, bool):
            val_display = "✅ True" if val else "❌ False"
        else:
            val_display = str(val)
        
        desc = ""
        for inp in schema.get("inputs", []):
            if inp["id"] == key:
                desc = inp.get("description", "")
                break
        
        if key in ["can_file", "is_v1_supported", "can_map", "needs_review"]:
            badge = '<span class="badge-conditional">Status</span>'
        elif key in ["blocking_errors", "review_warnings"]:
            badge = '<span class="badge-conditional">Diagnosis</span>'
        else:
            badge = '<span class="badge-input">Standard</span>'

        html_rows.append(
            f"<tr>"
            f"<td style='font-family:monospace; font-weight:bold;'>{key}</td>"
            f"<td>{desc}</td>"
            f"<td>{badge}</td>"
            f"<td style='text-align:right;'>{val_display}</td>"
            f"</tr>"
        )
        
    table_html = (
        f"<table class='field-table'>"
        f"<thead><tr><th>欄位名稱 (Key)</th><th>欄位描述</th><th>類型 (Type)</th><th style='text-align:right;'>欄位值 (Value)</th></tr></thead>"
        f"<tbody>{''.join(html_rows)}</tbody>"
        f"</table>"
    )
    st.markdown(table_html, unsafe_allow_html=True)

def render_calculation_trace_table(final_state: dict, schema: dict, input_detail_desc: str):
    """與 render_standard_fields_table 保持一致"""
    st.markdown("#### 🧮 欄位計算與來源詳細追蹤表")
    render_standard_fields_table(final_state, schema)

def render_topological_chain(schema: dict, final_state: dict):
    """顯示依賴排序順序 (拓撲鏈)"""
    st.markdown("#### 🔄 依賴與計算引擎鏈")
    st.info("Schedule C V1 採用確定性 Python 代數計算。依賴關係包含：")
    st.code("Part I Income -> Part II Expenses & Part V Other Expenses -> Line 28 Total Expenses -> Line 29 Tentative Profit -> Line 31 Net Profit -> Line 32 At-Risk Box & Diagnostics", language="text")
