# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""pytest-gpconf's logic (0.9.0 item c4, D-434), without pytest: pytest-gpconf/src/pytest_gpconf/core.py maps a real
gpconf run's report to one verdict per case, and the plugin file declares the pytest hooks it needs. The wiring under
pytest is untested on the machine that wrote it (no pytest there).

Run: python -m unittest tests.test_pytest_plugin"""
import ast
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pytest-gpconf", "src"))
from pytest_gpconf import core  # noqa: E402

TEMPLATE = os.path.join(ROOT, "templates", "python", "adapter.py")


class Core(unittest.TestCase):
    def test_a_real_run_maps_to_pass_and_skip(self):
        run = core.GpconfRun(cmd=f'"{sys.executable}" "{TEMPLATE}" {{fmt}}', root=ROOT,
                             cases=["alpha5-tle-derived", "corrupt-input", "kvn-syntax-variants"])
        env_path = os.environ.get("PYTHONPATH", "")
        os.environ["PYTHONPATH"] = ROOT + (os.pathsep + env_path if env_path else "")
        try:
            got = run.results()
        finally:
            os.environ["PYTHONPATH"] = env_path
            if not env_path:
                del os.environ["PYTHONPATH"]
        self.assertEqual(got["alpha5-tle-derived"].outcome, core.PASS)
        self.assertEqual(got["corrupt-input"].outcome, core.PASS)
        self.assertEqual(got["kvn-syntax-variants"].outcome, core.SKIP)   # the toy reads TLE only
        self.assertIn("unsupported", got["kvn-syntax-variants"].message)

    def test_a_failing_case_carries_its_failing_items(self):
        r = core.verdict({"case": "c", "status": "fail", "items": [
            {"check": "a", "status": "pass", "file": "f", "detail": ""},
            {"check": "b", "status": "fail", "file": "g.tle", "detail": "mean_motion reads 1 where 2"}]})
        self.assertEqual((r.outcome, len(r.failing)), (core.FAIL, 1))
        self.assertIn("[b] g.tle: mean_motion reads 1 where 2", r.message)

    def test_every_status_maps(self):
        for status, want in (("pass", core.PASS), ("pass-tolerance", core.PASS), ("fail", core.FAIL), ("skip", core.SKIP),
                             ("not-fetched", core.SKIP), ("not-available", core.SKIP), ("not-exercised", core.SKIP)):
            with self.subTest(status=status):
                self.assertEqual(core.verdict({"case": "c", "status": status, "items": []}).outcome, want)
        self.assertIn("gpconf fetch", core.verdict({"case": "c", "status": "not-fetched", "items": []}).message)

    def test_the_run_options_pass_through(self):
        # D-575: --data and four more of gpconf run's options (the design's gaps 1 and 2)
        run = core.GpconfRun(preset="reference", data="/d", sgp4_ver="/v", propagate=True, strict=True, tags=["a", "b"], cases=["c"])
        argv = run.argv
        for pair in (["--data", "/d"], ["--sgp4-ver", "/v"], ["--case", "c"], ["--tag", "a"], ["--tag", "b"]):
            self.assertTrue(any(argv[i:i + 2] == pair for i in range(len(argv))), (pair, argv))
        self.assertIn("--propagate", argv)
        self.assertIn("--strict", argv)
        self.assertNotIn("--data", core.GpconfRun(preset="reference").argv)

    def with_root_on_path(self, run):
        env_path = os.environ.get("PYTHONPATH", "")
        os.environ["PYTHONPATH"] = ROOT + (os.pathsep + env_path if env_path else "")
        try:
            return run.results(), run.ungraded()
        finally:
            os.environ["PYTHONPATH"] = env_path
            if not env_path:
                del os.environ["PYTHONPATH"]

    def test_a_session_that_grades_no_case_is_named(self):
        # the owner's ruling 8a (D-571, D-575): gpconf exits 2 when it grades nothing, and the plugin says so
        import tempfile
        with tempfile.TemporaryDirectory() as empty:
            run = core.GpconfRun(preset="reference", root=ROOT, data=empty, cases=["analyst-objects"])
            got, why = self.with_root_on_path(run)
        self.assertEqual(run.returncode, 2)
        self.assertEqual(got["analyst-objects"].outcome, core.SKIP)
        self.assertIn("no case was graded", why)

    def test_a_graded_session_is_not_flagged(self):
        run = core.GpconfRun(preset="reference", root=ROOT, cases=["alpha5-encoding-vectors"])
        _, why = self.with_root_on_path(run)
        self.assertIsNone(why)

    def test_a_report_without_the_fields_the_plugin_reads_stops_it(self):
        import json, tempfile
        from unittest import mock
        run = core.GpconfRun(preset="reference")

        def fake(argv, capture_output=None, text=None):
            out = argv[argv.index("--json") + 1]
            with open(out, "w", encoding="utf-8") as f:
                json.dump({"results": []}, f)
            return __import__("subprocess").CompletedProcess(argv, 0, "", "")
        with mock.patch("pytest_gpconf.core.subprocess.run", side_effect=fake):
            with self.assertRaises(RuntimeError) as e:
                run.results()
        self.assertIn("lacks gpconf, corpus_version", str(e.exception))

    def test_exactly_one_parser(self):
        with self.assertRaises(ValueError):
            core.GpconfRun()
        with self.assertRaises(ValueError):
            core.GpconfRun(preset="reference", cmd="x")


class Plugin(unittest.TestCase):
    def test_the_plugin_declares_its_hooks_and_the_entry_point(self):
        with open(os.path.join(ROOT, "pytest-gpconf", "src", "pytest_gpconf", "plugin.py"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        self.assertTrue({"pytest_addoption", "pytest_collection_modifyitems", "GpconfItem"} <= names)
        with open(os.path.join(ROOT, "pytest-gpconf", "pyproject.toml"), encoding="utf-8") as f:
            self.assertIn('gpconf = "pytest_gpconf.plugin"', f.read())


if __name__ == "__main__":
    unittest.main()
