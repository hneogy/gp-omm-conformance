# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The second blind review of the 0.8.0 candidate (D-370; a fresh session with the wheel of e42e9fd alone, the owner's
ruling of 2026-10-28): the grader findings fixed in 0.8.0, each with a wrong-on-purpose adapter or input and its twin.

- F1: check-tle --against said [pass], and exited 0, for wrong values written under an id the source holds more than
  once, whose round trip D-369 does not make; such a record now reads [not compared] and the run exits 3.
- F3: a reader that hands a day-of-year epoch back unconverted passed kvn-syntax-variants when it changed the text's Z
  to +00:00, or added a zero to its fraction (D-306 caught only the text as it was).
- F5: an Alpha-5 decoder reading the four digits through int() passed: a sign, an underscore or non-ASCII digits.
- F6: a reader one second late, 13:13:60 for 13:13:59, passed: the runner read second 60 as 59 on any date.
- F9 and F11, which do not reopen the gate: --json to a path that cannot be written; the ASCII check held.

The files are the corpus's own derived files and vectors (no provider's bytes, so the module runs in the public
export). Run: python -m unittest tests.adversarial.test_blind_review2_080"""
import contextlib
import io
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf import tle as T  # noqa: E402
from gpconf.__main__ import main as gpconf_main  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import Runner, unparsed_epoch  # noqa: E402


def case(parser, case_id):
    return Runner(parser, root=ROOT, fetch_hints=False).run(case_ids=[case_id])[0]


class HistoryNotCompared(unittest.TestCase):
    """F1: wrong values written under an id the source holds twice."""

    def test_wrong_values_under_a_twice_held_id_are_not_said_to_pass(self):
        with open(os.path.join(ROOT, "derived", "alpha5-tle", "alpha5-A-100000-saramago-first.tle"), encoding="utf-8") as f:
            n, l1, l2 = f.read().splitlines()[:3]
        fix = lambda line: line[:68] + str(T.checksum(line[:68]))   # noqa: E731
        l1b = fix(l1[:18] + "26201.50000000" + l1[32:])               # a second element set of the same id
        bad = fix(l2[:8] + " 12.3456" + l2[16:])                       # inclination 97.4593 written as 12.3456
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)

        def write(name, lines):
            path = os.path.join(tmp, name)
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            return path
        src = write("src.tle", [n, l1, l2, n, l1b, l2])
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = gpconf_main(["check-tle", write("bad.tle", [n, l1, bad, n, l1b, bad]), "--against", src])
        out = out.getvalue()
        self.assertEqual(code, 3, out)
        self.assertNotIn("[pass] line", out)
        self.assertIn("2 records: 0 pass, 0 fail, 2 not compared", out)
        # its twin, the same wrong line under an id the source holds once: compared, and a failure
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = gpconf_main(["check-tle", write("bad1.tle", [n, l1, bad]), "--against", write("src1.tle", [n, l1, l2])])
        self.assertEqual(code, 1, out.getvalue())
        self.assertIn("round trip: inclination", out.getvalue())


DOY_EPOCH = re.compile(rb"EPOCH\s*=\s*(\d{4}-\d{3}T[0-9:.]+Z?)")


class DoyHandedBack(Reference):
    """F3: a KVN reader that gives up on a day-of-year epoch and hands its text back, changed by `how`."""

    def __init__(self, how):
        self.how = how

    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        texts = [m.group(1).decode() for m in DOY_EPOCH.finditer(raw)] if fmt == "kvn" else []
        recs = [r for r in out if isinstance(r, dict) and "_refused" not in r]
        if len(texts) == len(recs):
            for r, t in zip(recs, texts):
                r["epoch"] = self.how(t)
        return out


class DayOfYearHandedBack(unittest.TestCase):

    def test_the_text_with_its_z_made_an_offset_or_a_zero_added_fails(self):
        for name, how in (("+00:00", lambda t: t[:-1] + "+00:00" if t.endswith("Z") else t + "+00:00"),
                          ("a zero added", lambda t: t[:-1] + "0Z" if t.endswith("Z") else t + "0")):
            with self.subTest(name):
                got = case(DoyHandedBack(how), "kvn-syntax-variants")
                self.assertEqual(got.status, "fail")
                self.assertTrue(any("D-306" in (i.detail or "") for i in got.items if i.status == "fail"),
                                [i.detail for i in got.items if i.status == "fail"][:2])

    def test_the_reference_passes_and_a_calendar_epoch_is_never_the_input_text(self):
        """The twins: the reference converts the epoch; a calendar epoch, or a day-of-year epoch the input does not
        hold (another instant), is not called the input's own text."""
        self.assertEqual(case(Reference(), "kvn-syntax-variants").status, "pass")
        raw = "EPOCH = 1998-324T06:49:59.999808Z\n"
        self.assertFalse(unparsed_epoch("1998-11-20T06:49:59.999808", raw))
        self.assertFalse(unparsed_epoch("1998-324T06:49:59.999809Z", raw))
        self.assertFalse(unparsed_epoch("1998-324T06:49:59.999808+01:00", raw))
        self.assertTrue(unparsed_epoch("1998-324T06:49:59.99980800+00:00", raw))


class IntDigits(Reference):
    """F5: an Alpha-5 decoder that checks the letter and the length, then reads the four digits with int()."""

    def alpha5_decode(self, field):
        if len(field) != 5:
            raise ValueError(field)
        if "0" <= field[0] <= "9":
            return int(field)
        letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
        if field[0] not in letters:
            raise ValueError(field)
        return (letters.index(field[0]) + 10) * 10000 + int(field[1:])


class Alpha5Digits(unittest.TestCase):

    def test_a_decoder_reading_the_digits_with_int_fails_naming_each_field(self):
        (got,) = [i for i in case(IntDigits(), "alpha5-encoding-vectors").items if i.check == "alpha5-decode"]
        self.assertEqual(got.status, "fail", got.detail)
        for shown in ("'A+123' accepted as 100123", "'A1_23' accepted as 100123", "'A１２３４' accepted as 101234"):
            self.assertIn(shown, got.detail)
        self.assertNotIn("A0000\\n", got.detail)   # the line-break shape is 0.8.1's (the owner's ruling, 2026-10-28)

    def test_the_reference_rejects_each(self):
        (got,) = [i for i in case(Reference(), "alpha5-encoding-vectors").items if i.check == "alpha5-decode"]
        self.assertEqual(got.status, "pass", got.detail)


class OneSecondLate(Reference):
    """F6: a reader whose epoch on second 59 comes back as second 60, an instant one second later."""

    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        for r in out:
            if isinstance(r, dict) and isinstance(r.get("epoch"), str):
                r["epoch"] = re.sub(r":59\.", ":60.", r["epoch"])
        return out


class SecondSixty(unittest.TestCase):

    def test_a_reader_one_second_late_fails(self):
        got = case(OneSecondLate(), "alpha5-tle-derived")
        self.assertEqual(got.status, "fail")
        self.assertTrue(any("second 60 outside a leap second" in (i.detail or "") for i in got.items if i.status == "fail"))

    def test_a_leap_second_is_still_read_and_the_vector_still_passes(self):
        """The twins: second 60 at 23:59:60 UTC on 30 June or 31 December, in either form and through an offset."""
        self.assertEqual(T.iso_epoch("2016-12-31T23:59:60"), "2016-12-31T23:59:59.000000")
        self.assertEqual(T.iso_epoch("2016-366T23:59:60Z"), "2016-12-31T23:59:59.000000")
        self.assertEqual(T.iso_epoch("2015-06-30T23:59:60.5"), "2015-06-30T23:59:59.500000")
        self.assertEqual(T.iso_epoch("2016-12-31T18:59:60-05:00"), "2016-12-31T23:59:59.000000")
        for wrong in ("2026-09-20T13:13:60.479104", "2016-12-31T23:58:60", "2016-12-30T23:59:60", "2016-12-31T23:59:60+01:00"):
            with self.subTest(wrong), self.assertRaises(ValueError):
                T.iso_epoch(wrong)
        (got,) = [i for i in case(Reference(), "alpha5-encoding-vectors").items if i.check == "ccsds-epoch-strings"]
        self.assertEqual(got.status, "pass", got.detail)


class JsonPath(unittest.TestCase):
    """F9: --json to a path that cannot be written printed the whole report, then ended in a traceback with exit 1 (a
    failure, to a script). It is now refused before anything runs, exit 2, in one line."""

    def gpconf(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = gpconf_main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_an_unwritable_path_is_refused_before_anything_runs(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        sets = os.path.join(ROOT, "derived", "corrupt-input", "unedited-sets.tle")
        for argv, why in ((["run", "--preset", "reference", "--case", "alpha5-encoding-vectors", "--root", ROOT, "--json",
                            os.path.join(tmp, "no", "x.json")], "does not exist"),
                          (["check-tle", sets, "--json", tmp], "is a folder")):
            with self.subTest(argv[0]):
                code, out, err = self.gpconf(*argv)
                self.assertEqual(code, 2, err)
                self.assertIn(why, err)
                self.assertIn("nothing was run", err)
                self.assertEqual(out, "")
                self.assertNotIn("Traceback", err)

    def test_a_writable_path_is_written(self):
        """The twin."""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        js = os.path.join(tmp, "x.json")
        code, _, err = self.gpconf("check-tle", os.path.join(ROOT, "derived", "corrupt-input", "unedited-sets.tle"), "--json", js)
        self.assertEqual(code, 0, err)
        self.assertTrue(os.path.getsize(js) > 0)


class AsciiBeforeTheCatalogField(unittest.TestCase):
    """F11 (information): writer.strict_catalog_field reads digits with str.isdigit, which other scripts' digits pass;
    the ASCII check of the line before it is what fails such a record. Held here, so that a change cannot drop it."""

    def test_a_catalog_field_in_full_width_digits_fails_the_record(self):
        from gpconf import writer as W
        with open(os.path.join(ROOT, "derived", "corrupt-input", "unedited-sets.tle"), encoding="utf-8") as f:
            _, l1, l2 = f.read().splitlines()[:3]
        wide = "\uff12\uff15\uff15\uff14\uff14"
        r = W.check_record(None, l1[:2] + wide + l1[7:], l2[:2] + wide + l2[7:])
        self.assertEqual(r["status"], "fail")
        self.assertIn("line 1 column 3 holds '２', which is not ASCII", r["problems"])


class ReadingMutants(unittest.TestCase):
    """D-370's reading: the mutants of its lines that lived, each held here."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(lambda: (os.chmod(self.tmp, 0o755), shutil.rmtree(self.tmp)))
        with open(os.path.join(ROOT, "derived", "alpha5-tle", "alpha5-A-100000-saramago-first.tle"), encoding="utf-8") as f:
            self.n, self.l1, self.l2 = f.read().splitlines()[:3]

    def write(self, name, lines):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return path

    def gpconf(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = gpconf_main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_m3_a_not_compared_record_with_a_format_problem_fails(self):
        l1b = self.l1[:18] + "26201.50000000" + self.l1[32:]
        l1b = l1b[:68] + str(T.checksum(l1b[:68]))
        src = self.write("src.tle", [self.n, self.l1, self.l2, self.n, l1b, self.l2])
        bad = self.l2[:68] + str((int(self.l2[68]) + 1) % 10)   # a wrong checksum
        code, out, _ = self.gpconf("check-tle", self.write("b.tle", [self.n, self.l1, bad, self.n, l1b, self.l2]), "--against", src)
        self.assertEqual(code, 1, out)
        self.assertIn("1 fail", out)

    def test_m12_m13_the_write_checks(self):
        from gpconf.__main__ import json_target_problem
        ro = os.path.join(self.tmp, "ro")
        os.mkdir(ro)
        existing = os.path.join(ro, "x.json")
        open(existing, "w").close()
        os.chmod(ro, 0o555)
        self.assertEqual(json_target_problem(os.path.join(ro, "new.json")), "cannot be written")   # a new file, a folder read-only
        self.assertIsNone(json_target_problem(existing))                                            # a writable file in it may be written
        os.chmod(ro, 0o755)
        os.chmod(existing, 0o444)
        self.assertEqual(json_target_problem(existing), "cannot be written")
        os.chmod(existing, 0o644)

    def test_m16_m17_a_write_that_fails_after_the_check_says_so(self):
        import gpconf.__main__ as cli
        saved = cli.json_target_problem
        cli.json_target_problem = lambda path: None
        try:
            code, out, err = self.gpconf("run", "--preset", "reference", "--case", "alpha5-encoding-vectors", "--root", ROOT,
                                         "--json", os.path.join(self.tmp, "no", "x.json"))
        finally:
            cli.json_target_problem = saved
        self.assertEqual(code, 2, err)
        self.assertIn("the report was not written", err)

    def test_m21_m23_the_input_text_found_verbatim_and_a_second_epoch(self):
        raw = "EPOCH = 1998-324T06:49:59.999808Z\nEPOCH = 1998-325T00:00:00Z\n26263.52959654\n"
        self.assertTrue(unparsed_epoch("26263.52959654", raw))             # not day-of-year, found verbatim (D-306)
        self.assertTrue(unparsed_epoch("1998-325T00:00:00.000+00:00", raw))  # the second epoch of the input, changed

    def test_m30_a_fraction_that_rounds_over_the_leap_second(self):
        self.assertEqual(T.iso_epoch("2016-12-31T23:59:60.9999996"), "2017-01-01T00:00:00.000000")

    def test_m41_the_case_holds_the_vectors_file_as_it_is(self):
        import json
        with open(os.path.join(ROOT, "vectors", "alpha5.json"), encoding="utf-8") as f:
            vectors = json.load(f)
        with open(os.path.join(ROOT, "fixtures", "alpha5-encoding-vectors", "expected.json"), encoding="utf-8") as f:
            held = json.load(f)["case_specific"]["vectors/alpha5.json"]
        self.assertEqual(held["decode_invalid"], vectors["decode_invalid"])


if __name__ == "__main__":
    unittest.main()
