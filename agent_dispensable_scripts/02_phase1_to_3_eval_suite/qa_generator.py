"""
qa_generator.py — 自動 QA 測試集生成器
====================================================
使用 Gemini 從以下兩種來源生成帶有分類標籤的 QA 對：
  - 路徑 A (--path A)：從 kv_store_text_chunks.json 抽取段落（Top-Down）
  - 路徑 B (--path B)：從 graph_chunk_entity_relation.graphml KG 節點（Bottom-Up）

執行方式：
    python tests/eval_suite/qa_generator.py --n 10 --path A
    python tests/eval_suite/qa_generator.py --n 10 --path B

輸出：
    tests/eval_suite/qa_dataset/qa_<YYYYMMDD_HHMMSS>.json
"""

import sys
import os
import json
import random
import argparse
import datetime
from pathlib import Path

# 專案根目錄
root_dir = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(root_dir))

from dotenv import load_dotenv
load_dotenv(dotenv_path=root_dir / ".env")

import google.generativeai as genai

# ==============================================================================
# 設定
# ==============================================================================
GEMINI_API_KEY    = os.environ.get("GEMINI_API_KEY")
GEMINI_JUDGE_MODEL= os.environ.get("GEMINI_JUDGE_MODEL", "gemini-2.5-pro-exp-03-25")
ACTIVE_KGS        = os.environ.get("ACTIVE_KGS", "tax_kg_v1").split(",")

OUTPUT_DIR = Path(__file__).resolve().parent / "qa_dataset"
if not OUTPUT_DIR.exists():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# MECE 類別（供 LLM 選擇）
CATEGORIES = ["Numerical", "Conditional", "Calculative", "Procedural"]
print(f"--- [DEBUG] qa_generator.py START ---")
print(f"--- [DEBUG] root_dir: {root_dir}")
print(f"--- [DEBUG] GEMINI_API_KEY: {'[SET]' if GEMINI_API_KEY else '[MISSING]'}")
print(f"--- [DEBUG] GEMINI_JUDGE_MODEL: {GEMINI_JUDGE_MODEL}")
print(f"--- [DEBUG] ACTIVE_KGS: {ACTIVE_KGS}")
DIFFICULTIES = ["Easy", "Medium", "Hard"]


# ==============================================================================
# QA 生成 Prompt
# ==============================================================================
QA_GEN_PROMPT = """You are an expert in US federal tax law. Based on the following tax document excerpt, generate a realistic and specific question that a taxpayer might ask, along with a precise ground truth answer.

**Requirements:**
- The question must be answerable using ONLY the provided excerpt.
- The question should be natural, written in English, as if asked by a real taxpayer (not a law student).
- The ground truth answer must be accurate, concise (2-4 sentences), and directly cite the key rule or number from the excerpt.
- Classify the question into one of: {categories}
- Assign difficulty: {difficulties}
- Do NOT ask generic questions. Be specific (e.g., mention exact dollar amounts, filing status, or conditions).

**Tax Document Excerpt:**
{excerpt}

**Output JSON format (output ONLY valid JSON, no markdown):**
{{
  "question": "...",
  "ground_truth": "...",
  "category": "...",
  "difficulty": "..."
}}"""

# ==============================================================================
# 資料載入工具
# ==============================================================================
def load_text_chunks(kg_name: str) -> list[dict]:
    """從 kv_store_text_chunks.json 載入文字段落"""
    path = root_dir / "data" / kg_name.strip() / "kv_store_text_chunks.json"
    if not path.exists():
        raise FileNotFoundError(f"找不到 text chunks: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 格式可能是 { chunk_id: {content: ...} } 或 list
    if isinstance(data, dict):
        chunks = [{"chunk_id": k, "content": v.get("content", "") if isinstance(v, dict) else str(v)}
                  for k, v in data.items() if v]
    else:
        chunks = data
    # 過濾太短的段落 (放寬到 120 字以增加池子大小)
    chunks = [c for c in chunks if len(c.get("content", "")) > 120]
    print(f"    [Load] Loaded {len(chunks)} valid text chunks (len > 120).")
    return chunks



def load_kg_rule_nodes(kg_name: str) -> list[dict]:
    """從 vdb_entities.json 或 kv_store_full_entities.json 載入 rule 型節點（路徑 B）"""
    kg_dir = root_dir / "data" / kg_name.strip()
    vdb_entities_path = kg_dir / "vdb_entities.json"
    full_entities_path = kg_dir / "kv_store_full_entities.json"

    nodes = []
    
    # 優先嘗試 sub-KG 格式 (vdb_entities.json)
    if vdb_entities_path.exists():
        with open(vdb_entities_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "data" in data:
            nodes = data["data"]
            for n in nodes:
                if "description" not in n and "content" in n:
                    n["description"] = n["content"]

    # 如果沒讀到，嘗試 legacy 格式 (kv_store_full_entities.json)
    if not nodes and full_entities_path.exists():
        with open(full_entities_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            nodes = [v for v in data.values() if isinstance(v, dict)]
        elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            nodes = data

    if not nodes:
        print(f"警告：在 {kg_name} 中找不到任何實體節點資訊。")
        return []

    print(f"  [Debug] 共嘗試從 {kg_name} 載入節點，目前池中有 {len(nodes)} 個節點。")
    
    rule_nodes = []
    for n in nodes:
        etype = str(n.get("entity_type", "")).lower()
        ename = str(n.get("entity_name", "")).lower()
        econt = str(n.get("content", "")).lower()
        
        # 只要是 rule 或是 description/content 夠長都行
        if etype == "rule" or "rule" in ename or "rule:" in econt:
            rule_nodes.append(n)
            
    # 如果還是太少，直接取前 N 個描述豐富的
    if len(rule_nodes) < 5:
        rule_nodes = [n for n in nodes if len(n.get("description", n.get("content", ""))) > 150]

    print(f"    [Load] Found {len(rule_nodes)} Rule-like nodes.")
    return [n for n in rule_nodes if n.get("description") or n.get("content")]



# ==============================================================================
# Gemini 呼叫
# ==============================================================================
# 使用 approved 的高階模型
# GEMINI_JUDGE_MODEL is already set above from env


def call_gemini(prompt: str, model_name: str = GEMINI_JUDGE_MODEL) -> str:
    """呼叫 Gemini 並回傳純文字 (含 retry)"""
    import time
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel(model_name)
    
    for attempt in range(3):
        try:
            response = model.generate_content(prompt)
            if not response.text:
                raise ValueError("Empty response from Gemini")
            return response.text.strip()
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                wait = (attempt + 1) * 5
                print(f"      [Retry] Quota hit, waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"      [Error] API call failed: {e}")
                if attempt == 2: raise e
                time.sleep(2)
    return ""



def generate_qa_from_excerpt(excerpt: str, source_id: str, path_type: str, idx: int) -> dict | None:
    """根據一段文字呼叫 Gemini 生成 QA，回傳結構化資料"""
    prompt = QA_GEN_PROMPT.format(
        excerpt=excerpt[:2000],  # 避免超過 token 限制
        categories=", ".join(CATEGORIES),
        difficulties=", ".join(DIFFICULTIES)
    )
    try:
        raw = call_gemini(prompt, GEMINI_JUDGE_MODEL)
        # 嘗試解析 JSON
        # 去除可能的 markdown code block
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)
        return {
            "id": f"Q{idx:03d}",
            "path_type": path_type,
            "category": parsed.get("category", "Unknown"),
            "difficulty": parsed.get("difficulty", "Medium"),
            "question": parsed.get("question", ""),
            "ground_truth": parsed.get("ground_truth", ""),
            "source_id": source_id,
        }
    except Exception as e:
        print(f"  [Warning] QA 生成失敗 (source: {source_id}): {e}")
        return None


# ==============================================================================
# 主流程
# ==============================================================================
def run_generator(n: int, path_type: str, output_dir_override: Path = None):
    global OUTPUT_DIR
    if output_dir_override:
        OUTPUT_DIR = output_dir_override

    if not GEMINI_API_KEY:

        print("❌ 請在 .env 設定 GEMINI_API_KEY")
        return

    print(f"\n{'='*60}")
    print(f"  QA Generator — 路徑 {path_type} | 題數: {n} | 模型: {GEMINI_JUDGE_MODEL}")
    print(f"{'='*60}\n")

    kg_name = ACTIVE_KGS[0]

    # 根據路徑載入素材
    if path_type == "A":
        print(f"[路徑 A] 載入 text chunks from '{kg_name}'...")
        chunks = load_text_chunks(kg_name)
        print(f"  找到 {len(chunks)} 個段落，隨機抽取 {n} 個...")
        sampled = random.sample(chunks, min(n, len(chunks)))
        sources = [(c.get("content", ""), c.get("chunk_id", f"chunk_{i}"), "A") for i, c in enumerate(sampled)]
    elif path_type == "B":
        print(f"[路徑 B] 載入 KG rule nodes from '{kg_name}'...")
        nodes = load_kg_rule_nodes(kg_name)
        print(f"  找到 {len(nodes)} 個 rule 節點，隨機抽取 {n} 個...")
        sampled = random.sample(nodes, min(n, len(nodes)))
        sources = [((n.get("description") or n.get("content") or "") + "\n" + n.get("source_id", ""), 
                    n.get("__id__") or n.get("entity_id") or n.get("entity_name") or f"rule_{i}", "B")
                   for i, n in enumerate(sampled)]
    elif path_type == "both":
        print(f"[路徑 Both] 混合載入 A 與 B from '{kg_name}'...")
        n_a = n // 2
        n_b = n - n_a
        
        # Load A
        chunks = load_text_chunks(kg_name)
        sampled_a = random.sample(chunks, min(n_a, len(chunks)))
        sources_a = [(c.get("content", ""), c.get("chunk_id", f"chunk_{i}"), "A") for i, c in enumerate(sampled_a)]
        
        # Load B
        nodes = load_kg_rule_nodes(kg_name)
        sampled_b = random.sample(nodes, min(n_b, len(nodes)))
        sources_b = [((n.get("description") or n.get("content") or "") + "\n" + n.get("source_id", ""), 
                      n.get("__id__") or n.get("entity_id") or n.get("entity_name") or f"rule_{i}", "B")
                     for i, n in enumerate(sampled_b)]
        
        sources = sources_a + sources_b
        print(f"  混合模式：A={len(sources_a)}, B={len(sources_b)} (Total: {len(sources)})")
    else:
        print(f"❌ 未知路徑 '{path_type}'，請使用 A, B 或 both")
        return

    # 逐題生成
    qa_pairs = []
    for idx, (excerpt, source_id, p_type) in enumerate(sources, start=1):
        print(f"  [{idx}/{len(sources)}] 生成中... (source: {source_id[:40]} | Path: {p_type})")
        qa = generate_qa_from_excerpt(excerpt, source_id, p_type, idx)
        if qa:
            qa_pairs.append(qa)
            print(f"    ✅ [{qa['category']} / {qa['difficulty']}] {qa['question'][:80]}...")

    # 儲存結果
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"qa_{ts}.json"
    output = {
        "metadata": {
            "generated_at": ts,
            "path_type": path_type,
            "n_requested": n,
            "n_generated": len(qa_pairs),
            "source_kg": kg_name,
            "generator_model": GEMINI_JUDGE_MODEL,
        },
        "qa_pairs": qa_pairs,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 完成！共生成 {len(qa_pairs)} 題")
    print(f"   儲存路徑：{out_path}")
    return str(out_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QA 測試集生成器")
    parser.add_argument("--n", type=int, default=10, help="生成題數 (預設: 10)")
    parser.add_argument("--path", type=str, default="A", choices=["A", "B", "both"], help="生成路徑 A, B 或 both (預設: A)")
    parser.add_argument("--output_dir", type=str, default=None, help="輸出目錄 (預設: tests/eval_suite/qa_dataset)")
    args = parser.parse_args()
    
    run_generator(n=args.n, path_type=args.path, output_dir_override=OUTPUT_DIR if args.output_dir else None)

