"""
export_glossary_frontend.py — 把「已審查」的詞庫匯出給前端做名詞提示框

只匯出可以放心顯示的詞：
  - tier=core（Claude 寫、GPT-5.4 交叉審核）或 verified=claude-manual（人工逐一審過）
  - skip=false 且有說明
沒審過的 fallback 說明可能是錯的（審查時抓到不少），顯示錯的提示框比不顯示更糟，所以不匯出。

輸出：frontend/src/data/glossary.json，格式 {"寫法": "白話說明"}（詞與別名都各佔一筆）。

用法：python scripts/nlp/export_glossary_frontend.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
GLOSSARY_PATH = ROOT / "data" / "processed" / "nlp" / "concept_glossary.json"
OUT_PATH = ROOT / "frontend" / "src" / "data" / "glossary.json"
MIN_SURFACE_LEN = 2


def is_displayable(entry: dict) -> bool:
    if entry.get("skip") or entry.get("needs_review") or not entry.get("gloss"):
        return False
    return entry.get("tier") == "core" or entry.get("verified") == "claude-manual"


def select_terms(terms: dict) -> dict[str, str]:
    """term / aliases → gloss。同一個寫法對到不同說明時，保留涵蓋課程較多的那個。"""
    chosen: dict[str, tuple[int, str]] = {}
    for term, entry in terms.items():
        if not is_displayable(entry):
            continue
        weight = entry.get("n_courses") or 0
        for surface in [term, *(entry.get("aliases") or [])]:
            surface = surface.strip()
            if len(surface) < MIN_SURFACE_LEN:
                continue
            if surface not in chosen or weight > chosen[surface][0]:
                chosen[surface] = (weight, entry["gloss"])
    return {s: g for s, (_, g) in sorted(chosen.items())}


def main() -> int:
    terms = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))["terms"]
    out = select_terms(terms)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=0, separators=(",", ":")), encoding="utf-8")
    print(f"已匯出 {len(out)} 個寫法到 {OUT_PATH}（{OUT_PATH.stat().st_size / 1024:.0f} KB）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
