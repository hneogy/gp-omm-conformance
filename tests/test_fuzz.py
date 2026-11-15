# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""gpconf fuzz (D-415): an adapter fuzzed against the reference reader, opt-in, its findings reported only.

Run: python -m unittest tests.test_fuzz"""
import contextlib
import io
import math
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import fuzz as F  # noqa: E402
from gpconf.__main__ import main as gpconf_main  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import Unsupported, _Guarded  # noqa: E402


def fuzz(parser, count=60, seed=7, out=None):
    return F.fuzz_parse(_Guarded(parser, []), ROOT, seed, count, out)


class TheOracle(unittest.TestCase):
    def test_the_reference_reader_fuzzed_against_itself_has_no_finding(self):
        rep = fuzz(Reference(), count=150)
        self.assertEqual(rep["findings"], [], rep["findings"][:2])
        self.assertEqual(rep["observations"], [])
        self.assertEqual(rep["formats"], ["csv", "json", "kvn", "tle", "xml"])

    def test_a_run_is_repeated_by_its_seed(self):
        a, b = fuzz(Reference(), seed=11), fuzz(Reference(), seed=11)
        self.assertEqual(a, b)
        self.assertNotEqual(fuzz(Reference(), seed=12)["tally"], {})

    def test_a_misreading_is_a_finding_minimised_and_saved(self):
        class TenfoldEccentricity(Reference):
            def parse(self, raw, fmt):
                from decimal import Decimal
                return [dict(r, eccentricity=str(Decimal(str(r["eccentricity"])) * 10)) if "eccentricity" in r and r["eccentricity"] not in (None, "") else r
                        for r in Reference.parse(self, raw, fmt)]
        with tempfile.TemporaryDirectory() as d:
            rep = fuzz(TenfoldEccentricity(), out=d)
            differs = [f for f in rep["findings"] if f["category"] == "differs"]
            self.assertTrue(differs)
            self.assertIn("eccentricity reads", differs[0]["detail"])
            saved = os.path.join(d, differs[0]["saved"])
            with open(os.path.join(ROOT, differs[0]["source"]), "rb") as f:
                self.assertLessEqual(os.path.getsize(saved), len(f.read()) + 16)

    def test_an_exit_is_a_crash(self):
        class Exits(Reference):
            def parse(self, raw, fmt):
                if fmt == "kvn":
                    raise SystemExit(3)
                return Reference.parse(self, raw, fmt)
        rep = fuzz(Exits())
        self.assertTrue([f for f in rep["findings"] if f["category"] == "crash" and f["fmt"] == "kvn"])

    def test_accepting_what_the_reference_refuses_is_an_observation_not_a_finding(self):
        class Lenient(Reference):
            def parse(self, raw, fmt):
                try:
                    return Reference.parse(self, raw, fmt)
                except Exception:
                    return [{"norad_cat_id": 1, "epoch": "2000-01-01T00:00:00.000000"}]
        rep = fuzz(Lenient(), count=150)
        self.assertTrue(rep["observations"])
        self.assertFalse([f for f in rep["findings"] if f["category"] == "crash"])

    def test_a_record_dropped_without_a_refusal_is_a_finding_and_refused_is_not(self):
        class DropsLast(Reference):
            REFUSE = False

            def parse(self, raw, fmt):
                out = [r for r in Reference.parse(self, raw, fmt) if "norad_cat_id" in r]
                if len(out) < 2:
                    return out
                last = out.pop()
                return out + ([{"_refused": "no", "_field": str(last["norad_cat_id"])}, {"_adapter": {"refusals": True}}] if self.REFUSE else [])
        dropped = fuzz(DropsLast(), count=80)["findings"]
        self.assertTrue([f for f in dropped if f["category"] == "dropped"])

        class RefusesLast(DropsLast):
            REFUSE = True
        self.assertFalse([f for f in fuzz(RefusesLast(), count=80)["findings"] if f["category"] == "dropped"])

    def test_returning_a_set_the_reference_refuses_beside_good_ones_is_an_observation(self):
        """python-sgp4's way with a corrupt set among good ones: leniency, reported apart, never a finding."""
        class KeepsEverything(Reference):
            def parse(self, raw, fmt):
                out = Reference.parse(self, raw, fmt)
                return [r for r in out if "_refused" not in r] + [{"norad_cat_id": 424242, "epoch": "2000-01-01T00:00:00.000000"}] * any("_refused" in r for r in out)
        rep = fuzz(KeepsEverything(), count=120)
        self.assertEqual([f for f in rep["findings"] if f["category"] != "dropped"], [])
        self.assertTrue(rep["observations"])

    def test_a_default_where_the_reference_reads_nothing_is_no_finding(self):
        """The review of D-415: a blank derivative read as 0 by the reader and as absent by the reference."""
        class Zeros(Reference):
            def parse(self, raw, fmt):
                return [dict(r, mean_motion_ddot=r.get("mean_motion_ddot") if r.get("mean_motion_ddot") not in (None, "") else "0")
                        if "norad_cat_id" in r else r for r in Reference.parse(self, raw, fmt)]
        self.assertEqual(fuzz(Zeros(), count=300, seed=2)["findings"], [])

    def test_floats_and_an_infinity_for_a_value_past_their_range_are_no_finding(self):
        class Floats(Reference):
            def parse(self, raw, fmt):
                out = []
                for r in Reference.parse(self, raw, fmt):
                    if "norad_cat_id" in r:
                        r = {k: (float(v) if k in F.COMPARED and k not in ("norad_cat_id", "epoch", "classification_type", "ephemeris_type", "element_set_no", "rev_at_epoch")
                                 and v not in (None, "") else v) for k, v in r.items()}
                    out.append(r)
                return out
        self.assertEqual(fuzz(Floats(), count=300, seed=2)["findings"], [])

    def test_a_dropped_copy_of_a_repeated_id_is_a_finding(self):
        b = {"norad_cat_id": 5, "epoch": "2000-01-01T00:00:00.000000", "mean_motion": "1"}
        b2 = dict(b, mean_motion="2")
        self.assertEqual(F.judge([b], [], [b, b2], [])[0], "dropped")
        self.assertEqual(F.judge([b2, b], [], [b, b2], [])[0], "ok")   # copies matched in any order

    def test_a_refusal_without_a_reason_is_no_refusal(self):
        b = {"norad_cat_id": 5, "epoch": "2000-01-01T00:00:00.000000"}
        self.assertEqual(F.judge([], [{"id": 5, "ok": False, "reason": None}], [b], [])[0], "dropped")
        self.assertEqual(F.judge([], [{"id": 5, "ok": True, "reason": "no"}], [b], [])[0], "ok")

    def test_a_nan_in_a_good_record_beside_a_refused_one_is_a_finding(self):
        """D-417 (the second reading of D-415): the leniency call is made per record, by its own id."""
        good = {"norad_cat_id": 5, "epoch": "2000-01-01T00:00:00.000000", "mean_motion": "1"}
        nan = dict(good, mean_motion=float("nan"))
        refused = [{"id": 7, "ok": True, "reason": "line 2 short", "field": "7", "input": None}]
        self.assertEqual(F.judge([nan], [], [good], refused)[0], "unreadable")
        self.assertEqual(F.judge([good, dict(nan, norad_cat_id=7)], [], [good], refused)[0], "lenient")   # the refused set's own record

    def test_a_nan_planted_in_the_first_good_record_is_found_beside_refusals(self):
        class PlantsNan(Reference):
            def parse(self, raw, fmt):
                out = Reference.parse(self, raw, fmt)
                for i, r in enumerate(out):
                    if "norad_cat_id" in r and "mean_motion" in r:
                        out[i] = dict(r, mean_motion=float("nan"))
                        break
                return out
        rep = fuzz(PlantsNan(), count=200, seed=0)
        self.assertGreater(sum(1 for f in rep["findings"] if f["category"] == "unreadable"), 50)

    def test_a_nan_copy_of_a_refused_set_beside_the_real_set_of_its_id_is_an_observation(self):
        """The check of D-417: a duplicated TLE line makes a corrupt copy of an id the reference refuses, beside the
        real set it reads; a reader returning the refused copy with a NaN, and the real set right, is lenient."""
        good = {"norad_cat_id": 5, "epoch": "2000-01-01T00:00:00.000000", "mean_motion": "1"}
        refused = [{"id": 5, "ok": True, "reason": "line 2 short", "field": "5", "input": None}]
        self.assertEqual(F.judge([good, dict(good, mean_motion=float("nan"))], [], [good], refused)[0], "lenient")

    def test_copies_are_counted_as_d311_counts_them(self):
        """D-421, the owner's ruling: exact duplicates follow D-311 (the second blind audit's F1). The input holds
        an id as often as the reference reads it; fewer copies returned is a dropped copy, more is a surplus."""
        x = {"norad_cat_id": 5, "epoch": "2000-01-01T00:00:00.000000", "mean_motion": "1"}
        y = dict(x, mean_motion="2")
        self.assertEqual(F.judge([y], [], [x, dict(x), y], [])[0], "dropped")
        self.assertEqual(F.judge([x, y], [], [x, dict(x), y], [])[0], "dropped")
        self.assertEqual(F.judge([x, dict(x), y], [], [x, dict(x), y], [])[0], "ok")
        self.assertEqual(F.judge([x], [], [x, dict(x)], [])[0], "dropped")
        self.assertEqual(F.judge([], [], [x, dict(x)], [])[0], "dropped")

    def test_one_copy_of_an_exact_duplicate_refused_with_a_reason_is_fine(self):
        x = {"norad_cat_id": 5, "epoch": "2000-01-01T00:00:00.000000", "mean_motion": "1"}
        refusal = [{"id": 5, "ok": True, "reason": "a second copy of 5", "field": None, "input": None}]
        self.assertEqual(F.judge([x], refusal, [x, dict(x)], [])[0], "ok")

    def test_a_record_returned_twice_where_the_input_holds_it_once_is_a_surplus(self):
        """D-311's own case, the red team's win_f1_dup_exact: every record returned twice."""
        x = {"norad_cat_id": 5, "epoch": "2000-01-01T00:00:00.000000", "mean_motion": "1"}
        self.assertEqual(F.judge([x, dict(x)], [], [x], [])[0], "surplus")

        class Doubles(Reference):
            def parse(self, raw, fmt):
                out = Reference.parse(self, raw, fmt)
                return out + [dict(r) for r in out]
        rep = fuzz(Doubles(), count=60)
        self.assertGreater(sum(1 for f in rep["findings"] if f["category"] == "surplus"), 20)

    def test_an_extra_copy_is_lenient_where_the_reference_refuses_a_set_of_its_id_or_one_unnamed(self):
        x = {"norad_cat_id": 5, "epoch": "2000-01-01T00:00:00.000000", "mean_motion": "1"}
        for rid in (5, None):
            refused = [{"id": rid, "ok": True, "reason": "line 2 short", "field": None, "input": None}]
            with self.subTest(refused_id=rid):
                self.assertEqual(F.judge([x, dict(x)], [], [x], refused)[0], "lenient")

    def test_an_empty_record_of_the_reference_is_no_record_to_drop(self):
        """D-429, found by the review of D-421: a KVN whose first line is written twice makes the reference read an
        empty message beside the real one; a reader that skips it dropped nothing."""
        with open(os.path.join(ROOT, "derived", "ephemeris-type-4", "type0.kvn"), "rb") as f:
            data = f.read()
        lines = data.split(b"\n")
        doubled = b"\n".join([lines[0]] + lines)
        want, ref_refusals = F.reference_reading(doubled, "kvn")
        self.assertEqual(len(want), 2)   # the empty message and the real one, as the reference reads them
        one, _ = F.reference_reading(data, "kvn")
        self.assertEqual(F.judge(one, [], want, ref_refusals)[0], "ok")
        self.assertEqual(F.judge(want, [], want, ref_refusals)[0], "ok")   # the review of D-429: returning it is no surplus
        noid = [dict(r, norad_cat_id=None) for r in want]   # v05's case: the real record carries no id either
        self.assertEqual(F.judge(noid, [], noid, ref_refusals)[0], "ok")
        self.assertEqual(F.judge([], [], want, ref_refusals)[0], "dropped")

    def test_a_surplus_copy_that_disagrees_is_a_surplus_too(self):
        """The review of D-421: D-311 counts copies, agreeing or not; a second copy with another mean motion beside
        the one the input holds is a surplus."""
        x = {"norad_cat_id": 5, "epoch": "2000-01-01T00:00:00.000000", "mean_motion": "1"}
        self.assertEqual(F.judge([x, dict(x, mean_motion="3")], [], [x], [])[0], "surplus")

    def test_a_format_it_does_not_read_is_left_out(self):
        class TleOnly(Reference):
            def parse(self, raw, fmt):
                if fmt != "tle":
                    raise Unsupported(fmt)
                return Reference.parse(self, raw, fmt)
        rep = fuzz(TleOnly())
        self.assertEqual(rep["formats"], ["tle"])
        self.assertEqual(rep["formats_unsupported"], ["csv", "json", "kvn", "xml"])

    def test_every_operator_mutates(self):
        import random
        for path, fmt in F.seeds(ROOT)[:20]:
            with open(os.path.join(ROOT, path), "rb") as f:
                data = f.read()
            for i in range(10):
                out, op = F.mutate(data, fmt, random.Random(f"m:{path}:{i}"))
                with self.subTest(path=path, op=op):
                    self.assertNotEqual(out, data)


class ThePropagateHook(unittest.TestCase):
    def prop(self, answer):
        class P(Reference):
            def propagate(self, raw, fmt, tsince):
                return answer(tsince)
        return F.fuzz_propagate(_Guarded(P(), []), ROOT)

    def test_nan_with_code_0_is_silent_nan(self):
        rep = self.prop(lambda ts: [{"r": [math.nan] * 3, "v": [math.nan] * 3, "error": 0} for _ in ts])
        self.assertEqual({f["category"] for f in rep["findings"]}, {"silent-nan"})

    def test_codes_and_finite_values_are_no_finding(self):
        rep = self.prop(lambda ts: [{"r": [7000.0, 0.0, 0.0], "v": [0.0, 7.5, 0.0], "error": 0} if abs(t) < 1e5 else {"r": None, "v": None, "error": 1}
                                    for t in ts])
        self.assertEqual(rep["findings"], [])

    def test_one_set_unsupported_keeps_the_others_findings(self):
        class P(Reference):
            def propagate(self, raw, fmt, tsince):
                if b"2056-" in raw:
                    raise Unsupported("no epochs past 2050")
                return [{"r": [math.nan] * 3, "v": [math.nan] * 3, "error": 0} for _ in tsince]
        rep = F.fuzz_propagate(_Guarded(P(), []), ROOT)
        self.assertTrue(rep["findings"])
        self.assertEqual(rep["tally"].get("unsupported"), 1)

    def test_no_hook_skips(self):
        self.assertIn("skipped", F.fuzz_propagate(_Guarded(Reference(), []), ROOT))


class TheCommand(unittest.TestCase):
    def test_gpconf_fuzz_runs_the_reference_and_says_it_moves_no_verdict(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gpconf_main(["fuzz", "--preset", "reference", "--count", "30", "--seed", "3", "--root", ROOT])
        self.assertEqual(code, 0)
        self.assertIn("fuzz: 30 inputs, seed 3", out.getvalue())
        self.assertIn("0 findings:", out.getvalue())
        self.assertIn("never move a case verdict", out.getvalue())

    def test_strict_exits_1_on_a_finding_and_0_without(self):
        """D-422, the owner's ruling: an opt-in --strict for an adapter's own CI step; the default stays 0."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "gpconf_d422_tenfold.py")
            with open(path, "w", encoding="utf-8") as f:
                f.write("from gpconf.adapters.reference import Parser as R\n"
                        "class Parser(R):\n"
                        "    def parse(self, raw, fmt):\n"
                        "        return [dict(r, eccentricity=str(float(r['eccentricity']) * 10)) if r.get('eccentricity') not in (None, '') else r for r in R.parse(self, raw, fmt)]\n")
            sys.path.insert(0, d)
            self.addCleanup(sys.modules.pop, "gpconf_d422_tenfold", None)
            self.addCleanup(sys.path.remove, d)
            mod = "gpconf_d422_tenfold"
            for argv, want in ((["--preset", "reference", "--strict"], 0), (["--adapter", mod], 0), (["--adapter", mod, "--strict"], 1)):
                out = io.StringIO()
                with self.subTest(argv=argv), contextlib.redirect_stdout(out):
                    self.assertEqual(gpconf_main(["fuzz", "--count", "20", "--seed", "3", "--root", ROOT] + argv), want)
                    self.assertEqual("--strict: exit 1" in out.getvalue(), want == 1)

    def test_fuzz_needs_a_parser(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            gpconf_main(["fuzz", "--root", ROOT])

    def test_options_that_do_not_belong_are_errors(self):
        with tempfile.NamedTemporaryFile() as f:
            for argv in (["fuzz", "--preset", "reference", "--case", "corrupt-input"], ["run", "--preset", "reference", "--count", "5"],
                         ["run", "--preset", "reference", "--strict"],
                         ["fuzz", "--preset", "reference", "--out", f.name], ["fuzz", "--write-cmd", "true"]):
                with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    gpconf_main(argv + ["--root", ROOT])


if __name__ == "__main__":
    unittest.main()
