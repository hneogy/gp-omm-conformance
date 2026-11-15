# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Tests that pin three survivors of the 0.8.0 mutation run (the 0.8.1 list's items 10, 11 and 12, Phase 2 of 0.9.0):
each passes on the code and fails under its mutant."""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import writer as W  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.gates import snapshot_facts  # noqa: E402


class LinesWithDifferentFields(Reference):
    """Writes each record correctly, then puts line 1's catalog field into line 2 as 12345 (checksum recomputed)."""

    def write_tle(self, record):
        l0, l1, l2 = W.normalise_lines(Reference.write_tle(self, record))
        body = l2[:2] + "12345" + l2[7:68]
        l2 = body + str(sum(int(c) if c.isdigit() else c == "-" for c in body) % 10)
        return [x for x in (l0, l1, l2) if x is not None]


class Item10TheCatalogFieldItemReadsBothLines(unittest.TestCase):
    def test_the_check_itself(self):
        l1 = "1 25544U 98067A   26189.79090935  .00012345  00000+0  21739-3 0  9993"
        l2 = "2 12345  51.6400 208.9163 0006317  69.9862  25.2906 15.50000000123456"
        ok, detail = W.check_catalog_field(l1, l2, 25544)
        self.assertFalse(ok)
        self.assertIn("differs from line 2 field '12345'", detail)

    def test_a_writer_whose_lines_differ_fails_the_item(self):
        from gpconf.runner import Runner
        (r,) = Runner(LinesWithDifferentFields(), root=ROOT, fetch_hints=False).run(case_ids=["tle-writer-alpha5"])
        (item,) = [i for i in r.items if i.check == "tle-writer-catalog-field"]
        self.assertEqual(item.status, "fail")
        self.assertIn("differs from line 2 field '12345'", item.detail)


class Item11TheErrorTextForALetterAndANonDigitTail(unittest.TestCase):
    def test_a12b3(self):
        with self.assertRaises(ValueError) as e:
            W.strict_catalog_field("A12B3")
        self.assertEqual(str(e.exception), "catalog field 'A12B3' is neither five digits nor Alpha-5")


class Item12TheHeadlineLettersAtA0000(unittest.TestCase):
    def test_100000_alone_gives_a(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "fixtures", "c"))
            with open(os.path.join(d, "fixtures", "c", "expected.json"), "w", encoding="utf-8") as f:
                json.dump({"records": [{"norad_cat_id": 25544}, {"norad_cat_id": 100000}], "sources": {}}, f)
            facts = snapshot_facts(d, {"snapshot_from": {"case": "c", "source": "s"}})
        self.assertEqual(facts["alpha5_letters"], ["A"])
        self.assertEqual((facts["id_min"], facts["id_max"], facts["count"]), (25544, 100000, 2))


if __name__ == "__main__":
    unittest.main()
