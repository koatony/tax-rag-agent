import streamlit as st
import httpx
import json
import time
import os
from typing import List, Dict
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

# --- 語系設定字典 ---
UI_TEXT = {
    "zh": {
        "page_title": "IRAC Tax RAG 診斷主控台",
        "sidebar_title": "系統控制與診斷",
        "mode_label": "選擇界面模式",
        "lang_label": "界面語言設定 (UI Language)",
        "config_header": "配置 (Config)",
        "clear_chat": "清除對話",
        "main_title": "Tax RAG",
        "status_normal": "當前處於：普通模式",
        "status_debug": "當前處於：偵錯模式",
        "diag_data": "診斷數據",
        "input_placeholder": "請輸入您的問題...",
        "searching": "檢索中...",
        "latency": "耗時 (Latency)",
        "in_tokens": "輸入 Token",
        "out_tokens": "輸出 Token",
        "total_tokens": "總計 Token",
        "candidates_header": "步驟 2: 候選規則 (分層)",
        "col_rank": "排名",
        "col_tier": "等級",
        "col_source": "來源",
        "col_score": "最終分數",
        "col_init_score": "初始分數",
        "col_id": "規則 ID",
        "col_desc": "描述",
        "no_candidates": "無候選規則。",
        "view_prompt": "檢視完整 Prompt",
        "view_context": "檢視組裝後的 Context",
        "view_decomposed": "檢視問題重寫結果",
        "query_bundle": "查詢束 (Query Bundle)",
        "fail": "失敗"
    },
    "en": {
        "page_title": "IRAC Tax RAG Diagnostic Console",
        "sidebar_title": "System Control & Diagnostics",
        "mode_label": "Interface Mode",
        "lang_label": "UI Language Settings",
        "config_header": "Configuration",
        "clear_chat": "Clear Conversation",
        "main_title": "Tax RAG",
        "status_normal": "Current Mode: Normal",
        "status_debug": "Current Mode: Debug",
        "diag_data": "Diagnostic Data",
        "input_placeholder": "Enter your question...",
        "searching": "Searching...",
        "latency": "Latency",
        "in_tokens": "Input Tokens",
        "out_tokens": "Output Tokens",
        "total_tokens": "Total Tokens",
        "candidates_header": "Step 2: Rule Candidates (Tiered)",
        "col_rank": "Rank",
        "col_tier": "Tier",
        "col_source": "Source",
        "col_score": "Final Score",
        "col_init_score": "Initial Score",
        "col_id": "Rule ID",
        "col_desc": "Description",
        "no_candidates": "No candidates found.",
        "view_prompt": "View Full Prompt",
        "view_context": "View Assembled Context",
        "view_decomposed": "View Decomposed Query",
        "query_bundle": "Query Bundle",
        "fail": "Failed"
    }
}

# --- 頁面配置 ---
st.set_page_config(
    page_title="IRAC Tax RAG",
    page_icon="",
    layout="centered",
    initial_sidebar_state="expanded"
)

# --- 隱藏特定工具元件 ---
st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
    [data-testid="stStatusWidget"] {display:none;}
    .block-container { padding-top: 5rem; }
    </style>
""", unsafe_allow_html=True)

# --- 常數 ---
API_URL = "http://localhost:8088/query"

# --- Session 狀態 ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- 密碼驗證 ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True
    def password_entered():
        # 同時檢查環境變數中的 APP_PASSWORD，增加安全性
        if st.session_state["password"] == os.environ.get("APP_PASSWORD", "1234"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    st.text_input("請輸入存取密碼 / Password", type="password", on_change=password_entered, key="password")
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("密碼錯誤 / Password incorrect")
    return False

if not check_password():
    st.stop()

# --- Sidebar ---
with st.sidebar:
    lang_selection = st.radio("Language", ["中文 (ZH)", "English (EN)"], index=0)
    lang = "zh" if lang_selection == "中文 (ZH)" else "en"
    T = UI_TEXT[lang]

    st.title(T["sidebar_title"])
    app_mode = st.radio(T["mode_label"], ["Normal", "Debug"], index=1)
    is_debug = (app_mode == "Debug")
    
    # --- 動態參數控制 (Diagnostic Workbench) ---
    retr_params = {}

    st.divider()
    kg_mode = os.environ.get("KG_MODE", "local").upper()
    workspace = os.environ.get("NEO4J_WORKSPACE", "N/A")
    st.info(f"Backend: **{kg_mode}**\n\nWorkspace: `{workspace}`")
    
    st.divider()
    if st.button(T["clear_chat"], use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# --- API ---
async def call_rag_api(question: str, force_english: bool = False, params: dict = None) -> Dict:
    internal_token = os.environ.get("INTERNAL_TOKEN", "tax-rag-secret-token")
    headers = {"X-API-Token": internal_token}
    
    async with httpx.AsyncClient(timeout=1800.0) as client:
        payload = {"question": question, "force_english": force_english}
        # 合併動態參數
        if params:
            payload.update(params)
            
        resp = await client.post(API_URL, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()

# --- Helpers ---
def render_debug_info(data: Dict, T: Dict, unique_key: str):
    t_usage = data.get("token_usage", {})
    col1, col2 = st.columns(2)
    col1.metric(T["latency"], f"{data.get('latency', 0):.2f}s")
    col1.metric(T["total_tokens"], t_usage.get("input_tokens", 0) + t_usage.get("output_tokens", 0))
    col2.metric(T["in_tokens"], t_usage.get("input_tokens", 0))
    col2.metric(T["out_tokens"], t_usage.get("output_tokens", 0))

    # --- 顯示分段耗時 (Per-Node Latency) ---
    st.divider()
    st.subheader("⏱️ 階段耗時 (Pipeline Latency)")
    
    debug_info = data.get("debug_info", {})
    # 提取所有 latency_ 開頭的欄位
    node_times = {k.replace("latency_", ""): v for k, v in debug_info.items() if k.startswith("latency_")}
    
    if node_times:
        # 定義顯示名稱對照表
        name_map = {
            "decompose": "1. 查詢拆解 (Decompose)",
            "hyde": "2. 增強生成 (StepBack/HyDE)",
            "rule_search": "3. 法規檢索 (Rule Search)",
            "fact_search": "4. 事實反查 (Fact Search)",
            "merge": "5. 合併加權 (Merge)",
            "rerank": "6. 重排序 (Rerank)",
            "build_sg": "7. 建構子圖 (Build Subgraph)",
            "fetch_text": "8. 讀取原文 (Fetch Text)",
            "assemble": "9. 組裝 Context (Assemble)",
            "fetch_table": "10. 表格獲取 (Table Data)",
            "generate": "11. 模型生成 (Generate Answer)"
        }
        
        lt_display = []
        for key, display_name in name_map.items():
            if key in node_times:
                lt_display.append({"階段 (Stage)": display_name, "耗時 (Sec)": f"{node_times[key]:.3f}s"})
        
        st.table(lt_display)
    else:
        st.info("尚無分段耗時數據 (可能是舊版快取結果)")

    st.divider()
    st.subheader(T["candidates_header"])
    candidates = data.get("rule_candidates", [])
    if candidates:
        display = [{
            T["col_rank"]: i + 1,
            T["col_tier"]: f"T{c.get('tier', 3)}",
            T["col_source"]: "Dual" if c.get("dual_hit") else "Single",
            T["col_score"]: round(c.get("final_score", 0), 4),
            T["col_id"]: c.get("rule_id", "N/A"),
            T["col_desc"]: c.get("rule_description", "")[:60] + "..."
        } for i, c in enumerate(candidates)]
        st.table(display)
    
    with st.expander(T["view_decomposed"]):
        dbg = data.get("debug_info", {})
        
        st.markdown("#### 🔍 查詢拆解 (Decompose)")
        st.markdown(f"**法規查詢 (Rule Query)**: \n> {dbg.get('rule_query', 'N/A')}")
        st.markdown(f"**事實查詢 (Fact Query)**: \n> {dbg.get('fact_query', 'N/A')}")
        
        keywords = dbg.get("keywords", [])
        if not keywords:
            st.markdown("**關鍵字 (Keywords)**: `(空)`")
        else:
            kw_str = " ".join([f"`{k}`" for k in keywords])
            st.markdown(f"**關鍵字 (Keywords)**: {kw_str}")

        st.markdown("#### 🧠 增強生成 (Query Bundle)")
        bundle = dbg.get("query_bundle", {})
        if bundle:
            if "original" in bundle:
                st.markdown("**原始提問 (Original)**:")
                st.info(bundle['original'])
            if "step_back" in bundle:
                st.markdown("**Step-Back 抽象化 (Step-Back)**:")
                st.info(bundle['step_back'])
            if "hyde" in bundle:
                st.markdown("**HyDE 假設性答案 (HyDE)**:")
                st.info(bundle['hyde'])
        else:
            st.info("未啟用或無增強生成資料")
    with st.expander(T["view_prompt"]):
        # 加上 unique_key 避免 ID 衝突
        st.text_area("Prompt", data.get("debug_info", {}).get("full_prompt_sent", "N/A"), height=300, key=f"prompt_ta_{unique_key}")
    with st.expander(T["view_context"]):
        st.markdown(data.get("context", "N/A"))

# --- Main UI ---
st.title(T["main_title"])
st.caption(T["status_debug"] if is_debug else T["status_normal"])

for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if is_debug and msg["role"] == "assistant" and "debug_payload" in msg:
            with st.expander(T["diag_data"]):
                render_debug_info(msg["debug_payload"], T, unique_key=f"hist_{i}")

if prompt := st.chat_input(T["input_placeholder"]):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            with st.spinner(T["searching"]):
                import asyncio
                response = asyncio.run(call_rag_api(prompt, force_english=(lang == "en"), params=retr_params))
            
            answer = response.get("answer", "...")
            st.markdown(answer)
            
            msg_obj = {"role": "assistant", "content": answer}
            if is_debug:
                msg_obj["debug_payload"] = response
                render_debug_info(response, T, unique_key=f"curr_{len(st.session_state.messages)}")
            st.session_state.messages.append(msg_obj)
            
        except Exception as e:
            st.error(f"{T['fail']}: {e}")
