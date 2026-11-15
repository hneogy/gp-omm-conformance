# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Tests that pin survivors of the 0.9.0 mutation run, named by mutant number in
docs/handoff/mutation-survivors-0.9.0-triage.md (D-520): each passes on the code and fails
under its mutant. The checks are driven directly, with hand-made records, items and files, so no provider data is
needed: describe_bytes' guesses, the field-form checks' counts and texts, the gate's per-format state and its
live-capture label, the element-set-zero presence filter and the CSV/JSON constant-metadata check.

Run: python -m unittest tests.test_triage_090_checks"""
import json
import os
import sys
import tempfile
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import gates  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import CaseResult, Item, Runner, describe_bytes  # noqa: E402

HTML = b"<!DOCTYPE html>\n<html><body>Forbidden</body></html>\n"
CSV_FILE = gates.GATES[0]["formats"]["csv"]["file"]


def runner():
    return Runner(Reference(), root=ROOT, fetch_hints=False)


def items_of(res, check):
    return [(i.status, i.detail) for i in res.items if i.check == check]


class DescribeBytesGuesses(unittest.TestCase):
    """The guesses a file the reference reader cannot read is described with (D-113). The two guesses no file reaches
    in 0.9.0 (CelesTrak's empty-response text, a TLE line 1 without a line 2) are kept by the owner; only their absence
    from other files is pinned here."""

    def test_an_html_page_is_only_an_html_page(self):
        """Kills 372, 376, 377 (wrong guesses added to every unreadable file)."""
        d = describe_bytes(HTML, "tle")
        self.assertIn("HTML document", d)
        self.assertNotIn("whitespace only", d)
        self.assertNotIn("empty-response", d)
        self.assertNotIn("line 1 without", d)

    def test_a_blank_file_is_whitespace_only(self):
        """Kills 372 (a blank file loses its guess)."""
        self.assertIn("whitespace only", describe_bytes(b" \n \n", "tle"))

    def test_a_bare_html_page_without_a_doctype_is_html(self):
        """Kills 374 (HTML guessed only with both a doctype and <html)."""
        self.assertIn("HTML document", describe_bytes(b"<html><body>Forbidden</body></html>\n", "tle"))

    def test_an_empty_file_is_no_html_page(self):
        """Kills 375 (every file without <html called an HTML document)."""
        d = describe_bytes(b"", "kvn")
        self.assertIn("empty file", d)
        self.assertNotIn("HTML document", d)

    def test_a_csv_header_line_is_header_only(self):
        """Kills 382, 384 (a one-line header with commas loses the guess)."""
        self.assertIn("CSV header only", describe_bytes(b"OBJECT_NAME,OBJECT_ID,EPOCH\n", "csv"))

    def test_an_html_page_served_as_csv_is_no_csv_header(self):
        """Kills 380 (every unreadable CSV file called header only)."""
        d = describe_bytes(HTML, "csv")
        self.assertIn("HTML document", d)
        self.assertNotIn("CSV header", d)


class FieldFormCounts(unittest.TestCase):
    """check_field_forms' pass texts count the values compared, the values within tolerance and the records with a
    negative BSTAR or first derivative (D-118)."""

    ORACLE = {1: {"bstar": Decimal("0.0001"), "mean_motion_ddot": Decimal("0")}}
    IMPLIED = "2 BSTAR and second-derivative fields with an implied decimal point and exponent decoded to the expected values"

    def implied(self, parsed, oracle=None):
        res = CaseResult("c", "c")
        runner().check_field_forms(res, "x.tle", "tle", parsed, oracle or self.ORACLE, {"bstar-implied-decimal-exponent"})
        return items_of(res, "bstar-implied-decimal-exponent")

    def test_an_exact_parser_counts_each_value_once_and_none_within_tolerance(self):
        """Kills 681, 693 (the count of values compared), 682, 698 (a tolerance count for exact values)."""
        got = self.implied([{"norad_cat_id": 1, "bstar": Decimal("0.0001"), "mean_motion_ddot": Decimal("0")}])
        self.assertEqual(got, [("pass", self.IMPLIED)])

    def test_nothing_compared_gives_no_item(self):
        """Kills 681 (an item with nothing compared)."""
        self.assertEqual(self.implied([{"norad_cat_id": 2, "bstar": Decimal("0.0001"), "mean_motion_ddot": Decimal("0")}]), [])

    def test_one_float_within_tolerance_is_counted_once(self):
        """Kills 699 (the tolerance count doubled), 682."""
        got = self.implied([{"norad_cat_id": 1, "bstar": Decimal("0.00010000000000001"), "mean_motion_ddot": Decimal("0"),
                             "_notes": {"bstar": "float"}}])
        self.assertEqual(got, [("pass", self.IMPLIED + "; 1 within tolerance")])

    def test_a_record_the_oracle_does_not_hold_is_skipped(self):
        """Kills 683 (an id outside the oracle compared: KeyError)."""
        got = self.implied([{"norad_cat_id": 1, "bstar": Decimal("0.0001"), "mean_motion_ddot": Decimal("0")},
                            {"norad_cat_id": 99, "bstar": Decimal("0.5"), "mean_motion_ddot": Decimal("0")}])
        self.assertEqual(got, [("pass", self.IMPLIED)])

    NEG_ORACLE = {1: {"bstar": Decimal("0"), "mean_motion_dot": Decimal("0.0001")},
                  2: {"bstar": Decimal("-0.0001"), "mean_motion_dot": Decimal("0")}}
    NEG = "1 record with a negative BSTAR or first derivative: sign and value preserved"

    def negative(self, parsed):
        res = CaseResult("c", "c")
        runner().check_field_forms(res, "x.tle", "tle", parsed, self.NEG_ORACLE, {"negative-bstar-and-ndot"})
        return items_of(res, "negative-bstar-and-ndot")

    def test_only_a_record_with_a_negative_value_is_counted(self):
        """Kills 713, 715, 716 (zero or positive values taken as negative)."""
        got = self.negative([{"norad_cat_id": 1, "bstar": Decimal("0"), "mean_motion_dot": Decimal("0.0001")},
                             {"norad_cat_id": 2, "bstar": Decimal("-0.0001"), "mean_motion_dot": Decimal("0")}])
        self.assertEqual(got, [("pass", self.NEG)])

    def test_a_record_without_a_negative_value_is_not_compared(self):
        """Kills 683 (records outside the negative ids compared)."""
        got = self.negative([{"norad_cat_id": 1, "bstar": Decimal("0.5"), "mean_motion_dot": Decimal("0.0001")},
                             {"norad_cat_id": 2, "bstar": Decimal("-0.0001"), "mean_motion_dot": Decimal("0")}])
        self.assertEqual(got, [("pass", self.NEG)])


class GateFormatState(unittest.TestCase):
    """format_result's state for one format from hand-made items (D-142, D-148, D-325)."""

    def test_a_failure_that_is_no_parse_failure_is_not_run(self):
        """Kills 1862 (any failing item read as the parser raising)."""
        got = gates.format_result([Item("source-readable", "fail", CSV_FILE, "reference reader found 0 of 256 expected records")])
        self.assertEqual(got, {"state": "not run"})

    def test_an_unreadable_value_is_said_so(self):
        """Kills 1865 (the D-325 note never chosen)."""
        got = gates.format_result([Item("parse", "fail", CSV_FILE,
                                        "the parser returned a value the runner cannot read: the answer is dict, not a list of records")])
        self.assertEqual(got["note"], "the runner could not read a value the parser returned")

    def test_a_declared_unsupported_format_is_not_read(self):
        """Kills 1870, 1871 (the format-supported skip falling through to not run)."""
        got = gates.format_result([Item("format-supported", "skip", CSV_FILE, "parser reports csv unsupported")])
        self.assertEqual(got, {"state": "not read"})

    def test_a_format_supported_failure_is_not_run(self):
        """Kills 1869 (a format-supported item matched on its check alone): under D-280 a skip becomes a fail when the
        parser read the same format elsewhere, and that is no declared-unsupported fact."""
        got = gates.format_result([Item("format-supported", "fail", CSV_FILE, "parser reports csv unsupported (D-280)")])
        self.assertEqual(got, {"state": "not run"})

    def test_another_checks_skip_is_not_run(self):
        """Kills 1869 (any skip item read as not read)."""
        got = gates.format_result([Item("empty-answer-yields-no-records", "skip", CSV_FILE, "parser reports csv unsupported")])
        self.assertEqual(got, {"state": "not run"})


class GateLiveCapture(unittest.TestCase):
    """A measured live capture is labelled with the fetch date from the data root's metadata (D-148)."""

    def test_a_live_capture_carries_its_fetch_date_from_the_data_root(self):
        """Kills 1896, 1897 (no live label for a measured live capture), 1899 (the metadata read from the corpus root)."""
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as data:
            case = gates.GATES[0]["snapshot_from"]["case"]
            os.makedirs(os.path.join(root, "fixtures", case))
            with open(os.path.join(root, "fixtures", case, "expected.json"), "w", encoding="utf-8") as f:
                json.dump({"records": [{"norad_cat_id": 100000}, {"norad_cat_id": 100001}], "sources": {}}, f)
            os.makedirs(os.path.dirname(os.path.join(data, CSV_FILE)))
            with open(os.path.join(data, CSV_FILE + ".meta.json"), "w", encoding="utf-8") as f:
                json.dump({"retrieved_at": "2026-09-26T08:00:00Z"}, f)   # under the data root only
            res = CaseResult(gates.GATES[0]["formats"]["csv"]["case"], "t")
            res.items.append(Item("values", "pass", CSV_FILE, counts={"expected": 2, "returned": 2, "loaded": 2,
                                                                     "misidentified": 0, "dropped": 0}))
            res.modes[CSV_FILE] = "live"
            (g,) = gates.compute_gates([res], root, data)
        self.assertEqual(g["formats"]["csv"]["live"], {"retrieved_at": "2026-09-26T08:00:00Z"})
        self.assertIn("live capture fetched 2026-09-26", g["headline"])


class ElementSetZeroFilter(unittest.TestCase):
    """The element-set-zero-and-rev-one presence check reads the records with element set 0 or revolution 0 or 1."""

    def test_the_filter_takes_set_zero_and_rev_zero_and_one_only(self):
        """Kills 792, 793, 794, 795, 796, 797 (the filter's members): C is outside the filter and wrong."""
        refrecs = [{"norad_cat_id": 1, "element_set_no": 0, "rev_at_epoch": 100},
                   {"norad_cat_id": 2, "element_set_no": 999, "rev_at_epoch": 1},
                   {"norad_cat_id": 3, "element_set_no": 999, "rev_at_epoch": 100},
                   {"norad_cat_id": 4, "element_set_no": 999, "rev_at_epoch": 0}]
        parsed = [dict(r) for r in refrecs]
        parsed[2]["element_set_no"] = 998
        res = CaseResult("c", "c")
        runner().check_presence(res, "x.csv", parsed, refrecs, {"element-set-zero-and-rev-one"})
        self.assertEqual(items_of(res, "element-set-zero-and-rev-one"),
                         [("pass", "3 records with element set 0 / rev 0-1 preserved")])


class ConstantMetadata(unittest.TestCase):
    """csv-json-omit-constant-metadata: a CSV/JSON parser may give None or the OMM default, and for MEAN_ELEMENT_THEORY
    SGP4 or SGP/SGP4; anything else is invented (D-285)."""

    def status(self, parsed):
        res = CaseResult("c", "c")
        runner().check_format_facts(res, "x.csv", "csv", parsed, {}, {"csv-json-omit-constant-metadata"})
        ((status, _),) = items_of(res, "csv-json-omit-constant-metadata")
        return status

    def test_sgp4_theory_and_the_defaults_pass(self):
        """Kills 811, 813, 814 (SGP4 theory failed)."""
        self.assertEqual(self.status([{"norad_cat_id": 1, "mean_element_theory": "SGP4", "center_name": "EARTH"}]), "pass")

    def test_another_centre_fails(self):
        """Kills 811 (an invented centre passed)."""
        self.assertEqual(self.status([{"norad_cat_id": 1, "center_name": "MARS"}]), "fail")

    def test_another_theory_fails(self):
        """Kills 812, 814 (any theory passed)."""
        self.assertEqual(self.status([{"norad_cat_id": 1, "mean_element_theory": "SGP8"}]), "fail")

    def test_sgp4_in_another_field_fails(self):
        """Kills 812, 813 (SGP4 accepted in any field)."""
        self.assertEqual(self.status([{"norad_cat_id": 1, "ref_frame": "SGP4"}]), "fail")

    def test_extra_columns_without_the_check_add_no_item(self):
        """Kills 815 (the supgp-extra-keys item added in a case that does not list it)."""
        res = CaseResult("c", "c")
        runner().check_format_facts(res, "x.csv", "csv", [{}], {"non_omm_columns": ["RMS"]}, set())
        self.assertEqual(res.items, [])


if __name__ == "__main__":
    unittest.main()
