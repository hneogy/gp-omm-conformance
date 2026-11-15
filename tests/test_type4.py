# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Ephemeris type 4 (D-409): an SGP4-XP element set must not come back as SGP4 positions; its type-0 twin must.

Run: python -m unittest tests.test_type4"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import CommandParser, Runner, Unsupported  # noqa: E402

CASE = "ephemeris-type-4-refused"
BASE = os.path.join(ROOT, "derived", "ephemeris-type-4")
with open(os.path.join(ROOT, "vectors", "propagation-twins.json"), encoding="utf-8") as _f:
    (SET,) = [s for s in json.load(_f)["sets"] if s["norad_cat_id"] == 20453]
TYPE4 = ["type4.tle", "type4.csv", "type4.json", "type4.xml", "type4.kvn", "type4-sgp4-xp.kvn"]


def run(parser):
    (r,) = Runner(parser, root=ROOT, fetch_hints=False).run(case_ids=[CASE])
    return r.status, {i.check: i for i in r.items}


def statuses(parser):
    return {k: v.status for k, v in run(parser)[1].items()}


class Exact(Reference):
    """Reads the set with the corpus's reference reader and answers the twins' reference steps: an exact propagator
    for 20453 (the stand-ins below change one thing each). TYPE4 is what it does with a type-4 set."""
    TYPE4 = "propagate"
    UNSUPPORTED = ()

    def etype(self, raw, fmt):
        (rec,) = [r for r in Reference.parse(self, raw, fmt) if "norad_cat_id" in r]
        return rec["ephemeris_type"]

    def propagate(self, raw, fmt, tsince):
        if fmt in self.UNSUPPORTED:
            raise Unsupported(fmt)
        steps = {s["t"]: s for s in SET["steps"]}
        if self.etype(raw, fmt) == 4:
            if self.TYPE4 == "raise":
                raise ValueError("ephemeris type 4 (SGP4-XP): not an SGP4 element set")
            if self.TYPE4 == "codes":
                return [{"r": None, "v": None, "error": 2} for _ in tsince]
            if self.TYPE4 == "one-position":
                return [{"r": None, "v": None, "error": 2}] * (len(tsince) - 1) + [dict(steps[tsince[-1]])]
            if self.TYPE4 == "unsupported":
                raise Unsupported("SGP4-XP")
            if self.TYPE4 == "stamped":
                return [{"r": steps[t]["r"], "v": steps[t]["v"], "error": 6} for t in tsince]
            if self.TYPE4 == "zeros":
                return [{"r": [0.0, 0.0, 0.0], "v": [0.0, 0.0, 0.0], "error": 2} for _ in tsince]
            if self.TYPE4 == "empty":
                return []
        elif self.TYPE4 == "twin-unsupported":
            raise Unsupported(fmt)
        return [{"r": steps[t]["r"], "v": steps[t]["v"], "error": steps[t]["error"]} for t in tsince]


class TheData(unittest.TestCase):
    def test_each_file_reads_as_the_twin_with_its_type(self):
        import gpref
        want = gpref.parse_tle_lines(None, SET["line1"], SET["line2"])
        for name in sorted(os.listdir(BASE)):
            if name.endswith(".provenance.json"):
                continue
            with self.subTest(name=name):
                _, (r,), _ = gpref.read_file(os.path.join(BASE, name))
                self.assertEqual(r["ephemeris_type"], 4 if name.startswith("type4") else 0)
                for k in ("norad_cat_id", "epoch", "mean_motion", "eccentricity", "inclination", "ra_of_asc_node",
                          "arg_of_pericenter", "mean_anomaly", "bstar"):
                    self.assertEqual(str(r[k]), str(want[k]), k)

    def test_the_type_4_tle_differs_from_its_twin_in_column_63_and_the_checksum_only(self):
        with open(os.path.join(BASE, "type4.tle"), encoding="ascii", newline="") as f:
            l1 = f.read().split("\r\n")[1]
        self.assertEqual([i for i, (a, b) in enumerate(zip(l1, SET["line1"])) if a != b], [62, 68])
        self.assertEqual(l1[62], "4")

    def test_the_variant_says_sgp4_xp(self):
        with open(os.path.join(BASE, "type4-sgp4-xp.kvn"), encoding="utf-8") as f:
            self.assertIn("MEAN_ELEMENT_THEORY = SGP4-XP", f.read())


class TheCase(unittest.TestCase):
    def test_a_parser_without_the_hook_skips(self):
        self.assertEqual(statuses(Reference()), {"type4-not-propagated": "skip", "type4-twins-propagate": "skip"})

    def test_a_hook_that_propagates_type_4_as_sgp4_fails(self):
        status, items = run(Exact())
        self.assertEqual(status, "fail")
        self.assertEqual(items["type4-not-propagated"].status, "fail")
        for name in TYPE4:
            self.assertIn(f"{name} propagated as SGP4", items["type4-not-propagated"].detail)
        self.assertEqual(items["type4-twins-propagate"].status, "pass")

    def test_a_hook_that_refuses_type_4_passes(self):
        class Refuses(Exact):
            TYPE4 = "raise"
        status, items = run(Refuses())
        self.assertEqual(status, "pass")
        self.assertIn("6 type-4 files not propagated", items["type4-not-propagated"].detail)
        self.assertIn("not an SGP4 element set", items["type4-not-propagated"].detail)

    def test_a_hook_that_answers_a_code_at_every_step_passes_as_vallados_cpp_does(self):
        class Codes(Exact):
            TYPE4 = "codes"
        status, items = run(Codes())
        self.assertEqual(status, "pass")
        self.assertIn("an SGP4 error code at every step", items["type4-not-propagated"].detail)

    def test_one_position_among_the_codes_fails(self):
        class OnePosition(Exact):
            TYPE4 = "one-position"
        self.assertEqual(statuses(OnePosition())["type4-not-propagated"], "fail")

    def test_a_hook_that_refuses_everything_fails_on_the_twins(self):
        class RefusesAll(Exact):
            def propagate(self, raw, fmt, tsince):
                raise ValueError("no")
        self.assertEqual(statuses(RefusesAll()), {"type4-not-propagated": "pass", "type4-twins-propagate": "fail"})

    def test_a_parse_that_refuses_type_4_passes_though_the_hook_propagates(self):
        class ParseRefuses(Exact):
            def parse(self, raw, fmt):
                out = Reference.parse(self, raw, fmt)
                return [{"_refused": "ephemeris type 4 is SGP4-XP", "_field": str(r["norad_cat_id"])}
                        if r.get("ephemeris_type") == 4 else r for r in out] + [{"_adapter": {"refusals": True}}]
        status, items = run(ParseRefuses())
        self.assertEqual(status, "pass")
        self.assertIn("refused when read (parse)", items["type4-not-propagated"].detail)

    def test_unsupported_for_the_type_4_set_alone_is_a_refusal(self):
        """The review of D-409: declining SGP4-XP as unsupported is a refusal in words; the twin is graded."""
        class UnsupportedForType4(Exact):
            TYPE4 = "unsupported"
        status, items = run(UnsupportedForType4())
        self.assertEqual(status, "pass")
        self.assertIn("declined as unsupported (SGP4-XP)", items["type4-not-propagated"].detail)

    def test_unsupported_for_the_twin_alone_fails_the_twins(self):
        class TwinUnsupported(Exact):
            TYPE4 = "twin-unsupported"
        status, items = run(TwinUnsupported())
        self.assertEqual(items["type4-twins-propagate"].status, "fail")
        self.assertIn("Unsupported is for a format's sets all or none (D-205, D-280)", items["type4-twins-propagate"].detail)

    def test_codes_stamped_on_sgp4_positions_fail(self):
        class Stamped(Exact):
            TYPE4 = "stamped"
        status, items = run(Stamped())
        self.assertEqual(items["type4-not-propagated"].status, "fail")
        self.assertIn("error codes beside SGP4 positions", items["type4-not-propagated"].detail)

    def test_codes_with_untouched_zero_arrays_pass(self):
        class Zeros(Exact):
            TYPE4 = "zeros"
        self.assertEqual(run(Zeros())[0], "pass")

    def test_an_empty_answer_is_no_refusal(self):
        class Empty(Exact):
            TYPE4 = "empty"
        status, items = run(Empty())
        self.assertEqual(items["type4-not-propagated"].status, "fail")
        self.assertIn("the answer is no list of steps", items["type4-not-propagated"].detail)

    def test_a_parse_that_refuses_everything_is_no_evidence(self):
        """The review of D-409: a parse refusal counts only while the twin in the same format is read."""
        class ParseRefusesAll(Exact):
            def parse(self, raw, fmt):
                raise ValueError("no")
        self.assertEqual(statuses(ParseRefusesAll())["type4-not-propagated"], "fail")

    def test_a_format_unsupported_for_both_files_is_skipped_and_said(self):
        class TleAndCsvOnly(Exact):
            TYPE4 = "raise"
            UNSUPPORTED = ("json", "xml", "kvn")
        status, items = run(TleAndCsvOnly())
        self.assertEqual(status, "pass")
        self.assertIn("2 type-4 files not propagated", items["type4-not-propagated"].detail)
        self.assertIn("unsupported for both files: type4.json, type4.xml, type4.kvn, type4-sgp4-xp.kvn",
                      items["type4-twins-propagate"].detail)

    def test_unsupported_for_every_format_skips(self):
        class None_(Exact):
            UNSUPPORTED = ("tle", "csv", "json", "xml", "kvn")
        self.assertEqual(statuses(None_()), {"type4-not-propagated": "skip", "type4-twins-propagate": "skip"})

    def test_a_claim_of_sgp4_xp_is_not_graded_and_the_twins_are(self):
        class Claims(Exact):
            propagates_sgp4_xp = True
        status, items = run(Claims())
        self.assertEqual(items["type4-not-propagated"].status, "skip")
        self.assertIn("claims SGP4-XP", items["type4-not-propagated"].detail)
        self.assertEqual(items["type4-twins-propagate"].status, "pass")

    def test_only_true_is_a_claim(self):
        class Says(Exact):
            propagates_sgp4_xp = "yes"
        self.assertEqual(statuses(Says())["type4-not-propagated"], "fail")

    def test_a_twin_off_the_reference_fails(self):
        class Off(Exact):
            TYPE4 = "raise"

            def propagate(self, raw, fmt, tsince):
                out = Exact.propagate(self, raw, fmt, tsince)
                return [dict(s, r=[s["r"][0] + 1e-6] + s["r"][1:]) for s in out]
        self.assertEqual(statuses(Off()), {"type4-not-propagated": "pass", "type4-twins-propagate": "fail"})


class ByCommand(unittest.TestCase):
    CODE = ("import json,sys; sys.path.insert(0, {root!r}); from gpconf.adapters.reference import Parser; "
            "q=json.load(sys.stdin)['input']; "
            "s={steps!r}; "
            "ts=q['tsince']; "
            "recs=[r for r in Parser().parse(q['raw'].encode(), q['fmt']) if 'norad_cat_id' in r] if ts else []; "
            "print(json.dumps({{'error': 'ephemeris type 4: SGP4-XP'}} if recs and recs[0]['ephemeris_type'] == 4 else "
            "{{'result': [{{'r': s[str(t)]['r'], 'v': s[str(t)]['v'], 'error': 0}} for t in ts]}}))")

    REFUSES_FIRST = ("import json,sys; sys.path.insert(0, {root!r}); from gpconf.adapters.reference import Parser; "
                     "q=json.load(sys.stdin)['input']; s={steps!r}; "
                     "recs=[r for r in Parser().parse(q['raw'].encode(), q['fmt']) if 'norad_cat_id' in r]; "
                     "print(json.dumps({{'error': 'ephemeris type 4: SGP4-XP'}} if recs[0]['ephemeris_type'] == 4 else "
                     "{{'result': [{{'r': s[str(t)]['r'], 'v': s[str(t)]['v'], 'error': 0}} for t in q['tsince']]}}))")

    def test_a_command_that_refuses_on_the_type_before_reading_the_times_passes_run_alone(self):
        """The review of D-409: the op is probed with the first set sent, so the case sends each twin first; a probe
        with the type-4 set would have read this command's refusal as having no op, and the case would skip."""
        steps = {str(s["t"]): {"r": s["r"], "v": s["v"]} for s in SET["steps"]}
        code = self.REFUSES_FIRST.format(root=ROOT, steps=steps)
        p = CommandParser([sys.executable, "-c", "print('[]')"], vectors_cmd=[sys.executable, "-c", code])
        self.assertEqual(statuses(p), {"type4-not-propagated": "pass", "type4-twins-propagate": "pass"})

    def test_a_command_answering_an_error_for_type_4_passes(self):
        steps = {str(s["t"]): {"r": s["r"], "v": s["v"]} for s in SET["steps"]}
        code = self.CODE.format(root=ROOT, steps=steps)
        p = CommandParser([sys.executable, "-c", "print('[]')"], vectors_cmd=[sys.executable, "-c", code])
        status, items = run(p)
        self.assertEqual({k: v.status for k, v in items.items()}, {"type4-not-propagated": "pass", "type4-twins-propagate": "pass"})


@unittest.skipUnless(__import__("importlib").util.find_spec("sgp4") is not None, "needs python-sgp4")
class PythonSgp4(unittest.TestCase):
    def test_python_sgp4_2_27_propagates_type_4_as_sgp4_from_tle_and_csv(self):
        """The owner's report, https://github.com/brandon-rhodes/python-sgp4/issues/178 (measured 2026-11-09)."""
        from gpconf.adapters.sgp4_adapter import Parser
        status, items = run(Parser())
        self.assertEqual(items["type4-not-propagated"].status, "fail")
        detail = items["type4-not-propagated"].detail
        self.assertIn("type4.tle propagated as SGP4", detail)
        self.assertIn("type4.csv propagated as SGP4", detail)
        self.assertIn(items["type4-twins-propagate"].status, ("pass", "pass-tolerance"))


if __name__ == "__main__":
    unittest.main()
