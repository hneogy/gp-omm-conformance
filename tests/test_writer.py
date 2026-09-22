"""Writer-side case (tle-writer-alpha5) and gpconf/writer.py. Run: python -m unittest tests.test_writer

The reference writer (the corpus renderer) must pass every check exactly; the naive writer (integer-formatted
catalog number) must fail the catalog field, the line checks and the refusal check; python-sgp4's export_tle,
when installed, must pass the catalog field and the line checks, refuse 340000 and 799501621, and (a known
lenience of to_alpha5) write '-0001' for -1. A refusal for a number the TLE field cannot carry is the correct
output, and the tests assert it is reported as a pass."""
import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import tle as T  # noqa: E402
from gpconf import writer as W  # noqa: E402
from gpconf.runner import Runner, CommandParser, Unsupported  # noqa: E402
from gpconf import reference as ref  # noqa: E402
from gpconf.__main__ import main as gpconf_main  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402
from tests.adapters.naive import Parser as Naive  # noqa: E402

CASE = "tle-writer-alpha5"


def run_case(parser):
    return Runner(parser, root=ROOT).run(case_ids=[CASE])[0]


def items(result):
    return {i.check: i for i in result.items}


def load_expected():
    with open(os.path.join(ROOT, "fixtures", CASE, "expected.json")) as f:
        return json.load(f)


class ExpectedInputsTests(unittest.TestCase):
    def test_inputs_are_frozen_records_plus_three_approved_synthetic_ids(self):
        exp = load_expected()
        self.assertEqual(exp["kind"], "writer")
        recs = exp["records"]
        synthetic = [r for r in recs if r["provenance"] == "synthetic-derived"]
        frozen = [r for r in recs if r["provenance"] == "derived"]
        self.assertEqual(sorted(r["norad_cat_id"] for r in synthetic), [-1, 340000, 799501621])
        self.assertTrue(all(r["representable_in_tle"] is False and r["expected_behaviour"] == "refuse" for r in synthetic))
        self.assertTrue(all(r["tier"] == "stable" and r["representable_in_tle"] for r in frozen))
        self.assertEqual(len(frozen), len({r["norad_cat_id"] for r in frozen}))
        self.assertEqual(len(synthetic) + len(frozen), len(recs))
        self.assertEqual(len(frozen), 606)  # 603 distinct Alpha-5 ids (270449 is in two derived files) + 25544, 69999, 81011
        letters = [r["expected_catalog_field"][0] for r in frozen if r["norad_cat_id"] >= 100000]
        self.assertEqual((letters.count("A"), letters.count("T"), len(letters)), (257, 346, 603))
        for r in frozen:
            self.assertEqual(r["expected_catalog_field"], T.to_alpha5(r["norad_cat_id"]))
            self.assertTrue(r["source_sha256"], r["norad_cat_id"])


class ReferenceWriterTests(unittest.TestCase):
    def test_passes_every_check_exactly(self):
        r = run_case(Reference())
        by = items(r)
        self.assertEqual(r.status, "pass", [(i.check, i.status, i.detail) for i in r.items if i.status not in ("pass", "info")])
        for check in ("tle-checksums-valid", "tle-writer-catalog-field", "tle-writer-round-trip", "tle-writer-refuses-unencodable"):
            self.assertEqual(by[check].status, "pass", check)
        self.assertNotIn("pass-tolerance", {i.status for i in r.items})
        self.assertIn("correctly refused", by["tle-writer-refuses-unencodable"].detail)
        self.assertIn("eccentricity: ", by["tle-writer-round-trip"].detail)  # the convention observed is reported
        self.assertEqual(by["tle-writer-secondary-fields"].status, "info")
        self.assertIn("'+'", by["tle-writer-secondary-fields"].detail)  # CelesTrak sign for a zero second derivative
        self.assertEqual(by["tle-writer-matches-provider-rendering"].status, "info")


class NaiveWriterTests(unittest.TestCase):
    def test_fails_catalog_field_lines_and_refusal(self):
        r = run_case(Naive())
        by = items(r)
        self.assertEqual(r.status, "fail")
        self.assertEqual(by["tle-writer-catalog-field"].status, "fail")
        self.assertIn("'10000'", by["tle-writer-catalog-field"].detail)  # six digits written, five read back
        self.assertEqual(by["tle-checksums-valid"].status, "fail")
        self.assertIn("70 characters", by["tle-checksums-valid"].detail)
        self.assertEqual(by["tle-writer-refuses-unencodable"].status, "fail")
        self.assertIn("0 of 3", by["tle-writer-refuses-unencodable"].detail)
        self.assertIn("instead of a refusal", by["tle-writer-refuses-unencodable"].detail)
        self.assertIn("3 of 606 catalog field(s) correct", by["tle-writer-catalog-field"].detail)


class Sgp4WriterTests(unittest.TestCase):
    def test_export_tle_encodes_alpha5_and_refuses_above_ceiling(self):
        try:
            from tests.adapters.sgp4_adapter import Parser as Sgp4
        except ImportError:
            self.skipTest("python-sgp4 not installed")
        r = run_case(Sgp4())
        by = items(r)
        self.assertEqual(by["tle-writer-catalog-field"].status, "pass", by["tle-writer-catalog-field"].detail)
        self.assertEqual(by["tle-checksums-valid"].status, "pass", by["tle-checksums-valid"].detail)
        # omm.initialize refuses 340000 and 799501621; to_alpha5(-1) returns '-0001' (no lower bound, as the vectors
        # case already records), so the library writes a line for -1 and the refusal check fails on that id alone
        ref = by["tle-writer-refuses-unencodable"]
        self.assertEqual(ref.status, "fail", ref.detail)
        self.assertIn("2 of 3", ref.detail)
        self.assertIn("correctly refused (340000, 799501621)", ref.detail)
        self.assertIn("written instead of refused: id -1:", ref.detail)
        self.assertNotIn("id 340000", ref.detail)
        self.assertNotIn("id 799501621", ref.detail)
        self.assertIn("'-'", by["tle-writer-secondary-fields"].detail)  # Space-Track sign for a zero second derivative


class WriterFunctionTests(unittest.TestCase):
    def test_strict_catalog_field(self):
        self.assertEqual(W.strict_catalog_field("A0000"), 100000)
        self.assertEqual(W.strict_catalog_field("00005"), 5)
        self.assertEqual(W.strict_catalog_field("Z9999"), 339999)
        for bad in ("I0000", "O1234", "a0000", "A000", "     ", " 1234", "1A000", "10000 "):
            with self.assertRaises(ValueError, msg=bad):
                W.strict_catalog_field(bad)

    def test_fit_tool_style_output_passes_format_checks_and_reports_secondary_fields(self):
        # an orbit-fitting tool's output: elements from the record, first/second derivative, element set and
        # revolution zeroed, eccentricity rounded, zero second derivative written with the '-' sign
        rec = next(r for r in load_expected()["records"] if r["norad_cat_id"] == 100000)["canonical"]
        f = T.omm_fields_from_record(rec)
        f.update({"MEAN_MOTION_DOT": "0", "MEAN_MOTION_DDOT": "0", "ELEMENT_SET_NO": "0", "REV_AT_EPOCH": "0"})
        _, l1, l2 = T.render(f, mantissa_mode="round", ecc_mode="round")
        l1 = l1[:50] + "-" + l1[51:68]
        l1 += str(T.checksum(l1))
        self.assertEqual(W.check_lines(l1, l2), [])
        self.assertEqual(W.check_catalog_field(l1, l2, 100000), (True, "A0000"))
        mism, conv = W.round_trip(None, l1, l2, rec)
        self.assertEqual(mism, [])
        self.assertIn(conv["eccentricity"], ("exact", "quantised", "round"))
        s = W.secondary_fields(None, l1, l2, rec)
        self.assertEqual((s["mean_motion_dot"], s["element_set_no"], s["rev_at_epoch"], s["object_name"], s["zero_ddot_sign"]),
                         ("zeroed", "zeroed", "zeroed", "dropped", "-"))

    def test_round_trip_reports_truncation_and_rounding(self):
        rec = next(r for r in load_expected()["records"] if r["norad_cat_id"] == 270449)["canonical"]  # eccentricity .00455596
        f = T.omm_fields_from_record(rec)
        for mode in ("truncate", "round"):
            _, l1, l2 = T.render(f, mantissa_mode="round", ecc_mode=mode)
            mism, conv = W.round_trip(None, l1, l2, rec)
            self.assertEqual(mism, [], mode)
            self.assertEqual(conv["eccentricity"], mode)
        l2_bad = l2[:26] + "0045500" + l2[33:68]
        l2_bad += str(T.checksum(l2_bad))
        mism, _ = W.round_trip(None, l1, l2_bad, rec)
        self.assertEqual(len(mism), 1)
        self.assertIn("eccentricity", mism[0])

    def test_normalise_lines(self):
        self.assertEqual(W.normalise_lines(("a", "b")), (None, "a", "b"))
        self.assertEqual(W.normalise_lines("n\r\n1 x\r\n2 y\r\n"), ("n", "1 x", "2 y"))
        with self.assertRaises(ValueError):
            W.normalise_lines(["only one"])


class WriteCommandTests(unittest.TestCase):
    def test_write_cmd_protocol(self):
        script = ("import json, sys\n"
                  f"sys.path.insert(0, {ROOT!r})\n"
                  "from gpconf import tle as T\n"
                  "r = json.load(sys.stdin)\n"
                  "print('\\n'.join(T.render(T.omm_fields_from_record(r), mantissa_mode='round')))\n")
        rec = next(r for r in load_expected()["records"] if r["norad_cat_id"] == 100000)["canonical"]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "w.py")
            with open(p, "w") as f:
                f.write(script)
            cp = CommandParser(None, write_cmd=f"{shlex.quote(sys.executable)} {shlex.quote(p)}")  # paths may contain spaces
            l0, l1, l2 = W.normalise_lines(cp.write_tle(rec))
            self.assertEqual(W.check_catalog_field(l1, l2, 100000), (True, "A0000"))
            with self.assertRaises(RuntimeError):  # the script raises for 340000 -> non-zero exit -> refusal
                cp.write_tle(dict(rec, norad_cat_id=340000))
            with self.assertRaises(Unsupported):
                cp.parse(b"", "tle")
            self.assertEqual(subprocess.run([sys.executable, "-c", "print(1)"], capture_output=True).returncode, 0)


class CheckTleTests(unittest.TestCase):
    """check-tle: the writer checks applied to a file a tool wrote (rffit's layout: name, two lines, '#' trailer)."""

    def setUp(self):
        self.rec = next(r for r in load_expected()["records"] if r["norad_cat_id"] == 100000)["canonical"]
        f = T.omm_fields_from_record(self.rec)
        f.update({"MEAN_MOTION_DOT": "0", "MEAN_MOTION_DDOT": "0", "ELEMENT_SET_NO": "0", "REV_AT_EPOCH": "0"})
        _, l1, l2 = T.render(f, mantissa_mode="round", ecc_mode="round")
        l1 = l1[:50] + "-" + l1[51:68]
        l1 += str(T.checksum(l1))
        self.fit_style = f"SARAMAGO\n{l1}\n{l2}\n# 20260714.50-20260714.90, 12 measurements, 0.123 kHz rms\n# generated using a fitting tool\n"
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text):
        p = os.path.join(self.tmp.name, name)
        with open(p, "w") as f:
            f.write(text)
        return p

    def source_csv(self):
        f = T.omm_fields_from_record(self.rec)
        return ",".join(ref.CELESTRAK_CSV_JSON_KEYS) + "\n" + ",".join(f[k] for k in ref.CELESTRAK_CSV_JSON_KEYS) + "\n"

    def test_fit_tool_layout_passes_and_ignores_the_trailer(self):
        res = W.check_file(self.fit_style)
        self.assertEqual(len(res), 1)
        r = res[0]
        self.assertEqual((r["status"], r["norad_cat_id"], r["catalog_field"], r["name"], r["line_number"]), ("pass", 100000, "A0000", "SARAMAGO", 2))
        self.assertTrue(any("'-'" in n for n in r["notes"]), r["notes"])
        self.assertTrue(any("A0000 decodes to 100000" in n for n in r["notes"]), r["notes"])

    def test_against_source_records_round_trips_and_reports_secondary_fields(self):
        against = W.load_against(self.write("source.csv", self.source_csv()))
        r = W.check_file(self.fit_style, against)[0]
        self.assertEqual(r["status"], "pass", r["problems"])
        self.assertEqual(r["round_trip"]["mismatches"], [])
        self.assertEqual((r["secondary_fields"]["mean_motion_dot"], r["secondary_fields"]["zero_ddot_sign"]), ("zeroed", "-"))
        other = {5: against[100000]}  # no record for this id -> round trip not checked, said so
        r = W.check_file(self.fit_style, other)[0]
        self.assertEqual(r["status"], "pass")
        self.assertTrue(any("no source record with id 100000" in n for n in r["notes"]))

    def test_six_digit_integer_field_and_blank_field_fail(self):
        l1, l2 = Naive().write_tle(self.rec)
        r = W.check_file(f"{l1}\n{l2}\n")[0]
        self.assertEqual(r["status"], "fail")
        self.assertTrue(any("6-digit catalog number 100000" in p and "'A0000'" in p for p in r["problems"]), r["problems"])
        self.assertTrue(any("70 characters" in p for p in r["problems"]), r["problems"])
        l1, l2 = Naive().write_tle(dict(self.rec, norad_cat_id=799501621))
        r = W.check_file(f"{l1}\n{l2}\n")[0]
        self.assertTrue(any("9-digit catalog number 799501621" in p and "refusal" in p for p in r["problems"]), r["problems"])
        _, l1, l2 = T.render(T.omm_fields_from_record(self.rec))
        l1, l2 = "1      " + l1[7:68], "2      " + l2[7:68]  # a blank field, as a writer without a range check may produce
        l1 += str(T.checksum(l1))
        l2 += str(T.checksum(l2))
        r = W.check_file(f"{l1}\n{l2}\n")[0]
        self.assertEqual(r["status"], "fail")
        self.assertTrue(any("not five non-blank characters" in p for p in r["problems"]), r["problems"])
        self.assertIsNone(r["norad_cat_id"])

    def test_cli_exit_codes_and_output(self):
        good = self.write("fit.tle", self.fit_style)
        bad_l1, bad_l2 = Naive().write_tle(self.rec)
        bad = self.write("bad.tle", f"{bad_l1}\n{bad_l2}\n")
        empty = self.write("empty.txt", "nothing here\n")
        src = self.write("source.csv", self.source_csv())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = gpconf_main(["check-tle", good, "--against", src, "--json", os.path.join(self.tmp.name, "r.json")])
        self.assertEqual(rc, 0, out.getvalue())
        self.assertIn("[pass] line 2: SARAMAGO | catalog field 'A0000' -> 100000", out.getvalue())
        self.assertIn("round trip against the source record", out.getvalue())
        with open(os.path.join(self.tmp.name, "r.json")) as f:
            self.assertEqual(json.load(f)["files"][0]["records"][0]["status"], "pass")
        for path, expect in ((bad, 1), (empty, 1)):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = gpconf_main(["check-tle", path])
            self.assertEqual(rc, expect, out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            gpconf_main(["check-tle", bad])
        self.assertIn("[fail]", out.getvalue())
        self.assertIn("must be the Alpha-5 form 'A0000'", out.getvalue())


if __name__ == "__main__":
    unittest.main()
