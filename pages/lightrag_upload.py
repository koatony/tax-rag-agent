import streamlit as st
import requests

if not st.session_state.get("password_correct", False):
    st.error("請先回到主頁面登入")
    st.stop()

LIGHTRAG_BASE_URL = "http://127.0.0.1:9629"
LIGHTRAG_UPLOAD_URL = f"{LIGHTRAG_BASE_URL}/documents/upload"

st.title("LightRAG 文件上傳")
st.caption("支援格式：PDF、TXT、MD、DOCX")

# 顯示目前 LightRAG server 的 workspace 資訊
try:
    health = requests.get(f"{LIGHTRAG_BASE_URL}/health", timeout=5).json()
    working_dir = health.get("working_directory", "未知")
    workspace = health.get("configuration", {}).get("workspace") or working_dir.split("/")[-1]
    st.info(f"📂 上傳目標 Workspace：`{workspace}`")
except Exception:
    st.warning("⚠️ 無法連線至 LightRAG server（127.0.0.1:9629），請確認 server 已啟動")

uploaded_files = st.file_uploader(
    "選擇文件（可多選）",
    type=["pdf", "txt", "md", "docx", "json"],
    accept_multiple_files=True,
)

if uploaded_files and st.button("上傳至 LightRAG", type="primary", use_container_width=True):
    for f in uploaded_files:
        with st.spinner(f"上傳中：{f.name} ..."):
            try:
                resp = requests.post(
                    LIGHTRAG_UPLOAD_URL,
                    files={"file": (f.name, f.getvalue(), f.type)},
                    headers={"accept": "application/json"},
                    timeout=120,
                )
                resp.raise_for_status()
                st.success(f"✅ {f.name} 上傳成功")
                st.json(resp.json())
            except requests.HTTPError as e:
                st.error(f"❌ {f.name} 上傳失敗（HTTP {e.response.status_code}）：{e.response.text}")
            except Exception as e:
                st.error(f"❌ {f.name} 上傳失敗：{e}")
