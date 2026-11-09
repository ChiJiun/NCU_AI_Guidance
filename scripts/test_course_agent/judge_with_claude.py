"""
judge_with_claude.py（v2）

對 test_rag.py 跑出的結果評分，分三層：
  1. 程式硬指標（不經 AI）：課名真實率、系所／學程被誤標成課、行為正確率（含 query 題的必要工具子指標）、
     精簡度（長度與標記課數）、穩定性（空白／錯誤、回應時間）
  2. AI 評審（claude -p）：主指標為檢查點達成率（逐條 met / not_met 並引用原文），
     輔助四面向各 0–2 分：切題、正確與誠實、高中生看得懂、引導探索
  3. 可信度：--passes 2 讓同一回答評兩次，報告兩次的一致率

評審透過 Claude Code 的無頭模式 `claude -p` 呼叫，使用 .env 的 CLAUDE_CODE_OAUTH_TOKEN
（claude setup-token 產生，僅限 Claude Code 使用，不可拿去直接呼叫 Anthropic API）。

執行方式：
  python scripts/test_course_agent/judge_with_claude.py                         # 評最新一份結果
  python scripts/test_course_agent/judge_with_claude.py --results data/test_results/xxx.json --passes 2
  python scripts/test_course_agent/judge_with_claude.py --ids A01,D03           # 只評指定題
  python scripts/test_course_agent/judge_with_claude.py --no-judge              # 只跑程式指標
輸出為 <run_id>_judge_v2.jsonl（逐次評審快取）、_judge_v2.md（報告）、_judge_v2_summary.json（彙總數字）。
程式指標每次重新計算；評審結果依（題號, 第幾次）快取，中斷或額度用完後重跑會自動略過已評完的部分。
"""

import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
RESULTS_DIR = ROOT / "data" / "test_results"
EVAL_PATH = ROOT / "docs" / "10-retrieval-evaluation" / "eval-set-v1.json"
COURSE_FILES = [ROOT / "data" / "processed" / "courses_deduped" / f for f in ("undergrad.json", "grad.json")]
GRAPH_PATH = ROOT / "data" / "processed" / "graph" / "knowledge_graph.json"
DEPT_PATH = ROOT / "data" / "processed" / "dept_college_map.json"
RULES_PATH = ROOT / "data" / "processed" / "curriculum_requirements_114.json"
ENV_PATH = ROOT / ".env"
TOKEN_VAR = "CLAUDE_CODE_OAUTH_TOKEN"
DEFAULT_JUDGE_MODEL = "claude-sonnet-5-5"
OUT_SUFFIX = "judge_v3"

DIMENSIONS = {
    "relevance": "切題",
    "honesty": "正確與誠實",
    "readable": "高中生看得懂",
    "guidance": "引導探索",
}
BEHAVIORS = {"query": "應查詢", "clarify": "應先追問", "correct_premise": "應指出前提／邊界"}
ERROR_FLAGS = ("hallucinated_course", "hallucinated_department", "unsupported_career_claim", "ignored_constraint")

ANSWER_TOO_LONG = 900       # 字
TOO_MANY_COURSES = 6        # 單題標記的不同課名數上限
TOOL_DATA_CHARS = 3000      # 提供給評審的工具回傳總長度上限
NAMES_PER_CALL = 40         # 每次工具呼叫最多列出幾個課名
EVIDENCE_CHARS = 9000       # 附給評審的課程資料總長度上限
RECORDS_PER_COURSE = 2      # 同名課程最多附幾個開課系所
RULES_CHARS = 3500          # 附給評審的系所畢業規定總長度上限

TAG_RE = re.compile(r"<course>(.*?)</course>", re.S)
BRACKET_RE = re.compile(r"[（(【\[［〔].*?[）)】\]］〕]")
QUOTE_RE = re.compile(r"[「」『』\"“”]")
TRAILING_NUM_RE = re.compile(r"(?:[IVX]+|[一二三])$")
DEPT_SUFFIX_RE = re.compile(r"(系|所|學程|學院)$")
# 結尾段落出現問號，或「你選一個／回我 A、B、C」這類請學生挑選的句型，視為有追問
ASK_RE = re.compile(r"[？?]|(你|妳)(先|可以)?(選|回|告訴|挑)|回我|選一個|你比較(想|喜歡|偏)|哪一(種|條|個|類|邊)")
# 出現這些句型之一，視為「有指出前提不成立或資料限制」（程式判定，粗略但可重現；AI 評審另有判定可對照）
PREMISE_CUES = tuple(re.compile(p) for p in (
    r"沒有.{0,8}(系|所|資料|對應|保證|客觀|排名|統計|證據|這類)",
    r"(無法|不能|沒辦法|不會)(保證|直接|判斷|推導|排名|比較出|提供|預測|告訴你哪)",
    r"(查不到|找不到|沒查到|不存在|並非|不代表|不一定|並不是|並不|不保證|不等於)",
    r"不是.{0,6}(一定|唯一|必須|只有|只在|浪費|不用|不需要|不能)",
    r"不是.{0,12}才(能|可以|適合)",
    r"(其實|仍然|還是)(需要|會用到|要用到|有).{0,6}數學",
))


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


def normalize_course_name(name: str) -> str:
    """NFKC、去括號內容、引號與空白、去結尾羅馬數字與一二三、臺→台。"""
    s = unicodedata.normalize("NFKC", name or "")
    s = QUOTE_RE.sub("", BRACKET_RE.sub("", s))
    s = re.sub(r"\s+", "", s)
    s = s.replace("臺", "台")
    prev = None
    while prev != s:  # 「物理化學實驗Ⅱ」「線性代數一」等，可能疊兩層
        prev = s
        s = TRAILING_NUM_RE.sub("", s) if len(s) > 1 else s
    return s


def load_known_courses(course_files=COURSE_FILES, graph_path=GRAPH_PATH) -> set[str]:
    """課程資料的「課程名稱(中文)」＋知識圖譜 Course 節點名稱，皆正規化。"""
    names: set[str] = set()
    for path in course_files:
        if path.exists():
            for c in json.loads(path.read_text(encoding="utf-8")):
                names.add(normalize_course_name(c.get("課程名稱(中文)", "")))
    if graph_path.exists():
        g = json.loads(graph_path.read_text(encoding="utf-8"))
        for n in g.get("nodes", []):
            if n.get("node_type") == "Course":
                names.add(normalize_course_name(n.get("name", "")))
    names.discard("")
    return names


def load_departments(path: Path = DEPT_PATH) -> list[str]:
    """中大系所／學位學程清單，提供給評審判斷 hallucinated_department。"""
    return sorted(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else []


# ── 第一層：程式硬指標 ────────────────────────────────────────────────────────

def check_required_tools(q: dict, rec: dict, banned: set[str]) -> dict:
    """原本的工具預期檢查；v2 只當 query 題的子指標。"""
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
        if not (t["allow_no_tool"] and not used):
            problems.append(f"未呼叫 any 清單中的任何工具：{', '.join(t['any'])}")
    for name in used & banned:
        problems.append(f"呼叫了已停用工具 {name}")
    return {"pass": not problems, "problems": problems}


def check_course_tags(answer: str, known: set[str]) -> dict:
    raw = [m.strip() for m in TAG_RE.findall(answer or "")]
    stripped = [re.sub(r"\s+", "", QUOTE_RE.sub("", BRACKET_RE.sub("", unicodedata.normalize("NFKC", r)))) for r in raw]
    dept_tags = sorted({s for s in stripped if s and DEPT_SUFFIX_RE.search(s)})
    names = [normalize_course_name(r) for r in raw]
    course_names = [n for n, s in zip(names, stripped) if n and s not in dept_tags]
    unique = sorted(set(course_names))
    unknown = sorted({r for r, n, s in zip(raw, names, stripped)
                      if n and s not in dept_tags and n not in known})
    return {
        "tags": len(raw),
        "course_tags": len(course_names),
        "found": sum(1 for n in course_names if n in known),
        "unknown": unknown,
        "unique_courses": len(unique),
        "dept_tags": dept_tags,
    }


def answer_tail(answer: str, lines: int = 4) -> str:
    rows = [r for r in (answer or "").strip().splitlines() if r.strip()]
    return "\n".join(rows[-lines:])


def observe_behavior(rec: dict, banned: set[str]) -> dict:
    answer = rec.get("answer", "") or ""
    tools = [c.get("tool") for c in rec.get("tool_calls") or [] if c.get("tool") not in banned]
    return {
        "tool_called": bool(tools) or bool(set(rec.get("tools_used") or []) - banned),
        "asks_question": bool(ASK_RE.search(answer_tail(answer))),
        "premise_cue": next((m.group(0) for c in PREMISE_CUES if (m := c.search(answer))), ""),
    }


def behavior_correct(q: dict, obs: dict, rec: dict) -> tuple[bool, str]:
    """實際行為是否符合 expected_behavior；回傳 (是否正確, 不正確的原因)。"""
    if rec.get("error") or not (rec.get("answer") or "").strip():
        return False, "空白或執行錯誤"
    eb = q["expected_behavior"]
    if eb == "query":
        return (True, "") if obs["tool_called"] else (False, "應查詢但沒有呼叫任何工具")
    if eb == "clarify":
        return (True, "") if obs["asks_question"] else (False, "應追問但結尾沒有提出問題")
    if not obs["premise_cue"]:
        return False, "沒有指出前提不成立或資料限制"
    if not q["tools"]["allow_no_tool"] and not obs["tool_called"]:
        return False, "指出了限制，但沒有先查證"
    return True, ""


def hard_signals(q: dict, rec: dict, banned: set[str], known: set[str]) -> dict:
    answer = rec.get("answer", "") or ""
    obs = observe_behavior(rec, banned)
    ok, why = behavior_correct(q, obs, rec)
    return {
        "expected_behavior": q["expected_behavior"],
        "observed": obs,
        "behavior_ok": ok,
        "behavior_problem": why,
        "required_tools": check_required_tools(q, rec, banned),
        "tags": check_course_tags(answer, known),
        "answer_chars": len(answer),
        "too_long": len(answer) > ANSWER_TOO_LONG,
        "empty_or_error": bool(rec.get("error")) or not answer.strip(),
        "elapsed_sec": rec.get("elapsed_sec"),
    }


# ── 第二層：AI 評審 ───────────────────────────────────────────────────────────

JUDGE_SYSTEM = """你是「大學選系輔導」的評審，同時扮演兩個角色：
(1) 一位高二學生：還不太懂大學，看到學分、先修、必修、學程這些詞會卡住；
(2) 一位嚴謹的輔導老師：不接受編造、不接受沒根據的保證。
你評的是「中央大學課程助理」對高中生提問的回答。回答長度與課程數量由程式另外計算，你不要因長短加減分。
只輸出一個 JSON 物件，不要有任何其他文字或 markdown 圍欄。"""

RUBRIC = """【評分步驟】
1. 檢查點：對【這題的檢查點】逐條判斷 met（達成）或 not_met（未達成），evidence 引用回答原文（20–60 字）；
   not_met 時若回答完全沒提到，evidence 寫「回答未提及」並用一句話說明缺什麼。
2. 四個輔助面向（每項 0/1/2，彼此不重疊）：
- relevance 切題：只看「有沒有回應學生真正問的事」。2=回應了問題的每個部分，學生點名的系所／課程／要求都有處理；1=回應了主要問題但漏掉一部分或偏題；0=答非所問或忽略主要問題。
- honesty 正確與誠實：只看「說的有沒有錯、有沒有編造、不確定時是否明說」。請對照【課程資料】：課程內容、學分、老師、必選修、年級限制與資料相符或是資料內容的合理白話轉述，都算有根據。2=沒有與資料矛盾、沒有編造課程或系所、沒有保證／排名／薪資等斷言，查不到時有明說；1=有一兩處與資料不符（例如把選修說成必修、學分或系所寫錯），或該說「查不到」卻含糊帶過；0=編造課程或系所、多處與資料矛盾，或做出無根據的保證／斷言。只要沒有找到矛盾、編造或斷言，就給 2；【課程資料】或【系所畢業規定】沒附到、因此無法核對的細節不是扣分理由（附上的只是部分資料），寫進 needs_human_check。回答比資料多做的一般性白話說明（例如「微積分用來描述變化」）不算延伸。
- readable 高中生看得懂：只看「措辭與講法」，不看長度。2=口語白話，學分、必修、先修、學程等新名詞第一次出現有解釋，先講學什麼再給課名；1=大致可讀，但有未解釋的術語或課表式段落；0=像課表或公文，高二學生看完仍不懂在說什麼。
- guidance 引導探索：只看「有沒有幫學生往下一步走」，不看長度。2=給出有區隔的方向或比較面向（純查詢題則是把答案講完整），不替學生做決定，結尾有一個具體、學生答得出來的追問或下一步；1=方向單一，或下一步空泛（如「有問題再問我」）；0=只推單一選項、替學生下結論，或完全沒有下一步。
3. behavior：asks_question=回答是否向學生提出問題以縮小範圍；corrects_premise=回答是否指出問題中的錯誤前提、保證要求或資料範圍限制（題目沒有這類前提時填 false）。
4. flags 只在有明確證據時標記，可用值：
- hallucinated_course：提到的課名在工具回傳中找不到，且明顯不像中大實際開的課
- hallucinated_department：提到中大不存在的系所，或把相近單位當成學生問的系所
- unsupported_career_claim：薪資、就業率、錄取分數、名額、涼課、老師評價、「適合什麼個性」等課程資料不可能有的斷言
- ignored_constraint：忽略學生明說的限制（例如只要大學部、不想讀資工、沒寫過程式）
5. 扣 honesty 分時，reasons 必須引用回答的哪一句，並指出它和【課程資料】或【系所畢業規定】的哪一處矛盾；說不出具體矛盾、只能說「沒附資料」「無法核對」時，honesty 給 2，並寫進 needs_human_check。

輸出 JSON 格式：
{
  "checks": [{"id": 1, "verdict": "met 或 not_met", "evidence": "引用原文或說明"}],
  "scores": {"relevance": 0-2, "honesty": 0-2, "readable": 0-2, "guidance": 0-2},
  "reasons": {"relevance": "一句話", "honesty": "一句話", "readable": "一句話", "guidance": "一句話"},
  "behavior": {"asks_question": true/false, "corrects_premise": true/false},
  "flags": [],
  "needs_human_check": ["無法從現有資訊判斷、需要人工對照的地方"]
}"""

TOOL_DATA_NOTE = ("（結果檔只保留每次工具呼叫的參數、筆數與回傳的課名清單；"
                  "回答中提到的課程，其描述、學分、老師等內容另見下方【課程資料】。）")
EVIDENCE_NOTE = ("（評測程式依回答中提到的課名，從中大課程資料查出的原始資訊，和助理當時查到的資料同源；"
                 "同名課程只附最相關的開課系所，內容有截斷。）")


def format_tool_data(rec: dict, limit: int = TOOL_DATA_CHARS) -> list[str]:
    calls = rec.get("tool_calls") or []
    if not calls:
        return ["- （沒有呼叫任何工具）"]
    out, used = [], 0
    for c in calls:
        n = c.get("count")
        names = c.get("coursesFound") or []
        head = f"- {c.get('tool')}({json.dumps(c.get('args', {}), ensure_ascii=False)})"
        head += f" → {n} 筆" if isinstance(n, int) else " →（此工具未回報筆數，不代表查無資料）"
        shown = names[:NAMES_PER_CALL]
        body = f"：{'、'.join(shown)}" + (f"…（另有 {len(names) - len(shown)} 個）" if len(names) > len(shown) else "") if names else ""
        line = head + body
        if used + len(line) > limit:
            out.append(f"- …（其餘 {len(calls) - len(out)} 次呼叫因長度省略）")
            break
        out.append(line)
        used += len(line)
    return out


def _clip(text, n: int) -> str:
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    return t if len(t) <= n else t[:n] + "…"


GRADE_RE = re.compile(r"年級:限[^。']*")


def load_course_details(course_files=COURSE_FILES) -> dict[str, list[dict]]:
    """{正規化課名: [精簡的開課紀錄, ...]}，同系所同課名只留最新一筆。"""
    best: dict[tuple[str, str], dict] = {}
    for path in course_files:
        if not path.exists():
            continue
        for c in json.loads(path.read_text(encoding="utf-8")):
            name = c.get("課程名稱(中文)", "")
            norm = normalize_course_name(name)
            if not norm:
                continue
            g = c.get("課程綱要") if isinstance(c.get("課程綱要"), dict) else {}
            sem = str(g.get("學期") or f"{c.get('學年度', '')}{c.get('學期', '')}")
            item = {
                "name": name, "dept": c.get("系所", ""), "semester": sem,
                "credits": c.get("學分", ""), "type": c.get("選修別", ""),
                "teachers": "、".join(t for t in str(c.get("授課教師", "")).split() if t),
                "grade": "；".join(sorted(set(GRADE_RE.findall(str(c.get("分發條件", "")))))[:2]),
                "goal": g.get("課程目標", ""), "content": g.get("授課內容", ""),
                "field": g.get("課程領域", ""),
            }
            k = (norm, item["dept"])
            if k not in best or sem > best[k]["semester"]:
                best[k] = item
    out: dict[str, list[dict]] = defaultdict(list)
    for (norm, _), item in best.items():
        out[norm].append(item)
    return dict(out)


def _squash(name: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(name))).replace("臺", "台")


def mentioned_courses(rec: dict, details: dict[str, list[dict]]) -> list[str]:
    """回答中提到的課（<course> 標記，以及工具回傳且出現在回答原文的課名），保留原寫法、依出現順序。

    同一門課的不同寫法（如「工程數學 Ｉ」「工程數學Ⅱ」）分開保留，才能各自附上對的那一筆。"""
    answer = rec.get("answer", "") or ""
    found: dict[str, tuple[int, str]] = {}
    cands = [(m.start(), m.group(1).strip()) for m in TAG_RE.finditer(answer)]
    for c in rec.get("tool_calls") or []:
        for raw in c.get("coursesFound") or []:
            pos = answer.find(str(raw).strip())
            if pos >= 0:
                cands.append((pos, str(raw).strip()))
    for pos, raw in cands:
        if normalize_course_name(raw) in details:
            k = _squash(raw)
            if k not in found or pos < found[k][0]:
                found[k] = (pos, raw)
    return [raw for pos, raw in sorted(found.values())]


def format_course_evidence(rec: dict, details: dict[str, list[dict]], limit: int = EVIDENCE_CHARS) -> list[str]:
    names = mentioned_courses(rec, details)
    if not names:
        return ["- （回答中沒有可對照的課程）"]
    answer = rec.get("answer", "") or ""
    context = answer + json.dumps([c.get("args", {}) for c in rec.get("tool_calls") or []], ensure_ascii=False)
    out, used = [], 0
    shown: set[tuple[str, str]] = set()
    for i, raw in enumerate(names):
        pool = details[normalize_course_name(raw)]
        exact = [r for r in pool if _squash(r["name"]) == _squash(raw)] or pool
        hit = [r for r in exact if r["dept"] and r["dept"] in context]
        recs = (hit or sorted(exact, key=lambda r: r["semester"], reverse=True))[:RECORDS_PER_COURSE]
        for r in recs:
            if (r["name"], r["dept"]) in shown:
                continue
            shown.add((r["name"], r["dept"]))
            parts = [f"{r['name']}｜{r['dept']}｜{r['credits']} 學分｜{r['type']}"]
            if r["teachers"]:
                parts.append(f"老師：{r['teachers']}")
            if r["grade"]:
                parts.append(r["grade"])
            if r["field"]:
                parts.append(f"領域：{_clip(r['field'], 30)}")
            if r["goal"]:
                parts.append(f"目標：{_clip(r['goal'], 160)}")
            if r["content"]:
                parts.append(f"內容：{_clip(r['content'], 260)}")
            line = "- " + "｜".join(parts)
            if used + len(line) > limit:
                out.append(f"- …（其餘 {len(names) - i} 門課因長度省略）")
                return out
            out.append(line)
            used += len(line)
    return out


def load_dept_rules(path: Path = RULES_PATH) -> dict[str, dict]:
    """{系所名稱: 114 學年畢業規定}，給評審核對學分數、必修課與修課年級。"""
    if not path.exists():
        return {}
    out = {}
    for col in json.loads(path.read_text(encoding="utf-8")).get("colleges", []):
        for d in col.get("departments", []):
            out[d["name"]] = d
    return out


def format_dept_rules(rec: dict, rules: dict[str, dict], limit: int = RULES_CHARS) -> list[str]:
    answer = rec.get("answer", "") or ""
    args = json.dumps([c.get("args", {}) for c in rec.get("tool_calls") or []], ensure_ascii=False)
    hits = sorted((answer.find(n) if n in answer else len(answer) + args.find(n), n)
                  for n in rules if n in answer or n in args)
    if not hits:
        return []
    out, used = [], 0
    for i, (_, name) in enumerate(hits):
        d = rules[name]
        rules_txt = "；".join(r.get("description", "") for r in d.get("graduation_rules", []) if r.get("description"))
        req = "、".join(f"{c['name']}（{c.get('when', '')}）" for c in d.get("required_courses", []))
        line = f"- {name}：{_clip(rules_txt, 500)}" + (f"｜系訂必修：{_clip(req, 700)}" if req else "")
        if used + len(line) > limit:
            out.append(f"- …（其餘 {len(hits) - i} 個系所因長度省略）")
            break
        out.append(line)
        used += len(line)
    return out


def build_prompt(q: dict, rec: dict, hard: dict, departments: list[str] | None = None,
                 details: dict[str, list[dict]] | None = None, rules: dict[str, dict] | None = None) -> str:
    rule_lines = format_dept_rules(rec, rules) if rules else []
    dept_line = (["【中大系所與學位學程清單（判斷 hallucinated_department 用；學院學士班、研究所也是實際單位）】",
                  "、".join(departments), ""] if departments else [])
    return "\n".join([
        RUBRIC, "",
        f"【題號】{q['id']}　【意圖】{'、'.join(q['intent'])}　【預期行為】{BEHAVIORS[q['expected_behavior']]}",
        f"【高中生的問題】{q['question']}", "",
        "【這題的檢查點】", *[f"{i}. {c}" for i, c in enumerate(q["checks"], 1)], "",
        f"【這題要特別留意的錯誤】{'、'.join(q['watch_flags']) or '無'}", "",
        "【助理呼叫的工具與回傳的課名】" + TOOL_DATA_NOTE, *format_tool_data(rec), "",
        *(["【課程資料】" + EVIDENCE_NOTE, *format_course_evidence(rec, details), ""] if details is not None else []),
        *(["【系所畢業規定】（114 學年；回答或工具參數中出現的系所）", *rule_lines, ""] if rule_lines else []),
        *dept_line,
        "【程式檢查】",
        f"- 回答中標記的課名在中大課程資料查不到的：{'、'.join(hard['tags']['unknown']) or '無'}（可能是課名寫法不同，需你判斷）",
        "",
        "【助理的回答】", rec.get("answer", "") or "（空白）", "",
        "請依步驟評分並只輸出 JSON。",
    ])


def run_claude(prompt: str, model: str, token: str, timeout: int) -> tuple[str | None, str, str]:
    """回傳 (文字結果, 錯誤訊息, 實際使用的模型)。實際模型取自 claude 回報的 modelUsage。"""
    exe = shutil.which("claude")
    if not exe:
        return None, "找不到 claude 指令", ""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # 確保走訂閱而非 API 計費
    env[TOKEN_VAR] = token
    cmd = [exe, "-p", "--tools", "", "--system-prompt", JUDGE_SYSTEM,
           "--output-format", "json", "--no-session-persistence", "--model", model]
    try:
        proc = subprocess.run(cmd, input=prompt.encode("utf-8"), capture_output=True,
                              env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "timeout", ""
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    err = proc.stderr.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        return None, (err or out)[:300], ""
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        return None, f"輸出不是 JSON：{out[:200]}", ""
    used = ",".join(sorted((payload.get("modelUsage") or {}).keys()))
    if payload.get("is_error"):
        return None, str(payload.get("result", ""))[:300], used
    return payload.get("result", ""), "", used


def parse_judgement(text: str, n_checks: int) -> dict | None:
    start = (text or "").find("{")
    if start < 0:
        return None
    try:
        # 只解析第一個完整的 JSON 物件；評審偶爾會在後面多附說明文字（其中可能還有大括號）
        j, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return None
    if not isinstance(j, dict):
        return None
    scores = j.get("scores")
    if not isinstance(scores, dict) or set(scores) != set(DIMENSIONS) or any(scores[k] not in (0, 1, 2) for k in scores):
        return None
    checks = j.get("checks")
    if not isinstance(checks, list) or len(checks) != n_checks:
        return None
    norm = []
    for i, c in enumerate(checks, 1):
        if not isinstance(c, dict) or c.get("verdict") not in ("met", "not_met"):
            return None
        norm.append({"id": i, "verdict": c["verdict"], "evidence": str(c.get("evidence", ""))})
    j["checks"] = norm
    raw_flags = j.get("flags")
    j["flags"] = sorted({f for f in (raw_flags if isinstance(raw_flags, list) else []) if f in ERROR_FLAGS})
    if not isinstance(j.get("reasons"), dict):
        j["reasons"] = {}
    b = j.get("behavior") if isinstance(j.get("behavior"), dict) else {}
    j["behavior"] = {"asks_question": bool(b.get("asks_question")), "corrects_premise": bool(b.get("corrects_premise"))}
    check = j.get("needs_human_check")
    j["needs_human_check"] = [str(x) for x in check] if isinstance(check, list) else ([str(check)] if check else [])
    return j


def looks_like_quota(msg: str) -> bool:
    m = (msg or "").lower()
    return any(w in m for w in ("limit", "quota", "rate", "usage", "429", "overloaded"))


def judge_once(prompt: str, n_checks: int, model: str, token: str, timeout: int) -> dict:
    text, err, used = run_claude(prompt, model, token, timeout)
    j = parse_judgement(text, n_checks) if text else None
    if text and not j:  # 格式不對時重試一次
        text, err, used = run_claude(prompt, model, token, timeout)
        j = parse_judgement(text, n_checks) if text else None
    if j:
        return {"judgement": j, "judge_model": used}
    return {"judgement": None, "judge_model": used, "judge_error": err or "評審輸出格式不符"}


# ── 彙總 ──────────────────────────────────────────────────────────────────────

def aux_total(j: dict) -> int:
    return sum(j["scores"].values())


def check_rate(j: dict) -> float:
    return sum(c["verdict"] == "met" for c in j["checks"]) / len(j["checks"]) if j["checks"] else 0.0


def _pct(a: int, b: int) -> float | None:
    return round(100 * a / b, 1) if b else None


def row_score(row: dict) -> float | None:
    """單題綜合分（用於排序與抽樣）：檢查點達成率為主，四面向總分為次。"""
    js = row["judgements"]
    if not js:
        return None
    return statistics.mean(check_rate(j) for j in js) * 100 + statistics.mean(aux_total(j) for j in js) / 8


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    tags = [r["hard"]["tags"] for r in rows]
    course_tags = sum(t["course_tags"] for t in tags)
    found = sum(t["found"] for t in tags)
    by_beh: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_beh[r["hard"]["expected_behavior"]].append(r)
    query_rows = by_beh.get("query", [])
    elapsed = [r["hard"]["elapsed_sec"] for r in rows if isinstance(r["hard"]["elapsed_sec"], (int, float))]
    hard = {
        "questions": n,
        "course_tags": course_tags,
        "course_found": found,
        "course_real_rate": _pct(found, course_tags),
        "unknown_course_names": sum(len(t["unknown"]) for t in tags),
        "dept_tags": sum(len(t["dept_tags"]) for t in tags),
        "behavior_ok": sum(r["hard"]["behavior_ok"] for r in rows),
        "behavior_rate": _pct(sum(r["hard"]["behavior_ok"] for r in rows), n),
        "behavior_by_type": {k: {"n": len(v), "ok": sum(r["hard"]["behavior_ok"] for r in v)} for k, v in by_beh.items()},
        "query_required_tools_ok": sum(r["hard"]["required_tools"]["pass"] for r in query_rows),
        "query_questions": len(query_rows),
        "too_long": sum(r["hard"]["too_long"] for r in rows),
        "too_many_courses": sum(t["unique_courses"] > TOO_MANY_COURSES for t in tags),
        "mean_chars": round(statistics.mean(r["hard"]["answer_chars"] for r in rows), 1) if rows else None,
        "empty_or_error": sum(r["hard"]["empty_or_error"] for r in rows),
        "median_elapsed_sec": round(statistics.median(elapsed), 2) if elapsed else None,
    }

    judged = [(r, j) for r in rows for j in r["judgements"]]
    ai: dict = {"judged_questions": sum(1 for r in rows if r["judgements"]), "judgements": len(judged)}
    if judged:
        items = [c for _, j in judged for c in j["checks"]]
        ai["check_items"] = len(items)
        ai["check_rate"] = _pct(sum(c["verdict"] == "met" for c in items), len(items))
        ai["dims"] = {k: round(statistics.mean(j["scores"][k] for _, j in judged), 2) for k in DIMENSIONS}
        ai["aux_total"] = round(statistics.mean(aux_total(j) for _, j in judged), 2)
        by_group: dict[str, list] = defaultdict(list)
        for r, j in judged:
            by_group[r["group"]].append(j)
        ai["by_group"] = {g: {"check_rate": _pct(sum(c["verdict"] == "met" for j in js for c in j["checks"]),
                                                 sum(len(j["checks"]) for j in js)),
                              "aux_total": round(statistics.mean(aux_total(j) for j in js), 2)}
                          for g, js in sorted(by_group.items())}
        any_flag: Counter = Counter()
        all_flag: Counter = Counter()
        for r in rows:
            if r["judgements"]:
                sets = [set(j["flags"]) for j in r["judgements"]]
                any_flag.update(set.union(*sets))
                all_flag.update(set.intersection(*sets))
        ai["flags_any_pass"] = dict(any_flag.most_common())
        ai["flags_all_passes"] = dict(all_flag.most_common())
        # AI 判定的「有指出前提」與程式關鍵詞判定的對照（只看 correct_premise 題）
        prem = [(r, j) for r, j in judged if r["hard"]["expected_behavior"] == "correct_premise"]
        if prem:
            ai["premise_ai_vs_program_agree"] = _pct(
                sum(j["behavior"]["corrects_premise"] == bool(r["hard"]["observed"]["premise_cue"]) for r, j in prem), len(prem))

    multi = [r for r in rows if len(r["judgements"]) >= 2]
    rel: dict = {"paired_questions": len(multi)}
    if multi:
        a = [r["judgements"][0] for r in multi]
        b = [r["judgements"][1] for r in multi]
        diffs = [abs(aux_total(x) - aux_total(y)) for x, y in zip(a, b)]
        rel["aux_exact"] = _pct(sum(d == 0 for d in diffs), len(diffs))
        rel["aux_within_1"] = _pct(sum(d <= 1 for d in diffs), len(diffs))
        rel["dim_exact"] = {k: _pct(sum(x["scores"][k] == y["scores"][k] for x, y in zip(a, b)), len(a)) for k in DIMENSIONS}
        pairs = [(cx["verdict"], cy["verdict"]) for x, y in zip(a, b) for cx, cy in zip(x["checks"], y["checks"])]
        rel["check_items"] = len(pairs)
        rel["check_agree"] = _pct(sum(p == q for p, q in pairs), len(pairs))
        rel["flags_agree"] = _pct(sum(set(x["flags"]) == set(y["flags"]) for x, y in zip(a, b)), len(a))
        rel["disagreements"] = [
            {"key": r["key"], "aux": [aux_total(x), aux_total(y)],
             "checks": [[c["verdict"] for c in x["checks"]], [c["verdict"] for c in y["checks"]]]}
            for r, x, y in zip(multi, a, b)
            if abs(aux_total(x) - aux_total(y)) > 1 or [c["verdict"] for c in x["checks"]] != [c["verdict"] for c in y["checks"]]
        ]
    return {"hard": hard, "ai": ai, "reliability": rel}


# ── 報告 ──────────────────────────────────────────────────────────────────────

def _fmt(v, suffix="") -> str:
    return "—" if v is None else f"{v}{suffix}"


def build_report(rows: list[dict], meta: dict, groups: dict) -> str:
    s = summarize(rows)
    h, ai, rel = s["hard"], s["ai"], s["reliability"]
    used_models = Counter(m or "（未記錄）" for r in rows for m in r["judge_models"])
    lines = [f"# 評測結果 {meta['run_id']}（評分 v2）", "",
             f"- 結果檔：`{meta['results_file']}`　評測集：`{meta['eval_file']}`",
             f"- 指定評審模型：`{meta['model']}`　每題評審次數：{meta['passes']}",
             "- 實際使用的評審模型：" + ("、".join(f"`{m}` ×{n}" for m, n in used_models.most_common()) or "（未評審）"),
             f"- 共 {h['questions']} 題，已由 AI 評審 {ai['judged_questions']} 題（{ai['judgements']} 次）", "",
             "> 評審只看得到工具回傳的課名清單與筆數，看不到課程描述、學分與規定原文；這些細節的對錯仍需人工抽查。", ""]
    if len(used_models) > 1:
        lines += ["> ⚠️ 這份報告混用了多個評審模型（或有未記錄的紀錄），分數不宜直接和其他報告比較。", ""]

    # 第一層
    lines += ["## 第一層：程式硬指標（不經 AI）", "",
              "| 指標 | 數值 |", "|---|---|",
              f"| 課名真實率（標記課名能在課程資料或知識圖譜找到） | {_fmt(h['course_real_rate'], '%')}（{h['course_found']}/{h['course_tags']}） |",
              f"| 查不到的課名（人次） | {h['unknown_course_names']} |",
              f"| 系所／學程被誤標成課 | {h['dept_tags']} |",
              f"| 行為正確率 | {_fmt(h['behavior_rate'], '%')}（{h['behavior_ok']}/{h['questions']}） |"]
    for k, v in h["behavior_by_type"].items():
        lines.append(f"| 　└ {BEHAVIORS[k]} | {v['ok']}/{v['n']} |")
    lines += [f"| 　└ query 題必要工具全數呼叫（子指標） | {h['query_required_tools_ok']}/{h['query_questions']} |",
              f"| 回答超過 {ANSWER_TOO_LONG} 字 | {h['too_long']} 題（平均 {h['mean_chars']} 字） |",
              f"| 單題標記超過 {TOO_MANY_COURSES} 門課 | {h['too_many_courses']} 題 |",
              f"| 空白或執行錯誤 | {h['empty_or_error']} 題 |",
              f"| 回應時間中位數 | {_fmt(h['median_elapsed_sec'], ' 秒')} |", ""]
    bad = [r for r in rows if not r["hard"]["behavior_ok"]]
    if bad:
        lines += ["### 行為不符預期", "", "| 題號 | 預期 | 實際 | 原因 |", "|---|---|---|---|"]
        for r in bad:
            o = r["hard"]["observed"]
            act = f"{'有' if o['tool_called'] else '未'}呼叫工具、結尾{'有' if o['asks_question'] else '未'}追問"
            lines.append(f"| {r['key']} | {BEHAVIORS[r['hard']['expected_behavior']]} | {act} | {r['hard']['behavior_problem']} |")
        lines.append("")
    tool_fail = [r for r in rows if r["hard"]["expected_behavior"] == "query" and not r["hard"]["required_tools"]["pass"]]
    if tool_fail:
        lines += ["### query 題必要工具未全數呼叫（子指標）", "", "| 題號 | 原因 |", "|---|---|"]
        lines += [f"| {r['key']} | {'；'.join(r['hard']['required_tools']['problems'])} |" for r in tool_fail]
        lines.append("")
    unknown = [r for r in rows if r["hard"]["tags"]["unknown"]]
    if unknown:
        lines += ["### 課程資料查不到的課名（請人工確認是否為寫法差異或編造）", "", "| 題號 | 課名 |", "|---|---|"]
        lines += [f"| {r['key']} | {'、'.join(r['hard']['tags']['unknown'])} |" for r in unknown]
        lines.append("")
    depts = [r for r in rows if r["hard"]["tags"]["dept_tags"]]
    if depts:
        lines += ["### 被標成課的系所／學程", ""]
        lines += [f"- {r['key']}：{'、'.join(r['hard']['tags']['dept_tags'])}" for r in depts]
        lines.append("")

    # 第二層
    if ai["judgements"]:
        lines += ["## 第二層：AI 評審", "",
                  f"- **檢查點達成率（主指標）：{ai['check_rate']}%**（{ai['check_items']} 個判定）",
                  f"- 輔助四面向平均總分：{ai['aux_total']} / 8", "",
                  "| 面向 | 平均（0–2） |", "|---|---|"]
        lines += [f"| {name} | {ai['dims'][k]} |" for k, name in DIMENSIONS.items()]
        lines += ["", "### 各類別", "", "| 類別 | 檢查點達成率 | 四面向平均 |", "|---|---|---|"]
        lines += [f"| {g}. {groups.get(g, '')} | {v['check_rate']}% | {v['aux_total']} |" for g, v in ai["by_group"].items()]
        lines += ["", "### 錯誤標記（題數）", "", "| 標記 | 任一次評審標記 | 每次評審都標記 |", "|---|---|---|"]
        for f in ERROR_FLAGS:
            lines.append(f"| `{f}` | {ai['flags_any_pass'].get(f, 0)} | {ai['flags_all_passes'].get(f, 0)} |")
        if "premise_ai_vs_program_agree" in ai:
            lines += ["", f"- correct_premise 題中，AI 判定「有指出前提」與程式關鍵詞判定一致：{ai['premise_ai_vs_program_agree']}%"]
        ranked = sorted((r for r in rows if r["judgements"]), key=row_score)
        lines += ["", "### 綜合分最低的 10 題（優先看）", "",
                  "| 題號 | 檢查點達成 | 四面向 | 未達成的檢查點 |", "|---|---|---|---|"]
        for r in ranked[:10]:
            j = r["judgements"][0]
            miss = [f"{c['id']}. {r['checks'][c['id'] - 1]}" for c in j["checks"] if c["verdict"] == "not_met"]
            rate = statistics.mean(check_rate(x) for x in r["judgements"])
            aux = statistics.mean(aux_total(x) for x in r["judgements"])
            lines.append(f"| {r['key']} | {rate:.0%} | {aux:.1f} | {'；'.join(miss) or '—'} |")
        need = [r for r in rows if any(j["needs_human_check"] for j in r["judgements"])]
        if need:
            lines += ["", "### 評審標示需人工對照的項目（第 1 次評審）", ""]
            for r in need:
                items = r["judgements"][0]["needs_human_check"]
                if items:
                    lines.append(f"- **{r['key']}**：" + "；".join(items))
        lines.append("")

    # 第三層
    if rel["paired_questions"]:
        lines += ["## 第三層：評審可信度（同一回答評兩次）", "",
                  "| 指標 | 一致率 |", "|---|---|",
                  f"| 四面向總分完全一致 | {rel['aux_exact']}% |",
                  f"| 四面向總分差 1 分內 | {rel['aux_within_1']}% |"]
        lines += [f"| 　└ {name} 完全一致 | {rel['dim_exact'][k]}% |" for k, name in DIMENSIONS.items()]
        lines += [f"| 檢查點判定一致（{rel['check_items']} 個） | {rel['check_agree']}% |",
                  f"| 錯誤標記完全相同 | {rel['flags_agree']}% |", ""]
        if rel["disagreements"]:
            lines += ["### 兩次評審分歧較大的題目（總分差 >1 或檢查點判定不同）", "",
                      "| 題號 | 四面向總分 | 檢查點判定（第 1 次 / 第 2 次） |", "|---|---|---|"]
            for d in rel["disagreements"]:
                c1 = "".join("✓" if v == "met" else "✗" for v in d["checks"][0])
                c2 = "".join("✓" if v == "met" else "✗" for v in d["checks"][1])
                lines.append(f"| {d['key']} | {d['aux'][0]} / {d['aux'][1]} | {c1} / {c2} |")
            lines.append("")
    elif meta["passes"] < 2 and ai["judgements"]:
        lines += ["## 第三層：評審可信度", "", "- 本次只評一次；加上 `--passes 2` 才能計算一致率。", ""]

    missing = [r for r in rows if len(r["judgements"]) < meta["passes"] and not meta["no_judge"]]
    if missing:
        lines += ["## 未完成評審", "",
                  "、".join(f"{r['key']}（{'；'.join(r['judge_errors']) or '未執行'}）" for r in missing), ""]
    return "\n".join(lines)


# ── 主流程 ────────────────────────────────────────────────────────────────────

def load_cache(path: Path) -> dict[tuple[str, int], dict]:
    done: dict[tuple[str, int], dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("judgement"):
                    done[(row["key"], row["pass"])] = row
    return done


def main() -> int:
    ap = argparse.ArgumentParser(description="用 claude -p 為 test_rag 結果評分（v2：程式指標＋檢查點＋一致率）")
    ap.add_argument("--results", default=None, help="test_rag.py 的結果 json（預設最新一份）")
    ap.add_argument("--eval", default=str(EVAL_PATH), help="評測集 json")
    ap.add_argument("--ids", default=None, help="只評指定題號，逗號分隔，例如 A01,D03")
    ap.add_argument("--model", default=DEFAULT_JUDGE_MODEL,
                    help=f"評審模型，預設鎖定完整型號 {DEFAULT_JUDGE_MODEL}（別名如 sonnet 會隨 Claude Code 更新而改變）")
    ap.add_argument("--passes", type=int, default=1, help="同一回答評幾次（2 次才能算一致率）")
    ap.add_argument("--workers", type=int, default=4, help="同時進行的評審數")
    ap.add_argument("--timeout", type=int, default=240, help="每次評審逾時秒數")
    ap.add_argument("--out-dir", default=str(RESULTS_DIR), help="輸出資料夾")
    ap.add_argument("--no-judge", action="store_true", help="只跑程式指標，不呼叫 claude")
    args = ap.parse_args()

    results_path = Path(args.results) if args.results else latest_results()
    results = json.loads(results_path.read_text(encoding="utf-8"))["results"]
    data = json.loads(Path(args.eval).read_text(encoding="utf-8"))
    qmap = {q["id"]: q for q in data["questions"]}
    banned = set(data["meta"]["tools_must_not_call"])
    known = load_known_courses()
    departments = load_departments()
    details = load_course_details()
    rules = load_dept_rules()
    if not known:
        print("⚠️ 找不到課程資料或知識圖譜，課名真實率將全部視為查不到")

    token = None
    if not args.no_judge:
        token = load_token()
        if not token:
            sys.exit(f"找不到 {TOKEN_VAR}：請在 .env 填入 claude setup-token 產生的 token，或改用 --no-judge")

    run_id = results_path.stem
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_jsonl = out_dir / f"{run_id}_{OUT_SUFFIX}.jsonl"
    out_md = out_dir / f"{run_id}_{OUT_SUFFIX}.md"
    out_summary = out_dir / f"{run_id}_{OUT_SUFFIX}_summary.json"
    cache = load_cache(out_jsonl)

    wanted = {x.strip() for x in args.ids.split(",")} if args.ids else None
    rows: list[dict] = []
    prompts: dict[str, tuple[str, int]] = {}
    for key, rec in index_records(results):
        qid = rec["category"]
        if qid not in qmap or (wanted and qid not in wanted):
            continue
        q = qmap[qid]
        hard = hard_signals(q, rec, banned, known)
        rows.append({"key": key, "qid": qid, "group": q["group"], "question": q["question"],
                     "checks": q["checks"], "hard": hard, "judgements": [], "judge_models": [], "judge_errors": []})
        if not hard["empty_or_error"]:
            prompts[key] = (build_prompt(q, rec, hard, departments, details, rules), len(q["checks"]))

    todo = [(k, p) for k in prompts for p in range(1, args.passes + 1) if (k, p) not in cache]
    if not args.no_judge and todo:
        print(f"需評審 {len(todo)} 次（已快取 {sum(1 for k in prompts for p in range(1, args.passes + 1) if (k, p) in cache)} 次）")
        quota_hit = False
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool, out_jsonl.open("a", encoding="utf-8") as f:
            futures = {}
            pending = iter(todo)

            def submit_next() -> bool:
                nxt = next(pending, None)
                if nxt is None:
                    return False
                k, p = nxt
                futures[pool.submit(judge_once, prompts[k][0], prompts[k][1], args.model, token, args.timeout)] = (k, p)
                return True

            for _ in range(max(1, args.workers)):
                submit_next()
            while futures:
                fut = next(as_completed(futures))
                k, p = futures.pop(fut)
                res = fut.result()
                row = {"key": k, "pass": p, **res}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                if res["judgement"]:
                    cache[(k, p)] = row
                    j = res["judgement"]
                    print(f"[{k} #{p}] 檢查點 {check_rate(j):.0%}　四面向 {aux_total(j)}/8　flags={j['flags']}")
                else:
                    print(f"[{k} #{p}] 評審失敗：{res['judge_error']}")
                    if looks_like_quota(res["judge_error"]):
                        quota_hit = True
                if not quota_hit:
                    submit_next()
        if quota_hit:
            print("評審因額度或頻率限制中止，等額度恢復後重跑同一指令即可從中斷處繼續。")

    failures: dict[str, list[str]] = defaultdict(list)
    if out_jsonl.exists():
        for line in out_jsonl.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                if not r.get("judgement") and (r["key"], r["pass"]) not in cache:
                    failures[r["key"]].append(r.get("judge_error", ""))
    for row in rows:
        for p in range(1, args.passes + 1):
            hit = cache.get((row["key"], p))
            if hit:
                row["judgements"].append(hit["judgement"])
                row["judge_models"].append(hit.get("judge_model", ""))
        row["judge_errors"] = sorted(set(failures.get(row["key"], [])))[:2]

    meta = {"run_id": run_id, "results_file": results_path.name, "eval_file": Path(args.eval).name,
            "model": args.model, "passes": args.passes, "no_judge": args.no_judge}
    out_md.write_text(build_report(rows, meta, data["meta"]["groups"]), encoding="utf-8")
    summary = summarize(rows)
    summary["meta"] = meta
    summary["per_question"] = [
        {"key": r["key"], "group": r["group"], "behavior_ok": r["hard"]["behavior_ok"],
         "unknown_courses": r["hard"]["tags"]["unknown"], "score": row_score(r)} for r in rows]
    out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n報告：{out_md}\n明細：{out_jsonl}\n彙總：{out_summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
