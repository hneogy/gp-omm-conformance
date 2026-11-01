# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""A parser returning more copies of a record's catalog number than the file holds fails the pairs, facts and XML
cases too, which have no values item (D-346, the 0.8.0 plan's 2e, D-311's stated limit), with wrong-on-purpose
adapters and twins.

Before: D-311 failed a surplus copy in the values item, and these cases make none; in a full run another case's values
item read the same files and failed it, but run alone a pairs or facts case passed it (a wrong copy before the right
one, which the TLE/OMM consistency check, reading the last, never saw). The XML case counted its <omm> elements
already and failed a surplus by that count, unless the copy stood in for a dropped record, the count unchanged: such
an answer passed and now fails.

The files are built at test time from the ISS record epoch-year-19xx freezes (no provider's bytes, so the module runs
in the public export). Run: python -m unittest tests.adversarial.test_surplus_cases_080"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import CaseResult, Runner  # noqa: E402
from tests.adversarial.test_history_080 import SETS, csv_text, json_text, tle_text  # noqa: E402
from tests.adversarial.test_strict_files_080 import LIVE, xml_text  # noqa: E402

ONE = SETS[:1]   # the ISS once
FILES = (("iss.tle", tle_text(ONE)), ("iss.csv", csv_text(ONE)), ("iss.json", json_text(ONE)), ("iss.xml", xml_text()))
WORDS = "id 25544: returned 2 times where the input holds it once (D-311)"


def answering(how, fmts):
    """The reference's records, those of the formats named passed through how."""
    class Adapter(Reference):
        def parse(self, raw, fmt):
            out = [r for r in super().parse(raw, fmt) if "_refused" not in r]
            return how(out) if fmt in fmts else out
    return Adapter()


def wrong_first(rs):
    """A wrong copy before the right one: the consistency check reads an id held once by its last copy."""
    return [dict(rs[0], mean_anomaly=str(Decimal(str(rs[0]["mean_anomaly"])) + 7))] + rs


def twice(rs):
    return rs + [dict(rs[0])]


class ASurplusCopyFailsTheCasesWithNoValuesItem(unittest.TestCase):

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-surplus-cases-")
        raw = os.path.join(self.data, LIVE)
        os.makedirs(raw, exist_ok=True)
        for name, text in FILES:
            with open(os.path.join(raw, name), "w", encoding="utf-8", newline="") as f:
                f.write(text)

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def run_case(self, parser, case):
        res = Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=[case])[0]
        return res, [i for i in res.items if i.check == "records-returned"]

    def write(self, name, text, folder=LIVE):
        os.makedirs(os.path.join(self.data, folder), exist_ok=True)
        with open(os.path.join(self.data, folder, name), "w", encoding="utf-8", newline="") as f:
            f.write(text)

    def test_the_twins_a_correct_parser_passes_with_no_new_item(self):
        for case in ("tle-vs-omm-precision-loss", "mean-motion-derivative-convention", "csv-json-omitted-mandatory-fields",
                     "omm-xml-schema"):
            with self.subTest(case=case):
                res, items = self.run_case(Reference(), case)
                self.assertEqual(items, [])
                self.assertNotIn("fail", [i.status for i in res.items], [i.detail for i in res.items if i.status == "fail"])

    def test_a_wrong_copy_before_the_right_one_fails_the_pairs_cases(self):
        for case in ("tle-vs-omm-precision-loss", "mean-motion-derivative-convention"):
            for fmt in ("tle", "csv"):
                with self.subTest(case=case, form=fmt):
                    res, items = self.run_case(answering(wrong_first, (fmt,)), case)
                    self.assertEqual(res.status, "fail")
                    self.assertEqual([(i.status, os.path.basename(i.file), i.detail) for i in items],
                                     [("fail", f"iss.{fmt}", WORDS)])

    def test_a_second_copy_fails_the_facts_and_xml_cases(self):
        for case, fmt in (("csv-json-omitted-mandatory-fields", "csv"), ("csv-json-omitted-mandatory-fields", "json"),
                          ("omm-xml-schema", "xml")):
            with self.subTest(case=case, form=fmt):
                res, items = self.run_case(answering(twice, (fmt,)), case)
                self.assertEqual(res.status, "fail")
                self.assertEqual([(i.status, os.path.basename(i.file), i.detail) for i in items],
                                 [("fail", f"iss.{fmt}", WORDS)])


    def test_a_file_in_two_pairs_is_read_for_its_surplus_once(self):
        """The pairs driver reads a file once for its surplus however many pairs hold it (no pairs list of the corpus
        holds one twice; the list is extended here in memory)."""
        case_id = "tle-vs-omm-precision-loss"
        with open(os.path.join(ROOT, "fixtures", case_id, "expected.json"), encoding="utf-8") as f:
            exp = json.load(f)
        with open(os.path.join(ROOT, "manifest.json"), encoding="utf-8") as f:
            case = next(c for c in json.load(f)["cases"] if c["id"] == case_id)
        exp["case_specific"]["pairs"] = [{"tle_file": "iss.tle", "omm_file": "iss.csv"}, {"tle_file": "iss.tle", "omm_file": "iss-first.csv"}]
        self.write("iss-first.csv", csv_text(ONE), os.path.join("fixtures", "epoch-year-19xx", "raw"))
        res = CaseResult(case_id, case_id)
        Runner(answering(wrong_first, ("tle",)), root=ROOT, data=self.data, fetch_hints=False).run_pairs(case, exp, res)
        self.assertEqual([(i.check, os.path.basename(i.file)) for i in res.items if i.check == "records-returned"],
                         [("records-returned", "iss.tle")])

    def test_an_id_the_file_holds_twice_fails_only_a_third_copy(self):
        self.write("iss.tle", tle_text(SETS[:2]))
        self.write("iss.csv", csv_text(SETS[:2]))
        res, items = self.run_case(Reference(), "tle-vs-omm-precision-loss")
        self.assertEqual(items, [])
        res, items = self.run_case(answering(lambda rs: rs + [dict(rs[0])], ("csv",)), "tle-vs-omm-precision-loss")
        self.assertEqual([i.detail for i in items], ["id 25544: returned 3 times where the input holds it 2 times (D-311)"])

    def test_the_item_names_twelve_ids_at_most(self):
        self.write("iss.csv", csv_text([dict(SETS[0], NORAD_CAT_ID=str(25544 + k)) for k in range(13)]))
        res, items = self.run_case(answering(lambda rs: rs + [dict(r) for r in rs], ("csv",)), "csv-json-omitted-mandatory-fields")
        (item,) = items
        self.assertEqual(item.detail.count("(D-311)"), 12)
        self.assertTrue(item.detail.endswith(" ..."), item.detail)

    def test_a_copy_under_an_id_the_file_does_not_hold_is_no_surplus(self):
        """A copy under another catalog number, or none, is not a surplus of the file's id: it carries no surplus words
        (D-348 fails it in these cases as the values item does, as misidentified; test_misidentified_cases_080)."""
        for name, how in (("another id", lambda rs: rs + [dict(rs[0], norad_cat_id=25544 + 10_000_000)]),
                          ("no id", lambda rs: rs + [{k: v for k, v in rs[0].items() if k != "norad_cat_id"}])):
            with self.subTest(copy=name):
                res, items = self.run_case(answering(how, ("tle",)), "tle-vs-omm-precision-loss")
                self.assertEqual([i for i in items if "(D-311)" in i.detail], [])


if __name__ == "__main__":
    unittest.main()
