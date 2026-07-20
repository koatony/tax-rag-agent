import streamlit as st
import time
import os
import sys

# 將工作路徑加入系統中以正確載入專案模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 載入共享 UI 輔助模組
import schedule_a_ui_helper

# --- 安全性：密碼驗證狀態檢查 ---
schedule_a_ui_helper.verify_login()

# --- 頁面配置 ---
st.set_page_config(
    page_title="Schedule A 表單盒動態提取與計算測試",
    layout="wide"
)

# 載入自訂 CSS 樣式
schedule_a_ui_helper.inject_custom_css()

# 載入核心模組
from missing_form_detector import format_input_data
from processors.processors.schedule_a import (
    extract_schedule_a_inputs_with_logs,
    calculate_schedule_a_dynamic,
    load_schedule_a_schema
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
    st.info("💡 說明：\n1. 本系統會動態載入外部的 `schedule_a_schema.json` 規則設定檔。\n2. LLM 只負責從原始資料中定性提取 Input 欄位。\n3. Python 圖論計算引擎會自動解析依賴，完成公式求值。")

# --- 主畫面標題 ---
st.title("📋 IRS Schedule A 表單盒動態提取與計算測試 (全部)")
st.write("此頁面用於測試將整個 Schedule A 作為單一盒子 (Box) 進行填寫。LLM 會閱讀所有原始憑證資料，依據外部 JSON 規格提取 Input 欄位，再由 Python 自動執行排序與公式計算。")

# 初始化 Session 狀態
if "rivera_input_text" not in st.session_state:
    st.session_state.rivera_input_text = ""

if "test_execution_result" not in st.session_state:
    st.session_state.test_execution_result = None

# --- 載入模擬資料控制按鈕 ---
col_btn1, col_btn2, _ = st.columns([2, 2, 3])
with col_btn1:
    if st.button("📥 載入 Sample 1~10（JSON）", use_container_width=True, help="載入 data/src_json_Marcus_and_Elena/ 下的 JSON 實驗資料"):
        st.session_state.rivera_input_text = schedule_a_ui_helper.load_all_rivera_samples()
        st.rerun()
with col_btn2:
    if st.button("📄 載入 v2 0622（Word 原始憑證）", use_container_width=True, help="載入 Sample Data Pack v2 0622 的 .docx 文件"):
        st.session_state.rivera_input_text = schedule_a_ui_helper.load_sample_data_pack_v2()
        st.rerun()

# 顯示輸入框
prompt_input = st.text_area(
    "請輸入原始報稅資料 (JSON 或 Markdown 文字列表)：",
    value=st.session_state.rivera_input_text,
    height=280,
    placeholder="在此輸入或點擊上方按鈕載入模擬的 8 個 Sample 憑證資料..."
)
st.session_state.rivera_input_text = prompt_input

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
                extracted_inputs, prompt_sent, llm_raw_out = extract_schedule_a_inputs_with_logs(
                    formatted_ctx, 
                    model_name=selected_model
                )
                
                # 3. 執行 Python 公式計算
                final_state = calculate_schedule_a_dynamic(extracted_inputs)
                latency = time.time() - t0
                
                # 4. 儲存結果
                st.session_state.test_execution_result = {
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

# --- 顯示結果分頁 ---
if st.session_state.test_execution_result:
    res = st.session_state.test_execution_result
    extracted_inputs = res["extracted_inputs"]
    final_state = res["final_state"]
    prompt_sent = res["prompt_sent"]
    llm_raw_out = res["llm_raw_out"]
    latency = res["latency"]
    
    st.divider()
    st.subheader("📊 執行結果分析報告")
    
    # 耗時卡片
    st.metric("總執行耗時", f"{latency:.2f} 秒")
    
    # 顯示比較面板
    schedule_a_ui_helper.render_itemize_comparison(final_state)
    st.divider()
    
    # 建立三個展示分頁
    tab_report, tab_extracted, tab_debug = st.tabs([
        "📄 Schedule A 完整填寫結果", 
        "📦 LLM 提取原始 Input JSON", 
        "🔍 Debug 日誌 (完整 Prompt & 原始輸出)"
    ])
    
    schema = load_schedule_a_schema()
    
    with tab_report:
        st.write("以下為 Schedule A 欄位名稱與對應欄位值：")
        
        def serialize_decimal(obj):
            from decimal import Decimal
            if isinstance(obj, Decimal):
                return float(obj)
            raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")

        LEGACY_KEYS = {
            "line_1_medical_and_dental_expenses_net",
            "line_3_agi_threshold_7_5_percent",
            "line_5a_general_sales_tax_elected",
            "line_5b_amount",
            "line_5c_amount",
            "line_5d_amount",
            "line_5e_amount",
            "line_6_amount",
            "line_7_amount",
            "line_8a",
            "line_8b",
            "line_8c",
            "line_8e",
            "line_9",
            "line_10_interest",
            "line_11",
            "line_12",
            "line_13",
            "line_14_charity",
            "line_15",
            "line_16",
            "line_17_total_itemized",
            "should_itemize",
            "ssn",
            "agi"
        }
        html_rows = []
        for key, val in sorted(final_state.items()):
            if key in LEGACY_KEYS:
                continue
            # 若為 list/dict/object 則轉為 JSON 格式
            if key == "line_11_cash_contributions" and final_state.get("line_11_cash_contributions_status") == "excluded_pending_documentation":
                val_display = f"<strong style='color:#f87171;'>0.0 (excluded_pending_documentation)</strong>"
            elif isinstance(val, (dict, list)):
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
 
    with tab_extracted:
        st.write("以下為 LLM 根據規格所提取出來的原始 JSON 資料：")
        st.json(extracted_inputs)
        
    with tab_debug:
        st.write("本分頁提供完整的計算追蹤、LLM Prompt 與模型原始回應：")
        
        # 計算與來源詳細追蹤表
        schedule_a_ui_helper.render_calculation_trace_table(final_state, schema, "LLM 自文件直接定性分類提取")
        
        st.divider()
        
        # 顯示依賴排序順序
        schedule_a_ui_helper.render_topological_chain(schema, final_state)
        
        st.divider()
        
        # 顯示發送的 Prompt
        st.markdown("#### 📡 輸入給 LLM 的完整 Prompt")
        st.text_area("LLM Prompt Sent", prompt_sent, height=350, key="log_prompt_sent")
        
        # 顯示 LLM 完整原始輸出
        st.markdown("#### 📥 LLM 的完整 Raw Output 輸出")
        st.text_area("LLM Raw Response Received", llm_raw_out, height=250, key="log_llm_raw_out")
