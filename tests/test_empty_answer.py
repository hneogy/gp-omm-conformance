"""The provider's empty answer, handed to the parser under test (D-143): zero records and no error is the only pass."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gpconf.runner import Runner, Unsupported  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402
from tests.adapters.naive import Parser as Naive  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECK = "empty-answer-yields-no-records"
CASES = ["tle-omits-six-digit-objects", "six-digit-omm-saramago", "analyst-objects", "nine-digit-supgp-launch-nominals"]
BODY_FILES = ["fixtures/tle-omits-six-digit-objects/raw/last-30-days.tle", "fixtures/tle-omits-six-digit-objects/raw/last-30-days-recapture.tle",
              "fixtures/six-digit-omm-saramago/raw/saramago-first.tle", "fixtures/six-digit-omm-saramago/raw/saramago.tle",
              "fixtures/analyst-objects/raw/analyst-270449-first.tle", "fixtures/nine-digit-supgp-launch-nominals/raw/starlink-38381-799501621.tle"]


def items(results, check):
    return [(r.case_id, i) for r in results for i in r.items if i.check == check]


class Raises:
    def parse(self, raw, fmt):
        raise ValueError("no TLE lines found")


class Invents:
    def parse(self, raw, fmt):
        return [{"norad_cat_id": 0, "epoch": "2026-01-01T00:00:00"}]


class TleUnsupported:
    def parse(self, raw, fmt):
        raise Unsupported(fmt)


class Declared(unittest.TestCase):
    def test_the_four_cases_declare_the_check(self):
        manifest = json.load(open(os.path.join(ROOT, "manifest.json")))
        declared = {c["id"] for c in manifest["cases"] if CHECK in c["checks"]}
        self.assertEqual(declared, set(CASES))


class OnDisk(unittest.TestCase):
    """Runs only where the recorded bodies are on disk (tools/fetch.py); CI's offline runs have no raw files."""
    present = [p for p in BODY_FILES if os.path.exists(os.path.join(ROOT, p))]

    def setUp(self):
        if not self.present:
            self.skipTest("no recorded 404 body on disk")

    def test_reference_and_naive_read_the_empty_answer_as_empty(self):
        for P in (Reference, Naive):
            got = items(Runner(P(), root=ROOT).run(case_ids=CASES), CHECK)
            self.assertEqual({i.file for _, i in got}, set(self.present), P)
            self.assertTrue(all(i.status == "pass" for _, i in got), [(c, i.file, i.detail) for c, i in got if i.status != "pass"])

    def test_an_error_is_a_failure_and_a_record_is_a_failure(self):
        got = items(Runner(Raises(), root=ROOT).run(case_ids=["tle-omits-six-digit-objects"]), CHECK)
        self.assertTrue(got and all(i.status == "fail" and "raised ValueError" in i.detail and "not an error" in i.detail for _, i in got), [i.detail for _, i in got])
        got = items(Runner(Invents(), root=ROOT).run(case_ids=["tle-omits-six-digit-objects"]), CHECK)
        self.assertTrue(got and all(i.status == "fail" and "returned 1 record" in i.detail for _, i in got), [i.detail for _, i in got])

    def test_a_parser_without_the_format_skips(self):
        got = items(Runner(TleUnsupported(), root=ROOT).run(case_ids=["tle-omits-six-digit-objects"]), CHECK)
        self.assertTrue(got and all(i.status == "skip" for _, i in got), [i.detail for _, i in got])


if __name__ == "__main__":
    unittest.main()
