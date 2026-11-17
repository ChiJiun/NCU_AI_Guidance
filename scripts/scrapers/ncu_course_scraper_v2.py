"""
NCU 課程爬蟲 v2 - 無需登入版本
直接訪問公開課程查詢頁面
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import os
import json
import re


class NCUCourseScraperV2:
    def __init__(self, year="114", semester="1", output_dir=None, headless=False):
        self.year = year
        self.semester = semester
        self.base_url = f"https://cis.ncu.edu.tw/Course/main/query/byYears?do=showDept&semester={year}{semester}"

        chrome_options = Options()
        if headless:
            chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--start-maximized')

        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 15)

        # 輸出與舊資料路徑（相對於 project root）；資料更新管線會指定暫存輸出目錄
        _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.output_dir = output_dir or os.path.join(_root, 'data', 'raw', 'courses', f"{year}_{semester}")
        os.makedirs(self.output_dir, exist_ok=True)
        print(f"✓ 輸出資料夾：{self.output_dir}")

        # 舊資料路徑（用於跳過已爬取的系所）
        self.data_dir = self.output_dir

    def navigate_to_course_page(self):
        """直接前往課程查詢頁面（無需登入）"""
        print("=" * 60)
        print(f"前往 {self.year}-{self.semester} 課程查詢頁面")
        print("=" * 60)
        try:
            self.driver.get(self.base_url)
            time.sleep(3)
            print("✓ 已進入課程查詢頁面")
            return True
        except Exception as e:
            print(f"✗ 錯誤: {e}")
            return False

    def split_serial_course(self, text):
        """分割流水號和課號"""
        parts = text.strip().split('\n')
        return {
            "流水號": parts[0] if len(parts) > 0 else "",
            "課號-班別": parts[1] if len(parts) > 1 else ""
        }

    def split_name_note(self, text):
        """分割課程名稱、英文名稱和備註"""
        parts = text.strip().split('\n')
        return {
            "課程名稱(中文)": parts[0] if len(parts) > 0 else "",
            "課程名稱(英文)": parts[1] if len(parts) > 1 else "",
            "備註": '\n'.join(parts[2:]) if len(parts) > 2 else ""
        }

    def split_time_room(self, text):
        """分割上課時間和教室"""
        if '/' in text:
            parts = text.split('/')
            return {
                "上課時間": parts[0].strip(),
                "教室": parts[1].strip() if len(parts) > 1 else ""
            }
        return {
            "上課時間": text.strip(),
            "教室": ""
        }

    def extract_url_from_onclick(self, onclick_attr):
        """從onclick屬性中提取URL"""
        if not onclick_attr:
            return ""

        match = re.search(r"['\"]([^'\"]+)['\"]", onclick_attr)
        if match:
            path = match.group(1)
            return f"https://cis.ncu.edu.tw{path}"
        return ""

    def parse_condition_detail(self, driver_window):
        """解析分發條件的詳細欄位（從表格）"""
        result = {}

        try:
            tables = driver_window.find_elements(By.TAG_NAME, "table")

            for table in tables:
                rows = table.find_elements(By.TAG_NAME, "tr")
                if len(rows) < 2:
                    continue

                header_cells = rows[0].find_elements(By.TAG_NAME, "th")
                if not header_cells:
                    header_cells = rows[0].find_elements(By.TAG_NAME, "td")

                headers = [cell.text.strip() for cell in header_cells]

                # 優先順序表格
                if any('優先' in h for h in headers):
                    priorities = []
                    for i in range(1, len(rows)):
                        cells = rows[i].find_elements(By.TAG_NAME, "td")
                        if len(cells) >= 2:
                            priority_data = {
                                "優先順序": cells[0].text.strip(),
                                "相關條件限制說明": cells[1].text.strip()
                            }
                            priorities.append(priority_data)
                    if priorities:
                        result['優先順序列表'] = priorities

                # 先修課程表格
                if any('先修' in h for h in headers):
                    prereqs = []
                    for i in range(1, len(rows)):
                        cells = rows[i].find_elements(By.TAG_NAME, "td")
                        if cells:
                            prereq_text = ' '.join([cell.text.strip() for cell in cells])
                            if prereq_text:
                                prereqs.append(prereq_text)
                    if prereqs:
                        result['先修課程'] = prereqs

            if not result:
                colspan_cells = driver_window.find_elements(By.XPATH, "//td[@colspan='2']")
                for cell in colspan_cells:
                    text = cell.text.strip()
                    if text and text != "課程沒有限制":
                        if not any(keyword in text for keyword in ['流水號', '課號', '課程名稱', 'MN', 'PE', 'Physical', 'All-out']):
                            result['限制說明'] = text
                            break
                    elif text == "課程沒有限制":
                        result['限制說明'] = text
                        break

            if not result:
                text = driver_window.find_element(By.TAG_NAME, "body").text
                lines = text.split('\n')
                cleaned_lines = []
                for line in lines:
                    line = line.strip()
                    if line and not any(keyword in line for keyword in ['流水號', '課號', 'Physical', 'All-out', 'Education', 'Training']):
                        if not (line.isdigit() or re.match(r'^[A-Z]{2}\d{4}$', line)):
                            cleaned_lines.append(line)
                
                cleaned_text = '\n'.join(cleaned_lines).strip()
                if cleaned_text:
                    result['限制說明'] = cleaned_text[:500]
                else:
                    result['限制說明'] = "課程沒有限制"

        except Exception as e:
            result['錯誤'] = str(e)
            result['限制說明'] = "解析失敗"

        return result

    def parse_outline_detail(self, driver_window):
        """解析課程綱要的詳細欄位（從 body text + 獨立找核心能力表格）"""
        result = {}

        try:
            text = driver_window.find_element(By.TAG_NAME, "body").text

            # 第一步：找系所核心能力 table（從最近的 ancestor table 往上找，避免抓到外層容器）
            core_abilities = []
            try:
                ability_table = driver_window.find_element(
                    By.XPATH, "//th[normalize-space()='系所核心能力']/ancestor::table[1]"
                )
                for row in ability_table.find_elements(By.TAG_NAME, "tr")[1:]:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 3:
                        name = cells[0].text.strip()
                        if name:
                            core_abilities.append({
                                "能力名稱": name,
                                "強度指數": cells[1].text.strip(),
                                "評量方式": cells[2].text.strip()
                            })
            except Exception:
                pass

            # 第二步：從 body text 解析所有欄位
            lines = text.split('\n')
            current_field = None
            current_value = []

            field_keywords = ['學期', '開課單位', '流水號', '課號', '授課教師',
                            '課程名稱(中文)', '課程名稱(英文)', '課程學制', '學分',
                            '課程目標', '授課內容', '教科書/參考書', '自編教材比例',
                            '授課方式', '評量配分比重', '辦公時間', '授課週數',
                            '彈性教學說明', '課程領域', 'Office Hours', '備註']

            for line in lines:
                line = line.strip()
                if not line or '智慧財產權' in line or '侵害他人著作權' in line:
                    continue

                is_field = False
                for keyword in field_keywords:
                    if line.startswith(keyword + ' ') or line == keyword:
                        if current_field and current_value:
                            result[current_field] = '\n'.join(current_value)
                        current_field = keyword
                        value = line[len(keyword):].strip()
                        current_value = [value] if value else []
                        is_field = True
                        break

                if not is_field and current_field:
                    current_value.append(line)

            if current_field and current_value:
                result[current_field] = '\n'.join(current_value)

            # 第三步：清理 課程領域，去掉混入的核心能力表格文字
            if '課程領域' in result:
                domain = result['課程領域']
                if '系所核心能力' in domain:
                    domain = domain[:domain.find('系所核心能力')].strip()
                result['課程領域'] = domain

            result['核心能力'] = core_abilities

            if not result:
                result['完整內容'] = text[:500]

        except Exception as e:
            text = driver_window.find_element(By.TAG_NAME, "body").text
            result['錯誤'] = str(e)
            result['完整內容'] = text[:500]

        return result

    def get_detail_by_click(self, link_elem, detail_type):
        """使用 Selenium 點擊獲取詳細內容"""
        try:
            current_window = self.driver.current_window_handle
            current_windows = self.driver.window_handles

            link_elem.click()
            time.sleep(2)

            new_windows = self.driver.window_handles
            if len(new_windows) > len(current_windows):
                new_window = None
                for w in new_windows:
                    if w not in current_windows:
                        new_window = w
                        break

                if new_window:
                    self.driver.switch_to.window(new_window)
                    time.sleep(1)

                    if detail_type == "分發條件":
                        result = self.parse_condition_detail(self.driver)
                    else:
                        result = self.parse_outline_detail(self.driver)

                    self.driver.close()
                    self.driver.switch_to.window(current_window)
                    time.sleep(0.5)

                    return result

            return {}
        except Exception as e:
            print(f"[獲取{detail_type}錯誤: {str(e)[:50]}]", end=" ")
            try:
                all_windows = self.driver.window_handles
                if len(all_windows) > len(current_windows):
                    for w in all_windows:
                        if w not in current_windows:
                            self.driver.switch_to.window(w)
                            self.driver.close()
                self.driver.switch_to.window(current_window)
            except:
                pass
            return {}

    def scrape_courses_with_pagination(self, college, dept_name):
        """爬取課程（支援翻頁）

        回傳 (courses, complete)。任何一頁發生例外時 complete 為 False，
        呼叫端不能把這份不完整的結果存檔（否則續爬時會被當成已爬完而跳過）。
        """
        courses = []
        complete = True
        page_num = 1
        has_next_page = True

        while has_next_page:
            print(f"  頁 {page_num}...", end=" ")

            try:
                tables = self.driver.find_elements(By.TAG_NAME, "table")
                course_table = max(tables, key=lambda t: len(t.find_elements(By.TAG_NAME, "tr")))
                rows = course_table.find_elements(By.TAG_NAME, "tr")
                courses_before = len(courses)

                for i in range(1, len(rows)):
                    tables = self.driver.find_elements(By.TAG_NAME, "table")
                    course_table = max(tables, key=lambda t: len(t.find_elements(By.TAG_NAME, "tr")))
                    rows = course_table.find_elements(By.TAG_NAME, "tr")
                    row = rows[i]
                    cells = row.find_elements(By.TAG_NAME, "td")

                    course_data = {
                        "學年度": self.year,
                        "學期": self.semester,
                        "學院": college,
                        "系所": dept_name
                    }

                    if len(cells) > 0:
                        serial_course = self.split_serial_course(cells[0].text)
                        course_data.update(serial_course)
                    if len(cells) > 1:
                        name_note = self.split_name_note(cells[1].text)
                        course_data.update(name_note)
                    if len(cells) > 2:
                        course_data["授課教師"] = cells[2].text.strip()
                    if len(cells) > 3:
                        course_data["學分"] = cells[3].text.strip()
                    if len(cells) > 4:
                        time_room = self.split_time_room(cells[4].text)
                        course_data.update(time_room)
                    if len(cells) > 5:
                        course_data["選修別"] = cells[5].text.strip()
                    if len(cells) > 6:
                        course_data["全半年"] = cells[6].text.strip()
                    if len(cells) > 7:
                        course_data["人數限制"] = cells[7].text.strip()

                    # 分發條件
                    if len(cells) > 8:
                        try:
                            condition_link = cells[8].find_element(By.TAG_NAME, "a")
                            onclick_attr = condition_link.get_attribute("onclick")
                            condition_url = self.extract_url_from_onclick(onclick_attr)
                            condition_detail = self.get_detail_by_click(condition_link, "分發條件")
                            course_data["分發條件_連結"] = condition_url
                            course_data["分發條件"] = condition_detail
                        except:
                            course_data["分發條件_連結"] = ""
                            course_data["分發條件"] = {}
                    else:
                        course_data["分發條件_連結"] = ""
                        course_data["分發條件"] = {}

                    # 課程綱要
                    try:
                        tables = self.driver.find_elements(By.TAG_NAME, "table")
                        if tables:
                            course_table = max(tables, key=lambda t: len(t.find_elements(By.TAG_NAME, "tr")))
                            rows = course_table.find_elements(By.TAG_NAME, "tr")
                            if i < len(rows):
                                row = rows[i]
                                cells = row.find_elements(By.TAG_NAME, "td")
                                if len(cells) > 9:
                                    outline_link = cells[9].find_element(By.TAG_NAME, "a")
                                    onclick_attr = outline_link.get_attribute("onclick")
                                    outline_url = self.extract_url_from_onclick(onclick_attr)
                                    outline_detail = self.get_detail_by_click(outline_link, "課程綱要")
                                    course_data["課程綱要_連結"] = outline_url
                                    course_data["課程綱要"] = outline_detail
                                else:
                                    course_data["課程綱要_連結"] = ""
                                    course_data["課程綱要"] = {}
                            else:
                                course_data["課程綱要_連結"] = ""
                                course_data["課程綱要"] = {}
                        else:
                            course_data["課程綱要_連結"] = ""
                            course_data["課程綱要"] = {}
                    except:
                        course_data["課程綱要_連結"] = ""
                        course_data["課程綱要"] = {}

                    courses.append(course_data)

                courses_on_page = len(courses) - courses_before
                print(f"{courses_on_page} 門", end=" ")

                # 檢查是否有下一頁
                pagelinks = self.driver.find_elements(By.CLASS_NAME, "pagelinks")
                if pagelinks:
                    next_btn = pagelinks[0].find_elements(By.XPATH, ".//a[contains(., '»')]")
                    if next_btn and next_btn[0].is_displayed():
                        print("[翻頁]", end=" ")
                        next_btn[0].click()
                        time.sleep(3)
                        page_num += 1
                    else:
                        has_next_page = False
                else:
                    has_next_page = False

            except Exception as e:
                print(f"錯誤: {str(e)[:30]}")
                has_next_page = False
                complete = False

        return courses, complete

    def save_dept_json(self, dept_name, courses):
        """儲存系所課程為獨立JSON；成功回傳 True"""
        try:
            safe_name = re.sub(r'[\\/:*?"<>|]', '_', dept_name)
            filename = os.path.join(self.output_dir, f"{safe_name}.json")
            tmp = filename + ".tmp"

            # 先寫暫存檔再換名，避免中斷時留下半個檔案被續爬當成已完成
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(courses, f, ensure_ascii=False, indent=2)
            os.replace(tmp, filename)
            print(f"  ✓ 已儲存至 {filename} ({len(courses)} 門課程)")
            return True
        except Exception as e:
            print(f"  ✗ 儲存錯誤: {e}")
            return False

    def _record_failure(self, name, reason):
        if not hasattr(self, "failed_depts"):
            self.failed_depts = []
        self.failed_depts.append((name, reason))
        print(f"  ✗ 失敗：{name}（{reason}）")

    def dept_already_scraped(self, full_name):
        """檢查該系所是否已有 JSON 檔案（同時檢查輸出資料夾和舊資料資料夾）"""
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', full_name)
        in_output = os.path.exists(os.path.join(self.output_dir, f"{safe_name}.json"))
        in_data = os.path.exists(os.path.join(self.data_dir, f"{safe_name}.json"))
        return in_output or in_data

    def scrape_all_depts(self, exclude_keywords=None, skip_existing=True, max_depts=None):
        """爬取所有系所

        失敗（系所清單讀不到、某系所翻頁出錯、存檔失敗）都會記到 self.failed_depts，
        由 run() 據此回傳 False；翻頁不完整的系所不存檔，續爬時會重爬。
        """
        if exclude_keywords is None:
            exclude_keywords = []
        self.failed_depts = []

        try:
            dept_list_url = self.driver.current_url

            tables = self.driver.find_elements(By.TAG_NAME, "table")
            dept_table = tables[-1]
            rows = dept_table.find_elements(By.TAG_NAME, "tr")
        except Exception as e:
            self._record_failure("系所清單", f"讀取失敗：{e}")
            return

        total_depts = len(rows) - 1
        print(f"\n找到 {total_depts} 個系所")
        if total_depts <= 0:
            self._record_failure("系所清單", "沒有找到任何系所")
            return

        scraped_count = 0
        for dept_index in range(total_depts):
            label = f"第 {dept_index + 1} 個系所"
            entered = False
            try:
                tables = self.driver.find_elements(By.TAG_NAME, "table")
                dept_table = tables[-1]
                rows = dept_table.find_elements(By.TAG_NAME, "tr")

                if dept_index + 1 >= len(rows):
                    self._record_failure(label, "系所清單列數變少，讀不到這一列")
                    continue

                row = rows[dept_index + 1]
                cells = row.find_elements(By.TAG_NAME, "td")
                college = cells[0].text.strip()
                dept_name = cells[1].text.strip()
                full_name = f"{college}_{dept_name}"
                label = full_name

                if any(keyword in full_name for keyword in exclude_keywords):
                    print(f"\n[{dept_index+1}/{total_depts}] 跳過：{full_name} (排除關鍵字)")
                    continue

                if skip_existing and self.dept_already_scraped(full_name):
                    print(f"\n[{dept_index+1}/{total_depts}] 已存在，跳過：{full_name}")
                    continue

                if max_depts is not None and scraped_count >= max_depts:
                    print(f"\n已達上限 {max_depts} 個系所，停止爬取")
                    return

                print(f"\n[{dept_index+1}/{total_depts}] 爬取：{full_name}")

                dept_link = cells[2].find_element(By.TAG_NAME, "a")
                entered = True  # 點擊本身失敗時頁面狀態不明，一律回系所清單
                dept_link.click()
                time.sleep(3)

                courses, complete = self.scrape_courses_with_pagination(college, dept_name)
                scraped_count += 1

                if not complete:
                    self._record_failure(full_name, f"翻頁途中出錯，已爬 {len(courses)} 門，不存檔")
                elif courses and not self.save_dept_json(full_name, courses):
                    self._record_failure(full_name, "存檔失敗")

            except Exception as e:
                self._record_failure(label, f"例外：{str(e)[:80]}")

            if entered:
                try:
                    self.driver.get(dept_list_url)
                    time.sleep(2)
                except Exception as e:
                    self._record_failure("系所清單", f"回不到系所清單，停止：{e}")
                    return

    def close(self):
        """關閉瀏覽器"""
        try:
            self.driver.quit()
        except:
            pass

    def run(self, max_depts=None):
        """執行；全部系所都成功才回傳 True。

        進不了課程查詢頁、系所清單讀不到、任何系所翻頁或存檔失敗，都回傳 False。
        """
        try:
            if not self.navigate_to_course_page():
                return False

            self.scrape_all_depts(max_depts=max_depts)
            failed = getattr(self, "failed_depts", [])

            print("\n" + "=" * 60)
            if failed:
                print(f"爬取未完成：{len(failed)} 個項目失敗（已成功的系所留在 {self.output_dir}，重跑會續爬）")
                for name, reason in failed:
                    print(f"  - {name}：{reason}")
            else:
                print(f"爬取完成！所有系所已儲存至 {self.output_dir}")
            print("=" * 60)
            return not failed

        except Exception as e:
            print(f"\n錯誤: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            self.close()


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="NCU 課程爬蟲 v2（公開頁面，不需登入）")
    parser.add_argument("--year", default="114", help="學年度，例如 114")
    parser.add_argument("--semesters", default="1,2", help="學期，逗號分隔，例如 1,2")
    parser.add_argument("--output-dir", default=None,
                        help="輸出目錄（只爬一個學期時使用；預設 data/raw/courses/{學年}_{學期}）")
    parser.add_argument("--headless", action="store_true", help="無頭模式（不開瀏覽器視窗）")
    parser.add_argument("--max-depts", type=int, default=None, help="最多爬幾個系所（試跑用）")
    args = parser.parse_args(argv)

    semesters = [s.strip() for s in args.semesters.split(",") if s.strip()]
    if args.output_dir and len(semesters) != 1:
        parser.error("--output-dir 只能搭配單一學期")

    print("=" * 60)
    print("  NCU 課程爬蟲 v2 (無需登入)")
    print("=" * 60)

    ok = True
    for semester in semesters:
        print(f"\n開始爬取 {args.year} 學年度第 {semester} 學期")
        print("=" * 60)

        scraper = NCUCourseScraperV2(year=args.year, semester=semester,
                                     output_dir=args.output_dir, headless=args.headless)
        ok = scraper.run(max_depts=args.max_depts) and ok

    print("\n" + "=" * 60)
    print("所有學期爬取完成！" if ok else "部分學期爬取失敗，請看上方錯誤訊息")
    print("=" * 60)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
