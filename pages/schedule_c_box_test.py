import streamlit as st
import time
import os
import sys

# 將工作路徑加入系統中以正確載入專案模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 載入共享 UI 輔助模組
import schedule_c_ui_helper

# --- 安全性：密碼驗證狀態檢查 ---
schedule_c_ui_helper.verify_login()

# --- 頁面配置 ---
st.set_page_config(
    page_title="Schedule C 表單盒動態提取與計算測試",
    layout="wide"
)

# 載入自訂 CSS 樣式
schedule_c_ui_helper.inject_custom_css()

# 載入核心模組
from missing_form_detector import format_input_data
from schedule_c_processor import (
    extract_schedule_c_inputs_with_logs,
    calculate_schedule_c_dynamic,
    load_schedule_c_schema
)

# --- 側邊欄控制與模型選擇 ---
with st.sidebar:
    st.header("⚙️ 執行參數設定")
    
    # 支援三種模型測試
    selected_model = st.selectbox(
        "選擇分析模型",
        options=["gemma4:31b", "gemma4:26b", "qwen3.6:35b", "gemini-2.5-flash", "gemini-2.5-pro"],
        index=0
    )
    
    app_mode = st.radio("界面模式", ["Normal", "Debug"], index=1)
    is_debug = (app_mode == "Debug")
    
    st.divider()
    st.info("💡 說明：\n1. 本系統會動態載入外部的 `schedule_c_schema.json` 規則設定檔。\n2. LLM 只負責從原始資料中定性提取 Input 欄位。\n3. Python 圖論計算引擎會自動解析依賴，完成公式求值。")

# --- 主畫面標題 ---
st.title("📋 IRS Schedule C 表單盒動態提取與計算測試")
st.write("此頁面用於測試將整個 Schedule C 作為單一盒子 (Box) 進行填寫。LLM 會閱讀所有原始 W-2, QuickBooks 等憑證資料，依據外部 JSON 規格提取 Input 欄位，再由 Python 自動執行排序與公式計算。")

# 初始化 Session 狀態
if "rivera_input_text" not in st.session_state:
    st.session_state.rivera_input_text = ""

if "test_execution_result" not in st.session_state:
    st.session_state.test_execution_result = None

# --- 載入模擬資料控制按鈕 ---
col_btn1, col_btn2, _ = st.columns([2, 2, 3])
with col_btn1:
    if st.button("📥 載入 Sample 1~10（JSON）", use_container_width=True, help="載入 data/src_json_Marcus_and_Elena/ 下的 JSON 實驗資料"):
        st.session_state.rivera_input_text = schedule_c_ui_helper.load_all_rivera_samples()
        st.rerun()
with col_btn2:
    if st.button("📄 載入 v2 0622（Word 原始憑證）", use_container_width=True, help="載入 Sample Data Pack v2 0622 的 .docx 文件"):
        st.session_state.rivera_input_text = schedule_c_ui_helper.load_sample_data_pack_v2()
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
                extracted_inputs, prompt_sent, llm_raw_out = extract_schedule_c_inputs_with_logs(
                    formatted_ctx, 
                    model_name=selected_model
                )
                
                # 3. 執行 Python 公式計算
                final_state = calculate_schedule_c_dynamic(extracted_inputs)
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
    
    # 建立三個展示分頁
    tab_report, tab_extracted, tab_debug = st.tabs([
        "📄 Schedule C 完整填寫結果", 
        "📦 LLM 提取原始 Input JSON", 
        "🔍 Debug 日誌 (完整 Prompt & 原始輸出)"
    ])
    
    schema = load_schedule_c_schema()
    
    with tab_report:
        st.write("以下為此申報人的 Schedule C 國稅局標準申報欄位填寫結果 (非標準之計算中間變數已自動隱藏)：")
        
        # 顯示基本資料
        schedule_c_ui_helper.render_general_info(final_state, schema)
                
        # 欄位詳細表格 (僅顯示標準 IRS 欄位)
        schedule_c_ui_helper.render_standard_fields_table(final_state, schema)

    with tab_extracted:
        st.write("以下為 LLM 根據規格所提取出來的原始 JSON 資料（包含直接輸入欄位與 Conditional 底層細項變數）：")
        st.json(extracted_inputs)
        
    with tab_debug:
        st.write("本分頁提供完整的計算追蹤、LLM Prompt 與模型原始回應。這有助於稽核與 Debug 整個規則引擎的計算過程：")
        
        # 計算與來源詳細追蹤表
        schedule_c_ui_helper.render_calculation_trace_table(final_state, schema, "LLM 自文件直接定性分類提取")
        
        st.divider()
        
        # 顯示依賴排序順序
        schedule_c_ui_helper.render_topological_chain(schema, final_state)
        
        # 顯示發送的 Prompt
        st.markdown("#### 📡 輸入給 LLM 的完整 Prompt")
        st.text_area("LLM Prompt Sent", prompt_sent, height=350, key="log_prompt_sent")
        
        # 顯示 LLM 完整原始輸出
        st.markdown("#### 📥 LLM 的完整 Raw Output 輸出")
        st.text_area("LLM Raw Response Received", llm_raw_out, height=250, key="log_llm_raw_out")
