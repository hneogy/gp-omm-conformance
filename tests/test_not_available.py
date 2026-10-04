"""D-229: a launch-window capture is requested by no fetch, and a case that needs one says not-available.

The fetch list carried ten requests for things CelesTrak serves only around a launch: the Starlink G15-27
post-deployment file and the launch nominal 799501621. A fetch built on them stops for every user once the window
closes. They stay in the list as the record of the corpus's own captures, marked with their launch, and no run plans
them. The runner reports a file of that kind as not-available: not-fetched would send the user to a fetch that does
not bring it, and not-exercised is kept for data that was read and lacked the feature (D-148).

Run: python -m unittest tests.test_not_available"""
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
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fetch  # noqa: E402
from gpconf.runner import CaseResult, Runner, launch_window_files  # noqa: E402
from gpconf.__main__ import main as gpconf_main  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402

ALL_CAPTURES = "supgp-celestrak-classification-c"      # its five provider files are the post-deployment file
PARTLY = "nine-digit-supgp-launch-nominals"            # five captures and the full Starlink supplemental file
GATE_CASE = "tle-omits-six-digit-objects"              # the command line reads the gate's facts from this case
LABEL = "Starlink G15-27, launched 2026-09-20"

with open(os.path.join(ROOT, "tools", "fetchlist.json")) as _f:
    FETCHLIST = json.load(_f)
CAPTURES = [e for e in FETCHLIST if e.get("launch_window")]


def corpus_copy(tmp, cases, fetchlist=True):
    """A corpus root with the manifest, the cases' expected.json (plus the gate's) and, unless told otherwise, the
    fetch list; no provider file."""
    shutil.copy(os.path.join(ROOT, "manifest.json"), tmp)
    for c in sorted(set(cases) | {GATE_CASE}):
        os.makedirs(os.path.join(tmp, "fixtures", c))
        shutil.copy(os.path.join(ROOT, "fixtures", c, "expected.json"), os.path.join(tmp, "fixtures", c))
    if fetchlist:
        os.makedirs(os.path.join(tmp, "tools"))
        shutil.copy(os.path.join(ROOT, "tools", "fetchlist.json"), os.path.join(tmp, "tools"))


def run_cli(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = gpconf_main(argv)
    return code, out.getvalue()


class TheList(unittest.TestCase):
    def test_ten_entries_name_their_launch_and_no_other_does(self):
        self.assertEqual(len(CAPTURES), 10)
        self.assertEqual({e["launch_window"] for e in CAPTURES}, {LABEL})
        self.assertEqual({e["case"] for e in CAPTURES}, {PARTLY})                       # the folder they were captured into
        marked = {e["url"] for e in CAPTURES}
        by_url = {e["url"] for e in FETCHLIST if "FILE=starlink-g15-27&" in e["url"] or "CATNR=799501621&" in e["url"]}
        self.assertEqual(marked, by_url)
        self.assertFalse([e["file"] for e in CAPTURES if e.get("recapture_of")])

    def test_a_users_run_has_four_known_404s(self):
        user = [e for e in FETCHLIST if not e.get("recapture_of") and not e.get("launch_window")]
        self.assertEqual(len(user), 51)                                              # 50 without the SATCAT file, which is on request (D-231)
        self.assertEqual(sorted(e["file"] for e in user if e.get("expect_status") == 404),
                         ["analyst-270449-first.tle", "last-30-days.tle", "saramago-first.tle", "saramago.tle"])

    def test_every_capture_is_a_source_of_some_case(self):
        with open(os.path.join(ROOT, "manifest.json")) as f:
            man = json.load(f)
        used = {s["path"] for c in man["cases"] for s in c.get("sources", [])}
        files = launch_window_files(ROOT)
        self.assertEqual(len(files), 10)
        self.assertEqual(set(files.values()), {LABEL})
        self.assertLessEqual(set(files), used)
        whole = [c["id"] for c in man["cases"] if (p := [s["path"] for s in c.get("sources", []) if "/raw/" in s["path"]]) and set(p) <= set(files)]
        self.assertEqual(whole, [ALL_CAPTURES])                                        # one case rests on captures alone


class TheFetchNeverAsks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_plan_holds_a_capture_whatever_is_asked_for(self):
        for opts in ({}, {"force": True}, {"include_recaptures": True}, {"force": True, "include_recaptures": True}):
            with self.subTest(opts=opts):
                planned = fetch.plan(FETCHLIST, root=self.root, **opts)
                self.assertFalse([p["entry"]["file"] for p in planned if p["entry"].get("launch_window")])
                self.assertEqual(sum(1 for p in planned if p["action"] == "fetch"), 50)
                self.assertEqual(sum(1 for p in fetch.plan(FETCHLIST, root=self.root, include_satcat=True, **opts) if p["action"] == "fetch"), 51)

    def test_no_run_requests_one_and_the_run_says_why(self):
        for argv in ([], ["--force"], ["--include-recaptures"], ["--case", PARTLY], ["--stage", "A"], ["--stage", "D"]):
            with self.subTest(argv=argv):
                asked, out = [], io.StringIO()

                def stub(entry, root=None, asked=asked):
                    asked.append(entry["url"])
                    return "stub"
                fetch.run(list(argv), root=self.root, corpus=ROOT, entries=FETCHLIST, fetch_one=stub, out=out, pause=0)
                self.assertFalse([u for u in asked if "g15-27" in u or "799501621" in u], argv)
                self.assertIn(f"launch-window capture(s) ({LABEL}).", out.getvalue())
                self.assertIn("no fetch asks for them", out.getvalue())

    def test_stage_a_alone_holds_only_captures_and_asks_nothing(self):
        asked, out = [], io.StringIO()
        code = fetch.run(["--stage", "A"], root=self.root, corpus=ROOT, entries=FETCHLIST,
                         fetch_one=lambda e, root=None: asked.append(e["url"]) or "stub", out=out, pause=0)
        self.assertEqual((code, asked), (0, []))
        self.assertIn("not requested: 5 launch-window capture(s)", out.getvalue())
        self.assertIn("done: 0 request(s) made", out.getvalue())


class TheRunnerSaysNotAvailable(unittest.TestCase):
    def test_a_case_whose_files_are_all_captures_is_not_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus_copy(tmp, [ALL_CAPTURES])
            r = Runner(Reference(), root=tmp).run(case_ids=[ALL_CAPTURES])[0]
        self.assertEqual(r.status, "not-available")
        self.assertEqual({(i.check, i.status) for i in r.items}, {("source-present", "not-available")})
        self.assertEqual((len(r.unavailable()), r.missing()), (5, []))
        self.assertEqual(r.counts()["not-available"], 5)
        self.assertEqual(r.as_dict()["counts"]["not-available"], 5)
        for i in r.items:
            self.assertIn(f"a launch-window capture ({LABEL})", i.detail)
            self.assertIn("no fetch requests it", i.detail)
            self.assertNotRegex(i.detail, r"fetch it with|gpconf fetch|tools/fetch\.py")   # there is no command to give

    def test_a_case_with_something_still_to_fetch_says_not_fetched(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus_copy(tmp, [PARTLY])
            r = Runner(Reference(), root=tmp).run(case_ids=[PARTLY])[0]
        self.assertEqual(r.status, "not-fetched")                                       # the full Starlink file is a fetch away
        c = r.counts()
        self.assertEqual((c["not-fetched"], c["not-available"]), (1, 5))
        self.assertEqual([os.path.basename(p) for p in r.missing()], ["starlink-all.csv"])

    def test_the_status_ranks_below_not_fetched_and_above_skip(self):
        def status(*statuses):
            r = CaseResult("c", "t")
            for s in statuses:
                r.add("x", s)
            return r.status
        self.assertEqual(status("not-available", "pass"), "pass")
        self.assertEqual(status("not-available", "fail", "pass"), "fail")
        self.assertEqual(status("not-available", "not-exercised"), "not-exercised")
        self.assertEqual(status("not-available", "not-fetched"), "not-fetched")
        self.assertEqual(status("not-available", "skip", "info"), "not-available")
        self.assertEqual(status("skip", "info"), "skip")

    def test_the_command_line_counts_it_and_names_no_fetch_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus_copy(tmp, [ALL_CAPTURES])
            report = os.path.join(tmp, "report.json")
            code, text = run_cli(["run", "--adapter", "tests.adapters.reference:Parser", "--root", tmp, "--case", ALL_CAPTURES, "--json", report])
            with open(report) as f:
                rep = json.load(f)
        self.assertEqual(code, 0)                                                       # absence is not a failure of the parser
        self.assertIn("exact  tol fail skip n/e n/f n/a", text)
        self.assertRegex(text, rf"{ALL_CAPTURES}\s+not-available\s+0\s+0\s+0\s+0\s+0\s+0\s+5\n")
        self.assertIn("1 case(s): 0 pass (exact), 0 pass within tolerance, 0 fail, 0 skip, 0 need fetched data, 1 not available, 0 not exercised", text)
        self.assertIn(f"1 case(s) cannot run from a fetch and report not-available: {ALL_CAPTURES}.", text)
        self.assertIn("The counts the corpus publishes were measured with those files.", text)
        self.assertIn("so it can show fewer failing cases than a published count", text)
        self.assertNotIn("fetch it with", text)
        self.assertNotIn("have none of their provider files on disk and report not-fetched", text)
        (r,) = rep["results"]
        self.assertEqual((r["status"], r["counts"]["not-available"], r["counts"]["not-fetched"]), ("not-available", 5, 0))

    def test_a_case_judged_on_its_other_files_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus_copy(tmp, [ALL_CAPTURES, PARTLY])
            code, text = run_cli(["run", "--adapter", "tests.adapters.reference:Parser", "--root", tmp, "--case", ALL_CAPTURES, "--case", PARTLY])
        self.assertIn("2 case(s): 0 pass (exact), 0 pass within tolerance, 0 fail, 0 skip, 1 need fetched data, 1 not available, 0 not exercised", text)
        self.assertIn(f"1 other case(s) name 5 launch-window file(s) (column n/a) and are judged on their other files: {PARTLY}.", text)
        self.assertIn("fetch it with", text)                                            # for the one file a fetch does bring

    def test_a_copy_without_the_fetch_list_cannot_tell_and_says_not_fetched(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus_copy(tmp, [ALL_CAPTURES], fetchlist=False)
            self.assertEqual(launch_window_files(tmp), {})
            r = Runner(Reference(), root=tmp).run(case_ids=[ALL_CAPTURES])[0]
        self.assertEqual(r.status, "not-fetched")

    def test_what_an_earlier_fetch_saved_in_a_captures_place_is_not_read(self):
        """A fetch before v0.5.1 asked for these files; once the window had closed it would have saved the provider's
        no-data answer where the capture belongs. That is not the capture."""
        rel = f"fixtures/{PARTLY}/raw/starlink-g15-27.csv"
        with tempfile.TemporaryDirectory() as tmp:
            corpus_copy(tmp, [ALL_CAPTURES])
            os.makedirs(os.path.join(tmp, os.path.dirname(rel)))
            with open(os.path.join(tmp, rel), "wb") as f:
                f.write(b"No SupGP data found")
            with open(os.path.join(tmp, rel + ".meta.json"), "w") as f:
                json.dump({"http_status": 404, "retrieved_at": "2026-09-27T10:00:00Z"}, f)
            r = Runner(Reference(), root=tmp).run(case_ids=[ALL_CAPTURES])[0]
        self.assertEqual(r.status, "not-available")
        self.assertEqual({i.status for i in r.items}, {"not-available"})
        (item,) = [i for i in r.items if i.file == rel]
        self.assertIn("holds an HTTP 404 response that an earlier fetch saved in its place, and is not read", item.detail)
        self.assertEqual(r.unexpected, {})


if __name__ == "__main__":
    unittest.main()
