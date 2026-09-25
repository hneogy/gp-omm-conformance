"""The refusal channel (D-144): an entry carrying `_refused` with a non-empty reason is a refusal, credited to its
expected id through `_field`; a refusal without a reason is no better than a drop and is marked so; the capability
declaration decides whether "dropped" means silently or merely unreported."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gpconf import gates  # noqa: E402
from gpconf.runner import Runner, split_refusals, field_to_id  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DERIVED = "derived/alpha5-tle/alpha5-A-last-30-days-snapshot.tle"


def values_item(results, path):
    """The item carrying the file's record counts: values, or records-returned when the parser returned nothing (fail closed)."""
    for r in results:
        for i in r.items:
            if i.check in ("values", "records-returned") and i.file == path:
                return i
    return None


class RefusingAll:
    """Refuses every Alpha-5 set with the field and a reason, and declares the channel."""
    declare = True
    reason = "TleException: Invalid character"

    def parse(self, raw, fmt):
        out = [{"_adapter": {"refusals": True}}] if self.declare else []
        lines = raw.decode().splitlines()
        for l in lines:
            if l.startswith("1 "):
                out.append({"_refused": self.reason, "_field": l[2:7], "_input": l[:80]})
        return out


class Undeclared(RefusingAll):
    declare = False


class NoReason(RefusingAll):
    reason = ""


class SplitOut(unittest.TestCase):
    def test_split_and_reason_rule(self):
        recs, refs, declared = split_refusals([{"_adapter": {"refusals": True}}, {"norad_cat_id": 1}, {"_refused": "x", "_field": "A0404"},
                                               {"_refused": "", "_field": "A0405"}, {"_refused": None}])
        self.assertEqual(len(recs), 1)
        self.assertEqual([r["ok"] for r in refs], [True, False, False])
        self.assertEqual(refs[0]["id"], 100404)
        self.assertTrue(declared)
        self.assertIsNone(split_refusals([{"norad_cat_id": 1}])[2])

    def test_field_to_id(self):
        self.assertEqual(field_to_id("A0404"), 100404)
        self.assertEqual(field_to_id(" 25544"), 25544)
        self.assertEqual(field_to_id("799501621"), 799501621)
        self.assertIsNone(field_to_id("I0000"))
        self.assertIsNone(field_to_id("NaN"))
        self.assertIsNone(field_to_id(None))


class ThroughARun(unittest.TestCase):
    def counts(self, parser):
        results = Runner(parser, root=ROOT).run(case_ids=["alpha5-tle-derived"])
        it = values_item(results, DERIVED)
        self.assertIsNotNone(it)
        return results, it

    def test_refusals_are_credited_and_named(self):
        results, it = self.counts(RefusingAll())
        c = it.counts
        self.assertEqual((c["refused"], c["refused_matched"], c["dropped"], c["loaded"]), (256, 256, 0, 0))
        self.assertTrue(c["refusals_reported"])
        self.assertEqual(it.check, "records-returned")
        self.assertIn("parser returned 0 of 256 record(s): 256 refused with a reason (TleException: Invalid character)", it.detail)
        info = [i for r in results for i in r.items if i.check == "refusals" and i.file == DERIVED]
        self.assertEqual(info[0].status, "info")
        self.assertIn("'TleException: Invalid character' x256", info[0].detail)
        g = gates.compute_gates(results, ROOT)[0]
        self.assertIn("256 refused (TleException: Invalid character)", g["headline"])

    def test_undeclared_adapter_is_not_credited_with_silence(self):
        results, it = self.counts(Undeclared())
        self.assertIsNone(it.counts["refusals_reported"])
        self.assertEqual(it.counts["refused_matched"], 256)

    def test_a_refusal_without_a_reason_counts_as_a_drop_and_fails_the_refusals_item(self):
        results, it = self.counts(NoReason())
        c = it.counts
        self.assertEqual((c["refused"], c["refused_without_reason"], c["dropped"]), (0, 256, 256))
        self.assertEqual(it.check, "records-returned")
        self.assertIn("256 dropped silently", it.detail)
        info = [i for r in results for i in r.items if i.check == "refusals" and i.file == DERIVED]
        self.assertEqual(info[0].status, "fail")
        self.assertIn("no better than a drop", info[0].detail)
        g = gates.compute_gates(results, ROOT)[0]
        self.assertIn("256 dropped silently", g["headline"])

    def test_partial_refusal_is_credited_in_the_values_item(self):
        class RefusesHalf(RefusingAll):
            def parse(self, raw, fmt):
                out = [{"_adapter": {"refusals": True}}]
                sets = [l for l in raw.decode().splitlines() if l.startswith(("1 ", "2 "))]
                ref = Reference().parse(raw, fmt)
                for k, rec in enumerate(ref):
                    if k % 2:
                        out.append({"_refused": "TleException: Invalid character", "_field": sets[2 * k][2:7]})
                    else:
                        out.append(rec)
                return out
        results, it = self.counts(RefusesHalf())
        self.assertEqual(it.check, "values")
        self.assertEqual((it.counts["loaded"], it.counts["refused_matched"], it.counts["dropped"]), (128, 128, 0))
        self.assertIn("128 refused with a reason (e.g. 'A0405': TleException: Invalid character), 0 silently", it.detail)

    def test_reference_reports_no_refusals(self):
        results, it = self.counts(Reference())
        self.assertEqual((it.counts["refused"], it.counts["dropped"], it.counts["loaded"]), (0, 0, 256))


class EmptyAnswerAndRefusal(unittest.TestCase):
    class RefusesTheBody:
        def parse(self, raw, fmt):
            return [{"_refused": "no TLE lines found", "_input": raw[:40].decode()}]

    def test_a_refusal_of_the_empty_answer_fails(self):
        p = "fixtures/tle-omits-six-digit-objects/raw/last-30-days.tle"
        if not os.path.exists(os.path.join(ROOT, p)):
            self.skipTest("recorded 404 body not on disk")
        results = Runner(self.RefusesTheBody(), root=ROOT).run(case_ids=["tle-omits-six-digit-objects"])
        its = [i for r in results for i in r.items if i.check == "empty-answer-yields-no-records"]
        self.assertTrue(its and all(i.status == "fail" and "refused" in i.detail and "not an unreadable one" in i.detail for i in its), [i.detail for i in its])


class Sgp4AdapterAdoption(unittest.TestCase):
    def test_nine_digit_id_is_refused_with_the_library_reason(self):
        try:
            from tests.adapters.sgp4_adapter import Parser
        except Exception:
            self.skipTest("python-sgp4 not installed")
        p = "fixtures/nine-digit-supgp-launch-nominals/raw/starlink-38381-799501621.csv"
        if not os.path.exists(os.path.join(ROOT, p)):
            self.skipTest("SupGP capture not on disk")
        raw = open(os.path.join(ROOT, p), "rb").read()
        recs, refs, declared = split_refusals(Parser().parse(raw, "csv"))
        self.assertTrue(declared)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["id"], 799501621)
        self.assertIn("339999", refs[0]["reason"])


if __name__ == "__main__":
    unittest.main()
