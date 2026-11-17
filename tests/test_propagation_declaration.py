# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The propagation tier's declaration of constants and budget (D-413; lane C's design section 6): what an adapter
declares is reported beside the propagation items and never trusted; a propagate call past the command's budget is a
crash, never a refusal.

Run: python -m unittest tests.test_propagation_declaration"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import CommandParser, Runner  # noqa: E402

with open(os.path.join(ROOT, "vectors", "propagation-twins.json"), encoding="utf-8") as _f:
    VEC = json.load(_f)
BY_LINE1 = {s["line1"]: {x["t"]: x for x in s["steps"]} for s in VEC["sets"]}


def run(parser, case="propagation-tle-omm-twins"):
    (r,) = Runner(parser, root=ROOT, fetch_hints=False).run(case_ids=[case])
    return r


class Exact(Reference):
    """Answers the twins' reference steps for a TLE set, and declares DECLARED (None: no declaration)."""
    DECLARED = None

    def parse(self, raw, fmt):
        out = Reference.parse(self, raw, fmt)   # the declaration in the same _adapter entry as the refusals one (ADAPTERS.md)
        if self.DECLARED is None:
            return out
        return [dict(r, _adapter=dict(r["_adapter"], propagation=self.DECLARED)) if "_adapter" in r else r for r in out] + \
            ([] if any("_adapter" in r for r in out) else [{"_adapter": {"propagation": self.DECLARED}}])

    def propagate(self, raw, fmt, tsince):
        if fmt != "tle":
            from gpconf.runner import Unsupported
            raise Unsupported(fmt)
        l1 = [l for l in raw.decode("ascii").split("\r\n") if l.startswith("1 ")][0]
        steps = BY_LINE1[l1]
        return [{"r": steps[t]["r"], "v": steps[t]["v"], "error": steps[t]["error"]} for t in tsince]


def declared(result):
    return [i for i in result.items if i.check == "propagation-constants-declared"]


class TheDeclaration(unittest.TestCase):
    def test_no_declaration_no_item(self):
        self.assertEqual(declared(run(Exact())), [])

    def test_the_references_constants_are_said_to_be_the_references(self):
        class Wgs72(Exact):
            DECLARED = {"gravity": "wgs72", "opsmode": "i"}
        (item,) = declared(run(Wgs72()))
        self.assertEqual(item.status, "info")
        self.assertIn("declares gravity wgs72, opsmode i: the reference's", item.detail)

    def test_another_declaration_is_reported_and_moves_nothing(self):
        class Wgs84(Exact):
            DECLARED = {"gravity": "wgs84", "opsmode": "a"}
        r, plain = run(Wgs84()), run(Exact())
        (item,) = declared(r)
        self.assertIn("declares gravity wgs84, opsmode a: not the reference's, WGS-72 and opsmode 'i'", item.detail)
        self.assertIn("reported, never trusted", item.detail)
        self.assertEqual(r.status, plain.status)
        self.assertEqual([(i.check, i.status) for i in r.items if i.check != "propagation-constants-declared"],
                         [(i.check, i.status) for i in plain.items])

    def test_a_declaration_that_is_no_object_is_said(self):
        class Odd(Exact):
            DECLARED = "wgs72"
        (item,) = declared(run(Odd()))
        self.assertIn("is no object", item.detail)

    def test_every_propagation_case_carries_it(self):
        class Wgs72(Exact):
            DECLARED = {"gravity": "wgs72", "opsmode": "i"}
        for case in ("propagation-tle-omm-twins", "ephemeris-type-4-refused", "sgp4-ver-propagation"):
            with self.subTest(case=case):
                self.assertEqual(len(declared(run(Wgs72(), case))), 1)

    def test_case_and_a_hyphen_do_not_matter(self):
        class Spelt(Exact):
            DECLARED = {"gravity": "WGS-72", "opsmode": "I"}
        (item,) = declared(run(Spelt()))
        self.assertIn(": the reference's", item.detail)

    def test_a_parser_exit_while_the_declaration_is_read_is_counted_and_grading_goes_on(self):
        """The review of D-413: the exit fails the case it happens in, which keeps its graded items."""
        class ExitsOnTheFirstTwinsSet(Exact):
            def parse(self, raw, fmt):
                if raw.startswith(b"1 25544U 98067A   98324"):
                    raise SystemExit(2)
                return Exact.parse(self, raw, fmt)
        r = run(ExitsOnTheFirstTwinsSet())
        checks = {i.check: i.status for i in r.items}
        self.assertEqual(r.status, "fail")
        self.assertIn("twins-tle-positions", checks)
        self.assertEqual(checks["twins-tle-positions"], "pass")

    def test_a_copy_without_the_twins_file_is_incomplete_not_a_parser_fail(self):
        """The review of D-413: a shipped file missing stops the run (D-148)."""
        import shutil
        import tempfile
        from gpconf.runner import CorpusIncomplete
        with tempfile.TemporaryDirectory() as d:
            for rel in ("manifest.json", "fixtures/ephemeris-type-4-refused", "derived/ephemeris-type-4", "vectors"):
                src, dst = os.path.join(ROOT, rel), os.path.join(d, rel)
                (shutil.copytree if os.path.isdir(src) else shutil.copy)(src, dst)
            with self.assertRaises(CorpusIncomplete):
                Runner(Exact(), root=d, fetch_hints=False).run(case_ids=["ephemeris-type-4-refused"])

    def test_a_parser_without_the_hook_has_no_item(self):
        class NoHook(Reference):
            def parse(self, raw, fmt):
                return Reference.parse(self, raw, fmt) + [{"_adapter": {"propagation": {"gravity": "wgs72", "opsmode": "i"}}}]
        self.assertEqual(declared(run(NoHook())), [])

    @unittest.skipUnless(__import__("importlib").util.find_spec("sgp4") is not None, "needs python-sgp4")
    def test_the_python_sgp4_preset_declares_its_constants(self):
        from gpconf.adapters.sgp4_adapter import Parser
        (item,) = declared(run(Parser()))
        self.assertIn("declares gravity wgs72, opsmode i: the reference's", item.detail)


class TheBudget(unittest.TestCase):
    """The command's budget applies to each propagate call (D-341). D-574 (the owner's ruling 10): no wall-clock race.
    The deterministic test hands each call to a stand-in for subprocess.run that raises the TimeoutExpired a real run
    raises past its budget (CSV calls) or answers at once (TLE calls), and checks every call carried the budget of 1 s.
    The real test makes every call with times outlast the budget five times over; a probe or parse call slowed past it
    is a timeout too, so load can only make it surer. Before, a TLE call had to finish a real Python start inside 1 s,
    and under load it did not (D-566). The shell-string form, the one the command line uses, is held too (D-578, the
    blind reader of D-574)."""
    VECTORS = os.path.join(ROOT, "vectors", "propagation-twins.json")

    def test_a_propagate_call_past_the_budget_is_a_crash_not_a_refusal(self):
        self.check_budget(["parse-cmd"], ["vectors-cmd"])

    def test_the_shell_string_form_carries_the_budget_too(self):
        # gpconf/__main__.py passes --cmd and --vectors-cmd as strings: _run's shell branch (D-578)
        self.check_budget("parse-cmd", "vectors-cmd")

    def check_budget(self, cmd, vectors_cmd):
        import subprocess
        from unittest import mock
        with open(self.VECTORS, encoding="utf-8") as f:
            v = json.load(f)
        by = {st["line1"]: {str(x["t"]): x for x in st["steps"]} for st in v["sets"]}
        budgets = []

        def stand_in(argv, input=None, capture_output=None, timeout=None, **kw):
            budgets.append(timeout)
            out = b"[]"
            if input:
                q = json.loads(input)["input"] if input.strip().startswith(b"{") else None
                if q is not None:
                    ts = q["tsince"]
                    if ts and q["fmt"] == "csv":
                        raise subprocess.TimeoutExpired(argv, timeout)   # what a real run past its budget raises
                    l1 = [l for l in q["raw"].splitlines() if l.startswith("1 ")]
                    res = [{"r": by[l1[0]][str(t)]["r"], "v": by[l1[0]][str(t)]["v"], "error": 0} for t in ts] if l1 or not ts else []
                    out = json.dumps({"result": res}).encode()
            return subprocess.CompletedProcess(argv, 0, out, b"")

        p = CommandParser(cmd, vectors_cmd=vectors_cmd, timeout=1)
        with mock.patch("gpconf.runner.subprocess.run", side_effect=stand_in):
            items = {i.check: i for i in run(p).items}
        self.assertEqual(items["twins-tle-positions"].status, "pass", items["twins-tle-positions"].detail)
        self.assertEqual(items["twins-omm-positions"].status, "fail")
        self.assertIn("a crash or a timeout is no refusal and no rejection (D-341)", items["twins-omm-positions"].detail)
        self.assertIn("did not finish within 1 seconds", items["twins-omm-positions"].detail)
        self.assertTrue(budgets and set(budgets) == {1}, budgets)   # the budget, unchanged, on every call

    def test_a_real_command_past_the_budget_is_a_crash(self):
        """Every call with times sleeps 5 s against the 1 s budget, so each is a crash, never a refusal (D-341)."""
        code = "import json,sys,time; q=json.load(sys.stdin)['input']; time.sleep(5) if q['tsince'] else None; print(json.dumps({'result': []}))"
        p = CommandParser([sys.executable, "-c", "print('[]')"], vectors_cmd=[sys.executable, "-c", code], timeout=1)
        items = {i.check: i for i in run(p).items}
        for c in ("twins-tle-positions", "twins-omm-positions"):
            self.assertEqual(items[c].status, "fail", items[c].detail)
            self.assertIn("a crash or a timeout is no refusal and no rejection (D-341)", items[c].detail)


if __name__ == "__main__":
    unittest.main()
