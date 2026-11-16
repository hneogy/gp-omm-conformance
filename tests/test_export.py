# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Export guard: the public release must contain no raw provider files, no Space-Track-named
paths and no SupGP-derived snapshot values (DECISIONS D-049)."""
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from public_scrub import SUPGP_CASES, supgp_value_strings  # noqa: E402
import export_public  # noqa: E402
from public_scrub import PRIVATE_NAMES as PRIVATE  # noqa: E402  (D-545; None in the public tree)

TEXT_EXT = (".json", ".md", ".py", ".txt", ".csv", ".kvn", ".xml", ".tle", ".2le", ".yml", ".toml", ".xsd", ".log", "")

# An absolute home path, whoever the user, in the three shapes (D-172): macOS and Linux (and root's home), and Windows
# with a drive letter and backslashes, escaped backslashes or forward slashes. A path glued to a word character is part
# of a URL or a relative path and does not count; one after a dot, a quote or a space does. The folder names are spelt
# with character classes, and the samples below are assembled at run time, so that this file does not match itself.
HOME_PATH = re.compile(r"(?<!\w)/(?:U[s]ers|h[o]me|r[o]ot)/[^\s\"'`<>)\]]*"
                       r"|(?i:\b[a-z]:(?:\\\\|\\|/)(?:u[s]ers|d[o]cuments and settings)(?:\\\\|\\|/))[^\s\"'`<>)\]]*")
# The one allowed path: the macOS home of a user named u, a fixture of the cache-folder test.
ALLOWED_HOME_PATHS = {("tests/test_install_layout.py", "/U" + "sers/u")}


def lines_removed(private):
    """How many lines the shortened passages take out of the private log: each passage's own line breaks less its
    replacement's, computed from the passages themselves (the owner's ruling of 2026-11-16, option A: exact, not loosened)."""
    from public_scrub import _PRIVATE
    n = 0
    for entry, head, tail, digest, new in _PRIVATE:
        start = private.find(f"**{entry} (")
        i = private.find(head, start)
        span = private[i:private.find(tail, i + len(head)) + len(tail)]
        n += span.count("\n") - new.count("\n")
    return n


class ExportGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dest = os.path.join(cls.tmp.name, "public")
        p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "export_public.py"), "--dest", cls.dest], capture_output=True, text=True)
        assert p.returncode == 0, p.stderr
        cls.files = []
        for d, _, fs in os.walk(cls.dest):
            for f in fs:
                cls.files.append(os.path.join(d, f))
        cls.values = supgp_value_strings(ROOT)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_module_of_the_package_and_the_tests_is_exported(self):
        # D-151: the allowlist's patterns do not recurse. "gpconf/*.py" covered the whole package until gpconf/adapters/
        # was added under it, and an export then shipped the tests/adapters/ shims without the modules they load. A
        # new folder of Python files without its own allowlist line fails here, not in public CI.
        # D-154 widened it from Python files to every file of the package: the Node harnesses are .mjs.
        rels = {os.path.relpath(f, self.dest) for f in self.files}
        # D-155 added harnesses/: every recipe file, its .gitignore included, since glob skips dotfiles unless listed.
        for top, wanted in (("gpconf", lambda f: not f.endswith(".pyc")), ("tests", lambda f: f.endswith(".py")),
                            ("harnesses", lambda f: f != ".DS_Store")):
            for d, _, fs in os.walk(os.path.join(ROOT, top)):
                if "__pycache__" in d:
                    continue
                for f in fs:
                    if wanted(f):
                        rel = os.path.relpath(os.path.join(d, f), ROOT)
                        if rel.replace(os.sep, "/") in export_public.WITHHELD:
                            self.assertNotIn(rel, rels, f"{rel} is withheld (D-367) but was exported")
                            continue
                        self.assertIn(rel, rels, f"{rel} is not in the export: add a line for its folder or file type to PUBLIC_ALLOWLIST.txt")

    def test_sm26s_adapters_are_exported(self):
        # D-367 withheld SM-26's adapters until SM-26's permission; SM-26 licensed them under Apache-2.0 (D-380), so from
        # D-382 they are exported with the tests that load them, and nothing is withheld.
        rels = {os.path.relpath(f, self.dest).replace(os.sep, "/") for f in self.files}
        self.assertFalse([k for k in export_public.WITHHELD if "sm26" in k])
        for f in ("sm26.py", "sm26_wrong2.py", "sm26_wrong3.py", "test_adversarial.py"):
            self.assertIn(f"tests/adversarial/{f}", rels)

    def test_vallados_files_are_withheld_from_the_export_and_the_package(self):
        # D-388, the owner's ruling (2026-11-06): private, for tests and the private repository only, until the owner
        # confirms written bundling permission; the package is staged from the export (tools/stage_package.py)
        rels = {os.path.relpath(f, self.dest).replace(os.sep, "/") for f in self.files}
        vallado = ["harnesses/vallado/reference/SGP4-VER.TLE", "harnesses/vallado/reference/tcppver.out"]
        self.assertEqual(sorted(export_public.WITHHELD), vallado)
        for f in vallado:
            self.assertNotIn(f, rels)
        self.assertIn("harnesses/vallado/reference/PROVENANCE.json", rels)   # what they are, and why withheld, is public
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import fnmatch, stage_package
        for f in vallado:
            self.assertFalse([p for p in stage_package.CORPUS if fnmatch.fnmatch(f, p)], f)

    def test_no_instructions_for_coding_assistants_are_exported(self):
        """D-461 (the owner's ruling, 2026-11-10): the instruction files and the assistant's settings folder stay
        private, whatever the allowlist says. Their names are spelt only in the private names file (D-545); the
        public tree matches them by hash."""
        found = [os.path.relpath(os.path.join(b, f), self.dest) for b, ds, fs in os.walk(self.dest) for f in fs + ds
                 if export_public.instruction_file(os.path.relpath(os.path.join(b, f), self.dest))]
        self.assertEqual(found, [])
        allow = open(os.path.join(ROOT, "PUBLIC_ALLOWLIST.txt"), encoding="utf-8").read().split()
        self.assertEqual([a for a in allow if export_public.instruction_file(a)], [])
        if not PRIVATE:
            self.skipTest("the private names file is absent (the public tree): its cases run in the private repository")
        cases = PRIVATE["instruction_file_cases"]
        for rel in cases["refused"]:
            self.assertTrue(export_public.instruction_file(rel), rel)
            self.assertTrue(re.search(PRIVATE["instruction_file_regex"], rel, re.I), rel)
            self.assertTrue(any(export_public._h(p) in export_public.INSTRUCTION_FILE_NAMES | export_public.INSTRUCTION_FOLDER_NAMES
                                for p in rel.split("/")), rel)   # the hash check alone refuses each, as in the public tree
        for rel in cases["kept"]:
            self.assertFalse(export_public.instruction_file(rel), rel)

    def test_the_exported_decision_log_names_no_coding_assistant(self):
        """D-462 (the owner's ruling, 2026-11-10): reworded in the exported copy, with a note; the private log intact."""
        text = open(os.path.join(self.dest, "DECISIONS.md"), encoding="utf-8").read()
        self.assertIn("Public copy: the coding assistant's name", text)
        self.assertIn("passages about unreported findings and private correspondence are shortened (D-542)", text)
        from public_scrub import scrub_decisions_md, named_in
        self.assertEqual(scrub_decisions_md("# T\nno mention here\n"), ("# T\nno mention here\n", 0))
        if not PRIVATE:
            self.skipTest("the private names file is absent (the public tree): its cases run in the private repository")
        self.assertEqual(named_in(text), [])
        private = open(os.path.join(ROOT, "DECISIONS.md"), encoding="utf-8").read()
        self.assertIn(PRIVATE["private_marker"], private)   # the original is untouched
        # the note and its blank line, less exactly the lines the shortened passages took up (D-274's reply, the owner's
        # ruling of 2026-11-16), nothing more
        self.assertEqual(len(text.splitlines()), len(private.splitlines()) + 2 - lines_removed(private))
        self.assertEqual(lines_removed(private), 18)   # pinned: D-274's reply block; any other line count is a change
        for given, want in PRIVATE["decisions_cases"]:
            self.assertEqual(scrub_decisions_md(given)[0].splitlines()[-1], want)

    def test_the_exported_tree_spells_no_private_name(self):
        """D-545 (the owner's ruling, 2026-11-14): no file of the exported tree, by name or content, holds the
        assistant's or its maker's name, an instruction file's name or the co-author trailer, in any case; the
        export refuses the private names file; and the check that stops the export finds each name it must."""
        rels = {os.path.relpath(f, self.dest).replace(os.sep, "/") for f in self.files}
        self.assertNotIn(export_public.PRIVATE_NAMES_FILE, rels)
        self.assertTrue(export_public.private_names_file(export_public.PRIVATE_NAMES_FILE))   # refused if ever allowlisted
        self.assertTrue(export_public.private_names_file("tools\\private-names.json".replace("\\", os.sep)))
        self.assertFalse(export_public.private_names_file("tools/fetchlist.json"))
        if PRIVATE:   # tracked in the private repository, so the export never depends on an untracked file
            p = subprocess.run(["git", "-C", ROOT, "ls-files", "--error-unmatch", export_public.PRIVATE_NAMES_FILE],
                               capture_output=True, text=True)
            if p.returncode != 128 or "not a git repository" not in p.stderr:   # a git archive tree has no repository
                self.assertEqual(p.returncode, 0, p.stderr)
        if not PRIVATE:
            self.skipTest("the private names file is absent (the public tree): its cases run in the private repository")
        from public_scrub import named_in
        hits = []
        for f in self.files:
            rel = os.path.relpath(f, self.dest)
            with open(f, "rb") as fh:
                hits += [(rel, h) for h in named_in(rel + "\n" + fh.read().decode("utf-8", "replace"))]
        self.assertEqual(hits, [])
        for sample in PRIVATE["names_cases"]["named"]:
            self.assertTrue(named_in(sample), sample)
        for sample in PRIVATE["names_cases"]["clean"]:
            self.assertEqual(named_in(sample), [], sample)

    def test_the_exported_decision_log_shortens_the_private_passages(self):
        """D-542 (the owner's ruling, 2026-11-14): each passage is shortened in the exported copy, nothing else changes,
        and a passage that is missing or not the recorded one stops the export. The passages are known here only by
        their SHA-256, since this file is exported too."""
        import hashlib
        from public_scrub import _PRIVATE, PrivatePassageError, scrub_private_passages
        text = open(os.path.join(self.dest, "DECISIONS.md"), encoding="utf-8").read()
        for entry, head, tail, digest, new in _PRIVATE:
            self.assertIn(new, text, entry)
        self.assertEqual(scrub_private_passages(text), (text, 0))   # the exported copy is already shortened
        if PRIVATE:   # the private repository holds the originals
            private = open(os.path.join(ROOT, "DECISIONS.md"), encoding="utf-8").read()
            out, n = scrub_private_passages(private)
            self.assertEqual(n, len(_PRIVATE))
            before, after = private.splitlines(), out.splitlines()
            self.assertEqual(len(before) - lines_removed(private), len(after))   # exactly the passages' own lines go
            self.assertEqual(len(before) - len(after), 18)   # pinned, not computed from the replacements
            import collections
            changed = list((collections.Counter(after) - collections.Counter(before)).elements())
            # one line per entry; D-499's two lines; D-274's title line and its reading's line (2026-11-16)
            self.assertEqual(len(changed), len({e for e, *_ in _PRIVATE}) + 2)
            for entry, head, tail, digest, new in _PRIVATE:
                i = private.find(head, private.find(f"**{entry} ("))
                span = private[i:private.find(tail, i + len(head)) + len(tail)]
                self.assertEqual(hashlib.sha256(span.encode("utf-8")).hexdigest(), digest, entry)
                self.assertNotIn(span, out, entry)
        entry, head, tail, digest, new = _PRIVATE[2]
        with self.assertRaises(PrivatePassageError):   # the head is there but the passage is not the recorded one
            scrub_private_passages(f"# T\n**{entry} (x)** {head}something else {tail}\n")
        with self.assertRaises(PrivatePassageError):   # the entry is there but its passage is gone
            scrub_private_passages(f"# T\n**{entry} (x)** nothing of it\n")

    def test_the_action_is_exported(self):
        # D-158: action.yml at the root is what `uses: hneogy/gp-omm-conformance@<tag>` reads; its script is in tools/
        rels = {os.path.relpath(f, self.dest) for f in self.files}
        self.assertIn("action.yml", rels)
        self.assertIn(os.path.join("tools", "action_report.py"), rels)

    def test_the_security_policy_is_exported(self):
        # D-160: GitHub shows SECURITY.md at the root of the public repository as its security policy
        rels = {os.path.relpath(f, self.dest) for f in self.files}
        self.assertIn("SECURITY.md", rels)

    def test_the_adapter_guide_is_exported(self):
        # D-161: docs/ files are allowlisted one by one; the README and the wiki link to this one
        rels = {os.path.relpath(f, self.dest) for f in self.files}
        self.assertIn(os.path.join("docs", "ADAPTERS.md"), rels)

    def test_the_one_provider_response_is_exported_and_it_is_the_sixteen_bytes(self):
        # D-247, a named exception to D-023: the provider's answer to a query with nothing to return, and its provenance
        rels = sorted(os.path.relpath(f, self.dest).replace(os.sep, "/") for f in self.files)
        self.assertEqual([r for r in rels if r.startswith("recorded/")],
                         ["recorded/celestrak-no-gp-data-found.provenance.json", "recorded/celestrak-no-gp-data-found.txt"])
        with open(os.path.join(self.dest, "recorded", "celestrak-no-gp-data-found.txt"), "rb") as f:
            self.assertEqual(f.read(), b"No GP data found")

    def test_anything_else_under_recorded_is_refused(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import export_public
        self.assertEqual(sorted(export_public.RECORDED), ["recorded/celestrak-no-gp-data-found.provenance.json", "recorded/celestrak-no-gp-data-found.txt"])
        src = open(os.path.join(ROOT, "tools", "export_public.py"), encoding="utf-8").read()
        self.assertIn('refused.append((rel, "not the one provider response the corpus ships (D-247)"))', src)

    def test_no_raw_and_no_spacetrack_paths(self):
        rels = [os.path.relpath(f, self.dest).replace(os.sep, "/") for f in self.files]
        self.assertFalse([r for r in rels if re.search(r"(^|/)fixtures/[^/]+/raw(/|$)", r)])
        # the verification TOOL is the single named exception to the Space-Track name guard (D-069)
        self.assertEqual([r for r in rels if re.search(r"space[-_ .]?track", r, re.I)], ["tools/verify_against_spacetrack.py"])

    def test_supgp_records_withheld(self):
        import json
        for case in SUPGP_CASES:
            p = os.path.join(self.dest, "fixtures", case, "expected.json")
            self.assertTrue(os.path.exists(p), case)
            with open(p, encoding="utf-8") as fh:
                exp = json.load(fh)
            self.assertEqual(exp["records"], [], case)
            self.assertIn("records_withheld", exp, case)

    def test_public_audit_copy_states_what_is_withheld(self):
        p = os.path.join(self.dest, "AUDIT.md")
        if not os.path.exists(p):
            self.skipTest("AUDIT.md not in the export")
        text = open(p, encoding="utf-8").read()
        private = open(os.path.join(ROOT, "AUDIT.md"), encoding="utf-8").read()
        if text == private:
            return  # nothing withheld in this checkout
        self.assertIn("Public-copy notice.", text)
        self.assertIn("private original, which is intact", text)
        self.assertNotIn("nine-digit-supgp-launch-nominals |", text)  # no appendix row from the SupGP case

    def test_the_home_path_guard_knows_every_shape(self):
        u, h, r, das = "Us" + "ers", "ho" + "me", "ro" + "ot", "Docu" + "ments and Settings"
        caught = [f"/{u}/alice/x", f"tests.adapters./{u}/alice/p", f"'/{u}/alice'", f"/{h}/bob/.cache", f"/{r}/.ssh",
                  f"C:\\{u}\\carol\\AppData", f"C:\\\\{u}\\\\carol", f"c:/{u}/carol/x", f"D:\\{das}\\dave"]
        missed = [s for s in caught if not HOME_PATH.search(s)]
        self.assertEqual(missed, [], "the guard misses these home-path shapes")
        ignored = [f"https://example.org/{h}/page", "~/.venvs/twine", f"relative/{u}/x", "docs/ADAPTERS.md"]
        self.assertEqual([s for s in ignored if HOME_PATH.search(s)], [], "the guard takes these for home paths")

    def test_no_absolute_home_path_in_any_exported_file(self):
        # D-172: three docstrings shipped the owner's home folder in v0.3.0, written through a shell whose zsh `:P`
        # modifier made a real path of `$name:Parser`. The maintainer's notes already warned against that spelling and did not stop it,
        # so the guard is a test: no exported file, of any type, may carry an absolute home path of any user.
        hits = []
        for f in self.files:
            rel = os.path.relpath(f, self.dest).replace(os.sep, "/")
            with open(f, "rb") as fh:
                text = fh.read().decode("utf-8", "replace")
            for m in HOME_PATH.finditer(text):
                path = m.group(0)
                if any(rel == af and (path == ap or path.startswith(ap + "/")) for af, ap in ALLOWED_HOME_PATHS):
                    continue
                hits.append(f"{rel}:{text.count(chr(10), 0, m.start()) + 1}: {path[:80]}")
        self.assertEqual(hits, [], "absolute home paths in exported files; a local path publishes a user name and a folder layout: " + "; ".join(hits[:10]))

    def test_no_supgp_values_anywhere(self):
        if not self.values:
            self.skipTest("no private SupGP snapshot values in this checkout (already public)")
        hits = []
        for f in self.files:
            if not f.endswith(TEXT_EXT):
                continue
            try:
                with open(f, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                continue
            for v in self.values:
                if v in text:
                    hits.append((os.path.relpath(f, self.dest), v))
        self.assertEqual(hits, [], f"SupGP-derived values found in the export: {hits[:10]}")


class LicenceFiles(unittest.TestCase):
    """D-219: LICENSE is the licence text and nothing else, so that a licence detector names it; what the licence covers and
    what it does not is in NOTICE, which is exported and packaged beside it."""

    def test_license_is_the_licence_text_alone_and_the_scope_note_is_in_notice(self):
        licence = open(os.path.join(ROOT, "LICENSE"), encoding="utf-8").read()
        import hashlib   # apache.org's LICENSE-2.0.txt, unaltered (D-310; the MIT text up to 0.6.2)
        self.assertEqual(hashlib.sha256(licence.encode("utf-8")).hexdigest(), "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30")
        self.assertNotIn("Scope note", licence)
        notice = open(os.path.join(ROOT, "NOTICE"), encoding="utf-8").read()
        for phrase in ("Scope note.", "raw data served by", "CelesTrak", "schemas/SOURCE.md", "LICENSE", "Copyright 2026 NEOGY LLC",
                       "https://doi.org/10.5281/zenodo.22867654", "gpconf is a name of NEOGY LLC. Forks are welcome under a different name."):
            self.assertIn(phrase, notice)
        allow = open(os.path.join(ROOT, "PUBLIC_ALLOWLIST.txt"), encoding="utf-8").read().splitlines()
        self.assertIn("NOTICE", allow)
        self.assertIn('license-files = ["LICENSE", "NOTICE"]', open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
