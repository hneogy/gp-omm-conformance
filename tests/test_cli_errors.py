"""D-269: the command line answers misuse with a message and exit status 2, never a silent no-op or a traceback.

An unknown --case had been silently ignored: `gpconf run --preset reference --case nosuch` printed a table with no
rows and exited 0, so a typo in a pipeline that names cases (CI's own commands do) stayed green forever. And
`check-tle` on a missing file ended in a raw FileNotFoundError. Both were findings of the audit of 2026-10-08
(D-268). Offline: the cases named here ship with the corpus; nothing is fetched."""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def gpconf(*args):
    return subprocess.run([sys.executable, "-m", "gpconf", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


class UnknownCase(unittest.TestCase):
    def test_an_unknown_case_is_an_error_naming_the_cases(self):
        r = gpconf("run", "--preset", "reference", "--case", "nosuch")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("no case 'nosuch'", r.stderr)
        self.assertIn("alpha5-tle-derived", r.stderr)                       # the message names the cases
        self.assertNotIn("Traceback", r.stderr)

    def test_a_typo_among_valid_cases_refuses_the_run_whole(self):
        r = gpconf("run", "--preset", "reference", "--case", "alpha5-encoding-vectors", "--case", "alpha5-tle-derivd")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("alpha5-tle-derivd", r.stderr)
        self.assertNotIn("alpha5-encoding-vectors                  pass", r.stdout)   # nothing ran

    def test_a_valid_case_still_runs(self):
        r = gpconf("run", "--preset", "reference", "--case", "alpha5-encoding-vectors")
        self.assertEqual(r.returncode, 0, r.stderr)


class CheckTleMissingFile(unittest.TestCase):
    def test_a_missing_file_is_a_one_line_error(self):
        r = gpconf("check-tle", os.path.join(ROOT, "no-such-file.tle"))
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("gpconf check-tle:", r.stderr)
        self.assertNotIn("Traceback", r.stderr)
