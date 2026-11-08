"""
build_glossary.py — 課程助理用的「名詞白話詞庫」

為什麼要另外做一份：
  nlp_simplified_concepts.json 是當初用本地 Qwen3-14B「逐課」改寫的，同一個詞在不同課的說明
  各不相同（出現 3 次以上的詞 99% 說法不一致），也沒有合併別名（神經網絡／神經網路）。
  課程助理要的是「一個詞一個說明」，讓後端能在回答裡自動附上白話說明，而不是讓模型自己解釋。

兩層：
  core     出現在 >=3 門課的詞 + 指定必收的詞：用 Claude 重寫（只解釋詞義，與課程無關）
  fallback 其餘的詞：不用 LLM，沿用舊說明中最常見的一種，並合併別名

流程（每一步都可單獨重跑）：
  python scripts/nlp/build_glossary.py candidates            # 統計並寫出候選清單
  python scripts/nlp/build_glossary.py generate --sample 30  # 小量試跑（等距抽樣）
  python scripts/nlp/build_glossary.py generate              # 產生全部 core（可中斷續跑）
  python scripts/nlp/build_glossary.py check                 # 自動品質檢查
  python scripts/nlp/build_glossary.py assemble              # 組合成 concept_glossary.json

Claude 透過 `claude -p` 呼叫，使用 .env 的 CLAUDE_CODE_OAUTH_TOKEN（claude setup-token 產生，僅限 Claude Code）。
產出是 AI 衍生內容，meta 會記錄模型、日期與來源，畫面上也應標示「白話說明由 AI 整理」。
"""

import argparse
import collections
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
NLP_DIR = ROOT / "data" / "processed" / "nlp"
IN_PATH = NLP_DIR / "nlp_simplified_concepts.json"
COURSE_INDEX = ROOT / "data" / "processed" / "course_index.json"
WORK_DIR = NLP_DIR / "glossary_work"
CANDIDATES_PATH = WORK_DIR / "core_candidates.json"
GENERATED_PATH = WORK_DIR / "core_generated.jsonl"
OUT_PATH = NLP_DIR / "concept_glossary.json"
ENV_PATH = ROOT / ".env"

TOKEN_VAR = "CLAUDE_CODE_OAUTH_TOKEN"
MODEL = "claude-sonnet-5-5"
STYLE_VERSION = 1

CORE_MIN_COURSES = 3          # 至少出現在幾門課才算 core
TERM_MIN_LEN, TERM_MAX_LEN = 2, 11   # core 詞長；更長的多半是短句
GLOSS_MIN_LEN, GLOSS_MAX_LEN = 6, 28   # 指示 Claude 寫 10–24 字，驗證留一點寬容
BATCH_SIZE = 10
HS_LINK_RE = re.compile(r"^高中[^：:]{1,6}[：:].{1,12}$")

# 評測中學生看不懂、評審點名過的詞；即使資料裡出現不到 3 次（甚至沒有）也要收
FORCED_TERMS = [
    "馬可夫鏈", "中央極限定理", "隨機變數", "單元操作", "輸送現象", "熱力學", "卷積神經網路",
    "OpenCV", "數值預報", "資料前處理", "分群", "神經網路", "機率論", "音韻學", "句法", "語料庫",
    "動態規劃", "NP完備性", "微分方程", "線性代數",
]

# 簡體專用字（只列常見者）：詞庫必須是繁體
SIMPLIFIED_ONLY = set(
    "这说习数据术种网络层级关线计设认为发现实际应对时间题开门学们过还进与动经济"
    "将从来调试观测体验处联统称两机质组织场边应该别录项师读译论证书买卖车"
)   # 刻意不放「系」「于」：它們在繁體也是合法用字（系統、人名）
BANNED_PHRASES = ("本課程", "這門課", "中大", "學生會", "你會學")

# 舊萃取檔 nlp_simplified_concepts.json 裡混入的簡體字原詞（共 17 筆），逐一對照成繁體
SIMPLIFIED_FIXES = {
    "交流与直流短路电流": "交流與直流短路電流", "交流旋转机械": "交流旋轉機械", "公司法学": "公司法學",
    "关键带": "關鍵帶", "反应器": "反應器", "古气候地質记录": "古氣候地質記錄",
    "多导体多电路架空线路": "多導體多電路架空線路", "多导体电缆": "多導體電纜", "对称分量": "對稱分量",
    "序列网络": "序列網路", "气候系统": "氣候系統", "海岸地形学": "海岸地形學", "电气参数": "電氣參數",
    "电脑计算": "電腦計算", "第四纪地质": "第四紀地質", "能源系统": "能源系統", "风力涡轮发电机": "風力渦輪發電機",
}

STYLE_GUIDE = """你在為「大學選課助理」編寫名詞白話說明，讀者是高二學生，他們還沒學過這些大學詞彙。

對輸入的每一個詞，寫出：
- gloss：一句話（10–24 個中文字），說明「這是什麼／用來做什麼」。只解釋詞義，與任何特定課程、學校無關；
  不要重複原詞，不要出現「本課程」「這門課」「中大」「學生會學到」，不要誇大，不要加句號以外的標點堆疊。
- hs_link：若能連到高中學過的科目與單元，寫成「高中數學：機率」這種格式（科目＋冒號＋單元）；
  連不上就填 null，不要硬湊。
- type：「概念」、「技術或工具」或「學科領域」三選一。
- skip：高中生日常就懂、或太籠統而不需要解釋的詞（例如「資料分析」「工程學」「人工智慧」），填 true；其餘 false。
- uncertain：你不確定這個詞在學術上的準確意思，或它其實是一整句話／課名而不是一個名詞時填 true，此時 gloss 填 null。

輸入附上的「出現的課程」與「舊說明」只用來判斷這個詞在哪個領域的意思，不可以抄進 gloss，gloss 也不可以提到課程。

範例：
- 微積分 → gloss「計算變化率與累積量的數學工具」，hs_link「高中數學：函數與極限」，type 概念
- 馬可夫鏈 → gloss「用現在的狀態預測下一步的機率模型」，hs_link「高中數學：機率」，type 概念
- 傅立葉轉換 → gloss「把訊號拆成不同頻率成分的數學工具」，hs_link「高中物理：波動」，type 概念
- Python → gloss「常用來處理資料和寫程式的語言」，hs_link null，type 技術或工具
- 資料分析 → skip true

只輸出一個 JSON 物件，不要有其他文字或 markdown 圍欄：
{"items":[{"term":"原詞","gloss":"...","hs_link":null,"type":"概念","skip":false,"uncertain":false}]}
items 的順序與數量必須和輸入完全一致。"""

_PAREN_RE = re.compile(r"[（(][^）)]*[）)]")


# ── 純函式（有單元測試）──────────────────────────────────────────────────────

def norm_key(term: str) -> str:
    """比對用的 key：全形半形統一、小寫、網絡→網路、去掉括號內容與空白標點。"""
    s = unicodedata.normalize("NFKC", term).strip()
    s = _PAREN_RE.sub("", unicodedata.normalize("NFKC", s)).lower()
    s = s.replace("網絡", "網路")
    return re.sub(r"[\s\-_/·、，,．.]", "", s)


def cluster_terms(concepts_by_course: dict) -> dict:
    """依 norm_key 合併別名。回傳 key -> {surfaces, glosses, courses}。"""
    clusters: dict = {}
    for code, entry in concepts_by_course.items():
        for c in entry.get("simplified_concepts", []):
            original = (c.get("original") or "").strip()
            original = SIMPLIFIED_FIXES.get(original, original)
            key = norm_key(original)
            if not key:
                continue
            cl = clusters.setdefault(key, {
                "surfaces": collections.Counter(), "glosses": collections.Counter(), "courses": set()})
            cl["surfaces"][original] += 1
            gloss = (c.get("display") or "").strip()
            if gloss:
                cl["glosses"][gloss] += 1
            cl["courses"].add(code)
    return clusters


def canonical_surface(surfaces: collections.Counter) -> str:
    """最常見的寫法；同票時偏好沒有括號的、較短的。"""
    return sorted(surfaces.items(), key=lambda kv: (-kv[1], bool(_PAREN_RE.search(kv[0])), len(kv[0]), kv[0]))[0][0]


def canonical_gloss(glosses: collections.Counter) -> str:
    """舊說明中最常見的一種；同票取較短者。"""
    if not glosses:
        return ""
    return sorted(glosses.items(), key=lambda kv: (-kv[1], len(kv[0]), kv[0]))[0][0]


def select_core(clusters: dict, forced: list[str]) -> list[str]:
    """回傳 core 的 key，依出現課數由多到少；forced 一定收，即使資料裡沒有。"""
    keys = []
    for key, cl in clusters.items():
        term = canonical_surface(cl["surfaces"])
        base = _PAREN_RE.sub("", term).strip()
        if len(cl["courses"]) >= CORE_MIN_COURSES and TERM_MIN_LEN <= len(base) <= TERM_MAX_LEN:
            keys.append(key)
    for t in forced:
        k = norm_key(t)
        if k and k not in keys:
            keys.append(k)
    keys.sort(key=lambda k: (-(len(clusters[k]["courses"]) if k in clusters else 0), k))
    return keys


def check_entry(term: str, entry: dict) -> list[str]:
    """自動品質檢查。回傳問題清單，空清單代表通過。skip 或 uncertain 的詞不檢查說明。"""
    if entry.get("skip") or entry.get("uncertain"):
        return []
    gloss = entry.get("gloss") or ""
    problems = []
    if not gloss:
        return ["沒有說明"]
    if not GLOSS_MIN_LEN <= len(gloss) <= GLOSS_MAX_LEN:
        problems.append(f"長度 {len(gloss)} 不在 {GLOSS_MIN_LEN}–{GLOSS_MAX_LEN}")
    base = _PAREN_RE.sub("", term).strip()
    if len(base) >= 3 and base in gloss:
        problems.append("說明包含原詞（循環解釋）")
    if any(ch in SIMPLIFIED_ONLY for ch in gloss):
        problems.append("含簡體字")
    if any(p in gloss for p in BANNED_PHRASES):
        problems.append("提到課程或學校")
    hs = entry.get("hs_link")
    if hs is not None and not HS_LINK_RE.match(hs):
        problems.append(f"hs_link 格式不符：{hs}")
    if entry.get("type") not in ("概念", "技術或工具", "學科領域"):
        problems.append(f"type 不合法：{entry.get('type')}")
    return problems


def build_fallback_entry(cl: dict) -> dict:
    term = canonical_surface(cl["surfaces"])
    base = _PAREN_RE.sub("", term).strip()
    return {
        "gloss": canonical_gloss(cl["glosses"]), "hs_link": None, "type": None,
        # 太短的詞、像短句的詞不適合自動標註
        "skip": len(base) < 3 or len(base) > TERM_MAX_LEN,
        "tier": "fallback", "n_courses": len(cl["courses"]),
        "aliases": sorted(s for s in cl["surfaces"] if s != term),
    }


def assemble(clusters: dict, core_keys: list[str], generated: dict[str, dict]) -> tuple[dict, dict]:
    """generated: key -> Claude 產生的項目（含 term）。回傳 (terms, 統計)。

    只有通過 check_entry 的 core 項目才用 Claude 版本；沒通過的退回 fallback 說明並標 needs_review。
    """
    terms: dict = {}
    stats = collections.Counter()
    core_set = set(core_keys)
    for key, cl in clusters.items():
        if key in core_set:
            continue
        term = canonical_surface(cl["surfaces"])
        terms[term] = build_fallback_entry(cl)
        stats["fallback"] += 1
    for key in core_keys:
        cl = clusters.get(key)
        gen = generated.get(key)
        term = canonical_surface(cl["surfaces"]) if cl else (gen or {}).get("term") or key
        n = len(cl["courses"]) if cl else 0
        aliases = sorted(s for s in cl["surfaces"] if s != term) if cl else []
        if gen and not gen.get("uncertain") and not check_entry(term, gen):
            terms[term] = {
                "gloss": gen.get("gloss"), "hs_link": gen.get("hs_link"), "type": gen.get("type"),
                "skip": bool(gen.get("skip")), "tier": "core", "n_courses": n, "aliases": aliases,
                "verified": gen.get("_verified", "claude-only")}
            if gen.get("_note"):
                terms[term]["note"] = gen["_note"]
            stats["core_ok"] += 1
        else:
            base = build_fallback_entry(cl) if cl else {
                "gloss": "", "hs_link": None, "type": None, "skip": True, "tier": "fallback",
                "n_courses": 0, "aliases": []}
            base["needs_review"] = True
            base["review_reason"] = (gen.get("_note") or "Claude 標示不確定") if gen and gen.get("uncertain") \
                else "；".join(check_entry(term, gen)) if gen else "尚未產生"
            terms[term] = base
            stats["core_needs_review"] += 1
    return terms, dict(stats)


MANUAL_PATH = NLP_DIR / "glossary_manual.json"


def apply_manual(terms: dict, manual: dict) -> dict:
    """套用人工審查結果：rewrite 改寫說明並取消 skip；skip 不自動標註；其餘 needs_review 的詞視為說明可用。"""
    stats = collections.Counter()
    for term, gloss in (manual.get("rewrite") or {}).items():
        entry = terms.get(term)
        if entry is None:
            stats["missing"] += 1
            continue
        problems = check_entry(term, {"gloss": gloss, "type": "概念", "hs_link": None})
        if problems:
            stats["rejected"] += 1
            print(f"  人工改寫未通過檢查：{term} → {gloss}（{'、'.join(problems)}）")
            continue
        entry.update(gloss=gloss, skip=False, verified="claude-manual")
        stats["rewritten"] += 1
    for term in manual.get("skip") or []:
        entry = terms.get(term)
        if entry is None:
            stats["missing"] += 1
            continue
        entry.update(skip=True, verified="claude-manual")
        stats["skipped"] += 1
    for entry in terms.values():
        if entry.get("needs_review") and entry.get("verified") == "claude-manual":
            entry.pop("needs_review", None)
            entry.pop("review_reason", None)
        elif entry.get("needs_review") and entry.get("gloss") and not entry.get("skip"):
            entry.update(verified="claude-manual")
            entry.pop("needs_review", None)
            entry.pop("review_reason", None)
            stats["approved"] += 1
    return dict(stats)


# ── Claude 呼叫 ───────────────────────────────────────────────────────────────

def load_token() -> str | None:
    val = os.environ.get(TOKEN_VAR, "").strip()
    if val:
        return val
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{TOKEN_VAR}="):
                return line.split("=", 1)[1].strip().strip("'\"") or None
    return None


def run_claude(user_prompt: str, token: str, timeout: int) -> tuple[str | None, str, str]:
    exe = shutil.which("claude")
    if not exe:
        return None, "找不到 claude 指令", ""
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env[TOKEN_VAR] = token
    cmd = [exe, "-p", "--tools", "", "--system-prompt", STYLE_GUIDE,
           "--output-format", "json", "--no-session-persistence", "--model", MODEL]
    try:
        proc = subprocess.run(cmd, input=user_prompt.encode("utf-8"), capture_output=True, env=env, timeout=timeout)
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


def parse_items(text: str, expected_terms: list[str]) -> list[dict] | None:
    start = text.find("{")
    if start < 0:
        return None
    try:
        # 只解析第一個完整的 JSON 物件；模型偶爾會在後面多附說明文字（其中可能還有大括號）
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        items = obj.get("items") if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None
    if not isinstance(items, list) or len(items) != len(expected_terms):
        return None
    if any(not isinstance(it, dict) or it.get("term") != t for it, t in zip(items, expected_terms)):
        return None
    return items


def looks_like_quota(msg: str) -> bool:
    m = msg.lower()
    return any(w in m for w in ("limit", "quota", "rate", "usage", "429", "overloaded"))


# ── 交叉審核（GPT-5.4 審 Claude 的產出）與改寫 ─────────────────────────────────

REVIEW_MODEL = "gpt-5.4"
REVIEW_PATH = WORK_DIR / "review_pass1.jsonl"
REFINED_PATH = WORK_DIR / "core_refined.jsonl"
REVIEW2_PATH = WORK_DIR / "review_pass2.jsonl"
REVIEW_BATCH = 25

REVIEW_SYSTEM = """你是嚴格的審稿人，審核給高二學生看的「名詞白話說明」，要找出會誤導學生的地方。逐一判斷每則：
- verdict：
  ok：學術上正確，高二生看得懂
  inaccurate：有事實錯誤，或簡化到會誤導（例如把特例寫成通則）
  too_hard：說明裡仍有高二生很可能看不懂、又沒被解釋的詞
  vague：太籠統，看完仍不知道這個詞是什麼
  ambiguous：這個詞在不同學科有明顯不同的意思（例如「函數」在數學與程式設計不同），單獨一句話會誤導
- hs_ok：若有 hs_link，判斷這個詞是否真的是台灣高中課程會教到的內容（只是「有關聯」不算）。true/false；沒有 hs_link 填 null。
- comment：一句話說明問題與建議的修正方向；verdict 為 ok 且 hs_ok 不為 false 時留空字串。
只輸出 JSON：{"items":[{"term":"..","verdict":"ok","hs_ok":null,"comment":""}]}，順序與數量必須和輸入一致。"""

REFINE_USER = """下面每個詞都有「目前說明」與審稿人的意見，請依意見重寫，並仍遵守系統提示的所有格式與風格規則。
- inaccurate：先確保正確，寧可寫得保守一點，不要把特例寫成通則。
- too_hard：把難詞換成日常用語，必要時用一個生活例子帶過（說明可到 28 字）。
- vague：寫出具體做什麼、用在哪。
- hs_link：除非這個詞確實是台灣高中課程會教的內容，否則填 null。
- 一詞多義的詞不要硬寫，skip 填 false、uncertain 填 true、gloss 填 null。
輸出格式同系統提示。"""


def _gpt_client():
    sys.path.insert(0, str(ROOT / "backend"))
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH)
    from app.services import llm_service
    return llm_service._get_client()


def review_batch(client, batch: list[dict], model: str = REVIEW_MODEL) -> list[dict] | None:
    payload = [{"term": e["term"], "gloss": e.get("gloss"), "hs_link": e.get("hs_link")} for e in batch]
    r = client.chat.completions.create(
        model=model, messages=[{"role": "system", "content": REVIEW_SYSTEM},
                               {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        max_completion_tokens=6000)
    return parse_items(r.choices[0].message.content or "", [e["term"] for e in batch])


def _load_review(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                it = json.loads(line)
                out[norm_key(it["term"])] = it
    return out


def needs_rewrite(review: dict | None) -> bool:
    return bool(review) and review.get("verdict") in ("inaccurate", "too_hard", "vague")


def apply_reviews(generated: dict, review1: dict, refined: dict, review2: dict) -> dict:
    """依兩輪審核決定每個 core 詞的最終內容。回傳 key -> 項目（含 verified 與 review_note）。

    規則：
    - 第一輪 ok → 沿用 Claude 原版（雙模型同意）。
    - 第一輪 inaccurate/too_hard/vague → 採用改寫版；改寫版第二輪也 ok 才算通過，否則待人工確認。
    - ambiguous（一詞多義）→ 不自動標註（skip），保留說明供人工參考。
    - hs_link 只在「最後採用的那一版」被 GPT 判為 hs_ok == true 時保留，其餘一律移除。
    """
    final: dict = {}
    for key, gen in generated.items():
        item = {k: v for k, v in gen.items() if not k.startswith("_")}
        r1 = review1.get(key)
        note, verified = "", "claude-only"
        last_review = r1
        if r1 is None:
            note = "尚未交叉審核"
        elif r1.get("verdict") == "ambiguous":
            item["skip"], note, verified = True, "一詞多義，不自動標註：" + (r1.get("comment") or ""), "claude+gpt"
        elif r1.get("verdict") == "ok":
            verified = "claude+gpt"
        else:  # 需要改寫
            ref = refined.get(key)
            r2 = review2.get(key)
            if ref and not ref.get("uncertain") and ref.get("gloss") and r2 and r2.get("verdict") == "ok":
                item = {k: v for k, v in ref.items() if not k.startswith("_")}
                verified, last_review = "claude+gpt(改寫後)", r2
            else:
                item["uncertain"] = True       # 讓 assemble 退回 fallback 並標待人工確認
                note = "審稿：" + (r1.get("verdict") or "") + "；" + (r1.get("comment") or "")
                last_review = r1
        if last_review is None or last_review.get("hs_ok") is not True:
            item["hs_link"] = None
        item["_verified"], item["_note"] = verified, note
        final[key] = item
    return final


# ── 命令 ──────────────────────────────────────────────────────────────────────

def _load_clusters() -> dict:
    return cluster_terms(json.loads(IN_PATH.read_text(encoding="utf-8")))


def _course_names() -> dict:
    idx = json.loads(COURSE_INDEX.read_text(encoding="utf-8"))
    return {code: v.get("name_zh", "") for code, v in idx.items()}


def cmd_candidates(_args) -> int:
    clusters = _load_clusters()
    core = select_core(clusters, FORCED_TERMS)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    names = _course_names()
    rows = []
    for k in core:
        cl = clusters.get(k)
        term = canonical_surface(cl["surfaces"]) if cl else next(t for t in FORCED_TERMS if norm_key(t) == k)
        rows.append({
            "key": k, "term": term, "n_courses": len(cl["courses"]) if cl else 0,
            "courses": sorted({names.get(c, "") for c in sorted(cl["courses"])[:6]} - {""})[:3] if cl else [],
            "old_glosses": [g for g, _ in cl["glosses"].most_common(2)] if cl else [],
        })
    CANDIDATES_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(len(c["courses"]) for c in clusters.values())
    print(f"不重複詞（合併別名後）：{len(clusters):,}｜core 候選：{len(rows):,}｜fallback：{len(clusters) - len(rows) + sum(1 for r in rows if r['key'] not in clusters):,}")
    print(f"core 候選涵蓋的『詞×課』條目：{sum(r['n_courses'] for r in rows):,} / {total:,}")
    print(f"已寫入 {CANDIDATES_PATH}")
    return 0


def _batch_prompt(batch: list[dict]) -> str:
    payload = [{"term": r["term"], "出現的課程": r["courses"], "舊說明": r["old_glosses"]} for r in batch]
    return "請為下列詞寫白話說明：\n" + json.dumps(payload, ensure_ascii=False, indent=1)


def _load_generated(path: Path) -> dict[str, dict]:
    done: dict[str, dict] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                for it in row["items"]:
                    done[norm_key(it["term"])] = {**it, "_model": row.get("model", "")}
    return done


def cmd_generate(args) -> int:
    if not CANDIDATES_PATH.exists():
        sys.exit("請先執行 candidates")
    token = load_token()
    if not token:
        sys.exit(f"找不到 {TOKEN_VAR}：請在 .env 填入 claude setup-token 產生的 token")
    rows = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
    out = Path(args.out) if args.out else GENERATED_PATH
    if args.sample:  # 等距抽樣，涵蓋高頻到低頻
        step = max(1, len(rows) // args.sample)
        rows = rows[::step][:args.sample]
    done = _load_generated(out)
    todo = [r for r in rows if r["key"] not in done]
    batches = [todo[i:i + BATCH_SIZE] for i in range(0, len(todo), BATCH_SIZE)]
    print(f"目標 {len(rows)} 個詞，已完成 {len(rows) - len(todo)}，待處理 {len(todo)}（{len(batches)} 批，並行 {args.workers}）")
    if not batches:
        return 0
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    stop = {"quota": False}

    def work(batch):
        if stop["quota"]:
            return batch, None, "已因額度中止", ""
        for _ in range(2):  # 格式不符時重試一次
            text, err, used = run_claude(_batch_prompt(batch), token, args.timeout)
            items = parse_items(text, [r["term"] for r in batch]) if text else None
            if items:
                return batch, items, "", used
            if err and looks_like_quota(err):
                stop["quota"] = True
                return batch, None, err, used
        return batch, None, err or "輸出格式不符", used

    ok = failed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex, out.open("a", encoding="utf-8") as f:
        for fut in as_completed([ex.submit(work, b) for b in batches]):
            batch, items, err, used = fut.result()
            if items:
                f.write(json.dumps({"model": used, "terms": [r["term"] for r in batch], "items": items},
                                   ensure_ascii=False) + "\n")
                f.flush()
                ok += 1
            else:
                failed += 1
                print(f"  批次失敗（{batch[0]['term']} 等 {len(batch)} 個）：{err}")
            print(f"  進度 成功 {ok} / 失敗 {failed} / 共 {len(batches)}")
    if stop["quota"]:
        print("因額度或頻率限制中止；等額度恢復後重跑同一指令即可從中斷處繼續。")
    return 0 if not failed else 1


def cmd_check(args) -> int:
    gen = _load_generated(Path(args.generated) if args.generated else GENERATED_PATH)
    clusters = _load_clusters()
    bad, skipped, unsure = [], 0, 0
    for key, it in gen.items():
        term = canonical_surface(clusters[key]["surfaces"]) if key in clusters else it["term"]
        if it.get("skip"):
            skipped += 1
        if it.get("uncertain"):
            unsure += 1
        probs = check_entry(term, it)
        if probs:
            bad.append((term, it.get("gloss"), probs))
    print(f"已產生 {len(gen)} 個｜標示 skip {skipped}｜Claude 標示不確定 {unsure}｜未通過自動檢查 {len(bad)}")
    for term, gloss, probs in bad[:40]:
        print(f"  ✗ {term}：{gloss}  →  {'；'.join(probs)}")
    models = collections.Counter(it.get("_model") or "（未記錄）" for it in gen.values())
    print("使用的模型：", dict(models))
    return 0


def cmd_review(args) -> int:
    """用 GPT-5.4 交叉審核 Claude 寫的說明。--second 審核改寫後的版本。"""
    src, path = (REFINED_PATH, REVIEW2_PATH) if args.second else (GENERATED_PATH, REVIEW_PATH)
    gen, done = _load_generated(src), _load_review(path)
    targets = [{"term": it["term"], "gloss": it.get("gloss"), "hs_link": it.get("hs_link")}
               for k, it in gen.items() if k not in done and not it.get("skip") and not it.get("uncertain") and it.get("gloss")]
    batches = [targets[i:i + REVIEW_BATCH] for i in range(0, len(targets), REVIEW_BATCH)]
    print(f"待審核 {len(targets)} 個（{len(batches)} 批），已審核 {len(done)}")
    if not batches:
        return 0
    client = _gpt_client()
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    def work(b):
        for _ in range(2):
            try:
                items = review_batch(client, b, args.model)
            except Exception as e:  # 網路或配額錯誤：回報後略過這批，續跑可補
                return b, None, str(e)[:160]
            if items:
                return b, items, ""
        return b, None, "輸出格式不符"

    ok = bad = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex, path.open("a", encoding="utf-8") as f:
        for fut in as_completed([ex.submit(work, b) for b in batches]):
            b, items, err = fut.result()
            if items:
                for it in items:
                    f.write(json.dumps({**it, "reviewer": args.model}, ensure_ascii=False) + "\n")
                f.flush(); ok += 1
            else:
                bad += 1; print(f"  批次失敗（{b[0]['term']} 等）：{err}")
    rv = _load_review(path)
    print(f"完成：成功 {ok} 批、失敗 {bad} 批｜審核結果：{dict(collections.Counter(r['verdict'] for r in rv.values()))}")
    return 0 if not bad else 1


def cmd_refine(args) -> int:
    """對審核未通過（inaccurate/too_hard/vague）的詞，依審稿意見請 Claude 改寫。"""
    token = load_token()
    if not token:
        sys.exit(f"找不到 {TOKEN_VAR}")
    gen, r1, done = _load_generated(GENERATED_PATH), _load_review(REVIEW_PATH), _load_generated(REFINED_PATH)
    todo = [{"term": gen[k]["term"], "目前說明": gen[k].get("gloss"), "目前hs_link": gen[k].get("hs_link"),
             "審稿意見": f"{r['verdict']}：{r.get('comment', '')}"}
            for k, r in r1.items() if needs_rewrite(r) and k in gen and k not in done]
    batches = [todo[i:i + BATCH_SIZE] for i in range(0, len(todo), BATCH_SIZE)]
    print(f"需改寫 {len(todo)} 個（{len(batches)} 批），已改寫 {len(done)}")
    if not batches:
        return 0

    def work(b):
        prompt = REFINE_USER + "\n" + json.dumps(b, ensure_ascii=False, indent=1)
        for _ in range(2):
            text, err, used = run_claude(prompt, token, args.timeout)
            items = parse_items(text, [x["term"] for x in b]) if text else None
            if items:
                return b, items, "", used
        return b, None, err or "輸出格式不符", ""

    ok = bad = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex, REFINED_PATH.open("a", encoding="utf-8") as f:
        for fut in as_completed([ex.submit(work, b) for b in batches]):
            b, items, err, used = fut.result()
            if items:
                f.write(json.dumps({"model": used, "terms": [x["term"] for x in b], "items": items}, ensure_ascii=False) + "\n")
                f.flush(); ok += 1
            else:
                bad += 1; print(f"  批次失敗（{b[0]['term']} 等）：{err}")
    print(f"完成：成功 {ok} 批、失敗 {bad} 批")
    return 0 if not bad else 1


def cmd_assemble(args) -> int:
    clusters = _load_clusters()
    gen_path = Path(args.generated) if args.generated else GENERATED_PATH
    generated = {k: v for k, v in _load_generated(gen_path).items()}
    review1 = _load_review(REVIEW_PATH)
    if review1:   # 有做過交叉審核才套用審核規則
        generated = apply_reviews(generated, review1, _load_generated(REFINED_PATH), _load_review(REVIEW2_PATH))
    core_keys = select_core(clusters, FORCED_TERMS)
    terms, stats = assemble(clusters, core_keys, generated)
    if MANUAL_PATH.exists():
        stats["manual"] = apply_manual(terms, json.loads(MANUAL_PATH.read_text(encoding="utf-8")))
    models = collections.Counter(v.get("_model") or "" for v in generated.values())
    out = {
        "meta": {
            "version": 1, "created": date.today().isoformat(), "style_version": STYLE_VERSION,
            "provenance": "AI 衍生內容。core 層由 Claude 依統一風格重寫（只解釋詞義）；fallback 層沿用舊說明中最常見的一種（舊說明由本地 Qwen3-14B 逐課改寫）。",
            "source": "data/processed/nlp/nlp_simplified_concepts.json",
            "core_model": ",".join(m for m in models if m) or MODEL,
            "counts": {**stats, "total": len(terms)},
            "usage": "後端比對時以 term 與 aliases 對應；skip=true 的詞不標註；needs_review=true 的詞不要使用其說明。",
        },
        "terms": terms,
    }
    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已寫入 {OUT_PATH}（{OUT_PATH.stat().st_size / 1e6:.1f} MB）｜{out['meta']['counts']}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="建立課程助理用的名詞白話詞庫")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("candidates", help="統計並寫出 core 候選清單").set_defaults(fn=cmd_candidates)
    g = sub.add_parser("generate", help="用 Claude 產生 core 詞庫（可中斷續跑）")
    g.add_argument("--sample", type=int, default=0, help="只處理等距抽樣的 N 個詞（試跑用）")
    g.add_argument("--out", default=None, help="輸出 jsonl（預設 glossary_work/core_generated.jsonl）")
    g.add_argument("--workers", type=int, default=3)
    g.add_argument("--timeout", type=int, default=240)
    g.set_defaults(fn=cmd_generate)
    r = sub.add_parser("review", help="用 GPT-5.4 交叉審核（--second 審核改寫後的版本）")
    r.add_argument("--second", action="store_true")
    r.add_argument("--model", default=REVIEW_MODEL)
    r.add_argument("--workers", type=int, default=4)
    r.set_defaults(fn=cmd_review)
    rf = sub.add_parser("refine", help="依審稿意見請 Claude 改寫未通過的詞")
    rf.add_argument("--workers", type=int, default=3)
    rf.add_argument("--timeout", type=int, default=240)
    rf.set_defaults(fn=cmd_refine)
    c = sub.add_parser("check", help="自動品質檢查")
    c.add_argument("--generated", default=None)
    c.set_defaults(fn=cmd_check)
    a = sub.add_parser("assemble", help="組合 core + fallback 成 concept_glossary.json")
    a.add_argument("--generated", default=None)
    a.set_defaults(fn=cmd_assemble)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
