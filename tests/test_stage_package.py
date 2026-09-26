"""D-156, v0.3.0 stage 5: tools/stage_package.py and the packaging metadata.

The staging script takes a public export as its only input and refuses anything else; it walks the package
recursively, copies the shipped corpus into gpconf/corpus/, checks every staged file against the export manifest, and
audits a built wheel or sdist file by file. These tests build no real package (CI has no build frontend): the audit is
exercised on archives made here from a staged tree, correct and then damaged in each way it must catch.

D-159, stage 8: README.md is staged as the PyPI description, its relative links made absolute and pinned to the release
tag, while the repository's README keeps them relative; the audit fails a long description with a relative link."""
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import stage_package as sp  # noqa: E402


def make_wheel(stage_dir, path, mutate=None, metadata=b"Name: gpconf\n"):
    files = {}
    for base, _, fs in os.walk(os.path.join(stage_dir, "gpconf")):
        for f in fs:
            full = os.path.join(base, f)
            files[os.path.relpath(full, stage_dir).replace(os.sep, "/")] = open(full, "rb").read()
    files["gpconf-0.0.0.dist-info/METADATA"] = metadata
    if mutate:
        mutate(files)
    with zipfile.ZipFile(path, "w") as z:
        for n, data in files.items():
            z.writestr(n, data)


def make_sdist(stage_dir, path):
    with tarfile.open(path, "w:gz") as t:
        for base, _, fs in os.walk(stage_dir):
            for f in fs:
                full = os.path.join(base, f)
                t.add(full, arcname="gpconf-0.0.0/" + os.path.relpath(full, stage_dir).replace(os.sep, "/"))
        info = tarfile.TarInfo("gpconf-0.0.0/PKG-INFO")
        info.size = 6
        t.addfile(info, io.BytesIO(b"Name: "))


class StagePackage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.export = os.path.join(cls.tmp, "export")
        p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "export_public.py"), "--dest", cls.export], capture_output=True, text=True)
        assert p.returncode == 0, p.stderr
        cls.stage = os.path.join(cls.tmp, "stage")
        cls.pairs = sp.stage(cls.export, cls.stage)
        cls.manifest = sp.read_manifest(cls.export)
        cls.top = sp.expected_top(cls.export, cls.manifest)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def copy_export(self, name):
        d = os.path.join(self.tmp, name)
        shutil.copytree(self.export, d)
        return d

    def test_the_staged_tree_holds_the_whole_package_and_the_shipped_corpus(self):
        staged = {d for _, d in self.pairs}
        for want in ("gpconf/adapters/tlejs.mjs", "gpconf/adapters/sgp4_adapter.py", "gpconf/corpus/manifest.json",
                     "gpconf/corpus/tools/fetchlist.json", "gpconf/corpus/vectors/alpha5.json", "pyproject.toml", "LICENSE"):
            self.assertIn(want, staged)
        cases = [d for d in os.listdir(os.path.join(self.export, "fixtures")) if not d.startswith(".")]
        for c in cases:
            self.assertIn(f"gpconf/corpus/fixtures/{c}/expected.json", staged)
            self.assertIn(f"gpconf/corpus/fixtures/{c}/case.md", staged)
        package = {os.path.relpath(os.path.join(b, f), self.export).replace(os.sep, "/")
                   for b, _, fs in os.walk(os.path.join(self.export, "gpconf")) for f in fs if not f.endswith(".pyc")}
        self.assertEqual({d for d in staged if d.startswith("gpconf/") and not d.startswith("gpconf/corpus/")}, package)
        self.assertFalse([d for d in staged if sp.RAW.search(d)])

    def test_refusals(self):
        with self.assertRaises(sp.Refused):  # no export manifest
            sp.check_export(self.tmp)
        d = self.copy_export("with-raw")
        os.makedirs(os.path.join(d, "fixtures", "analyst-objects", "raw"))
        open(os.path.join(d, "fixtures", "analyst-objects", "raw", "analyst.tle"), "w").write("x")
        with self.assertRaisesRegex(sp.Refused, "provider file"):
            sp.check_export(d)
        d = self.copy_export("with-handoff")
        os.makedirs(os.path.join(d, "docs", "handoff"))
        with self.assertRaisesRegex(sp.Refused, "private repository"):
            sp.check_export(d)
        d = self.copy_export("changed")
        with open(os.path.join(d, "README.md"), "a") as f:
            f.write("\nchanged after the export\n")
        with self.assertRaisesRegex(sp.Refused, "changed after it was made"):
            sp.stage(d, os.path.join(self.tmp, "stage-changed"))

    def test_the_command_line_refuses_with_exit_2(self):
        p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "stage_package.py"), "--export", self.tmp, "--out",
                            os.path.join(self.tmp, "x")], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn("not a public export", p.stderr)

    def test_the_audit_passes_a_faithful_wheel_and_sdist(self):
        w = os.path.join(self.tmp, "good.whl")
        make_wheel(self.stage, w)
        report, problems = sp.audit(w, self.manifest, self.pairs, self.top)
        self.assertEqual(problems, [])
        n_corpus = sum(1 for _, d in self.pairs if d.startswith("gpconf/corpus/"))
        self.assertIn(f"{n_corpus} corpus files", report[0])
        s = os.path.join(self.tmp, "good.tar.gz")
        make_sdist(self.stage, s)
        self.assertEqual(sp.audit(s, self.manifest, self.pairs, self.top)[1], [])

    def test_the_audit_catches_each_kind_of_damage(self):
        cases = {
            "differs from the export": lambda f: f.__setitem__("gpconf/corpus/manifest.json", f["gpconf/corpus/manifest.json"] + b" "),
            "staged file missing": lambda f: f.pop("gpconf/corpus/vectors/alpha5.json"),
            "provider file": lambda f: f.__setitem__("gpconf/corpus/fixtures/analyst-objects/raw/analyst.tle", b"x"),
            "not listed": lambda f: f.__setitem__("gpconf/corpus/extra.json", b"{}"),
            "unexpected file": lambda f: f.__setitem__("tests/test_x.py", b""),
        }
        for want, mutate in cases.items():
            with self.subTest(damage=want):
                w = os.path.join(self.tmp, f"bad-{len(want)}.whl")
                make_wheel(self.stage, w, mutate)
                problems = sp.audit(w, self.manifest, self.pairs, self.top)[1]
                self.assertTrue(any(want in p for p in problems), problems)

    def test_the_staged_readme_is_the_pypi_copy_and_the_repository_keeps_its_own(self):
        repo = open(os.path.join(self.export, "README.md"), encoding="utf-8").read()
        staged = open(os.path.join(self.stage, "README.md"), encoding="utf-8").read()
        version = sp.version_of(self.export)
        self.assertIn("](AUDIT.md)", repo)  # relative in the repository: resolves on GitHub, in a clone, at any tag
        self.assertNotIn("](AUDIT.md)", staged)
        self.assertIn(f"(https://github.com/hneogy/gp-omm-conformance/blob/v{version}/AUDIT.md)", staged)
        self.assertEqual(sp.relative_links(staged), [])
        self.assertEqual(sp.relative_links(repo), ["AUDIT.md"])  # counted on 2026-09-26: the README's one relative link
        self.assertEqual(len(staged.splitlines()), len(repo.splitlines()))  # links rewritten, nothing else

    def test_the_audit_reads_the_long_description(self):
        staged = open(os.path.join(self.stage, "README.md"), "rb").read()
        good = os.path.join(self.tmp, "desc-good.whl")
        make_wheel(self.stage, good, metadata=b"Name: gpconf\nDescription-Content-Type: text/markdown\n\n" + staged)
        self.assertEqual(sp.audit(good, self.manifest, self.pairs, self.top)[1], [])
        bad = os.path.join(self.tmp, "desc-bad.whl")
        make_wheel(self.stage, bad, metadata=b"Name: gpconf\n\nSee [the audit](AUDIT.md).\n")
        problems = sp.audit(bad, self.manifest, self.pairs, self.top)[1]
        self.assertTrue(any("relative link in the long description" in p and "AUDIT.md" in p for p in problems), problems)


class PypiReadme(unittest.TestCase):
    FILES = {"AUDIT.md": "file", "docs": "dir", "docs/FAILURES.md": "file", "img/x.png": "file", "harnesses": "dir",
             ".github/workflows/ci.yml": "file"}

    def rewrite(self, text):
        return sp.pypi_readme(text, "v9.9.9", self.FILES.get)

    def test_every_relative_form_becomes_absolute_at_the_tag(self):
        blob = "https://github.com/hneogy/gp-omm-conformance/blob/v9.9.9/"
        tree = "https://github.com/hneogy/gp-omm-conformance/tree/v9.9.9/"
        raw = "https://raw.githubusercontent.com/hneogy/gp-omm-conformance/v9.9.9/"
        cases = {
            "[a](AUDIT.md)": f"[a]({blob}AUDIT.md)",
            '[f](./docs/FAILURES.md#naive "t")': f'[f]({blob}docs/FAILURES.md#naive "t")',
            "[d](docs/)": f"[d]({tree}docs)",
            "[h](/harnesses)": f"[h]({tree}harnesses)",
            "[c](./.github/workflows/ci.yml)": f"[c]({blob}.github/workflows/ci.yml)",
            "[x](#quick-start)": f"[x]({blob}README.md#quick-start)",
            "![p](img/x.png)": f"![p]({raw}img/x.png)",
            "[r]: docs/FAILURES.md": f"[r]: {blob}docs/FAILURES.md",
            '<a href="docs/FAILURES.md">h</a>': f'<a href="{blob}docs/FAILURES.md">h</a>',
            "[![b](img/x.png)](AUDIT.md)": f"[![b]({raw}img/x.png)]({blob}AUDIT.md)",
        }
        for src, want in cases.items():
            with self.subTest(src=src):
                self.assertEqual(self.rewrite(src), want)

    def test_absolute_links_and_code_are_left_alone(self):
        for text in ("[DOI](https://doi.org/10.5281/zenodo.22867654)", "[![DOI](https://zenodo.org/b.svg)](https://doi.org/x)",
                     "mail [me](mailto:a@b.c)", "`[not a link](AUDIT.md)`", "```\n[not a link](AUDIT.md)\n```\n",
                     "~~~md\n[not a link](missing.md)\n~~~\n"):
            with self.subTest(text=text):
                self.assertEqual(self.rewrite(text), text)

    def test_a_link_the_export_does_not_hold_is_refused(self):
        for text in ("[x](missing.md)", "[x](../outside.md)", "![x](img/none.png)"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(sp.Refused, "dead link"):
                    self.rewrite(text)


class Metadata(unittest.TestCase):
    def setUp(self):
        self.text = open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8").read()

    def test_packages_are_found_not_listed_and_include_the_adapters(self):
        self.assertIn("[tool.setuptools.packages.find]", self.text)
        self.assertIn('include = ["gpconf", "gpconf.*"]', self.text)
        self.assertNotRegex(self.text, r'(?m)^packages\s*=')
        self.assertIn('gpconf = ["corpus/**/*"]', self.text)
        self.assertIn('"gpconf.adapters" = ["*.mjs"]', self.text)

    def test_the_extras_are_the_library_presets_and_crosscheck_is_gone(self):
        extras = re.search(r"\[project\.optional-dependencies\]\n(.*?)\n\[", self.text, re.S).group(1)
        names = re.findall(r'(?m)^(\w[\w-]*)\s*=', extras)
        self.assertEqual(names, ["sgp4", "pyephem"])
        self.assertIn('sgp4 = ["sgp4"]', extras)
        self.assertIn('pyephem = ["ephem"]', extras)
        self.assertNotIn("crosscheck", self.text)
        readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
        self.assertIn("tools/crosscheck-requirements.lock.txt", readme)
        self.assertNotIn("`crosscheck` extra", readme)

    def test_the_runtime_needs_nothing(self):
        self.assertIn("dependencies = []", self.text)

    def test_the_pypi_sidebar_links(self):
        # D-159: the repository, the site, the issue tracker and the Zenodo concept DOI, the only navigation PyPI gives
        urls = re.search(r"\[project\.urls\]\n(.*?)(?:\n\[|\Z)", self.text, re.S).group(1)
        links = dict(re.findall(r'(?m)^(\w+) = "([^"]+)"', urls))
        self.assertEqual(links, {"Homepage": "https://gpconf.neogy.dev",
                                 "Repository": "https://github.com/hneogy/gp-omm-conformance",
                                 "Issues": "https://github.com/hneogy/gp-omm-conformance/issues",
                                 "DOI": "https://doi.org/10.5281/zenodo.22867654"})


if __name__ == "__main__":
    unittest.main()
