# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""D-468: the suite's wall-clock limits widen under a tracer and with GPCONF_TIME_SCALE, never narrow, and every limit in
the suite goes through them."""
import os
import re
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tests import timebudget as T  # noqa: E402


class Budget(unittest.TestCase):
    def untraced(self):
        return mock.patch.object(T, "traced", lambda: False)

    def test_an_ordinary_run_keeps_the_measured_bound(self):
        with self.untraced(), mock.patch.dict(os.environ, {"GPCONF_TIME_SCALE": ""}):
            self.assertEqual(T.budget(3.0), 3.0)

    def test_a_traced_run_gets_four_times_the_bound(self):
        with mock.patch.object(T, "traced", lambda: True), mock.patch.dict(os.environ, {"GPCONF_TIME_SCALE": ""}):
            self.assertEqual(T.budget(3.0), 12.0)

    def test_the_scale_multiplies_and_is_never_below_one(self):
        with self.untraced():
            for raw, want in (("2", 6.0), ("1.5", 4.5), ("0.1", 3.0), ("-4", 3.0), ("nan", 3.0), ("x", 3.0), ("1", 3.0)):
                with mock.patch.dict(os.environ, {"GPCONF_TIME_SCALE": raw}):
                    self.assertEqual(T.budget(3.0), want, raw)

    def test_coverage_counts_as_a_tracer(self):
        with mock.patch.object(sys, "gettrace", lambda: None), mock.patch.dict(sys.modules, {"coverage": object()}):
            self.assertTrue(T.traced())

    def test_a_hang_still_fails_at_the_nightlys_settings(self):
        # The nightly's widest setting (GPCONF_TIME_SCALE 2, under coverage) multiplies a bound by 8, no more. The hangs
        # these limits were written for took minutes against bounds of seconds (a 3 s bound: minutes for 12,000 sets),
        # and a work that takes ten times its bound fails at every bound in the suite; the 300 s bound guards an answer
        # that never ends, which fails any finite limit.
        with mock.patch.object(T, "traced", lambda: True), mock.patch.dict(os.environ, {"GPCONF_TIME_SCALE": "2"}):
            self.assertEqual(T.scale(), 8.0)
            for bound in (1, 2, 3, 5, 10, 20, 30, 60, 300):
                hang = 10 * bound
                self.assertFalse(hang < T.budget(bound), bound)   # assertLess(hang, budget) would fail: the hang is caught

    def test_the_nightly_sets_the_scale_it_is_tested_at(self):
        with open(os.path.join(ROOT, ".github", "workflows", "nightly.yml"), encoding="utf-8") as f:
            self.assertIn('GPCONF_TIME_SCALE: "2"', f.read())

    def test_every_wall_clock_limit_in_the_suite_goes_through_the_budget(self):
        bare = []
        for base, _, files in os.walk(os.path.join(ROOT, "tests")):
            for name in files:
                if not name.endswith(".py") or name in ("timebudget.py", "test_timebudget.py"):
                    continue
                path = os.path.join(base, name)
                with open(path, encoding="utf-8") as f:
                    for n, line in enumerate(f, 1):
                        m = re.search(r"assertLess(?:Equal)?\((?:time\.\w+\(\) - \w+|elapsed|took)\s*,\s*(.*)", line)
                        if m and not m.group(1).startswith("budget("):
                            bare.append(f"{os.path.relpath(path, ROOT)}:{n}")
        self.assertEqual(bare, [])


if __name__ == "__main__":
    unittest.main()
