import streamlit as st
import json
import time
import re
import os
import sys
import concurrent.futures

# 將工作路徑加入系統中以正確載入專案模組
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 載入共享 UI 輔助模組
import schedule_c_ui_helper

# --- 安全性：密碼驗證狀態檢查 ---
schedule_c_ui_helper.verify_login()

# --- 頁面配置 ---
st.set_page_config(
    page_title="Schedule C 單一欄位併發提取與計算測試",
    layout="wide"
)

# 載入自訂 CSS 樣式
schedule_c_ui_helper.inject_custom_css()

# 載入核心模組與 LLM 封裝
from missing_form_detector import format_input_data
from llm_wrappers import GeminiLLM
from processors.processors.schedule_c import (
    calculate_schedule_c_dynamic,
    load_schedule_c_schema
)
from langchain_core.messages import SystemMessage, HumanMessage

# --- 單一欄位提取邏輯 (執行緒執行) ---
def extract_single_field(field: dict, document_context: str, api_key: str) -> tuple:
    system_instruction = f"""你是一位專業的美國稅務申報與數據提取專家。
你的任務是從申報人基本資料（Taxpayer Profile）以及上傳的文件內容中，精準提取出國稅局 (IRS) Schedule C (Form 1040) 中一個特定的「直接輸入型 (Input)」或「底層非標準」欄位值。

【提取欄位】
- 欄位 ID: `{field["id"]}`
- 資料類型: `{field["type"]}`
- 欄位描述與提取規則: {field["description"]}

【提取與格式化規範】
1. 只需提取這一個特定欄位的值，請勿猜測或計算其他任何欄位。
2. 對於數值欄位 (float)，若沒有相關資訊或未提及，則直接回傳 0.0；對於布林值 (boolean)，若無資訊則回傳 false；對於字串 (string) 欄位，若無資訊則回傳 null。
3. 數值必須是純數字，不要包含任何貨幣符號 ($) 或千分位逗號 (,)。
4. 絕對不要自行計算任何毛利或總費用，直接提取收據或 PnL 中的原始對應值。例如餐飲費請提取原始總額，不要先乘以 0.5。

【輸出格式】
你必須精確返回一個符合該欄位型態的 JSON 對象，例如：
{{
  "{field["id"]}": <提取的值>
}}
直接返回乾淨的 JSON 字串，不要使用 markdown ```json ``` 區塊，也不要包含任何說明文字。
"""
    
    llm = GeminiLLM(model_name="gemini-2.5-flash", api_key=api_key, temperature=0.0)
    
    messages = [
        SystemMessage(content=system_instruction),
        HumanMessage(content=f"以下是申報人與上傳文件的相關內容，請提取指定欄位：\n\n{document_context}")
    ]
    
    t0 = time.time()
    try:
        # 呼叫 Gemini
        resp = llm.invoke(messages, response_mime_type="application/json")
        raw_output = resp.content.strip()
        
        # 清理並提取 JSON
        clean_output = re.sub(r"<think>.*?</think>", "", raw_output, flags=re.DOTALL).strip()
        match = re.search(r"\{.*\}", clean_output, re.DOTALL)
        from json_repair import repair_json
        repaired_output = repair_json(clean_output)
        data = json.loads(repaired_output)
        val = data.get(field["id"])
        
        # 根據 Schema 型態強制轉換型態
        if field["type"] == "float":
            val = float(val) if val is not None else 0.0
        elif field["type"] == "boolean":
            if val is not None:
                val = True if str(val).lower() in ["true", "1", "yes"] else False
            else:
                val = False
        elif field["type"] == "array":
            val = val if isinstance(val, list) else []
        else:
            val = val
                
        latency = time.time() - t0
        return field["id"], val, raw_output, system_instruction, latency, None
    except Exception as e:
        latency = time.time() - t0
        # 發生錯誤時返回預設值
        default_val = 0.0 if field["type"] == "float" else (False if field["type"] == "boolean" else ([] if field["type"] == "array" else None))
        return field["id"], default_val, f"錯誤: {e}", system_instruction, latency, str(e)

# --- 側邊欄控制與模型選擇 ---
with st.sidebar:
    st.header("⚙️ 執行參數設定")
    
    # 限制僅使用 2.5 flash
    st.selectbox(
        "選擇分析模型 (已鎖定)",
        options=["gemini-2.5-flash"],
        index=0,
        disabled=True
    )
    
    # 設定並發數
    concurrency = st.slider("並發執行緒數 (Max Workers)", min_value=5, max_value=25, value=15, step=5)
    
    app_mode = st.radio("界面模式", ["Normal", "Debug"], index=1)
    is_debug = (app_mode == "Debug")
    
    st.divider()
    st.info("💡 說明：\n1. 此模式會將每個 Input 欄位**拆分為獨立的 LLM 請求**，併發送給 Gemini API。\n2. 優點：LLM 專注度極高，防漏提取效果最好；缺點：請求次數較多。\n3. 使用 ThreadPoolExecutor 控制流量，防 429 資源超限。")

# --- 主畫面標題 ---
st.title("📋 IRS Schedule C 單一欄位併發提取與計算測試")
st.write("此頁面為**第二代測試方案**。在此模式中，系統會依據 Schema 的每一個欄位單獨呼叫 Gemini 2.5 Flash 進行提取，隨後在 Python 端彙整並透過拓撲公式完成全表計算。")

# 初始化 Session 狀態
if "rivera_input_text_2" not in st.session_state:
    st.session_state.rivera_input_text_2 = ""

if "test_execution_result_2" not in st.session_state:
    st.session_state.test_execution_result_2 = None

# --- 載入模擬資料控制按鈕 ---
col_actions, _ = st.columns([2, 5])
with col_actions:
    if st.button("📥 載入 Rivera 夫婦完整實驗資料 (Sample 01~08)", use_container_width=True):
        st.session_state.rivera_input_text_2 = schedule_c_ui_helper.load_all_rivera_samples()
        st.rerun()

# 顯示輸入框
prompt_input = st.text_area(
    "請輸入原始報稅資料 (JSON 或 Markdown 文字列表)：",
    value=st.session_state.rivera_input_text_2,
    height=280,
    placeholder="在此輸入或點擊上方按鈕載入模擬的 8 個 Sample 憑證資料..."
)
st.session_state.rivera_input_text_2 = prompt_input

# --- 執行按鈕 ---
run_btn = st.button("🚀 開始執行併發提取與計算", type="primary", use_container_width=True)

if run_btn:
    if not prompt_input.strip():
        st.error("輸入內容不可為空！")
    else:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            st.error("環境變數 GEMINI_API_KEY 未設定，無法呼叫 Gemini API。")
        else:
            schema = load_schedule_c_schema()
            fields = schema["inputs"]
            total_fields = len(fields)
            
            # 建立動態進度顯示器
            progress_container = st.container()
            with progress_container:
                st.write("### ⏳ 併發提取進度")
                progress_bar = st.progress(0.0)
                status_text = st.empty()
                status_text.text(f"開始排程 1 / {total_fields} ...")
                
            formatted_ctx = format_input_data(prompt_input)
            
            extracted_inputs = {}
            debug_logs = {}
            completed_count = 0
            t_start = time.time()
            
            # 使用 ThreadPoolExecutor 發送併發請求
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = {executor.submit(extract_single_field, f, formatted_ctx, api_key): f for f in fields}
                
                for future in concurrent.futures.as_completed(futures):
                    field = futures[future]
                    field_id, val, raw_out, sys_prompt, latency, err = future.result()
                    
                    extracted_inputs[field_id] = val
                    debug_logs[field_id] = {
                        "raw_output": raw_out,
                        "system_prompt": sys_prompt,
                        "latency_seconds": latency,
                        "error": err
                    }
                    
                    completed_count += 1
                    pct = completed_count / total_fields
                    progress_bar.progress(pct)
                    status_text.text(f"已完成 {completed_count} / {total_fields} 欄位 (目前完成: {field_id} | 耗時: {latency:.2f}s)...")
            
            total_latency = time.time() - t_start
            
            # 執行計算
            try:
                final_state = calculate_schedule_c_dynamic(extracted_inputs)
                
                st.session_state.test_execution_result_2 = {
                    "extracted_inputs": extracted_inputs,
                    "final_state": final_state,
                    "debug_logs": debug_logs,
                    "latency": total_latency
                }
                st.success(f"完成！總共 70+ 個欄位併發提取與計算，耗時 {total_latency:.2f} 秒！")
                st.rerun()
            except Exception as e:
                st.error(f"運算引擎在加總時發生錯誤：{e}")

# --- 顯示結果分頁 ---
if st.session_state.test_execution_result_2:
    res = st.session_state.test_execution_result_2
    extracted_inputs = res["extracted_inputs"]
    final_state = res["final_state"]
    debug_logs = res["debug_logs"]
    latency = res["latency"]
    
    st.divider()
    st.subheader("📊 執行結果分析報告")
    st.metric("總執行耗時", f"{latency:.2f} 秒")
    
    tab_report, tab_extracted, tab_debug = st.tabs([
        "📄 Schedule C 完整填寫結果", 
        "📦 彙整後的 Input JSON 資料", 
        "🔍 Debug 日誌 (單一欄位 Prompt & 完整 Trace)"
    ])
    
    schema = load_schedule_c_schema()
    
    with tab_report:
        st.write("以下為此申報人的 Schedule C 國稅局標準申報欄位填寫結果 (非標準之計算中間變數已自動隱藏)：")
        
        # 顯示基本資料
        schedule_c_ui_helper.render_general_info(final_state, schema)
                
        # 欄位詳細表格
        schedule_c_ui_helper.render_standard_fields_table(final_state, schema)
        
    with tab_extracted:
        st.write("以下為將 70+ 個欄位併發提取後彙整出的完整單一 JSON 資料：")
        st.json(extracted_inputs)
        
    with tab_debug:
        st.write("本分頁提供單一欄位的計算追蹤、拓撲鏈以及每個單一欄位的獨立 Prompt 與 Response 稽核：")
        
        # 計算與來源詳細追蹤表
        schedule_c_ui_helper.render_calculation_trace_table(final_state, schema, "LLM 併發獨立提取")
        
        st.divider()
        
        # 顯示依賴排序順序
        schedule_c_ui_helper.render_topological_chain(schema, final_state)
        
        st.divider()
        
        # 選擇單一欄位查看其專屬 Prompt/Response 日誌
        st.markdown("#### 🕵️‍♂️ 檢視單一欄位 LLM 併發日誌")
        selected_log_field = st.selectbox("選擇要檢視的欄位", options=list(debug_logs.keys()))
        
        if selected_log_field in debug_logs:
            f_log = debug_logs[selected_log_field]
            col_l, col_r = st.columns(2)
            with col_l:
                st.markdown(f"**📡 傳送給 LLM 的 System Prompt ({selected_log_field})**")
                st.text_area("System Prompt", f_log["system_prompt"], height=250, key=f"sys_pr_{selected_log_field}")
            with col_r:
                st.markdown(f"**📥 LLM 原始回應 ({selected_log_field})**")
                st.text_area("LLM Raw Response", f_log["raw_output"], height=250, key=f"raw_res_{selected_log_field}")
                st.write(f"⏱️ 耗時: `{f_log['latency_seconds']:.2f}` 秒")
                if f_log["error"]:
                    st.error(f"錯誤訊息: {f_log['error']}")
