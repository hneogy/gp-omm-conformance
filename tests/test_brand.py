"""
docs/BRAND.md is the single source for the project's name and for the lines it describes itself with (D-241). These
tests hold the surfaces in this repository to it, word for word (D-242): the README's first screen, the package's
summary, the citation's title, the Action's name and the runner's help text. A line is changed in docs/BRAND.md
first; a surface that drifts from it, or a brand line reworded in one place only, fails here.
"""
import io
import os
import re
import sys
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gpconf import __main__ as cli  # noqa: E402


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def flat(text):
    return " ".join(text.split())


def brand():
    """docs/BRAND.md's quoted lines, by the heading and the label they stand under."""
    text = read("docs", "BRAND.md")
    quotes = [flat(q) for q in re.findall(r"^> (.+)$", text, re.M)]
    return {
        "title": quotes[0], "slogan": quotes[1], "spoken": quotes[2], "written": quotes[3], "about": quotes[4],
        "headline": quotes[5], "short headline": quotes[6], "under the headline": quotes[7],
    }


class TheSource(unittest.TestCase):
    def test_the_lines_are_the_owner_s(self):
        b = brand()
        self.assertEqual(b["headline"], "The satellite catalog passed 99,999. Does your software know?")
        self.assertEqual(b["short headline"], "The satellite catalog passed 99,999. Is your code ready?")
        self.assertEqual(b["slogan"], "Test what your parser actually reads.")
        self.assertEqual(b["about"], "Free test kit: does your satellite software handle catalog numbers above 99,999? Built from real CelesTrak data.")
        self.assertTrue(b["written"].startswith("gpconf is a free test kit that tells you whether your satellite software handles catalog numbers above 99,999"))
        self.assertTrue(b["written"].endswith("built from real CelesTrak data, with every expected answer traced to its source."))
        self.assertEqual(b["title"], "gpconf: a conformance corpus for orbital-data parsers crossing the five-digit catalog-number boundary")

    def test_the_file_is_exported(self):
        self.assertIn("docs/BRAND.md", read("PUBLIC_ALLOWLIST.txt").splitlines())


class TheReadme(unittest.TestCase):
    def setUp(self):
        self.raw = read("README.md")
        self.text = flat(self.raw.replace("**gpconf**", "gpconf"))
        self.b = brand()

    def test_the_first_screen_is_headline_then_sentence_then_install_then_fixes(self):
        self.assertEqual(self.raw.splitlines()[0], "# " + self.b["headline"])
        order = [self.text.index(self.b["headline"]), self.text.index(self.b["written"]), self.text.index("pip install gpconf"),
                 self.text.index("Fixes merged or acted on upstream"), self.text.index("## What gpconf is"), self.text.index("Status: version")]
        self.assertEqual(order, sorted(order))

    def test_the_line_under_the_headline_says_where_the_five_digit_range_ended(self):
        second = flat(self.raw.split("\n\n")[1])
        self.assertEqual(second, self.b["under the headline"])
        self.assertEqual(second, "On 11 July 2026 the catalog assigned number 100000, and every object catalogued since has a six-digit number. "
                                 "The usable five-digit range had already run out at 69,999 (CelesTrak).")
        self.assertNotIn("not 99,999", second)                               # not directly under a headline that says 99,999 (owner)
        self.assertNotIn("five-digit numbers ran to 99,999", self.text)     # the claim D-188 rules out

    def test_nothing_the_readme_opened_with_is_gone(self):
        for kept in ("A conformance corpus for orbital-data parsers crossing the five-digit catalog-number boundary:",
                     "It answers one question for a developer: **does my parser survive the migration?**",
                     "Status: version `", "https://zenodo.org/badge/DOI/10.5281/zenodo.22867654.svg",
                     "See `DECISIONS.md` for the full decision log and `MANIFEST.md` for every case"):
            self.assertIn(kept, flat(self.raw))

    def test_the_fixes_table_links_each_fix(self):
        table = self.raw.split("Fixes merged or acted on upstream")[1].split("## What gpconf is")[0]
        for url in ("https://github.com/brandon-rhodes/python-sgp4/pull/172", "https://github.com/shashwatak/satellite-js/pull/186",
                    "https://github.com/shashwatak/satellite-js/pull/187", "https://github.com/ATTron/astroz/issues/97",
                    "https://github.com/ATTron/astroz/issues/98", "https://github.com/ATTron/astroz/pull/99",
                    "https://github.com/dnwrnr/sgp4/pull/42#issuecomment-5824123874", "https://github.com/dnwrnr/sgp4/pull/46",
                    "https://github.com/csete/gpredict/pull/428"):
            self.assertIn(url, table)
        rows = [line for line in table.splitlines() if line.startswith("| ") and not line.startswith("| library") and not line.startswith("|---")]
        self.assertEqual([r.split(" | ")[0] for r in rows], ["| python-sgp4", "| satellite.js", "| astroz", "| libsgp4", "| Gpredict"])   # Gpredict joined with PR #428, merged 2026-10-08 (D-267, D-269)
        # one rule (owner): a fix is listed when it followed a corpus report and answered it. astroz #102 came from probes,
        # not from a corpus case (site S-051), and SatDump #1221 and CelesTrak #172 have no fix yet.
        self.assertIn("A fix is listed when it followed a report made from the corpus's results and answered it", flat(table))
        for absent in ("astroz/issues/102", "astroz/pull/104", "SatDump", "CelesTrak/fundamentals"):
            self.assertNotIn(absent, table)
        # the cells that expire with a release (the site's HANDOFF.md, "Expiring claims", names them and the check)
        self.assertEqual(table.count("no release carries it yet") + table.count("no release carries them yet"), 3)   # python-sgp4, satellite.js, Gpredict (D-269)

    def test_the_table_s_date_moves_with_each_release(self):
        """"No release carries it yet" is true until python-sgp4 or satellite.js publishes one, and no offline test can
        know that. This one makes the claim expire with the corpus's own releases: the table is dated, and its date may
        not be older than the release date in CITATION.cff. Preparing a release moves that date, this fails, and the
        cells are checked against PyPI and npm before the table's date is moved after it (the check is in the site's
        HANDOFF.md, "Expiring claims")."""
        as_of = re.search(r"Fixes merged or acted on upstream, as of (\d{4}-\d{2}-\d{2})\.", self.raw).group(1)
        released = re.search(r'^date-released: "(\d{4}-\d{2}-\d{2})"$', read("CITATION.cff"), re.M).group(1)
        self.assertGreaterEqual(as_of, released, "the README's table of upstream fixes is older than this release: check its "
                                "'no release carries it yet' cells against PyPI (sgp4) and npm (satellite.js), then move its date")

    def test_the_name_and_the_repository(self):
        self.assertIn("gpconf is the GP/OMM conformance corpus. This repository, `gp-omm-conformance`, holds the corpus and its runner.", self.text)

    def test_the_citation_sentence_uses_the_cited_title(self):
        self.assertIn(self.b["title"] + ", version ", self.text)


class ThePackageAndTheAction(unittest.TestCase):
    def test_the_summary_is_the_about_line(self):
        self.assertIn(f'description = "{brand()["about"]}"', read("pyproject.toml"))

    def test_keywords_and_classifiers_are_declared_and_no_licence_classifier(self):
        toml = read("pyproject.toml")
        self.assertRegex(toml, r'(?m)^keywords = \[.*"Alpha-5".*\]$')
        self.assertIn('"Topic :: Software Development :: Testing"', toml)
        self.assertNotIn("License ::", toml)                     # the licence is an expression (PEP 639)
        self.assertIn('name = "gpconf"', toml)

    def test_the_citation_s_title_and_the_audit_s_wording(self):
        cff = read("CITATION.cff")
        self.assertIn(f'title: "{brand()["title"]}"', cff)
        self.assertIn("v0.1.0 was audited by a separate AI session with no access to the build context", flat(cff))
        self.assertNotIn("independently audited", cff)

    def test_the_action_is_named_gpconf_and_called_by_the_repository(self):
        action = read("action.yml")
        self.assertEqual(action.splitlines()[0], "name: gpconf")
        self.assertIn("Runs a parser against gpconf, the GP/OMM conformance corpus, offline", flat(action))
        self.assertIn('title = f"### gpconf: preset `{preset}`\\n\\n"', read("tools", "action_report.py"))
        self.assertIn("- uses: hneogy/gp-omm-conformance@v", read("README.md"))

    def test_the_help_text_says_what_the_kit_is(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit):
            cli.main(["--help"])
        self.assertIn("gpconf, the GP/OMM conformance corpus. " + brand()["about"], flat(out.getvalue()))


if __name__ == "__main__":
    unittest.main()
