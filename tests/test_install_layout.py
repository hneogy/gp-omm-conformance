"""D-150, v0.3.0 stage 1: the runner works when installed, not only from a clone.

Two roots: the corpus root (what ships) and the data root (what this machine fetched). An installed copy finds its
corpus bundled in gpconf/corpus/ and keeps provider files in a per-user cache folder, or wherever --data or
GPCONF_DATA says. The fetch script is the `gpconf fetch` subcommand; tools/fetch.py runs the same code in a clone.

The installed copy is simulated without a build: the package's files are copied into a scratch site folder and the
corpus's shipped files into its corpus/ folder, as the build of a later stage will do, and every run is a subprocess
with only that folder on PYTHONPATH, a scratch HOME and no GPCONF_DATA. No test makes a network request: the fetch
is exercised with --dry-run or with a stub in place of the request."""
import contextlib
import glob
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gpconf import locate  # noqa: E402
from gpconf import fetch as gfetch  # noqa: E402
from gpconf.__main__ import main as gpconf_main  # noqa: E402

VERSION = locate.corpus_version(ROOT)
FETCHLIST = json.load(open(os.path.join(ROOT, "tools", "fetchlist.json")))
NORMAL_ENTRIES = [e for e in FETCHLIST if not e.get("recapture_of")]


def shipped_files(root):
    """What ships with the corpus, relative to its root: the files the runner reads besides provider data."""
    rels = ["manifest.json", os.path.join("tools", "fetchlist.json")]
    for pattern in ("fixtures/*/expected.json", "fixtures/*/case.md", "derived/**/*", "vectors/**/*"):
        rels += [os.path.relpath(p, root) for p in glob.glob(os.path.join(root, pattern), recursive=True) if os.path.isfile(p)]
    return sorted(set(rels))


def install(tmp, with_corpus=True):
    """A copy of the package outside the repository -> (site folder, HOME, a project folder holding the user's adapter)."""
    site, home, project = (os.path.join(tmp, d) for d in ("site", "home", "project"))
    pkg = os.path.join(site, "gpconf")
    os.makedirs(site)
    shutil.copytree(os.path.join(ROOT, "gpconf"), pkg, ignore=shutil.ignore_patterns("__pycache__", locate.BUNDLED))
    if with_corpus:
        for rel in shipped_files(ROOT):
            dest = os.path.join(pkg, locate.BUNDLED, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy(os.path.join(ROOT, rel), dest)
    os.makedirs(home)
    os.makedirs(project)
    shutil.copy(os.path.join(ROOT, "gpconf", "adapters", "reference.py"), os.path.join(project, "my_adapter.py"))
    return site, home, project


def run_installed(site, home, cwd, *args, extra_env=None):
    env = {"PATH": os.environ.get("PATH", ""), "HOME": home, "PYTHONPATH": site, "PYTHONDONTWRITEBYTECODE": "1"}
    if sys.platform.startswith("win"):
        env.update({"USERPROFILE": home, "LOCALAPPDATA": os.path.join(home, "AppData", "Local"), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")})
    env.update(extra_env or {})
    p = subprocess.run([sys.executable, *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=300)
    return p.returncode, p.stdout + p.stderr


def raw_present():
    return all(os.path.exists(os.path.join(ROOT, "fixtures", e["case"], "raw", e["file"])) for e in NORMAL_ENTRIES)


def copy_raw(dest, include_recaptures=False):
    """The clone's provider files into a data folder: what a completed `gpconf fetch` leaves there (a normal fetch
    requests no re-capture)."""
    for e in FETCHLIST:
        if e.get("recapture_of") and not include_recaptures:
            continue
        for name in (e["file"], e["file"] + ".meta.json"):
            src = os.path.join(ROOT, "fixtures", e["case"], "raw", name)
            if os.path.exists(src):
                d = os.path.join(dest, "fixtures", e["case"], "raw")
                os.makedirs(d, exist_ok=True)
                shutil.copy(src, d)


class CacheFolder(unittest.TestCase):
    def test_linux_and_others(self):
        self.assertEqual(locate.user_cache_dir("0.3.0", env={}, platform="linux", home="/h"), "/h/.cache/gpconf/0.3.0")
        self.assertEqual(locate.user_cache_dir("0.3.0", env={"XDG_CACHE_HOME": "/x"}, platform="linux", home="/h"), "/x/gpconf/0.3.0")
        # the XDG specification says a relative value is ignored
        self.assertEqual(locate.user_cache_dir("0.3.0", env={"XDG_CACHE_HOME": "rel"}, platform="linux", home="/h"), "/h/.cache/gpconf/0.3.0")

    def test_macos(self):
        self.assertEqual(locate.user_cache_dir("0.3.0", env={"XDG_CACHE_HOME": "/x"}, platform="darwin", home="/Users/u"),
                         "/Users/u/Library/Caches/gpconf/0.3.0")

    def test_windows(self):
        got = locate.user_cache_dir("0.3.0", env={"LOCALAPPDATA": "C:/L"}, platform="win32", home="C:/U")
        self.assertEqual(got, os.path.join("C:/L", "gpconf", "Cache", "0.3.0"))
        got = locate.user_cache_dir("0.3.0", env={}, platform="win32", home="C:/U")
        self.assertEqual(got, os.path.join("C:/U", "AppData", "Local", "gpconf", "Cache", "0.3.0"))


class Precedence(unittest.TestCase):
    def test_data_root_order(self):
        env = {locate.DATA_ENV: "/from-env"}
        self.assertEqual(locate.data_root(ROOT, "clone", "/flag", env), ("/flag", "--data"))
        self.assertEqual(locate.data_root(ROOT, "clone", None, env), ("/from-env", locate.DATA_ENV))
        self.assertEqual(locate.data_root(ROOT, "clone", None, {}), (ROOT, "clone"))
        self.assertEqual(locate.data_root(ROOT, "--root", None, {}), (ROOT, "--root"))
        path, why = locate.data_root(ROOT, "installed", None, {})
        self.assertEqual(why, "per-user cache")
        self.assertTrue(path.endswith(os.path.join("gpconf", VERSION)), path)

    def test_this_checkout_is_a_clone(self):
        self.assertEqual(locate.corpus_root(), (ROOT, "clone"))

    def test_a_root_that_is_not_a_corpus_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(locate.CorpusNotFound):
            locate.corpus_root(tmp)

    def test_a_clone_prints_no_data_line(self):
        out = io.StringIO()
        with mock.patch.dict(os.environ, {}, clear=False), contextlib.redirect_stdout(out):
            os.environ.pop(locate.DATA_ENV, None)
            gpconf_main(["run", "--adapter", "tests.adapters.reference:Parser", "--case", "alpha5-encoding-vectors"])
        self.assertNotIn("provider data:", out.getvalue())


class InstalledCopy(unittest.TestCase):
    """A copy outside the repository, as pip would leave it, with nothing fetched yet."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.site, cls.home, cls.project = install(cls.tmp)
        cls.cache = locate.user_cache_dir(VERSION, env={}, home=cls.home)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_the_copy_not_the_repository_is_imported(self):
        code, out = run_installed(self.site, self.home, self.project, "-c", "import gpconf; print(gpconf.__file__)")
        self.assertEqual(code, 0, out)
        self.assertTrue(out.strip().startswith(self.site), out)

    def test_an_offline_run_finds_the_bundled_corpus_and_names_the_cache(self):
        code, out = run_installed(self.site, self.home, self.project, "-m", "gpconf", "run", "--adapter", "my_adapter:Parser")
        self.assertEqual(code, 0, out)
        self.assertIn(f"provider data: {self.cache} (per-user cache)", out)
        self.assertIn("17 case(s): 4 pass (exact), 0 pass within tolerance, 0 fail, 0 skip, 13 need fetched data, 0 not exercised", out)
        self.assertIn("fetch it with python3 -m gpconf fetch.", out)
        self.assertNotIn("tools/fetch.py", out)
        self.assertIn("in every format measured here (CSV not measured: not fetched)", out)
        self.assertFalse(os.path.exists(self.cache), "a run must not create the cache folder")

    def test_list_reads_the_bundled_manifest(self):
        code, out = run_installed(self.site, self.home, self.project, "-m", "gpconf", "list")
        self.assertEqual(code, 0, out)
        self.assertEqual(len(out.strip().splitlines()), 17, out)

    def test_fetch_dry_run_plans_every_normal_entry_into_the_cache_and_writes_nothing(self):
        code, out = run_installed(self.site, self.home, self.project, "-m", "gpconf", "fetch", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn(f"provider data: {self.cache} (per-user cache)", out)
        self.assertEqual(sum(1 for line in out.splitlines() if line.startswith("FETCH ")), len(NORMAL_ENTRIES), out)
        self.assertIn(f"dry run: no request made; a run would make {len(NORMAL_ENTRIES)} request(s) and leave 0 entries as they are", out)
        self.assertFalse(os.path.exists(self.cache), "a dry run must not create the cache folder")

    def test_the_data_flag_and_the_variable_redirect_run_and_fetch(self):
        data = os.path.join(self.tmp, "chosen data")
        code, out = run_installed(self.site, self.home, self.project, "-m", "gpconf", "fetch", "--dry-run", "--data", data)
        self.assertEqual(code, 0, out)
        self.assertIn(f"provider data: {data} (--data)", out)
        code, out = run_installed(self.site, self.home, self.project, "-m", "gpconf", "fetch", "--dry-run", extra_env={locate.DATA_ENV: data})
        self.assertIn(f"provider data: {data} ({locate.DATA_ENV})", out)
        code, out = run_installed(self.site, self.home, self.project, "-m", "gpconf", "run", "--adapter", "my_adapter:Parser", "--data", data)
        self.assertEqual(code, 0, out)
        self.assertIn(f"fetch it with python3 -m gpconf fetch --data '{data}'.", out)

    def test_with_fetched_data_the_copy_runs_every_case(self):
        if not raw_present():
            self.skipTest("provider files absent (public clone): nothing to copy into the data folder")
        data = os.path.join(self.tmp, "fetched")
        copy_raw(data)
        code, out = run_installed(self.site, self.home, self.project, "-m", "gpconf", "run", "--adapter", "my_adapter:Parser",
                                  extra_env={locate.DATA_ENV: data})
        self.assertEqual(code, 0, out)
        self.assertIn(f"provider data: {data} ({locate.DATA_ENV})", out)
        self.assertIn("17 case(s): 16 pass (exact), 0 pass within tolerance, 0 fail, 0 skip, 0 need fetched data, 1 not exercised", out)
        self.assertIn("reads this month's launches in every format it reads here", out)
        self.assertIn("3 case(s) ran without 3 of their provider files", out)  # the re-captures a normal fetch leaves out
        self.assertIn("only with --include-recaptures", out)
        self.assertNotIn("fetch it with", out)  # nothing a normal fetch would bring is missing


class InstalledPresets(unittest.TestCase):
    """D-151: --preset runs a shipped adapter from an installed copy, with no adapter written."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.site, cls.home, cls.project = install(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_preset(self, name):
        return run_installed(self.site, self.home, self.project, "-m", "gpconf", "run", "--preset", name)

    def test_the_standard_library_presets_run_offline(self):
        code, out = self.run_preset("reference")
        self.assertEqual(code, 0, out)
        self.assertIn("parser: preset reference\n", out)
        self.assertIn("17 case(s): 4 pass (exact), 0 pass within tolerance, 0 fail, 0 skip, 13 need fetched data, 0 not exercised", out)
        code, out = self.run_preset("naive")
        self.assertEqual(code, 1, out)  # it fails the four offline cases, which is what it is for
        self.assertIn("parser: preset naive (a demonstration of failure, not a parser anyone should use)", out)
        self.assertIn("17 case(s): 0 pass (exact), 0 pass within tolerance, 4 fail, 0 skip, 13 need fetched data, 0 not exercised", out)

    def test_the_library_presets_name_the_version_found(self):
        code, out = run_installed(self.site, self.home, self.project, "-m", "gpconf", "presets")
        self.assertEqual(code, 0, out)
        self.assertEqual([line.split()[0] for line in out.strip().splitlines()],
                         ["reference", "naive", "sgp4", "pyephem", "satellite.js", "tle.js", "tle.js-api"])
        from gpconf.presets import found_version
        for name, dist, library in (("sgp4", "sgp4", "python-sgp4"), ("pyephem", "ephem", "PyEphem")):
            code, out = self.run_preset(name)
            if found_version(dist) is None:
                self.assertEqual(code, 2, out)
                self.assertIn(f"needs {library}, which is not installed: pip install {dist}", out)
            else:
                self.assertIn(code, (0, 1), out)
                self.assertIn(f"parser: preset {name} ({library} {found_version(dist)}", out)


class InstalledWithoutCorpus(unittest.TestCase):
    def test_run_refuses_and_check_tle_still_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            site, home, project = install(tmp, with_corpus=False)
            code, out = run_installed(site, home, project, "-m", "gpconf", "run", "--adapter", "my_adapter:Parser")
            self.assertEqual(code, 2, out)
            self.assertIn("no corpus found", out)
            tle = os.path.join(ROOT, "derived", "alpha5-tle", "alpha5-A-100000-saramago-first.tle")
            code, out = run_installed(site, home, project, "-m", "gpconf", "check-tle", tle)
            self.assertEqual(code, 0, out)
            self.assertIn("check-tle", out)


class FetchSubcommand(unittest.TestCase):
    """In-process, with a stub where the request would be."""

    def test_writes_to_the_data_root_and_reads_the_list_from_the_corpus_root(self):
        calls = []

        def stub(entry, root=None):
            calls.append((entry["case"], entry["file"], root))
            return "stub"

        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            code = gfetch.run(["--data", tmp, "--case", "analyst-objects"], fetch_one=stub, out=out, pause=0)
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn(f"provider data: {tmp} (--data)", out.getvalue())
        want = [(e["case"], e["file"]) for e in NORMAL_ENTRIES if e["case"] == "analyst-objects"]
        self.assertEqual([(c, f) for c, f, _ in calls], want)
        self.assertTrue(all(r == tmp for _, _, r in calls), calls)

    def test_gpconf_fetch_and_tools_fetch_run_the_same_code(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        try:
            import fetch as tools_fetch  # noqa: E402
        finally:
            sys.path.pop(0)
        self.assertIs(tools_fetch, gfetch)
        p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fetch.py"), "--dry-run", "--case", "epoch-year-19xx"],
                           cwd=ROOT, capture_output=True, text=True, timeout=120,
                           env={k: v for k, v in os.environ.items() if k != locate.DATA_ENV})
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn(f"provider data: {ROOT} (clone)", p.stdout)
        self.assertIn("dry run: no request made", p.stdout)


if __name__ == "__main__":
    unittest.main()
