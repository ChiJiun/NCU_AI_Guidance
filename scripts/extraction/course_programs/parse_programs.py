"""
Step 5: 學分學程資料解析
1. 直接解析 學分學程/學分學程.js（JSON 結構）
2. 可選：解析 PDF 補充資訊

輸出：data/processed/programs_structured.json
"""

import json
import re
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]

JS_FILE     = BASE_DIR / "data" / "raw" / "學分學程" / "學分學程.js"
PROGRAMS_DIR = BASE_DIR / "data" / "raw" / "學分學程"
COURSES_RAW  = BASE_DIR / "data" / "raw" / "courses"
OUTPUT_PATH  = BASE_DIR / "data" / "processed" / "programs_structured.json"

# 學院目錄對應（子目錄名稱 → 標準學院名稱）
COLLEGE_DIR_MAP = {
    "工學院":             "工學院",
    "生醫理工學院":        "生醫理工學院",
    "地科學院":           "地球科學學院",
    "客家學院":           "客家學院",
    "教務處":             "教務處",
    "理學院":             "理學院",
    "通識中心":           "通識中心",
    "資電學院":           "資訊電機學院",
    "管理學院":           "管理學院",
    "語言中心":           "語言中心",
    "臺灣大專院校人工智慧學程聯盟TAICA": "TAICA",
}


# ============================================================
# 解析 .js 檔案
# ============================================================

def parse_js_file(js_path: Path) -> list[dict]:
    """
    解析 學分學程.js。
    格式：const programs = [ ... ]  或  var programs = [ ... ]
    """
    content = js_path.read_text(encoding="utf-8")

    # 提取 JSON array 部分
    # 支援 const/var/let programs = [...]
    match = re.search(r'(?:const|var|let)\s+\w+\s*=\s*(\[.*\])', content, re.DOTALL)
    if not match:
        # 嘗試直接解析（可能整個檔案就是 JSON array）
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            raise ValueError(f"無法解析 JS 檔案：{js_path}")

    json_str = match.group(1)

    # 清理 JS 特有語法（trailing comma、單引號等）
    # 移除行尾的多餘逗號（JSON 不允許）
    json_str = re.sub(r',\s*([}\]])', r'\1', json_str)

    return json.loads(json_str)


# ============================================================
# 掃描 PDF 目錄，取得學程的學院分類
# ============================================================

def scan_programs_directory() -> dict[str, dict]:
    """
    掃描 學分學程/ 的子目錄，建立學程名稱 → 學院的對應。
    回傳 { "「人工智慧跨域應用」學分學程": { "college": "通識中心", "pdf_path": "..." } }
    """
    program_meta = {}
    for subdir in PROGRAMS_DIR.iterdir():
        if not subdir.is_dir():
            continue
        college = COLLEGE_DIR_MAP.get(subdir.name, subdir.name)
        for pdf in subdir.glob("*.pdf"):
            program_meta[pdf.stem] = {
                "college": college,
                "pdf_path": str(pdf),
            }
    return program_meta


# ============================================================
# 比對學分學程的課程代碼與現有課程資料
# ============================================================

def build_course_code_index() -> dict[str, dict]:
    """
    從 data/raw/courses/ 建立課號索引：
    { "CE1001": { "name": "計算機概論Ⅰ", "dept": "資訊工程學系", ... } }
    """
    index = {}
    for semester_dir in COURSES_RAW.iterdir():
        if not semester_dir.is_dir():
            continue
        for json_file in semester_dir.glob("*.json"):
            try:
                courses = json.loads(json_file.read_text(encoding="utf-8"))
                for course in courses:
                    raw_code = course.get("課號-班別", "")
                    # 取課號主體（去掉班別，如 CE1001-A → CE1001）
                    code = raw_code.split("-")[0].strip() if raw_code else None
                    if code and code not in index:
                        index[code] = {
                            "name": course.get("課程名稱(中文)", ""),
                            "dept": course.get("系所", ""),
                            "college": course.get("學院", ""),
                            "credits": int(course.get("學分", 0) or 0),
                        }
            except Exception:
                continue
    return index


def match_program_courses(
    program_courses: list[dict], code_index: dict[str, dict]
) -> list[dict]:
    """
    為學程的每門課程找到對應的課程資訊。
    回傳增強後的課程清單。
    """
    enriched = []
    for course in program_courses:
        code = course.get("code", "").strip()
        matched = code_index.get(code, {})

        enriched.append({
            "code": code,
            "name": course.get("name", ""),
            "school": course.get("school", ""),
            # 從課程索引補充資訊
            "matched_name": matched.get("name", ""),
            "dept": matched.get("dept", ""),
            "college": matched.get("college", ""),
            "credits": matched.get("credits"),
            "matched": bool(matched),
        })
    return enriched


# ============================================================
# 主流程
# ============================================================

def main():
    print("📂 解析 學分學程.js...")
    programs_raw = parse_js_file(JS_FILE)
    print(f"   找到 {len(programs_raw)} 個學分學程")

    print("\n📂 掃描學程 PDF 目錄...")
    program_meta = scan_programs_directory()
    print(f"   PDF 目錄中找到 {len(program_meta)} 個學程")

    print("\n📂 建立課程代碼索引...")
    code_index = build_course_code_index()
    print(f"   課程代碼索引：{len(code_index)} 個")

    print("\n🔗 整合資料...")
    results = []
    match_count = 0
    total_course_count = 0

    for prog in programs_raw:
        name = prog.get("name", "").strip()
        description = prog.get("description", "")
        courses_raw = prog.get("courses", [])

        # 比對課程代碼
        enriched_courses = match_program_courses(courses_raw, code_index)
        matched = sum(1 for c in enriched_courses if c["matched"])
        match_count += matched
        total_course_count += len(enriched_courses)

        # 尋找 PDF 對應的學院
        college = "未知"
        pdf_path = None
        # 嘗試模糊匹配學程名稱
        for pdf_stem, meta in program_meta.items():
            if name in pdf_stem or pdf_stem in name:
                college = meta["college"]
                pdf_path = meta["pdf_path"]
                break

        results.append({
            "name": name,
            "description": description,
            "college": college,
            "pdf_path": pdf_path,
            "course_count": len(enriched_courses),
            "matched_course_count": matched,
            "courses": enriched_courses,
        })

    # 統計
    print(f"\n{'=' * 50}")
    print(f"學分學程總數：{len(results)}")
    print(f"課程總數：{total_course_count}")
    print(f"成功比對課程：{match_count}/{total_course_count} "
          f"({match_count/total_course_count*100:.1f}%)" if total_course_count else "")

    # 學院分布
    from collections import Counter
    college_dist = Counter(p["college"] for p in results)
    print("\n學院分布：")
    for college, count in college_dist.most_common():
        print(f"  {college}：{count} 個學程")

    # 輸出
    output = {
        "summary": {
            "total_programs": len(results),
            "total_courses": total_course_count,
            "matched_courses": match_count,
        },
        "programs": results,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 結果已儲存至：{OUTPUT_PATH}")

    # 顯示前幾個學程範例
    print("\n範例（前3個學程）：")
    for prog in results[:3]:
        print(f"  📚 {prog['name']} ({prog['college']})")
        print(f"     課程數：{prog['course_count']}，比對成功：{prog['matched_course_count']}")
        for c in prog['courses'][:3]:
            status = "✅" if c["matched"] else "❓"
            print(f"     {status} {c['code']} {c['name']}")
        if prog['course_count'] > 3:
            print(f"     ... 還有 {prog['course_count'] - 3} 門")


if __name__ == "__main__":
    main()
