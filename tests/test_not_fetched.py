"""D-148: a provider file that is not on disk reports not-fetched, never skip, which the corpus keeps for a parser
with no reader for a format or no hook for a check. The count line says how many cases need fetched data, a case
that ran on part of its files is named below it, and the fetch command names a script that exists."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gpconf.runner import Runner, CorpusIncomplete, fetch_hint, is_provider_data  # noqa: E402
from gpconf.__main__ import main as gpconf_main  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402

CASE = "bstar-and-derivative-forms"          # raw files only, one of them a re-capture
RECAPTURE = "fixtures/bstar-and-derivative-forms/raw/decaying-recapture.tle"


GATE_CASE = "tle-omits-six-digit-objects"  # the gate reads its snapshot facts from this case's expected.json


def sourceless_root(tmp, cases):
    """A corpus root with the manifest and the cases' expected.json (plus the gate's), and no provider file."""
    shutil.copy(os.path.join(ROOT, "manifest.json"), tmp)
    for c in set(cases) | {GATE_CASE}:
        os.makedirs(os.path.join(tmp, "fixtures", c))
        shutil.copy(os.path.join(ROOT, "fixtures", c, "expected.json"), os.path.join(tmp, "fixtures", c))


def run_cli(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = gpconf_main(argv)
    return code, out.getvalue()


class NotFetchedStatus(unittest.TestCase):
    def test_a_case_with_no_provider_file_reports_not_fetched_with_a_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            sourceless_root(tmp, [CASE])
            r = Runner(Reference(), root=tmp).run(case_ids=[CASE])[0]
        self.assertEqual(r.status, "not-fetched")
        self.assertNotIn("skip", {i.status for i in r.items})
        self.assertEqual(r.counts()["not-fetched"], len(r.items))
        self.assertEqual(r.counts()["skip"], 0)
        self.assertEqual(sorted(r.missing()), sorted(i.file for i in r.items))
        for i in r.items:
            self.assertEqual(i.check, "source-present")
            self.assertIn("provider data is not shipped with the corpus", i.detail)
            self.assertIn("python3 -m gpconf fetch --root", i.detail)  # a bare corpus copy: the subcommand, pointed at it (D-150)

    def test_the_json_report_carries_the_status_and_the_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            sourceless_root(tmp, [CASE])
            out = os.path.join(tmp, "report.json")
            code, _ = run_cli(["run", "--adapter", "tests.adapters.reference:Parser", "--root", tmp, "--case", CASE, "--json", out])
            with open(out) as f:
                rep = json.load(f)
        self.assertEqual(code, 0)  # absence is not a failure of the parser
        (r,) = rep["results"]
        self.assertEqual(r["status"], "not-fetched")
        self.assertGreater(r["counts"]["not-fetched"], 0)

    def test_the_count_line_and_the_table_say_how_many_need_fetched_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            sourceless_root(tmp, [CASE, "epoch-year-19xx"])
            code, text = run_cli(["run", "--adapter", "tests.adapters.reference:Parser", "--root", tmp, "--case", CASE, "--case", "epoch-year-19xx"])
        self.assertEqual(code, 0)
        self.assertIn("exact  tol fail skip n/e n/f", text)
        self.assertIn("2 case(s): 0 pass (exact), 0 pass within tolerance, 0 fail, 0 skip, 2 need fetched data, 0 not exercised", text)
        self.assertIn("2 case(s) have none of their provider files on disk and report not-fetched", text)
        self.assertIn("fetch it with python3 -m gpconf fetch --root", text)  # no tools/fetch.py under this root (D-150)
        self.assertNotIn("run tools/fetch.py", text)

    def test_a_parser_without_a_reader_still_skips(self):
        # the other half of the distinction: skip keeps its meaning where the input is on disk (a parser with no hooks)
        r = Runner(object(), root=ROOT).run(case_ids=["alpha5-encoding-vectors"])[0]
        self.assertEqual(r.status, "skip")
        self.assertEqual(r.counts()["not-fetched"], 0)


class PartlyFetchedCase(unittest.TestCase):
    """After a first fetch the re-capture files are not yet on disk (they are fetched two hours after their
    originals), and three cases used to report pass with no word about the missing file."""

    def setUp(self):
        if not all(os.path.exists(os.path.join(ROOT, p)) for p in json.load(open(os.path.join(ROOT, "fixtures", CASE, "expected.json")))["sources"]):
            self.skipTest(f"raw sources for {CASE} absent (public clone): run tools/fetch.py to exercise the partly fetched case")

    def partial_root(self, tmp):
        sourceless_root(tmp, [CASE])
        exp = json.load(open(os.path.join(ROOT, "fixtures", CASE, "expected.json")))
        for p in exp["sources"]:
            if p != RECAPTURE:
                os.makedirs(os.path.dirname(os.path.join(tmp, p)), exist_ok=True)
                shutil.copy(os.path.join(ROOT, p), os.path.join(tmp, p))
                if os.path.exists(os.path.join(ROOT, p + ".meta.json")):
                    shutil.copy(os.path.join(ROOT, p + ".meta.json"), os.path.join(tmp, p + ".meta.json"))

    def test_the_result_covers_the_files_present_and_names_the_missing_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.partial_root(tmp)
            r = Runner(Reference(), root=tmp).run(case_ids=[CASE])[0]
            code, text = run_cli(["run", "--adapter", "tests.adapters.reference:Parser", "--root", tmp, "--case", CASE])
        self.assertEqual(r.status, "pass")
        self.assertEqual(r.missing(), [RECAPTURE])
        self.assertEqual(code, 0)
        self.assertIn("0 need fetched data", text)
        self.assertIn(f"1 case(s) ran without 1 of their provider files, so each result covers only the files on disk (column n/f): {CASE}.", text)
        # D-150 corrects D-148: a normal fetch never requests a re-capture, so no later run brings it
        self.assertIn("the fetch requests it only with --include-recaptures", text)
        self.assertIn("so a normal fetch leaves these cases without it", text)
        self.assertNotIn("fetched on a later run", text)
        self.assertNotIn("fetch it with", text)  # a normal fetch would not bring a re-capture, so no fetch command (D-150)


class FetchHint(unittest.TestCase):
    def test_a_clone_is_given_its_own_script(self):
        self.assertTrue(fetch_hint(ROOT).startswith("python3 "), fetch_hint(ROOT))
        self.assertTrue(fetch_hint(ROOT).rstrip("'").endswith("tools/fetch.py"), fetch_hint(ROOT))
        self.assertTrue(fetch_hint(ROOT, "--check-drift").endswith(" --check-drift"))

    def test_a_path_with_spaces_is_quoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = os.path.realpath(tmp)  # macOS: /var is a link to /private/var, and getcwd() returns the latter
            root = os.path.join(tmp, "a corpus")
            os.makedirs(os.path.join(root, "tools"))
            open(os.path.join(root, "tools", "fetch.py"), "w").close()
            cwd = os.getcwd()
            try:
                os.chdir(tmp)  # from outside the root, so the relative path does not start with ".."
                self.assertEqual(fetch_hint(root), "python3 'a corpus/tools/fetch.py'")
            finally:
                os.chdir(cwd)

    def test_a_copy_without_the_script_is_given_the_subcommand(self):
        # D-150: the fetch is a subcommand of the package, so a copy without tools/fetch.py is given a command it has
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(fetch_hint(tmp), "python3 -m gpconf fetch")
            self.assertEqual(fetch_hint(tmp, data_why="--root"), f"python3 -m gpconf fetch --root {tmp}")
            self.assertEqual(fetch_hint(tmp, "--check-drift", data="/d d", data_why="--data"), "python3 -m gpconf fetch --data '/d d' --check-drift")
            self.assertEqual(fetch_hint(tmp, data="/d", data_why="GPCONF_DATA"), "python3 -m gpconf fetch")  # the variable reaches the fetch itself


class IncompleteCopy(unittest.TestCase):
    """A file that ships with the corpus cannot be fetched, so 'need fetched data' would be false; the run stops."""

    def test_provider_data_is_recognised_by_its_place(self):
        self.assertTrue(is_provider_data("fixtures/analyst-objects/raw/analyst.tle"))
        for p in ("derived/alpha5-tle/alpha5-A-100000-saramago-first.tle", "vectors/alpha5.json", "fixtures/analyst-objects/expected.json"):
            self.assertFalse(is_provider_data(p), p)

    def test_a_missing_shipped_file_stops_the_run_with_exit_2(self):
        case = "alpha5-tle-derived"
        with tempfile.TemporaryDirectory() as tmp:
            sourceless_root(tmp, [case])
            with self.assertRaises(CorpusIncomplete) as cm:
                Runner(Reference(), root=tmp).run(case_ids=[case])
            self.assertIn("ships with the corpus", str(cm.exception))
            code, text = run_cli(["run", "--adapter", "tests.adapters.reference:Parser", "--root", tmp, "--case", case])
        self.assertEqual(code, 2)
        self.assertIn("this copy of the corpus is incomplete", text)


if __name__ == "__main__":
    unittest.main()
