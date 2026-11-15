# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Tests that pin survivors of the 0.9.0 mutation run the owner ruled must have a test before the release (work list 1),
named by mutant number: each passes on the code and fails under its mutant.

The reference reader's words (the line or entry a refusal names, the absent-metadata list, the eight columns of an
exponent field, an indented element line, text between XML elements) are driven with the 1998 ISS record that
tests/adversarial/test_strict_files_080.py writes from a public expected.json; the runner's pieces (the propagate
answer, norm_record, TolStats, CaseResult, the checks and compare_values) are driven directly with hand-made records,
items and files, or with the one record of the shipped alpha5-A-100000-saramago-first.tle, so no provider data is needed.

Run: python -m unittest tests.test_must_090_1"""
import json
import os
import sys
import tempfile
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import reference as ref  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import (CaseResult, Runner, TolStats, UnreadableValue, _propagate_answer,  # noqa: E402
                           leading_dot_keywords, norm_record)
from tests.adversarial.test_strict_files_080 import (LINES, column, csv_text, json_text, kvn_text,  # noqa: E402
                                                     tle_text, xml_text)

ALPHA5 = os.path.join(ROOT, "derived", "alpha5-tle", "alpha5-A-100000-saramago-first.tle")


def runner(data=None):
    return Runner(Reference(), root=ROOT, data=data, fetch_hints=False)


def items_of(res, check):
    return [(i.status, i.detail) for i in res.items if i.check == check]


class _Rejects(unittest.TestCase):
    def rejects(self, reader, text, *words):
        with self.assertRaises(ValueError) as cm:
            reader(text)
        for w in words:
            self.assertIn(w, str(cm.exception))
        return str(cm.exception)


class TheReferenceReaderNamesTheRightPlace(_Rejects):
    """A refusal names the line, entry or field the fault is in: the number a user reads to find it."""

    def test_a_card_fault_names_its_own_tle_line(self):
        """Kills 2238 (a card-image fault in line 1 reported as line 2), 2239 (one in line 2 reported as line 3)."""
        l0, l1, l2 = tle_text().splitlines()
        self.rejects(ref.read_tle_text, f"{l0}\n{l1}0\n{l2}\n", "TLE line 1 is 70 columns", "column 70")
        self.rejects(ref.read_tle_text, f"{l0}\n{l1}\n{l2}0\n", "TLE line 2 is 70 columns", "column 70")

    def test_a_second_derivative_one_column_over_is_refused(self):
        """Kills 2300 (the second derivative read from nine columns, so '  1234-5' over columns 45 to 52 is read as
        0.1234E-5, its eight-column rule lost)."""
        self.rejects(ref.read_tle_text, tle_text(column(LINES[1], 44, 52, "  1234-5")), "TLE second derivative field", "is not a number")
        self.assertEqual(len(ref.read_tle_text(tle_text(column(LINES[1], 44, 52, "+11563-4")))), 1)       # twin: the format's form

    def test_an_indented_line_one_is_an_element_line(self):
        """Kills 2342 (an element line after leading blanks taken for a name line, so an indented line 1 at a file's
        end is passed over and its set goes missing, D-336)."""
        self.assertEqual(ref.element_line("  1 " + "X" * 30), "1")
        self.assertEqual(ref.element_line("  2 " + "X" * 30), "2")
        name, l1, l2 = LINES[0].rstrip(), tle_text().splitlines()[1], tle_text().splitlines()[2]
        self.rejects(ref.read_tle_text, f"{name}\n{l1}\n{l2}\n {l1}\n", "TLE line 4", "pairs with nothing")
        self.assertIsNone(ref.element_line("1 SATELLITE"))                                                # twin: a short name

    def test_a_json_entry_that_is_no_object_is_named_by_its_place(self):
        """Kills 2407 (JSON entries counted from 2, so the first entry is refused as entry 2)."""
        self.rejects(ref.read_json_text, "[5]", "JSON entry 1 is int, not an object")
        self.rejects(ref.read_json_text, "[{}, 5]", "JSON entry 2 is int, not an object")

    def test_a_kvn_refusal_names_its_line(self):
        """Kills 2470 (KVN lines counted from 2, so every KVN refusal names a line one too high)."""
        self.rejects(ref.read_kvn_text, "CCSDS_OMM_VERS = 2.0\nnot a keyword line\n", "KVN line 2 is neither")

    def test_text_after_a_metadata_element_is_refused(self):
        """Kills 2438 (the metadata block left out of the text-between-elements check, so
        '<OBJECT_NAME>...</OBJECT_NAME>junk' is read)."""
        self.rejects(ref.read_xml_text, xml_text().replace("</OBJECT_NAME>", "</OBJECT_NAME>junk", 1),
                     "XML element metadata", "holds text between its elements")


class TheAbsentMetadataList(unittest.TestCase):
    """The csv-json-omit-constant-metadata pass detail says which mandatory metadata keywords the file leaves out."""

    ABSENT = ["CENTER_NAME", "REF_FRAME", "TIME_SYSTEM", "MEAN_ELEMENT_THEORY"]   # CelesTrak's columns carry the other two

    def test_csv_names_the_columns_it_lacks(self):
        """Kills 2398 (the CSV list inverted: it names the metadata columns the file has)."""
        _, facts = ref.read_csv_text(csv_text())
        self.assertEqual(facts["omm_mandatory_metadata_absent"], self.ABSENT)

    def test_json_names_the_keys_it_lacks(self):
        """Kills 2419 (the JSON list inverted: it names the metadata keys the file has)."""
        _, facts = ref.read_json_text(json_text())
        self.assertEqual(facts["omm_mandatory_metadata_absent"], self.ABSENT)


class ThePropagateAnswer(unittest.TestCase):
    def test_an_answer_that_is_no_container_is_handed_on_as_it_is(self):
        """Kills 26 ('and' made 'or': a hook answering None, a forgotten return, or a number is read as an iterable and
        raises TypeError, reported as the parser's raise)."""
        self.assertIsNone(_propagate_answer(None))
        self.assertEqual(_propagate_answer(5), 5)
        self.assertEqual(_propagate_answer(1.5), 1.5)


class ABoolIsNoElementValue(unittest.TestCase):
    def test_true_and_false_are_held_to_the_grammar(self):
        """Kills 104 (a bool in an element field read as Decimal 1 or 0, so True for an inclination of 1 deg passes)."""
        for bad in (True, False):
            with self.subTest(value=bad):
                with self.assertRaises(UnreadableValue) as cm:
                    norm_record({"inclination": bad})
                self.assertIn("is not a plain decimal number", str(cm.exception))
        self.assertEqual(norm_record({"inclination": 1})[0]["inclination"], Decimal(1))                   # twin: an int


class TheToleranceTally(unittest.TestCase):
    def test_counts_mean_max_and_units(self):
        """Kills 155 (the count starts at 1), 157 (each pass counted twice), 158 (the signed sum added into the max slot),
        159 (the signed sum always 0), 162 (the max always 0), 163 (epoch labelled rel, decimals us), 164 (n written as
        the signed sum), 165 (mean_signed from the max), 166 (mean_signed as sum / sum)."""
        t = TolStats()
        t.add("epoch", 2.0)
        t.add("epoch", -4.0)
        t.add("inclination", 2e-13)
        self.assertEqual(t.as_dict(), {"epoch": {"n": 2, "mean_signed": -1.0, "max_abs": 4.0},
                                       "inclination": {"n": 1, "mean_signed": 2e-13, "max_abs": 2e-13}})
        self.assertEqual(t.text(), "within tolerance: epoch n=2 mean=-1us max=4us; inclination n=1 mean=+2e-13rel max=2e-13rel")


class ACaseResultAndItsCounts(unittest.TestCase):
    def test_a_data_caused_not_exercised_item_leaves_a_pass(self):
        """Kills 338 (a data-caused not-exercised item counted as voided by the parser, so the case reads
        not-exercised), 361 (every case's counts start with info 1)."""
        r = CaseResult("c", "t", purpose=("a", "b"))
        r.add("a", "not-exercised", cause="data")
        r.add("b", "pass")
        self.assertEqual(r.voided_by_parser(), [])
        self.assertEqual(r.status, "pass")
        self.assertEqual(r.counts(), {"pass": 1, "pass-tolerance": 0, "fail": 0, "skip": 0, "not-exercised": 1,
                                      "not-fetched": 0, "not-available": 0, "info": 0})
        v = CaseResult("c", "t", purpose=("a",))                                                          # twin: the parser's
        v.add("a", "not-exercised", cause="parser")
        self.assertEqual((v.voided_by_parser(), v.status), (["a"], "not-exercised"))


class LeadingDotKeywords(unittest.TestCase):
    def test_only_a_value_written_without_its_leading_zero_counts(self):
        """Kills 366 ('and' made 'or': every non-empty CSV header counted as a leading-dot keyword)."""
        self.assertEqual(leading_dot_keywords("MEAN_MOTION,ECCENTRICITY\n15.5,.0006\n", "csv"), {"ECCENTRICITY"})


class AnUnexpectedResponsesReason(unittest.TestCase):
    PATH = "fixtures/some-case/raw/a.csv"

    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix="gpconf-must-090-1-")
        self.addCleanup(d.cleanup)
        self.data = d.name
        os.makedirs(os.path.dirname(os.path.join(self.data, self.PATH)))

    def kept(self, meta):
        full = os.path.join(self.data, self.PATH)
        with open(full + ".unexpected", "wb") as f:
            f.write(b"<!DOCTYPE html>\n<html><body>Forbidden</body></html>\n")
        with open(full + ".unexpected.meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f)
        return runner(self.data).unexpected_response(self.PATH)

    def test_the_recorded_reason_is_kept(self):
        """Kills 408 ('or' made 'and': the fetch's recorded reason replaced by 'HTTP <status>')."""
        self.assertEqual(self.kept({"http_status": 200, "unexpected": "no-data text where data is recorded"})["why"],
                         "no-data text where data is recorded")

    def test_with_no_reason_recorded_the_status_is_named(self):
        """Kills 408 (with no reason recorded the reason is None, and the item says the fetch got None)."""
        self.assertEqual(self.kept({"http_status": 403})["why"], "HTTP 403")


class TheSurplusCheck(unittest.TestCase):
    def test_a_record_whose_id_is_no_integer_is_not_also_one_without_an_id(self):
        """Kills 485 ('-' made '+': a record whose norad_cat_id is not an integer also adds '... without norad_cat_id')."""
        res = CaseResult("c", "c")
        runner().check_surplus(res, "x.csv", [{"norad_cat_id": None, "_bad": {"norad_cat_id": "'x' (str)"}}], [{"norad_cat_id": 1}])
        ((status, detail),) = items_of(res, "records-returned")
        self.assertEqual(status, "fail")
        self.assertIn("1 record whose norad_cat_id is not an integer", detail)
        self.assertNotIn("without norad_cat_id", detail)
        res = CaseResult("c", "c")                                                                        # twin: no id at all
        runner().check_surplus(res, "x.csv", [{"norad_cat_id": None}], [{"norad_cat_id": 1}])
        self.assertIn("1 record without norad_cat_id", items_of(res, "records-returned")[0][1])


class CompareValuesWords(unittest.TestCase):
    """compare_values driven directly with the one record of a shipped derived TLE file (id 100000)."""

    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix="gpconf-must-090-1-")
        self.addCleanup(d.cleanup)
        self.runner = runner(d.name)
        (self.rec,) = self.runner.parse(ALPHA5, "tle")
        self.want = {k: v for k, v in self.rec.items() if not k.startswith("_")}
        self.wrong = str(Decimal(str(self.rec["mean_motion"])) + 1)

    def values_item(self, parsed, oracle, res=None, **kw):
        res = res or CaseResult("x", "x")
        self.runner.compare_values(res, ALPHA5, "tle", "live", parsed, oracle, **kw)
        (item,) = [i for i in res.items if i.check == "values"]
        return item

    def test_a_dropped_compared_record_is_not_also_outside_the_subset(self):
        """Kills 547 ('and' made 'or': on a partly frozen file a dropped compared record is also counted 'outside the
        compared subset neither returned nor refused')."""
        outside = dict(self.rec, norad_cat_id=25544)
        item = self.values_item([outside], {100000: self.want}, partial=True, held_in_file={100000: 1, 25544: 1})
        self.assertEqual(item.status, "fail")
        self.assertIn("1 expected record not returned", item.detail)
        self.assertNotIn("outside the compared subset", item.detail)

    def test_a_surplus_copy_where_nothing_is_held_reads_once(self):
        """Kills 606 (with held None a surplus copy reads 'where the input holds it 2 times')."""
        item = self.values_item([dict(self.rec), dict(self.rec, mean_motion=self.wrong)], {100000: self.want})
        self.assertEqual(item.status, "fail")
        self.assertIn("returned 2 times where the input holds it once (D-311)", item.detail)

    def test_an_id_held_twice_with_the_same_record_is_no_repeat_that_differs(self):
        """Kills 613 ('and' made 'or': an input holding an id twice with identical records said to hold it 'with records
        that differ')."""
        oracle = {100000: dict(self.want, _copies=[dict(self.want), dict(self.want)])}
        item = self.values_item([dict(self.rec), dict(self.rec)], oracle, held={100000: 2})
        self.assertEqual(item.status, "pass")
        self.assertNotIn("with records that differ", item.detail)

    def test_a_record_refused_with_a_reason_is_counted_once(self):
        """Kills 648 (ids_not_returned off by twice the refused count), 650 (refused_without_reason counting the refusals
        with a reason too)."""
        res = CaseResult("x", "x")
        res.refusals[ALPHA5] = [{"reason": "this set is too old", "ok": True, "field": "100000", "input": None, "id": 100000}]
        item = self.values_item([], {100000: self.want}, res=res)
        self.assertEqual(item.status, "fail")
        self.assertEqual((item.counts["refused"], item.counts["refused_matched"]), (1, 1))
        self.assertEqual(item.counts["ids_not_returned"], 0)
        self.assertEqual(item.counts["refused_without_reason"], 0)


class TheOracleLabel(unittest.TestCase):
    def test_live_bytes_and_withheld_snapshot_values_are_told_apart(self):
        """Kills 670 ('and' made 'or': a live file of a records-withheld case labelled snapshot values withheld), 671
        ('==' made '!=': the snapshot of such a case labelled live bytes)."""
        exp = {"records_withheld": True, "records": []}
        _, live, _ = runner().oracle_for(exp, "fixtures/c/raw/a.tle", "tle", "live", [])
        _, snap, _ = runner().oracle_for(exp, "fixtures/c/raw/a.tle", "tle", "snapshot", [])
        self.assertIn("live bytes", live)
        self.assertNotIn("withheld", live)
        self.assertIn("withheld from the public release", snap)
        self.assertNotIn("live bytes", snap)


class TheFieldFormCounts(unittest.TestCase):
    ORACLE = {1: {"bstar": Decimal("0.0001"), "mean_motion_ddot": Decimal("0")}}
    IMPLIED = "2 BSTAR and second-derivative fields with an implied decimal point and exponent decoded to the expected values"

    def test_an_exact_parser_has_none_within_tolerance(self):
        """Kills 682 (the tolerance count starts at 1), 698 ('==' made '!=': every exact value counted within
        tolerance)."""
        res = CaseResult("c", "c")
        runner().check_field_forms(res, "x.tle", "tle", [{"norad_cat_id": 1, "bstar": Decimal("0.0001"), "mean_motion_ddot": Decimal("0")}],
                                   self.ORACLE, {"bstar-implied-decimal-exponent"})
        self.assertEqual(items_of(res, "bstar-implied-decimal-exponent"), [("pass", self.IMPLIED)])


class TheNineDigitItem(unittest.TestCase):
    PARSED = [{"norad_cat_id": 799501621, "_notes": {"norad_cat_id": "int"}}]

    def nine(self, active, parsed=None):
        res = CaseResult("c", "c")
        runner().check_ints(res, "x.csv", parsed or self.PARSED, active)
        return [s for s, _ in items_of(res, "nine-digit-ids-parse")]

    def test_the_item_is_added_only_where_the_case_lists_it(self):
        """Kills 726 ('in' made 'not in': the nine-digit case gets no pass item, other cases an unlisted one), 728
        ('or' made 'and': the nine-digit pass item never added)."""
        self.assertEqual(self.nine({"nine-digit-ids-parse", "catalog-number-is-integer"}), ["pass"])
        self.assertEqual(self.nine({"catalog-number-is-integer"}), [])
        self.assertEqual(self.nine({"nine-digit-ids-parse"}, [{"norad_cat_id": 100000000, "_notes": {"norad_cat_id": "int"}}]), ["pass"])


class TheTleLineChecks(unittest.TestCase):
    @staticmethod
    def refrec(i, checksums_valid=True):
        return {"norad_cat_id": i, "tle": {"checksums_valid": checksums_valid, "line_lengths": [0, 69, 69],
                                           "catalog_field_is_alpha5": False}}

    def test_a_bad_checksum_on_69_column_lines_fails(self):
        """Kills 731 ('or' made 'and': a bad checksum on lines of the right length reported 'all checksums valid')."""
        res = CaseResult("c", "c")
        runner().check_tle_lines(res, "x.tle", [{"norad_cat_id": 1}], [self.refrec(1, False)], {"tle-checksums-valid"})
        self.assertEqual([s for s, _ in items_of(res, "tle-checksums-valid")], ["fail"])

    def test_a_refusal_without_a_reason_is_a_drop(self):
        """Kills 741 ('and' made 'or': a refusal with no reason of an expected id counted as refused, so the dropped
        record no longer fails tle-catalog-field-decodes)."""
        for ok, status in ((False, "fail"), (True, "pass")):                                              # twin: with a reason
            with self.subTest(reason=ok):
                res = CaseResult("c", "c")
                res.refusals["x.tle"] = [{"id": 2, "ok": ok, "reason": "too old" if ok else None}]
                runner().check_tle_lines(res, "x.tle", [{"norad_cat_id": 1}], [self.refrec(1), self.refrec(2)],
                                         {"tle-catalog-field-decodes"})
                self.assertEqual([s for s, _ in items_of(res, "tle-catalog-field-decodes")], [status])


class TheOmmFormatsAgree(unittest.TestCase):
    REFRECS = [{"norad_cat_id": 1}]

    def agree(self, csv_parsed, json_parsed):
        res = CaseResult("c", "c")
        runner().check_set_relations(res, {}, "the set", {"a.csv": ("ok", "csv", csv_parsed, self.REFRECS),
                                                          "a.json": ("ok", "json", json_parsed, self.REFRECS)},
                                     {"omm-formats-agree"})
        ((status, detail),) = items_of(res, "omm-formats-agree")
        return status, detail

    def test_the_ids_compared_are_the_parsers(self):
        """Kills 837 (the ids taken from the reference records: an id the parser makes up is never compared, so a
        disagreement on it passes, and the count of records agreed on changes)."""
        recs = [{"norad_cat_id": 1, "mean_motion": Decimal("15.5")}, {"norad_cat_id": 5, "mean_motion": Decimal("15.5")},
                {"norad_cat_id": None, "mean_motion": Decimal("15.5")}]
        self.assertEqual(self.agree(recs, [dict(r) for r in recs]), ("pass", "2 OMM renderings agree on 3 records"))
        other = [dict(r) for r in recs]
        other[1]["mean_motion"] = Decimal("16.5")
        status, detail = self.agree(recs, other)
        self.assertEqual(status, "fail")
        self.assertIn("id 5 mean_motion", detail)


if __name__ == "__main__":
    unittest.main()
