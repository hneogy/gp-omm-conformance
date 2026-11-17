# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The type-check ratchet runs on every push and in the nightly, with one bound (D-571, the owner's ruling: the
ratchet also on push, the bound unchanged). The two copies of the step may not drift apart.

Run: python -m unittest tests.test_ratchet"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ratchet(workflow):
    with open(os.path.join(ROOT, ".github", "workflows", workflow), encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"--check-untyped-defs > mypy\.txt.*?echo \"errors: \$n \(ceiling (\d+)\)\"\s+test \"\$n\" -le (\d+)", text, re.S)
    return m and (int(m.group(1)), int(m.group(2)))


class TheRatchet(unittest.TestCase):
    def test_it_runs_on_push_and_nightly_with_one_bound(self):
        ci, nightly = ratchet("ci.yml"), ratchet("nightly.yml")
        self.assertIsNotNone(ci, "ci.yml has no ratchet step")
        self.assertIsNotNone(nightly, "nightly.yml has no ratchet step")
        self.assertEqual(ci[0], ci[1], "ci.yml's printed ceiling and its test differ")
        self.assertEqual(nightly[0], nightly[1], "nightly.yml's printed ceiling and its test differ")
        self.assertEqual(ci, nightly, "the push and nightly ratchets have different bounds")
        self.assertEqual(ci[0], 45)   # unchanged by D-571; lowering it is a separate change, raising it never


if __name__ == "__main__":
    unittest.main()
