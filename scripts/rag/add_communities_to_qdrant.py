"""
add_communities_to_qdrant.py — 將 Leiden 社群 label 嵌入進 ncu_graph_nodes

把 48 個社群節點（node_type=Community）upsert 到現有 ncu_graph_nodes collection，
讓向量搜尋「AI 課程類別」、「機器學習相關類別」時能以 Community 節點當 PPR 種子。

用法：
  python scripts/rag/add_communities_to_qdrant.py

不需要 --reset，直接 upsert（不影響已有的 Concept/Technology/Field 節點）。
"""

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT           = Path(__file__).parent.parent.parent

# 腳本使用與後端相同的 Bedrock 存取層（憑證來自 AWS CLI profile / SSO / 環境變數）
sys.path.insert(0, str(ROOT / "backend"))
from app.services.bedrock_client import embedding_dim, get_ai_client  # noqa: E402
COMMUNITIES    = ROOT / "data" / "processed" / "graph" / "communities.json"
QDRANT_DIR     = ROOT / "data" / "processed" / "qdrant_data"
COLLECTION     = "ncu_graph_nodes"
VECTOR_DIM     = embedding_dim()  # Titan Text Embeddings V2（原 text-embedding-3-large 為 3072）


def _node_id_to_int(node_id: str) -> int:
    return int(hashlib.md5(node_id.encode()).hexdigest()[:15], 16)


def main():
    from dotenv import load_dotenv
    for env_path in [ROOT / ".env", ROOT / "backend" / ".env", Path(".env")]:
        if env_path.exists():
            load_dotenv(env_path)
            print(f"載入環境變數：{env_path}")
            break

    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct
    except ImportError as e:
        print(f"缺少套件：{e}")
        return

    if not COMMUNITIES.exists():
        print(f"找不到 {COMMUNITIES}，請先執行 compute_communities.py")
        return

    communities: list[dict] = json.loads(COMMUNITIES.read_text(encoding="utf-8"))
    print(f"載入 {len(communities)} 個社群")

    oai = get_ai_client()

    qdrant_url = os.environ.get("QDRANT_URL", "")
    qdrant_api_key = os.environ.get("QDRANT_API_KEY")
    if qdrant_url:
        client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
    else:
        client = QdrantClient(path=str(QDRANT_DIR))
    cols = [c.name for c in client.get_collections().collections]
    if COLLECTION not in cols:
        print(f"[錯誤] Collection '{COLLECTION}' 不存在，請先執行 build_qdrant_index.py")
        return

    # 建立每個社群的嵌入文字：label + top_concepts + 代表課程
    texts, community_meta = [], []
    for c in communities:
        label    = c.get("label") or f"社群{c['id']}"
        concepts = "、".join(c.get("top_concepts", [])[:6])
        courses  = "、".join(
            (x["name"] if isinstance(x, dict) else x)
            for x in c.get("courses", [])[:6]
        )
        # 讓 embedding 同時感知 label、概念、代表課程
        text = f"{label}（Community）核心概念：{concepts} 代表課程：{courses}"
        texts.append(text)
        community_meta.append({
            "node_id":   f"community::{c['id']}",
            "node_type": "Community",
            "name":      label,
            "size":      c["size"],
            "connected_courses": [
                (x["name"] if isinstance(x, dict) else x)
                for x in c.get("courses", [])[:10]
            ],
        })

    # 一次 embed 全部 48 個（遠低於 rate limit）
    resp = oai.embeddings.create(input=texts)
    vectors = [item.embedding for item in resp.data]

    points = [
        PointStruct(
            id=_node_id_to_int(meta["node_id"]),
            vector=vec,
            payload=meta,
        )
        for meta, vec in zip(community_meta, vectors)
    ]

    client.upsert(collection_name=COLLECTION, points=points)
    print(f"成功 upsert {len(points)} 個 Community 節點到 '{COLLECTION}'")
    for p in points:
        print(f"  {p.payload['node_id']} → {p.payload['name']}")


if __name__ == "__main__":
    main()
