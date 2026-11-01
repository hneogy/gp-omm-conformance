# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""A command that crashes or runs out of time refuses nothing (D-341), and a provider line blank in column 68 is
refused (D-341, the owner's ruling on D-338's second reading), each with its wrong-on-purpose adapter and twin.

Before: a --cmd parser killed by a signal, or still running after its time, on a cut corrupt input passed
`corrupt-file-cut` as the file refused as a whole; a --vectors-cmd that crashed on an input it must reject passed as
rejecting it; a --write-cmd that crashed on an id the TLE field cannot carry passed as refusing it. And a provider line
cut inside its element set or revolution number and padded to 69 columns read the cut number.

Run: python -m unittest tests.adversarial.test_crashes_080"""
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf import reference as ref  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import CommandCrashed, CommandParser  # noqa: E402
from tests.adversarial.test_hardening import failing, run  # noqa: E402
from tests.adversarial.test_strict_files_080 import LINES, column, tle_text  # noqa: E402

CUT = [os.path.join(ROOT, "derived", "corrupt-input", n) for n in ("c5-cut-last-row.csv", "c5-cut-closing-bracket.json")]
Q = (lambda s: subprocess.list2cmdline([s])) if os.name == "nt" else shlex.quote
POSIX = unittest.skipIf(os.name == "nt", "Windows has no signals: a crash there is its exit code, a stated limit (D-341)")

HARNESS = r'''
import json, os, signal, sys, time
sys.path.insert(0, os.environ["GPCONF_ROOT"])
from gpconf.adapters.reference import Parser
mode, role = os.environ["GPCONF_MODE"], sys.argv[1]
cut = {open(p, "rb").read() for p in os.environ["GPCONF_CUT"].split(os.pathsep)}


def mark():
    """The suite's crash detector, where it runs (tools/run_suite.py): a marker beside this process's own file, named
    after it, so that this crash reads as expected and no other process's does."""
    own = getattr(sys.modules.get("sitecustomize"), "_f", None)
    if own is not None and os.environ.get("GPCONF_CRASH_DIR"):
        open(own.name[:-len(".txt")] + ".deliberate", "w").close()


def quiet():
    """macOS: this crash is deliberate, so it writes no crash report and raises no dialog (the owner's ruling of
    2026-10-18): the task's crash exception ports cleared, the signal still kills the process and the runner still sees
    it; and its thread named, so that a report written all the same reads as deliberate (tools/run_suite.py)."""
    import ctypes, platform
    mark()
    libc = ctypes.CDLL(None)
    libc.pthread_setname_np(b"gpconf-deliberate-crash")
    task = ctypes.c_uint.in_dll(libc, "mach_task_self_")
    EXC_MASK_CRASH, EXC_MASK_CORPSE_NOTIFY = 1 << 10, 1 << 13
    flavors = (5, 13) if platform.machine() == "arm64" else (13, 5)   # THREAD_STATE_NONE on arm64, on x86_64
    libc.task_set_exception_ports.argtypes = [ctypes.c_uint] * 5
    if not any(libc.task_set_exception_ports(task, EXC_MASK_CRASH | EXC_MASK_CORPSE_NOTIFY, 0, 1, f) == 0 for f in flavors):
        sys.exit("the harness could not clear its crash exception ports, so it does not crash (a report and a dialog would follow)")


def fault(reason):
    """What a harness does where the reference refuses: crashes, hangs, or refuses in the protocol's own way."""
    if mode == "crash":
        if sys.platform == "darwin":
            quiet()
        else:   # the suite's crash detector reads the marker on every system
            mark()
        os.kill(os.getpid(), signal.SIGSEGV)
    if mode == "hang":
        time.sleep(60)
    if mode.startswith("exit:"):
        sys.exit(int(mode[5:]))
    if role == "vectors":
        print(json.dumps({"error": reason}))
        sys.exit(0)
    sys.stderr.write(reason)
    sys.exit(1)


data = sys.stdin.buffer.read()
if role == "parse":
    if data in cut:
        fault("cut short")
    print(json.dumps(Parser().parse(data, sys.argv[2]), default=str))
elif role == "vectors":
    ask = json.loads(data)
    if ask["op"] in os.environ.get("GPCONF_CRASH_OPS", "").split(","):
        fault("every call of this hook")
    try:
        got = getattr(Parser(), ask["op"])(ask["input"])
    except Exception as e:
        fault(f"rejected: {e}")
    print(json.dumps({"result": got.isoformat() if hasattr(got, "isoformat") else got}))
else:
    if str(json.loads(data)["norad_cat_id"]) in os.environ.get("GPCONF_CRASH_IDS", "").split(","):
        fault("this id")
    try:
        lines = Parser().write_tle(json.loads(data))
    except Exception as e:
        fault(f"refused: {e}")
    print("\n".join(lines))
'''


class ACommandThatCrashesOrRunsOutOfTimeRefusesNothing(unittest.TestCase):
    """Escape 1 of D-339's reading, ruled a fix by the owner (2026-10-17): a crash or a timeout is a fail, not a
    refusal. The twins: the same harness refusing in the protocol's own way (an exit of 1, an error answer) passes."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="gpconf-crashes-")
        cls.script = os.path.join(cls.dir, "harness.py")
        with open(cls.script, "w", encoding="utf-8") as f:
            f.write(HARNESS)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def command(self, mode, timeout=120, shell=False, cut=CUT, ops="", ids=""):
        env = dict(os.environ, GPCONF_ROOT=ROOT, GPCONF_MODE=mode, GPCONF_CUT=os.pathsep.join(cut), GPCONF_CRASH_OPS=ops,
                   GPCONF_CRASH_IDS=ids)
        py, s = sys.executable, self.script
        if shell:   # a shell that runs more after the harness reports its signal as 128 + its number (bash, dash, zsh)
            run_ = f"{Q(py)} {Q(s)}"
            return CommandParser(f"{run_} parse {{fmt}}; exit $?", vectors_cmd=f"{run_} vectors; exit $?",
                                 write_cmd=f"{run_} write; exit $?", timeout=timeout, env=env)
        return CommandParser([py, s, "parse", "{fmt}"], vectors_cmd=[py, s, "vectors"], write_cmd=[py, s, "write"],
                             timeout=timeout, env=env)

    def hybrid(self, mode, ops="", ids=""):
        """The same harness, answered in-process where the reference answers and run as a real process only where the
        reference refuses, or where the hook or id is one the harness is told to crash on, so each crash is a real one
        and a case of hundreds of calls takes seconds, not minutes."""
        cmd, real = self.command(mode, ops=ops, ids=ids), CommandParser._run

        def _run(c, data, fmt=None):
            try:
                if c is cmd.vectors_cmd:
                    ask = json.loads(data)
                    if ask["op"] in ops.split(","):
                        return real(cmd, c, data, fmt)
                    got = getattr(Reference(), ask["op"])(ask["input"])
                    out = json.dumps({"result": got.isoformat() if hasattr(got, "isoformat") else got})
                elif c is cmd.write_cmd:
                    if str(json.loads(data)["norad_cat_id"]) in ids.split(","):
                        return real(cmd, c, data, fmt)
                    out = "\n".join(Reference().write_tle(json.loads(data)))
                else:
                    return real(cmd, c, data, fmt)
            except Exception:
                return real(cmd, c, data, fmt)
            return subprocess.CompletedProcess(c, 0, out.encode(), b"")
        cmd._run = _run
        return cmd

    def details(self, result, case):
        return [i.detail for i in result[case].items if i.status == "fail"]

    @POSIX
    def test_a_crash_on_a_cut_corrupt_input_fails_it(self):
        for shell in (False, True):
            with self.subTest(shell=shell):
                r = run(self.command("crash", shell=shell), cases=["corrupt-input"])
                self.assertEqual(failing(r), ["corrupt-input"])
                cut = [i for i in r["corrupt-input"].items if i.check == "corrupt-file-cut"]
                self.assertEqual([i.status for i in cut], ["fail", "fail"])
                for i in cut:
                    self.assertIn("exited 139, which is how a shell reports signal 11 (SIGSEGV)" if shell else
                                  "was ended by signal 11 (SIGSEGV)", i.detail)
                    self.assertIn("a crash or a timeout is no refusal and no rejection (D-341)", i.detail)
        self.assertEqual(failing(run(self.command("refuse"), cases=["corrupt-input"])), [])   # the twin: a refusal

    @POSIX
    def test_a_shell_exit_that_names_no_crash_signal_is_the_commands_own_answer(self):
        """Only 128 plus a crash signal's number is read as a signal from a shell: an exit of 130, 143 or 255 there is
        the command's refusal, as before; 139, 152 and 153 are SIGSEGV's, SIGXCPU's and SIGXFSZ's, and read as the crash,
        a stated limit; a program's own exit of 139 with no shell is its answer."""
        for code in (130, 143, 255):
            with self.subTest(exit=code):
                self.assertEqual(failing(run(self.command(f"exit:{code}", shell=True), cases=["corrupt-input"])), [])
        for code, name in ((139, "SIGSEGV"), (152, "SIGXCPU"), (153, "SIGXFSZ")):
            with self.subTest(exit=code):
                r = run(self.command(f"exit:{code}", shell=True), cases=["corrupt-input"])
                self.assertEqual(failing(r), ["corrupt-input"])
                self.assertTrue(any(f"exited {code}, which is how a shell reports signal" in d and name in d for d in self.details(r, "corrupt-input")))
        # no shell, no shell's report: a program's own exit of 139 is its answer, a refusal
        self.assertEqual(failing(run(self.command("exit:139"), cases=["corrupt-input"])), [])

    @POSIX
    def test_a_crash_on_a_valid_file_fails_it_as_parse_in_the_commands_words(self):
        unedited = os.path.join(ROOT, "derived", "corrupt-input", "unedited-sets.tle")
        r = run(self.command("crash", cut=[unedited]), cases=["corrupt-input"])
        parse = [i for i in r["corrupt-input"].items if i.check == "parse" and (i.file or "").endswith("unedited-sets.tle")]
        self.assertEqual([i.status for i in parse], ["fail"])
        self.assertTrue(parse[0].detail.startswith("the parser's command was ended by signal 11 (SIGSEGV)"), parse[0].detail)
        voided = [i for i in r["corrupt-input"].items if i.status == "not-exercised" and (i.file or "").endswith(".tle")]
        self.assertTrue(voided and all("cannot serve as one (the parser's command was ended by signal 11 (SIGSEGV)" in i.detail for i in voided))

    @POSIX
    def test_a_crash_on_a_valid_input_is_worded_as_the_commands_end(self):
        """Where a crash fails an item that a raise would fail too, it reads as the command's end, never as a value the
        hook returned or a refusal the writer made."""
        import re
        r = run(self.hybrid("crash", ops="alpha5_decode,alpha5_encode,parse_catalog_id"), cases=["alpha5-encoding-vectors"])
        items = {i.check: i.detail for i in r["alpha5-encoding-vectors"].items if i.status == "fail"}
        self.assertRegex(items["alpha5-decode"], r"(^|; )[0-9A-Z]{5}: the parser's command was ended by signal 11 \(SIGSEGV\)")
        self.assertRegex(items["alpha5-encode"], r"(^|; )\d+: the parser's command was ended by signal 11 \(SIGSEGV\)")
        for check in ("alpha5-decode", "alpha5-encode"):
            self.assertNotIn("-> the parser's command", items[check])
            self.assertNotIn("-> \"the parser's command", items[check])
        self.assertRegex(items["catalog-number-is-integer"], r"'[^']*': the parser's command was ended by signal 11")
        self.assertIsNone(re.search(r"raised CommandCrashed", " ".join(items.values())))
        w = run(self.hybrid("crash", ids="25544"), cases=["tle-writer-alpha5"])
        field = [i.detail for i in w["tle-writer-alpha5"].items if i.check == "tle-writer-catalog-field"]
        self.assertIn("id 25544: the parser's command was ended by signal 11 (SIGSEGV)", field[0])
        self.assertNotIn("refused although", field[0])
        # the twins: the same calls refused in the protocol's own way read as before, a raise and a refusal
        r = run(self.hybrid("refuse", ops="alpha5_decode,alpha5_encode,parse_catalog_id"), cases=["alpha5-encoding-vectors"])
        items = {i.check: i.detail for i in r["alpha5-encoding-vectors"].items if i.status == "fail"}
        self.assertRegex(items["alpha5-decode"], r"[0-9A-Z]{5} -> raised ValueError \(expected \d+\)")
        self.assertNotIn("the parser's command", " ".join(items.values()))
        w = run(self.hybrid("refuse", ids="25544"), cases=["tle-writer-alpha5"])
        field = [i.detail for i in w["tle-writer-alpha5"].items if i.check == "tle-writer-catalog-field"]
        self.assertIn("id 25544 refused although the TLE field can carry it", field[0])

    @POSIX
    def test_a_command_parser_subclass_crash_is_a_crash(self):
        """A Python adapter that builds on the runner's CommandParser keeps its command's crash a crash, so it cannot
        pass a cut corrupt input by crashing on it (the third reading). The twin: the same subclass refusing passes."""
        class Mine(CommandParser):
            pass

        class Fresh(CommandParser):   # re-raises its command's crash as a CommandCrashed of its own (D-342's reading)
            def parse(self, raw, fmt):
                try:
                    return super().parse(raw, fmt)
                except CommandCrashed as e:
                    raise CommandCrashed(str(e)) from None
        for kind in (Mine, Fresh):
            for mode, want in (("crash", ["corrupt-input"]), ("refuse", [])):
                with self.subTest(kind=kind.__name__, mode=mode):
                    plain = self.command(mode)
                    mine = kind(plain.cmd, vectors_cmd=plain.vectors_cmd, write_cmd=plain.write_cmd, env=plain.env)
                    self.assertEqual(failing(run(mine, cases=["corrupt-input"])), want)

    def test_a_timeout_on_a_cut_corrupt_input_fails_it(self):
        start = time.monotonic()
        r = run(self.command("hang", timeout=3), cases=["corrupt-input"])
        self.assertLess(time.monotonic() - start, 60)
        self.assertEqual(failing(r), ["corrupt-input"])
        self.assertTrue(all("did not finish within 3 seconds" in d for d in self.details(r, "corrupt-input")),
                        self.details(r, "corrupt-input"))

    @POSIX
    def test_a_crash_on_a_vector_it_must_reject_fails_it(self):
        r = run(self.hybrid("crash"), cases=["alpha5-encoding-vectors"])
        self.assertEqual(failing(r), ["alpha5-encoding-vectors"])
        failed = {i.check for i in r["alpha5-encoding-vectors"].items if i.status == "fail"}
        self.assertEqual(failed, {"alpha5-decode", "alpha5-encode", "ccsds-epoch-strings", "catalog-number-is-integer"})
        self.assertTrue(any("no refusal and no rejection (D-341)" in d for d in self.details(r, "alpha5-encoding-vectors")))
        self.assertEqual(failing(run(self.hybrid("refuse"), cases=["alpha5-encoding-vectors"])), [])   # the twin

    @POSIX
    def test_a_crash_on_an_id_the_field_cannot_carry_fails_the_writer(self):
        r = run(self.hybrid("crash"), cases=["tle-writer-alpha5"])
        self.assertEqual(failing(r), ["tle-writer-alpha5"])
        refuse = [i for i in r["tle-writer-alpha5"].items if i.check == "tle-writer-refuses-unencodable"]
        self.assertEqual([i.status for i in refuse], ["fail"])
        self.assertIn("crashed instead of refusing: id 340000: the parser's command was ended by signal 11", refuse[0].detail)
        self.assertNotIn("written instead of refused", refuse[0].detail)
        self.assertEqual(failing(run(self.hybrid("refuse"), cases=["tle-writer-alpha5"])), [])   # the twin

    def test_a_python_parser_cannot_raise_the_runners_crash(self):
        """CommandCrashed passes the guard as itself only from the runner's own CommandParser: a Python parser that
        raises it is read as raising, its refusal of the file as a whole, as before. The twin is the test above."""
        cut = {open(p, "rb").read() for p in CUT}

        class Pretends(Reference):
            def parse(self, raw, fmt):
                if raw in cut:
                    raise CommandCrashed("was ended by signal 11 (SIGSEGV)")
                return super().parse(raw, fmt)
        self.assertEqual(failing(run(Pretends(), cases=["corrupt-input"])), [])


class AProviderLineBlankInColumn68IsRefused(unittest.TestCase):
    """The owner's ruling (2026-10-17) on D-338's second reading: a provider line cut inside its element set number
    (line 1) or its revolution number (line 2) and padded to 69 columns read the cut number (292 as 29, 56353 as 5635);
    a right-justified number never ends in a blank, so a provider line blank in column 68 is refused, in words, in the
    reader and the control adapter. The twins: the whole lines read, as lines and as card images, and a line a writer
    wrote is read as its fields say, not refused by this rule."""

    @staticmethod
    def lines():
        """The ISS set with the reading's numbers: element set 292 and revolution 56353, which a cut leaves as 29 and
        5635 where the single-digit element set of the plain set would leave no digit at all."""
        return tle_text(column(LINES[1], 64, 68, " 292"), column(LINES[2], 63, 68, "56353")).splitlines()

    def test_a_line_blank_in_column_68_is_refused_in_words(self):
        l0, l1, l2 = self.lines()
        for name, a, b, words in (
                ("line 1 cut at column 67 and padded to 69", f"{l1[:67]:69}", l2, "TLE line 1 is blank in column 68, the last digit of its element set number"),
                ("line 1 blank in column 68 beside a checksum", l1[:67] + " " + l1[68], l2, "TLE line 1 is blank in column 68"),
                ("line 2 cut at column 67 and padded to 69", l1, f"{l2[:67]:69}", "TLE line 2 is blank in column 68, the last digit of its revolution number"),
                ("a card image blank in column 68", f"{l1[:67] + ' ' + l1[68]:80}", f"{l2:80}", "TLE line 1 is blank in column 68")):
            with self.subTest(line=name):
                with self.assertRaises(ValueError) as cm:
                    ref.read_tle_text(f"{l0}\n{a}\n{b}\n")
                self.assertIn(words, str(cm.exception))
                self.assertIn("a line cut short", str(cm.exception))
                out = Reference().parse(f"{l0}\n{a}\n{b}\n".encode(), "tle")
                self.assertTrue(out and all("_refused" in r for r in out), out)

    def test_the_twins_whole_lines_read(self):
        l0, l1, l2 = self.lines()
        self.assertEqual((l1[64:68], l2[63:68]), (" 292", "56353"))
        for name, text in (("lines", f"{l0}\n{l1}\n{l2}\n"), ("card images", f"{l0}\n{l1:80}\n{l2:80}\n")):   # D-338
            with self.subTest(read_as=name):
                got = ref.read_tle_text(text)
                self.assertEqual((got[0]["element_set_no"], got[0]["rev_at_epoch"]), (292, 56353))
        written = ref.parse_tle_lines(l0, l1[:64] + " 29 " + l1[68], l2, written=True)   # a writer's line: its fields
        self.assertEqual(written["element_set_no"], 29)


class TheGuardReadsNoClassAParserClaims(unittest.TestCase):
    """The third reading of D-341, mended in D-342: the guard asked isinstance() of a parser, and isinstance() reads the
    parser's own __class__ where it differs from the type. A parser that claimed to be the runner's guard was left
    unwrapped, its own comparisons deciding checks; and a claimed __class__ ran, as the parser's code, outside the
    guard's try. Runner.__init__ now reads type(), and the guard knows the runner's crash by identity, or a
    CommandParser subclass's by its type. The twins: the same parsers without the claim, or refusing."""

    def test_a_parser_that_claims_to_be_the_guard_is_guarded(self):
        from gpconf.runner import _Guarded

        class Equal(int):
            """An integer that says it equals anything."""
            def __eq__(self, other):
                return True

            def __ne__(self, other):
                return False
            __hash__ = int.__hash__

        class Lies(Reference):
            """A wrong decoder: it rejects what the reference rejects and decodes every valid field to 0."""
            def alpha5_decode(self, field):
                super().alpha5_decode(field)
                return Equal(0)

        class Claims(Lies):
            @property
            def __class__(self):
                return _Guarded
        self.assertEqual(failing(run(Lies(), cases=["alpha5-encoding-vectors"])), ["alpha5-encoding-vectors"])   # the twin
        self.assertEqual(failing(run(Claims(), cases=["alpha5-encoding-vectors"])), ["alpha5-encoding-vectors"])

    def test_a_class_the_parser_claims_is_never_read(self):
        cut = {open(p, "rb").read() for p in CUT}
        read = []

        class Forges(Reference):
            def parse(self, raw, fmt):
                if raw in cut:
                    raise CommandCrashed("was ended by signal 11 (SIGSEGV)")
                return super().parse(raw, fmt)

        class Claims(Forges):
            @property
            def __class__(self):
                read.append(True)
                return CommandParser
        self.assertEqual(failing(run(Forges(), cases=["corrupt-input"])), [])      # the twin: its raise, a refusal
        self.assertEqual(failing(run(Claims(), cases=["corrupt-input"])), [])      # the same, its claim unread
        self.assertEqual(read, [])

    @POSIX
    def test_a_crash_that_comes_up_through_a_wrapper_or_a_proxy_is_a_crash(self):
        """The reading of D-342: with the class read by type(), a proxy around the runner's CommandParser (wrapt's
        ObjectProxy, a mock with a spec), whose __class__ says CommandParser, had its command's crash read as its raise.
        The runner now knows its own crashes by identity: one that comes up unchanged through any wrapper is a crash.
        The twins: the same wrappers around a command that refuses pass."""
        harness = ACommandThatCrashesOrRunsOutOfTimeRefusesNothing
        harness.setUpClass()
        try:
            for mode, want in (("crash", ["corrupt-input"]), ("refuse", [])):
                inner = harness.command(harness(), mode)

                class Wrapper:   # a plain wrapper that lets what its parser raises pass
                    def parse(self, raw, fmt):
                        return inner.parse(raw, fmt)

                class Proxy(Wrapper):   # a proxy that says it is what it wraps
                    @property
                    def __class__(self):
                        return CommandParser
                for wrapper in (Wrapper(), Proxy()):
                    with self.subTest(mode=mode, wrapper=type(wrapper).__name__):
                        self.assertEqual(failing(run(wrapper, cases=["corrupt-input"])), want)
        finally:
            harness.tearDownClass()


if __name__ == "__main__":
    unittest.main()
