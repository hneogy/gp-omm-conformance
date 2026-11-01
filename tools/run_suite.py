#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The suite, run with a check of the crashes that happen while it runs (the owner's instructions, 2026-10-18).

    python3 tools/run_suite.py [--python PY] [--pyopt=OPTION ...] [-- unittest arguments]

Runs `PY -m unittest discover -s tests -t .` from the repository root (or `PY -m unittest` with the arguments given
after `--`) and reports every Python that crashed during the run, ending with "crash reports: N expected, M unexpected".
Expected crashes are test_crashes_080's harness killing itself on purpose; any other is unexpected, printed with what
is known of it, and the exit status is 3, so that whoever runs the suite stops and looks.

The check sees crashes two ways. First, its own detector: a `sitecustomize` on the suite's PYTHONPATH turns on Python's
faulthandler in every Python the suite starts that inherits its environment and runs its site module, each writing to a
file of its own in the run's crash folder (named by its process id and the time it started, so that an id used twice is
two files), headed with its process, its parent, its working directory and its argv (the whole command line from Python
3.10, `sys.orig_argv`; on 3.9 only "-c" or "-m" for a Python started so, all its site module sees); a fatal signal
(SIGSEGV, SIGFPE, SIGABRT, SIGBUS or SIGILL, and SIGTRAP, which a trap instruction raises on arm64) writes the traceback
there; SIGTRAP is registered only where it would end the process, not where a parent left it ignored, though on Linux a
trap instruction ends such a process all the same, unseen, and on macOS it runs again and again, a hang (a kill() of
SIGTRAP is ignored on both); SIGKILL and other signals run no handler, so a Python of the suite ended by one is seen
only where macOS reports it, or, for the suite's own process, by its exit status; and the harness drops a marker beside
its own file before it kills itself, so its crash reads as expected. Before the suite the check crashes a canary of its
own the same way, with the suite's Python and its options, and must find it, or the suite is not run and the exit status
is 4: a check that cannot see a crash would say "0 unexpected" of one. The suite's own process ended by a signal with no
record of its crash is unexpected too. A Python that a test starts with an environment of its own (one whose PYTHONPATH
it sets) is watched only where the test passes that environment through `tests/crashwatch.py`'s `watched()`, as the four
test modules that do so now do (D-355); the check exports its sitecustomize folder as GPCONF_CRASH_SITE for it. The
`sitecustomize` then runs the one it hides, the first a Python alone would import from a later entry of its path
(Homebrew's Python ships one), never another of the check's own.
Second, macOS's crash reports (~/Library/Logs/DiagnosticReports/Python*.ips) whose recorded crash time falls in the run
and whose process or parent is one of the suite's (a detector file names it), matched to the first by process id so
that one crash counts once; a report of any other Python is printed as possibly another program's and not counted.
macOS wrote none for Python from 2026-10-18 08:08 on, for a reason not seen here, so they are a second signal only. The
harness and the canary clear their crash exception ports first, so that macOS writes no report of them and raises no
dialog (the owner's ruling); where they cannot be cleared, neither crashes, and the check says so. Processes that are
not Python (a compiled harness, node) are not seen: only Python's reports are read. Times are read from the reports and
the files' contents, never from the files' own times. The check runs on POSIX systems only: on Windows `os.kill` ends a
process with no handler run, so no detector sees it, and the check stops with exit status 4 before the suite."""
import argparse
import datetime as dt
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS = os.path.expanduser("~/Library/Logs/DiagnosticReports")
MARK = "gpconf-deliberate-crash"   # the thread name test_crashes_080's harness sets before it kills itself
CRASH_DIR_ENV = "GPCONF_CRASH_DIR"
FATAL = "Fatal Python error"
TRACE = "(most recent call first)"   # the traceback faulthandler writes, a registered SIGTRAP's with no FATAL line

# faulthandler in every Python the suite starts, one file a process; the header names what it ran
SITECUSTOMIZE = '''"""Written by tools/run_suite.py for one suite run (the owner's instruction, 2026-10-18): this Python writes a fatal
error's traceback (faulthandler) to a file of its own in the run's crash folder, headed with its process and its argv."""
import faulthandler as _fh, json as _json, os as _os, signal as _signal, sys as _sys, time as _time
_d = _os.environ.get("GPCONF_CRASH_DIR")
if _d and _os.path.isdir(_d):
    try:
        _f = open(_os.path.join(_d, f"py-{_os.getpid()}-{_time.time_ns()}.txt"), "x", encoding="utf-8")
        _f.write(_json.dumps({"pid": _os.getpid(), "ppid": _os.getppid(), "executable": _sys.executable, "argv": _sys.argv,
                              "orig_argv": getattr(_sys, "orig_argv", None), "cwd": _os.getcwd(),
                              "canary": bool(_os.environ.get("GPCONF_CRASH_CANARY"))}) + "\\n")
        _f.flush()
        _fh.enable(file=_f, all_threads=True)
        # SIGTRAP, what a trap instruction raises on arm64 (a C extension's or a runtime's), where it would end the
        # process: one a parent left ignored lives on, and is not to be counted as a crash
        if hasattr(_signal, "SIGTRAP") and _signal.getsignal(_signal.SIGTRAP) is _signal.SIG_DFL:
            _fh.register(_signal.SIGTRAP, file=_f, all_threads=True, chain=True)
    except (OSError, RuntimeError, ValueError):
        pass
# the sitecustomize this one hides: the first a Python alone would import from a later entry of the path (a module, a
# package or a compiled file), never another of the check's own, which a test running the check puts on the path too
import importlib.machinery as _m, importlib.util as _u
for _p in list(_sys.path):
    try:
        _spec = _m.PathFinder.find_spec("sitecustomize", [_p])
        if _spec is None or _spec.loader is None or not _spec.origin:
            continue
        with open(_spec.origin, "rb") as _h:
            if b"Written by tools/run_suite.py" in _h.read(4096):
                continue
    except (OSError, ImportError, ValueError):
        continue
    _spec.loader.exec_module(_u.module_from_spec(_spec))
    break
'''

# the canary: quiet for macOS (no report, no dialog), seen by the check's own detector; where its crash exception ports
# cannot be cleared (THREAD_STATE_NONE is 5 on arm64 and 13 on x86_64), it does not crash but exits with QUIET_FAILED
QUIET_FAILED = 70
CANARY_CODE = ("import ctypes, os, platform, signal, sys\n"
               "if sys.platform == 'darwin':\n"
               "    libc = ctypes.CDLL(None)\n"
               "    libc.task_set_exception_ports.argtypes = [ctypes.c_uint] * 5\n"
               "    task = ctypes.c_uint.in_dll(libc, 'mach_task_self_')\n"
               "    flavors = (5, 13) if platform.machine() == 'arm64' else (13, 5)\n"
               "    if not any(libc.task_set_exception_ports(task, (1 << 10) | (1 << 13), 0, 1, f) == 0 for f in flavors):\n"
               f"        sys.exit({QUIET_FAILED})\n"
               "os.kill(os.getpid(), signal.SIGSEGV)\n")


# ---- the check's own detector
def read_files(folder):
    """-> [(file name, header, text)] for every Python the detector watched, crashed or not."""
    out = []
    for path in sorted(glob.glob(os.path.join(folder, "py-*.txt"))):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                head, _, body = f.read().partition("\n")
            header = json.loads(head)
        except (OSError, ValueError):
            continue
        if isinstance(header, dict):
            out.append((os.path.basename(path), header, body))
    return out


def read_dumps(folder):
    """-> [(file name, header, text)] for the processes that crashed: a file whose body holds a fatal error's or a
    registered SIGTRAP's traceback."""
    return [(name, header, body) for name, header, body in read_files(folder) if crashed(body)]


def crashed(body):
    return FATAL in body or TRACE in body


def deliberate(folder, name):
    """Whether the harness marked this file's crash as its own: a marker beside it, named after it."""
    return os.path.exists(os.path.join(folder, name[:-len(".txt")] + ".deliberate"))


# ---- macOS's reports, the second signal
def read_report(path):
    """The report's body (the JSON after its one-line header), or None for a file that is not one."""
    try:
        with open(path, encoding="utf-8") as f:
            _, body = f.read().split("\n", 1)
        return json.loads(body)
    except (OSError, ValueError):
        return None


def crash_time(body):
    try:
        return dt.datetime.strptime(body["captureTime"], "%Y-%m-%d %H:%M:%S.%f %z")
    except (KeyError, TypeError, ValueError):
        return None


def faulting_thread(body):
    threads = body.get("threads") or [{}]
    i = body.get("faultingThread", 0)
    thread = threads[i] if isinstance(i, int) and 0 <= i < len(threads) else {}
    return thread if isinstance(thread, dict) else {}


def thread_name(body):
    return faulting_thread(body).get("name")


def scan(since, until, folder=REPORTS):
    """-> (expected, unexpected): macOS's Python crash reports whose recorded crash time is in [since, until], each as
    (file name, body); expected when the crashing thread is the harness's, by its name."""
    expected: list = []
    unexpected: list = []
    for path in sorted(glob.glob(os.path.join(folder, "Python*.ips"))):
        body = read_report(path)
        t = crash_time(body) if body else None
        if t is None or not since <= t <= until:
            continue
        (expected if thread_name(body) == MARK else unexpected).append((os.path.basename(path), body))
    return expected, unexpected


def classify(crash_dir, since, until, reports=REPORTS):
    """-> (expected, unexpected, canary, others): every crash of the run, from both signals, one entry a crash, each as
    (source, name, what): what is the detector's header and traceback, or the macOS report's body. A macOS report counts
    where its process or its parent is one the detector watched (the suite's own); others are reports of other Pythons."""
    expected: list = []
    unexpected: list = []
    others: list = []
    canary = None
    dead, family = set(), set()
    for name, header, body in read_files(crash_dir):
        family |= {header.get("pid"), header.get("ppid")}
        if not crashed(body):
            continue
        dead.add(header.get("pid"))
        if header.get("canary"):
            canary = name
        elif deliberate(crash_dir, name):
            expected.append(("detector", name, (header, body)))
        else:
            unexpected.append(("detector", name, (header, body)))
    family.discard(None)
    seen_expected, seen_unexpected = scan(since, until, reports) if os.path.isdir(reports) else ([], [])
    for sink, seen in ((expected, seen_expected), (unexpected, seen_unexpected)):
        for name, body in seen:
            if body.get("pid") in dead:
                continue
            (sink if body.get("pid") in family or body.get("parentPid") in family else others).append(("macOS", name, body))
    return expected, unexpected, canary, others


def unrecorded(pid, code, crashes):
    """[the suite's own process, as an unexpected crash] where it ended by a signal and neither signal recorded it."""
    if code >= 0 or any(pid == (what[0] if source == "detector" else what).get("pid") for source, _, what in crashes):
        return []
    return [("suite", f"the suite's own process (pid {pid})", -code)]


def describe(source, name, what):
    """What is known of a crash, for whoever runs the suite to read."""
    if source == "suite":
        return f"  {name}: ended by signal {what}, with no crash record of it (a Python the detector does not watch?)"
    if source == "detector":
        header, body = what
        lines = [f"  {name}: {header.get('executable')} (pid {header.get('pid')}, parent {header.get('ppid')}), in {header.get('cwd')}",
                 f"    command: {header.get('orig_argv') or header.get('argv')}"]
        lines += [f"    {line}" for line in body.strip().splitlines()[:14]]
        return "\n".join(lines)
    body = what
    exc = body.get("exception") or {}
    images = body.get("usedImages") or []
    thread = faulting_thread(body)
    lines = [f"  {name} (macOS report): {body.get('procPath')} (pid {body.get('pid')}), crashed {body.get('captureTime')}",
             f"    parent {body.get('parentProc')} (pid {body.get('parentPid')}); responsible {body.get('responsibleProc')}; "
             f"{exc.get('type')} {exc.get('signal')}; thread {thread.get('name')!r}"]
    for frame in (thread.get("frames") or [])[:8]:
        i = frame.get("imageIndex")
        image = images[i].get("name", "?") if isinstance(i, int) and i < len(images) else "?"
        lines.append(f"      {image} {frame.get('symbol', '?')}")
    return "\n".join(lines)


def summary(expected, unexpected):
    return f"crash reports: {len(expected)} expected, {len(unexpected)} unexpected"


def environment(crash_dir, site_dir, canary=False):
    env = dict(os.environ, **{CRASH_DIR_ENV: crash_dir, "GPCONF_CRASH_SITE": site_dir})   # the site, for tests/crashwatch.py
    env["PYTHONPATH"] = site_dir + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    if canary:
        env["GPCONF_CRASH_CANARY"] = "1"
    return env


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--python", default=sys.executable, help="the Python that runs the suite (default: this one)")
    ap.add_argument("--pyopt", action="append", default=[], help="an option for that Python, written --pyopt=-Wignore (repeatable)")
    ap.add_argument("rest", nargs="*", help="unittest's own arguments, after --")
    a = ap.parse_args(argv)
    if os.name != "posix":
        print("crash reports NOT SEEN: the crash check runs on POSIX systems only (on this system os.kill ends a process with no "
              "handler run, so its detector sees no crash); the suite was not run. Run it with python -m unittest.")
        return 4
    command = [a.python] + a.pyopt + ["-m", "unittest"] + (a.rest or ["discover", "-s", "tests", "-t", "."])
    crash_dir = tempfile.mkdtemp(prefix="gpconf-crashes-")
    site_dir = tempfile.mkdtemp(prefix="gpconf-crashsite-")
    with open(os.path.join(site_dir, "sitecustomize.py"), "w", encoding="utf-8") as f:
        f.write(SITECUSTOMIZE)
    try:
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
        rc = subprocess.call([a.python] + a.pyopt + ["-c", CANARY_CODE], env=environment(crash_dir, site_dir, canary=True), stderr=subprocess.DEVNULL)
        canary = classify(crash_dir, since, dt.datetime.now(dt.timezone.utc), reports=os.devnull)[2]
        if not canary:
            why = ("the canary could not clear its crash exception ports, so it did not crash (that would have left a report and "
                   "a dialog)" if rc == QUIET_FAILED else
                   "the check's own detector did not catch its canary crash, made with the suite's Python and options, so a crash "
                   "during the suite could go unseen")
            print(f"crash reports NOT SEEN: {why}; the suite was not run. Stop and look before going on.")
            return 4
        suite = subprocess.Popen(command, cwd=ROOT, env=environment(crash_dir, site_dir))
        code = suite.wait()
        time.sleep(5)   # a macOS report is written a few seconds after its crash
        expected, unexpected, _, others = classify(crash_dir, since, dt.datetime.now(dt.timezone.utc))
        unexpected += unrecorded(suite.pid, code, expected + unexpected)
        for source, name, _ in expected:
            print(f"  expected: {name} ({source}: test_crashes_080's deliberate crash)")
        for source, name, what in others:
            print(f"  not counted: {name}, a crash report of a Python that is not one of the suite's (possibly another program's):")
            print(describe(source, name, what))
        if unexpected:
            print("UNEXPECTED crashes during the run, to be looked at before anything else:")
            for source, name, what in unexpected:
                print(describe(source, name, what))
        print(f"crash reports seen: the check's own canary crash was caught by its detector ({canary})")
        print(summary(expected, unexpected))
        return 3 if unexpected else code
    finally:
        shutil.rmtree(site_dir, ignore_errors=True)
        shutil.rmtree(crash_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
