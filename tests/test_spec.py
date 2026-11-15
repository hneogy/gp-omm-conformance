# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""docs/SPEC.md, the gpconf specification 1.0 draft (0.9.0 item d1, D-432): its case table is the manifest's, its
statuses are the runner's, and the files it names exist.

Run: python -m unittest tests.test_spec"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf.runner import CASE_STATUSES  # noqa: E402


def spec():
    with open(os.path.join(ROOT, "docs", "SPEC.md"), encoding="utf-8") as f:
        return f.read()


class Spec(unittest.TestCase):
    def test_the_case_table_is_the_manifests(self):
        with open(os.path.join(ROOT, "manifest.json"), encoding="utf-8") as f:
            cases = json.load(f)["cases"]
        rows = {m.group(1): (m.group(2), re.findall(r"`([^`]+)`", m.group(3)))
                for m in re.finditer(r"^\| `([a-z0-9-]+)` \| ([a-z0-9-]+) \| (.*) \|$", spec().split("## 3.")[1].split("## 4.")[0], re.M)}
        want = {c["id"]: (c["kind"], [ch["id"] if isinstance(ch, dict) else ch for ch in c["checks"]]) for c in cases}
        self.assertEqual(rows, want)

    def test_the_statuses_are_the_runners(self):
        m = re.search(r"An item ends in one of (.*?)\. A case", spec(), re.S)
        self.assertEqual(re.findall(r"`([a-z-]+)`", m.group(1)), list(CASE_STATUSES) + ["info"])

    def test_the_files_it_names_exist(self):
        for rel in ("gpconf/schemas/results-1.0.schema.json", "harnesses/vallado/reference-manifest.json",
                    "vectors/propagation-twins.json", "docs/ADAPTERS.md", "docs/WRITERS.md", "manifest.json"):
            with self.subTest(file=rel):
                self.assertIn(f"`{rel}`", spec())
                self.assertTrue(os.path.exists(os.path.join(ROOT, rel)))

    def test_it_says_it_is_a_draft_and_what_is_open(self):
        text = spec()
        self.assertIn("Status: **draft**", text)
        self.assertIn("## 11. Open points in this draft", text)


if __name__ == "__main__":
    unittest.main()
