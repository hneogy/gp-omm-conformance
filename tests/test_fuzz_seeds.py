# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""tools/export_fuzz_seeds.py (0.9.0 item d3, D-433): one seed zip and one dictionary per format, from derived/ only,
reproducible byte for byte.

Run: python -m unittest tests.test_fuzz_seeds"""
import os
import re
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import export_fuzz_seeds as X  # noqa: E402
from gpconf.fuzz import seeds  # noqa: E402


class Seeds(unittest.TestCase):
    def test_every_shipped_input_once_in_its_formats_zip_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as d:
            done = X.export(d)
            want = {}
            for path, fmt in seeds(ROOT):
                want.setdefault(fmt, set()).add(path.replace("/", "__"))
            self.assertEqual(set(done), set(want))
            for fmt, (zpath, n, _h) in done.items():
                with self.subTest(fmt=fmt), zipfile.ZipFile(zpath) as z:
                    names = set(z.namelist())
                    self.assertEqual(names, want[fmt])
                    self.assertEqual(n, len(names))
                    self.assertTrue(all(name.startswith("derived__") for name in names))   # never a provider file
                    first = sorted(names)[0]
                    with open(os.path.join(ROOT, first.replace("__", "/")), "rb") as f:
                        self.assertEqual(z.read(first), f.read())

    def test_the_bytes_repeat(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.assertEqual({k: v[2] for k, v in X.export(a).items()}, {k: v[2] for k, v in X.export(b).items()})

    def test_the_dictionaries_are_libfuzzer_syntax(self):
        with tempfile.TemporaryDirectory() as d:
            X.export(d)
            for fmt in X.export(d):
                with self.subTest(fmt=fmt), open(os.path.join(d, f"gpconf_{fmt}.dict"), encoding="ascii") as f:
                    lines = [l.rstrip("\n") for l in f if not l.startswith("#")]
                self.assertEqual(len(lines), len(X.TOKENS[fmt]))
                for l in lines:
                    self.assertRegex(l, r'^"(?:[\x20-\x21\x23-\x5b\x5d-\x7e]|\\x[0-9A-F]{2})*"$')
        self.assertEqual(X.dict_line("a\"\r\n"), '"a\\x22\\x0D\\x0A"')


if __name__ == "__main__":
    unittest.main()
