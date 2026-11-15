# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""D-155, v0.3.0 stage 4: harnesses/, the recipes for the five libraries of the one-off runs that cannot be presets; and, since
D-216, a sixth recipe of another kind, Vallado's SGP4 C++ as CelesTrak publishes it.

Each recipe folder holds exactly its harness files and a README that names the pinned commits in full, the project's
licence, and says it is best-effort, not installable by pip, and tied to what may break silently. SatDump follows
D-152: its harnesses and the list of symbol names, never a stand-in file, and no recipe source defines any of those
symbols. Two checks run only in the private repository, where the one-off runs' originals are: the copies match them,
and the SatDump list names exactly the symbols the corpus's own stand-ins defined."""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = os.path.join(ROOT, "harnesses")
ORIGINALS = os.path.join(ROOT, "docs", "handoff", "batch-g")

RECIPES = {
    "libsgp4": {"files": {"README.md", "harness.cpp", "vectors.cpp", "common.h"}, "licence": "Apache-2.0",
                "commits": ["661e057a5d369d5ee424676cf1d69cbead95ff2c", "2b8d14139fa266cdf57cb52ec9e1dfa041ee343d", "c6ebb90625b43d7f6c6eb38b386f343d3cfe03a6"]},
    "gpredict": {"files": {"README.md", "harness.c", "stubs/glib.h", "stubs/glib/gprintf.h"}, "licence": "GPL-2.0",
                 "commits": ["c9fa018f2f16bff6dd1c5c51befb8188fe5a5e35"]},
    "satdump": {"files": {"README.md", "harness.cpp", "harness-rel.cpp"}, "licence": "GPL-3.0",
                "commits": ["f3d82adbfe04e57c596b93479d687f4b830ee26c", "7aef0fe8441bc3eb440b1b6ba053556da5e40991"]},
    "astroz": {"files": {"README.md", "harness.zig", "vectors.zig", "common.zig"}, "licence": ("GPL-3.0", "MIT"),
               "commits": ["d558933ec3a9c9ee826eb8de665b6e5d229ebecb", "67ca74c8313c5c42159217e2bbddfaedad07e0cd"]},
    "gods-eye-view": {"files": {"README.md", "harness.mjs", "register.mjs", "cesium-hook.mjs", "cesium-stub.mjs"}, "licence": "MIT",
                      # D-221: pinned to release v0.2.1; ce671ce, the first two rounds' commit, stays named beside it
                      "commits": ["aa16b7c3b0166a89d8c7a6089e0aff53a22faaee", "ce671ce500a393be27e3cbb2a08799fbca9b6e28"]},
    # D-216: the reference reader itself. The repository is AGPL-3.0 and its NOTICE, which gives the SGP4 C++ folder its
    # original unrestricted terms, entered the tree at 4b04ddc: the recipe pins that commit, the first whose checkout
    # carries the terms, and names 7e0078a, which last changed the code and whose tree has no NOTICE; the files are identical.
    "vallado": {"files": {"README.md", "harness.cpp", "vectors.cpp", "common.h"}, "licence": ("AGPL-3.0", "unrestricted"),
                "commits": ["4b04ddce172a3f5d958b4256a29ea996c8e666be", "7e0078a10e9aed2a44eef0ab646c0018ca69e1ad"]},
    # D-427 (0.9.0 item b5): GPKit carries its own adapter, so its recipe is the pin and the commands, no harness code
    "gpkit": {"files": {"README.md"}, "licence": "Apache-2.0",   # D-456: v1.3.0; D-438's v1.2.0 and v1.1.0 named beside it
              "commits": ["1f5405bd3c27a61d79824af7e4f6c3b0bf4c995a", "971b642bc35d4f9d10bf3fbe017ae55ba785bbfd", "0c4d39667cc6de1fa59c04172390e87225d0fe56"]},
    # D-428 (items b1 and b2): written without the toolchains, never run; no commit to pin until a first run
    "orekit": {"files": {"README.md", "Harness.java"}, "licence": "Apache-2.0", "commits": [], "untested": True},
    "rust-sgp4": {"files": {"README.md", "Cargo.toml", "src/main.rs"}, "licence": "MIT", "commits": []},   # run in CI (D-442)
    # D-438 (items b3 and b4): brahe run here from PyPI 1.8.1; SGP.NET and akhenakh/sgp4 for CI's runners to build first
    "brahe": {"files": {"README.md", "brahe_adapter.py"}, "licence": "MIT", "commits": []},
    "sgp-net": {"files": {"README.md", "Harness.csproj", "Program.cs"}, "licence": "MIT", "commits": []},   # run in CI (D-440)
    "go-sgp4": {"files": {"README.md", "go.mod", "main.go"}, "licence": "Apache-2.0",
                # D-451: v1.0.4, after D-445; v1.0.2, the first runs' pin, named beside it
                "commits": ["b2e5162d8b5e5e78717891786ce6a7614785b60f", "06ae3b63682a4432b2941d7a038b8f1b93d368dc"]},   # run in CI (D-440)
    # D-438: moved from the owner's swift-satellite workspace (phase 1) by the owner's word, 2026-11-10
    "sgpkit": {"files": {"README.md", "Package.swift", "Sources/SGPKitBridge/bridge.cpp", "Sources/SGPKitBridge/include/SGPKitBridge.h",
                         "Sources/sgpkit-harness/main.swift", "Sources/sgpkit-vectors/main.swift", "support/Package.swift",
                         "support/Sources/HarnessSupport/Support.swift", "v4/Package.swift", "v4/Sources/sgpkit-v4-probe/main.swift"},
               "licence": "MIT", "commits": ["30bb5731715a1e048636ab7cbb25a24a773e1220"]},
}
ORIGINAL_DIR = {"libsgp4": "libsgp4", "gpredict": "gpredict", "satdump": "satdump", "astroz": "astroz", "gods-eye-view": "gods-eye-view",
                "vallado": "vallado/recipe-run"}
ORIGINAL_FILE = {("astroz", "harness.zig"): "round-2/harness.zig",  # round two's harness, with the refusal channel (D-185)
                 ("gpredict", "harness.c"): "round-2/harness.c",  # round two's harness, with the refusal channel (D-178)
                 ("libsgp4", "harness.cpp"): "round-2/harness.cpp",  # likewise (D-182)
                 ("astroz", "vectors.zig"): "round-3/vectors.zig"}  # the field's text quoted as a JSON string (D-509)


# beside the recipe, data, not recipe code: the corpus's manifest of Vallado's verification files and their provenance,
# and the two files themselves, private and withheld, in the maintainer's copy only (D-388)
VALLADO_DATA = {"reference-manifest.json", "reference/PROVENANCE.json"}
VALLADO_PRIVATE = {"reference/SGP4-VER.TLE", "reference/tcppver.out"}


HOOKS = ("parse", "alpha5_decode", "alpha5_encode", "two_digit_year", "parse_epoch", "parse_catalog_id", "propagate", "write")


def hooks_row(name):
    """D-451, the recipe rule of D-445: each README's `hooks` row, read as (answered, unsupported) hook names."""
    text = open(os.path.join(H, name, "README.md"), encoding="utf-8").read()
    m = re.search(r"^\| hooks \(D-451\) \| answers: (.*?); unsupported: (.*?) \|$", text, re.M)
    if not m:
        return None
    names = lambda part: [h for h in HOOKS if re.search(r"(?<![\w-])" + h + r"(?![\w-])", part)]  # noqa: E731
    return names(m.group(1)), names(m.group(2))


def files_under(d):
    out = set()
    for base, dirs, fs in os.walk(d):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in fs:
            if f != ".DS_Store":
                out.add(os.path.relpath(os.path.join(base, f), d).replace(os.sep, "/"))
    return out


def satdump_readme_names():
    text = open(os.path.join(H, "satdump", "README.md"), encoding="utf-8").read()
    sections = {}
    for label, key in (("Master:", "master"), ("Release 1.2.2:", "release")):
        block = text.split(label, 1)[1].split("\n\n", 2)[1]
        sections[key] = [m.group(1) for m in re.finditer(r"^- `([^`]+)`", block, re.M)]
    return sections


class Recipes(unittest.TestCase):
    def test_the_folder_holds_the_recipes_and_its_readme(self):
        self.assertEqual({x for x in os.listdir(H) if not x.startswith(".")}, set(RECIPES) | {"README.md"})
        self.assertTrue(os.path.exists(os.path.join(H, ".gitignore")))

    def test_each_folder_holds_exactly_its_files(self):
        for name, spec in RECIPES.items():
            with self.subTest(recipe=name):
                found = files_under(os.path.join(H, name))
                if name == "vallado":
                    self.assertTrue(VALLADO_DATA <= found)
                    found -= VALLADO_DATA | VALLADO_PRIVATE   # data beside the recipe; the private two in the maintainer's copy only (D-388)
                self.assertEqual(found, spec["files"])

    def test_each_readme_names_the_hooks_it_answers_and_the_ones_it_leaves_unsupported(self):
        """D-451 (D-445's recipe rule): a library's new writer or encoder must be exposed before its row is re-run, so each
        README says, for every hook, which side it is on; a hook it answers is in the harness's code, unless the
        project's own adapter answers it (GPKit)."""
        for name in RECIPES:
            with self.subTest(recipe=name):
                row = hooks_row(name)
                self.assertIsNotNone(row, "no hooks row")
                answered, unsupported = row
                self.assertEqual(sorted(answered + unsupported), sorted(HOOKS))   # every hook, once
                self.assertIn("parse", answered)
                if name == "gpkit":
                    continue
                code = ""
                for f in files_under(os.path.join(H, name)):
                    if not f.endswith((".md", ".json", ".TLE", ".out")):
                        code += open(os.path.join(H, name, f), encoding="utf-8", errors="replace").read()
                for h in answered:
                    if h in ("parse",):
                        continue
                    self.assertIn("write" if h == "write" else h, code, f"{h} answered but not in the harness's code")

    def test_the_rule_catches_a_writer_left_unexposed(self):
        """The check, proved on a known-bad case: the Go recipe's row before D-451 (no encoder, no writer) fails the
        answered-in-code rule if it claimed them, and its old row had no hooks line at all."""
        self.assertIsNone(re.search(r"^\| hooks \(D-451\)", "| licence of the code | Apache-2.0 |\n", re.M))
        answered, unsupported = hooks_row("go-sgp4")
        self.assertIn("alpha5_encode", answered)
        self.assertIn("write", answered)

    def test_each_readme_pins_the_commits_names_the_licence_and_the_limits(self):
        for name, spec in RECIPES.items():
            with self.subTest(recipe=name):
                text = " ".join(open(os.path.join(H, name, "README.md"), encoding="utf-8").read().split())  # prose wraps freely
                for c in spec["commits"]:
                    self.assertIn(c, text)
                for licence in [spec["licence"]] if isinstance(spec["licence"], str) else spec["licence"]:
                    self.assertIn(licence, text)
                self.assertIn("Best-effort, not installable by pip.", text)
                self.assertIn("with nothing to say so", text)  # the break-silently statement
                self.assertIn("published result", text)
                if spec.get("untested"):   # a recipe never run says so in its title and its first row (D-428)
                    self.assertIn("UNTESTED", text.split("|")[0])
                    self.assertIn("**not run.**", text)
        # the build commands check out the pinned commit, the first of each recipe's list where the recipe has one checkout
        vallado = open(os.path.join(H, "vallado", "README.md"), encoding="utf-8").read()
        self.assertIn("git -C repo checkout " + RECIPES["vallado"]["commits"][0], vallado)
        self.assertNotIn("git -C repo checkout " + RECIPES["vallado"]["commits"][1], vallado)
        gev = open(os.path.join(H, "gods-eye-view", "README.md"), encoding="utf-8").read()
        self.assertIn("git -C main checkout " + RECIPES["gods-eye-view"]["commits"][0], gev)  # D-221: the release, v0.2.1
        self.assertNotIn("git -C main checkout " + RECIPES["gods-eye-view"]["commits"][1], gev)

    def test_the_folder_readme_says_what_a_recipe_is_and_is_not(self):
        text = " ".join(open(os.path.join(H, "README.md"), encoding="utf-8").read().split())
        self.assertIn("not part of the `gpconf` package", text)
        self.assertIn("They break silently.", text)
        for name in RECIPES:
            self.assertIn(f"[{name}]({name}/)", text)


class SatDump(unittest.TestCase):
    """D-152: the recipe lists the symbols the link needs; no stand-in file, and no definition of those symbols, is here."""

    def test_the_readme_lists_the_symbols_and_says_why_there_are_no_stand_ins(self):
        names = satdump_readme_names()
        self.assertEqual((len(names["master"]), len(names["release"])), (9, 7))
        text = " ".join(open(os.path.join(H, "satdump", "README.md"), encoding="utf-8").read().split())
        self.assertIn("The stand-in files the corpus used for its own run are not in this folder.", text)
        self.assertIn("D-152", text)

    def test_no_recipe_source_defines_those_symbols(self):
        # a definition, not a mention: a function body opening after the name, or an object declared with an optional
        # initialiser and a semicolon; include lines and comments are skipped, since `db/kepler/...` is a path
        tokens = {n.split("::")[-1].split("<")[0] for ns in satdump_readme_names().values() for n in ns}
        for base, _, fs in os.walk(H):
            for f in fs:
                if f.endswith((".c", ".cpp", ".h", ".zig", ".mjs")):
                    lines = open(os.path.join(base, f), encoding="utf-8").read().splitlines()
                    src = "\n".join(l for l in lines if not l.strip().startswith(("#", "//", "/*", "*")))
                    found = sorted(t for t in tokens
                                   if re.search(rf"\b{re.escape(t)}\s*(<\w+>)?\s*\([^;{{}}]*\)\s*\{{", src)
                                   or re.search(rf"[\w>&*]\s+(\w+::)*{re.escape(t)}\s*(=[^;]*)?;", src))
                    self.assertEqual(found, [], os.path.relpath(os.path.join(base, f), ROOT))

    @unittest.skipUnless(os.path.isdir(ORIGINALS), "the one-off runs' originals are private")
    def test_the_list_names_exactly_what_the_corpus_stand_ins_defined(self):
        def defined(path):
            text = open(path, encoding="utf-8").read()
            text = "\n".join(l for l in text.splitlines() if not l.strip().startswith(("#", "//")))
            funcs = re.findall(r"([A-Za-z_][\w:]*(?:<\w+>)?)\s*\([^()]*\)\s*\{", text)
            objs = re.findall(r"\b([A-Za-z_]\w*)\s*(?:=\s*[^;{}]+)?;", text)
            return {n.split("::")[-1] for n in funcs + objs}
        names = satdump_readme_names()
        for key, stubs in (("master", "stubs.cpp"), ("release", "stubs-rel.cpp")):
            with self.subTest(tree=key):
                self.assertEqual({n.split("::")[-1] for n in names[key]}, defined(os.path.join(ORIGINALS, "satdump", stubs)))


class AstrozCatalogText(unittest.TestCase):
    """D-509: astroz's vectors hook gives parse_catalog_id's and parse_epoch's input, the field's text, to Tle.parseOmm
    as a JSON string. It used to paste the catalog text bare into the NORAD_CAT_ID number slot, so valid text such as
    00964 or +25544 made invalid JSON and came back refused, the harness's mistake reported as the library's."""
    VALID = (("00964", 964), ("+25544", 25544))

    def test_the_text_is_quoted(self):
        src = open(os.path.join(H, "astroz", "vectors.zig"), encoding="utf-8").read()
        self.assertIn("c.jsonString(rec, input)", src)
        self.assertNotRegex(src, r"allocPrint\([^;]*OMM_[^;]*\binput\b")   # no splice of the text into the record
        self.assertRegex(src, r'const OMM_MID = ",')   # the record's EPOCH is a quoted value written by jsonString

    @unittest.skipUnless(os.environ.get("GPCONF_ASTROZ_VECTORS"), "needs a built astroz vectors binary (harnesses/astroz/README.md)")
    def test_valid_text_reads_as_its_number(self):
        import json
        import subprocess
        for text, value in self.VALID:
            with self.subTest(text=text):
                out = subprocess.run([os.environ["GPCONF_ASTROZ_VECTORS"]], input=json.dumps({"op": "parse_catalog_id", "input": text}),
                                     capture_output=True, text=True, timeout=60)
                self.assertEqual(json.loads(out.stdout), {"result": value}, out.stderr)


@unittest.skipUnless(os.path.isdir(ORIGINALS), "the one-off runs' originals are private")
class CopiesOfTheOneOffRuns(unittest.TestCase):
    """The recipes' harness files are the one-off runs' files, byte for byte under the two header lines, except the first comment line of astroz's
    common.zig, which says whose code it is and the library's licence, reworded for the public copy. astroz's
    harness.zig is round two's, which reports refusals (D-185) and also builds at d558933; Gpredict's harness.c is
    round two's too (D-178), and so is libsgp4's harness.cpp (D-182)."""

    def test_copies_match(self):
        for name, spec in RECIPES.items():
            if spec.get("untested") or name in ("brahe", "sgpkit", "sgp-net", "go-sgp4", "rust-sgp4"):   # written for 0.9.0 or moved, no batch-g copy (D-428, D-438)
                continue
            for rel in spec["files"] - {"README.md"}:
                with self.subTest(file=f"{name}/{rel}"):
                    ours = open(os.path.join(H, name, rel), encoding="utf-8").read().splitlines()
                    # the two header lines every source file carries from v0.7.0 (D-310); the originals have none
                    self.assertEqual([l.lstrip("/# ") for l in ours[:2]], ["SPDX-License-Identifier: Apache-2.0", "Copyright 2026 NEOGY LLC"])
                    ours = ours[2:]
                    theirs = open(os.path.join(ORIGINALS, ORIGINAL_DIR[name], ORIGINAL_FILE.get((name, rel), rel)), encoding="utf-8").read().splitlines()
                    if name == "astroz" and rel == "common.zig":
                        ours, theirs = ours[1:], theirs[1:]  # the first comment line says whose code it is, reworded for the public copy
                    self.assertEqual(ours, theirs)


if __name__ == "__main__":
    unittest.main()
