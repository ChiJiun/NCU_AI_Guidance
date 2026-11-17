"""資料更新管線主流程。

  fetch   → 直接寫 data/raw（加 --fetch 且 --apply 才連網）
  build   → 複製一份 repo 到暫存沙盒，在沙盒裡跑既有腳本
  check   → 在沙盒裡做唯讀檢查
  驗證    → 每個步驟的輸出要能解析、不能是空的、筆數不能比現有少太多
  套用    → 只有 --apply 且全部通過才把變動檔案換進正式目錄（先備份，再原子替換）
  publish → 套用成功後才寫外部服務（Qdrant / Cloudinary），每一類都要明確旗標
"""

from __future__ import annotations

import datetime as _dt
import filecmp
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import changes as ch
from .fetch import fetch_courses, parse_term
from .proc import build_env, load_env_files, run_logged
from .steps import (BLOCKED, BUILD, CHECK, EXTERNAL, FETCH, FLAG_FOR_TAG, LIVE_TAGS, LOCAL_LLM, NETWORK, PAID,
                    DESTRUCTIVE, PUBLISH, RUN_DIR_TOKEN, STEPS, Step)

ROOT = Path(__file__).resolve().parents[2]

# 沙盒要複製的目錄，以及不複製的部分（大型、被 gitignore、或與資料更新無關）
SANDBOX_DIRS = ("scripts", "backend", "data")
SANDBOX_FILES = ("frontend/src/data/glossary.json",)
SKIP_DIR_NAMES = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache", "node_modules", ".venv", "venv"})
SKIP_REL_PREFIXES = (
    "data/raw/projects", "data/processed/qdrant", "data/processed/chroma_db_backup",
    "data/processed/curriculum_maps_png", "data/sessions", "data/test_results", "data/evaluation/runs",
)
# 沙盒中比對「未宣告變動」的範圍
WATCHED_ROOTS = ("data", "frontend/src/data")


@dataclass
class Options:
    apply: bool = False
    fetch: bool = False
    local_llm: bool = False
    allow_paid: bool = False
    allow_external: bool = False
    allow_destructive: bool = False
    only: tuple[str, ...] = ()
    include: tuple[str, ...] = ()
    skip: tuple[str, ...] = ()
    terms: tuple[str, ...] = ("114_1", "114_2")
    max_shrink: float = 0.10
    allow_shrink: bool = False
    keep_sandbox: bool = False
    fresh_fetch: bool = False


@dataclass
class StepResult:
    name: str
    stage: str
    status: str            # ok / failed / skipped / planned / not_run
    detail: str = ""
    changed: list[str] = field(default_factory=list)


@dataclass
class RunReport:
    run_id: str
    run_dir: Path
    options: Options
    results: list[StepResult] = field(default_factory=list)
    changes: list[ch.FileChange] = field(default_factory=list)
    undeclared: list[str] = field(default_factory=list)
    promoted: bool = False
    sandbox: Path | None = None
    messages: list[str] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(r.status == "failed" for r in self.results)


# ── 選步驟與權限 ──────────────────────────────────────────────────────────

def granted_tags(opts: Options) -> set[str]:
    granted = set()
    if opts.fetch:
        granted.add(NETWORK)
    if opts.local_llm:
        granted.add(LOCAL_LLM)
    if opts.allow_paid:
        granted.add(PAID)
    if opts.allow_external:
        granted.add(EXTERNAL)
    if opts.allow_destructive:
        granted.add(DESTRUCTIVE)
    return granted


def missing_flags(step: Step, opts: Options) -> list[str]:
    granted = granted_tags(opts)
    return [FLAG_FOR_TAG[t] for t in sorted(step.tags) if t not in granted]


def _check_names(names: tuple[str, ...], known: set[str]) -> None:
    for n in names:
        if n in BLOCKED:
            raise ValueError(f"「{n}」已被擋下：{BLOCKED[n]}")
        if n not in known:
            raise ValueError(f"沒有名為「{n}」的步驟；用 --list 查看所有步驟")


def select_steps(opts: Options, steps: tuple[Step, ...] = STEPS) -> list[Step]:
    known = {s.name for s in steps}
    for names in (opts.only, opts.include, opts.skip):
        _check_names(names, known)
    if opts.only:
        chosen = set(opts.only)
    else:
        chosen = {s.name for s in steps if s.default and not s.explicit_only} | set(opts.include)
    chosen -= set(opts.skip)
    return [s for s in steps if s.name in chosen]


def expand_requires(step: Step, terms: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for r in step.requires:
        if "{term}" in r:
            out.extend(r.replace("{term}", t) for t in terms)
        else:
            out.append(r)
    return out


def missing_inputs(step: Step, base: Path, terms: tuple[str, ...]) -> list[str]:
    missing = []
    for rel in expand_requires(step, terms):
        p = base / rel
        if not p.exists() or (p.is_dir() and not any(f.is_file() for f in p.rglob("*"))):
            missing.append(rel)
    return missing


# ── 沙盒 ──────────────────────────────────────────────────────────────────

def _skip_rel(rel: str) -> bool:
    return rel.startswith(SKIP_REL_PREFIXES)


def _is_env_file(name: str) -> bool:
    return name == ".env" or name.startswith(".env.")


def create_sandbox(root: Path, dest: Path) -> Path:
    """複製 scripts/、backend/、data/ 到 dest（不含 .env 與大型、被忽略的目錄）。"""
    dest.mkdir(parents=True, exist_ok=True)
    for top in SANDBOX_DIRS:
        src = root / top
        if not src.is_dir():
            continue

        def ignore(dirpath: str, names: list[str], _src=src, _top=top) -> set[str]:
            rel_dir = Path(dirpath).relative_to(_src)
            skipped = set()
            for n in names:
                rel = (Path(_top) / rel_dir / n).as_posix()
                if n in SKIP_DIR_NAMES or _is_env_file(n) or _skip_rel(rel):
                    skipped.add(n)
            return skipped

        shutil.copytree(src, dest / top, ignore=ignore)
    for rel in SANDBOX_FILES:
        if (root / rel).is_file():
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / rel, dest / rel)
    (dest / "logs").mkdir(exist_ok=True)   # NLP agent 會往 logs/ 寫除錯檔，目錄不存在會讓每門課都失敗
    return dest


def watched_changes(sandbox: Path, root: Path) -> list[str]:
    """沙盒中所有內容與正式資料不同（或新增）的檔案。"""
    out = []
    for top in WATCHED_ROOTS:
        base = sandbox / top
        if not base.is_dir():
            continue
        for f in base.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(sandbox).as_posix()
            if _skip_rel(rel):
                continue
            dst = root / rel
            if not dst.exists() or not filecmp.cmp(f, dst, shallow=False):
                out.append(rel)
    return sorted(out)


def promote(files: list[str], sandbox: Path, root: Path, backup_dir: Path, run_id: str) -> None:
    """先備份，再逐檔原子替換；任何一檔失敗就還原已替換的檔案。"""
    done: list[tuple[Path, Path | None]] = []
    try:
        for rel in files:
            src, dst = sandbox / rel, root / rel
            backup = None
            if dst.exists():
                backup = backup_dir / rel
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dst, backup)
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_name(f"{dst.name}.update-{run_id}.tmp")
            shutil.copy2(src, tmp)
            os.replace(tmp, dst)
            done.append((dst, backup))
    except Exception:
        for dst, backup in reversed(done):
            if backup is not None:
                shutil.copy2(backup, dst)
            else:
                dst.unlink(missing_ok=True)
        raise


# ── 執行 ──────────────────────────────────────────────────────────────────

class Pipeline:
    def __init__(self, opts: Options, *, root: Path = ROOT, python: str = sys.executable,
                 echo: Callable[[str], None] = print, env: dict[str, str] | None = None,
                 sandbox_parent: Path | None = None, steps: tuple[Step, ...] = STEPS):
        self.opts = opts
        self.steps = steps
        self.root = root
        self.python = python
        self.echo = echo
        self.base_env = dict(os.environ if env is None else env)
        self.sandbox_parent = sandbox_parent
        self.run_id = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.run_dir = root / "logs" / "data_update" / self.run_id
        self.report = RunReport(self.run_id, self.run_dir, opts)
        self._credentials: dict[str, str] | None = None

    # 子程序
    def _env_for(self, step: Step) -> dict[str, str]:
        needs_credentials = bool(step.tags & {PAID, EXTERNAL})
        creds = None
        if needs_credentials:
            if self._credentials is None:
                self._credentials = load_env_files(self.root)
            creds = self._credentials
        return build_env(self.base_env, terms=list(self.opts.terms), credentials=creds)

    def _argv(self, cmd: tuple[str, ...]) -> list[str]:
        return [self.python, cmd[0], *(a.replace(RUN_DIR_TOKEN, str(self.run_dir)) for a in cmd[1:])]

    def _run_commands(self, step: Step, cwd: Path) -> tuple[bool, str]:
        env = self._env_for(step)
        log_path = self.run_dir / "steps" / f"{step.name}.log"
        for cmd in step.commands:
            self.echo(f"  $ python {' '.join(cmd)}")
            rc = run_logged(self._argv(cmd), cwd=cwd, env=env, log_path=log_path,
                            echo=lambda line: self.echo(f"    {line}"))
            if rc != 0:
                return False, f"{cmd[0]} 結束碼 {rc}（log：{log_path}）"
        return True, ""

    def _gate(self, step: Step) -> StepResult | None:
        """回傳 None 代表可以執行；否則是跳過／只列計畫的結果。"""
        miss = missing_flags(step, self.opts)
        if miss:
            return StepResult(step.name, step.stage, "skipped", f"需要 {' '.join(miss)}")
        if not self.opts.apply and step.tags & LIVE_TAGS:
            return StepResult(step.name, step.stage, "planned", "dry-run：不連網、不花錢、不碰外部服務，只列出計畫")
        if not self.opts.apply and step.stage == PUBLISH:
            return StepResult(step.name, step.stage, "planned", "dry-run：不寫外部服務")
        return None

    def _add(self, res: StepResult) -> StepResult:
        self.report.results.append(res)
        mark = {"ok": "完成", "failed": "失敗", "skipped": "跳過", "planned": "計畫", "not_run": "未執行"}[res.status]
        self.echo(f"[{mark}] {res.name}" + (f"：{res.detail}" if res.detail else ""))
        return res

    # 階段
    def run_fetch(self, steps: list[Step]) -> bool:
        for step in steps:
            gated = self._gate(step)
            if gated:
                self._add(gated)
                continue
            self.echo(f"\n== {step.name}：{step.title}")
            if step.runner == "fetch_courses":
                env = self._env_for(step)
                log_path = self.run_dir / "steps" / f"{step.name}.log"
                ok, detail = fetch_courses(
                    root=self.root, run_dir=self.run_dir, terms=list(self.opts.terms), python=self.python,
                    run=lambda argv: run_logged(argv, cwd=self.root, env=env, log_path=log_path,
                                                echo=lambda line: self.echo(f"    {line}")),
                    log=self.echo, max_shrink=self.opts.max_shrink, allow_shrink=self.opts.allow_shrink,
                    fresh=self.opts.fresh_fetch,
                )
            else:
                missing = missing_inputs(step, self.root, self.opts.terms)
                if missing:
                    self._add(StepResult(step.name, step.stage, "skipped", f"缺少輸入：{', '.join(missing)}"))
                    continue
                ok, detail = self._run_commands(step, self.root)
            self._add(StepResult(step.name, step.stage, "ok" if ok else "failed", detail))
            if not ok:
                return False
        return True

    def _ensure_sandbox(self) -> Path:
        if self.report.sandbox is None:
            parent = self.sandbox_parent or Path(tempfile.gettempdir())
            parent.mkdir(parents=True, exist_ok=True)
            sandbox = Path(tempfile.mkdtemp(prefix=f"ncu_update_{self.run_id}_", dir=parent))
            self.report.sandbox = sandbox
            self.echo(f"\n建立沙盒：{sandbox}")
            create_sandbox(self.root, sandbox)
        return self.report.sandbox

    def run_build(self, steps: list[Step]) -> bool:
        if not any(self._gate(s) is None for s in steps):
            for step in steps:
                self._add(self._gate(step))   # type: ignore[arg-type]
            return True

        sandbox = self._ensure_sandbox()
        limits = ch.Limits(self.opts.max_shrink, self.opts.allow_shrink)

        ok_steps: list[Step] = []
        for i, step in enumerate(steps):
            gated = self._gate(step)
            if gated:
                self._add(gated)
                continue
            missing = missing_inputs(step, sandbox, self.opts.terms)
            if missing:
                self._add(StepResult(step.name, step.stage, "skipped", f"缺少輸入：{', '.join(missing)}"))
                continue
            self.echo(f"\n== {step.name}：{step.title}")
            ok, detail = self._run_commands(step, sandbox)
            if not ok:
                self._add(StepResult(step.name, step.stage, "failed", detail))
                self._mark_not_run(steps[i + 1:])
                return False
            changed = ch.changed_files(sandbox, self.root, step.outputs)
            errors = [e for rel in changed for e in ch.validate_file(rel, sandbox / rel, self.root / rel, limits)]
            errors += ch.paired_errors(changed, self.root)
            if errors:
                self._add(StepResult(step.name, step.stage, "failed", "驗證失敗：" + "；".join(errors), changed))
                self._mark_not_run(steps[i + 1:])
                return False
            self._add(StepResult(step.name, step.stage, "ok",
                                 f"{len(changed)} 個輸出檔有變動" if step.outputs else "", changed))
            ok_steps.append(step)

        declared = [o for s in ok_steps for o in s.outputs]
        all_changed = watched_changes(sandbox, self.root)
        promotable = [f for f in all_changed if ch.is_within(f, declared)]
        self.report.undeclared = [f for f in all_changed if not ch.is_within(f, declared)]
        self.report.changes = [ch.describe_change(f, sandbox / f, self.root / f) for f in promotable]
        if self.opts.apply and promotable:
            promote(promotable, sandbox, self.root, self.run_dir / "backup", self.run_id)
            self.report.promoted = True
        return True

    def _mark_not_run(self, steps: list[Step]) -> None:
        for s in steps:
            self._add(StepResult(s.name, s.stage, "not_run", "前面的步驟失敗"))

    def run_publish(self, steps: list[Step], upstream_ok: bool) -> bool:
        for step in steps:
            if not upstream_ok:
                self._add(StepResult(step.name, step.stage, "not_run", "前面的步驟失敗，不寫外部服務"))
                continue
            gated = self._gate(step)
            if gated:
                self._add(gated)
                continue
            missing = missing_inputs(step, self.root, self.opts.terms)
            if missing:
                self._add(StepResult(step.name, step.stage, "skipped", f"缺少輸入：{', '.join(missing)}"))
                continue
            self.echo(f"\n== {step.name}：{step.title}")
            ok, detail = self._run_commands(step, self.root)
            self._add(StepResult(step.name, step.stage, "ok" if ok else "failed", detail))
            if not ok:
                upstream_ok = False
        return upstream_ok

    def run(self) -> RunReport:
        for t in self.opts.terms:
            parse_term(t)
        selected = select_steps(self.opts, self.steps)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        mode = "套用（--apply）" if self.opts.apply else "dry-run（不寫入正式資料；加 --apply 才套用）"
        self.echo(f"資料更新 {self.run_id}｜模式：{mode}｜學期：{','.join(self.opts.terms)}")
        self.echo(f"步驟：{', '.join(s.name for s in selected) or '（無）'}")

        by_stage = {st: [s for s in selected if s.stage == st] for st in (FETCH, BUILD, CHECK, PUBLISH)}
        ok = self.run_fetch(by_stage[FETCH])
        if ok:
            ok = self.run_build(by_stage[BUILD] + by_stage[CHECK])
        else:
            self._mark_not_run(by_stage[BUILD] + by_stage[CHECK])
        self.run_publish(by_stage[PUBLISH], ok)

        self._finish()
        return self.report

    def _finish(self) -> None:
        rep = self.report
        sandbox = rep.sandbox
        if sandbox is not None:
            if rep.failed or self.opts.keep_sandbox:
                rep.messages.append(f"沙盒保留在 {sandbox}（除錯用，確認後可自行刪除）")
            else:
                shutil.rmtree(sandbox, ignore_errors=True)
        md = render_report(rep)
        (rep.run_dir / "summary.md").write_text(md, encoding="utf-8")
        (rep.run_dir / "summary.json").write_text(json.dumps(report_json(rep), ensure_ascii=False, indent=2),
                                                  encoding="utf-8")
        self.echo("\n" + md)
        self.echo(f"報告：{rep.run_dir / 'summary.md'}")


# ── 報告 ──────────────────────────────────────────────────────────────────

_STATUS_ZH = {"ok": "完成", "failed": "失敗", "skipped": "跳過", "planned": "計畫（dry-run）", "not_run": "未執行"}


def render_report(rep: RunReport) -> str:
    o = rep.options
    lines = [f"# 資料更新報告 {rep.run_id}", "",
             f"- 模式：{'套用' if o.apply else 'dry-run'}",
             f"- 學期：{', '.join(o.terms)}",
             f"- 結果：{'有步驟失敗，正式資料未變更' if rep.failed else '全部通過'}", "",
             "## 步驟", "", "| 步驟 | 階段 | 狀態 | 說明 |", "|---|---|---|---|"]
    for r in rep.results:
        detail = r.detail.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {r.name} | {r.stage} | {_STATUS_ZH[r.status]} | {detail} |")

    lines += ["", "## 資料變更", ""]
    if rep.changes:
        verb = "已套用到正式目錄" if rep.promoted else ("dry-run，未寫入" if not o.apply else "未套用")
        lines.append(f"共 {len(rep.changes)} 個檔案（{verb}）：")
        lines.append("")
        lines += [ch.format_change(c) for c in rep.changes]
        if rep.promoted:
            lines += ["", f"原檔備份在 `{(rep.run_dir / 'backup').as_posix()}`。"
                          "後端多數 JSON 有快取，需重啟後端才會讀到新資料。"]
    else:
        lines.append("沒有資料檔變動。")

    if rep.undeclared:
        lines += ["", "## 未宣告的變動（沒有套用）", "",
                  "下列檔案在沙盒裡被改到，但不在任何步驟宣告的輸出內，所以沒有套用：", ""]
        lines += [f"- `{f}`" for f in rep.undeclared[:50]]
        if len(rep.undeclared) > 50:
            lines.append(f"- …另外 {len(rep.undeclared) - 50} 個")

    if rep.messages:
        lines += ["", "## 其他", ""] + [f"- {m}" for m in rep.messages]
    return "\n".join(lines) + "\n"


def report_json(rep: RunReport) -> dict:
    return {
        "run_id": rep.run_id,
        "apply": rep.options.apply,
        "terms": list(rep.options.terms),
        "failed": rep.failed,
        "promoted": rep.promoted,
        "steps": [r.__dict__ for r in rep.results],
        "changes": [c.to_dict() for c in rep.changes],
        "undeclared": rep.undeclared,
        "messages": rep.messages,
    }
