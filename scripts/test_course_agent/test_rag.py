"""
test_rag.py

自動測試 /api/chat/stream，將每題的工具呼叫細節、推薦課程、完整回答
記錄成 JSON + 易讀 Markdown 報告。

每題都會呼叫 /api/chat/stream（SSE），因此 session 也會存入後端，
可在前端歷史對話中查看。

執行方式：
  python scripts/test_rag.py
  python scripts/test_rag.py --url http://localhost:8000
  python scripts/test_rag.py --cats program,graduation     # 只跑指定類別
  python scripts/test_rag.py --nos 1,3,5                   # 只跑指定題號
  python scripts/test_rag.py --questions scripts/my.txt    # 自訂題目 txt
  python scripts/test_rag.py --questions docs/10-retrieval-evaluation/eval-set-v1.json   # 評測集（結果以題號標示）

輸出：
  data/test_results/<timestamp>.json  — 完整結果（含工具細節）
  data/test_results/<timestamp>.md    — 易讀報告（工具呼叫 + 推薦課程 + 回答）
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent.parent
RESULTS_DIR = ROOT / "data" / "test_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# 測試題目版本：v6（2026-05-18）
# 調整方向：改成高中生口吻，較口語自然，避免「哪些系所的課程有教到 X」這類像 benchmark 的問法
DEFAULT_QUESTIONS = [
    # ── P0 修正回歸 ────────────────────────────────────────────────────────
    ("regression",  "人工智慧技術應用學程要修哪些課？"),
    ("regression",  "我想學 GIS 地理資訊系統，讀哪個系比較有機會接觸到？"),
    ("regression",  "地科系都在學什麼？有哪些課可以選？"),
    ("regression",  "讀資工系的話，大學四年有哪些課是一定要修的？"),

    # ── 系所別名 ──────────────────────────────────────────────────────────
    ("alias",       "大氣系畢業需要達到什麼條件？"),
    ("alias",       "化材系主要在教哪些東西？"),
    ("alias",       "資管系是在學什麼的？"),

    # ── 修課資格 ──────────────────────────────────────────────────────────
    ("eligibility", "我不是客語系的，可以去選客語教學這門課嗎？"),
    ("eligibility", "資料結構可以大一就修嗎？有什麼限制嗎？"),
    ("eligibility", "我是別系的學生，可以修機率與統計嗎？要有什麼先修嗎？"),

    # ── 人文 / 語言系所 ────────────────────────────────────────────────────
    ("humanities",  "讀中文系的話，有哪些課是必修的？"),
    ("humanities",  "英美語文系適合什麼樣的人去讀？有沒有比較特別的課？"),
    ("humanities",  "我想學法文，中央有法語課可以上嗎？"),
    ("humanities",  "通識裡面有沒有哲學或倫理學相關的課可以選？"),

    # ── 經濟 / 財務 / 管理 ────────────────────────────────────────────────
    ("econ_fin",    "經濟系大一大二要修哪些必修課？"),
    ("econ_fin",    "財金系主要在培養什麼方向的人才？適合對什麼有興趣的人讀？"),
    ("econ_fin",    "我對股票投資很感興趣，中央有這方面的課嗎？"),
    ("econ_fin",    "管理學院有哪些學分學程可以選？"),
    ("econ_fin",    "企管系要怎麼畢業？需要多少學分？"),

    # ── 社會科學 / 客家 ───────────────────────────────────────────────────
    ("social_sci",  "客家語文系都在學什麼？有哪些課是必修的？"),
    ("social_sci",  "客家文化相關的課程和老師在中央有哪些？"),
    ("social_sci",  "法律與政府研究所主要研究什麼方向？"),
    ("social_sci",  "通識有沒有和性別平等或社會議題有關的課可以修？"),

    # ── 生醫 / 生命科學 ───────────────────────────────────────────────────
    ("life_sci",    "讀生醫工程系的話，有哪些必修課要修？"),
    ("life_sci",    "生命科學系主要在做什麼研究？適合喜歡什麼的人讀？"),
    ("life_sci",    "我對基因或分子生物學有興趣，中央有哪些相關課可以修？"),

    # ── 自然科學 / 數學 ───────────────────────────────────────────────────
    ("natural_sci", "物理系的必修課有哪些？"),
    ("natural_sci", "數學系的課程主要偏哪些方向？"),
    ("natural_sci", "我對統計或數據分析有興趣，中央有相關課程或系所嗎？"),

    # ── 通識 ──────────────────────────────────────────────────────────────
    ("general",     "語言中心有沒有日文課或西班牙文課？"),
    ("general",     "通識有沒有跟法律相關的課？"),
    ("general",     "我很在意環保議題，有沒有和永續發展相關的課可以選？"),
    ("general_adv", "通識有沒有藝術欣賞或音樂方面的課？"),
    ("general_adv", "通識裡面有沒有討論公民社會或法律的課？"),
    ("general_adv", "有沒有討論 AI 對社會影響或科技倫理的通識課可以修？"),
    ("general_adv", "通識有沒有介紹台灣歷史或本土文化的課？"),

    # ── 學分學程 ──────────────────────────────────────────────────────────
    ("program",     "永續發展學分學程在學什麼？要修哪些課？"),
    ("program",     "中央有沒有語言或文化相關的學分學程？"),
    ("program",     "財務工程學程需要修哪些課？"),

    # ── 系所介紹 / 知識側寫 ───────────────────────────────────────────────
    ("dept_info",   "資工系適合什麼樣的人？讀完以後可以做什麼？"),
    ("dept_info",   "地科系的課程主要偏什麼方向？"),
    ("dept_info",   "大氣系適合對什麼事情有興趣的學生去讀？"),

    # ── 基礎工具覆蓋 ──────────────────────────────────────────────────────
    ("tech",        "我想學 Python，中央有哪些課可以學到？"),
    ("dept_req",    "大氣系的必修課有哪些？"),
    ("dept_elec",   "通識中心有哪些選修課可以選？"),
    ("course_det",  "統計學這門課主要在教什麼？"),
    ("graduation",  "讀中文系要怎麼畢業？學分要求是什麼？"),
    ("teacher",     "哪位老師的專長是自然語言處理？"),
    ("teacher",     "江振瑞教授在中央開了哪些課？"),
    ("similar",     "有沒有和生物統計概念比較相近的課程推薦？"),

    # ── PPR overview ──────────────────────────────────────────────────────
    ("ppr_overview","AI 在中央有哪些課程、老師和系所？我想全面了解一下。"),
    ("ppr_overview","影像處理和電腦視覺在中央有哪些相關課程和老師？"),

    # ── 系所比較 ──────────────────────────────────────────────────────────
    ("dept_compare","大氣系和地科系有什麼不同？各自比較有特色的課是什麼？"),
    ("dept_compare","我在考慮資工和電機，這兩個系方向差在哪裡？"),
    ("dept_compare","財金系和經濟系有什麼差別？分別適合什麼樣的人？"),
    ("dept_compare","生命科學系和生醫工程系各在學什麼？差在哪裡？"),

    # ── 多工具 ────────────────────────────────────────────────────────────
    ("multi",       "我對土木工程有興趣，土木系有什麼特色？主要在學哪些東西？"),
    ("multi",       "我高中讀社會組，喜歡分析數據，有沒有不需要很強程式基礎的課程或學程？"),

    # ── Fallback ──────────────────────────────────────────────────────────
    ("fallback",    "有沒有和全球環境變遷相關的課可以修？"),
    ("fallback",    "中央有沒有區塊鏈或 Web3 應用的課程？"),
    ("fallback_name","深度學習概論這門課有什麼先修條件嗎？"),
    ("fallback_name","機率統計我是外系的可以修嗎？有什麼限制？"),

    # ── 語意豐富化 ────────────────────────────────────────────────────────
    ("enrich",      "哪些課有在教 Docker 或容器化技術？這類課主要在學什麼概念？"),

    # ── 分班去重 ──────────────────────────────────────────────────────────
    ("dedup",       "數學系有哪些必修課？同一門課有分幾個班嗎？"),

    # ── 學士班 ────────────────────────────────────────────────────────────
    ("special_prog","管院學士班是什麼？和一般管理系所有什麼不同？"),
    ("special_prog","中央有哪些跨領域的學院學士班或整合型學程？"),

    # ── v4 回歸 ───────────────────────────────────────────────────────────
    ("v4_regression", "總體經濟學有在中央開課嗎？"),
    ("v4_regression", "自然語言處理這門課是哪個系開的？"),
    ("v4_regression", "張家凱老師在教哪些課？"),
    ("v4_regression", "投資學在哪些系有開？"),
]

CAT_LABELS = {
    "regression":    "P0 回歸測試",
    "alias":         "系所別名",
    "eligibility":   "修課資格",
    "humanities":    "人文/語言系所",
    "econ_fin":      "經濟/財務/管理",
    "social_sci":    "社科/客家",
    "life_sci":      "生醫/生命科學",
    "natural_sci":   "自然科學/數學",
    "general":       "通識/語言",
    "general_adv":   "通識進階",
    "program":       "學分學程",
    "dept_info":     "系所介紹/側寫",
    "tech":          "技術找課",
    "dept_req":      "系所必修",
    "dept_elec":     "系所選修",
    "course_det":    "課程詳情",
    "graduation":    "畢業規定",
    "teacher":       "教師查詢",
    "similar":       "相似課推薦",
    "ppr_overview":  "PPR Overview 模式",
    "dept_compare":  "系所比較",
    "multi":         "多工具",
    "fallback":      "Fallback",
    "fallback_name": "課程名稱 Fallback",
    "enrich":        "語意豐富化欄位",
    "dedup":         "分班去重",
    "special_prog":  "學士班/特殊班制",
    "v4_regression": "v4 修正回歸",
}


def ask_stream(base_url: str, question: str) -> dict:
    """呼叫 /api/chat/stream，解析 SSE 事件，回傳完整結果（含工具呼叫細節）。"""
    try:
        resp = requests.post(
            f"{base_url}/api/chat/stream",
            json={"question": question},
            timeout=120,
            stream=True,
        )
        resp.raise_for_status()

        answer_parts: list[str] = []
        done_data: dict = {}

        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line or not raw_line.startswith("data: "):
                continue
            try:
                data = json.loads(raw_line[6:])
            except Exception:
                continue

            t = data.get("type")
            if t == "token":
                answer_parts.append(data.get("text", ""))
            elif t == "done":
                done_data = data

        streamed = "".join(answer_parts)
        # 前端在 done 時會用 final_answer 取代串流文字，所以評測以使用者最後看到的為準
        answer = done_data.get("final_answer") or streamed
        trace_calls = done_data.get("debug_trace", {}).get("toolCalls", [])

        return {
            "answer":            answer,
            "answer_streamed":   streamed,
            "model":             done_data.get("model", ""),
            "tools_used":        done_data.get("tools_used", []),
            "course_cards":      done_data.get("course_cards", []),
            "course_pool_count": done_data.get("course_pool_count", 0),
            "has_large_result":  done_data.get("has_large_result", False),
            "input_tokens":      done_data.get("input_tokens", 0),
            "output_tokens":     done_data.get("output_tokens", 0),
            # 每個工具呼叫的細節：{tool, args, coursesFound, count, scores, scoreType}
            "tool_calls":        trace_calls,
        }
    except requests.exceptions.Timeout:
        return {"error": "timeout",   "answer": "", "tools_used": [], "course_cards": [], "tool_calls": []}
    except Exception as e:
        return {"error": str(e),      "answer": "", "tools_used": [], "course_cards": [], "tool_calls": []}


def run_tests(base_url: str, questions: list[tuple[str, str]]) -> list[dict]:
    results = []
    total = len(questions)
    for i, (category, q) in enumerate(questions, 1):
        label = CAT_LABELS.get(category, category)
        print(f"[{i:02d}/{total}] [{label}] {q}")
        t0 = time.time()
        resp = ask_stream(base_url, q)
        elapsed = round(time.time() - t0, 2)

        record = {
            "no":            i,
            "category":      category,
            "question":      q,
            "answer":        resp.get("answer", ""),
            "answer_streamed": resp.get("answer_streamed", ""),
            "model":         resp.get("model", ""),
            "tools_used":    resp.get("tools_used", []),
            "tool_calls":    resp.get("tool_calls", []),
            "course_cards":  resp.get("course_cards", []),
            "course_pool_count": resp.get("course_pool_count", 0),
            "has_large_result":  resp.get("has_large_result", False),
            "input_tokens":  resp.get("input_tokens", 0),
            "output_tokens": resp.get("output_tokens", 0),
            "elapsed_sec":   elapsed,
            "error":         resp.get("error", ""),
        }
        results.append(record)

        status = "❌" if record["error"] else "✅"
        tools_str = ", ".join(record["tools_used"]) if record["tools_used"] else "—"
        cards_n = len(record["course_cards"])
        print(f"  {status} {elapsed}s | tools: {tools_str} | cards: {cards_n}")
        print()

    return results


def _fmt_args(args: dict) -> str:
    s = json.dumps(args, ensure_ascii=False)
    return s[:120] + "…" if len(s) > 120 else s


def save_json(results: list[dict], path: Path) -> None:
    path.write_text(
        json.dumps({"results": results, "total": len(results)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_markdown(results: list[dict], path: Path) -> None:
    lines = ["# RAG 測試報告\n\n"]
    lines.append(f"> 執行時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}  \n")
    lines.append(f"> 版本：v6（2026-05-18）  \n")
    lines.append(f"> 題目數：{len(results)}  \n\n---\n")

    current_cat = None
    for r in results:
        if r["category"] != current_cat:
            current_cat = r["category"]
            label = CAT_LABELS.get(current_cat, current_cat)
            lines.append(f"\n## {label}\n")

        status = "❌" if r["error"] else "✅"
        cards = r.get("course_cards", [])
        tcs   = r.get("tool_calls", [])

        lines.append(f"### {status} Q{r['no']}：{r['question']}\n\n")
        lines.append(f"**耗時：** {r['elapsed_sec']}s　"
                     f"**in/out tokens：** {r.get('input_tokens',0)}/{r.get('output_tokens',0)}　"
                     f"**Cards：** {len(cards)}　**Pool：** {r.get('course_pool_count',0)}  \n\n")

        if r["error"]:
            lines.append(f"**錯誤：** {r['error']}\n\n")
            continue

        # ── 工具呼叫明細 ────────────────────────────────────────────────────
        if tcs:
            lines.append("**工具呼叫：**\n\n")
            lines.append("| # | 工具 | 參數 | 回傳 | 範例課程 |\n")
            lines.append("|---|------|------|------|---------|\n")
            for j, tc in enumerate(tcs, 1):
                tool      = tc.get("tool", "?")
                args_str  = _fmt_args(tc.get("args", {}))
                count     = tc.get("count")
                sc_type   = tc.get("scoreType") or ""
                count_str = f"{count} 筆" if count is not None else "—"
                if sc_type:
                    count_str += f"（{sc_type}）"
                courses   = tc.get("coursesFound", [])[:4]
                scores    = tc.get("scores", [])
                course_parts = []
                for k, c in enumerate(courses):
                    sc = f"[{scores[k]:.2f}]" if k < len(scores) and scores[k] else ""
                    course_parts.append(f"{c} {sc}".strip())
                course_str = "、".join(course_parts) if course_parts else "—"
                lines.append(f"| {j} | `{tool}` | `{args_str}` | {count_str} | {course_str} |\n")
            lines.append("\n")

        # ── 推薦課程卡片 ────────────────────────────────────────────────────
        if cards:
            lines.append(f"**推薦課程（{len(cards)} 門）：**\n\n")
            for c in cards:
                name    = c.get("name", "?")
                dept    = c.get("dept", "")
                credits = c.get("credits") or ""
                ctype   = c.get("type", "")
                teacher = c.get("teacher", "")
                meta    = "　".join(filter(None, [dept, f"{credits}學分" if credits else "", ctype, teacher]))
                lines.append(f"- **{name}**　{meta}\n")
            lines.append("\n")
        else:
            lines.append("**推薦課程：** 無課程卡片（非課程類回答）  \n\n")

        # ── 完整回答 ────────────────────────────────────────────────────────
        answer_quoted = r["answer"].replace("\n", "\n> ")
        lines.append(f"**回答：**\n> {answer_quoted}\n\n---\n")

    path.write_text("".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="NCU RAG 自動測試工具")
    parser.add_argument("--url",       default="http://localhost:8000", help="API base URL")
    parser.add_argument("--questions", default=None, help="每行一題的 txt 檔，或評測集 .json（不填則用內建題目）")
    parser.add_argument("--nos",  default=None, help="只跑指定題號，逗號分隔，例如 --nos 1,3,5")
    parser.add_argument("--cats", default=None, help="只跑指定類別，逗號分隔，例如 --cats program,graduation")
    args = parser.parse_args()

    questions = DEFAULT_QUESTIONS
    if args.questions and args.questions.endswith(".json"):
        # 評測集 JSON：類別欄位放題號（如 D03），結果可依題號對回預期工具，也能用 --cats D03,D04 重跑
        data = json.loads(Path(args.questions).read_text(encoding="utf-8"))
        questions = [(q["id"], q["question"]) for q in data["questions"]]
    elif args.questions:
        txt = Path(args.questions).read_text(encoding="utf-8")
        questions = [("custom", line.strip()) for line in txt.splitlines()
                     if line.strip() and not line.startswith("#")]

    if args.nos:
        nos = {int(x.strip()) for x in args.nos.split(",")}
        questions = [(cat, q) for i, (cat, q) in enumerate(questions, 1) if i in nos]

    if args.cats:
        cats = {c.strip() for c in args.cats.split(",")}
        questions = [(cat, q) for cat, q in questions if cat in cats]

    print(f"目標：{args.url}")
    print(f"題數：{len(questions)}\n")

    results = run_tests(args.url, questions)

    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = RESULTS_DIR / f"{ts}.json"
    md_path   = RESULTS_DIR / f"{ts}.md"

    save_json(results, json_path)
    save_markdown(results, md_path)

    errors   = sum(1 for r in results if r["error"])
    avg_time = round(sum(r["elapsed_sec"] for r in results) / len(results), 2)
    print(f"\n完成｜成功：{len(results) - errors}/{len(results)}｜平均耗時：{avg_time}s")
    print(f"JSON：{json_path}")
    print(f"報告：{md_path}")


if __name__ == "__main__":
    main()
