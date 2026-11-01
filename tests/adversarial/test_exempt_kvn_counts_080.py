# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The exempt KVN file's counts (D-357, split off D-356 by the owner after its third reading), with wrong-on-purpose
adapters and twins: the one record of the KVN file without NORAD_CAT_ID counted loaded and misidentified both, where the
file's bytes are the snapshot's and where they are not; a record whose id is not an integer counted loaded; and D-311's
words naming an id no copy carried.

The files are the corpus's own derived files or built at test time from the ISS record epoch-year-19xx freezes (no
provider's bytes, so the module runs in the public export). Run: python -m unittest tests.adversarial.test_exempt_kvn_counts_080"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import CaseResult, Runner  # noqa: E402
from tests.adversarial.test_history_080 import SETS, csv_text, tle_text  # noqa: E402
from tests.adversarial.test_internal_errors_080 import answering  # noqa: E402
from tests.adversarial.test_strict_files_080 import LIVE  # noqa: E402

KVN_NO_ID = "v05-omm-3.0-header-optional-keywords-omitted.kvn"


class ExemptKvnCounts(unittest.TestCase):

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-exempt-kvn-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def iss_item(self, parser, check):
        os.makedirs(os.path.join(self.data, LIVE), exist_ok=True)
        for name, text in (("iss.tle", tle_text(SETS[:1])), ("iss.csv", csv_text(SETS[:1]))):
            with open(os.path.join(self.data, LIVE, name), "w", encoding="utf-8", newline="") as f:
                f.write(text)
        res = Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["baseline-iss-five-formats"])[0]
        (item,) = [i for i in res.items if i.check == check and (i.file or "").endswith("iss.csv")]
        return item

    def kvn(self, parser, root=ROOT):
        res = Runner(parser, root=root, fetch_hints=False).run(case_ids=["kvn-syntax-variants"])[0]
        (item,) = [i for i in res.items if i.check == "values" and (i.file or "").endswith(KVN_NO_ID)]
        return item

    def test_the_one_record_of_a_kvn_file_without_its_id_is_counted_once(self):
        """The reference's one record of the file whose NORAD_CAT_ID keyword is absent read loaded 1, misidentified 1,
        extra 1; it is loaded 1 and nothing else. The record returned twice, both without an id, is a duplicate copy, as
        on a file that carries its id (D-355's first reading, finding 1), not also misidentified. Its twin: a second record under
        an id the file does not hold is counted misidentified."""
        c = self.kvn(Reference()).counts
        self.assertEqual({k: c[k] for k in ("expected", "loaded", "misidentified", "extra", "dropped")},
                         {"expected": 1, "loaded": 1, "misidentified": 0, "extra": 0, "dropped": 0})
        item = self.kvn(answering(lambda rs: rs + [dict(rs[0])], fmts=("kvn",)))
        c = item.counts
        self.assertEqual({k: c[k] for k in ("loaded", "misidentified", "extra", "duplicate_copies")},
                         {"loaded": 1, "misidentified": 0, "extra": 1, "duplicate_copies": 1})
        # named as the record the file leaves without an id, not by an id no copy carried (D-356's second reading, finding 5)
        self.assertIn("the record whose id the file leaves out: returned 2 times where the input holds it once (D-311)", item.detail)
        self.assertNotIn("id 25544", item.detail)
        c = self.kvn(answering(lambda rs: rs + [dict(rs[0], norad_cat_id=99998)], fmts=("kvn",))).counts
        self.assertEqual((c["loaded"], c["misidentified"]), (1, 1))
        # D-355's second reading, finding 2: the right id and a record without one, the second still misidentified
        c = self.kvn(answering(lambda rs: [dict(rs[0], norad_cat_id=25544), dict(rs[0])], fmts=("kvn",))).counts
        self.assertEqual((c["loaded"], c["misidentified"], c["extra"]), (1, 1, 1))

    def test_the_kvn_file_without_its_id_counts_alike_when_its_bytes_are_not_the_snapshots(self):
        """D-355's second reading, finding 1: where the file's bytes differ from the snapshot (a comment line added, in a
        root of this case's own), the oracle is the reference reader's, keyed None as the record is, and the record
        was counted twice there still; it counts loaded 1 alone, and returned twice a duplicate copy."""
        root = tempfile.mkdtemp(prefix="gpconf-kvn-drift-")
        self.addCleanup(shutil.rmtree, root, True)
        shutil.copy(os.path.join(ROOT, "manifest.json"), root)
        shutil.copytree(os.path.join(ROOT, "fixtures", "kvn-syntax-variants"), os.path.join(root, "fixtures", "kvn-syntax-variants"))
        shutil.copytree(os.path.join(ROOT, "derived", "kvn-variants"), os.path.join(root, "derived", "kvn-variants"))
        path = os.path.join(root, "derived", "kvn-variants", KVN_NO_ID)
        with open(path, encoding="utf-8", newline="") as f:
            lines = f.read().split("\n")
        lines.insert(1, "COMMENT a line the snapshot does not hold")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("\n".join(lines))
        c = self.kvn(Reference(), root).counts
        self.assertEqual({k: c[k] for k in ("expected", "loaded", "misidentified", "extra")}, {"expected": 1, "loaded": 1, "misidentified": 0, "extra": 0})
        item = self.kvn(answering(lambda rs: rs + [dict(rs[0])], fmts=("kvn",)), root)
        c = item.counts
        self.assertEqual({k: c[k] for k in ("loaded", "misidentified", "extra", "duplicate_copies")},
                         {"loaded": 1, "misidentified": 0, "extra": 1, "duplicate_copies": 1})
        # the oracle keyed None here, the D-311 words still name the record, not "id None" (D-357's first reading, finding 2)
        self.assertIn("the record whose id the file leaves out: returned 2 times where the input holds it once (D-311)", item.detail)
        self.assertNotIn("id None", item.detail)
        # a record whose id is not an integer, as on the snapshot's bytes (D-357's second reading, finding 1): alone
        # misidentified, the id not returned; before a record without an id, not a duplicate copy
        for bad in ("garbage", float("nan")):
            with self.subTest(id=bad):
                item = self.kvn(answering(lambda rs: [dict(rs[0], norad_cat_id=bad)], fmts=("kvn",)), root)
                c = item.counts
                self.assertEqual({k: c[k] for k in ("loaded", "misidentified", "extra", "duplicate_copies", "non_integer_id", "ids_not_returned")},
                                 {"loaded": 0, "misidentified": 1, "extra": 0, "duplicate_copies": 0, "non_integer_id": 1, "ids_not_returned": 1})
                self.assertEqual(item.status, "fail")   # its value named (D-358)
                self.assertTrue(item.detail.startswith("1 compared vs "), item.detail)
                self.assertIn("norad_cat_id should be absent/None (keyword omitted in source), got ", item.detail)
                item = self.kvn(answering(lambda rs: [dict(rs[0], norad_cat_id=bad), rs[0]], fmts=("kvn",)), root)
                c = item.counts
                self.assertEqual({k: c[k] for k in ("loaded", "misidentified", "extra", "duplicate_copies", "ids_not_returned")},
                                 {"loaded": 1, "misidentified": 1, "extra": 1, "duplicate_copies": 0, "ids_not_returned": 0})
                self.assertIn("the record whose id the file leaves out: returned 2 times where the input holds it once (D-311)", item.detail)
        # the right id and a record without one, and a wrong id, as on the snapshot's bytes (D-356's second reading, finding 2)
        c = self.kvn(answering(lambda rs: [dict(rs[0], norad_cat_id=25544), dict(rs[0])], fmts=("kvn",)), root).counts
        self.assertEqual((c["loaded"], c["misidentified"], c["extra"]), (1, 1, 1))
        c = self.kvn(answering(lambda rs: rs + [dict(rs[0], norad_cat_id=99998)], fmts=("kvn",)), root).counts
        self.assertEqual((c["loaded"], c["misidentified"]), (1, 1))

    def test_a_record_whose_id_is_not_an_integer_is_still_misidentified(self):
        """D-355's third reading, finding 4: on the exempt KVN file a record whose id is not an integer was counted
        loaded, misidentified and extra all at once (a record taken for the file's own and for a wrong id both); it is
        misidentified alone, as ADAPTERS.md defines it, and an id no good copy came back under is an id not returned. Its
        twin: a record without an id whose other integer field is not an integer ("x") is the file's own record, loaded and
        not misidentified. Such a record fails the item, its value named (D-358, on the owner's ruling (e)); the words
        count the record graded, with no note (the owner's ruling on D-356's split)."""
        for bad in ("garbage", float("nan")):
            with self.subTest(id=bad, alone=True):
                # misidentified, and neither loaded nor a duplicate copy (D-356's first reading, finding 1)
                item = self.kvn(answering(lambda rs: [dict(rs[0], norad_cat_id=bad)], fmts=("kvn",)))
                c = item.counts
                self.assertEqual({k: c[k] for k in ("loaded", "misidentified", "extra", "duplicate_copies", "non_integer_id", "ids_not_returned")},
                                 {"loaded": 0, "misidentified": 1, "extra": 0, "duplicate_copies": 0, "non_integer_id": 1, "ids_not_returned": 1})
                # the words count the record graded, with no note; the record fails, its value named (D-358)
                self.assertEqual(item.status, "fail")
                self.assertTrue(item.detail.startswith("1 compared vs frozen expected values; the record whose id the file leaves out: "
                                                       "norad_cat_id should be absent/None (keyword omitted in source), got "), item.detail)
                self.assertNotIn("not loaded", item.detail)
            with self.subTest(id=bad, beside_a_good_record=True):
                # beside the right record without an id it reads as a wrong id beside the right one does: no duplicate copy
                c = self.kvn(answering(lambda rs: [rs[0], dict(rs[0], norad_cat_id=bad)], fmts=("kvn",))).counts
                self.assertEqual({k: c[k] for k in ("loaded", "misidentified", "extra", "duplicate_copies", "ids_not_returned")},
                                 {"loaded": 1, "misidentified": 1, "extra": 1, "duplicate_copies": 0, "ids_not_returned": 0})
            with self.subTest(id=bad, twice=True):
                # two such records, no good one: the failing item's head counts the record graded, 1, not the 0 loaded
                item = self.kvn(answering(lambda rs: [dict(rs[0], norad_cat_id=bad)] * 2, fmts=("kvn",)))
                self.assertTrue(item.detail.startswith("1 compared vs frozen expected values; "), item.detail)
                self.assertEqual((item.counts["loaded"], item.counts["misidentified"], item.counts["ids_not_returned"]), (0, 2, 1))
        # the twin (D-356's second reading, finding 3): another integer field not an integer leaves the record the file's own
        item = self.kvn(answering(lambda rs: [dict(rs[0], rev_at_epoch="x")], fmts=("kvn",)))
        c = item.counts
        self.assertEqual({k: c[k] for k in ("loaded", "misidentified", "extra", "duplicate_copies", "non_integer_id", "ids_not_returned")},
                         {"loaded": 1, "misidentified": 0, "extra": 0, "duplicate_copies": 0, "non_integer_id": 0, "ids_not_returned": 0})
        self.assertNotIn("not loaded", item.detail)

    def test_a_file_that_carries_its_id_reads_as_before(self):
        """D-356's third reading, finding 2 (mutant C2): the words' number is the records graded, one copy each at most,
        which on a file that carries its id is the records loaded, as before: an ISS CSV (graded live, built at test
        time) returned twice is "1 compared", as it was, with D-311's words naming the id."""
        item = self.iss_item(answering(lambda rs: rs + rs), "values")
        self.assertTrue(item.detail.startswith("1 compared vs "), item.detail)
        self.assertIn("; id 25544: returned 2 times where the input holds it once (D-311)", item.detail)
        self.assertEqual((item.counts["loaded"], item.counts["duplicate_copies"]), (1, 1))

    def test_a_file_not_exempt_with_an_oracle_keyed_none_reads_as_before(self):
        """D-357's first reading, finding 3 (mutant M26): the exempt branch is the exempt file's alone. A file that is not
        exempt whose oracle holds a record without an id (a live file the reference reads without NORAD_CAT_ID), by a
        direct call as test_redteam2 makes: a record without an id still misidentified, a second one D-311's "id None",
        a record whose id is not an integer still loaded, the counts as before this entry."""
        runner = Runner(Reference(), root=ROOT, fetch_hints=False)
        path = os.path.join(ROOT, "derived", "kvn-variants", "v01-baseline-reserialised.kvn")
        (rec,) = runner.parse(path, "kvn")
        want = dict({k: v for k, v in rec.items() if not k.startswith("_")}, norad_cat_id=None)
        idless = dict(rec, norad_cat_id=None)
        bad = dict(rec, norad_cat_id=None, _bad={"norad_cat_id": "'garbage' (str)"})
        keys = ("loaded", "misidentified", "extra", "duplicate_copies")
        for name, parsed, counts, words in (("without an id", [idless], (1, 1, 1, 0), None),
                                            ("twice", [idless, dict(idless)], (1, 2, 3, 1), "id None: returned 2 times"),
                                            ("an id not an integer", [bad], (1, 1, 1, 0), None)):
            with self.subTest(name):
                res = CaseResult("x", "x")
                runner.compare_values(res, path, "kvn", "live", parsed, {None: want})
                (item,) = [i for i in res.items if i.check == "values"]
                self.assertEqual(tuple(item.counts[k] for k in keys), counts)
                self.assertEqual(item.status, "fail")
                if words:
                    self.assertIn(words, item.detail)
                self.assertNotIn("leaves out", item.detail)
        # the words' number capped by the expected records (`times`, the records without an id counted once), not by the
        # records the input holds (`held`; D-357's third reading, mutant N7): two records without an id, held twice,
        # "1 compared" as before
        res = CaseResult("x", "x")
        runner.compare_values(res, path, "kvn", "live", [dict(idless), dict(idless)], {None: dict(want, _copies=[want, dict(want)])},
                              held={None: 2})
        (item,) = [i for i in res.items if i.check == "values"]
        self.assertTrue(item.detail.startswith("1 compared vs "), item.detail)
        self.assertEqual((item.counts["expected"], item.counts["loaded"], item.counts["misidentified"]), (1, 1, 2))


if __name__ == "__main__":
    unittest.main()
