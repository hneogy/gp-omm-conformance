# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Tests that pin survivors of the 0.9.0 mutation run, named by mutant number in
docs/handoff/mutation-survivors-0.9.0-triage.md (D-522): the writer case's counts and detail
text in gpconf/runner.py (run_writer), and the reference TLE reader's line splitting and names in gpconf/reference.py.
Each passes on the code and fails under its mutant.

The writer tests call Runner.run_writer on three frozen inputs of the tle-writer-alpha5 case (representable ids with a
zero second derivative), so the counts are small and known. The reader tests write their sets from the frozen 1998 ISS
record of a public expected.json, as tests/adversarial/test_strict_files_080.py does; no provider file is needed.
Run: python -m unittest tests.test_triage_090_writer_reader"""
import json
import os
import sys
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import reference as ref  # noqa: E402
from gpconf import tle as T  # noqa: E402
from gpconf import writer as W  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import CaseResult, Runner, Unsupported  # noqa: E402
from gpconf.words import qty  # noqa: E402

CASE = "tle-writer-alpha5"


def three_inputs():
    """Three frozen, representable writer inputs whose second derivative is zero (so the Reference writer writes the
    zero-exponent sign '+' for each)."""
    with open(os.path.join(ROOT, "fixtures", CASE, "expected.json"), encoding="utf-8") as f:
        recs = json.load(f)["records"]
    picked = [r for r in recs if r["provenance"] == "derived" and r["representable_in_tle"]
              and Decimal(str(r["canonical"].get("mean_motion_ddot") or 0)) == 0][:3]
    assert len(picked) == 3, picked
    return picked


def run_writer(parser, records):
    res = CaseResult(CASE, CASE)
    Runner(parser, root=ROOT, fetch_hints=False).run_writer(None, {"records": records}, res)
    return res, {i.check: i for i in res.items}


def fix(line):
    """A line's first 68 columns with its check digit written again."""
    body = line[:68]
    return body + str(T.checksum(body))


def counts(text):
    """'f: a 1, b 2; g: c 3' -> {'f': [1, 2], 'g': [3]}: the per-field counts a writer item's detail reports."""
    out = {}
    for seg in text.split("; "):
        field, rest = seg.split(": ", 1)
        out[field] = [int(part.rsplit(" ", 1)[1]) for part in rest.split(", ")]
    return out


class OneRecordChanged(Reference):
    """Writes every record as the Reference writer does, and changes the lines of one id through `change`."""

    def __init__(self, cat, change):
        self.cat, self.change = cat, change

    def write_tle(self, record):
        out = Reference.write_tle(self, record)
        if record["norad_cat_id"] != self.cat:
            return out
        l0, l1, l2 = W.normalise_lines(out)
        l1, l2 = self.change(l1, l2)
        return [x for x in (l0, l1, l2) if x is not None]


class AWriterThatAnswersUnsupported(unittest.TestCase):
    def test_the_skip_detail_carries_the_parsers_own_reason(self):
        """Kills 1050, 1051 (the Unsupported reason: replaced by 'no reason given', or never collected)."""
        class NoWriter(Reference):
            def write_tle(self, record):
                raise Unsupported("no TLE writer here")
        _, by = run_writer(NoWriter(), three_inputs())
        item = by["tle-writer-catalog-field"]
        self.assertEqual(item.status, "skip")
        self.assertEqual(item.detail, "parser reports TLE writing unsupported: no TLE writer here")


class TheReferenceWritersCounts(unittest.TestCase):
    def setUp(self):
        self.inputs = three_inputs()
        _, self.by = run_writer(Reference(), self.inputs)

    def test_each_rendering_count_adds_up_to_the_records_read_back(self):
        """Kills 1068 (the round-trip detail's rendering counts, counted down instead of up)."""
        item = self.by["tle-writer-round-trip"]
        self.assertEqual(item.status, "pass", item.detail)
        self.assertNotRegex(item.detail, r" -\d")
        conv = item.detail.split("rendering observed per field: ", 1)[1].rsplit(")", 1)[0]
        per_field = counts(conv)
        self.assertIn("eccentricity", per_field)
        for field, ns in per_field.items():
            self.assertEqual(sum(ns), 3, (field, item.detail))

    def test_each_secondary_field_count_adds_up_to_the_records_written(self):
        """Kills 1071 (the secondary-fields info detail's counts, counted down instead of up)."""
        item = self.by["tle-writer-secondary-fields"]
        self.assertEqual(item.status, "info")
        self.assertNotRegex(item.detail, r" -\d")
        sec = item.detail.split("; zero second-derivative exponent sign: ", 1)[0]
        per_field = counts(sec)
        self.assertEqual(sorted(per_field), sorted(W.SECONDARY_FIELDS))
        for field, ns in per_field.items():
            self.assertEqual(sum(ns), 3, (field, item.detail))

    def test_the_zero_second_derivative_sign_is_counted_once_per_record(self):
        """Kills 1076 (the zero second-derivative sign count, counted down instead of up)."""
        item = self.by["tle-writer-secondary-fields"]
        self.assertIn("; zero second-derivative exponent sign: '+' 3 (CelesTrak writes +, Space-Track -)", item.detail)


class OneRecordWrittenWrong(unittest.TestCase):
    def setUp(self):
        self.inputs = three_inputs()
        self.cat = self.inputs[1]["norad_cat_id"]

    def run_changed(self, change):
        return run_writer(OneRecordChanged(self.cat, change), self.inputs)[1]

    def test_a_record_with_one_line_cut_short_is_not_read_back(self):
        """Kills 1058 (a record with one line of the wrong length went on to the layout and round-trip checks)."""
        by = self.run_changed(lambda l1, l2: (l1, l2[:68]))
        lines = by["tle-checksums-valid"]
        self.assertEqual(lines.status, "fail")
        self.assertTrue(lines.detail.startswith(f"2 of 3 records correct; id {self.cat}: line 2 is 68 characters, not 69"), lines.detail)
        self.assertEqual(by["tle-writer-catalog-field"].status, "pass", by["tle-writer-catalog-field"].detail)
        self.assertEqual(by["tle-writer-column-layout"].detail, f"{qty(2, 'record')} with every field in its fixed columns")
        self.assertEqual(by["tle-writer-round-trip"].status, "pass", by["tle-writer-round-trip"].detail)
        self.assertTrue(by["tle-writer-secondary-not-changed"].detail.startswith(f"{qty(2, 'record')} with each side field kept"),
                        by["tle-writer-secondary-not-changed"].detail)

    def test_a_refused_representable_record_counts_among_the_catalog_fields(self):
        """Kills 1090 (n_real = written - refused_real: the catalog-field detail's 'of N' went wrong)."""
        cat = self.cat

        class RefusesOne(Reference):
            def write_tle(self, record):
                if record["norad_cat_id"] == cat:
                    raise ValueError("cannot encode")
                return Reference.write_tle(self, record)
        _, by = run_writer(RefusesOne(), self.inputs)
        item = by["tle-writer-catalog-field"]
        self.assertEqual(item.status, "fail")
        self.assertTrue(item.detail.startswith(f"2 of 3 catalog fields correct; id {cat} refused although the TLE field can carry it"),
                        item.detail)

    def test_a_field_out_of_its_columns_in_one_record_counts_two_of_three(self):
        """Kills 1097 (the failing column-layout detail's count of correct records)."""
        by = self.run_changed(lambda l1, l2: (fix(l1[:62] + "X" + l1[63:]), l2))   # the ephemeris type, a letter
        item = by["tle-writer-column-layout"]
        self.assertEqual(item.status, "fail")
        self.assertTrue(item.detail.startswith(f"2 of 3 records correct; id {self.cat}: line 1 columns 63-63 (ephemeris type)"),
                        item.detail)

    def test_a_mean_anomaly_one_degree_off_in_one_record_counts_two_of_three(self):
        """Kills 1098 (the failing round-trip detail's count of correct records)."""
        def off(l1, l2):
            ma = (float(l2[43:51]) + 1.0) % 360.0
            return l1, fix(l2[:43] + f"{ma:8.4f}" + l2[51:])
        by = self.run_changed(off)
        self.assertEqual(by["tle-writer-column-layout"].status, "pass", by["tle-writer-column-layout"].detail)
        item = by["tle-writer-round-trip"]
        self.assertEqual(item.status, "fail")
        self.assertTrue(item.detail.startswith(f"2 of 3 records correct; id {self.cat}: mean_anomaly: "), item.detail)

    def test_an_element_set_number_written_as_another_value_counts_two_of_three(self):
        """Kills 1109 (the failing secondary-not-changed detail's count of correct records)."""
        def other(l1, l2):
            g = int(l1[64:68]) % 9999 + 1   # neither the number written, nor zero, nor the record's
            return fix(l1[:64] + f"{g:4d}" + l1[68:]), l2
        by = self.run_changed(other)
        self.assertEqual(by["tle-writer-round-trip"].status, "pass", by["tle-writer-round-trip"].detail)
        item = by["tle-writer-secondary-not-changed"]
        self.assertEqual(item.status, "fail")
        self.assertTrue(item.detail.startswith(f"2 of 3 records correct; id {self.cat}: element_set_no written as another value"),
                        item.detail)


with open(os.path.join(ROOT, "fixtures", "epoch-year-19xx", "expected.json"), encoding="utf-8") as _f:
    _ISS = json.load(_f)["records"][0]["canonical"]   # ISS (ZARYA), 1998-11-20, frozen
_LINES = T.render(T.omm_fields_from_record(_ISS), mantissa_mode="round", ecc_mode="truncate")
NAME, L1, L2 = _LINES[0].rstrip(), fix(_LINES[1]), fix(_LINES[2])


class TheReaderSplitsLines(unittest.TestCase):
    def test_a_last_line_without_a_line_end_is_kept(self):
        """Kills 2071, 2072 (text_lines dropped a last line that has no line end after it)."""
        self.assertEqual(ref.text_lines("a\nb"), ["a", "b"])
        recs = ref.read_tle_text(f"{NAME}\n{L1}\n{L2}")
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["tle"]["line2"], L2)

    def test_a_final_line_end_adds_no_empty_line(self):
        """Kills 2072 (text_lines kept the empty string after a final line end)."""
        self.assertEqual(ref.text_lines("a\n"), ["a"])
        self.assertEqual(ref.text_lines("a\r\nb\r\n"), ["a", "b"])

    def test_a_dos_mark_that_ends_the_last_line_goes_with_the_padding(self):
        """Kills 2075 (the padding was cut at its first line end, not at its DOS mark, leaving the mark in line 2)."""
        recs = ref.read_tle_text(f"{NAME}\r\n{L1}\r\n{L2}\x1a\r\n")
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["tle"]["line2"], L2)


class TheReaderNamesItsSets(unittest.TestCase):
    def test_a_24_character_name_beginning_1_is_a_name(self):
        """Kills 2343 (a name line of exactly 24 characters beginning '1 ' read as an element line)."""
        name = "1 " + "X" * 22
        self.assertEqual(len(name), 24)
        recs = ref.read_tle_text(f"{NAME}\n{L1}\n{L2}\n{name}\n{L1}\n{L2}\n")
        self.assertEqual(len(recs), 2)
        self.assertEqual(recs[1]["object_name"], name)

    def test_a_following_2le_set_takes_no_name_from_the_line_2_before_it(self):
        """Kills 2363 (every set after the first took the line before it as its name, a line 2 among them)."""
        recs = ref.read_tle_text(f"{L1}\n{L2}\n{L1}\n{L2}\n")
        self.assertEqual(len(recs), 2)
        self.assertIsNone(recs[1]["object_name"])
        self.assertIsNone(recs[1]["tle"]["line0"])

    def test_the_first_set_takes_no_name_from_the_files_last_line(self):
        """Kills 2364 (at the file's first line, lines[-1], the file's last line, was taken as the first set's name)."""
        recs = ref.read_tle_text(f"{L1}\n{L2}\nTRAILER\n")
        self.assertEqual(len(recs), 1)
        self.assertIsNone(recs[0]["object_name"])
        self.assertIsNone(recs[0]["tle"]["line0"])


if __name__ == "__main__":
    unittest.main()
