# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Where the frozen values cover part of a file, a record under a catalog number the file does not hold fails the values
item, and the file's own records outside the compared subset are in no count but `returned` (D-349, D-348's reading,
its finding 3, on the owner's ruling and instruction), with wrong-on-purpose adapters and twins.

Before: the values item failed an unexpected id only where the values cover the whole file (`if extra and not
partial`), so nine-digit-supgp-launch-nominals, whose starlink-all.csv is held to its 27 nine-digit records alone,
passed a made-up record, run alone or in a full run (no other case reads the file); and the file's other 11,114 records
were counted misidentified, for a correct parser too, and stood in for expected records a parser dropped.

The first test runs on the snapshot's bytes of starlink-all.csv (the maintainer's copy; an export holds none, and a
fetch brings later bytes, which are read live and held whole) and skips without them; the others build their files at
test time and run anywhere.
Run: python -m unittest tests.adversarial.test_partial_values_080"""
import hashlib
import io
import contextlib
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf import reference as ref  # noqa: E402
from gpconf import runner as R  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import CaseResult, Runner, _held  # noqa: E402
from gpconf.words import qty  # noqa: E402
from tests.adversarial.test_history_080 import SETS, csv_text  # noqa: E402

CASE = "nine-digit-supgp-launch-nominals"
STARLINK_ALL = os.path.join(ROOT, "fixtures", CASE, "raw", "starlink-all.csv")
MADE_UP = 123456789   # a nine-digit catalog number the file does not hold (checked below)


def snapshot_bytes():
    """True where starlink-all.csv holds the bytes the case's frozen values were taken from and those values are not
    withheld (D-349's readings: a fetched copy is read live, and an export's case withholds its records, each holding the
    file whole, so the partial item does not arise). The source key is written with forward slashes on every system."""
    if not os.path.exists(STARLINK_ALL):
        return False
    with open(os.path.join(ROOT, "fixtures", CASE, "expected.json"), encoding="utf-8") as f:
        exp = json.load(f)
    if exp.get("records_withheld"):
        return False
    src = exp["sources"].get(f"fixtures/{CASE}/raw/starlink-all.csv", {})
    with open(STARLINK_ALL, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest() == src.get("sha256")


def adding(record_for, when):
    """The reference's records, with record_for(records) added to the answers when(records) picks."""
    class Adapter(Reference):
        def parse(self, raw, fmt):
            out = [r for r in super().parse(raw, fmt) if "_refused" not in r]
            return out + [record_for(out)] if when(out) else out
    return Adapter()


def _only_nine_digit():
    """A parser returning the 27 records the frozen values grade and dropping every other (D-349's reading, finding 5)."""
    class Adapter(Reference):
        def parse(self, raw, fmt):
            out = [r for r in super().parse(raw, fmt) if "_refused" not in r]
            return [r for r in out if r["norad_cat_id"] >= 100_000_000] if len(out) > 1000 else out
    return Adapter()


@unittest.skipUnless(snapshot_bytes(), "needs the snapshot's bytes of starlink-all.csv (the maintainer's copy)")
class AMadeUpRecordInThePartlyFrozenFile(unittest.TestCase):

    def values_item(self, parser):
        res = Runner(parser, root=ROOT, fetch_hints=False).run(case_ids=[CASE])[0]
        (item,) = [i for i in res.items if i.check == "values" and (i.file or "").endswith("starlink-all.csv")]
        return res, item

    def test_a_made_up_record_now_fails_and_the_counts_count_none_of_the_files_own(self):
        held = _held(r["norad_cat_id"] for r in ref.read_file(STARLINK_ALL)[1])
        self.assertNotIn(MADE_UP, held)
        self.assertGreater(len(held), 10000)
        made_up = adding(lambda rs: dict(rs[0], norad_cat_id=MADE_UP), lambda rs: len(rs) > 1000)
        res, item = self.values_item(made_up)
        self.assertEqual(res.status, "fail")
        self.assertEqual(item.status, "fail", item.detail)
        self.assertIn(f"1 unexpected record id, e.g. [{MADE_UP}]", item.detail)
        self.assertEqual((item.counts["misidentified"], item.counts["extra"]), (1, 1))
        res, item = self.values_item(_only_nine_digit())
        self.assertEqual(item.status, "fail", item.detail)
        self.assertIn(f"{qty(len(held) - 27, 'record')} outside the compared subset neither returned nor refused with a reason that names it", item.detail)
        res, twin = self.values_item(Reference())   # its twin, the same parser without the record
        self.assertEqual(twin.status, "pass", twin.detail)
        self.assertEqual((twin.counts["expected"], twin.counts["loaded"], twin.counts["misidentified"], twin.counts["extra"]),
                         (27, 27, 0, 0))


class APartialValuesItemDrivenDirectly(unittest.TestCase):
    """The values item where the frozen values cover part of a file, driven as run_gp_like drives it, on a two-record
    file held to its first record alone."""

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-partial-values-")
        self.path = os.path.join(self.data, "two.csv")
        with open(self.path, "w", encoding="utf-8", newline="") as f:
            f.write(csv_text([SETS[0], dict(SETS[1], NORAD_CAT_ID="25545")]))

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def item(self, how=lambda rs: rs, refusals=()):
        runner = Runner(Reference(), root=ROOT, data=self.data, fetch_hints=False)
        refrecs = ref.read_file(self.path)[1]
        full, _, _ = runner.oracle_for({"records": []}, self.path, "csv", "live", refrecs)
        res = CaseResult("partial", "partial")
        res.refusals[self.path] = list(refusals)
        parsed = how([p for p in runner.parse(self.path, "csv")])
        with contextlib.redirect_stdout(io.StringIO()):
            runner.compare_values(res, self.path, "csv", "snapshot", parsed, {25544: full[25544]}, partial=True,
                                  oracle_label="frozen expected values", held={25544: 1}, held_in_file=_held(r["norad_cat_id"] for r in refrecs))
        (item,) = [i for i in res.items if i.check == "values"]
        return item

    def test_the_twin_passes_and_the_files_own_other_record_is_in_no_count(self):
        item = self.item()
        self.assertEqual(item.status, "pass", item.detail)
        self.assertEqual({k: item.counts[k] for k in ("expected", "returned", "loaded", "misidentified", "dropped", "extra")},
                         {"expected": 1, "returned": 2, "loaded": 1, "misidentified": 0, "dropped": 0, "extra": 0})

    def test_a_made_up_record_fails(self):
        item = self.item(lambda rs: rs + [dict(rs[0], norad_cat_id=MADE_UP)])
        self.assertEqual(item.status, "fail", item.detail)
        self.assertIn(f"1 unexpected record id, e.g. [{MADE_UP}]", item.detail)
        self.assertEqual((item.counts["misidentified"], item.counts["extra"]), (1, 1))

    def test_a_surplus_copy_outside_the_subset_is_counted_extra(self):
        """From the reading: the file's other record returned twice fails as before and is counted as a surplus copy is
        where the values cover the whole file, 1 extra and 1 duplicate copy (D-349)."""
        item = self.item(lambda rs: rs + [dict(next(r for r in rs if r["norad_cat_id"] == 25545))])
        self.assertEqual(item.status, "fail", item.detail)
        self.assertIn("1 id outside the compared subset returned more often than the input holds it", item.detail)
        self.assertIn("1 duplicate copy returned, 1 of the file's records outside the compared subset, counted in extra", item.detail)
        self.assertEqual((item.counts["misidentified"], item.counts["extra"], item.counts["duplicate_copies"]), (0, 1, 1))

    def test_a_record_outside_the_subset_dropped_silently_fails(self):
        """From the reading, folded in on the owner's ruling: the file's other record, which no frozen value grades,
        dropped with nothing said, fails; its twins, the record refused with a reason or returned, pass (D-349)."""
        drop = lambda rs: [r for r in rs if r["norad_cat_id"] != 25545]
        item = self.item(drop)
        self.assertEqual(item.status, "fail", item.detail)
        self.assertIn("1 record outside the compared subset neither returned nor refused with a reason that names it, e.g. [25545]", item.detail)
        refused = self.item(drop, [{"ok": True, "id": 25545, "reason": "this set is too old", "field": "25545", "input": ""}])
        self.assertEqual(refused.status, "pass", refused.detail)
        self.assertEqual(self.item().status, "pass")

    def test_a_dropped_record_is_counted_dropped(self):
        """The file's other record no longer stands in for the dropped one (it did: dropped 0, misidentified 1)."""
        item = self.item(lambda rs: [r for r in rs if r["norad_cat_id"] != 25544])
        self.assertEqual(item.status, "fail", item.detail)
        self.assertEqual((item.counts["dropped"], item.counts["misidentified"], item.counts["extra"]), (1, 0, 0))


class EveryOtherValuesItemCoversItsFileWhole(unittest.TestCase):
    """The owner's question (2026-10-18): does any other values item cover only part of a file? Measured on every case
    a reference run reaches: the oracle's catalog numbers against the reference reader's numbers for the same file. On
    the maintainer's data one item covers part of its file, starlink-all.csv's; on fetched files, read live, and in an
    export without provider files (the items that ship with the corpus alone), none."""

    def test_only_the_nine_digit_set_covers_part_of_a_file(self):
        seen = []
        original = R.Runner.compare_values

        def spy(self, res, path, fmt, mode, parsed, oracle, *a, **k):
            ids = {r["norad_cat_id"] for r in ref.read_file(self.path(path))[1]} - {None}
            if not set(oracle) >= ids:
                seen.append((os.path.basename(path), k.get("partial", False)))
            return original(self, res, path, fmt, mode, parsed, oracle, *a, **k)
        R.Runner.compare_values = spy
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                Runner(Reference(), root=ROOT, fetch_hints=False).run()
        finally:
            R.Runner.compare_values = original
        self.assertEqual(seen, [("starlink-all.csv", True)] if snapshot_bytes() else [])


if __name__ == "__main__":
    unittest.main()
