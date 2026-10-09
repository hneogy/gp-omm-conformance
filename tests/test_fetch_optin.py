"""D-231: the legacy SATCAT file is fetched only on request.

pub/satcat.txt is 9.4 MB, three quarters of the bytes of the whole fetch list, and one case reads it: a data check on
the file itself, in which no parser takes part. CelesTrak asks software to download only the data it needs, so a
fetch leaves the file out unless --include-satcat is given. Without the file the case reports not-exercised, as it
does with it, and a line says that --include-satcat runs the check (D-232): reporting that the case needs fetched data
would tell every user to fetch the file that was made optional.

Run: python -m unittest tests.test_fetch_optin"""
import contextlib
import datetime as dt
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

PY3 = r"python3?"   # D-270: the hint says python3 on POSIX and python on Windows

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fetch  # noqa: E402
from gpconf.runner import Runner, opt_in_files  # noqa: E402
from gpconf.__main__ import main as gpconf_main  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402

CASE = "satcat-70000-cutoff"
GATE_CASE = "tle-omits-six-digit-objects"
FILE = f"fixtures/{CASE}/raw/satcat.txt"
URL = "https://celestrak.org/pub/satcat.txt"
NOW = dt.datetime(2026, 10, 5, 12, 0, 0, tzinfo=dt.timezone.utc)

with open(os.path.join(ROOT, "tools", "fetchlist.json"), encoding="utf-8") as _f:
    FETCHLIST = json.load(_f)
with open(os.path.join(ROOT, "manifest.json"), encoding="utf-8") as _f:
    RECORDED = {s["path"]: s for c in json.load(_f)["cases"] for s in c.get("sources", [])}


def run_cli(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = gpconf_main(argv)
    return code, out.getvalue()


class TheList(unittest.TestCase):
    def test_one_entry_is_on_request_and_it_is_most_of_the_bytes(self):
        on_request = [e for e in FETCHLIST if e.get("opt_in")]
        self.assertEqual([(e["url"], e["opt_in"]) for e in on_request], [(URL, "satcat")])
        self.assertEqual(opt_in_files(ROOT), {FILE: "--include-satcat"})
        user = [e for e in FETCHLIST if not e.get("recapture_of") and not e.get("launch_window")]
        size = lambda es: sum(RECORDED[f"fixtures/{e['case']}/raw/{e['file']}"]["bytes"] for e in es)
        self.assertEqual((len(user), size(user)), (51, 12511746))
        default = [e for e in user if not e.get("opt_in")]
        self.assertEqual((len(default), size(default)), (50, 3131880))
        asked = [e for e in default if not e.get("recorded")]              # four are written from the corpus's record (D-247)
        self.assertEqual((len(asked), size(asked)), (46, 3131816))
        self.assertGreater(size(on_request) / size(user), 0.74)                        # three quarters

    def test_only_the_data_check_reads_it(self):
        with open(os.path.join(ROOT, "manifest.json"), encoding="utf-8") as f:
            readers = [c["id"] for c in json.load(f)["cases"] if any(s["path"] == FILE for s in c.get("sources", []))]
        self.assertEqual(readers, [CASE])


class TheFetch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def run_fetch(self, argv):
        asked, out = [], io.StringIO()

        def stub(entry, root=None):
            asked.append(entry["url"])
            return "stub"
        code = fetch.run(list(argv), root=self.root, corpus=ROOT, entries=FETCHLIST, now=NOW, fetch_one=stub, out=out, pause=0)
        return code, asked, out.getvalue()

    def put(self, hours_old):
        d = os.path.join(self.root, os.path.dirname(FILE))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(self.root, FILE), "wb") as f:
            f.write(b"an earlier fetch left this here\n")
        with open(os.path.join(self.root, FILE + ".meta.json"), "w", encoding="utf-8") as f:
            json.dump({"retrieved_at": (NOW - dt.timedelta(hours=hours_old)).strftime("%Y-%m-%dT%H:%M:%SZ")}, f)

    def test_a_plain_fetch_leaves_it_out_and_says_how_to_ask(self):
        code, asked, out = self.run_fetch([])
        self.assertEqual(len(asked), 46)
        self.assertNotIn(URL, asked)
        self.assertIn("not requested: the legacy SATCAT file (pub/satcat.txt, 9.4 MB).", out)
        self.assertIn("no parser takes part in that check; pass --include-satcat to fetch it.", out)

    def test_the_flag_brings_it(self):
        code, asked, out = self.run_fetch(["--include-satcat"])
        self.assertEqual(len(asked), 47)
        self.assertIn(URL, asked)
        self.assertNotIn("not requested: the legacy SATCAT file", out)

    def test_the_dry_run_counts_the_same(self):
        for argv, n in ((["--dry-run"], 46), (["--dry-run", "--include-satcat"], 47)):
            code, asked, out = self.run_fetch(argv)
            self.assertEqual(asked, [])
            self.assertIn(f"a run would make {n} requests", out)

    def test_force_does_not_refresh_a_copy_on_disk_unless_it_is_asked_for(self):
        """A clone that fetched under an earlier version holds the file: a forced refresh of everything else must not
        download 9.4 MB again that nobody asked for."""
        self.put(hours_old=30)
        plan = {p["entry"]["file"]: (p["action"], p["reason"]) for p in fetch.plan(FETCHLIST, force=True, root=self.root, now=NOW)}
        self.assertEqual(plan["satcat.txt"][0], "cached")
        self.assertIn("refreshed only with --include-satcat", plan["satcat.txt"][1])
        plan = {p["entry"]["file"]: p["action"] for p in fetch.plan(FETCHLIST, force=True, include_satcat=True, root=self.root, now=NOW)}
        self.assertEqual(plan["satcat.txt"], "fetch")
        self.put(hours_old=1)                                                           # and the two-hour rule holds for it as for any file
        plan = {p["entry"]["file"]: p["action"] for p in fetch.plan(FETCHLIST, force=True, include_satcat=True, root=self.root, now=NOW)}
        self.assertEqual(plan["satcat.txt"], "cached")

    def test_skipping_the_case_is_not_the_way_to_leave_it_out(self):
        """--skip-case satcat-70000-cutoff leaves out every entry filed under the case, two of which other cases read
        (D-230 withdrew that advice)."""
        code, asked, out = self.run_fetch(["--skip-case", CASE])
        self.assertEqual(len(asked), 40)
        self.assertFalse([u for u in asked if "gp-first.php?CATNR=69999" in u])


def corpus_copy(tmp, cases):
    shutil.copy(os.path.join(ROOT, "manifest.json"), tmp)
    for c in sorted(set(cases) | {GATE_CASE}):
        os.makedirs(os.path.join(tmp, "fixtures", c, "raw"))
        shutil.copy(os.path.join(ROOT, "fixtures", c, "expected.json"), os.path.join(tmp, "fixtures", c))
    os.makedirs(os.path.join(tmp, "tools"))
    shutil.copy(os.path.join(ROOT, "tools", "fetchlist.json"), os.path.join(tmp, "tools"))


class TheRunner(unittest.TestCase):
    def records_only(self, tmp):
        """The case's six small SATCAT records on disk, as stand-ins, and no legacy file: a user's folder after a fetch."""
        corpus_copy(tmp, [CASE])
        with open(os.path.join(ROOT, "fixtures", CASE, "expected.json"), encoding="utf-8") as f:
            sources = json.load(f)["sources"]
        for rel in sources:
            if rel != FILE:
                os.makedirs(os.path.dirname(os.path.join(tmp, rel)), exist_ok=True)
                with open(os.path.join(tmp, rel), "wb") as f:
                    f.write(b"[]")
        return [rel for rel in sources if rel != FILE]

    def test_without_the_file_the_case_is_not_exercised_and_the_item_names_the_flag(self):
        """D-232: "needs fetched data" would tell every user to fetch the file that was made optional."""
        with tempfile.TemporaryDirectory() as tmp:
            self.records_only(tmp)
            r = Runner(Reference(), root=tmp).run(case_ids=[CASE])[0]
            quiet = Runner(Reference(), root=tmp, fetch_hints=False).run(case_ids=[CASE])[0]
        self.assertEqual(r.status, "not-exercised")                                     # what it reports with the file, too
        self.assertEqual(r.missing(), [])
        self.assertNotIn("not-fetched", {i.status for i in r.items})
        (item,) = [i for i in r.items if i.file == FILE]
        self.assertEqual((item.check, item.status), ("satcat-legacy-below-70000", "not-exercised"))
        self.assertIn("the data check was not made: the fetch brings the legacy SATCAT file only on request, and the parser under test is not involved", item.detail)
        self.assertRegex(item.detail, rf"to run it, fetch the file with {PY3} (tools[/\\\\]fetch\.py|-m gpconf fetch).* --include-satcat$")
        self.assertEqual(r.on_request, {FILE: "--include-satcat"})
        self.assertEqual(r.as_dict()["on_request"], {FILE: "--include-satcat"})
        (item,) = [i for i in quiet.items if i.file == FILE]                             # the Action's run names no command
        self.assertTrue(item.detail.endswith("; the fetch brings the file with --include-satcat"), item.detail)
        self.assertNotRegex(item.detail, r"python3|gpconf fetch|tools/fetch")

    def test_a_line_says_what_runs_the_check_and_nothing_tells_the_user_to_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.records_only(tmp)
            code, text = run_cli(["run", "--adapter", "tests.adapters.reference:Parser", "--root", tmp, "--case", CASE])
            quiet_code, quiet = run_cli(["run", "--adapter", "tests.adapters.reference:Parser", "--root", tmp, "--case", CASE, "--no-fetch-hint"])
        self.assertEqual(code, 0)
        self.assertIn("1 case: 0 pass (exact), 0 pass within tolerance, 0 fail, 0 skip, 0 need fetched data, 0 not available, 1 not exercised", text)
        self.assertIn(f"{CASE} is a data check on the legacy SATCAT file, 9.4 MB, which the fetch brings only on request. It was not made, "
                      "and no parser takes part in it: nothing about the parser under test depends on it.", text)
        self.assertRegex(text, rf"--include-satcat runs it: {PY3} -m gpconf fetch --root \S+ --include-satcat\.")
        self.assertNotIn("report not-fetched", text)
        self.assertNotIn("Provider data is not shipped with the corpus; fetch it with", text)   # nothing is missing that a plain fetch brings
        self.assertIn("The fetch's --include-satcat runs it.", quiet)
        self.assertNotRegex(quiet, r"gpconf fetch|tools/fetch\.py")

    def test_before_any_fetch_the_case_reads_the_same_and_its_six_small_files_are_a_plain_fetch_away(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus_copy(tmp, [CASE])
            r = Runner(Reference(), root=tmp).run(case_ids=[CASE])[0]
            code, text = run_cli(["run", "--adapter", "tests.adapters.reference:Parser", "--root", tmp, "--case", CASE])
        self.assertEqual(r.status, "not-exercised")
        self.assertEqual((r.counts()["not-exercised"], r.counts()["not-fetched"]), (1, 6))
        self.assertIn("1 case: 0 pass (exact), 0 pass within tolerance, 0 fail, 0 skip, 0 need fetched data, 0 not available, 1 not exercised", text)
        self.assertIn(f"1 case ran without 6 of its provider files, so its result covers only the files on disk (column n/f): {CASE}.", text)
        self.assertIn("Provider data is not shipped with the corpus; fetch it with", text)

    def test_a_refusal_kept_for_the_file_is_reported_as_one(self):
        """Asked for with --include-satcat and refused: the file is missing for that reason, not by default (D-228)."""
        with tempfile.TemporaryDirectory() as tmp:
            self.records_only(tmp)
            with open(os.path.join(tmp, FILE + ".unexpected"), "wb") as f:
                f.write(b"<html>403 Forbidden</html>")
            with open(os.path.join(tmp, FILE + ".unexpected.meta.json"), "w", encoding="utf-8") as f:
                json.dump({"http_status": 403, "retrieved_at": "2026-10-05T12:00:00Z", "unexpected": "HTTP 403"}, f)
            r = Runner(Reference(), root=tmp).run(case_ids=[CASE])[0]
        self.assertEqual(r.status, "not-fetched")
        self.assertEqual(r.on_request, {})
        (item,) = [i for i in r.items if i.file == FILE]
        self.assertIn("the fetch got HTTP 403 for it", item.detail)

    def test_with_the_file_the_check_is_made_and_no_parser_is_credited(self):
        if not os.path.exists(os.path.join(ROOT, FILE)):
            self.skipTest("the legacy SATCAT file is not on disk (public clone, or a fetch without --include-satcat)")
        r = Runner(Reference(), root=ROOT).run(case_ids=[CASE])[0]
        self.assertEqual(r.status, "not-exercised")


if __name__ == "__main__":
    unittest.main()
