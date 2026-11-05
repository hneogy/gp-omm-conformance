# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The 0.8.0 mutation run's survivors in the catalog-number core that a test can hold with no change to gpconf.

The full run on candidate c (de0c01d) left these mutants alive in `gpconf/writer.py`; each was read as hiding no false
pass on realistic data, and each test here passes on 0.8.0's code and fails under its mutant (D-379):
- i1284, `<= ALPHA5_CEILING` -> `<` in `representable`: 339999 (Z9999) would count as a number the field cannot carry;
- i1283 and i1285, `0 <=` -> `0 <` and `1 <=`: catalog number 0 likewise;
- i1543 and i1566, the `held` defaults for a plain dict as the source: every record "not compared", or every id
  expected twice;
- i1504, `extract_records` reading the strays in place of the records;
and in `gpconf/runner.py`:
- i681, `or` -> `and` in `check_ints`' list of bad records: a catalog number returned as text or as a float passed
  `catalog-number-is-integer` in the facts and XML cases, where that item is the only reader of the id's type;
- i1155, `outcome[cat][0]` -> `[1]` in the corrupt-input case's set of records the parser does not read from the
  unedited file either: a record such a parser returns only from the edited input, the edit's doing, went ungraded.

Run: python -m unittest tests.adversarial.test_mutation_survivors_080"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from gpconf import reference as ref  # noqa: E402
from gpconf import tle as T  # noqa: E402
from gpconf import writer as W  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import Runner  # noqa: E402

SARAMAGO = os.path.join(ROOT, "derived", "alpha5-tle", "alpha5-A-100000-saramago-first.tle")
ISS_RAW = os.path.join(ROOT, "fixtures", "baseline-iss-five-formats", "raw")


def source(ids):
    """A source as `load_against` makes one: each id held once."""
    a = W.Against((i, {}) for i in ids)
    a.held, a.without_id = {i: 1 for i in ids}, 0
    return a


class TheLastNumberTheFieldCarries(unittest.TestCase):
    """i1284: 339999 is Z9999, the field's last value; a source holding it that no file wrote is a failure."""

    def test_339999_is_carried_and_340000_is_not(self):
        self.assertTrue(W.representable(339999))
        self.assertFalse(W.representable(340000))
        self.assertEqual(T.to_alpha5(339999), "Z9999")

    def test_339999_not_written_fails_and_340000_not_written_is_a_correct_refusal(self):
        coverage = W.source_coverage([], source([339999, 340000]))
        self.assertEqual(coverage["not_written"], [(339999, 0, 1)])
        self.assertEqual(coverage["refusal_correct"], [340000])


class CatalogNumberZero(unittest.TestCase):
    """i1283 and i1285: 0 is a number the field carries (00000); a source holding it that no file wrote is a failure."""

    def test_0_is_carried(self):
        self.assertTrue(W.representable(0))
        self.assertFalse(W.representable(-1))

    def test_0_not_written_fails(self):
        coverage = W.source_coverage([], source([0]))
        self.assertEqual(coverage["not_written"], [(0, 0, 1)])
        self.assertEqual(coverage["refusal_correct"], [])


class APlainDictAsTheSource(unittest.TestCase):
    """i1543 and i1566: through the Python API a source may be a plain dict, {id: record}, with no `held`; each of
    its ids is then held once, so each written record is compared and each id expected once."""

    def setUp(self):
        _, records, _ = ref.read_file(SARAMAGO)
        self.record = records[0]
        with open(SARAMAGO, encoding="utf-8") as f:
            self.text = f.read()

    def test_each_written_record_is_compared(self):
        results = W.check_file(self.text, against={self.record["norad_cat_id"]: self.record})
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "pass", results[0])
        self.assertIn("round_trip", results[0])
        self.assertEqual([n for n in results[0]["notes"] if "not compared" in n], [])

    def test_each_id_is_expected_once(self):
        against = {self.record["norad_cat_id"]: self.record, 25544: {}}
        coverage = W.source_coverage(W.check_file(self.text, against=against), against)
        self.assertEqual(coverage["not_written"], [(25544, 0, 1)])
        self.assertEqual((coverage["written_more"], coverage["not_compared"]), ([], []))


class ExtractRecords(unittest.TestCase):
    """i1504: `extract_records` returns the records `scan_lines` finds, not its strays."""

    def test_the_records_of_a_file(self):
        with open(SARAMAGO, encoding="utf-8") as f:
            text = f.read()
        lines = text.splitlines()
        got = W.extract_records(text)
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0][1], got[0][2]), (lines[1], lines[2]))


@unittest.skipUnless(os.path.exists(os.path.join(ISS_RAW, "iss.csv")) and os.path.exists(os.path.join(ISS_RAW, "iss.xml")),
                     "the provider files are not on disk (a fresh clone or an export)")
class ACatalogNumberThatIsNotAnInteger(unittest.TestCase):
    """i681: in the facts case and the XML case a catalog number returned as text ("25544") or as a float (25544.0)
    fails `catalog-number-is-integer`, and the same parser returning integers passes it. Run on the provider data, at
    the runner's default location."""
    CASES = ["csv-json-omitted-mandatory-fields", "omm-xml-schema"]

    def statuses(self, as_type):
        class Adapter(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                for r in out:
                    if "_refused" not in r and isinstance(r.get("norad_cat_id"), int):
                        r["norad_cat_id"] = as_type(r["norad_cat_id"])
                return out
        results = {r.case_id: r for r in Runner(Adapter(), root=ROOT, fetch_hints=False).run(case_ids=self.CASES)}
        return {c: sorted({i.status for i in results[c].items if i.check == "catalog-number-is-integer"}) for c in self.CASES}

    def test_text_and_float_fail_in_both_cases(self):
        for as_type in (str, float):
            for case, statuses in self.statuses(as_type).items():
                self.assertIn("fail", statuses, (as_type.__name__, case))

    def test_integers_pass_in_both_cases(self):
        for case, statuses in self.statuses(int).items():
            self.assertEqual(statuses, ["pass"], case)


class ARecordReturnedOnlyFromTheEditedInput(unittest.TestCase):
    """i1155: in the corrupt-input case a record the parser does not return from the unedited file, and does return
    from the edited one, is the edit's doing and fails the input; its twin, the reference, passes it."""
    EDIT = "26189.7O99"   # c3's letter in line 1's epoch
    C3 = "c3-letter-in-epoch.tle"

    def c3_statuses(self, parser):
        result = {r.case_id: r for r in Runner(parser, root=ROOT, fetch_hints=False).run(case_ids=["corrupt-input"])}["corrupt-input"]
        return sorted({i.status for i in result.items if os.path.basename(i.file or "") == self.C3})

    def test_a_neighbour_read_only_from_the_edited_input_fails_c3(self):
        edit = self.EDIT

        class Adapter(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
                if fmt in ("tle", "2le") and edit not in text:
                    out = [r for r in out if r.get("norad_cat_id") != 20453]   # 20453 left out wherever c3's edit is not
                return out
        self.assertIn("fail", self.c3_statuses(Adapter()))

    def test_the_reference_does_not_fail_c3(self):
        statuses = self.c3_statuses(Reference())
        self.assertTrue(statuses)
        self.assertNotIn("fail", statuses)


if __name__ == "__main__":
    unittest.main()
