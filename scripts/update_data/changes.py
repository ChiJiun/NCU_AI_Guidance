"""比對沙盒與正式資料：找出變動檔案、驗證輸出、產生變更摘要。"""

from __future__ import annotations

import filecmp
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# list[dict] 用來比對新增／移除項目的鍵（依序找第一個大多數項目都有的欄位）
KEY_CANDIDATES = ("課號-班別", "id", "course_code", "code", "program_id", "node_id", "name")
SAMPLE_SIZE = 8


def rel_files(base: Path, rel: str) -> list[str]:
    """把 outputs 裡的一個項目（檔案或目錄）展開成 repo 相對檔案路徑。"""
    p = base / rel
    if p.is_file():
        return [rel]
    if p.is_dir():
        return sorted(f.relative_to(base).as_posix() for f in p.rglob("*") if f.is_file())
    return []


def changed_files(sandbox: Path, root: Path, rels: Iterable[str]) -> list[str]:
    """沙盒裡內容與正式資料不同（或新增）的檔案。"""
    out: set[str] = set()
    for rel in rels:
        for f in rel_files(sandbox, rel):
            dst = root / f
            if not dst.exists() or not filecmp.cmp(sandbox / f, dst, shallow=False):
                out.add(f)
    return sorted(out)


def is_within(rel: str, outputs: Iterable[str]) -> bool:
    return any(rel == o or rel.startswith(o.rstrip("/") + "/") for o in outputs)


# ── 計數 ──────────────────────────────────────────────────────────────────

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def json_count(obj: Any) -> int:
    """「筆數」：list 取長度；圖譜取節點數；其他 dict 取鍵數。"""
    if isinstance(obj, list):
        return len(obj)
    if isinstance(obj, dict):
        if isinstance(obj.get("nodes"), list):
            return len(obj["nodes"])
        return len(obj)
    return 0


def pick_key(items: list) -> str | None:
    dicts = [x for x in items if isinstance(x, dict)]
    if not dicts:
        return None
    for k in KEY_CANDIDATES:
        if sum(1 for d in dicts if d.get(k) not in (None, "")) >= 0.9 * len(dicts):
            return k
    return None


def item_keys(obj: Any) -> tuple[str | None, set[str]]:
    if isinstance(obj, dict) and isinstance(obj.get("nodes"), list):
        return "id", {str(n.get("id")) for n in obj["nodes"] if isinstance(n, dict)}
    if isinstance(obj, dict):
        return "(key)", set(map(str, obj.keys()))
    if isinstance(obj, list):
        k = pick_key(obj)
        if k:
            return k, {str(d.get(k)) for d in obj if isinstance(d, dict) and d.get(k) not in (None, "")}
    return None, set()


def node_type_counts(obj: Any) -> Counter:
    if isinstance(obj, dict) and isinstance(obj.get("nodes"), list):
        return Counter(n.get("node_type", "?") for n in obj["nodes"] if isinstance(n, dict))
    return Counter()


def raw_course_nodes(obj: Any) -> int:
    """圖譜中有完整原始資料的課程節點數（原始課程缺失時會掉到 0）。"""
    if isinstance(obj, dict) and isinstance(obj.get("nodes"), list):
        return sum(1 for n in obj["nodes"]
                   if isinstance(n, dict) and n.get("node_type") == "Course" and n.get("source") == "raw")
    return 0


# ── 驗證 ──────────────────────────────────────────────────────────────────

@dataclass
class Limits:
    max_shrink: float = 0.10
    allow_shrink: bool = False


def _shrunk(old: int, new: int, limits: Limits) -> bool:
    return (not limits.allow_shrink) and old > 0 and new < old * (1 - limits.max_shrink)


def validate_file(rel: str, new_path: Path, old_path: Path | None, limits: Limits) -> list[str]:
    """回傳錯誤訊息清單；空清單代表通過。"""
    errors: list[str] = []
    if new_path.stat().st_size == 0:
        return [f"{rel}：輸出是空檔"]
    if new_path.suffix != ".json":
        return errors

    try:
        new = load_json(new_path)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return [f"{rel}：不是合法 JSON（{e}）"]

    new_n = json_count(new)
    if new_n == 0:
        errors.append(f"{rel}：輸出沒有任何資料")

    old = None
    if old_path is not None and old_path.exists():
        try:
            old = load_json(old_path)
        except (json.JSONDecodeError, UnicodeDecodeError):
            old = None
    if old is not None:
        old_n = json_count(old)
        if _shrunk(old_n, new_n, limits):
            errors.append(f"{rel}：筆數從 {old_n} 掉到 {new_n}（超過 {limits.max_shrink:.0%}，"
                          f"確認無誤可加 --allow-shrink 或調高 --max-shrink）")
        old_raw, new_raw = raw_course_nodes(old), raw_course_nodes(new)
        if _shrunk(old_raw, new_raw, limits):
            errors.append(f"{rel}：有原始資料的課程節點從 {old_raw} 掉到 {new_raw}，可能是原始課程資料缺漏")

    if rel.startswith("data/processed/courses_deduped/") and isinstance(new, list):
        keys = [c.get("課號-班別", "") for c in new if isinstance(c, dict)]
        dups = len(keys) - len(set(keys))
        if dups:
            errors.append(f"{rel}：有 {dups} 筆重複的 課號-班別")
    return errors


# 必須一起更新的輸出：前者變了、後者卻沒變（而且後者原本就存在）就視為失敗。
# 後端優先讀 knowledge_graph.pkl（igraph），沒裝 python-igraph 時 build_graph 只會更新 json，
# 後端就會繼續用舊圖。
PAIRED_OUTPUTS = (
    ("data/processed/graph/knowledge_graph.json", "data/processed/graph/knowledge_graph.pkl"),
)


def paired_errors(changed: Iterable[str], root: Path) -> list[str]:
    changed = set(changed)
    return [f"{a} 已更新但 {b} 沒有更新（後端會優先讀 {Path(b).name}；請安裝 python-igraph 後重跑）"
            for a, b in PAIRED_OUTPUTS if a in changed and b not in changed and (root / b).exists()]


# ── 變更摘要 ──────────────────────────────────────────────────────────────

@dataclass
class FileChange:
    path: str
    kind: str                     # added / modified
    old_count: int | None = None
    new_count: int | None = None
    key: str | None = None
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    n_added: int = 0
    n_removed: int = 0
    node_types: dict[str, list[int]] = field(default_factory=dict)
    old_size: int | None = None
    new_size: int | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def describe_change(rel: str, new_path: Path, old_path: Path | None) -> FileChange:
    old_file = old_path if old_path is not None and old_path.exists() else None
    kind = "modified" if old_file is not None else "added"
    ch = FileChange(path=rel, kind=kind, new_size=new_path.stat().st_size,
                    old_size=old_file.stat().st_size if old_file is not None else None)
    if new_path.suffix != ".json":
        return ch
    try:
        new = load_json(new_path)
        old = load_json(old_file) if old_file is not None else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ch

    ch.new_count = json_count(new)
    if old is None:
        return ch
    ch.old_count = json_count(old)

    k_new, new_keys = item_keys(new)
    k_old, old_keys = item_keys(old)
    if k_new and k_new == k_old:
        added, removed = sorted(new_keys - old_keys), sorted(old_keys - new_keys)
        ch.key, ch.n_added, ch.n_removed = k_new, len(added), len(removed)
        ch.added, ch.removed = added[:SAMPLE_SIZE], removed[:SAMPLE_SIZE]

    old_types, new_types = node_type_counts(old), node_type_counts(new)
    for t in sorted(set(old_types) | set(new_types)):
        if old_types[t] != new_types[t]:
            ch.node_types[t] = [old_types[t], new_types[t]]
    return ch


def format_change(ch: FileChange) -> str:
    if ch.kind == "added":
        count = f"，{ch.new_count} 筆" if ch.new_count is not None else ""
        return f"- `{ch.path}`：新增檔案{count}"
    parts = []
    if ch.old_count is not None and ch.new_count is not None:
        delta = ch.new_count - ch.old_count
        parts.append(f"{ch.old_count} → {ch.new_count} 筆（{delta:+d}）")
    elif ch.old_size is not None and ch.new_size is not None:
        parts.append(f"{ch.old_size:,} → {ch.new_size:,} bytes")
    if ch.key and (ch.n_added or ch.n_removed):
        parts.append(f"依 `{ch.key}` 比對：新增 {ch.n_added}、移除 {ch.n_removed}")
    elif ch.key:
        parts.append("項目相同，內容有更新")
    line = f"- `{ch.path}`：" + "；".join(parts or ["內容有更新"])
    if ch.added:
        line += f"\n  - 新增例：{', '.join(ch.added)}"
    if ch.removed:
        line += f"\n  - 移除例：{', '.join(ch.removed)}"
    if ch.node_types:
        types = "、".join(f"{t} {a}→{b}" for t, (a, b) in ch.node_types.items())
        line += f"\n  - 節點類型：{types}"
    return line
