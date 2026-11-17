"""資料更新管線（scripts/update_data）的測試。

全部在暫存目錄裡用假的 repo 跑，不連網、不呼叫任何 API、不碰 data/ 正式檔案。
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.update_data import changes as ch  # noqa: E402
from scripts.update_data import fetch, pipeline, proc  # noqa: E402
from scripts.update_data.steps import (BLOCKED, BUILD, CHECK, DESTRUCTIVE, EXTERNAL, PAID,  # noqa: E402
                                       PUBLISH, STEPS, Step)


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _load_script(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── 步驟登錄表與選擇 ──────────────────────────────────────────────────────

class StepRegistry(unittest.TestCase):
    def test_step_names_are_unique_and_not_blocked(self):
        names = [s.name for s in STEPS]
        self.assertEqual(len(names), len(set(names)))
        self.assertFalse(set(names) & set(BLOCKED))

    def test_every_command_script_exists(self):
        for s in STEPS:
            for cmd in s.commands:
                self.assertTrue((ROOT / cmd[0]).is_file(), f"{s.name}: {cmd[0]} 不存在")

    def test_paid_or_external_steps_are_never_free(self):
        for s in STEPS:
            if "embed" in s.cost or "Azure" in s.cost:
                self.assertIn(PAID, s.tags, s.name)
            if s.stage == PUBLISH:
                self.assertIn(EXTERNAL, s.tags, s.name)

    def test_steps_that_delete_external_data_need_destructive_flag(self):
        by_name = {s.name: s for s in STEPS}
        for name in ("qdrant_graph_nodes", "qdrant_course_vectors_rebuild"):
            self.assertTrue({PAID, EXTERNAL, DESTRUCTIVE} <= by_name[name].tags)

    def test_graph_sync_is_always_followed_by_community_rewrite(self):
        step = {s.name: s for s in STEPS}["qdrant_graph_nodes"]
        scripts = [c[0] for c in step.commands]
        self.assertEqual(scripts, ["scripts/rag/sync_graph_nodes.py", "scripts/rag/add_communities_to_qdrant.py"])

    def test_compute_communities_is_bound_to_labelling(self):
        step = {s.name: s for s in STEPS}["communities"]
        self.assertEqual([c[0] for c in step.commands],
                         ["scripts/graph/compute_communities.py", "scripts/graph/label_communities.py"])

    def test_no_step_uses_dangerous_modes(self):
        for s in STEPS:
            for cmd in s.commands:
                self.assertNotIn("--payload-only", cmd, s.name)
                self.assertNotIn("--enrich-only", cmd, s.name)
                self.assertNotIn("1_extract_pdf_metadata.py", cmd[0])
                self.assertNotIn("3b_summarize_with_azure.py", cmd[0])
                self.assertNotIn("process_course_domain.py", cmd[0])


class SelectSteps(unittest.TestCase):
    def test_defaults_skip_explicit_only_and_opt_in_steps(self):
        names = {s.name for s in pipeline.select_steps(pipeline.Options())}
        self.assertIn("course_index", names)
        for n in ("curriculum_merge_schedule", "qdrant_course_vectors_rebuild", "cloudinary_pdfs",
                  "glossary_frontend", "project_document_ids"):
            self.assertNotIn(n, names)

    def test_only_include_and_skip(self):
        only = pipeline.select_steps(pipeline.Options(only=("graph", "course_index")))
        self.assertEqual([s.name for s in only], ["course_index", "graph"])   # 依登錄表順序
        inc = {s.name for s in pipeline.select_steps(pipeline.Options(include=("curriculum_merge_schedule",)))}
        self.assertIn("curriculum_merge_schedule", inc)
        skipped = {s.name for s in pipeline.select_steps(pipeline.Options(skip=("graph",)))}
        self.assertNotIn("graph", skipped)

    def test_blocked_and_unknown_names_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "已被擋下"):
            pipeline.select_steps(pipeline.Options(only=("extract_pdf_metadata",)))
        with self.assertRaisesRegex(ValueError, "已被擋下"):
            pipeline.select_steps(pipeline.Options(include=("vector_payload_only",)))
        with self.assertRaisesRegex(ValueError, "沒有名為"):
            pipeline.select_steps(pipeline.Options(only=("nope",)))

    def test_missing_flags(self):
        step = {s.name: s for s in STEPS}["qdrant_graph_nodes"]
        self.assertEqual(pipeline.missing_flags(step, pipeline.Options()),
                         ["--allow-destructive", "--allow-external", "--allow-paid"])
        opts = pipeline.Options(allow_paid=True, allow_external=True, allow_destructive=True)
        self.assertEqual(pipeline.missing_flags(step, opts), [])

    def test_requires_expand_terms(self):
        step = {s.name: s for s in STEPS}["courses"]
        self.assertEqual(pipeline.expand_requires(step, ("115_1", "115_2")),
                         ["data/raw/courses/115_1", "data/raw/courses/115_2"])

    def test_missing_inputs_treats_empty_dir_as_missing(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "data/raw/courses/114_1").mkdir(parents=True)
            step = Step("x", BUILD, "x", requires=("data/raw/courses/{term}",))
            self.assertEqual(pipeline.missing_inputs(step, base, ("114_1",)), ["data/raw/courses/114_1"])
            _write_json(base / "data/raw/courses/114_1/a.json", [])
            self.assertEqual(pipeline.missing_inputs(step, base, ("114_1",)), [])


# ── 驗證與變更摘要 ────────────────────────────────────────────────────────

class Validation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.limits = ch.Limits(max_shrink=0.10)

    def tearDown(self):
        self.tmp.cleanup()

    def _pair(self, old, new, name="x.json"):
        o, n = self.d / f"old_{name}", self.d / f"new_{name}"
        if old is not None:
            _write_json(o, old)
        _write_json(n, new)
        return n, (o if old is not None else None)

    def test_empty_output_fails(self):
        n, o = self._pair([1, 2], [])
        self.assertTrue(any("沒有任何資料" in e for e in ch.validate_file("data/processed/x.json", n, o, self.limits)))

    def test_invalid_json_fails(self):
        n = self.d / "bad.json"
        n.write_text("{not json", encoding="utf-8")
        self.assertTrue(any("不是合法 JSON" in e for e in ch.validate_file("x.json", n, None, self.limits)))

    def test_large_shrink_fails_unless_allowed(self):
        n, o = self._pair(list(range(100)), list(range(80)))
        self.assertTrue(ch.validate_file("x.json", n, o, self.limits))
        self.assertEqual(ch.validate_file("x.json", n, o, ch.Limits(0.10, allow_shrink=True)), [])
        n2, o2 = self._pair(list(range(100)), list(range(95)), "y.json")
        self.assertEqual(ch.validate_file("y.json", n2, o2, self.limits), [])

    def test_graph_without_raw_courses_fails(self):
        old = {"nodes": [{"id": f"c{i}", "node_type": "Course", "source": "raw"} for i in range(50)], "links": []}
        new = {"nodes": [{"id": f"c{i}", "node_type": "Course", "source": "curriculum_only"} for i in range(50)],
               "links": []}
        n, o = self._pair(old, new)
        errors = ch.validate_file("data/processed/graph/knowledge_graph.json", n, o, self.limits)
        self.assertTrue(any("原始資料的課程節點" in e for e in errors))

    def test_duplicate_course_keys_fail(self):
        n, o = self._pair(None, [{"課號-班別": "CE1001-A"}, {"課號-班別": "CE1001-A"}])
        errors = ch.validate_file("data/processed/courses_deduped/undergrad.json", n, o, self.limits)
        self.assertTrue(any("重複" in e for e in errors))

    def test_describe_change_reports_added_and_removed_keys(self):
        old = [{"課號-班別": "A-1"}, {"課號-班別": "B-1"}]
        new = [{"課號-班別": "A-1"}, {"課號-班別": "C-1"}, {"課號-班別": "D-1"}]
        n, o = self._pair(old, new)
        c = ch.describe_change("data/processed/courses_deduped/undergrad.json", n, o)
        self.assertEqual((c.old_count, c.new_count, c.key, c.n_added, c.n_removed), (2, 3, "課號-班別", 2, 1))
        text = ch.format_change(c)
        self.assertIn("2 → 3 筆（+1）", text)
        self.assertIn("B-1", text)

    def test_graph_json_without_pkl_update_fails(self):
        _write_json(self.d / "data/processed/graph/knowledge_graph.pkl", [])
        json_rel = "data/processed/graph/knowledge_graph.json"
        pkl_rel = "data/processed/graph/knowledge_graph.pkl"
        self.assertTrue(ch.paired_errors([json_rel], self.d))
        self.assertEqual(ch.paired_errors([json_rel, pkl_rel], self.d), [])
        self.assertEqual(ch.paired_errors([json_rel], self.d / "no-pkl-here"), [])

    def test_describe_change_reports_node_type_counts(self):
        old = {"nodes": [{"id": "a", "node_type": "Course"}], "links": []}
        new = {"nodes": [{"id": "a", "node_type": "Course"}, {"id": "t", "node_type": "Teacher"}], "links": []}
        n, o = self._pair(old, new)
        c = ch.describe_change("g.json", n, o)
        self.assertEqual(c.node_types, {"Teacher": [0, 1]})


# ── 子程序與憑證控管 ──────────────────────────────────────────────────────

class Redaction(unittest.TestCase):
    def test_secret_values_are_masked(self):
        cases = {
            "AZURE_OPENAI_API_KEY=abc123": "AZURE_OPENAI_API_KEY=***",
            "token: 'xyz'": "token: '***'",
            "url postgres://user:pw@host/db": "url postgres://***:***@host/db",
            "Authorization: Bearer abcdefghijklmnop": "Authorization: Bearer ***",
        }
        for raw, expected in cases.items():
            self.assertEqual(proc.redact(raw), expected)

    def test_normal_lines_are_untouched(self):
        line = "[驗證] undergrad 重複 key 數：0（應為 0）"
        self.assertEqual(proc.redact(line), line)

    def test_free_steps_get_no_credentials(self):
        base = {"PATH": "x", "AZURE_OPENAI_API_KEY": "k", "QDRANT_URL": "u", "DATABASE_URL": "d"}
        env = proc.build_env(base, terms=["114_1"], credentials=None)
        self.assertNotIn("AZURE_OPENAI_API_KEY", env)
        self.assertNotIn("QDRANT_URL", env)
        self.assertNotIn("DATABASE_URL", env)
        self.assertEqual(env["NCU_DATA_TERMS"], "114_1")

    def test_credentialed_steps_prefer_shell_values(self):
        env = proc.build_env({"QDRANT_URL": "shell"}, terms=["114_1"],
                             credentials={"QDRANT_URL": "file", "AZURE_OPENAI_API_KEY": "k"})
        self.assertEqual(env["QDRANT_URL"], "shell")
        self.assertEqual(env["AZURE_OPENAI_API_KEY"], "k")


# ── 爬取分流 ──────────────────────────────────────────────────────────────

class FetchSplit(unittest.TestCase):
    def test_classify_by_known_lists_then_name(self):
        ug, grad = {"資訊工程學系"}, {"永續與綠能科技研究學院"}
        cases = {
            "資訊電機學院_資訊工程學系": "courses",
            "永續與綠能科技研究學院_永續與綠能科技研究學院": "graduate_courses",
            "管理學院_工業管理研究所碩士班": "graduate_courses",
            "客家學院_客家語文暨社會科學學系客家研究碩士在職專班": "graduate_courses",
            "管理學院_國際經營管理碩士學位學程": "graduate_courses",
            "中心、處室_體育室": "courses",
            "理學院_理學院學士班": "courses",
            # 假想的未來系所：名稱含「學位學程」但是大學部
            "理學院_數據科學學士學位學程": "courses",
        }
        for stem, level in cases.items():
            self.assertEqual(fetch.classify_dept_file(stem, ug, grad), level, stem)

    def test_existing_grad_names_all_classify_as_grad(self):
        grad_json = ROOT / "data/processed/courses_deduped/grad.json"
        ug_json = ROOT / "data/processed/courses_deduped/undergrad.json"
        if not grad_json.exists():
            self.skipTest("沒有 courses_deduped")
        ug = {c["系所"] for c in json.loads(ug_json.read_text(encoding="utf-8"))}
        grad = {c["系所"] for c in json.loads(grad_json.read_text(encoding="utf-8"))}
        # 只靠名稱規則（不給已知名單）時，研究所名稱幾乎都該被分到研究所，大學部都不該
        misfiled_ug = [d for d in ug if fetch.classify_dept_file(f"x_{d}", set(), set()) != "courses"]
        self.assertEqual(misfiled_ug, [])
        misfiled_grad = [d for d in grad if fetch.classify_dept_file(f"x_{d}", set(), set()) != "graduate_courses"]
        self.assertEqual(misfiled_grad, [])

    def test_parse_term(self):
        self.assertEqual(fetch.parse_term("115_2"), ("115", "2"))
        with self.assertRaises(ValueError):
            fetch.parse_term("1152")

    def test_check_term_rejects_incomplete_scrape(self):
        with tempfile.TemporaryDirectory() as d:
            root, staging = Path(d), Path(d) / "staging"
            _write_json(root / "data/raw/courses/114_1/a_甲學系.json", [{}] * 100)
            _write_json(staging / "a_甲學系.json", [{}] * 50)
            self.assertFalse(fetch.check_term(staging, root, "114_1", 0.1, False).ok)
            self.assertTrue(fetch.check_term(staging, root, "114_1", 0.1, True).ok)
            self.assertFalse(fetch.check_term(root / "empty", root, "114_1", 0.1, True).ok)

    def test_promote_term_splits_and_backs_up(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            backup = root / "logs/run"
            _write_json(root / "data/raw/courses/114_1/old_舊系.json", [{"x": 1}])
            staging = root / "logs/data_update/incoming/114_1"
            _write_json(staging / "理學院_物理學系.json", [{}])
            _write_json(staging / "理學院_統計研究所碩士班.json", [{}])
            counts = fetch.promote_term(staging, root, "114_1", backup, set(), set())
            self.assertEqual(counts, {"courses": 1, "graduate_courses": 1})
            self.assertEqual([p.name for p in (root / "data/raw/courses/114_1").iterdir()], ["理學院_物理學系.json"])
            self.assertTrue((root / "data/raw/graduate_courses/114_1/理學院_統計研究所碩士班.json").exists())
            self.assertTrue((backup / "raw/courses/114_1/old_舊系.json").exists())
            self.assertFalse(staging.exists())

    def test_fetch_failure_leaves_raw_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write_json(root / "data/raw/courses/114_1/a_甲學系.json", [{}] * 10)
            ok, detail = fetch.fetch_courses(
                root=root, run_dir=root / "logs/run", terms=["114_1"], python="py",
                run=lambda argv: 1, log=lambda s: None, max_shrink=0.1, allow_shrink=False, fresh=False)
            self.assertFalse(ok)
            self.assertIn("續爬", detail)
            self.assertTrue((root / "data/raw/courses/114_1/a_甲學系.json").exists())


# ── 沙盒與套用 ────────────────────────────────────────────────────────────

class SandboxAndPromote(unittest.TestCase):
    def test_sandbox_excludes_env_and_large_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            (root / "backend").mkdir(parents=True)
            (root / "backend/.env").write_text("SECRET=1", encoding="utf-8")
            (root / "backend/app.py").write_text("", encoding="utf-8")
            (root / "scripts/__pycache__").mkdir(parents=True)
            _write_json(root / "data/processed/a.json", [1])
            _write_json(root / "data/raw/projects/104-114/x.json", [1])
            _write_json(root / "data/processed/qdrant_data/x.json", [1])
            sb = pipeline.create_sandbox(root, Path(d) / "sb")
            self.assertTrue((sb / "backend/app.py").exists())
            self.assertFalse((sb / "backend/.env").exists())
            self.assertFalse((sb / "scripts/__pycache__").exists())
            self.assertTrue((sb / "data/processed/a.json").exists())
            self.assertFalse((sb / "data/raw/projects").exists())
            self.assertFalse((sb / "data/processed/qdrant_data").exists())
            self.assertTrue((sb / "logs").is_dir())

    def test_promote_backs_up_and_rolls_back_on_failure(self):
        with tempfile.TemporaryDirectory() as d:
            root, sb, backup = Path(d) / "root", Path(d) / "sb", Path(d) / "backup"
            _write_json(root / "data/a.json", ["old"])
            _write_json(sb / "data/a.json", ["new"])
            _write_json(sb / "data/b.json", ["new"])
            real_replace = os.replace
            calls = []

            def flaky(src, dst):
                calls.append(dst)
                if len(calls) == 2:
                    raise OSError("disk full")
                real_replace(src, dst)

            with mock.patch.object(pipeline.os, "replace", side_effect=flaky):
                with self.assertRaises(OSError):
                    pipeline.promote(["data/a.json", "data/b.json"], sb, root, backup, "t")
            self.assertEqual(json.loads((root / "data/a.json").read_text(encoding="utf-8")), ["old"])
            self.assertFalse((root / "data/b.json").exists())

            pipeline.promote(["data/a.json", "data/b.json"], sb, root, backup, "t")
            self.assertEqual(json.loads((root / "data/a.json").read_text(encoding="utf-8")), ["new"])
            self.assertEqual(json.loads((backup / "data/a.json").read_text(encoding="utf-8")), ["old"])

    def test_promote_cleans_temp_file_when_replace_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root, sb, backup = Path(d) / "root", Path(d) / "sb", Path(d) / "backup"
            _write_json(root / "data/a.json", ["old"])
            _write_json(sb / "data/a.json", ["new"])
            with mock.patch.object(pipeline, "REPLACE_RETRY_DELAY", 0), \
                    mock.patch.object(pipeline.os, "replace", side_effect=PermissionError("locked")):
                with self.assertRaises(PermissionError):
                    pipeline.promote(["data/a.json"], sb, root, backup, "t")
            self.assertEqual([p.name for p in (root / "data").iterdir()], ["a.json"])
            self.assertEqual(json.loads((root / "data/a.json").read_text(encoding="utf-8")), ["old"])

    def test_promote_retries_when_target_briefly_locked(self):
        with tempfile.TemporaryDirectory() as d:
            root, sb, backup = Path(d) / "root", Path(d) / "sb", Path(d) / "backup"
            _write_json(root / "data/a.json", ["old"])
            _write_json(sb / "data/a.json", ["new"])
            real_replace, calls = os.replace, []

            def locked_twice(src, dst):
                calls.append(dst)
                if len(calls) <= 2:
                    raise PermissionError("locked")
                real_replace(src, dst)

            with mock.patch.object(pipeline, "REPLACE_RETRY_DELAY", 0), \
                    mock.patch.object(pipeline.os, "replace", side_effect=locked_twice):
                pipeline.promote(["data/a.json"], sb, root, backup, "t")
            self.assertEqual(len(calls), 3)
            self.assertEqual(json.loads((root / "data/a.json").read_text(encoding="utf-8")), ["new"])


# ── 端對端：假 repo ───────────────────────────────────────────────────────

FAKE_SCRIPT = textwrap.dedent("""
    import json, os, sys
    from pathlib import Path
    ROOT = Path(__file__).resolve().parents[2]
    out = ROOT / "data" / "processed" / "items.json"
    mode = sys.argv[1]
    if mode == "grow":
        out.write_text(json.dumps([{"id": "a"}, {"id": "b"}, {"id": "c"}]), encoding="utf-8")
    elif mode == "empty":
        out.write_text("[]", encoding="utf-8")
    elif mode == "fail":
        print("api_key=should-be-hidden")
        sys.exit(3)
    elif mode == "stray":
        (ROOT / "data" / "processed" / "stray.json").write_text("[1]", encoding="utf-8")
        out.write_text(json.dumps([{"id": "a"}, {"id": "b"}, {"id": "z"}]), encoding="utf-8")
    elif mode == "envcheck":
        print("HAS_KEY" if os.environ.get("AZURE_OPENAI_API_KEY") else "NO_KEY")
        print("TERMS=" + os.environ.get("NCU_DATA_TERMS", ""))
    elif mode == "publish":
        (ROOT / "published.txt").write_text("yes", encoding="utf-8")
""")


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "repo"
        (self.root / "scripts/fake").mkdir(parents=True)
        (self.root / "scripts/fake/w.py").write_text(FAKE_SCRIPT, encoding="utf-8")
        _write_json(self.root / "data/processed/items.json", [{"id": "a"}, {"id": "b"}])
        self.sandbox_parent = base / "sandboxes"
        self.lines: list[str] = []

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, steps, **opts):
        env = dict(os.environ, AZURE_OPENAI_API_KEY="fake-key-for-test")
        p = pipeline.Pipeline(pipeline.Options(**opts), root=self.root, python=sys.executable,
                              echo=self.lines.append, env=env, sandbox_parent=self.sandbox_parent,
                              steps=tuple(steps))
        with mock.patch.object(pipeline, "load_env_files", return_value={}):
            return p.run()

    def _items(self):
        return json.loads((self.root / "data/processed/items.json").read_text(encoding="utf-8"))

    def _build(self, mode, name="items", **kw):
        return Step(name, BUILD, "t", commands=(("scripts/fake/w.py", mode),),
                    outputs=("data/processed/items.json",), **kw)

    def test_dry_run_reports_without_writing(self):
        rep = self._run([self._build("grow")])
        self.assertFalse(rep.failed)
        self.assertFalse(rep.promoted)
        self.assertEqual(len(self._items()), 2)
        self.assertEqual([(c.path, c.old_count, c.new_count, c.n_added) for c in rep.changes],
                         [("data/processed/items.json", 2, 3, 1)])
        summary = (rep.run_dir / "summary.md").read_text(encoding="utf-8")
        self.assertIn("dry-run，未寫入", summary)
        self.assertFalse(any(self.sandbox_parent.iterdir()))   # 成功就刪除沙盒

    def test_apply_promotes_with_backup(self):
        rep = self._run([self._build("grow")], apply=True)
        self.assertTrue(rep.promoted)
        self.assertEqual(len(self._items()), 3)
        backup = rep.run_dir / "backup/data/processed/items.json"
        self.assertEqual(len(json.loads(backup.read_text(encoding="utf-8"))), 2)

    def test_validation_failure_keeps_existing_data(self):
        rep = self._run([self._build("empty"), self._build("grow", name="later")], apply=True)
        self.assertTrue(rep.failed)
        self.assertEqual([r.status for r in rep.results], ["failed", "not_run"])
        self.assertEqual(len(self._items()), 2)
        self.assertIsNotNone(rep.sandbox)
        self.assertTrue(rep.sandbox.exists())   # 失敗時保留沙盒

    def test_script_failure_keeps_existing_data_and_masks_output(self):
        rep = self._run([self._build("fail")], apply=True)
        self.assertTrue(rep.failed)
        self.assertEqual(len(self._items()), 2)
        log = (rep.run_dir / "steps/items.log").read_text(encoding="utf-8")
        self.assertIn("api_key=***", log)
        self.assertNotIn("should-be-hidden", log)

    def test_later_step_clobbering_earlier_output_fails_final_validation(self):
        (self.root / "scripts/fake/z.py").write_text(textwrap.dedent("""
            from pathlib import Path
            R = Path(__file__).resolve().parents[2]
            (R / "data/processed/items.json").write_text("[]", encoding="utf-8")
            (R / "data/processed/other.json").write_text("[1]", encoding="utf-8")
        """), encoding="utf-8")
        clobber = Step("b", BUILD, "t", commands=(("scripts/fake/z.py",),),
                       outputs=("data/processed/other.json",))
        rep = self._run([self._build("grow"), clobber], apply=True)
        self.assertTrue(rep.failed)
        self.assertFalse(rep.promoted)
        self.assertEqual(rep.results[-1].name, "final_validation")
        self.assertIn("items.json", rep.results[-1].detail)
        self.assertEqual(len(self._items()), 2)
        self.assertFalse((self.root / "data/processed/other.json").exists())

    def test_promote_failure_writes_report_and_restores(self):
        with mock.patch.object(pipeline, "_replace_with_retry", side_effect=PermissionError("locked")):
            rep = self._run([self._build("grow")], apply=True)
        self.assertTrue(rep.failed)
        self.assertFalse(rep.promoted)
        self.assertEqual((rep.results[-1].name, rep.results[-1].status), ("promote", "failed"))
        summary = (rep.run_dir / "summary.md").read_text(encoding="utf-8")
        self.assertIn("套用到正式目錄失敗", summary)
        self.assertEqual(len(self._items()), 2)
        self.assertEqual([f.name for f in (self.root / "data/processed").iterdir()], ["items.json"])

    def test_undeclared_writes_are_not_promoted(self):
        rep = self._run([self._build("stray")], apply=True)
        self.assertEqual(rep.undeclared, ["data/processed/stray.json"])
        self.assertFalse((self.root / "data/processed/stray.json").exists())
        self.assertEqual([i["id"] for i in self._items()], ["a", "b", "z"])

    def test_free_steps_cannot_see_credentials(self):
        step = Step("env", CHECK, "t", commands=(("scripts/fake/w.py", "envcheck"),))
        self._run([step], terms=("115_1", "115_2"))
        self.assertTrue(any("NO_KEY" in line for line in self.lines))
        self.assertTrue(any("TERMS=115_1,115_2" in line for line in self.lines))

    def test_paid_and_publish_steps_are_gated(self):
        paid = Step("paid", BUILD, "t", commands=(("scripts/fake/w.py", "envcheck"),), tags=frozenset({PAID}))
        pub = Step("pub", PUBLISH, "t", commands=(("scripts/fake/w.py", "publish"),), tags=frozenset({EXTERNAL}))

        rep = self._run([paid, pub])                                   # 沒旗標
        self.assertEqual([r.status for r in rep.results], ["skipped", "skipped"])
        rep = self._run([paid, pub], allow_paid=True, allow_external=True)   # 有旗標但 dry-run
        self.assertEqual([r.status for r in rep.results], ["planned", "planned"])
        self.assertFalse((self.root / "published.txt").exists())

        rep = self._run([paid, pub], apply=True, allow_paid=True, allow_external=True)
        self.assertEqual([r.status for r in rep.results], ["ok", "ok"])
        self.assertTrue(any("HAS_KEY" in line for line in self.lines))
        self.assertTrue((self.root / "published.txt").exists())

    def test_results_follow_registry_order(self):
        paid = Step("paid", BUILD, "t", commands=(("scripts/fake/w.py", "envcheck"),), tags=frozenset({PAID}))
        rep = self._run([self._build("grow", name="first"), paid, self._build("grow", name="last")])
        self.assertEqual([r.name for r in rep.results], ["first", "paid", "last"])
        self.assertEqual([r.status for r in rep.results], ["ok", "skipped", "ok"])

    def test_publish_does_not_run_after_build_failure(self):
        pub = Step("pub", PUBLISH, "t", commands=(("scripts/fake/w.py", "publish"),), tags=frozenset({EXTERNAL}))
        rep = self._run([self._build("fail"), pub], apply=True, allow_external=True)
        self.assertEqual([r.status for r in rep.results], ["failed", "not_run"])
        self.assertFalse((self.root / "published.txt").exists())


class RealCoursesStep(unittest.TestCase):
    """用真的 deduplicate_courses / parse_distribution_conditions 跑 courses 步驟（假資料、暫存 repo）。"""

    def _course(self, code, dept, college="理學院"):
        return {"學年度": "115", "學期": "1", "學院": college, "系所": dept, "流水號": code,
                "課號-班別": code, "課程名稱(中文)": f"課{code}", "授課教師": "王老師", "學分": "3",
                "分發條件": {"限制說明": "課程沒有限制"}, "課程綱要": {}}

    def test_courses_step_with_new_term(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "repo"
            for name in ("deduplicate_courses.py", "parse_distribution_conditions.py"):
                dst = root / "scripts/extraction/course_programs" / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes((ROOT / "scripts/extraction/course_programs" / name).read_bytes())
            _write_json(root / "data/raw/courses/115_1/理學院_物理學系.json",
                        [self._course("PH1001-A", "物理學系"), self._course("PH1002-A", "物理學系")])
            _write_json(root / "data/raw/graduate_courses/115_1/理學院_統計研究所碩士班.json",
                        [self._course("ST5001-*", "統計研究所碩士班")])
            # 舊學期資料不該被讀進來
            _write_json(root / "data/raw/courses/114_1/理學院_物理學系.json", [self._course("OLD0001-A", "物理學系")])

            step = {s.name: s for s in STEPS}["courses"]
            lines: list[str] = []
            rep = pipeline.Pipeline(pipeline.Options(apply=True, terms=("115_1",)), root=root,
                                    python=sys.executable, echo=lines.append,
                                    sandbox_parent=Path(d) / "sb", steps=(step,)).run()
            self.assertFalse(rep.failed, "\n".join(lines[-30:]))
            ug = json.loads((root / "data/processed/courses_deduped/undergrad.json").read_text(encoding="utf-8"))
            grad = json.loads((root / "data/processed/courses_deduped/grad.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(c["課號-班別"] for c in ug), ["PH1001-A", "PH1002-A"])
            self.assertEqual([c["課號-班別"] for c in grad], ["ST5001-*"])
            self.assertTrue((root / "data/processed/course_eligibility.json").exists())
            self.assertTrue((root / "data/processed/dept_college_map.json").exists())


# ── 被修改的既有腳本 ──────────────────────────────────────────────────────

class ExistingScriptFixes(unittest.TestCase):
    def test_guarded_scripts_refuse_to_run(self):
        for rel in ("scripts/extraction/projects_pdf/1_extract_pdf_metadata.py",
                    "scripts/extraction/course_programs/process_course_domain.py",
                    "scripts/extraction/projects_pdf/3b_summarize_with_azure.py"):
            env = proc.strip_credentials(os.environ)
            r = subprocess.run([sys.executable, str(ROOT / rel)], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", env=dict(env, PYTHONIOENCODING="utf-8"),
                               cwd=tempfile.gettempdir(), timeout=60)
            self.assertNotEqual(r.returncode, 0, rel)
            self.assertIn("已停用", r.stderr + r.stdout, rel)

    def test_subdirectory_scripts_resolve_repo_root(self):
        for rel in ("scripts/extraction/curriculum_maps/convert_to_png.py",
                    "scripts/extraction/curriculum_maps/extract_curriculum_map.py",
                    "scripts/extraction/requirements/export_tables_html.py",
                    "scripts/extraction/requirements/extract_requirements_pdfplumber.py",
                    "scripts/extraction/requirements/parse_requirements_table.py",
                    "scripts/extraction/course_programs/parse_programs.py"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("BASE_DIR", text, rel)
            self.assertIn("Path(__file__).resolve().parents[3]", text, rel)
        for rel in ("scripts/extraction/projects_pdf/3a_extract_pdf_sections.py",
                    "scripts/extraction/projects_pdf/3c_extract_abstract.py"):
            self.assertIn("os.path.join(SCRIPT_DIR, '..', '..', '..')", (ROOT / rel).read_text(encoding="utf-8"))
        for rel in ("scripts/extraction/requirements/fix_requirements_notes.py",
                    "scripts/extraction/requirements/fix_notes_newlines.py",
                    "scripts/extraction/course_programs/extract_program_descriptions.py"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("'data/raw/", text, rel)
            self.assertNotIn("Path('data/", text, rel)

    def test_dedupe_terms_follow_env(self):
        with mock.patch.dict(os.environ, {"NCU_DATA_TERMS": "115_1,115_2"}):
            mod = _load_script("dedupe_t", "scripts/extraction/course_programs/deduplicate_courses.py")
        self.assertEqual(mod.TERMS, ["115_1", "115_2"])
        mod_default = _load_script("dedupe_d", "scripts/extraction/course_programs/deduplicate_courses.py")
        self.assertEqual(mod_default.TERMS, ["114_1", "114_2"])

    def test_sync_graph_nodes_never_deletes_community_points(self):
        try:
            mod = _load_script("sync_graph_nodes_t", "scripts/rag/sync_graph_nodes.py")
        except ImportError as e:
            self.skipTest(f"缺少依賴：{e}")
        existing = {1: {"node_type": "Concept"}, 2: {"node_type": "Community"}, 3: {"node_type": "Concept"}}
        expected = {3: {"node_type": "Concept"}, 4: {"node_type": "Concept"}}
        p = mod.plan(existing, expected)
        self.assertEqual(p["delete"], [1])
        self.assertEqual(p["add"], [4])

    def test_sync_graph_nodes_deletes_only_stale_community_points(self):
        try:
            mod = _load_script("sync_graph_nodes_t2", "scripts/rag/sync_graph_nodes.py")
        except ImportError as e:
            self.skipTest(f"缺少依賴：{e}")
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "communities.json"
            _write_json(path, [{"id": 0}, {"id": 1}])
            keep = mod.current_community_ids(path)
            self.assertIsNone(mod.current_community_ids(Path(d) / "missing.json"))
        live = mod.bq._node_id_to_int("community::0")
        stale = mod.bq._node_id_to_int("community::99")
        self.assertIn(live, keep)
        existing = {live: {"node_type": "Community"}, stale: {"node_type": "Community"},
                    7: {"node_type": "Concept"}}
        p = mod.plan(existing, {}, keep)
        self.assertEqual(sorted(p["delete"]), sorted([stale, 7]))
        # 讀不到 communities.json（keep_ids=None）時全部保留，不刪任何社群點
        self.assertEqual(mod.plan(existing, {}, None)["delete"], [7])

    def test_content_scraper_checkpoint_uses_course_identity(self):
        try:
            mod = _load_script("scrape_content_t", "scripts/scrapers/scrape_content_by_url.py")
        except ImportError as e:
            self.skipTest(f"缺少依賴：{e}")
        f = Path("data/raw/courses/114_1/a.json")
        k1 = mod.checkpoint_key(f, {"課號-班別": "CE1001-A", "學年度": "114", "學期": "1"})
        k2 = mod.checkpoint_key(f, {"課號-班別": "CE1002-A", "學年度": "114", "學期": "1"})
        self.assertNotEqual(k1, k2)
        self.assertIn("CE1001-A", k1)

    def test_vector_payload_only_requires_force_flag(self):
        text = (ROOT / "scripts/rag/build_vector_index.py").read_text(encoding="utf-8")
        self.assertIn("if args.payload_only and not args.force_payload_only", text)


# ── 課程爬蟲：失敗要回報失敗 ───────────────────────────────────────────────

class _El:
    """假的 Selenium 元素：children 依 tag 名稱回傳子元素。"""

    def __init__(self, text="", children=None, on_click=None):
        self.text, self.children, self.on_click = text, children or {}, on_click

    def find_elements(self, _by, tag):
        return self.children.get(tag, [])

    def find_element(self, _by, tag):
        return self.children[tag][0]

    def click(self):
        if self.on_click:
            self.on_click()


class _DeptListDriver:
    """只有系所清單頁的假瀏覽器；點系所連結只記錄目前在哪個系所。"""

    current_url = "dept-list"

    def __init__(self, depts):
        self.page = None
        rows = [_El()]  # 表頭
        for college, dept in depts:
            link = _El(on_click=lambda dept=dept: setattr(self, "page", dept))
            rows.append(_El(children={"td": [_El(college), _El(dept), _El(children={"a": [link]})]}))
        self.table = _El(children={"tr": rows})

    def find_elements(self, _by, tag):
        return [self.table] if tag == "table" else []

    def get(self, url):
        self.page = None

    def quit(self):
        pass


class _BoomDriver:
    current_url = "x"

    def find_elements(self, *a, **k):
        raise RuntimeError("stale element / timeout 模擬")

    def get(self, url):
        pass

    def quit(self):
        pass


class CourseScraperFailures(unittest.TestCase):
    def setUp(self):
        try:
            self.mod = _load_script("ncu_scraper_v2_t", "scripts/scrapers/ncu_course_scraper_v2.py")
        except ImportError as e:
            self.skipTest(f"缺少依賴：{e}")
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        sleep = mock.patch.object(self.mod.time, "sleep", lambda s: None)
        sleep.start()
        self.addCleanup(sleep.stop)
        self.addCleanup(self.tmp.cleanup)

    def _scraper(self, driver, results=None):
        s = object.__new__(self.mod.NCUCourseScraperV2)
        s.driver, s.output_dir, s.data_dir = driver, str(self.out), str(self.out)
        s.year, s.semester = "115", "1"
        s.navigate_to_course_page = lambda: True
        if results is not None:
            def fake(college, dept):
                r = results[dept]
                if isinstance(r, Exception):
                    raise r
                return r
            s.scrape_courses_with_pagination = fake
        return s

    def test_unreadable_dept_list_fails_run_and_main(self):
        with mock.patch("sys.stdout"):
            self.assertFalse(self._scraper(_BoomDriver()).run())
            inst = self._scraper(_BoomDriver())
            with mock.patch.object(self.mod, "NCUCourseScraperV2", return_value=inst):
                self.assertEqual(self.mod.main(["--semesters", "1", "--output-dir", str(self.out)]), 1)

    def test_incomplete_or_crashed_dept_is_not_saved_and_run_fails(self):
        depts = [("理學院", "物理學系"), ("理學院", "數學系"), ("理學院", "化學系")]
        results = {"物理學系": ([{"課號": "PH1"}], True),
                   "數學系": ([{"課號": "MA1"}], False),  # 翻頁到一半出錯
                   "化學系": RuntimeError("點擊逾時")}
        s = self._scraper(_DeptListDriver(depts), results)
        with mock.patch("sys.stdout"):
            self.assertFalse(s.run())
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["理學院_物理學系.json"])
        self.assertEqual(sorted(n for n, _ in s.failed_depts), ["理學院_化學系", "理學院_數學系"])

        # 續爬：已成功的跳過，失敗的重爬，全部成功才回傳 True
        results.update({"數學系": ([{"課號": "MA1"}], True), "化學系": ([{"課號": "CH1"}], True)})
        s2 = self._scraper(_DeptListDriver(depts), results)
        with mock.patch("sys.stdout"):
            self.assertTrue(s2.run())
        self.assertEqual(len(list(self.out.glob("*.json"))), 3)
        self.assertEqual(list(self.out.glob("*.tmp")), [])

    def test_pagination_error_marks_result_incomplete(self):
        s = self._scraper(_BoomDriver())
        with mock.patch("sys.stdout"):
            courses, complete = s.scrape_courses_with_pagination("理學院", "物理學系")
        self.assertEqual(courses, [])
        self.assertFalse(complete)

    def test_empty_dept_list_is_a_failure(self):
        s = self._scraper(_DeptListDriver([]), {})
        with mock.patch("sys.stdout"):
            self.assertFalse(s.run())


# ── 補課綱：斷點在重爬後重置、出錯不記斷點 ─────────────────────────────────

def _course(code, filled=False):
    return {"課號-班別": code, "學年度": "114", "學期": "1", "系所": "物理學系",
            "課程名稱(中文)": code, "課程綱要_連結": f"https://example.invalid/{code}",
            "課程綱要": {"課程目標": "這門課的目標說明文字很長" if filled else ""}}


class ContentScraperCheckpoint(unittest.TestCase):
    def setUp(self):
        try:
            self.mod = _load_script("scrape_content_t2", "scripts/scrapers/scrape_content_by_url.py")
        except ImportError as e:
            self.skipTest(f"缺少依賴：{e}")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_errors_are_not_checkpointed(self):
        d = self.root / "data/raw/courses/114_1"
        f = d / "理學院_物理學系.json"
        _write_json(f, [_course("A"), _course("B"), _course("C")])

        def fake(driver, course, dry_run):
            code = course["課號-班別"]
            if code == "A":
                course["課程綱要"]["課程目標"] = "補回來的課程目標說明文字"
                return True, False
            if code == "B":
                return False, True  # 頁面載入失敗
            raise RuntimeError("driver 掛掉")

        done: set[str] = set()
        with mock.patch("sys.stdout"):
            counts = self.mod.process_file(None, f, [0, 1, 2], done, dry_run=False, scrape=fake, pause=0)
        self.assertEqual(counts, {"processed": 3, "updated": 1, "errors": 2})
        self.assertEqual(done, {self.mod.checkpoint_key(f, _course("A"))})
        saved = json.loads(f.read_text(encoding="utf-8"))
        self.assertIn("補回來", saved[0]["課程綱要"]["課程目標"])
        self.assertEqual(list(d.glob("*.tmp")), [])

        self.mod.save_checkpoint(d, done)
        pending, _ = self.mod.pending_targets([d])
        # A 已補齊（不再是待補）、B 與 C 出錯沒記斷點，下次重試
        self.assertEqual([i for _, i in pending], [1, 2])

    def test_dry_run_does_not_checkpoint_or_write(self):
        d = self.root / "data/raw/courses/114_1"
        f = d / "a.json"
        _write_json(f, [_course("A")])
        before = f.read_text(encoding="utf-8")
        done: set[str] = set()
        with mock.patch("sys.stdout"):
            self.mod.process_file(None, f, [0], done, dry_run=True,
                                  scrape=lambda drv, c, dry_run: (True, False), pause=0)
        self.assertEqual(done, set())
        self.assertEqual(f.read_text(encoding="utf-8"), before)

    def test_checkpoint_resets_after_rescrape(self):
        term_dir = self.root / "data/raw/courses/114_1"
        f = term_dir / "理學院_物理學系.json"
        _write_json(f, [_course("A")])
        # 上一輪補課綱時「無新資料」的課也會記進斷點
        self.mod.save_checkpoint(term_dir, {self.mod.checkpoint_key(f, _course("A"))})
        self.assertEqual(self.mod.pending_targets([term_dir])[0], [])
        self.assertEqual(fetch.count_courses([term_dir]), (1, 1))  # 斷點檔不算系所檔

        # 定期 --fetch --apply：重爬後課綱又是空的，整個學期目錄被換掉
        staging = self.root / "logs/data_update/incoming/114_1"
        _write_json(staging / "理學院_物理學系.json", [_course("A")])
        fetch.promote_term(staging, self.root, "114_1", self.root / "logs/run", set(), set())

        self.assertFalse((term_dir / self.mod.CHECKPOINT_NAME).exists())
        pending, done = self.mod.pending_targets([term_dir])
        self.assertEqual(pending, [(f, 0)])
        self.assertEqual(done[term_dir], set())

    def _main(self, courses, scrape=None, driver=None, argv=("--headless",)):
        d = self.root / "data/raw/courses/114_1"
        _write_json(d / "a.json", courses)
        calls = []

        def counting(drv, course, dry_run):
            calls.append(course["課號-班別"])
            return scrape(drv, course, dry_run)

        patches = [mock.patch.object(self.mod, "COURSE_DIRS", [d]),
                   mock.patch.object(self.mod.time, "sleep", lambda s: None),
                   mock.patch.object(self.mod, "make_driver", lambda headless=False: driver or _BoomDriver()),
                   mock.patch("sys.stdout")]
        if scrape is not None:
            patches.append(mock.patch.object(self.mod, "scrape_course", counting))
        for p in patches:
            p.start()
        try:
            rc = self.mod.main(list(argv))
        finally:
            for p in reversed(patches):
                p.stop()
        return rc, calls, self.mod.load_checkpoint(d)

    def test_dead_driver_exits_nonzero(self):
        class Dead:
            def get(self, url):
                raise RuntimeError("invalid session id")

            def quit(self):
                pass

        rc, _, done = self._main([_course("A"), _course("B")], driver=Dead())
        self.assertEqual(rc, 1)
        self.assertEqual(done, set())

    def test_consecutive_errors_abort_early(self):
        rc, calls, done = self._main([_course(f"C{i:02d}") for i in range(15)],
                                     scrape=lambda drv, c, dry_run: (False, True))
        self.assertEqual(rc, 1)
        self.assertEqual(len(calls), 10)   # 預設連續 10 筆出錯就中止
        self.assertEqual(done, set())

    def test_few_errors_still_succeed(self):
        def one_bad(drv, course, dry_run):
            return False, course["課號-班別"] == "C03"

        rc, calls, done = self._main([_course(f"C{i:02d}") for i in range(10)], scrape=one_bad)
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 10)
        self.assertEqual(len(done), 9)

    def test_high_error_rate_exits_nonzero(self):
        def every_other(drv, course, dry_run):
            return False, int(course["課號-班別"][1:]) % 2 == 0

        rc, calls, done = self._main([_course(f"C{i:02d}") for i in range(10)], scrape=every_other)
        self.assertEqual(rc, 1)            # 5/10 出錯 > 20%
        self.assertEqual(len(calls), 10)   # 沒有連續 10 筆，不會提早中止
        self.assertEqual(len(done), 5)

    def test_nothing_pending_exits_zero(self):
        rc, calls, _ = self._main([_course("A", filled=True)], scrape=lambda *a, **k: (True, False))
        self.assertEqual((rc, calls), (0, []))

    def test_error_page_is_not_treated_as_no_data(self):
        class Busy:
            def get(self, url):
                pass

            def find_element(self, by, value):
                if value == "body":
                    return _El("系統忙碌，請稍後再試")
                raise RuntimeError("no element")

            def find_elements(self, *a):
                return []

        course = _course("A")
        with mock.patch.object(self.mod.time, "sleep", lambda s: None), mock.patch("sys.stdout"):
            self.assertEqual(self.mod.scrape_course(Busy(), course, dry_run=False), (False, True))
        self.assertTrue(self.mod.is_outline_page({"課號": "CE1001", "課程目標": ""}))
        self.assertFalse(self.mod.is_outline_page({"核心能力": []}))

    def test_legacy_checkpoint_file_is_ignored(self):
        self.assertFalse(hasattr(self.mod, "CHECKPOINT_PATH"))
        text = (ROOT / "scripts/scrapers/scrape_content_by_url.py").read_text(encoding="utf-8")
        self.assertNotIn("CHECKPOINT_PATH", text)


class CommandLine(unittest.TestCase):
    def test_list_runs_and_shows_blocked(self):
        r = subprocess.run([sys.executable, "-m", "scripts.update_data", "--list"], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("qdrant_graph_nodes", r.stdout)
        self.assertIn("extract_pdf_metadata", r.stdout)

    def test_blocked_step_exits_with_error(self):
        from scripts.update_data.__main__ import main
        with mock.patch("sys.stderr"):
            self.assertEqual(main(["--only", "summarize_with_azure"]), 2)


if __name__ == "__main__":
    unittest.main()
