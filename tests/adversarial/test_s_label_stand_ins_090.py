# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Each of SM-26's findings S1, S2, S3 and S6 tied to the corpus's own adapters that stand in for it (0.8.1 list item
3; D-379).

SM-26's adapters stay out of the public export until their permission is confirmed (D-367), so in a clone, an export
or public CI the grader is held to these four findings only by adapters the corpus ships. The map below is the one
`test_own_s_findings_080`'s docstring states; this module holds it: every adapter named there under a label is named
here under the same label, and each fails the case its finding is about. A stand-in that stops failing, or a label
left with no stand-in, fails here by name. S4 and S5 are written in `test_own_s_findings_080` itself.

Written from DECISIONS.md (D-280 to D-282) and the corpus's own adapters; nothing here comes from
tests/adversarial/sm26.py.

Run: python -m unittest tests.adversarial.test_s_label_stand_ins_090"""
import ast
import importlib
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf.runner import Runner  # noqa: E402
from tests.adversarial import sweep  # noqa: E402

OWN_S = os.path.join(ROOT, "tests", "adversarial", "test_own_s_findings_080.py")   # read, not imported: importing it
# would make its empty folder with no tearDownModule to remove it
NO_DATA = ["alpha5-encoding-vectors", "alpha5-tle-derived", "kvn-syntax-variants", "tle-writer-alpha5", "corrupt-input"]
EMPTY = tempfile.mkdtemp(prefix="gpconf-s-labels-empty-")


def tearDownModule():
    if os.path.isdir(EMPTY):
        os.rmdir(EMPTY)


def raw_present():   # as test_adversarial's: N7 needs the provider files of the case it dodges
    return os.path.exists(os.path.join(ROOT, "fixtures", "analyst-objects", "raw", "analyst.csv"))


def redteam(module, cls):
    return lambda: getattr(importlib.import_module(f"tests.adversarial.redteam.{module}"), cls)()


def redteam2(module):
    return lambda: importlib.import_module(f"tests.adversarial.redteam2.{module}").Parser()


# label -> rows of (the name own_s's docstring uses, this row's own name, a maker, the cases run, the case that must
# fail). N7 dodges per input, so it runs beside another case that reads TLE, as in test_adversarial.
STAND_INS = {
    "S1": [("N3WriterPartway", "sweep.N3WriterPartway", sweep.N3WriterPartway, ["tle-writer-alpha5"], "tle-writer-alpha5"),
           ("e02", "redteam e02 Win", redteam("e02", "Win"), ["tle-writer-alpha5"], "tle-writer-alpha5"),
           ("twin_f4_writer_mix", "redteam2 twin_f4_writer_mix", redteam2("twin_f4_writer_mix"), ["tle-writer-alpha5"],
            "tle-writer-alpha5")],
    "S2": [("e01", "redteam e01 Win", redteam("e01", "Win"), ["alpha5-tle-derived"], "alpha5-tle-derived"),
           ("guard_f3_partial_unsup", "redteam2 guard_f3_partial_unsup", redteam2("guard_f3_partial_unsup"),
            NO_DATA, "corrupt-input"),
           ("N7EmptyAnswerDodge", "sweep.N7EmptyAnswerDodge", sweep.N7EmptyAnswerDodge,
            ["tle-omits-six-digit-objects", "corrupt-input"], "tle-omits-six-digit-objects")],
    "S3": [("e03", "redteam e03 Win", redteam("e03", "Win"), ["alpha5-tle-derived"], "alpha5-tle-derived"),
           ("e03", "redteam e03 Twin", redteam("e03", "Twin"), ["alpha5-tle-derived"], "alpha5-tle-derived"),
           ("twin_f1_dup_disagree", "redteam2 twin_f1_dup_disagree", redteam2("twin_f1_dup_disagree"),
            ["alpha5-tle-derived"], "alpha5-tle-derived")],
    "S6": [("e07", "redteam e07 Win", redteam("e07", "Win"), ["corrupt-input"], "corrupt-input")],
}
NEEDS_RAW = {"sweep.N7EmptyAnswerDodge"}


def docstring_map():
    """own_s's docstring, label -> its paragraph, for the four labels held by the corpus's adapters."""
    with open(OWN_S, encoding="utf-8") as f:
        doc = ast.get_docstring(ast.parse(f.read()))
    doc = doc.split("Two were held only in part")[0]
    parts = re.split(r"\n  (S\d) \(", doc)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


class TheMapIsTheDocstrings(unittest.TestCase):
    def test_the_same_four_labels(self):
        self.assertEqual(sorted(docstring_map()), ["S1", "S2", "S3", "S6"])
        self.assertEqual(sorted(STAND_INS), ["S1", "S2", "S3", "S6"])

    def test_every_stand_in_is_named_under_its_label_and_no_other(self):
        doc = docstring_map()
        for label, rows in STAND_INS.items():
            for token, name, *_ in rows:
                with self.subTest(label=label, name=name):
                    self.assertRegex(doc[label], rf"\b{token}\b")
                    self.assertEqual([lb for lb, p in doc.items() if re.search(rf"\b{token}\b", p)], [label])

    def test_the_names_are_unique(self):
        names = [name for rows in STAND_INS.values() for _, name, *_ in rows]
        self.assertEqual(len(names), len(set(names)))


class EachStandInFailsItsCase(unittest.TestCase):
    def test_each_fails_the_case_its_finding_is_about(self):
        for label, rows in STAND_INS.items():
            for _, name, make, cases, must_fail in rows:
                with self.subTest(label=label, name=name, case=must_fail):
                    if name in NEEDS_RAW and not raw_present():
                        self.skipTest("provider files absent (a fresh clone or an export)")
                    data = None if name in NEEDS_RAW else EMPTY   # N7's case reads the provider files where they are
                    results = {r.case_id: r for r in Runner(make(), root=ROOT, data=data, fetch_hints=False).run(case_ids=cases)}
                    self.assertEqual(results[must_fail].status, "fail")

    def test_every_label_keeps_a_stand_in_that_needs_no_provider_data(self):
        for label, rows in STAND_INS.items():
            with self.subTest(label=label):
                self.assertTrue([r for r in rows if r[1] not in NEEDS_RAW])


if __name__ == "__main__":
    unittest.main()
