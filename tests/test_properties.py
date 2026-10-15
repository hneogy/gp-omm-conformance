# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Property-based tests (D-320, from the hardening review of 2026-10-11): what holds for EVERY input of a kind, where
the vector files hold a chosen few. Alpha-5 encoding and decoding, the two-digit year pivot, epoch reading, catalog-id
text, the element-value grammar and the TLE checksum: round trips, bounds, and refusal of what is not valid.

They need Hypothesis, a test-only dependency (`pip install "gpconf[test]"`, or `pip install hypothesis`); the package
itself needs nothing. Without it each test is skipped by name, so a run says what it left out; and where
GPCONF_REQUIRE_HYPOTHESIS is set, as it is in CI, its absence is an error and the run fails: these tests do not skip
silently where they are meant to run (D-322). Examples per property: 100, or GPCONF_PROPERTY_EXAMPLES (the nightly
workflow runs 2,000). Properties the review found NOT to hold are not here; they are listed for the next release.

Run: python -m unittest tests.test_properties"""
import datetime as dt
import os
import string
import sys
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from hypothesis import assume, given, settings, strategies as st
    from hypothesis.configuration import set_hypothesis_home_dir
    import tempfile
    set_hypothesis_home_dir(tempfile.mkdtemp(prefix="gpconf-hypothesis-"))   # nothing is written into the tree
except ImportError:
    if os.environ.get("GPCONF_REQUIRE_HYPOTHESIS"):
        raise ImportError("Hypothesis is not installed and GPCONF_REQUIRE_HYPOTHESIS is set: the property tests must run here "
                          "(pip install hypothesis)")
    # elsewhere every test below is skipped, one by one, so the module loads and reports them as skips
    class _Anything:
        def __call__(self, *a, **k):
            return self

        def __getattr__(self, name):
            return self
    st = _Anything()

    def given(*a, **k):
        return unittest.skip("Hypothesis is not installed")

    def settings(**k):
        return lambda f: f

    def assume(condition):
        return True

from gpconf import reference as ref  # noqa: E402
from gpconf import tle  # noqa: E402
from gpconf.adapters.reference import Parser  # noqa: E402
from gpconf.runner import PLAIN_DECIMAL, norm_epoch, norm_record  # noqa: E402

P = Parser()
N = settings(max_examples=int(os.environ.get("GPCONF_PROPERTY_EXAMPLES", "100")), deadline=None, derandomize=True, database=None)
DIGITS = "0123456789"
LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
OTHER_DIGITS = str.maketrans(DIGITS, "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669")
DATETIMES = st.datetimes(min_value=dt.datetime(1957, 1, 1), max_value=dt.datetime(2056, 12, 31, 23, 59, 59, 999999))
LINE_CHARS = DIGITS + string.ascii_uppercase + " .+-"


class Alpha5(unittest.TestCase):
    @N
    @given(st.integers(min_value=0, max_value=339999))
    def test_round_trip(self, n):
        f = tle.to_alpha5(n)
        self.assertEqual(len(f), 5)
        self.assertTrue(all(c in DIGITS for c in f[1:]) and (f[0] in DIGITS or f[0] in LETTERS))
        self.assertEqual((tle.from_alpha5(f), P.alpha5_decode(f), P.alpha5_encode(n)), (n, n, f))

    @N
    @given(st.integers(min_value=0, max_value=339998))
    def test_the_next_number_is_the_next_field(self, n):
        self.assertEqual(tle.from_alpha5(tle.to_alpha5(n)) + 1, tle.from_alpha5(tle.to_alpha5(n + 1)))

    @N
    @given(st.one_of(st.integers(max_value=-1), st.integers(min_value=340000)))
    def test_encode_refuses_what_the_field_cannot_carry(self, n):
        for fn in (tle.to_alpha5, P.alpha5_encode):
            with self.assertRaises(ValueError):
                fn(n)

    @N
    @given(st.one_of(st.text(max_size=8), st.text(alphabet=string.ascii_letters + string.digits + " -+.", min_size=5, max_size=5)))
    def test_decode_accepts_exactly_the_definition(self, s):
        ok = len(s) == 5 and (s[0] in DIGITS or s[0] in LETTERS) and all(c in DIGITS for c in s[1:])
        for fn in (tle.from_alpha5, P.alpha5_decode):
            if ok:
                self.assertEqual(tle.to_alpha5(fn(s)), s)
            else:
                with self.assertRaises(ValueError):
                    fn(s)


class TwoDigitYear(unittest.TestCase):
    @N
    @given(st.integers(min_value=0, max_value=99))
    def test_the_pivot_is_57(self, yy):
        y = ref.two_digit_year(yy)
        self.assertEqual(y, 1900 + yy if yy >= 57 else 2000 + yy)
        self.assertTrue(1957 <= y <= 2056)
        self.assertEqual((ref.two_digit_year(f"{yy:02d}"), P.two_digit_year(f"{yy:02d}")), (y, y))


class Epochs(unittest.TestCase):
    @N
    @given(DATETIMES)
    def test_calendar_round_trip(self, t):
        text = t.strftime("%Y-%m-%dT%H:%M:%S.%f")
        self.assertEqual((tle.iso_epoch(text), norm_epoch(t), norm_epoch(text)), (text, text, text))
        self.assertEqual((P.parse_epoch(text), P.parse_epoch(text + "Z")), (t, t))

    @N
    @given(DATETIMES)
    def test_day_of_year_is_the_same_instant(self, t):
        doy = t.strftime("%Y-%jT%H:%M:%S.%f")
        self.assertEqual(tle.iso_epoch(doy), t.strftime("%Y-%m-%dT%H:%M:%S.%f"))
        self.assertEqual(P.parse_epoch(doy), t)

    @N
    @given(DATETIMES, st.integers(min_value=-14 * 60, max_value=14 * 60))
    def test_an_offset_is_converted_to_utc(self, t, minutes):
        text = t.strftime("%Y-%m-%dT%H:%M:%S.%f") + f"{'+' if minutes >= 0 else '-'}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"
        self.assertEqual(tle.iso_epoch(text), (t - dt.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.%f"))

    @N
    @given(DATETIMES, st.text(alphabet=DIGITS, min_size=1, max_size=12))
    def test_a_fraction_of_any_length_lands_within_half_a_microsecond(self, t, frac):
        t = t.replace(microsecond=0)
        got = dt.datetime.strptime(tle.iso_epoch(t.strftime("%Y-%m-%dT%H:%M:%S") + "." + frac), "%Y-%m-%dT%H:%M:%S.%f")
        self.assertLessEqual(abs(Decimal((got - t) // dt.timedelta(microseconds=1)) - Decimal("0." + frac) * 1_000_000), Decimal("0.5"))

    @N
    @given(st.one_of(st.text(max_size=30), st.text(alphabet=DIGITS + "-T:.Z+ ", max_size=30)))
    def test_a_reader_raises_valueerror_or_nothing(self, s):
        for fn in (tle.iso_epoch, P.parse_epoch):
            try:
                fn(s)
            except ValueError:
                pass

    @N
    @given(DATETIMES)
    def test_the_digits_of_another_script_are_refused(self, t):                 # D-319
        with self.assertRaises(ValueError):
            tle.iso_epoch(t.strftime("%Y-%m-%dT%H:%M:%S").translate(OTHER_DIGITS))

    @N
    @given(st.integers(min_value=1957, max_value=2056), st.integers(min_value=0, max_value=400))
    def test_the_runner_s_reader_holds_the_day_of_year_to_the_year(self, year, doy):
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        if 1 <= doy <= (366 if leap else 365):
            tle.iso_epoch(f"{year}-{doy:03d}T00:00:00")
        else:
            with self.assertRaises(ValueError):
                tle.iso_epoch(f"{year}-{doy:03d}T00:00:00")


class CatalogIdText(unittest.TestCase):
    @N
    @given(st.integers(min_value=0, max_value=999999999))
    def test_round_trip(self, n):
        self.assertEqual((P.parse_catalog_id(str(n)), P.parse_catalog_id(f"{n:09d}")), (n, n))

    @N
    @given(st.text(alphabet=string.printable, max_size=12))
    def test_ascii_text_is_accepted_only_as_up_to_nine_digits(self, s):
        t = s.strip()
        body = t[1:] if t.startswith("+") else t
        ok = 1 <= len(body) <= 9 and all(c in DIGITS for c in body)
        if ok:
            self.assertEqual(P.parse_catalog_id(s), int(body))
        else:
            with self.assertRaises(ValueError):
                P.parse_catalog_id(s)


class ElementValueText(unittest.TestCase):                                      # D-319
    @N
    @given(st.decimals(allow_nan=False, allow_infinity=False, places=8, min_value=-1000, max_value=1000))
    def test_a_plain_decimal_string_is_read_as_its_value(self, d):
        out, _, bad = norm_record({"mean_motion": str(d)})
        self.assertEqual((out["mean_motion"], bad), (d, {}))

    @N
    @given(st.text(max_size=14))
    def test_text_is_read_only_if_it_is_a_plain_ascii_decimal(self, s):
        assume(s != "")
        if PLAIN_DECIMAL.fullmatch(s):
            self.assertTrue(s.isascii() and s == s.strip() and "_" not in s)
            out, _, bad = norm_record({"mean_motion": s})
            self.assertEqual((out["mean_motion"], bad), (Decimal(s), {}))
        else:
            with self.assertRaises(ValueError):
                norm_record({"mean_motion": s})


class Checksum(unittest.TestCase):
    @N
    @given(st.text(alphabet=LINE_CHARS, min_size=68, max_size=68))
    def test_the_definition(self, line):
        want = (sum(int(c) for c in line if c in DIGITS) + line.count("-")) % 10
        self.assertEqual((tle.checksum(line), tle.checksum(line + "7")), (want, want))      # column 69 is the checksum itself

    @N
    @given(st.text(alphabet=LINE_CHARS, min_size=68, max_size=68), st.integers(min_value=0, max_value=67), st.sampled_from(DIGITS))
    def test_any_single_digit_change_is_detected(self, line, i, d):
        assume(line[i] in DIGITS and line[i] != d)
        self.assertNotEqual(tle.checksum(line[:i] + d + line[i + 1:]), tle.checksum(line))


class TheyRan(unittest.TestCase):
    def test_how_many_properties_this_module_holds(self):
        """A count, so that a property dropped by accident is noticed, and so that a report can say how many ran."""
        names = [n for c in (Alpha5, TwoDigitYear, Epochs, CatalogIdText, ElementValueText, Checksum) for n in dir(c) if n.startswith("test_")]
        self.assertEqual(len(names), 18)


if __name__ == "__main__":
    unittest.main()
