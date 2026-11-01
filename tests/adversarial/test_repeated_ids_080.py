# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""An id the input holds more than once is compared copy by copy with the input's record each copy matches (D-343,
the 0.8.0 plan's 2a, D-317's withdrawn note done properly), with its wrong-on-purpose adapters and twins.

Before: the oracle kept one record of an id, the last, and every copy a parser returned was compared with it, so on a
live file that holds an id twice with records that differ a correct parser failed (the limit D-311 stated). Now each
copy is paired with one of the input's records, the pairing that fails least, and the item says so.

Run: python -m unittest tests.adversarial.test_repeated_ids_080"""
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
from tests.adversarial.test_strict_files_080 import LIVE, csv_text  # noqa: E402

FIRST = csv_text()
SECOND_ROW = csv_text(ELEMENT_SET_NO="998", EPOCH="1998-11-20T07:30:00.000000").splitlines()[1]
TWICE = FIRST + SECOND_ROW + "\r\n"   # the ISS twice, the second record a later element set


def records_as(how):
    """The reference's records of the CSV, rearranged by how (a list of the records -> the list returned)."""
    class Adapter(Reference):
        def parse(self, raw, fmt):
            out = super().parse(raw, fmt)
            if fmt != "csv":
                return out
            return how([r for r in out if "_refused" not in r])
    return Adapter()


class AnIdTheInputHoldsTwiceIsComparedCopyByCopy(unittest.TestCase):

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-repeated-ids-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def values_item(self, parser, text=TWICE):
        os.makedirs(os.path.join(self.data, LIVE), exist_ok=True)
        with open(os.path.join(self.data, LIVE, "iss.csv"), "w", encoding="utf-8", newline="") as f:
            f.write(text)
        res = Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["baseline-iss-five-formats"])[0]
        (item,) = [i for i in res.items if i.check == "values" and (i.file or "").endswith("iss.csv")]
        return item

    def test_a_correct_parser_passes_and_the_item_says_why(self):
        item = self.values_item(Reference())
        self.assertEqual(item.status, "pass", item.detail)
        self.assertIn("the input holds 1 id more than once with records that differ (e.g. id 25544, 2 records)", item.detail)
        self.assertIn("each copy returned is compared with the input's record it matches (D-343)", item.detail)

    def test_the_copies_in_any_order_pass(self):
        self.assertEqual(self.values_item(records_as(lambda rs: rs[::-1])).status, "pass")

    def test_the_twins_a_wrong_copy_fails_against_the_record_it_pairs_with(self):
        def second_wrong(rs):
            return [rs[0], dict(rs[1], inclination=str(Decimal(str(rs[1]["inclination"])) + 1))]
        for name, how, words in (("the first record twice", lambda rs: [rs[0], dict(rs[0])], "element_set_no"),
                                 ("the last record twice, which passed before", lambda rs: [dict(rs[1]), rs[1]], "element_set_no"),
                                 ("the second record's inclination a degree off", second_wrong, "inclination"),
                                 ("a third copy", lambda rs: rs + [dict(rs[1])], "returned 3 times where the input holds it 2 times (D-311)")):
            with self.subTest(parser=name):
                item = self.values_item(records_as(how))
                self.assertEqual(item.status, "fail", item.detail)
                self.assertIn(words, item.detail)
                if "D-311" not in words:   # a value that differs names the record its copy was paired with
                    self.assertIn("against the input's record", item.detail)

    def test_a_field_only_a_later_record_carries_is_a_gap_when_never_returned(self):
        """The reading of D-343: D-284's gap line read the first record of a repeated id only."""
        first_unnamed = csv_text(OBJECT_NAME="") + SECOND_ROW + "\r\n"

        def nameless(rs):
            return [{k: v for k, v in r.items() if k != "object_name"} for r in rs]
        os.makedirs(os.path.join(self.data, LIVE), exist_ok=True)
        with open(os.path.join(self.data, LIVE, "iss.csv"), "w", encoding="utf-8", newline="") as f:
            f.write(first_unnamed)
        res = Runner(records_as(nameless), root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["baseline-iss-five-formats"])[0]
        gaps = [i for i in res.items if i.check == "fields-not-returned" and (i.file or "").endswith("iss.csv")]
        self.assertEqual([i.status for i in gaps], ["not-exercised"])
        self.assertIn("object_name", gaps[0].detail)

    def test_many_records_of_one_id_are_paired_in_one_pass(self):
        """The reading of D-343: the pairing costed every copy against every record, 147 s for 2,000 records of one id;
        a correct parser's copies are now paired by element set number and revolution in one pass."""
        import time
        rows = [csv_text(ELEMENT_SET_NO=str(n), REV_AT_EPOCH=str(n)).splitlines()[1] for n in range(1, 2001)]
        text = FIRST.splitlines()[0] + "\r\n" + "\r\n".join(rows) + "\r\n"
        start = time.monotonic()
        item = self.values_item(records_as(lambda rs: rs[::-1]), text)
        self.assertLess(time.monotonic() - start, 20)
        self.assertEqual(item.status, "pass", item.detail[:300])

    def test_copies_within_tolerance_of_each_other_are_paired_exactly(self):
        """The reading of D-343: a pairing that counted failures alone could pair reversed copies within tolerance where
        an exact pairing existed; a value within tolerance now weighs, below any failure."""
        close = FIRST + csv_text(EPOCH="1998-11-20T06:49:59.999809").splitlines()[1] + "\r\n"
        item = self.values_item(records_as(lambda rs: rs[::-1]), close)
        self.assertEqual(item.status, "pass", item.detail)
        self.assertEqual(self.values_item(Reference(), close).status, "pass")

    def test_past_the_pairing_cap_copies_in_another_order_still_pass(self):
        """The second reading of D-343: beyond PAIRING_CAP the copies left were paired with the records left in the
        input's order, so 101 records of one id sharing a set number and revolution, returned in another order, failed a
        correct parser; they are paired in epoch order there now. The twin: one copy wrong among them fails."""
        rows = [csv_text(EPOCH=f"1998-11-20T{6 + n // 60:02d}:{n % 60:02d}:59.999808").splitlines()[1] for n in range(101)]
        text = FIRST.splitlines()[0] + "\r\n" + "\r\n".join(rows) + "\r\n"
        self.assertEqual(self.values_item(records_as(lambda rs: rs[::-1]), text).status, "pass")

        def one_off(rs):
            rs = rs[::-1]
            return [dict(rs[0], inclination=str(Decimal(str(rs[0]["inclination"])) + 1))] + rs[1:]
        self.assertEqual(self.values_item(records_as(one_off), text).status, "fail")

    def test_a_parsers_own_record_key_is_not_the_runners(self):
        """The second reading of D-343: the record a copy was paired with is the runner's own key on it, `_record`, which
        the field-form checks read; a parser's own `_record` is dropped like `_notes` and `_bad`, so a parser that flips
        a sign and hands over a record carrying the flipped value still fails the field form. The twin: the reference.
        Without the drop the held-once case ends as an internal error, where the runner reads the parser's text as a
        record; the held-twice case passes either way, since the runner sets the key on each copy it pairs."""
        def flipped(rs):
            return [dict(r, mean_motion_dot="0.00003657", _record={"mean_motion_dot": "0.00003657"}) for r in rs]
        second = csv_text(ELEMENT_SET_NO="998", EPOCH="1998-11-20T07:30:00.000000").splitlines()[1]
        for held, text in (("held once", FIRST), ("held twice", FIRST + second + "\r\n")):
            for name, parser, want in (("flipped, with its own _record", records_as(flipped), "fail"), ("the reference", Reference(), "pass")):
                with self.subTest(held=held, parser=name):
                    raw = os.path.join(self.data, "fixtures", "epoch-year-19xx", "raw")
                    os.makedirs(raw, exist_ok=True)
                    with open(os.path.join(raw, "iss-first.csv"), "w", encoding="utf-8", newline="") as f:
                        f.write(text)
                    res = Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["epoch-year-19xx"])[0]
                    (item,) = [i for i in res.items if i.check == "negative-bstar-and-ndot" and (i.file or "").endswith("iss-first.csv")]
                    self.assertEqual(item.status, want, item.detail)

    def test_a_file_that_holds_the_id_once_reads_as_before(self):
        item = self.values_item(Reference(), FIRST)
        self.assertEqual(item.status, "pass", item.detail)
        self.assertNotIn("D-343", item.detail)
        self.assertNotIn("against the input's record", item.detail)


if __name__ == "__main__":
    unittest.main()
