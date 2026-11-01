# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""T2 (0.8.0): a counter returned as a float fails, whole or not, and its twin with an int passes (D-283, D-295; D-363).

The protocol says integers for the catalog number and the counters (docs/ADAPTERS.md, D-283), and D-295 says what an
integer is: any integer type, never a bool, a float, a string or a Decimal, whatever the value. SM-26's S5FloatIds
holds the catalog number to that; no adversarial adapter held a counter to it. Here the reference adapter, correct in
everything else, returns `rev_at_epoch` as a float: once as the same number written as a float (95679 as 95679.0), a
value that converts cleanly and is still the wrong type, and once as a number no counter can be (95679.5). Each must
fail every case whose records carry the field; the twin, the same records with the value as an int, must pass them,
and a wrong int must fail them, so that what fails the float is its type and what passes the twin is its value.

On the cases that need no provider data, so it runs in a clone, an export and public CI.
Run: python -m unittest tests.adversarial.test_counters_080"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import Runner  # noqa: E402

NO_DATA = ["alpha5-encoding-vectors", "alpha5-tle-derived", "kvn-syntax-variants", "tle-writer-alpha5", "corrupt-input"]
EMPTY = tempfile.mkdtemp(prefix="gpconf-counters-empty-")
CARRY_IT = ["alpha5-tle-derived", "corrupt-input", "kvn-syntax-variants"]   # the no-data cases whose records hold rev_at_epoch


def counter_as(make):
    """The reference adapter with rev_at_epoch handed back as make(the int it read); every other value untouched."""
    class Adapter(Reference):
        def parse(self, raw, fmt):
            out = super().parse(raw, fmt)
            for r in out:
                if "_refused" not in r and r.get("rev_at_epoch") is not None:
                    r["rev_at_epoch"] = make(r["rev_at_epoch"])
            return out
    return Adapter()


def run(parser):
    return {r.case_id: r for r in Runner(parser, root=ROOT, data=EMPTY, fetch_hints=False).run(case_ids=NO_DATA)}


def failing(results):
    return sorted(c for c, r in results.items() if r.status == "fail")


def failed_details(results):
    return [i.detail for r in results.values() for i in r.items if i.status == "fail"]


class ACounterReturnedAsAFloatFails(unittest.TestCase):
    def test_the_reference_returns_the_counter_as_an_int_and_the_cases_hold_it(self):
        seen = []
        r = run(counter_as(lambda v: seen.append(v) or v))
        self.assertEqual(failing(r), [])
        self.assertTrue(seen and all(type(v) is int for v in seen), "the reference reads rev_at_epoch as an int")
        self.assertTrue(any(v >= 1000 for v in seen))                                  # real counters, not only zeros

    def test_a_whole_float_fails_as_the_wrong_type(self):
        r = run(counter_as(float))                                                      # 95679 -> 95679.0
        self.assertEqual(failing(r), CARRY_IT)
        details = failed_details(r)
        self.assertTrue(details and all("rev_at_epoch returned as float" in d and "not int" in d for d in details), details[:3])
        self.assertEqual([d for d in details if "internal error" in d], [])

    def test_a_fractional_float_fails_as_no_integer(self):
        r = run(counter_as(lambda v: float(v) + 0.5))                                   # 95679 -> 95679.5
        self.assertEqual(failing(r), CARRY_IT)
        details = failed_details(r)
        self.assertTrue(details and all("rev_at_epoch is not an integer" in d and "(float, fractional)" in d for d in details), details[:3])
        self.assertEqual([d for d in details if "internal error" in d], [])

    def test_twin_the_same_records_with_an_int_pass_and_a_wrong_int_fails(self):
        self.assertEqual(failing(run(counter_as(int))), [])                             # the twin: the same values as int
        r = run(counter_as(lambda v: int(v) + 1))                                       # the control: an int, but wrong
        self.assertEqual(failing(r), CARRY_IT)
        self.assertTrue(all("rev_at_epoch" in d for d in failed_details(r)))


if __name__ == "__main__":
    unittest.main()
