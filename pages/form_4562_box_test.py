import streamlit as st
import time
import os
import sys
import zipfile
import xml.etree.ElementTree as ET

# 將工作路徑加入系統中以正確載入專案模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 載入共享 UI 輔助模組
import schedule_a_ui_helper

# --- 安全性：密碼驗證狀態檢查 ---
schedule_a_ui_helper.verify_login()

# --- 頁面配置 ---
st.set_page_config(
    page_title="Form 4562 表單盒動態提取與計算測試",
    layout="wide"
)

# 載入自訂 CSS 樣式
schedule_a_ui_helper.inject_custom_css()

# 載入核心模組
from missing_form_detector import format_input_data
from form_4562_processor import (
    extract_form_4562_inputs_with_logs,
    calculate_form_4562_dynamic,
    load_form_4562_schema
)

# --- 側邊欄控制與模型選擇 ---
with st.sidebar:
    st.header("⚙️ 執行參數設定")

    # 支援模型測試
    selected_model = st.selectbox(
        "選擇分析模型",
        options=["gemini-2.5-pro", "gemini-2.5-flash"],
        index=0
    )

    app_mode = st.radio("界面模式", ["Normal", "Debug"], index=1)
    is_debug = (app_mode == "Debug")

    st.divider()
    st.info("💡 說明：\n1. 本系統會動態載入外部的 `form_4562_schema.json` 規則設定檔。\n2. LLM 只負責從原始資料中定性提取 Input 欄位。\n3. Python 圖論計算引擎會自動解析依賴，完成公式求值。\n4. Part III MACRS 折舊僅接收已計算完成之個別資產折舊金額，不自行依折舊率表推算。")

# --- 主畫面標題 ---
st.title("📋 IRS Form 4562 表單盒動態提取與計算測試")
st.write("此頁面用於測試將整個 Form 4562 作為單一盒子 (Box) 進行填寫。LLM 會閱讀所有原始憑證資料，依據外部 JSON 規格提取 Input 欄位，再由 Python 自動執行排序與公式計算。")

# 初始化 Session 狀態
if "rivera_input_text_4562" not in st.session_state:
    st.session_state.rivera_input_text_4562 = ""

if "test_execution_result_4562" not in st.session_state:
    st.session_state.test_execution_result_4562 = None

# --- Docx 提取函數 ---
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

# --- 載入模擬資料控制按鈕 ---
col_btn1, col_btn2, _ = st.columns([2, 2, 3])
with col_btn1:
    if st.button("📥 載入 Sample 1~10（JSON）", use_container_width=True, help="載入 data/src_json_Marcus_and_Elena/ 下的 JSON 實驗資料"):
        st.session_state.rivera_input_text_4562 = schedule_a_ui_helper.load_all_rivera_samples()
        st.rerun()
with col_btn2:
    if st.button("📄 載入 v2 0622（Word 原始憑證）", use_container_width=True, help="載入 Sample Data Pack v2 0622 的 .docx 文件"):
        st.session_state.rivera_input_text_4562 = load_sample_data_pack_v2()
        st.rerun()

# 顯示輸入框
prompt_input = st.text_area(
    "請輸入原始報稅資料 (JSON 或 Markdown 文字列表)：",
    value=st.session_state.rivera_input_text_4562,
    height=280,
    placeholder="在此輸入或點擊上方按鈕載入模擬的 Word 憑證資料..."
)
st.session_state.rivera_input_text_4562 = prompt_input

# --- 執行按鈕 ---
run_btn = st.button("🚀 開始執行表單盒提取與計算", type="primary", use_container_width=True)

if run_btn:
    if not prompt_input.strip():
        st.error("輸入內容不可為空！")
    else:
        with st.spinner("正在呼叫 LLM 進行欄位提取並執行拓撲公式計算..."):
            t0 = time.time()
            try:
                # 1. 格式化輸入
                formatted_ctx = format_input_data(prompt_input)

                # 2. 呼叫提取函數，取得 Input 欄位、Prompt 與 LLM 完整輸出
                extracted_inputs, prompt_sent, llm_raw_out = extract_form_4562_inputs_with_logs(
                    formatted_ctx,
                    model_name=selected_model
                )

                # 3. 執行 Python 公式計算
                final_state = calculate_form_4562_dynamic(extracted_inputs)
                latency = time.time() - t0

                # 4. 儲存結果
                st.session_state.test_execution_result_4562 = {
                    "extracted_inputs": extracted_inputs,
                    "final_state": final_state,
                    "prompt_sent": prompt_sent,
                    "llm_raw_out": llm_raw_out,
                    "latency": latency
                }
                st.success("執行成功！")
                st.rerun()
            except Exception as e:
                st.error(f"執行過程中發生錯誤：{e}")

# --- 顯示結果 ---
if st.session_state.test_execution_result_4562:
    res = st.session_state.test_execution_result_4562
    extracted_inputs = res["extracted_inputs"]
    final_state = res["final_state"]
    prompt_sent = res["prompt_sent"]
    llm_raw_out = res["llm_raw_out"]
    latency = res["latency"]

    st.divider()
    st.subheader("📊 執行結果分析報告")

    # 耗時卡片
    st.metric("總執行耗時", f"{latency:.2f} 秒")

    # 建立三個展示分頁
    tab_report, tab_extracted, tab_debug = st.tabs([
        "📄 Form 4562 欄位與欄位值",
        "📦 LLM 提取原始 Input JSON",
        "🔍 Debug 日誌 (完整 Prompt & 原始輸出)"
    ])

    schema = load_form_4562_schema()

    with tab_report:
        st.write("以下為 Form 4562 欄位名稱與對應欄位值：")

        # 建立一個簡單的欄位與值表格
        def serialize_decimal(obj):
            from decimal import Decimal
            if isinstance(obj, Decimal):
                return float(obj)
            raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

        html_rows = []
        for key, val in sorted(final_state.items()):
            # 若為 list/dict/object 則轉為 JSON 格式
            if isinstance(val, (dict, list)):
                import json
                val_display = f"<code>{json.dumps(val, default=serialize_decimal, ensure_ascii=False)}</code>"
            elif isinstance(val, float) or hasattr(val, "as_tuple"): # Decimal
                val_display = f"<strong style='color:#a3e635;'>{val}</strong>"
            elif isinstance(val, bool):
                val_display = "✅ True" if val else "❌ False"
            else:
                val_display = str(val)

            # 從 schema 中尋找說明
            desc = ""
            for inp in schema.get("inputs", []):
                if inp["id"] == key:
                    desc = inp.get("description", "")
                    break
            if not desc:
                for formula in schema.get("formulas", []):
                    if formula["id"] == key:
                        desc = formula.get("description", "")
                        break

            html_rows.append(
                f"<tr>"
                f"<td style='font-family:monospace; font-weight:bold;'>{key}</td>"
                f"<td>{desc}</td>"
                f"<td>{val_display}</td>"
                f"</tr>"
            )

        table_html = (
            f"<table class='field-table'>"
            f"<thead><tr><th>欄位名稱 (Key)</th><th>欄位描述</th><th>欄位值 (Value)</th></tr></thead>"
            f"<tbody>{''.join(html_rows)}</tbody>"
            f"</table>"
        )
        st.markdown(table_html, unsafe_allow_html=True)

        # --- Part I / Part III 明細逐列表格 (將陣列欄位展開為表格，方便對照官方表單) ---
        import pandas as pd

        section_179_entries = final_state.get("section_179_entries") or []
        if section_179_entries:
            st.markdown("#### 📋 Part I Line 6 — Section 179 財產明細")
            st.dataframe(pd.DataFrame(section_179_entries), use_container_width=True, hide_index=True)

        macrs_gds_entries = final_state.get("macrs_gds_entries") or []
        if macrs_gds_entries:
            st.markdown("#### 📋 Part III Section B — GDS 資產折舊明細 (Line 19a-19j)")
            st.dataframe(pd.DataFrame(macrs_gds_entries), use_container_width=True, hide_index=True)

        macrs_ads_entries = final_state.get("macrs_ads_entries") or []
        if macrs_ads_entries:
            st.markdown("#### 📋 Part III Section C — ADS 資產折舊明細 (Line 20a-20e)")
            st.dataframe(pd.DataFrame(macrs_ads_entries), use_container_width=True, hide_index=True)

    with tab_extracted:
        st.write("以下為 LLM 根據規格所提取出來的原始 JSON 資料：")
        st.json(extracted_inputs)

    with tab_debug:
        st.write("本分頁提供完整的 LLM Prompt 與模型原始回應：")

        # 顯示發送的 Prompt
        st.markdown("#### 📡 輸入給 LLM 的完整 Prompt")
        st.text_area("LLM Prompt Sent", prompt_sent, height=350, key="log_prompt_sent")

        # 顯示 LLM 完整原始輸出
        st.markdown("#### 📥 LLM 的完整 Raw Output 輸出")
        st.text_area("LLM Raw Response Received", llm_raw_out, height=250, key="log_llm_raw_out")
