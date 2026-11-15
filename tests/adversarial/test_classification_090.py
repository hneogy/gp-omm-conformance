# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""D-404 (the third blind pass's 1): a TLE reader that reports every set as classified U fails offline, where every
offline set was U before; the set classified C (330205) is read on the parse path only."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from gpconf.adapters.reference import Parser as Reference  # noqa: E402

FILE = "alpha5-synthetic-classification.tle"


class AlwaysU(Reference):
    """The red team's e01: column 8 ignored, every TLE set reported U."""

    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        if fmt in ("tle", "2le"):
            for r in out:
                if "_refused" not in r and "_adapter" not in r:
                    r["classification_type"] = "U"
        return out


def run(p):
    from gpconf.runner import Runner
    (r,) = Runner(p, root=ROOT, fetch_hints=False).run(case_ids=["alpha5-tle-derived"])
    return r


class AClassificationOfC(unittest.TestCase):
    def test_a_reader_reporting_u_fails_on_that_set_alone(self):
        r = run(AlwaysU())
        self.assertEqual(r.status, "fail")
        bad = [i for i in r.items if i.status == "fail"]
        self.assertEqual([(i.check, os.path.basename(i.file)) for i in bad], [("values", FILE)])
        self.assertIn("id 330205: classification_type = 'U', expected 'C'", bad[0].detail)

    def test_the_reference_passes(self):
        self.assertIn(run(Reference()).status, ("pass", "pass-tolerance"))

    def test_the_set_is_no_writer_input(self):
        with open(os.path.join(ROOT, "fixtures", "tle-writer-alpha5", "expected.json"), encoding="utf-8") as f:
            ids = {r["norad_cat_id"] for r in json.load(f)["records"]}
        self.assertNotIn(330205, ids)
        self.assertEqual(len(ids), 762)


if __name__ == "__main__":
    unittest.main()
