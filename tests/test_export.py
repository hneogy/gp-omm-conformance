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

TEXT_EXT = (".json", ".md", ".py", ".txt", ".csv", ".kvn", ".xml", ".tle", ".2le", ".yml", ".toml", ".xsd", ".log", "")

# An absolute home path, whoever the user, in the three shapes (D-172): macOS and Linux (and root's home), and Windows
# with a drive letter and backslashes, escaped backslashes or forward slashes. A path glued to a word character is part
# of a URL or a relative path and does not count; one after a dot, a quote or a space does. The folder names are spelt
# with character classes, and the samples below are assembled at run time, so that this file does not match itself.
HOME_PATH = re.compile(r"(?<!\w)/(?:U[s]ers|h[o]me|r[o]ot)/[^\s\"'`<>)\]]*"
                       r"|(?i:\b[a-z]:(?:\\\\|\\|/)(?:u[s]ers|d[o]cuments and settings)(?:\\\\|\\|/))[^\s\"'`<>)\]]*")
# The one allowed path: the macOS home of a user named u, a fixture of the cache-folder test.
ALLOWED_HOME_PATHS = {("tests/test_install_layout.py", "/U" + "sers/u")}


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
                        self.assertIn(rel, rels, f"{rel} is not in the export: add a line for its folder or file type to PUBLIC_ALLOWLIST.txt")

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

    def test_no_raw_and_no_spacetrack_paths(self):
        rels = [os.path.relpath(f, self.dest) for f in self.files]
        self.assertFalse([r for r in rels if re.search(r"(^|/)fixtures/[^/]+/raw(/|$)", r)])
        # the verification TOOL is the single named exception to the Space-Track name guard (D-069)
        self.assertEqual([r for r in rels if re.search(r"space[-_ .]?track", r, re.I)], ["tools/verify_against_spacetrack.py"])

    def test_supgp_records_withheld(self):
        import json
        for case in SUPGP_CASES:
            p = os.path.join(self.dest, "fixtures", case, "expected.json")
            self.assertTrue(os.path.exists(p), case)
            with open(p) as fh:
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
        # modifier made a real path of `$name:Parser`. CLAUDE.md already warned against that spelling and did not stop it,
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


if __name__ == "__main__":
    unittest.main()
