import streamlit as st
import httpx
import json
import time
import re
import os
import html
import asyncio
from typing import List, Dict, Tuple

# --- 安全性：密碼驗證狀態檢查 ---
if not st.session_state.get("password_correct", False):
    st.error("請先回到主頁面登入")
    st.stop()

# --- 頁面基本配置 ---
st.set_page_config(
    page_title="AI 缺失表單與申報障礙稽核",
    layout="wide"
)

# --- 載入自訂 CSS 樣式 ---
st.markdown("""
    <style>
    /* 已移除全局背景色覆蓋以相容 Streamlit 主題 */
    .metric-box {
        padding: 10px 15px;
        margin-bottom: 8px;
    }
    </style>
""", unsafe_allow_html=True)

API_URL = "http://localhost:8088/detect-missing-forms"

# --- 輔助函式：解析實驗格式的輸出內容 ---
def parse_results(content: str) -> List[Dict[str, str]]:
    items = []
    parts = re.split(r"### 🚩\s*(?:標記：)?", content)
    for part in parts:
        part = part.strip()
        if not part:
            continue
            
        lines = part.split("\n")
        flag_name = lines[0].strip()
        remaining_text = "\n".join(lines[1:])
        
        def get_field(label_pattern, text):
            # Matches "- **label**: text" or "- label: text"
            m = re.search(r"-\s*\*?\*?" + label_pattern + r"\*?\*?:\s*(.*)", text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                val = re.sub(r"^\*\*|\*\*", "", val).strip()
                return val
            return ""
            
        target_component = get_field(r"受影響表單/科目 \(Target Component\)", remaining_text)
        risk_level = get_field(r"風險等級 \(Risk Level\)", remaining_text)
        requires_cpa = get_field(r"是否需要 CPA 裁量與審查 \(Requires CPA Review\)", remaining_text)
        
        def get_long_field(label_pattern, text):
            # Matches up to the next bullet point starting with "- " or end of text
            pattern = r"-\s*\*?\*?" + label_pattern + r"\*?\*?:\s*(.*?)(?=\n\s*-\s*\*?|$)"
            m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                val = re.sub(r"^\*\*|\*\*", "", val).strip()
                return val
            return ""
            
        explanation = get_long_field(r"稅法依據與說明 \(Explanation & Tax Law Basis\)", remaining_text)
        follow_up = get_long_field(r"後續 Action / 確認事項 \(Follow-up Actions\)", remaining_text)
        source_doc = get_long_field(r"來源憑證檔案 \(Source Document\)", remaining_text)
        
        if not explanation:
            explanation = get_field(r"稅法依據與說明 \(Explanation & Tax Law Basis\)", remaining_text)
        if not follow_up:
            follow_up = get_field(r"後續 Action / 確認事項 \(Follow-up Actions\)", remaining_text)
        if not source_doc:
            source_doc = get_field(r"來源憑證檔案 \(Source Document\)", remaining_text)
            
        if not target_component and not risk_level:
            continue
            
        items.append({
            "flag_name": flag_name,
            "target_component": target_component or "N/A",
            "risk_level": risk_level or "Low",
            "requires_cpa": requires_cpa or "No",
            "explanation": explanation or "N/A",
            "follow_up": follow_up or "N/A",
            "source_doc": source_doc or "None"
        })
    return items

# --- 呼叫後端 API 函式 ---
async def call_detect_missing_forms_api(question: str, strategy: str, model_name: str) -> dict:
    internal_token = os.environ.get("INTERNAL_TOKEN", "")
    headers = {"X-API-Token": internal_token}
    
    async with httpx.AsyncClient(timeout=3600.0) as client:
        payload = {
            "question": question,
            "strategy": strategy,
            "model_name": model_name
        }
        resp = await client.post(API_URL, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()

# --- 側邊欄設定 ---
with st.sidebar:
    st.header("診斷策略與設定")
    
    # 策略選單
    selected_strategy = st.radio(
        "選擇稽核推理策略",
        options=["Map-Reduce", "Looping (Stateful)"],
        index=0
    )
    
    # 模型選單 (預設 gemini-2.5-flash)
    selected_model = st.selectbox(
        "指定分析模型",
        options=["gemini-2.5-flash", "gemini-2.5-pro", "gemma4:31b"],
        index=0
    )
    
    # 界面模式
    app_mode = st.radio("界面模式", ["Normal", "Debug"], index=1)
    is_debug = (app_mode == "Debug")
    
    st.divider()
    st.info("提示：\n- Map-Reduce：速度快，對 inbound 憑證和 outbound 表單進行平行解析，噪音最低。\n- Looping (Stateful)：使用單一會話歷史進行序列追問，推理脈絡更連貫。")

# --- 主畫面 ---
st.title("AI 缺失文件與申報受阻稽核診斷")
st.write("輸入納稅人的基本資料與上傳的文件清單 JSON/純文字，AI 將精準判斷缺失的原始憑證，以及申報過程中受影響的稅務表單。")

# 初始化 session 狀態以儲存輸入框內容與分析結果
if "input_box_value" not in st.session_state:
    st.session_state.input_box_value = ""

if "diagnosis_result" not in st.session_state:
    st.session_state.diagnosis_result = None

# --- 範本載入控制 ---
col_actions_1, col_actions_2 = st.columns([1, 4])
with col_actions_1:
    if st.button("載入 Rivera 夫婦實驗數據", use_container_width=True):
        import missing_form_detector
        st.session_state.input_box_value = missing_form_detector.get_rivera_mock_data()
        st.rerun()

# 使用 text_area 作為手動輸入框
prompt_input = st.text_area(
    "請輸入納稅人檔案與已上傳文件清單 (支援 JSON 格式或純文字描述)：",
    value=st.session_state.input_box_value,
    height=320,
    placeholder="例：\n{\n  \"taxpayer_profile\": \"...\",\n  \"uploaded_documents\": [...]\n}"
)

# 保存輸入框的值
st.session_state.input_box_value = prompt_input

# --- 執行按鈕 ---
run_diagnosis = st.button("開始執行 AI 診斷", type="primary", use_container_width=True)

if run_diagnosis:
    if not prompt_input.strip():
        st.error("輸入內容不可為空！")
    else:
        with st.spinner("正在進行兩階段稅法推理與缺漏診斷中，請稍候..."):
            try:
                # 呼叫 API
                response = asyncio.run(call_detect_missing_forms_api(
                    prompt_input,
                    selected_strategy,
                    selected_model
                ))
                st.session_state.diagnosis_result = response
                st.success("診斷分析完成！")
                st.rerun()
            except Exception as e:
                st.error(f"診斷過程中發生錯誤：{e}")

# --- 顯示結果區 ---
if st.session_state.diagnosis_result:
    res = st.session_state.diagnosis_result
    answer = res.get("answer", "")
    latency = res.get("latency", 0.0)
    token_usage = res.get("token_usage", {})
    debug_info = res.get("debug_info", {})
    
    # 解析出稽核標記清單
    audit_items = parse_results(answer)
    
    st.divider()
    st.subheader("診斷報告分析結果")
    
    if audit_items:
        for item in audit_items:
            flag_name = item["flag_name"]
            target_component = item["target_component"]
            risk_level = item["risk_level"]
            requires_cpa = item["requires_cpa"]
            explanation = item["explanation"]
            follow_up = item["follow_up"]
            source_doc = item["source_doc"]
            
            with st.container(border=True):
                st.markdown(f"### 🚩 標記：{flag_name}")
                col1, col2 = st.columns(2)
                col1.markdown(f"**受影響表單/科目 (Target Component)**: `{target_component}`")
                col2.markdown(f"**風險等級 (Risk Level)**: `{risk_level}` | **需要 CPA 審查**: `{requires_cpa}`")
                
                st.markdown(f"**💡 AI 發現與稅法依據 (Explanation & Tax Law Basis)**:\n{explanation}")
                st.markdown(f"**📋 後續 CPA 行動 (CPA Action Needed)**:\n{follow_up}")
                st.markdown(f"**來源憑證檔案 (Source Document)**: `{source_doc}`")
    else:
        st.info("未發現任何稅務申報與合規疑慮項目。")
            
    # --- Debug 模式下的詳細診斷數據 ---
    if is_debug:
        st.divider()
        st.subheader("診斷耗時與 Token 消耗細節 (Debug 模式)")
        
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("診斷耗時 (Latency)", f"{latency:.2f} 秒")
        col_m2.metric("輸入 Token 數", token_usage.get("input_tokens", 0))
        col_m3.metric("輸出 Token 數", token_usage.get("output_tokens", 0))
        col_m4.metric("總共 Token 數", token_usage.get("input_tokens", 0) + token_usage.get("output_tokens", 0))
        
        # 顯示中介步驟的 Prompt 與產出
        debug_steps = debug_info.get("debug_steps", [])
        if debug_steps:
            with st.expander("檢視中介執行步驟與 Prompt / Context 明細"):
                for step_idx, step in enumerate(debug_steps):
                    phase_name = step.get("phase", "未知階段")
                    st.markdown(f"**{phase_name}**")
                    
                    if "prompts" in step:
                        # 顯示 Planner/Scanner Phase 的 Prompts 和 Output
                        for p in step["prompts"]:
                            role = p.get("role", "user")
                            content = p.get("content", "")
                            st.text_area(f"{role.capitalize()} Prompt", content, height=180, key=f"ds_{step_idx}_{phase_name}_{role}")
                        st.text_area("Output JSON", step.get("output", ""), height=150, key=f"ds_{step_idx}_{phase_name}_out")
                        st.divider()

                    elif "neo4j_query" in step:
                        # Neo4j Rules Evaluation Phase
                        neo4j_query = step.get("neo4j_query", "")
                        neo4j_raw = step.get("neo4j_raw_result", [])
                        violated = step.get("violated_rules", [])
                        extracted_context = step.get("extracted_context")

                        if extracted_context:
                            st.markdown("**🧠 第一階段 LLM 提取的結構化上下文 (Extracted Context)：**")
                            st.json(extracted_context)

                        st.markdown("**📡 實際執行的 Cypher 查詢語句：**")
                        st.code(neo4j_query, language="cypher")

                        st.markdown(f"**📦 Neo4j 原始查詢結果（共 {len(neo4j_raw)} 筆規則節點）：**")
                        if neo4j_raw:
                            st.json(neo4j_raw[:10])  # 只顯示前10筆，避免過長
                            if len(neo4j_raw) > 10:
                                st.caption(f"... 共 {len(neo4j_raw)} 筆，僅顯示前 10 筆")
                        else:
                            st.info("查詢結果為空")

                        st.markdown(f"**⚠️ 本次違反規則（共 {len(violated)} 條）：**")
                        if violated:
                            for r in violated:
                                with st.container(border=True):
                                    st.markdown(f"`{r['id']}` **({r['severity']})** — {r['message']}")
                                    col_a, col_b = st.columns(2)
                                    col_a.code(f"Trigger: {r.get('trigger_expr', '')}", language="python")
                                    col_b.code(f"Validate: {r.get('validate_expr', '')}", language="python")
                        else:
                            st.success("本次執行未觸發任何確定性違反規則")
                        st.divider()

                    elif "tasks" in step:
                        # Map Phase
                        st.markdown("各表單平行 Map 任務明細：")
                        for idx, task in enumerate(step["tasks"]):
                            form = task.get("form_name", "")
                            with st.container(border=True):
                                st.markdown(f"表單名稱：{form}")
                                st.text_area("System Prompt", task.get("prompt_system", ""), height=100, key=f"map_sys_{step_idx}_{idx}")
                                st.text_area("User Prompt", task.get("prompt_user", ""), height=150, key=f"map_usr_{step_idx}_{idx}")
                                st.text_area("Output Reason", task.get("output", ""), height=100, key=f"map_out_{step_idx}_{idx}")
                        st.divider()

                    elif "history" in step:
                        # Stateful Looping History
                        st.markdown("會話歷程紀錄 (Chat Session History)：")
                        for idx, msg in enumerate(step["history"]):
                            role = msg.get("role", "user")
                            content = msg.get("content", "")
                            st.text_area(f"[{idx+1}] {role.capitalize()}", content, height=120 if role == "user" else 80, key=f"loop_history_{step_idx}_{idx}")
                        st.divider()

        with st.expander("檢視原始 API 生成內容"):
            st.text_area("LLM Output Text", answer, height=250)
            
        with st.expander("檢視 Planner 輸出的 JSON 資料"):
            raw_json = debug_info.get("raw_json", {})
            st.json(raw_json)
