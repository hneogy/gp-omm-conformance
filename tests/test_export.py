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
