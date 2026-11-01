# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Values and files that ended a case as "internal error in runner" now read as what they are (D-351, the runner's own
entry), with wrong-on-purpose adapters and twins.

Before: in the TLE/OMM consistency check an OMM BSTAR or second derivative that was empty (None or ""), or that no TLE
exponent field holds as providers write it (1E99, 1E-99, 1E30, Decimal('1E+1000000')), and an eccentricity of 1E+30, raised outside any
guard, the reference adapter itself ending a case so on a provider CSV with an empty BSTAR; and the SATCAT case raised on
an empty legacy satcat.txt (max() of no id) and read an error page an earlier fetch had saved in a file's place.

The files are built at test time from the ISS record epoch-year-19xx freezes (no provider's bytes, so the module runs
in the public export). Run: python -m unittest tests.adversarial.test_internal_errors_080"""
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
from gpconf.runner import Runner  # noqa: E402
from tests.adversarial.test_history_080 import SETS, csv_text, tle_text  # noqa: E402
from tests.adversarial.test_strict_files_080 import LIVE  # noqa: E402

ONE = SETS[:1]
PAIRS = "tle-vs-omm-precision-loss"   # a pairs case: the consistency item is its only item, nothing else fails a parser
B = "0.00012345"
CONSISTENCY = "tle-values-match-omm-within-tle-precision"
SATCAT = os.path.join("fixtures", "satcat-70000-cutoff", "raw")


def answering(how, fmts=("csv",)):
    class Adapter(Reference):
        def parse(self, raw, fmt):
            out = [r for r in super().parse(raw, fmt) if "_refused" not in r]
            return how(out) if fmt in fmts else out
    return Adapter()


class InternalErrorsReadAsWhatTheyAre(unittest.TestCase):

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-internal-errors-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def write(self, folder, name, text):
        os.makedirs(os.path.join(self.data, folder), exist_ok=True)
        with open(os.path.join(self.data, folder, name), "w", encoding="utf-8", newline="") as f:
            f.write(text)

    def pairs(self, parser, tle_sets, csv_sets):
        """The pairs case on the ISS files written from these sets: its consistency item."""
        self.write(LIVE, "iss.tle", tle_text(tle_sets))
        self.write(LIVE, "iss.csv", csv_text(csv_sets))
        res = Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=[PAIRS])[0]
        return {i.check: i for i in res.items}[CONSISTENCY]

    def assert_fails(self, item, words="where the input gives a value (D-351)"):
        self.assertEqual(item.status, "fail", item.detail)
        self.assertIn(words, item.detail)

    def assert_passes(self, item):
        self.assertEqual(item.status, "pass", item.detail)

    def test_an_empty_field_of_one_id_does_not_excuse_another(self):
        other = dict(SETS[0], NORAD_CAT_ID="25545", OBJECT_ID="1998-067B", BSTAR=B)
        sets, csv = [SETS[0], other], [dict(SETS[0], BSTAR=""), other]
        self.assert_fails(self.pairs(answering(lambda rs: [dict(r, bstar=None) for r in rs]), sets, csv))
        self.assert_passes(self.pairs(Reference(), sets, csv))

    def iss(self, parser, csv=None, sets=ONE):
        self.write(LIVE, "iss.tle", tle_text(sets))
        self.write(LIVE, "iss.csv", csv if csv is not None else csv_text(ONE))
        res = Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["baseline-iss-five-formats"])[0]
        return res, {i.check: i for i in res.items if i.check in (CONSISTENCY, "runner")}

    def test_the_reference_passes_a_csv_with_an_empty_bstar_and_second_derivative(self):
        res, got = self.iss(Reference(), csv_text([dict(ONE[0], BSTAR="", MEAN_MOTION_DDOT="")]))
        self.assertNotIn("runner", got, got.get("runner") and got["runner"].detail)
        self.assertEqual(got[CONSISTENCY].status, "pass", got[CONSISTENCY].detail)
        self.assertNotEqual(res.status, "fail", [(i.check, i.detail) for i in res.items if i.status == "fail"])

    def test_a_value_no_tle_field_can_hold_fails_the_item_naming_it(self):
        for field, value in (("bstar", "1E99"), ("bstar", "1E-99"), ("bstar", "1E30"), ("bstar", Decimal("1E+1000000")),
                             ("mean_motion_ddot", "1E-99"), ("eccentricity", "1E+30"), ("eccentricity", "-0.5"), ("eccentricity", "-1E-8"), ("eccentricity", "1.5")):
            with self.subTest(field=field, value=value):
                res, got = self.iss(answering(lambda rs: [dict(r, **{field: value}) for r in rs]))
                self.assertNotIn("runner", got, got.get("runner") and got["runner"].detail)
                self.assertEqual(got[CONSISTENCY].status, "fail", got[CONSISTENCY].detail)
                shown = Decimal(str(value))   # as the runner's reading holds it
                self.assertIn(f"{field}: omm {shown} is a value no TLE field holds as providers write it (D-351)", got[CONSISTENCY].detail)

    def test_a_value_the_input_gives_and_the_parser_drops_fails(self):
        """The reading's escape: the skip of an empty OMM value let a parser that drops one pass the item, and the pairs
        cases have no values item to fail it; an empty value is skipped only where the input's own record is empty."""
        for field in ("bstar", "mean_motion_ddot", "eccentricity"):
            for empty in (None, ""):
                with self.subTest(field=field, empty=empty):
                    res, got = self.iss(answering(lambda rs: [dict(r, **{field: empty}) for r in rs]))
                    self.assertNotIn("runner", got, got.get("runner") and got["runner"].detail)
                    self.assertEqual(got[CONSISTENCY].status, "fail", got[CONSISTENCY].detail)
                    # the runner reads an empty text as None before any check
                    self.assertIn(f"{field}: omm None, where the input gives a value (D-351)", got[CONSISTENCY].detail)

    def test_where_the_omm_record_is_empty_the_tle_value_is_compared_with_the_tle_file(self):
        """The second reading's finding 2: with the input's OMM BSTAR empty, nothing compared the TLE side; a parser
        answering a TLE BSTAR the file does not hold now fails. Its twin is the reference test above."""
        res, got = self.iss(answering(lambda rs: [dict(r, bstar="0.5") for r in rs], fmts=("tle",)), csv_text([dict(ONE[0], BSTAR="")]))
        self.assertEqual(got[CONSISTENCY].status, "fail", got[CONSISTENCY].detail)
        self.assertIn("vs the TLE file's 0 (the OMM record leaves it empty)", got[CONSISTENCY].detail)

    def test_its_twin_the_reference_on_a_csv_whose_bstar_alone_is_empty(self):
        res, got = self.iss(Reference(), csv_text([dict(ONE[0], BSTAR="")]))
        self.assertEqual(got[CONSISTENCY].status, "pass", got[CONSISTENCY].detail)

    def test_an_empty_value_under_an_id_the_input_does_not_hold_fails_saying_so(self):
        res, got = self.iss(answering(lambda rs: [dict(r, norad_cat_id=99998, bstar=None) for r in rs], fmts=("csv", "tle")))
        self.assertEqual(got[CONSISTENCY].status, "fail", got[CONSISTENCY].detail)
        self.assertIn("id 99998 bstar: omm None, for an id the input's OMM file does not hold (D-351)", got[CONSISTENCY].detail)
        # an id the TLE file holds and the OMM file does not (the short reading's finding 1)
        other = dict(SETS[0], NORAD_CAT_ID="25545", OBJECT_ID="1998-067B")
        self.assert_fails(self.pairs(answering(lambda rs: rs + [dict(rs[0], norad_cat_id=25545, bstar=None)]), [SETS[0], other], [SETS[0]]),
                          "id 25545 bstar: omm None, for an id the input's OMM file does not hold (D-351)")

    def test_the_twin_a_correct_answer_passes(self):
        res, got = self.iss(Reference())
        self.assertEqual(got[CONSISTENCY].status, "pass", got[CONSISTENCY].detail)
        self.assertNotIn("runner", got)

    def test_a_meta_file_that_is_not_an_object_is_read_as_no_record(self):
        """The second reading's finding 12, on the owner's ruling into this entry: load_source read .meta.json itself, and a
        list, a string or a directory there, or a reused_from or recorded that is not an object, ended the case as
        "internal error in runner"; now each reads as no record, the file read as data. Its twin is the error page
        test below, whose .meta.json records HTTP 404 and is refused."""
        for what, meta in (("a list", "[404]"), ("a string", '"404"'), ("a directory", None),
                           ("reused_from text", json.dumps({"reused_from": "0.7.0"})),
                           ("recorded text", json.dumps({"provenance": "recorded", "recorded": "x", "http_status": 200}))):
            with self.subTest(meta=what):
                shutil.rmtree(self.data, ignore_errors=True)
                os.makedirs(self.data)
                if meta is None:
                    os.makedirs(os.path.join(self.data, LIVE, "iss.csv.meta.json"))
                else:
                    self.write(LIVE, "iss.csv.meta.json", meta)
                res, got = self.iss(Reference())
                self.assertNotIn("runner", got, got.get("runner") and got["runner"].detail)
                self.assertEqual(got[CONSISTENCY].status, "pass", got[CONSISTENCY].detail)

    def test_a_kept_response_whose_meta_file_is_not_an_object_is_still_reported(self):
        self.write(LIVE, "iss.tle", tle_text(ONE))
        self.write(LIVE, "iss.csv.unexpected", "<html>503</html>")
        self.write(LIVE, "iss.csv.unexpected.meta.json", "[503]")
        res = Runner(Reference(), root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["baseline-iss-five-formats"])[0]
        items = {(i.check, os.path.basename(i.file or "")): i for i in res.items}
        self.assertNotIn(("runner", ""), items, [(i.check, i.detail) for i in res.items if i.check == "runner"])
        self.assertIn("kept that response as iss.csv.unexpected", items[("source-present", "iss.csv")].detail)

    def test_an_empty_reused_from_is_not_read_as_reused(self):
        """The third reading's finding 5: an empty reused_from read as reused ("reused from corpus None's cache")."""
        self.write(LIVE, "iss.csv.meta.json", json.dumps({"reused_from": {}}))
        res, _ = self.iss(Reference())
        self.assertEqual(res.reused, {})
        self.write(LIVE, "iss.csv.meta.json", json.dumps({"reused_from": {"corpus_version": "0.7.0"}}))   # its twin
        res, _ = self.iss(Reference())
        self.assertEqual(list(res.reused.values()), ["0.7.0"])

    def satcat(self, fetch_hints=False):
        res = Runner(Reference(), root=ROOT, data=self.data, fetch_hints=fetch_hints).run(case_ids=["satcat-70000-cutoff"])[0]
        return res, [(i.check, os.path.basename(i.file or ""), i.status, i.detail) for i in res.items]

    def test_the_remedy_for_an_error_page_names_the_fetch_that_brings_the_file(self):
        """The third reading's finding 5: the legacy satcat.txt comes only on request (D-231), so "fetch it again" names
        the flag that brings it; a file a plain fetch brings, its twin, names none."""
        for name in ("satcat.txt", "satcat-25544.json"):
            self.write(SATCAT, name, "<html>404 Not Found</html>")
            self.write(SATCAT, name + ".meta.json", json.dumps({"http_status": 404}))
        res, items = self.satcat(fetch_hints=True)
        said = {i[1]: i[3] for i in items if i[0] == "source-present"}
        self.assertRegex(said["satcat.txt"], r"then fetch it again with .*--")
        self.assertTrue(said["satcat-25544.json"].endswith("then fetch it again"), said["satcat-25544.json"])

    def test_an_empty_legacy_satcat_file_is_a_data_item(self):
        self.write(SATCAT, "satcat.txt", "")
        res, items = self.satcat()
        self.assertNotIn("runner", [c for c, _, _, _ in items], items)
        (legacy,) = [i for i in items if i[0] == "satcat-legacy-below-70000"]
        self.assertEqual(legacy[2], "not-exercised", legacy)
        self.assertIn("the file holds no SATCAT line (0 bytes)", legacy[3])

    def test_an_error_page_saved_in_a_satcat_files_place_is_not_read(self):
        self.write(SATCAT, "satcat-25544.json", "<html>404 Not Found</html>")
        self.write(SATCAT, "satcat-25544.json.meta.json", json.dumps({"http_status": 404, "retrieved_at": "2026-10-18T00:00:00Z"}))
        res, items = self.satcat()
        (item,) = [i for i in items if i[1] == "satcat-25544.json"]
        self.assertEqual((item[0], item[2]), ("source-present", "not-fetched"), item)
        # in load_source's words, its time included (the reading's finding 6)
        self.assertIn("holds an HTTP 404 response that an earlier fetch saved in the data's place at 2026-10-18T00:00:00Z", item[3])
        # keyed as expected.json names the file, with "/" on every system (os.path.join gave "\\" on Windows; lane C, 2026-10-24)
        self.assertTrue(res.unexpected["fixtures/satcat-70000-cutoff/raw/satcat-25544.json"]["in_place"], res.unexpected)
        self.assertNotIn("satcat-25544.json", res.modes and [os.path.basename(p) for p in res.modes])
        self.write(SATCAT, "satcat-25544.json.meta.json", json.dumps({"http_status": 200}))   # its twin, the answer recorded as 200
        res, items = self.satcat()
        (item,) = [i for i in items if i[1] == "satcat-25544.json"]
        self.assertEqual(item[0], "satcat-record", item)


if __name__ == "__main__":
    unittest.main()
