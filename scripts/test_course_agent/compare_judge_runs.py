"""
compare_judge_runs.py

把多份 judge_with_claude.py（v2）產生的 *_judge_v2_summary.json 整理成一張比較表。

執行方式：
  python scripts/test_course_agent/compare_judge_runs.py 20261108_151846 20261108_170323 20261108_224715
  python scripts/test_course_agent/compare_judge_runs.py <run_id ...> --out docs/10-retrieval-evaluation/judge-v2-comparison.md
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from judge_with_claude import BEHAVIORS, DIMENSIONS, ERROR_FLAGS, OUT_SUFFIX, RESULTS_DIR  # noqa: E402


def _v(x, suffix=""):
    return "—" if x is None else f"{x}{suffix}"


def build_table(summaries: dict[str, dict]) -> str:
    ids = list(summaries)
    head = "| 指標 | " + " | ".join(ids) + " |"
    sep = "|---|" + "---|" * len(ids)

    def row(label, fn):
        cells = []
        for s in summaries.values():
            try:
                cells.append(fn(s))
            except (KeyError, TypeError, ZeroDivisionError):
                cells.append("—")
        return f"| {label} | " + " | ".join(cells) + " |"

    lines = ["## 第一層：程式硬指標", "", head, sep,
             row("課名真實率", lambda s: f"{_v(s['hard']['course_real_rate'], '%')}（{s['hard']['course_found']}/{s['hard']['course_tags']}）"),
             row("查不到的課名（人次）", lambda s: str(s["hard"]["unknown_course_names"])),
             row("系所／學程被誤標成課", lambda s: str(s["hard"]["dept_tags"])),
             row("行為正確率", lambda s: f"{_v(s['hard']['behavior_rate'], '%')}")]
    for k, name in BEHAVIORS.items():
        lines.append(row(f"　└ {name}", lambda s, k=k: "{ok}/{n}".format(**s["hard"]["behavior_by_type"][k])))
    lines += [row("　└ query 題必要工具全數呼叫", lambda s: f"{s['hard']['query_required_tools_ok']}/{s['hard']['query_questions']}"),
              row("回答平均字數", lambda s: str(s["hard"]["mean_chars"])),
              row("超過 900 字（題）", lambda s: str(s["hard"]["too_long"])),
              row("標記超過 6 門課（題）", lambda s: str(s["hard"]["too_many_courses"])),
              row("空白或錯誤（題）", lambda s: str(s["hard"]["empty_or_error"])),
              row("回應時間中位數（秒）", lambda s: str(s["hard"]["median_elapsed_sec"])),
              "", "## 第二層：AI 評審", "", head, sep,
              row("**檢查點達成率**", lambda s: f"**{s['ai']['check_rate']}%**"),
              row("四面向平均總分（/8）", lambda s: str(s["ai"]["aux_total"]))]
    for k, name in DIMENSIONS.items():
        lines.append(row(f"　└ {name}", lambda s, k=k: str(s["ai"]["dims"][k])))
    for f in ERROR_FLAGS:
        lines.append(row(f"`{f}`（任一次／兩次都標）",
                         lambda s, f=f: f"{s['ai']['flags_any_pass'].get(f, 0)}／{s['ai']['flags_all_passes'].get(f, 0)}"))
    lines += ["", "## 第三層：評審可信度（同一回答評兩次）", "", head, sep,
              row("四面向總分完全一致", lambda s: f"{s['reliability']['aux_exact']}%"),
              row("四面向總分差 1 分內", lambda s: f"{s['reliability']['aux_within_1']}%"),
              row("檢查點判定一致", lambda s: f"{s['reliability']['check_agree']}%"),
              row("錯誤標記完全相同", lambda s: f"{s['reliability']['flags_agree']}%")]
    for k, name in DIMENSIONS.items():
        lines.append(row(f"　└ {name} 完全一致", lambda s, k=k: f"{s['reliability']['dim_exact'][k]}%"))
    groups = sorted({g for s in summaries.values() for g in s.get("ai", {}).get("by_group", {})})
    if groups:
        lines += ["", "## 各類別檢查點達成率", "", "| 類別 | " + " | ".join(ids) + " |", sep]
        for g in groups:
            lines.append(row(g, lambda s, g=g: f"{s['ai']['by_group'][g]['check_rate']}%"))
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="比較多次 v2 評分的彙總數字")
    ap.add_argument("runs", nargs="+", help="run_id（例如 20261108_224715）或 summary json 路徑")
    ap.add_argument("--dir", default=str(RESULTS_DIR), help="summary 所在資料夾")
    ap.add_argument("--out", default=None, help="輸出 md 路徑（預設印到螢幕）")
    args = ap.parse_args()

    summaries = {}
    for r in args.runs:
        p = Path(r) if r.endswith(".json") else Path(args.dir) / f"{r}_{OUT_SUFFIX}_summary.json"
        s = json.loads(p.read_text(encoding="utf-8"))
        summaries[s["meta"]["run_id"]] = s
    text = "\n".join([
        "# 課程助理三次評測比較（評分 v2）", "",
        "> 同一套評測集標註（含 expected_behavior）與同一版評審（`claude-sonnet-5-5`，每題評 2 次）重評既有回答，"
        "三次回答之間課程助理的提示詞不同，因此本表比較的是回答品質，評分標準固定。", "",
        build_table(summaries), ""])
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"已寫入 {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
