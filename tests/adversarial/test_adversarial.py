# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Each adversarial adapter behaves exactly as designed against the current runner (D-287; issue #1).

A suspect must FAIL the case it once passed (or, for the two whole-field omissions, show the visible gap
D-284 rules for them); every twin and control must fail; the reference adapter stays exact. Data-needing
checks skip in a public clone, where the raw fixtures are absent, like the rest of the suite.

Run: python -m unittest tests.adversarial.test_adversarial"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf.runner import Runner  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from tests.adversarial import sm26, sweep  # noqa: E402

NO_DATA = ["alpha5-encoding-vectors", "alpha5-tle-derived", "kvn-syntax-variants", "tle-writer-alpha5", "corrupt-input"]


def raw_present():
    return os.path.exists(os.path.join(ROOT, "fixtures", "analyst-objects", "raw", "analyst.csv"))


def run(parser, cases=NO_DATA):
    return Runner(parser, root=ROOT, fetch_hints=False).run(case_ids=cases)


def failing(results):
    return sorted(r.case_id for r in results if r.status == "fail")


def gap_items(results):
    return [i for r in results for i in r.items if i.check == "fields-not-returned"]


class Suspects(unittest.TestCase):
    """The adapters that passed with zero fails on gpconf 0.6.1 (SM-26's run and the corpus's reproduction)."""

    def test_s1_writer_dodge_fails_the_writer_case(self):
        self.assertIn("tle-writer-alpha5", failing(run(sm26.S1WriterDodge())))          # D-280

    def test_s2_file_dodge_fails_where_it_read_the_format(self):
        self.assertEqual(failing(run(sm26.S2FileDodge())), ["alpha5-tle-derived", "corrupt-input"])   # D-280

    def test_s3_duplicate_tail_fails(self):
        self.assertEqual(failing(run(sm26.S3DuplicateTail())), ["alpha5-tle-derived", "corrupt-input", "kvn-syntax-variants"])   # D-281; corrupt-input since D-299 grades its unedited OMM files

    def test_s4_split_decoder_fails_on_the_synthetic_letters(self):
        self.assertIn("alpha5-tle-derived", failing(run(sm26.S4SplitDecoder())))        # D-286

    def test_s5_non_integer_ids_fail(self):
        for a in (sm26.S5FloatIds(), sm26.S5StrIds()):
            self.assertIn("alpha5-tle-derived", failing(run(a)))                        # D-283

    def test_s6_stray_refusal_fails(self):
        self.assertEqual(failing(run(sm26.S6StrayRefusal())), ["corrupt-input"])        # D-282

    def test_n2_invented_metadata_fails(self):
        self.assertIn("alpha5-tle-derived", failing(run(sweep.N2MetaInvention())))      # D-285

    def test_n3_writer_partway_fails_and_keeps_the_graded_output(self):
        results = run(sweep.N3WriterPartway())
        self.assertIn("tle-writer-alpha5", failing(results))                            # D-280
        (case,) = [r for r in results if r.case_id == "tle-writer-alpha5"]
        detail = " | ".join(i.detail for i in case.items)
        self.assertIn("unsupported for all of its records or none", detail)
        self.assertIn("mean_motion", detail)                                            # the wrong lines stayed graded

    def test_n7_per_input_dodge_fails_across_the_run(self):
        results = run(sweep.N7EmptyAnswerDodge(), ["tle-omits-six-digit-objects", "corrupt-input"])
        if not raw_present():
            self.skipTest("provider files absent (public clone)")
        self.assertEqual(failing(results), ["tle-omits-six-digit-objects"])             # D-280, run-wide

    def test_n5_class_key_drop_shows_the_gap(self):
        if not raw_present():
            self.skipTest("provider files absent (public clone)")
        results = run(sweep.N5ClassKeyDrop(), ["supgp-celestrak-classification-c"])
        self.assertEqual(failing(results), [])
        self.assertTrue(gap_items(results), "the dropped field must be a visible gap (D-284)")

    def test_n1_whole_field_omission_is_a_visible_gap_never_a_clean_pass(self):
        results = run(sweep.N1ElsetKeyDrop())
        self.assertEqual(failing(results), [])
        gaps = gap_items(results)
        self.assertTrue(gaps, "the omitted fields must show as a gap (D-284)")
        self.assertTrue(all("element_set_no" in i.detail for i in gaps))

    def test_n8_omission_cannot_hide_a_wrong_value(self):
        self.assertIn("alpha5-tle-derived", failing(run(sweep.N8OmissionHidesWrong())))  # D-284


class TwinsAndControls(unittest.TestCase):
    """The same bugs without their hatches, and the ordinary bugs: all fail, before the fixes and after."""

    def test_every_twin_fails(self):
        for a in (sm26.S1WriterDodgeTwin, sm26.S2FileDodgeTwin, sm26.S3DuplicateHead, sm26.S4SplitDecoderTwin,
                  sm26.S5FloatIdsHook, sm26.S6SilentDrop, sweep.N1ElsetKeyDropTwin, sweep.N3WriterPartwayTwin):
            with self.subTest(a.__name__):
                self.assertTrue(failing(run(a())), a.__name__)

    def test_every_control_fails(self):
        for a in (sm26.C1NoIOSkip, sm26.C2OffByOne, sm26.C3Pivot58, sm26.C4NanId, sm26.C5Crash, sm26.C6Lenient, sm26.C7PlausibleWrong):
            with self.subTest(a.__name__):
                self.assertTrue(failing(run(a())), a.__name__)

    def test_n5_twin_fails(self):
        if not raw_present():
            self.skipTest("provider files absent (public clone)")
        self.assertEqual(failing(run(sweep.N5ClassKeyDropTwin(), ["supgp-celestrak-classification-c"])), ["supgp-celestrak-classification-c"])


class TheReference(unittest.TestCase):
    def test_the_reference_stays_exact_with_no_gaps(self):
        results = run(Reference())
        self.assertEqual(failing(results), [])
        self.assertEqual(gap_items(results), [])
        self.assertEqual({r.status for r in results}, {"pass"})
