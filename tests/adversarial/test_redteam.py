# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The fresh-session red team's adapters against the current runner (D-293 to D-303).

A blind audit of gpconf 0.6.2 from PyPI on 2026-10-09 wrote fourteen escapes, each a "Win" that ended a run with
no failing case, and a "Twin" with the same bug that failed. Here every Win that was an escape fails, or reads
not-exercised where nothing can be measured; the two the report itself marks as by design still pass, and say so;
every Twin fails as it did. Run offline: the data folder is empty, as the red team's was.

Run: python -m unittest tests.adversarial.test_redteam"""
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf.runner import Runner  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from tests.crashwatch import watched  # noqa: E402

NO_DATA = ["alpha5-encoding-vectors", "alpha5-tle-derived", "kvn-syntax-variants", "tle-writer-alpha5", "corrupt-input"]
EMPTY = tempfile.mkdtemp(prefix="gpconf-redteam-empty-")


def adapter(module, cls):
    return getattr(importlib.import_module(f"tests.adversarial.redteam.{module}"), cls)()


def run(parser, cases=NO_DATA):
    return {r.case_id: r for r in Runner(parser, root=ROOT, data=EMPTY, fetch_hints=False).run(case_ids=cases)}


def failing(results):
    return sorted(c for c, r in results.items() if r.status == "fail")


class EscapesThatAreClosed(unittest.TestCase):
    def test_e1_per_file_unsupported(self):                     # D-280
        self.assertEqual(failing(run(adapter("e01", "Win"))), ["alpha5-tle-derived"])

    def test_e1_through_the_command_protocol(self):             # D-280: exit 3 decided on content
        from gpconf.runner import CommandParser
        script = os.path.join(ROOT, "tests", "adversarial", "redteam", "cmd_e01.py")
        r = run(CommandParser([sys.executable, script, "{fmt}"]), ["alpha5-tle-derived"])
        self.assertEqual(failing(r), ["alpha5-tle-derived"])
        self.assertTrue(any("(D-280)" in i.detail for i in r["alpha5-tle-derived"].items))

    def test_e2_writer_unsupported_on_one_input(self):          # D-280
        self.assertEqual(failing(run(adapter("e02", "Win"))), ["tle-writer-alpha5"])

    def test_e3_duplicate_under_a_known_id(self):               # D-281
        self.assertIn("alpha5-tle-derived", failing(run(adapter("e03", "Win"))))

    def test_e4_optional_key_lost_on_some_records(self):        # D-284
        self.assertIn("alpha5-tle-derived", failing(run(adapter("e04", "Win"))))

    def test_e5a_float_from_the_decode_hook(self):              # D-296
        r = run(adapter("e05a", "Win"))
        self.assertEqual(failing(r), ["alpha5-encoding-vectors"])
        (item,) = [i for i in r["alpha5-encoding-vectors"].items if i.check == "alpha5-decode"]
        self.assertIn("expected int", item.detail)

    def test_e5b_float_ids_from_parse(self):                    # D-283
        self.assertEqual(failing(run(adapter("e05b", "Win"))), ["alpha5-tle-derived", "corrupt-input", "kvn-syntax-variants"])

    def test_e7_unrelated_refusal(self):                        # D-282
        self.assertEqual(failing(run(adapter("e07", "Win"))), ["corrupt-input"])

    def test_e8_a_consistent_drop_cannot_read_pass(self):       # D-294, D-342
        r = run(adapter("e08", "Win"))
        self.assertEqual(failing(r), ["corrupt-input"])          # the unedited TLE file's frozen values catch the drop (D-342)
        values = [i for i in r["corrupt-input"].items if i.check == "values" and (i.file or "").endswith("unedited-sets.tle")]
        self.assertEqual([i.status for i in values], ["fail"])
        self.assertEqual(len(r["corrupt-input"].voided_by_parser()), 5)   # the inputs it leaves ungraded are still named (five with D-360's sixth input)
        self.assertEqual(r["corrupt-input"].as_dict()["voided_by_parser"], r["corrupt-input"].voided_by_parser())
        for name in ("Empty", "RefuseSome"):                     # the report's two wider cases
            self.assertNotEqual(run(adapter("e00", name))["corrupt-input"].status, "pass", name)

    def test_e9_sys_exit_inside_parse_fails_with_a_report(self):  # D-293, in process
        r = run(adapter("e09", "Win"))
        self.assertEqual(failing(r), ["corrupt-input"])
        (item,) = [i for i in r["corrupt-input"].items if i.check == "parser-exit"]
        self.assertIn("SystemExit", item.detail)

    def test_e9_from_the_command_line_exits_1_and_writes_the_report(self):  # D-293, as the red team ran it
        out = os.path.join(tempfile.mkdtemp(), "report.json")
        p = subprocess.run([sys.executable, "-m", "gpconf", "run", "--adapter", "tests.adversarial.redteam.e09:Win", "--root", ROOT, "--data", EMPTY,
                            "--no-fetch-hint", "--json", out], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 1, p.stderr[-300:])       # on 0.6.2: exit 0, no report
        report = json.load(open(out, encoding="utf-8"))
        self.assertEqual(report["summary"]["fail"], 1)

    def test_an_adapter_that_exits_while_loading_is_a_setup_error(self):   # D-293
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "exits_on_import.py"), "w", encoding="utf-8") as f:
            f.write("import sys\nsys.exit(0)\n")
        p = subprocess.run([sys.executable, "-m", "gpconf", "run", "--adapter", "exits_on_import:Parser", "--root", ROOT, "--data", EMPTY],
                           cwd=d, env=watched(dict(os.environ, PYTHONPATH=ROOT)), capture_output=True, text=True)
        self.assertEqual(p.returncode, 2, p.stdout[-200:] + p.stderr[-200:])
        self.assertIn("exited while loading", p.stderr)

    def test_e11_reader_and_hook_with_different_tables(self):   # D-286, D-300
        self.assertEqual(failing(run(adapter("e11", "Win"))), ["alpha5-tle-derived"])
        self.assertEqual(failing(run(adapter("e11", "WinNoHook"))), ["alpha5-tle-derived"])

    def test_e15_an_omm_value_is_graded_offline(self):          # D-299
        r = run(adapter("e15", "Win"))
        self.assertEqual(failing(r), ["corrupt-input"])
        bad = sorted(os.path.basename(i.file) for i in r["corrupt-input"].items if i.check == "values" and i.status == "fail")
        self.assertEqual(bad, ["unedited-array.json", "unedited-rows.csv", "v07-xml-ndm-reserialised.xml"])   # CSV, JSON and XML

    def test_e6_epoch_text_handed_back_unparsed(self):          # D-306
        """The escape: a parser with no day-of-year support returns the epoch text as it found it, and the runner
        parsed it for the parser. The red team's adapter stands on the reference adapter's output, which up to 0.6.2
        carried a KVN epoch as the file wrote it; the reference now parses its own epochs, so the adapter is stood
        here on that 0.6.2 behaviour, rebuilt in this test, the base it was written against, with its own file untouched."""
        e06 = importlib.import_module("tests.adversarial.redteam.e06")

        class AsWritten(Reference):
            """The reference adapter as it stood at 0.6.2: the corpus's readers, each epoch left as the file wrote
            it. Test code only; the shipped adapter has no such door."""
            def parse(self, raw, fmt):
                from gpconf import reference as ref
                from gpconf.adapters.reference import tle_sets
                from gpconf.runner import CORE_FIELDS, OPTIONAL_FIELDS, Unsupported
                text = raw.decode("utf-8")
                if fmt in ("tle", "2le"):
                    recs = tle_sets(text)
                elif fmt in ("csv", "json", "xml", "kvn"):
                    recs, _ = getattr(ref, f"read_{fmt}_text")(text)
                else:
                    raise Unsupported(fmt)
                return [r if "_refused" in r else {k: r.get(k) for k in CORE_FIELDS + OPTIONAL_FIELDS if r.get(k) is not None or k in CORE_FIELDS}
                        for r in recs]

        class Win(e06.Win, AsWritten):
            pass

        class Twin(e06.Twin, AsWritten):
            pass
        r = run(Win())
        self.assertEqual(failing(r), ["alpha5-encoding-vectors", "kvn-syntax-variants"])
        (hook,) = [i for i in r["alpha5-encoding-vectors"].items if i.check == "ccsds-epoch-strings"]
        self.assertIn("parse_epoch must return a datetime", hook.detail)
        (values,) = [i for i in r["kvn-syntax-variants"].items if i.check == "values" and i.status == "fail"]
        self.assertIn("v02-day-of-year-epoch-Z.kvn", values.file)
        self.assertIn("passed back unparsed", values.detail)
        self.assertEqual(failing(run(Twin())), ["alpha5-encoding-vectors", "kvn-syntax-variants"])
        # on today's reference the adapter's KVN bug never meets raw text; its hook still hands text back, and fails
        self.assertEqual(failing(run(adapter("e06", "Win"))), ["alpha5-encoding-vectors"])

    def test_e6_a_command_that_echoes_the_epoch_fails(self):    # D-306: a command answers in text
        from gpconf.runner import CommandParser
        echo = "import json,sys; q=json.load(sys.stdin); print(json.dumps({'result': q['input']} if q['op']=='parse_epoch' else {'unsupported': 'only the epoch hook'}))"
        parser = CommandParser(None, vectors_cmd=[sys.executable, "-c", echo])
        r = run(parser, ["alpha5-encoding-vectors"])["alpha5-encoding-vectors"]
        (hook,) = [i for i in r.items if i.check == "ccsds-epoch-strings"]
        self.assertEqual(hook.status, "fail")
        self.assertIn("rejected (ValueError)", hook.detail)     # the proxy's refusal of the echoed text

    def test_text_a_harness_built_itself_is_still_normalised(self):   # D-306: what the rule leaves alone
        """The corpus's harnesses return a TLE epoch as year and day-of-year text, by design, and the runner
        normalises it: such text is in no input, so nothing was handed back unparsed."""
        import datetime as dt

        class DayOfYear(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                for d in out:
                    if "_refused" not in d and isinstance(d.get("epoch"), str):
                        t = dt.datetime.strptime(d["epoch"], "%Y-%m-%dT%H:%M:%S.%f")
                        d["epoch"] = f"{t.year:04d}-{t.timetuple().tm_yday:03d}T{t.strftime('%H:%M:%S.%f')}"
                return out
        self.assertEqual(failing(run(DayOfYear(), ["alpha5-tle-derived", "corrupt-input"])), [])


class ByDesign(unittest.TestCase):
    """The two the report itself says contradict nothing (D-303)."""

    def test_e10_writer_secondary_fields_are_information(self):
        self.assertEqual(failing(run(adapter("e10", "Win"))), [])

    def test_e17_float_output_within_the_documented_tolerance(self):
        r = run(adapter("e17", "Win"))
        self.assertEqual(failing(r), [])
        self.assertEqual(r["alpha5-tle-derived"].status, "pass-tolerance")


class Twins(unittest.TestCase):
    def test_every_twin_fails(self):
        for m in ("e01", "e02", "e03", "e04", "e05a", "e06", "e07", "e09", "e10", "e11", "e17"):   # e06's on its 0.6.2 base is in the E6 test
            with self.subTest(m):
                self.assertTrue(failing(run(adapter(m, "Twin"))), m)

    def test_the_two_adapters_with_no_escape_fail(self):
        for name in ("Empty", "RefuseSome"):   # corrupt-input since D-342: no TLE record, or a valid one refused, from the unedited file
            self.assertEqual(failing(run(adapter("e00", name))), ["alpha5-tle-derived", "corrupt-input"], name)


class FalseFailsOnCorrectParsers(unittest.TestCase):
    """Section 6 of the report: two ways a right parser was failed (D-295)."""

    def test_an_integer_type_that_is_not_int_is_an_integer(self):
        class MyInt(int):
            pass

        class Tagged(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                for r in out:
                    if isinstance(r.get("norad_cat_id"), int):
                        r["norad_cat_id"] = MyInt(r["norad_cat_id"])
                return out
        self.assertEqual(failing(run(Tagged())), [])
        from gpconf.runner import is_integral
        self.assertEqual([is_integral(v) for v in (1, MyInt(1), True, 1.0, "1")], [True, True, False, False, False])

    def test_a_record_carrying_an_adapter_key_is_kept(self):
        from gpconf.runner import split_refusals
        recs, refusals, declared = split_refusals([{"_adapter": {"refusals": True}}, {"_adapter": "v1", "norad_cat_id": 25544}])
        self.assertEqual((len(recs), refusals, declared), (1, [], True))


class ReportingDefects(unittest.TestCase):
    """Sections 4 and 6: what the report said was misattributed or miscounted (D-298)."""

    def test_refused_records_are_not_called_wrong_decodes(self):
        r = run(adapter("e00", "RefuseSome"), ["alpha5-tle-derived"])["alpha5-tle-derived"]
        decodes = [i for i in r.items if i.check == "tle-catalog-field-decodes" and "last-30-days" in (i.file or "")]
        self.assertEqual([i.status for i in decodes], ["pass"])
        self.assertIn("refused with a reason, not graded here", decodes[0].detail)

    def test_the_gate_says_when_more_came_back_than_the_file_holds(self):
        from gpconf.gates import compute_gates
        results = Runner(adapter("e03", "Win"), root=ROOT, data=EMPTY, fetch_hints=False).run(case_ids=["alpha5-tle-derived"])
        (gate,) = compute_gates(results, ROOT, EMPTY)
        self.assertIn("256 returned beyond the file's records", gate["headline"])


class EveryListedCheckIsEvaluated(unittest.TestCase):
    """Section 5: a check a case lists and never evaluates is a claim nothing backs (D-301). For the reference
    adapter, every check each case lists appears among its items, in every case that has its data."""

    def test_no_listed_check_goes_unevaluated(self):
        manifest = json.load(open(os.path.join(ROOT, "manifest.json"), encoding="utf-8"))
        results = {r.case_id: r for r in Runner(Reference(), root=ROOT, fetch_hints=False).run()}
        for c in manifest["cases"]:
            r = results[c["id"]]
            if r.status in ("not-fetched", "not-available") or any(i.status in ("not-fetched", "not-available") for i in r.items):
                continue
            with self.subTest(c["id"]):
                self.assertEqual(sorted(set(c["checks"]) - {i.check for i in r.items}), [])
