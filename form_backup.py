import streamlit as st
import json
import io
from PIL import Image
from pdf2image import convert_from_bytes
import requests


# =========================
# Streamlit page config
# =========================
st.set_page_config(layout="wide")


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

            # PDF 每頁轉圖片
            pdf_images = convert_from_bytes(pdf_bytes)

            for page_idx, image in enumerate(pdf_images):
                img_bytes = io.BytesIO()

                image.save(img_bytes, format="PNG")
                img_bytes.seek(0)

                # 模擬 UploadedFile 所需欄位
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
    將 API 回傳的 data 轉成 dict/list。
    如果 data 是 JSON 字串，就 json.loads。
    如果已經是 dict/list，就直接回傳。
    """
    result_data = api_response.get("data", {})

    if isinstance(result_data, str):
        result_data = result_data.strip()

        # 容錯：移除 Markdown code block
        if result_data.startswith("```"):
            result_data = (
                result_data
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )

        result_data = json.loads(result_data)

    return result_data


def is_value_conf_leaf(obj):
    """
    判斷是否為新的欄位格式：

    {
        "value": "...",
        "conf_score": 0.98
    }

    只要同時有 value 和 conf_score，就視為一個可編輯欄位。
    """
    return (
        isinstance(obj, dict)
        and "value" in obj
        and "conf_score" in obj
    )


def format_conf_score(conf_score):
    """
    將 conf_score 轉成百分比字串。
    -1 或 None 顯示 N/A。
    """
    try:
        score = float(conf_score)
    except (TypeError, ValueError):
        return "N/A"

    if score < 0:
        return "N/A"

    return f"{score * 100:.2f}%"


def render_conf_badge(conf_score):
    """
    依照信心分數顯示不同顏色。
    """
    try:
        score = float(conf_score)
    except (TypeError, ValueError):
        st.caption("Confidence: N/A")
        return

    if score < 0:
        st.caption("Confidence: N/A")
    elif score >= 0.95:
        st.success(f"Confidence: {score * 100:.2f}%")
    elif score >= 0.85:
        st.warning(f"Confidence: {score * 100:.2f}%")
    else:
        st.error(f"Confidence: {score * 100:.2f}%")


def render_editable_json(data, path, file_key):
    """
    自動根據資料結構生成輸入框，並將編輯結果同步回 session_state。

    支援新格式：
    {
        "欄位名稱": {
            "value": "...",
            "conf_score": 0.98
        }
    }

    顯示方式：
    欄位名稱 | 可編輯 value | 信心分數
    """

    # =========================
    # Dict
    # =========================
    if isinstance(data, dict):
        for key, value in data.items():
            new_path = f"{path}_{key}"

            # ===== 新格式 leaf node: {"value": ..., "conf_score": ...} =====
            if is_value_conf_leaf(value):
                st.markdown(f"**{key}**")

                col_value, col_conf = st.columns([3, 1])

                with col_value:
                    new_val = st.text_input(
                        label=key,
                        value=str(value.get("value", "")),
                        key=f"input_{file_key}_{new_path}_value",
                        label_visibility="collapsed"
                    )

                    # 只更新 value，不覆蓋 conf_score
                    data[key]["value"] = new_val

                with col_conf:
                    render_conf_badge(value.get("conf_score", -1))

            # ===== 巢狀 dict =====
            elif isinstance(value, dict):
                with st.expander(f"📂 {key}", expanded=True):
                    render_editable_json(value, new_path, file_key)

            # ===== list =====
            elif isinstance(value, list):
                with st.expander(f"📂 {key}", expanded=True):
                    render_editable_json(value, new_path, file_key)

            # ===== 舊格式 fallback =====
            else:
                st.markdown(f"**{key}**")

                new_val = st.text_input(
                    label=key,
                    value=str(value),
                    key=f"input_{file_key}_{new_path}",
                    label_visibility="collapsed"
                )

                data[key] = new_val

    # =========================
    # List
    # =========================
    elif isinstance(data, list):
        for i, item in enumerate(data):
            new_path = f"{path}_{i}"

            # list 裡面直接是 {"value": ..., "conf_score": ...}
            if is_value_conf_leaf(item):
                st.markdown(f"**Item {i + 1}**")

                col_value, col_conf = st.columns([3, 1])

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

            # list 裡面是 dict，例如 box_12 的每一組 code/amount
            elif isinstance(item, dict):
                with st.expander(f"📄 Item {i + 1}", expanded=True):
                    render_editable_json(item, new_path, file_key)

            # list 裡面又是 list
            elif isinstance(item, list):
                with st.expander(f"📄 Item {i + 1}", expanded=True):
                    render_editable_json(item, new_path, file_key)

            # list 裡面是一般值
            else:
                new_val = st.text_input(
                    label=f"{path}_{i}",
                    value=str(item),
                    key=f"input_{file_key}_{new_path}",
                    label_visibility="collapsed"
                )

                data[i] = new_val

            st.divider()


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

    img_scale = st.slider(
        "圖片顯示大小 (Width %)",
        min_value=10,
        max_value=100,
        value=70,
        disabled=st.session_state.get("is_parsing", False)
    )

    file_names = [f.name for f in processed_files]
    tabs = st.tabs(file_names)

    combined_result_key = "combined_extraction_result"
    combined_time_key = "combined_time_cost"

    global_disabled = st.session_state.is_parsing

    for i, tab in enumerate(tabs):
        with tab:
            current_file = processed_files[i]
            current_file.seek(0)

            col_left, col_right = st.columns([3, 2], gap="large")

            # =========================
            # Left: image preview
            # =========================
            with col_left:
                st.subheader("Image Preview")

                st.image(
                    current_file,
                    caption=f"檔案名稱: {current_file.name}",
                    width=int(img_scale * 10)
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

                    with st.container(height=700):
                        render_editable_json(
                            parsed_data,
                            "root",
                            f"editor_{i}"
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