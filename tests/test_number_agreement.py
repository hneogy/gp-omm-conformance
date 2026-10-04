"""
A count agrees in number with the words beside it (D-239): one case passes where two pass, one request is made where
two are, and no line hedges a plural with a bracketed s. The slip that started it was the Action's summary reading
"1 need launch-window data". Each test pins the singular and the plural form of a line the runner, the fetch or the
Action prints; the last ones read the source, so that a new count joined to a bracketed plural fails here.
No test makes a request.
"""
import ast
import contextlib
import glob
import importlib.util
import io
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gpconf import __main__ as cli  # noqa: E402
from gpconf import fetch  # noqa: E402
from gpconf import gates  # noqa: E402
from gpconf import writer as W  # noqa: E402
from gpconf.runner import Runner  # noqa: E402
from gpconf.words import pick, qty  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402

PRINTING_SOURCES = sorted(glob.glob(os.path.join(ROOT, "gpconf", "*.py")) + glob.glob(os.path.join(ROOT, "gpconf", "adapters", "*.py"))
                          + [os.path.join(ROOT, "tools", "action_report.py"), os.path.join(ROOT, "tools", "make_failures.py")])


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "tools", name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Result:
    """What the lines under the table read of a case's result."""

    def __init__(self, case_id, status, missing=(), unavailable=(), unexpected=None, on_request=None):
        self.case_id, self.status = case_id, status
        self._missing, self._unavailable = list(missing), list(unavailable)
        self.unexpected, self.on_request, self.reused = unexpected or {}, on_request or {}, {}

    def missing(self):
        return self._missing

    def unavailable(self):
        return self._unavailable


class NoHints:
    fetch_hints, opt_in = False, {}

    def hint(self, *flags):
        return "the fetch"


def lines_under_the_table(results):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        cli.print_missing(results, [r for r in results if r.status == "not-fetched"], NoHints())
    return out.getvalue()


class TheTwoFunctions(unittest.TestCase):
    def test_one_is_singular_and_every_other_number_plural(self):
        self.assertEqual([qty(n, "record") for n in (0, 1, 2, 256)], ["0 records", "1 record", "2 records", "256 records"])
        self.assertEqual([qty(n, "entry", "entries") for n in (0, 1, 2)], ["0 entries", "1 entry", "2 entries"])
        self.assertEqual([pick(n, "needs", "need") for n in (0, 1, 2)], ["need", "needs", "need"])
        self.assertEqual(qty(1, "space or tab", "spaces or tabs"), "1 space or tab")


class TheCountLine(unittest.TestCase):
    STATUSES = ("pass", "pass-tolerance", "fail", "skip", "not-fetched", "not-available", "not-exercised")

    def test_one_of_each(self):
        self.assertEqual(cli.count_line([Result(s, s) for s in self.STATUSES]),
                         "7 cases: 1 passes (exact), 1 passes within tolerance, 1 fails, 1 skips, 1 needs fetched data, 1 not available, 1 not exercised")

    def test_two_of_each(self):
        self.assertEqual(cli.count_line([Result(s, s) for s in self.STATUSES * 2]),
                         "14 cases: 2 pass (exact), 2 pass within tolerance, 2 fail, 2 skip, 2 need fetched data, 2 not available, 2 not exercised")

    def test_one_case_and_none(self):
        self.assertEqual(cli.count_line([Result("a", "pass")]),
                         "1 case: 1 passes (exact), 0 pass within tolerance, 0 fail, 0 skip, 0 need fetched data, 0 not available, 0 not exercised")
        self.assertTrue(cli.count_line([]).startswith("0 cases: 0 pass (exact), "))


class TheLinesUnderTheTable(unittest.TestCase):
    def test_cases_with_nothing_on_disk(self):
        self.assertIn("1 case has none of its provider files on disk and reports not-fetched;", lines_under_the_table([Result("a", "not-fetched", ["f"])]))
        self.assertIn("2 cases have none of their provider files on disk and report not-fetched;",
                      lines_under_the_table([Result("a", "not-fetched", ["f"]), Result("b", "not-fetched", ["g"])]))

    def test_cases_that_ran_on_part_of_their_files(self):
        self.assertIn("1 case ran without 2 of its provider files, so its result covers only the files on disk (column n/f): a.",
                      lines_under_the_table([Result("a", "pass", ["f", "g"])]))
        self.assertIn("2 cases ran without 2 of their provider files, so each result covers only the files on disk (column n/f): a, b.",
                      lines_under_the_table([Result("a", "pass", ["f"]), Result("b", "fail", ["g"])]))

    def test_cases_no_fetch_can_run(self):
        one = lines_under_the_table([Result("a", "not-available", unavailable=["f"])])
        self.assertIn("1 case cannot run from a fetch and reports not-available: a. Every provider file it needs is a launch-window capture:", one)
        two = lines_under_the_table([Result("a", "not-available", unavailable=["f"]), Result("b", "not-available", unavailable=["g"])])
        self.assertIn("2 cases cannot run from a fetch and report not-available: a, b. Every provider file they need is a launch-window capture:", two)

    def test_cases_judged_on_their_other_files(self):
        self.assertIn("1 other case names 1 launch-window file (column n/a) and is judged on its other files: a.",
                      lines_under_the_table([Result("a", "pass", unavailable=["f"])]))
        self.assertIn("2 other cases name 3 launch-window files (column n/a) and are judged on their other files: a, b.",
                      lines_under_the_table([Result("a", "pass", unavailable=["f", "g"]), Result("b", "fail", unavailable=["h"])]))

    def test_files_the_fetch_got_an_unexpected_answer_for(self):
        why = {"why": "HTTP 403"}
        self.assertIn("1 provider file is missing because the fetch got a response it did not expect for it (HTTP 403); "
                      "the response is kept beside the data, not in its place, and is not read.",
                      lines_under_the_table([Result("a", "not-fetched", ["f"], unexpected={"f": why})]))
        self.assertIn("2 provider files are missing because the fetch got a response it did not expect for them (HTTP 403); "
                      "each response is kept beside the data, not in its place, and is not read.",
                      lines_under_the_table([Result("a", "not-fetched", ["f", "g"], unexpected={"f": why, "g": why})]))


class TheFetch(unittest.TestCase):
    def test_the_closing_line(self):
        self.assertEqual(fetch.done_line(1, 0, 1), "done: 1 request made, 1 entry skipped")
        self.assertEqual(fetch.done_line(50, 0, 0), "done: 50 requests made, 0 entries skipped")
        self.assertEqual(fetch.done_line(28, 1, 2), "done: 28 requests made, 1 file reused from an earlier corpus version's cache, 2 entries skipped")
        self.assertEqual(fetch.done_line(28, 22, 0), "done: 28 requests made, 22 files reused from an earlier corpus version's cache, 0 entries skipped")

    def test_the_dry_run(self):
        self.assertEqual(fetch.dry_run_line(1, 0, 1), "dry run: no request made; a run would make 1 request and leave 1 entry as it is")
        self.assertEqual(fetch.dry_run_line(50, 0, 0), "dry run: no request made; a run would make 50 requests and leave 0 entries as they are")
        self.assertEqual(fetch.dry_run_line(3, 1, 2), "dry run: no request made; a run would make 3 requests, reuse 1 file from an earlier corpus "
                                                      "version's cache and leave 2 entries as they are")

    def test_the_captures_no_fetch_requests(self):
        self.assertEqual(fetch.captures_line(1, ["a launch"]),
                         "not requested: 1 launch-window capture (a launch). CelesTrak serves launch nominals for the days after a launch; "
                         "this entry records the corpus's own capture and no fetch asks for it.")
        self.assertEqual(fetch.captures_line(10, ["a launch"]),
                         "not requested: 10 launch-window captures (a launch). CelesTrak serves launch nominals for the days after a launch; "
                         "these entries record the corpus's own capture and no fetch asks for them.")

    def test_the_two_quiet_hours(self):
        one = fetch.refusal_line(403, 60, 60, "URL", "kept")
        self.assertIn("with HTTP 403 1 minute ago (URL).", one)
        self.assertIn("with or without --force: 1 minute remains. The refused response is kept as kept;", one)
        many = fetch.refusal_line(429, 1800, 5400, "URL", "kept")
        self.assertIn("with HTTP 429 30 minutes ago (URL).", many)
        self.assertIn("with or without --force: 90 minutes remain.", many)

    def test_the_drift_line(self):
        self.assertEqual(fetch.drift_line(1, 1, 1, 1, 0, 0),
                         "1 file matches the tested snapshot (1 stable, 0 live); 1 STABLE source drifted; "
                         "1 live source differs (expected: live data changes every 2 hours); 0 missing; 0 not in the manifest.")
        self.assertEqual(fetch.drift_line(26, 22, 0, 24, 0, 0),
                         "26 files match the tested snapshot (22 stable, 4 live); 0 STABLE sources drifted; "
                         "24 live sources differ (expected: live data changes every 2 hours); 0 missing; 0 not in the manifest.")


class TheActionSummary(unittest.TestCase):
    """Where the slip was seen: "1 need launch-window data that no fetch brings"."""

    def test_one_and_many(self):
        sentence = load_tool("action_report").counts_sentence
        one = sentence({"pass": 1, "pass-tolerance": 1, "fail": 1, "not-fetched": 1, "not-available": 1, "skip": 1, "not-exercised": 1}, 7)
        self.assertEqual(one, "**3 of 7 cases exercised**, offline: 1 passes, 1 passes within tolerance, 1 fails. 1 needs provider data, which this Action "
                              "does not fetch; 1 needs launch-window data that no fetch brings; 1 skips, where the parser has no reader for the format or "
                              "no hook for the check; 1 not exercised. Failed cases do not fail this job.\n\n")
        many = sentence({"pass": 5, "not-fetched": 11, "not-available": 2, "skip": 2, "fail": 3}, 23)
        self.assertEqual(many, "**8 of 23 cases exercised**, offline: 5 pass, 0 pass within tolerance, 3 fail. 11 need provider data, which this Action "
                               "does not fetch; 2 need launch-window data that no fetch brings; 2 skip, where the parser has no reader for the format or "
                               "no hook for the check; 0 not exercised. Failed cases do not fail this job.\n\n")
        self.assertTrue(sentence({"pass": 1}, 1).startswith("**1 of 1 case exercised**, offline: 1 passes, 0 pass within tolerance, 0 fail."))

    def test_at_this_release_s_offline_counts(self):
        text = load_tool("action_report").counts_sentence({"pass": 5, "not-fetched": 11, "not-available": 1, "not-exercised": 1}, 18)
        self.assertIn("11 need provider data, which this Action does not fetch; 1 needs launch-window data that no fetch brings;", text)
        self.assertNotIn("1 need launch-window data", text)


class WhatTheRunnerSaysOfAnItem(unittest.TestCase):
    """Item details from a real run of the control on a case that ships with the corpus: its two files hold one record
    and 256, so the same sentences appear in both numbers."""

    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as empty:
            cls.result = Runner(Reference(), root=ROOT, data=empty).run(case_ids=["alpha5-tle-derived"])[0]
        cls.details = [i.detail for i in cls.result.items]

    def test_values(self):
        self.assertIn("1 record matches frozen expected values", self.details)
        self.assertIn("256 records match frozen expected values", self.details)

    def test_data_checks(self):
        self.assertIn("1 record, all checksums valid (data check)", self.details)
        self.assertIn("256 records, all checksums valid (data check)", self.details)
        self.assertIn("1 catalog field decoded correctly (Alpha-5)", self.details)
        self.assertIn("256 catalog fields decoded correctly (Alpha-5)", self.details)


class OtherTextWithACount(unittest.TestCase):
    def test_the_writer_checks(self):
        self.assertEqual(W.check_lines("1 " + "x" * 67, "2")[1], "line 2 is 1 character, not 69")
        self.assertIn("line 1 is 70 characters, not 69", W.check_lines("1 " + "x" * 68, "2 " + "x" * 67))

    def test_the_gate_s_snapshot_note(self):
        self.assertEqual(gates._label("TLE", {"live": {"retrieved_at": "2026-10-04T00:00:00Z"}, "expected": 1}),
                         "TLE; live capture fetched 2026-10-04, 1 object, not the snapshot")
        self.assertEqual(gates._label("TLE", {"live": {"retrieved_at": "2026-10-04T00:00:00Z"}, "expected": 256}),
                         "TLE; live capture fetched 2026-10-04, 256 objects, not the snapshot")


class NoBracketedPlural(unittest.TestCase):
    """The form the audit removed: a count beside "record(s)". A string in the code that prints must not carry it."""

    def strings(self, path):
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        return [(node.lineno, node.value) for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]

    def test_no_string_the_runner_the_fetch_or_the_action_prints_has_one(self):
        self.assertGreater(len(PRINTING_SOURCES), 15)
        found = [f"{os.path.relpath(p, ROOT)}:{line}: {text[:80]!r}" for p in PRINTING_SOURCES for line, text in self.strings(p) if "(s)" in text]
        self.assertEqual(found, [])

    def test_the_catalogue_generated_from_the_reports_has_none(self):
        with open(os.path.join(ROOT, "docs", "FAILURES.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("(s)", text)
        self.assertRegex(text, r"\n1 failing item\.\n")
        self.assertRegex(text, r"\n\d+ failing items, shown as 1 bullet: ")
        self.assertRegex(text, r"\n\d+ failing items, shown as [2-9] bullets: ")


if __name__ == "__main__":
    unittest.main()
