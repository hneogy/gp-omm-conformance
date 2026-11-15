# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""D-399 (the third blind pass's 18, Phase 2 of 0.9.0): the writer case holds an input with eccentricity 0 (99998,
synthetic-derived), so a writer that leaves the field blank for 0 fails; before, none of its records had 0."""
import os
import sys
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.tle import checksum  # noqa: E402


def fix(line):
    return line[:68] + str(checksum(line))


class BlanksZero(Reference):
    """The red team's e18 (docs/handoff/redteam-2026-10-29/copy/bugged/e18_writer_zero_eccentricity.py, its logic):
    the eccentricity field left blank when the eccentricity is exactly 0 (a falsy-zero test)."""

    def write_tle(self, record):
        l0, l1, l2 = super().write_tle(record)
        if Decimal(str(record["eccentricity"])) == 0:
            l2 = fix(l2[:26] + " " * 7 + l2[33:])
        return l0, l1, l2


class ZeroBstarBlanked(Reference):
    """The twin (the red team's t18): the same falsy-zero test on BSTAR, which the case already held (seven zero BSTARs)."""

    def write_tle(self, record):
        l0, l1, l2 = super().write_tle(record)
        if Decimal(str(record.get("bstar") or 0)) == 0:
            l1 = fix(l1[:53] + " " * 8 + l1[61:])
        return l0, l1, l2


def run(p):
    from gpconf.runner import Runner
    (r,) = Runner(p, root=ROOT, fetch_hints=False).run(case_ids=["tle-writer-alpha5"])
    return r


class AZeroEccentricity(unittest.TestCase):
    def test_the_input_is_there(self):
        import json
        e = json.load(open(os.path.join(ROOT, "fixtures", "tle-writer-alpha5", "expected.json"), encoding="utf-8"))
        zero = [r for r in e["records"] if Decimal(str(r["canonical"]["eccentricity"])) == 0]
        self.assertEqual([r["norad_cat_id"] for r in zero], [99998])
        self.assertEqual(zero[0]["reference_tle_fields"]["ecc_field"], "0000000")

    def test_a_writer_that_blanks_it_fails_the_layout_naming_it(self):
        r = run(BlanksZero())
        self.assertEqual(r.status, "fail")
        (item,) = [i for i in r.items if i.check == "tle-writer-column-layout"]
        self.assertEqual(item.status, "fail")
        self.assertIn("id 99998", item.detail)
        self.assertIn("eccentricity", item.detail)
        (rt,) = [i for i in r.items if i.check == "tle-writer-round-trip"]   # the blank field is no number to read back
        self.assertEqual(rt.status, "fail")
        self.assertIn("id 99998", rt.detail)

    def test_the_reference_writes_it(self):
        self.assertEqual(run(Reference()).status, "pass")

    def test_the_twin_on_bstar_was_already_caught(self):
        self.assertEqual(run(ZeroBstarBlanked()).status, "fail")


if __name__ == "__main__":
    unittest.main()
