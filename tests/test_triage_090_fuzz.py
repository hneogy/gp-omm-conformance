# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Tests that pin survivors of the 0.9.0 mutation run in gpconf/fuzz.py, named by mutant number in
docs/handoff/mutation-survivors-0.9.0-triage.md (D-521): what each TLE operator does to the
line it edits, _replace_value in each format's own syntax, and minimise against a parser that crashes on known bytes.
Each passes on the code and fails under its mutants.

Run: python -m unittest tests.test_triage_090_fuzz"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import fuzz as F  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import _Guarded  # noqa: E402


def seed_text(ext):
    """A shipped seed (derived/ephemeris-type-4/type0.<ext>, CRLF line endings) as bytes."""
    with open(os.path.join(ROOT, "derived", "ephemeris-type-4", "type0." + ext), "rb") as f:
        return f.read()


class Pick:
    """random.Random with its draws given: choice() hands back the next given value (the first is the operator or the
    key), or the sequence's first item once they run out or when the given one is not in it (so an empty sequence
    raises IndexError, as random.choice does); randrange() hands back n when it lies in the range, randint() k and
    random() x."""

    def __init__(self, *picks, n=None, k=1, x=0.25):
        self.picks, self.n, self.k, self.x = list(picks), n, k, x

    def choice(self, seq):
        if self.picks:
            v = self.picks.pop(0)
            try:
                if v in seq:
                    return v
            except TypeError:
                pass
        return seq[0]

    def randrange(self, a, b=None):
        lo, hi = (0, a) if b is None else (a, b)
        return self.n if self.n is not None and lo <= self.n < hi else lo

    def randint(self, a, b):
        return self.k

    def random(self):
        return self.x


class TheTleOperators(unittest.TestCase):
    """type0.tle: lines[0] the name, lines[1] line 1, lines[2] line 2, lines[3] empty after the last CRLF."""

    def edit(self, *picks, **draws):
        data = seed_text("tle")
        out, got = F._mutate(data, "tle", Pick(*picks, **draws))
        old, new = data.decode("utf-8").split("\r\n"), out.decode("utf-8").split("\r\n")
        self.assertEqual(len(old[1]), 69)
        self.assertEqual(len(old[2]), 69)
        return got, old, new

    def assert_only_line(self, i, old, new, want):
        self.assertEqual(len(new), len(old))
        self.assertEqual(new[i], want)
        self.assertEqual(len(new[i]), 69)
        self.assertNotEqual(new[i], old[i])
        self.assertEqual(new[:i] + new[i + 1:], old[:i] + old[i + 1:])

    def test_shift_column_right_puts_a_blank_in_and_keeps_the_length(self):
        """Kills 3118 (shift-column taken by the other operators' branches)."""
        got, old, new = self.edit("shift-column", 1, n=30, x=0.25)
        self.assertEqual(got, "shift-column")
        self.assert_only_line(1, old, new, old[1][:30] + " " + old[1][30:68])

    def test_shift_column_left_takes_a_character_out_and_keeps_the_length(self):
        """Kills 3118, 3125 (l[c - 1:69] repeats a character: a 71-character line)."""
        got, old, new = self.edit("shift-column", 1, n=30, x=0.75)
        self.assertEqual(got, "shift-column")
        self.assert_only_line(1, old, new, old[1][:30] + old[1][31:69] + " ")

    def test_checksum_broken_changes_the_checksum_alone(self):
        """Kills 3128 (checksum-broken changes nothing), 3118."""
        got, old, new = self.edit("checksum-broken", 2, k=3)
        self.assertEqual(got, "checksum-broken")
        self.assert_only_line(2, old, new, old[2][:68] + str((int(old[2][68]) + 3) % 10))

    def test_checksum_recomputed_changes_one_column_and_the_checksum_follows(self):
        """Kills 3141 (checksum-recomputed changes nothing), 3146 (l[c - 1:68]: a 71-character line, the checksum
        out of its column), 3128 (it would break the checksum instead), 3118."""
        got, old, new = self.edit("checksum-recomputed", 1, "9", n=40)
        self.assertEqual(got, "checksum-recomputed")
        body = old[1][:40] + "9" + old[1][41:68]
        self.assert_only_line(1, old, new, body + F._checksum(body))
        self.assertEqual(F._checksum(new[1][:68]), new[1][68])

    def test_alpha5_letter_writes_a_letter_into_the_catalog_field(self):
        """Kills 3152 (alpha5-letter changes nothing), 3141, 3128, 3118 (each sends it down another branch)."""
        got, old, new = self.edit("alpha5-letter", 2, "Z")
        self.assertEqual(got, "alpha5-letter")
        body = old[2][:2] + "Z" + old[2][3:68]
        self.assert_only_line(2, old, new, body + F._checksum(body))

    def test_exponent_form_writes_one_of_its_fields_into_line_1(self):
        """Kills 3161 (exponent-form changes nothing), 3168 (l[start - 8:68]: a 77-character line), 3152, 3141,
        3128, 3118."""
        got, old, new = self.edit("exponent-form", 1, "1.1606-4", 53)
        self.assertEqual(got, "exponent-form")
        body = old[1][:53] + "1.1606-4" + old[1][61:68]
        self.assert_only_line(1, old, new, body + F._checksum(body))

    def test_letter_in_epoch_writes_a_letter_into_line_1s_epoch(self):
        """Kills 3175 (line 1 skipped, answered "none"), 3181 (l[c - 1:68]: a 71-character line), 3161, 3152, 3141,
        3128, 3118."""
        got, old, new = self.edit("letter-in-epoch", 1, "O", n=20)
        self.assertEqual(got, "letter-in-epoch")
        body = old[1][:20] + "O" + old[1][21:68]
        self.assert_only_line(1, old, new, body + F._checksum(body))

    def test_letter_in_epoch_leaves_line_2_alone(self):
        """Kills 3175 (a letter put into line 2's inclination and node columns)."""
        data = seed_text("tle")
        out, got = F._mutate(data, "tle", Pick("letter-in-epoch", 2, "O", n=20))
        self.assertEqual((out, got), (data, "none"))


class ReplaceValue(unittest.TestCase):
    def test_kvn_gets_its_value_replaced_bare(self):
        """Kills 3199 (KVN sent to the CSV branch), 3209 (None whenever the pattern matches), 3210 (NaN quoted
        outside JSON)."""
        text = seed_text("kvn").decode("utf-8")
        self.assertEqual(text.count("= 0.00075989"), 1)
        out = F._replace_value(text, "kvn", Pick("BSTAR"), "NaN")
        self.assertEqual(out, text.replace("= 0.00075989", "= NaN"))

    def test_xml_gets_its_value_replaced_inside_the_element(self):
        """Kills 3199 (XML given the KVN pattern), 3200 (XML sent to the CSV branch), 3209."""
        text = seed_text("xml").decode("utf-8")
        self.assertEqual(text.count("<BSTAR>0.00075989<"), 1)
        out = F._replace_value(text, "xml", Pick("BSTAR"), "NaN")
        self.assertEqual(out, text.replace("<BSTAR>0.00075989<", "<BSTAR>NaN<"))

    def test_json_quotes_nan_and_empty_and_leaves_an_overflow_a_number(self):
        """Kills 3199, 3200 (JSON given another format's pattern), 3201 (JSON sent to the CSV branch), 3209, 3210
        (NaN and empty written bare: no JSON), 3211 (1e999 quoted: a string, not an overflowing number)."""
        text = seed_text("json").decode("utf-8")
        self.assertEqual(text.count('"BSTAR":0.00075989'), 1)
        for new, written in (("NaN", '"NaN"'), ("", '""'), ("1e999", "1e999")):
            with self.subTest(new=new):
                out = F._replace_value(text, "json", Pick("BSTAR"), new)
                self.assertEqual(out, text.replace('"BSTAR":0.00075989', '"BSTAR":' + written))

    def test_a_crlf_csv_gets_one_value_replaced_and_keeps_its_line_endings(self):
        """Kills 3199, 3200, 3201 (CSV given another format's pattern), 3202 (a CRLF file split on LF: the row
        rewritten without its CR), 3206 (None whenever the key is there), 3207 (None whenever there are rows)."""
        text = seed_text("csv").decode("utf-8")
        self.assertEqual(text.count(",0.00075989,"), 1)
        out = F._replace_value(text, "csv", Pick("BSTAR"), "NaN")
        self.assertEqual(out, text.replace(",0.00075989,", ",NaN,"))
        self.assertEqual(out.count("\r\n"), text.count("\r\n"))

    def test_an_lf_csv_gets_one_value_replaced(self):
        """Kills 3202 (an LF file read as one line, so no rows: None)."""
        head = ",".join(F.NUMBER_KEYS)
        text = head + "\n" + ",".join(["1"] * len(F.NUMBER_KEYS)) + "\n"
        row = ["1"] * len(F.NUMBER_KEYS)
        row[F.NUMBER_KEYS.index("BSTAR")] = "NaN"
        out = F._replace_value(text, "csv", Pick("BSTAR"), "NaN")
        self.assertEqual(out, head + "\n" + ",".join(row) + "\n")

    def test_a_csv_without_the_key_or_without_rows_gives_none(self):
        """Kills 3205 (head.index of a missing key raises ValueError; a header-only file reaches rng.choice([])),
        3207 (a header-only file reaches rng.choice([]))."""
        self.assertIsNone(F._replace_value("NORAD_CAT_ID\r\n5\r\n", "csv", Pick("BSTAR"), "NaN"))
        self.assertIsNone(F._replace_value(",".join(F.NUMBER_KEYS) + "\r\n", "csv", Pick("BSTAR"), "NaN"))


def crashes_on(*needles):
    """A parser, guarded as the fuzz run guards it, that exits (a "crash") when every needle is in the input and
    otherwise returns no records."""
    class P(Reference):
        def parse(self, raw, fmt):
            if all(n in raw for n in needles):
                raise SystemExit(1)
            return []
    return _Guarded(P(), [])


class Minimise(unittest.TestCase):
    def test_a_crash_on_one_byte_is_cut_to_that_byte(self):
        """Kills 3279 (cur[j:j - 1] is b'': the result is empty), 3285 (size 1 never tried: stops at b'Xb'), 3298
        (any candidate accepted unasked: ends at b'c', another category)."""
        parser = crashes_on(b"X")
        small = F.minimise(parser, b"aaa\nbXb\nccc", "tle", "crash")
        self.assertEqual(small, b"X")
        self.assertEqual(F.classify(parser, small, "tle")[0], "crash")

    def test_a_crash_needing_two_lines_is_cut_by_characters_too(self):
        """Kills 3284 (the line pass goes on at size 0 until the budget is spent, so no character pass:
        b'aXa\\nbYb' kept)."""
        small = F.minimise(crashes_on(b"X", b"Y"), b"aXa\nbYb\nccc", "tle", "crash")
        self.assertEqual(small, b"XY")

    def test_a_sweep_that_removes_nothing_halves_the_chunk(self):
        """Kills 3291 (shrunk starts True: size 2 repeated until the budget is gone), 3302 (size halved only after
        a removal), 3285 (size 1 never tried): b'aXXa' would stay b'aXXa'."""
        small = F.minimise(crashes_on(b"XX"), b"aXXa", "tle", "crash")
        self.assertEqual(small, b"XX")


if __name__ == "__main__":
    unittest.main()
