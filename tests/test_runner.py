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


class SatcatCaseTests(unittest.TestCase):
    """satcat-70000-cutoff is a data check the runner makes itself; no adapter reads SATCAT. For every parser the
    case must report not-exercised (never pass or fail), so a per-library table cannot read it as a library result."""

    def test_not_a_parser_result(self):
        parsers = [Reference(), Naive()]
        try:
            from tests.adapters.sgp4_adapter import Parser as Sgp4
            parsers.append(Sgp4())
        except ImportError:
            pass
        for parser in parsers:
            with self.subTest(parser=type(parser).__module__):
                r = next(x for x in Runner(parser, root=ROOT).run(case_ids=["satcat-70000-cutoff"]) if x.case_id == "satcat-70000-cutoff")
                statuses = [i.status for i in r.items]
                self.assertNotIn("pass", statuses, statuses)
                self.assertNotIn("pass-tolerance", statuses, statuses)
                self.assertNotIn("fail", statuses, statuses)
                if os.path.exists(os.path.join(ROOT, "fixtures", "satcat-70000-cutoff", "raw", "satcat.txt")):
                    self.assertEqual(r.status, "not-exercised", statuses)
                    item = next(i for i in r.items if i.check == "satcat-legacy-below-70000")
                    self.assertIn("not involved", item.detail)
                else:  # public clone without the legacy file: source-present not-fetched items only (D-148)
                    self.assertEqual(r.status, "not-fetched", statuses)


class NaiveAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = Runner(Naive(), root=ROOT).run()
        cls.by_id = {r.case_id: r for r in cls.results}

    # Cases the naive parser must fail. The first group ships with the repository (derived files, vectors, inline
    # writer inputs) and runs from a fresh clone; the second needs the CelesTrak files in fixtures/*/raw, which the
    # public clone does not carry (provider data is not redistributed; tools/fetch.py fetches them).
    OFFLINE_MUST_FAIL = ["alpha5-encoding-vectors", "alpha5-tle-derived", "kvn-syntax-variants", "tle-writer-alpha5"]
    FETCHED_MUST_FAIL = ["six-digit-omm-saramago", "analyst-objects", "supgp-celestrak-classification-c"]

    def test_expected_failures_offline(self):
        for c in self.OFFLINE_MUST_FAIL:
            self.assertEqual(self.by_id[c].status, "fail", f"{c} should fail for the naive parser")

    def test_expected_failures_on_fetched_sources(self):
        # Without the fetched files the runner must report these cases as not-fetched, never as passed or skipped, and
        # this test reports the absence and its reason instead of passing vacuously (D-119, D-148). The naive parser's failures here are
        # parse failures on the provider's own bytes (six-digit ids, an empty OBJECT_ID, classification C), so the
        # cases are not driven from frozen records: rendering those back into provider formats would test the
        # corpus's rendering, not the provider's files, and the SupGP values are withheld from the export (D-049).
        present = [c for c in self.FETCHED_MUST_FAIL if self.by_id[c].status != "not-fetched"]
        for c in present:
            self.assertEqual(self.by_id[c].status, "fail", f"{c} should fail for the naive parser")
        absent = [c for c in self.FETCHED_MUST_FAIL if self.by_id[c].status == "not-fetched"]
        for c in absent:
            items = self.by_id[c].items
            self.assertTrue(items and all(i.check == "source-present" and i.status == "not-fetched" for i in items),
                            f"{c}: a case without its sources must consist of source-present not-fetched items only, not {[(i.check, i.status) for i in items][:5]}")
        if absent:
            self.skipTest(f"raw sources absent for {', '.join(absent)} (public clone): run tools/fetch.py to exercise these cases")

    def test_baseline_may_pass(self):
        # the naive parser reads a plain current ISS TLE/CSV correctly; the corpus must not fail it for that
        r = self.by_id["epoch-year-19xx"]
        self.assertNotIn("parse", [i.check for i in r.items if i.status == "fail" and i.file and i.file.endswith(".tle")])


class SourcelessCases(unittest.TestCase):
    """A case none of whose files is on disk (the public clone before tools/fetch.py) reports not-fetched. It used to
    report 'not exercised' when it listed a check with a case-level fallback (nine-digit ids since v0.1.0, the three
    field-form checks since D-118), which reads as 'the data lacked the feature' when there was no data (D-119); and
    then 'skip', which the corpus also uses for a parser with no reader for the format (D-148)."""

    CASES = ["epoch-year-19xx", "baseline-iss-five-formats", "nine-digit-supgp-launch-nominals", "bstar-and-derivative-forms",
             "six-digit-omm-saramago", "analyst-objects", "supgp-celestrak-classification-c"]

    def test_a_case_without_its_files_is_not_fetched_never_skip_or_not_exercised(self):
        import json
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(os.path.join(ROOT, "manifest.json"), tmp)
            for c in self.CASES:
                os.makedirs(os.path.join(tmp, "fixtures", c))
                shutil.copy(os.path.join(ROOT, "fixtures", c, "expected.json"), os.path.join(tmp, "fixtures", c))
            for parser in (Reference(), Naive()):
                for r in Runner(parser, root=tmp).run(case_ids=self.CASES):
                    self.assertEqual(r.status, "not-fetched", (r.case_id, [(i.check, i.status) for i in r.items if i.status != "not-fetched"]))
                    self.assertTrue(all(i.check == "source-present" and i.status == "not-fetched" for i in r.items), r.case_id)
        with open(os.path.join(ROOT, "fixtures", "nine-digit-supgp-launch-nominals", "expected.json")) as f:
            self.assertIn("nine-digit-ids-parse", [k["id"] for k in json.load(f)["checks"]])  # the case that had the fallback since v0.1.0


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
