"""
judge_with_claude.py

對 test_rag.py 跑出的結果做評分，分兩層：
  1. 程式檢查（不花額度）：auto_tool 工具預期、<course> 標籤是否有對應的課程卡片、回答是否過長
  2. Claude 評審（claude -p）：以「高二學生＋輔導老師」的視角，按 manual_12 六面向打 0–2 分並標記錯誤

評審透過 Claude Code 的無頭模式 `claude -p` 呼叫，使用 .env 的 CLAUDE_CODE_OAUTH_TOKEN
（claude setup-token 產生，僅限 Claude Code 使用，不可拿去直接呼叫 Anthropic API）。

執行方式：
  python scripts/test_course_agent/judge_with_claude.py                    # 評最新一份結果
  python scripts/test_course_agent/judge_with_claude.py --results data/test_results/xxx.json
  python scripts/test_course_agent/judge_with_claude.py --ids A01,D03      # 只評指定題
  python scripts/test_course_agent/judge_with_claude.py --no-judge         # 只做程式檢查
評審結果逐題寫入 .jsonl，中斷或額度用完後重跑會自動略過已評完的題目。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
RESULTS_DIR = ROOT / "data" / "test_results"
EVAL_PATH = ROOT / "docs" / "10-retrieval-evaluation" / "eval-set-v1.json"
ENV_PATH = ROOT / ".env"
TOKEN_VAR = "CLAUDE_CODE_OAUTH_TOKEN"

DIMENSIONS = {
    "evidence": "證據正確性",
    "relevance": "探索相關性",
    "breadth": "範圍與多樣性",
    "clarify": "澄清與不確定性",
    "readable": "高中生可理解性",
    "next_step": "下一步可行性",
}

JUDGE_SYSTEM = """你是「大學選系輔導」的評審，同時扮演兩個角色：
(1) 一位高二學生：還不太懂大學，看到學分、先修、必修、學程這些詞會卡住，希望有人像學長姐一樣講清楚；
(2) 一位嚴謹的輔導老師：不接受編造、不接受沒根據的保證。

你要評的是一個「中央大學課程助理」對高中生提問的回答。
你看不到工具回傳的原始資料，只看得到：問題、回答、助理呼叫了哪些工具與參數、系統產生的課程卡片名單、程式檢查訊號。
因此：
- 課名不在「課程卡片名單」內只是提示：可能是真實存在的課但系統沒產生卡片。只有課名本身明顯不像中大開的課、或與工具參數矛盾時才標 hallucinated_course；否則寫進 needs_human_check。
- 薪資、就業率、錄取分數、名額、涼課、老師評價、「適合什麼個性」這類中大課程資料不可能有的內容，只要回答裡出現就是 unsupported_career_claim。
- 拿不準的地方寫進 needs_human_check，不要為了湊分數而下結論。
只輸出一個 JSON 物件，不要有任何其他文字或 markdown 圍欄。"""

RUBRIC = """評分標準（每面向 0/1/2）：
- evidence 證據正確性：2=回答內容都能對上工具呼叫與課程卡片，沒有越界斷言；1=大致有根據但有一兩句無法對上或過度歸納；0=明顯編造或與卡片矛盾。
- relevance 探索相關性：2=切中學生真正想探索的方向；1=部分切題；0=答非所問。
- breadth 範圍與多樣性：2=給了 2–4 個不同方向或比較面向，不只塞單一系；1=範圍偏窄或偏多；0=只推單一選項，或一次倒出一長串課名。
- clarify 澄清與不確定性：2=該追問時追問、查不到時明說、有適度保留語氣；1=有做但生硬或不足；0=該追問卻直接給結論、查不到卻裝作有。
- readable 高中生可理解性：站在高二學生的角度，2=用白話、新名詞有解釋、先講學什麼再講課名、長度適中；1=可讀但有術語或太長；0=像公文或課表，學生看完仍不知道在說什麼。
- next_step 下一步可行性：2=結尾給出學生接得下去的具體下一步（例如選一條方向、看哪類課）；1=有但空泛；0=沒有。

error_flags 只在有明確證據時標記，可用值：
hallucinated_course, hallucinated_department, unsupported_career_claim,
premature_single_recommendation, overwhelming_list, missed_clarification, ignored_constraint

輸出 JSON 格式：
{
  "scores": {"evidence": 0-2, "relevance": 0-2, "breadth": 0-2, "clarify": 0-2, "readable": 0-2, "next_step": 0-2},
  "reasons": {"evidence": "一句話", "relevance": "一句話", "breadth": "一句話", "clarify": "一句話", "readable": "一句話", "next_step": "一句話"},
  "flags": ["..."],
  "student_view": "用高二學生的口吻，一兩句話說看完這個回答之後的感受與還不懂的地方",
  "worst_sentence": "回答中最需要人工檢查的一句原文，沒有則留空字串",
  "needs_human_check": ["無法從現有資訊判斷、需要對照工具原始回傳的地方"]
}"""

ERROR_FLAGS = (
    "hallucinated_course", "hallucinated_department", "unsupported_career_claim",
    "premature_single_recommendation", "overwhelming_list", "missed_clarification", "ignored_constraint",
)

TAG_RE = re.compile(r"<course>(.*?)</course>", re.S)
PAREN_RE = re.compile(r"[（(].*?[）)]")
ANSWER_TOO_LONG = 900  # 字；高中生一次要讀完的上限，僅作為提示訊號


# ── 環境與資料載入 ────────────────────────────────────────────────────────────

def load_token() -> str | None:
    """從環境變數或 .env 取得 token；不印出內容。"""
    val = os.environ.get(TOKEN_VAR, "").strip()
    if val:
        return val
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{TOKEN_VAR}="):
                return line.split("=", 1)[1].strip().strip("'\"") or None
    return None


def latest_results() -> Path:
    files = sorted(p for p in RESULTS_DIR.glob("*.json") if re.fullmatch(r"\d{8}_\d{6}", p.stem))
    if not files:
        sys.exit("找不到 test_rag.py 的結果檔，請先跑 test_rag.py --questions eval-set-v1.json")
    return files[-1]


def index_records(results: list[dict]) -> list[tuple[str, dict]]:
    """結果的 category 欄位是題號；同題重跑時給 A01#1、A01#2。"""
    seen: Counter = Counter()
    out = []
    for rec in results:
        qid = rec["category"]
        seen[qid] += 1
        out.append((qid if seen[qid] == 1 else f"{qid}#{seen[qid]}", rec))
    return out


# ── 程式檢查 ──────────────────────────────────────────────────────────────────

def check_tools(q: dict, rec: dict, banned: set[str]) -> dict:
    t = q["tools"]
    used = set(rec.get("tools_used") or [])
    calls = Counter(c.get("tool") for c in rec.get("tool_calls") or [])
    problems = []

    if rec.get("error"):
        problems.append(f"執行錯誤：{rec['error']}")
    for name in t["all"]:
        if name not in used:
            problems.append(f"未呼叫必要工具 {name}")
    for name, n in t["min_calls"].items():
        if calls.get(name, 0) < n:
            problems.append(f"{name} 只呼叫 {calls.get(name, 0)} 次，預期至少 {n} 次")
    if t["any"] and not (used & set(t["any"])):
        # allow_no_tool：先追問或說明邊界時，沒呼叫任何工具是允許的
        if not (t["allow_no_tool"] and not used):
            problems.append(f"未呼叫 any 清單中的任何工具：{', '.join(t['any'])}")
    for name in used & banned:
        problems.append(f"呼叫了已停用工具 {name}")
    return {"pass": not problems, "problems": problems}


def check_course_tags(rec: dict) -> dict:
    """回答中被 <course> 標記的課，必須出現在系統產生的課程卡片裡。"""
    answer = rec.get("answer", "")
    card_names = {PAREN_RE.sub("", c.get("name", "")).strip() for c in rec.get("course_cards") or []}
    tagged = [PAREN_RE.sub("", m).strip() for m in TAG_RE.findall(answer)]
    missing = sorted({n for n in tagged if n and n not in card_names})
    return {"tagged": len(tagged), "cards": len(card_names), "tag_without_card": missing}


def signals(q: dict, rec: dict, banned: set[str]) -> dict:
    answer = rec.get("answer", "")
    return {
        "tools": check_tools(q, rec, banned),
        "tags": check_course_tags(rec),
        "answer_chars": len(answer),
        "answer_too_long": len(answer) > ANSWER_TOO_LONG,
        "empty_answer": not answer.strip(),
    }


# ── Claude 評審 ───────────────────────────────────────────────────────────────

def build_prompt(q: dict, rec: dict, sig: dict) -> str:
    def _count(c: dict) -> str:
        n = c.get("count")
        # 非課程類工具（老師、畢業規定等）不回報筆數，不能讓評審誤以為查無資料
        return f"找到 {n} 筆" if isinstance(n, int) else "（此工具未回報筆數，不代表查無資料）"

    calls = [f"- {c.get('tool')}({json.dumps(c.get('args', {}), ensure_ascii=False)}) → {_count(c)}"
             for c in rec.get("tool_calls") or []] or ["- （沒有呼叫任何工具）"]
    cards = sorted({c.get("name", "") for c in rec.get("course_cards") or []}) or ["（無）"]
    return "\n".join([
        RUBRIC, "",
        f"【題號】{q['id']}　【意圖】{'、'.join(q['intent'])}",
        f"【高中生的問題】{q['question']}", "",
        "【這題的檢查點】", *[f"- {c}" for c in q["checks"]], "",
        f"【這題要特別留意的錯誤】{'、'.join(q['watch_flags']) or '無'}", "",
        "【助理呼叫的工具】", *calls, "",
        f"【系統產生的課程卡片名單（共 {len(cards)} 門）】{'、'.join(cards)}", "",
        "【程式檢查訊號】",
        f"- 工具預期：{'通過' if sig['tools']['pass'] else '未通過：' + '；'.join(sig['tools']['problems'])}",
        f"- 回答中被 <course> 標記但卡片名單沒有的課（僅供參考，不等於編造）：{'、'.join(sig['tags']['tag_without_card']) or '無'}",
        f"- 回答長度：{sig['answer_chars']} 字", "",
        "【助理的回答】", rec.get("answer", "") or "（空白）", "",
        "請依標準評分並只輸出 JSON。",
    ])


def run_claude(prompt: str, model: str, token: str, timeout: int) -> tuple[str | None, str]:
    """回傳 (文字結果, 錯誤訊息)。"""
    exe = shutil.which("claude")
    if not exe:
        return None, "找不到 claude 指令"
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # 確保走訂閱而非 API 計費
    env[TOKEN_VAR] = token
    cmd = [exe, "-p", "--tools", "", "--system-prompt", JUDGE_SYSTEM,
           "--output-format", "json", "--no-session-persistence", "--model", model]
    try:
        proc = subprocess.run(cmd, input=prompt.encode("utf-8"), capture_output=True,
                              env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    err = proc.stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        return None, (err or out)[:300]
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        return None, f"輸出不是 JSON：{out[:200]}"
    if payload.get("is_error"):
        return None, str(payload.get("result", ""))[:300]
    return payload.get("result", ""), ""


def parse_judgement(text: str) -> dict | None:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        j = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    scores = j.get("scores", {})
    if set(scores) != set(DIMENSIONS) or any(scores[k] not in (0, 1, 2) for k in scores):
        return None
    # 評審偶爾會自創標記或回傳字串；只保留合法標記，欄位型態統一
    raw_flags = j.get("flags")
    j["flags"] = [f for f in (raw_flags if isinstance(raw_flags, list) else []) if f in ERROR_FLAGS]
    if not isinstance(j.get("reasons"), dict):
        j["reasons"] = {}
    check = j.get("needs_human_check")
    j["needs_human_check"] = [str(x) for x in check] if isinstance(check, list) else ([str(check)] if check else [])
    return j


def looks_like_quota(msg: str) -> bool:
    m = msg.lower()
    return any(w in m for w in ("limit", "quota", "rate", "usage", "429", "overloaded"))


# ── 報告 ──────────────────────────────────────────────────────────────────────

def total(j: dict) -> int:
    return sum(j["scores"].values())


def build_report(rows: list[dict], meta: dict, groups: dict) -> str:
    judged = [r for r in rows if r.get("judgement")]
    lines = [f"# 評測結果 {meta['run_id']}", "",
             f"- 結果檔：`{meta['results_file']}`　評審模型：`{meta['model']}`",
             f"- 共 {len(rows)} 筆，已由 Claude 評審 {len(judged)} 筆", "",
             "> 評審看不到工具原始回傳，分數僅供篩選；標記為「需人工檢查」的題目請對照原始結果抽查。", ""]

    tool_pass = sum(1 for r in rows if r["signals"]["tools"]["pass"])
    lines += ["## 一、程式檢查（不經 LLM）", "",
              f"- 工具預期通過：{tool_pass}/{len(rows)}",
              f"- 回答超過 {ANSWER_TOO_LONG} 字：{sum(r['signals']['answer_too_long'] for r in rows)} 題",
              f"- 有 <course> 標記但卡片名單沒有的課：{sum(bool(r['signals']['tags']['tag_without_card']) for r in rows)} 題",
              f"- 空白回答或執行錯誤：{sum(1 for r in rows if r['signals']['empty_answer'] or r['error'])} 題", ""]
    fails = [r for r in rows if not r["signals"]["tools"]["pass"]]
    if fails:
        lines += ["### 工具預期未通過", "", "| 題號 | 問題 | 原因 |", "|---|---|---|"]
        for r in fails:
            lines.append(f"| {r['key']} | {r['question']} | {'；'.join(r['signals']['tools']['problems'])} |")
        lines.append("")
    tagged = [r for r in rows if r["signals"]["tags"]["tag_without_card"]]
    if tagged:
        lines += ["### 疑似編造或未被系統收錄的課程標記", "", "| 題號 | 課名 |", "|---|---|"]
        for r in tagged:
            lines.append(f"| {r['key']} | {'、'.join(r['signals']['tags']['tag_without_card'])} |")
        lines.append("")

    if judged:
        lines += ["## 二、Claude 評審（高中生視角，每面向 0–2，滿分 12）", "",
                  f"- 平均總分：{sum(total(r['judgement']) for r in judged) / len(judged):.2f} / 12", "",
                  "| 面向 | 平均 |", "|---|---|"]
        for k, name in DIMENSIONS.items():
            lines.append(f"| {name} | {sum(r['judgement']['scores'][k] for r in judged) / len(judged):.2f} |")
        by_group: dict[str, list[dict]] = defaultdict(list)
        for r in judged:
            by_group[r["group"]].append(r)
        lines += ["", "### 各類別平均總分", "", "| 類別 | 題數 | 平均 |", "|---|---|---|"]
        for g, rs in sorted(by_group.items()):
            lines.append(f"| {g}. {groups.get(g, '')} | {len(rs)} | {sum(total(r['judgement']) for r in rs) / len(rs):.2f} |")
        flag_count = Counter(f for r in judged for f in r["judgement"]["flags"])
        lines += ["", "### 錯誤標記次數", ""]
        lines += [f"- `{f}`：{n}" for f, n in flag_count.most_common()] or ["- 無"]
        lines += ["", "### 分數最低的 10 題（優先看）", "",
                  "| 題號 | 總分 | 問題 | 高中生的感受 | 錯誤標記 |", "|---|---|---|---|---|"]
        for r in sorted(judged, key=lambda r: total(r["judgement"]))[:10]:
            j = r["judgement"]
            lines.append(f"| {r['key']} | {total(j)} | {r['question']} | {j.get('student_view', '')} | {'、'.join(j['flags'])} |")
        checks = [r for r in judged if r["judgement"].get("needs_human_check") or r["judgement"].get("worst_sentence")]
        lines += ["", "### 需人工對照原始回傳的項目", ""]
        for r in checks:
            j = r["judgement"]
            items = list(j.get("needs_human_check") or [])
            if j.get("worst_sentence"):
                items.insert(0, f"最可疑句：「{j['worst_sentence']}」")
            lines.append(f"- **{r['key']}**：" + "；".join(items))
        lines.append("")
    skipped = [r for r in rows if not r.get("judgement")]
    if skipped:
        lines += ["## 未評審", "", "、".join(f"{r['key']}（{r.get('judge_error', '未執行')}）" for r in skipped), ""]
    return "\n".join(lines)


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="用 claude -p 為 test_rag 結果評分（高中生視角）")
    ap.add_argument("--results", default=None, help="test_rag.py 的結果 json（預設最新一份）")
    ap.add_argument("--eval", default=str(EVAL_PATH), help="評測集 json")
    ap.add_argument("--ids", default=None, help="只評指定題號，逗號分隔，例如 A01,D03")
    ap.add_argument("--model", default="sonnet", help="評審模型別名（預設 sonnet）")
    ap.add_argument("--timeout", type=int, default=180, help="每題逾時秒數")
    ap.add_argument("--no-judge", action="store_true", help="只做程式檢查，不呼叫 claude")
    args = ap.parse_args()

    results_path = Path(args.results) if args.results else latest_results()
    results = json.loads(results_path.read_text(encoding="utf-8"))["results"]
    data = json.loads(Path(args.eval).read_text(encoding="utf-8"))
    qmap = {q["id"]: q for q in data["questions"]}
    banned = set(data["meta"]["tools_must_not_call"])

    token = None
    if not args.no_judge:
        token = load_token()
        if not token:
            sys.exit(f"找不到 {TOKEN_VAR}：請在 .env 填入 claude setup-token 產生的 token，或改用 --no-judge")

    run_id = results_path.stem
    out_jsonl = RESULTS_DIR / f"{run_id}_judge.jsonl"
    out_md = RESULTS_DIR / f"{run_id}_judge.md"
    done: dict[str, dict] = {}
    if out_jsonl.exists():
        for line in out_jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("judgement"):
                    done[row["key"]] = row

    wanted = {x.strip() for x in args.ids.split(",")} if args.ids else None
    rows: list[dict] = []
    quota_hit = False
    for key, rec in index_records(results):
        qid = rec["category"]
        if qid not in qmap or (wanted and qid not in wanted):
            continue
        q = qmap[qid]
        if key in done:
            rows.append(done[key])
            continue
        sig = signals(q, rec, banned)
        row = {"key": key, "group": q["group"], "question": q["question"], "signals": sig,
               "error": rec.get("error", ""), "judgement": None}
        if not args.no_judge and not quota_hit and not sig["empty_answer"]:
            text, err = run_claude(build_prompt(q, rec, sig), args.model, token, args.timeout)
            j = parse_judgement(text) if text else None
            if text and not j:  # 格式不對時重試一次
                text, err = run_claude(build_prompt(q, rec, sig), args.model, token, args.timeout)
                j = parse_judgement(text) if text else None
            if j:
                row["judgement"] = j
            else:
                row["judge_error"] = err or "評審輸出格式不符"
                if looks_like_quota(err):
                    quota_hit = True
            print(f"[{key}] " + (f"總分 {total(j)}/12 flags={j['flags']}" if j else f"評審失敗：{row['judge_error']}"))
        else:
            print(f"[{key}] 僅程式檢查" + ("（已因額度中止評審）" if quota_hit else ""))
        rows.append(row)
        with out_jsonl.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    meta = {"run_id": run_id, "results_file": results_path.name, "model": args.model}
    out_md.write_text(build_report(rows, meta, data["meta"]["groups"]), encoding="utf-8")
    print(f"\n報告：{out_md}\n明細：{out_jsonl}")
    if quota_hit:
        print("評審因額度或頻率限制中止，等額度恢復後重跑同一指令即可從中斷處繼續。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
