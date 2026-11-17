# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""A refused TLE member is not compared with the OMM set (S1 of blind pass D, D-565): its two count items are
not-exercised, where they passed on "TLE has 0 records" (or failed, beside ids below 100000). The case still fails on
the file's own item.

Run: python -m unittest tests.adversarial.test_refused_tle_member_091"""
import csv
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
TWINS_CSV = os.path.join(ROOT, "derived", "propagation-twins", "twins.csv")
CHECKS = ("tle-format-omits-ids-above-99999", "tle-count-equals-omm-count-below-100000")
HTML = b"<!DOCTYPE html>\n<html><head><title>502 Bad Gateway</title></head><body>Bad Gateway</body></html>\n"


class NoTleReader(Reference):
    """Raises on every TLE file: the runner records a parse error for it."""
    def parse(self, raw, fmt):
        if fmt in ("tle", "2le", "3le"):
            raise ValueError("this parser cannot read TLE")
        return super().parse(raw, fmt)


class ARefusedTleMemberIsNotCompared(unittest.TestCase):
    def setUp(self):
        self.data = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.data, RAW))

    def tearDown(self):
        shutil.rmtree(self.data)

    def omm(self, with_five_digit):
        with open(TWINS_CSV, encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))
        col = rows[0].index("NORAD_CAT_ID")
        kept = [rows[0]] + [r for r in rows[1:] if with_five_digit or int(r[col]) >= 100000]
        with open(os.path.join(self.data, RAW, "last-30-days.csv"), "w", encoding="utf-8", newline="") as f:
            csv.writer(f, lineterminator="\r\n").writerows(kept)

    def tle(self, data):
        with open(os.path.join(self.data, RAW, "last-30-days.tle"), "wb") as f:
            f.write(data)

    def run_case(self, parser=None):
        r = Runner(parser or Reference(), root=ROOT, data=self.data, fetch_hints=False).run(case_ids=[CASE])[0]
        return r, [i for i in r.items if i.check in CHECKS and i.file == "last-30-days"]

    def test_an_unreadable_tle_member(self):
        for five in (False, True):
            with self.subTest(with_five_digit_ids=five):
                self.omm(five)
                self.tle(HTML)
                r, items = self.run_case()
                self.assertEqual(sorted(i.check for i in items), sorted(CHECKS), items)
                self.assertTrue(all(i.status == "not-exercised" and i.cause == "data" for i in items), items)
                self.assertIn("was not read (unreadable", items[0].detail)
                self.assertTrue(any(i.status == "fail" and i.check == "source-readable" for i in r.items), r.items)   # the case still fails
                self.assertEqual(r.status, "fail")

    def test_a_tle_member_the_parser_could_not_read_stays_graded(self):
        # a parse error is the parser's: its member's items stay graded, as in 0.9.0 (D-144, D-345); only a file the
        # runner refused is not compared (D-565)
        self.omm(True)
        with open(os.path.join(ROOT, "derived", "propagation-twins", "twins.tle"), "rb") as f:
            self.tle(f.read())
        r, items = self.run_case(NoTleReader())
        self.assertTrue(items and all(i.status == "fail" for i in items), [(i.status, i.detail) for i in items])
        self.assertEqual(r.status, "fail")

    def test_a_tle_member_the_reference_reader_rejected_is_not_compared(self):
        # the blind reader's D1 (D-570): the reference reader's own rejection is a parse-error with no reference records;
        # no parser read the file, so it is not compared (it passed on "TLE has 0 records", or failed beside five-digit ids)
        with open(os.path.join(ROOT, "derived", "propagation-twins", "twins.tle"), "rb") as f:
            good = f.read()
        line1 = next(l for l in good.splitlines(keepends=True) if l.startswith(b"1 "))   # a line 1 with no line 2
        for five in (False, True):
            with self.subTest(with_five_digit_ids=five):
                self.omm(five)
                self.tle(good + line1)
                r, items = self.run_case()
                self.assertTrue(items and all(i.status == "not-exercised" for i in items), [(i.status, i.detail) for i in items])
                self.assertIn("rejected by the reference reader", items[0].detail)
                self.assertEqual(r.status, "fail")

    def test_a_readable_tle_member_is_compared_as_before(self):
        self.omm(False)
        self.tle(b"No GP data found")
        _, items = self.run_case()
        self.assertTrue(items and all(i.status == "pass" for i in items), items)


if __name__ == "__main__":
    unittest.main()
