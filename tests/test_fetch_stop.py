"""D-228: the fetch stops at the first response the list does not expect, and that response never becomes data.

CelesTrak asks software to stop querying on any response that is not an HTTP 200 and to have a person look, and says a
403 or 404 will not change by repeating the request. The fetch used to carry an allow_error flag that let any HTTP
error pass on the entries that had it, a 403 included, and it wrote an unexpected response to the data path itself,
where the runner read it as provider data. Now: the run goes on past a non-200 only when it is the provider's 404
with its no-data text on an entry that names it (expect_status); anything else ends the run at once; the response is
kept beside the data as <file>.unexpected; the URL is not asked again short of --force two hours later; and after a
refusal (403 or 429) no request at all is made for two hours.

The real request function runs here against a stand-in opener; socket creation is blocked for the length of each
test, so nothing can leave the machine.

Run: python -m unittest tests.test_fetch_stop"""
import contextlib
import datetime as dt
import email.message
import io
import json
import os
import shutil
import socket
import sys
import tempfile
import unittest
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fetch  # noqa: E402
from gpconf.runner import Runner  # noqa: E402
from gpconf.__main__ import main as gpconf_main  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402

T0 = dt.datetime(2026, 10, 5, 12, 0, 0, tzinfo=dt.timezone.utc)
BASE = "https://celestrak.org/NORAD/elements/gp.php?"
A = {"stage": "A", "case": "c", "file": "a.csv", "url": BASE + "GROUP=analyst&FORMAT=CSV"}
T = {"stage": "A", "case": "c", "file": "t.tle", "url": BASE + "CATNR=100000&FORMAT=TLE", "expect_status": 404}
B = {"stage": "A", "case": "c", "file": "b.csv", "url": BASE + "CATNR=25544&FORMAT=CSV"}
NO_DATA = b"No GP data found"
HTML = b"<!DOCTYPE html>\n<html><head><title>403 Forbidden</title></head><body>one download per update</body></html>\n"


def _blocked(*a, **k):
    raise AssertionError("a test tried to open a socket")


class _Resp:
    def __init__(self, status, body):
        self.status, self.reason, self.version, self._body = status, "OK", 11, body
        self.headers = email.message.Message()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Opener:
    """Answers from a table {url: (status, body)}; an HTTP error is raised as urllib raises it, a redirect included,
    since the fetch follows none. A URL missing from the table raises KeyError: the test did not expect it asked."""

    def __init__(self, table):
        self.table, self.calls = table, []

    def open(self, req, timeout=None):
        url = req.full_url
        self.calls.append(url)
        answer = self.table[url]
        if answer == "no answer":
            raise urllib.error.URLError("timed out")
        status, body = answer
        if status == 200:
            return _Resp(status, body)
        raise urllib.error.HTTPError(url, status, "err", email.message.Message(), io.BytesIO(body))


class _Fetch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.clock = T0
        self._saved = (fetch._opener, fetch.now_utc, socket.socket, socket.create_connection)
        socket.socket = socket.create_connection = _blocked
        fetch.now_utc = lambda precise=False: self.clock.strftime("%Y-%m-%dT%H:%M:%S") + (".000000Z" if precise else "Z")

    def tearDown(self):
        fetch._opener, fetch.now_utc, socket.socket, socket.create_connection = self._saved
        self.tmp.cleanup()

    def go(self, table, argv=(), entries=(A, T, B), minutes=0):
        """One run of the real fetch at T0 + minutes -> (exit code or 'exit N', stdout, stderr, URLs asked)."""
        self.clock = T0 + dt.timedelta(minutes=minutes)
        opener = fetch._opener = Opener(table)
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                code = fetch.run(list(argv), root=self.root, entries=list(entries), now=self.clock, out=out, pause=0)
        except SystemExit as e:
            code = f"exit {e.code}"
        return code, out.getvalue(), err.getvalue(), opener.calls

    def raw(self, name):
        return os.path.join(self.root, "fixtures", "c", "raw", name)

    def meta(self, name):
        with open(self.raw(name) + ".meta.json") as f:
            return json.load(f)


GOOD = {A["url"]: (200, b"OBJECT_NAME,NORAD_CAT_ID\r\nX,81011\r\n"), T["url"]: (404, NO_DATA), B["url"]: (200, b"OBJECT_NAME,NORAD_CAT_ID\r\nISS,25544\r\n")}


class WhatStopsTheRun(_Fetch):
    def test_the_known_404_is_recorded_and_the_run_goes_on(self):
        code, out, err, calls = self.go(GOOD)
        self.assertEqual((code, calls), (0, [A["url"], T["url"], B["url"]]), out + err)
        with open(self.raw("t.tle"), "rb") as f:
            self.assertEqual(f.read(), NO_DATA)                       # the provider's answer is the fixture
        m = self.meta("t.tle")
        self.assertEqual(m["http_status"], 404)
        self.assertNotIn("unexpected", m)
        self.assertIn("expect_status 404", m["note"])
        self.assertFalse(os.path.exists(self.raw("t.tle") + ".unexpected"))
        self.assertEqual(err, "")

    def test_a_403_stops_the_run_at_once_and_never_becomes_data(self):
        code, out, err, calls = self.go({**GOOD, A["url"]: (403, HTML)})
        self.assertEqual((code, calls), ("exit 2", [A["url"]]))        # one request, then none
        self.assertFalse(os.path.exists(self.raw("a.csv")))            # nothing where the data would be
        with open(self.raw("a.csv") + ".unexpected", "rb") as f:
            self.assertEqual(f.read(), HTML)
        m = self.meta("a.csv.unexpected")
        self.assertEqual((m["http_status"], m["unexpected"], m["url"]), (403, "HTTP 403", A["url"]))
        self.assertEqual(m["retrieved_at"], "2026-10-05T12:00:00Z")
        self.assertIn("STOP: HTTP 403 for " + A["url"], err)
        self.assertIn(os.path.join("fixtures", "c", "raw", "a.csv.unexpected"), err)
        self.assertIn("Nothing was retried and no further request was made.", err)
        self.assertIn("CelesTrak has refused this address", err)
        self.assertIn("no request at all for the next two hours", err)
        self.assertIn("one download per update", err)                  # the body is shown: it says why

    def test_a_403_stops_the_run_on_an_entry_that_expects_a_404_too(self):
        """The old allow_error flag let any HTTP error pass on such an entry, a refusal included."""
        code, out, err, calls = self.go({**GOOD, T["url"]: (403, HTML)})
        self.assertEqual((code, calls), ("exit 2", [A["url"], T["url"]]))
        self.assertFalse(os.path.exists(self.raw("t.tle")))
        self.assertEqual(self.meta("t.tle.unexpected")["http_status"], 403)

    def test_a_404_with_another_body_stops_the_run_where_a_404_is_expected(self):
        code, out, err, calls = self.go({**GOOD, T["url"]: (404, HTML)})
        self.assertEqual((code, calls), ("exit 2", [A["url"], T["url"]]))
        self.assertEqual(self.meta("t.tle.unexpected")["unexpected"], "HTTP 404")
        self.assertNotIn("refused this address", err)                  # not a refusal: a report to the corpus
        self.assertIn(fetch.ISSUES_URL, err)
        self.assertIn("only with --force, two hours or more from now", err)

    def test_a_404_where_a_200_is_expected_stops_the_run(self):
        """What the launch nominal's requests would have met once its window closed: the provider's no-data text on
        an entry that expects data."""
        code, out, err, calls = self.go({**GOOD, A["url"]: (404, b"No SupGP data found")})
        self.assertEqual((code, calls), ("exit 2", [A["url"]]))
        self.assertFalse(os.path.exists(self.raw("a.csv")))
        self.assertEqual(self.meta("a.csv.unexpected")["http_status"], 404)

    def test_a_500_a_redirect_and_a_204_stop_the_run(self):
        for status in (500, 301, 204):
            with self.subTest(status=status):
                shutil.rmtree(os.path.join(self.root, "fixtures"), ignore_errors=True)
                code, out, err, calls = self.go({**GOOD, A["url"]: (status, b"")})
                self.assertEqual((code, calls), ("exit 2", [A["url"]]))
                self.assertEqual(self.meta("a.csv.unexpected")["unexpected"], f"HTTP {status}")

    def test_a_200_that_is_an_html_page_or_empty_stops_the_run(self):
        for body, why in ((HTML, "an HTML page under HTTP 200"), (b"  \r\n", "an empty body under HTTP 200")):
            with self.subTest(why=why):
                shutil.rmtree(os.path.join(self.root, "fixtures"), ignore_errors=True)
                code, out, err, calls = self.go({**GOOD, A["url"]: (200, body)})
                self.assertEqual((code, calls), ("exit 2", [A["url"]]))
                self.assertFalse(os.path.exists(self.raw("a.csv")))
                self.assertEqual(self.meta("a.csv.unexpected")["unexpected"], why)
                self.assertIn("STOP: " + why, err)

    def test_an_xml_answer_is_not_taken_for_a_page(self):
        xml = b'<?xml version="1.0" encoding="UTF-8"?>\r\n<ndm xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><omm id="CCSDS_OMM_VERS" version="2.0"></omm></ndm>'
        self.assertIsNone(fetch.why_unexpected({}, 200, xml))
        self.assertIsNone(fetch.why_unexpected({}, 200, b"1 25544U 98067A   26264.50000000  .00010000  00000+0  10000-3 0  9990"))
        self.assertEqual(fetch.why_unexpected({}, 404, NO_DATA), "HTTP 404")                 # a 404 is expected only where the list says so
        self.assertIsNone(fetch.why_unexpected({"expect_status": 404}, 404, b"No SupGP data found\r\n"))

    def test_no_answer_at_all_exits_3_and_keeps_nothing(self):
        code, out, err, calls = self.go({**GOOD, A["url"]: "no answer"})
        self.assertEqual((code, calls), ("exit 3", [A["url"]]))
        self.assertFalse(os.path.exists(os.path.join(self.root, "fixtures")) and os.listdir(os.path.join(self.root, "fixtures", "c", "raw")))
        self.assertIn("STOP: network error", err)


class NotAskedAgain(_Fetch):
    def test_a_later_run_does_not_ask_the_url_again_and_fetches_the_rest(self):
        self.go({**GOOD, A["url"]: (404, b"No SupGP data found")})
        code, out, err, calls = self.go({T["url"]: GOOD[T["url"]], B["url"]: GOOD[B["url"]]}, minutes=10)   # A is not in the table
        self.assertEqual((code, calls), (0, [T["url"], B["url"]]), out + err)
        self.assertIn("answered HTTP 404 0.2 h ago: kept as a.csv.unexpected, not requested again (--force applies after two hours)", out)
        self.assertTrue(os.path.exists(self.raw("b.csv")))

    def test_force_asks_again_only_after_two_hours_and_a_good_answer_clears_the_kept_one(self):
        self.go({**GOOD, A["url"]: (500, b"<html>Internal Server Error</html>")})
        code, out, err, calls = self.go({T["url"]: GOOD[T["url"]], B["url"]: GOOD[B["url"]]}, argv=["--force"], minutes=60)
        self.assertEqual((code, calls), (0, [T["url"], B["url"]]), out + err)
        self.assertIn("less than two hours: --force does not apply", out)
        code, out, err, calls = self.go(GOOD, argv=["--force"], minutes=180)
        self.assertEqual(calls[0], A["url"])                                 # asked again, three hours on
        self.assertEqual(code, 0, out + err)
        self.assertTrue(os.path.exists(self.raw("a.csv")))
        self.assertFalse(os.path.exists(self.raw("a.csv") + ".unexpected"))
        self.assertFalse(os.path.exists(self.raw("a.csv") + ".unexpected.meta.json"))

    def test_the_dry_run_says_so_and_asks_nothing(self):
        self.go({**GOOD, A["url"]: (404, HTML)})
        code, out, err, calls = self.go({}, argv=["--dry-run"], minutes=30)
        self.assertEqual((code, calls), (0, []))
        self.assertIn("unexpected " + A["url"], out)
        self.assertIn("FETCH   " + T["url"], out)
        self.assertIn("a run would make 2 requests", out)

    def test_a_cached_file_whose_refresh_was_refused_keeps_its_data(self):
        self.go(GOOD)
        code, out, err, calls = self.go({**GOOD, A["url"]: (403, HTML)}, argv=["--force"], minutes=180)
        self.assertEqual((code, calls), ("exit 2", [A["url"]]))
        with open(self.raw("a.csv"), "rb") as f:
            self.assertEqual(f.read(), GOOD[A["url"]][1])                    # the earlier data stands
        self.assertEqual(self.meta("a.csv")["retrieved_at"], "2026-10-05T12:00:00Z")
        self.assertEqual(self.meta("a.csv.unexpected")["http_status"], 403)
        plan = {p["entry"]["file"]: (p["action"], p["reason"]) for p in fetch.plan([A, T, B], force=True, root=self.root, now=T0 + dt.timedelta(minutes=181))}
        self.assertEqual(plan["a.csv"][0], "cached")                         # and is not asked for again inside two hours of the refusal
        self.assertIn("answered HTTP 403 0.0 h ago", plan["a.csv"][1])


class TwoQuietHoursAfterARefusal(_Fetch):
    def test_no_request_is_made_inside_two_hours_whatever_is_asked_for(self):
        self.go({**GOOD, A["url"]: (403, HTML)})
        for argv in ([], ["--force"], ["--dry-run"], ["--case", "c"]):
            with self.subTest(argv=argv):
                code, out, err, calls = self.go({}, argv=argv, minutes=30)   # an empty table: any request would raise
                self.assertEqual((code, calls), (2, []))
                self.assertIn("STOP: CelesTrak refused this address with HTTP 403 30 minutes ago", out)
                self.assertIn("No request is made for two hours after a refusal, with or without --force: 90 minutes remain.", out)
                self.assertIn(os.path.join("fixtures", "c", "raw", "a.csv.unexpected"), out)

    def test_after_two_hours_the_rest_is_fetched_and_the_refused_url_is_not(self):
        self.go({**GOOD, A["url"]: (403, HTML)})
        code, out, err, calls = self.go({T["url"]: GOOD[T["url"]], B["url"]: GOOD[B["url"]]}, minutes=121)
        self.assertEqual((code, calls), (0, [T["url"], B["url"]]), out + err)
        self.assertIn("answered HTTP 403 2.0 h ago: kept as a.csv.unexpected, not requested again", out)

    def test_a_429_is_a_refusal_and_a_500_is_not(self):
        self.go({**GOOD, A["url"]: (429, b"Too Many Requests")})
        self.assertEqual(self.go({}, minutes=5)[0], 2)
        shutil.rmtree(os.path.join(self.root, "fixtures"))
        self.go({**GOOD, A["url"]: (500, b"")})
        code, out, err, calls = self.go({T["url"]: GOOD[T["url"]], B["url"]: GOOD[B["url"]]}, minutes=5)
        self.assertEqual((code, calls), (0, [T["url"], B["url"]]))          # a server error leaves the other URLs askable

    def test_checking_drift_needs_no_request_and_is_not_blocked(self):
        self.go({**GOOD, A["url"]: (403, HTML)})
        code, out, err, calls = self.go({}, argv=["--check-drift"], minutes=5)
        self.assertEqual(calls, [])
        self.assertNotIn("STOP", out)


class TheShippedList(unittest.TestCase):
    """The list names an expected status on exactly the entries the manifest records as answering 404."""

    def test_expect_status_agrees_with_the_manifest(self):
        with open(os.path.join(ROOT, "tools", "fetchlist.json")) as f:
            entries = json.load(f)
        with open(os.path.join(ROOT, "manifest.json")) as f:
            man = json.load(f)
        recorded = {}
        for c in man["cases"]:
            for s in c.get("sources", []):
                recorded.setdefault(s["path"], s.get("http_status"))
        self.assertFalse([e["file"] for e in entries if "allow_error" in e])
        self.assertEqual({e["expect_status"] for e in entries if "expect_status" in e}, {404})
        for e in entries:
            path = f"fixtures/{e['case']}/raw/{e['file']}"
            self.assertEqual(e.get("expect_status", 200), recorded[path], path)
        self.assertEqual(sorted(e["file"] for e in entries if e.get("expect_status") == 404),
                         ["analyst-270449-first.tle", "last-30-days-recapture.tle", "last-30-days.tle", "saramago-first.tle",
                          "saramago.tle", "starlink-38381-799501621.tle"])


CASE = "bstar-and-derivative-forms"
DATA_FILE = f"fixtures/{CASE}/raw/decaying.csv"                 # recorded as HTTP 200
EMPTY_CASE = "tle-omits-six-digit-objects"
EMPTY_FILE = f"fixtures/{EMPTY_CASE}/raw/last-30-days.tle"      # recorded as HTTP 404, the provider's no-data text


def corpus_copy(tmp, cases):
    """A corpus root with the manifest and the cases' expected.json (plus the gate's case, which the command line
    reads), an empty raw folder for each, and no provider file."""
    shutil.copy(os.path.join(ROOT, "manifest.json"), tmp)
    for c in sorted(set(cases) | {EMPTY_CASE}):
        os.makedirs(os.path.join(tmp, "fixtures", c, "raw"))
        shutil.copy(os.path.join(ROOT, "fixtures", c, "expected.json"), os.path.join(tmp, "fixtures", c))


def put(tmp, rel, body, status, at="2026-10-05T12:00:00Z", why=None):
    with open(os.path.join(tmp, rel), "wb") as f:
        f.write(body)
    meta = {"http_status": status, "retrieved_at": at, "url": "https://celestrak.org/x"}
    if why:
        meta["unexpected"] = why
    with open(os.path.join(tmp, rel + ".meta.json"), "w") as f:
        json.dump(meta, f)


def run_cli(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = gpconf_main(argv)
    return code, out.getvalue()


class TheRunnerNeverReadsAnUnexpectedResponse(unittest.TestCase):
    """Before D-228 a refusal page saved in the data's place made the reference adapter fail the case: "reference
    reader found 0 of 565 expected records". An error page is not a result of the parser under test."""

    def test_a_kept_response_is_reported_as_not_fetched_with_what_the_fetch_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus_copy(tmp, [CASE])
            put(tmp, DATA_FILE + ".unexpected", HTML, 403, why="HTTP 403")
            r = Runner(Reference(), root=tmp).run(case_ids=[CASE])[0]
            code, text = run_cli(["run", "--adapter", "tests.adapters.reference:Parser", "--root", tmp, "--case", CASE])
        self.assertEqual(r.status, "not-fetched")
        self.assertEqual({i.status for i in r.items}, {"not-fetched"})   # nothing failed, nothing was parsed
        (item,) = [i for i in r.items if i.file == DATA_FILE]
        self.assertIn("the fetch got HTTP 403 for it at 2026-10-05T12:00:00Z and kept that response as decaying.csv.unexpected", item.detail)
        self.assertIn("is not provider data and is not read", item.detail)
        self.assertIn("only with --force, two hours or more after that answer", item.detail)
        self.assertNotIn("fetch it with", item.detail)
        self.assertEqual(r.as_dict()["unexpected"], {DATA_FILE: {"http_status": 403, "at": "2026-10-05T12:00:00Z", "why": "HTTP 403", "kept": "decaying.csv.unexpected"}})
        self.assertEqual(code, 0)
        self.assertIn("1 provider file is missing because the fetch got a response it did not expect for it (HTTP 403)", text)
        self.assertIn("fetch it with", text)                              # the case's other files are simply not fetched yet

    def test_a_response_an_earlier_fetch_saved_in_the_datas_place_is_not_read(self):
        for body, status in ((HTML, 403), (b"No SupGP data found", 404), (b"<html>Internal Server Error</html>", 500)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                corpus_copy(tmp, [CASE])
                put(tmp, DATA_FILE, body, status)
                r = Runner(Reference(), root=tmp).run(case_ids=[CASE])[0]
                self.assertEqual({i.status for i in r.items}, {"not-fetched"}, [(i.check, i.status, i.detail[:80]) for i in r.items if i.status != "not-fetched"])
                (item,) = [i for i in r.items if i.file == DATA_FILE]
                self.assertIn(f"holds an HTTP {status} response that an earlier fetch saved in the data's place", item.detail)
                self.assertIn("where the corpus records HTTP 200: not provider data, and not read", item.detail)
                self.assertEqual(r.unexpected[DATA_FILE]["http_status"], status)

    def test_the_recorded_404_is_still_the_fixture(self):
        """The provider's no-data text where the corpus records a 404 is data: the empty answer a parser must handle."""
        with tempfile.TemporaryDirectory() as tmp:
            corpus_copy(tmp, [EMPTY_CASE])
            put(tmp, EMPTY_FILE, NO_DATA, 404)
            r = Runner(Reference(), root=tmp).run(case_ids=[EMPTY_CASE])[0]
        self.assertEqual(r.unexpected, {})
        mine = [i for i in r.items if i.file == EMPTY_FILE]
        self.assertTrue(mine)
        self.assertNotIn("not-fetched", {i.status for i in mine})
        self.assertNotIn("fail", {i.status for i in mine})


if __name__ == "__main__":
    unittest.main()
