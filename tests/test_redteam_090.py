# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""D-459: the 0.9.0 red-team's grader findings, each with the wrong-on-purpose adapter that showed it (a fresh reviewer
that did not write the 0.9.0 work, 2026-11-10): a propagate answer with one step for many times, an agreement over no
step, the error-codes item's words when sets were refused, and `gpconf fuzz --strict` over nothing fuzzed."""
import contextlib
import io
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf.__main__ import main as gpconf_main  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import Runner, Unsupported  # noqa: E402
from gpconf import propagation as P  # noqa: E402


def items(parser, case):
    (r,) = Runner(parser, root=ROOT, fetch_hints=False).run(case_ids=[case])
    return r.status, {i.check: i for i in r.items}


class OneStep(Reference):
    """One error code for however many times were asked."""
    def propagate(self, raw, fmt, tsince):
        return [{"r": None, "v": None, "error": 6}]


class ErrorsEverywhere(Reference):
    """An error code at every step, so nothing is ever propagated."""
    def propagate(self, raw, fmt, tsince):
        return [{"r": None, "v": None, "error": 6} for _ in tsince]


class RefuseAll(Reference):
    def propagate(self, raw, fmt, tsince):
        if not tsince:
            return []
        raise ValueError("refused")


class ReadsNothing:
    def parse(self, raw, fmt):
        raise Unsupported(fmt)


class RefusesEverything:
    def parse(self, raw, fmt):
        raise ValueError("refused")


class TheFindings(unittest.TestCase):
    def test_one_step_for_many_times_is_no_code_at_every_step(self):
        status, it = items(OneStep(), "ephemeris-type-4-refused")
        self.assertEqual(it["type4-not-propagated"].status, "fail")
        self.assertIn("steps answered for", it["type4-not-propagated"].detail)

    def test_an_agreement_over_no_step_is_no_agreement(self):
        status, it = items(ErrorsEverywhere(), "propagation-tle-omm-twins")
        self.assertEqual(it["twins-tle-omm-agree"].status, "fail")
        self.assertIn("no step was propagated from both renderings", it["twins-tle-omm-agree"].detail)

    @unittest.skipUnless(P.locate(ROOT)[0], "needs Vallado's files with the corpus's bytes (private, D-388)")
    def test_refused_sets_do_not_read_as_a_pass_in_the_codes_item(self):
        status, it = items(RefuseAll(), "sgp4-ver-propagation")
        self.assertEqual(it["sgp4-ver-error-codes"].status, "fail")
        self.assertNotIn("no false decay", it["sgp4-ver-error-codes"].detail)
        self.assertIn("not graded for every set", it["sgp4-ver-error-codes"].detail)

    def fuzz(self, cls, *extra):
        name = "gpconf_rt090_" + cls.__name__.lower()
        mod = type(sys)(name)
        setattr(mod, "Parser", cls)
        sys.modules[name] = mod
        self.addCleanup(sys.modules.pop, name, None)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gpconf_main(["fuzz", "--count", "10", "--seed", "1", "--root", ROOT, "--adapter", name] + list(extra))
        return code, out.getvalue()

    def test_fuzz_strict_with_no_format_read_exits_2(self):
        code, out = self.fuzz(ReadsNothing, "--strict")
        self.assertEqual(code, 2)
        self.assertIn("the adapter reads no format", out)
        self.assertEqual(self.fuzz(ReadsNothing)[0], 0)   # the default stays 0 (D-415)

    def test_a_reader_refusing_every_input_is_said_not_failed(self):
        """the review of D-459: a refusal is a fine answer, so a strict reader refusing every input on a small count
        must not turn its CI red by chance; the run says so"""
        code, out = self.fuzz(RefusesEverything, "--strict")
        self.assertEqual(code, 0)
        self.assertIn("every input was refused", out)

    def test_the_json_tally_counts_refusals_apart(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.json")
            self.fuzz(RefusesEverything, "--json", p)
            with open(p) as f:
                tally = json.load(f)["parse"]["tally"]
        self.assertEqual(tally.get("refused"), 10)
        self.assertNotIn("ok", tally)

    def test_propagate_only_adapters_are_fuzzed_not_nothing(self):
        class CleanProp(ReadsNothing):
            def propagate(self, raw, fmt, tsince):
                return [{"r": None, "v": None, "error": 1} for _ in tsince]

        class NanProp(ReadsNothing):
            def propagate(self, raw, fmt, tsince):
                return [{"r": [float("nan")] * 3, "v": [float("nan")] * 3, "error": 0} for _ in tsince]
        self.assertEqual(self.fuzz(CleanProp, "--propagate", "--strict")[0], 0)
        self.assertEqual(self.fuzz(NanProp, "--propagate", "--strict")[0], 1)   # its findings are not hidden by exit 2

    def test_a_refusal_at_parse_passes_whatever_the_hook_answers(self):
        """D-464 (the owner's ruling, 2026-11-11): parse refusing the type-4 set passes, its twin read; positions fail only
        for a set parse accepted."""
        def is_type4(raw, fmt):
            t = raw.decode("utf-8", "replace")
            if fmt in ("tle", "2le"):
                l1 = [x for x in t.splitlines() if x.startswith("1 ")]
                return bool(l1) and len(l1[0]) > 62 and l1[0][62] == "4"
            import re
            return bool(re.search(r'EPHEMERIS_TYPE"?\s*[:=]\s*"?4\b|<EPHEMERIS_TYPE>\s*4\s*<|SGP4-XP', t)) or (
                fmt == "csv" and ",4," in t.splitlines()[-1] if t.strip() else False)

        class ParseRefusesType4(Reference):
            def parse(self, raw, fmt):
                if is_type4(raw, fmt):
                    raise ValueError("SGP4-XP element set (EPHEMERIS_TYPE 4): not read")
                return Reference.parse(self, raw, fmt)

            def propagate(self, raw, fmt, tsince):   # positions for every set, type 4 too
                return [{"r": [7000.0, 1.0, 1.0], "v": [1.0, 7.0, 1.0], "error": 0} for _ in tsince]

        class AcceptsAndPropagates(ParseRefusesType4):
            def parse(self, raw, fmt):
                return Reference.parse(self, raw, fmt)

        def hook(answer4):
            class H(ParseRefusesType4):
                def propagate(self, raw, fmt, tsince):
                    if is_type4(raw, fmt):
                        return answer4(tsince)
                    return [{"r": [7000.0, 1.0, 1.0], "v": [1.0, 7.0, 1.0], "error": 0} for _ in tsince]
            return H()
        # what D-464 moved: a parse refusal passes whatever the hook answers for that set, an empty or short answer too
        for name, answer4 in (("empty", lambda t: []), ("one step", lambda t: [{"r": None, "v": None, "error": 6}]),
                              ("positions", lambda t: [{"r": [7000.0, 1.0, 1.0], "v": [1.0, 7.0, 1.0], "error": 0} for _ in t])):
            with self.subTest(hook=name):
                status, it = items(hook(answer4), "ephemeris-type-4-refused")
                self.assertIn(it["type4-not-propagated"].status, ("pass", "pass-tolerance"), it["type4-not-propagated"].detail)
                self.assertIn("refused when read (parse)", it["type4-not-propagated"].detail)
        status, it = items(AcceptsAndPropagates(), "ephemeris-type-4-refused")
        self.assertEqual(it["type4-not-propagated"].status, "fail")

        class RefusesInTleOnly(ParseRefusesType4):   # accepted elsewhere, with positions: those formats fail
            def parse(self, raw, fmt):
                if fmt in ("tle", "2le") and is_type4(raw, fmt):
                    raise ValueError("SGP4-XP")
                return Reference.parse(self, raw, fmt)
        status, it = items(RefusesInTleOnly(), "ephemeris-type-4-refused")
        self.assertEqual(it["type4-not-propagated"].status, "fail")

        class RefusesEverything(Reference):   # no twin read: no evidence, and an empty hook answer fails
            def parse(self, raw, fmt):
                raise ValueError("no")

            def propagate(self, raw, fmt, tsince):
                return []
        status, it = items(RefusesEverything(), "ephemeris-type-4-refused")
        self.assertEqual(it["type4-not-propagated"].status, "fail")

    def test_too_many_steps_fail_too(self):
        class SevenForSix(Reference):
            def propagate(self, raw, fmt, tsince):
                return [{"r": None, "v": None, "error": 6} for _ in list(tsince) + [0]]
        status, it = items(SevenForSix(), "ephemeris-type-4-refused")
        self.assertEqual(it["type4-not-propagated"].status, "fail")
        self.assertIn("steps answered for", it["type4-not-propagated"].detail)


if __name__ == "__main__":
    unittest.main()
