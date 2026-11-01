# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The corrupt-input case's unedited TLE file is held to its records' frozen values, as the CSV and JSON ones are
(D-342, the owner's ruling on escape 3 of D-339's reading), with its wrong-on-purpose adapters and twins.

Before: the unedited TLE file was read only to be compared with the same parser's reading of the inputs (D-175), so a
parser that dropped the corrupt record's id from it as well as from the inputs read not-exercised (D-294), and one that
read every TLE set one degree off passed; the CSV and JSON comparison files, held to their frozen values since D-299,
caught both.

Run: python -m unittest tests.adversarial.test_unedited_tle_080"""
import os
import sys
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from tests.adversarial.test_hardening import failing, run  # noqa: E402

UNEDITED_TLE = open(os.path.join(ROOT, "derived", "corrupt-input", "unedited-sets.tle"), "rb").read()


def tle_records(how, comparison_too=True):
    """The reference, with every record it reads from a TLE file (the unedited one too, or only the inputs) passed
    through how, which returns the record or None to drop it."""
    class Adapter(Reference):
        def parse(self, raw, fmt):
            out = super().parse(raw, fmt)
            if fmt != "tle" or (raw == UNEDITED_TLE and not comparison_too):
                return out
            return [r for r in (how(r) if "_refused" not in r else r for r in out) if r is not None]
    return Adapter()


def off_by_a_degree(r):
    return dict(r, inclination=str(Decimal(str(r["inclination"])) + 1))


class TheUneditedTleFileIsHeldToItsFrozenValues(unittest.TestCase):

    def items(self, result, name):
        return [i for i in result["corrupt-input"].items if (i.file or "").endswith(name)]

    def test_a_record_dropped_from_every_tle_file_fails(self):
        drop = tle_records(lambda r: None if r["norad_cat_id"] == 69999 else r)
        r = run(drop, cases=["corrupt-input"])
        self.assertEqual(failing(r), ["corrupt-input"])
        values = [i for i in self.items(r, "unedited-sets.tle") if i.check == "values"]
        self.assertEqual([i.status for i in values], ["fail"])
        self.assertIn("69999", values[0].detail)
        twin = tle_records(lambda r: None if r["norad_cat_id"] == 69999 else r, comparison_too=False)
        self.assertEqual(failing(run(twin, cases=["corrupt-input"])), ["corrupt-input"])   # dropped from the inputs only

    def test_every_tle_set_read_a_degree_off_fails(self):
        r = run(tle_records(off_by_a_degree), cases=["corrupt-input"])
        self.assertEqual(failing(r), ["corrupt-input"])
        values = [i for i in self.items(r, "unedited-sets.tle") if i.check == "values"]
        self.assertEqual([i.status for i in values], ["fail"])
        self.assertIn("inclination", values[0].detail)

    def test_the_twin_a_correct_parser_passes_and_the_file_is_graded(self):
        r = run(Reference(), cases=["corrupt-input"])
        self.assertEqual(failing(r), [])
        self.assertEqual([i.status for i in self.items(r, "unedited-sets.tle") if i.check == "values"], ["pass"])


if __name__ == "__main__":
    unittest.main()
