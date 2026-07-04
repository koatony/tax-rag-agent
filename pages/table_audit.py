import streamlit as st
import requests
import json
import time

# --- Debug 渲染函式 ---
def render_audit_debug(data: dict):
    t_usage = data.get("token_usage", {})
    cols = st.columns(4)
    cols[0].metric("耗時 (Latency)", f"{data.get('latency', 0):.2f}s")
    cols[1].metric("輸入 Token", t_usage.get("input_tokens", 0))
    cols[2].metric("輸出 Token", t_usage.get("output_tokens", 0))
    cols[3].metric("總計 Token", t_usage.get("input_tokens", 0) + t_usage.get("output_tokens", 0))

    st.divider()
    st.subheader("步驟 2: 候選規則 (分層排名)")
    candidates = data.get("rule_candidates", [])
    if candidates:
        display = [{
            "排名": i + 1,
            "等級": f"T{c.get('tier', 3)}",
            "來源": ", ".join(c.get("sources", [])),
            "最終分數": round(c.get("final_score", 0), 4),
            "規則 ID": c.get("rule_id", "N/A"),
            "描述": c.get("rule_description", "")
        } for i, c in enumerate(candidates)]
        st.dataframe(display, use_container_width=True, height=400)
    
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("檢視完整 Prompt")
        st.text_area("Prompt Content", data.get("debug_info", {}).get("full_prompt_sent", "N/A"), height=400)
    with col_b:
        st.subheader("檢視組裝後的 Context")
        st.text_area("Context Content", data.get("context", "N/A"), height=400)

# 檢查登入狀態
if not st.session_state.get("password_correct", False):
    st.error("請先回到主頁面登入")
    st.stop()

if "is_parsing" not in st.session_state:
    st.session_state.is_parsing = False
    
# --- 模型清單維護 ---
MODEL_LIST = [
    "gemma4:26b",
    "gemma4:31b",
    "qwen3.6:35b",
]

def call_ocr_api(uploaded_file, model_name):
    target_url = "http://140.115.54.89:7777/extract-w2"
    params = {"model_name": model_name}
    
    files = {
        "file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)
    }
    headers = {"accept": "application/json"}
    
    response = requests.post(target_url, params=params, files=files, headers=headers, timeout=350)
    response.raise_for_status()
    return response.json()

# --- 側邊欄設定 ---
with st.sidebar:
    st.header("審核設定 / Audit Settings")
    app_mode = st.radio("界面模式", ["Normal", "Debug"], index=1)
    is_debug = (app_mode == "Debug")
    
    selected_model = st.selectbox(
        "選擇解析模型",
        options=MODEL_LIST,
        index=0
    )
    st.warning("⚠️ **開發中功能**：此頁面除了解析外，還包含表格缺漏判斷功能。")
    st.divider()
    st.info(f"目前使用模型: {selected_model}")

st.title("📑 Table Audit & Validation")
st.info("此頁面用於解析稅務表格並判斷是否存在資訊缺漏。")

uploaded_file = st.file_uploader("上傳表單圖片 (JPG/PNG)", type=["png", "jpg", "jpeg"])

if uploaded_file:
    file_key = f"audit_result_{uploaded_file.name}"
    
    img_scale = st.slider("圖片顯示大小 (Width %)", min_value=10, max_value=100, value=60, disabled=st.session_state.is_parsing)
   
    col_left, col_right = st.columns([1, 1], gap="large")
    
    with col_left:
        st.subheader("Image Preview")
        st.image(uploaded_file, width=int(img_scale * 10)) 
    
    with col_right:
        st.subheader(f"解析與分析 ({selected_model})")
        
        run_button = st.button(
            "開始分析 / Run Audit", 
            use_container_width=True, 
            disabled=st.session_state.is_parsing,
            type="primary"
        )
        
        if run_button:
            # 清除舊的結果
            keys_to_delete = [
                k for k in st.session_state.keys() 
                if k.startswith(f"audit_result_{uploaded_file.name}")
            ]
            for k in keys_to_delete:
                del st.session_state[k]
            
            st.session_state.is_parsing = True
            st.rerun()
                
        if st.session_state.is_parsing:
            try:
                with st.spinner(f"正在使用 {selected_model} 進行解析與審核..."):
                    api_response = call_ocr_api(uploaded_file, selected_model)
                    
                    if "data" in api_response and isinstance(api_response["data"], str):
                        from json_repair import repair_json
                        repaired_data = repair_json(api_response["data"])
                        st.session_state[file_key] = json.loads(repaired_data)
                    else:
                        st.session_state[file_key] = api_response.get("data", api_response)
                    
                    st.session_state[f"time_{file_key}"] = api_response.get("time_cost", "N/A")
                    st.rerun()
            except Exception as e:
                st.error(f"解析失敗: {e}")
            finally:
                st.session_state.is_parsing = False
                st.rerun()

        # --- 顯示與分析區 ---
        if file_key in st.session_state:
            parsed_data = st.session_state[file_key]
            
            # 建立分頁標籤：一邊顯示資料，一邊顯示你的「缺漏判斷」
            tab1, tab2 = st.tabs(["Raw Data / 編輯資料", "🔍 Missing Value Audit / 缺漏判斷"])
            
            with tab1:
                st.caption(f"⏱️ 解析耗時: {st.session_state.get(f'time_{file_key}', 'N/A')} s")
                with st.container(height=500):
                    for key, value in parsed_data.items():
                        st.write(f"**{key}**")
                        if isinstance(value, list):
                            updated_list = []
                            for i, item in enumerate(value):
                                new_item = st.text_input(label=f"{key}_{i}", value=str(item), key=f"in_{file_key}_{key}_{i}", label_visibility="collapsed")
                                updated_list.append(new_item)
                            st.session_state[file_key][key] = updated_list
                        else:
                            new_val = st.text_input(label=key, value=str(value), key=f"in_{file_key}_{key}", label_visibility="collapsed")
                            st.session_state[file_key][key] = new_val
                        st.divider()

            with tab2:
                st.subheader("🔍 AI 報稅缺失診斷")
                st.write("根據當前的 W-2 內容，AI 將結合 IRS 法規判斷您的申報完整性。")
                
                # 建立診斷按鈕
                if st.button("🚀 執行 AI 缺漏診斷", use_container_width=True, type="primary"):
                    with st.spinner("正在檢索 IRS 法規並分析中..."):
                        try:
                            # 1. 準備檢索器 (與主程式相同邏輯)
                            from retriever import IRACRetriever
                            retriever = IRACRetriever.from_active_kgs()
                            
                            # 2. 組裝問題：將目前的 JSON 資料轉為文字描述
                            current_json = st.session_state[file_key]
                            query_text = (
                                f"以下是從 W-2 表格解析出的 JSON 內容：\n{json.dumps(current_json, indent=2, ensure_ascii=False)}\n\n"
                                "請推測用戶需要填寫哪些主要的報稅表格，並根據 W-2 的跡象，判斷用戶是否還缺少其他輔助文件或證明。"
                            )
                            
                            # 3. 執行檢索 (會自動套用我們剛才在 prompts.py 改的新指令)
                            t0 = time.time()
                            result = retriever.retrieve(query_text)
                            latency = time.time() - t0
                            
                            # 將結果存入 session_state 以便 Debug 顯示
                            result["latency"] = latency
                            st.session_state[f"rag_result_{uploaded_file.name}"] = result
                            
                            st.rerun() # 重新渲染以顯示結果
                                
                        except Exception as e:
                            st.error(f"診斷過程中發生錯誤: {e}")
                            import traceback
                            st.code(traceback.format_exc())

                # --- 顯示診斷結果 ---
                rag_res_key = f"rag_result_{uploaded_file.name}"
                if rag_res_key in st.session_state:
                    res = st.session_state[rag_res_key]
                    st.divider()
                    st.markdown("### 🤖 稽核專家診斷結果")
                    st.markdown(res.get("answer", "無法生成診斷結果。"))
                    

                # --- 基礎缺漏檢查 (原有的簡單邏輯) ---
                st.divider()
                st.subheader("基礎欄位檢查 (Raw Check)")
                missing_fields = [k for k, v in parsed_data.items() if not v or str(v).strip() == "" or v == "None"]
                if missing_fields:
                    st.error(f"偵測到 {len(missing_fields)} 個解析結果為空的欄位：")
                    st.write(missing_fields)
                else:
                    st.success("✅ 基礎欄位解析完整。")

        else:
            if not run_button:
                st.info("請上傳檔案並點擊 [開始分析] 按鈕。")

    # --- Debug Mode 全寬顯示區 ---
    if is_debug and uploaded_file:
        rag_res_key = f"rag_result_{uploaded_file.name}"
        if rag_res_key in st.session_state:
            st.divider()
            st.subheader("🛠️ RAG 診斷數據 (Debug Full-Width Mode)")
            render_audit_debug(st.session_state[rag_res_key])
