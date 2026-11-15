# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The readers for Vallado's two verification files and the corpus's manifest of them (D-388).

The readers are tested on text written here, so they run everywhere; the manifest is held to the private copies,
which the export and the package leave out until the owner confirms written bundling permission, so those tests skip
in a clone, an export and public CI.

Run: python -m unittest tests.test_sgp4ver"""
import hashlib
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gpconf import sgp4ver  # noqa: E402

REF = os.path.join(ROOT, "harnesses", "vallado", "reference")
MANIFEST = os.path.join(ROOT, "harnesses", "vallado", "reference-manifest.json")
# invented element lines in the file's layout (none of Vallado's text is copied into this public test)
L1 = "1 99901U 26001A   26001.50000000  .00000000  00000-0  00000-0 0  9990"
L2 = "2 99901  45.0000  90.0000 0010000  10.0000  20.0000 14.00000000    10"


def private_present():
    return all(os.path.exists(os.path.join(REF, f)) for f in ("SGP4-VER.TLE", "tcppver.out"))


class TheReaders(unittest.TestCase):
    def test_the_element_sets_and_their_runs(self):
        text = f"#   header\n#   a test set\n{L1}\n{L2}     0.00      4320.0        360\n"
        (s,) = sgp4ver.parse_ver_tle(text)
        self.assertEqual((s["catalog"], s["comment"], s["start"], s["stop"], s["step"]), (99901, "a test set", 0.0, 4320.0, 360.0))
        self.assertEqual((s["line1"], s["line2"]), (L1, L2))

    def test_a_malformed_file_is_refused(self):
        for text in (f"{L1}\n", f"{L1}\n{L2}\n", "something else\n"):
            with self.subTest(text=text[:20]):
                self.assertRaises(ValueError, sgp4ver.parse_ver_tle, text)

    def test_the_blocks(self):
        text = ("99901 xx\n       0.00000000    7000.00000000    -100.00000000      10.00000000  1.000000000  7.000000000  0.500000000\n"
                "     360.00000000   -7000.00000000     200.00000000     -20.00000000 -1.000000000 -7.000000000 -0.500000000    7000.000000\n"
                "99902 xx\n")
        b = sgp4ver.parse_tcppver(text)
        self.assertEqual([(x["catalog"], len(x["rows"])) for x in b], [(99901, 2), (99902, 0)])
        self.assertEqual(b[0]["rows"][1][0], 360.0)
        self.assertRaises(ValueError, sgp4ver.parse_tcppver, "  1.0 2.0 3.0\n")

    def test_the_schedule(self):
        self.assertEqual(sgp4ver.schedule(0.0, 720.0, 360.0), [0.0, 360.0, 720.0])
        self.assertEqual(sgp4ver.schedule(0.0, 100.0, 30.0), [0.0, 30.0, 60.0, 90.0, 100.0])   # the stop itself, once
        self.assertEqual(sgp4ver.schedule(-60.0, 0.0, 30.0), [0.0, -60.0, -30.0, 0.0])         # 0 first, then the run


@unittest.skipUnless(private_present(), "Vallado's files are private (D-388): not in a clone, an export or public CI")
class TheManifestHoldsThePrivateCopies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(MANIFEST, encoding="utf-8") as f:
            cls.m = json.load(f)
        cls.raw = {n: open(os.path.join(REF, n), "rb").read() for n in cls.m["files"]}

    def test_bytes_hashes_and_lines(self):
        for name, want in self.m["files"].items():
            b = self.raw[name]
            with self.subTest(name):
                self.assertEqual({"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest(), "lines": b.count(b"\n")}, want)

    def test_every_set_and_every_line(self):
        sets = sgp4ver.parse_ver_tle(self.raw["SGP4-VER.TLE"].decode("ascii"))
        blocks = sgp4ver.parse_tcppver(self.raw["tcppver.out"].decode("ascii"))
        self.assertEqual(len(sets), self.m["set_count"])
        self.assertEqual(len(sets), 33)
        self.assertEqual(sum(len(b["rows"]) for b in blocks) + len(blocks), 700)
        for s, b, e in zip(sets, blocks, self.m["sets"]):
            with self.subTest(catalog=s["catalog"]):
                self.assertEqual((s["catalog"], b["catalog"]), (e["catalog"], e["catalog"]))
                self.assertEqual(len(sgp4ver.schedule(s["start"], s["stop"], s["step"])), e["steps_scheduled"])
                self.assertEqual(len(b["rows"]), e["steps_printed"])
                if "error" not in e:
                    self.assertEqual(e["steps_printed"], e["steps_scheduled"])

    def test_seven_blocks_end_in_an_error(self):
        errs = [(s["catalog"], s["error"]["code"]) for s in self.m["sets"] if "error" in s]
        self.assertEqual([c for _, c in errs], [1, 1, 6, 6, 4, 3, 6])
        self.assertEqual([n for n, _ in errs], [22312, 28350, 28872, 29141, 33333, 33334, 20413])


if __name__ == "__main__":
    unittest.main()
