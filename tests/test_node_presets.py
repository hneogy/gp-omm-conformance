"""D-154, v0.3.0 stage 3: the Node presets satellite.js, tle.js and tle.js-api.

A shipped harness runs as `node --input-type=module --eval <source>` from the working directory, so the library
resolves as it would for a script in the user's project; `--module PATH` names its entry file instead. A preflight runs
before any case: a missing Node or library is a setup error, exit 2, that says nothing ran and nothing about the
library (D-153), never a parse failure in every case.

Tests that need Node skip without it. Tests that need the libraries run only where GPCONF_TEST_NODE_PROJECT names a
folder whose node_modules hold satellite.js and tle.js (`npm install satellite.js@7.1.0 tle.js@5.0.3`); CI has no
such folder and skips them."""
import contextlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

# D-270: these command lines go through the platform shell; quote for the shell the host has
Q = (lambda s: subprocess.list2cmdline([s])) if os.name == "nt" else shlex.quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gpconf import presets  # noqa: E402
from gpconf.__main__ import main as gpconf_main  # noqa: E402
from gpconf.runner import CommandParser, Runner, Unsupported  # noqa: E402

NODE = shutil.which("node")
PROJECT = os.environ.get("GPCONF_TEST_NODE_PROJECT")
HAVE_PROJECT = bool(PROJECT) and all(os.path.isdir(os.path.join(PROJECT, "node_modules", p)) for p in ("satellite.js", "tle.js"))
OFFLINE = ["alpha5-encoding-vectors", "alpha5-tle-derived", "kvn-syntax-variants", "tle-writer-alpha5"]


def run_cli(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = gpconf_main(argv)
        except SystemExit as e:
            code = e.code
    return code, out.getvalue()


class Registry(unittest.TestCase):
    def test_three_node_presets(self):
        node = {n: p for n, p in presets.PRESETS.items() if p.get("kind") == "node"}
        self.assertEqual(list(node), ["satellite.js", "tle.js", "tle.js-api"])
        self.assertEqual((node["tle.js"]["args"], node["tle.js-api"]["args"]), (["fields"], ["api"]))  # D-153: fields by default
        self.assertEqual(node["tle.js"]["harness"], node["tle.js-api"]["harness"])
        self.assertEqual({p["tested_with"] for p in node.values()}, {"7.1.0", "5.0.3"})
        for p in node.values():
            for f in (p["harness"], p.get("vectors"), "node_preflight.mjs"):
                if f:
                    self.assertTrue(os.path.exists(os.path.join(presets.ADAPTERS, f)), f)

    def test_module_applies_to_node_presets_only(self):
        with self.assertRaises(presets.PresetUnavailable):
            presets.load("sgp4", module="x.js")
        code, out = run_cli(["run", "--adapter", "tests.adapters.reference:Parser", "--module", "x.js"])
        self.assertEqual(code, 2, out)


class CommandLists(unittest.TestCase):
    """The command parser takes an argument list: no shell, the working directory and environment given, and only an
    element that is exactly {fmt} substituted, so a harness's source passed as an argument is never altered."""

    def test_fmt_substitution_cwd_and_exit_3(self):
        src = ("import sys, os, json\n"
               "if sys.argv[1] == 'kvn': sys.exit(3)\n"
               "print(json.dumps([{'fmt': sys.argv[1], 'untouched': sys.argv[2], 'cwd': os.getcwd()}]))")
        with tempfile.TemporaryDirectory() as tmp:
            p = CommandParser([sys.executable, "-c", src, "{fmt}", "x{fmt}"], cwd=tmp)
            (rec,) = p.parse(b"", "tle")
            self.assertEqual((rec["fmt"], rec["untouched"]), ("tle", "x{fmt}"))
            self.assertEqual(os.path.realpath(rec["cwd"]), os.path.realpath(tmp))
            with self.assertRaises(Unsupported):
                p.parse(b"", "kvn")

    def test_a_shell_string_still_works(self):
        import shlex
        p = CommandParser(f"{Q(sys.executable)} -c \"import json; print(json.dumps([{{'fmt': '{{fmt}}'}}]))\"")
        self.assertEqual(p.parse(b"", "csv"), [{"fmt": "csv"}])


class SetupErrors(unittest.TestCase):
    """D-153: a preset that cannot run is refused before any case, with exit 2, and the message says it is not a result."""

    def test_no_node(self):
        with mock.patch.object(presets.shutil, "which", return_value=None):
            with self.assertRaises(presets.PresetUnavailable) as cm:
                presets.load("tle.js")
        self.assertIn("needs Node.js, which was not found on PATH", str(cm.exception))
        self.assertIn("Nothing was run; this says nothing about tle.js.", str(cm.exception))

    @unittest.skipUnless(NODE, "Node.js not installed")
    def test_a_folder_without_the_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, package in (("satellite.js", "satellite.js"), ("tle.js", "tle.js"), ("tle.js-api", "tle.js")):
                with self.subTest(preset=name):
                    with self.assertRaises(presets.PresetUnavailable) as cm:
                        presets.load(name, cwd=tmp)
                    msg = str(cm.exception)
                    self.assertIn(f"could not import {package} from {tmp}", msg)
                    self.assertIn(f"npm install {package}", msg)
                    self.assertIn(f"Nothing was run; this says nothing about {package}.", msg)
            p = subprocess.run([sys.executable, "-m", "gpconf", "run", "--preset", "tle.js", "--root", ROOT, "--case", "alpha5-tle-derived"],
                               cwd=tmp, capture_output=True, text=True, timeout=120, env=dict(os.environ, PYTHONPATH=ROOT))
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertNotRegex(p.stdout, r"\d+ cases?: ")  # no count line: nothing ran

    @unittest.skipUnless(NODE, "Node.js not installed")
    def test_the_listing_says_where_the_library_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            lines = {line.split()[0]: line for line in presets.listing(cwd=tmp)}
        self.assertIn("not importable from this directory: npm install tle.js", lines["tle.js"])


@unittest.skipUnless(NODE and HAVE_PROJECT, "set GPCONF_TEST_NODE_PROJECT to a folder with satellite.js and tle.js installed")
class WithTheLibraries(unittest.TestCase):
    def test_each_preset_runs_from_the_project_and_names_the_version(self):
        want = {"satellite.js": ("7.1.0", {"alpha5-encoding-vectors": "skip", "alpha5-tle-derived": "fail", "kvn-syntax-variants": "skip", "tle-writer-alpha5": "skip"}),
                "tle.js": ("5.0.3", {"alpha5-encoding-vectors": "fail", "alpha5-tle-derived": "fail", "kvn-syntax-variants": "skip", "tle-writer-alpha5": "skip"}),
                "tle.js-api": ("5.0.3", {"alpha5-encoding-vectors": "fail", "alpha5-tle-derived": "fail", "kvn-syntax-variants": "skip", "tle-writer-alpha5": "skip"})}
        for name, (version, statuses) in want.items():
            with self.subTest(preset=name):
                parser, spec = presets.load(name, cwd=PROJECT)
                self.assertEqual(spec["found"], version)
                self.assertIn(f"({spec['library']} {version}, the version it was tested with)", spec["label"])
                got = {r.case_id: r.status for r in Runner(parser, root=ROOT).run(case_ids=OFFLINE)}
                self.assertEqual(got, statuses)

    def test_fields_and_api_differ_only_in_the_epoch(self):
        raw = open(os.path.join(ROOT, "derived", "alpha5-tle", "alpha5-T-270449-analyst-first.tle"), "rb").read()
        (f,) = presets.load("tle.js", cwd=PROJECT)[0].parse(raw, "tle")
        (a,) = presets.load("tle.js-api", cwd=PROJECT)[0].parse(raw, "tle")
        self.assertEqual({k for k in f if f[k] != a[k]}, {"epoch"})

    def test_module_names_the_entry_file_from_anywhere(self):
        entry = os.path.join(PROJECT, "node_modules", "tle.js", "src", "index.js")
        with tempfile.TemporaryDirectory() as tmp:
            _, spec = presets.load("tle.js", module=entry, cwd=tmp)
        self.assertEqual(spec["found"], "5.0.3")


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(NODE, "Node.js not installed")
class SatelliteJsNaNEpoch(unittest.TestCase):
    """With #190's fix (Number() for parseFloat()), satellite.js gives NaN for a field that is not wholly numeric and
    keeps error 0; the harness must emit such an epoch as null and say so on stderr, as it already does for the other
    non-finite fields, instead of building the string 2026-NaNTNaN:NaN:NaN.000NaN that the runner reported as its own
    internal error (the branch run of 2026-10-01, D-199)."""

    SET = ("1 69999U 58002D   26189.7O990935 -.00000023  00000+0 -70517-5 0  9996\n"
           "2 69999  34.2417 341.8745 1487004  19.9191 345.3718 11.62373363189308\n")

    def test_a_nan_epoch_is_emitted_as_null_and_noted(self):
        harness = os.path.join(ROOT, "gpconf", "adapters", presets.PRESETS["satellite.js"]["harness"])
        with open(harness, encoding="utf-8") as f:
            source = f.read()
        with tempfile.TemporaryDirectory() as tmp:
            stub = os.path.join(tmp, "stub.mjs")
            with open(stub, "w", encoding="utf-8") as f:   # what the library returns for the letter line, after the fix
                f.write("export function twoline2satrec(l1) { return { satnum: l1.substring(2, 7), epochyr: 26, epochdays: NaN,"
                        " no: 0.0506912634, ecco: 0.1487004, inclo: 0.5976, nodeo: 5.9665, argpo: 0.3476, mo: 6.0271,"
                        " bstar: -7.0517e-6, ndot: -6.97e-13, nddot: 0, error: 0 }; }\n"
                        "export function json2satrec() { throw new Error('unused'); }\n")
            env = dict(os.environ, GPCONF_NODE_MODULE=stub)
            p = subprocess.run([NODE, "--input-type=module", "--eval", source, "--", "tle"], input=self.SET,
                               capture_output=True, text=True, env=env, cwd=tmp)
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["norad_cat_id"], 69999)
        self.assertIsNone(out[0]["epoch"])
        self.assertAlmostEqual(out[0]["bstar"], -7.0517e-6)   # the fields around it still come through
        self.assertIn("non-finite epoch for 69999", p.stderr)
