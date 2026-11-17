# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""A detail that names only the first few of its findings says how many it leaves out, and the JSON report's item
carries every one of them (D-593; found while checking GPKit 2.0.0 against gpconf 0.9.0: set 20413's seven
failing steps showed six; D-593). No status changes: only the words and an added field.

Run: python -m unittest tests.test_cut_lists_0100"""
import io
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import runner as R  # noqa: E402
from gpconf import schema as S  # noqa: E402


def sgp4_present():
    try:
        import sgp4.api  # noqa: F401
        return True
    except ImportError:
        return False


class TheHelpers(unittest.TestCase):
    def test_a_short_list_is_shown_whole_with_nothing_added(self):
        self.assertEqual(R.shown(["a", "b"]), "a; b")
        self.assertIsNone(R.cut(["a", "b"]))
        self.assertEqual(R.more([1, 2, 3], 3), "")

    def test_a_list_of_exactly_n_is_not_cut(self):
        self.assertEqual(R.shown(list("abcdef")), "a; b; c; d; e; f")
        self.assertIsNone(R.cut(list("abcdef")))

    def test_a_longer_list_says_how_many_are_left_out(self):
        self.assertEqual(R.shown(list("abcdefgh")), "a; b; c; d; e; f; … and 2 more")
        self.assertEqual(R.cut(list("abcdefgh")), list("abcdefgh"))
        self.assertEqual(R.shown([1, 2, 3, 4], 3, ", "), "1, 2, 3, … and 1 more")
        self.assertEqual(R.more([1, 2, 3, 4, 5], 3), " and 2 more")

    def test_the_item_carries_details_only_when_cut(self):
        self.assertNotIn("details", R.Item("c", "fail", None, "x").as_dict())
        self.assertEqual(R.Item("c", "fail", None, "x", details=["a", "b"]).as_dict()["details"], ["a", "b"])

    def test_a_report_with_details_matches_the_results_schema(self):
        item = R.Item("twins-omm-positions", "fail", None, "a; … and 1 more", details=["a", "b"]).as_dict()
        schema = S.load_schema()
        self.assertEqual(S.errors(item, schema["$defs"]["item"], root=schema), [])
        bad = dict(item, details="a, b")   # a string is not the list the schema names
        self.assertNotEqual(S.errors(bad, schema["$defs"]["item"], root=schema), [])


@unittest.skipUnless(sgp4_present(), "needs python-sgp4")
class MoreThanSixFailuresInARealCase(unittest.TestCase):
    """The twins case with every OMM step wrong: seven sets of seven steps, far more than six failures, as in the
    GPKit finding."""
    def wrong_omm(self):
        from sgp4 import omm
        from sgp4.api import Satrec
        from gpconf.adapters.sgp4_adapter import Parser

        class Wrong(Parser):
            def propagate(self, raw, fmt, tsince):
                if fmt != "csv":
                    return Parser.propagate(self, raw, fmt, tsince)
                (fields,) = list(omm.parse_csv(io.StringIO(raw.decode())))
                fields["MEAN_MOTION"] = str(float(fields["MEAN_MOTION"]) * 1.001)
                s = Satrec()
                omm.initialize(s, fields)
                out = []
                for t in tsince:
                    e, r, v = s.sgp4_tsince(t)
                    out.append({"r": list(r), "v": list(v), "error": e} if e == 0 else {"error": e})
                return out
        return Wrong()

    def test_the_detail_counts_what_it_leaves_out_and_the_json_lists_them_all(self):
        (r,) = R.Runner(self.wrong_omm(), root=ROOT, fetch_hints=False).run(case_ids=["propagation-tle-omm-twins"])
        self.assertEqual(r.status, "fail")
        (item,) = [i for i in r.items if i.check == "twins-omm-positions"]
        self.assertEqual(item.status, "fail")
        self.assertGreater(len(item.details or []), 6, item.detail)
        self.assertIn(f"… and {len(item.details) - 6} more", item.detail)
        self.assertTrue(item.detail.startswith("steps fail in "), item.detail[:80])   # the failing-sets opening comes first (D-593)
        listed = item.detail.split("; ", 1)[1]
        shown_part = listed.split("; … and")[0].split("; ")
        self.assertEqual(shown_part, item.details[:6])   # the six shown are the first six of the whole list
        d = r.as_dict()
        (j,) = [i for i in d["items"] if i["check"] == "twins-omm-positions"]
        self.assertEqual(j["details"], item.details)
        schema = S.load_schema()
        self.assertEqual(S.errors(json.loads(json.dumps(d)), schema["$defs"]["case"], root=schema), [])

    def test_a_correct_parser_gets_no_details(self):
        from gpconf.adapters.sgp4_adapter import Parser
        (r,) = R.Runner(Parser(), root=ROOT, fetch_hints=False).run(case_ids=["propagation-tle-omm-twins"])
        self.assertTrue(all(not i.details for i in r.items), [i.check for i in r.items if i.details])


if __name__ == "__main__":
    unittest.main()
