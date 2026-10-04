"""D-248: "TLE set" and "line" are used strictly, and the two figures the corpus quotes most are counts of sets.

A TLE set is one object's lines: line 1 and line 2, with the name line before them where the format has one. A line is
one line. The corpus ships 604 derived Alpha-5 TLE sets, which are 1,208 element lines, 1,812 lines with the name
lines; and its rendering rules were derived from 304 TLE sets fetched from CelesTrak, each with its OMM record. Both
were called "lines" in places, which understates the first by half and misstates what was compared in the second.

These tests count the derived files, so that the figures are measured and not copied, and fail on either figure said
of lines in the files the corpus writes today. The auditor's text (AUDIT.md), the decision log and the dated research
and planning notes are records and are left as written; the frozen expected.json files keep the prose they were
generated with, which the runner does not read.

Run: python -m unittest tests.test_sets_and_lines"""
import glob
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# a figure followed, after at most a few describing words, by "lines": "604 derived Alpha-5 lines", "304 of 304 lines",
# "304 CelesTrak TLE lines", "604 TLE lines"
SAID_OF_LINES = re.compile(r"\b(?:604|304)(?: of 304)?(?: (?:derived|Alpha-5|CelesTrak|TLE|fetched|provider|rendered))* lines\b")
SHORTHAND = re.compile(r"\b304/304\b")
CURRENT = (["README.md", "MANIFEST.md", "CITATION.cff", "NOTICE", "docs/WRITERS.md", "docs/ADAPTERS.md", "docs/BRAND.md",
            "tools/cases.py", "tools/make_manifest.py", "tools/crosscheck.py", "gpconf/tle.py"]
           + sorted(os.path.relpath(p, ROOT).replace(os.sep, "/") for p in glob.glob(os.path.join(ROOT, "fixtures", "*", "case.md"))))


def read(rel):
    with open(os.path.join(ROOT, *rel.split("/")), encoding="utf-8", newline="") as f:
        return f.read()


def flat(text):
    return " ".join(text.split())


class TheDerivedFiles(unittest.TestCase):
    """The figures, counted from the four files the corpus ships."""

    @classmethod
    def setUpClass(cls):
        cls.files = sorted(glob.glob(os.path.join(ROOT, "derived", "alpha5-tle", "*.tle")))
        cls.lines = [line for p in cls.files for line in read(os.path.relpath(p, ROOT).replace(os.sep, "/")).splitlines()]

    def test_604_sets_are_1208_element_lines_and_1812_lines(self):
        self.assertEqual(len(self.files), 4)
        line1 = [x for x in self.lines if x.startswith("1 ")]
        line2 = [x for x in self.lines if x.startswith("2 ")]
        self.assertEqual((len(line1), len(line2)), (604, 604))
        self.assertEqual(len(line1) + len(line2), 1208)
        self.assertEqual(len(self.lines), 1812)                         # each set has its name line
        self.assertTrue(all(len(x) == 69 for x in line1 + line2))

    def test_257_sets_carry_the_letter_a_and_347_the_letter_t(self):
        letters = [x[2] for x in self.lines if x.startswith("1 ")]
        self.assertEqual((letters.count("A"), letters.count("T"), len(letters)), (257, 347, 604))
        self.assertEqual(len({x[2:7] for x in self.lines if x.startswith("1 ")}), 603)   # 270449 is there twice


class TheWords(unittest.TestCase):
    def test_neither_figure_is_said_of_lines(self):
        for rel in CURRENT:
            text = flat(read(rel))
            self.assertEqual(SAID_OF_LINES.findall(text), [], rel)
            self.assertEqual(SHORTHAND.findall(text), [], f"{rel}: write '304 of 304 fetched TLE sets'")

    def test_the_pattern_catches_what_was_written_before(self):
        for was in ("604 derived Alpha-5 lines (letters A and T)", "validated (304 of 304 lines byte for byte)",
                    "reproducing 304 of 304 CelesTrak TLE lines byte for byte", "604 TLE lines it renders", "all 604 lines correctly",
                    "the 604 derived lines"):
            self.assertTrue(SAID_OF_LINES.search(was), was)
        for fine in ("604 derived Alpha-5 TLE sets, 1,208 element lines", "304 of 304 fetched TLE sets byte for byte: the name line, line 1 and line 2",
                     "604 Alpha-5 TLE sets, each a name line, line 1 and line 2 (1,208 element lines, 1,812 lines in the four files)"):
            self.assertIsNone(SAID_OF_LINES.search(fine), fine)

    def test_the_readme_says_sets_with_their_lines(self):
        readme = flat(read("README.md"))
        self.assertIn("| `alpha5-tle-derived` | 604 derived Alpha-5 TLE sets, 1,208 element lines (letters A and T), from real CelesTrak records |", readme)
        self.assertIn("was validated (304 of 304 fetched TLE sets byte for byte: the name line, line 1 and line 2 of each)", readme)
        self.assertIn("by reproducing 304 of 304 fetched CelesTrak TLE sets byte for byte", readme)
        self.assertIn('The corpus says "TLE set" for an object\'s lines and "line" for one line: 604 derived Alpha-5 TLE sets, 304 fetched TLE sets (D-248).', readme)

    def test_the_case_document_gives_all_three_counts(self):
        doc = read("fixtures/alpha5-tle-derived/case.md")
        self.assertIn("604 Alpha-5 TLE sets, each a name line, line 1 and line 2 (1,208 element lines, 1,812 lines in the four files): "
                      "257 with letter A (ids 100000-100789), 347 with letter T (ids 270000-270449)", doc)
        self.assertIn("from 304 TLE sets fetched from CelesTrak, each with its OMM record", doc)

    def test_the_sample_of_304_is_said_with_what_it_is_made_of(self):
        doc = read("fixtures/tle-vs-omm-precision-loss/case.md")
        self.assertIn("a sample of 304 TLE sets fetched from CelesTrak on 2026-09-21, each with the OMM record of the same object "
                      "(219 analyst, 79 decaying, 2 SupGP, 4 single objects)", doc)
        self.assertEqual(219 + 79 + 2 + 4, 304)
        self.assertIn("reproduced 304 of 304 TLE sets byte for byte, the name line, line 1 and line 2 of each (912 lines)", doc)
        self.assertEqual(304 * 3, 912)
        self.assertIn("every TLE and 2LE set CelesTrak served in the corpus's captures, 604 of them, plus the 604 derived Alpha-5 TLE sets, 1,208 sets in all", doc)


if __name__ == "__main__":
    unittest.main()
