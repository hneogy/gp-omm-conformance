# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""One copy where the input holds two fails, and the counts count records, not ids (D-344, the 0.8.0 plan's 2b and
2c), with their wrong-on-purpose adapters and twins.

Before: where a live file held a catalog number twice, a parser returning one record of it passed (2b), and the values
item's counts counted ids, so the input's second record was in no count (2c). Where every id is held once, as in every
input the corpus has, every count is what it was.

Run: python -m unittest tests.adversarial.test_repeated_ids_counts_080"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf import reference as ref  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import CaseResult, Runner  # noqa: E402
from tests.adversarial.test_repeated_ids_080 import FIRST, TWICE, records_as  # noqa: E402
from tests.adversarial.test_strict_files_080 import LIVE, csv_text  # noqa: E402

OTHER_ROW = csv_text(NORAD_CAT_ID="25545", OBJECT_NAME="OTHER").splitlines()[1]
TWICE_AND_ANOTHER = TWICE + OTHER_ROW + "\r\n"   # the ISS twice, and one other object once
NO_ID = [csv_text(NORAD_CAT_ID="", EPOCH=e, OBJECT_NAME="UNKNOWN").splitlines()[1] + "\r\n"
         for e in ("1998-11-21T06:49:59.999808", "1998-11-22T06:49:59.999808")]   # two rows with no number
NO_ID_ROWS = FIRST + "".join(NO_ID)
NO_FIELD = {"_refused": "no catalog number", "_input": ""}   # a refusal that names no catalog field


def refusing_the_iss(n):
    """The other object returned, and n refusals with a reason of the ISS's records in place of its copies."""
    return records_as(lambda rs: [r for r in rs if r["norad_cat_id"] != 25544]
                      + [{"_refused": "this set is too old", "_field": "25544", "_input": ""}] * n)


class OneCopyWhereTheInputHoldsTwoFailsAndTheCountsCountRecords(unittest.TestCase):

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-repeated-counts-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def values_item(self, parser, text=TWICE, check="values"):
        os.makedirs(os.path.join(self.data, LIVE), exist_ok=True)
        with open(os.path.join(self.data, LIVE, "iss.csv"), "w", encoding="utf-8", newline="") as f:
            f.write(text)
        res = Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["baseline-iss-five-formats"])[0]
        (item,) = [i for i in res.items if i.check == check and (i.file or "").endswith("iss.csv")]
        return item

    def counted(self, item, *keys):
        return tuple(item.counts[k] for k in keys)

    def test_one_record_of_two_fails(self):
        for name, how in (("the first alone", lambda rs: rs[:1]), ("the last alone", lambda rs: rs[1:])):
            with self.subTest(parser=name):
                item = self.values_item(records_as(how))
                self.assertEqual(item.status, "fail", item.detail)
                self.assertIn("id 25544: returned once where the input holds it 2 times (D-344)", item.detail)
                self.assertEqual((item.counts["expected"], item.counts["loaded"], item.counts["dropped"]), (2, 1, 1))

    def test_a_record_refused_with_a_reason_is_credited_and_still_not_returned(self):
        def refuse_second(rs):
            return [rs[0], {"_refused": "this set is too old", "_field": "25544", "_input": ""}]
        item = self.values_item(records_as(refuse_second))
        self.assertEqual(item.status, "fail", item.detail)
        self.assertEqual((item.counts["expected"], item.counts["loaded"], item.counts["refused_matched"], item.counts["dropped"]),
                         (2, 1, 1, 0))

    def test_the_twins_both_records_pass_and_count_as_two(self):
        item = self.values_item(Reference())
        self.assertEqual(item.status, "pass", item.detail)
        self.assertEqual((item.counts["expected"], item.counts["loaded"], item.counts["dropped"], item.counts["extra"]), (2, 2, 0, 0))
        once = self.values_item(Reference(), FIRST)
        self.assertEqual(once.status, "pass", once.detail)
        self.assertEqual((once.counts["expected"], once.counts["loaded"], once.counts["ids_not_returned"]), (1, 1, 0))

    def test_the_words_count_records_as_the_counts_do(self):
        """The reading of D-344: the words counted ids where the counts count records."""
        item = self.values_item(records_as(lambda rs: [r for r in rs if r["norad_cat_id"] != 25544]), TWICE_AND_ANOTHER)
        self.assertIn("1 compared vs", item.detail)
        self.assertIn("2 expected records not returned, e.g. [25544]", item.detail)
        self.assertEqual(self.counted(item, "expected", "loaded", "dropped", "ids_not_returned"), (3, 1, 2, 1))
        item = self.values_item(refusing_the_iss(1), TWICE_AND_ANOTHER)
        self.assertIn("2 expected records not returned: 1 refused with a reason", item.detail)
        self.assertIn(", 1 silently, e.g. [25544]", item.detail)
        self.assertEqual(self.counted(item, "refused_matched", "dropped"), (1, 1))
        item = self.values_item(refusing_the_iss(2), TWICE_AND_ANOTHER)   # its twin: both records refused with a reason
        self.assertIn("2 expected records not returned: 2 refused with a reason", item.detail)
        self.assertIn(", 0 silently", item.detail)
        self.assertEqual(self.counted(item, "refused_matched", "dropped"), (2, 0))
        item = self.values_item(Reference(), TWICE_AND_ANOTHER)
        self.assertEqual(item.status, "pass", item.detail)
        self.assertIn("3 records match", item.detail)

    def test_a_parser_returning_nothing_is_counted_in_records(self):
        """The records-returned item, where a parser returns no record of a file: each refusal with a reason credits one
        record of its id, and ids_not_returned counts ids, as in the values item."""
        item = self.values_item(records_as(lambda rs: []), check="records-returned")
        self.assertEqual(self.counted(item, "expected", "dropped", "refused_matched", "ids_not_returned"), (2, 2, 0, 1))
        item = self.values_item(records_as(lambda rs: [{"_refused": "this set is too old", "_field": "25544", "_input": ""}] * 2),
                                check="records-returned")
        self.assertIn("parser returned 0 of 2 records: 2 refused with a reason", item.detail)
        self.assertEqual(self.counted(item, "expected", "dropped", "refused_matched", "ids_not_returned"), (2, 0, 2, 0))
        item = self.values_item(records_as(lambda rs: []), FIRST, check="records-returned")   # the ISS held once: as before
        self.assertEqual(self.counted(item, "expected", "dropped", "refused_matched", "ids_not_returned"), (1, 1, 0, 1))

    def test_records_without_a_catalog_number_count_once_as_before(self):
        """Two rows with no catalog number are counted as one expected record, as before, with no shortfall words."""
        for name, how, counts in (("returned", lambda rs: rs, (2, 2, 0)),
                                  ("one of them returned", lambda rs: [r for r in rs if r["norad_cat_id"] is not None]
                                   + [r for r in rs if r["norad_cat_id"] is None][:1], (2, 2, 0)),
                                  ("dropped", lambda rs: [r for r in rs if r["norad_cat_id"] is not None], (2, 1, 1))):
            with self.subTest(rows=name):
                item = self.values_item(records_as(how), NO_ID_ROWS)
                self.assertNotIn("D-344", item.detail)
                self.assertEqual(self.counted(item, "expected", "loaded", "dropped"), counts)

    def test_records_without_a_catalog_number_read_as_before_in_the_other_items(self):
        """The second reading of D-344: the silent ids named, the records-returned credit and the presence checks read
        the records without a catalog number as before; one count moves, ids_not_returned counting them as one id."""
        def iss_and_nameless_refused(rs):
            return ([r for r in rs if r["norad_cat_id"] == 25545]
                    + [{"_refused": "this set is too old", "_field": "25544", "_input": ""}, dict(NO_FIELD)])
        item = self.values_item(records_as(iss_and_nameless_refused), FIRST + OTHER_ROW + "\r\n" + NO_ID[0])
        self.assertIn("2 expected records not returned: 1 refused with a reason", item.detail)
        self.assertIn(", 1 silently, e.g. [None]", item.detail)
        item = self.values_item(records_as(lambda rs: [dict(NO_FIELD), dict(NO_FIELD)]), NO_ID_ROWS, check="records-returned")
        self.assertIn("parser returned 0 of 3 records: 1 refused with a reason", item.detail)
        self.assertEqual(self.counted(item, "expected", "refused_matched", "dropped", "ids_not_returned"), (3, 1, 2, 1))
        path = os.path.join(self.data, "nameless.csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(NO_ID_ROWS)

        def last_nameless_renamed(rs):
            nameless = [r for r in rs if r["norad_cat_id"] is None]
            return [r for r in rs if r["norad_cat_id"] is not None] + nameless[:1] + [dict(nameless[1], object_name="X")]
        for name, parser, status in (("the last renamed", records_as(last_nameless_renamed), "fail"), ("its twin", Reference(), "pass")):
            with self.subTest(presence=name):
                runner = Runner(parser, root=ROOT, data=self.data, fetch_hints=False)
                res = CaseResult("nameless", "nameless")
                runner.check_presence(res, path, runner.parse(path, "csv"), ref.read_file(path)[1], {"object-name-unknown-literal"})
                self.assertEqual([i.status for i in res.items], [status], [i.detail for i in res.items])

    def test_a_third_copy_is_still_a_surplus(self):
        item = self.values_item(records_as(lambda rs: rs + [dict(rs[1])]))
        self.assertEqual(item.status, "fail", item.detail)
        self.assertEqual((item.counts["expected"], item.counts["loaded"], item.counts["extra"], item.counts["duplicate_copies"]), (2, 2, 1, 1))


if __name__ == "__main__":
    unittest.main()
