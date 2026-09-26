"""D-159, v0.3.0 stage 8: every version constant agrees, so that the release step's bump cannot miss one.

The version is set by hand in four places, gpconf/__init__.py, pyproject.toml, tools/make_manifest.py (CORPUS_VERSION)
and CITATION.cff, and stated in two sentences of the README, its status line and its citation; manifest.json and
MANIFEST.md are generated from CORPUS_VERSION. The package version is the corpus version (the runner prints both), so
all of them carry one number. Mentions of earlier versions (the changelog's headings, DECISIONS.md, the earlier DOIs)
are history and are not read here."""
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def found():
    """-> {where: the version it carries}."""
    readme = read("README.md")
    return {
        "gpconf/__init__.py": re.search(r'(?m)^__version__ = "([^"]+)"', read("gpconf/__init__.py")).group(1),
        "pyproject.toml": re.search(r'(?m)^version = "([^"]+)"', read("pyproject.toml")).group(1),
        "tools/make_manifest.py CORPUS_VERSION": re.search(r'(?m)^CORPUS_VERSION = "([^"]+)"', read("tools/make_manifest.py")).group(1),
        "CITATION.cff": re.search(r'(?m)^version: "([^"]+)"', read("CITATION.cff")).group(1),
        "manifest.json (generated)": json.loads(read("manifest.json"))["corpus_version"],
        "MANIFEST.md (generated)": re.match(r"# Corpus manifest \(([^)]+)\)", read("MANIFEST.md")).group(1),
        "README.md status line": re.search(r"Status: version `([^`]+)`", readme).group(1),
        "README.md citation": re.search(r"gp-omm-conformance, version ([0-9][^,]*), ", readme).group(1),
    }


class VersionConstants(unittest.TestCase):
    def test_every_constant_carries_one_version(self):
        versions = found()
        self.assertEqual(len(set(versions.values())), 1, versions)
        self.assertRegex(next(iter(versions.values())), r"^\d+\.\d+\.\d+$")

    def test_the_citation_date_is_the_same_in_both_places(self):
        cff = re.search(r'(?m)^date-released: "([^"]+)"', read("CITATION.cff")).group(1)
        readme = re.search(r"gp-omm-conformance, version [^,]+, (\d{4}-\d{2}-\d{2}),", read("README.md")).group(1)
        self.assertEqual(cff, readme)

    def test_the_versioning_rule_reads_the_same_in_both_places(self):
        # decision 1 of 2026-09-25: an additive protocol change is a minor version; the README and the changelog's
        # preamble both state the rule
        for rel in ("README.md", "CHANGELOG.md"):
            text = " ".join(read(rel).split())
            self.assertIn("refreshed live snapshots, added cases, or an additive protocol change", text, rel)


if __name__ == "__main__":
    unittest.main()
