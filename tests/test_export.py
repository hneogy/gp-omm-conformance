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
from public_scrub import SUPGP_CASES, supgp_value_strings, entry_start  # noqa: E402
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
    replacement's, computed from the passages themselves (the owner's ruling of 2026-11-16: exact, not loosened)."""
    from public_scrub import _PRIVATE
    n = 0
    for entry, head, tail, digest, new in _PRIVATE:
        start = entry_start(private, entry)
        i = private.find(head, start)
        span = private[i:private.find(tail, i + len(head)) + len(tail)]
        n += span.count("\n") - new.count("\n")
    return n


# D-612 (the owner's ruling of 2026-11-17): the exported tree names private correspondence nowhere outside the stub
# lines. WORDING finds every line that names the operator, correspondence, a reply, or a letter in its correspondence
# forms; each such line may stay only if it is listed, by file and the SHA-256 of the line, in
# tests/export_wording_allowlist.tsv, a list reviewed line by line (a citation or credit, an Alpha-5 or other technical
# use, or a public GitHub reply; never a description of the correspondence). Any other such line fails, and so does a
# listed line that is gone or changed. And no window of WINDOW characters of any text the export removes (a stubbed
# entry or a shortened passage) may appear in the exported decision log or changelog, unless the same window stays in
# the private log outside what is removed, in a replacement, or in another file of the tree (an entry quoting the
# README, say); every other file is held by the wording check above.
# Each family of wording the guard looks for, matched in any case and with either apostrophe (D-615); the planted test
# holds every family with a line that only that family catches.
WORDING_FAMILIES = [
    ("name", r"kelso"),
    ("operator", r"celestrak['\u2019]s operator"),
    ("written to", r"written to (?:celestrak|its operator|the operator)"),
    ("wrote to", r"wrote to (?:celestrak|its operator|the operator)"),
    ("sent to", r"sent to (?:celestrak|its operator|the operator)"),
    ("correspondence", r"correspondence"),
    ("confirmed in", r"confirmed in"),
    ("asked for separately", r"asked for separately"),
    ("rights holders", r"rights holders"),
    ("permission asked", r"permission (?:is|was) (?:asked|awaited|requested)"),
    ("permission request", r"permission request"),
    ("bundling answer", r"bundling answer"),
    ("reply", r"\brepl(?:y|ied|ies)\b"),
    ("the letter", r"\bthe letter (?:to|of|from|was|is|says|said|promise[sd]?|asks|gives|went|sent)\b"),
    ("letter to", r"\bletter to\b"),
    ("the letter's", r"\bthe letter['\u2019]s\b"),
    ("draft", r"\b(?:the|this|that|its) draft\b(?! release)"),
    ("letter near the provider", r"\bletter\b[^.\n]{0,40}\b(?:celestrak|operator)\b"),
    ("bundling permi" + "ssion", r"bundling permissio(?:n)"),   # D-617
    ("written permi" + "ssion", r"written permissio(?:n)"),   # D-619
    ("assist" + "ant", r"\bassistan(?:t)(?:s|['\u2019]s)?\b"),   # D-618
]
WORDING = re.compile("(?i:" + "|".join(rx for _, rx in WORDING_FAMILIES) + ")")
WORDING_ALLOWLIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "export_wording_allowlist.tsv")
WINDOW = 60


def wording_hits(root):
    """-> [(path relative to root, line number, line)] for every text line WORDING finds outside the stub lines."""
    from public_scrub import STUB_LINES
    out = []
    for d, dirs, fs in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x != ".git")
        for f in sorted(fs):
            p = os.path.join(d, f)
            try:
                with open(p, encoding="utf-8") as fh:
                    lines = fh.read().splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            out += [(rel, i, l) for i, l in enumerate(lines, 1) if l not in STUB_LINES and WORDING.search(l)]
    return out


def wording_failures(root, allowlist_path=WORDING_ALLOWLIST):
    """-> [str]: every unlisted WORDING line, and every listed line not found exactly once."""
    import hashlib
    listed = {}
    with open(allowlist_path, encoding="utf-8") as fh:
        rows = fh.read().splitlines()
    for row in rows:
        if row.strip() and not row.startswith("#"):
            rel, digest = row.split("\t")
            listed[(rel, digest)] = 0
    bad = []
    for rel, i, l in wording_hits(root):
        key = (rel, hashlib.sha256(l.encode("utf-8")).hexdigest())
        if key in listed:
            listed[key] += 1
        else:
            bad.append(f"{rel}:{i}: not on the reviewed list: {l[:120]}")
    bad += [f"{rel}: a listed line ({d[:12]}) is gone, changed or repeated ({n} found)" for (rel, d), n in listed.items() if n != 1]
    return bad


def removed_windows(private_decisions, private_changelog, other=""):
    """The WINDOW-character windows of every text the export removes that stay nowhere else: not in the private log or
    changelog outside the removed text, and not in any replacement or stub line."""
    from public_scrub import _PRIVATE, _STUBS, _CHANGELOG, STUB_LINES
    spans, kept_d, kept_c = [], private_decisions, private_changelog
    for entry, digest, line in _STUBS:
        s = entry_start(private_decisions, entry)
        ends = [x for x in (private_decisions.find("\n**D-", s + 1), private_decisions.find("\n## ", s + 1)) if x > 0]
        spans.append(private_decisions[s:min(ends)])
    for entry, head, tail, digest, new in _PRIVATE:
        s = entry_start(private_decisions, entry); i = private_decisions.find(head, s)
        spans.append(private_decisions[i:private_decisions.find(tail, i + len(head)) + len(tail)])
    for release, head, tail, digest, new in _CHANGELOG:
        s = private_changelog.find(f"## [{release}]"); i = private_changelog.find(head, s)
        span = private_changelog[i:private_changelog.find(tail, i + len(head)) + len(tail)]
        spans.append(span); kept_c = kept_c.replace(span, "\0")
    for span in spans:
        kept_d = kept_d.replace(span, "\0")
    keep = "\0".join([kept_d, kept_c, other] + [e[4] for e in _PRIVATE] + [e[4] for e in _CHANGELOG] + list(STUB_LINES))
    norm = lambda s: " ".join(s.split())
    keep = norm(keep)
    out = set()
    for span in spans:
        s = norm(span)
        out |= {s[k:k + WINDOW] for k in range(0, max(1, len(s) - WINDOW + 1)) if s[k:k + WINDOW] not in keep}
    return out


def tree_text(root, skip=("DECISIONS.md", "CHANGELOG.md")):
    """Every other text file of a tree, whitespace normalised and joined (what a removed window may also be in)."""
    parts = []
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if x != ".git"]
        for f in fs:
            p = os.path.join(d, f)
            if os.path.relpath(p, root).replace(os.sep, "/") in skip:
                continue
            try:
                with open(p, encoding="utf-8") as fh:
                    parts.append(" ".join(fh.read().split()))
            except (UnicodeDecodeError, OSError):
                continue
    return "\0".join(parts)


def window_leaks(root, windows, files=("DECISIONS.md", "CHANGELOG.md")):
    """-> [str]: the exported log and changelog files that hold any removed window (whitespace normalised)."""
    bad = []
    for rel in files:
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as fh:
            text = " ".join(fh.read().split())
        found = [w for w in windows if w in text]
        if found:
            bad.append(f"{rel}: {len(found)} removed window(s), e.g. {found[0][:40]!r}")
    return bad


def stub_lines_removed(private):
    """How many lines the stubbed entries take out of the private log (D-612), computed from the entries themselves."""
    from public_scrub import _STUBS
    n = 0
    for entry, digest, line in _STUBS:
        s = entry_start(private, entry)
        ends = [x for x in (private.find("\n**D-", s + 1), private.find("\n## ", s + 1)) if x > 0]
        body = private[s:min(ends)]
        n += body.count("\n") - line.count("\n") - (1 if body.endswith("\n") else 0)
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
        # D-388, the owner's ruling (2026-11-06): private, for tests and the private repository only, kept out of the
        # public copy; the package is staged from the export (tools/stage_package.py)
        rels = {os.path.relpath(f, self.dest).replace(os.sep, "/") for f in self.files}
        vallado = ["harnesses/vallado/reference/SGP4-VER.TLE", "harnesses/vallado/reference/tcppver.out"]
        self.assertEqual(sorted(k for k, v in export_public.WITHHELD.items() if v == export_public.VALLADO_PRIVATE), vallado)
        self.assertEqual(sorted(k for k, v in export_public.WITHHELD.items() if v != export_public.VALLADO_PRIVATE),
                         ["docs/upstream/python-sgp4-omm-initialize-drops-classification.md"])   # a draft held until filed (D-613)
        for f in vallado:
            self.assertNotIn(f, rels)
        self.assertIn("harnesses/vallado/reference/PROVENANCE.json", rels)   # what they are, and why withheld, is public
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import fnmatch, stage_package
        for f in vallado:
            self.assertFalse([p for p in stage_package.CORPUS if fnmatch.fnmatch(f, p)], f)

    def test_no_private_instruction_files_are_exported(self):
        """D-461 (the owner's ruling, 2026-11-10): the instruction files and the private settings folder stay
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

    def test_the_exported_decision_log_spells_no_private_name(self):
        """D-462 (the owner's ruling, 2026-11-10): reworded in the exported copy, with a note; the private log intact."""
        text = open(os.path.join(self.dest, "DECISIONS.md"), encoding="utf-8").read()
        self.assertIn("Public copy: private names and files", text)
        self.assertIn("passages about unreported findings and private correspondence are shortened (D-542)", text)
        from public_scrub import scrub_decisions_md, named_in
        self.assertEqual(scrub_decisions_md("# T\nno mention here\n"), ("# T\nno mention here\n", 0))
        if not PRIVATE:
            self.skipTest("the private names file is absent (the public tree): its cases run in the private repository")
        self.assertEqual(named_in(text), [])
        private = open(os.path.join(ROOT, "DECISIONS.md"), encoding="utf-8").read()
        self.assertIn(PRIVATE["private_marker"], private)   # the original is untouched
        # the note and its blank line, less exactly the lines the shortened passages and the stubbed entries took up
        # (D-612), nothing more
        self.assertEqual(len(text.splitlines()), len(private.splitlines()) + 2 - lines_removed(private) - stub_lines_removed(private))
        self.assertEqual(lines_removed(private), 14)   # pinned (D-616): any other line count is a change
        self.assertEqual(stub_lines_removed(private), 117)   # pinned: D-274's, D-609's and D-618's six entries' lines become one each
        for given, want in PRIVATE["decisions_cases"]:
            self.assertEqual(scrub_decisions_md(given)[0].splitlines()[-1], want)

    def test_the_exported_tree_spells_no_private_name(self):
        """D-545 (the owner's ruling, 2026-11-14): no file of the exported tree, by name or content, holds the
        private names, an instruction file's name or the co-author trailer, in any case; the
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

    def test_no_private_correspondence_outside_the_stubs(self):
        """D-612, D-613: every flagged line is a reviewed one, and no removed text is left."""
        import hashlib
        self.assertEqual(wording_failures(self.dest), [])
        if PRIVATE:
            windows = removed_windows(open(os.path.join(ROOT, "DECISIONS.md"), encoding="utf-8").read(),
                                      open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read(), tree_text(self.dest))
            self.assertGreater(len(windows), 1000)   # the removed text is long; a handful would mean the spans are wrong
            self.assertEqual(window_leaks(self.dest, windows), [])
            # the windows exempted because another file of the tree holds them are exactly the reviewed ones (D-613)
            from public_scrub import EXEMPT_WINDOWS
            every = removed_windows(open(os.path.join(ROOT, "DECISIONS.md"), encoding="utf-8").read(),
                                    open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read())
            exempt = {hashlib.sha256(w.encode("utf-8")).hexdigest() for w in every - windows}
            self.assertEqual(exempt, EXEMPT_WINDOWS)

    def test_the_wording_guard_fails_on_planted_lines(self):
        """The guard is proven on planted copies: an unlisted line, a listed line changed, a removed window put back."""
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "t")
            shutil.copytree(self.dest, root)
            with open(os.path.join(root, "README.md"), "a", encoding="utf-8") as f:
                f.write("\nA note from CelesTrak's oper" + "ator, confirm" + "ed in his rep" + "ly.\n")
            self.assertTrue(any("README.md" in b and "not on the reviewed list" in b for b in wording_failures(root)))
            hit = wording_hits(self.dest)[0]
            p = os.path.join(root, hit[0]); lines = open(p, encoding="utf-8").read().split("\n")
            lines[hit[1] - 1] += " (changed)"
            open(p, "w", encoding="utf-8").write("\n".join(lines))
            self.assertTrue(any("gone, changed or repeated" in b for b in wording_failures(root)))
        if PRIVATE:
            windows = removed_windows(open(os.path.join(ROOT, "DECISIONS.md"), encoding="utf-8").read(),
                                      open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read(), tree_text(self.dest))
            w = sorted(windows)[len(windows) // 2]
            with tempfile.TemporaryDirectory() as tmp:
                k = w.find(" ", 10)   # across a line break, as the hard-wrapped log would carry it
                open(os.path.join(tmp, "DECISIONS.md"), "w", encoding="utf-8").write("text " + w[:k] + "\n  " + w[k + 1:] + " text\n")
                self.assertEqual(len(window_leaks(tmp, windows)), 1)

    def test_the_exported_changelog_names_no_private_correspondence(self):
        """D-612, D-613 (the owner's rulings, 2026-11-17): two released changelog lines are shortened in the public
        copy only, the private CHANGELOG staying as released; a passage missing or not the recorded one stops the export."""
        import hashlib
        from public_scrub import _CHANGELOG, PrivatePassageError, scrub_changelog_md
        text = open(os.path.join(self.dest, "CHANGELOG.md"), encoding="utf-8").read()
        self.assertIn("eccentricity truncation, after D-277.", text)
        self.assertIn("72001 (a single satellite), which in the corpus's TLE captures appear only there (D-274). Text only; no value moves (D-340).", " ".join(text.split()))
        self.assertEqual(scrub_changelog_md(text), (text, 0))   # the exported copy is already shortened
        self.assertEqual(len(_CHANGELOG), 2 if PRIVATE else 0)   # the lists are private (D-613): empty in the public tree
        if PRIVATE:   # the private repository holds the released lines
            private = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read()
            out, n = scrub_changelog_md(private)
            self.assertEqual(n, 2)
            self.assertEqual(len(private.splitlines()) - len(out.splitlines()), 0)   # pinned: the 0.8.0 passage keeps its line count
            norm = lambda s: " ".join(s.split())
            # the whole sentences around each replacement, so a passage cut in the wrong place fails here
            self.assertIn("rendered with CelesTrak's eccentricity truncation, after D-277. The documentation", norm(out))
            self.assertIn("80000-89999; CelesTrak's supplemental data gave launch 2026-219 the temporary ids 72000 (the stack) "
                          "and 72001 (a single satellite), which in the corpus's TLE captures appear only there (D-274). Text only; "
                          "no value moves (D-340). Changed:", norm(out))
            self.assertEqual(norm(out).count("no value moves (D-340)."), norm(private).count("no value moves (D-340)."))
            for release, head, tail, digest, new in _CHANGELOG:
                s0 = private.find(f"## [{release}]"); i = private.find(head, s0)
                span = private[i:private.find(tail, i + len(head)) + len(tail)]
                self.assertEqual(hashlib.sha256(span.encode("utf-8")).hexdigest(), digest, release)
        if not _CHANGELOG:
            return
        release, head, tail, digest, new = _CHANGELOG[0]
        with self.assertRaises(PrivatePassageError):   # the head is there but the passage is not the recorded one
            scrub_changelog_md(f"# C\n## [{release}] - x\n{head}something else{tail}\n")
        with self.assertRaises(PrivatePassageError):   # the release is there but its passage is gone
            scrub_changelog_md(f"# C\n## [{release}] - x\nnothing of it\n")

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
            self.assertEqual(len(before) - len(after), 14)   # pinned, not computed from the replacements (D-616)
            import collections
            changed = list((collections.Counter(after) - collections.Counter(before)).elements())
            # one line per entry, and the further lines of entries shortened in more than one place (pinned, D-613)
            self.assertEqual(len(changed), len({e for e, *_ in _PRIVATE}) + 7)
            for entry, head, tail, digest, new in _PRIVATE:
                i = private.find(head, entry_start(private, entry))
                span = private[i:private.find(tail, i + len(head)) + len(tail)]
                self.assertEqual(hashlib.sha256(span.encode("utf-8")).hexdigest(), digest, entry)
                self.assertNotIn(span, out, entry)
        if not _PRIVATE:
            return   # the lists are private (D-613): nothing to plant against in the public tree
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


class PrivateListsAreNotPublished(unittest.TestCase):
    def test_the_export_carries_no_list_of_what_it_withholds(self):
        """D-613: no hash or match string of removed text is published; the private file is refused by the export and
        the exported scrub tool holds no SHA-256 of removed text."""
        self.assertTrue(export_public.private_names_file("tools/private-passages.json"))
        src = open(os.path.join(ROOT, "tools", "public_scrub.py"), encoding="utf-8").read()
        self.assertEqual(re.findall(r"\b[0-9a-f]{64}\b", src), [])
        self.assertIn("docs/upstream/python-sgp4-omm-initialize-drops-classification.md", export_public.WITHHELD)


class EntryLookup(unittest.TestCase):
    def test_undated_and_dated_entries_are_both_found(self):
        """D-613: the early entries are written "**D-n —"; a lookup by "**D-n (" alone skipped them without a word."""
        text = "# L\n\n**D-046 — An early one.** x\n\n**D-490 (2026-11-11) — A later one.** y\n"
        self.assertEqual(text[entry_start(text, "D-046"):].split("**")[1], "D-046 — An early one.")
        self.assertEqual(text[entry_start(text, "D-490"):].split("**")[1], "D-490 (2026-11-11) — A later one.")
        self.assertEqual(entry_start(text, "D-047"), -1)


class WordingGuardPlanted(unittest.TestCase):
    PLANTS = {   # one line per family, split so that this file's own text is not a hit
        "name": "As Kel" + "so wrote in the FAQ.", "operator": "celestrak\u2019s oper" + "ator said so.",
        "written to": "A sentence writ" + "ten to CelesTrak.", "wrote to": "The owner wro" + "te to celestrak.",
        "sent to": "The note was se" + "nt to CelesTrak.", "correspondence": "Some corres" + "pondence followed.",
        "confirmed in": "It was confir" + "med in a note.", "asked for separately": "It is ask" + "ed for separately.",
        "rights holders": "The rights hol" + "ders agreed.", "permission asked": "The permission is awa" + "ited.",
        "permission request": "The permission requ" + "est went out.", "bundling answer": "It waits on the bundling ans" + "wer.",
        "reply": "A rep" + "ly came.", "the letter": "The let" + "ter was in the drawer.",
        "letter to": "A let" + "ter to the editor.", "the letter's": "The let" + "ter\u2019s margin.",
        "draft": "This dra" + "ft says so.", "letter near the provider": "A let" + "ter for CelesTrak.",
        "bundling permi" + "ssion": "It waits on written bundling permi" + "ssion.",
        "written permi" + "ssion": "Not before written permi" + "ssion.", "assist" + "ant": "A coding assis" + "tant helped.",
    }

    def test_each_family_has_a_plant_only_it_catches(self):
        """D-615: every family of the guard has a planted line that it, and no other family, catches; so dropping any one
        family misses its line; and the guard as a whole flags every planted line."""
        pinned = ["bundling answer", "confirmed in", "correspondence", "draft", "letter near the provider", "letter to",
                  "name", "operator", "permission asked", "permission request", "reply", "rights holders", "sent to",
                  "the letter", "the letter's", "written to", "wrote to", "asked for separately", "bundling permi" + "ssion",
                  "written permi" + "ssion", "assist" + "ant"]
        self.assertEqual(sorted(name for name, _ in WORDING_FAMILIES), sorted(pinned))   # pinned (D-616 to D-619): 21 families
        self.assertEqual(sorted(self.PLANTS), sorted(pinned))
        for name, line in self.PLANTS.items():
            caught = [n for n, rx in WORDING_FAMILIES if re.search("(?i:" + rx + ")", line)]
            self.assertEqual(caught, [name], line)
            without = re.compile("(?i:" + "|".join(rx for n, rx in WORDING_FAMILIES if n != name) + ")")
            self.assertIsNone(without.search(line), name)
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "x.md"), "w", encoding="utf-8").write("\n".join(self.PLANTS.values()) + "\n")
            empty = os.path.join(tmp, "allow.tsv"); open(empty, "w").close()
            self.assertEqual(len(wording_failures(tmp, empty)), len(self.PLANTS))


if __name__ == "__main__":
    unittest.main()
