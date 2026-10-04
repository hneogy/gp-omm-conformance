"""
The JSON report carries the case totals as numbers, in `summary` (D-240): what a script reads in place of the printed
count line, whose wording can change from one version to the next (it did in D-239). These tests hold the summary to
the cases it summarises, to the line the runner prints and to the Action's outputs; they check that the field is an
addition, every earlier field where it was; and they pin the sentence in the README and the adapter guide that sends a
script to the report or the exit status. The last class is the catalogue's table, whose cells say "(1 failing)".
No test makes a request.
"""
import collections
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gpconf import __main__ as cli  # noqa: E402
from gpconf.runner import CASE_STATUSES, status_totals  # noqa: E402
from tests.test_action import run_step  # noqa: E402

OFFLINE_CASES = ["alpha5-encoding-vectors", "alpha5-tle-derived", "kvn-syntax-variants", "tle-writer-alpha5", "corrupt-input"]


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def flat(text):
    return " ".join(text.split())


class Case:
    def __init__(self, status):
        self.status = status


def run(preset, *args):
    """One run of the command line with no provider data -> (exit status, what it printed, the JSON report)."""
    with tempfile.TemporaryDirectory() as tmp:
        report = os.path.join(tmp, "report.json")
        empty = os.path.join(tmp, "data")
        os.mkdir(empty)
        p = subprocess.run([sys.executable, "-m", "gpconf", "run", "--preset", preset, "--root", ROOT, "--data", empty, "--json", report, *args],
                           cwd=tmp, capture_output=True, text=True, timeout=300, env=dict(os.environ, PYTHONPATH=ROOT))
        with open(report, encoding="utf-8") as f:
            return p.returncode, p.stdout, json.load(f)


class TheTotals(unittest.TestCase):
    def test_every_status_is_there_with_its_count_zeros_included(self):
        totals = status_totals([Case("pass"), Case("pass"), Case("fail"), Case("not-available")])
        self.assertEqual(list(totals), ["cases", *CASE_STATUSES])
        self.assertEqual(totals, {"cases": 4, "pass": 2, "pass-tolerance": 0, "fail": 1, "skip": 0, "not-fetched": 0, "not-available": 1, "not-exercised": 0})
        self.assertEqual(status_totals([]), {"cases": 0, **{s: 0 for s in CASE_STATUSES}})

    def test_the_statuses_are_the_seven_a_case_can_end_in(self):
        self.assertEqual(CASE_STATUSES, ("pass", "pass-tolerance", "fail", "skip", "not-fetched", "not-available", "not-exercised"))

    def test_the_counts_add_up_to_the_cases(self):
        totals = status_totals([Case(s) for s in CASE_STATUSES * 3])
        self.assertEqual(sum(totals[s] for s in CASE_STATUSES), totals["cases"])


class TheReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code, cls.out, cls.report = run("reference")
        cls.naive_code, cls.naive_out, cls.naive = run("naive", *[a for c in OFFLINE_CASES for a in ("--case", c)])

    def test_the_summary_counts_the_cases_of_the_report(self):
        for report in (self.report, self.naive):
            summary, results = report["summary"], report["results"]
            self.assertEqual(summary["cases"], len(results))
            counted = collections.Counter(r["status"] for r in results)
            self.assertEqual({s: summary[s] for s in CASE_STATUSES}, {s: counted.get(s, 0) for s in CASE_STATUSES})
            self.assertTrue(all(isinstance(v, int) and not isinstance(v, bool) for v in summary.values()), summary)
            self.assertEqual(list(summary), ["cases", *CASE_STATUSES])

    def test_the_summary_is_the_count_line_s_numbers(self):
        for out, report in ((self.out, self.report), (self.naive_out, self.naive)):
            self.assertIn(cli.count_line([Case(r["status"]) for r in report["results"]]), out.splitlines())
        self.assertEqual(self.naive["summary"]["fail"], 5)       # the five cases that ship with the corpus, all failing for naive
        self.assertIn("5 cases: 0 pass (exact), 0 pass within tolerance, 5 fail, 0 skip, 0 need fetched data, 0 not available, 0 not exercised", self.naive_out)

    def test_the_exit_status_says_whether_a_case_failed(self):
        self.assertEqual((self.code, self.report["summary"]["fail"]), (0, 0))
        self.assertEqual(self.naive_code, 1)

    def test_the_field_is_an_addition(self):
        """Every field the report had before D-240 is still there, in the order it had."""
        keys = list(self.report)
        self.assertEqual(keys, ["gpconf", "corpus_version", "parser", "preset", "generated_at", "summary", "results", "gates"])
        self.assertEqual(sorted(self.report["results"][0]), sorted(["case", "title", "status", "counts", "modes", "drift", "items"]))

    def test_the_action_s_outputs_are_the_summary_s_numbers(self):
        code, _, outputs, _, report = run_step("reference", full=True)
        self.assertEqual(code, 0)
        summary = report["summary"]
        self.assertEqual(int(outputs["failed"]), summary["fail"])
        self.assertEqual(int(outputs["exercised"]), summary["pass"] + summary["pass-tolerance"] + summary["fail"])


class WhatAScriptIsTold(unittest.TestCase):
    SENTENCE = "should read the JSON report or the exit status, never the printed lines, whose wording can change from one version to the next (D-240)"

    def test_the_readme_says_it_and_names_where_the_numbers_are(self):
        readme = flat(read("README.md"))
        self.assertIn("A script " + self.SENTENCE, readme)
        self.assertIn("`--json FILE` writes the report: its `summary`, from 0.6.0, holds the number of cases in each status", readme)
        self.assertIn("the exit status is 0 when no case failed, 1 when one did and 2 when nothing could run", readme)
        self.assertIn("the Action's outputs `failed`, `exercised` and `report` carry the same", readme)

    def test_the_adapter_guide_says_it_and_describes_the_summary(self):
        guide = flat(read("docs", "ADAPTERS.md"))
        self.assertIn("A script should read this report or the exit status, never the printed lines, whose wording can change from one version to the next (D-240)", guide)
        self.assertIn("`generated_at`, `summary`, `results` and `gates`", guide)
        for status in CASE_STATUSES:
            self.assertIn(f"`{status}`", guide)
        self.assertIn("they add up to `cases`", guide)

    def test_the_changelog_says_it(self):
        unreleased = flat(read("CHANGELOG.md").split("## [0.5.1]")[0])
        self.assertIn("in a `summary` object at its top level", unreleased)
        self.assertIn("A script " + self.SENTENCE.replace(" (D-240)", ""), unreleased)


class TheCatalogueTable(unittest.TestCase):
    def test_a_cell_gives_the_failing_items_with_a_word_that_does_not_vary(self):
        text = read("docs", "FAILURES.md")
        rows = [line for line in text.splitlines() if line.startswith("| `")]
        self.assertEqual(len(rows), 18)
        self.assertNotRegex(text, r"\(\d+ fail\)")
        self.assertIn("fail (1 failing)", text)
        self.assertIn("pass (0 failing)", text)
        self.assertRegex(text, r"fail \((?:[2-9]|\d\d+) failing\)")
        for row in rows:
            self.assertRegex(row, r"^\| `[a-z0-9-]+` \| [a-z-]+ \(\d+ failing\) \| [a-z-]+ \(\d+ failing\) \| [a-z-]+ \(\d+ failing\) \|$")


if __name__ == "__main__":
    unittest.main()
