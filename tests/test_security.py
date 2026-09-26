"""D-160: SECURITY.md, the public repository's security policy, stays true to the repository it describes.

Every path it names exists, so that a move or a rename cannot leave the policy pointing at nothing; its report address
is this repository's private vulnerability reporting; and its sentence that the package has no runtime dependencies
holds only while pyproject.toml declares none, so adding one fails here until the policy is revisited."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class SecurityPolicy(unittest.TestCase):
    def setUp(self):
        self.text = read("SECURITY.md")

    def test_every_path_it_names_exists(self):
        paths = re.findall(r"`([A-Za-z0-9_./-]+/?)`", self.text)
        paths = [p for p in paths if "/" in p or "." in p]  # file and folder names, not the extras' names
        self.assertGreaterEqual(len(paths), 8, paths)
        for p in paths:
            with self.subTest(path=p):
                self.assertTrue(os.path.exists(os.path.join(ROOT, p.rstrip("/"))), p)

    def test_the_tool_that_takes_credentials_is_in_scope(self):
        # added at the owner's word after the first draft left it out: it takes Space-Track credentials, so it is where
        # a vulnerability would matter most (D-160)
        in_scope = " ".join(self.text.split("In scope:", 1)[1].split("Not in scope:", 1)[0].split())
        self.assertIn("`tools/verify_against_spacetrack.py`", in_scope)

    def test_reports_go_to_private_vulnerability_reporting(self):
        self.assertIn("https://github.com/hneogy/gp-omm-conformance/security/advisories/new", self.text)
        self.assertIn("do not open a public issue", self.text)

    def test_no_runtime_dependencies_holds(self):
        self.assertIn("no runtime dependencies", self.text)
        self.assertRegex(read("pyproject.toml"), r"(?m)^dependencies = \[\]$")


if __name__ == "__main__":
    unittest.main()
