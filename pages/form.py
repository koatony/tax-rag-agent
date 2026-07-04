import streamlit as st
import json
import io
from pdf2image import convert_from_bytes
import requests


# =========================
# Streamlit page config
# =========================
st.set_page_config(
    page_title="Form Parser",
    layout="wide"
)


# =========================
# Custom CSS
# =========================
st.markdown(
    """
    <style>
    /* Main page spacing */
    .block-container {
        padding-top: 1.4rem;
        padding-bottom: 2rem;
        max-width: 1500px;
    }

    h1, h2, h3 {
        letter-spacing: 0.2px;
    }

    /* Tabs */
    button[data-baseweb="tab"] {
        font-size: 0.95rem;
        font-weight: 600;
    }

    /* Result panel */
    .result-panel {
        border: 1px solid rgba(255, 255, 255, 0.12);
        border-radius: 16px;
        padding: 16px 18px;
        background: rgba(255, 255, 255, 0.025);
    }

    /* Field row */
    .field-row {
        padding: 7px 0 9px 0;
        border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }

    .field-label {
        font-size: 0.88rem;
        font-weight: 700;
        color: rgba(255, 255, 255, 0.9);
        padding-top: 0.35rem;
        word-break: break-word;
        line-height: 1.25rem;
    }

    /* Confidence badge */
    .conf-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 76px;
        height: 34px;
        padding: 0 10px;
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 700;
        white-space: nowrap;
        margin-top: 0.05rem;
    }

    .conf-high {
        background: rgba(34, 197, 94, 0.16);
        color: #86efac;
        border: 1px solid rgba(34, 197, 94, 0.35);
    }

    .conf-mid {
        background: rgba(234, 179, 8, 0.16);
        color: #fde68a;
        border: 1px solid rgba(234, 179, 8, 0.35);
    }

    .conf-low {
        background: rgba(239, 68, 68, 0.16);
        color: #fca5a5;
        border: 1px solid rgba(239, 68, 68, 0.35);
    }

    .conf-na {
        background: rgba(148, 163, 184, 0.12);
        color: #cbd5e1;
        border: 1px solid rgba(148, 163, 184, 0.25);
    }

    /* Streamlit input compact style */
    div[data-baseweb="input"] {
        border-radius: 10px;
    }

    div[data-testid="stTextInput"] {
        margin-bottom: 0.15rem;
    }

    /* Expander */
    details {
        border-radius: 12px !important;
    }

    details summary {
        font-weight: 700;
    }

    /* Buttons */
    .stButton > button {
        border-radius: 10px;
        font-weight: 700;
    }

    .stDownloadButton > button {
        border-radius: 10px;
        font-weight: 700;
    }

    /* Caption spacing */
    div[data-testid="stCaptionContainer"] {
        margin-bottom: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# =========================
# File processing
# =========================
def process_uploaded_files(uploaded_files):
    processed_files = []

    for uploaded_file in uploaded_files:
        uploaded_file.seek(0)

        # ===== PDF =====
        if uploaded_file.type == "application/pdf":
            pdf_bytes = uploaded_file.read()

            # Convert every PDF page to image
            pdf_images = convert_from_bytes(pdf_bytes)

            for page_idx, image in enumerate(pdf_images):
                img_bytes = io.BytesIO()
                image.save(img_bytes, format="PNG")
                img_bytes.seek(0)

                img_bytes.name = f"{uploaded_file.name}_page_{page_idx + 1}.png"
                img_bytes.type = "image/png"

                processed_files.append(img_bytes)

        # ===== Image =====
        else:
            uploaded_file.seek(0)
            processed_files.append(uploaded_file)

    return processed_files


# =========================
# API call
# =========================
def call_ocr_api(uploaded_files, model_name, thinking):
    target_url = "http://140.115.54.89:7777/extractForm"

    params = {
        "model_name": model_name,
        "thinking": thinking
    }

    headers = {
        "accept": "application/json"
    }

    files = [
        ("files", (f.name, f.getvalue(), f.type))
        for f in uploaded_files
    ]

    response = requests.post(
        target_url,
        params=params,
        files=files,
        headers=headers,
        timeout=600
    )

    response.raise_for_status()
    return response.json()


# =========================
# JSON helpers
# =========================
def parse_api_data(api_response):
    """
    API 回傳的 data 可能是 dict/list，也可能是 JSON string。
    這裡統一轉成 Python dict/list。
    """
    result_data = api_response.get("data", {})

    if isinstance(result_data, str):
        result_data = result_data.strip()

        if result_data.startswith("```"):
            result_data = (
                result_data
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )

        from json_repair import repair_json
        repaired_result_data = repair_json(result_data)
        result_data = json.loads(repaired_result_data)

    return result_data


def is_value_conf_leaf(obj):
    """
    判斷是否為欄位 leaf：

    {
        "value": "...",
        "conf_score": 0.98
    }
    """
    return (
        isinstance(obj, dict)
        and "value" in obj
        and "conf_score" in obj
    )


def render_conf_badge(conf_score):
    """
    用小 badge 顯示 confidence，不使用 st.success/st.warning/st.error，
    避免畫面變成很大的直式色塊。
    """
    try:
        score = float(conf_score)
    except (TypeError, ValueError):
        st.markdown(
            '<span class="conf-badge conf-na">N/A</span>',
            unsafe_allow_html=True
        )
        return

    if score < 0:
        badge_class = "conf-na"
        label = "N/A"
    else:
        label = f"{score * 100:.1f}%"

        if score >= 0.95:
            badge_class = "conf-high"
        elif score >= 0.85:
            badge_class = "conf-mid"
        else:
            badge_class = "conf-low"

    st.markdown(
        f'<span class="conf-badge {badge_class}">{label}</span>',
        unsafe_allow_html=True
    )


def render_editable_json(data, path, file_key):
    """
    自動根據資料結構生成輸入框。

    新格式：
    {
        "field_name": {
            "value": "...",
            "conf_score": 0.98
        }
    }

    顯示方式：
    欄位名稱 | 可編輯 value | confidence badge
    """

    # =========================
    # Dict
    # =========================
    if isinstance(data, dict):
        for key, value in data.items():
            new_path = f"{path}_{key}"

            # ===== Leaf node: {"value": ..., "conf_score": ...} =====
            if is_value_conf_leaf(value):
                st.markdown('<div class="field-row">', unsafe_allow_html=True)

                col_label, col_value, col_conf = st.columns([1.35, 2.6, 0.75])

                with col_label:
                    st.markdown(
                        f'<div class="field-label">{key}</div>',
                        unsafe_allow_html=True
                    )

                with col_value:
                    new_val = st.text_input(
                        label=key,
                        value=str(value.get("value", "")),
                        key=f"input_{file_key}_{new_path}_value",
                        label_visibility="collapsed"
                    )
                    data[key]["value"] = new_val

                with col_conf:
                    render_conf_badge(value.get("conf_score", -1))

                st.markdown('</div>', unsafe_allow_html=True)

            # ===== Nested dict =====
            elif isinstance(value, dict):
                with st.expander(f"📂 {key}", expanded=True):
                    render_editable_json(value, new_path, file_key)

            # ===== List =====
            elif isinstance(value, list):
                if len(value) == 0:
                    with st.expander(f"📂 {key}", expanded=False):
                        st.caption("No items")
                else:
                    with st.expander(f"📂 {key}", expanded=True):
                        render_editable_json(value, new_path, file_key)

            # ===== Fallback old format =====
            else:
                st.markdown('<div class="field-row">', unsafe_allow_html=True)

                col_label, col_value = st.columns([1.35, 3.35])

                with col_label:
                    st.markdown(
                        f'<div class="field-label">{key}</div>',
                        unsafe_allow_html=True
                    )

                with col_value:
                    new_val = st.text_input(
                        label=key,
                        value=str(value),
                        key=f"input_{file_key}_{new_path}",
                        label_visibility="collapsed"
                    )
                    data[key] = new_val

                st.markdown('</div>', unsafe_allow_html=True)

    # =========================
    # List
    # =========================
    elif isinstance(data, list):
        for i, item in enumerate(data):
            new_path = f"{path}_{i}"

            # list 裡面直接是 {"value": ..., "conf_score": ...}
            if is_value_conf_leaf(item):
                st.markdown('<div class="field-row">', unsafe_allow_html=True)

                col_label, col_value, col_conf = st.columns([1.35, 2.6, 0.75])

                with col_label:
                    st.markdown(
                        f'<div class="field-label">Item {i + 1}</div>',
                        unsafe_allow_html=True
                    )

                with col_value:
                    new_val = st.text_input(
                        label=f"{path}_{i}",
                        value=str(item.get("value", "")),
                        key=f"input_{file_key}_{new_path}_value",
                        label_visibility="collapsed"
                    )
                    data[i]["value"] = new_val

                with col_conf:
                    render_conf_badge(item.get("conf_score", -1))

                st.markdown('</div>', unsafe_allow_html=True)

            # list 裡面是 dict，例如 box_12 的 code/amount
            elif isinstance(item, dict):
                with st.expander(f"📄 Item {i + 1}", expanded=True):
                    render_editable_json(item, new_path, file_key)

            # list 裡面又是 list
            elif isinstance(item, list):
                with st.expander(f"📄 Item {i + 1}", expanded=True):
                    render_editable_json(item, new_path, file_key)

            # list 裡面是一般值
            else:
                st.markdown('<div class="field-row">', unsafe_allow_html=True)

                col_label, col_value = st.columns([1.35, 3.35])

                with col_label:
                    st.markdown(
                        f'<div class="field-label">Item {i + 1}</div>',
                        unsafe_allow_html=True
                    )

                with col_value:
                    new_val = st.text_input(
                        label=f"{path}_{i}",
                        value=str(item),
                        key=f"input_{file_key}_{new_path}",
                        label_visibility="collapsed"
                    )
                    data[i] = new_val

                st.markdown('</div>', unsafe_allow_html=True)


# =========================
# Login check
# =========================
if not st.session_state.get("password_correct", False):
    st.error("請先回到主頁面登入")
    st.stop()


# =========================
# Session state init
# =========================
if "is_parsing" not in st.session_state:
    st.session_state.is_parsing = False


# =========================
# Model list
# =========================
MODEL_LIST = [
    "gemma4:26b",
    "gemma4:31b",
    "gemma4:e4b",
    "gemma4:e2b",
    "qwen3.6:35b",
]


# =========================
# Sidebar
# =========================
with st.sidebar:
    st.header("模型設定 / Model Settings")

    thinking_mode = st.checkbox(
        "Thinking Mode",
        value=False
    )

    selected_model = st.selectbox(
        "選擇解析模型",
        options=MODEL_LIST,
        index=0
    )

    st.warning(
        """
⚠️ **注意事項**：目前解析功能僅支援：

* **W-2**
* **1099-DIV**
* **1099-INT**
* **1040**

上傳其他類型的文件可能會導致解析失敗或結果不準確。
"""
    )

    st.divider()
    st.info(f"目前使用模型: {selected_model}")


# =========================
# Main page
# =========================
st.title("Form Parser")

uploaded_files = st.file_uploader(
    "File upload (JPG/PNG/PDF)",
    type=["png", "jpg", "jpeg", "pdf"],
    accept_multiple_files=True
)


# =========================
# Main flow
# =========================
if uploaded_files:
    processed_files = process_uploaded_files(uploaded_files)

    file_names = [f.name for f in processed_files]
    tabs = st.tabs(file_names)

    combined_result_key = "combined_extraction_result"
    combined_time_key = "combined_time_cost"

    global_disabled = st.session_state.is_parsing

    for i, tab in enumerate(tabs):
        with tab:
            current_file = processed_files[i]
            current_file.seek(0)

            # 右邊結果區給多一點空間，避免 confidence 被擠壓
            col_left, col_right = st.columns([1.05, 1.25], gap="large")

            # =========================
            # Left: image preview
            # =========================
            with col_left:
                st.subheader("Image Preview")

                st.image(
                    current_file,
                    caption=f"檔案名稱: {current_file.name}",
                    use_container_width=True
                )

            # =========================
            # Right: parser result
            # =========================
            with col_right:
                st.subheader(f"解析結果 ({selected_model})")

                run_button = st.button(
                    "開始合併解析 / Run All-in-One Extraction",
                    use_container_width=True,
                    disabled=global_disabled,
                    key=f"run_btn_{i}"
                )

                if run_button:
                    st.session_state.is_parsing = True
                    st.rerun()

                # =========================
                # Run API
                # =========================
                if st.session_state.is_parsing:
                    try:
                        with st.spinner(f"正在整合解析 {len(processed_files)} 張照片..."):
                            api_response = call_ocr_api(
                                processed_files,
                                selected_model,
                                thinking_mode
                            )

                            result_data = parse_api_data(api_response)

                            st.session_state[combined_result_key] = result_data
                            st.session_state[combined_time_key] = api_response.get(
                                "total_time_cost",
                                "N/A"
                            )

                    except json.JSONDecodeError as e:
                        st.error(f"JSON 解析失敗: {e}")

                    except requests.exceptions.RequestException as e:
                        st.error(f"API 請求失敗: {e}")

                    except Exception as e:
                        st.error(f"合併解析失敗: {e}")

                    finally:
                        st.session_state.is_parsing = False
                        st.rerun()

                # =========================
                # Display and edit result
                # =========================
                if combined_result_key in st.session_state:
                    parsed_data = st.session_state[combined_result_key]

                    st.caption(
                        f"⏱️ 總耗時: {st.session_state.get(combined_time_key, 'N/A')}"
                    )

                    st.markdown(
                        '<div class="result-panel">',
                        unsafe_allow_html=True
                    )

                    with st.container(height=680):
                        render_editable_json(
                            parsed_data,
                            "root",
                            f"editor_{i}"
                        )

                    st.markdown(
                        '</div>',
                        unsafe_allow_html=True
                    )

                    st.success("所有照片已完成合併解析")

                    col_json, col_dl = st.columns(2)

                    with col_json:
                        if st.button(
                            "查看 JSON 格式",
                            type="primary",
                            use_container_width=True,
                            key=f"view_json_{i}"
                        ):
                            st.json(st.session_state[combined_result_key])

                    with col_dl:
                        final_json = json.dumps(
                            st.session_state[combined_result_key],
                            indent=4,
                            ensure_ascii=False
                        )

                        st.download_button(
                            label="下載合併 JSON",
                            data=final_json,
                            file_name="combined_results.json",
                            mime="application/json",
                            use_container_width=True,
                            key=f"dl_btn_{i}"
                        )

                else:
                    if not st.session_state.get("is_parsing", False):
                        st.info("點擊上方按鈕開始解析所有上傳的照片。")

else:
    st.info("請上傳 JPG、PNG 或 PDF 檔案。")