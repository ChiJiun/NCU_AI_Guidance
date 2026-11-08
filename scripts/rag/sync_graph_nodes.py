"""
sync_graph_nodes.py — 圖譜重建後，用「差異」同步 Qdrant 的 ncu_graph_nodes

為什麼不直接 `build_qdrant_index.py --reset`：
  全量重建會重新 embed 兩萬多筆並大量寫入（資料夾在 OneDrive 底下，曾因同步衝突讓 Qdrant 崩潰）。
  而這個 collection 的向量只由「節點名稱」決定（見 _concept_text），所以：
    - 名稱沒變的節點：向量不用動，只需更新 payload（例如 connected_courses）
    - 新出現的節點：才需要 embed
    - 圖譜已不存在的節點：刪除

用法：
  python scripts/rag/sync_graph_nodes.py                        # 乾跑：只列出計畫
  python scripts/rag/sync_graph_nodes.py --apply --backup out.json   # 實際執行（先把受影響的點與向量備份）
"""

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

_spec = importlib.util.spec_from_file_location("build_qdrant_index", Path(__file__).parent / "build_qdrant_index.py")
bq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bq)

SCROLL_PAGE = 1000


def expected_points(graph: dict) -> dict[int, dict]:
    """依圖譜算出 Qdrant 應有的 {point_id: payload}（與建索引使用同一個 node_payload）。"""
    nodes = graph["nodes"]
    edges = graph.get("links", graph.get("edges", []))
    by_id = {n["id"]: n for n in nodes}
    in_adj: dict[str, list] = {n["id"]: [] for n in nodes}
    for e in edges:
        if e.get("target") in in_adj:
            in_adj[e["target"]].append((e["source"], e.get("relation", "")))
    out = {}
    for n in nodes:
        t = n.get("node_type")
        if (t in bq.INDEXED_TYPES or t == "Course") and (n.get("name") or n.get("node_name") or "").strip():
            out[bq._node_id_to_int(n["id"])] = bq.node_payload(n, by_id, in_adj)
    return out


def plan(existing: dict[int, dict], expected: dict[int, dict]) -> dict:
    to_delete = sorted(set(existing) - set(expected))
    to_add = sorted(set(expected) - set(existing))
    to_update = sorted(i for i in set(existing) & set(expected) if existing[i] != expected[i])
    return {"delete": to_delete, "add": to_add, "update": to_update}


def fetch_existing(client, collection: str) -> dict[int, dict]:
    out, offset = {}, None
    while True:
        pts, offset = client.scroll(collection_name=collection, limit=SCROLL_PAGE, offset=offset,
                                    with_payload=True, with_vectors=False)
        out.update({p.id: p.payload for p in pts})
        if offset is None:
            return out


def main() -> int:
    ap = argparse.ArgumentParser(description="圖譜重建後差異同步 ncu_graph_nodes")
    ap.add_argument("--apply", action="store_true", help="實際執行（預設乾跑）")
    ap.add_argument("--backup", default=None, help="執行前把將被刪除／修改的點（含向量）存成 JSON")
    args = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from qdrant_client.models import PointStruct, PointIdsList, SetPayload, SetPayloadOperation

    graph = json.loads(bq.GRAPH_JSON.read_text(encoding="utf-8"))
    expected = expected_points(graph)
    client = bq._create_qdrant_client(os.environ.get("QDRANT_URL", "http://localhost:6333"), os.environ.get("QDRANT_API_KEY"))
    existing = fetch_existing(client, bq.COLLECTION)
    p = plan(existing, expected)

    print(f"圖譜應有 {len(expected):,} 點｜Qdrant 現有 {len(existing):,} 點")
    print(f"  刪除 {len(p['delete'])}｜新增 {len(p['add'])}｜更新 payload {len(p['update'])}")
    by_type = lambda ids, src: dict(__import__("collections").Counter(src[i].get("node_type") for i in ids))
    print(f"  刪除依類型：{by_type(p['delete'], existing)}｜新增依類型：{by_type(p['add'], expected)}｜更新依類型：{by_type(p['update'], expected)}")
    for label, ids, src in (("刪除", p["delete"], existing), ("新增", p["add"], expected), ("更新", p["update"], expected)):
        print(f"  {label}例：{[src[i].get('name') for i in ids[:6]]}")
    if not args.apply:
        print("乾跑模式：沒有改動 Qdrant。確認後加上 --apply --backup <檔案>")
        return 0

    touched = p["delete"] + p["update"]
    if args.backup and touched:
        saved = []
        for i in range(0, len(touched), 200):
            for r in client.retrieve(bq.COLLECTION, ids=touched[i:i + 200], with_payload=True, with_vectors=True):
                saved.append({"id": r.id, "payload": r.payload, "vector": r.vector})
        Path(args.backup).write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
        print(f"已備份 {len(saved)} 個點到 {args.backup}")

    if p["delete"]:
        client.delete(bq.COLLECTION, points_selector=PointIdsList(points=p["delete"]), wait=True)
        print(f"已刪除 {len(p['delete'])} 點")
    if p["add"]:
        ids = p["add"]
        for i in range(0, len(ids), bq.BATCH_SIZE):
            chunk = ids[i:i + bq.BATCH_SIZE]
            vecs = bq._embed_batch([expected[x]["name"] for x in chunk])
            client.upsert(bq.COLLECTION, points=[PointStruct(id=x, vector=v, payload=expected[x])
                                                 for x, v in zip(chunk, vecs)], wait=True)
        print(f"已新增 {len(ids)} 點（需 embed 的只有這些）")
    if p["update"]:
        for i in range(0, len(p["update"]), 100):
            ops = [SetPayloadOperation(set_payload=SetPayload(payload=expected[x], points=[x]))
                   for x in p["update"][i:i + 100]]
            client.batch_update_points(bq.COLLECTION, update_operations=ops, wait=True)
        print(f"已更新 {len(p['update'])} 點的 payload")

    after = fetch_existing(client, bq.COLLECTION)
    left = plan(after, expected)
    print(f"驗證：Qdrant 現有 {len(after):,} 點｜與圖譜差異 刪除 {len(left['delete'])}／新增 {len(left['add'])}／更新 {len(left['update'])}")
    return 0 if not any(left.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
