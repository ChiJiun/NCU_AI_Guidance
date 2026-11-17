import json
import re
import os
from pathlib import Path

def parse_course_domain(domain_text):
    """
    解析課程領域字段，提取課程領域名稱和核心能力表格

    返回格式:
    {
        "課程領域": "專業基礎學科",  # 可能為空字符串
        "核心能力": [
            {
                "能力名稱": "運用數學、科學及工程知識之能力",
                "強度指數": "(1) 非常低",
                "評量方式": "無"
            },
            ...
        ]
    }
    """
    if not domain_text or domain_text.strip() == "":
        return {
            "課程領域": "",
            "核心能力": []
        }

    lines = domain_text.strip().split('\n')

    # 初始化
    course_domain = ""
    core_abilities = []

    # 尋找表格標題行（系所核心能力 強度指數 評量方式）
    table_header_index = -1
    for i, line in enumerate(lines):
        if "系所核心能力" in line and "強度指數" in line and "評量方式" in line:
            table_header_index = i
            # 如果表格標題不在第一行，前面的內容就是課程領域
            if i > 0:
                course_domain = '\n'.join(lines[:i]).strip()
            break

    # 如果沒有找到表格標題，整個內容都是課程領域
    if table_header_index == -1:
        return {
            "課程領域": domain_text.strip(),
            "核心能力": []
        }

    # 解析表格數據（表格標題後面的所有行）
    for i in range(table_header_index + 1, len(lines)):
        line = lines[i].strip()
        if not line:
            continue

        # 使用正則表達式提取數據
        # 格式: 能力名稱 (數字) 強度文字 評量方式1 ， 評量方式2 ， ...
        # 例如: 運用數學、科學及工程知識之能力 (1) 非常低 無

        # 嘗試匹配 "(數字) 強度" 的模式來分割
        match = re.match(r'^(.+?)\s+(\(\d+\)\s+[^\s]+)\s+(.+)$', line)

        if match:
            ability_name = match.group(1).strip()
            intensity = match.group(2).strip()
            evaluation = match.group(3).strip()

            core_abilities.append({
                "能力名稱": ability_name,
                "強度指數": intensity,
                "評量方式": evaluation
            })

    return {
        "課程領域": course_domain,
        "核心能力": core_abilities
    }

def process_json_file(file_path):
    """處理單個 JSON 文件"""
    print(f"處理文件: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 處理每個課程
    modified = False
    for course in data:
        if '課程綱要' in course and '課程領域' in course['課程綱要']:
            original_domain = course['課程綱要']['課程領域']
            parsed_data = parse_course_domain(original_domain)

            # 更新數據結構
            course['課程綱要']['課程領域'] = parsed_data['課程領域']
            course['課程綱要']['核心能力'] = parsed_data['核心能力']
            modified = True

    # 保存修改後的文件
    if modified:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✓ 已更新: {file_path}")
    else:
        print(f"- 無需更新: {file_path}")

    return modified

def main():
    """主函數：處理所有 JSON 文件"""
    import sys
    # 這支是修第一版爬蟲格式的一次性腳本。v2 爬蟲已把核心能力拆成獨立欄位，
    # 再跑會把「核心能力」覆寫成空陣列。
    if '--i-understand-this-overwrites' not in sys.argv:
        sys.exit(
            "已停用：這支會直接改寫 data/raw/courses/**，對 v2 爬蟲資料會把核心能力清成空陣列。\n"
            "確定要重跑請加 --i-understand-this-overwrites。"
        )
    base_dir = Path(__file__).resolve().parents[3] / "data" / "raw" / "courses"

    # 查找所有 JSON 文件
    json_files = list(base_dir.glob("**/*.json"))

    print(f"找到 {len(json_files)} 個 JSON 文件\n")

    modified_count = 0
    for json_file in json_files:
        try:
            if process_json_file(json_file):
                modified_count += 1
        except Exception as e:
            print(f"✗ 處理失敗 {json_file}: {e}")

    print(f"\n處理完成！")
    print(f"總共處理: {len(json_files)} 個文件")
    print(f"已修改: {modified_count} 個文件")

if __name__ == "__main__":
    main()
