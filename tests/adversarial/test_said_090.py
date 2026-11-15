# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""D-402 (the third blind pass's 5, 11 and D): what a run and check-tle say where they said nothing."""
import contextlib
import io
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from gpconf.__main__ import main as gpconf_main, nine_digit_line  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import Runner  # noqa: E402
from tests.raw_needed import needs_raw  # noqa: E402

ISS_RAW = os.path.join("fixtures", "baseline-iss-five-formats", "raw")   # withheld from the export (D-408)


class NoNineDigitHook(Reference):
    def __getattribute__(self, name):
        if name == "parse_catalog_id":
            raise AttributeError(name)
        return object.__getattribute__(self, name)


def results(parser, root):
    return Runner(parser, root=ROOT, data=root, fetch_hints=False).run(case_ids=["alpha5-encoding-vectors", "nine-digit-supgp-launch-nominals"])


class TheNineDigitLine(unittest.TestCase):
    def test_said_when_no_nine_digit_id_was_read(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertIn("No nine-digit catalog number was read in this run", nine_digit_line(results(NoNineDigitHook(), empty)) or "")

    def test_the_twin_with_the_hook_says_nothing(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertIsNone(nine_digit_line(results(Reference(), empty)))


@needs_raw(ISS_RAW)
class CheckTleClosingLine(unittest.TestCase):
    def run_check(self, against_text):
        with tempfile.TemporaryDirectory() as d:
            tle = os.path.join(d, "w.tle")
            with open(os.path.join(ROOT, "fixtures", "baseline-iss-five-formats", "raw", "iss.tle"), "rb") as f, open(tle, "wb") as g:
                g.write(f.read())
            src = os.path.join(d, "src.json")
            with open(src, "w", encoding="utf-8") as f:
                f.write(against_text)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = gpconf_main(["check-tle", tle, "--against", src])
        return code, out.getvalue()

    def source(self, extra=""):
        with open(os.path.join(ROOT, "fixtures", "baseline-iss-five-formats", "raw", "iss.json"), encoding="utf-8") as f:
            text = f.read().strip()
        return text[:-1] + extra + "]"

    def test_with_a_record_without_a_catalog_number_the_line_says_whose(self):
        code, out = self.run_check(self.source(', {"OBJECT_NAME": "NO ID", "EPOCH": "2026-01-01T00:00:00"}'))
        self.assertIn("[pass] every source record with a catalog number written", out)

    def test_without_one_it_reads_as_before(self):
        code, out = self.run_check(self.source())
        self.assertIn("[pass] every source record written, none more often", out)


if __name__ == "__main__":
    unittest.main()
