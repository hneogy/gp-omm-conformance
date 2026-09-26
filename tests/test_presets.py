"""D-151, v0.3.0 stage 2: `gpconf run --preset NAME` runs a shipped adapter with no adapter written.

Four presets: reference and naive (standard library), sgp4 (python-sgp4) and pyephem (PyEphem). The adapters live in
gpconf/adapters/; the old tests/adapters/ names are the same modules. A preset records the version it was tested
against and the report prints the version found. A preset whose library is absent is refused with the pip command
that installs it. The library presets' tests skip where the library is not installed."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gpconf import presets  # noqa: E402
from gpconf.__main__ import main as gpconf_main  # noqa: E402
from gpconf.runner import Runner  # noqa: E402

OFFLINE = ["alpha5-encoding-vectors", "alpha5-tle-derived", "kvn-syntax-variants", "tle-writer-alpha5"]


def run_cli(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = gpconf_main(argv)
        except SystemExit as e:  # argparse errors
            code = e.code
    return code, out.getvalue()


def items(results):
    return [(r.case_id, r.status, [(i.check, i.status, i.file, i.detail) for i in r.items]) for r in results]


class Registry(unittest.TestCase):
    def test_four_presets_with_what_each_is(self):
        self.assertEqual(list(presets.PRESETS), ["reference", "naive", "sgp4", "pyephem"])
        lines = presets.listing()
        self.assertEqual([line.split()[0] for line in lines], ["reference", "naive", "sgp4", "pyephem"])
        self.assertIn("a demonstration of failure, not a parser anyone should use", lines[1])
        for name, library, tested in (("sgp4", "python-sgp4", "2.27"), ("pyephem", "PyEphem", "4.2.1")):
            spec = presets.PRESETS[name]
            self.assertEqual((spec["library"], spec["tested_with"], spec["extra"]), (library, tested, name))

    def test_naive_is_labelled_a_demonstration_of_failure_in_the_report(self):
        _, spec = presets.load("naive")
        self.assertEqual(spec["label"], "preset naive (a demonstration of failure, not a parser anyone should use)")

    def test_the_label_names_the_version_found_and_the_version_tested(self):
        base = {"name": "sgp4", "library": "python-sgp4", "tested_with": "2.27"}
        self.assertEqual(presets.label({**base, "found": "2.27"}), "preset sgp4 (python-sgp4 2.27, the version it was tested with)")
        self.assertEqual(presets.label({**base, "found": "2.28"}),
                         "preset sgp4 (python-sgp4 2.28 found; the preset was tested with 2.27, so results may differ from the published ones)")

    def test_an_unknown_preset_is_refused_with_the_list(self):
        with self.assertRaises(presets.PresetUnavailable) as cm:
            presets.load("skyfield")
        self.assertIn("reference, naive, sgp4, pyephem", str(cm.exception))
        code, out = run_cli(["run", "--preset", "skyfield"])
        self.assertEqual(code, 2, out)

    def test_a_missing_library_is_refused_with_the_install_command(self):
        for name, blocked, adapter in (("sgp4", ("sgp4", "sgp4.api", "sgp4.omm", "sgp4.exporter", "sgp4.conveniences", "sgp4.alpha5"), "gpconf.adapters.sgp4_adapter"),
                                       ("pyephem", ("ephem",), "gpconf.adapters.pyephem_adapter")):
            with self.subTest(preset=name), mock.patch.dict(sys.modules, {m: None for m in blocked}):
                sys.modules.pop(adapter, None)
                with self.assertRaises(presets.PresetUnavailable) as cm:
                    presets.load(name)
                self.assertIn(f"pip install {presets.PRESETS[name]['requires']}", str(cm.exception))
            sys.modules.pop(adapter, None)  # a later import sees the real library again

    def test_preset_cannot_be_combined_with_another_parser(self):
        code, out = run_cli(["run", "--preset", "reference", "--adapter", "tests.adapters.reference:Parser"])
        self.assertEqual(code, 2, out)
        self.assertIn("cannot be combined", out)


class SameAdapters(unittest.TestCase):
    """The move changed where the code lives, not what it does."""

    def test_old_names_are_the_package_modules(self):
        import gpconf.adapters.naive as n
        import gpconf.adapters.reference as r
        import tests.adapters.naive as tn
        import tests.adapters.reference as tr
        self.assertIs(tr, r)
        self.assertIs(tn, n)
        try:
            import gpconf.adapters.sgp4_adapter as s
            import tests.adapters.sgp4_adapter as ts
        except ImportError:
            return
        self.assertIs(ts, s)

    def test_a_preset_gives_the_adapters_results_over_the_offline_cases(self):
        from tests.adapters.naive import Parser as Naive
        from tests.adapters.reference import Parser as Reference
        pairs = [("reference", Reference), ("naive", Naive)]
        try:
            from tests.adapters.sgp4_adapter import Parser as Sgp4
            pairs.append(("sgp4", Sgp4))
        except ImportError:
            pass
        for name, cls in pairs:
            with self.subTest(preset=name):
                parser, _ = presets.load(name)
                self.assertEqual(items(Runner(parser, root=ROOT).run(case_ids=OFFLINE)), items(Runner(cls(), root=ROOT).run(case_ids=OFFLINE)))


class Report(unittest.TestCase):
    def test_the_json_report_records_the_preset(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "r.json")
            code, text = run_cli(["run", "--preset", "reference", "--case", "alpha5-encoding-vectors", "--json", out])
            with open(out) as f:
                rep = json.load(f)
        self.assertEqual(code, 0, text)
        self.assertEqual(rep["parser"], "preset reference")
        self.assertEqual(rep["preset"], {"name": "reference", "library": None, "found": None, "tested_with": None})

    def test_a_library_preset_prints_the_version_it_found(self):
        for name in ("sgp4", "pyephem"):
            spec = presets.PRESETS[name]
            found = presets.found_version(spec["distribution"])
            with self.subTest(preset=name):
                if found is None:
                    self.skipTest(f"{spec['library']} not installed here")
                code, text = run_cli(["run", "--preset", name, "--case", "alpha5-tle-derived"])
                self.assertIn(code, (0, 1), text)
                self.assertIn(f"parser: preset {name} ({spec['library']} {found}", text)


if __name__ == "__main__":
    unittest.main()
