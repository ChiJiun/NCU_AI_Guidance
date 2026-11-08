"""
normalize_aliases.py — 合併 NLP 檔案裡寫法不同的同一個詞（別名），並統一成繁體

為什麼：知識圖譜的概念節點 id 是 `concept::名稱`，名稱來自 NLP 檔案。「神經網絡」與「神經網路」、
「大型語言模型」與「大型語言模型（LLM）」會變成兩個節點，使共享概念、PPR、相似課的計算被拆開。
最乾淨的修法是在源頭統一，再重建圖譜與索引，而不是在圖譜上事後補丁。

規則（刻意偏粗，已與使用者確認「粗一點沒關係」）：
  - 比對 key：全形半形統一、轉小寫、網絡→網路、去掉括號內容、去掉空白與標點
  - 同一個 key 的所有寫法併成一個；正規寫法 = 沒有括號的版本優先，其次最常見，再其次較短
  - 舊檔混入的簡體字原詞先逐一對照成繁體
  - 三個類別分開處理（概念、技術、領域），不跨類別合併
所有檔案用同一份對照表一起改，教授到領域的連線才不會斷（領域名稱同時出現在
nlp_domain_tags、nlp_professor_links、dept_professor_map）。

用法：
  python scripts/nlp/normalize_aliases.py            # 乾跑：只產生報告與對照表，不改檔
  python scripts/nlp/normalize_aliases.py --apply    # 實際改寫 NLP 檔案（檔案由 git 追蹤，可 git checkout 還原）
"""

import argparse
import collections
import importlib.util
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
NLP_DIR = ROOT / "data" / "processed" / "nlp"
MAP_PATH = NLP_DIR / "concept_alias_map.json"
REPORT_PATH = NLP_DIR / "alias_merge_report.md"

_spec = importlib.util.spec_from_file_location("build_glossary", Path(__file__).parent / "build_glossary.py")
_bg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_bg)
norm_key, SIMPLIFIED_FIXES = _bg.norm_key, _bg.SIMPLIFIED_FIXES
_PAREN = _bg._PAREN_RE

RELEVANCE_RANK = {"high": 3, "medium": 2, "low": 1}


def fix_simplified(term: str) -> str:
    return SIMPLIFIED_FIXES.get(term, term)


def canonical_of(counts: collections.Counter) -> str:
    """沒有括號的優先；其次最常見；再其次較短、字典序。"""
    return sorted(counts.items(), key=lambda kv: (bool(_PAREN.search(kv[0])), -kv[1], len(kv[0]), kv[0]))[0][0]


_ENUM_PAREN = re.compile(r"^[（(]\s*(?:[一二三四五六七八九十]+|\d+|[IVXivx]+)\s*[）)]$")
_PUNCT = re.compile(r"[\s\-_/·、，,．.（）()]")


def _squash(s: str) -> str:
    """全形半形、小寫、網絡→網路、去掉空白與標點（括號符號也去掉，括號內的字保留）。"""
    return _PUNCT.sub("", unicodedata.normalize("NFKC", s).lower().replace("網絡", "網路"))


def key_pair(term: str) -> tuple[str, str | None]:
    """回傳 (基底 key, 限定詞 key)。限定詞 key 為 None 代表沒有可忽略的括號。

    不可忽略括號的情況，視為詞的一部分（限定詞 key 為 None、基底 key 含括號內容）：
      - 前置括號：「(跨)民族主義」
      - 編號括號：「企業舞弊案例(一)」「不規則動詞現在時（二）」，各是不同的單元
    """
    s = unicodedata.normalize("NFKC", term).strip()
    parens = _PAREN.findall(s)
    if s.startswith("(") or any(_ENUM_PAREN.match(p) for p in parens):
        return _squash(s), None
    base = _squash(_PAREN.sub("", s))
    qualifier = _squash("".join(parens)) if parens else None
    return base, qualifier


def build_map(surface_counts: collections.Counter) -> tuple[dict, list]:
    """surface_counts: 寫法 -> 出現次數。回傳 (寫法->正規寫法 只含有變動者, 合併群組清單)。

    同一個基底 key 的寫法分兩種處理：
      - 其中有「不帶括號」的寫法：所有帶括號的寫法併入它（偏粗，已與使用者確認）
      - 全都帶括號：只有括號內容相同者才併（避免「形容詞（性數變化）」與「形容詞（形容詞協調）」被併成一個）
    """
    by_base: dict[str, list[tuple[str, int, str | None]]] = collections.defaultdict(list)
    for surface, n in surface_counts.items():
        s = fix_simplified(surface.strip())
        base, qual = key_pair(s)
        if base:
            by_base[base].append((s, n, qual))

    final_clusters: list[collections.Counter] = []
    for variants in by_base.values():
        has_bare = any(q is None for _, _, q in variants)
        if has_bare:
            merged = collections.Counter()
            for s, n, _ in variants:
                merged[s] += n
            final_clusters.append(merged)
        else:
            by_qual: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
            for s, n, q in variants:
                by_qual[q or ""][s] += n
            final_clusters.extend(by_qual.values())

    mapping: dict[str, str] = {}
    groups = []
    for counts in final_clusters:
        canon = canonical_of(counts)
        for surface in counts:
            if surface != canon:
                mapping[surface] = canon
        if len(counts) > 1:
            groups.append({"canonical": canon, "variants": sorted(counts), "uses": sum(counts.values()),
                           "has_chinese_qualifier": any(_PAREN.search(v) and not _ascii_only_paren(v) for v in counts)})
    # 簡體原詞本身也要有對照（即使它單獨成群）
    for wrong, right in SIMPLIFIED_FIXES.items():
        if wrong in surface_counts:
            mapping[wrong] = mapping.get(right, right)
    return mapping, groups


def _ascii_only_paren(term: str) -> bool:
    inner = _PAREN.findall(term)
    return bool(inner) and all(re.fullmatch(r"[（(][A-Za-z0-9 /+\-_.]+[）)]", p) for p in inner)


def map_list(items: list, mapping: dict) -> list:
    """依對照表改寫並去重（保留第一次出現的順序）。"""
    out, seen = [], set()
    for it in items:
        s = mapping.get(it, mapping.get(it.strip(), it))
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def merge_fields(entries: list[dict], mapping: dict, union_key: str | None = None) -> list[dict]:
    """改寫每個 {field, relevance, ...} 的 field；改寫後同名者合併：relevance 取較高者，union_key 欄位取聯集。"""
    merged: dict[str, dict] = {}
    for x in entries:
        raw = x.get("field", "")
        f = mapping.get(raw, mapping.get(raw.strip(), raw))
        if f in merged:
            m = merged[f]
            if RELEVANCE_RANK.get(x.get("relevance"), 0) > RELEVANCE_RANK.get(m.get("relevance"), 0):
                m["relevance"] = x["relevance"]
            if union_key:
                m[union_key] = list(dict.fromkeys(m.get(union_key, []) + x.get(union_key, [])))
        else:
            merged[f] = {**x, "field": f}
    return list(merged.values())


# ── 各檔案的處理 ──────────────────────────────────────────────────────────────

def collect(tech: dict, domain: dict, prof: dict, dept: dict, simp: dict) -> dict:
    concept, technology, field = (collections.Counter() for _ in range(3))
    for d in tech.values():
        if isinstance(d, dict):
            concept.update(set(d.get("concepts", [])))
            technology.update(set(d.get("languages", []) + d.get("tools", [])))
    for d in domain.values():
        if isinstance(d, dict):
            field.update({t["field"] for t in d.get("domain_tags", []) if t.get("field")})
    for links in prof.values():
        field.update({x["field"] for x in links if x.get("field")})
    for d in dept.values():
        field.update(set(d.get("specialty_vocab", [])))
    for d in simp.values():
        concept.update({c["original"].strip() for c in d.get("simplified_concepts", [])})
    return {"concept": concept, "technology": technology, "field": field}


def apply_all(maps: dict, tech: dict, domain: dict, prof: dict, dept: dict, simp: dict) -> None:
    cm, tm, fm = maps["concept"], maps["technology"], maps["field"]
    for d in tech.values():
        if isinstance(d, dict):
            d["concepts"] = map_list(d.get("concepts", []), cm)
            d["languages"] = map_list(d.get("languages", []), tm)
            d["tools"] = map_list(d.get("tools", []), tm)
    for d in domain.values():
        if isinstance(d, dict) and "domain_tags" in d:
            d["domain_tags"] = merge_fields(d["domain_tags"], fm)
    for code, links in prof.items():
        prof[code] = merge_fields(links, fm, union_key="professors")
    for d in dept.values():
        if "specialty_vocab" in d:
            d["specialty_vocab"] = map_list(d["specialty_vocab"], fm)
    for d in simp.values():
        seen, out = set(), []
        for c in d.get("simplified_concepts", []):
            o = cm.get(c["original"].strip(), c["original"].strip())
            if o not in seen:
                seen.add(o)
                out.append({**c, "original": o})
        if "simplified_concepts" in d:
            d["simplified_concepts"] = out


def report(maps: dict, groups: dict, before: dict, after: dict) -> str:
    lines = ["# 別名合併報告", "",
             "由 `scripts/nlp/normalize_aliases.py` 產生。規則偏粗：括號內容、全形半形、大小寫、網絡／網路都視為同一個詞。", "",
             "| 類別 | 合併前不重複寫法 | 合併後 | 合併群組 | 其中括號內含中文限定 |", "|---|---|---|---|---|"]
    for k, label in (("concept", "概念"), ("technology", "技術"), ("field", "領域")):
        g = groups[k]
        lines.append(f"| {label} | {before[k]:,} | {after[k]:,} | {len(g)} | {sum(x['has_chinese_qualifier'] for x in g)} |")
    for k, label in (("concept", "概念"), ("technology", "技術"), ("field", "領域")):
        g = sorted(groups[k], key=lambda x: (-x["has_chinese_qualifier"], -x["uses"]))
        lines += ["", f"## {label}（先列括號內含中文限定的，可能損失細節）", "", "| 正規寫法 | 被合併的寫法 | 使用次數 |", "|---|---|---|"]
        for x in g:
            flag = "⚠ " if x["has_chinese_qualifier"] else ""
            lines.append(f"| {flag}{x['canonical']} | {'、'.join(v for v in x['variants'] if v != x['canonical'])} | {x['uses']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="合併 NLP 檔案中的別名並統一成繁體")
    ap.add_argument("--apply", action="store_true", help="實際改寫檔案（預設乾跑）")
    args = ap.parse_args()

    paths = {n: NLP_DIR / f"{n}.json" for n in
             ("nlp_tech_nodes", "nlp_domain_tags", "nlp_professor_links", "dept_professor_map", "nlp_simplified_concepts")}
    raw = {n: p.read_text(encoding="utf-8") for n, p in paths.items()}
    data = {n: json.loads(t) for n, t in raw.items()}
    tech, domain, prof, dept, simp = (data[n] for n in paths)

    counts = collect(tech, domain, prof, dept, simp)
    maps, groups = {}, {}
    for k, c in counts.items():
        maps[k], groups[k] = build_map(c)
    before = {k: len(c) for k, c in counts.items()}
    # 對照表只含「會改變」的寫法；合併後數量以重算為準
    after_data = json.loads(json.dumps(data))
    apply_all(maps, *(after_data[n] for n in paths))
    after = {k: len(c) for k, c in collect(*(after_data[n] for n in paths)).items()}

    MAP_PATH.write_text(json.dumps({"concept": maps["concept"], "technology": maps["technology"], "field": maps["field"]},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    REPORT_PATH.write_text(report(maps, groups, before, after), encoding="utf-8")
    for k in counts:
        print(f"{k:<10} 合併前 {before[k]:>6,} → 合併後 {after[k]:>6,}（{len(groups[k])} 組，改寫 {len(maps[k])} 種寫法）")
    print(f"對照表：{MAP_PATH}\n報告：{REPORT_PATH}")
    if args.apply:
        for n, p in paths.items():
            # 與原檔排版一致（縮排 2、保留中文、保留結尾換行），git diff 才只會出現真正被合併的地方
            text = json.dumps(after_data[n], ensure_ascii=False, indent=2) + ("\n" if raw[n].endswith("\n") else "")
            p.write_text(text, encoding="utf-8", newline="")
        print("已改寫 NLP 檔案（可用 git diff / git checkout 檢視或還原）")
    else:
        print("乾跑模式：沒有改動任何 NLP 檔案；確認後加上 --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
