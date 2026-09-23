"""Runner completeness (D-118): every listed check is evaluated, every hook is reachable, a raising hook fails
its vector and nothing else, legal epoch forms are accepted, and the report and catalogue say what ran."""
import contextlib
import io
import json
import os
import shlex
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from gpconf.runner import Runner, CommandParser, norm_epoch  # noqa: E402
from gpconf import tle as T  # noqa: E402
from gpconf.__main__ import main as gpconf_main  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402
import make_failures  # noqa: E402

THREE = {"leading-dot-decimals": ("epoch-year-19xx", "baseline-iss-five-formats"),
         "bstar-implied-decimal-exponent": ("bstar-and-derivative-forms",),
         "negative-bstar-and-ndot": ("epoch-year-19xx", "bstar-and-derivative-forms")}


def raw_present(case):
    exp = json.load(open(os.path.join(ROOT, "fixtures", case, "expected.json")))
    return all(os.path.exists(os.path.join(ROOT, p)) for p in exp["sources"])


class ListedChecksAreEvaluated(unittest.TestCase):
    """10.8: the three checks named in the manifest and the case documents produce items."""

    @classmethod
    def setUpClass(cls):
        cls.cases = sorted({c for cs in THREE.values() for c in cs})
        if not all(raw_present(c) for c in cls.cases):
            raise unittest.SkipTest("raw fixtures absent (public clone); run tools/fetch.py")
        cls.results = {r.case_id: r for r in Runner(Reference(), root=ROOT).run(case_ids=cls.cases)}

    def test_each_listed_check_yields_a_passing_item_for_the_reference(self):
        for check, cases in THREE.items():
            for case in cases:
                items = [i for i in self.results[case].items if i.check == check]
                self.assertTrue(items, (case, check))
                self.assertTrue(all(i.status in ("pass", "not-exercised") for i in items), [(i.status, i.detail) for i in items])
                self.assertTrue(any(i.status == "pass" for i in items), (case, check))

    def test_every_check_a_case_lists_appears_in_its_items(self):
        manifest = json.load(open(os.path.join(ROOT, "manifest.json")))
        for c in manifest["cases"]:
            if c["id"] not in self.results:
                continue
            seen = {i.check for i in self.results[c["id"]].items}
            self.assertEqual(sorted(set(c["checks"]) - seen), [], c["id"])


class Vectors(unittest.TestCase):
    """10.10 and 10.11."""

    def test_a_raising_hook_fails_that_vector_and_the_case_continues(self):
        class Parser(Reference):
            def two_digit_year(self, yy):
                if yy == "57":
                    raise ValueError("boom")
                return super().two_digit_year(yy)
        r = Runner(Parser(), root=ROOT).run(case_ids=["alpha5-encoding-vectors"])[0]
        checks = {i.check: i for i in r.items}
        self.assertNotIn("runner", checks)                                      # no "internal error in runner"
        self.assertEqual(checks["two-digit-year-pivot"].status, "fail")
        self.assertIn("57", checks["two-digit-year-pivot"].detail)
        self.assertIn("raised", checks["two-digit-year-pivot"].detail)
        for other in ("alpha5-decode", "alpha5-encode", "ccsds-epoch-strings", "catalog-number-is-integer"):
            self.assertEqual(checks[other].status, "pass", other)

    def vectors_script(self):
        code = ("import json, sys\n"
                "sys.path.insert(0, %r)\n"
                "from gpconf import tle as T\n"
                "from tests.adapters.reference import Parser\n"
                "req = json.load(sys.stdin); p = Parser()\n"
                "try:\n"
                "    r = getattr(p, req['op'])(req['input'])\n"
                "    if hasattr(r, 'isoformat'): r = r.isoformat()\n"
                "    print(json.dumps({'result': r}))\n"
                "except Exception as e:\n"
                "    print(json.dumps({'error': str(e)})); sys.exit(1)\n") % ROOT
        d = tempfile.mkdtemp()
        p = os.path.join(d, "vec.py")
        with open(p, "w") as f:
            f.write(code)
        return f"{shlex.quote(sys.executable)} {shlex.quote(p)}"

    def test_vectors_cmd_reaches_parse_catalog_id(self):
        cp = CommandParser(None, vectors_cmd=self.vectors_script())
        self.assertTrue(hasattr(cp, "parse_catalog_id"))
        self.assertEqual(cp.parse_catalog_id("799501621"), 799501621)
        r = Runner(cp, root=ROOT).run(case_ids=["alpha5-encoding-vectors"])[0]
        item = next(i for i in r.items if i.check == "catalog-number-is-integer")
        self.assertEqual(item.status, "pass", item.detail)

    def test_a_command_answer_without_result_is_an_error_not_a_crash(self):
        cp = CommandParser(None, vectors_cmd="echo '{}'")
        with self.assertRaises(ValueError):
            cp.alpha5_decode("A0000")


class EpochForms(unittest.TestCase):
    """10.12: legal ISO forms the normaliser used to reject as 'parser raised'."""

    def test_offsets_and_leap_second(self):
        self.assertEqual(norm_epoch("2026-09-20T12:42:37.141056+00:00"), "2026-09-20T12:42:37.141056")
        self.assertEqual(norm_epoch("2026-09-20T14:42:37.141056+02:00"), "2026-09-20T12:42:37.141056")
        self.assertEqual(norm_epoch("2026-09-20T10:42:37-02:00"), "2026-09-20T12:42:37.000000")
        self.assertEqual(norm_epoch("2026-09-20T12:42:37.141056Z"), "2026-09-20T12:42:37.141056")
        self.assertEqual(norm_epoch("2016-12-31T23:59:60"), "2016-12-31T23:59:59.000000")   # as the reference adapter maps it
        self.assertEqual(norm_epoch("2016-366T23:59:60.5"), "2016-12-31T23:59:59.500000")


class ReportAndCatalogue(unittest.TestCase):
    """10.15."""

    def test_json_report_names_the_write_cmd_parser(self):
        d = tempfile.mkdtemp()
        out = os.path.join(d, "r.json")
        with contextlib.redirect_stdout(io.StringIO()):
            gpconf_main(["run", "--write-cmd", "exit 3", "--case", "tle-writer-alpha5", "--json", out])
        self.assertEqual(json.load(open(out))["parser"], "exit 3")

    def test_catalogue_withholds_supgp_values_for_every_value_carrying_check(self):
        supgp = "fixtures/nine-digit-supgp-launch-nominals/raw/starlink-g15-27.csv"
        item = lambda check, detail, file=supgp: {"check": check, "status": "fail", "file": file, "detail": detail}
        rep = {"generated_at": "now", "gpconf": "x", "corpus_version": "x", "parser": "p", "results": [
            {"case": "nine-digit-supgp-launch-nominals", "status": "fail", "counts": {"fail": 3}, "items": [
                item("values", "mean_motion: got 15.1234567 want 15.1234568"),
                item("omm-formats-agree", "{'15.1234567': ['a.csv'], '15.1234568': ['b.xml']}"),
                item("tle-values-match-omm-within-tle-precision", "eccentricity tle 0.0001234 omm 0.0001235"),
                item("parse", "parser raised ValueError: satellite number cannot exceed 339999")]}]}
        md = make_failures.render({"reference": rep, "naive": rep, "sgp4": None}, "2026-01-01T00:00:00Z")
        self.assertEqual(md.count("withheld"), 3, md)
        self.assertNotIn("15.1234567", md)
        self.assertNotIn("0.0001234", md)
        self.assertIn("satellite number cannot exceed 339999", md)   # a structural detail stays readable


class Rendering(unittest.TestCase):
    def test_ndot_field_rounds_half_up_like_the_provider(self):
        self.assertEqual(T.ndot_field("0.000000125"), " .00000013")
        self.assertEqual(T.ndot_field("-0.000000125"), "-.00000013")
        self.assertEqual(T.ndot_field("0.00008422"), " .00008422")


if __name__ == "__main__":
    unittest.main()
