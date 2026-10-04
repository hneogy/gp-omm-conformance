"""D-247: the one provider response the corpus ships, and the fetch that no longer requests it.

CelesTrak answers a TLE request for an object numbered above 99999 with HTTP 404 and the 16-byte text
"No GP data found". Four entries of a user's fetch are such requests. Up to 0.5.1 the fetch made them and let the
404 pass, its one exception to "stop on any response that is not a 200". Now the answer ships with the corpus, in
recorded/, with the provenance of every capture of it; the fetch writes it where it used to request it, under no flag
does it ask for those URLs, and no request of a user's run is expected to answer anything but 200.

This is a named exception to D-023 (no raw CelesTrak bytes are shipped), so the tests also hold the exception to its
name: one file, those sixteen bytes, nothing else under recorded/, and the public sentences that say so.

Run: python -m unittest tests.test_recorded_answer"""
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fetch  # noqa: E402
from gpconf.__main__ import main as gpconf_main  # noqa: E402
from gpconf.runner import Runner  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402

RECORD = "recorded/celestrak-no-gp-data-found.txt"
PROVENANCE = "recorded/celestrak-no-gp-data-found.provenance.json"
BODY = b"No GP data found"
SHA = "000844fd5b7a7b64f14b58cc34f0016ad51b0982b0d38f915986560e4e217683"
FOUR = ["fixtures/analyst-objects/raw/analyst-270449-first.tle", "fixtures/six-digit-omm-saramago/raw/saramago-first.tle",
        "fixtures/six-digit-omm-saramago/raw/saramago.tle", "fixtures/tle-omits-six-digit-objects/raw/last-30-days.tle"]
NOW = dt.datetime(2026, 10, 5, 12, 0, 0, tzinfo=dt.timezone.utc)
CASE = "tle-omits-six-digit-objects"
CSV = f"fixtures/{CASE}/raw/last-30-days.csv"
TLE = f"fixtures/{CASE}/raw/last-30-days.tle"
SUPGP_TLE = "fixtures/nine-digit-supgp-launch-nominals/raw/starlink-38381-799501621.tle"


def read(rel, mode="r"):
    with open(os.path.join(ROOT, *rel.split("/")), mode, **({} if "b" in mode else {"encoding": "utf-8"})) as f:
        return f.read()


def flat(text):
    return " ".join(text.split())


FETCHLIST = json.loads(read("tools/fetchlist.json"))
MANIFEST = json.loads(read("manifest.json"))
SOURCES = {}
for _c in MANIFEST["cases"]:
    for _s in _c.get("sources", []):
        SOURCES.setdefault(_s["path"], _s)
RECORDED_ENTRIES = [e for e in FETCHLIST if e.get("recorded")]


class TheRecord(unittest.TestCase):
    def test_it_is_the_sixteen_bytes_and_nothing_else_is_there(self):
        self.assertEqual(read(RECORD, "rb"), BODY)
        self.assertEqual(hashlib.sha256(BODY).hexdigest(), SHA)
        self.assertEqual(sorted(os.listdir(os.path.join(ROOT, "recorded"))),
                         ["celestrak-no-gp-data-found.provenance.json", "celestrak-no-gp-data-found.txt"])

    def test_its_provenance_names_every_capture(self):
        p = json.loads(read(PROVENANCE))
        self.assertEqual((p["file"], p["text"], p["bytes"], p["sha256"], p["http_status"]), (RECORD, BODY.decode(), 16, SHA, 404))
        self.assertIs(p["holds_orbital_data"], False)
        self.assertIn("D-023", p["exception"])
        self.assertIn("D-247", p["exception"])
        self.assertEqual(p["written_by_the_fetch_as"], FOUR)
        self.assertEqual(len(p["captures"]), 5)                                       # the four, and the re-capture of one of them
        self.assertEqual(len(p["received_again"]), 4)
        for c in p["captures"] + p["received_again"]:
            self.assertEqual((c["http_status"], c["bytes"], c["sha256"]), (404, 16, SHA), c)
            self.assertRegex(c["url"], r"^https://celestrak\.org/NORAD/elements/gp(-first)?\.php\?(CATNR=(100000|270449)|GROUP=last-30-days)&FORMAT=(TLE|tle)$")
            self.assertRegex(c["retrieved_at"], r"^2026-(09-21|10-04)T\d\d:\d\d:\d\dZ$")
        # each capture is the manifest's record of that file
        for c in p["captures"]:
            self.assertEqual((SOURCES[c["file"]]["retrieved_at"], SOURCES[c["file"]]["sha256"], SOURCES[c["file"]]["http_status"]),
                             (c["retrieved_at"], SHA, 404))
        self.assertEqual({c["url"] for c in p["received_again"]}, {e["url"] for e in RECORDED_ENTRIES})

    def test_no_orbital_data_is_in_it(self):
        text = BODY.decode()
        self.assertFalse(any(ch.isdigit() for ch in text))
        self.assertEqual(len(text.splitlines()), 1)


class TheList(unittest.TestCase):
    def test_four_entries_are_written_from_the_record(self):
        self.assertEqual(sorted(f"fixtures/{e['case']}/raw/{e['file']}" for e in RECORDED_ENTRIES), FOUR)
        for e in RECORDED_ENTRIES:
            self.assertEqual((e["recorded"], e["expect_status"]), (RECORD, 404))
            self.assertFalse(e.get("recapture_of") or e.get("launch_window") or e.get("opt_in"))
            self.assertTrue(e["url"].endswith("&FORMAT=TLE"))

    def test_no_request_of_a_users_run_expects_anything_but_a_200(self):
        user = [e for e in FETCHLIST if not e.get("recapture_of") and not e.get("launch_window") and not e.get("recorded")]
        self.assertEqual(len(user), 47)                                               # 46, and the SATCAT file on request
        self.assertFalse([e["file"] for e in user if "expect_status" in e])
        # the one entry that still names a 404 and can be requested is a maintainer's re-capture
        left = [e["file"] for e in FETCHLIST if e.get("expect_status") and not e.get("recorded") and not e.get("launch_window")]
        self.assertEqual(left, ["last-30-days-recapture.tle"])

    def test_the_manifest_says_which_sources_ship_as_the_record(self):
        self.assertEqual(sorted(p for p, s in SOURCES.items() if s.get("recorded_response")), FOUR)
        for p in FOUR:
            s = SOURCES[p]
            self.assertEqual((s["recorded_response"], s["http_status"], s["bytes"], s["sha256"]), (RECORD, 404, 16, SHA))
        design = MANIFEST["design"]
        self.assertIs(design["provider_data_shipped"], False)
        self.assertEqual(design["raw_provider_files_shipped"], [RECORD])
        shipped = design["provider_responses_shipped"]
        self.assertEqual(len(shipped), 1)
        self.assertEqual((shipped[0]["path"], shipped[0]["sha256"], shipped[0]["holds_orbital_data"], shipped[0]["written_by_the_fetch_as"]),
                         (RECORD, SHA, False, FOUR))


class TheFetch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def run_fetch(self, argv, entries=FETCHLIST):
        asked, out = [], io.StringIO()

        def stub(entry, root=None):
            asked.append(entry["url"])
            return "stub"
        code = fetch.run(list(argv), root=self.root, corpus=ROOT, entries=entries, now=NOW, fetch_one=stub, out=out, pause=0)
        return code, asked, out.getvalue()

    def test_no_plan_requests_one_whatever_is_asked_for(self):
        urls = {e["url"] for e in RECORDED_ENTRIES}
        for opts in ({}, {"force": True}, {"include_recaptures": True}, {"include_satcat": True},
                     {"force": True, "include_recaptures": True, "include_satcat": True}):
            with self.subTest(opts=opts):
                planned = fetch.plan(FETCHLIST, root=self.root, now=NOW, **opts)
                self.assertFalse([p["entry"]["file"] for p in planned if p["action"] == "fetch" and p["entry"]["url"] in urls])
                self.assertEqual(sorted(p["entry"]["file"] for p in planned if p["action"] == "record"),
                                 sorted(e["file"] for e in RECORDED_ENTRIES))

    def test_a_run_writes_the_four_and_requests_none_of_them(self):
        code, asked, out = self.run_fetch([])
        self.assertEqual(len(asked), 46)
        self.assertFalse(set(asked) & {e["url"] for e in RECORDED_ENTRIES})
        self.assertIn("not requested: 4 TLE requests for objects numbered above 99999, which CelesTrak answers with HTTP 404 and the text "
                      "'No GP data found'. That answer ships with the corpus as a recorded response (recorded/); the files are written from it.", out)
        self.assertIn("done: 46 requests made, 4 files written from the corpus's record of the provider's answer, 0 entries skipped", out)
        for e in RECORDED_ENTRIES:
            rel = f"fixtures/{e['case']}/raw/{e['file']}"
            with open(os.path.join(self.root, rel), "rb") as f:
                self.assertEqual(f.read(), BODY)
            with open(os.path.join(self.root, rel + ".meta.json")) as f:
                meta = json.load(f)
            self.assertEqual((meta["provenance"], meta["requested"], meta["http_status"], meta["bytes"], meta["sha256"], meta["url"]),
                             ("recorded", False, 404, 16, SHA, e["url"]))
            self.assertEqual(meta["retrieved_at"], SOURCES[rel]["retrieved_at"])      # the corpus's capture, not the time of this run
            self.assertEqual(meta["recorded"]["file"], RECORD)
            self.assertEqual(len(meta["recorded"]["received_again"]), 1)
            self.assertIn("Not requested by this fetch.", meta["note"])
            self.assertNotIn("response_headers", meta)                               # nothing was received, so nothing of a response is claimed

    def test_the_dry_run_says_so_and_writes_nothing(self):
        code, asked, out = self.run_fetch(["--dry-run"])
        self.assertEqual(asked, [])
        self.assertEqual(sum(1 for line in out.splitlines() if line.startswith("RECORD  ")), 4)
        self.assertIn("dry run: no request made; a run would make 46 requests, write 4 files from the corpus's record of the provider's "
                      "answer and leave 0 entries as they are", out)
        self.assertEqual(os.listdir(self.root), [])

    def test_a_file_on_disk_is_left_alone_and_never_refreshed(self):
        """In the maintainer's clone the four files are the captures themselves: no run overwrites or re-requests them."""
        e = RECORDED_ENTRIES[0]
        d = os.path.join(self.root, "fixtures", e["case"], "raw")
        os.makedirs(d)
        with open(os.path.join(d, e["file"]), "wb") as f:
            f.write(BODY)
        with open(os.path.join(d, e["file"] + ".meta.json"), "w") as f:
            json.dump({"retrieved_at": "2026-09-21T00:09:59Z", "http_status": 404, "provenance": "live"}, f)
        for opts in ({}, {"force": True}):
            plan = {p["entry"]["file"]: p for p in fetch.plan(FETCHLIST, root=self.root, now=NOW, **opts)}
            self.assertEqual(plan[e["file"]]["action"], "cached")
            self.assertIn("never requested", plan[e["file"]]["reason"])
        self.run_fetch(["--force"])
        with open(os.path.join(d, e["file"] + ".meta.json")) as f:
            self.assertEqual(json.load(f)["provenance"], "live")

    def test_a_record_that_is_not_the_recorded_bytes_is_refused(self):
        corpus = os.path.join(self.root, "corpus")
        os.makedirs(os.path.join(corpus, "recorded"))
        shutil.copy(os.path.join(ROOT, "manifest.json"), corpus)
        shutil.copy(os.path.join(ROOT, *PROVENANCE.split("/")), os.path.join(corpus, "recorded"))
        with open(os.path.join(corpus, *RECORD.split("/")), "wb") as f:
            f.write(b"not the recorded answer")
        with self.assertRaisesRegex(ValueError, "does not hold the bytes"):
            fetch.recorded_answer(RECORDED_ENTRIES[0], corpus)
        self.assertEqual(fetch.recorded_answer(RECORDED_ENTRIES[0], ROOT)[0], BODY)

    def test_the_stable_ones_are_written_not_copied_from_an_earlier_version(self):
        old = os.path.join(self.root, "gpconf", "0.5.1")
        new = os.path.join(self.root, "gpconf", "0.6.0")
        os.makedirs(new)
        stable = [e for e in RECORDED_ENTRIES if SOURCES[f"fixtures/{e['case']}/raw/{e['file']}"]["tier"] == "stable"]
        self.assertEqual(len(stable), 2)
        for e in stable:
            d = os.path.join(old, "fixtures", e["case"], "raw")
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, e["file"]), "wb") as f:
                f.write(BODY)
            with open(os.path.join(d, e["file"] + ".meta.json"), "w") as f:
                json.dump({"retrieved_at": "2026-10-04T03:26:08Z", "http_status": 404}, f)
        self.assertEqual(fetch.reusable(stable, new, ROOT, fetch.version_folders(new)), {})


@unittest.skipUnless(os.path.exists(os.path.join(ROOT, *CSV.split("/"))), "the group's CSV is provider data and is not on disk")
class TheRunner(unittest.TestCase):
    """With the record in the data folder in place of a fetched answer. Needs the group's CSV, which is provider data, so
    these run where a fetch has been made and skip in CI."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = self.tmp.name
        fetch.run([], root=self.data, corpus=ROOT, entries=[e for e in RECORDED_ENTRIES if e["case"] == CASE], now=NOW,
                  fetch_one=lambda e, root=None: self.fail("a request was made"), out=io.StringIO(), pause=0)

    def tearDown(self):
        self.tmp.cleanup()

    def put_csv(self, change=None):
        raw = read(CSV, "rb")
        if change:
            raw = change(raw)
        with open(os.path.join(self.data, *CSV.split("/")), "wb") as f:
            f.write(raw)

    def run_case(self):
        return Runner(Reference(), root=ROOT, data=self.data).run(case_ids=[CASE])[0]

    def items(self, res, check):
        return [i for i in res.items if i.check == check]

    def test_the_parser_is_still_handed_the_empty_answer(self):
        self.put_csv()
        res = self.run_case()
        empty = [i for i in self.items(res, "empty-answer-yields-no-records") if i.file == TLE]
        self.assertEqual([i.status for i in empty], ["pass"])
        self.assertIn("(HTTP 404, body 'No GP data found', 16 bytes) read as zero records, no error", empty[0].detail)

    def test_the_items_say_the_answer_is_the_corpus_s_record(self):
        self.put_csv()
        res = self.run_case()
        self.assertEqual(res.recorded, {TLE: {"file": RECORD, "http_status": 404, "captured_at": SOURCES[TLE]["retrieved_at"]}})
        self.assertEqual(res.as_dict()["recorded"], res.recorded)
        for check in ("tle-format-omits-ids-above-99999", "tle-count-equals-omm-count-below-100000"):
            (item,) = self.items(res, check)
            self.assertEqual(item.status, "pass")
            self.assertEqual(item.detail, f"the corpus's record of the TLE answer is 'No GP data found' (HTTP 404, captured {SOURCES[TLE]['retrieved_at']}; "
                                          "not requested by this fetch); OMM set has 0 ids below 100000 (expected 0)")
        info = [i for i in self.items(res, "sha256-matches-tested-snapshot") if i.file == TLE]
        self.assertEqual(info[0].detail, f"snapshot: the corpus's record of the provider's empty answer (captured {SOURCES[TLE]['retrieved_at']}), "
                                         "written by the fetch and not requested")
        self.assertNotEqual(res.status, "fail")

    def test_a_record_that_no_longer_describes_the_day_is_not_compared(self):
        """If the fetched group holds an id the TLE format can carry, CelesTrak's answer that day is data, not the
        recorded 404. The fetch did not ask, so the comparison is not made: a stale record is never a failure."""
        def one_five_digit_id(raw):
            lines = raw.decode("utf-8").splitlines(keepends=True)
            head = lines[0].strip().split(",")
            col = head.index("NORAD_CAT_ID")
            row = lines[1].rstrip("\r\n").split(",")
            row[col] = "25544"
            lines[1] = ",".join(row) + lines[1][len(lines[1].rstrip("\r\n")):]
            return "".join(lines).encode("utf-8")
        self.put_csv(one_five_digit_id)
        res = self.run_case()
        for check in ("tle-format-omits-ids-above-99999", "tle-count-equals-omm-count-below-100000"):
            (item,) = self.items(res, check)
            self.assertEqual(item.status, "not-exercised", item.detail)
            self.assertIn("the OMM set fetched now holds 1, so CelesTrak's TLE answer today is not the recorded one, and this fetch did not request it: not compared", item.detail)
        self.assertFalse([i.check for i in res.items if i.status == "fail" and i.check.startswith("tle-")])

    def test_the_run_says_how_many_files_are_the_record(self):
        self.put_csv()
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            gpconf_main(["run", "--preset", "reference", "--root", ROOT, "--data", self.data, "--case", CASE])
        self.assertIn("1 provider file holds the corpus's record of CelesTrak's empty answer (HTTP 404, 'No GP data found', to a TLE request "
                      "above 99999): written by the fetch from recorded/, not requested.", out.getvalue())


@unittest.skipUnless(os.path.exists(os.path.join(ROOT, *TLE.split("/"))), "the maintainer's captures are provider data and are not on disk")
class ACaptureIsStillACapture(unittest.TestCase):
    """On the maintainer's copy the four files are the responses themselves, and nothing about them is reworded."""

    def test_a_fetched_answer_is_described_as_requested(self):
        res = Runner(Reference(), root=ROOT).run(case_ids=[CASE])[0]
        self.assertEqual(res.recorded, {})
        (item,) = [i for i in res.items if i.check == "tle-format-omits-ids-above-99999"]
        self.assertEqual(item.detail, "TLE request returned 'No GP data found'; OMM set has 0 ids below 100000 (expected 0)")

    @unittest.skipUnless(os.path.exists(os.path.join(ROOT, *SUPGP_TLE.split("/"))), "the launch-window capture is not on disk")
    def test_the_supgp_answer_is_quoted_as_it_is(self):
        """The item used to say 'No GP data found' of a file whose body is 'No SupGP data found' (fixed with D-247)."""
        self.assertEqual(read(SUPGP_TLE, "rb").strip(), b"No SupGP data found")
        res = Runner(Reference(), root=ROOT).run(case_ids=["nine-digit-supgp-launch-nominals"])[0]
        details = [i.detail for i in res.items if i.check == "tle-format-omits-ids-above-99999"]
        self.assertEqual(details, ["TLE request returned 'No SupGP data found'; OMM set has 0 ids below 100000 (expected 0)"])


class TheExceptionIsNamed(unittest.TestCase):
    """D-023 shipped no raw CelesTrak bytes. Where the corpus said so, it now names the one response it ships."""

    def test_the_readme_names_it_where_it_says_no_raw_files(self):
        readme = flat(read("README.md"))
        self.assertIn("It carries no provider data, and one provider response, named below", readme)
        self.assertIn("One exception, named here because the rule has no other (D-247, which amends D-023): the corpus ships one response from CelesTrak, "
                      "`recorded/celestrak-no-gp-data-found.txt`.", readme)
        self.assertIn("It holds no orbital data: no element, no catalog number, nothing that stands in for a fetch.", readme)
        self.assertIn("It is CelesTrak's text, and the MIT licence does not cover it.", readme)
        # the status paragraph: "is now 46 requests" at 0.6.0, where the change was made; from 0.6.1 it says the list is 0.6.0's
        self.assertIn("A user's fetch is 46 requests, the same 46 as in 0.6.0, and asks for nothing it knows will answer 404", readme)

    def test_the_notice_the_citation_and_the_manifest_document_name_it(self):
        self.assertIn('One response from CelesTrak is in the repository, and the licence does not cover it either: the 16-byte text "No GP data found" in recorded/',
                      flat(read("NOTICE")))
        self.assertIn('No provider data is redistributed, and one provider response is, the 16-byte answer "No GP data found"', flat(read("CITATION.cff")))
        self.assertIn("No provider data is shipped, and one provider response is: CelesTrak's 16-byte answer `No GP data found`, in `recorded/` with its "
                      "provenance, which holds no orbital data (D-247, a named exception to D-023).", read("MANIFEST.md"))
        for old in ("No raw provider files are shipped.", "Raw provider data is not redistributed"):
            for name in ("MANIFEST.md", "CITATION.cff"):
                self.assertNotIn(old, read(name))

    def test_the_export_carries_the_two_files_by_name_and_refuses_anything_else_there(self):
        allow = read("PUBLIC_ALLOWLIST.txt").splitlines()
        self.assertIn(RECORD, allow)
        self.assertIn(PROVENANCE, allow)
        self.assertFalse([line for line in allow if line.startswith("recorded/") and "*" in line])
        with tempfile.TemporaryDirectory() as tmp:
            p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "export_public.py"), "--dest", os.path.join(tmp, "out"), "--dry-run"],
                               capture_output=True, text=True, timeout=300)
        self.assertEqual(p.returncode, 0, p.stderr)
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import export_public
        self.assertEqual(export_public.RECORDED, {RECORD: SHA, PROVENANCE: None})

    def test_the_package_carries_them_for_the_fetch_to_read(self):
        import stage_package
        self.assertIn(RECORD, stage_package.CORPUS)
        self.assertIn(PROVENANCE, stage_package.CORPUS)


if __name__ == "__main__":
    unittest.main()
