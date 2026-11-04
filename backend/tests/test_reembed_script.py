"""reembed_qdrant_collection.py 的測試：用記憶體內 Qdrant 與假的 embedder（不需網路／AWS）。"""
import importlib.util
import sys
from pathlib import Path

import pytest
from qdrant_client import QdrantClient, models

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("reembed", ROOT / "scripts" / "rag" / "reembed_qdrant_collection.py")
reembed_mod = importlib.util.module_from_spec(spec)
sys.modules["reembed"] = reembed_mod
spec.loader.exec_module(reembed_mod)

DIM = 4


def fake_embed(texts):
    return [[float(len(t)), 1.0, 0.0, 0.5] for t in texts]


def make_hybrid(client, name="reports"):
    client.create_collection(
        name,
        vectors_config={"dense": models.VectorParams(size=8, distance=models.Distance.COSINE)},
        sparse_vectors_config={"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )
    client.upsert(name, points=[
        models.PointStruct(
            id=i,
            vector={"dense": [0.1] * 8, "sparse": models.SparseVector(indices=[i, i + 10], values=[1.0, 2.0])},
            payload={"page_content": f"內容{i}" * (i + 1), "metadata": {"page": i}},
        )
        for i in range(1, 6)
    ] + [models.PointStruct(id=99, vector={"dense": [0.1] * 8}, payload={"metadata": {}})])  # 沒有文字


def test_reembed_named_hybrid_keeps_sparse_and_payload():
    c = QdrantClient(":memory:")
    make_hybrid(c)
    n = reembed_mod.reembed(c, c, "reports", "reports_new", text_field="page_content",
                            embed=fake_embed, dim=DIM, batch_size=2)
    assert n == 5  # id=99 無文字被略過

    info = c.get_collection("reports_new")
    assert info.config.params.vectors["dense"].size == DIM
    assert "sparse" in (info.config.params.sparse_vectors or {})

    pts, _ = c.scroll("reports_new", limit=10, with_payload=True, with_vectors=True)
    by_id = {p.id: p for p in pts}
    assert set(by_id) == {1, 2, 3, 4, 5}
    p3 = by_id[3]
    assert len(p3.vector["dense"]) == DIM
    # Cosine 距離會讓 Qdrant 把向量正規化存放，因此比對正規化後的值
    raw = fake_embed(["內容3" * 4])[0]
    norm = sum(x * x for x in raw) ** 0.5
    assert p3.vector["dense"] == pytest.approx([x / norm for x in raw], rel=1e-5)
    assert p3.vector["sparse"].indices == [3, 13]
    assert p3.payload["metadata"] == {"page": 3}
    # 來源 collection 不被修改
    assert c.get_collection("reports").config.params.vectors["dense"].size == 8


def test_reembed_unnamed_vector_collection():
    c = QdrantClient(":memory:")
    c.create_collection("courses", vectors_config=models.VectorParams(size=8, distance=models.Distance.COSINE))
    c.upsert("courses", points=[
        models.PointStruct(id=1, vector=[0.2] * 8, payload={"_text": "資料結構", "name": "A"}),
        models.PointStruct(id=2, vector=[0.3] * 8, payload={"_text": "  ", "name": "B"}),
    ])
    n = reembed_mod.reembed(c, c, "courses", "courses_new", text_field="_text", embed=fake_embed, dim=DIM)
    assert n == 1
    pts, _ = c.scroll("courses_new", limit=10, with_vectors=True)
    assert len(pts[0].vector) == DIM


def test_existing_destination_requires_recreate():
    c = QdrantClient(":memory:")
    make_hybrid(c)
    reembed_mod.reembed(c, c, "reports", "reports_new", text_field="page_content", embed=fake_embed, dim=DIM)
    with pytest.raises(RuntimeError, match="--recreate"):
        reembed_mod.reembed(c, c, "reports", "reports_new", text_field="page_content", embed=fake_embed, dim=DIM)
    n = reembed_mod.reembed(c, c, "reports", "reports_new", text_field="page_content",
                            embed=fake_embed, dim=DIM, recreate=True)
    assert n == 5


def test_get_by_path_nested():
    assert reembed_mod.get_by_path({"a": {"b": "x"}}, "a.b") == "x"
    assert reembed_mod.get_by_path({"a": 1}, "a.b") is None


def test_same_name_destination_is_rejected_even_with_recreate():
    c = QdrantClient(":memory:")
    make_hybrid(c)
    with pytest.raises(RuntimeError, match="不可與來源同名"):
        reembed_mod.reembed(c, c, "reports", "reports", text_field="page_content",
                            embed=fake_embed, dim=DIM, recreate=True)
    assert c.count("reports").count == 6  # 來源沒有被刪除
