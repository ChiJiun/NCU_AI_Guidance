"""
retriever.py

Qdrant 向量搜尋介面，對應六個 collection：
  ncu_courses_ug / ncu_courses_grad / ncu_credit_programs
  ncu_departments / ncu_teachers / ncu_graph_nodes

filters 參數沿用 ChromaDB where 語法（dict），由 _qdrant_filter() 內部轉換，
tools.py 不需要修改。
"""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.services.bedrock_client import get_ai_client
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Filter, FieldCondition, MatchValue, MatchAny,
    Prefetch, FusionQuery, Fusion, SparseVector,
)

ROOT = Path(__file__).parent.parent.parent.parent
QDRANT_DIR        = ROOT / "data" / "processed" / "qdrant_data"
_ELIGIBILITY_PATH = ROOT / "data" / "processed" / "course_eligibility.json"
_COLLEGE_MAP_PATH = ROOT / "data" / "processed" / "dept_college_map.json"


@lru_cache(maxsize=1)
def _get_qdrant() -> QdrantClient:
    qdrant_url = os.getenv("QDRANT_URL", "").strip()
    if qdrant_url:
        return QdrantClient(
            url=qdrant_url,
            api_key=os.getenv("QDRANT_API_KEY", "").strip() or None,
            timeout=30,
        )
    return QdrantClient(path=str(QDRANT_DIR))


_bm25_model = None  # 模組級快取，避免每次重新載入


def _get_bm25():
    global _bm25_model
    if _bm25_model is None:
        from fastembed import SparseTextEmbedding
        _bm25_model = SparseTextEmbedding(model_name="Qdrant/bm25")
    return _bm25_model


def _sparse_embed(text: str):
    return list(_get_bm25().embed([text]))[0]


_DENSE_ONLY_COLLECTIONS = {"ncu_graph_nodes"}


def _merge_must_not(base_filter: Filter | None, must_not_conds: list[dict]) -> Filter | None:
    """將 must_not_conds（ChromaDB 語法 list）合併進 base_filter。

    must_not_conds 格式範例：
      [{"dept_exclude": {"$contains": "資工系"}}, {"dept_exclude": {"$contains": "電機系"}}]
    → 每個 $contains 轉換為 FieldCondition(MatchAny)，放入 filter.must_not
    """
    if not must_not_conds:
        return base_filter
    mn_conditions = []
    for cond in must_not_conds:
        for key, op in cond.items():
            if not isinstance(op, dict):
                continue
            if "$contains" in op:
                mn_conditions.append(FieldCondition(key=key, match=MatchAny(any=[op["$contains"]])))
            elif "$eq" in op:
                mn_conditions.append(FieldCondition(key=key, match=MatchValue(value=op["$eq"])))
    if not mn_conditions:
        return base_filter
    if base_filter is None:
        return Filter(must_not=mn_conditions)
    existing_mn = list(base_filter.must_not or [])
    base_filter.must_not = existing_mn + mn_conditions
    return base_filter


def _hybrid_search(client, collection, dense_vec, query_text, qdrant_filter, n_results):
    """Dense + BM25 prefetch → RRF 融合；graph_nodes 或失敗時降級為純 dense。"""
    if collection in _DENSE_ONLY_COLLECTIONS:
        result = client.query_points(
            collection_name=collection,
            query=dense_vec,
            query_filter=qdrant_filter,
            limit=n_results,
            with_payload=True,
        )
        return result.points
    try:
        sp = _sparse_embed(query_text)
        result = client.query_points(
            collection_name=collection,
            prefetch=[
                Prefetch(query=dense_vec, limit=n_results * 3),
                Prefetch(
                    query=SparseVector(
                        indices=sp.indices.tolist(),
                        values=sp.values.tolist(),
                    ),
                    using="bm25",
                    limit=n_results * 3,
                ),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            query_filter=qdrant_filter,
            limit=n_results,
            with_payload=True,
        )
        return result.points
    except Exception:
        result = client.query_points(
            collection_name=collection,
            query=dense_vec,
            query_filter=qdrant_filter,
            limit=n_results,
            with_payload=True,
        )
        return result.points


@lru_cache(maxsize=512)
def _embed(text: str) -> list[float]:
    # Titan Text Embeddings V2（1024 維，已 normalize）；模型 ID 與維度見 bedrock_client
    resp = get_ai_client().embeddings.create(input=[text])
    return resp.data[0].embedding


@lru_cache(maxsize=1)
def _load_eligibility_index() -> dict[str, dict]:
    if not _ELIGIBILITY_PATH.exists():
        return {}
    data = json.loads(_ELIGIBILITY_PATH.read_text(encoding="utf-8"))
    return {entry["course_code"]: entry for entry in data if entry.get("course_code")}


def get_course_eligibility(course_code: str) -> dict:
    """回傳課程的完整修課資格資料，直接從 JSON 讀取。"""
    return _load_eligibility_index().get(course_code, {})


@lru_cache(maxsize=1)
def _load_college_map() -> dict[str, str]:
    if not _COLLEGE_MAP_PATH.exists():
        return {}
    return json.loads(_COLLEGE_MAP_PATH.read_text(encoding="utf-8"))


def get_dept_college(dept: str) -> str:
    """回傳系所所屬學院名稱，查無則回傳空字串。"""
    return _load_college_map().get(dept, "")


# ── Filter 轉換 ───────────────────────────────────────────────────────────────

def _qdrant_filter(chroma_filter: dict) -> Filter:
    """ChromaDB where 語法 → Qdrant Filter（遞迴轉換）。

    支援：
      {"field": {"$eq": value}}
      {"field": {"$contains": value}}  →  MatchAny（payload 中該欄位為陣列）
      {"$and": [...]}
      {"$or": [...]}
    """
    if "$and" in chroma_filter:
        return Filter(must=[_qdrant_filter(f) for f in chroma_filter["$and"]])
    if "$or" in chroma_filter:
        return Filter(should=[_qdrant_filter(f) for f in chroma_filter["$or"]])

    conditions = []
    for key, cond in chroma_filter.items():
        if key.startswith("$") or not isinstance(cond, dict):
            continue
        if "$eq" in cond:
            conditions.append(FieldCondition(key=key, match=MatchValue(value=cond["$eq"])))
        elif "$contains" in cond:
            # payload 中此欄位為 list[str]，用 MatchAny 做成員匹配
            conditions.append(FieldCondition(key=key, match=MatchAny(any=[cond["$contains"]])))

    if len(conditions) == 1:
        return Filter(must=conditions)
    return Filter(must=conditions)


# ── 輸出格式化 ────────────────────────────────────────────────────────────────

def _fmt_search(hits) -> list[dict]:
    """ScoredPoint list → 標準化 list[dict]"""
    results = []
    for h in hits:
        payload = h.payload or {}
        results.append({
            "id":       str(h.id),
            "document": payload.get("_text", ""),
            "metadata": {k: v for k, v in payload.items() if k != "_text"},
            "distance": round(max(0.0, 1.0 - h.score), 4),
        })
    return results


def _fmt_scroll(records) -> list[dict]:
    """Record list → 標準化 list[dict]"""
    results = []
    for r in records:
        payload = r.payload or {}
        results.append({
            "id":       str(r.id),
            "document": payload.get("_text", ""),
            "metadata": {k: v for k, v in payload.items() if k != "_text"},
            "distance": 0.0,
        })
    return results


# ── 公開介面 ─────────────────────────────────────────────────────────────────

def search_courses(
    query: str,
    filters: Optional[dict] = None,
    n_results: int = 10,
    collection: str = "ncu_courses_ug",
    must_not_conds: Optional[list[dict]] = None,
) -> list[dict]:
    """向量搜尋課程。

    filters 使用 ChromaDB where 語法，內部自動轉為 Qdrant Filter。
    must_not_conds：list[dict]，格式同 filters，但轉為 Qdrant must_not 條件，
      用於排除特定欄位值（例如排除 dept_exclude 含指定系所的課程）。
    filterable 欄位（tools/languages/concepts/when_semesters/eligible_years 等）
    在 Qdrant payload 中以陣列儲存，支援 $contains → MatchAny 轉換。
    """
    embedding = _embed(query)
    client = _get_qdrant()
    qdrant_filter = _qdrant_filter(filters) if filters else None
    qdrant_filter = _merge_must_not(qdrant_filter, must_not_conds or [])

    try:
        points = _hybrid_search(client, collection, embedding, query, qdrant_filter, n_results)
        return _fmt_search(points)
    except Exception:
        if filters:
            try:
                points = _hybrid_search(client, collection, embedding, query, None, n_results)
                return _fmt_search(points)
            except Exception:
                pass
        return []


def search_programs(query: str, n_results: int = 5) -> list[dict]:
    emb = _embed(query)
    return _fmt_search(_hybrid_search(_get_qdrant(), "ncu_credit_programs", emb, query, None, n_results))


def search_departments(query: str, n_results: int = 5) -> list[dict]:
    emb = _embed(query)
    return _fmt_search(_hybrid_search(_get_qdrant(), "ncu_departments", emb, query, None, n_results))


def search_teachers(
    query: str,
    filters: Optional[dict] = None,
    n_results: int = 8,
) -> list[dict]:
    emb = _embed(query)
    f = _qdrant_filter(filters) if filters else None
    return _fmt_search(_hybrid_search(_get_qdrant(), "ncu_teachers", emb, query, f, n_results))


def get_teacher_by_name(name: str) -> list[dict]:
    """直接用姓名查教師（不走向量）。"""
    records, _ = _get_qdrant().scroll(
        collection_name="ncu_teachers",
        scroll_filter=Filter(must=[FieldCondition(key="name", match=MatchValue(value=name))]),
        limit=10,
        with_payload=True,
        with_vectors=False,
    )
    return _fmt_scroll(records)


def get_courses_by_code(code: str, collection: str = "ncu_courses_ug") -> list[dict]:
    """直接用課號查課程（不走向量）。"""
    records, _ = _get_qdrant().scroll(
        collection_name=collection,
        scroll_filter=Filter(must=[FieldCondition(key="course_code", match=MatchValue(value=code))]),
        limit=10,
        with_payload=True,
        with_vectors=False,
    )
    return _fmt_scroll(records)


def get_courses_by_dept_type(
    dept: str,
    course_type: str = "選修",
    collection: str = "ncu_courses_ug",
    limit: int = 200,
) -> list[dict]:
    """直接用 dept + type 精確過濾，回傳全部課程（不走向量）。"""
    records, _ = _get_qdrant().scroll(
        collection_name=collection,
        scroll_filter=Filter(must=[
            FieldCondition(key="dept", match=MatchValue(value=dept)),
            FieldCondition(key="type", match=MatchValue(value=course_type)),
        ]),
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    return _fmt_scroll(records)


def get_courses_by_name(
    name: str,
    collection: str = "ncu_courses_ug",
    also_grad: bool = True,
) -> list[dict]:
    """用課程名稱精確比對，同時搜大學部與研究所（課程消歧義用）。"""
    results = []
    cols = [collection]
    if also_grad and collection == "ncu_courses_ug":
        cols.append("ncu_courses_grad")
    for col_name in cols:
        records, _ = _get_qdrant().scroll(
            collection_name=col_name,
            scroll_filter=Filter(must=[FieldCondition(key="name_zh", match=MatchValue(value=name))]),
            limit=50,
            with_payload=True,
            with_vectors=False,
        )
        results.extend(_fmt_scroll(records))
    return results


_CONCEPT_VEC_INDEX: dict | None = None  # 快取載入的 npz 資料
_CONCEPT_VEC_NPZ   = ROOT / "data" / "processed" / "ncu_course_concept_vecs.npz"


def _load_concept_vec_index() -> dict | None:
    """載入 ncu_course_concept_vecs.npz，快取後回傳。檔案不存在回傳 None。"""
    global _CONCEPT_VEC_INDEX
    if _CONCEPT_VEC_INDEX is not None:
        return _CONCEPT_VEC_INDEX
    if not _CONCEPT_VEC_NPZ.exists():
        return None
    try:
        import numpy as np
        data = np.load(str(_CONCEPT_VEC_NPZ), allow_pickle=False)
        _CONCEPT_VEC_INDEX = {
            "names": data["names"],   # shape (N,)
            "codes": data["codes"],   # shape (N,)
            "depts": data["depts"],   # shape (N,)
            "vecs":  data["vecs"].astype("float32"),  # shape (N, D)
        }
        return _CONCEPT_VEC_INDEX
    except Exception:
        return None


def search_by_concept_vec_for(
    course_name: str,
    n_results: int = 15,
) -> list[dict]:
    """Option A：用課程的概念平均向量搜尋最相似課程（ncu_course_concept_vecs.npz）。

    需先執行 build_qdrant_index.py --phase3。
    檔案不存在時回傳空 list（靜默降級）。
    """
    import numpy as np
    idx = _load_concept_vec_index()
    if idx is None:
        return []

    names = idx["names"]
    vecs  = idx["vecs"]
    depts = idx["depts"]
    codes = idx["codes"]

    # 找查詢課程的向量
    matches = np.where(names == course_name)[0]
    if len(matches) == 0:
        return []
    q_vec = vecs[matches[0]]  # shape (D,)

    # Cosine similarity（vecs 已 L2-normalize，直接點積）
    sims   = vecs @ q_vec          # shape (N,)
    order  = np.argsort(-sims)     # 降序

    results = []
    for i in order:
        if names[i] == course_name:
            continue
        results.append({
            "id":       str(codes[i]),
            "document": "",
            "metadata": {
                "name_zh": str(names[i]),
                "dept":    str(depts[i]),
            },
            "distance": round(float(1.0 - sims[i]), 4),
        })
        if len(results) >= n_results:
            break
    return results
