# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""A .meta.json whose http_status is not an integer is not read (S3 of blind pass D, D-567): "404" gave a
self-contradicting message, and 404.0 passed as 404. No gpconf fetch writes either.

Run: python -m unittest tests.adversarial.test_meta_status_type_091"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from gpconf.runner import Runner  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402

CASE = "tle-omits-six-digit-objects"
RAW = os.path.join("fixtures", CASE, "raw")
TLE = os.path.join(RAW, "last-30-days.tle")


class AStatusThatIsNotAnInteger(unittest.TestCase):
    def setUp(self):
        self.data = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.data, RAW))
        with open(os.path.join(self.data, TLE), "wb") as f:
            f.write(b"No GP data found")

    def tearDown(self):
        shutil.rmtree(self.data)

    def items(self, status):
        with open(os.path.join(self.data, TLE + ".meta.json"), "w", encoding="utf-8") as f:
            json.dump({"http_status": status, "provenance": "live", "retrieved_at": "2026-09-21T00:10:10Z"}, f)
        r = Runner(Reference(), root=ROOT, data=self.data, fetch_hints=False).run(case_ids=[CASE])[0]
        return [i for i in r.items if i.file == TLE.replace(os.sep, "/") and i.check == "source-present"]

    def test_a_string_a_float_a_list_or_a_boolean_is_not_read(self):
        for bad in ("404", 404.0, [404], True, "200"):
            with self.subTest(status=bad):
                items = self.items(bad)
                self.assertEqual(len(items), 1, items)
                self.assertEqual(items[0].status, "not-fetched")
                self.assertIn(f"gives http_status {bad!r}, not an integer status", items[0].detail)
                self.assertNotIn("where the corpus records", items[0].detail)   # the old self-contradiction

    def test_the_satcat_reader_refuses_a_non_integer_status_too(self):
        # the blind reader's S1 (D-570): the SATCAT path had no test; 200.0 was read as SATCAT data
        import shutil as sh
        case, rel = "satcat-70000-cutoff", os.path.join("fixtures", "satcat-70000-cutoff", "raw", "satcat-25544.json")
        os.makedirs(os.path.join(self.data, os.path.dirname(rel)), exist_ok=True)
        with open(os.path.join(self.data, rel), "w", encoding="utf-8") as f:
            f.write("[]")
        for bad in (200.0, "200", True):
            with self.subTest(status=bad):
                with open(os.path.join(self.data, rel + ".meta.json"), "w", encoding="utf-8") as f:
                    json.dump({"http_status": bad, "provenance": "live", "retrieved_at": "2026-09-21T00:10:10Z"}, f)
                r = Runner(Reference(), root=ROOT, data=self.data, fetch_hints=False).run(case_ids=[case])[0]
                hits = [i for i in r.items if i.file == rel.replace(os.sep, "/") and i.check == "source-present"]
                self.assertEqual([i.status for i in hits], ["not-fetched"], [(i.check, i.status, i.detail) for i in r.items if i.file == rel.replace(os.sep, "/")])
                self.assertIn(f"gives http_status {bad!r}, not an integer status", hits[0].detail)

    def test_the_integer_404_is_still_read(self):
        # no source-present item is raised for a file that is present and read; beside an OMM set, the case's count
        # items are graded
        shutil.copy(os.path.join(ROOT, "derived", "propagation-twins", "twins.csv"), os.path.join(self.data, RAW, "last-30-days.csv"))
        self.assertEqual(self.items(404), [])
        r = Runner(Reference(), root=ROOT, data=self.data, fetch_hints=False).run(case_ids=[CASE])[0]
        counts = [i for i in r.items if i.check == "tle-count-equals-omm-count-below-100000"]
        self.assertTrue(counts, r.items)
        self.assertFalse(any("not an integer status" in (i.detail or "") for i in r.items))


if __name__ == "__main__":
    unittest.main()
