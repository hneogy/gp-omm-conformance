# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""D-398 (the third blind pass's 19, Phase 2 of 0.9.0): a command's JSON that holds a key twice in one object is no
answer. json.loads kept the last value without a word, so a command could print one value and have another graded."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from gpconf.runner import CommandParser, Runner  # noqa: E402
from tests.raw_needed import needs_raw  # noqa: E402

ISS_RAW = os.path.join("fixtures", "baseline-iss-five-formats", "raw")   # withheld from the export (D-408)

TWICE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "twice_cmd.py")


def command(mode, vec=None):
    return CommandParser([sys.executable, TWICE, mode, "{fmt}"],
                         vectors_cmd=[sys.executable, TWICE, vec or "vec-" + mode.split("-")[1], "x"])


def run(mode, case, vec=None):
    (r,) = Runner(command(mode, vec), root=ROOT, fetch_hints=False).run(case_ids=[case])
    return r


class AKeyTwice(unittest.TestCase):
    @needs_raw(ISS_RAW)
    def test_the_twin_with_each_key_once_passes_as_the_reference(self):
        self.assertEqual(run("parse-ok", "baseline-iss-five-formats").status, "pass")

    @needs_raw(ISS_RAW)
    def test_a_record_with_a_key_twice_fails_parse_and_says_so(self):
        r = run("parse-twice", "baseline-iss-five-formats")
        self.assertEqual(r.status, "fail")
        bad = [i for i in r.items if i.check == "parse" and i.status == "fail"]
        self.assertTrue(bad)
        self.assertIn("holding the key 'norad_cat_id' twice in one object, with two different values", bad[0].detail)

    def test_a_corrupt_input_answered_with_a_key_twice_is_not_a_refusal(self):
        r = run("parse-twice", "corrupt-input")
        self.assertEqual(r.status, "fail")
        words = [i.detail for i in r.items if "twice in one object" in i.detail]
        self.assertTrue(words)
        self.assertTrue(all("no refusal and no rejection (D-398)" in i.detail for i in r.items if i.check.startswith("corrupt-tle")))

    def test_a_vector_answer_with_a_key_twice_is_no_rejection(self):
        self.assertEqual(run("parse-ok", "alpha5-encoding-vectors").status, "pass")
        r = run("parse-twice", "alpha5-encoding-vectors")
        self.assertEqual(r.status, "fail")
        self.assertTrue([i for i in r.items if "twice in one object" in i.detail and i.status == "fail"])


    def test_a_rejection_twice_on_invalid_vectors_alone_is_no_rejection(self):
        r = run("parse-ok", "alpha5-encoding-vectors", "vec-invalidtwice")
        self.assertEqual(r.status, "fail")
        self.assertTrue([i for i in r.items if "twice in one object" in i.detail and i.status == "fail"])

    # the review of D-398: two readers it failed at first
    def test_a_non_zero_exit_is_a_rejection_whatever_it_printed(self):
        self.assertEqual(run("parse-ok", "alpha5-encoding-vectors", "vec-nztwice").status, "pass")

    @needs_raw(ISS_RAW)
    def test_the_same_value_twice_is_one_value(self):
        r = run("parse-same", "baseline-iss-five-formats")
        self.assertEqual(r.status, "pass", [i.detail for i in r.items if i.status == "fail"][:2])


if __name__ == "__main__":
    unittest.main()
