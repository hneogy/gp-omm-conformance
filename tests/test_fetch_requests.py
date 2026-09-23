"""tools/fetch.py request logic, exercised without any request (D-119, audit item 10.14).

A raw file on disk without its .meta.json is not re-requested; a re-capture entry is requested only when its
original is on disk, was retrieved at least two hours earlier and was not requested in the same run; the two-hour
rule reads the recorded retrieved_at, not the file's mtime (a checkout or a sync rewrites mtimes); a run's exit
code reports stable drift; no URL is requested twice in one run. The fetch function is replaced by a stub that
records calls and never touches the network.

Run: python -m unittest tests.test_fetch_requests"""
import datetime as dt
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fetch  # noqa: E402

NOW = dt.datetime(2026, 9, 24, 12, 0, 0, tzinfo=dt.timezone.utc)
URL_A = "https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=TLE"
ENTRIES = [
    {"stage": "A", "case": "c", "file": "a.tle", "url": URL_A},
    {"stage": "E", "case": "c", "file": "a-recapture.tle", "url": URL_A.replace("FORMAT=TLE", "FORMAT=tle"), "recapture_of": "a.tle"},
    {"stage": "A", "case": "c", "file": "b.csv", "url": "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=CSV"},
]


class Stub:
    """Stands in for fetch_one: records the entries it was asked for and writes a file plus metadata."""

    def __init__(self, root):
        self.root, self.calls = root, []

    def __call__(self, entry, root=None):
        self.calls.append(entry["file"])
        d, path, meta = fetch.target_paths(entry, root=self.root)
        os.makedirs(d, exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"STUB")
        with open(meta, "w") as f:
            json.dump({"url": entry["url"], "retrieved_at": fetch.now_utc(), "sha256": hashlib.sha256(b"STUB").hexdigest()}, f)
        return "HTTP/1.1 200 OK, 4 bytes (stub)"


class _Root(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.stub = Stub(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, name, data=b"DATA", retrieved_at=None, mtime=None, meta=True):
        d = os.path.join(self.root, "fixtures", "c", "raw")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name)
        with open(p, "wb") as f:
            f.write(data)
        if meta:
            m = {"url": "", "sha256": hashlib.sha256(data).hexdigest()}
            if retrieved_at is not None:
                m["retrieved_at"] = retrieved_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            with open(p + ".meta.json", "w") as f:
                json.dump(m, f)
        if mtime is not None:
            os.utime(p, (mtime.timestamp(), mtime.timestamp()))
        return p

    def manifest(self, stable_sha):
        with open(os.path.join(self.root, "manifest.json"), "w") as f:
            json.dump({"cases": [{"id": "c", "sources": [{"path": "fixtures/c/raw/a.tle", "tier": "stable", "sha256": stable_sha}]}]}, f)

    def plan(self, entries=ENTRIES, **opts):
        return {p["entry"]["file"]: (p["action"], p["reason"]) for p in fetch.plan(entries, root=self.root, now=NOW, **opts)}

    def execute(self, argv, entries=ENTRIES):  # not 'run': unittest.TestCase.run is the framework's
        out = io.StringIO()
        rc = fetch.run(argv, root=self.root, entries=entries, now=NOW, fetch_one=self.stub, out=out, pause=0)
        return rc, out.getvalue()


class RawFileWithoutMetadata(_Root):
    def test_is_not_re_requested(self):
        self.put("a.tle", meta=False)
        plan = self.plan()
        self.assertEqual(plan["a.tle"][0], "cached")
        self.assertIn("metadata", plan["a.tle"][1])
        rc, out = self.execute([])
        self.assertEqual(self.stub.calls, ["b.csv"])
        self.assertIn("metadata", out)

    def test_force_falls_back_to_mtime_when_there_is_no_metadata(self):
        self.put("a.tle", meta=False, mtime=NOW - dt.timedelta(hours=3))
        self.assertEqual(self.plan(force=True)["a.tle"][0], "fetch")
        self.put("a.tle", meta=False, mtime=NOW - dt.timedelta(minutes=30))
        self.assertEqual(self.plan(force=True)["a.tle"][0], "cached")


class Recaptures(_Root):
    def test_fresh_checkout_requests_the_original_only(self):
        plan = self.plan(include_recaptures=True)
        self.assertEqual(plan["a.tle"][0], "fetch")
        self.assertEqual(plan["a-recapture.tle"][0], "skip")
        self.assertIn("original", plan["a-recapture.tle"][1])
        rc, out = self.execute(["--include-recaptures"])
        self.assertEqual(self.stub.calls, ["a.tle", "b.csv"])

    def test_requested_when_the_original_is_on_disk_and_two_hours_old(self):
        self.put("a.tle", retrieved_at=NOW - dt.timedelta(hours=3))
        self.assertEqual(self.plan(include_recaptures=True)["a-recapture.tle"][0], "fetch")
        rc, out = self.execute(["--include-recaptures"])
        self.assertEqual(self.stub.calls, ["a-recapture.tle", "b.csv"])

    def test_skipped_when_the_original_is_younger_than_two_hours(self):
        self.put("a.tle", retrieved_at=NOW - dt.timedelta(minutes=90))
        plan = self.plan(include_recaptures=True)
        self.assertEqual(plan["a-recapture.tle"][0], "skip")
        self.assertIn("two hours", plan["a-recapture.tle"][1])

    def test_never_requested_in_the_same_run_as_its_original(self):
        self.put("a.tle", retrieved_at=NOW - dt.timedelta(hours=5))
        plan = self.plan(include_recaptures=True, force=True)  # --force re-fetches the old original in this run
        self.assertEqual(plan["a.tle"][0], "fetch")
        self.assertEqual(plan["a-recapture.tle"][0], "skip")
        self.assertIn("this run", plan["a-recapture.tle"][1])
        rc, out = self.execute(["--include-recaptures", "--force"])
        self.assertEqual(self.stub.calls, ["a.tle", "b.csv"])

    def test_excluded_unless_asked_for(self):
        self.put("a.tle", retrieved_at=NOW - dt.timedelta(hours=3))
        self.assertNotIn("a-recapture.tle", self.plan())


class TwoHourRule(_Root):
    def test_force_reads_retrieved_at_not_mtime(self):
        self.put("a.tle", retrieved_at=NOW - dt.timedelta(minutes=30), mtime=NOW - dt.timedelta(days=2))
        plan = self.plan(force=True)
        self.assertEqual(plan["a.tle"][0], "cached")
        self.assertIn("retrieved", plan["a.tle"][1])
        self.put("a.tle", retrieved_at=NOW - dt.timedelta(hours=2, seconds=1), mtime=NOW)
        self.assertEqual(self.plan(force=True)["a.tle"][0], "fetch")

    def test_without_force_a_cached_file_is_never_requested(self):
        self.put("a.tle", retrieved_at=NOW - dt.timedelta(days=30))
        self.assertEqual(self.plan()["a.tle"][0], "cached")


class OneRequestPerUrl(_Root):
    def test_duplicate_urls_differing_in_case_are_refused(self):
        dupes = fetch.duplicate_urls(ENTRIES + [{"stage": "A", "case": "c", "file": "a2.tle", "url": URL_A.lower()}])
        self.assertEqual(dupes, [URL_A.lower()])
        self.assertEqual(fetch.duplicate_urls(ENTRIES), [])  # the re-capture is the permitted repeat
        rc, out = self.execute([], entries=ENTRIES + [{"stage": "A", "case": "c", "file": "a2.tle", "url": URL_A.lower()}])
        self.assertEqual(rc, 1)
        self.assertEqual(self.stub.calls, [])

    def test_dry_run_makes_no_request(self):
        rc, out = self.execute(["--dry-run", "--include-recaptures"])
        self.assertEqual(self.stub.calls, [])
        self.assertIn("FETCH", out)
        self.assertEqual(rc, 0)


class ExitCode(_Root):
    def test_stable_drift_after_a_run_is_exit_2(self):
        self.manifest(hashlib.sha256(b"SNAPSHOT").hexdigest())
        rc, out = self.execute(["--case", "c"])
        self.assertEqual(self.stub.calls, ["a.tle", "b.csv"])
        self.assertEqual(rc, 2, out)
        self.assertIn("DRIFT", out)

    def test_matching_snapshot_is_exit_0(self):
        self.manifest(hashlib.sha256(b"STUB").hexdigest())
        rc, out = self.execute([])
        self.assertEqual(rc, 0, out)


if __name__ == "__main__":
    unittest.main()
