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
    page_title="Schedule C 分組併發提取與計算測試",
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

# --- 5 大語意分組定義 (Semantic Baskets) ---
GROUPS = [
    {
        "id": "group_1_general",
        "name": "基本資訊與業務屬性組 (General Info & Profile)",
        "fields": [
            "proprietor_name", "ssn", "principal_business", "line_b_principal_activity_code",
            "business_name", "ein", "business_address", "accounting_method", "started_acquired_2025",
            "owner_annual_hours", "is_sole_participant", "others_annual_hours",
            "any_contractor_paid_600_or_more", "is_1099_filed"
        ]
    },
    {
        "id": "group_2_revenue_cogs",
        "name": "營業收入與銷貨成本組 (Revenue & COGS)",
        "fields": [
            "line_1_gross_receipts", "line_2_returns_allowances", "line_6_other_income",
            "line_33_inventory_valuation_method", "line_34_change_in_valuation",
            "line_36_purchases_less_personal", "line_38_materials_supplies", "line_39_other_costs",
            "line_41_ending_inventory", "prior_year_ending_inventory", "book_beginning_inventory",
            "production_labor_wages", "owner_production_labor_pay"
        ]
    },
    {
        "id": "group_3_expenses_wages",
        "name": "營運費用與薪資組 (Operating Expenses & Wages)",
        "fields": [
            "line_8_advertising", "line_10_commissions_fees", "line_11_contract_labor",
            "line_14_employee_benefit_programs", "line_15_insurance", "line_16a_mortgage_interest",
            "line_16b_other_interest", "line_17_legal_professional", "line_18_office_expense",
            "line_19_pension_profit_sharing", "line_20a_rent_machinery_equipment",
            "line_20b_rent_other_property", "line_21_repairs_maintenance", "line_22_supplies",
            "line_25_utilities", "w2_gross_wages", "employment_credits", "owner_salary_or_draw"
        ]
    },
    {
        "id": "group_4_vehicle_travel_meals",
        "name": "車輛、差旅與膳食費組 (Vehicle, Travel & Meals)",
        "fields": [
            "line_43_date_placed_in_service", "line_44a_business_miles", "line_44b_commuting_miles",
            "line_44c_other_miles", "line_45_available_for_personal_use", "line_46_another_vehicle_available",
            "line_47a_evidence_to_support", "line_47b_evidence_written", "actual_car_expenses",
            "parking_and_tolls", "selected_mileage_method", "travel_transit_cost", "travel_lodging_cost",
            "total_trip_days", "business_days", "is_international", "meals_50_pct", "meals_100_pct",
            "entertainment_cost"
        ]
    },
    {
        "id": "group_5_depr_home_other",
        "name": "折舊、家庭辦公室與雜項費用組 (Depreciation, Home & Other)",
        "fields": [
            "macrs_depreciation", "sec179_asset_cost", "use_sec179", "improved_building_sqft",
            "certified_deduction_rate", "home_office_sqft", "total_home_sqft", "allowable_home_expenses",
            "is_exclusive_and_regular", "selected_home_method", "nonrecourse_debt",
            "guaranteed_non_risk_funding", "stripe_merchant_fees", "software_subscriptions",
            "cleaning_services", "book_amortization", "book_bad_debts", "de_minimis_safe_harbor_cost",
            "other_misc_expenses_list"
        ]
    }
]

# --- 單一分組提取邏輯 (執行緒執行) ---
def extract_group_fields(group: dict, schema: dict, document_context: str, api_key: str, model_name: str) -> tuple:
    # 篩選出屬於該組的 schema inputs 定義
    group_fields = [f for f in schema["inputs"] if f["id"] in group["fields"]]
    
    inputs_def = []
    for f in group_fields:
        inputs_def.append(f'- `{f["id"]}` ({f["type"]}): {f["description"]}')
    inputs_str = "\n".join(inputs_def)
    
    system_instruction = f"""你是一位專業的美國稅務申報與數據提取專家。
你的任務是從申報人基本資料（Taxpayer Profile）以及上傳的文件內容中，精準提取出國稅局 (IRS) Schedule C (Form 1040) 中一組特定的「直接輸入型 (Input)」或「底層非標準」欄位值。

【本組提取任務：{group["name"]}】
你必須「同時且僅對」以下列出的欄位進行定性分類與提取。請注意各個相近欄位之間的互斥對比關係，嚴禁將同一個數值重複提取到多個互斥欄位中：

【本組提取欄位定義】
{inputs_str}

【提取與格式化規範】
1. 只需提取本組列出的欄位。不要包含本組未提及的欄位。
2. 對於數值欄位 (float)，若沒有相關資訊，則填寫 0.0；對於布林值 (boolean)，若無資訊則填寫 false；對於字串 (string) 欄位，若無資訊則填寫 null。
3. 數值必須是純數字，不能包含貨幣符號 ($) 或千分位逗號 (,)。
4. 絕對不要自行計算任何毛利或總費用公式，保持原始金額。例如不要對餐飲費乘以 0.5。
5. ⚠️ 嚴禁重複提取同一個數字：請仔細對比本組內類似欄位的定義。
   - 例如：`meals_50_pct` (一般膳食)、`meals_100_pct` (尾牙聚餐) 與 `entertainment_cost` (娛樂費) 彼此互斥，同一筆餐費切勿重複提取；
   - 里程數 `line_44a_business_miles` (商用)、`line_44b_commuting_miles` (通勤) 與 `line_44c_other_miles` (個人) 必須做好嚴格的科目區分，不能把同一個數字填入多個格子；
   - 員工薪資 `w2_gross_wages` 嚴禁包含業主自己的提款 `owner_salary_or_draw` 或自營工資 `owner_production_labor_pay`。

【輸出格式】
你必須精確返回一個符合本組欄位的 JSON 對象，例如：
{{
  "field_id_1": val1,
  "field_id_2": val2,
  ...
}}
直接返回乾淨的 JSON 字串，不要使用 markdown ```json ``` 區塊，也不要包含任何說明文字。
"""
    
    llm = GeminiLLM(model_name=model_name, api_key=api_key, temperature=0.0)
    
    messages = [
        SystemMessage(content=system_instruction),
        HumanMessage(content=f"以下是申報人與上傳文件的相關內容，請提取本組欄位：\n\n{document_context}")
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
        
        # 強制執行型態轉換以符合 Schema
        coerced_data = {}
        for f in group_fields:
            fid = f["id"]
            ftype = f["type"]
            val = data.get(fid)
            
            if ftype == "float":
                coerced_data[fid] = float(val) if val is not None else 0.0
            elif ftype == "boolean":
                if val is not None:
                    coerced_data[fid] = True if str(val).lower() in ["true", "1", "yes"] else False
                else:
                    coerced_data[fid] = False
            elif ftype == "array":
                coerced_data[fid] = val if isinstance(val, list) else []
            else:
                coerced_data[fid] = val
                
        latency = time.time() - t0
        return group["id"], coerced_data, raw_output, system_instruction, latency, None
    except Exception as e:
        latency = time.time() - t0
        # 發生錯誤時提供本組預設 fallback
        fallback_data = {}
        for f in group_fields:
            fid = f["id"]
            ftype = f["type"]
            fallback_data[fid] = 0.0 if ftype == "float" else (False if ftype == "boolean" else ([] if ftype == "array" else None))
        return group["id"], fallback_data, f"錯誤: {e}", system_instruction, latency, str(e)

# --- 側邊欄控制 ---
with st.sidebar:
    st.header("⚙️ 執行參數設定")
    
    selected_model = st.selectbox(
        "選擇分析模型",
        options=["gemini-2.5-pro", "gemini-2.5-flash"],
        index=0
    )
    
    app_mode = st.radio("界面模式", ["Normal", "Debug"], index=1)
    is_debug = (app_mode == "Debug")
    
    st.divider()
    st.info("💡 說明：\n1. 此模式為 **分組對比併發提取 (Method 3)**。\n2. 將 70+ 個輸入變數拆分為 **5 個高關聯的語意籃子**。\n3. 優點：能藉由同個 Prompt 提供**對比注意力**，有效解決 Flash 模型的 Token 數字記憶污染與科目錯置問題，且僅需 5 次 API 呼叫，性能極快。")

# --- 主畫面標題 ---
st.title("📋 IRS Schedule C 分組對比併發提取與計算測試 (Method 3)")
st.write("此頁面為**第三代測試方案**。透過 5 個精心設計的對比組（General, Revenue/COGS, Expense/Wages, Vehicle/Travel/Meals, Depr/Home），強迫 LLM 在提取時進行互斥性檢視，以獲取最優的稅務提取精確度。")

# 初始化 Session 狀態
if "rivera_input_text_3" not in st.session_state:
    st.session_state.rivera_input_text_3 = ""

if "test_execution_result_3" not in st.session_state:
    st.session_state.test_execution_result_3 = None

# --- 載入模擬資料控制按鈕 ---
col_actions, _ = st.columns([2, 5])
with col_actions:
    if st.button("📥 載入 Rivera 夫婦完整實驗資料 (Sample 01~08)", use_container_width=True):
        st.session_state.rivera_input_text_3 = schedule_c_ui_helper.load_all_rivera_samples()
        st.rerun()

# 顯示輸入框
prompt_input = st.text_area(
    "請輸入原始報稅資料 (JSON 或 Markdown 文字列表)：",
    value=st.session_state.rivera_input_text_3,
    height=280,
    placeholder="在此輸入或點擊上方按鈕載入模擬的 8 個 Sample 憑證資料..."
)
st.session_state.rivera_input_text_3 = prompt_input

# --- 執行按鈕 ---
run_btn = st.button("🚀 開始分組併發提取與計算", type="primary", use_container_width=True)

if run_btn:
    if not prompt_input.strip():
        st.error("輸入內容不可為空！")
    else:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            st.error("環境變數 GEMINI_API_KEY 未設定，無法呼叫 Gemini API。")
        else:
            schema = load_schedule_c_schema()
            total_groups = len(GROUPS)
            
            # 建立動態進度顯示器
            progress_container = st.container()
            with progress_container:
                st.write("### ⏳ 語意分組提取進度")
                progress_bar = st.progress(0.0)
                status_text = st.empty()
                status_text.text(f"開始分配並發任務 ...")
                
            formatted_ctx = format_input_data(prompt_input)
            
            extracted_inputs = {}
            debug_logs = {}
            completed_count = 0
            t_start = time.time()
            
            # 併發發送 5 組 Request
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(extract_group_fields, g, schema, formatted_ctx, api_key, selected_model): g for g in GROUPS}
                
                for future in concurrent.futures.as_completed(futures):
                    g = futures[future]
                    gid, group_data, raw_out, sys_prompt, latency, err = future.result()
                    
                    # 合併提取結果到主 JSON 物件
                    extracted_inputs.update(group_data)
                    debug_logs[gid] = {
                        "name": g["name"],
                        "raw_output": raw_out,
                        "system_prompt": sys_prompt,
                        "latency_seconds": latency,
                        "error": err
                    }
                    
                    completed_count += 1
                    pct = completed_count / total_groups
                    progress_bar.progress(pct)
                    status_text.text(f"已完成 {completed_count} / {total_groups} 組 ({g['name']} | 耗時: {latency:.2f}s)...")
            
            total_latency = time.time() - t_start
            
            # 執行計算
            try:
                final_state = calculate_schedule_c_dynamic(extracted_inputs)
                
                st.session_state.test_execution_result_3 = {
                    "extracted_inputs": extracted_inputs,
                    "final_state": final_state,
                    "debug_logs": debug_logs,
                    "latency": total_latency
                }
                st.success(f"完成！5 大分組提取與公式計算順利執行完畢，總耗時 {total_latency:.2f} 秒！")
                st.rerun()
            except Exception as e:
                st.error(f"運算引擎在加總時發生錯誤：{e}")

# --- 顯示結果分頁 ---
if st.session_state.test_execution_result_3:
    res = st.session_state.test_execution_result_3
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
        "🔍 Debug 日誌 (語意分組 Prompt & 完整 Trace)"
    ])
    
    schema = load_schedule_c_schema()
    
    with tab_report:
        st.write("以下為此申報人的 Schedule C 國稅局標準申報欄位填寫結果 (非標準之計算中間變數已自動隱藏)：")
        
        # 顯示基本資料
        schedule_c_ui_helper.render_general_info(final_state, schema)
                
        # 欄位詳細表格
        schedule_c_ui_helper.render_standard_fields_table(final_state, schema)
        
    with tab_extracted:
        st.write("以下為 5 個語意組併發提取後彙整出的完整單一 JSON 資料：")
        st.json(extracted_inputs)
        
    with tab_debug:
        st.write("本分頁提供單一分組的計算追蹤、拓撲鏈以及每個語意籃子的獨立 Prompt 與 Response 稽核：")
        
        # 計算與來源詳細追蹤表
        schedule_c_ui_helper.render_calculation_trace_table(final_state, schema, "LLM 語意籃子提取")
        
        st.divider()
        
        # 顯示依賴排序順序
        schedule_c_ui_helper.render_topological_chain(schema, final_state)
        
        st.divider()
        
        # 選擇單一分組查看其專屬 Prompt/Response 日誌
        st.markdown("#### 🕵️‍♂️ 檢視單一語意分組 (Group) LLM 併發日誌")
        selected_log_group = st.selectbox(
            "選擇要檢視的語意組", 
            options=[g["id"] for g in GROUPS],
            format_func=lambda gid: next(g["name"] for g in GROUPS if g["id"] == gid)
        )
        
        if selected_log_group in debug_logs:
            g_log = debug_logs[selected_log_group]
            col_l, col_r = st.columns(2)
            with col_l:
                st.markdown(f"**📡 傳送給 LLM 的 System Prompt ({selected_log_group})**")
                st.text_area("System Prompt", g_log["system_prompt"], height=250, key=f"sys_pr_{selected_log_group}")
            with col_r:
                st.markdown(f"**📥 LLM 原始回應 ({selected_log_group})**")
                st.text_area("LLM Raw Response", g_log["raw_output"], height=250, key=f"raw_res_{selected_log_group}")
                st.write(f"⏱️ 耗時: `{g_log['latency_seconds']:.2f}` 秒")
                if g_log["error"]:
                    st.error(f"錯誤訊息: {g_log['error']}")
