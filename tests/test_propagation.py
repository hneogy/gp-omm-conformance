# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The propagation tier (D-401): grading a parser's propagate hook against Vallado's verification files.

The grading is tested on invented numbers written here, so it runs everywhere; the case itself needs the two files,
located on the machine (gpconf ships neither, D-388), so those tests skip where python-sgp4 or the private copy is
absent, as in an export without python-sgp4.

Run: python -m unittest tests.test_propagation"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gpconf import propagation as P  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import CommandParser, Runner  # noqa: E402

# an invented reference set: three steps, positions and velocities of no real orbit
REF = {"catalog": 99901, "times": [0.0, 60.0, 120.0], "error": None, "stale": False,
       "rows": [(0.0, 7000.0, 0.0, 0.0, 0.0, 7.5, 0.0), (60.0, 6000.0, 3000.0, 100.0, -3.0, 6.0, 1.0),
                (120.0, 5000.0, 5000.0, 200.0, -5.0, 5.0, 2.0)]}


def steps(rows, dr=0.0, codes=None):
    return [{"r": [x + dr, y, z], "v": [vx, vy, vz], "error": (codes or {}).get(i, 0)} for i, (t, x, y, z, vx, vy, vz) in enumerate(rows)]


class TheGrading(unittest.TestCase):
    def test_exact_and_within_the_bar(self):
        for dr in (0.0, 1.9e-7):
            problems, st = P.grade_set(REF, steps(REF["rows"], dr))
            self.assertEqual(problems, {"values": [], "codes": []})
            self.assertEqual(st["compared"], 3)

    def test_beyond_the_bar_fails_naming_the_step(self):
        problems, st = P.grade_set(REF, steps(REF["rows"], 3e-7))
        self.assertEqual(len(problems["values"]), 3)
        self.assertIn("t = 0: position off by 3e-07 km", problems["values"][0])
        self.assertAlmostEqual(st["max_r"], 3e-7, delta=1e-12)

    def test_a_false_decay_and_a_silent_run(self):
        problems, _ = P.grade_set(REF, steps(REF["rows"], codes={1: 6}))
        self.assertIn("false decay", problems["codes"][0])
        ref = dict(REF, error={"code": 6, "at_minutes": 120.0, "step_index": 2}, rows=REF["rows"][:2])
        problems, _ = P.grade_set(ref, steps(REF["rows"]))
        self.assertIn("a silent propagation", problems["codes"][0])
        problems, _ = P.grade_set(ref, steps(REF["rows"], codes={2: 6}))
        self.assertEqual(problems, {"values": [], "codes": []})
        problems, _ = P.grade_set(ref, steps(REF["rows"], codes={2: 1}))
        self.assertIn("error 1 where the reference ends the run with error 6", problems["codes"][0])

    def test_answers_that_are_no_answer(self):
        for bad in (None, "x", steps(REF["rows"])[:2]):
            self.assertTrue(P.grade_set(REF, bad)[0]["values"])
        nan = steps(REF["rows"])
        nan[1]["r"][0] = float("nan")
        self.assertIn("three finite numbers", P.grade_set(REF, nan)[0]["values"][0])
        boolish = steps(REF["rows"])
        boolish[0]["error"] = False
        self.assertIn("no integer", P.grade_set(REF, boolish)[0]["codes"][0])

    def test_files_with_other_bytes_are_not_used(self):
        with tempfile.TemporaryDirectory() as d:
            for f in P.FILES:
                with open(os.path.join(d, f), "w") as fh:
                    fh.write("not Vallado's file\n")
            directory, where, why = P.locate(ROOT, d)
        self.assertIsNone(directory)
        self.assertIn("differ from the corpus's manifest, not used", why)


def located():
    return P.locate(ROOT)[0] is not None


def sgp4_present():
    try:
        import sgp4.api  # noqa: F401
        return True
    except ImportError:
        return False


def run(parser, **kw):
    (r,) = Runner(parser, root=ROOT, fetch_hints=False, **kw).run(case_ids=["sgp4-ver-propagation"])
    return r.status, {i.check: i for i in r.items}


@unittest.skipUnless(sgp4_present() and located(), "needs python-sgp4 and Vallado's files with the corpus's bytes")
class TheCase(unittest.TestCase):
    def sgp4(self, gravity="WGS72", silent=False, shift=0.0):
        from sgp4.api import Satrec
        import sgp4.api as api

        class Sgp4(Reference):
            def propagate(self, raw, fmt, tsince):
                l1, l2 = [l for l in raw.decode().splitlines() if l[:2] in ("1 ", "2 ")]
                s = Satrec.twoline2rv(l1, l2, getattr(api, gravity))
                out = []
                for t in tsince:
                    e, r, v = s.sgp4_tsince(t)
                    if silent:
                        e = 0
                    out.append({"r": [r[0] + shift, r[1], r[2]], "v": list(v), "error": e})
                return out
        return Sgp4()

    def test_the_preset_passes(self):
        from gpconf.adapters.sgp4_adapter import Parser
        status, items = run(Parser())
        self.assertEqual(status, "pass-tolerance", {k: v.detail for k, v in items.items()})
        self.assertIn("largest differences", items["sgp4-ver-positions"].detail)

    def test_wgs84_constants_fail_the_positions(self):
        status, items = run(self.sgp4("WGS84"))
        self.assertEqual(items["sgp4-ver-positions"].status, "fail")

    def test_a_shift_past_the_bar_fails_and_one_inside_passes(self):
        self.assertEqual(run(self.sgp4(shift=5e-7))[1]["sgp4-ver-positions"].status, "fail")
        self.assertEqual(run(self.sgp4(shift=5e-8))[1]["sgp4-ver-positions"].status, "pass-tolerance")

    def test_a_silent_propagation_fails_the_codes(self):
        status, items = run(self.sgp4(silent=True))
        self.assertEqual(items["sgp4-ver-error-codes"].status, "fail")
        self.assertIn("a silent propagation", items["sgp4-ver-error-codes"].detail)

    def test_files_given_by_directory(self):
        d = P.locate(ROOT)[0]
        self.assertEqual(run(self.sgp4(), sgp4_ver=d)[0], "pass-tolerance")
        with tempfile.TemporaryDirectory() as e:
            status, items = run(self.sgp4(), sgp4_ver=e)
        self.assertEqual(items["sgp4-ver-positions"].status, "not-exercised")
        self.assertIn("check the directory given with --sgp4-ver", items["sgp4-ver-positions"].detail)   # never falls back


    def test_numpy_arrays_and_a_generator_of_steps(self):
        # the review of D-401: python-sgp4's own sgp4_array answers with numpy rows
        import numpy as np
        from sgp4.api import Satrec, WGS72

        class Arrays(Reference):
            def propagate(self, raw, fmt, tsince):
                l1, l2 = [l for l in raw.decode().splitlines() if l[:2] in ("1 ", "2 ")]
                s = Satrec.twoline2rv(l1, l2, WGS72)
                e, r, v = s.sgp4_array(np.zeros(len(tsince)) + s.jdsatepoch, np.array(tsince) / 1440.0 + s.jdsatepochF)
                return ({"r": r[i], "v": v[i], "error": int(e[i])} for i in range(len(tsince)))
        status, items = run(Arrays())
        self.assertEqual(items["sgp4-ver-positions"].status, "pass-tolerance", items["sgp4-ver-positions"].detail)

    def test_no_pass_with_nothing_compared(self):
        class NoneCodes(Reference):
            def propagate(self, raw, fmt, tsince):
                return [{"r": [0.0, 0.0, 0.0], "v": [0.0, 0.0, 0.0], "error": None} for t in tsince]
        status, items = run(NoneCodes())
        self.assertEqual(items["sgp4-ver-positions"].status, "fail")
        self.assertIn("no step was compared", items["sgp4-ver-positions"].detail)

    def test_a_valid_set_refused_fails(self):
        class Refuses(Reference):
            def propagate(self, raw, fmt, tsince):
                raise ValueError("cannot read this set")
        status, items = run(Refuses())
        self.assertEqual(items["sgp4-ver-positions"].status, "fail")
        self.assertIn("33 valid element sets refused", items["sgp4-ver-positions"].detail)


class WithoutTheHook(unittest.TestCase):
    def test_a_parser_without_it_skips(self):
        status, items = run(Reference())
        self.assertEqual({k: v.status for k, v in items.items()}, {"sgp4-ver-positions": "skip", "sgp4-ver-error-codes": "skip"})

    def test_a_vectors_command_without_the_op_is_unsupported_however_it_says_so(self):
        # the shipped harnesses answer an op they lack in their own words: astroz's "unknown op propagate" with exit 0,
        # libsgp4's and Vallado's "the library has no propagate" with exit 1 (measured 2026-11-08)
        for answer, code in (("{'error': 'unknown op propagate'}", 0), ("{'error': 'the library has no propagate'}", 1),
                             ("{'unsupported': 'no propagator'}", 0)):
            with self.subTest(answer=answer):
                cmd = [sys.executable, "-c", f"import json,sys; json.load(sys.stdin); print(json.dumps({answer})); sys.exit({code})"]
                with self.assertRaises(Exception) as e:
                    CommandParser(None, vectors_cmd=cmd).propagate(b"1 x\r\n2 x\r\n", "tle", [0.0])
                self.assertEqual(type(e.exception).__name__, "Unsupported")
                self.assertIn("did not answer the probe with no times with an empty list", str(e.exception))

    def test_a_command_with_the_op_answers_the_probe_and_is_graded(self):
        code = ("import json,sys; q=json.load(sys.stdin)['input']; "
                "print(json.dumps({'result': [{'r': [1.0, 2.0, 3.0], 'v': [0.1, 0.2, 0.3], 'error': 0} for t in q['tsince']]}))")
        p = CommandParser(None, vectors_cmd=[sys.executable, "-c", code])
        self.assertEqual(p.propagate(b"1 x\r\n2 x\r\n", "tle", [0.0, 1.0]), [{"r": [1.0, 2.0, 3.0], "v": [0.1, 0.2, 0.3], "error": 0}] * 2)


if __name__ == "__main__":
    unittest.main()
