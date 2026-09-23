"""A stable-tier source whose bytes differ from the tested snapshot is reported as drift, explicitly (D-115).

Before: the file silently became "live", the reference reader became the oracle, and the only trace was an
info item hidden without --verbose. Now: a failing `stable-source-drift` item, a `drift` field in the JSON,
and a values item that says the frozen expected values were not applied and why."""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gpconf.runner import Runner  # noqa: E402
from gpconf import tle as T  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402

CASE = "alpha5-tle-derived"
FILE = "derived/alpha5-tle/alpha5-A-100000-saramago-first.tle"


def scratch_root():
    d = tempfile.mkdtemp()
    m = json.load(open(os.path.join(ROOT, "manifest.json")))
    m["cases"] = [c for c in m["cases"] if c["id"] == CASE]
    json.dump(m, open(os.path.join(d, "manifest.json"), "w"))
    os.makedirs(os.path.join(d, "fixtures", CASE))
    shutil.copy(os.path.join(ROOT, "fixtures", CASE, "expected.json"), os.path.join(d, "fixtures", CASE))
    shutil.copytree(os.path.join(ROOT, "derived", "alpha5-tle"), os.path.join(d, "derived", "alpha5-tle"))
    return d


def edit_one_digit(path):
    """Change the last mean-motion digit on line 2 and recompute the checksum: a valid line with one value changed."""
    lines = open(path).read().splitlines()
    i = next(n for n, l in enumerate(lines) if l.startswith("2 "))
    l2 = lines[i]
    digit = "1" if l2[62] != "1" else "2"
    body = l2[:62] + digit + l2[63:68]
    lines[i] = body + str(T.checksum(body))
    open(path, "w").write("\n".join(lines) + "\n")


class StableDriftTests(unittest.TestCase):
    def run_case(self, mutate):
        d = scratch_root()
        try:
            if mutate:
                edit_one_digit(os.path.join(d, FILE))
            r = Runner(Reference(), root=d).run(case_ids=[CASE])[0]
        finally:
            shutil.rmtree(d)
        return r

    def test_matching_stable_file_reports_exact_against_the_frozen_values(self):
        r = self.run_case(mutate=False)
        self.assertEqual(r.status, "pass")
        self.assertEqual(r.as_dict()["drift"], {})
        self.assertEqual([i for i in r.items if i.check == "stable-source-drift"], [])
        values = [i for i in r.items if i.check == "values"]
        self.assertEqual(len(values), 4)
        self.assertTrue(all(i.status == "pass" and "match frozen expected values" in i.detail for i in values), [i.detail for i in values])

    def test_edited_stable_file_reports_drift_and_reference_comparison(self):
        r = self.run_case(mutate=True)
        self.assertEqual(r.status, "fail")
        drift = [i for i in r.items if i.check == "stable-source-drift"]
        self.assertEqual([(i.status, i.file) for i in drift], [("fail", FILE)])
        for phrase in ("stable-tier", "differ from the tested snapshot", "frozen expected values were not applied", "reference reader", "recorded SHA-256", "actual"):
            self.assertIn(phrase, drift[0].detail, drift[0].detail)
        j = r.as_dict()
        self.assertEqual(sorted(j["drift"]), [FILE])
        self.assertEqual(sorted(j["drift"][FILE]), ["actual_sha256", "recorded_sha256"])
        self.assertNotEqual(j["drift"][FILE]["actual_sha256"], j["drift"][FILE]["recorded_sha256"])
        self.assertEqual(len(j["drift"][FILE]["actual_sha256"]), 64)
        values = {i.file: i for i in r.items if i.check == "values"}
        self.assertEqual(values[FILE].status, "pass")                       # the reference adapter agrees with the reference reader
        self.assertIn("frozen expected values not applied", values[FILE].detail)
        self.assertIn("stable source drifted", values[FILE].detail)
        for f, i in values.items():
            if f != FILE:
                self.assertIn("match frozen expected values", i.detail, f)     # the other three files are untouched
        self.assertEqual([i for i in r.items if i.status == "fail"], drift)   # drift is the only failure


if __name__ == "__main__":
    unittest.main()
