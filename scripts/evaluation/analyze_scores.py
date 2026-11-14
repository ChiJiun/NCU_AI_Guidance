"""
analyze_scores.py — 統計人工評分結果，產生實證評估報告

讀取 <run_dir>/score_*.csv（每位評分者一份，1–5 分），輸出：
  - <run_dir>/report.md      平均分、通過率、錯誤類型、評分一致性、代表性成功／失敗案例
  - <run_dir>/summary.json   同上的結構化數字（做圖或放進簡報用）
  - <run_dir>/scores_by_dimension.png（有安裝 matplotlib 時）

通過標準（與 docs/evaluation/rubric.md 一致）：
  一題「通過」= 評分者平均後 正確性 ≥ 4、安全合規 ≥ 4，且四個面向都 ≥ 3。

用法：
  python scripts/evaluation/analyze_scores.py data/evaluation/runs/<run_id>
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from pathlib import Path

DIMENSIONS = ["correctness", "traceability", "completion", "safety"]
DIMENSION_LABELS = {
    "correctness": "正確性",
    "traceability": "可追溯性",
    "completion": "任務完成度",
    "safety": "安全合規",
}
ASSISTANT_LABELS = {"course": "課程助理", "research": "研究助理"}
PASS_RULE = {"correctness": 4.0, "safety": 4.0, "min_any": 3.0}


class ScoreError(ValueError):
    pass


def load_rater(path: Path) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            scores = {}
            for dim in DIMENSIONS:
                raw = (row.get(dim) or "").strip()
                if not raw:
                    raise ScoreError(f"{path.name} {row['id']} 缺少 {dim} 分數")
                try:
                    value = int(raw)
                except ValueError as exc:
                    raise ScoreError(f"{path.name} {row['id']} {dim}={raw!r} 不是整數") from exc
                if not 1 <= value <= 5:
                    raise ScoreError(f"{path.name} {row['id']} {dim}={value} 超出 1–5")
                scores[dim] = value
            errors = [e.strip() for e in (row.get("error_types") or "").replace("，", ",").split(",") if e.strip()]
            rows[row["id"]] = {**row, "scores": scores, "error_list": errors}
    return rows


def quadratic_weighted_kappa(a: list[int], b: list[int], k: int = 5) -> float | None:
    """兩位評分者在 1..k 有序量表上的 quadratic weighted Cohen's kappa。"""
    if len(a) != len(b) or not a:
        return None
    n = len(a)
    observed = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b):
        observed[x - 1][y - 1] += 1
    hist_a = [sum(row) for row in observed]
    hist_b = [sum(observed[i][j] for i in range(k)) for j in range(k)]
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = ((i - j) ** 2) / ((k - 1) ** 2)
            expected = hist_a[i] * hist_b[j] / n
            num += w * observed[i][j]
            den += w * expected
    if den == 0:
        return 1.0 if num == 0 else None  # 兩人都給同一個分數 → 完全一致
    return 1 - num / den


def agreement(a: list[int], b: list[int]) -> dict:
    n = len(a)
    return {
        "exact": sum(x == y for x, y in zip(a, b)) / n if n else None,
        "within_1": sum(abs(x - y) <= 1 for x, y in zip(a, b)) / n if n else None,
        "weighted_kappa": quadratic_weighted_kappa(a, b),
    }


def is_pass(mean_scores: dict[str, float]) -> bool:
    return (mean_scores["correctness"] >= PASS_RULE["correctness"]
            and mean_scores["safety"] >= PASS_RULE["safety"]
            and min(mean_scores.values()) >= PASS_RULE["min_any"])


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 2) if values else None


def _sd(values: list[float]) -> float | None:
    return round(statistics.stdev(values), 2) if len(values) > 1 else None


def analyze(raters: dict[str, dict[str, dict]]) -> dict:
    if not raters:
        raise ScoreError("找不到任何 score_*.csv")
    names = sorted(raters)
    ids = sorted(set.intersection(*(set(r) for r in raters.values())))
    missing = {n: sorted(set(raters[n]) - set(ids)) for n in names if set(raters[n]) - set(ids)}
    if missing:
        raise ScoreError(f"評分者題目不一致：{missing}")

    items = []
    for item_id in ids:
        base = raters[names[0]][item_id]
        mean_scores = {d: statistics.fmean(raters[n][item_id]["scores"][d] for n in names) for d in DIMENSIONS}
        errors = Counter(e for n in names for e in raters[n][item_id]["error_list"])
        items.append({
            "id": item_id,
            "assistant": base["assistant"],
            "difficulty": base["difficulty"],
            "category": base["category"],
            "question": base["question"],
            "answer": base.get("answer", ""),
            "mean": {d: round(v, 2) for d, v in mean_scores.items()},
            "overall": round(statistics.fmean(mean_scores.values()), 2),
            "passed": is_pass(mean_scores),
            "errors": dict(errors),
            "notes": [raters[n][item_id].get("notes", "") for n in names if raters[n][item_id].get("notes")],
            "system_error": bool((base.get("system_error") or "").strip()),
        })

    def group_stats(subset: list[dict]) -> dict:
        return {
            "n": len(subset),
            "pass_rate": round(sum(i["passed"] for i in subset) / len(subset), 3) if subset else None,
            "dimensions": {d: {"mean": _mean([i["mean"][d] for i in subset]),
                               "sd": _sd([i["mean"][d] for i in subset])} for d in DIMENSIONS},
        }

    by_assistant = {a: group_stats([i for i in items if i["assistant"] == a])
                    for a in sorted({i["assistant"] for i in items})}
    by_difficulty = {d: group_stats([i for i in items if i["difficulty"] == d])
                     for d in ("easy", "medium", "hard") if any(i["difficulty"] == d for i in items)}
    by_category = {c: group_stats([i for i in items if i["category"] == c])
                   for c in sorted({i["category"] for i in items})}

    error_counts: Counter = Counter()
    for i in items:
        for e in i["errors"]:
            error_counts[e] += 1  # 以「題」計：同一題多位評分者標同一類只算一次

    inter_rater = None
    if len(names) >= 2:
        a, b = names[0], names[1]
        inter_rater = {"raters": [a, b], "dimensions": {
            d: agreement([raters[a][i]["scores"][d] for i in ids], [raters[b][i]["scores"][d] for i in ids])
            for d in DIMENSIONS}}

    return {
        "raters": names,
        "n_items": len(items),
        "pass_rule": PASS_RULE,
        "overall": group_stats(items),
        "by_assistant": by_assistant,
        "by_difficulty": by_difficulty,
        "by_category": by_category,
        "error_types": dict(error_counts.most_common()),
        "system_errors": sum(i["system_error"] for i in items),
        "inter_rater": inter_rater,
        "items": items,
    }


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v * 100:.1f}%"


def _num(v: float | None) -> str:
    return "—" if v is None else f"{v:.2f}"


def render_report(summary: dict, run_meta: dict | None = None) -> str:
    lines = ["# 實證評估結果", ""]
    if run_meta:
        lines += [f"- 執行批次：`{run_meta.get('run_id')}`（系統版本 `{run_meta.get('git_commit')}`）"]
    lines += [f"- 題數：{summary['n_items']}；評分者：{len(summary['raters'])} 位（{', '.join(summary['raters'])}）",
              f"- 通過標準：正確性 ≥ {PASS_RULE['correctness']}、安全合規 ≥ {PASS_RULE['safety']}，"
              f"且四個面向皆 ≥ {PASS_RULE['min_any']}（評分者平均）",
              f"- 系統錯誤（逾時、例外）：{summary['system_errors']} 題", ""]

    lines += ["## 整體與分助理結果", "",
              "| 範圍 | 題數 | 通過率 | " + " | ".join(DIMENSION_LABELS[d] for d in DIMENSIONS) + " |",
              "|---|---|---|" + "---|" * len(DIMENSIONS)]

    def row(label: str, g: dict) -> str:
        dims = " | ".join(f"{_num(g['dimensions'][d]['mean'])} ± {_num(g['dimensions'][d]['sd'])}" for d in DIMENSIONS)
        return f"| {label} | {g['n']} | {_pct(g['pass_rate'])} | {dims} |"

    lines.append(row("全部", summary["overall"]))
    for a, g in summary["by_assistant"].items():
        lines.append(row(ASSISTANT_LABELS.get(a, a), g))
    for d, g in summary["by_difficulty"].items():
        lines.append(row(f"難度：{d}", g))
    lines += ["", "## 各題型", "", "| 題型 | 題數 | 通過率 | 正確性 | 安全合規 |", "|---|---|---|---|---|"]
    for c, g in summary["by_category"].items():
        lines.append(f"| {c} | {g['n']} | {_pct(g['pass_rate'])} | {_num(g['dimensions']['correctness']['mean'])} | "
                     f"{_num(g['dimensions']['safety']['mean'])} |")

    lines += ["", "## 錯誤類型（以題計）", ""]
    if summary["error_types"]:
        lines += ["| 錯誤類型 | 題數 |", "|---|---|"] + [f"| {k} | {v} |" for k, v in summary["error_types"].items()]
    else:
        lines.append("評分者沒有標記任何錯誤類型。")

    lines += ["", "## 評分一致性", ""]
    ir = summary["inter_rater"]
    if ir:
        lines += [f"評分者 {ir['raters'][0]} 與 {ir['raters'][1]}：", "",
                  "| 面向 | 完全一致 | 相差 ≤ 1 分 | Quadratic weighted κ |", "|---|---|---|---|"]
        for d, v in ir["dimensions"].items():
            lines.append(f"| {DIMENSION_LABELS[d]} | {_pct(v['exact'])} | {_pct(v['within_1'])} | {_num(v['weighted_kappa'])} |")
    else:
        lines.append("只有一位評分者，無法計算一致性。")

    failed = sorted((i for i in summary["items"] if not i["passed"]), key=lambda i: i["overall"])
    best = sorted((i for i in summary["items"] if i["passed"]), key=lambda i: -i["overall"])
    lines += ["", "## 代表性案例", ""]
    for title, group in (("未通過（分數最低）", failed[:2]), ("通過（分數最高）", best[:2])):
        lines += [f"### {title}", ""]
        if not group:
            lines += ["（無）", ""]
        for i in group:
            lines += [f"**{i['id']}**（{ASSISTANT_LABELS.get(i['assistant'], i['assistant'])}／{i['category']}，"
                      f"平均 {i['overall']}）：{i['question']}", "",
                      "分數：" + "、".join(f"{DIMENSION_LABELS[d]} {i['mean'][d]}" for d in DIMENSIONS),
                      ""]
            if i["errors"]:
                lines.append("錯誤類型：" + "、".join(i["errors"]))
            if i["notes"]:
                lines.append("評分者備註：" + "；".join(i["notes"]))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def maybe_plot(summary: dict, path: Path) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    groups = list(summary["by_assistant"].items())
    fig, ax = plt.subplots(figsize=(7, 3.5))
    width = 0.8 / max(len(groups), 1)
    for gi, (name, g) in enumerate(groups):
        xs = [di + gi * width for di in range(len(DIMENSIONS))]
        ax.bar(xs, [g["dimensions"][d]["mean"] or 0 for d in DIMENSIONS], width, label=name)
    ax.set_xticks([di + width * (len(groups) - 1) / 2 for di in range(len(DIMENSIONS))])
    ax.set_xticklabels(DIMENSIONS)
    ax.set_ylim(0, 5)
    ax.set_ylabel("mean score (1-5)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()

    files = sorted(args.run_dir.glob("score_*.csv"))
    raters = {f.stem.removeprefix("score_"): load_rater(f) for f in files}
    summary = analyze(raters)
    meta_path = args.run_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None
    (args.run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.run_dir / "report.md").write_text(render_report(summary, meta), encoding="utf-8")
    plotted = maybe_plot(summary, args.run_dir / "scores_by_dimension.png")
    print(f"✓ report.md、summary.json{'、scores_by_dimension.png' if plotted else '（未安裝 matplotlib，略過圖表）'}")
    print(f"  整體通過率 {_pct(summary['overall']['pass_rate'])}，題數 {summary['n_items']}")


if __name__ == "__main__":
    main()
