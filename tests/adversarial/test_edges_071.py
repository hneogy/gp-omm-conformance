# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The small edge cases of 0.7.1, each with its wrong-on-purpose adapter and a twin (CLAUDE.md, "Grader changes").

From the hardening review of 2026-10-11 (W1 to W3 of its report): an infinite or NaN value, or a digit of another
script in a written line, failed in words that blamed the wrong side ("parser raised OverflowError", "internal error in
runner"); an epoch string with whitespace around it was read as the instant inside it, where element text is held to
nothing around it (D-319); the reference adapter's parse_epoch took day 366 of a common year, and no vector asked; the
reference's year pivot and Alpha-5 encoder took values that are not what they are for.

Each wrong adapter must fail, in words that name what it returned; each twin, the same adapter without the fault,
must pass. Run: python -m unittest tests.adversarial.test_edges_071"""
import datetime as dt
import os
import sys
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf import reference as refmod  # noqa: E402
from gpconf import tle as tlemod  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from tests.adversarial.test_hardening import failing, rewrite, run  # noqa: E402

THREE = ["alpha5-tle-derived", "corrupt-input", "kvn-syntax-variants"]   # the no-data cases whose records the parser returns


def set_field(field, value):
    class Adapter(Reference):
        def parse(self, raw, fmt):
            out = super().parse(raw, fmt)
            for r in out:
                if "_refused" not in r:
                    r[field] = value
            return out
    return Adapter()


def details(results):
    return [i.detail for c in results.values() for i in c.items if i.status == "fail"]


def no_wrong_words(test, results):
    for d in details(results):
        test.assertNotIn("internal error in runner", d)
        test.assertNotIn("OverflowError", d)
        test.assertNotIn("InvalidOperation", d)
        test.assertNotIn("parser raised UnreadableValue", d)
        test.assertNotIn("parser raised ValueError: not an ISO/CCSDS epoch", d)
        test.assertNotIn("parser raised OverflowError", d)


class ValuesThatAreNotFiniteFailInTheirOwnWords(unittest.TestCase):

    def test_an_infinite_catalog_number_fails_as_not_finite(self):
        for value in (float("inf"), float("-inf"), Decimal("Infinity")):
            with self.subTest(value=value):
                r = run(set_field("norad_cat_id", value))
                self.assertEqual(failing(r), THREE)
                no_wrong_words(self, r)
                self.assertTrue(any("not finite" in d for d in details(r)))

    def test_an_infinite_counter_fails_as_not_finite(self):
        r = run(set_field("rev_at_epoch", Decimal("Infinity")))
        self.assertEqual(failing(r), THREE)
        no_wrong_words(self, r)
        self.assertTrue(any("rev_at_epoch is not an integer" in d and "not finite" in d for d in details(r)))

    def test_nan_or_an_infinity_as_an_element_value_fails_the_file_as_parse(self):
        for field, value in (("mean_motion", float("nan")), ("mean_motion", float("inf")), ("eccentricity", Decimal("NaN")),
                             ("bstar", Decimal("-Infinity"))):
            with self.subTest(field=field, value=value):
                r = run(set_field(field, value))
                self.assertEqual(failing(r), THREE)
                no_wrong_words(self, r)
                parse = [i for c in r.values() for i in c.items if i.check == "parse" and i.status == "fail"]
                self.assertTrue(parse)
                self.assertTrue(all(i.detail.startswith("the parser returned a value the runner cannot read: ") for i in parse))
                self.assertTrue(all("is not a finite number" in i.detail for i in parse))

    def test_twin_finite_values_of_the_same_types_pass(self):
        """The same adapters with finite values of the same types pass: elements as float and as Decimal. (A float
        catalog number of 25544.0 is still not an integer, D-283, so the catalog number has no float twin.)"""
        def as_type(kind):
            class Adapter(Reference):
                def parse(self, raw, fmt):
                    out = super().parse(raw, fmt)
                    for r in out:
                        for k in ("mean_motion", "eccentricity", "bstar", "inclination"):
                            if "_refused" not in r and r.get(k) is not None:
                                r[k] = kind(str(r[k]))
                    return out
            return Adapter()
        self.assertEqual(failing(run(as_type(float))), [])
        self.assertEqual(failing(run(as_type(Decimal))), [])


class AWrittenLineWithAnotherScriptsDigitFailsOnItsChecksum(unittest.TestCase):

    def test_a_superscript_digit_in_a_written_line_fails_the_writer_case(self):
        class SupDigit(Reference):
            def write_tle(self, record):
                out = list(super().write_tle(record))
                out[-2] = out[-2][:60] + "¹" + out[-2][61:]
                return tuple(out)
        r = run(SupDigit(), cases=["tle-writer-alpha5"])
        self.assertEqual(failing(r), ["tle-writer-alpha5"])
        no_wrong_words(self, r)
        self.assertTrue(any(i.check == "tle-checksums-valid" and i.status == "fail" for i in r["tle-writer-alpha5"].items))

    def test_arabic_indic_digits_in_written_lines_fail_and_count_nothing_in_the_checksum(self):
        class Arabic(Reference):
            def write_tle(self, record):
                return tuple(line.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
                             for line in super().write_tle(record))
        r = run(Arabic(), cases=["tle-writer-alpha5"])
        self.assertEqual(failing(r), ["tle-writer-alpha5"])
        no_wrong_words(self, r)

    def test_another_scripts_digits_in_one_field_with_the_checksum_recomputed_fail(self):
        """The reviewer's escape (D-325): one element field in Arabic-Indic digits and the check digit recomputed over
        ASCII digits; the layout's \\d and the round trip read the field as the number it spells, so the case passed."""
        AR = str.maketrans("0123456789", "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669")
        def one_field(line_no, a, b):
            class Adapter(Reference):
                def write_tle(self, record):
                    out = list(super().write_tle(record))
                    i = len(out) - 3 + line_no
                    line = out[i][:a] + out[i][a:b].translate(AR) + out[i][b:68]
                    out[i] = line + str(tlemod.checksum(line))
                    return tuple(out)
            return Adapter()
        for line_no, a, b in ((2, 8, 16), (2, 52, 63), (2, 63, 68), (2, 26, 33), (1, 64, 68), (1, 53, 61)):
            with self.subTest(line=line_no, columns=f"{a + 1}-{b}"):
                r = run(one_field(line_no, a, b), cases=["tle-writer-alpha5"])
                self.assertEqual(failing(r), ["tle-writer-alpha5"])
                no_wrong_words(self, r)
                self.assertTrue(any("which is not ASCII" in d for d in details(r)))

    def test_twin_the_same_writer_in_ascii_digits_passes(self):
        class Recomputed(Reference):
            def write_tle(self, record):
                out = list(super().write_tle(record))
                out[-1] = out[-1][:68] + str(tlemod.checksum(out[-1]))
                return tuple(out)
        self.assertEqual(failing(run(Recomputed(), cases=["tle-writer-alpha5"])), [])

    def test_the_checksum_counts_ascii_digits_and_minus_signs_only(self):
        self.assertEqual(tlemod.checksum("1 ¹٣"), 1)            # the line number 1; the superscript and the Arabic-Indic 3 count nothing
        self.assertEqual(tlemod.checksum("-12"), 4)

    def test_twin_the_reference_writer_passes(self):
        self.assertEqual(failing(run(Reference(), cases=["tle-writer-alpha5"])), [])


class AnEpochStringIsTheEpochAndNothingAroundIt(unittest.TestCase):

    def test_whitespace_around_an_epoch_fails_the_file_as_parse(self):
        for name, pad in (("leading space", lambda s: " " + s), ("trailing space", lambda s: s + " "),
                          ("newline", lambda s: s + "\n"), ("tab", lambda s: "\t" + s)):
            with self.subTest(pad=name):
                r = run(rewrite("epoch", pad))
                self.assertEqual(failing(r), THREE)
                no_wrong_words(self, r)
                self.assertTrue(any("has whitespace around it" in d and "(D-325)" in d for d in details(r)))

    def test_an_epoch_the_reader_refuses_is_worded_as_the_parsers_value(self):
        """The reviewer's second finding: such an epoch read "parser raised ValueError", though the parser raised nothing."""
        for name, how in (("not a date", lambda s: "not a date"), ("BOM", lambda s: "\ufeff" + s), ("zero-width space", lambda s: s + "\u200b"),
                          ("Arabic-Indic digits", lambda s: s.translate(str.maketrans("0123456789", "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669")))):
            with self.subTest(epoch=name):
                r = run(rewrite("epoch", how))
                self.assertEqual(failing(r), THREE)
                no_wrong_words(self, r)
                parse = [i.detail for c in r.values() for i in c.items if i.check == "parse" and i.status == "fail"]
                self.assertTrue(parse and all(d.startswith("the parser returned a value the runner cannot read: ") for d in parse), parse[:1])

    def test_twin_the_same_epoch_as_text_with_nothing_around_it_passes(self):
        self.assertEqual(failing(run(rewrite("epoch", lambda s: s))), [])


class AnEpochPastTheYearsADatetimeHoldsIsWordedAsTheParsersValue(unittest.TestCase):
    """The second reading's finding: such an epoch read "parser raised OverflowError" (D-325)."""

    def test_an_epoch_string_that_overflows_fails_the_file_as_parse_in_the_parsers_words(self):
        for name, how in (("fraction past 9999", lambda s: "9999-12-31T23:59:59.9999999"), ("offset before year 1", lambda s: "0001-01-01T00:00:00+01:00")):
            with self.subTest(epoch=name):
                r = run(rewrite("epoch", how))
                self.assertEqual(failing(r), THREE)
                no_wrong_words(self, r)
                parse = [i.detail for c in r.values() for i in c.items if i.check == "parse" and i.status == "fail"]
                self.assertTrue(parse and all(d.startswith("the parser returned a value the runner cannot read: ") for d in parse), parse[:1])

    def test_a_datetime_whose_offset_overflows_fails_the_same_way(self):
        r = run(set_field("epoch", dt.datetime(1, 1, 1, tzinfo=dt.timezone(dt.timedelta(hours=1)))))
        self.assertEqual(failing(r), THREE)
        no_wrong_words(self, r)


class DayOfYearIsADayOfThatYear(unittest.TestCase):

    def test_a_parse_epoch_that_takes_day_366_of_a_common_year_fails_the_vectors(self):
        class LaxDay(Reference):
            def parse_epoch(self, text):          # the reference's hook as it was: strptime's %j takes 366 in any year
                if len(text.split("T")[0]) == 8 and text[5:8] == "366":
                    base = text.rstrip("Z").split(".")[0]
                    return dt.datetime.strptime(base, "%Y-%jT%H:%M:%S")
                return super().parse_epoch(text)
        r = run(LaxDay(), cases=["alpha5-encoding-vectors"])
        self.assertEqual(failing(r), ["alpha5-encoding-vectors"])
        item = next(i for i in r["alpha5-encoding-vectors"].items if i.check == "ccsds-epoch-strings")
        self.assertEqual(item.status, "fail")
        self.assertIn("invalid '2026-366T12:42:37' accepted", item.detail)

    def test_twin_the_reference_refuses_it_and_takes_day_366_of_a_leap_year(self):
        p = Reference()
        self.assertEqual(failing(run(p, cases=["alpha5-encoding-vectors"])), [])
        with self.assertRaises(ValueError):
            p.parse_epoch("2026-366T12:42:37")
        with self.assertRaises(ValueError):
            p.parse_epoch("1957-366T00:00:00")
        self.assertEqual(p.parse_epoch("2024-366T12:00:00"), dt.datetime(2024, 12, 31, 12))
        with self.assertRaises(ValueError):
            p.parse_epoch("2024-367T00:00:00")
        with self.assertRaises(ValueError):
            p.parse_epoch("2024-000T00:00:00")
        with self.assertRaises(ValueError):          # digits of another script are not the epoch's digits
            p.parse_epoch("٢٠٢٦-001T00:00:00")


class TheReferenceTakesOnlyWhatItIsFor(unittest.TestCase):
    """Reference-side only: no corpus input reaches these, and no grading changes (the report's W3)."""

    def test_the_reference_catalog_id_hook_takes_ascii_digits_only(self):
        with self.assertRaises(ValueError):
            Reference().parse_catalog_id("\u0662\u0665\u0665\u0664\u0664")
        self.assertEqual(Reference().parse_catalog_id("25544"), 25544)

    def test_the_year_pivot_takes_two_digits_or_an_integer_from_0_to_99(self):
        for bad in (-1, 100, "0", "100", "5a", True, 57.0, "٥٧"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                refmod.two_digit_year(bad)
        self.assertEqual([refmod.two_digit_year(v) for v in ("57", "56", "00", "99", 57, 0, 99)],
                         [1957, 2056, 2000, 1999, 1957, 2000, 1999])

    def test_the_alpha5_encoder_takes_integers_only(self):
        for bad in (0.0, 25544.9, 25544.0, "25544", True, Decimal(25544)):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                tlemod.to_alpha5(bad)
        self.assertEqual([tlemod.to_alpha5(n) for n in (0, 25544, 100000, 339999)], ["00000", "25544", "A0000", "Z9999"])


if __name__ == "__main__":
    unittest.main()
