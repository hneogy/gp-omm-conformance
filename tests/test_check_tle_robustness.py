"""Batch D3 (D-119): check-tle reports stray lines instead of dropping them (10.6), a day-of-year source epoch
in --against is handled (10.7), and the writer checks catch misaligned columns (10.4).

Run: python -m unittest tests.test_check_tle_robustness"""
import contextlib
import glob
import io
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import tle as T  # noqa: E402
from gpconf import writer as W  # noqa: E402
from gpconf import reference as ref  # noqa: E402
from gpconf.runner import Runner  # noqa: E402
from gpconf.__main__ import main as gpconf_main  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402

CASE = "tle-writer-alpha5"


def record(catnr=100000):
    with open(os.path.join(ROOT, "fixtures", CASE, "expected.json")) as f:
        return next(r for r in json.load(f)["records"] if r["norad_cat_id"] == catnr)["canonical"]


def rendered(rec):
    """(line0, line1, line2) in the corpus's own rendering, mantissas and eccentricity rounded like a fitting tool."""
    return T.render(T.omm_fields_from_record(rec), mantissa_mode="round", ecc_mode="round")


def with_checksum(line68):
    return line68 + str(T.checksum(line68))


def csv_source(rec, **override):
    f = T.omm_fields_from_record(rec)
    f.update(override)
    return ",".join(ref.CELESTRAK_CSV_JSON_KEYS) + "\n" + ",".join(f[k] for k in ref.CELESTRAK_CSV_JSON_KEYS) + "\n"


class _Files(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rec = record()
        self.l0, self.l1, self.l2 = rendered(self.rec)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, text, binary=False):
        p = os.path.join(self.tmp.name, name)
        with open(p, "wb" if binary else "w") as f:
            f.write(text)
        return p

    def cli(self, *args):
        out = io.StringIO()
        report = os.path.join(self.tmp.name, "report.json")
        with contextlib.redirect_stdout(out):
            rc = gpconf_main(["check-tle", *args, "--json", report])
        with open(report) as f:
            return rc, out.getvalue(), json.load(f)


class StrayLines(_Files):
    """10.6: a '1 ' line without its '2 ', a '2 ' without its '1 ', an indented pair and a BOM used to vanish silently
    from check-tle, which then exited 0 (or 1 for 'nothing to check') without naming them."""

    def test_a_line_1_without_a_line_2_is_a_failing_entry(self):
        res = W.check_file(f"{self.l0}\n{self.l1}\n")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["status"], "fail")
        self.assertEqual(res[0]["line_number"], 2)
        self.assertTrue(any("line 1" in p and "no line 2" in p for p in res[0]["problems"]), res[0]["problems"])
        rc, out, rep = self.cli(self.write("orphan1.tle", f"{self.l0}\n{self.l1}\n"))
        self.assertEqual(rc, 1)
        self.assertIn("[fail]", out)
        self.assertIn("no line 2", out)
        self.assertEqual(rep["files"][0]["records"][0]["status"], "fail")

    def test_a_line_2_without_a_line_1_is_a_failing_entry(self):
        res = W.check_file(f"{self.l0}\n{self.l2}\n")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["status"], "fail")
        self.assertTrue(any("line 2" in p and "no line 1" in p for p in res[0]["problems"]), res[0]["problems"])

    def test_two_line_1s_in_a_row_report_the_first_as_unpaired(self):
        res = W.check_file(f"{self.l1}\n{self.l1}\n{self.l2}\n")
        self.assertEqual([r["status"] for r in res], ["fail", "pass"])
        self.assertEqual([r["line_number"] for r in res], [1, 2])

    def test_an_indented_pair_is_checked_and_the_indentation_reported(self):
        res = W.check_file(f"{self.l0}\n  {self.l1}\n  {self.l2}\n")
        self.assertEqual(len(res), 1)
        r = res[0]
        self.assertEqual(r["status"], "fail")
        self.assertEqual((r["norad_cat_id"], r["catalog_field"]), (100000, "A0000"))  # still identified after de-indenting
        self.assertTrue(any("indented" in p and "2 space" in p for p in r["problems"]), r["problems"])
        self.assertTrue(any("column 1" in p for p in r["problems"]), r["problems"])

    def test_a_bom_before_line_1_is_reported(self):
        text = "﻿" + f"{self.l1}\n{self.l2}\n"
        res = W.check_file(text)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["status"], "fail")
        self.assertTrue(any("BOM" in p for p in res[0]["problems"]), res[0]["problems"])
        self.assertEqual(res[0]["norad_cat_id"], 100000)
        rc, out, rep = self.cli(self.write("bom.tle", ("﻿" + f"{self.l0}\n{self.l1}\n{self.l2}\n").encode("utf-8"), binary=True))
        self.assertEqual(rc, 1)
        self.assertIn("BOM", out)

    def test_a_bom_before_a_name_line_is_reported_on_the_record(self):
        res = W.check_file("﻿" + f"{self.l0}\n{self.l1}\n{self.l2}\n")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["status"], "fail")
        self.assertTrue(any("BOM" in p for p in res[0]["problems"]), res[0]["problems"])
        self.assertEqual(res[0]["name"], "SARAMAGO")

    def test_a_clean_file_with_a_trailer_still_passes(self):
        res = W.check_file(f"{self.l0}\n{self.l1}\n{self.l2}\n# 20260714.50-20260714.90, 12 measurements\n")
        self.assertEqual([r["status"] for r in res], ["pass"])
        rc, out, rep = self.cli(self.write("clean.tle", f"{self.l0}\n{self.l1}\n{self.l2}\n"))
        self.assertEqual(rc, 0, out)

    def test_a_mixed_file_counts_every_entry(self):
        text = f"{self.l0}\n{self.l1}\n{self.l2}\n{self.l1}\n"
        rc, out, rep = self.cli(self.write("mixed.tle", text))
        self.assertEqual(rc, 1)
        self.assertEqual([r["status"] for r in rep["files"][0]["records"]], ["pass", "fail"])
        self.assertIn("2 record(s): 1 pass, 1 fail", out)


class DayOfYearSourceEpoch(_Files):
    """10.7: a source record whose EPOCH is the CCSDS day-of-year form (legal; the corpus's own KVN case declares it)
    used to raise an uncaught ValueError out of check-tle --against."""

    def doy(self, iso):
        import datetime as dt
        return dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.%f").strftime("%Y-%jT%H:%M:%S.%f") + "Z"

    def test_day_of_year_source_epoch_round_trips(self):
        src = self.write("source.csv", csv_source(self.rec, EPOCH=self.doy(self.rec["epoch"])))
        against = W.load_against(src)
        self.assertTrue(against[100000]["epoch"].startswith("2026-"), against[100000]["epoch"])
        self.assertIn("T", against[100000]["epoch"])
        res = W.check_file(f"{self.l0}\n{self.l1}\n{self.l2}\n", against)
        self.assertEqual(res[0]["status"], "pass", res[0]["problems"])
        self.assertIn(res[0]["round_trip"]["conventions"]["epoch"], ("exact", "quantised", "round", "truncate"))
        rc, out, rep = self.cli(self.write("w.tle", f"{self.l0}\n{self.l1}\n{self.l2}\n"), "--against", src)
        self.assertEqual(rc, 0, out)

    def test_an_unreadable_source_epoch_is_a_problem_not_a_crash(self):
        src = self.write("source.csv", csv_source(self.rec, EPOCH="yesterday"))
        against = W.load_against(src)
        res = W.check_file(f"{self.l0}\n{self.l1}\n{self.l2}\n", against)
        self.assertEqual(res[0]["status"], "fail")
        self.assertTrue(any("round trip" in p and "yesterday" in p for p in res[0]["problems"]), res[0]["problems"])

    def test_the_renderer_and_the_normaliser_accept_the_day_of_year_form(self):
        self.assertEqual(T.epoch_field("1998-324T06:49:59.999808Z"), T.epoch_field("1998-11-20T06:49:59.999808"))
        self.assertEqual(T.iso_epoch("2020-064T10:34:41.4264"), "2020-03-04T10:34:41.426400")
        self.assertEqual(T.iso_epoch("2002-204T15:56:23Z"), "2002-07-23T15:56:23.000000")
        self.assertEqual(T.iso_epoch("2026-09-20T12:42:37.141056+00:00"), "2026-09-20T12:42:37.141056")
        self.assertEqual(T.iso_epoch("2016-12-31T23:59:60"), "2016-12-31T23:59:59.000000")
        with self.assertRaises(ValueError):
            T.iso_epoch("yesterday")


def roundtrip_files():
    out = [p for p in glob.glob(os.path.join(ROOT, "fixtures", "*", "raw", "*.tle")) + glob.glob(os.path.join(ROOT, "fixtures", "*", "raw", "*.2le"))
           if os.path.getsize(p) > 100]
    return sorted(out) + sorted(glob.glob(os.path.join(ROOT, "derived", "alpha5-tle", "*.tle")))


class ColumnLayout(_Files):
    """10.4: left-justified values with a recomputed checksum passed every writer check, because the checks read the
    values back and never looked at where the fields sit. The layout check pins each field to its columns."""

    def test_every_provider_and_derived_line_has_the_standard_layout(self):
        n = 0
        for p in roundtrip_files():
            for r in ref.read_tle_text(open(p, encoding="utf-8").read()):
                n += 1
                self.assertEqual(W.check_layout(r["tle"]["line1"], r["tle"]["line2"]), [], (p, r["norad_cat_id"]))
        self.assertGreater(n, 600)

    def misaligned_line2(self):
        l2 = self.l2[:8] + self.l2[8:16].strip().ljust(8) + self.l2[16:68]  # inclination left-justified
        return with_checksum(l2)

    def test_a_left_justified_field_with_a_valid_checksum_fails_the_layout_check_only(self):
        l2 = self.misaligned_line2()
        self.assertEqual(W.check_lines(self.l1, l2), [])  # length and checksum are fine: that was the gap
        problems = W.check_layout(self.l1, l2)
        self.assertTrue(problems, "misaligned inclination not detected")
        self.assertTrue(any("columns 9-16" in p and "inclination" in p for p in problems), problems)
        r = W.check_file(f"{self.l0}\n{self.l1}\n{l2}\n")[0]
        self.assertEqual(r["status"], "fail")
        self.assertTrue(any("columns 9-16" in p for p in r["problems"]), r["problems"])

    def test_a_shifted_line_1_names_the_first_misplaced_field(self):
        l1 = with_checksum(self.l1[:32] + self.l1[33:68] + " ")  # everything after the epoch moves one column left
        self.assertEqual(W.check_lines(l1, self.l2), [])
        problems = W.check_layout(l1, self.l2)
        self.assertTrue(problems)
        self.assertTrue(any("line 1" in p and "columns 34-43" in p for p in problems), problems)

    def test_the_writer_case_reports_the_layout_item(self):
        r = Runner(Reference(), root=ROOT).run(case_ids=[CASE])[0]
        by = {i.check: i for i in r.items}
        self.assertIn("tle-writer-column-layout", by)
        self.assertEqual(by["tle-writer-column-layout"].status, "pass", by["tle-writer-column-layout"].detail)

        class Misaligned(Reference):
            def write_tle(self, rec):
                l0, l1, l2 = Reference.write_tle(self, rec)
                l2 = l2[:8] + l2[8:16].strip().ljust(8) + l2[16:68]
                return l0, l1, with_checksum(l2)

        r = Runner(Misaligned(), root=ROOT).run(case_ids=[CASE])[0]
        by = {i.check: i for i in r.items}
        self.assertEqual(by["tle-writer-column-layout"].status, "fail")
        self.assertIn("columns 9-16", by["tle-writer-column-layout"].detail)
        # the checks that used to be the whole story still pass on these lines: the layout item is what catches it
        for c in ("tle-checksums-valid", "tle-writer-catalog-field", "tle-writer-round-trip"):
            self.assertEqual(by[c].status, "pass", (c, by[c].detail))
        self.assertEqual(r.status, "fail")

    def test_check_tle_cli_shows_the_layout_failure(self):
        rc, out, rep = self.cli(self.write("shifted.tle", f"{self.l0}\n{self.l1}\n{self.misaligned_line2()}\n"))
        self.assertEqual(rc, 1)
        self.assertIn("columns 9-16", out)


if __name__ == "__main__":
    unittest.main()
