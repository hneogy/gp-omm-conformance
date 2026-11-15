# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Tests that pin survivors of the 0.9.0 mutation run in gpconf/plain.py, named by mutant number in
docs/handoff/mutation-survivors-0.9.0-triage.md (D-519): a record that shows one value and
holds another, one per kind of value; how as_text writes a container at and past FIELD_TEXT characters; and ints at
Python's digit limit. Each passes on the code and fails under its mutants."""
import datetime as dt
import os
import sys
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import plain  # noqa: E402


def two_faced(held, shown):
    """A dict subclass that holds {'v': held} and whose [] shows `shown` for every key."""
    class Two(dict):
        def __getitem__(self, k):
            return shown
    return Two(v=held)


UTC = dt.timezone.utc
PLUS1 = dt.timezone(dt.timedelta(hours=1))
PLUS2 = dt.timezone(dt.timedelta(hours=2))


class ARecordThatShowsOneValueAndHoldsAnother(unittest.TestCase):
    """Each pair differs in one value of one kind, so the comparison of the two readings must tell them apart by
    digest; each twin shows an equal value that is another object, which must read as one record."""

    def assert_two_faced(self, held, shown):
        out = plain.record(two_faced(held, shown))
        self.assertIs(type(out), plain.Problem, out)
        self.assertIn("show other fields or values than it holds", out.what)

    def assert_one_record(self, held, shown):
        out = plain.record(two_faced(held, shown))
        self.assertEqual(out, {"v": held})

    def test_values_that_are_all_other_objects_are_compared(self):
        """Kills 2584 (the one-reading shortcut taken when every shown value is another object)."""
        class Two(dict):
            def __getitem__(self, k):
                return 2
        out = plain.record(Two(a=1))
        self.assertIs(type(out), plain.Problem, out)
        self.assertIn("show other fields or values than it holds", out.what)
        self.assertEqual(plain.record(type("Same", (dict,), {})(a=1)), {"a": 1})

    def test_a_bool_shown_for_another_bool(self):
        """Kills 2626 (True and False digested alike), 2584."""
        self.assert_two_faced(False, True)
        self.assert_one_record(True, True)

    def test_a_float_shown_for_another_float(self):
        """Kills 2633 (a float's digest raises), 2584."""
        self.assert_two_faced(0.5, 1.5)
        self.assert_one_record(0.5, float("0.5"))

    def test_a_set_of_floats_is_read_as_its_values(self):
        """Kills 2633 (a set's entries are ordered by digest)."""
        out = plain.value({0.5, 1.5})
        self.assertIs(type(out), list)
        self.assertEqual(sorted(out), [0.5, 1.5])

    def test_a_timezone_shown_for_another_timezone(self):
        """Kills 2647, 2648 (a timezone's digest raises), 2655, 2656 (its offset's digest), 2584."""
        self.assert_two_faced(PLUS1, PLUS2)
        self.assert_one_record(PLUS1, dt.timezone(dt.timedelta(hours=1)))

    def test_a_naive_datetime_shown_for_another(self):
        """Kills 2649 (every datetime digested alike), 2584."""
        self.assert_two_faced(dt.datetime(2020, 1, 1), dt.datetime(2020, 1, 2))
        self.assert_one_record(dt.datetime(2020, 1, 1), dt.datetime(2020, 1, 1))

    def test_the_same_wall_time_in_another_zone(self):
        """Kills 2652 (an aware datetime digested without its zone), 2647, 2648, 2584."""
        self.assert_two_faced(dt.datetime(2020, 1, 1, tzinfo=UTC), dt.datetime(2020, 1, 1, tzinfo=PLUS1))
        self.assert_one_record(dt.datetime(2020, 1, 1, tzinfo=PLUS1),
                               dt.datetime(2020, 1, 1, tzinfo=dt.timezone(dt.timedelta(hours=1))))

    def test_a_date_shown_for_another_date(self):
        """Kills 2653 (every date digested alike), 2654 (a date's digest raises), 2584."""
        self.assert_two_faced(dt.date(2020, 1, 1), dt.date(2020, 1, 2))
        self.assert_one_record(dt.date(2020, 1, 1), dt.date(2020, 1, 1))

    def test_a_timedelta_shown_for_another_timedelta(self):
        """Kills 2655 (every timedelta digested alike), 2656 (a timedelta's digest raises), 2653, 2584."""
        self.assert_two_faced(dt.timedelta(1), dt.timedelta(2))
        self.assert_one_record(dt.timedelta(1), dt.timedelta(days=1))


def text(v):
    out = plain.as_text(v)
    if type(out) is not plain.Written:  # not a bare assert, so that python -O keeps the check
        raise AssertionError(f"as_text gave {type(out).__name__}, not Written")
    return str.__str__(out)


class AsTextAtAndPastTheLimit(unittest.TestCase):
    def test_a_short_dict_is_written_whole(self):
        """Kills 2677 (every dict entry taken as unwritable)."""
        self.assertEqual(text({"a": 1}), "{'a': 1}")
        self.assertEqual(plain.as_text({"a": 1}).kind, "dict")

    def test_a_container_of_exactly_the_limit_is_written_whole(self):
        """Kills 2683, 2690 (a text of exactly FIELD_TEXT characters cut)."""
        v = ["x" * 996]
        self.assertEqual(len(repr(v)), plain.FIELD_TEXT)
        self.assertEqual(text(v), repr(v))

    def test_one_character_more_is_cut_with_a_digest(self):
        """The twin of 2683, 2690: 1,001 characters are cut."""
        out = text(["x" * 997])
        self.assertTrue(out.startswith("['" + "x" * 997 + "'… <a list too long to write out, #"), out[-80:])

    def test_the_marker_says_a_list(self):
        """Kills 2742 (the article inverted: 'an list')."""
        self.assertIn("… <a list too long to write out, #", text(["x" * 2000]))

    def test_the_head_writes_nested_containers_and_a_short_decimal_as_python_does(self):
        """Kills 2703 (a dict opened with '(' and a tuple with '{'), 2708, 2709 (the closing brackets swapped), 2710 (a
        short Decimal written by its digits alone)."""
        out = text([[1], {"a": 1}, (2, 3), Decimal("1.5"), "x" * 2000])
        self.assertTrue(out.startswith("[[1], {'a': 1}, (2, 3), Decimal('1.5'), 'xxx"), out[:60])

    def test_a_short_text_straddling_the_limit_fills_the_head(self):
        """Kills 2718 (a short leaf cut two characters early, the closing bracket in its last place)."""
        out = text(["a" * 1000])
        self.assertTrue(out.startswith("[" + repr("a" * 1000)[:999] + "… <a list too long to write out, #"), out[990:1040])

    def test_a_marker_straddling_the_limit_fills_the_head(self):
        """Kills 2715 (a Written leaf cut two characters early, the closing bracket in its last place)."""
        v = plain.value(["x" * 990, 10 ** 5000])
        self.assertIs(type(v[1]), plain.Written)
        out = text(v)
        self.assertEqual(out[:plain.FIELD_TEXT], "['" + "x" * 990 + "', <an i")
        self.assertEqual(out[plain.FIELD_TEXT], "…")


class IntsAtTheDigitLimit(unittest.TestCase):
    """Under a limit of 4,300 digits: 10 ** 4300 - 1 (4,300 digits) and 10 ** 4300 (4,301) have the same length in
    bits, so only the exact comparison tells them apart."""

    def setUp(self):
        if not hasattr(sys, "set_int_max_str_digits"):
            self.skipTest("this Python has no limit on the digits it writes (sys.set_int_max_str_digits)")
        old = sys.get_int_max_str_digits()
        self.addCleanup(sys.set_int_max_str_digits, old)
        sys.set_int_max_str_digits(4300)

    def assert_marker(self, n):
        out = plain.value(n)
        self.assertIs(type(out), plain.Written)
        self.assertEqual(out.kind, "int")
        self.assertTrue(str.__str__(out).startswith("<an integer of "), str.__str__(out)[:40])

    def assert_int(self, n):
        out = plain.value(n)
        self.assertIs(type(out), int)
        self.assertTrue(out == n)   # no assertEqual: its message would write the int

    def test_4300_digits_are_an_int(self):
        """Kills 2517 (taken as too big from its bits), 2521 (the limit's power never made: KeyError), 2523 (the
        comparison inverted)."""
        self.assert_int(10 ** 4300 - 1)
        self.assert_int(-(10 ** 4300 - 1))

    def test_4301_digits_are_a_marker(self):
        """Kills 2512 (the fast path widened past the limit), 2523, 2525 (10 ** 4300 itself in range)."""
        self.assert_marker(10 ** 4300)

    def test_minus_4301_digits_are_a_marker(self):
        """Kills 2512, 2524 (-10 ** 4300 itself in range), 2523."""
        self.assert_marker(-10 ** 4300)


if __name__ == "__main__":
    unittest.main()
