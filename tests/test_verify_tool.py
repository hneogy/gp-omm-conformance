"""Comparison logic of tools/verify_against_spacetrack.py, exercised only with the repository's own
derived lines (as both sides). No Space-Track output is fabricated and no network is touched."""
import glob
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import verify_against_spacetrack as V  # noqa: E402


def first_derived():
    p = sorted(glob.glob(os.path.join(ROOT, "derived", "alpha5-tle", "*.tle")))[0]
    return V.parse_tle_pairs(open(p, encoding="utf-8").read())[0]


class DecodeTests(unittest.TestCase):
    def test_strict_alpha5(self):
        self.assertEqual(V.decode_alpha5("A0000"), 100000)
        self.assertEqual(V.decode_alpha5("T0449"), 270449)
        self.assertEqual(V.decode_alpha5("Z9999"), 339999)
        self.assertEqual(V.decode_alpha5("25544"), 25544)
        for bad in ("I0000", "O0000", "a0000", "A000", " A000", "AA000"):
            with self.assertRaises(ValueError):
                V.decode_alpha5(bad)


class CompareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.idx = V.load_derived()
        cls.l1, cls.l2 = first_derived()
        cls.field = cls.l1[2:7]
        cls.rng = (V.decode_alpha5(cls.field), V.decode_alpha5(cls.field))

    def test_identical_lines_are_exact(self):
        r = V.compare_record(self.l1, self.l2, self.idx, self.rng)
        self.assertEqual(r["verdict"], "EXACT")
        self.assertTrue(r["line2_field_matches"] and r["in_range"])

    def test_single_column_change_is_located(self):
        # flip the exponent sign of the second-derivative field (column 51) on line 1
        l1 = self.l1[:50] + ("-" if self.l1[50] == "+" else "+") + self.l1[51:]
        r = V.compare_record(l1, self.l2, self.idx, self.rng)
        self.assertEqual(r["verdict"], "same field and epoch; lines differ")
        self.assertEqual(r["columns_l1"], [51])
        self.assertEqual(r["columns_l2"], [])

    def test_different_epoch_reports_encoding_and_designator(self):
        l1 = self.l1[:18] + ("27" if self.l1[18:20] != "27" else "28") + self.l1[20:]
        r = V.compare_record(l1, self.l2, self.idx, self.rng)
        self.assertTrue(r["verdict"].startswith("encoding field matches"))
        self.assertTrue(r["intl_designator_matches"])
        self.assertTrue(r["inclination_within_0_05"])
        self.assertEqual(r["columns_l1"], [])

    def test_line2_field_mismatch_is_flagged(self):
        l2 = self.l2[:2] + "Z9999" + self.l2[7:]
        r = V.compare_record(self.l1, l2, self.idx, self.rng)
        self.assertFalse(r["line2_field_matches"])
        self.assertEqual(V.summarize([r])["line2_field_mismatch"], 1)

    def test_unknown_field_and_out_of_range(self):
        l1 = self.l1[:2] + "Z9998" + self.l1[7:]
        l2 = self.l2[:2] + "Z9998" + self.l2[7:]
        r = V.compare_record(l1, l2, self.idx, (100000, 100020))
        self.assertTrue(r["verdict"].startswith("field decodes correctly; no derived line"))
        self.assertFalse(r["in_range"])
        self.assertEqual(V.summarize([r])["out_of_range"], 1)

    def test_invalid_field(self):
        l1 = self.l1[:2] + "I0000" + self.l1[7:]
        r = V.compare_record(l1, self.l2, self.idx, self.rng)
        self.assertTrue(r["invalid"])
        self.assertEqual(V.summarize([r])["invalid_field"], 1)

    def test_output_never_contains_element_values(self):
        r = V.compare_record(self.l1, self.l2, self.idx, self.rng)
        text = V.format_result("q1", r)
        for piece in (self.l1[18:32], self.l1[33:43], self.l2[8:16], self.l2[52:63]):
            self.assertNotIn(piece.strip(), text)

    def test_output_dir_guard(self):
        self.assertFalse(V.output_dir_ok(os.path.join(ROOT, "spacetrack-verify"), ROOT))
        self.assertFalse(V.output_dir_ok(ROOT, ROOT))
        self.assertTrue(V.output_dir_ok(os.path.expanduser("~/spacetrack-verify"), ROOT) or os.path.realpath(os.path.expanduser("~")).startswith(os.path.realpath(ROOT)))


if __name__ == "__main__":
    unittest.main()
