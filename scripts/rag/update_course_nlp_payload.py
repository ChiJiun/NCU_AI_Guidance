"""
update_course_nlp_payload.py — NLP 檔案（別名合併後）→ 課程 Qdrant payload 差異更新

只更新「有差異」的課程點、只改 NLP 衍生的欄位，不動向量與 _text：
  concepts / languages / tools / domain_tags / domain_tags_rich / simplified_concepts
欄位格式與 build_vector_index.py 完全一致。

用法：
  python scripts/rag/update_course_nlp_payload.py            # 乾跑：只列出會改幾個點
  python scripts/rag/update_course_nlp_payload.py --apply
"""

import argparse
import collections
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
NLP_DIR = ROOT / "data" / "processed" / "nlp"
COLLECTIONS = ["ncu_courses_ug", "ncu_courses_grad"]
FIELDS = ["concepts", "languages", "tools", "domain_tags", "domain_tags_rich", "simplified_concepts"]
SCROLL_PAGE = 500


def expected_fields(code: str, tech: dict, domain: dict, simp: dict) -> dict | None:
    """依 NLP 檔案算出某門課應有的 payload 欄位；NLP 完全沒有這門課時回傳 None（不處理）。"""
    if code not in tech and code not in domain and code not in simp:
        return None
    t = tech.get(code, {}) or {}
    raw_domain = (domain.get(code, {}) or {}).get("domain_tags", []) or []
    fields = [x["field"] for x in raw_domain if isinstance(x, dict) and x.get("field")]
    rich = "||".join(f"{x['field']}::{x.get('relevance', 'medium')}"
                     for x in raw_domain if isinstance(x, dict) and x.get("field"))
    simplified = (simp.get(code, {}) or {}).get("simplified_concepts", [])
    return {
        "concepts": t.get("concepts", []), "languages": t.get("languages", []), "tools": t.get("tools", []),
        "domain_tags": fields, "domain_tags_rich": rich,
        "simplified_concepts": "||".join(f"{c.get('original', '')}::{c.get('display', '')}"
                                         for c in simplified if c.get("original") and c.get("display")),
    }


def diff_fields(current: dict, expected: dict) -> list[str]:
    return [k for k in FIELDS if current.get(k, [] if isinstance(expected[k], list) else "") != expected[k]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    from qdrant_client import QdrantClient
    from qdrant_client.models import SetPayload, SetPayloadOperation

    tech = json.loads((NLP_DIR / "nlp_tech_nodes.json").read_text(encoding="utf-8"))
    domain = json.loads((NLP_DIR / "nlp_domain_tags.json").read_text(encoding="utf-8"))
    simp = json.loads((NLP_DIR / "nlp_simplified_concepts.json").read_text(encoding="utf-8"))
    client = QdrantClient(url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
                          api_key=os.environ.get("QDRANT_API_KEY") or None, timeout=60)

    total_changed = 0
    for col in COLLECTIONS:
        updates: list[tuple[int, dict]] = []
        by_field = collections.Counter()
        seen = no_nlp = 0
        offset = None
        while True:
            pts, offset = client.scroll(col, limit=SCROLL_PAGE, offset=offset,
                                        with_payload=["course_code", *FIELDS], with_vectors=False)
            for p in pts:
                seen += 1
                exp = expected_fields(p.payload.get("course_code", ""), tech, domain, simp)
                if exp is None:
                    no_nlp += 1
                    continue
                changed = diff_fields(p.payload, exp)
                if changed:
                    updates.append((p.id, {k: exp[k] for k in changed}))
                    by_field.update(changed)
            if offset is None:
                break
        print(f"[{col}] 共 {seen} 點｜NLP 沒有這門課而略過 {no_nlp}｜需更新 {len(updates)}｜欄位分佈 {dict(by_field)}")
        if args.apply and updates:
            for i in range(0, len(updates), 100):
                ops = [SetPayloadOperation(set_payload=SetPayload(payload=pl, points=[pid]))
                       for pid, pl in updates[i:i + 100]]
                client.batch_update_points(col, update_operations=ops, wait=True)
            print(f"  已更新 {len(updates)} 點")
        total_changed += len(updates)
    if not args.apply:
        print("乾跑模式：沒有改動 Qdrant。確認後加上 --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
