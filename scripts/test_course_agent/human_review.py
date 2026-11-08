"""
human_review.py

人工抽查 AI 評審（v2）：
  make   產生盲評用的審查表（A～J 每類 2 題：該類綜合分中位數以下、以上各一，固定亂數種子）
  agree  使用者填完後，計算人工與 AI 評審的一致率

執行方式：
  python scripts/test_course_agent/human_review.py make --run 20261108_224715 --out 人工抽查_AI評審.md
  python scripts/test_course_agent/human_review.py agree 人工抽查_AI評審.md --run 20261108_224715
"""

import argparse
import json
import random
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import judge_with_claude as J  # noqa: E402

SEED = 20261109
MARK_RE = re.compile(r"<!-- review:(\S+) -->")
CHECK_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|[^|]*\|\s*([^|]*?)\s*\|", re.M)
DIM_ROW_RE = re.compile(r"^\|\s*(" + "|".join(J.DIMENSIONS.values()) + r")\s*\|\s*([^|]*?)\s*\|", re.M)
YES = {"✓", "✔", "v", "V", "o", "O", "y", "Y", "met", "是", "有", "達成", "1"}
NO = {"✗", "✘", "x", "X", "n", "N", "not_met", "否", "沒有", "未達成", "0"}


# ── 資料載入 ──────────────────────────────────────────────────────────────────

def load_judgements(jsonl: Path) -> dict[str, list[dict]]:
    """{key: [第 1 次評審, 第 2 次評審, ...]}（依 pass 排序）"""
    by_key: dict[str, dict[int, dict]] = defaultdict(dict)
    for line in jsonl.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("judgement"):
                by_key[r["key"]][r["pass"]] = r["judgement"]
    return {k: [v[p] for p in sorted(v)] for k, v in by_key.items()}


def question_score(js: list[dict]) -> float:
    return statistics.mean(J.check_rate(j) for j in js) * 100 + statistics.mean(J.aux_total(j) for j in js) / 8


def pick_sample(scores: dict[str, float], groups: dict[str, str], seed: int = SEED) -> list[str]:
    """每類取兩題：綜合分 ≤ 該類中位數的一題、> 中位數的一題（全部同分時改取 ≥ 中位數的另一題）。"""
    rng = random.Random(seed)
    by_group: dict[str, list[str]] = defaultdict(list)
    for key, g in groups.items():
        if key in scores:
            by_group[g].append(key)
    picked = []
    for g in sorted(by_group):
        keys = sorted(by_group[g])
        med = statistics.median(scores[k] for k in keys)
        low = [k for k in keys if scores[k] <= med]
        lo = rng.choice(low)
        high = [k for k in keys if scores[k] > med] or [k for k in keys if scores[k] >= med and k != lo]
        picked += [lo] + ([rng.choice(high)] if high else [])
    return picked


# ── 產生審查表 ────────────────────────────────────────────────────────────────

def _quote(text: str) -> list[str]:
    return [f"> {line}" if line.strip() else ">" for line in (text or "（空白）").splitlines()]


def _cell(text: str) -> str:
    return str(text).replace("|", "／").replace("\n", " ")


def render_question(i: int, key: str, q: dict, rec: dict, hard: dict, js: list[dict]) -> list[str]:
    calls = [f"`{c.get('tool')}({json.dumps(c.get('args', {}), ensure_ascii=False)})` → "
             + (f"{c['count']} 筆" if isinstance(c.get("count"), int) else "未回報筆數")
             for c in rec.get("tool_calls") or []]
    obs = hard["observed"]
    out = [f"## {i}. {key}｜{q['question']}", "", f"<!-- review:{key} -->", "",
           f"- 類別：{q['group']}　預期行為：{J.BEHAVIORS[q['expected_behavior']]}　回答字數：{hard['answer_chars']}",
           "- 呼叫的工具：" + ("；".join(calls) if calls else "（沒有呼叫工具）"),
           f"- 程式判定（非 AI）：{'有' if obs['tool_called'] else '未'}呼叫工具、結尾{'有' if obs['asks_question'] else '未'}追問"
           f" → 行為{'符合' if hard['behavior_ok'] else '不符'}預期" + (f"（{hard['behavior_problem']}）" if hard["behavior_problem"] else ""),
           "", "### 課程助理的回答", "", *_quote(rec.get("answer", "")), "",
           "### 人工判定：檢查點", "", "| # | 檢查點 | 達成？（填 ✓ 或 ✗） | 備註 |", "|---|---|---|---|"]
    out += [f"| {n} | {_cell(c)} |  |  |" for n, c in enumerate(q["checks"], 1)]
    out += ["", "### 人工評分：四面向", "", "| 面向 | 我的分數（0–2） | 備註 |", "|---|---|---|"]
    out += [f"| {name} |  |  |" for name in J.DIMENSIONS.values()]
    out += ["", "- 事實錯誤（課名、系所、學分、規定寫錯；沒有就寫「無」）：",
            "- 我會標的錯誤標記（hallucinated_course／hallucinated_department／unsupported_career_claim／ignored_constraint；沒有就寫「無」）：",
            "", "<details>", "<summary>AI 評審的判定（自己評完再展開）</summary>", ""]
    if js:
        j1 = js[0]
        out += ["**檢查點（第 1 次評審）**", "", "| # | AI 判定 | AI 引用的證據 | 第 2 次評審 |", "|---|---|---|---|"]
        for n, c in enumerate(j1["checks"], 1):
            second = js[1]["checks"][n - 1]["verdict"] if len(js) > 1 else ""
            mark = {"met": "✓", "not_met": "✗"}
            out.append(f"| {n} | {mark[c['verdict']]} | {_cell(c['evidence'])} | {mark.get(second, '—')} |")
        out += ["", "**四面向（第 1 次評審）**", "", "| 面向 | AI 分數 | AI 的理由 | 第 2 次評審 |", "|---|---|---|---|"]
        for k, name in J.DIMENSIONS.items():
            second = js[1]["scores"][k] if len(js) > 1 else "—"
            out.append(f"| {name} | {j1['scores'][k]} | {_cell(j1['reasons'].get(k, ''))} | {second} |")
        out += [f"| **總分** | **{J.aux_total(j1)}** |  | {J.aux_total(js[1]) if len(js) > 1 else '—'} |", "",
                "- 錯誤標記：" + ("、".join(j1["flags"]) or "無") + (f"（第 2 次：{'、'.join(js[1]['flags']) or '無'}）" if len(js) > 1 else ""),
                "- AI 認為需人工對照：" + ("；".join(j1["needs_human_check"]) or "無")]
    else:
        out.append("（這題沒有 AI 評審紀錄）")
    if hard["tags"]["unknown"]:
        out.append("- 程式查不到的課名：" + "、".join(hard["tags"]["unknown"]))
    out += ["", "</details>", "", "---", ""]
    return out


def make(args) -> int:
    run = args.run
    results = json.loads((Path(args.results_dir) / f"{run}.json").read_text(encoding="utf-8"))["results"]
    data = json.loads(Path(args.eval).read_text(encoding="utf-8"))
    qmap = {q["id"]: q for q in data["questions"]}
    banned = set(data["meta"]["tools_must_not_call"])
    known = J.load_known_courses()
    judgements = load_judgements(Path(args.judge_dir) / f"{run}_{J.OUT_SUFFIX}.jsonl")

    recs = {k: r for k, r in J.index_records(results) if r["category"] in qmap and "#" not in k}
    scores = {k: question_score(judgements[k]) for k in recs if judgements.get(k)}
    sample = pick_sample(scores, {k: qmap[k]["group"] for k in recs}, args.seed)

    lines = ["# 人工抽查：AI 評審是否可信（評分 v2）", "",
             f"> 來源：`project/data/test_results/{run}.json`（課程助理回答）與 `{run}_{J.OUT_SUFFIX}.jsonl`（AI 評審，每題評 2 次）。",
             f"> 抽樣：A～J 十類各 2 題，一題來自該類綜合分（檢查點達成率為主、四面向為次）中位數以下、一題來自中位數以上；"
             f"固定亂數種子 {args.seed}，可用 `python scripts/test_course_agent/human_review.py make --run {run}` 重現。共 {len(sample)} 題。", "",
             "## 怎麼審（先盲評，再對照）", "",
             "1. **先別展開「AI 評審的判定」**。讀問題和回答後，在「檢查點」表逐條填 ✓（達成）或 ✗（未達成），在「四面向」表填 0、1、2。",
             "2. 發現事實錯誤（課名、系所、學分、規定）請寫出來，這比分數更重要；可對照呼叫的工具與 `project/data/processed/` 的課程資料。",
             "3. 全部填完再展開 AI 的判定看差在哪裡，**不要回頭改自己的分數**；有想法可寫在備註。",
             "4. 填完後執行下面指令，會算出人工與 AI 的一致率：", "",
             "```bash", f"python scripts/test_course_agent/human_review.py agree \"<本檔路徑>\" --run {run}", "```", "",
             "## 四面向評分標準（每項 0–2，彼此不重疊；長度不在這裡評）", "",
             "| 面向 | 2 | 1 | 0 |", "|---|---|---|---|",
             "| 切題 | 回應了問題的每個部分，點名的系所／課程／要求都有處理 | 回應主要問題但漏掉一部分或偏題 | 答非所問 |",
             "| 正確與誠實 | 課名、系所、學程、規定都有根據；查不到或超出資料範圍有明說；沒有保證、排名、薪資斷言 | 大致有根據，但一兩處過度延伸或含糊帶過 | 編造課程或系所、與資料矛盾、無根據的保證 |",
             "| 高中生看得懂 | 口語白話，學分／必修／先修／學程第一次出現有解釋，先講學什麼再給課名 | 大致可讀，但有未解釋術語或課表式段落 | 像課表或公文，看完仍不懂 |",
             "| 引導探索 | 給出有區隔的方向（純查詢題則答完整），不替學生決定，結尾有具體、答得出來的追問或下一步 | 方向單一或下一步空泛 | 只推單一選項、替學生下結論、沒有下一步 |",
             "", "## 進度總表", "", "| # | 題號 | 類別 | 預期行為 | 填完了嗎 |", "|---|---|---|---|---|"]
    lines += [f"| {i} | {k} | {qmap[k]['group']} | {J.BEHAVIORS[qmap[k]['expected_behavior']]} |  |" for i, k in enumerate(sample, 1)]
    lines += ["", "---", ""]
    for i, k in enumerate(sample, 1):
        q, rec = qmap[k], recs[k]
        lines += render_question(i, k, q, rec, J.hard_signals(q, rec, banned, known), judgements.get(k, []))
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"已寫入 {args.out}（{len(sample)} 題：{'、'.join(sample)}）")
    return 0


# ── 計算一致率 ────────────────────────────────────────────────────────────────

def parse_sheet(text: str) -> dict[str, dict]:
    """回傳 {題號: {"checks": {n: "met"/"not_met"}, "scores": {dim_key: 0-2}}}，只收已填的格子。"""
    name_to_key = {v: k for k, v in J.DIMENSIONS.items()}
    parts = MARK_RE.split(text)
    out = {}
    for key, body in zip(parts[1::2], parts[2::2]):
        body = body.split("<details>")[0]
        checks, scores = {}, {}
        for n, val in CHECK_ROW_RE.findall(body):
            v = val.strip()
            if v in YES:
                checks[int(n)] = "met"
            elif v in NO:
                checks[int(n)] = "not_met"
        for name, val in DIM_ROW_RE.findall(body):
            if val.strip() in ("0", "1", "2"):
                scores[name_to_key[name]] = int(val.strip())
        out[key] = {"checks": checks, "scores": scores}
    return out


def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    labels = {x for p in pairs for x in p}
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    pe = sum((sum(a == l for a, _ in pairs) / n) * (sum(b == l for _, b in pairs) / n) for l in labels)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else None


def agreement(human: dict[str, dict], ai: dict[str, list[dict]], which: int = 0) -> dict:
    """人工 vs 第 which+1 次 AI 評審。"""
    check_pairs, dim_pairs, totals = [], defaultdict(list), []
    for key, h in human.items():
        js = ai.get(key) or []
        if len(js) <= which:
            continue
        j = js[which]
        for n, v in h["checks"].items():
            if 1 <= n <= len(j["checks"]):
                check_pairs.append((v, j["checks"][n - 1]["verdict"]))
        for k, v in h["scores"].items():
            dim_pairs[k].append((v, j["scores"][k]))
        if len(h["scores"]) == len(J.DIMENSIONS):
            totals.append((sum(h["scores"].values()), J.aux_total(j)))

    def pct(xs):
        return round(100 * sum(xs) / len(xs), 1) if xs else None

    return {
        "questions": sum(1 for k, h in human.items() if (h["checks"] or h["scores"]) and len(ai.get(k) or []) > which),
        "check_items": len(check_pairs),
        "check_agree": pct([a == b for a, b in check_pairs]),
        "check_kappa": cohen_kappa(check_pairs),
        "human_check_rate": pct([a == "met" for a, _ in check_pairs]),
        "ai_check_rate": pct([b == "met" for _, b in check_pairs]),
        "dim_exact": {k: pct([a == b for a, b in v]) for k, v in dim_pairs.items()},
        "dim_within_1": {k: pct([abs(a - b) <= 1 for a, b in v]) for k, v in dim_pairs.items()},
        "total_pairs": len(totals),
        "total_exact": pct([a == b for a, b in totals]),
        "total_within_1": pct([abs(a - b) <= 1 for a, b in totals]),
        "mean_total_human": round(statistics.mean(a for a, _ in totals), 2) if totals else None,
        "mean_total_ai": round(statistics.mean(b for _, b in totals), 2) if totals else None,
    }


def agree(args) -> int:
    human = parse_sheet(Path(args.sheet).read_text(encoding="utf-8"))
    ai = load_judgements(Path(args.judge_dir) / f"{args.run}_{J.OUT_SUFFIX}.jsonl")
    filled = {k: h for k, h in human.items() if h["checks"] or h["scores"]}
    print(f"審查表共 {len(human)} 題，已填 {len(filled)} 題")
    if not filled:
        return 1
    lines = [f"# 人工 vs AI 評審一致率（{args.run}，{len(filled)} 題）", ""]
    for which in (0, 1):
        a = agreement(filled, ai, which)
        if not a["questions"]:
            continue
        lines += [f"## 對照第 {which + 1} 次 AI 評審", "",
                  "| 指標 | 數值 |", "|---|---|",
                  f"| 檢查點判定一致率 | {a['check_agree']}%（{a['check_items']} 個；Cohen's κ = {a['check_kappa']}） |",
                  f"| 檢查點達成率：人工／AI | {a['human_check_rate']}%／{a['ai_check_rate']}% |",
                  f"| 四面向總分完全一致 | {a['total_exact']}%（{a['total_pairs']} 題） |",
                  f"| 四面向總分差 1 分內 | {a['total_within_1']}% |",
                  f"| 四面向平均總分：人工／AI | {a['mean_total_human']}／{a['mean_total_ai']} |"]
        for k, name in J.DIMENSIONS.items():
            if k in a["dim_exact"]:
                lines.append(f"| 　└ {name}：完全一致／差 1 內 | {a['dim_exact'][k]}%／{a['dim_within_1'][k]}% |")
        lines.append("")
    text = "\n".join(lines)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"已寫入 {args.out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="人工抽查 AI 評審（v2）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make", help="產生盲評審查表")
    m.add_argument("--run", required=True, help="run_id，例如 20261108_224715")
    m.add_argument("--out", required=True, help="輸出 md 路徑")
    m.add_argument("--seed", type=int, default=SEED)
    m.add_argument("--results-dir", default=str(J.RESULTS_DIR), help="課程助理結果 json 所在資料夾")
    m.add_argument("--judge-dir", default=str(J.RESULTS_DIR), help="v2 評審 jsonl 所在資料夾")
    m.add_argument("--eval", default=str(J.EVAL_PATH))
    a = sub.add_parser("agree", help="計算人工與 AI 的一致率")
    a.add_argument("sheet", help="填好的審查表 md")
    a.add_argument("--run", required=True)
    a.add_argument("--judge-dir", default=str(J.RESULTS_DIR))
    a.add_argument("--out", default=None, help="把結果另存成 md")
    args = ap.parse_args()
    return make(args) if args.cmd == "make" else agree(args)


if __name__ == "__main__":
    sys.exit(main())
