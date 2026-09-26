"""D-158, v0.3.0 stage 7: the GitHub Action, action.yml and tools/action_report.py.

The Action runs the corpus from its own checkout at the tag a workflow names, offline and report-only: failed cases
exit 0, a preset that cannot run exits 2 with a summary saying nothing ran and nothing about the library, and the job
summary carries the case table, the gate line and the site's sentence. These tests run the report script the way the
composite step does, with this repository as the action's folder and scratch files for GitHub's summary and outputs."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def read(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


ACTION = read(os.path.join(ROOT, "action.yml"))
SENTENCE = "A count is a result against that version on that date, not a verdict on the project."


def run_step(preset, python=sys.executable, cwd=None, extra_env=None, full=False):
    """The composite step's command, with the environment the Action sets -> (exit, summary, outputs), and with
    full=True also the step's log and the JSON report it wrote."""
    tmp = tempfile.mkdtemp()
    summary, outputs = os.path.join(tmp, "summary.md"), os.path.join(tmp, "output.txt")
    command = re.search(r"^      run: '(.*)'$", ACTION, re.M).group(1)
    env = dict(os.environ, GPCONF_ACTION_PATH=ROOT, GPCONF_PRESET=preset, GPCONF_PYTHON=python, GPCONF_MODULE="",
               GITHUB_STEP_SUMMARY=summary, GITHUB_OUTPUT=outputs, RUNNER_TEMP=tmp)
    env.pop("GPCONF_DATA", None)
    env.update(extra_env or {})
    p = subprocess.run(["bash", "-c", command], cwd=cwd or tmp, env=env, capture_output=True, text=True, timeout=300)
    out = {k: v for k, v in (line.split("=", 1) for line in read(outputs).splitlines() if "=" in line)}
    result = (p.returncode, read(summary), out)
    if full:
        result += (p.stdout + p.stderr, json.loads(read(out["report"])) if out.get("report") else None)
    shutil.rmtree(tmp, ignore_errors=True)
    return result


class Definition(unittest.TestCase):
    def test_a_composite_action_that_runs_from_its_own_checkout(self):
        self.assertIn("using: composite", ACTION)
        self.assertIn("GPCONF_ACTION_PATH: ${{ github.action_path }}", ACTION)
        self.assertIn("run: '\"$GPCONF_PYTHON\" \"$GPCONF_ACTION_PATH/tools/action_report.py\"'", ACTION)

    def test_inputs_reach_the_script_through_the_environment_only(self):
        run_line = re.search(r"^      run: .*$", ACTION, re.M).group(0)
        self.assertNotIn("${{", run_line)  # no expression in the shell text: no script injection through an input

    def test_it_never_fetches_and_never_installs(self):
        self.assertNotRegex(ACTION, r"gpconf fetch|pip install|npm install")
        script = read(os.path.join(ROOT, "tools", "action_report.py"))
        self.assertNotRegex(script, r"\"fetch\"|pip install")
        self.assertIn('"--data", empty', script)
        self.assertIn('"--no-fetch-hint"', script)

    def test_the_outputs_and_no_badge(self):
        for name in ("report:", "failed:", "exercised:"):
            self.assertIn(f"  {name}", ACTION)
        self.assertNotRegex(ACTION.lower(), r"badge|shields")


class Behaviour(unittest.TestCase):
    def test_a_passing_preset(self):
        code, summary, out = run_step("reference")
        self.assertEqual(code, 0, summary)
        self.assertIn("**4 of 17 cases exercised**, offline: 4 pass", summary)
        self.assertIn("| case | status | exact | tol | fail | skip | n/e | n/f |", summary)
        self.assertIn("**Gate, this month's launches:**", summary)
        self.assertIn(SENTENCE, summary)
        self.assertEqual((out.get("failed"), out.get("exercised")), ("0", "4"))
        self.assertTrue(out.get("report", "").endswith("gpconf-report-reference.json"))

    def test_failed_cases_do_not_fail_the_job(self):
        code, summary, out = run_step("naive")
        self.assertEqual(code, 0, summary)
        self.assertEqual(out.get("failed"), "4")
        self.assertIn("Failed cases do not fail this job.", summary)
        self.assertIn("a demonstration of failure, not a parser anyone should use", summary)

    def test_a_preset_that_cannot_run_is_a_setup_error(self):
        code, summary, out = run_step("skyfield")  # no such preset
        self.assertEqual(code, 2, summary)
        self.assertIn("**Setup error: nothing was run.**", summary)
        self.assertIn("not a result about the library", summary)
        self.assertNotIn("|---|", summary)
        try:
            import ephem  # noqa: F401
            return
        except ImportError:
            pass
        code, summary, _ = run_step("pyephem")
        self.assertEqual(code, 2, summary)
        self.assertIn("needs PyEphem, which is not installed: pip install ephem. Nothing was run; this says nothing about PyEphem.", summary)

    @unittest.skipUnless(shutil.which("node"), "Node.js not installed")
    def test_a_node_preset_without_its_library_is_a_setup_error(self):
        code, summary, _ = run_step("tle.js")
        self.assertEqual(code, 2, summary)
        self.assertIn("could not import tle.js", summary)

    def test_the_action_names_no_fetch_command(self):
        # the live test of 2026-09-26 printed the runner's advice to fetch into the Action's empty data folder, which
        # goes with the job, and on Windows as python3 with a quoted Windows path (D-158); the log and the report now
        # say only that provider data is not shipped, and every status is what it was
        code, summary, out, log, report = run_step("reference", full=True)
        self.assertEqual(code, 0, summary)
        for text in (log, summary, json.dumps(report)):
            self.assertNotIn("fetch it with", text)
            self.assertNotRegex(text, r"tools[/\\]fetch\.py|gpconf fetch|--check-drift")
        missing = [i for r in report["results"] for i in r["items"] if i["status"] == "not-fetched"]
        self.assertTrue(missing)
        self.assertEqual({i["detail"] for i in missing}, {"not on disk: provider data is not shipped with the corpus"})
        self.assertEqual(sum(1 for r in report["results"] if r["status"] == "not-fetched"), 13)

    def test_the_hint_is_suppressed_only_where_asked(self):
        # outside the Action, a run still names the command that fetches the missing files
        empty = tempfile.mkdtemp()
        try:
            base = [sys.executable, "-m", "gpconf", "run", "--preset", "reference", "--data", empty, "--case", "epoch-year-19xx"]
            plain = subprocess.run(base, cwd=ROOT, capture_output=True, text=True)
            quiet = subprocess.run(base + ["--no-fetch-hint"], cwd=ROOT, capture_output=True, text=True)
        finally:
            shutil.rmtree(empty, ignore_errors=True)
        self.assertIn("Provider data is not shipped with the corpus; fetch it with python3 ", plain.stdout)
        self.assertNotIn("fetch it with", quiet.stdout)
        table = lambda s: [line for line in s.splitlines() if line.startswith("epoch-year-19xx")]
        self.assertEqual(table(plain.stdout), table(quiet.stdout))
        self.assertEqual(plain.returncode, quiet.returncode)

    def test_a_drifted_source_reads_as_a_sentence_either_way(self):
        sys.path.insert(0, ROOT)
        from gpconf.runner import Runner
        from gpconf.adapters.reference import Parser
        manifest = json.loads(read(os.path.join(ROOT, "manifest.json")))
        case, src = next((c["id"], s) for c in manifest["cases"] for s in c.get("sources", [])
                         if s.get("tier") == "stable" and "/raw/" in s["path"])
        data = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.dirname(os.path.join(data, src["path"])))
            with open(os.path.join(data, src["path"]), "wb") as f:
                f.write(b"bytes that are not the tested snapshot\n")
            details = {}
            for hints in (True, False):
                r = Runner(Parser(), root=ROOT, data=data, data_why="--data", fetch_hints=hints).run(case_ids=[case])[0]
                details[hints] = [i.detail for i in r.items if i.check == "stable-source-drift"]
        finally:
            shutil.rmtree(data, ignore_errors=True)
        self.assertEqual(len(details[True]), 1)
        self.assertIn(" --check-drift; if CelesTrak changed this first-ever record", details[True][0])
        self.assertIn("instead. If CelesTrak changed this first-ever record", details[False][0])
        self.assertNotIn("--check-drift", details[False][0])

    def test_offline_whatever_the_job_sets(self):
        code, summary, out = run_step("reference", extra_env={"GPCONF_DATA": ROOT})
        self.assertEqual(code, 0, summary)
        self.assertIn("13 need provider data, which this Action does not fetch", summary)
        self.assertEqual(out.get("exercised"), "4")


if __name__ == "__main__":
    unittest.main()
