# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""tools/run_suite.py's check of the crashes during a run (the owner's instructions, 2026-10-18): its own detector
(faulthandler in every Python the suite starts, one file a process) and macOS's reports, one crash counted once; a
crash test_crashes_080's harness marked is expected, any other is unexpected and stops the run; the check's canary
must be caught, or the run stops too. Times are read from the reports, never from the files' own times.

Run: python -m unittest tests.test_run_suite"""
import contextlib
import datetime as dt
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

POSIX = os.name == "posix"   # the check runs there only: on Windows os.kill ends a process with no handler run
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import run_suite  # noqa: E402

T0 = dt.datetime(2026, 10, 18, 8, 0, 0, tzinfo=dt.timezone(dt.timedelta(hours=-4)))
FATAL_BODY = "Fatal Python error: Segmentation fault\n\nCurrent thread 0x1 (most recent call first):\n  File \"<string>\", line 3 in <module>\n"


def report(folder, name, at, thread_name, signal="SIGSEGV", pid=1, parent=2):
    body = {"captureTime": at.strftime("%Y-%m-%d %H:%M:%S.%f %z"),
            "procPath": "/usr/bin/python3", "pid": pid, "parentProc": "Python", "parentPid": parent, "responsibleProc": "claude",
            "exception": {"type": "EXC_CRASH", "signal": signal}, "faultingThread": 0,
            "threads": [{"name": thread_name, "frames": [{"imageIndex": 0, "symbol": "__kill"}]}],
            "usedImages": [{"name": "libsystem_kernel.dylib"}]}
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        f.write(json.dumps({"app_name": "Python", "bug_type": "309"}) + "\n" + json.dumps(body))


def dump(folder, pid, body=FATAL_BODY, canary=False, argv=("harness.py", "parse", "csv"), started=1):
    with open(os.path.join(folder, f"py-{pid}-{started}.txt"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"pid": pid, "ppid": 2, "executable": "/usr/bin/python3", "argv": list(argv), "orig_argv": None,
                            "cwd": "/tmp", "canary": canary}) + "\n" + body)


class TheCrashCheck(unittest.TestCase):

    def setUp(self):
        self.crashes = tempfile.mkdtemp(prefix="gpconf-crashes-")
        self.reports = tempfile.mkdtemp(prefix="gpconf-reports-")

    def tearDown(self):
        shutil.rmtree(self.crashes, ignore_errors=True)
        shutil.rmtree(self.reports, ignore_errors=True)

    def classify(self):
        return run_suite.classify(self.crashes, T0, T0 + dt.timedelta(minutes=10), self.reports)

    def test_the_detector_counts_a_marked_crash_expected_and_any_other_unexpected(self):
        dump(self.crashes, 101)
        open(os.path.join(self.crashes, "py-101-1.deliberate"), "w").close()
        dump(self.crashes, 102, argv=("-m",))   # what a Python 3.9 started with -m holds when its site module runs
        dump(self.crashes, 103, body="")   # a Python that ended well: a header and nothing more
        expected, unexpected, canary, others = self.classify()
        self.assertEqual([n for _, n, _ in expected], ["py-101-1.txt"])
        self.assertEqual([n for _, n, _ in unexpected], ["py-102-1.txt"])
        self.assertEqual((canary, others), (None, []))
        self.assertEqual(run_suite.summary(expected, unexpected), "crash reports: 1 expected, 1 unexpected")
        text = run_suite.describe(*unexpected[0])
        self.assertIn("['-m']", text)
        self.assertIn("Fatal Python error: Segmentation fault", text)

    def test_a_process_id_used_twice_is_two_files_and_the_marker_is_the_files_own(self):
        """The second reading's finding 8: a pid used twice in one run; the harness's crash under it is expected, and a
        later crash under the same pid is not, nor is it lost."""
        dump(self.crashes, 110, started=1)
        open(os.path.join(self.crashes, "py-110-1.deliberate"), "w").close()
        dump(self.crashes, 110, started=2)
        expected, unexpected, _, _ = self.classify()
        self.assertEqual(([n for _, n, _ in expected], [n for _, n, _ in unexpected]), (["py-110-1.txt"], ["py-110-2.txt"]))

    def test_the_canary_is_counted_neither_way_and_says_the_detector_sees(self):
        dump(self.crashes, 104, canary=True)
        expected, unexpected, canary, others = self.classify()
        self.assertEqual((expected, unexpected, canary, others), ([], [], "py-104-1.txt", []))

    def test_macos_reports_are_a_second_signal_one_crash_counted_once(self):
        dump(self.crashes, 105)   # unexpected, seen by both
        report(self.reports, "Python-a.ips", T0 + dt.timedelta(minutes=1), None, pid=105)
        report(self.reports, "Python-b.ips", T0 + dt.timedelta(minutes=2), None, "SIGABRT", pid=106)   # macOS alone
        report(self.reports, "Python-c.ips", T0 + dt.timedelta(minutes=3), run_suite.MARK, pid=107)
        report(self.reports, "Python-early.ips", T0 - dt.timedelta(minutes=1), None, pid=108)   # outside the run
        report(self.reports, "Python-other.ips", T0 + dt.timedelta(minutes=4), None, pid=109, parent=99)   # another program's
        with open(os.path.join(self.reports, "Python-broken.ips"), "w", encoding="utf-8") as f:
            f.write("not a report")
        expected, unexpected, canary, others = self.classify()
        self.assertEqual([(s, n) for s, n, _ in unexpected], [("detector", "py-105-1.txt"), ("macOS", "Python-b.ips")])
        self.assertEqual([(s, n) for s, n, _ in expected], [("macOS", "Python-c.ips")])
        self.assertEqual([(s, n) for s, n, _ in others], [("macOS", "Python-other.ips")])
        self.assertIn("SIGABRT", run_suite.describe(*unexpected[1]))

    def test_a_report_with_no_faulting_thread_is_described(self):
        report(self.reports, "Python-null.ips", T0 + dt.timedelta(minutes=1), None, pid=111)
        path = os.path.join(self.reports, "Python-null.ips")
        head, body = open(path, encoding="utf-8").read().split("\n", 1)
        body = json.loads(body)
        body["faultingThread"] = None
        self.assertIn("Python-null.ips (macOS report)", run_suite.describe("macOS", "Python-null.ips", body))

    @unittest.skipUnless(POSIX, "the check runs on POSIX systems only")
    def test_the_detector_catches_a_real_crash_through_its_sitecustomize(self):
        """End to end, as the check runs it: a Python started with the check's environment dumps its fatal error; the
        canary's code is quiet for macOS (its crash exception ports cleared), so it raises no dialog."""
        site = tempfile.mkdtemp(prefix="gpconf-crashsite-")
        try:
            with open(os.path.join(site, "sitecustomize.py"), "w", encoding="utf-8") as f:
                f.write(run_suite.SITECUSTOMIZE)
            code = subprocess.call([sys.executable, "-c", run_suite.CANARY_CODE],
                                   env=run_suite.environment(self.crashes, site, canary=True), stderr=subprocess.DEVNULL)
            self.assertNotEqual(code, 0)
            expected, unexpected, canary, _ = run_suite.classify(self.crashes, T0, T0, self.reports)
            self.assertTrue(canary, os.listdir(self.crashes))
            self.assertEqual((expected, unexpected), ([], []))
        finally:
            shutil.rmtree(site, ignore_errors=True)

    def test_the_suite_ended_by_a_signal_with_no_record_is_unexpected(self):
        """The reading's finding: a suite the detector cannot see (its Python run with -I, -E or -S) crashed and the
        check said "0 unexpected"; now the canary runs with the suite's options, and a signal no record names is counted."""
        self.assertEqual(run_suite.unrecorded(7, -11, []), [("suite", "the suite's own process (pid 7)", 11)])
        self.assertEqual(run_suite.unrecorded(7, -11, [("detector", "py-7.txt", ({"pid": 7}, FATAL_BODY))]), [])
        self.assertEqual(run_suite.unrecorded(7, 1, []), [])
        self.assertIn("ended by signal 11", run_suite.describe(*run_suite.unrecorded(7, -11, [])[0]))

    @unittest.skipUnless(POSIX, "the check runs on POSIX systems only")
    def test_a_canary_the_suites_options_hide_stops_the_check_before_the_suite(self):
        for opt in ("-I", "-E", "-S"):
            with self.subTest(opt=opt):
                out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "run_suite.py"), f"--pyopt={opt}", "--", "tests.no_such_module"],
                                     capture_output=True, text=True, timeout=60)
                self.assertEqual(out.returncode, 4, out.stdout + out.stderr)
                self.assertIn("the suite was not run", out.stdout)
                self.assertNotIn("no_such_module", out.stdout + out.stderr)

    def test_the_sitecustomize_it_hides_still_runs(self):
        site, other = tempfile.mkdtemp(prefix="gpconf-crashsite-"), tempfile.mkdtemp(prefix="gpconf-othersite-")
        try:
            with open(os.path.join(site, "sitecustomize.py"), "w", encoding="utf-8") as f:
                f.write(run_suite.SITECUSTOMIZE)
            with open(os.path.join(other, "sitecustomize.py"), "w", encoding="utf-8") as f:
                f.write("import os\nopen(os.path.join(os.path.dirname(__file__), 'ran'), 'w').close()\n")
            env = run_suite.environment(self.crashes, site)
            env["PYTHONPATH"] = site + os.pathsep + other
            subprocess.check_call([sys.executable, "-c", "import faulthandler, sys; sys.exit(0 if faulthandler.is_enabled() else 1)"], env=env)
            self.assertTrue(os.path.exists(os.path.join(other, "ran")))
            # two of the check's own on the path (a test running the check inside the suite): neither runs the other
            env["PYTHONPATH"] = site + os.pathsep + self.crashes + os.pathsep + other
            with open(os.path.join(self.crashes, "sitecustomize.py"), "w", encoding="utf-8") as f:
                f.write(run_suite.SITECUSTOMIZE)
            out = subprocess.run([sys.executable, "-c", "pass"], env=env, capture_output=True, text=True)
            self.assertEqual((out.returncode, out.stderr), (0, ""))
            # the second reading's finding 9: a package hides a later module, as for a Python alone
            pkg, late = os.path.join(self.crashes, "pkg"), os.path.join(self.crashes, "late")
            os.makedirs(os.path.join(pkg, "sitecustomize"))
            os.makedirs(late)
            with open(os.path.join(pkg, "sitecustomize", "__init__.py"), "w", encoding="utf-8") as f:
                f.write("import os\nopen(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ran'), 'w').close()\n")
            with open(os.path.join(late, "sitecustomize.py"), "w", encoding="utf-8") as f:
                f.write("import os\nopen(os.path.join(os.path.dirname(__file__), 'ran'), 'w').close()\n")
            env["PYTHONPATH"] = os.pathsep.join([site, pkg, late])
            subprocess.check_call([sys.executable, "-c", "pass"], env=env)
            self.assertEqual((os.path.exists(os.path.join(pkg, "ran")), os.path.exists(os.path.join(late, "ran"))), (True, False))
        finally:
            shutil.rmtree(site, ignore_errors=True)
            shutil.rmtree(other, ignore_errors=True)

    def check(self, test_text, *opts):
        """tools/run_suite.py run on a one-test suite of its own: (exit status, what it printed)."""
        suite = tempfile.mkdtemp(prefix="gpconf-onetest-")
        try:
            with open(os.path.join(suite, "test_one.py"), "w", encoding="utf-8") as f:
                f.write(test_text)
            out = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "run_suite.py"), *opts, "--", "discover", "-s", suite, "-t", suite],
                                 capture_output=True, text=True, timeout=120)
            return out.returncode, out.stdout + out.stderr
        finally:
            shutil.rmtree(suite, ignore_errors=True)

    @unittest.skipUnless(POSIX, "the check runs on POSIX systems only")
    def test_the_twin_a_suite_run_with_its_options_is_run_and_checked(self):
        """The second reading's finding 11, the twin of the canary test: an option (-O) reaches the suite's Python, the
        suite runs, and the check ends with its summary and the suite's status."""
        code, text = self.check("import unittest\nclass T(unittest.TestCase):\n    def test(self):\n        self.assertFalse(__debug__)\n", "--pyopt=-O")
        self.assertEqual(code, 0, text)
        self.assertIn("Ran 1 test", text)
        self.assertIn("crash reports: 0 expected, 0 unexpected", text)

    @unittest.skipUnless(POSIX, "the check runs on POSIX systems only")
    def test_a_suite_ended_by_a_signal_no_record_names_stops_the_run(self):
        """SIGKILL runs no handler, so no detector records it, and macOS writes no report of it: the suite's own process
        ended so is unexpected, and the check exits 3."""
        code, text = self.check("import os, signal, unittest\nclass T(unittest.TestCase):\n    def test(self):\n        os.kill(os.getpid(), signal.SIGKILL)\n")
        self.assertEqual(code, 3, text)
        self.assertIn("ended by signal 9, with no crash record of it", text)
        self.assertIn("crash reports: 0 expected, 1 unexpected", text)

    def site(self):
        site = tempfile.mkdtemp(prefix="gpconf-crashsite-")
        self.addCleanup(shutil.rmtree, site, True)
        with open(os.path.join(site, "sitecustomize.py"), "w", encoding="utf-8") as f:
            f.write(run_suite.SITECUSTOMIZE)
        return site

    def test_each_python_writes_one_file_of_its_own_headed_with_its_parent(self):
        """The third reading's finding 6: the detector's writing side, its file named by process id and start time and
        headed with the process and its parent; two Pythons, two files."""
        env = run_suite.environment(self.crashes, self.site())
        pids = [int(subprocess.check_output([sys.executable, "-c", "import os; print(os.getpid())"], env=env)) for _ in range(2)]
        names = sorted(os.listdir(self.crashes))
        self.assertEqual(len(names), 2, names)
        for name in names:
            self.assertRegex(name, r"^py-\d+-\d+\.txt$")
        headers = [h for _, h, _ in run_suite.read_files(self.crashes)]
        self.assertEqual(sorted(h["pid"] for h in headers), sorted(pids))
        self.assertEqual({h["ppid"] for h in headers}, {os.getpid()})
        self.assertEqual(run_suite.read_dumps(self.crashes), [])   # both ended well

    @unittest.skipUnless(POSIX and hasattr(signal, "SIGTRAP"), "a POSIX signal")
    def test_a_python_ended_by_a_trap_is_seen(self):
        """The third reading's finding 3: SIGTRAP (an arm64 trap instruction) ran no handler and left no record; the
        detector registers it. The crash is quiet for macOS, as the canary's is."""
        code = run_suite.CANARY_CODE.replace("signal.SIGSEGV", "signal.SIGTRAP")
        self.assertNotEqual(subprocess.call([sys.executable, "-c", code], env=run_suite.environment(self.crashes, self.site()),
                                            stderr=subprocess.DEVNULL), 0)
        expected, unexpected, canary, _ = self.classify()
        self.assertEqual(([n for _, n, _ in expected], len(unexpected), canary), ([], 1, None), os.listdir(self.crashes))

    @unittest.skipUnless(POSIX and hasattr(signal, "SIGTRAP"), "a POSIX signal")
    def test_a_python_whose_parent_ignores_traps_is_not_counted_when_it_lives_on(self):
        """The fourth reading's finding 6: a SIGTRAP its parent left ignored does not end the process, so the detector
        does not register it, and nothing is counted. Its twin is the test above."""
        # the canary's crash ports cleared first, so that a regression making the trap fatal raises no dialog
        quiet = run_suite.CANARY_CODE.replace("os.kill(os.getpid(), signal.SIGSEGV)\n", "")
        code = quiet + "os.kill(os.getpid(), signal.SIGTRAP)\nprint('alive')\n"
        out = subprocess.run([sys.executable, "-c", code], env=run_suite.environment(self.crashes, self.site()), capture_output=True,
                             text=True, preexec_fn=lambda: signal.signal(signal.SIGTRAP, signal.SIG_IGN))
        self.assertEqual((out.returncode, out.stdout.strip()), (0, "alive"), out.stderr)
        self.assertEqual(self.classify()[:3], ([], [], None))

    @unittest.skipUnless(POSIX, "the check runs on POSIX systems only")
    def test_a_python_a_test_starts_with_its_own_pythonpath_is_watched(self):
        """D-355: four test modules start gpconf with a PYTHONPATH (or a whole environment) of their own, and ran it
        unwatched; tests/crashwatch.py carries the detector over. A crash there is caught; its twin, the same environment
        not carried over, is not seen."""
        sys.path.insert(0, ROOT)
        from tests.crashwatch import watched
        site = self.site()
        outer = run_suite.environment(self.crashes, site)
        self.assertEqual(outer["GPCONF_CRASH_SITE"], site)
        with unittest.mock.patch.dict(os.environ, {"GPCONF_CRASH_SITE": site, "GPCONF_CRASH_DIR": self.crashes}):
            self.assertEqual(watched({"PYTHONPATH": "first"})["PYTHONPATH"], site + os.pathsep + "first")   # the check's folder first
        with unittest.mock.patch.dict(os.environ, {"GPCONF_CRASH_SITE": site, "GPCONF_CRASH_DIR": self.crashes}):
            for env, seen in ((watched({"PATH": os.environ.get("PATH", ""), "PYTHONPATH": ROOT}), 1), ({"PATH": os.environ.get("PATH", ""), "PYTHONPATH": ROOT}, 0)):
                with self.subTest(carried=bool(seen)):
                    subprocess.call([sys.executable, "-c", run_suite.CANARY_CODE], env=env, stderr=subprocess.DEVNULL)
                    self.assertEqual(len(self.classify()[1]), seen)
                    for name in os.listdir(self.crashes):
                        os.remove(os.path.join(self.crashes, name))

    def test_the_canary_seen_by_both_signals_is_counted_once(self):
        dump(self.crashes, 120, canary=True)
        report(self.reports, "Python-canary.ips", T0 + dt.timedelta(minutes=1), None, pid=120)
        self.assertEqual(self.classify(), ([], [], "py-120-1.txt", []))

    @unittest.skipUnless(POSIX, "the check runs on POSIX systems only")
    def test_a_canary_that_cannot_clear_its_ports_is_named_as_the_reason(self):
        out = io.StringIO()
        saved = run_suite.CANARY_CODE
        run_suite.CANARY_CODE = f"import sys; sys.exit({run_suite.QUIET_FAILED})"
        try:
            with contextlib.redirect_stdout(out):
                code = run_suite.main(["--", "tests.no_such_module"])
        finally:
            run_suite.CANARY_CODE = saved
        self.assertEqual(code, 4)
        self.assertIn("could not clear its crash exception ports", out.getvalue())

    @unittest.skipUnless(POSIX, "the check runs on POSIX systems only")
    def test_the_harness_crash_reads_expected_end_to_end(self):
        """The third reading's finding 6: the real harness of test_crashes_080, crashing on a cut file under the check's
        sitecustomize, marks its own file, so its crash reads expected (a harness that cannot mark reads unexpected)."""
        text = open(os.path.join(ROOT, "tests", "adversarial", "test_crashes_080.py"), encoding="utf-8").read()
        quotes = "'" * 3
        site = self.site()
        harness = os.path.join(site, "harness.py")
        with open(harness, "w", encoding="utf-8") as f:
            f.write(re.search("HARNESS = r" + quotes + "(.*?)" + quotes, text, re.S).group(1))
        cut = os.path.join(ROOT, "derived", "corrupt-input", "c5-cut-last-row.csv")
        env = dict(run_suite.environment(self.crashes, site), GPCONF_ROOT=ROOT, GPCONF_MODE="crash", GPCONF_CUT=cut)
        with open(cut, "rb") as f:
            done = subprocess.run([sys.executable, harness, "parse", "csv"], input=f.read(), env=env, capture_output=True)
        self.assertLess(done.returncode, 0, done.stderr[-300:])
        expected, unexpected, _, _ = self.classify()
        self.assertEqual((len(expected), unexpected), (1, []), os.listdir(self.crashes))

    def test_the_harness_marks_and_quiets_its_crash_before_it_kills_itself(self):
        with open(os.path.join(ROOT, "tests", "adversarial", "test_crashes_080.py"), encoding="utf-8") as f:
            text = f.read()
        kill = text.find("os.kill(os.getpid(), signal.SIGSEGV)")
        for needle in ('own.name[:-len(".txt")] + ".deliberate"', f'pthread_setname_np(b"{run_suite.MARK}")',
                       "task_set_exception_ports(task, EXC_MASK_CRASH | EXC_MASK_CORPSE_NOTIFY", "quiet()"):
            with self.subTest(needle=needle):
                self.assertGreater(text.find(needle), 0)
                self.assertLess(text.find(needle), kill)


if __name__ == "__main__":
    unittest.main()
