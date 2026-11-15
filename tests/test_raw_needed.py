# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""D-408: the raw-file guard skips only in the public export; in the private repository a missing raw file fails."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tests.raw_needed import MARKER, in_export, needs_raw  # noqa: E402

RAW = os.path.join("fixtures", "baseline-iss-five-formats", "raw")


def outcome(root, present):
    """Run one guarded test that opens RAW/iss.json under root; return (errors, skipped, passed)."""
    if present:
        os.makedirs(os.path.join(root, RAW))
        with open(os.path.join(root, RAW, "iss.json"), "w", encoding="utf-8") as f:
            f.write("[]")

    class Guarded(unittest.TestCase):
        @needs_raw(RAW, root=root)
        def test_reads_raw(self):
            with open(os.path.join(root, RAW, "iss.json"), encoding="utf-8") as f:
                f.read()

    result = unittest.TestResult()
    unittest.defaultTestLoader.loadTestsFromTestCase(Guarded).run(result)
    return len(result.errors) + len(result.failures), len(result.skipped), result.wasSuccessful() and not result.skipped


class TheGuard(unittest.TestCase):
    def test_in_the_private_repository_a_missing_raw_file_fails_not_skips(self):
        with tempfile.TemporaryDirectory() as root:   # no marker: the private repository's shape
            self.assertEqual(outcome(root, present=False), (1, 0, False))

    def test_in_the_export_a_missing_raw_file_skips(self):
        with tempfile.TemporaryDirectory() as root:
            open(os.path.join(root, MARKER), "w").close()
            self.assertEqual(outcome(root, present=False), (0, 1, False))

    def test_in_the_export_a_present_raw_file_runs(self):
        with tempfile.TemporaryDirectory() as root:
            open(os.path.join(root, MARKER), "w").close()
            self.assertEqual(outcome(root, present=True), (0, 0, True))

    def test_in_the_private_repository_there_is_no_marker_and_the_raw_files_are_present(self):
        """Known by docs/handoff, which the export never carries (not by the marker, which a stray copy could forge):
        here EXPORT-MANIFEST.txt must be absent, so the guarded tests cannot skip, and their raw files present."""
        if not os.path.isdir(os.path.join(ROOT, "docs", "handoff")):
            self.skipTest("not the private repository (no docs/handoff)")
        self.assertFalse(os.path.exists(os.path.join(ROOT, MARKER)),
                         MARKER + " in the private repository would make the raw-file tests skip (D-408)")
        self.assertFalse(in_export())
        for name in ("iss.json", "iss.tle"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, RAW, name)), name)


if __name__ == "__main__":
    unittest.main()
