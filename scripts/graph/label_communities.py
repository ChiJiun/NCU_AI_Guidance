"""
label_communities.py — 用 LLM 批次命名 Leiden 社群

每次送 BATCH_SIZE 個社群給 LLM，讓它看到多個社群對比後再命名，
避免出現「資料分析與AI」vs「AI與資料分析」這種重複。

用法：
  python scripts/graph/label_communities.py           # 只補空白 label
  python scripts/graph/label_communities.py --reset   # 全部重新命名
  python scripts/graph/label_communities.py --dry-run # 只印 prompt，不呼叫 API

結束碼：0 全部命名成功（或沒有需要命名的社群）；1 找不到 communities.json、缺少 Azure 環境變數，
或有社群命名失敗（API 錯誤、回應解析不到）。命名失敗時仍會寫回已成功的名稱，重跑會只補空白的 label。
資料更新管線靠這個結束碼判斷，避免把 label 被清空的 communities.json 套用到正式目錄。
"""

import argparse
import json
import os
import re
import time
from collections import Counter
from pathlib import Path

ROOT             = Path(__file__).parent.parent.parent
COMMUNITIES_JSON = ROOT / "data" / "processed" / "graph" / "communities.json"
GRAPH_JSON       = ROOT / "data" / "processed" / "graph" / "knowledge_graph.json"

BATCH_SIZE = 6  # 每批送幾個社群給 LLM

SYSTEM_PROMPT = (
    "你是台灣大學課程分類專家。"
    "你會根據課程的概念與系所特色，給予簡短且有區分度的中文名稱。"
)

BATCH_TEMPLATE = """\
以下 {n} 個大學課程社群需要命名。
請為每個社群取一個 8-15 字的繁體中文名稱，要求：
1. 名稱要能區分這 {n} 個社群，不能重複或過於相似
2. 優先體現「學科領域」+「核心技術或方法」，不要只說「XX課程」
3. 格式固定：「社群X名稱：答案」，每行一個，不要額外解釋

{blocks}

請依序輸出每個社群的名稱："""

COMMUNITY_BLOCK = """\
【社群{label}】（{size} 門課，主要系所：{depts}）
核心概念：{concepts}
代表課程：{courses}"""


def load_graph_dept_map() -> dict[str, str]:
    """回傳 course_code → dept 對應表。"""
    if not GRAPH_JSON.exists():
        return {}
    raw   = json.loads(GRAPH_JSON.read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in raw["nodes"]}
    return {
        nid: n.get("dept", "")
        for nid, n in nodes.items()
        if n.get("node_type") == "Course" and n.get("dept")
    }


def top_depts(community: dict, dept_map: dict, n: int = 3) -> str:
    """找社群內出現最多次的系所，回傳逗號分隔字串。"""
    counts = Counter(
        dept_map.get(c["code"] if isinstance(c, dict) else c, "")
        for c in community.get("courses", [])
    )
    counts.pop("", None)
    top = [d for d, _ in counts.most_common(n)]
    return "、".join(top) if top else "不限系所"


def build_batch_prompt(batch: list[dict], dept_map: dict) -> tuple[str, list[str]]:
    """建立批次 prompt，回傳 (prompt_str, label_list)。"""
    labels = [chr(ord("A") + i) for i in range(len(batch))]
    blocks = []
    for label, c in zip(labels, batch):
        concepts = "、".join(c.get("top_concepts", [])[:10]) or "（無）"
        courses  = "、".join(
            (x["name"] if isinstance(x, dict) else x)
            for x in c.get("courses", [])[:10]
        ) or "（無）"
        depts = top_depts(c, dept_map)
        blocks.append(COMMUNITY_BLOCK.format(
            label=label, size=c["size"],
            depts=depts, concepts=concepts, courses=courses,
        ))
    prompt = BATCH_TEMPLATE.format(n=len(batch), blocks="\n\n".join(blocks))
    return prompt, labels


def parse_response(text: str, labels: list[str]) -> dict[str, str]:
    """從 LLM 回應中解析 {label: name} 對應。"""
    result: dict[str, str] = {}
    for label in labels:
        # 匹配「社群A名稱：XXX」或「社群A：XXX」
        pattern = rf"社群{label}(?:名稱)?[：:]\s*(.+)"
        m = re.search(pattern, text)
        if m:
            name = m.group(1).strip().strip("「」《》【】\"""''")
            result[label] = name
    return result


def call_llm(prompt: str, client, deployment: str) -> str:
    resp = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        max_completion_tokens=200,
        temperature=0.4,
    )
    return resp.choices[0].message.content.strip()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset",   action="store_true", help="重新命名所有社群")
    parser.add_argument("--dry-run", action="store_true", help="只印 prompt，不呼叫 API")
    args = parser.parse_args(argv)

    if not COMMUNITIES_JSON.exists():
        print(f"找不到 {COMMUNITIES_JSON}，請先執行 compute_communities.py")
        return 1

    communities: list[dict] = json.loads(COMMUNITIES_JSON.read_text(encoding="utf-8"))
    dept_map = load_graph_dept_map()

    to_label = [c for c in communities if args.reset or not c.get("label")]
    print(f"社群總數：{len(communities)}，需要命名：{len(to_label)}")

    if not to_label:
        print("所有社群已有名稱，使用 --reset 重新命名。")
        return 0

    if args.dry_run:
        batch = to_label[:BATCH_SIZE]
        prompt, labels = build_batch_prompt(batch, dept_map)
        print(f"── 批次 prompt 預覽（前 {len(batch)} 個社群）──\n")
        print(prompt)
        print(f"\n[dry-run] 共 {len(to_label)} 個社群，"
              f"分 {-(-len(to_label) // BATCH_SIZE)} 批命名。")
        return 0

    # 載入環境變數
    from dotenv import load_dotenv
    for env_path in [ROOT / ".env", ROOT / "backend" / ".env", Path(".env")]:
        if env_path.exists():
            load_dotenv(env_path)
            break

    missing = [k for k in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT")
               if not os.environ.get(k)]
    if missing:
        print(f"[錯誤] 缺少環境變數：{missing}")
        return 1

    from openai import AzureOpenAI
    client = AzureOpenAI(
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01"),
    )
    deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini")

    id_to_community = {c["id"]: c for c in communities}
    errors = 0
    done   = 0

    # 分批處理
    for batch_start in range(0, len(to_label), BATCH_SIZE):
        batch  = to_label[batch_start: batch_start + BATCH_SIZE]
        prompt, labels = build_batch_prompt(batch, dept_map)

        try:
            raw_response = call_llm(prompt, client, deployment)
            parsed = parse_response(raw_response, labels)

            for label, c in zip(labels, batch):
                name = parsed.get(label, "")
                if name:
                    id_to_community[c["id"]]["label"] = name
                    print(f"  社群 {c['id']:2d} ({c['size']:2d} 門課) → {name}")
                    done += 1
                else:
                    print(f"  社群 {c['id']:2d} 解析失敗（回應：{raw_response[:60]}...）")
                    errors += 1
        except Exception as ex:
            print(f"  批次 {batch_start//BATCH_SIZE + 1} 失敗：{ex}")
            errors += len(batch)

        time.sleep(0.5)

    # 寫回 JSON
    COMMUNITIES_JSON.write_text(
        json.dumps(communities, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n完成！成功 {done} 個，失敗 {errors} 個 → {COMMUNITIES_JSON}")
    if errors:
        print(f"[錯誤] 有 {errors} 個社群沒有命名成功，以結束碼 1 結束；重跑會只補空白的 label。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
