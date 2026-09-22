"""Runner self-tests. Run: python -m unittest discover -s tests (from the repository root)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gpconf.runner import Runner  # noqa: E402
from gpconf import tle as tlemod  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402
from tests.adapters.naive import Parser as Naive  # noqa: E402


def failures(results):
    return {r.case_id: [i for i in r.items if i.status == "fail"] for r in results if r.status == "fail"}


class ReferenceAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = Runner(Reference(), root=ROOT).run()

    def test_no_failures(self):
        f = failures(self.results)
        self.assertEqual(f, {}, "\n".join(f"{c}: {i.check} {i.file}: {i.detail}" for c, items in f.items() for i in items))

    def test_reference_is_exact(self):
        # the reference adapter produced the expected values; it must never need a tolerance
        tol = [(r.case_id, i.check, i.file) for r in self.results for i in r.items if i.status == "pass-tolerance"]
        self.assertEqual(tol, [])

    def test_offline_cases_pass_without_raw_files(self):
        # cases whose sources are all shipped (derived/, vectors/) must pass even when fixtures/*/raw is absent
        for r in self.results:
            if r.case_id in ("alpha5-encoding-vectors", "alpha5-tle-derived", "kvn-syntax-variants", "tle-writer-alpha5"):
                self.assertEqual(r.status, "pass", r.case_id)


class NaiveAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = Runner(Naive(), root=ROOT).run()
        cls.by_id = {r.case_id: r for r in cls.results}

    def test_expected_failures(self):
        must_fail = ["alpha5-encoding-vectors", "alpha5-tle-derived", "kvn-syntax-variants", "six-digit-omm-saramago",
                     "analyst-objects", "supgp-celestrak-classification-c", "tle-writer-alpha5"]
        for c in must_fail:
            if self.by_id[c].status == "skip":  # sources not fetched in this checkout
                continue
            self.assertEqual(self.by_id[c].status, "fail", f"{c} should fail for the naive parser")

    def test_baseline_may_pass(self):
        # the naive parser reads a plain current ISS TLE/CSV correctly; the corpus must not fail it for that
        r = self.by_id["epoch-year-19xx"]
        self.assertNotIn("parse", [i.check for i in r.items if i.status == "fail" and i.file and i.file.endswith(".tle")])


class Alpha5Tests(unittest.TestCase):
    def test_official_examples(self):
        for n, f in [(100000, "A0000"), (148493, "E8493"), (182931, "J2931"), (234018, "P4018"), (301928, "W1928"), (339999, "Z9999")]:
            self.assertEqual(tlemod.to_alpha5(n), f)
            self.assertEqual(tlemod.from_alpha5(f), n)

    def test_invalid(self):
        for bad in ("I0000", "O0000", "a0000"):
            with self.assertRaises(ValueError):
                tlemod.from_alpha5(bad)
        with self.assertRaises(ValueError):
            tlemod.to_alpha5(340000)


if __name__ == "__main__":
    unittest.main()
