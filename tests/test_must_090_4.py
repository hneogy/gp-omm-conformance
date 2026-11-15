# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Tests that pin survivors of the 0.9.0 mutation run the owner ruled must be tested before the release, the fourth
share: the fuzz judge's refusal count, minimise, a propagate answer's steps and the fuzz command's exit and words
(gpconf/fuzz.py); the adapter declaration's truth and a dict's text (gpconf/plain.py); and in gpconf/runner.py the
corrupt-input case's surplus check, counts, causes, cut-site evidence and values-only file, the Vallado propagation
case's words, the twins' agreement, the type-4 case, --tag and the write command's exit 3. Each test names the mutants
it kills; each passes on the code and fails under them.

Run: python -m unittest tests.test_must_090_4"""
import contextlib
import io
import json
import math
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import fuzz as F  # noqa: E402
from gpconf import plain  # noqa: E402
from gpconf import propagation as P  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import CaseResult, CommandParser, Runner, Unsupported  # noqa: E402
from gpconf.words import qty  # noqa: E402
import tests.test_corrupt_input as CI  # noqa: E402  (a module, so that its TestCases are not collected here again)
from tests.test_propagation import located, run as vallado_run, sgp4_present  # noqa: E402
from tests.test_triage_090_fuzz import crashes_on  # noqa: E402
from tests.test_twins import run as twins_run  # noqa: E402
from tests.test_type4 import SET, TYPE4, Exact, run as type4_run  # noqa: E402

FIVE = CI.read(os.path.join(CI.D, "unedited-five.tle"))
C1 = CI.read(os.path.join(CI.D, "c1-checksum-digit.tle"))
CUT_JSON = CI.read(os.path.join(CI.D, "c5-cut-closing-bracket.json"))
XML = "derived/kvn-variants/v07-xml-ndm-reserialised.xml"


def first_record(out):
    return next(r for r in out if "_refused" not in r and "norad_cat_id" in r)


# ---- gpconf/fuzz.py

class TheJudgesRefusalCount(unittest.TestCase):
    def test_refusals_excuse_as_many_missing_records_as_they_name(self):
        """Kills 3247 (one unnamed refusal counted twice), 3248 (refusals naming an id counted as unnamed, unnamed ones
        not at all), 3268 (one named refusal spent twice), 3270 (one unnamed refusal excuses nothing), 3271 (one
        unnamed refusal spent twice). A refusal with a reason excuses one missing record: by its id, or any one when it
        names none (D-290's line, D-311's count)."""
        x = {"norad_cat_id": 5, "epoch": "2000-01-01T00:00:00.000000", "mean_motion": "1"}
        y = dict(x, norad_cat_id=6)
        r = {"id": None, "ok": True, "reason": "r"}
        n5 = {"id": 5, "ok": True, "reason": "a"}
        n7 = {"id": 7, "ok": True, "reason": "b"}
        self.assertEqual(F.judge([], [r], [x, y], [])[0], "dropped")                         # 3247
        self.assertEqual(F.judge([], [r], [x], [])[0], "ok")                                 # 3248, 3270
        self.assertEqual(F.judge([], [r, dict(r)], [x, y], [])[0], "ok")                     # 3271, 3248
        self.assertEqual(F.judge([], [n5, dict(n5, reason="c")], [x, dict(x)], [])[0], "ok")   # 3268
        self.assertEqual(F.judge([], [n7], [x], [])[0], "dropped")                           # 3248


class Minimising(unittest.TestCase):
    def test_a_candidate_is_kept_only_when_it_keeps_the_category(self):
        """Kills 3298 (any non-empty candidate kept without asking the parser: the saved input ends at b'b', which
        does not crash it)."""
        parser = crashes_on(b"X")
        small = F.minimise(parser, b"aXa\nbbb", "tle", "crash")
        self.assertEqual(small, b"X")
        self.assertEqual(F.classify(parser, small, "tle")[0], "crash")


class TheStepsOfAPropagateAnswer(unittest.TestCase):
    def test_a_wrong_number_of_steps_is_unreadable(self):
        """Kills 3333 (a list of the wrong length passes the shape check: one step for seven times reads 'ok')."""
        self.assertEqual(F._steps_category([{"r": None, "v": None, "error": 6}])[0], "unreadable")

    def test_a_step_without_a_code_holding_nan_is_silent_nan(self):
        """Kills 3339 (a step with no 'error' key taken as an error, so its NaN is not reported). A step with no code
        is a step that propagated."""
        ans = [{"r": [math.nan] * 3, "v": [math.nan] * 3} for _ in F.TIMES]
        self.assertEqual(F._steps_category(ans)[0], "silent-nan")

    def test_a_finite_position_beside_a_nan_velocity_is_silent_nan(self):
        """Kills 3342 (a code-0 step needs only one of position and velocity finite)."""
        ans = [{"r": [7000.0, 0.0, 0.0], "v": [math.nan] * 3, "error": 0} for _ in F.TIMES]
        self.assertEqual(F._steps_category(ans)[0], "silent-nan")


class TheFuzzCommand(unittest.TestCase):
    def fuzz(self, parser, count, propagate=False, strict=False, json_path=None, seed=7):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                code = F.main_fuzz(parser, ROOT, seed, count, None, propagate, json_path=json_path, strict=strict)
            except SystemExit as e:   # an unguarded parser's exit ends the run: said as a failure, not as an error
                self.fail(f"the parser's SystemExit({e.code}) left main_fuzz: the adapter was not guarded (D-337)")
        return code, out.getvalue()

    def test_an_adapter_that_exits_is_guarded_and_counted_a_crash(self):
        """Kills 3351 (the adapter the command line hands over, unguarded, is left so: its exit ends gpconf instead of
        being a counted crash)."""
        class Exits(Reference):
            def parse(self, raw, fmt):
                raise SystemExit(3)
        code, out = self.fuzz(Exits(), 2, strict=True)
        self.assertEqual(code, 1, out)
        self.assertIn("[crash]", out)

    def test_strict_counts_parse_and_propagate_findings_together(self):
        """Kills 3353 (the findings counted as parse findings minus propagate findings: '-13 findings'). An adapter
        that reads no format and answers NaN with code 0 for every domain set has one finding per set."""
        class PropagatesNan(Reference):
            def parse(self, raw, fmt):
                raise Unsupported(fmt)

            def propagate(self, raw, fmt, tsince):
                return [{"r": [math.nan] * 3, "v": [math.nan] * 3, "error": 0} for _ in tsince]
        code, out = self.fuzz(PropagatesNan(), 5, propagate=True, strict=True)
        self.assertEqual(code, 1, out)
        self.assertIn(f"--strict: exit 1, {qty(len(F._domain_sets(ROOT)), 'finding')}\n", out)

    def test_a_run_that_judged_inputs_does_not_say_none_was_read(self):
        """Kills 3359 (every run with a count says 'no input was read and compared with the reference', D-459's words
        for a run that judged nothing)."""
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "fuzz.json")
            code, out = self.fuzz(Reference(), 20, json_path=p)
            with open(p, encoding="utf-8") as f:
                rep = json.load(f)["parse"]
        self.assertEqual(code, 0)
        judged = sum(v for k, v in rep["tally"].items() if k not in ("refused", "unsupported"))
        self.assertGreater(judged, 0, rep["tally"])
        self.assertNotIn("no input was read", out)


# ---- gpconf/plain.py

class TheAdapterDeclaration(unittest.TestCase):
    def test_refusals_truth_is_read_from_the_refusals_key_only(self):
        """Kills 2597 (the truth taken from the declaration's first text key: a propagation-only declaration, or a
        'version' key before 'refusals': False, reads as refusals True)."""
        a = plain.record({"_adapter": {"propagation": {"gravity": "wgs72", "opsmode": "i"}}}, entry=True)["_adapter"]
        b = plain.record({"_adapter": {"version": "1", "refusals": False}}, entry=True)["_adapter"]
        self.assertNotIn("refusals", a)
        self.assertIs(b["refusals"], False)


class AsText(unittest.TestCase):
    def test_a_dict_is_written_key_then_value(self):
        """Kills 2674 (each key written as its value: {'a': 1} as {1: 1})."""
        for v, want in (({"a": 1}, "{'a': 1}"), ({"k": "v"}, "{'k': 'v'}")):
            out = plain.as_text(v)
            self.assertIs(type(out), plain.Written)
            self.assertEqual(str.__str__(out), want)


# ---- gpconf/runner.py: corrupt-input

class CorruptInputCounts(unittest.TestCase):
    """One run of the corrupt-input case with the reference reader, changed twice: it returns the first record of
    unedited-five.tle twice from that file, and a made-up record (id 99999, which the file does not hold) beside its
    answer to c1-checksum-digit.tle."""

    @classmethod
    def setUpClass(cls):
        cls.dup = int(first_record(Reference().parse(FIVE, "tle"))["norad_cat_id"])

        class Odd(Reference):
            def parse(self, raw, fmt):
                out = list(Reference.parse(self, raw, fmt))
                if raw == FIVE:
                    out.append(dict(first_record(out)))
                elif raw == C1:
                    out.append(dict(first_record(out), norad_cat_id=99999))
                return out
        cls.r = CI.run(Odd())

    def test_a_record_returned_twice_from_an_unedited_file_fails_its_values(self):
        """Kills 1141 (the D-311 surplus check of the unedited file never runs), 1145 (it looks only at records with no
        id), 1147 (a record returned exactly twice is not over). The file's frozen-values item (D-342, compare_values)
        fails the same copy too, in a detail of its own that opens with the records compared; the D-311 item of
        run_corrupt_input is the one whose whole detail is the surplus, so the test asks for that item."""
        fails = [i.detail for i in self.r.items if i.check == "values" and i.status == "fail"
                 and i.file and i.file.endswith("unedited-five.tle")]
        self.assertIn(f"id {self.dup}: returned 2 times where the input holds it once (D-311)", fails)

    def test_a_made_up_record_counts_as_misidentified(self):
        """Kills 1221 (a record the file does not hold lowers misidentified: -1 here)."""
        it = CI.item(self.r, "c1-checksum-digit.tle", "corrupt-tle-checksum-digit")
        self.assertEqual(it.counts["misidentified"], 1)
        self.assertEqual(it.status, "fail")
        self.assertIn("1 record the file does not hold, built from garbage", it.detail)

    def test_a_reasoned_refusal_is_not_counted_without_a_reason(self):
        """Kills 1228 (refused_without_reason is refusals plus reasoned refusals: 2 for the reference's one reasoned
        refusal of c2's short line)."""
        c = CI.item(self.r, "c2-line-2-short.tle", "corrupt-tle-line-short").counts
        self.assertEqual(c["refused"], 1)
        self.assertEqual(c["refused_without_reason"], 0)

    def test_the_values_only_xml_file_with_its_recorded_bytes_is_a_snapshot(self):
        """Kills 1260 (the values-only XML file with its recorded bytes reported 'live', and one with other bytes
        'snapshot')."""
        self.assertEqual(self.r.modes[XML], "snapshot")


class CorruptInputWithoutAComparison(unittest.TestCase):
    """One run of the corrupt-input case with the reference reader, which here raises on unedited-five.tle and never
    returns 25544 or 20453 from a TLE file (records and refusals of them left out)."""

    @classmethod
    def setUpClass(cls):
        class Narrow(Reference):
            def parse(self, raw, fmt):
                if raw == FIVE:
                    raise ValueError("cannot read this file")
                out = Reference.parse(self, raw, fmt)
                if fmt != "tle":
                    return out
                return [r for r in out if r.get("norad_cat_id") not in (25544, 20453) and r.get("_field") not in ("25544", "20453")]
        cls.r = CI.run(Narrow())

    def test_an_unedited_file_the_parser_refuses_leaves_its_input_not_exercised_by_the_parser(self):
        """Kills 1152 (the not-exercised items of an unedited file the parser refused blame the data)."""
        voided = [i for i in self.r.items if i.status == "not-exercised" and "unedited file unedited-five.tle cannot serve" in i.detail]
        self.assertEqual(sorted(i.check for i in voided), ["corrupt-input-neighbours-load", "corrupt-tle-letter-in-number"])
        self.assertEqual({i.cause for i in voided}, {"parser"})

    def test_two_valid_sets_the_parser_never_returns_are_counted_as_two(self):
        """Kills 1256 (two valid sets read as 'does not return the 1 valid set')."""
        it = CI.item(self.r, "c3-letter-in-epoch.tle", "corrupt-input-neighbours-load")
        self.assertEqual(it.status, "not-exercised")
        self.assertIn("the parser returns none of the 2 valid sets around the corrupt one from the unedited file "
                      "unedited-sets.tle either", it.detail)


def quoting(part):
    """The lenient reader of test_corrupt_input's Rules, which returns the cut JSON file's three complete records,
    with a reasoned refusal of that file alone whose _input is raw.decode()[part]."""
    class Quotes(CI.Rules.Lenient):
        def parse(self, raw, fmt):
            out = super().parse(raw, fmt)
            if fmt == "json" and raw == CUT_JSON:
                out = out + [{"_refused": "JSON array not closed", "_input": raw.decode()[part]}]
            return out
    return Quotes()


class TheCutSite(unittest.TestCase):
    def test_a_quote_of_the_files_head_is_no_evidence_of_the_cut(self):
        """Kills 1191 (a quote not in the file's last 200 characters taken as the cut site's evidence: the cut passes),
        1197 (every failing cut detail says a refusal quoting the cut site was set aside, D-400, here where the parser
        refused nothing in the unedited file)."""
        text = CUT_JSON.decode()
        self.assertNotIn(text[:60], text[-200:])   # the premise: the head is no part of the tail
        it = CI.item(CI.run(quoting(slice(0, 60))), "c5-cut-closing-bracket.json", "corrupt-file-cut")
        self.assertEqual(it.status, "fail")
        self.assertIn("silent partial loading", it.detail)
        self.assertNotIn("not counted", it.detail)

    def test_a_quote_inside_the_files_tail_is_evidence_of_the_cut(self):
        """Kills 1191 (a quote of the tail that does not end the file loses its credit)."""
        text = CUT_JSON.decode()
        self.assertTrue(text[-60:-20].strip())   # the premise: a quote of text, within the tail, that does not end the file
        self.assertFalse(text.rstrip().endswith(text[-60:-20].rstrip()))
        it =CI.item(CI.run(quoting(slice(-60, -20))), "c5-cut-closing-bracket.json", "corrupt-file-cut")
        self.assertEqual(it.status, "pass", it.detail)
        self.assertIn("quotes the cut site", it.detail)


class TheValuesOnlyFile(unittest.TestCase):
    def test_a_dodge_of_the_xml_file_names_its_own_skip_item(self):
        """Kills 1263 (the D-280 bookkeeping names the item before the skip, so the run-wide pass looks at an item that
        is no skip and the dodge is not failed)."""
        class NoXml(Reference):
            def parse(self, raw, fmt):
                if fmt == "xml":
                    raise Unsupported("xml")
                return Reference.parse(self, raw, fmt)
        res = CaseResult("corrupt-input", "corrupt input")
        res.add("values", "pass", "derived/corrupt-input/unedited-rows.csv", "an item graded before the XML file")
        Runner(NoXml(), root=ROOT, fetch_hints=False).grade_values_only(None, CI.EXPECTED, res, {})
        self.assertEqual(len(res.fmt_dodged), 1)
        fmt, idx, path = res.fmt_dodged[0]
        it = res.items[idx]
        self.assertEqual((fmt, path), ("xml", XML))
        self.assertEqual((it.check, it.status, it.file), ("format-supported", "skip", XML))


# ---- gpconf/runner.py: the propagation cases

@unittest.skipUnless(sgp4_present() and located(), "needs python-sgp4 and Vallado's files with the corpus's bytes")
class TheValladoCase(unittest.TestCase):
    def test_exact_positions_and_velocities_off_inside_the_bar(self):
        """Kills 1281 (the error-code count starts at 1: one run more said to end in an SGP4 error), 1288 (exact
        positions with velocities off inside the bar graded 'pass', as an exact answer). The hook answers the located
        files' own numbers, read at run time, each velocity component 1e-9 km/s off, and their error codes."""
        refs = P.reference(P.locate(ROOT)[0], ROOT)
        table = {(P.raw_of(r), tuple(r["times"])): r for r in refs}

        class Numbers(Reference):
            def propagate(self, raw, fmt, tsince):
                ref = table[(bytes(raw), tuple(tsince))]
                err, out = ref["error"], []
                for i in range(len(tsince)):
                    if err and i >= err["step_index"]:
                        out.append({"r": None, "v": None, "error": err["code"]})
                    else:
                        row = ref["rows"][i]
                        out.append({"r": list(row[1:4]), "v": [x + 1e-9 for x in row[4:7]], "error": 0})
                return out
        _, items = vallado_run(Numbers())
        self.assertEqual(items["sgp4-ver-positions"].status, "pass-tolerance", items["sgp4-ver-positions"].detail)
        codes = items["sgp4-ver-error-codes"]
        self.assertEqual(codes.status, "pass", codes.detail)
        n = sum(bool(r["error"]) for r in refs)
        self.assertTrue(codes.detail.startswith(f"{qty(n, 'run')} ending in an SGP4 error"), codes.detail)

    def test_a_hook_unsupported_with_a_reason_says_it(self):
        """Kills 1282 (an Unsupported with a reason said as 'no reason given')."""
        class NoSgp4(Reference):
            def propagate(self, raw, fmt, tsince):
                raise Unsupported("no SGP4 here")
        _, items = vallado_run(NoSgp4())
        for check in ("sgp4-ver-positions", "sgp4-ver-error-codes"):
            self.assertEqual(items[check].status, "skip")
            self.assertIn("no SGP4 here", items[check].detail)


class TheTwins(unittest.TestCase):
    def test_a_tle_only_propagator_skips_the_agreement(self):
        """Kills 1336 (a set propagated from one rendering enters the agreement, whose missing CSV answer raises a
        KeyError inside the runner: a failing 'runner' item). The hook answers the twins' reference steps for a TLE and
        Unsupported for every CSV, as a TLE-only library does."""
        sets = {(s["line1"], s["line2"]): s for s in P.twins(ROOT)["sets"]}

        class TleOnly(Reference):
            def propagate(self, raw, fmt, tsince):
                if fmt == "csv":
                    raise Unsupported("csv")
                l1, l2 = bytes(raw).decode("ascii").split("\r\n")[:2]
                steps = {x["t"]: x for x in sets[(l1, l2)]["steps"]}
                return [{"r": steps[t]["r"], "v": steps[t]["v"], "error": steps[t]["error"]} for t in tsince]
        _, items = twins_run(TleOnly())
        self.assertNotIn("runner", items, items.get("runner") and items["runner"].detail)
        self.assertEqual(items["twins-tle-positions"].status, "pass", items["twins-tle-positions"].detail)
        self.assertEqual(items["twins-omm-positions"].status, "skip")
        self.assertEqual(items["twins-tle-omm-agree"].status, "skip")
        self.assertIn("no set was propagated from both renderings", items["twins-tle-omm-agree"].detail)


class TheType4Case(unittest.TestCase):
    def test_twins_with_velocities_off_inside_the_bar_pass_within_tolerance(self):
        """Kills 1405 (type4-twins-propagate 'pass' when the positions are exact and only the velocities differ)."""
        class VelocityOff(Exact):
            TYPE4 = "codes"

            def propagate(self, raw, fmt, tsince):
                out = Exact.propagate(self, raw, fmt, tsince)
                if self.etype(raw, fmt) == 4:
                    return out
                return [dict(a, v=[x + 1e-9 for x in a["v"]]) for a in out]
        _, items = type4_run(VelocityOff())
        self.assertEqual(items["type4-not-propagated"].status, "pass", items["type4-not-propagated"].detail)
        self.assertEqual(items["type4-twins-propagate"].status, "pass-tolerance", items["type4-twins-propagate"].detail)

    def test_steps_without_a_code_are_steps_that_propagated(self):
        """Kills 1376 (a step with no 'error' key read as code 1: positions with no code are 'error codes beside SGP4
        positions', and steps that are empty objects pass as a code at every step)."""
        steps = {s["t"]: s for s in SET["steps"]}

        class NoCodes(Exact):
            EMPTY = False

            def propagate(self, raw, fmt, tsince):
                if self.etype(raw, fmt) == 4:
                    return [{} if self.EMPTY else {"r": steps[t]["r"], "v": steps[t]["v"]} for t in tsince]
                return Exact.propagate(self, raw, fmt, tsince)

        class EmptySteps(NoCodes):
            EMPTY = True
        for parser in (NoCodes(), EmptySteps()):
            with self.subTest(empty=parser.EMPTY):
                it = type4_run(parser)[1]["type4-not-propagated"]
                self.assertEqual(it.status, "fail", it.detail)
                for name in TYPE4:
                    self.assertIn(f"{name} propagated as SGP4", it.detail)
                self.assertNotIn("beside SGP4 positions", it.detail)


# ---- gpconf/runner.py: run and the write command

class TheTagOption(unittest.TestCase):
    def test_a_tag_runs_exactly_the_cases_that_carry_it(self):
        """Kills 1430 (--tag runs the cases without the tag and leaves out those with it)."""
        tag = "sgp4-propagation"
        runner = Runner(Reference(), root=ROOT, fetch_hints=False)
        cases = runner.manifest["cases"]
        want = [c["id"] for c in cases if tag in c["tests"]]
        self.assertTrue(0 < len(want) < len(cases))
        self.assertEqual([r.case_id for r in runner.run(tags=[tag])], want)


class TheWriteCommand(unittest.TestCase):
    def test_exit_3_is_unsupported_and_exit_4_a_refusal(self):
        """Kills 1477 (exit 4 read as unsupported and exit 3, the documented 'writing unsupported', as refusing the
        record)."""
        def ends(code):
            return CommandParser(None, write_cmd=[sys.executable, "-c", f"import sys; sys.stdin.read(); sys.exit({code})"])
        rec = {"norad_cat_id": 25544}
        with self.assertRaises(Unsupported):
            ends(3).write_tle(rec)
        with self.assertRaises(Exception) as e:
            ends(4).write_tle(rec)
        self.assertIs(type(e.exception), RuntimeError)
        self.assertIn("exit 4", str(e.exception))


if __name__ == "__main__":
    unittest.main()
