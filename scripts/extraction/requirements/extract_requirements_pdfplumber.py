"""
從 data/raw/應修科目表/ 所有 PDF，用純 pdfplumber 規則式萃取每門課的年級與學期。

不呼叫任何 LLM。欄位偵測邏輯源自 parse_requirements_table.py。

輸出：data/processed/requirements_semester_map.json
格式：
{
  "資訊工程學系": {
    "pdf": "資訊工程學系_114.pdf",
    "courses": [
      {
        "key": "CS1001",          // 課號（優先）或標準化課名
        "key_type": "code",       // "code" | "name"
        "year_level": 1,          // 1–4
        "semester": 1,            // 1=上, 2=下
        "credits": 3,
        "spans_semesters": [[1,1],[1,2]],  // 跨學期時才有
        "low_confidence": false   // true = 建議人工確認
      }
    ],
    "low_confidence_count": 0,
    "total": 30,
    "error": null
  }
}

相依套件：pdfplumber
"""

import json
import re
from pathlib import Path

BASE_DIR         = Path(__file__).resolve().parents[3]
REQUIREMENTS_DIR = BASE_DIR / "data" / "raw" / "應修科目表"
OUTPUT_PATH      = BASE_DIR / "data" / "processed" / "requirements_semester_map.json"

DEPT_ALIASES = {
    "地科院學士班": "地球科學學院學士班",
}


# ── 工具函式（源自 parse_requirements_table.py）─────────────────

def normalize_dept_name(stem: str) -> str:
    name = re.sub(r'_\d{3}$', '', stem)
    return DEPT_ALIASES.get(name, name)


def _extract_code(text: str):
    m = re.search(r'[A-Z]{2,4}\d{4}', text or "")
    return m.group(0) if m else None


def _normalize_name(text: str) -> str:
    text = re.sub(r'[A-Z]{2,4}\d{4}', '', text or "")
    text = re.sub(r'[/\s\-\u0020-\u002F\u003A-\u0040]+', '', text)
    return text.strip()


def extract_semester_map(pdf_path: Path) -> dict:
    """
    用 pdfplumber 提取課程與學期的對應關係。
    回傳 {課號或標準化課名: {"year_level": int, "semester": int, "all": [(y,s),...], "credits": int}}

    欄位結構（固定）：
      ...大一上, 大一下, 大二上, 大二下, 大三上, 大三下, 大四上, 大四下
    """
    try:
        import pdfplumber
    except ImportError:
        return {}

    REL_TO_YS = {
        0: (1, 1), 1: (1, 2),
        2: (2, 1), 3: (2, 2),
        4: (3, 1), 5: (3, 2),
        6: (4, 1), 7: (4, 2),
    }

    semester_map: dict = {}

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                for table in (page.extract_tables() or []):
                    if not table:
                        continue

                    # 找「上/下」header 行，確認學期欄位起始 index
                    sem_start_col = None
                    for row in table[:6]:
                        vals = [str(c or "").strip() for c in row]
                        up_down = [i for i, v in enumerate(vals) if v in ("上", "下")]
                        if len(up_down) >= 4:
                            sem_start_col = up_down[0]
                            break

                    if sem_start_col is None:
                        continue

                    for row in table:
                        if row is None:
                            continue

                        code = None
                        for cell in row:
                            c = _extract_code(str(cell or ""))
                            if c:
                                code = c
                                break

                        SKIP_KW = {"學分", "必修", "選修", "課群", "應用", "基礎", "專業", "主修"}
                        name_raw = ""
                        if not code:
                            for ci in [1, 2, 3]:
                                cell_val = str(row[ci] if ci < len(row) else "").strip()
                                if (cell_val and len(cell_val) >= 2
                                        and not any(kw in cell_val for kw in SKIP_KW)):
                                    name_raw = cell_val
                                    break

                        if not code and not name_raw:
                            continue

                        active = []
                        first_credit = None
                        for rel_idx, (y, s) in REL_TO_YS.items():
                            col_i = sem_start_col + rel_idx
                            if col_i >= len(row):
                                break
                            val = row[col_i]
                            if val is None:
                                continue
                            val_str = str(val).strip()
                            try:
                                credit = float(val_str)
                                if 0 < credit <= 6:
                                    active.append((y, s))
                                    if first_credit is None:
                                        first_credit = int(credit)
                                    next_i = col_i + 1
                                    next_next_i = col_i + 2
                                    if (next_i < len(row)
                                            and row[next_i] is None
                                            and (next_next_i >= len(row) or row[next_next_i] is not None)
                                            and rel_idx + 1 in REL_TO_YS):
                                        active.append(REL_TO_YS[rel_idx + 1])
                            except ValueError:
                                pass

                        if not active:
                            continue

                        entry = {
                            "year_level": active[0][0],
                            "semester":   active[0][1],
                            "all":        active,
                            "credits":    first_credit,
                        }

                        if code:
                            semester_map[code] = entry
                        norm = _normalize_name(name_raw)
                        if norm:
                            semester_map[norm] = entry

    except Exception as e:
        print(f"  ⚠️  pdfplumber 學期偵測失敗: {e}")

    return semester_map


# ── 低可信度判斷 ────────────────────────────────────────────────

def _is_low_confidence(entry: dict, key_type: str) -> bool:
    if len(entry.get("all", [])) > 3:
        return True
    if key_type == "name":
        return True
    return False


# ── 主流程 ─────────────────────────────────────────────────────

def process_pdf(pdf_path: Path) -> dict:
    result = {
        "pdf": pdf_path.name,
        "courses": [],
        "low_confidence_count": 0,
        "total": 0,
        "error": None,
    }

    try:
        semester_map = extract_semester_map(pdf_path)
    except Exception as e:
        result["error"] = str(e)
        return result

    if not semester_map:
        result["error"] = "pdfplumber 未偵測到學期欄位（可能是掃描圖 PDF 或表格格式特殊）"
        return result

    code_pattern = re.compile(r'^[A-Z]{2,4}\d{4}$')
    seen_codes: set = set()

    for key, entry in semester_map.items():
        key_type = "code" if code_pattern.match(key) else "name"

        if key_type == "code":
            if key in seen_codes:
                continue
            seen_codes.add(key)

        low_conf = _is_low_confidence(entry, key_type)

        course_entry: dict = {
            "key":          key,
            "key_type":     key_type,
            "year_level":   entry["year_level"],
            "semester":     entry["semester"],
            "credits":      entry.get("credits"),
            "low_confidence": low_conf,
        }
        if len(entry.get("all", [])) > 1:
            course_entry["spans_semesters"] = entry["all"]

        result["courses"].append(course_entry)
        if low_conf:
            result["low_confidence_count"] += 1

    result["total"] = len(result["courses"])
    return result


def main():
    pdfs = sorted(REQUIREMENTS_DIR.rglob("*.pdf"))
    if not pdfs:
        print(f"❌ 找不到 PDF：{REQUIREMENTS_DIR}")
        return

    print(f"找到 {len(pdfs)} 個 PDF，開始處理...\n")

    existing: dict = {}
    if OUTPUT_PATH.exists():
        try:
            with OUTPUT_PATH.open(encoding="utf-8") as f:
                existing = json.load(f)
            print(f"  已有 {len(existing)} 筆舊結果，跳過已處理的系所\n")
        except Exception:
            existing = {}

    all_results = dict(existing)

    for i, pdf_path in enumerate(pdfs, 1):
        dept_name = normalize_dept_name(pdf_path.stem)

        if dept_name in all_results:
            print(f"  [{i:02d}/{len(pdfs)}] ⏭  跳過（已處理）：{dept_name}")
            continue

        print(f"  [{i:02d}/{len(pdfs)}] 處理：{dept_name} ({pdf_path.name})")
        dept_result = process_pdf(pdf_path)

        total = dept_result["total"]
        lc    = dept_result["low_confidence_count"]
        err   = dept_result["error"]

        if err:
            print(f"         ⚠️  {err}")
        else:
            print(f"         ✅ {total} 門課，{lc} 筆需確認")

        all_results[dept_name] = dept_result

        OUTPUT_PATH.write_text(
            json.dumps(all_results, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    total_depts   = len(all_results)
    total_courses = sum(v["total"] for v in all_results.values())
    total_lc      = sum(v["low_confidence_count"] for v in all_results.values())
    error_depts   = [k for k, v in all_results.items() if v.get("error")]

    print(f"\n{'='*50}")
    print(f"完成！共 {total_depts} 個系所，{total_courses} 筆課程記錄")
    print(f"需人工確認：{total_lc} 筆")
    if error_depts:
        print(f"解析失敗（需手動處理）：{', '.join(error_depts)}")
    print(f"輸出：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()
