# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The type-check ratchet's three findings on 0.10.0 (D-611): the corrupt-input case's one path with no corrupt record
named, and the loud stop that replaced reading a missing record.

Run: python -m unittest tests.test_mypy_mends_0100"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import runner as R  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402

CUT_JSON = "derived/corrupt-input/c5-cut-closing-bracket.json"


class TheCutJsonHasNoCorruptRecord(unittest.TestCase):
    """The JSON array cut before its closing bracket holds every record whole, so no record is the corrupt one
    (runner: corrupt is None there). Its item is graded, carries no details and raises no internal error."""
    def test_the_none_branch_is_graded_without_details(self):
        (r,) = R.Runner(Reference(), root=ROOT, fetch_hints=False).run(case_ids=["corrupt-input"])
        items = [i for i in r.items if i.file == CUT_JSON and i.check == "corrupt-file-cut"]
        self.assertTrue(items, [(i.check, i.file) for i in r.items][:20])
        for it in items:
            self.assertNotIn("internal error", it.detail.lower(), it.detail)
            self.assertIsNone(it.details, it.detail)
            # the reference refuses the cut file as a whole: the pass D-611 names (D-612)
            self.assertEqual(it.status, "pass", it.detail)
            self.assertIn("refused the file as a whole", it.detail)

    def test_a_silent_partial_load_of_the_cut_file_fails_without_an_internal_error(self):
        """The None branch's failing path: a parser that keeps all but the last record of the cut file and says nothing
        fails as silent partial loading, with no internal error and no details (D-611)."""
        class Partial(Reference):
            def parse(self, raw, fmt):
                s = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                if fmt == "json" and s.rstrip().endswith("}") and not s.rstrip().endswith("]"):
                    import json
                    keep = json.loads(s.rstrip() + "]")[:-1]   # every whole record but the last, nothing said
                    return Reference.parse(self, json.dumps(keep).encode("utf-8"), "json")
                return Reference.parse(self, raw, fmt)
        (r,) = R.Runner(Partial(), root=ROOT, fetch_hints=False).run(case_ids=["corrupt-input"])
        (it,) = [i for i in r.items if i.file == CUT_JSON and i.check == "corrupt-file-cut"]
        self.assertEqual(it.status, "fail", it.detail)
        self.assertIn("silent partial loading", it.detail)
        self.assertNotIn("internal error", it.detail.lower())
        self.assertIsNone(it.details)

    def test_built_a_record_said_with_no_corrupt_record_stops_loudly(self):
        """The loud stop itself (D-612): with no corrupt record named, a fail text that says
        "built a record" (here put there through the cut file's edit statement, which the fail text quotes) must stop
        the run with the D-611 internal error, never read a missing record."""
        import json
        from unittest import mock
        real = R.read_bytes
        def planted(path, *a, **k):
            data = real(path, *a, **k)
            if path.replace(os.sep, "/").endswith("fixtures/corrupt-input/expected.json"):
                exp = json.loads(data.decode("utf-8"))
                exp["case_specific"]["files"][os.path.basename(CUT_JSON)]["file_edit"] = "built a record, said by the edit"
                data = json.dumps(exp).encode("utf-8")
            return data
        class Partial(Reference):
            def parse(self, raw, fmt):
                s = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                if fmt == "json" and s.rstrip().endswith("}") and not s.rstrip().endswith("]"):
                    keep = json.loads(s.rstrip() + "]")[:-1]
                    return Reference.parse(self, json.dumps(keep).encode("utf-8"), "json")
                return Reference.parse(self, raw, fmt)
        with mock.patch.object(R, "read_bytes", planted):
            try:
                (r,) = R.Runner(Partial(), root=ROOT, fetch_hints=False).run(case_ids=["corrupt-input"])
            except RuntimeError as e:
                self.assertIn("no corrupt record named (D-611)", str(e))
                return
        said = [i.detail for i in r.items if "D-611" in (i.detail or "")]
        self.assertTrue(said, "the planted text neither raised nor was reported as the D-611 internal error")
        self.assertIn("no corrupt record named (D-611)", said[0])

if __name__ == "__main__":
    unittest.main()
