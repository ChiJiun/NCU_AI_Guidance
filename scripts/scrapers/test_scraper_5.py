"""
測試爬蟲 - 只爬第一個未爬過系所的前 5 筆課程
"""
import sys, os, json, time, re
sys.path.insert(0, os.path.dirname(__file__))

from selenium.webdriver.common.by import By
from ncu_course_scraper_v2 import NCUCourseScraperV2

OUTPUT_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'raw', 'courses')

scraper = NCUCourseScraperV2(year="114", semester="1")
scraper.output_dir = os.path.normpath(os.path.join(OUTPUT_BASE, "114_1"))

try:
    scraper.navigate_to_course_page()

    # 找第一個還沒爬過的系所
    tables = scraper.driver.find_elements(By.TAG_NAME, "table")
    dept_table = tables[-1]
    rows = dept_table.find_elements(By.TAG_NAME, "tr")

    target_row = None
    for row in rows[1:]:
        cells = row.find_elements(By.TAG_NAME, "td")
        if len(cells) < 3:
            continue
        college = cells[0].text.strip()
        dept_name = cells[1].text.strip()
        full_name = f"{college}_{dept_name}"
        if not scraper.dept_already_scraped(full_name):
            target_row = row
            target_college = college
            target_dept = dept_name
            break

    if not target_row:
        print("所有系所都已爬完！")
    else:
        print(f"\n測試系所：{target_college}_{target_dept}")
        dept_list_url = scraper.driver.current_url
        target_row.find_element(By.TAG_NAME, "a").click()
        time.sleep(3)

        # 只爬前 5 筆課程
        tables = scraper.driver.find_elements(By.TAG_NAME, "table")
        course_table = max(tables, key=lambda t: len(t.find_elements(By.TAG_NAME, "tr")))
        rows = course_table.find_elements(By.TAG_NAME, "tr")

        courses = []
        for i in range(1, min(6, len(rows))):  # 最多 5 筆
            tables = scraper.driver.find_elements(By.TAG_NAME, "table")
            course_table = max(tables, key=lambda t: len(t.find_elements(By.TAG_NAME, "tr")))
            rows = course_table.find_elements(By.TAG_NAME, "tr")
            row = rows[i]
            cells = row.find_elements(By.TAG_NAME, "td")

            course_data = {"學院": target_college, "系所": target_dept}
            if len(cells) > 0: course_data.update(scraper.split_serial_course(cells[0].text))
            if len(cells) > 1: course_data.update(scraper.split_name_note(cells[1].text))
            if len(cells) > 2: course_data["授課教師"] = cells[2].text.strip()

            # 課程綱要
            try:
                outline_link = cells[9].find_element(By.TAG_NAME, "a")
                outline_detail = scraper.get_detail_by_click(outline_link, "課程綱要")
                course_data["課程綱要"] = outline_detail
            except:
                course_data["課程綱要"] = {}

            courses.append(course_data)
            print(f"  [{i}] {course_data.get('課程名稱(中文)', '?')} — 核心能力數: {len(course_data['課程綱要'].get('核心能力', []))}")

        # 輸出結果
        out_path = "test_output_5courses.json"
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(courses, f, ensure_ascii=False, indent=2)
        print(f"\n✓ 已儲存至 {out_path}")

        # 印出第一筆的課程綱要供檢查
        if courses and courses[0].get('課程綱要'):
            outline = courses[0]['課程綱要']
            print(f"\n--- 第一筆課程綱要欄位 ---")
            for k, v in outline.items():
                if k == '核心能力':
                    print(f"  核心能力: {len(v)} 筆")
                    for ab in v[:2]:
                        print(f"    {ab}")
                else:
                    print(f"  {k}: {str(v)[:60]}")

finally:
    scraper.close()
