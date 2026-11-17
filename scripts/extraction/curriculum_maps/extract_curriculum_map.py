"""
Step 3: 課程地圖結構化提取（GPT-4o Vision）
讀取 curriculum_maps_png/ 的 PNG，
批次送 Azure OpenAI / OpenAI Vision API，
提取每學期的課程清單與先修關係。

相依套件：
  pip install openai pillow python-dotenv

輸出：data/processed/curriculum_map_structured.json
"""

import os
import json
import base64
import time
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / ".env")

PNG_DIR     = BASE_DIR / "data" / "processed" / "curriculum_maps_png"
OUTPUT_PATH = BASE_DIR / "data" / "processed" / "curriculum_map_structured.json"

# ============================================================
# OpenAI 客戶端初始化
# ============================================================

def get_client():
    """自動選擇 Azure OpenAI 或標準 OpenAI"""
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
        raise ValueError("請在 .env 設定 AZURE_OPENAI_API_KEY 或 OPENAI_API_KEY")


# ============================================================
# Vision Prompt
# ============================================================

EXTRACTION_PROMPT = """
你是一個課程地圖分析專家。請仔細分析這張大學科系課程地圖圖片，提取以下資訊。

**請回傳 JSON 格式，不要加任何說明文字。**

{
  "department": "系所名稱",
  "map_type": "flowchart",
  "semesters": [
    {
      "year": 1,
      "semester": 1,
      "courses": [
        {
          "name": "課程名稱",
          "credits": 3,
          "type": "必修",
          "code": "課號（如有）"
        }
      ]
    }
  ],
  "prerequisites": [
    {
      "from": "前置課程名稱",
      "to": "後續課程名稱",
      "confidence": 0.9
    }
  ],
  "career_paths": {
    "structured": ["職稱或產業1", "職稱或產業2"],
    "description": "關於職涯方向的完整描述文字",
    "industries": ["產業類別1", "產業類別2"]
  },
  "notes": "任何特殊說明或無法確定的部分"
}

規則：
1. year 從 1 開始（大一、大二...），semester 為 1 或 2
2. type 為「必修」、「選修」或「通識」
3. prerequisites 根據圖中的箭頭或明顯的先後順序判斷
4. confidence 表示先修關係的確定程度（0-1）
5. 若圖片中沒有明確箭頭，prerequisites 設為空陣列 []，不要推斷
6. 若某些資訊不清楚，courses 的 code 或 credits 可設為 null
7. map_type 判斷：
   - "flowchart"：有學期欄位（大一上/下...）且課程間有箭頭
   - "infographic"：無箭頭，課程依研究群或專業方向分組
   - "flow"：從左到右的群組流程（基礎→進階），無課程層級箭頭
8. career_paths：從圖中「未來發展」、「職涯方向」、「就業方向」等區塊提取；
   structured 列出明確的職稱或產業名稱清單；若圖中無此區塊，設為空陣列/空字串
"""


def encode_image_to_base64(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def extract_from_image(
    client, model: str, image_path: Path, dept_name: str
) -> dict | None:
    """對單張圖片呼叫 Vision API"""
    image_b64 = encode_image_to_base64(image_path)

    prompt_with_dept = EXTRACTION_PROMPT.replace(
        '"department": "系所名稱"',
        f'"department": "{dept_name}"'
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt_with_dept},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_b64}",
                                "detail": "high"
                            },
                        },
                    ],
                }
            ],
            max_tokens=4096,
            temperature=0,
        )

        content = response.choices[0].message.content.strip()

        # 解析 JSON（移除可能的 markdown code block）
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        return json.loads(content)

    except json.JSONDecodeError as e:
        print(f"    ⚠️  JSON 解析失敗: {e}")
        print(f"    原始回應（前500字）: {content[:500]}")
        return {"department": dept_name, "raw_response": content, "error": "json_parse_error"}
    except Exception as e:
        print(f"    ❌ API 呼叫失敗: {e}")
        return None


# ============================================================
# 主流程
# ============================================================

def get_dept_name_from_stem(stem: str) -> str:
    """從檔案 stem 取得系所名稱（移除頁碼後綴）"""
    # 移除 _p1, _p2 等頁碼後綴
    import re
    return re.sub(r'_p\d+$', '', stem)


def group_pages_by_dept(png_dir: Path) -> dict[str, list[Path]]:
    """將同一系所的多頁 PNG 歸組"""
    groups: dict[str, list[Path]] = {}
    for png in sorted(png_dir.glob("*.png")):
        dept = get_dept_name_from_stem(png.stem)
        groups.setdefault(dept, []).append(png)
    return groups


def merge_multipage_results(results: list[dict]) -> dict:
    """
    合併同一系所多頁的結果
    （第一頁通常包含完整地圖，後續頁可能是補充）
    """
    if not results:
        return {}
    if len(results) == 1:
        return results[0]

    merged = results[0].copy()
    merged["semesters"] = []
    merged["prerequisites"] = []

    seen_course_names = set()
    for result in results:
        for sem in result.get("semesters", []):
            # 合併學期（避免重複）
            existing_sem = next(
                (s for s in merged["semesters"]
                 if s.get("year") == sem.get("year") and
                    s.get("semester") == sem.get("semester")),
                None
            )
            if existing_sem is None:
                merged["semesters"].append(sem)
            else:
                # 加入新課程
                for course in sem.get("courses", []):
                    if course["name"] not in seen_course_names:
                        existing_sem["courses"].append(course)
                        seen_course_names.add(course["name"])

        # 合併先修關係
        for prereq in result.get("prerequisites", []):
            if prereq not in merged["prerequisites"]:
                merged["prerequisites"].append(prereq)

    return merged


def main():
    import argparse
    parser = argparse.ArgumentParser(description="課程地圖 Vision API 提取")
    parser.add_argument("--dept", help="只處理特定系所（部分名稱即可）", default=None)
    parser.add_argument("--skip-existing", action="store_true", help="略過已有結果的系所")
    args = parser.parse_args()

    # 載入已有結果（增量處理）
    existing_results = {}
    if OUTPUT_PATH.exists():
        with open(OUTPUT_PATH, encoding="utf-8") as f:
            existing_results = json.load(f)

    print("初始化 OpenAI 客戶端...")
    client, model = get_client()

    print(f"使用模型：{model}")

    if not PNG_DIR.exists():
        print(f"❌ PNG 目錄不存在：{PNG_DIR}")
        print("   請先執行 scripts/convert_to_png.py")
        return

    dept_groups = group_pages_by_dept(PNG_DIR)
    print(f"找到 {len(dept_groups)} 個系所的課程地圖")

    # 篩選
    if args.dept:
        dept_groups = {
            k: v for k, v in dept_groups.items()
            if args.dept in k
        }
        print(f"篩選後：{len(dept_groups)} 個系所")

    results = dict(existing_results)
    failed = []

    for i, (dept_name, png_files) in enumerate(sorted(dept_groups.items())):
        print(f"\n[{i+1}/{len(dept_groups)}] 處理：{dept_name}")

        if args.skip_existing and dept_name in results:
            print(f"  ✅ 已有結果，略過")
            continue

        page_results = []
        for j, png_path in enumerate(png_files):
            print(f"  📄 第 {j+1}/{len(png_files)} 頁：{png_path.name}")
            result = extract_from_image(client, model, png_path, dept_name)

            if result:
                page_results.append(result)
                print(f"     ✅ 提取成功")
                if "semesters" in result:
                    total_courses = sum(
                        len(s.get("courses", []))
                        for s in result.get("semesters", [])
                    )
                    print(f"     課程數：{total_courses}，先修關係：{len(result.get('prerequisites', []))}")
            else:
                print(f"     ❌ 提取失敗")
                failed.append(f"{dept_name}_p{j+1}")

            # 避免 API rate limit
            time.sleep(1)

        if page_results:
            results[dept_name] = merge_multipage_results(page_results)

        # 每處理完一個系所就儲存（避免中途失敗遺失資料）
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

    # 最終統計
    print("\n" + "=" * 60)
    print("提取完成！")
    total_depts = len(results)
    total_courses = sum(
        sum(len(s.get("courses", [])) for s in v.get("semesters", []))
        for v in results.values()
    )
    total_prereqs = sum(
        len(v.get("prerequisites", []))
        for v in results.values()
    )
    print(f"系所數：{total_depts}")
    print(f"課程總數：{total_courses}")
    print(f"先修關係總數：{total_prereqs}")

    if failed:
        print(f"\n失敗項目（{len(failed)} 個）：")
        for item in failed:
            print(f"  ❌ {item}")

    print(f"\n✅ 結果已儲存至：{OUTPUT_PATH}")


if __name__ == "__main__":
    main()
