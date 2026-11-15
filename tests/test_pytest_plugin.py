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
