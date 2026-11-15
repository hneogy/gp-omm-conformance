# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""SM-26's round two (issue #1, comment 6583242093, 2026-11-02): the wrong-on-purpose adapters of
`sm26_wrong2.py` and `sm26_wrong3.py`, each the reference parser with one bug, held to the cases they got through on
gpconf 0.8.0, and their twins, which 0.8.0 already caught, held to still failing. Credited to SM-26 (D-380).

Second 60 (D-382): L1 read :60 in any minute and L2 took 23:59:60 on any 30 June or 31 December; both passed every
case, the first because the reference adapter itself did so, and both now fail the epoch vectors. L2's twin, the 27
real leap seconds only, passes: a correct table costs nothing.

Run: python -m unittest tests.adversarial.test_sm26_round2_090"""
import datetime as dt
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf import tle as tlemod  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from tests.adversarial import sm26_wrong2 as w2, sm26_wrong3 as w3  # noqa: E402
from tests.adversarial.test_adversarial import NO_DATA, failing, run  # noqa: E402

VECTORS = "alpha5-encoding-vectors"


class SecondSixty(unittest.TestCase):
    """R4 and R5 (D-382)."""

    def test_any_minute_fails_the_vectors(self):
        self.assertEqual(failing(run(w3.L1AnyMinute60())), [VECTORS])

    def test_any_30_june_or_31_december_fails_the_vectors(self):
        self.assertEqual(failing(run(w3.L2CalendarLeapSeconds())), [VECTORS])

    def test_the_27_leap_seconds_alone_pass(self):
        self.assertEqual(failing(run(w3.L2CalendarLeapSecondsTwin())), [])

    def test_refusing_every_second_60_still_fails(self):
        self.assertEqual(failing(run(w3.L1AnyMinute60Twin())), [VECTORS])

    def test_the_reference_passes(self):
        self.assertEqual(failing(run(Reference())), [])

    def test_the_table_is_sm26s_27(self):
        # two independent copies: SM-26's, typed from IERS, and the runner's (D-382)
        self.assertEqual(len(tlemod.LEAP_SECOND_DATES), 27)
        self.assertEqual({d.isoformat() for d in tlemod.LEAP_SECOND_DATES}, w3.LEAP_DATES)

    def test_both_readers_take_each_leap_second_and_no_other_end_of_half_year(self):
        ref = Reference()
        for year in range(1960, 2031):
            for month, day in ((6, 30), (12, 31)):
                d = dt.date(year, month, day)
                for text in (f"{d.isoformat()}T23:59:60", f"{year}-{d.timetuple().tm_yday:03d}T23:59:60.5Z"):
                    with self.subTest(text=text):
                        if d in tlemod.LEAP_SECOND_DATES:
                            self.assertEqual(tlemod.iso_epoch(text)[:19], f"{d.isoformat()}T23:59:59")
                            self.assertEqual(ref.parse_epoch(text).date(), d)
                        else:
                            self.assertRaises(ValueError, tlemod.iso_epoch, text)
                            self.assertRaises(ValueError, ref.parse_epoch, text)

    def test_second_60_in_another_minute_of_a_leap_second_date(self):
        for text in ("2016-12-31T23:58:60", "2016-12-31T22:59:60", "2016-12-31T00:00:60", "2017-01-01T00:00:60"):
            with self.subTest(text=text):
                self.assertRaises(ValueError, tlemod.iso_epoch, text)
                self.assertRaises(ValueError, Reference().parse_epoch, text)

    def test_an_offset_is_read_in_utc_first(self):
        # 00:59:60+01:00 is 23:59:60 UTC; 23:59:60+01:00 is 22:59:60 UTC, not a leap second
        self.assertEqual(tlemod.iso_epoch("2017-01-01T00:59:60+01:00"), "2016-12-31T23:59:59.000000")
        self.assertRaises(ValueError, tlemod.iso_epoch, "2016-12-31T23:59:60+01:00")


def second_60(allowed):
    """The reference parser, but second 60 read as 59 wherever allowed(datetime read as :59) says so."""
    import re

    class Wrong(Reference):
        def parse_epoch(self, text):
            m = re.fullmatch(r"(.*T\d{2}:\d{2}:)60(\.\d+)?(Z?)", text)
            if not m:
                return Reference.parse_epoch(self, text)
            t = Reference.parse_epoch(self, m.group(1) + "59" + (m.group(2) or "") + m.group(3))
            if allowed(t):
                return t
            raise ValueError(text)
    return Wrong


# a command that is the reference for every hook, but answers parse_epoch's second 60 in any minute with the second 60
# kept: the runner's own reader refused that answer, and the refusal was credited to the command (the review's F1)
KEEPS_60 = r"""
import json, re, sys
sys.path.insert(0, sys.argv[1])
from gpconf.adapters.reference import Parser
q = json.load(sys.stdin); op, x = q["op"], q["input"]
try:
    if op == "parse_epoch" and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:60(\.\d+)?Z?", x):
        out = x.rstrip("Z")
    else:
        out = getattr(Parser(), op)(x)
        out = out.isoformat(timespec="microseconds") if op == "parse_epoch" else out
    print(json.dumps({"result": out}))
except Exception as e:
    print(json.dumps({"error": str(e)}))
"""


class TheSeparateReview(unittest.TestCase):
    """What the separate review of D-382 found still passing (2026-11-05): each fails now."""

    def vectors_item(self, parser):
        (r,) = run(parser, [VECTORS])
        (it,) = [i for i in r.items if i.check == "ccsds-epoch-strings"]
        return it

    def test_a_command_that_keeps_second_60_in_its_answer(self):
        import sys as _sys
        from gpconf.runner import CommandParser
        it = self.vectors_item(CommandParser(None, vectors_cmd=[_sys.executable, "-c", KEEPS_60, ROOT]))
        self.assertEqual(it.status, "fail")
        self.assertIn("'2026-09-20T12:42:60' accepted", it.detail)

    def test_the_twin_command_the_reference_passes(self):
        import sys as _sys
        from gpconf.runner import CommandParser
        ref = KEEPS_60.replace('re.fullmatch(r"\\d{4}', 'False and re.fullmatch(r"\\d{4}')
        self.assertNotEqual(ref, KEEPS_60)
        self.assertEqual(self.vectors_item(CommandParser(None, vectors_cmd=[_sys.executable, "-c", ref, ROOT])).status, "pass")

    def test_wrong_tables_fail(self):
        wrong = {"any minute, fraction or Z": lambda t: True,
                 "any minute of a leap-second date": lambda t: t.date() in tlemod.LEAP_SECOND_DATES,
                 "every 31 December from 1972 to 2016, and the real 30 Junes":
                     lambda t: (t.hour, t.minute) == (23, 59) and (t.date() in tlemod.LEAP_SECOND_DATES
                                                                   or ((t.month, t.day) == (12, 31) and 1972 <= t.year <= 2016)),
                 "only the last leap second": lambda t: (t.date(), t.hour, t.minute) == (dt.date(2016, 12, 31), 23, 59)}
        for name, allowed in wrong.items():
            with self.subTest(name):
                self.assertEqual(self.vectors_item(second_60(allowed)()).status, "fail")
        with self.subTest("the twin: the 27, at 23:59"):
            self.assertEqual(self.vectors_item(second_60(tlemod.is_leap_second)()).status, "pass")


def writes(change):
    """The reference writer, with change(record) applied to a copy of each record before it is written."""
    class Writer(Reference):
        def write_tle(self, record):
            r = dict(record)
            change(r)
            return Reference.write_tle(self, r)
    return Writer


class SideFields(unittest.TestCase):
    """R1 (D-381, the owner's ruling; D-383): a side field may be zeroed or left out as documented, but any other
    value must be the record's, or the writer case fails."""

    def side_item(self, parser):
        (r,) = run(parser, ["tle-writer-alpha5"])
        (it,) = [i for i in r.items if i.check == "tle-writer-secondary-not-changed"]
        return r, it

    def test_w1_and_w4_fail(self):
        for a, field in ((w2.W1NdotDoubled, "mean_motion_dot"), (w2.W4ObjectId, "object_id")):
            with self.subTest(a.__name__):
                r, it = self.side_item(a())
                self.assertEqual(r.status, "fail")
                self.assertEqual(it.status, "fail")
                self.assertIn(field, it.detail)

    def test_the_reference_passes(self):
        r, it = self.side_item(Reference())
        self.assertEqual((r.status, it.status), ("pass", "pass"))

    def test_zeroed_or_left_out_as_documented_passes(self):
        def zero(r):
            r.update(mean_motion_dot="0", mean_motion_ddot="0", element_set_no=0, rev_at_epoch=0)

        def drop(r):
            r.update(object_id=None)
        for name, change in (("zeroed", zero), ("designator left out", drop)):
            with self.subTest(name):
                self.assertEqual(self.side_item(writes(change)())[1].status, "pass")

    def test_each_other_value_fails(self):
        changes = {"element_set_no": lambda r: r.update(element_set_no=(r.get("element_set_no") or 0) % 998 + 1),
                   "rev_at_epoch": lambda r: r.update(rev_at_epoch=(r.get("rev_at_epoch") or 0) % 99998 + 1),
                   "mean_motion_ddot": lambda r: r.update(mean_motion_ddot="0.00012345"),
                   "classification_type": lambda r: r.update(classification_type="C")}
        for field, change in changes.items():
            with self.subTest(field):
                it = self.side_item(writes(change)())[1]
                self.assertEqual(it.status, "fail")
                self.assertIn(field, it.detail)


def edits(name_line=None, designator=None, without_id_only=False):
    """The reference writer, its lines then edited: the name line made name_line(name), line 1's designator columns
    set to designator (on the records that hold one, or with without_id_only on those that hold none), the checksum
    written again."""
    class Writer(Reference):
        def write_tle(self, record):
            out = Reference.write_tle(self, record)
            l0, l1, l2 = out if len(out) == 3 else (None, *out)
            if designator is not None and bool(record.get("object_id")) != without_id_only:
                l1 = l1[:9] + designator + l1[17:68]
                l1 += str(tlemod.checksum(l1))
            if name_line is not None:
                l0 = name_line(l0 or "")
            return [l1, l2] if l0 is None else [l0, l1, l2]
    return Writer


class SideFieldsTheReview(unittest.TestCase):
    """The separate review of D-383 (2026-11-05): an unreadable designator passed as left out; Space-Track's "0 " name
    prefix and an empty name line failed a correct writer; a number past its columns, written modulo, was "changed"."""

    def side(self, parser):
        (r,) = run(parser, ["tle-writer-alpha5"])
        return [i for i in r.items if i.check == "tle-writer-secondary-not-changed"][0]

    def test_an_unreadable_designator_is_another_value(self):
        for field in ("XXXXXXXX", "UNKNOWN ", " 8067A  "):
            with self.subTest(field=field):
                it = self.side(edits(designator=field)())
                self.assertEqual(it.status, "fail")
                self.assertIn("object_id", it.detail)
        for field in ("XXXXXXXX", "UNKNOWN ", "98067A  "):
            with self.subTest(field=field, record="no OBJECT_ID"):   # the second reading: None == None passed
                it = self.side(edits(designator=field, without_id_only=True)())
                self.assertEqual(it.status, "fail")
                self.assertIn("object_id", it.detail)
        with self.subTest("the twin: blank columns, left out"):
            self.assertEqual(self.side(edits(designator=" " * 8)()).status, "pass")

    def test_the_name_in_space_tracks_form_or_empty_passes(self):
        for name, line in (("0 prefix", lambda l0: "0 " + l0 if l0 else l0), ("empty", lambda l0: "")):
            with self.subTest(name):
                self.assertEqual(self.side(edits(name_line=line)()).status, "pass")
        with self.subTest("the twin: another name"):
            it = self.side(edits(name_line=lambda l0: (l0 + "X") if l0 else l0)())
            self.assertEqual(it.status, "fail")
            self.assertIn("object_name", it.detail)

    def test_a_number_past_its_columns_written_modulo(self):
        from gpconf import writer as W
        rec = {"norad_cat_id": 25544, "object_name": "ISS (ZARYA)", "object_id": "1998-067A", "epoch": "2026-09-20T12:42:37.141056",
               "mean_motion": "15.5", "eccentricity": "0.0001", "inclination": "51.6", "ra_of_asc_node": "10",
               "arg_of_pericenter": "10", "mean_anomaly": "10", "bstar": "0.0001", "mean_motion_dot": "0",
               "mean_motion_ddot": "0", "ephemeris_type": 0, "classification_type": "U", "element_set_no": 12345,
               "rev_at_epoch": 123456}
        l0, l1, l2 = tlemod.render(tlemod.omm_fields_from_record(dict(rec, element_set_no=2345, rev_at_epoch=23456)),
                                   mantissa_mode="round", ecc_mode="truncate")
        s = W.secondary_fields(l0, l1, l2, rec)
        self.assertEqual((s["element_set_no"], s["rev_at_epoch"]), ("preserved", "preserved"))
        s = W.secondary_fields(l0, l1, l2, dict(rec, element_set_no=2346, rev_at_epoch=123457))
        self.assertEqual((s["element_set_no"], s["rev_at_epoch"]), ("changed", "changed"))


class DayThreeSixtySix(unittest.TestCase):
    """R3 (D-384): day 366 reached no reader but through one epoch vector, so a reader whose day of year stops at 365
    (SM-26's E1) failed the vectors alone. Five synthetic-derived TLE sets and five OMM messages on 31 December of a
    leap year now carry it through the parse path."""

    def test_e1_fails_the_derived_tle_and_the_kvn_case(self):
        failed = failing(run(w2.E1NoDay366()))
        for case in (VECTORS, "alpha5-tle-derived", "kvn-syntax-variants"):
            with self.subTest(case):
                self.assertIn(case, failed)

    def test_the_new_files_hold_day_366(self):
        with open(os.path.join(ROOT, "derived", "alpha5-tle", "alpha5-synthetic-day-366.tle"), encoding="utf-8") as f:
            epochs = [l[18:23] for l in f.read().splitlines() if l.startswith("1 ")]
        self.assertEqual(epochs, ["60366", "96366", "00366", "24366", "56366"])
        with open(os.path.join(ROOT, "derived", "kvn-variants", "v08-synthetic-epochs.kvn"), encoding="utf-8") as f:
            kvn = f.read()
        for e in ("1960-12-31T", "1996-366T", "2000-12-31T", "2024-366T", "2056-12-31T"):
            self.assertIn(f"= {e}", kvn)


class PastTwentyThirtyEight(unittest.TestCase):
    """R6 (D-385): no epoch vector went past 2026 or before 1972, so a 32-bit time_t wrap in the epoch hook alone passed
    (SM-26's Y1 failed only through the synthetic TLE years on 0.8.0). Vectors at and past 2038-01-19T03:14:07 and one
    in 1960 now hold the hook; the OMM path was held already by D-384's 2056 and 1960 messages, and three messages at
    the boundary join them."""

    class HookOnly(Reference):
        def parse_epoch(self, text):
            return w3.wrap32(Reference.parse_epoch(self, text))

    class OmmOnly(w3.Y1Wrap2038):
        def parse(self, raw, fmt):
            return w3.Y1Wrap2038.parse(self, raw, fmt) if fmt not in ("tle", "2le") else Reference.parse(self, raw, fmt)

        def parse_epoch(self, text):
            return Reference.parse_epoch(self, text)

    def test_y1_fails_the_vectors_the_tle_and_the_kvn_case(self):
        failed = failing(run(w3.Y1Wrap2038()))
        for case in (VECTORS, "alpha5-tle-derived", "kvn-syntax-variants"):
            with self.subTest(case):
                self.assertIn(case, failed)

    def test_the_wrap_in_the_hook_alone_fails_the_vectors(self):
        self.assertEqual(failing(run(self.HookOnly())), [VECTORS])

    def test_an_unsigned_wrap_in_the_hook_fails_the_vectors(self):
        class Unsigned(Reference):   # the separate review: wrapping only before 1970 (or after 2106) passed every case
            def parse_epoch(self, text):
                t = Reference.parse_epoch(self, text)
                s = int((t - w3.EPOCH0).total_seconds())
                return t + dt.timedelta(seconds=s % 2 ** 32 - s)
        self.assertEqual(failing(run(Unsigned())), [VECTORS])

    def test_the_wrap_in_the_omm_path_alone_fails_the_kvn_case(self):   # already so through D-384's 2056 message
        self.assertIn("kvn-syntax-variants", failing(run(self.OmmOnly())))
        self.assertNotIn(VECTORS, failing(run(self.OmmOnly())))

    def test_the_last_second_before_the_wrap_and_the_first_after(self):
        with open(os.path.join(ROOT, "derived", "kvn-variants", "v08-synthetic-epochs.kvn"), encoding="utf-8") as f:
            kvn = f.read()
        for e in ("2038-01-19T03:14:07.000000", "2038-01-19T03:14:08.000000", "2050-06-15T12:00:00.000000"):
            self.assertIn(f"= {e}", kvn)
        self.assertEqual(dt.datetime(2038, 1, 19, 3, 14, 7) - dt.datetime(1970, 1, 1), dt.timedelta(seconds=2 ** 31 - 1))


class CheckTleSideFields(unittest.TestCase):
    """D-387, the owner's ruling extending D-381 to `check-tle --against`: a written side field may be zeroed or left
    out; another value than the source's fails the record."""

    SRC = {"norad_cat_id": 25544, "object_name": "ISS (ZARYA)", "object_id": "1998-067A",
           "epoch": "2026-09-20T12:42:37.141056", "mean_motion": "15.5", "eccentricity": "0.0001", "inclination": "51.6",
           "ra_of_asc_node": "10", "arg_of_pericenter": "10", "mean_anomaly": "10", "bstar": "0.0001",
           "mean_motion_dot": "0.00012", "mean_motion_ddot": "0", "ephemeris_type": 0, "classification_type": "U",
           "element_set_no": 999, "rev_at_epoch": 54321}

    def check(self, **written):
        from gpconf import writer as W
        lines = tlemod.render(tlemod.omm_fields_from_record(dict(self.SRC, **written)), mantissa_mode="round", ecc_mode="truncate")
        against = W.Against({25544: self.SRC})
        against.held, against.without_id = {25544: 1}, 0
        (r,) = W.check_file("\n".join(lines) + "\n", against)
        return r

    def test_the_source_values_pass(self):
        self.assertEqual(self.check()["status"], "pass")

    def test_zeroed_or_left_out_pass(self):
        self.assertEqual(self.check(rev_at_epoch=0, element_set_no=0, mean_motion_dot="0", object_id=None)["status"], "pass")

    def check_src(self, src, **written):
        from gpconf import writer as W
        lines = tlemod.render(tlemod.omm_fields_from_record(dict(self.SRC, **written)), mantissa_mode="round", ecc_mode="truncate")
        against = W.Against({25544: dict(self.SRC, **src)})
        against.held, against.without_id = {25544: 1}, 0
        (r,) = W.check_file("\n".join(lines) + "\n", against)
        return r

    def test_the_separate_review(self):
        # a zeroed second derivative whose source value the field cannot carry: zeroed, not a crash (F5)
        self.assertEqual(self.check_src({"mean_motion_ddot": "1.2345E-13"}, mean_motion_ddot="0")["status"], "pass")
        # the source's designator as a TLE can write it: trailing blanks and lower case (F6)
        for oid in ("1998-067A ", "1998-067a"):
            with self.subTest(oid=oid):
                self.assertEqual(self.check_src({"object_id": oid})["status"], "pass")
        # a value written where the source has none is another value (F2, documented)
        r = self.check_src({"object_id": None})
        self.assertEqual(r["status"], "fail")
        self.assertTrue(any("side field object_id" in p for p in r["problems"]), r["problems"])

    def test_another_value_fails_by_name(self):
        for field, value in (("rev_at_epoch", 12345), ("element_set_no", 1), ("mean_motion_dot", "0.00024"),
                             ("object_id", "1998-067B")):
            with self.subTest(field):
                r = self.check(**{field: value})
                self.assertEqual(r["status"], "fail")
                self.assertTrue(any(f"side field {field}" in p for p in r["problems"]), r["problems"])


class KnownLimit(unittest.TestCase):
    """R2 (D-386, the owner's ruling): SM-26's W3, a writer that rounds ties half down, passes and is recorded as the
    per-record rounding rule's known limit (docs/WRITERS.md): on a tie it writes the truncated value, and a writer of
    binary floats lands on either side of a decimal tie too, so one convention per field would fail correct float
    writers. Pinned, so that a change that starts or stops catching it is seen."""

    def test_w3_passes_and_its_twin_fails(self):
        self.assertEqual(failing(run(w2.W3HalfDown())), [])
        self.assertEqual(failing(run(w2.W3HalfDownTwin())), ["tle-writer-alpha5"])

    def test_float_formatting_lands_on_both_sides_of_a_decimal_tie(self):
        from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
        sides = set()
        for k in range(1, 400):
            tie = Decimal(15) + Decimal(k).scaleb(-8) + Decimal(5).scaleb(-9)
            got = Decimal("%.8f" % float(tie))
            q = Decimal(1).scaleb(-8)
            sides.add("up" if got == tie.quantize(q, ROUND_HALF_UP) else "down" if got == tie.quantize(q, ROUND_DOWN) else "other")
        self.assertEqual(sides, {"up", "down"})


class AlreadyCaught(unittest.TestCase):
    """What 0.8.0 caught in round two stays caught."""

    def test_twins_fail(self):
        for a, cases in ((w2.W1NdotDoubledTwin, ["tle-writer-alpha5"]), (w2.W3HalfDownTwin, ["tle-writer-alpha5"])):
            with self.subTest(a.__name__):
                self.assertEqual(failing(run(a())), cases)
        with self.subTest("E1NoDay366Twin"):
            self.assertTrue(failing(run(w2.E1NoDay366Twin())))

    def test_per_case_unsupported_is_caught(self):
        # P1: the all-or-none rule spans a case's files, so answering Unsupported for some TLE files fails
        self.assertIn("corrupt-input", failing(run(w2.P1PerCaseUnsupported(), NO_DATA)))


if __name__ == "__main__":
    unittest.main()
