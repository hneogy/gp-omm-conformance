# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Tests that pin survivors of the 0.9.0 mutation run the owner ruled must be covered before the release: the counts of a
format whose parser raised, the day-of-year bound, the writer checks' fixed columns, epoch convention and secondary
fields, check-tle's name lines and stray lines, and its pairing with the source's copies of an id (D-403). Each test
passes on the code and fails under the mutants its docstring names.

Run: python -m unittest tests.test_must_090_3"""
import os
import sys
import tempfile
import unittest
from decimal import ROUND_DOWN

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import gates  # noqa: E402
from gpconf import tle as T  # noqa: E402
from gpconf import writer as W  # noqa: E402
from gpconf.runner import Item  # noqa: E402
from tests.test_check_tle_robustness import csv_source, record, rendered, with_checksum  # noqa: E402


def put(line, i, text):
    """A 69-character line with text written from 0-based column i and its checksum recomputed."""
    return with_checksum((line[:i] + text + line[i + len(text):])[:68])


# ---- gates.format_result for a parser that raised on the gate's file

class TheCountsOfAParserThatRaised(unittest.TestCase):

    def test_a_parser_that_raised_returned_and_misidentified_nothing(self):
        """Kills 1866 (returned written as 1), 1868 (misidentified written as 1): a parser that raised on the file
        returned no record and misidentified none."""
        res = gates.format_result([Item("parse", "fail", detail="ValueError: the file could not be read")])
        self.assertEqual(res, {"state": "measured", "note": "the parser raised on the file", "expected": None,
                               "returned": 0, "loaded": 0, "misidentified": 0, "dropped": None})


# ---- tle.iso_epoch: the day-of-year form

class TheDayOfYearBound(unittest.TestCase):

    def test_day_366_is_refused_in_a_common_year_and_read_in_a_leap_year(self):
        """Kills 1974 (a common year allowed 366 days): day 366 of 2023 is outside the year, not 1 January 2024."""
        with self.assertRaises(ValueError):
            T.iso_epoch("2023-366T00:00:00")
        self.assertEqual(T.iso_epoch("2024-366T00:00:00"), "2024-12-31T00:00:00.000000")
        self.assertEqual(T.iso_epoch("2023-365T00:00:00"), "2023-12-31T00:00:00.000000")


# ---- writer.LAYOUT: each field's first column is checked and the columns are named as the format has them

class TheFieldColumns(unittest.TestCase):

    FIELDS = [   # (line, 0-based first column, end, the problem's words)
        (1, 64, 68, "line 1 columns 65-68 (element set number, right-justified)"),
        (2, 17, 25, "line 2 columns 18-25 (RA of ascending node, right-justified nnn.nnnn)"),
        (2, 34, 42, "line 2 columns 35-42 (argument of pericenter, right-justified nnn.nnnn)"),
        (2, 43, 51, "line 2 columns 44-51 (mean anomaly, right-justified nnn.nnnn)"),
        (2, 52, 63, "line 2 columns 53-63 (mean motion, right-justified nn.nnnnnnnn)"),
        (2, 63, 68, "line 2 columns 64-68 (revolution number, right-justified)"),
    ]

    def test_a_letter_in_a_fields_first_column_is_named_with_the_fields_columns(self):
        """Kills 1583 (element set number from column 66), 1584 (element set number to column 69), 1593 (RA of
        ascending node from column 19), 1601 (argument of pericenter from column 36), 1605 (mean anomaly from column
        45), 1609 (mean motion from column 54), 1611 (revolution number from column 65), 1612 (revolution number to
        column 69): an 'X' in the first column of each field is one problem, worded with the field's own columns."""
        _, l1, l2 = rendered(record())
        self.assertEqual(W.check_layout(l1, l2), [])
        for n, a, b, words in self.FIELDS:
            with self.subTest(field=words):
                bad1, bad2 = (put(l1, a, "X"), l2) if n == 1 else (l1, put(l2, a, "X"))
                sub = (bad1 if n == 1 else bad2)[a:b]
                self.assertEqual(sub[0], "X")
                self.assertEqual(W.check_layout(bad1, bad2), [f"{words}: {sub!r}"])


# ---- writer.round_trip: the epoch's convention

class TheEpochConvention(unittest.TestCase):

    def test_an_exact_epoch_reads_exact_and_a_truncated_one_truncate(self):
        """Kills 1629 (the exact epoch taken where the two quantisations differ): an epoch the field holds exactly,
        12:00:00, is 'exact'; one 500 us later, which truncation and rounding write differently, written truncated,
        is 'truncate'."""
        rec = dict(record(), epoch="2026-07-14T12:00:00.000000")
        _, l1, l2 = rendered(rec)
        mism, conv = W.round_trip(None, l1, l2, rec)
        self.assertEqual(mism, [])
        self.assertEqual(conv["epoch"], "exact")
        rec = dict(record(), epoch="2026-07-14T12:00:00.000500")
        _, l1, l2 = T.render(T.omm_fields_from_record(rec), mantissa_mode="round", ecc_mode="round", epoch_rounding=ROUND_DOWN)
        self.assertEqual(l1[18:32], "26195.50000000")
        mism, conv = W.round_trip(None, l1, l2, rec)
        self.assertEqual(mism, [])
        self.assertEqual(conv["epoch"], "truncate")


# ---- writer.secondary_fields

class TheSecondaryFields(unittest.TestCase):

    def setUp(self):
        self.rec = record()
        self.l0, self.l1, self.l2 = rendered(self.rec)

    def test_a_derivative_left_out_or_zero_in_the_source_and_written_as_zero_is_preserved(self):
        """Kills 1633 (a source derivative of none or 0 read as 1): a source with no first derivative and a second
        derivative of 0.0, written as zeros, kept both."""
        rec = dict(self.rec, mean_motion_ddot=0.0)
        del rec["mean_motion_dot"]
        l0, l1, l2 = rendered(rec)
        s = W.secondary_fields(l0, l1, l2, rec)
        self.assertEqual((s["mean_motion_dot"], s["mean_motion_ddot"]), ("preserved", "preserved"))

    def test_a_source_with_no_classification_written_u_and_c_written_c_are_preserved(self):
        """Kills 1654 (the 'U' default for a source with no classification turned into 'and')."""
        for given in (None, "C"):
            with self.subTest(classification=given):
                rec = dict(self.rec, classification_type=given)
                l0, l1, l2 = rendered(rec)
                self.assertEqual(l1[7], given or "U")
                self.assertEqual(W.secondary_fields(l0, l1, l2, rec)["classification_type"], "preserved")

    def test_a_designator_blanked_but_for_column_10_is_another_value(self):
        """Kills 1658 (the blank test from column 11): '9' left in column 10 and the rest blank is no designator the
        reader can read, another value than the source's, not one left out (D-383)."""
        l1 = put(self.l1, 9, "9       ")
        self.assertEqual(l1[9:17], "9       ")
        self.assertEqual(W.secondary_fields(self.l0, l1, self.l2, self.rec)["object_id"], "changed")

    def test_a_long_name_written_as_another_name_is_changed(self):
        """Kills 1667 (a name over 24 characters taken as cut whatever was written)."""
        rec = dict(self.rec, object_name="A" * 30)
        self.assertEqual(W.secondary_fields("OTHER", self.l1, self.l2, rec)["object_name"], "changed")

    def test_a_25_character_name_written_cut_to_24_is_cut_to_24(self):
        """Kills 1669 (only a name over 25 characters taken as cut)."""
        name = "ABCDEFGHIJKLMNOPQRSTUVWXY"
        self.assertEqual(len(name), 25)
        rec = dict(self.rec, object_name=name)
        self.assertEqual(W.secondary_fields(name[:24], self.l1, self.l2, rec)["object_name"], "cut-to-24")


# ---- writer.scan_lines and check_file: name lines and stray lines

class TheNameLine(unittest.TestCase):

    def setUp(self):
        _, self.l1, self.l2 = rendered(record())

    def names(self, text):
        """The name scan_lines gives each record, and the name check_file reports for it."""
        return [r[0] for r in W.scan_lines(text)[0]], [r["name"] for r in W.check_file(text)]

    def test_only_a_line_before_line_1_that_is_a_name_is_the_name(self):
        """Kills 1716 (the file's last line taken as the first record's name), 1720 (any non-blank line before line 1
        taken as the name): a trailer after the only record, the line 2 of the record before, and a '#' comment are
        no name; a name line is."""
        l1, l2 = self.l1, self.l2
        self.assertEqual(self.names(f"{l1}\n{l2}\nTRAILER\n"), ([None], [None]))
        self.assertEqual(self.names(f"{l1}\n{l2}\n{l1}\n{l2}\n"), ([None, None], [None, None]))
        self.assertEqual(self.names(f"# rffit\n{l1}\n{l2}\n"), ([None], [None]))
        self.assertEqual(self.names(f"SARAMAGO\n{l1}\n{l2}\n"), (["SARAMAGO"], ["SARAMAGO"]))


class AStrayLine2(unittest.TestCase):

    def test_a_line_2_before_a_pair_is_one_unpaired_entry_at_its_own_line(self):
        """Kills 1733 (the stray reported at i - 1), 1734 (at i + 2), 1735 (the line after a stray skipped), 1809 (its
        catalog field from column 4), 1810 (its catalog field to column 8), 1811 (unpaired written false)."""
        _, l1, l2 = rendered(record())
        res = W.check_file(f"{l2}\n{l1}\n{l2}\n")
        self.assertEqual([r["status"] for r in res], ["fail", "pass"])
        self.assertEqual([r["line_number"] for r in res], [1, 2])
        self.assertEqual(res[0]["catalog_field"], l2[2:7])
        self.assertEqual(res[0]["catalog_field"], "A0000")
        self.assertIs(res[0]["unpaired"], True)
        self.assertTrue(any("line 2" in p and "no line 1" in p for p in res[0]["problems"]), res[0]["problems"])
        self.assertNotIn("unpaired", res[1])


class AWrittenNameLine(unittest.TestCase):

    def test_a_name_line_a_tool_wrote_in_utf_8_passes(self):
        """Kills 1766 (check-tle reading a tool's output by the provider-file rules): a name line outside ASCII is
        reported for information on lines a writer wrote (D-336), so a correct record under it passes."""
        _, l1, l2 = rendered(record())
        r = W.check_file(f"SATÉLITE\n{l1}\n{l2}\n")[0]
        self.assertEqual(r["status"], "pass", r["problems"])
        self.assertEqual(r["name"], "SATÉLITE")


# ---- writer.check_record: pairing with the source's copies of an id (D-403)

class PairingWithTheSource(unittest.TestCase):

    def setUp(self):
        self.rec = record()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_an_id_the_source_holds_once_is_compared_without_pairing_by_epoch(self):
        """Kills 1778 (an id held once paired by epoch as a history): the record is compared with the one source record,
        and nothing says it was paired with a copy."""
        path = os.path.join(self.tmp.name, "source.csv")
        with open(path, "w", encoding="utf-8") as f:
            f.write(csv_source(self.rec))
        against = W.load_against(path)
        self.assertEqual(against.held, {100000: 1})
        l0, l1, l2 = rendered(self.rec)
        r = W.check_file(f"{l0}\n{l1}\n{l2}\n", against)[0]
        self.assertEqual(r["status"], "pass", r["problems"])
        self.assertNotIn("paired_copy", r)
        self.assertNotIn("matches_copies", r)
        self.assertFalse(any("paired by its epoch" in n for n in r["notes"]), r["notes"])

    def test_a_record_written_from_the_second_of_two_copies_at_one_epoch_pairs_with_it(self):
        """Kills 1786 (clean() true for a copy that round-trips but whose side fields differ), 1791 (clean() reading
        only the fields that are not side fields), 1796, 1797 (matches_copies shifted), 1798, 1799 (paired_copy
        shifted). Two copies of one id at the same epoch and elements, element set numbers 100 and 200; the record
        written from copy 2 round-trips to it alone, is paired with it and passes."""
        one, two = dict(self.rec, element_set_no=100), dict(self.rec, element_set_no=200)
        against = W.Against({100000: two})   # as load_against holds it: the last copy, every copy in `copies`
        against.held, against.without_id, against.copies = {100000: 2}, 0, {100000: [one, two]}
        l0, l1, l2 = rendered(two)
        self.assertEqual(l1[64:68], " 200")
        r = W.check_file(f"{l0}\n{l1}\n{l2}\n", against)[0]
        self.assertEqual(r["status"], "pass", r["problems"])
        self.assertEqual(r["paired_copy"], 2)
        self.assertEqual(r["matches_copies"], [2])
        self.assertIn("paired by its epoch with copy 2 of 2 in the source", r["notes"])


if __name__ == "__main__":
    unittest.main()
