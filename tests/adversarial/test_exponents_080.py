# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""A value whose exponent no TLE field can hold is refused from its exponent, before any arithmetic (D-354, D-351's
first reading, finding 8), with a wrong-on-purpose adapter and its twin.

Before: `tle_side` wrote the value out in full (`format(d, "f")`), so 1E+999999999 cost seconds and most of a gigabyte;
`exp_field` normalised 1E-9999999 to nothing and wrote it as " 00000+1", which the TLE/OMM consistency check read as 0,
so a parser answering it where the TLE field holds 0 passed; and 1E+9999999 raised decimal.Overflow, not the ValueError
`exp_field` names. The files are built at test time from the ISS record epoch-year-19xx freezes (no provider's bytes, so
the module runs in the public export). Run: python -m unittest tests.adversarial.test_exponents_080"""
import os
import shutil
import sys
import tempfile
import time
import tracemalloc
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf import tle  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import Runner, tle_side  # noqa: E402
from tests.adversarial.test_history_080 import SETS, csv_text, tle_text  # noqa: E402
from tests.adversarial.test_internal_errors_080 import answering  # noqa: E402
from tests.adversarial.test_strict_files_080 import LIVE  # noqa: E402

CONSISTENCY = "tle-values-match-omm-within-tle-precision"


class ExponentsNoFieldHolds(unittest.TestCase):

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-exponents-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def iss(self, parser):
        for name, text in (("iss.tle", tle_text(SETS[:1])), ("iss.csv", csv_text(SETS[:1]))):
            os.makedirs(os.path.join(self.data, LIVE), exist_ok=True)
            with open(os.path.join(self.data, LIVE, name), "w", encoding="utf-8", newline="") as f:
                f.write(text)
        res = Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["baseline-iss-five-formats"])[0]
        items = {i.check: i for i in res.items}
        self.assertNotIn("runner", items, items.get("runner") and items["runner"].detail)
        return items[CONSISTENCY]

    def test_an_absurd_exponent_costs_nothing(self):
        """1E+999999999 and its like are decided from the exponent: well under a second and 128 KB each, the bound tight
        enough that a guard loosened to a million (1E+999998 written out is a megabyte) is caught."""
        for value in ("1E+999999999", "1E+9999999", "1E-999999999", Decimal("1E+999999999"), "1E+999998", "1E-999998", "1E+999999"):
            with self.subTest(value=value):
                tracemalloc.start()
                t = time.perf_counter()
                self.assertIsNone(tle_side("bstar", value))
                with self.assertRaises(ValueError):
                    tle.exp_field(str(value), "round")
                spent, (_, peak) = time.perf_counter() - t, tracemalloc.get_traced_memory()
                tracemalloc.stop()
                self.assertLess(spent, 1.0)
                self.assertLess(peak, 1 << 17)

    def test_exp_field_refuses_with_a_value_error_naming_the_exponent(self):
        for value, exponent in (("1E-9999999", -9999998), ("1E+9999999", 10000000), ("1E+999999", 1000000), ("1E-11", -10), ("1E+99", 100)):
            for mode in ("truncate", "round"):
                with self.subTest(value=value, mode=mode):
                    with self.assertRaisesRegex(ValueError, f"exponent {exponent} not representable in a TLE field"):
                        tle.exp_field(value, mode)

    def test_the_edges_read_as_before(self):
        """Its twin: values at the field's edges, which rounding may carry into the field or out of it, as before."""
        self.assertEqual(tle.exp_field("9.99995E-11", "round"), " 10000-9")   # e -10, rounded up into the field
        with self.assertRaises(ValueError):
            tle.exp_field("9.99994E-11", "round")                            # e -10, stays out
        self.assertEqual(tle.exp_field("9.99999E+8", "truncate"), " 99999+9")
        with self.assertRaises(ValueError):
            tle.exp_field("9.99999E+8", "round")                             # rounded up to e 10
        self.assertEqual(tle.exp_field("-.70517E-5", "round"), "-70517-5")

    def test_tle_side_holds_the_same_edges_and_any_zero(self):
        """D-354's reading, findings 1 and 2: the consistency check's own reading of a value, at the field's edges, and a
        zero of any exponent (a zero's exponent is no number's size: "0.0000000000000" was refused once the guard came
        first), decided at no cost."""
        for value, want in (("9.99995E-11", "0.0000000001"), ("9.99994E-11", None), ("9.99999E+8", None), ("1E+1000000", None),
                            ("1E-1000000", None), ("-.70517E-5", "-0.0000070517")):
            with self.subTest(value=value):
                self.assertEqual(tle_side("bstar", value), want)
        self.assertIsNotNone(tle_side("bstar", "9.99994E+8"))
        for zero in ("0.0000000000000", "-0.000000000000", "0E+20", "0E-13", Decimal("0E-13"), Decimal("-0E-99999999"), "0E-999999999"):
            with self.subTest(zero=zero):
                tracemalloc.start()
                t = time.perf_counter()
                self.assertEqual(tle_side("bstar", zero), "0")
                spent, (_, peak) = time.perf_counter() - t, tracemalloc.get_traced_memory()
                tracemalloc.stop()
                self.assertLess(spent, 1.0)
                self.assertLess(peak, 1 << 17)

    def test_a_zero_with_many_decimals_passes(self):
        """A parser handing back the OMM text of a zero, or a Decimal of it, with thirteen decimals: the item passes, as
        it did before this entry (the twin of the vanishing exponent below)."""
        for zero in ("0.0000000000000", Decimal("0E-13"), "-0.000000000000"):
            with self.subTest(zero=zero):
                item = self.iss(answering(lambda rs: [dict(r, bstar=zero) for r in rs]))
                self.assertEqual(item.status, "pass", item.detail)

    def test_a_parser_answering_a_vanishing_exponent_fails(self):
        """The escape: an OMM BSTAR of 1E-9999999 where the TLE field holds 0 was read as 0 and passed; it fails now,
        named as a value no TLE field holds; its twin, the reference, passes."""
        for value in ("1E-9999999", Decimal("1E-9999999")):
            with self.subTest(value=value):
                item = self.iss(answering(lambda rs: [dict(r, bstar=value) for r in rs]))
                self.assertEqual(item.status, "fail", item.detail)
                self.assertIn("bstar: omm 1E-9999999 is a value no TLE field holds as providers write it", item.detail)
        twin = self.iss(Reference())
        self.assertEqual(twin.status, "pass", twin.detail)


if __name__ == "__main__":
    unittest.main()
