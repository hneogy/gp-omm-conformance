# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The adapter templates (0.9.0 item b6, D-426): each language's template, built where its toolchain is on the
machine, runs the two offline TLE cases through `--cmd` and passes both. A template whose toolchain is absent is
skipped with its reason; templates/README.md says which were run where.

Run: python -m unittest tests.test_templates"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf.__main__ import main as gpconf_main  # noqa: E402

T = os.path.join(ROOT, "templates")
CASES = ("alpha5-tle-derived", "corrupt-input")
BUILD_SECONDS = 600
EXE = ".exe" if os.name == "nt" else ""   # Windows runs a built program by its .exe name only (D-437)


def q(path):
    return '"' + path + '"' if " " in path else path


class Templates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="gpconf-templates-")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def build(self, argv, cwd=None):
        r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=BUILD_SECONDS)
        self.assertEqual(r.returncode, 0, f"build failed: {' '.join(argv)}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")

    def grade(self, cmd):
        out = os.path.join(self.tmp, "report.json")
        argv = ["run", "--cmd", cmd, "--root", ROOT, "--json", out]
        for c in CASES:
            argv += ["--case", c]
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()) as s:
            gpconf_main(argv)
        with open(out, encoding="utf-8") as f:
            got = {r["case"]: r["status"] for r in json.load(f)["results"]}
        self.assertEqual(got, {c: "pass" for c in CASES}, s.getvalue()[-3000:])

    def need(self, *tools):
        for t in tools:
            if not shutil.which(t):
                self.skipTest(f"{t} is not on this machine")

    def test_python(self):
        self.grade(f"{q(sys.executable)} {q(os.path.join(T, 'python', 'adapter.py'))} {{fmt}}")

    def test_node(self):
        self.need("node")
        self.grade(f"node {q(os.path.join(T, 'node', 'adapter.mjs'))} {{fmt}}")

    def test_cpp(self):
        cxx = next((c for c in ("c++", "clang++", "g++") if shutil.which(c)), None)
        if cxx is None:
            self.skipTest("no C++ compiler on this machine")
        exe = os.path.join(self.tmp, "adapter-cpp" + EXE)
        self.build([cxx, "-std=c++17", "-O2", "-o", exe, os.path.join(T, "cpp", "adapter.cpp")])
        self.grade(f"{q(exe)} {{fmt}}")

    def test_swift(self):
        self.need("swiftc")
        exe = os.path.join(self.tmp, "adapter-swift" + EXE)
        self.build(["swiftc", "-O", "-o", exe, os.path.join(T, "swift", "adapter.swift")])
        self.grade(f"{q(exe)} {{fmt}}")

    def test_java(self):
        self.need("java")
        r = subprocess.run(["java", "-version"], capture_output=True, text=True)
        if r.returncode != 0:   # macOS ships a stub `java` that only says no runtime is installed
            self.skipTest("no Java runtime on this machine")
        self.grade(f"java {q(os.path.join(T, 'java', 'Adapter.java'))} {{fmt}}")

    def test_go(self):
        self.need("go")
        exe = os.path.join(self.tmp, "adapter-go" + EXE)
        self.build(["go", "build", "-o", exe, os.path.join(T, "go", "adapter.go")])
        self.grade(f"{q(exe)} {{fmt}}")

    def test_rust(self):
        self.need("cargo")
        target = os.path.join(self.tmp, "rust-target")
        self.build(["cargo", "build", "--release", "--offline", "--manifest-path", os.path.join(T, "rust", "Cargo.toml"),
                    "--target-dir", target])
        self.grade(f"{q(os.path.join(target, 'release', 'gpconf-adapter-template' + EXE))} {{fmt}}")

    def test_csharp(self):
        self.need("dotnet")
        out = os.path.join(self.tmp, "csharp-out")
        self.build(["dotnet", "build", "-c", "Release", "-o", out, os.path.join(T, "csharp", "Adapter.csproj")])
        self.grade(f"dotnet {q(os.path.join(out, 'Adapter.dll'))} {{fmt}}")



class Guides(unittest.TestCase):
    """docs/guides (0.9.0 item c2, D-436): one per template; each names a template that exists, runs the two offline
    cases the template test runs, and a guide for a template not run here says it is untested."""

    RUN_HERE = {"python", "node", "cpp", "swift", "java", "rust", "csharp", "go"}   # the four others in CI (D-437)

    def test_each_guide_points_at_its_template_and_the_green_run(self):
        g = os.path.join(ROOT, "docs", "guides")
        names = {n[:-3] for n in os.listdir(g) if n.endswith(".md") and n != "README.md"}
        self.assertEqual(names, {"python", "node", "cpp", "swift", "java", "rust", "csharp", "go"})
        for n in names:
            with self.subTest(guide=n):
                with open(os.path.join(g, n + ".md"), encoding="utf-8") as f:
                    text = f.read()
                paths = re.findall(r"\]\(\.\./\.\./(templates/[^)]+)\)", text)
                self.assertTrue(paths)
                for rel in paths:
                    self.assertTrue(os.path.exists(os.path.join(ROOT, rel)), rel)
                self.assertIn("--case alpha5-tle-derived --case corrupt-input", text)
                self.assertEqual("**Untested.**" in text, n not in self.RUN_HERE)


if __name__ == "__main__":
    unittest.main()
