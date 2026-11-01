# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""A record under a catalog number the file does not hold, or with none, fails the pairs, facts and XML cases too, in
the values item's words, and the TLE/OMM consistency check no longer passes on no pair where the two files share a
catalog number (D-348, the D-346 reading's finding 1, on the owner's ruling), with wrong-on-purpose adapters and twins.

Before: no check of a pairs case read such a record, nor of the facts or XML case for an integer id in place of one
the file holds, so run alone they passed a wrong copy under another catalog number or with none, a parser that returned
every TLE record without its catalog number, at "0 TLE/OMM pairs consistent", and a record renumbered in place, its
count unchanged (the XML case's count of <omm> elements failed an added copy only). In a full run the record's own
case's values item failed each.

The files are built at test time from the ISS record epoch-year-19xx freezes (no provider's bytes, so the module runs
in the public export). Run: python -m unittest tests.adversarial.test_misidentified_cases_080"""
import os
import shutil
import sys
import tempfile
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import Runner  # noqa: E402
from tests.adversarial.test_history_080 import SETS, csv_text, json_text, tle_text  # noqa: E402
from tests.adversarial.test_strict_files_080 import LIVE, xml_text  # noqa: E402

ONE = SETS[:1]   # the ISS once
FILES = (("iss.tle", tle_text(ONE)), ("iss.csv", csv_text(ONE)), ("iss.json", json_text(ONE)), ("iss.xml", xml_text()))
PAIRS = ("tle-vs-omm-precision-loss", "mean-motion-derivative-convention")
CONSISTENCY = {"tle-vs-omm-precision-loss": "tle-values-match-omm-within-tle-precision",
               "mean-motion-derivative-convention": "mmdot-is-tle-field-value"}


def answering(how, fmts):
    """The reference's records, those of the formats named passed through how."""
    class Adapter(Reference):
        def parse(self, raw, fmt):
            out = [r for r in super().parse(raw, fmt) if "_refused" not in r]
            return how(out) if fmt in fmts else out
    return Adapter()


def wrong(r):
    return dict(r, mean_anomaly=str(Decimal(str(r["mean_anomaly"])) + 7))


def without_id(r):
    return {k: v for k, v in r.items() if k != "norad_cat_id"}


class AMisidentifiedRecordFailsTheCasesWithNoValuesItem(unittest.TestCase):

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-misidentified-cases-")
        for name, text in FILES:
            self.write(name, text)

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def write(self, name, text):
        os.makedirs(os.path.join(self.data, LIVE), exist_ok=True)
        with open(os.path.join(self.data, LIVE, name), "w", encoding="utf-8", newline="") as f:
            f.write(text)

    def run_case(self, parser, case):
        res = Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=[case])[0]
        return res, [(os.path.basename(i.file), i.detail) for i in res.items if i.check == "records-returned"]

    def test_a_wrong_copy_under_another_id_or_none_fails_the_pairs_cases(self):
        for name, how, words in (
                ("another catalog number", lambda rs: [dict(wrong(rs[0]), norad_cat_id=rs[0]["norad_cat_id"] + 10_000_000)] + rs,
                 "1 unexpected record id, e.g. [10025544]"),
                ("none", lambda rs: [without_id(wrong(rs[0]))] + rs, "1 record without norad_cat_id"),
                ("Alpha-5 text where an integer belongs", lambda rs: [dict(wrong(rs[0]), norad_cat_id="A5544")] + rs,
                 "1 record whose norad_cat_id is not an integer")):
            for case in PAIRS:
                with self.subTest(copy=name, case=case):
                    res, items = self.run_case(answering(how, ("tle",)), case)
                    self.assertEqual(res.status, "fail")
                    self.assertEqual(len(items), 1, items)
                    self.assertEqual(items[0][0], "iss.tle")
                    self.assertIn(words, items[0][1])

    def test_every_tle_record_without_its_number_fails_on_no_pair(self):
        for case in PAIRS:
            with self.subTest(case=case):
                res, items = self.run_case(answering(lambda rs: [without_id(r) for r in rs], ("tle",)), case)
                self.assertEqual(res.status, "fail")
                (pair,) = [i for i in res.items if i.check == CONSISTENCY[case]]
                self.assertEqual(pair.status, "fail", pair.detail)
                self.assertIn("0 pairs: the two files share 1 catalog number", pair.detail)

    def test_the_twins_files_that_share_no_catalog_number_still_pass_on_no_pair(self):
        """Two files of different objects: a correct parser forms no pair, and the check passes on nothing, as before."""
        self.write("iss.csv", csv_text([dict(SETS[0], NORAD_CAT_ID="25545")]))
        for case in PAIRS:
            with self.subTest(case=case):
                res, items = self.run_case(Reference(), case)
                self.assertEqual(items, [])
                (pair,) = [i for i in res.items if i.check == CONSISTENCY[case]]
                self.assertEqual(pair.status, "pass", pair.detail)
                self.assertNotIn("D-348", pair.detail)

    def test_the_facts_and_xml_cases_fail_a_record_under_another_id(self):
        def renumbered(rs):   # the same count, one record under a number the file does not hold
            return [dict(rs[0], norad_cat_id=rs[0]["norad_cat_id"] + 1)] + rs[1:]
        for case, fmt in (("csv-json-omitted-mandatory-fields", "csv"), ("csv-json-omitted-mandatory-fields", "json"),
                          ("omm-xml-schema", "xml")):
            with self.subTest(case=case, form=fmt):
                res, items = self.run_case(answering(renumbered, (fmt,)), case)
                self.assertEqual(res.status, "fail")
                self.assertEqual(items, [(f"iss.{fmt}", "1 unexpected record id, e.g. [25545]")])

    def test_the_twins_a_correct_parser_passes_every_case_with_no_item(self):
        for case in PAIRS + ("csv-json-omitted-mandatory-fields", "omm-xml-schema"):
            with self.subTest(case=case):
                res, items = self.run_case(Reference(), case)
                self.assertEqual(items, [])
                self.assertNotIn("fail", [i.status for i in res.items], [i.detail for i in res.items if i.status == "fail"])


    def test_the_item_holds_its_words_in_one_item_in_order(self):
        """From the reading: a surplus copy and a misidentified record in one file make one item, the surplus first;
        two copies under one unexpected id are one id; three examples at most are named."""
        def both(rs):
            return rs + [dict(rs[0])] + [dict(rs[0], norad_cat_id=rs[0]["norad_cat_id"] + 10_000_000)]
        res, items = self.run_case(answering(both, ("tle",)), PAIRS[0])
        self.assertEqual(items, [("iss.tle", "id 25544: returned 2 times where the input holds it once (D-311); "
                                             "1 unexpected record id, e.g. [10025544]")])
        res, items = self.run_case(answering(lambda rs: rs + [dict(rs[0], norad_cat_id=99)] * 2, ("tle",)), PAIRS[0])
        self.assertEqual(items, [("iss.tle", "1 unexpected record id, e.g. [99]")])
        res, items = self.run_case(answering(lambda rs: rs + [dict(rs[0], norad_cat_id=k) for k in (91, 92, 93, 94)], ("tle",)), PAIRS[0])
        self.assertEqual(items, [("iss.tle", "4 unexpected record ids, e.g. [91, 92, 93]")])

    def test_a_file_whose_own_records_lack_a_number_gets_no_nameless_words(self):
        """A stated limit (D-348): where the reference reader's records of a file include one without a catalog number,
        a record returned without one is not counted against the parser here (no CelesTrak file holds such a record)."""
        self.write("iss.csv", csv_text(ONE + [dict(SETS[1], NORAD_CAT_ID="")]))
        res, items = self.run_case(answering(lambda rs: rs + [without_id(rs[0])], ("csv",)), PAIRS[0])
        self.assertEqual([d for _, d in items if "without norad_cat_id" in d], [])


if __name__ == "__main__":
    unittest.main()
