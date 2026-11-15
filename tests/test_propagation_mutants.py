# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The propagation tier's mutant adapters (D-414): the correct base passes the shipped propagation cases, and each of
sixteen wrong propagators fails at least one of them.

Run: python -m unittest tests.test_propagation_mutants"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import propagation_mutants as PM  # noqa: E402


class TheMutants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base, cls.mutants = PM.run(ROOT)

    def test_the_base_passes_every_shipped_propagation_case(self):
        self.assertEqual(set(self.base), set(PM.CASES))
        self.assertTrue(all(s in ("pass", "pass-tolerance") for s in self.base.values()), self.base)

    def test_every_mutant_fails_a_case(self):
        for kind in PM.MUTANTS:
            with self.subTest(kind=kind):
                self.assertIn("fail", self.mutants[kind].values(), self.mutants[kind])

    def test_type_4_propagated_fails_the_type_4_case_and_only_it(self):
        self.assertEqual(self.mutants["type-4-propagated"], {"propagation-tle-omm-twins": "pass", "ephemeris-type-4-refused": "fail"})

    def test_the_wrong_answers_are_wrong(self):
        """Each physics table differs from the reference somewhere beyond the bar, so its mutant is a wrong propagator."""
        with open(os.path.join(ROOT, "vectors", "propagation-twins.json"), encoding="utf-8") as f:
            ref = {s["norad_cat_id"]: {x["t"]: x for x in s["steps"]} for s in json.load(f)["sets"]}
        _, wrong = PM.tables(ROOT)
        for kind, sets in wrong.items():
            with self.subTest(kind=kind):
                worst = max(abs(a - b) for i, steps in sets.items() for s in steps if s["error"] == 0
                            for a, b in zip(s["r"], ref[i][s["t"]]["r"]))
                self.assertGreater(worst, 1e-3)


if __name__ == "__main__":
    unittest.main()
