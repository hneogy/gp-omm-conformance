# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""A TLE reader whose letter table swaps two letters (D-372; found by D-371's reading, the owner's ruling of 2026-10-28).

The synthetic-letters sets carried one record's elements under every catalog number, and tle-catalog-field-decodes
compares the ids returned with those expected as a set: a reader that read every V set as a W set and every W set as
a V set returned the right ids, each with the right values, and passed every case that needs no provider data. Each
set now has its own mean anomaly (tools/derive_alpha5.py), so a record read under another set's id fails on its
values. The reader's decode hook is the reference's: the parse path is what is wrong.

On the cases that need no provider data, so it runs in a clone, an export and public CI.
Run: python -m unittest tests.adversarial.test_letter_swap_080"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf.adapters.reference import Parser as Reference, tle_sets  # noqa: E402
from gpconf.runner import Runner  # noqa: E402

NO_DATA = ["alpha5-encoding-vectors", "alpha5-tle-derived", "kvn-syntax-variants", "tle-writer-alpha5", "corrupt-input"]
ALPHA5 = "ABCDEFGHJKLMNPQRSTUVWXYZ"   # A = 10 ... Z = 33, I and O skipped


class SwappingReader(Reference):
    """The reference adapter, except that its TLE reader decodes the catalog field with its own letter table, in which
    the letters `swap` change places (none: the table is right, the twin)."""
    swap = ""

    def decode(self, field):
        c = field[0]
        if c.isdigit():
            return int(field)
        if self.swap and c in self.swap:
            c = self.swap[1] if c == self.swap[0] else self.swap[0]
        return (ALPHA5.index(c) + 10) * 10000 + int(field[1:])

    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        if fmt in ("tle", "2le"):
            sets = tle_sets(raw.decode("utf-8"))   # the same sets, in the same order, as the reference read them
            assert len(sets) == len(out)
            for d, s in zip(out, sets):
                if "_refused" not in d:
                    d["norad_cat_id"] = self.decode(s["tle"]["catalog_field"])
        return out


class SwapVW(SwappingReader):
    swap = "VW"


class SwapBC(SwappingReader):
    swap = "BC"


class LetterSwap(unittest.TestCase):

    def setUp(self):
        self.empty = tempfile.mkdtemp(prefix="gpconf-letter-swap-")
        self.addCleanup(os.rmdir, self.empty)

    def run_cases(self, parser):
        return {r.case_id: r for r in Runner(parser, root=ROOT, data=self.empty, fetch_hints=False).run(case_ids=NO_DATA)}

    def test_a_reader_swapping_two_letters_fails_on_values(self):
        for parser in (SwapVW(), SwapBC()):
            with self.subTest(swap=parser.swap):
                got = self.run_cases(parser)
                self.assertEqual(got["alpha5-tle-derived"].status, "fail")
                self.assertEqual(got["alpha5-encoding-vectors"].status, "pass")   # the hook is right: the reader fails
                details = [i.detail for i in got["alpha5-tle-derived"].items if i.status == "fail"]
                self.assertTrue(any("mean_anomaly" in d for d in details), details[:3])

    def test_the_twin_with_its_table_right_passes(self):
        got = self.run_cases(SwappingReader())
        self.assertEqual(sorted(c for c, r in got.items() if r.status == "fail"), [])

    def test_each_synthetic_set_has_its_own_mean_anomaly(self):
        with open(os.path.join(ROOT, "derived", "alpha5-tle", "alpha5-synthetic-letters.tle"), "rb") as f:
            recs = Reference().parse(f.read(), "tle")
        self.assertEqual(len({str(r["mean_anomaly"]) for r in recs}), len(recs))
        from decimal import Decimal
        self.assertTrue(all(0 <= Decimal(str(r["mean_anomaly"])) < 360 for r in recs))   # D-372's reading: an angle, modulo 360


if __name__ == "__main__":
    unittest.main()
