"""
3b_summarize_with_azure.py

讀取 3a 產生的 pdf_sections_raw.json，
透過 Azure OpenAI 摘要每份 PDF 的三段原文，
寫入 data/processed/assessment_questions.json。

執行前請設定環境變數：
    set AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
    set AZURE_OPENAI_API_KEY=<your-key>
    set AZURE_OPENAI_DEPLOYMENT=<deployment-name>   # 例如 gpt-4o-mini

執行（在 scripts/ 目錄下）：
    python 3b_summarize_with_azure.py
    python 3b_summarize_with_azure.py --limit 10   # 只跑前 10 筆測試
    python 3b_summarize_with_azure.py --dry-run     # 只印 prompt，不呼叫 API

依賴套件：
    pip install openai tiktoken
"""

import os
import re
import json
import time
import argparse

# ─────────────────────────────────────────
# 路徑設定
# ─────────────────────────────────────────
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(SCRIPT_DIR, '..', '..', '..')
INPUT_JSON   = os.path.join(PROJECT_ROOT, 'data', 'processed', 'pdf_sections_raw.json')
OUTPUT_JSON  = os.path.join(PROJECT_ROOT, 'data', 'processed', 'assessment_questions.json')

# 送給 Azure OpenAI 前，每段原文最多保留的 token 數
# （三段合計約 2400 tokens，加 prompt 本身不超過 4096）
MAX_TOKENS_PER_SECTION = 800


# ─────────────────────────────────────────
# mode 對應
# ─────────────────────────────────────────
def year_to_mode(year_str: str) -> str:
    try:
        y = int(year_str)
    except ValueError:
        return 'grade2'
    if y <= 107:
        return 'grade1'
    elif y <= 110:
        return 'grade2'
    else:
        return 'grade3'


# ─────────────────────────────────────────
# Token 截斷工具
# ─────────────────────────────────────────
try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")

    def truncate_to_tokens(text: str, max_tokens: int) -> str:
        tokens = _enc.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return _enc.decode(tokens[:max_tokens]) + '...(截斷)'

except ImportError:
    def truncate_to_tokens(text: str, max_tokens: int) -> str:
        # 估算：1 token ≈ 1.5 字元（中文偏多）
        max_chars = int(max_tokens * 1.5)
        return text[:max_chars] + '...(截斷)' if len(text) > max_chars else text


# ─────────────────────────────────────────
# Azure OpenAI 摘要
# ─────────────────────────────────────────
def build_client():
    try:
        from openai import AzureOpenAI
    except ImportError:
        raise ImportError("請先安裝 openai：pip install openai")

    endpoint   = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
    api_key    = os.environ.get("AZURE_OPENAI_API_KEY", "")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

    if not endpoint or not api_key:
        raise EnvironmentError(
            "請設定環境變數 AZURE_OPENAI_ENDPOINT 和 AZURE_OPENAI_API_KEY"
        )

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version="2024-02-01",
    )
    return client, deployment


def build_prompt(title: str, department: str,
                 motivation_raw: str, method_raw: str, result_raw: str) -> str:
    def fmt(text, label):
        if text:
            return f"=== {label} ===\n{text}"
        return f"=== {label} ===\n（未找到，請根據標題推測）"

    return f"""論文標題：{title}
所屬系所：{department}

{fmt(motivation_raw, '研究動機原文')}

{fmt(method_raw, '研究方法原文')}

{fmt(result_raw, '研究結果原文')}

請根據以上內容，以繁體中文輸出下列 JSON（不要有其他文字）：
{{
  "motivation": "2到3句話，說明這份研究的背景與動機，讓高中生能看懂",
  "method": "2到3句話，說明研究使用的方法或步驟",
  "result": "2到3句話，說明主要發現或研究貢獻",
  "tags": ["標籤1", "標籤2", "標籤3"]
}}
tags 請給 3 到 5 個，反映核心技術或領域，每個不超過 6 個字。"""


def call_azure(client, deployment: str, prompt: str, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system",
                     "content": "你是學術摘要助理，擅長把大學研究計畫摘要成高中生能理解的內容，只輸出 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=500,
            )
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            return json.loads(raw)

        except json.JSONDecodeError as e:
            print(f"  [警告] GPT 輸出非合法 JSON（第 {attempt+1} 次）：{e}")
            if attempt < retries - 1:
                time.sleep(2)

        except Exception as e:
            err = str(e)
            if any(code in err for code in ('429', 'rate_limit', 'RateLimitError')):
                wait = 30 * (attempt + 1)
                print(f"  Rate limit，等待 {wait}s ...")
                time.sleep(wait)
            else:
                print(f"  [錯誤] {e}")
                break

    return {"motivation": "", "method": "", "result": "", "tags": []}


# ─────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit',   type=int, default=0,    help='限制處理筆數（0 = 全部）')
    parser.add_argument('--dry-run', action='store_true',    help='只印 prompt，不呼叫 API')
    parser.add_argument('--i-understand-this-overwrites', action='store_true',
                        help='確認要在現行 assessment_questions.json 上重跑（預設拒絕）')
    args = parser.parse_args()

    # 現行 assessment_questions.json 由 scripts/data/import_step2_step3_summaries.py 產生，
    # 紀錄裡沒有 source_id；這支腳本靠 source_id 斷點續跑，重跑會把全部紀錄再附加一次並呼叫付費 API。
    if not args.dry_run and not args.i_understand_this_overwrites:
        raise SystemExit(
            "已停用：現行 assessment_questions.json 由 import_step2_step3_summaries.py 產生，"
            "重跑這支會重複附加全部題目並呼叫 Azure OpenAI。\n"
            "定期更新請改用 python -m scripts.update_data。"
            "確定要重跑請加 --i-understand-this-overwrites。"
        )

    if not os.path.exists(INPUT_JSON):
        print(f"找不到輸入檔：{INPUT_JSON}")
        print("請先執行 3a_extract_pdf_sections.py")
        return

    with open(INPUT_JSON, 'r', encoding='utf-8') as f:
        records = json.load(f)

    # 斷點續跑
    if os.path.exists(OUTPUT_JSON):
        with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
            questions = json.load(f)
        done_ids = {q.get('source_id', '') for q in questions}
        print(f"發現已有 {len(questions)} 筆，繼續補跑...")
    else:
        questions = []
        done_ids = set()

    client, deployment = (None, None) if args.dry_run else build_client()

    limit = args.limit if args.limit > 0 else len(records)
    processed = 0

    for rec in records:
        if processed >= limit:
            break

        rec_id = rec['id']
        if rec_id in done_ids:
            continue

        title  = rec.get('title', '')
        dept   = rec.get('department', '')
        year   = rec.get('year', '')

        # 截斷至合理 token 數
        m_raw = truncate_to_tokens(rec.get('motivation_raw', ''), MAX_TOKENS_PER_SECTION)
        me_raw = truncate_to_tokens(rec.get('method_raw', ''),    MAX_TOKENS_PER_SECTION)
        r_raw = truncate_to_tokens(rec.get('result_raw', ''),     MAX_TOKENS_PER_SECTION)

        print(f"[{rec_id}] {dept} | {title[:35]}...")

        prompt = build_prompt(title, dept, m_raw, me_raw, r_raw)

        if args.dry_run:
            print(f"  ── PROMPT ──\n{prompt}\n")
            processed += 1
            continue

        summary = call_azure(client, deployment, prompt)

        question = {
            'id':          f'q{len(questions) + 1:03d}',
            'source_id':   rec_id,
            'mode':        year_to_mode(year),
            'department':  dept,
            'title':       title,
            'motivation':  summary.get('motivation', ''),
            'method':      summary.get('method', ''),
            'result':      summary.get('result', ''),
            'tags':        summary.get('tags', []),
            'extracted':   any([rec.get('motivation_raw'), rec.get('method_raw'), rec.get('result_raw')]),
        }
        questions.append(question)
        done_ids.add(rec_id)
        processed += 1

        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(questions, f, ensure_ascii=False, indent=2)

        print(f"  已儲存（共 {len(questions)} 筆）")
        time.sleep(0.3)

    if not args.dry_run:
        print(f"\n完成！共處理 {processed} 筆，總計 {len(questions)} 筆已存入：\n  {OUTPUT_JSON}")


if __name__ == '__main__':
    main()
