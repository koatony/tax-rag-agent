import streamlit as st
import json
import time
import os
import sys
import zipfile
import xml.etree.ElementTree as ET

# 將工作路徑加入系統中以正確載入專案模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 載入共享 UI 輔助模組
import schedule_a_ui_helper

# ─── 安全性：密碼驗證 ─────────────────────────────────────────────────────
schedule_a_ui_helper.verify_login()

# ─── 頁面配置 ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Schedule E Part I — LLM Schema Extraction & Rules Engine 測試",
    layout="wide",
)

# ─── 自訂 CSS ─────────────────────────────────────────────────────────────
schedule_a_ui_helper.inject_custom_css()

st.markdown(
    """
    <style>
    .schedule-e-card {
        background: linear-gradient(135deg, rgba(99,102,241,0.15) 0%, rgba(16,185,129,0.10) 100%);
        border: 1px solid rgba(99,102,241,0.35);
        border-radius: 14px;
        padding: 22px 28px;
        margin-bottom: 18px;
    }
    .step-badge {
        display: inline-block;
        background: rgba(168,85,247,0.2);
        color: #c084fc;
        border: 1px solid rgba(168,85,247,0.35);
        border-radius: 6px;
        padding: 2px 10px;
        font-size: 0.78rem;
        font-weight: 700;
        margin-right: 6px;
    }
    .field-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 10px;
        margin-bottom: 20px;
    }
    .field-table th, .field-table td {
        border: 1px solid rgba(255,255,255,0.1);
        padding: 10px 14px;
        text-align: left;
    }
    .field-table th {
        background: rgba(255,255,255,0.05);
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─── 輔助函式：從 Docx 讀取文字 ─────────────────────────────────────────────
def get_docx_text(path: str) -> str:
    if not os.path.exists(path):
        return f"找不到檔案: {path}"
    try:
        with zipfile.ZipFile(path) as z:
            xml_content = z.read("word/document.xml")
            root = ET.fromstring(xml_content)
            namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            texts = []
            for paragraph in root.findall('.//w:t', namespaces):
                if paragraph.text:
                    texts.append(paragraph.text)
            return "\n".join(texts)
    except Exception as e:
        return f"讀取 Word 檔案錯誤: {str(e)}"

# ─── 載入模組 ─────────────────────────────────────────────────────────────
from processors.parsers.schedule_e import ScheduleELLMParser
from processors.processors.schedule_e import calculate_schedule_e_dynamic

# ─── 主頁面渲染 ───────────────────────────────────────────────────────────
st.title("📄 Schedule E Part I — LLM Schema Extraction & Rules Engine")
st.markdown(
    "本頁面展示最新設計的 **`ScheduleELLMParser`**，它直接依據 [`schedule_e_schema.json`](file:///home/metaya/tax-rag-agent/docs/how_to_fill_forms_docs/schedule_e/schedule_e_schema.json) 的定義，"
    "從原始申報憑證文字中，一次性（Single-shot）提取出符合規格的計算輸入，並將結果送入規則引擎進行運算。"
)

# 準備 v2 0622 資料路徑
workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
src_data_dir = os.path.join(workspace_dir, "docs", "Sample Data Pack v2 0622", "src_data")
sample5_path = os.path.join(src_data_dir, "Sample 05 - Rental Property Income_.docx")
sample6_path = os.path.join(src_data_dir, "Sample 06 - Depreciation Information.docx")

# ─── 資料集選擇 ────────────────────────────────────────────────────────────
st.markdown("### 📂 測試資料集選擇")

# 初始化 session state
if "se_input_text" not in st.session_state:
    st.session_state.se_input_text = ""

data_source = st.radio(
    "選擇輸入資料來源",
    options=["📄 v2 0622（Word 原始憑證）", "📥 Sample 1~10（JSON 實驗資料）"],
    horizontal=True,
    key="se_data_source"
)

col_loadbtn, _ = st.columns([2, 5])
with col_loadbtn:
    if data_source == "📄 v2 0622（Word 原始憑證）":
        if st.button("📄 載入 v2 0622 Word 憑證", use_container_width=True):
            # 用 helper 將 docx 轉成字串（和 Schedule B 相同做法）
            import schedule_a_ui_helper as _ui_helper
            st.session_state.se_input_text = _ui_helper.load_sample_data_pack_v2()
            st.rerun()
    else:
        if st.button("📥 載入 Sample 1~10 JSON", use_container_width=True):
            import schedule_a_ui_helper as _ui_helper
            st.session_state.se_input_text = _ui_helper.load_all_rivera_samples()
            st.rerun()

# 統一的文字輸入框（兩種資料集都用同一個）
st.session_state.se_input_text = st.text_area(
    "原始憑證文字（點擊上方按鈕載入，或手動貼入）：",
    value=st.session_state.se_input_text,
    height=220,
    placeholder="點擊上方按鈕載入資料，或在此直接貼入文字..."
)

# 建立操作介面
st.markdown("### ⚙️ 執行參數與設定")

taxpayer_profile_input = """Taxpayer Profile Details:
- Name: Marcus Rivera
- SSN: 555-12-3456
- Tax Year: 2025
- Filing Status: Married Filing Jointly (MFJ)
- Accounting Method: CASH
- Form 1099 compliance: Requirement status is REQUIRED, and all required forms were filed."""

col_prof, col_btn = st.columns([2, 1])
with col_prof:
    profile_text = st.text_area("申報人基本設定 (將作為上下文輸入給 LLM)", taxpayer_profile_input, height=180)

with col_btn:
    st.markdown("<br><br>", unsafe_allow_html=True)
    model_option = st.selectbox("選擇使用的 LLM 模型", ["gemini-2.5-pro", "gemini-2.5-flash"])
    is_debug = st.checkbox("啟用偵錯控制台", value=True)
    run_clicked = st.button("🚀 執行 LLM Schema 提取與計算", use_container_width=True)

if run_clicked:
    raw_input = st.session_state.get("se_input_text", "").strip()
    if not raw_input:
        st.error("請先點擊載入按鈕選取資料，或手動貼入文字。")
        st.stop()
    full_context = f"{profile_text}\n\n=== SOURCE DOCUMENTS ===\n{raw_input}"
    
    with st.spinner("⏳ 正在呼叫 LLM 進行 Schema 事實提取..."):
            t_start = time.time()
            try:
                parser = ScheduleELLMParser(model_name=model_option)
                extracted_inputs, prompt_log, raw_output = parser.parse(full_context)
                llm_latency = time.time() - t_start
                st.success(f"✅ LLM 提取完成！耗時 {llm_latency:.2f} 秒")
                
                # 儲存到 session state
                st.session_state.part1_extracted_inputs = extracted_inputs
                st.session_state.part1_prompt_log = prompt_log
                st.session_state.part1_raw_output = raw_output
                st.session_state.part1_latency = llm_latency
                
                # 執行計算
                with st.spinner("⚙️ 正在運行規則計算引擎..."):
                    calc_result = calculate_schedule_e_dynamic(extracted_inputs)
                    st.session_state.part1_calc_result = calc_result
            except Exception as e:
                st.error(f"❌ LLM 提取或解析失敗：{str(e)}")
                if is_debug:
                    st.divider()
                    st.markdown("### 🔍 提取失敗日誌")
                    st.text_area("LLM 原始回傳", str(e), height=300)

# ─── 呈現提取與計算結果 ────────────────────────────────────────────────────
if "part1_calc_result" in st.session_state:
    inputs_data = st.session_state.part1_extracted_inputs
    calc_result = st.session_state.part1_calc_result
    
    st.divider()
    
    col_l, col_r = st.columns(2)
    
    with col_l:
        st.markdown("### 📥 LLM 提取的輸入 DTO 結構")
        st.json(inputs_data)
        
    with col_r:
        st.markdown("### 📊 計算後輸出表單資料 (Part I Result)")
        st.json(calc_result)
        
    # ─── 行號視覺化對照卡片 ────────────────────────────────────────────────
    st.markdown("### 📑 Schedule E Part I 申報行號視覺對照")
    
    properties = calc_result.get("properties") or []
    if properties:
        for idx, prop in enumerate(properties):
            col_letter = prop.get("property_column") or "A"
            address = prop.get("line_1a_physical_address") or "N/A"
            prop_type = prop.get("line_1b_property_type_code") or 1
            
            with st.container():
                st.markdown(
                    f"""
                    <div class="schedule-e-card">
                        <h4>🏠 Property {col_letter}：{address}</h4>
                        <p><b>物業類型編碼 (Line 1b)：</b> {prop_type} (Single-Family Residence)<br>
                        <b>公平出租天數 (Line 2)：</b> {prop.get('line_2_fair_rental_days')} 天 | 
                        <b>個人使用天數 (Line 2)：</b> {prop.get('line_2_personal_use_days')} 天</p>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
                # 建立行號表格
                html_rows = []
                # 租金
                html_rows.append(f"<tr><td>Line 3</td><td>Rents received</td><td style='text-align:right; font-weight:bold;'>${prop.get('line_3_rents_received', 0.0):,.2f}</td></tr>")
                # 費用
                html_rows.append(f"<tr><td>Line 9</td><td>Insurance</td><td style='text-align:right;'>${prop.get('line_9_insurance', 0.0):,.2f}</td></tr>")
                html_rows.append(f"<tr><td>Line 12</td><td>Mortgage interest paid to banks, etc.</td><td style='text-align:right;'>${prop.get('line_12_mortgage_interest', 0.0):,.2f}</td></tr>")
                html_rows.append(f"<tr><td>Line 14</td><td>Repairs</td><td style='text-align:right;'>${prop.get('line_14_repairs', 0.0):,.2f}</td></tr>")
                html_rows.append(f"<tr><td>Line 16</td><td>Taxes</td><td style='text-align:right;'>${prop.get('line_16_taxes', 0.0):,.2f}</td></tr>")
                html_rows.append(f"<tr><td>Line 18</td><td>Depreciation expense or depletion</td><td style='text-align:right; color:#6366f1; font-weight:bold;'>${prop.get('line_18_depreciation', 0.0):,.2f}</td></tr>")
                
                # 總計費用
                html_rows.append(f"<tr style='background:rgba(255,255,255,0.08); font-weight:bold;'><td>Line 20</td><td>Total expenses (Lines 5-19)</td><td style='text-align:right;'>${prop.get('line_20_total_expenses', 0.0):,.2f}</td></tr>")
                
                # 淨利潤
                html_rows.append(f"<tr style='background:rgba(16,185,129,0.15); font-weight:bold; color:#10b981;'><td>Line 21</td><td>Net Income / (Loss)</td><td style='text-align:right;'>${prop.get('line_21_income_or_loss', 0.0):,.2f}</td></tr>")
                
                table_html = f"""
                <table class="field-table">
                    <thead>
                        <tr>
                            <th style="width:120px;">IRS 行號</th>
                            <th>行號描述</th>
                            <th style="text-align:right; width:180px;">申報值 (Value)</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(html_rows)}
                    </tbody>
                </table>
                """
                st.markdown(table_html, unsafe_allow_html=True)
                
    # ─── Acceptance Criteria 驗證 ──────────────────────────────────────────
    st.markdown("#### ✅ Acceptance Criteria 驗證 (v2 0622 正解比對)")
    ac_rows = []
    
    if properties:
        prop0 = properties[0]
        rents_val = prop0.get("line_3_rents_received") or 0.0
        insurance_val = prop0.get("line_9_insurance") or 0.0
        tax_val = prop0.get("line_16_taxes") or 0.0
        repairs_val = prop0.get("line_14_repairs") or 0.0
        dep_val = prop0.get("line_18_depreciation") or 0.0
        interest_val = prop0.get("line_12_mortgage_interest") or 0.0
        net_inc_val = calc_result.get("line_26_total_rental_income_or_loss") or 0.0
        
        # 1. 租金收入 $16,650
        ac1_pass = abs(rents_val - 16650.0) < 0.01
        ac_rows.append((
            "Rents Received mapped to Schedule E Line 3 ($16,650)",
            f"✅ ${rents_val:,.2f}" if ac1_pass else f"❌ ${rents_val:,.2f}",
            ac1_pass
        ))
        
        # 2. 保險 $900
        ac2_pass = abs(insurance_val - 900.0) < 0.01
        ac_rows.append((
            "Landlord Insurance Policy mapped to Schedule E Line 9 ($900)",
            f"✅ ${insurance_val:,.2f}" if ac2_pass else f"❌ ${insurance_val:,.2f}",
            ac2_pass
        ))
        
        # 3. 縣房產稅 $2,400
        ac3_pass = abs(tax_val - 2400.0) < 0.01
        ac_rows.append((
            "County Property Tax mapped to Schedule E Line 16 ($2,400)",
            f"✅ ${tax_val:,.2f}" if ac3_pass else f"❌ ${tax_val:,.2f}",
            ac3_pass
        ))
        
        # 4. 修繕費用 $550
        ac4_pass = abs(repairs_val - 550.0) < 0.01
        ac_rows.append((
            "Plumbing, Appliance and General Maintenance aggregated into Line 14 ($550)",
            f"✅ ${repairs_val:,.2f}" if ac4_pass else f"❌ ${repairs_val:,.2f}",
            ac4_pass
        ))
        
        # 5. 折舊費 $8,000
        ac5_pass = abs(dep_val - 8000.0) < 0.01
        ac_rows.append((
            "Depreciation Expense mapped/supplied to Line 18 ($8,000)",
            f"✅ ${dep_val:,.2f}" if ac5_pass else f"❌ ${dep_val:,.2f}",
            ac5_pass
        ))
        
        # 6. 利息費用 $4,800
        ac6_pass = abs(interest_val - 4800.0) < 0.01
        ac_rows.append((
            "Mortgage Interest mapped to Line 12 ($4,800)",
            f"✅ ${interest_val:,.2f}" if ac6_pass else f"❌ ${interest_val:,.2f}",
            ac6_pass
        ))
        
        # 7. 最終淨所得 $0
        ac7_pass = abs(net_inc_val - 0.0) < 0.01
        ac_rows.append((
            "Final Line 26 Net Income calculated correctly ($0.00)",
            f"✅ ${net_inc_val:,.2f}" if ac7_pass else f"❌ ${net_inc_val:,.2f}",
            ac7_pass
        ))
        
    ac_html_rows = []
    for criterion, result_str, passed in ac_rows:
        icon = "✅" if passed else "❌"
        row_color = "rgba(16,185,129,0.08)" if passed else "rgba(239,68,68,0.08)"
        ac_html_rows.append(
            f'<tr style="background:{row_color};">'
            f'<td style="font-size:1.1rem; text-align:center;">{icon}</td>'
            f"<td>{criterion}</td>"
            f'<td style="font-weight:bold; color:#a3e635;">{result_str}</td>'
            f"</tr>"
        )
        
    ac_table = f"""
    <table class="field-table">
        <thead>
            <tr>
                <th style="text-align:center; width:50px;">狀態</th>
                <th>Acceptance Criteria</th>
                <th>驗證結果</th>
            </tr>
        </thead>
        <tbody>
            {''.join(ac_html_rows)}
        </tbody>
    </table>
    """
    st.markdown(ac_table, unsafe_allow_html=True)

    # ─── Debug 偵錯控制台 ──────────────────────────────────────────────────
    if is_debug:
        st.divider()
        st.markdown("### 🔍 Debug 偵錯控制台")
        
        col_dl, col_dr = st.columns(2)
        with col_dl:
            st.markdown("#### 📡 構造出的 Extraction Prompt (System Prompt)")
            st.text_area(
                "System Prompt",
                st.session_state.part1_prompt_log,
                height=400,
                key="part1_sys_prompt"
            )
        with col_dr:
            st.markdown("#### 📥 LLM 原始回應")
            st.text_area(
                "Raw Output",
                st.session_state.part1_raw_output,
                height=400,
                key="part1_raw_out"
            )
