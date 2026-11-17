"""
Step 4: 應修科目表解析
從 應修科目表/*.pdf 提取各年級必選修課程與學分要求。

策略：
  1. PyMuPDF 提取文字（不需要 poppler）
  2. GPT-4o text mode 整理成結構化 JSON（比 Vision 便宜且準確）
  3. 文字為空（掃描圖 PDF）→ fallback Vision API

相依套件：
  pip install pymupdf openai python-dotenv

輸出：data/processed/requirements_structured.json
"""

import os
import json
import base64
import re
import time
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / ".env")

REQUIREMENTS_DIR = BASE_DIR / "data" / "raw" / "應修科目表"
OUTPUT_PATH      = BASE_DIR / "data" / "processed" / "requirements_structured.json"

DEPT_ALIASES = {
    "地科院學士班": "地球科學學院學士班",
}


# ============================================================
# 工具函式
# ============================================================

def normalize_dept_name(stem: str) -> str:
    name = re.sub(r'_\d{3}$', '', stem)
    return DEPT_ALIASES.get(name, name)


def get_client():
    azure_key      = os.getenv("AZURE_OPENAI_API_KEY", "")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    openai_key     = os.getenv("OPENAI_API_KEY", "")

    if azure_key and azure_endpoint:
        from openai import AzureOpenAI
        return AzureOpenAI(
            api_key=azure_key,
            azure_endpoint=azure_endpoint,
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
        ), os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o")
    elif openai_key:
        from openai import OpenAI
        return OpenAI(api_key=openai_key), "gpt-4o"
    else:
        raise ValueError("請在 .env 設定 OPENAI_API_KEY 或 AZURE_OPENAI_API_KEY")


# ============================================================
# 步驟一：PyMuPDF 文字提取
# ============================================================

def extract_text_with_pymupdf(pdf_path: Path) -> str:
    """用 PyMuPDF 提取 PDF 所有頁面的文字，合併成一個字串。"""
    import fitz
    doc = fitz.open(str(pdf_path))
    pages_text = []
    for page in doc:
        text = page.get_text()
        if text.strip():
            pages_text.append(text)
    doc.close()
    return "\n".join(pages_text)


# ============================================================
# 步驟一補充：pdfplumber 學期欄位偵測
# ============================================================

def _extract_code(text: str) -> str | None:
    """從課程名稱字串中提取第一個課號（如 IM1001）。"""
    m = re.search(r'[A-Z]{2,4}\d{4}', text or "")
    return m.group(0) if m else None


def _normalize_name(text: str) -> str:
    """標準化課程名稱：去除課號、空白、標點，方便比對。"""
    text = re.sub(r'[A-Z]{2,4}\d{4}', '', text or "")
    text = re.sub(r'[/\s\-Ⅱ\u0020-\u002F\u003A-\u0040]+', '', text)
    return text.strip()


def extract_semester_map(pdf_path: Path) -> dict[str, dict]:
    """
    用 pdfplumber 提取課程與學期的對應關係。
    回傳 {課號或標準化課名: {"year_level": int, "semester": int, "all": [(y,s),...]}}

    欄位結構（固定）：
      col0=科目分類, col1=課名課號, col2=None,
      col3=大一上, col4=大一下, col5=大二上, col6=大二下,
      col7=大三上, col8=大三下, col9=大四上, col10=大四下
    """
    try:
        import pdfplumber
    except ImportError:
        return {}

    # 相對學期索引 → (year_level, semester)
    REL_TO_YS = {
        0: (1, 1), 1: (1, 2),
        2: (2, 1), 3: (2, 2),
        4: (3, 1), 5: (3, 2),
        6: (4, 1), 7: (4, 2),
    }

    semester_map: dict[str, dict] = {}

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
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
                        continue  # 這張表沒有學期欄，跳過

                    for row in table:
                        if row is None:
                            continue

                        # 在任意欄位尋找課號（最可靠的識別鍵）
                        code = None
                        for cell in row:
                            c = _extract_code(str(cell or ""))
                            if c:
                                code = c
                                break

                        # 若無課號，從 col1/col2/col3 找課名（排除分類標題）
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

                        # 學期偵測：
                        #   - 有學分值（1–6）→ 該學期 active
                        #   - 緊跟 1 個 None → 水平合併（如國文 '5',None,''）→ 延伸到下一格
                        #   - 連續 2+ 個 None → 縱向合併（如文學院課群）→ 忽略
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
                                    # 檢查是否為水平合併（下一格恰好為 None，且再下一格不是 None）
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

                        # 用前面掃全行找到的 code 儲存（不覆蓋 code 變數）
                        if code:
                            semester_map[code] = entry
                        # 也用標準化課名儲存（供無課號的課程比對）
                        norm = _normalize_name(name_raw)
                        if norm:
                            semester_map[norm] = entry

    except Exception as e:
        print(f"  ⚠️  pdfplumber 學期偵測失敗: {e}")

    return semester_map


def merge_semester_info(courses: list[dict], semester_map: dict) -> list[dict]:
    """
    將 pdfplumber 的學期資訊合併進 LLM 解析的課程清單。
    以課號優先比對，次以標準化課名比對。
    """
    if not semester_map:
        return courses

    for course in courses:
        if course.get("year_level") and course.get("semester"):
            continue  # 已有資料，不覆蓋

        matched = None

        # 1. 用課號比對
        code = course.get("code")
        if code:
            # 課號可能含 " / " 分隔多個，取第一個
            first_code = re.split(r'[\s/]+', code)[0].strip()
            matched = semester_map.get(first_code)

        # 2. 用標準化課名比對
        if not matched:
            norm = _normalize_name(course.get("name", ""))
            matched = semester_map.get(norm)

        if matched:
            course["year_level"] = matched["year_level"]
            course["semester"]   = matched["semester"]
            if len(matched["all"]) > 1:
                course["spans_semesters"] = matched["all"]
            # 補學分（只在 LLM 沒抓到時覆蓋）
            if not course.get("credits") and matched.get("credits"):
                course["credits"] = matched["credits"]

    return courses


# ============================================================
# 步驟二：GPT-4o text mode 解析
# ============================================================

LLM_PARSE_PROMPT = """你是一個大學課程規劃分析專家。以下是從 PDF 應修科目表提取的原始文字，
格式可能雜亂（因表格合併儲存格導致欄位位置亂掉），但課程名稱、課號、學分數、分類等資訊都在裡面。

請仔細分析並輸出結構化 JSON，**只回傳 JSON，不加任何說明**。

---

判斷 table_type：
- "single_track"：一般系所，課程分為共同必修、院訂必修、系訂必修、選修
- "multi_track"：學士班或跨域學程，有多個主修課群（學生需從中選修一個方向）

---

單軌型格式（single_track）：
```json
{
  "department": "系所名稱",
  "academic_year": 114,
  "table_type": "single_track",
  "graduation_requirements": {
    "total_credits": 128,
    "required_credits": 80,
    "notes": "其他畢業規定文字"
  },
  "courses": [
    {
      "name": "課程名稱",
      "code": "IM1001",
      "credits": 3,
      "category": "系訂必修",
      "year_level": 1,
      "semester": 1,
      "track": null
    }
  ],
  "rules_text": "備註與特殊規定的完整文字"
}
```

多軌型格式（multi_track）：
```json
{
  "department": "系所名稱",
  "academic_year": 114,
  "table_type": "multi_track",
  "graduation_requirements": {
    "total_credits": 128,
    "notes": "畢業規定文字"
  },
  "track_rule": {
    "type": "choose_at_least_one",
    "min_credits_per_track": 27,
    "description": "規則說明"
  },
  "tracks": ["課群名稱A", "課群名稱B", "課群名稱C"],
  "courses": [
    {
      "name": "課程名稱",
      "code": "PD1101",
      "credits": 3,
      "category": "基礎課程",
      "year_level": null,
      "semester": null,
      "track": null
    },
    {
      "name": "課群專屬課程",
      "code": "PD2203",
      "credits": 3,
      "category": "專業課程",
      "year_level": null,
      "semester": null,
      "track": "課群名稱A"
    }
  ],
  "rules_text": "備註與特殊規定的完整文字"
}
```

規則：
1. category 值：「共同必修」/「院訂必修」/「系訂必修」/「基礎課程」/「專業課程」/「應用課程」/「選修」
2. year_level（1-4）和 semester（1 或 2）：若能從文字判斷就填，不確定則設 null
3. code：課號格式通常是 2-4 個英文字母 + 4 個數字（如 IM1001），找到就填，無則 null
4. credits：數字，不確定設 null
5. multi_track 的課程要正確歸屬到對應的 track；共同必修/基礎課程 track 設 null
6. rules_text：把備註、特殊規定、雙主修規定等文字完整保留

---

系所名稱：{dept_name}

原始文字：
{raw_text}
"""


def parse_with_llm(raw_text: str, dept_name: str, client, model: str) -> dict | None:
    """送 GPT-4o text mode 解析應修科目表文字。"""
    prompt = (LLM_PARSE_PROMPT
              .replace("{dept_name}", dept_name)
              .replace("{raw_text}", raw_text[:8000]))

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8192,
            temperature=0,
        )

        content = response.choices[0].message.content.strip()

        # 移除 markdown code block
        if "```" in content:
            # 取第一個 ``` 到最後一個 ``` 之間的內容
            start = content.find("```") + 3
            end = content.rfind("```")
            content = content[start:end].strip()
            if content.startswith("json"):
                content = content[4:].strip()

        return json.loads(content)

    except json.JSONDecodeError as e:
        print(f"    ⚠️  JSON 解析失敗: {e}")
        print(f"    原始回應（前300字）: {content[:300]}")
        return {"department": dept_name, "source": "llm_parse_error", "courses": [], "raw_response": content}
    except Exception as e:
        print(f"    ❌ LLM 呼叫失敗: {e}")
        return None


# ============================================================
# Fallback：Vision API（掃描圖 PDF）
# ============================================================

VISION_FALLBACK_PROMPT = """
請分析這張應修科目表圖片，提取所有課程資訊。**只回傳 JSON，不加任何說明。**

{
  "department": "系所名稱",
  "academic_year": 114,
  "table_type": "single_track",
  "graduation_requirements": {
    "total_credits": 128,
    "required_credits": 80,
    "notes": ""
  },
  "tracks": [],
  "track_rule": null,
  "courses": [
    {
      "name": "課程名稱",
      "code": "課號或null",
      "credits": 3,
      "category": "系訂必修",
      "year_level": 1,
      "semester": 1,
      "track": null
    }
  ],
  "rules_text": "備註文字"
}
"""


def extract_with_vision(pdf_path: Path, dept_name: str, client, model: str) -> dict | None:
    """掃描圖 PDF fallback：轉圖片後用 Vision API。"""
    import fitz
    import io

    doc = fitz.open(str(pdf_path))
    all_courses = []
    grad_req = {}

    for i, page in enumerate(doc):
        if i >= 3:
            break
        print(f"    📄 Vision 處理第 {i+1} 頁...")

        mat = fitz.Matrix(150 / 72, 150 / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")

        prompt = VISION_FALLBACK_PROMPT.replace('"department": "系所名稱"', f'"department": "{dept_name}"')

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {
                            "url": f"data:image/png;base64,{img_b64}",
                            "detail": "high"
                        }},
                    ],
                }],
                max_tokens=4096,
                temperature=0,
            )

            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])
                if content.startswith("json"):
                    content = content[4:]

            page_data = json.loads(content)
            all_courses.extend(page_data.get("courses", []))
            if page_data.get("graduation_requirements"):
                grad_req = page_data["graduation_requirements"]

        except Exception as e:
            print(f"    ⚠️  Vision 失敗: {e}")

        time.sleep(1)

    doc.close()

    if not all_courses:
        return None

    return {
        "department": dept_name,
        "source": "vision_api",
        "graduation_requirements": grad_req,
        "courses": all_courses,
    }


# ============================================================
# 主流程
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="應修科目表解析（PyMuPDF + GPT-4o text mode）")
    parser.add_argument("--dept", help="只處理特定系所（部分名稱即可）", default=None)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--vision-only", action="store_true", help="強制使用 Vision API")
    args = parser.parse_args()

    existing_results = {}
    if OUTPUT_PATH.exists():
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            existing_results = json.load(f)

    client = None
    model = None

    pdf_files = sorted(REQUIREMENTS_DIR.rglob("*.pdf"))
    if args.dept:
        pdf_files = [f for f in pdf_files if args.dept in f.stem]

    print(f"找到 {len(pdf_files)} 個應修科目表 PDF")

    results = dict(existing_results)

    for i, pdf_path in enumerate(pdf_files):
        dept_name = normalize_dept_name(pdf_path.stem)
        print(f"\n[{i+1}/{len(pdf_files)}] {dept_name}（{pdf_path.name}）")

        if args.skip_existing and dept_name in results:
            print("  ✅ 已有結果，略過")
            continue

        if client is None:
            try:
                client, model = get_client()
                print(f"  使用模型：{model}")
            except ValueError as e:
                print(f"  ❌ {e}")
                return

        result = None

        if not args.vision_only:
            # 步驟一：PyMuPDF 文字提取
            print("  📄 PyMuPDF 提取文字...")
            raw_text = extract_text_with_pymupdf(pdf_path)

            if raw_text.strip():
                char_count = len(raw_text)
                print(f"  ✅ 提取到 {char_count} 字元，送 LLM 解析...")
                result = parse_with_llm(raw_text, dept_name, client, model)
                if result:
                    result["source"] = "pymupdf+llm"
                    # 用 pdfplumber 補學期資訊
                    if result.get("table_type") in ("single_track", "multi_track"):
                        print("  📅 pdfplumber 補學期資訊...")
                        sem_map = extract_semester_map(pdf_path)
                        if sem_map:
                            result["courses"] = merge_semester_info(result.get("courses", []), sem_map)
                            filled = sum(1 for c in result["courses"] if c.get("semester"))
                            print(f"     → 補齊 {filled}/{len(result['courses'])} 門課程的學期")
                    course_count = len(result.get("courses", []))
                    table_type = result.get("table_type", "unknown")
                    print(f"  ✅ 解析完成：{table_type}，{course_count} 門課程")
            else:
                print("  ⚠️  文字為空（掃描圖 PDF），改用 Vision API...")

        # Fallback：Vision API
        if result is None:
            print("  🖼️  使用 Vision API...")
            result = extract_with_vision(pdf_path, dept_name, client, model)
            if result:
                print(f"  ✅ Vision 成功，{len(result.get('courses', []))} 門課程")
            else:
                print(f"  ❌ 提取失敗")
                result = {"department": dept_name, "source": "failed", "courses": []}

        results[dept_name] = result

        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        time.sleep(0.5)

    print("\n" + "=" * 60)
    total_courses = sum(len(v.get("courses", [])) for v in results.values())
    success = sum(1 for v in results.values() if v.get("source") not in ("failed", None))
    print(f"成功解析：{success}/{len(results)} 個系所")
    print(f"課程總數：{total_courses}")
    print(f"\n✅ 結果已儲存至：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()
