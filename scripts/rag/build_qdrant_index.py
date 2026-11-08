"""
build_qdrant_index.py — 建立 ncu_graph_nodes Qdrant collection

將知識圖譜中的 Concept / Technology / Field 節點嵌入為向量，
存入本地 Qdrant（無需 Docker / 雲端），供 explore_concept_neighborhood 向量入口使用。

用法：
  python scripts/rag/build_qdrant_index.py
  python scripts/rag/build_qdrant_index.py --reset   # 強制重建（清空舊資料）

前置條件：
  - 已安裝 qdrant-client：pip install qdrant-client
  - 已設定 AZURE_OPENAI_API_KEY / AZURE_OPENAI_ENDPOINT 環境變數
  - 已存在 data/processed/graph/knowledge_graph.json
"""

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent

GRAPH_JSON  = ROOT / "data" / "processed" / "graph" / "knowledge_graph.json"
QDRANT_DIR  = ROOT / "data" / "processed" / "qdrant_data"
COLLECTION  = "ncu_graph_nodes"
VECTOR_DIM  = 3072  # text-embedding-3-large

# 豐富文字節點類型（名稱 + 相關課程）
INDEXED_TYPES = {"Concept", "Technology", "Field", "Competency"}
# Course 節點用精簡文字（只放課名 + 系所，避免與 Concept 節點語意混淆）

# 每批 embed 的筆數（避免 API rate limit）
BATCH_SIZE = 32


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _create_qdrant_client(url: str, api_key: str | None):
    from qdrant_client import QdrantClient
    prefer_grpc = _env_bool("QDRANT_PREFER_GRPC", False)
    grpc_port = _env_int("QDRANT_GRPC_PORT", 6334)
    timeout = _env_float("QDRANT_TIMEOUT_SEC", 60.0)
    return QdrantClient(
        url=url,
        api_key=api_key,
        prefer_grpc=prefer_grpc,
        grpc_port=grpc_port,
        timeout=timeout,
    )


def _get_oai():
    from openai import AzureOpenAI
    return AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01"),
    )


def _embed_batch(texts: list[str]) -> list[list[float]]:
    deployment = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")
    for attempt in range(3):
        try:
            resp = _get_oai().embeddings.create(model=deployment, input=texts)
            return [item.embedding for item in resp.data]
        except Exception as ex:
            if attempt == 2:
                raise
            delay = 2 ** attempt
            print(f"  [WARN] embed 失敗，{delay}s 後重試：{ex}")
            time.sleep(delay)
    return []


def _node_id_to_int(node_id: str) -> int:
    """將字串 node_id 轉為穩定的正整數（Qdrant point id）。"""
    return int(hashlib.md5(node_id.encode()).hexdigest()[:15], 16)


def build_connected_courses(node_id: str, in_adj: dict) -> list[str]:
    """找與此節點有課程連結邊的來源課程 ID（最多 10 筆）。
    支援 Concept/Technology/Field（COVERS/TEACHES/COVERS_FIELD）與
    Competency（DEVELOPS）節點。
    """
    COURSE_RELS = {"COVERS", "TEACHES", "COVERS_FIELD", "DEVELOPS"}
    courses = []
    for src, rel in in_adj.get(node_id, []):
        if rel in COURSE_RELS:
            courses.append(src)
        if len(courses) >= 10:
            break
    return courses


def _concept_text(n: dict, nodes_by_id: dict, in_adj: dict) -> str:
    """Concept / Technology / Field：只放節點名稱，避免相關課程汙染語意。"""
    return n.get("name", "") or n.get("node_name", "")


def _course_text(n: dict, nodes_by_id: dict, in_adj: dict) -> str:
    """Course：只放課程名稱，系所不放入 embedding 避免語意偏移。"""
    return n.get("name", "") or n.get("node_name", "")


def node_payload(n: dict, nodes_by_id: dict, in_adj: dict) -> dict:
    """單一圖譜節點在 Qdrant 的 payload（建索引與差異同步共用，避免兩邊漂移）。"""
    nid   = n["id"]
    ntype = n.get("node_type", "")
    name  = n.get("name", "") or n.get("node_name", "")
    if ntype == "Course":
        return {
            "node_id":   nid,
            "node_type": ntype,
            "name":      name,
            "dept":      n.get("dept", ""),
            "college":   n.get("college", ""),
            "level":     n.get("level", ""),   # "ugrad" / "grad"
        }
    connected    = build_connected_courses(nid, in_adj)
    course_names = [nodes_by_id.get(c, {}).get("name", c) for c in connected]
    return {
        "node_id":           nid,
        "node_type":         ntype,
        "name":              name,
        "source":            n.get("source", ""),
        "connected_courses": course_names,
    }


def _upsert_nodes(client, nodes: list, nodes_by_id: dict, in_adj: dict,
                  text_fn, args) -> tuple[int, int]:
    """分批 embed 並 upsert，回傳 (uploaded, errors)。"""
    from qdrant_client.models import PointStruct
    limit = getattr(args, "limit", 0)
    if limit:
        nodes = nodes[:limit]
    uploaded, errors = 0, 0
    total = len(nodes)
    for start in range(0, total, BATCH_SIZE):
        batch = nodes[start: start + BATCH_SIZE]
        texts = [text_fn(n, nodes_by_id, in_adj) for n in batch]
        try:
            vectors = _embed_batch(texts)
        except Exception as ex:
            print(f"  [ERROR] embed batch {start}-{start+len(batch)}：{ex}")
            errors += len(batch)
            time.sleep(2)
            continue

        points = []
        for n, vec in zip(batch, vectors):
            points.append(PointStruct(id=_node_id_to_int(n["id"]), vector=vec,
                                      payload=node_payload(n, nodes_by_id, in_adj)))

        _upsert_with_retry(client, COLLECTION, points)
        uploaded += len(points)
        print(f"  上傳 {uploaded}/{total} 筆...", end="\r")
        time.sleep(0.1)
    print()
    return uploaded, errors


def _upsert_with_retry(client, collection_name: str, points: list) -> None:
    retries = max(1, _env_int("QDRANT_UPSERT_RETRIES", 5))
    wait = _env_bool("QDRANT_UPSERT_WAIT", False)
    for attempt in range(retries):
        try:
            client.upsert(collection_name=collection_name, points=points, wait=wait)
            return
        except Exception as ex:
            if attempt == retries - 1:
                raise
            delay = min(30, 2 ** attempt)
            print(f"  [WARN] upsert 失敗，{delay}s 後重試：{ex}")
            time.sleep(delay)


def _build_course_concept_vecs(
    node_list: list,
    nodes_by_id: dict,
    edge_list: list,
    args,
    out_path: Path,
) -> None:
    """Phase 3：為每門課程建立「概念平均向量」並存成 .npz 檔（不開 Qdrant，無 OOM）。

    輸出：out_path.npz（或直接 out_path 副檔名為 .npz）
      - names: shape (N,), dtype str   — 課程中文名稱
      - vecs:  shape (N, D), dtype float32 — L2-normalized 概念平均向量
      - depts: shape (N,), dtype str   — 系所
      - codes: shape (N,), dtype str   — node_id（course::xxx）

    搜尋端（retriever.py）直接 np.load + cosine sim，不需要 Qdrant。
    """
    import numpy as np

    # 準備 concept edge 對應表：course_node_id → list[concept_node_id]
    CONCEPT_RELS = {"COVERS", "TEACHES", "COVERS_FIELD"}
    course_to_concepts: dict[str, list[str]] = {}
    for e in edge_list:
        rel = e.get("relation", "")
        if rel not in CONCEPT_RELS:
            continue
        src, tgt = e["source"], e["target"]
        if (nodes_by_id.get(src, {}).get("node_type") == "Course"
                and nodes_by_id.get(tgt, {}).get("node_type") in ("Concept", "Technology", "Field")):
            course_to_concepts.setdefault(src, []).append(tgt)

    # 去重：只 embed 實際被課程用到的概念節點名稱
    used_concept_ids: set[str] = {
        nid for nids in course_to_concepts.values() for nid in nids
    }
    concept_id_list = list(used_concept_ids)
    concept_names   = [nodes_by_id.get(nid, {}).get("name", nid) for nid in concept_id_list]
    print(f"  課程實際用到的概念節點：{len(concept_id_list)} 個（去重後）")

    limit_n = getattr(args, "limit", 0)
    if limit_n:
        concept_id_list = concept_id_list[:limit_n]
        concept_names   = concept_names[:limit_n]

    # Embed 概念名稱（batch）
    print(f"  embed {len(concept_id_list)} 個概念名稱（批大小 {BATCH_SIZE}）...")
    concept_vecs: dict[str, list[float]] = {}
    for start in range(0, len(concept_id_list), BATCH_SIZE):
        batch_ids   = concept_id_list[start: start + BATCH_SIZE]
        batch_names = concept_names[start: start + BATCH_SIZE]
        try:
            vectors = _embed_batch(batch_names)
            for nid, vec in zip(batch_ids, vectors):
                concept_vecs[nid] = vec
        except Exception as ex:
            print(f"\n  [ERROR] embed batch {start}: {ex}")
            time.sleep(2)
        done = min(start + BATCH_SIZE, len(concept_id_list))
        print(f"  embed 進度：{done}/{len(concept_id_list)}", end="\r")
    print(f"\n  embed 完成，取得 {len(concept_vecs)} 個概念向量")

    # 計算每門課的概念平均向量
    course_nodes = [n for n in node_list if n.get("node_type") == "Course"]
    names_out, codes_out, depts_out, vecs_out = [], [], [], []
    skipped = 0
    for n in course_nodes:
        nid      = n["id"]
        cname    = n.get("name", "")
        if not cname:
            skipped += 1
            continue
        concepts = course_to_concepts.get(nid, [])
        c_vecs   = [concept_vecs[c] for c in concepts if c in concept_vecs]
        if not c_vecs:
            skipped += 1
            continue
        arr      = np.array(c_vecs, dtype=np.float32)
        mean_vec = arr.mean(axis=0)
        norm     = np.linalg.norm(mean_vec)
        if norm > 0:
            mean_vec /= norm
        names_out.append(cname)
        codes_out.append(nid)
        depts_out.append(n.get("dept", ""))
        vecs_out.append(mean_vec)

    # 儲存 .npz
    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        str(out_path),
        names=np.array(names_out),
        codes=np.array(codes_out),
        depts=np.array(depts_out),
        vecs=np.array(vecs_out, dtype=np.float32),
    )
    print(f"  完成：{len(names_out)} 筆，跳過（無名稱/無概念邊）{skipped} 筆")
    print(f"  輸出：{out_path}")


def _get_existing_qdrant_ids(client, collection: str, ids: list[int]) -> set[int]:
    """分批查詢 Qdrant，回傳已存在的 point id 集合。"""
    existing: set[int] = set()
    for start in range(0, len(ids), 200):
        batch = ids[start: start + 200]
        found = client.retrieve(collection_name=collection, ids=batch, with_vectors=False)
        existing.update(p.id for p in found)
    return existing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset",        action="store_true", help="強制重建，清空舊資料")
    parser.add_argument("--limit",        type=int, default=0, help="只處理前 N 筆（0=全量，測試用）")
    parser.add_argument("--phase3",       action="store_true", help="執行 Phase 3：建立 ncu_course_concept_vecs")
    parser.add_argument("--sync-courses", action="store_true",
                        help="增量同步：只 embed 圖中有但 Qdrant 缺少的 Course 節點（省費用）")
    args = parser.parse_args()

    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams, PointStruct
    except ImportError:
        print("請先安裝：pip install qdrant-client")
        return

    if not GRAPH_JSON.exists():
        print(f"找不到圖譜檔案：{GRAPH_JSON}")
        return

    print("載入知識圖譜...")
    raw = json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
    node_list = raw["nodes"]
    edge_list  = raw.get("links", raw.get("edges", []))

    # 建立 node_id → attrs 對應
    nodes_by_id: dict[str, dict] = {n["id"]: n for n in node_list}

    # 建立反向鄰接表（只需要 in_adj 找連結課程）
    in_adj: dict[str, list[tuple[str, str]]] = {n["id"]: [] for n in node_list}
    for e in edge_list:
        tgt = e.get("target", "")
        if tgt in in_adj:
            in_adj[tgt].append((e["source"], e.get("relation", "")))

    # 過濾目標節點（Phase 1 用）
    target_nodes = [
        n for n in node_list
        if n.get("node_type") in INDEXED_TYPES and n.get("name", "").strip()
    ]
    print(f"Concept/Technology/Field/Competency 節點：{len(target_nodes)} 筆")
    print(f"Course 節點：{sum(1 for n in node_list if n.get('node_type') == 'Course')} 筆")

    # ── Phase 3 only（不開 Qdrant，完全繞過 OOM）────────────────────────────
    if args.phase3 and not args.reset and not args.sync_courses:
        print("\n[--phase3 模式] 跳過 Phase 1/2 與 Qdrant 初始化，直接執行 Phase 3")
    else:
        # 建立 Qdrant client（Phase 1/2 才需要）
        qdrant_url = os.environ.get("QDRANT_URL", "")
        qdrant_api_key = os.environ.get("QDRANT_API_KEY")
        if qdrant_url:
            client = _create_qdrant_client(qdrant_url, qdrant_api_key)
        else:
            QDRANT_DIR.mkdir(parents=True, exist_ok=True)
            client = QdrantClient(path=str(QDRANT_DIR))

        existing_cols = [c.name for c in client.get_collections().collections]
        if COLLECTION in existing_cols:
            if args.reset:
                print(f"刪除舊 collection：{COLLECTION}")
                client.delete_collection(COLLECTION)
                client.create_collection(
                    collection_name=COLLECTION,
                    vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
                )
                print(f"重建 collection：{COLLECTION}（dim={VECTOR_DIM}）")
            else:
                print(f"Collection '{COLLECTION}' 已存在，直接 upsert（使用 --reset 強制重建）")
        else:
            client.create_collection(
                collection_name=COLLECTION,
                vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
            )
            print(f"建立 collection：{COLLECTION}（dim={VECTOR_DIM}）")

        # ── --sync-courses：只補缺少的 Course 節點 ───────────────────────────────
        if args.sync_courses:
            course_nodes = [
                n for n in node_list
                if n.get("node_type") == "Course" and n.get("name", "").strip()
            ]
            all_point_ids = [_node_id_to_int(n["id"]) for n in course_nodes]
            print(f"\n[--sync-courses] 圖中 Course 節點：{len(course_nodes)} 筆，查詢 Qdrant 現有狀態...")
            existing_ids = _get_existing_qdrant_ids(client, COLLECTION, all_point_ids)
            new_nodes = [
                n for n, pid in zip(course_nodes, all_point_ids)
                if pid not in existing_ids
            ]
            print(f"  Qdrant 已有：{len(existing_ids)} 筆，待補：{len(new_nodes)} 筆")
            if new_nodes:
                uploaded, errors = _upsert_nodes(
                    client, new_nodes, nodes_by_id, in_adj,
                    text_fn=_course_text, args=args,
                )
                print(f"  完成：上傳 {uploaded} 筆，錯誤 {errors} 筆")
            else:
                print("  Course 節點已全部同步，無需更新。")
            info = client.get_collection(COLLECTION)
            print(f"\n✓ {COLLECTION} 總筆數：{info.points_count}")
            print(f"Qdrant 資料位置：{QDRANT_DIR}")

        else:
            # ── Phase 1：Concept / Technology / Field / Competency 節點 ────────────
            print(f"\n[Phase 1] Concept / Technology / Field / Competency 節點：{len(target_nodes)} 筆")
            uploaded, errors = _upsert_nodes(
                client, target_nodes, nodes_by_id, in_adj,
                text_fn=_concept_text, args=args,
            )
            print(f"  完成：上傳 {uploaded} 筆，錯誤 {errors} 筆")

            # ── Phase 2：Course 節點（精簡文字，只放課名 + 系所） ────────────────────
            course_nodes = [
                n for n in node_list
                if n.get("node_type") == "Course" and n.get("name", "").strip()
            ]
            print(f"\n[Phase 2] Course 節點：{len(course_nodes)} 筆")
            uploaded, errors = _upsert_nodes(
                client, course_nodes, nodes_by_id, in_adj,
                text_fn=_course_text, args=args,
            )
            print(f"  完成：上傳 {uploaded} 筆，錯誤 {errors} 筆")

            info = client.get_collection(COLLECTION)
            print(f"\n✓ {COLLECTION} 總筆數：{info.points_count}")
            print(f"Qdrant 資料位置：{QDRANT_DIR}")

    # ── Phase 3：Course concept-averaged vectors（.npz，不開 Qdrant）──────────
    if args.phase3:
        print(f"\n[Phase 3] 建立 ncu_course_concept_vecs.npz（每課概念平均向量）")
        try:
            import numpy  # noqa: F401
        except ImportError:
            print("  [ERROR] 請先安裝 numpy：pip install numpy")
        else:
            out_npz = QDRANT_DIR.parent / "ncu_course_concept_vecs.npz"
            _build_course_concept_vecs(
                node_list, nodes_by_id, edge_list, args, out_path=out_npz
            )


if __name__ == "__main__":
    from dotenv import load_dotenv
    # 依序嘗試常見的 .env 位置
    for env_path in [ROOT / ".env", ROOT / "backend" / ".env", Path(".env")]:
        if env_path.exists():
            load_dotenv(env_path)
            print(f"載入環境變數：{env_path}")
            break

    # 提前驗證必要環境變數
    missing = [k for k in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT") if not os.environ.get(k)]
    if missing:
        print(f"[錯誤] 缺少環境變數：{missing}")
        print("請確認 .env 檔案存在且包含以下設定：")
        print("  AZURE_OPENAI_API_KEY=...")
        print("  AZURE_OPENAI_ENDPOINT=...")
    else:
        main()
