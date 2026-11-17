"""一鍵資料更新：python -m scripts.update_data

預設是 dry-run：在暫存沙盒裡跑完所有免費、不碰外部服務的步驟，印出變更摘要，不寫入正式資料。
詳細說明見 scripts/update_data/README.md。
"""

from __future__ import annotations

import argparse
import sys

from .pipeline import Options, Pipeline
from .steps import BLOCKED, FLAG_FOR_TAG, STAGES, STEPS


def _names(value: str) -> tuple[str, ...]:
    return tuple(n.strip() for n in value.split(",") if n.strip())


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m scripts.update_data",
        description="一鍵更新 data/processed：預設 dry-run，加 --apply 才寫入；"
                    "會連網、花錢、寫外部服務的步驟各自要加旗標。",
    )
    p.add_argument("--apply", action="store_true", help="驗證通過後把變動套用到正式目錄，並執行已允許的外部步驟")
    p.add_argument("--fetch", action="store_true", help="允許連學校網站爬資料（課程、課綱、應修科目表 PDF）")
    p.add_argument("--with-local-llm", dest="local_llm", action="store_true",
                   help="允許跑需要本機 vLLM 的 NLP 標註步驟")
    p.add_argument("--allow-paid", action="store_true", help="允許呼叫付費 API（Azure OpenAI chat / embedding）")
    p.add_argument("--allow-external", action="store_true", help="允許讀寫外部服務（Qdrant、Cloudinary、PostgreSQL）")
    p.add_argument("--allow-destructive", action="store_true", help="允許刪除外部服務裡的資料（例如 Qdrant 的點或 collection）")
    p.add_argument("--only", type=_names, default=(), help="只跑這些步驟（逗號分隔）")
    p.add_argument("--include", type=_names, default=(), help="在預設步驟之外加跑這些步驟（逗號分隔）")
    p.add_argument("--skip", type=_names, default=(), help="跳過這些步驟（逗號分隔）")
    p.add_argument("--terms", type=_names, default=("114_1", "114_2"),
                   help="學期清單，舊到新，逗號分隔（預設 114_1,114_2）")
    p.add_argument("--max-shrink", type=float, default=0.10,
                   help="輸出筆數比現有少超過這個比例就視為失敗（預設 0.10）")
    p.add_argument("--allow-shrink", action="store_true", help="不檢查筆數減少（確定資料本來就變少時使用）")
    p.add_argument("--allow-incomplete-content", action="store_true",
                   help="補課綱沒有成功跑完（學期目錄留著 .content_fix_pending）時仍用目前的原始課程 build")
    p.add_argument("--fresh-fetch", action="store_true", help="不續爬，先把上次沒爬完的暫存目錄移開再從頭爬")
    p.add_argument("--keep-sandbox", action="store_true", help="跑完保留暫存沙盒（預設成功就刪除，失敗才保留）")
    p.add_argument("--list", action="store_true", help="列出所有步驟、權限需求與被擋下的腳本後結束")
    return p


def print_steps() -> None:
    print("步驟（依執行順序）：\n")
    for stage in STAGES:
        for s in (x for x in STEPS if x.stage == stage):
            flags = " ".join(FLAG_FOR_TAG[t] for t in sorted(s.tags)) or "（不需旗標）"
            if s.explicit_only:
                when = "需用 --only/--include 點名"
            elif s.default:
                when = "預設納入"
            else:
                when = "需用 --include 點名"
            print(f"  [{s.stage}] {s.name}：{s.title}")
            print(f"      權限：{flags}｜{when}｜成本：{s.cost}")
            if s.note:
                print(f"      說明：{s.note}")
    print("\n被擋下、管線不會執行的腳本：\n")
    for name, why in BLOCKED.items():
        print(f"  {name}：{why}")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)
    if args.list:
        print_steps()
        return 0
    if not 0 <= args.max_shrink < 1:
        print("--max-shrink 要介於 0 與 1 之間", file=sys.stderr)
        return 2

    opts = Options(
        apply=args.apply, fetch=args.fetch, local_llm=args.local_llm, allow_paid=args.allow_paid,
        allow_external=args.allow_external, allow_destructive=args.allow_destructive,
        only=args.only, include=args.include, skip=args.skip, terms=args.terms,
        max_shrink=args.max_shrink, allow_shrink=args.allow_shrink,
        keep_sandbox=args.keep_sandbox, fresh_fetch=args.fresh_fetch,
        allow_incomplete_content=args.allow_incomplete_content,
    )
    try:
        report = Pipeline(opts).run()
    except ValueError as e:
        print(f"錯誤：{e}", file=sys.stderr)
        return 2
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
