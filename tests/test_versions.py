# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
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
        "README.md citation": re.search(r"catalog-number boundary, version ([0-9][^,]*),\s", readme).group(1),
    }


class VersionConstants(unittest.TestCase):
    def test_every_constant_carries_one_version(self):
        versions = found()
        self.assertEqual(len(set(versions.values())), 1, versions)
        self.assertRegex(next(iter(versions.values())), r"^\d+\.\d+\.\d+$")

    def test_the_citation_date_is_the_same_in_both_places(self):
        cff = re.search(r'(?m)^date-released: "([^"]+)"', read("CITATION.cff")).group(1)
        readme = re.search(r"catalog-number boundary, version [^,]+,\s+(\d{4}-\d{2}-\d{2}),", read("README.md")).group(1)
        self.assertEqual(cff, readme)

    def test_the_versioning_rule_reads_the_same_in_both_places(self):
        # decision 1 of 2026-09-25: an additive protocol change is a minor version; the README and the changelog's
        # preamble both state the rule
        for rel in ("README.md", "CHANGELOG.md"):
            text = " ".join(read(rel).split())
            self.assertIn("refreshed live snapshots, added cases, or an additive protocol change", text, rel)


# The examples a user copies: the Action's tag and the Docker image's version. Each names the release being shipped,
# so a user who copies one gets the corpus whose README they are reading. 0.9.0 shipped the README's Action example
# still at @v0.8.0 (the owner's finding, 2026-11-15); this holds every such pin to the package version.
PIN_FILES = ("README.md", "docs/ONBOARDING.md", "docs/ADAPTERS.md", "docs/MIGRATION.md", "docs/BRAND.md",
             "docs/guides", "docker/Dockerfile", "pytest-gpconf/README.md")
PINS = (
    (r"gp-omm-conformance@v?(\d+\.\d+(?:\.\d+)?)", "the Action's tag"),
    (r"GPCONF_VERSION=(\d+\.\d+(?:\.\d+)?)", "the Docker build's version"),
    (r"\bgpconf:(\d+\.\d+(?:\.\d+)?)", "the Docker image's tag"),
)


def pin_files():
    out = []
    for rel in PIN_FILES:
        path = os.path.join(ROOT, rel)
        if os.path.isdir(path):
            for dirpath, _, names in os.walk(path):
                out += [os.path.relpath(os.path.join(dirpath, n), ROOT) for n in sorted(names) if n.endswith(".md")]
        elif os.path.exists(path):
            out.append(rel)
    return out


def pins(text):
    """-> [(what, version)] for every version pin in an example."""
    return [(what, m.group(1)) for rx, what in PINS for m in re.finditer(rx, text)]


class ExamplePins(unittest.TestCase):
    def setUp(self):
        self.version = re.search(r'(?m)^__version__ = "([^"]+)"', read("gpconf/__init__.py")).group(1)

    def test_the_readmes_action_example_pins_this_release(self):
        found_ = [v for what, v in pins(read("README.md")) if what == "the Action's tag"]
        self.assertTrue(found_, "the README has no `uses: hneogy/gp-omm-conformance@v...` example")
        self.assertEqual(set(found_), {self.version})

    def test_every_example_pin_names_this_release(self):
        wrong = [(rel, what, v) for rel in pin_files() for what, v in pins(read(rel)) if v != self.version]
        self.assertEqual(wrong, [], f"example pins that are not {self.version}")

    def test_the_pin_reader_finds_the_forms_it_holds(self):
        text = ("- uses: hneogy/gp-omm-conformance@v0.8.0\n"
                "docker build --build-arg GPCONF_VERSION=0.9.0 -t gpconf:0.9.0 docker/\n"
                "uses: hneogy/gp-omm-conformance@<tag>")
        self.assertEqual(pins(text), [("the Action's tag", "0.8.0"), ("the Docker build's version", "0.9.0"),
                                      ("the Docker image's tag", "0.9.0")])


if __name__ == "__main__":
    unittest.main()
