"""A source file the reference reader cannot read must fail the case, not pass it vacuously (D-113).

Four reproductions from the audit of 2026-09-23: an HTML error body saved as a TLE file, a TLE cut off after
line 1, an empty KVN file and a BOM-prefixed KVN file. Each used to yield zero records, and zero records made
every per-file check pass. A 16-byte CelesTrak 404 body is the legitimate zero-record file and must stay ok."""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gpconf.runner import Runner, CaseResult  # noqa: E402
from gpconf.runner import sha256 as file_sha256  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402

GOOD_TLE = os.path.join(ROOT, "derived", "alpha5-tle", "alpha5-A-100000-saramago-first.tle")
GOOD_KVN = os.path.join(ROOT, "derived", "kvn-variants", "v01-baseline-reserialised.kvn")


class LoadSourceTests(unittest.TestCase):
    def setUp(self):
        self.runner = Runner(Reference(), root=ROOT)
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def load(self, name, data, src):
        path = os.path.join(self.tmp, name)
        with open(path, "wb") as f:
            f.write(data)
        res = CaseResult("scratch", "scratch")
        state, *_ = self.runner.load_source(res, {"id": "scratch", "checks": []}, path, src)
        return state, [i for i in res.items if i.status == "fail"]

    def bad_inputs(self):
        tle = open(GOOD_TLE, "rb").read()
        kvn = open(GOOD_KVN, "rb").read()
        return {
            "html.tle": (b"<!DOCTYPE html>\n<html><head><title>403 Forbidden</title></head><body>Forbidden</body></html>\n", "tle", ("HTML",)),
            "truncated.tle": (b"\n".join(tle.splitlines()[:2]) + b"\n", "tle", ("line 2", "truncated")),
            "empty.kvn": (b"", "kvn", ("empty",)),
            "bom.kvn": (b"\xef\xbb\xbf" + kvn, "kvn", ("BOM",)),
        }

    def test_zero_of_n_records_fails_with_a_description(self):
        for name, (data, fmt, words) in self.bad_inputs().items():
            with self.subTest(name):
                state, fails = self.load(name, data, {"format": fmt, "sha256": "0" * 64, "record_count": 1})
                if name == "bom.kvn":  # since D-117 the reader rejects a BOM outright, which is the clearer error
                    self.assertEqual(state, "parse-error")
                    self.assertEqual([i.check for i in fails], ["reference-reader"])
                    self.assertIn("BOM", fails[0].detail)
                    continue
                self.assertEqual(state, "unreadable")
                self.assertEqual([i.check for i in fails], ["source-readable"], fails)
                detail = fails[0].detail
                self.assertIn("0 of 1", detail)
                self.assertIn(f"{len(data)} bytes", detail)
                self.assertIn(repr(data[:16])[:12], detail)          # the first bytes are quoted
                for w in words:
                    self.assertIn(w, detail, detail)

    def test_the_404_body_is_a_legitimate_zero_record_file(self):
        body = b"No GP data found"
        src = {"format": "tle", "http_status": 404, "record_count": 0, "bytes": 16, "sha256": __import__("hashlib").sha256(body).hexdigest()}
        state, fails = self.load("saramago.tle", body, src)
        self.assertEqual((state, fails), ("empty-404", []))

    def test_a_readable_file_is_ok_and_a_live_file_is_not_count_checked(self):
        tle = open(GOOD_TLE, "rb").read()
        state, fails = self.load("good.tle", tle, {"format": "tle", "sha256": file_sha256(GOOD_TLE), "record_count": 1})
        self.assertEqual((state, fails), ("ok", []))
        two = tle + tle  # a live file (hash differs) with a different count than the frozen one: still ok
        state, fails = self.load("live.tle", two, {"format": "tle", "sha256": file_sha256(GOOD_TLE), "record_count": 1})
        self.assertEqual((state, fails), ("ok", []))

    def test_a_snapshot_file_with_the_wrong_recorded_count_is_an_internal_inconsistency(self):
        tle = open(GOOD_TLE, "rb").read()
        state, fails = self.load("good.tle", tle, {"format": "tle", "sha256": file_sha256(GOOD_TLE), "record_count": 5})
        self.assertEqual(state, "unreadable")
        self.assertIn("1 of 5", fails[0].detail)
        self.assertIn("matches the tested snapshot", fails[0].detail)


class CaseLevelTests(unittest.TestCase):
    """Through Runner.run on a scratch root holding one shipped case: an unreadable variant fails the case."""

    def scratch_root(self):
        d = tempfile.mkdtemp()
        m = json.load(open(os.path.join(ROOT, "manifest.json")))
        m["cases"] = [c for c in m["cases"] if c["id"] == "kvn-syntax-variants"]
        json.dump(m, open(os.path.join(d, "manifest.json"), "w"))
        os.makedirs(os.path.join(d, "fixtures", "kvn-syntax-variants"))
        shutil.copy(os.path.join(ROOT, "fixtures", "kvn-syntax-variants", "expected.json"), os.path.join(d, "fixtures", "kvn-syntax-variants"))
        shutil.copytree(os.path.join(ROOT, "derived", "kvn-variants"), os.path.join(d, "derived", "kvn-variants"))
        return d

    def test_an_empty_variant_fails_the_case_instead_of_passing_it(self):
        d = self.scratch_root()
        try:
            target = os.path.join(d, "derived", "kvn-variants", "v01-baseline-reserialised.kvn")
            open(target, "wb").close()
            r = Runner(Reference(), root=d).run(case_ids=["kvn-syntax-variants"])[0]
        finally:
            shutil.rmtree(d)
        self.assertEqual(r.status, "fail")
        rel = "derived/kvn-variants/v01-baseline-reserialised.kvn"
        fails = [i for i in r.items if i.status == "fail"]
        # the emptied file is a stable-tier source, so it is reported twice, correctly: as drift (D-115) and as unreadable
        self.assertEqual(sorted((i.check, i.file) for i in fails), [("source-readable", rel), ("stable-source-drift", rel)], fails)
        self.assertEqual([i for i in r.items if i.file == rel and i.detail.startswith("variant parsed")], [])
        self.assertTrue(any(i.status == "pass" and i.file and i.file.endswith("v02-day-of-year-epoch-Z.kvn") for i in r.items))


if __name__ == "__main__":
    unittest.main()
