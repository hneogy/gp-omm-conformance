# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""CelesTrak's no-data TLE answer beside an OMM set holding ids below 100000 is compared only when the two were
fetched together (D-543; blind pass D's WV-1, a correct situation graded wrong).

`tle-omits-six-digit-objects` failed the reference adapter on CelesTrak's exact 16-byte answer whenever that file's
.meta.json did not say the fetch wrote it from the corpus's record: no meta at all, or the "live" meta of a data folder
fetched before 0.6.0, which a later fetch keeps. With the recorded meta the same bytes were not compared. An answer
from another time is no evidence about today's OMM set, and the parser is not to blame.

Run: python -m unittest tests.adversarial.test_set_relations_404_090"""
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
TWINS_CSV = os.path.join(ROOT, "derived", "propagation-twins", "twins.csv")   # ids 25544, 20453, 69999 and four above 99999
CHECKS = ("tle-format-omits-ids-above-99999", "tle-count-equals-omm-count-below-100000")


class TheNoDataAnswerBesideFiveDigitIds(unittest.TestCase):
    def setUp(self):
        self.data = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.data, RAW))
        shutil.copy(TWINS_CSV, os.path.join(self.data, RAW, "last-30-days.csv"))
        with open(os.path.join(self.data, RAW, "last-30-days.tle"), "wb") as f:
            f.write(b"No GP data found")

    def tearDown(self):
        shutil.rmtree(self.data)

    def meta(self, name, **fields):
        with open(os.path.join(self.data, RAW, name + ".meta.json"), "w", encoding="utf-8") as f:
            json.dump(fields, f)

    def items(self):
        r = Runner(Reference(), root=ROOT, data=self.data, fetch_hints=False).run(case_ids=[CASE])[0]
        return r, [i for i in r.items if i.check in CHECKS and i.file == "last-30-days"]

    def assert_not_compared(self):
        r, items = self.items()
        self.assertEqual(sorted(i.check for i in items), sorted(CHECKS), items)
        self.assertTrue(all(i.status == "not-exercised" for i in items), items)
        self.assertFalse(any(i.status == "fail" for i in r.items if i.check in CHECKS), r.items)
        return items

    def test_with_no_meta_the_answer_is_not_compared(self):
        items = self.assert_not_compared()
        for i in items:   # every item, not the first only (the blind reader of D-543)
            self.assertIn("the metadata does not show it was fetched with the OMM set", i.detail)

    def test_a_pre_060_live_meta_is_not_compared(self):
        self.meta("last-30-days.tle", http_status=404, provenance="live", retrieved_at="2026-09-21T00:10:10Z",
                  url="https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=TLE")
        self.meta("last-30-days.csv", http_status=200, provenance="live", retrieved_at="2026-11-14T12:00:00Z")
        self.assert_not_compared()

    def test_the_recorded_meta_is_not_compared_as_before(self):
        self.meta("last-30-days.tle", http_status=404, provenance="recorded", retrieved_at="2026-09-21T00:10:10Z",
                  recorded={"file": "recorded/celestrak-no-gp-data-found.txt", "captured_at": "2026-09-21T00:10:10Z"})
        _, items = self.items()
        self.assertTrue(items and all(i.status == "not-exercised" for i in items), items)
        self.assertIn("the corpus's record of the TLE answer", items[0].detail)

    def test_answers_fetched_together_are_compared_and_fail(self):
        # the TLE request said no data while the OMM set fetched with it holds ids the TLE format carries: a real
        # disagreement of the provider's two answers, which the case reports
        self.meta("last-30-days.tle", http_status=404, provenance="live", retrieved_at="2026-11-14T12:00:05Z")
        self.meta("last-30-days.csv", http_status=200, provenance="live", retrieved_at="2026-11-14T12:00:00Z")
        _, items = self.items()
        self.assertTrue(items and all(i.status == "fail" for i in items), items)
        self.assertIn("TLE request returned 'No GP data found'; OMM set has 3 ids below 100000", items[0].detail)

    def test_with_no_id_below_100000_the_answer_passes_as_before(self):
        import csv
        with open(TWINS_CSV, encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))
        col = rows[0].index("NORAD_CAT_ID")
        kept = [rows[0]] + [r for r in rows[1:] if int(r[col]) >= 100000]
        with open(os.path.join(self.data, RAW, "last-30-days.csv"), "w", encoding="utf-8", newline="") as f:
            csv.writer(f, lineterminator="\r\n").writerows(kept)
        _, items = self.items()
        self.assertTrue(items and all(i.status == "pass" for i in items), items)



class Truncating(Reference):
    """Wrong on purpose: reads a six-digit catalog number as its last five digits."""
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        for r in out:
            if isinstance(r.get("norad_cat_id"), int) and r["norad_cat_id"] >= 100000:
                r["norad_cat_id"] %= 100000
        return out


class TheBlindReadersCases(TheNoDataAnswerBesideFiveDigitIds):
    """D-564 (the blind reader of D-543): whether the OMM set disagrees with the TLE answer is decided from the input,
    not from the parser's ids; the window is one run's, not two hours."""
    def only_six_digit(self):
        import csv
        with open(TWINS_CSV, encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))
        col = rows[0].index("NORAD_CAT_ID")
        kept = [rows[0]] + [r for r in rows[1:] if int(r[col]) >= 100000]
        with open(os.path.join(self.data, RAW, "last-30-days.csv"), "w", encoding="utf-8", newline="") as f:
            csv.writer(f, lineterminator="\r\n").writerows(kept)

    def items_with(self, parser):
        r = Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=[CASE])[0]
        return [i for i in r.items if i.check in CHECKS and i.file == "last-30-days"]

    def test_a_parser_mangling_six_digit_ids_fails_with_no_meta(self):
        self.only_six_digit()
        items = self.items_with(Truncating())
        self.assertTrue(items and all(i.status == "fail" for i in items), items)

    def test_a_parser_mangling_six_digit_ids_fails_beside_the_recorded_answer(self):
        # in 0.9.0 this was not-exercised: the recorded branch looked at the parser's ids (the reader's F1, "older and wider")
        self.only_six_digit()
        self.meta("last-30-days.tle", http_status=404, provenance="recorded", retrieved_at="2026-09-21T00:10:10Z",
                  recorded={"file": "recorded/celestrak-no-gp-data-found.txt", "captured_at": "2026-09-21T00:10:10Z"})
        items = self.items_with(Truncating())
        self.assertTrue(items and all(i.status == "fail" for i in items), items)
        self.assertTrue(all(i.status == "pass" for i in self.items_with(Reference())), self.items_with(Reference()))

    def window(self, seconds, **csv_meta):
        self.meta("last-30-days.tle", http_status=404, provenance="live", retrieved_at="2026-11-14T12:00:00Z")
        when = __import__("datetime").datetime(2026, 11, 14, 12, 0, 0) + __import__("datetime").timedelta(seconds=seconds)
        self.meta("last-30-days.csv", **dict({"http_status": 200, "provenance": "live", "retrieved_at": when.strftime("%Y-%m-%dT%H:%M:%SZ")}, **csv_meta))
        return {i.status for i in self.items()[1]}

    def test_the_window_is_one_runs(self):
        self.assertEqual(self.window(899), {"fail"})            # fetched together: a real disagreement
        self.assertEqual(self.window(900), {"not-exercised"})   # fifteen minutes or more: not the same run
        self.assertEqual(self.window(7200), {"not-exercised"})  # the refetch age, which the reader showed was inside the old window

    def test_a_missing_csv_meta_beside_a_live_tle_meta(self):
        self.meta("last-30-days.tle", http_status=404, provenance="live", retrieved_at="2026-11-14T12:00:00Z")
        self.assert_not_compared()

    def test_a_malformed_or_non_string_time(self):
        for bad in ("2026-11-14 12:00:00", "2026-11-14T12:00:00+00:00", 1794700000, None):
            with self.subTest(bad=bad):
                self.assertEqual(self.window(1, retrieved_at=bad), {"not-exercised"})

    def test_no_provenance_on_either_counts_as_live(self):
        self.meta("last-30-days.tle", http_status=404, retrieved_at="2026-11-14T12:00:00Z")
        self.meta("last-30-days.csv", http_status=200, retrieved_at="2026-11-14T12:00:01Z")
        self.assertEqual({i.status for i in self.items()[1]}, {"fail"})


if __name__ == "__main__":
    unittest.main()
