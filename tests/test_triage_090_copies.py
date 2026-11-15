# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Tests that pin survivors of the 0.9.0 mutation run, those about the copies of an id and the counts of a file a parser
returns nothing of, named by mutant number in docs/handoff/mutation-survivors-0.9.0-triage.md (D-523): each passes on the code and fails under its mutant.

The TLE/OMM consistency check reads an id the input holds once by its last copy, a design kept for 0.9.0 (owner ruling
3 on 900, 903 and 905): the tests here say only that a wrong copy placed before the right one is caught by some check
of the case, never which, so that design is not frozen.

Run: python -m unittest tests.test_triage_090_copies"""
import datetime as dt
import os
import shutil
import sys
import tempfile
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import reference as ref  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import FAIL_WEIGHT, CaseResult, Runner, _match_copies, _TleValuesByEpoch  # noqa: E402
from tests.adversarial.test_history_080 import SETS, csv_text as history_csv, tle_text  # noqa: E402
from tests.adversarial.test_repeated_ids_080 import TWICE, records_as  # noqa: E402
from tests.adversarial.test_strict_files_080 import LIVE  # noqa: E402
from tests.adversarial.test_surplus_cases_080 import answering as answering_formats, wrong_first  # noqa: E402

EPOCH_FORM = "%Y-%m-%dT%H:%M:%S.%f"
REFUSAL = {"_refused": "this set is too old", "_field": "25544", "_input": ""}


def shifted(epoch, us):
    """An epoch in the runner's form moved by us microseconds."""
    return (dt.datetime.strptime(str(epoch), EPOCH_FORM) + dt.timedelta(microseconds=us)).strftime(EPOCH_FORM)


def mean_anomaly_off(r):
    return dict(r, mean_anomaly=str(Decimal(str(r["mean_anomaly"])) + 7))


# ---- _match_copies past seven copies (the greedy pairing and its augmenting paths)

def pair(costs, n=8):
    """The record index _match_copies gives each of n copies against n records, by a table {(copy, record): cost},
    every pair not in it a failure. The copies and records carry no element set number or revolution, so the first
    pass pairs none of them and all go to the greedy pairing (more than seven of each, n * n within PAIRING_CAP)."""
    copies = [{"k": i} for i in range(n)]
    records = [{"r": j} for j in range(n)]
    return [j for _, j in _match_copies(copies, records, lambda g, r: costs.get((g["k"], r["r"]), FAIL_WEIGHT))]


class PairingPastSevenCopies(unittest.TestCase):

    def test_copies_that_all_match_one_record_take_a_record_each(self):
        """Kills 220, 221, 222 (the greedy pairing: a copy takes a record no other copy took). Eight copies each equal to
        record 0 alone: each record goes to a copy of its own, so seven of them fail; with the mutants every copy (or all
        but one) takes the same record, and a parser returning one record eight times would pass."""
        self.assertEqual(pair({(i, 0): 0 for i in range(8)}), list(range(8)))

    def test_an_augmenting_path_finds_the_pairing_that_fails_nothing(self):
        """Kills 223, 224, 225, 226, 227, 228, 229, 232, 233 (the augmenting search after a greedy pairing with one
        failure). Copy k equals record k + 1 exactly and is within tolerance of record k; the last copy is within
        tolerance of the last record alone. Greedy pairs copy k with record k + 1 and leaves the last copy against
        record 0, a failure of exactly FAIL_WEIGHT; the one pairing that fails nothing is copy k with record k."""
        costs = {(k, k + 1): 0 for k in range(7)}
        costs.update({(k, k): 1 for k in range(8)})
        self.assertEqual(pair(costs), list(range(8)))

    def test_an_augmenting_path_past_a_dead_end(self):
        """Kills 230 (a search that meets a dead end reports it as a path). Copy 2 fails against what greedy leaves it
        (record 2); its first edge, record 0, is held by copy 0, which has no other edge (a dead end); its second, record
        1, is held by copy 1, which can move to the free record 2. The pairing that fails nothing swaps copies 1 and 2."""
        costs = {(0, 0): 0, (1, 1): 0, (1, 2): 1, (2, 0): 1, (2, 1): 1}
        costs.update({(k, k): 0 for k in range(3, 8)})
        self.assertEqual(pair(costs), [0, 2, 1, 3, 4, 5, 6, 7])


# ---- the records-returned item of a file the parser returns nothing of

class TheCountsOfAParserReturningNothing(unittest.TestCase):

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-triage-copies-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def returned_item(self, parser, text=TWICE):
        """The records-returned item of the ISS CSV, the ISS held twice, as test_repeated_ids_counts_080 reads it."""
        os.makedirs(os.path.join(self.data, LIVE), exist_ok=True)
        with open(os.path.join(self.data, LIVE, "iss.csv"), "w", encoding="utf-8", newline="") as f:
            f.write(text)
        res = Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["baseline-iss-five-formats"])[0]
        (item,) = [i for i in res.items if i.check == "records-returned" and (i.file or "").endswith("iss.csv")]
        return item

    def counted(self, item, *keys):
        return tuple(item.counts[k] for k in keys)

    def test_one_refusal_of_an_id_held_twice_credits_one_record(self):
        """Kills 449, 450 (a refusal with a reason counted from 1, or as 2): one refusal of the ISS, held twice, credits
        one record and leaves one dropped; the cap of two hid the mutants where both records were refused."""
        item = self.returned_item(records_as(lambda rs: [dict(REFUSAL)]))
        self.assertEqual(self.counted(item, "expected", "dropped", "refused_matched", "ids_not_returned"), (2, 1, 1, 0))

    def test_the_counts_of_records_never_returned_are_zero(self):
        """Kills 454, 456, 458, 460 (returned, misidentified, extra and non_integer_id started at 1): a parser returning
        nothing returned, misidentified and added nothing."""
        item = self.returned_item(records_as(lambda rs: []))
        self.assertEqual(self.counted(item, "returned", "loaded", "misidentified", "extra", "non_integer_id"), (0, 0, 0, 0, 0))

    def test_refusals_with_a_reason_are_not_counted_as_without_one(self):
        """Kills 461 (refused_without_reason as the sum of the refusals and those with a reason)."""
        for n in (1, 2):
            with self.subTest(refusals=n):
                item = self.returned_item(records_as(lambda rs: [dict(REFUSAL) for _ in range(n)]))
                self.assertEqual(self.counted(item, "refused", "refused_without_reason"), (n, 0))

    def test_the_words_join_their_parts_with_no_stray_comma(self):
        """Kills 466 (the comma between the refused and dropped parts written where only one of them is)."""
        item = self.returned_item(records_as(lambda rs: []))
        self.assertTrue(item.detail.startswith("parser returned 0 of 2 records: 2 dropped"), item.detail)
        item = self.returned_item(records_as(lambda rs: [dict(REFUSAL), dict(REFUSAL)]))
        self.assertTrue(item.detail.startswith("parser returned 0 of 2 records: 2 refused with a reason ("), item.detail)
        self.assertTrue(item.detail.endswith(")"), item.detail)
        self.assertNotIn(", ", item.detail[-2:])


# ---- the pivot and presence checks on an id held more than once

class AHistoryInThePivotAndPresenceChecks(unittest.TestCase):

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-triage-copies-")
        self.runner = Runner(Reference(), root=ROOT, data=self.data, fetch_hints=False)

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def file(self, name, text):
        path = os.path.join(self.data, name)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return path

    def pivot(self, sets, how=None):
        """The pivot item on the TLE file of sets, as test_history_080 drives it: the runner's reading of the reference's
        answer, passed through how, and the reference reader's records of the same bytes."""
        path = self.file("history.tle", tle_text(sets))
        parsed = self.runner.parse(path, "tle")
        res = CaseResult("history", "history")
        self.runner.check_tle_lines(res, path, how(parsed) if how else parsed, ref.read_file(path)[1], {"two-digit-year-pivot"})
        (item,) = [i for i in res.items if i.check == "two-digit-year-pivot"]
        return item

    def test_an_id_held_exactly_twice_matches_each_record_with_a_copy_of_its_own(self):
        """Kills 752 (an id held twice read by its last copy alone). Two element sets a day apart, a correct parser."""
        item = self.pivot(SETS[:2])
        self.assertEqual(item.status, "pass", item.detail)

    def test_copies_a_microsecond_early_match_within_tolerance(self):
        """Kills 756, 757, 766, 767 (the copy before the bisection point never tried, or a copy within tolerance never
        taken). Each copy of a three-set history returned 1 us before its record's epoch, within the 2 us the pivot
        check allows; the copy that matches each record lies before the bisection point."""
        item = self.pivot(SETS, lambda ps: [dict(p, epoch=shifted(p["epoch"], -1)) for p in ps])
        self.assertEqual(item.status, "pass-tolerance", item.detail)
        self.assertIn("epoch n=3", item.detail)

    def test_a_dropped_set_costs_its_own_record_alone(self):
        """Kills 765 (a copy that mismatches taken while nothing matched yet): the middle set dropped fails its own
        record, and the third set's copy is left for the third record."""
        item = self.pivot(SETS, lambda ps: [ps[0], ps[2]])
        self.assertEqual(item.status, "fail", item.detail)
        self.assertEqual(item.detail, "epoch mismatch for ids [25544]")

    def test_set_zero_is_found_among_two_copies(self):
        """Kills 776 (an id held twice read by its last copy alone in the presence checks). The ISS held twice, the
        first set numbered 0 at revolution 0; its copy is the first of the two."""
        path = self.file("history.csv", history_csv(SETS[:2]))
        res = CaseResult("history", "history")
        self.runner.check_presence(res, path, self.runner.parse(path, "csv"), ref.read_file(path)[1], {"element-set-zero-and-rev-one"})
        (item,) = [i for i in res.items if i.check == "element-set-zero-and-rev-one"]
        self.assertEqual(item.status, "pass", item.detail)


# ---- the TLE values at an epoch, for an empty OMM copy of a repeated id

class TheTleValuesAtAnEpoch(unittest.TestCase):

    def test_a_copy_that_leaves_the_field_empty_gives_no_value(self):
        """Kills 291 (values_near's emptiness filter dropped): a TLE copy whose BSTAR the reader reads as None, as
        blanks, or not at all, gives no value at its epoch, and the caller compares nothing there."""
        epoch = SETS[0]["EPOCH"]
        at = dt.datetime.strptime(epoch, EPOCH_FORM)
        for name, extra in (("None", {"bstar": None}), ("blanks", {"bstar": "   "}), ("no key", {})):
            with self.subTest(bstar=name):
                values = _TleValuesByEpoch([dict({"norad_cat_id": 25544, "epoch": epoch}, **extra)])
                self.assertEqual(values.values_near(25544, at, "bstar"), ([], []))


# ---- a wrong copy before the right one, in the pairs case whose one judge is the consistency check

class AWrongCopyBeforeTheRightOneIsCaught(unittest.TestCase):
    """Owner ruling 3 (900, 903, 905): each test says the case does not pass and some item fails, never which."""

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-triage-copies-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def run_case(self, parser, tle_sets, csv_sets):
        raw = os.path.join(self.data, LIVE)
        os.makedirs(raw, exist_ok=True)
        for name, text in (("iss.tle", tle_text(tle_sets)), ("iss.csv", history_csv(csv_sets))):
            with open(os.path.join(raw, name), "w", encoding="utf-8", newline="") as f:
                f.write(text)
        return Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["tle-vs-omm-precision-loss"])[0]

    def assertCaught(self, res):
        self.assertNotIn(res.status, ("pass", "pass-tolerance"), [(i.check, i.status, i.detail) for i in res.items])
        self.assertIn("fail", [i.status for i in res.items])

    def test_a_wrong_copy_before_the_right_one_is_caught_where_the_tle_file_holds_the_id_twice(self):
        """Kills 903, 905 (an id the TLE file holds twice and the OMM file once read by its last copy alone). The TLE
        file holds the ISS's set twice, the CSV once; the parser returns the first TLE copy with its mean anomaly 7
        degrees off, the second right. No copy is a surplus, so with the mutants nothing in the case reads the wrong one.
        The twin: the reference passes."""
        twice, once = [SETS[0], SETS[0]], [SETS[0]]
        self.assertIn(self.run_case(Reference(), twice, once).status, ("pass", "pass-tolerance"))
        self.assertCaught(self.run_case(answering_formats(lambda rs: [mean_anomaly_off(rs[0])] + rs[1:], ("tle",)), twice, once))

    def test_a_wrong_copy_before_the_right_one_is_caught_where_each_file_holds_the_id_once(self):
        """Kills none of 900, 903, 905: with the mutants a held-once id's copies are all compared, which catches the
        wrong copy too. It pins the behaviour those mutants touch, a wrong copy before the right one caught, by whichever
        check, in either form."""
        for fmt in ("tle", "csv"):
            with self.subTest(form=fmt):
                self.assertCaught(self.run_case(answering_formats(wrong_first, (fmt,)), SETS[:1], SETS[:1]))


if __name__ == "__main__":
    unittest.main()
