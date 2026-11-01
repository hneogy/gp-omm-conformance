# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""D-361: Trusted Publishing. The maintainer's SHA-256 of a release's two files travel in the annotated tag's message,
and .github/workflows/publish.yml publishes the files it builds from the tag only when tools/release_hashes.py finds them
byte for byte the maintainer's.

The check is exercised on folders made here: it passes on the two files the message names, fails (exit 1) on a file
that differs, and refuses (exit 2) anything that is not a release: a missing, extra or linked file, a tag that does not
name the version, a hash line missing, repeated, malformed or naming another file. The message goes through a real
`git tag -a` and back, where git is installed. A real build of v0.7.0 checked against PyPI's hashes is in the private
handoff (it needs the build frontend, which the suite does not have). The workflows' own shape is checked as text: every
action pinned by commit (D-269), and publish.yml's permissions and triggers."""
import io
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import release_hashes as rh  # noqa: E402

WORKFLOWS = os.path.join(ROOT, ".github", "workflows")
WHEEL, SDIST = "gpconf-1.2.3-py3-none-any.whl", "gpconf-1.2.3.tar.gz"


def remove_tree(path):
    """shutil.rmtree that also removes read-only files: git writes its objects read-only, and Windows refuses to
    unlink a read-only file (WinError 5), which failed ThroughGit's clean-up in the private repository's Windows CI
    (lane C, 2026-10-24). The flag is cleared and the removal tried again, on Windows only, for a file only (git's
    objects are files), and never through a link (os.chmod follows one, and the publishing step's tree links to the
    interpreter: D-365's reading); elsewhere the error is raised as before."""
    def clear_and_retry(func, p, exc):
        if os.name != "nt" or os.path.islink(p) or not os.path.isfile(p):
            raise exc if isinstance(exc, BaseException) else exc[1]   # onexc hands the exception, onerror exc_info
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=clear_and_retry)
    else:
        shutil.rmtree(path, onerror=clear_and_retry)


class Folder(unittest.TestCase):
    """A pyproject.toml at 1.2.3 and a dist folder with the two files."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(remove_tree, self.tmp)
        self.pyproject = os.path.join(self.tmp, "pyproject.toml")
        with open(self.pyproject, "w", encoding="utf-8") as f:
            f.write('[project]\nname = "gpconf"\nversion = "1.2.3"\n')
        self.dist = os.path.join(self.tmp, "dist")
        os.mkdir(self.dist)
        self.write(WHEEL, b"the wheel's bytes")
        self.write(SDIST, b"the sdist's bytes")

    def write(self, name, data):
        with open(os.path.join(self.dist, name), "wb") as f:
            f.write(data)

    def message(self, epoch=1792023858):
        return rh.message(self.dist, "1.2.3", epoch)

    def run_check(self, text, tag="v1.2.3", **extra):
        path = os.path.join(self.tmp, "message.txt")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        argv = ["check", "--dist", self.dist, "--pyproject", self.pyproject, "--tag", tag, "--message", path]
        for k, v in extra.items():
            argv += ["--" + k.replace("_", "-"), v]
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = rh.main(argv)
        return code, out.getvalue(), err.getvalue()


class TheMessage(Folder):
    def test_the_message_is_the_subject_a_sentence_and_one_line_per_file(self):
        lines = self.message().split("\n")
        self.assertEqual(lines[0], "gp-omm-conformance 1.2.3")
        self.assertEqual(lines[1], "")
        self.assertIn("SOURCE_DATE_EPOCH 1792023858", lines[2])
        self.assertEqual(lines[3], f"{rh.sha256_file(os.path.join(self.dist, WHEEL))}  {WHEEL}")
        self.assertEqual(lines[4], f"{rh.sha256_file(os.path.join(self.dist, SDIST))}  {SDIST}")
        self.assertEqual(lines[5:], [""])

    def test_the_lines_are_what_sha256sum_prints(self):
        # "<64 lowercase hex>  <name>": what `sha256sum` and `shasum -a 256` print in the folder, so a maintainer can
        # compare the message with their own tool's output by eye.
        import hashlib
        want = hashlib.sha256(b"the wheel's bytes").hexdigest()
        self.assertIn(f"\n{want}  {WHEEL}\n", self.message())

    def test_message_refuses_a_folder_that_is_not_the_two_files(self):
        self.write("gpconf-1.2.3-cp314-cp314-macosx_11_0_arm64.whl", b"x")
        with self.assertRaisesRegex(rh.Refused, "must hold exactly"):
            self.message()


class TheCheck(Folder):
    def test_the_two_files_of_the_message_pass(self):
        code, out, err = self.run_check(self.message())
        self.assertEqual(code, 0, err)
        self.assertEqual(out.count("MATCH"), 2)
        self.assertNotIn("DIFFERS", out)

    def test_a_file_that_differs_by_one_byte_fails(self):
        text = self.message()
        self.write(SDIST, b"the sdist's bytez")
        code, out, err = self.run_check(text)
        self.assertEqual(code, 1)
        self.assertIn(f"{SDIST}: DIFFERS", out)
        self.assertIn(f"{WHEEL}: MATCH", out)
        self.assertIn("nothing is published", err)

    def test_both_files_swapped_fail(self):
        a, b = rh.sha256_file(os.path.join(self.dist, WHEEL)), rh.sha256_file(os.path.join(self.dist, SDIST))
        code, out, _ = self.run_check(f"x\n\n{b}  {WHEEL}\n{a}  {SDIST}\n")
        self.assertEqual(code, 1)
        self.assertEqual(out.count("DIFFERS"), 2)

    def test_outputs_are_written_on_a_match_only(self):
        output = os.path.join(self.tmp, "github_output")
        code, _, _ = self.run_check(self.message(), github_output=output)
        self.assertEqual(code, 0)
        with open(output, encoding="utf-8") as f:
            got = dict(line.split("=", 1) for line in f.read().splitlines())
        self.assertEqual(got, {"version": "1.2.3", "wheel": WHEEL, "sdist": SDIST,
                               "wheel-sha256": rh.sha256_file(os.path.join(self.dist, WHEEL)),
                               "sdist-sha256": rh.sha256_file(os.path.join(self.dist, SDIST))})
        os.remove(output)
        text = self.message()
        self.write(WHEEL, b"another wheel")
        code, _, _ = self.run_check(text, github_output=output)
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(output))

    def test_the_summary_says_which_matched(self):
        summary = os.path.join(self.tmp, "summary.md")
        text = self.message()
        self.write(WHEEL, b"another wheel")
        self.run_check(text, summary=summary)
        with open(summary, encoding="utf-8") as f:
            body = f.read()
        self.assertIn(f"`{WHEEL}`: **DIFFERS**", body)
        self.assertIn(f"`{SDIST}`: **MATCH**", body)

    def test_a_signature_and_prose_around_the_lines_are_not_read(self):
        text = ("gp-omm-conformance 1.2.3\n\nSome words, a number 1792023858 and a short hex deadbeef.\n"
                + self.message().split("\n", 3)[3]
                + "-----BEGIN PGP SIGNATURE-----\n\niQIzBAABCAAdFiEEabcdefGHIJ+/0123456789=\n=AbCd\n-----END PGP SIGNATURE-----\n")
        code, _, err = self.run_check(text)
        self.assertEqual(code, 0, err)


class Refusals(Folder):
    """Exit 2, in words, and no MATCH: what is checked is not a release."""

    def refused(self, text, pattern, tag="v1.2.3"):
        code, out, err = self.run_check(text, tag=tag)
        self.assertEqual(code, 2, (out, err))
        self.assertRegex(err, pattern)
        self.assertNotIn("MATCH", out)

    def test_a_tag_that_does_not_name_the_version(self):
        self.refused(self.message(), r"the tag is 'v1\.2\.4'", tag="v1.2.4")
        self.refused(self.message(), r"tagged v1\.2\.3", tag="1.2.3")

    def test_an_extra_file_in_dist(self):
        text = self.message()
        self.write("gpconf-1.2.3-py2.py3-none-any.whl", b"x")
        self.refused(text, "must hold exactly")

    def test_a_hidden_file_in_dist(self):
        text = self.message()
        self.write(".DS_Store", b"x")
        self.refused(text, "must hold exactly")

    def test_a_missing_file_in_dist(self):
        text = self.message()
        os.remove(os.path.join(self.dist, SDIST))
        self.refused(text, "must hold exactly")

    @unittest.skipIf(not hasattr(os, "symlink") or sys.platform == "win32", "symbolic links")
    def test_a_linked_file_in_dist(self):
        text = self.message()
        target = os.path.join(self.tmp, "elsewhere")
        os.replace(os.path.join(self.dist, SDIST), target)
        os.symlink(target, os.path.join(self.dist, SDIST))
        self.refused(text, "not a plain file")

    def test_a_missing_line(self):
        lines = self.message().split("\n")
        self.refused("\n".join(lines[:4]) + "\n", f"no SHA-256 for {re.escape(SDIST)}")
        self.refused("gp-omm-conformance 1.2.3\n", "no SHA-256 for")

    def test_a_repeated_line(self):
        lines = self.message().split("\n")
        self.refused("\n".join(lines[:5] + [lines[4]]) + "\n", "twice")

    def test_a_line_for_another_file(self):
        lines = self.message().split("\n")
        other = lines[4].replace(SDIST, "gpconf-1.2.2.tar.gz")
        self.refused("\n".join(lines[:5] + [other]) + "\n", "not one of this release's files")

    def test_malformed_lines(self):
        lines = self.message().split("\n")
        digest, name = lines[3].split("  ")
        for bad in (f"{digest.upper()}  {name}",            # sha256sum and the tool write lowercase
                    f"{digest} {name}",                     # one space
                    f"{digest} *{name}",                    # a binary-mode marker
                    f"{digest}  dist/{name}",               # a path, not the file's name
                    f"{digest}  {name} ",                   # anything after the name
                    f"sha256 {digest}  {name}",             # anything before the hash
                    f"{digest}0  {name}",                   # 65 hex digits
                    f"{digest}  {name}\r"):                 # a CR line end
            with self.subTest(bad=bad):
                self.refused("\n".join(lines[:3] + [bad, lines[4]]) + "\n", "is not '<64 lowercase hex>  <file name>'")

    def test_a_version_that_names_no_files_this_check_knows(self):
        with open(self.pyproject, "w", encoding="utf-8") as f:
            f.write('[project]\nversion = "1.2.3 ; x"\n')
        self.refused(self.message(), "is not one this check knows")
        with open(self.pyproject, "w", encoding="utf-8") as f:
            f.write('[project]\nname = "gpconf"\n')
        self.refused(self.message(), r"no \[project\] version in")

    def test_an_unreadable_message(self):
        path = os.path.join(self.tmp, "message.txt")
        with open(path, "wb") as f:
            f.write(b"\xff\xfe not utf-8")
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = rh.main(["check", "--dist", self.dist, "--pyproject", self.pyproject, "--tag", "v1.2.3", "--message", path])
        self.assertEqual(code, 2)
        self.assertIn("cannot read the tag message", err.getvalue())


class TheVersion(unittest.TestCase):
    """[project].version, read as the build reads it: tomllib where Python has it, a pattern scoped to the [project]
    table before 3.11. Both readers are held to the same forms on every Python."""
    FORMS = {'[project]\nname = "gpconf"\nversion = "0.8.0"\n': "0.8.0",
             '[project]\nversion = "0.8.0"  # the release\n': "0.8.0",
             "[project]\nversion = '0.8.0'\n": "0.8.0",
             '[tool.x]\nversion = "9"\n\n[project]\nname = "gpconf"\nversion = "0.8.0"\n': "0.8.0",
             '[project]\nname = "gpconf"\n\n[tool.x]\nversion = "9"\n': None,
             '[build-system]\nrequires = ["setuptools>=77"]\n': None}

    def test_the_pattern_reads_the_project_table_only(self):
        for text, want in self.FORMS.items():
            with self.subTest(text=text):
                self.assertEqual(rh.version_by_pattern(text), want)

    def test_tomllib_agrees_where_python_has_it(self):
        try:
            import tomllib
        except ImportError:
            self.skipTest("Python before 3.11 has no tomllib; the pattern is what reads the version there")
        for text, want in self.FORMS.items():
            with self.subTest(text=text):
                self.assertEqual(tomllib.loads(text).get("project", {}).get("version"), want)

    def test_a_project_that_is_no_table_and_a_version_with_a_line_break_are_refused(self):
        for text in ('project = "x"\n', '[project]\nversion = "0.8.0\\n"\n'):
            with self.subTest(text=text):
                tmp = tempfile.mkdtemp()
                self.addCleanup(remove_tree, tmp)
                path = os.path.join(tmp, "pyproject.toml")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                with self.assertRaises(rh.Refused):
                    rh.version_of(path)

    def test_the_repository_s_own_version(self):
        with open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(rh.version_by_pattern(text), rh.version_of(os.path.join(ROOT, "pyproject.toml")))


@unittest.skipIf(shutil.which("git") is None, "git is not installed")
class ThroughGit(Folder):
    """The message as the workflow reads it: written into an annotated tag by `git tag -a -F` and read back with
    `git for-each-ref --format=%(contents)`; git's message clean-up leaves the lines as they were."""

    def git(self, *args, cwd=None):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false",
                               "-c", "tag.gpgsign=false", *args], cwd=cwd or self.repo, capture_output=True, text=True,
                              encoding="utf-8", check=True)

    def test_an_annotated_tag_carries_the_message_through(self):
        self.repo = os.path.join(self.tmp, "repo")
        os.mkdir(self.repo)
        self.git("init", "--quiet")
        with open(os.path.join(self.repo, "README"), "w", encoding="utf-8") as f:
            f.write("x\n")
        self.git("add", "README")
        self.git("commit", "--quiet", "-m", "x")
        path = os.path.join(self.tmp, "tag-message-in.txt")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(self.message())
        self.git("tag", "-a", "v1.2.3", "-F", path)
        self.assertEqual(self.git("cat-file", "-t", "refs/tags/v1.2.3").stdout.strip(), "tag")
        back = self.git("for-each-ref", "--format=%(contents)", "refs/tags/v1.2.3").stdout
        code, out, err = self.run_check(back)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.count("MATCH"), 2)


def workflow(name):
    with open(os.path.join(WORKFLOWS, name), encoding="utf-8") as f:
        return f.read()


JOB = re.compile(r"(?m)^  ([A-Za-z_][A-Za-z0-9_-]*):[ \t]*$")


def jobs_of(text):
    """publish.yml's text -> {job id: the job's own text}: every two-space key under `jobs:`, which is the last top-level
    key (a test below holds it there)."""
    body = text.split("\njobs:\n", 1)[1]
    starts = [(m.start(), m.group(1)) for m in JOB.finditer(body)]
    return {name: body[at:(starts[i + 1][0] if i + 1 < len(starts) else len(body))] for i, (at, name) in enumerate(starts)}


def conditions_of(text):
    """-> {job id: the job's `if:` expression}, read from each job's own text."""
    out = {}
    for job, body in jobs_of(text).items():
        m = re.search(r"(?m)^    if: (.+)$", body)
        out[job] = m.group(1).strip() if m else None
    return out


def publishing_step(text, job="pypi"):
    """The `run:` script of a publishing job's check step, as bash would get it."""
    body = jobs_of(text)[job]
    after = body.split("- name: The files about to be published", 1)[1].split("        run: |\n", 1)[1]
    lines = []
    for line in after.split("\n"):
        if line.strip() and not line.startswith(" " * 10):
            break
        lines.append(line[10:])
    return "\n".join(lines).rstrip() + "\n"


PUSH = "github.event_name == 'push' && github.ref_type == 'tag' && startsWith(github.ref, 'refs/tags/v')"
BY_HAND = "github.event_name == 'workflow_dispatch' && github.ref_type == 'tag' && startsWith(github.ref, 'refs/tags/v')"
CONDITIONS = {"build": "github.ref_type == 'tag' && startsWith(github.ref, 'refs/tags/v')", "pypi": PUSH, "testpypi": BY_HAND}
PUBLISH = "uses: pypa/gh-action-pypi-publish@"


def shape_problems(text):
    """What the shape tests below hold publish.yml to, as a list of problems (empty when it holds): used on the file and
    on the wrong forms the reviews of D-361 built, each of which an earlier form of these tests let through."""
    problems = []
    if re.search(r"(?m)^[A-Za-z]", text.split("\njobs:\n", 1)[1]):
        problems.append("a top-level key after jobs:")
    jobs = jobs_of(text)
    if sorted(jobs) != ["build", "pypi", "testpypi"]:
        problems.append(f"jobs {sorted(jobs)}")
    if conditions_of(text) != CONDITIONS:
        problems.append(f"conditions {conditions_of(text)}")
    for word in ("write-all", "read-all", "packages-dir", "packages_dir", "repository_url"):
        if word in text:
            problems.append(word)
    if text.count("id-token: write") != 2 or "id-token" in jobs.get("build", ""):
        problems.append("id-token outside the two publishing jobs")
    if text.count(PUBLISH) != 2 or jobs.get("pypi", "").count(PUBLISH) != 1 or jobs.get("testpypi", "").count(PUBLISH) != 1:
        problems.append("not one publish step in each publishing job")
    if text.count("repository-url:") != 1 or "repository-url: https://test.pypi.org/legacy/" not in jobs.get("testpypi", ""):
        problems.append("repository-url outside the TestPyPI job")
    for name in ("pypi", "testpypi"):
        body = jobs.get(name, "")
        if not (0 <= body.find("- name: The files about to be published") < body.find(PUBLISH)):
            problems.append(f"{name}: the check is not before the publish step")
        if not re.search(r"permissions:\n\s+id-token: write\s+#[^\n]*\n\s+steps:", body):
            problems.append(f"{name}: permissions other than id-token: write")
        if not re.search(rf"environment:\n\s+name: {name}\b", body):
            problems.append(f"{name}: environment")
        if "actions/checkout" in body or "pip install" in body or "needs: build" not in body:
            problems.append(f"{name}: a checkout, an install, or no needs: build")
    if "secrets." in text:
        problems.append("a secret")
    return problems


class Workflows(unittest.TestCase):
    """Read as text: the suite has no YAML parser. ThePublishingStep, below, runs the step itself."""

    def test_every_action_is_pinned_by_commit_with_its_version_named(self):
        names = sorted(n for n in os.listdir(WORKFLOWS) if n.endswith((".yml", ".yaml")))
        self.assertIn("publish.yml", names)
        for name in names:
            for line in workflow(name).splitlines():
                m = re.match(r"^\s*(?:-\s+)?uses:\s*(\S+)(.*)$", line)
                if not m:
                    continue
                with self.subTest(workflow=name, uses=m.group(1)):
                    self.assertRegex(m.group(1), r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$", "pinned by a full commit id (D-269)")
                    # publish.yml, the release path, names the exact release each commit is, not a major tag that moves
                    self.assertRegex(m.group(2), r"#\s*v\d+\.\d+\.\d+\b" if name == "publish.yml" else r"#\s*v\d+(\.\d+)*\b",
                                     "the version the commit is, named beside it")

    def test_publish_holds_its_shape(self):
        text = workflow("publish.yml")
        self.assertRegex(text, r"(?m)^permissions: \{\}")
        on = text.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]
        self.assertEqual([l.strip() for l in on.strip().splitlines()], ["push:", 'tags: ["v*"]', "workflow_dispatch:"])
        self.assertEqual(shape_problems(text), [])
        build = jobs_of(text)["build"]
        self.assertRegex(build, r"permissions:\n\s+contents: read\n\s+outputs:")
        self.assertIn("persist-credentials: false", build)

    def test_the_shape_check_catches_the_wrong_forms_the_reviews_built(self):
        text = workflow("publish.yml")
        publish_step = "      - " + PUBLISH
        wrong = {
            "conditions swapped": text.replace(f"if: {PUSH}", "if: @@").replace(f"if: {BY_HAND}", f"if: {PUSH}").replace("if: @@", f"if: {BY_HAND}"),
            "PyPI by hand too": text.replace(f"if: {PUSH}", f"if: {PUSH} || github.event_name == 'workflow_dispatch'"),
            "a fourth job publishing by hand with no check": text + ("\n  pypi-by-hand:\n    needs: build\n    if: github.event_name == 'workflow_dispatch'\n"
                                                                 "    runs-on: ubuntu-24.04\n    environment:\n      name: pypi\n    permissions: write-all\n"
                                                                 "    steps:\n      - uses: actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333   # v8.0.2\n"
                                                                 "        with:\n          name: dist\n          path: dist\n"
                                                                 "      - uses: pypa/gh-action-pypi-publish@dc37677b2e1c63e2034f94d8a5b11f265b73ba33   # v1.14.2\n"),
            "another folder uploaded": text.replace("          attestations: true\n          print-hash: true\n\n  testpypi:",
                                                    "          attestations: true\n          print-hash: true\n          packages-dir: export-dist/\n\n  testpypi:"),
            "a second publish step in the TestPyPI job": text.rstrip("\n") + "\n" + publish_step + "dc37677b2e1c63e2034f94d8a5b11f265b73ba33   # v1.14.2\n",
        }
        for label, form in wrong.items():
            with self.subTest(label):
                self.assertNotEqual(form, text)
                self.assertNotEqual(shape_problems(form), [])

    def test_the_tag_is_read_before_setup_python_and_the_toolchain(self):
        build = jobs_of(workflow("publish.yml"))["build"]
        self.assertLess(build.index("id: tag"), build.index("actions/setup-python"))
        self.assertLess(build.index("id: tag"), build.index("pip install"))
        self.assertIn("tag-object: ${{ steps.tag.outputs.object }}", build)

    def test_both_publishing_jobs_check_the_files_the_same_way(self):
        text = workflow("publish.yml")
        self.assertEqual(publishing_step(text, "pypi"), publishing_step(text, "testpypi"))
        step = publishing_step(text)
        self.assertIn('python3 -I "$RUNNER_TEMP/release_hashes.py" check', step)
        jobs = jobs_of(text)
        for name in ("pypi", "testpypi"):
            self.assertIn("TAG_OBJECT: ${{ needs.build.outputs.tag-object }}", jobs[name])
            self.assertIn("EVENT_AFTER: ${{ github.event.after }}", jobs[name])


@unittest.skipIf(sys.platform == "win32" or shutil.which("git") is None or shutil.which("bash") is None,
                 "runs the step under bash with git (not on Windows)")
class ThePublishingStep(unittest.TestCase):
    """The publishing jobs' check step, as publish.yml writes it, run by bash -eo pipefail against a scratch repository
    reached by file://, the tag annotated with the hashes of two files made here. It passes where the tag is the one the
    build job read and the push event names (or the event names the commit, or there is no event: a run by hand), and
    stops, saying why, where the tag the build job read is missing or another, or the event names another object.
    The wrong forms of the step the second review of D-361 built (a guard deleted, made always true, or made to take an
    empty value) each let through a case the real step stops."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(remove_tree, self.tmp)
        self.remote = os.path.join(self.tmp, "remote")
        os.makedirs(os.path.join(self.remote, "tools"))
        shutil.copy(os.path.join(ROOT, "tools", "release_hashes.py"), os.path.join(self.remote, "tools", "release_hashes.py"))
        with open(os.path.join(self.remote, "pyproject.toml"), "w", encoding="utf-8") as f:
            f.write('[project]\nname = "gpconf"\nversion = "1.2.3"\n')
        self.dist = os.path.join(self.tmp, "dist")
        os.mkdir(self.dist)
        for name, data in ((WHEEL, b"the wheel's bytes"), (SDIST, b"the sdist's bytes")):
            with open(os.path.join(self.dist, name), "wb") as f:
                f.write(data)
        message = os.path.join(self.tmp, "message.txt")
        with open(message, "w", encoding="utf-8", newline="\n") as f:
            f.write(rh.message(self.dist, "1.2.3", 1792023858))
        self.git("init", "--quiet")
        self.git("add", "-A")
        self.git("commit", "--quiet", "-m", "x")
        self.git("tag", "-a", "v1.2.3", "-F", message)
        self.object = self.git("rev-parse", "refs/tags/v1.2.3")
        self.commit = self.git("rev-parse", "HEAD")
        self.shim = os.path.join(self.tmp, "shim")
        os.mkdir(self.shim)
        os.symlink(sys.executable, os.path.join(self.shim, "python3"))
        self.step = publishing_step(workflow("publish.yml"))

    def git(self, *args):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false",
                               "-c", "tag.gpgsign=false", "-c", "init.defaultBranch=main", *args], cwd=self.remote,
                              capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()

    def run_step(self, tag_object, event_after, script=None):
        work = tempfile.mkdtemp(dir=self.tmp)
        shutil.copytree(self.dist, os.path.join(work, "dist"))
        os.mkdir(os.path.join(work, "temp"))
        path = os.path.join(work, "step.sh")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(script if script is not None else self.step)
        env = dict(os.environ, PATH=self.shim + os.pathsep + os.environ.get("PATH", ""), GITHUB_REF_NAME="v1.2.3",
                   GITHUB_SHA=self.commit, GITHUB_SERVER_URL="file://" + self.tmp, GITHUB_REPOSITORY="remote",
                   TAG_OBJECT=tag_object, EVENT_AFTER=event_after, RUNNER_TEMP=os.path.join(work, "temp"),
                   GITHUB_STEP_SUMMARY=os.path.join(work, "temp", "summary.md"))
        p = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", path], cwd=work, env=env,
                           capture_output=True, text=True, encoding="utf-8")
        return p.returncode, p.stdout + p.stderr

    def passing(self):
        return [(self.object, self.object), (self.object, self.commit), (self.object, "")]

    def stopping(self):
        return [("", self.object), ("0" * 40, self.object), (self.object, "1" * 40)]

    def test_the_tag_the_build_job_read_and_the_push_names_passes(self):
        for tag_object, after in self.passing():
            with self.subTest(after=after or "(a run by hand)"):
                code, out = self.run_step(tag_object, after)
                self.assertEqual(code, 0, out)
                self.assertEqual(out.count("MATCH"), 2, out)
                self.assertIn(f"object {self.object}, commit {self.commit}", out)

    def test_another_tag_stops_saying_why(self):
        for tag_object, after in self.stopping():
            with self.subTest(tag_object=tag_object, after=after):
                code, out = self.run_step(tag_object, after)
                self.assertEqual(code, 1, out)
                self.assertIn("::error::", out)
                self.assertNotIn("MATCH", out)

    def test_a_file_that_is_not_the_maintainer_s_stops(self):
        with open(os.path.join(self.dist, WHEEL), "ab") as f:
            f.write(b"\0")
        code, out = self.run_step(self.object, self.object)
        self.assertEqual(code, 1, out)
        self.assertIn(f"{WHEEL}: DIFFERS", out)

    def test_each_wrong_form_of_the_guards_lets_a_stopping_case_through(self):
        tag_guard = '[ -n "$TAG_OBJECT" ] && [ "$object" = "$TAG_OBJECT" ]'
        event_guard = '[ -z "$EVENT_AFTER" ] ||'
        self.assertIn(tag_guard, self.step)
        self.assertIn(event_guard, self.step)
        wrong = {
            "the event guard always true": self.step.replace(event_guard, '[ -n "$EVENT_AFTER" ] ||'),
            "the event guard deleted": re.sub(r"(?m)^\[ -z \"\$EVENT_AFTER\" \].*\n.*\n", "", self.step),
            "the tag guard taking an empty value": self.step.replace(tag_guard, '{ [ -z "$TAG_OBJECT" ] || [ "$object" = "$TAG_OBJECT" ]; }'),
        }
        for label, script in wrong.items():
            with self.subTest(label):
                self.assertNotEqual(script, self.step)
                through = [case for case in self.stopping() if self.run_step(*case, script=script)[0] == 0]
                self.assertTrue(through, "the wrong form stopped every case the real step stops")


if __name__ == "__main__":
    unittest.main()
