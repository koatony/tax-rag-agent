"""
KG Retriever v2 — Two-layer retrieval

Layer 1: Semantic search via bge-m3 (Ollama) + cosine similarity on cached embeddings
Layer 2: Dynamic Cypher traversal from matched rule nodes
         → LEADS_TO conclusion, BASED_ON regulation/statute

Cache: rule_embeddings_cache.pkl
  - Built once on first run, reused on subsequent calls
  - Re-run build_cache() manually if KG is updated
"""

import os
import pickle
import numpy as np
import httpx
from pathlib import Path
from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://140.115.54.87:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

# This Neo4j instance holds multiple LightRAG ingestion runs side by side,
# each isolated under its own workspace label (see KG.md). Queries must
# scope to this label or they'll pull rule nodes from unrelated experiments.
WORKSPACE_LABEL = "ALL5_Publication"

OLLAMA_HOST = "http://140.115.54.89:11434"
EMBED_MODEL = "bge-m3"

CACHE_PATH = Path(__file__).parent / "rule_embeddings_cache.pkl"

_driver = None
_cache = None  # {"entity_ids": [...], "embeddings": np.ndarray}


# ---------------------------------------------------------------------------
# Neo4j driver
# ---------------------------------------------------------------------------

def get_driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


# ---------------------------------------------------------------------------
# Embedding via Ollama bge-m3
# ---------------------------------------------------------------------------

def embed(text: str) -> np.ndarray:
    """Call Ollama bge-m3 to get embedding for a single text."""
    response = httpx.post(
        f"{OLLAMA_HOST}/api/embeddings",
        json={"model": EMBED_MODEL, "prompt": text},
        timeout=30,
    )
    response.raise_for_status()
    return np.array(response.json()["embedding"], dtype=np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cosine similarity between vector a and matrix b (rows are vectors)."""
    a_norm = a / (np.linalg.norm(a) + 1e-10)
    b_norms = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-10)
    return b_norms @ a_norm


# ---------------------------------------------------------------------------
# Cache: build and load
# ---------------------------------------------------------------------------

def build_cache():
    """
    Pull all rule nodes from Neo4j, embed their descriptions with bge-m3,
    and save to CACHE_PATH. Run this once (or after KG updates).
    """
    print("[cache] Fetching rule nodes from Neo4j...")
    driver = get_driver()
    with driver.session() as session:
        rows = session.run(f"""
            MATCH (r:rule:{WORKSPACE_LABEL})
            WHERE r.description IS NOT NULL AND r.description <> ''
            RETURN r.entity_id AS entity_id, r.description AS description
        """).data()

    print(f"[cache] Found {len(rows)} rule nodes. Embedding with {EMBED_MODEL}...")

    entity_ids = []
    descriptions = []
    embeddings = []

    for i, row in enumerate(rows):
        if i % 100 == 0:
            print(f"[cache]  {i}/{len(rows)}...")
        try:
            vec = embed(row["description"][:1000])  # truncate very long descriptions
            entity_ids.append(row["entity_id"])
            descriptions.append(row["description"])
            embeddings.append(vec)
        except Exception as e:
            print(f"[cache] embed failed for {row['entity_id']}: {e}")

    cache = {
        "entity_ids": entity_ids,
        "descriptions": descriptions,
        "embeddings": np.stack(embeddings),
    }
    with open(CACHE_PATH, "wb") as f:
        pickle.dump(cache, f)

    print(f"[cache] Saved {len(entity_ids)} embeddings to {CACHE_PATH}")
    return cache


def load_cache() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    if not CACHE_PATH.exists():
        print("[cache] Cache not found. Building now (this may take a few minutes)...")
        _cache = build_cache()
    else:
        with open(CACHE_PATH, "rb") as f:
            _cache = pickle.load(f)
        print(f"[cache] Loaded {len(_cache['entity_ids'])} rule embeddings from cache.")
    return _cache


# ---------------------------------------------------------------------------
# Layer 1: Semantic search
# ---------------------------------------------------------------------------

def semantic_search(query: str, top_k: int = 5) -> list[dict]:
    """
    Embed the query and return top-k most similar rule nodes.
    Returns list of {"entity_id": ..., "description": ..., "score": ...}
    """
    cache = load_cache()
    query_vec = embed(query)
    scores = cosine_similarity(query_vec, cache["embeddings"])
    top_indices = np.argsort(scores)[::-1][:top_k]

    return [
        {
            "entity_id": cache["entity_ids"][i],
            "description": cache["descriptions"][i],
            "score": float(scores[i]),
        }
        for i in top_indices
    ]


# ---------------------------------------------------------------------------
# Layer 2: Dynamic Cypher traversal
# ---------------------------------------------------------------------------

def graph_traverse(entity_ids: list[str]) -> list[dict]:
    """
    Given a list of rule entity_ids, traverse the graph to fetch
    connected legalissues, conclusions, and authorities.
    """
    if not entity_ids:
        return []

    driver = get_driver()
    with driver.session() as session:
        rows = session.run(f"""
            UNWIND $entity_ids AS eid
            MATCH (r:rule:{WORKSPACE_LABEL} {{entity_id: eid}})

            OPTIONAL MATCH (r)-[:ADDRESSES]->(li:legalissue:{WORKSPACE_LABEL})
            OPTIONAL MATCH (r)-[:LEADS_TO]->(c:conclusion:{WORKSPACE_LABEL})
            OPTIONAL MATCH (r)-[:BASED_ON]->(auth)
            WHERE (auth:regulation OR auth:statute) AND auth:{WORKSPACE_LABEL}

            RETURN
                r.entity_id      AS rule_id,
                r.description    AS rule_desc,
                li.description   AS issue_desc,
                c.description    AS conclusion_desc,
                auth.entity_id   AS authority_id,
                auth.description AS authority_desc,
                labels(auth)[0]  AS authority_type
        """, entity_ids=entity_ids).data()

    return rows


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def query_kg_for_issue(issue_name: str, target_component: str, top_k: int = 4) -> str:
    """
    Two-layer retrieval:
      Layer 1 — semantic search with bge-m3
      Layer 2 — Cypher graph traversal from matched nodes
    Returns formatted string for LLM prompt injection.
    """
    query = f"{issue_name} {target_component}"

    # Layer 1
    hits = semantic_search(query, top_k=top_k)
    if not hits:
        return ""

    # Layer 2
    entity_ids = [h["entity_id"] for h in hits]
    rows = graph_traverse(entity_ids)
    if not rows:
        return ""

    return _format_kg_context(rows, hits, top_k)


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------

def _format_kg_context(rows: list[dict], hits: list[dict], top_k: int) -> str:
    score_map = {h["entity_id"]: h["score"] for h in hits}
    lines = ["[KG RETRIEVED RULES — authoritative reference from IRS publications]"]
    seen = set()
    count = 0

    for row in rows:
        rule_desc = row.get("rule_desc") or ""
        if not rule_desc or rule_desc in seen:
            continue
        seen.add(rule_desc)

        issue_desc = row.get("issue_desc") or ""
        conclusion = row.get("conclusion_desc") or ""
        authority_id = row.get("authority_id") or ""
        authority_desc = row.get("authority_desc") or ""
        authority_type = row.get("authority_type") or ""
        score = score_map.get(row.get("rule_id"), 0)

        lines.append(f"\n[similarity={score:.3f}]")
        if issue_desc:
            lines.append(f"Legal Issue : {issue_desc}")
        lines.append(f"Rule        : {rule_desc}")
        if conclusion:
            lines.append(f"Conclusion  : {conclusion}")
        if authority_id:
            auth_label = f"{authority_type} — {authority_id}"
            if authority_desc:
                auth_label += f": {authority_desc[:200]}"
            lines.append(f"Authority   : {auth_label}")
        lines.append("---")

        count += 1
        if count >= top_k:
            break

    return "\n".join(lines) if count > 0 else ""


# ---------------------------------------------------------------------------
# CLI: build cache manually
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    build_cache()
