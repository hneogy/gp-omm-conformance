# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Tests that pin survivors of the 0.9.0 mutation run, the owner's five priority tests, named by mutant number in
docs/handoff/mutation-survivors-0.9.0-triage.md (D-518): each passes on the code and fails
under its mutant.

Run: python -m unittest tests.test_triage_090_priority"""
import os
import sys
import tempfile
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import schema as S  # noqa: E402
from gpconf import tle  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import CaseResult, Runner, tle_side  # noqa: E402
from tests.test_type4 import Exact, run as run_type4  # noqa: E402

NAN = float("nan")


class NanBesideACode(Exact):
    """Answers each type-4 set with an error code and NaN arrays at every step, as python-sgp4 does for a set it
    cannot propagate; the type-0 twins propagate exactly."""

    def propagate(self, raw, fmt, tsince):
        if self.etype(raw, fmt) == 4:
            return [{"error": 6, "r": [NAN, NAN, NAN], "v": [NAN, NAN, NAN]} for _ in tsince]
        return Exact.propagate(self, raw, fmt, tsince)


class TypeFourNanArrays(unittest.TestCase):
    def test_a_code_beside_nan_arrays_at_every_step_is_no_position(self):
        """Kills 1367 (position: a NaN counted finite, so NaN arrays beside a code read as stamped positions)."""
        status, items = run_type4(NanBesideACode())
        self.assertEqual(items["type4-not-propagated"].status, "pass")
        self.assertIn("an SGP4 error code at every step", items["type4-not-propagated"].detail)
        self.assertEqual(status, "pass")


class TleSideEccentricityEdges(unittest.TestCase):
    def test_an_eccentricity_of_zero_is_held_as_zero(self):
        """Kills 305 (tle_side: 0 <= d made 0 < d, so an eccentricity of exactly 0 is a value no field holds)."""
        self.assertEqual(tle_side("eccentricity", "0"), Decimal("0"))
        self.assertEqual(tle_side("eccentricity", "0.0000000"), Decimal("0"))
        self.assertIsNone(tle_side("eccentricity", "1"))
        self.assertIsNone(tle_side("eccentricity", "-0.0000001"))


class TheCopyTag(unittest.TestCase):
    """compare_values tags a wrong value with '(copy i of n)' only where an id came back more than once or the input
    holds it more than once; an ordinary wrong value carries no tag."""

    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix="gpconf-triage-090-")
        self.addCleanup(d.cleanup)
        self.runner = Runner(Reference(), root=ROOT, data=d.name, fetch_hints=False)
        self.path = os.path.join(ROOT, "derived", "alpha5-tle", "alpha5-A-100000-saramago-first.tle")
        (self.rec,) = self.runner.parse(self.path, "tle")
        self.oracle = {100000: {k: v for k, v in self.rec.items() if not k.startswith("_")}}
        self.wrong = str(Decimal(str(self.rec["mean_motion"])) + 1)

    def values_item(self, parsed):
        res = CaseResult("x", "x")
        self.runner.compare_values(res, self.path, "tle", "live", parsed, self.oracle)
        (item,) = [i for i in res.items if i.check == "values"]
        return item

    def test_an_ordinary_wrong_value_carries_no_copy_tag(self):
        """Kills 619, 620, 621, 622 (compare_values: one copy of one record tagged ' (copy 1 of 1)')."""
        item = self.values_item([dict(self.rec, mean_motion=self.wrong)])
        self.assertEqual(item.status, "fail")
        self.assertIn("id 100000: mean_motion = ", item.detail)
        self.assertNotIn(" (copy ", item.detail)

    def test_a_wrong_value_on_a_surplus_copy_names_the_copy(self):
        """Kills 618 (compare_values: 'and' made 'or', so a surplus copy of a record held once loses its tag)."""
        item = self.values_item([self.rec, dict(self.rec, mean_motion=self.wrong)])
        self.assertEqual(item.status, "fail")
        self.assertIn("returned 2 times where the input holds it once (D-311)", item.detail)
        self.assertIn("mean_motion = ", item.detail)
        self.assertIn(" (copy 2 of 2)", item.detail)


class DayOfYearInACommonYear(unittest.TestCase):
    def test_day_366_of_a_common_year_is_refused(self):
        """Kills 1958 (iso_epoch: 'and' made 'or', so every year is a leap year and day 366 of 2023 reads as 2024-01-01)."""
        for text in ("2023-366T00:00:00", "1900-366T00:00:00", "2100-366T12:00:00Z"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    tle.iso_epoch(text)

    def test_day_366_of_a_leap_year_is_its_last_day(self):
        """The twin of the test above: day 366 is 31 December where the year has one."""
        self.assertEqual(tle.iso_epoch("2024-366T00:00:00"), "2024-12-31T00:00:00.000000")
        self.assertEqual(tle.iso_epoch("2000-366T00:00:00"), "2000-12-31T00:00:00.000000")


class TheValidatorsTypes(unittest.TestCase):
    def test_a_text_or_a_fraction_is_no_integer(self):
        """Kills 3370 (_is: 'and' made 'or', so anything not a bool is an integer)."""
        self.assertEqual(S.errors("3", {"type": "integer"}), ["$: str where integer is expected"])
        self.assertEqual(S.errors(1.5, {"type": "integer"}), ["$: float where integer is expected"])
        self.assertEqual(S.errors(3, {"type": "integer"}), [])

    def test_a_text_is_no_number(self):
        """Kills 3373 (_is: 'and' made 'or', so anything not a bool is a number)."""
        self.assertEqual(S.errors("x", {"type": "number"}), ["$: str where number is expected"])
        self.assertEqual(S.errors(True, {"type": "number"}), ["$: bool where number is expected"])

    def test_a_float_is_a_number(self):
        """Kills 3374 (_is: 'not' dropped, so only a bool is a number)."""
        self.assertEqual(S.errors(1.5e-9, {"type": "number"}), [])
        self.assertEqual(S.errors(2, {"type": "number"}), [])

    def test_a_number_without_a_minimum_is_checked_against_none(self):
        """Kills 3389 (errors: 'minimum' in schema made 'not in', so a number with no minimum raises KeyError)."""
        self.assertEqual(S.errors(0.5, {"type": "number"}), [])

    def test_a_count_below_zero_is_said(self):
        """Kills 3389 (errors: with 'not in' a schema's minimum is never read) and 3370 (a text count passes)."""
        count = S.load_schema()["$defs"]["count"]
        faults = S.errors(-1, count)
        self.assertEqual(len(faults), 1)
        self.assertIn("below 0", faults[0])
        self.assertEqual(S.errors(0, count), [])
        self.assertEqual(S.errors("0", count), ["$: str where integer is expected"])

    def test_an_item_with_tolerance_stats_matches(self):
        """Kills 3374 and 3389 (a pass-tolerance item's mean_signed and max_abs are floats against schemas with no
        minimum): no report the suite validates carries one."""
        schema = S.load_schema()
        item = {"check": "values", "status": "pass-tolerance", "file": "x.tle", "detail": "1 record matches",
                "tolerance_stats": {"mean_motion": {"n": 1, "mean_signed": 1e-9, "max_abs": 2e-9}}}
        self.assertEqual(S.errors(item, schema["$defs"]["item"], schema), [])
        bad = {"check": "values", "status": "pass-tolerance", "file": "x.tle", "detail": "1 record matches",
               "tolerance_stats": {"mean_motion": {"n": "1", "mean_signed": "x", "max_abs": 2e-9}}}
        self.assertEqual(len(S.errors(bad, schema["$defs"]["item"], schema)), 2)


if __name__ == "__main__":
    unittest.main()
