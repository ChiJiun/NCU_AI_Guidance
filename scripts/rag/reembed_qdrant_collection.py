"""
reembed_qdrant_collection.py — 把既有 Qdrant collection 用 Bedrock Titan 重新向量化

用途：從 Azure text-embedding-3-large（3072 維）遷移到 Amazon Bedrock Titan Text Embeddings V2
（預設 1024 維）時，維度不同、向量不能共用，所有 collection 都必須重新向量化。
課程／系所／教師／學程／圖譜節點可以直接用 build_vector_index.py、build_qdrant_index.py 從原始資料
重建；PDF 研究計畫的 `reports` collection 沒有對應的建索引腳本，改用本腳本：

  1. 從來源 collection 讀出所有 point（payload + sparse 向量）
  2. 取出 payload 內的文字欄位（預設 `_text`；LangChain 寫入的是 `page_content`）重新 embed
  3. 在目的 collection 以相同 id / payload / sparse 向量寫入新的 dense 向量

來源與目的可以是同一個 Qdrant、不同 collection 名稱，切換時只需把後端環境變數
`PDF_QDRANT_COLLECTION` 指到新名稱（舊 collection 保留，可隨時回滾）。

用法：
  # 先 dry-run：只列出來源 collection 的結構，不呼叫 Bedrock、不寫入
  python scripts/rag/reembed_qdrant_collection.py reports --text-field page_content --dry-run

  python scripts/rag/reembed_qdrant_collection.py reports --text-field page_content \\
      --dest reports_titan1024

  # 來源是本機 local-mode 資料夾
  python scripts/rag/reembed_qdrant_collection.py ncu_courses_ug --src-path data/processed/qdrant_data

環境變數：QDRANT_URL / QDRANT_API_KEY（來源與目的預設都用這組）；
Bedrock 憑證與區域見 backend/app/services/bedrock_client.py。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from qdrant_client import QdrantClient, models  # noqa: E402

EmbedFn = Callable[[list[str]], list[list[float]]]


def get_by_path(payload: dict, dotted: str) -> Any:
    cur: Any = payload
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _dense_configs(info) -> dict[str | None, models.VectorParams]:
    """回傳 {向量名稱 or None: VectorParams}；None 代表未命名的單一向量。"""
    vectors = info.config.params.vectors
    if isinstance(vectors, dict):
        return dict(vectors)
    return {None: vectors}


def create_dest_collection(src: QdrantClient, dst: QdrantClient, name: str, dest: str, dim: int) -> None:
    info = src.get_collection(name)
    dense = _dense_configs(info)
    vectors_config: Any = {
        key: models.VectorParams(size=dim, distance=cfg.distance) for key, cfg in dense.items() if key is not None
    } or models.VectorParams(size=dim, distance=dense[None].distance)
    sparse = info.config.params.sparse_vectors or None
    dst.create_collection(
        collection_name=dest,
        vectors_config=vectors_config,
        sparse_vectors_config=sparse,
    )
    # 複製 payload index（失敗不致命：只影響過濾效能，不影響結果）
    for field, schema in (info.payload_schema or {}).items():
        try:
            dst.create_payload_index(dest, field_name=field, field_schema=schema.data_type)
        except Exception as exc:  # noqa: BLE001
            print(f"  [WARN] payload index {field} 建立失敗：{exc}")


def reembed(
    src: QdrantClient,
    dst: QdrantClient,
    collection: str,
    dest: str,
    *,
    text_field: str,
    embed: EmbedFn,
    dim: int,
    batch_size: int = 64,
    limit: int = 0,
    recreate: bool = False,
) -> int:
    if src is dst and dest == collection:
        raise RuntimeError("目的 collection 不可與來源同名（同一個 Qdrant 內會覆蓋來源）。")
    existing = {c.name for c in dst.get_collections().collections}
    if dest in existing:
        if not recreate:
            raise RuntimeError(f"目的 collection '{dest}' 已存在；確定要覆蓋請加 --recreate。")
        dst.delete_collection(dest)
    create_dest_collection(src, dst, collection, dest, dim)

    dense_names = [k for k in _dense_configs(src.get_collection(collection))]
    total = skipped = 0
    offset = None
    while True:
        points, offset = src.scroll(
            collection, limit=batch_size, offset=offset, with_payload=True, with_vectors=True
        )
        if not points:
            break
        texts, keep = [], []
        for p in points:
            text = get_by_path(p.payload or {}, text_field)
            if isinstance(text, str) and text.strip():
                texts.append(text)
                keep.append(p)
            else:
                skipped += 1
        if keep:
            new_dense = embed(texts)
            out = []
            for p, vec in zip(keep, new_dense):
                if dense_names == [None]:
                    vector: Any = vec
                else:
                    # 具名向量：保留 sparse 等其他向量，只換掉 dense
                    vector = {k: v for k, v in (p.vector or {}).items() if k not in dense_names}
                    vector.update({k: vec for k in dense_names if k is not None})
                out.append(models.PointStruct(id=p.id, vector=vector, payload=p.payload))
            dst.upsert(dest, points=out)
            total += len(out)
            print(f"  已寫入 {total} 筆（略過無文字 {skipped} 筆）")
        if limit and total >= limit:
            break
        if offset is None:
            break
    return total


def _client(url: str | None, api_key: str | None, path: str | None) -> QdrantClient:
    if path:
        return QdrantClient(path=path)
    if not url:
        raise SystemExit("請設定 QDRANT_URL（或用 --src-path 指定本機資料夾）")
    return QdrantClient(url=url, api_key=api_key or None, timeout=60)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("collection", help="來源 collection 名稱")
    parser.add_argument("--dest", help="目的 collection 名稱（預設：<來源>_titan<維度>）")
    parser.add_argument("--text-field", default="_text", help="payload 內的文字欄位，支援 a.b 巢狀（預設 _text）")
    parser.add_argument("--src-path", help="來源為本機 local-mode 資料夾時使用")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--limit", type=int, default=0, help="只處理前 N 筆（測試用，0=全部）")
    parser.add_argument("--recreate", action="store_true", help="目的 collection 已存在時刪除重建")
    parser.add_argument("--dry-run", action="store_true", help="只檢視來源結構，不呼叫 Bedrock、不寫入")
    args = parser.parse_args()

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from app.services.bedrock_client import embedding_dim, get_ai_client

    dim = embedding_dim()
    dest = args.dest or f"{args.collection}_titan{dim}"
    url, key = os.getenv("QDRANT_URL", "").strip(), os.getenv("QDRANT_API_KEY", "").strip()
    src = _client(url, key, args.src_path)
    dst = _client(url, key, None) if url else src

    info = src.get_collection(args.collection)
    sample, _ = src.scroll(args.collection, limit=1, with_payload=True, with_vectors=False)
    print(f"來源 {args.collection}: points={info.points_count} dense={ {k: v.size for k, v in _dense_configs(info).items()} } "
          f"sparse={list(info.config.params.sparse_vectors or {})}")
    print(f"  payload 欄位範例：{sorted(sample[0].payload)[:20] if sample else '(空)'}")
    print(f"  文字欄位 {args.text_field!r} 範例長度：{len(str(get_by_path(sample[0].payload, args.text_field) or '')) if sample else 0}")
    if args.dry_run:
        print(f"[dry-run] 將寫入 {dest}（dim={dim}），未執行。")
        return

    client = get_ai_client()

    def embed(texts: list[str]) -> list[list[float]]:
        resp = client.embeddings.create(input=[t[:4000] for t in texts])
        return [d.embedding for d in resp.data]

    n = reembed(src, dst, args.collection, dest, text_field=args.text_field, embed=embed, dim=dim,
                batch_size=args.batch_size, limit=args.limit, recreate=args.recreate)
    print(f"✓ 完成：{n} 筆寫入 {dest}。後端切換請設定對應的 collection 環境變數。")


if __name__ == "__main__":
    main()
