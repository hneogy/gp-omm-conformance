"""D-155, v0.3.0 stage 4: harnesses/, the recipes for the five hand-run libraries that cannot be presets.

Each recipe folder holds exactly its harness files and a README that names the pinned commits in full, the project's
licence, and says it is best-effort, not installable by pip, and tied to what may break silently. SatDump follows
D-152: its harnesses and the list of symbol names, never a stand-in file, and no recipe source defines any of those
symbols. Two checks run only in the private repository, where the hand runs' originals are: the copies match them,
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
                "commits": ["661e057a5d369d5ee424676cf1d69cbead95ff2c", "2b8d14139fa266cdf57cb52ec9e1dfa041ee343d"]},
    "gpredict": {"files": {"README.md", "harness.c", "stubs/glib.h", "stubs/glib/gprintf.h"}, "licence": "GPL-2.0",
                 "commits": ["c9fa018f2f16bff6dd1c5c51befb8188fe5a5e35"]},
    "satdump": {"files": {"README.md", "harness.cpp", "harness-rel.cpp"}, "licence": "GPL-3.0",
                "commits": ["f3d82adbfe04e57c596b93479d687f4b830ee26c", "7aef0fe8441bc3eb440b1b6ba053556da5e40991"]},
    "astroz": {"files": {"README.md", "harness.zig", "vectors.zig", "common.zig"}, "licence": "GPL-3.0",
               "commits": ["d558933ec3a9c9ee826eb8de665b6e5d229ebecb"]},
    "gods-eye-view": {"files": {"README.md", "harness.mjs", "register.mjs", "cesium-hook.mjs", "cesium-stub.mjs"}, "licence": "MIT",
                      "commits": ["ce671ce500a393be27e3cbb2a08799fbca9b6e28"]},
}
ORIGINAL_DIR = {"libsgp4": "libsgp4", "gpredict": "gpredict", "satdump": "satdump", "astroz": "astroz", "gods-eye-view": "gods-eye-view"}


def files_under(d):
    out = set()
    for base, dirs, fs in os.walk(d):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in fs:
            if f != ".DS_Store":
                out.add(os.path.relpath(os.path.join(base, f), d))
    return out


def satdump_readme_names():
    text = open(os.path.join(H, "satdump", "README.md"), encoding="utf-8").read()
    sections = {}
    for label, key in (("Master:", "master"), ("Release 1.2.2:", "release")):
        block = text.split(label, 1)[1].split("\n\n", 2)[1]
        sections[key] = [m.group(1) for m in re.finditer(r"^- `([^`]+)`", block, re.M)]
    return sections


class Recipes(unittest.TestCase):
    def test_the_folder_holds_the_five_recipes_and_its_readme(self):
        self.assertEqual({x for x in os.listdir(H) if not x.startswith(".")}, set(RECIPES) | {"README.md"})
        self.assertTrue(os.path.exists(os.path.join(H, ".gitignore")))

    def test_each_folder_holds_exactly_its_files(self):
        for name, spec in RECIPES.items():
            with self.subTest(recipe=name):
                self.assertEqual(files_under(os.path.join(H, name)), spec["files"])

    def test_each_readme_pins_the_commits_names_the_licence_and_the_limits(self):
        for name, spec in RECIPES.items():
            with self.subTest(recipe=name):
                text = " ".join(open(os.path.join(H, name, "README.md"), encoding="utf-8").read().split())  # prose wraps freely
                for c in spec["commits"]:
                    self.assertIn(c, text)
                self.assertIn(spec["licence"], text)
                self.assertIn("Best-effort, not installable by pip.", text)
                self.assertIn("with nothing to say so", text)  # the break-silently statement
                self.assertIn("published result", text)

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

    @unittest.skipUnless(os.path.isdir(ORIGINALS), "the hand runs' originals are private")
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


@unittest.skipUnless(os.path.isdir(ORIGINALS), "the hand runs' originals are private")
class CopiesOfTheHandRuns(unittest.TestCase):
    """The recipes' harness files are the hand runs' files, byte for byte, except one reworded comment in astroz."""

    def test_copies_match(self):
        for name, spec in RECIPES.items():
            for rel in spec["files"] - {"README.md"}:
                with self.subTest(file=f"{name}/{rel}"):
                    ours = open(os.path.join(H, name, rel), encoding="utf-8").read().splitlines()
                    theirs = open(os.path.join(ORIGINALS, ORIGINAL_DIR[name], rel), encoding="utf-8").read().splitlines()
                    if (name, rel) == ("astroz", "common.zig"):
                        ours, theirs = ours[1:], theirs[1:]  # the first comment line says whose code it is, reworded for the public copy
                    self.assertEqual(ours, theirs)


if __name__ == "__main__":
    unittest.main()
