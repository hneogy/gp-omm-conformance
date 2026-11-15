# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Tests the owner asked for from part 1b of the 0.9.0 survivor triage (D-527): day 366 of 2020 in both epoch
readers, a byte-order-marked TLE file holding no record, and the command timeout ADAPTERS.md states. Mutant numbers
are those in docs/handoff/mutation-survivors-0.9.0-triage.md; each test passes on the code and fails under its
mutant.

Run: python -m unittest tests.test_triage_090_1b"""
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import reference as ref  # noqa: E402
from gpconf import tle  # noqa: E402
from gpconf import writer as W  # noqa: E402
from gpconf.__main__ import main as gpconf_main  # noqa: E402
from gpconf.runner import CommandParser  # noqa: E402
from tests.test_check_tle_robustness import record, rendered  # noqa: E402


class DayOfYear2020(unittest.TestCase):
    """2020 is a leap year divisible by 101, so a year test written with 101 for 100 makes it a common year and
    refuses real element sets of 31 December 2020. The tests so far used 2024, 2028 and 2000, which no such slip
    reaches."""

    def test_the_tle_epoch_reader_reads_day_366_of_2020(self):
        """Kills 2120 (reference.tle_epoch_to_iso: year % 101 for year % 100)."""
        self.assertTrue(ref.tle_epoch_to_iso("20366.00000000").startswith("2020-12-31T00:00:00"))
        self.assertTrue(ref.tle_epoch_to_iso("20366.50000000").startswith("2020-12-31T12:00:00"))

    def test_the_tle_epoch_reader_refuses_day_366_of_a_common_year_and_367_of_2020(self):
        """Kills 2125 (367 days in a leap year) and holds the common-year bound."""
        for field in ("21366.00000000", "23366.00000000", "20367.00000000"):
            with self.subTest(field):
                with self.assertRaises(ValueError):
                    ref.tle_epoch_to_iso(field)

    def test_the_iso_epoch_reader_reads_day_366_of_2020(self):
        """Kills 1964 (tle.iso_epoch: year % 101 for year % 100)."""
        self.assertEqual(tle.iso_epoch("2020-366T00:00:00"), "2020-12-31T00:00:00.000000")

    def test_the_iso_epoch_reader_refuses_day_366_of_a_common_year_and_367_of_2020(self):
        """Kills 1973 (367 days in a leap year) and 1974 (366 in a common year)."""
        for text in ("2021-366T00:00:00", "2020-367T00:00:00"):
            with self.subTest(text):
                with self.assertRaises(ValueError):
                    tle.iso_epoch(text)


class ABomFileWithNoRecord(unittest.TestCase):
    """check-tle reports a byte-order mark on line 1 when the file holds no whole record, through a path no test
    reached before; a mutant reading the file's second line there raised IndexError on a one-line file."""

    BOM_WORDS = "byte-order mark"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.l0, self.l1, self.l2 = rendered(record())

    def tearDown(self):
        self.tmp.cleanup()

    def bom_entries(self, res):
        return [r for r in res if any(self.BOM_WORDS in p for p in r["problems"])]

    def test_a_bom_and_one_line_1_report_the_bom_on_line_1(self):
        """Kills 1737 (the BOM entry on line 2) and 1738 (lines[1] in place of lines[0]: IndexError here)."""
        res = W.check_file("﻿" + self.l1 + "\n")
        bom = self.bom_entries(res)
        self.assertEqual(len(bom), 1, res)
        self.assertEqual(bom[0]["line_number"], 1)
        self.assertEqual(bom[0]["status"], "fail")
        self.assertEqual(bom[0]["catalog_field"], self.l1[2:7])

    def test_a_bom_and_a_name_line_alone_do_not_crash(self):
        """The same path with no element line at all (1738 raises IndexError here too)."""
        res = W.check_file("﻿" + self.l0 + "\n")
        bom = self.bom_entries(res)
        self.assertEqual(len(bom), 1, res)
        self.assertEqual(bom[0]["line_number"], 1)

    def test_check_tle_on_such_a_file_exits_1_and_names_the_bom(self):
        path = os.path.join(self.tmp.name, "bom-orphan.tle")
        with open(path, "wb") as f:
            f.write(("﻿" + self.l1 + "\n").encode("utf-8"))
        report = os.path.join(self.tmp.name, "report.json")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = gpconf_main(["check-tle", path, "--json", report])
        self.assertEqual(rc, 1)
        self.assertIn("BOM", out.getvalue())
        with open(report, encoding="utf-8") as f:
            recs = json.load(f)["files"][0]["records"]
        self.assertTrue(any(r["line_number"] == 1 and any(self.BOM_WORDS in p for p in r["problems"]) for r in recs), recs)


class TheCommandTimeout(unittest.TestCase):
    """docs/ADAPTERS.md tells a harness author that a command has 120 seconds a call; the default holds to it (1446).
    Test-only, the owner's ruling on 1b."""

    def test_a_command_parser_gives_a_command_120_seconds(self):
        self.assertEqual(CommandParser("x").timeout, 120)

    def test_adapters_md_states_120_seconds(self):
        with open(os.path.join(ROOT, "docs", "ADAPTERS.md"), encoding="utf-8") as f:
            text = f.read()
        self.assertRegex(text, r"still running after 120 seconds")
        self.assertNotRegex(text, r"after (?!120 )\d+ seconds")


if __name__ == "__main__":
    unittest.main()
