# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The second blind audit's adapters against the current runner (D-311 to D-313).

A fresh session audited the gpconf 0.7.0 release candidate on 2026-10-10 from its wheel and sdist alone. It found no
compared value that escapes: each of its seven wins avoided comparison through a documented outcome. One is closed
(F1: a record returned more often than the input holds it now fails). The other six stand by design, and what this
file holds them to is that the run SAYS so: an item that skipped and a field that was never returned show in the
case's status line, and a run on five cases says it graded five. Every twin and every guard fails as it did.

Run: python -m unittest tests.adversarial.test_redteam2"""
import importlib
import os
import sys
import tempfile
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf.__main__ import graded_line, inside_line  # noqa: E402
from gpconf.runner import CaseResult, Runner, annotation_totals  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402

NO_DATA = ["alpha5-encoding-vectors", "alpha5-tle-derived", "kvn-syntax-variants", "tle-writer-alpha5", "corrupt-input"]
EMPTY = tempfile.mkdtemp(prefix="gpconf-redteam2-empty-")


def adapter(module):
    return importlib.import_module(f"tests.adversarial.redteam2.{module}").Parser()


def run(parser, cases=NO_DATA):
    return {r.case_id: r for r in Runner(parser, root=ROOT, data=EMPTY, fetch_hints=False).run(case_ids=cases)}


def failing(results):
    return sorted(c for c, r in results.items() if r.status == "fail")


class TheOneThatIsClosed(unittest.TestCase):
    def test_f1_a_record_returned_twice_fails(self):            # D-311, reversing D-281's second half
        r = run(adapter("win_f1_dup_exact"))
        self.assertEqual(failing(r), ["alpha5-tle-derived", "corrupt-input", "kvn-syntax-variants"])
        (item,) = [i for i in r["alpha5-tle-derived"].items if i.check == "values" and (i.file or "").endswith("alpha5-A-100000-saramago-first.tle")]
        self.assertEqual(item.status, "fail")
        self.assertIn("id 100000: returned 2 times where the input holds it once (D-311)", item.detail)
        self.assertEqual((item.counts["duplicate_copies"], item.counts["extra"], item.counts["loaded"]), (1, 1, 1))   # the vocabulary stands
        # the corrupt-input case holds each id once too: the edited files' neighbours come back twice
        self.assertTrue(any("returned 2 times where the input holds it once (D-311)" in i.detail for i in r["corrupt-input"].items if i.status == "fail"))

    def test_f1_an_input_that_holds_an_id_twice_may_return_it_twice(self):
        """The rule is 'more copies than the input holds', not 'any duplicate': a live file may carry an id twice,
        and a parser that returns both is right. No frozen input does, so the rule is held here on the comparison."""
        runner = Runner(Reference(), root=ROOT, data=EMPTY, fetch_hints=False)
        path = os.path.join(ROOT, "derived", "alpha5-tle", "alpha5-A-100000-saramago-first.tle")
        (rec,) = runner.parse(path, "tle")
        oracle = {100000: {k: v for k, v in rec.items() if not k.startswith("_")}}
        for held, status in (({100000: 2}, "pass"), (None, "fail"), ({100000: 1}, "fail")):
            res = CaseResult("x", "x")
            runner.compare_values(res, path, "tle", "live", [rec, dict(rec)], oracle, held=held)
            (item,) = [i for i in res.items if i.check == "values"]
            self.assertEqual(item.status, status, held)
        res = CaseResult("x", "x")
        runner.compare_values(res, path, "tle", "live", [rec, dict(rec), dict(rec)], oracle, held={100000: 2})
        self.assertIn("returned 3 times where the input holds it 2 times (D-311)", [i for i in res.items if i.check == "values"][0].detail)

    def test_f1_the_reference_returns_no_surplus_copy(self):
        for r in run(Reference()).values():
            self.assertEqual(sum((i.counts or {}).get("duplicate_copies", 0) for i in r.items), 0, r.case_id)


class WhatTheReviewOfTheRuleFound(unittest.TestCase):
    """D-311 was read by a separate reviewer before it was committed. It found four places where a surplus copy still
    got through; each has its wrong-on-purpose adapter here, and the reference adapter is the twin of all four."""

    def test_a_record_without_an_id_returned_twice_fails(self):
        class Dup(Reference):                                    # the KVN file whose NORAD_CAT_ID keyword is absent
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                return out + [dict(r) for r in out if "_refused" not in r and r.get("norad_cat_id") is None]
        r = run(Dup(), ["kvn-syntax-variants"])
        self.assertEqual(failing(r), ["kvn-syntax-variants"])
        (item,) = [i for i in r["kvn-syntax-variants"].items if i.status == "fail"]
        self.assertIn("v05-", item.file)
        self.assertIn("returned 2 times where the input holds it once (D-311)", item.detail)
        self.assertEqual(item.counts["duplicate_copies"], 1)

    def test_a_copy_outside_a_partial_oracle_fails(self):
        """One snapshot file is compared on a subset of its records (27 of 11,141). An id outside the subset is not
        compared, but returned twice where the file holds it once it is a surplus copy."""
        runner = Runner(Reference(), root=ROOT, data=EMPTY, fetch_hints=False)
        path = os.path.join(ROOT, "derived", "alpha5-tle", "alpha5-A-last-30-days-snapshot.tle")
        recs = runner.parse(path, "tle")
        inside, outside = recs[0], recs[1]
        oracle = {inside["norad_cat_id"]: {k: v for k, v in inside.items() if not k.startswith("_")}}
        in_file = {r["norad_cat_id"]: 1 for r in recs}
        for parsed, status in ((recs, "pass"), (recs + [dict(outside)], "fail")):
            res = CaseResult("x", "x")
            runner.compare_values(res, path, "tle", "snapshot", parsed, oracle, partial=True, held_in_file=in_file)
            (item,) = [i for i in res.items if i.check == "values"]
            self.assertEqual(item.status, status)
        self.assertIn("outside the compared subset returned more often than the input holds it", item.detail)

    def test_a_copy_in_the_edited_files_only_fails_in_its_own_words(self):
        # the corrupt-input files hold each id once: outcomes and counts are those of a parser that returned one copy
        once = run(Reference(), ["corrupt-input"])["corrupt-input"]

        class DupEdited(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                edited = fmt == "tle" and any("_refused" in r for r in out)       # the files with a corrupt record
                return out + [dict(r) for r in out if "_refused" not in r] if edited else out
        r = run(DupEdited(), ["corrupt-input"])["corrupt-input"]
        self.assertEqual(r.status, "fail")
        fails = [i for i in r.items if i.status == "fail" and i.check == "corrupt-input-neighbours-load"]
        self.assertEqual(len(fails), 3)                                            # the three files the reference refuses a record of
        for i in fails:
            self.assertIn("returned 2 times where the input holds it once (D-311)", i.detail)
            self.assertNotIn("changed by the corrupt input", i.detail)            # it is not the edit's doing
            self.assertIn("2 of 2 valid sets", i.detail)                           # the sets still loaded
        loaded = {i.file: i.counts["loaded"] for i in once.items if i.counts}
        self.assertEqual({i.file: i.counts["loaded"] for i in r.items if i.counts}, loaded)   # no count of outcomes moves

    def test_a_copy_in_the_unedited_comparison_file_only_fails(self):
        class Dup(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                clean = fmt == "tle" and sum(1 for r in out if "_refused" not in r) == 3 and not any("_refused" in r for r in out)
                return out + [dict(r) for r in out] if clean else out
        r = run(Dup(), ["corrupt-input"])["corrupt-input"]
        fails = [i for i in r.items if i.status == "fail"]
        self.assertTrue(any(i.check == "values" and i.file.endswith("unedited-sets.tle") and "(D-311)" in i.detail for i in fails), [(i.check, i.file) for i in fails])


class ByDesignAndSaidSo(unittest.TestCase):
    """D-313. These six end with no failing case, as the report found, and that stands: each avoids comparison through
    an outcome the adapter guide documents. What changed is that the run no longer reads as clean (D-312)."""

    def test_f2_a_field_never_returned_shows_in_the_status(self):
        r = run(adapter("win_f2_omit_objid"))
        self.assertEqual(failing(r), [])
        self.assertEqual(r["alpha5-tle-derived"].status, "pass")                      # the status is untouched
        self.assertEqual(r["alpha5-tle-derived"].status_text(), "pass (5 field gaps)")
        self.assertEqual(r["alpha5-tle-derived"].as_dict()["annotations"], {"items_skipped": 0, "field_gaps": 5})
        self.assertIn("field gap", inside_line(list(r.values())))

    def test_f3_a_format_answered_unsupported_shows_in_the_status(self):
        r = run(adapter("win_f3_xml_unsup"))
        self.assertEqual(failing(r), [])
        self.assertEqual(r["corrupt-input"].status_text(), "pass (1 item skipped)")
        self.assertEqual(annotation_totals(list(r.values()))["items_skipped"], 1)
        self.assertIn("1 item skipped because the parser answered unsupported or has no hook for the check", inside_line(list(r.values())))

    def test_f4_a_writer_answered_unsupported_skips_its_case(self):
        r = run(adapter("win_f4_writer_unsup"))
        self.assertEqual(failing(r), [])
        self.assertEqual(r["tle-writer-alpha5"].status, "skip")                       # a whole-case skip is already the status
        self.assertEqual(r["tle-writer-alpha5"].status_text(), "skip")

    def test_f5_a_hook_answered_unsupported_shows_in_the_status(self):
        r = run(adapter("win_f5_encode_unsup"))
        self.assertEqual(failing(r), [])
        self.assertEqual(r["alpha5-encoding-vectors"].status_text(), "pass (1 item skipped)")

    def test_f6_writer_secondary_fields_are_information(self):   # D-095: fitting tools regenerate them
        r = run(adapter("win_f6_writer_secondary"))
        self.assertEqual(failing(r), [])
        (info,) = [i for i in r["tle-writer-alpha5"].items if i.check == "tle-writer-secondary-fields"]
        self.assertEqual(info.status, "info")
        self.assertIn("zeroed", info.detail)

    def test_f7_a_record_dropped_everywhere_voids_the_case_and_never_passes_it(self):   # D-175, D-294
        r = run(adapter("win_f7_corrupt_void"))
        self.assertEqual(failing(r), [])
        self.assertEqual(r["corrupt-input"].status, "not-exercised")
        self.assertEqual(annotation_totals(list(r.values()))["cases_graded"], 4)

    def test_a_clean_run_carries_no_annotation(self):
        r = run(Reference())
        self.assertEqual([x.status_text() for x in r.values()], ["pass"] * 5)
        self.assertIsNone(inside_line(list(r.values())))
        self.assertNotIn("annotations", r["corrupt-input"].as_dict())


class TheRunSaysHowMuchItGraded(unittest.TestCase):          # D-312
    def test_five_of_eighteen_offline(self):
        results = Runner(Reference(), root=ROOT, data=EMPTY, fetch_hints=False).run()
        self.assertEqual(graded_line(results), "5 of 18 cases graded offline; not a full conformance result.")

    def test_a_folder_with_only_the_satcat_files_is_not_offline(self):
        """The data check's items are information, so nothing in them says a provider file was read; the case's
        record of the sources it loaded does (found by the review of D-311)."""
        import shutil
        raw = os.path.join(ROOT, "fixtures", "satcat-70000-cutoff", "raw")
        names = [n for n in ("satcat-25544.json", "satcat-25544.csv") if os.path.exists(os.path.join(raw, n))]
        if not names:
            self.skipTest("the SATCAT provider files are not on disk (a fresh clone or an export)")
        data = tempfile.mkdtemp(prefix="gpconf-satcat-only-")
        try:
            os.makedirs(os.path.join(data, "fixtures", "satcat-70000-cutoff", "raw"))
            for n in names:
                shutil.copy(os.path.join(raw, n), os.path.join(data, "fixtures", "satcat-70000-cutoff", "raw", n))
            results = Runner(Reference(), root=ROOT, data=data, fetch_hints=False).run()
            self.assertEqual(graded_line(results), "5 of 18 cases graded; 11 need fetched data: not a full conformance result.")
        finally:
            shutil.rmtree(data, ignore_errors=True)

    def test_nothing_is_said_when_no_case_lacks_data(self):
        results = Runner(Reference(), root=ROOT, data=EMPTY, fetch_hints=False).run(case_ids=NO_DATA)
        self.assertIsNone(graded_line(results))


class TwinsAndGuardsStillFail(unittest.TestCase):
    TWINS = {"twin_f1_dup_disagree": 3, "twin_f2_wrong_objid": 3, "twin_f3_xml_wrong": 1, "twin_f4_writer_mix": 1,
             "twin_f5_encode_wrong": 1, "twin_f6_writer_primary": 1, "twin_f7_corrupt_drop": 1}
    GUARDS = {"guard_empty": 1, "guard_epochtext": 1, "guard_exit": 2, "guard_f3_partial_unsup": 1, "guard_intfloat": 3}

    def test_every_twin_fails_as_the_report_has_it(self):
        for m, n in self.TWINS.items():
            with self.subTest(m=m):
                self.assertEqual(len(failing(run(adapter(m)))), n)

    def test_every_guard_fails_as_the_report_has_it(self):
        for m, n in self.GUARDS.items():
            with self.subTest(m=m):
                self.assertEqual(len(failing(run(adapter(m)))), n)

    def test_all_nineteen_are_here(self):
        here = sorted(f[:-3] for f in os.listdir(os.path.join(ROOT, "tests", "adversarial", "redteam2")) if f.endswith(".py") and f != "__init__.py")
        self.assertEqual(len(here), 19)
        self.assertEqual(sorted(list(self.TWINS) + list(self.GUARDS) + [f"win_f{i}_{s}" for i, s in enumerate(
            ("dup_exact", "omit_objid", "xml_unsup", "writer_unsup", "encode_unsup", "writer_secondary", "corrupt_void"), 1)]), here)


if __name__ == "__main__":
    unittest.main()
