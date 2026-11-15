# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The results schema (0.9.0 item d2, D-431): reports gpconf writes match gpconf/schemas/results-1.0.schema.json, the
schema's statuses are the runner's, and the validator finds what does not match.

Run: python -m unittest tests.test_results_schema"""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import schema as S  # noqa: E402
from gpconf.__main__ import main as gpconf_main  # noqa: E402
from gpconf.runner import CASE_STATUSES  # noqa: E402

REPORTS = {}


def report(name, argv):
    """One run's --json report, made once per test run."""
    if name not in REPORTS:
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "r.json")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                gpconf_main(["run", "--root", ROOT, "--json", out] + argv)
            with open(out, encoding="utf-8") as f:
                REPORTS[name] = json.load(f)
    return REPORTS[name]


class Reports(unittest.TestCase):
    def test_reports_of_every_kind_of_run_match(self):
        runs = {"reference, every case": ["--preset", "reference"],
                "naive, every case": ["--preset", "naive"],
                "a command, two cases": ["--cmd", f'"{sys.executable}" "{os.path.join(ROOT, "templates", "python", "adapter.py")}" {{fmt}}',
                                         "--case", "alpha5-tle-derived", "--case", "corrupt-input"]}
        for name, argv in runs.items():
            with self.subTest(run=name):
                rep = report(name, argv)
                self.assertTrue(rep["results"])
                self.assertEqual(S.errors(rep, S.load_schema()), [])

    def test_the_schemas_statuses_are_the_runners(self):
        d = S.load_schema()["$defs"]
        self.assertEqual(tuple(d["case_status"]["enum"]), CASE_STATUSES)
        self.assertEqual(tuple(d["item_status"]["enum"]), CASE_STATUSES + ("info",))
        self.assertEqual(set(S.load_schema()["properties"]["summary"]["required"]), {"cases"} | set(CASE_STATUSES))

    def test_the_validator_finds_what_does_not_match(self):
        rep = report("reference, every case", ["--preset", "reference"])
        sch = S.load_schema()
        bad = copy.deepcopy(rep)
        del bad["summary"]["fail"]
        bad["results"][0]["status"] = "passed"
        bad["results"][0]["items"][0]["file"] = 3
        bad["generated_at"] = "2026-11-10 10:00"
        found = "\n".join(S.errors(bad, sch))
        for want in ("$.summary: 'fail' is missing", "$.results[0].status: 'passed' is not one of",
                     "$.results[0].items[0].file: int where string or null is expected", "$.generated_at:"):
            self.assertIn(want, found)
        ok = copy.deepcopy(rep)
        ok["a_key_from_a_later_minor_version"] = {"any": 1}   # additive changes stay valid (the versioning rule)
        self.assertEqual(S.errors(ok, sch), [])

    def test_the_command_line(self):
        rep = report("reference, every case", ["--preset", "reference"])
        with tempfile.TemporaryDirectory() as d:
            good, bad = os.path.join(d, "good.json"), os.path.join(d, "bad.json")
            with open(good, "w", encoding="utf-8") as f:
                json.dump(rep, f)
            with open(bad, "w", encoding="utf-8") as f:
                json.dump(dict(rep, summary={}), f)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(S.main([good]), 0)
                self.assertEqual(S.main([bad]), 1)
            self.assertIn("matches results schema 1.0", out.getvalue())
            self.assertIn("8 faults against results schema 1.0", out.getvalue())


if __name__ == "__main__":
    unittest.main()
