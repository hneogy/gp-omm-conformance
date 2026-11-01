# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Refusals that said something other than what happened (D-356, split from D-355 by the owner after its third
reading, and from D-357 after D-356's own third reading), with wrong-on-purpose adapters and twins: a tie between refusal
reasons settled by the hash seed, and the reasons tallied by a count per distinct reason; and a refusal without a reason
said to be counted dropped.

The files are the corpus's own derived files or built at test time from the ISS record epoch-year-19xx freezes (no
provider's bytes, so the module runs in the public export). Run: python -m unittest tests.adversarial.test_refusal_counts_080"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf.runner import Runner  # noqa: E402
from tests.adversarial.test_history_080 import SETS, csv_text, tle_text  # noqa: E402
from tests.adversarial.test_internal_errors_080 import answering  # noqa: E402
from tests.adversarial.test_strict_files_080 import LIVE  # noqa: E402
from tests.crashwatch import watched  # noqa: E402


class RefusalsAndCounts(unittest.TestCase):

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-refusal-counts-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def iss(self, parser):
        os.makedirs(os.path.join(self.data, LIVE), exist_ok=True)
        for name, text in (("iss.tle", tle_text(SETS[:1])), ("iss.csv", csv_text(SETS[:1]))):
            with open(os.path.join(self.data, LIVE, name), "w", encoding="utf-8", newline="") as f:
                f.write(text)
        return Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["baseline-iss-five-formats"])[0]

    def iss_item(self, parser, check):
        (item,) = [i for i in self.iss(parser).items if i.check == check and (i.file or "").endswith("iss.csv")]
        return item

    def test_a_tie_between_refusal_reasons_does_not_follow_the_hash_seed(self):
        """Every corrupt input answered with one refusal "alpha" and one "beta": the top reason is the same under four
        hash seeds, "beta", as compare_values settles a tie (by count, then the reason's text, the last first)."""
        script = ("import sys, json; sys.path.insert(0, sys.argv[1])\n"
                  "from gpconf.runner import Runner\n"
                  "class P:\n"
                  "    def parse(self, raw, fmt):\n"
                  "        return [{'_refused': 'alpha'}, {'_refused': 'beta'}]\n"
                  "r = Runner(P(), root=sys.argv[1], fetch_hints=False).run(case_ids=['corrupt-input'])[0]\n"
                  "print(json.dumps(sorted({(i.counts or {}).get('top_refusal_reason') for i in r.items if i.counts and (i.counts or {}).get('top_refusal_reason')})))\n")
        seen = self.top_reasons(script, ("1", "2", "3", "4"))
        self.assertEqual(seen, {json.dumps(["beta"])})
        # its twin, no tie: "alpha" twice and "beta" once, "alpha" (the count first, the text only on a tie)
        seen = self.top_reasons(script.replace("{'_refused': 'beta'}]", "{'_refused': 'beta'}, {'_refused': 'alpha'}]"), ("1", "2"))
        self.assertEqual(seen, {json.dumps(["alpha"])})

    def top_reasons(self, script, seeds):
        seen = set()
        for seed in seeds:
            out = subprocess.run([sys.executable, "-c", script, ROOT], env=watched(dict(os.environ, PYTHONHASHSEED=seed)),
                                 capture_output=True, text=True, timeout=120)
            self.assertEqual(out.returncode, 0, out.stderr[-500:])
            seen.add(out.stdout.strip())
        return seen

    def test_compare_values_settles_the_top_reason_by_count_then_text(self):
        """D-355's third reading, finding 3: the Counter rewrite of the tallies (compare_values' and the records-returned
        item's) had no test of order. Beside the records, and with no record returned, "alpha" twice and "beta" once:
        "alpha"; a tie: "beta"; refusals without a reason, more of them than of any reason, counted in neither."""
        # beside three refusals without a reason, more than any one reason: no tally counts them (D-356's reading, finding 2)
        blank = [{"_refused": ""}, {"_refused": ""}, {"_refused": ""}]
        three = lambda base: lambda rs: base(rs) + blank + [{"_refused": "alpha"}, {"_refused": "beta"}, {"_refused": "alpha"}]
        tie = lambda base: lambda rs: base(rs) + blank + [{"_refused": "alpha"}, {"_refused": "beta"}]
        keep, none = (lambda rs: rs), (lambda rs: [])
        self.assertEqual(self.iss_item(answering(three(keep)), "values").counts["top_refusal_reason"], "alpha")
        self.assertEqual(self.iss_item(answering(tie(keep)), "values").counts["top_refusal_reason"], "beta")
        # with no record returned there is no values item: the counts are the records-returned item's
        self.assertEqual(self.iss_item(answering(three(none)), "records-returned").counts["top_refusal_reason"], "alpha")
        self.assertEqual(self.iss_item(answering(tie(none)), "records-returned").counts["top_refusal_reason"], "beta")

    def test_a_refusal_without_a_reason_counts_as_no_refusal(self):
        """Its words were "counted as dropped", false for a record outside a partly frozen subset; and "neither returned
        nor refused" (D-355's third reading, finding 1) was false where the parser also returns the record. It credits no
        record, whatever else the parser returns."""
        for name, how in (("beside the records", lambda rs: rs + [{"_refused": ""}]),
                          ("for a record also returned", lambda rs: rs + [{"_refused": "", "_field": "25544"}]),
                          ("alone", lambda rs: [{"_refused": ""}])):
            with self.subTest(name):
                item = self.iss_item(answering(how), "refusals")
                self.assertIn("1 refusal without a reason, counted as no refusal, crediting no record", item.detail)
                self.assertNotIn("counted as dropped", item.detail)


if __name__ == "__main__":
    unittest.main()
