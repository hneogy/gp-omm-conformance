# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The pairs-case escapes (D-358), each with a wrong-on-purpose adapter and its twin: (a) the mmdot item never compared
MEAN_MOTION_DDOT, so a parser multiplying it by 6 passed; (b) a key the parser left out was not compared, in either
file; (e) on the KVN variant whose NORAD_CAT_ID keyword is absent, a value the guard could not read as an integer, or an
empty text, for one of its absent integer keywords passed as absent. (The copy checks, (c) and (d), are D-359's, split
off after D-358's third reading.)

The files are the corpus's own derived files or built at test time from the ISS record epoch-year-19xx freezes (no
provider's bytes, so the module runs in the public export). Run: python -m unittest tests.adversarial.test_pairs_escapes_080"""
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
from tests.adversarial.test_internal_errors_080 import answering  # noqa: E402
from tests.adversarial.test_strict_files_080 import LIVE  # noqa: E402

CONSISTENCY = "tle-values-match-omm-within-tle-precision"
MMDOT = "mmdot-is-tle-field-value"
KVN_NO_ID = "v05-omm-3.0-header-optional-keywords-omitted.kvn"


def parser(tle=None, omm=None):
    """The reference's records, each format's passed through its function."""
    class P(Reference):
        def parse(self, raw, fmt):
            out = [r for r in super().parse(raw, fmt) if "_refused" not in r]
            how = tle if fmt in ("tle", "2le") else omm
            return how(out) if how else out
    return P()


def without(*fields):
    return lambda rs: [{k: v for k, v in r.items() if k not in fields} for r in rs]


class PairsCaseEscapes(unittest.TestCase):

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-pairs-escapes-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def files(self, tle_sets, csv_sets=None):
        os.makedirs(os.path.join(self.data, LIVE), exist_ok=True)
        for name, text in (("iss.tle", tle_text(tle_sets)), ("iss.csv", csv_text(csv_sets or tle_sets))):
            with open(os.path.join(self.data, LIVE, name), "w", encoding="utf-8", newline="") as f:
                f.write(text)

    def items(self, p, case="tle-vs-omm-precision-loss"):
        res = Runner(p, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=[case])[0]
        self.assertNotIn("runner", {i.check for i in res.items})
        return {(i.check, os.path.basename(i.file or "")): i for i in res.items if "iss.tle" in (i.file or "") or "iss.csv" in (i.file or "")}

    def item(self, p, check, case="tle-vs-omm-precision-loss"):
        (it,) = [i for (c, _), i in self.items(p, case).items() if c == check]
        return it

    # (a)
    def test_a_ddot_six_times_too_large_fails_the_mmdot_item(self):
        """D-351's first reading, finding 2: the case says "MEAN_MOTION_DDOT likewise equals the TLE second-derivative
        field", and its item compared MEAN_MOTION_DOT alone; its twin, the reference, passes, in words that name both."""
        self.files(SETS[:1])
        times6 = parser(omm=lambda rs: [dict(r, mean_motion_ddot=Decimal(str(r["mean_motion_ddot"])) * 6) for r in rs])
        got = self.item(times6, MMDOT, "mean-motion-derivative-convention")
        self.assertEqual(got.status, "fail", got.detail)
        self.assertIn("mean_motion_ddot", got.detail)
        twin = self.item(Reference(), MMDOT, "mean-motion-derivative-convention")
        self.assertEqual(twin.status, "pass", twin.detail)
        self.assertIn("OMM MEAN_MOTION_DOT equals the TLE field as printed, and MEAN_MOTION_DDOT the TLE field's five rounded digits", twin.detail)

    # (b)
    def test_a_key_left_out_is_read_as_none(self):
        """D-351's second reading, finding 3: a key left out, on either side, was not compared, so a parser leaving every
        key out passed; a field every TLE carries left out, or None, on both sides read as equal."""
        self.files(SETS[:1])
        for f in ("mean_motion", "inclination", "ra_of_asc_node", "arg_of_pericenter", "mean_anomaly", "mean_motion_dot",
                  "eccentricity", "bstar", "mean_motion_ddot", "epoch"):
            for side, p in (("omm", parser(omm=without(f))), ("tle", parser(tle=without(f))), ("both", parser(tle=without(f), omm=without(f)))):
                with self.subTest(field=f, side=side):
                    # MEAN_MOTION_DOT is the mmdot item's, in the case that runs it; the others the consistency item's
                    got = (self.item(p, MMDOT, "mean-motion-derivative-convention") if f == "mean_motion_dot" else self.item(p, CONSISTENCY))
                    self.assertEqual(got.status, "fail", got.detail)
                    self.assertIn(f, got.detail)
                    self.assertIn("left out", got.detail)   # the words say it (D-358's first reading, mutant B10)
        with self.subTest("None on both sides"):
            got = self.item(parser(tle=lambda rs: [dict(r, mean_motion=None) for r in rs], omm=lambda rs: [dict(r, mean_motion=None) for r in rs]), CONSISTENCY)
            self.assertEqual(got.status, "fail", got.detail)
            self.assertIn("mean_motion: tle None omm None, where every TLE carries a value (D-358)", got.detail)
        twin = self.item(Reference(), CONSISTENCY)
        self.assertEqual(twin.status, "pass", twin.detail)

    def test_a_key_left_out_where_the_input_leaves_it_empty_passes(self):
        """Its twin: read as None, a BSTAR key left out of the OMM record where the input's CSV leaves it empty is judged
        as an empty answer is (D-351): it passes, the TLE field compared with the input's."""
        self.files([dict(SETS[0], BSTAR="0")], [dict(SETS[0], BSTAR="")])
        got = self.item(parser(omm=without("bstar")), CONSISTENCY)
        self.assertEqual(got.status, "pass", got.detail)

    def test_a_ddot_reaches_the_mmdot_item_on_every_path(self):
        """The check of the split's mended lines (mutants F1 to F5, each living): DDOT's failures where the parser's OMM
        answer is empty, or no TLE field holds it, reach the mmdot item too, as its mismatches do: the TLE value against
        the input's TLE record where the input's CSV leaves DDOT empty (an id held once, and held twice); an empty answer
        where the input gives a value; a value no TLE field holds; an empty answer for an id the input's OMM file does
        not hold; and, for an id held twice, an empty answer in a copy with no epoch, and one where no input copy leaves it
        empty near that epoch (the second check, mutants F6, F7). Each fails the mmdot item AND the consistency item,
        naming mean_motion_ddot (the third check: the consistency half was not asserted); the reference passes both. And
        the tolerance on the two TLE-file paths (mutants F8, F9 and their consistency halves): a TLE DDOT a float within
        the tolerance where the CSV leaves it empty, held once and twice, reads pass-tolerance in both items, naming the
        field."""
        ddot6 = lambda rs: [dict(r, mean_motion_ddot=Decimal(str(r["mean_motion_ddot"])) * 6) for r in rs]
        empty = lambda rs: [dict(r, mean_motion_ddot=None) for r in rs]
        renamed = lambda rs: [dict(r, norad_cat_id=25545) for r in rs]
        for name, sets, csv_sets, p in (
                ("held once, CSV empty, TLE wrong", SETS[:1], [dict(SETS[0], MEAN_MOTION_DDOT="")], parser(tle=ddot6, omm=empty)),
                ("held twice, CSV empty, TLE wrong", SETS[:2], [dict(s, MEAN_MOTION_DDOT="") for s in SETS[:2]], parser(tle=ddot6, omm=empty)),
                ("empty where the input gives one", SETS[:1], None, parser(omm=empty)),
                ("no TLE field holds it", SETS[:1], None, parser(omm=lambda rs: [dict(r, mean_motion_ddot=Decimal("1E+99")) for r in rs])),
                ("empty, for an id the OMM file does not hold", SETS[:1], None, parser(tle=renamed, omm=lambda rs: empty(renamed(rs)))),
                ("held twice, empty in a copy with no epoch", SETS[:2], [dict(s, MEAN_MOTION_DDOT="") for s in SETS[:2]],
                 parser(omm=lambda rs: [dict({k: v for k, v in rs[0].items() if k != "epoch"}, mean_motion_ddot=None)] + rs[1:])),
                ("held twice, empty where no copy leaves it empty", SETS[:2], None, parser(omm=empty))):
            with self.subTest(name):
                self.files(sets, csv_sets)
                for check, case in ((MMDOT, "mean-motion-derivative-convention"), (CONSISTENCY, "tle-vs-omm-precision-loss")):
                    got = self.item(p, check, case)
                    self.assertEqual(got.status, "fail", got.detail)
                    self.assertIn(f"id {25545 if 'does not hold' in name else 25544} mean_motion_ddot: ", got.detail)
                    twin = self.item(Reference(), check, case)
                    self.assertEqual(twin.status, "pass", twin.detail)
        near = lambda rs: [dict(r, mean_motion_ddot=float(Decimal(str(r["mean_motion_ddot"]))) * (1 + 1e-15)) for r in rs]
        for name, sets in (("held once", SETS[:1]), ("held twice", SETS[:2])):
            with self.subTest("tolerance, CSV empty, " + name):
                self.files(sets, [dict(s, MEAN_MOTION_DDOT="") for s in sets])
                for check, case in ((MMDOT, "mean-motion-derivative-convention"), (CONSISTENCY, "tle-vs-omm-precision-loss")):
                    got = self.item(parser(tle=near, omm=empty), check, case)
                    self.assertEqual(got.status, "pass-tolerance", got.detail)
                    self.assertIn("mean_motion_ddot", got.detail.split("within tolerance")[1])

    def test_a_ddot_within_the_float_tolerance_reads_so_in_the_mmdot_item(self):
        """D-358's first reading, mutants A2 and A6 (pinned before only by the golden test that skips without the
        maintainer's data): a TLE reader giving DDOT as a float a little off the field, within the tolerance (as
        python-sgp4's does), reads pass-tolerance in the mmdot item and in the consistency item, naming the field; the
        reference, given it exactly, passes the mmdot item. (The OMM value is rounded to the field's five digits before
        it is compared, so a float error on that side is not seen.)"""
        self.files(SETS[:1])
        near = parser(tle=lambda rs: [dict(r, mean_motion_ddot=float(Decimal(str(r["mean_motion_ddot"]))) * (1 + 1e-15)) for r in rs])
        got = self.item(near, MMDOT, "mean-motion-derivative-convention")
        self.assertEqual(got.status, "pass-tolerance", got.detail)
        self.assertIn("mean_motion_ddot", got.detail.split("within tolerance")[1])
        self.assertEqual(self.item(Reference(), MMDOT, "mean-motion-derivative-convention").status, "pass")
        # and in the consistency item, which holds DDOT too: its tolerances read in both (the split's short reading, a
        # mutant sending them to the mmdot item alone)
        got = self.item(near, CONSISTENCY)
        self.assertEqual(got.status, "pass-tolerance", got.detail)
        self.assertIn("mean_motion_ddot", got.detail.split("within tolerance")[1])

    # (e)
    def kvn(self, p):
        res = Runner(p, root=ROOT, fetch_hints=False).run(case_ids=["kvn-syntax-variants"])[0]
        (it,) = [i for i in res.items if i.check == "values" and (i.file or "").endswith(KVN_NO_ID)]
        return it

    def test_a_value_that_is_no_integer_is_no_absent_keyword(self):
        """D-355's first reading, finding 4, and D-356's second reading, finding 4 (the owner's ruling (e)): read as None,
        each passed as the keyword the file leaves out; each fails, its value named; its twin, the reference, passes."""
        for f, v in (("norad_cat_id", "garbage"), ("norad_cat_id", float("nan")), ("norad_cat_id", ""),
                     ("rev_at_epoch", "x"), ("rev_at_epoch", 1.5), ("rev_at_epoch", float("nan")),
                     ("element_set_no", "x"), ("element_set_no", 1.5), ("element_set_no", float("nan")),
                     ("ephemeris_type", "x"), ("ephemeris_type", 1.5), ("ephemeris_type", float("nan"))):
            with self.subTest(field=f, value=v):
                it = self.kvn(answering(lambda rs, f=f, v=v: [dict(rs[0], **{f: v})], fmts=("kvn",)))
                self.assertEqual(it.status, "fail", it.detail)
                self.assertIn(f"the record whose id the file leaves out: {f} should be absent/None (keyword omitted in source), got ", it.detail)
                self.assertIn("(D-358)", it.detail)
                # the value the guard marked, named (D-358's first reading, mutant E9)
                shown = {"garbage": "'garbage' (str)", "": "'' (an empty text)", "x": "'x' (str)", 1.5: "1.5 (float, fractional)"}.get(v, "nan (float)")
                self.assertIn(f"got {shown}", it.detail)
        twin = self.kvn(Reference())
        self.assertEqual(twin.status, "pass", twin.detail)


if __name__ == "__main__":
    unittest.main()
