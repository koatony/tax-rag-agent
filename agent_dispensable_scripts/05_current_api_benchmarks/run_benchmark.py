import os
import json
import urllib.request
import time
from pathlib import Path

# --- 配置 ---
INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "")
TESTS_FILE = "../../tax_test_generator/output/tests.json"
API_URL = "http://127.0.0.1:8088/query"
OUTPUT_DIR = "../../miss_form_result_v2"

def run_full_benchmark():
    # 建立輸出目錄
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    # 讀取測試集
    if not os.path.exists(TESTS_FILE):
        print(f"錯誤: 找不到測試檔案 {TESTS_FILE}")
        return

    try:
        with open(TESTS_FILE, "r", encoding="utf-8") as f:
            test_cases = json.load(f)
    except Exception as e:
        print(f"讀取 JSON 失敗: {e}")
        return

    total = len(test_cases)
    print(f"--- 開始全量基準測試，共 {total} 個案例 ---")

    for i, case in enumerate(test_cases):
        case_id = case.get("id", f"case_{i}")
        report_path = f"{OUTPUT_DIR}/{case_id}.md"
        
        print(f"[{i+1}/{total}] 正在處理: {case_id}...")

        # 準備輸入
        forms_input = json.dumps(case.get("uploaded_forms", []), indent=2, ensure_ascii=False)
        query_input = f"Uploaded Forms:\n{forms_input}"

        # 準備 Payload
        payload = {
            "question": query_input,
            "mode": "irac"
        }
        data_bytes = json.dumps(payload).encode('utf-8')

        # 發送 API 請求
        req = urllib.request.Request(API_URL, data=data_bytes, method='POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('x-api-token', INTERNAL_TOKEN)

        start_time = time.time()
        try:
            with urllib.request.urlopen(req, timeout=300) as response:
                res_body = response.read().decode('utf-8')
                data = json.loads(res_body)
                latency = time.time() - start_time
        except Exception as e:
            print(f"  FAILED: {e}")
            data = {"answer": f"API 請求失敗: {str(e)}", "debug_info": {}}
            latency = time.time() - start_time

        # 寫入個別報告
        with open(report_path, "w", encoding="utf-8") as out:
            out.write(f"# Tax RAG 診斷報告 - {case_id}\n\n")
            out.write(f"- **測試時間**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            out.write(f"- **總體耗時**: {latency:.2f}s\n\n")

            out.write(f"## 🤖 AI 診斷結果\n")
            out.write(f"{data.get('answer', '無回答')}\n\n")

            out.write(f"## 🎯 檢索候選規則 (Top 15)\n")
            candidates = data.get("rule_candidates", [])
            if candidates:
                out.write("| 排名 | 規則 ID | 分數 | Tier |\n")
                out.write("|:---:|:---|:---:|:---:|\n")
                for j, c in enumerate(candidates[:15]):
                    out.write(f"| {j+1} | `{c.get('rule_id')}` | {c.get('final_score', 0):.4f} | T{c.get('tier')} |\n")
            else:
                out.write("*未抓取到候選規則*\n")
            out.write("\n")

            out.write(f"## 📖 注入的 Context\n")
            out.write("<details><summary>點擊展開法規 Context</summary>\n\n")
            out.write(f"```text\n{data.get('context', 'N/A')}\n```\n")
            out.write("\n</details>\n\n")

            out.write(f"## 🛠️ Debug 資訊 (管道耗時)\n")
            out.write("<details><summary>點擊展開管道耗時詳情</summary>\n\n")
            debug_info = data.get("debug_info", {})
            node_latency = debug_info.get("node_latency", {})
            if node_latency:
                out.write("| 節點 | 耗時 (s) |\n")
                out.write("|:---|:---:|\n")
                for node, l in node_latency.items():
                    out.write(f"| {node} | {l:.3f}s |\n")
            out.write("\n")
            out.write(f"**Token 消耗**: In `{debug_info.get('total_tokens_in', 0)}` / Out `{debug_info.get('total_tokens_out', 0)}`\n")
            out.write("\n</details>\n\n")

            out.write(f"## 📝 原始發送 Prompt\n")
            out.write("<details><summary>點擊展開完整 Prompt</summary>\n\n")
            out.write(f"```text\n{debug_info.get('full_prompt_sent', 'N/A')}\n```\n")
            out.write("\n</details>\n")

        print(f"  SUCCESS: 報告已存至 {report_path}")

    print(f"\n✅ 全量測試完成！所有報告均已存放在 {OUTPUT_DIR}/ 目錄下。")

if __name__ == "__main__":
    run_full_benchmark()
