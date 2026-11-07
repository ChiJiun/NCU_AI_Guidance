"""
render_eval_set.py

評測集 eval-set-v1.json 是唯一的資料來源；本腳本驗證內容並產生易讀的 md 與每行一題的 txt。

執行方式：
  python scripts/test_course_agent/render_eval_set.py          # 驗證並重新產生 md / txt
  python scripts/test_course_agent/render_eval_set.py --check  # 只驗證，不寫檔

驗證項目：題號唯一、工具名稱存在、不要求已停用工具、14 個工具都至少被一題強制呼叫。
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
EVAL_DIR = ROOT / "docs" / "10-retrieval-evaluation"
JSON_PATH = EVAL_DIR / "eval-set-v1.json"
MD_PATH = EVAL_DIR / "eval-set-v1.md"
TXT_PATH = EVAL_DIR / "eval-set-v1.txt"


def load(path: Path = JSON_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(data: dict) -> list[str]:
    """回傳錯誤訊息清單；空清單代表通過。"""
    errors: list[str] = []
    meta = data["meta"]
    enabled = set(meta["tools_enabled"])
    banned = set(meta["tools_must_not_call"])
    questions = data["questions"]

    ids = [q["id"] for q in questions]
    if len(ids) != len(set(ids)):
        errors.append("題號重複")
    if meta["total"] != len(questions):
        errors.append(f"meta.total={meta['total']} 與實際題數 {len(questions)} 不符")
    texts = [q["question"] for q in questions]
    if len(texts) != len(set(texts)):
        errors.append("有重複的問題文字")

    forced: set[str] = set()
    for q in questions:
        qid = q["id"]
        if q["group"] not in meta["groups"]:
            errors.append(f"{qid}: 未知類別 {q['group']}")
        t = q["tools"]
        named = set(t["all"]) | set(t["any"]) | set(t["min_calls"])
        for name in named:
            if name in banned:
                errors.append(f"{qid}: 預期已停用工具 {name}")
            elif name not in enabled:
                errors.append(f"{qid}: 未知工具 {name}")
        if not t["all"] and not t["any"] and not t["allow_no_tool"]:
            errors.append(f"{qid}: 沒有任何工具預期，也未標示可不呼叫工具")
        for name, n in t["min_calls"].items():
            if name not in t["all"]:
                errors.append(f"{qid}: min_calls 的 {name} 必須同時列在 all")
            if n < 2:
                errors.append(f"{qid}: min_calls 應 ≥ 2")
        if t["multi_tool"] != (len(t["all"]) >= 2 or bool(t["min_calls"])):
            errors.append(f"{qid}: multi_tool 標示與 all/min_calls 不一致")
        if not q["checks"]:
            errors.append(f"{qid}: 缺少檢查點")
        if q["scoring"] not in meta["scoring"]:
            errors.append(f"{qid}: 未知評分方式 {q['scoring']}")
        for f in q["watch_flags"]:
            if f not in meta["error_flags"]:
                errors.append(f"{qid}: 未知錯誤標記 {f}")
        forced.update(t["all"])

    missing = enabled - forced
    if missing:
        errors.append(f"以下工具沒有任何一題強制呼叫：{sorted(missing)}")
    return errors


def _tools_text(t: dict) -> str:
    parts = []
    if t["all"]:
        parts.append("必呼叫：" + "、".join(
            f"{n}×{t['min_calls'][n]}" if n in t["min_calls"] else n for n in t["all"]))
    if t["any"]:
        parts.append("至少一個：" + "、".join(t["any"]))
    if t["allow_no_tool"]:
        parts.append("第一輪可不呼叫工具")
    return "；".join(parts)


def render_md(data: dict) -> str:
    meta = data["meta"]
    lines = [
        f"# {meta['name']} {meta['version']}",
        "",
        "> 由 `eval-set-v1.json` 產生，請勿直接編輯本檔；修改請改 JSON 後執行",
        "> `python scripts/test_course_agent/render_eval_set.py`。",
        "",
        f"- 日期：{meta['date']}　題數：{meta['total']}　語氣：{meta['language']}",
        f"- 涵蓋工具：{len(meta['tools_enabled'])} 個；不得呼叫：{'、'.join(meta['tools_must_not_call'])}（已停用）",
        "",
        "## 評分方式",
        "",
    ]
    for k, v in meta["scoring"].items():
        lines.append(f"- `{k}`：{v}")
    lines += ["", "## 工具預期欄位說明", ""]
    for k, v in meta["tool_semantics"].items():
        lines.append(f"- `{k}`：{v}")
    lines += ["", "## 錯誤標記", "", "、".join(f"`{f}`" for f in meta["error_flags"]), ""]

    by_group: dict[str, list[dict]] = {}
    for q in data["questions"]:
        by_group.setdefault(q["group"], []).append(q)
    for g, qs in by_group.items():
        lines += [f"## {g}. {meta['groups'][g]}（{len(qs)} 題）", "",
                  "| ID | 問題 | 意圖 | 工具預期 | 檢查點 | 評分 |",
                  "|---|---|---|---|---|---|"]
        for q in qs:
            mark = " ×3" if q["repeat3"] else ""
            lines.append(
                f"| {q['id']}{mark} | {q['question']} | {'＋'.join(q['intent'])} | "
                f"{_tools_text(q['tools'])} | {'；'.join(q['checks'])} | {q['scoring']} |")
        lines.append("")
    lines += ["`×3`：該題建議重跑 3 次以觀察穩定度。", ""]
    return "\n".join(lines)


def render_txt(data: dict) -> str:
    return "\n".join(q["question"] for q in data["questions"]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="驗證並產生評測集 md / txt")
    parser.add_argument("--check", action="store_true", help="只驗證，不寫檔")
    args = parser.parse_args()

    data = load()
    errors = validate(data)
    if errors:
        print("評測集驗證失敗：")
        for e in errors:
            print("  -", e)
        return 1
    print(f"驗證通過：{len(data['questions'])} 題")
    if not args.check:
        MD_PATH.write_text(render_md(data), encoding="utf-8")
        TXT_PATH.write_text(render_txt(data), encoding="utf-8")
        print(f"已寫入 {MD_PATH.name}、{TXT_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
