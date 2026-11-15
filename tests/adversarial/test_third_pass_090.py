# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The third blind pass's findings that were not adapter wins (a fresh session on the 0.8.0 candidate, 2026-10-29;
its report and adapters are in the private handoff), held here as they are mended for 0.9.0 (D-389 onward).

A: a parser's refusal reason reached the gate headline raw (a line break forged a gate line; a lone surrogate ended
the run before the --json report). B: the --json report lacked the printed table's "secondary fields not kept".
C: a --tag that names nothing, and a run that grades nothing, exited 0.

Run: python -m unittest tests.adversarial.test_third_pass_090"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf.__main__ import main as gpconf_main  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.words import printable  # noqa: E402
from tests.raw_needed import needs_raw  # noqa: E402

ISS_RAW = os.path.join("fixtures", "baseline-iss-five-formats", "raw")   # withheld from the export (D-408)

EMPTY = tempfile.mkdtemp(prefix="gpconf-third-pass-empty-")


def tearDownModule():
    if os.path.isdir(EMPTY):   # a module run twice in one process removes it once (the 0.8.1 list's item 7)
        os.rmdir(EMPTY)


def gpconf(*args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = gpconf_main(["run", "--root", ROOT, "--data", EMPTY, "--no-fetch-hint", *args])
    return rc, out.getvalue(), err.getvalue()


class Refuses(Reference):
    """Refuses every record of every TLE file with the reason the test sets (the third pass's p01 probe, rewritten)."""
    REASON = ""

    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        if fmt in ("tle", "2le"):
            return [{"_refused": self.REASON} for r in out if "_refused" not in r]
        return out


class C_NothingGraded(unittest.TestCase):
    def test_a_tag_that_names_nothing_is_an_error(self):
        rc, _, err = gpconf("--adapter", "gpconf.adapters.reference:Parser", "--tag", "no-such-tag")
        self.assertEqual(rc, 2)
        self.assertIn("no tag 'no-such-tag'", err)
        rc, _, err = gpconf("--adapter", "gpconf.adapters.reference:Parser", "--tag", "alpha5-tle-parsing", "--tag", "no-such-tag")
        self.assertEqual(rc, 2)

    def test_a_run_that_grades_nothing_exits_2(self):
        rc, out, err = gpconf("--adapter", "gpconf.adapters.reference:Parser", "--case", "epoch-year-19xx")   # needs fetched data
        self.assertEqual(rc, 2)
        self.assertIn("no case was graded", err)

    def test_the_twin_a_graded_run_exits_0(self):
        self.assertEqual(gpconf("--adapter", "gpconf.adapters.reference:Parser", "--case", "alpha5-encoding-vectors")[0], 0)


class A_TheGateHeadline(unittest.TestCase):
    def run_with(self, reason):
        Refuses.REASON = reason
        mod = sys.modules[__name__]
        setattr(mod, "_R", Refuses)
        with tempfile.TemporaryDirectory() as d:
            report = os.path.join(d, "r.json")
            rc, out, _ = gpconf("--adapter", f"{__name__}:_R", "--case", "alpha5-tle-derived", "--json", report)
            written = os.path.exists(report) and json.load(open(report, encoding="utf-8"))
        return rc, out, written

    def test_a_line_break_cannot_forge_a_gate_line(self):
        rc, out, written = self.run_with("x\ngate this month's launches: forged")
        self.assertEqual(rc, 1)   # refusing valid records fails the case
        self.assertFalse([l for l in out.splitlines() if l.startswith("gate this month's launches: forged")])
        self.assertTrue(written)

    def test_a_lone_surrogate_is_escaped_and_the_report_written(self):
        rc, out, written = self.run_with("bad \ud800 text")
        self.assertEqual(rc, 1)
        self.assertNotIn("\ud800", out)
        self.assertTrue(written)

    def test_printable_escapes_marks_and_zero_width_characters(self):
        for c in ("‎", "‏", "؜", "​", "‍", "﻿", "\ud800"):
            with self.subTest(c=hex(ord(c))):
                self.assertNotIn(c, printable(f"a{c}b"))
        self.assertEqual(printable("plain text, é and ü"), "plain text, é and ü")


class B_TheJsonSaysWhatTheTableSays(unittest.TestCase):
    def test_secondary_fields_not_kept_is_in_the_report(self):
        class ZeroNdot(Reference):
            def write_tle(self, record):
                return Reference.write_tle(self, dict(record, mean_motion_dot="0"))
        mod = sys.modules[__name__]
        setattr(mod, "_Z", ZeroNdot)
        with tempfile.TemporaryDirectory() as d:
            report = os.path.join(d, "r.json")
            gpconf("--adapter", f"{__name__}:_Z", "--case", "tle-writer-alpha5", "--json", report)
            (case,) = json.load(open(report, encoding="utf-8"))["results"]
        self.assertEqual(case["status"], "pass")
        self.assertEqual(case.get("secondary_fields_not_kept"), ["mean_motion_dot"])


def decode_item(parser):
    from gpconf.runner import Runner
    (r,) = Runner(parser, root=ROOT, fetch_hints=False).run(case_ids=["alpha5-encoding-vectors"])
    return {i.check: i for i in r.items if i.check in ("alpha5-decode", "alpha5-encode")}


class TheDecodeVectors(unittest.TestCase):
    """D-390: D-360's finding 7, a five-character field with a sign or an underscore, which int() reads past. (The
    third pass's padded fields, the not-five-characters class and catalog number 0 wait for the owner's ruling.)"""

    def test_a_lenient_decoder_fails_by_name(self):
        class Lenient(Reference):
            def alpha5_decode(self, f):
                return int(f) if f[:1] in "+-" or "_" in f or " " in f.strip() else Reference.alpha5_decode(self, f)
        it = decode_item(Lenient())["alpha5-decode"]
        self.assertEqual(it.status, "fail")
        for f in ("'+1234' accepted as 1234", "'-1234' accepted as -1234", "'1_234' accepted as 1234"):
            self.assertIn(f, it.detail)
        self.assertEqual({k: v.status for k, v in decode_item(Reference()).items()}, {"alpha5-decode": "pass", "alpha5-encode": "pass"})

class TheCorruptInputs(unittest.TestCase):
    """D-391: the third pass's 16 (a TLE reader taking a leading O for 0) and 17 (one never comparing line 2's catalog
    field with line 1's) passed every case: the only invalid field on the parse path was I9999, and no input's two
    lines differed. Inputs 7 (O9999) and 8 (line 2 names 69998 under line 1's 69999) now carry them."""

    def corrupt(self, parser):
        from gpconf.runner import Runner
        (r,) = Runner(parser, root=ROOT, fetch_hints=False).run(case_ids=["corrupt-input"])
        return r.status, {(i.check, os.path.basename(i.file or "")): i.status for i in r.items}

    def test_o_read_as_0_fails_input_7(self):
        import re

        class OasZero(Reference):
            def parse(self, raw, fmt):
                return super().parse(re.sub(rb"(?m)^([12] )O", rb"\g<1>0", raw) if fmt in ("tle", "2le") else raw, fmt)
        status, items = self.corrupt(OasZero())
        self.assertEqual(status, "fail")
        self.assertEqual(items[("corrupt-tle-invalid-catalog-field", "c7-letter-o-catalog-field.tle")], "fail")
        self.assertEqual(items[("corrupt-tle-invalid-catalog-field", "c6-invalid-catalog-field.tle")], "pass")

    def test_line_1s_field_for_both_fails_input_8(self):
        from gpconf.tle import checksum

        class Line1Field(Reference):
            def parse(self, raw, fmt):
                if fmt in ("tle", "2le"):
                    lines, f = raw.split(b"\n"), None
                    for i, line in enumerate(lines):
                        if line.startswith(b"1 "):
                            f = line[2:7]
                        elif line.startswith(b"2 ") and f is not None:
                            body = line[:2] + f + line[7:68]
                            lines[i] = body + str(checksum(body.decode())).encode() + line[69:]
                    raw = b"\n".join(lines)
                return super().parse(raw, fmt)
        status, items = self.corrupt(Line1Field())
        self.assertEqual(status, "fail")
        self.assertEqual(items[("corrupt-tle-line-fields-differ", "c8-line-fields-differ.tle")], "fail")

    def test_the_reference_refuses_both(self):
        status, items = self.corrupt(Reference())
        self.assertEqual(status, "pass")
        self.assertEqual(items[("corrupt-tle-invalid-catalog-field", "c7-letter-o-catalog-field.tle")], "pass")
        self.assertEqual(items[("corrupt-tle-line-fields-differ", "c8-line-fields-differ.tle")], "pass")


class TheDecoyLetter(unittest.TestCase):
    """D-392, the separate review of D-391: a parser that drops the set it refuses, says nothing, and plants a refusal
    whose _input is one letter the edit introduced ("O", in no unedited line) had the drop of inputs 3 and 7 credited;
    an _input is evidence now only where it holds a whole line the edit introduced."""

    def test_a_one_letter_decoy_credits_nothing(self):
        from gpconf.runner import Runner

        class Decoy(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                if fmt in ("tle", "2le"):
                    out = [r for r in out if "_refused" not in r] + [{"_refused": "x", "_input": "O"}, {"_adapter": {"refusals": True}}]
                return out
        (r,) = Runner(Decoy(), root=ROOT, fetch_hints=False).run(case_ids=["corrupt-input"])
        by = {(i.check, os.path.basename(i.file or "")): i.status for i in r.items}
        self.assertEqual(by[("corrupt-tle-letter-in-number", "c3-letter-in-epoch.tle")], "fail")
        self.assertEqual(by[("corrupt-tle-invalid-catalog-field", "c7-letter-o-catalog-field.tle")], "fail")

    def test_the_twin_quoting_the_edited_line_is_credited(self):
        from gpconf.runner import Runner

        class Quotes(Reference):   # refuses with no _field, quoting the offending line whole: credited, as before
            def parse(self, raw, fmt):
                return [{k: v for k, v in r.items() if k != "_field"} if "_refused" in r else r for r in super().parse(raw, fmt)]
        (r,) = Runner(Quotes(), root=ROOT, fetch_hints=False).run(case_ids=["corrupt-input"])
        by = {(i.check, os.path.basename(i.file or "")): i.status for i in r.items}
        self.assertEqual(by[("corrupt-tle-letter-in-number", "c3-letter-in-epoch.tle")], "pass")
        self.assertEqual(by[("corrupt-tle-invalid-catalog-field", "c7-letter-o-catalog-field.tle")], "pass")


    def test_a_set_quoted_from_its_name_line_is_credited(self):
        # the second reading of D-392: the test read the report's 80 characters, which cut line 1 short
        from gpconf.runner import Runner

        class Set(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                if fmt not in ("tle", "2le"):
                    return out
                lines = raw.decode("ascii").split("\r\n")
                res = []
                for r in out:
                    if "_refused" in r:
                        i = next(k for k, l in enumerate(lines) if l[:80] == r["_input"][:80])
                        r = {"_refused": r["_refused"], "_input": "\r\n".join(lines[max(i - 1, 0):i + 2])}
                    res.append(r)
                return res
        (r,) = Runner(Set(), root=ROOT, fetch_hints=False).run(case_ids=["corrupt-input"])
        by = {(i.check, os.path.basename(i.file or "")): i.status for i in r.items}
        self.assertEqual(by[("corrupt-tle-letter-in-number", "c3-letter-in-epoch.tle")], "pass")
        self.assertEqual(by[("corrupt-tle-invalid-catalog-field", "c7-letter-o-catalog-field.tle")], "pass")


class TheQuoteIsReadWhole(unittest.TestCase):
    """D-393: the evidence test reads a refusal's _input up to INPUT_READ characters (4,096), so an honest quote of a
    corrupt input, the whole file included, is read whole where it was cut at 1,024; an _input longer than INPUT_READ
    voids the file's quoted-input evidence, the cut site's included, since lines past what is read go unseen. A
    refusal's _field still credits."""

    def credited(self, parser):
        from gpconf.runner import Runner
        (r,) = Runner(parser, root=ROOT, fetch_hints=False).run(case_ids=["corrupt-input"])
        return {os.path.basename(i.file or "") for i in r.items if i.check.startswith("corrupt-tle") and i.status == "pass"}

    def test_an_honest_whole_file_quote_is_credited(self):
        class WholeFile(Reference):   # the reference's refusals, no _field, each quoting the whole file
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                if fmt not in ("tle", "2le"):
                    return out
                return [{"_refused": r["_refused"], "_input": raw.decode("ascii")} if "_refused" in r else r for r in out]
        self.assertTrue({"c3-letter-in-epoch.tle", "c6-invalid-catalog-field.tle", "c7-letter-o-catalog-field.tle"} <= self.credited(WholeFile()))

    def test_the_limit_stays_above_any_whole_input(self):
        # the owner's guard (2026-11-07): an honest quote of a whole corrupt input must fit in what is read, with room;
        # every input, the ones added later included, stays under half the limit, or the limit rises with the data
        from gpconf.runner import INPUT_READ
        d = os.path.join(ROOT, "derived", "corrupt-input")
        sizes = {f: len(open(os.path.join(d, f), encoding="utf-8").read()) for f in os.listdir(d) if not f.endswith(".provenance.json")}
        self.assertTrue(len(sizes) >= 9)
        self.assertEqual({f: n for f, n in sizes.items() if n > INPUT_READ // 2}, {})

    def test_a_quote_past_1024_characters_is_read(self):
        # the widening itself (the review of D-393): every .tle input fits in 1,024 characters, so a stand-in quote longer
        # than that, the line at its end, is what only the wider read credits
        class Long(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                if fmt not in ("tle", "2le"):
                    return out
                return [{"_refused": r["_refused"], "_input": "context: " + "-" * 1100 + "\r\n" + r["_input"]} if "_refused" in r else r
                        for r in out]
        self.assertTrue({"c3-letter-in-epoch.tle", "c6-invalid-catalog-field.tle", "c7-letter-o-catalog-field.tle"} <= self.credited(Long()))

    def test_a_cut_site_quote_past_what_is_read_credits_nothing(self):
        from gpconf.runner import INPUT_READ, Runner

        class CutPadded(Reference):   # the review's: keeps what it loads of the cut JSON, adds one over-long refusal of the cut site
            def parse(self, raw, fmt):
                if fmt != "json":
                    return super().parse(raw, fmt)
                out = super().parse(raw + b"]", fmt) if raw.rstrip().endswith(b"}") else super().parse(raw, fmt)
                return [r for r in out if "_refused" not in r] + [{"_refused": "x", "_input": raw.decode()[-100:] + " " * (INPUT_READ + 10)},
                                                                   {"_adapter": {"refusals": True}}]
        (r,) = Runner(CutPadded(), root=ROOT, fetch_hints=False).run(case_ids=["corrupt-input"])
        (it,) = [i for i in r.items if i.check == "corrupt-file-cut" and (i.file or "").endswith("c5-cut-closing-bracket.json")]
        self.assertEqual(it.status, "fail")

    def test_an_input_past_what_is_read_credits_nothing(self):
        from gpconf.runner import INPUT_READ

        class Padded(Reference):   # drops silently; one refusal holding the edited set, then more than is read
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                if fmt not in ("tle", "2le"):
                    return out
                return ([r for r in out if "_refused" not in r]
                        + [{"_refused": "x", "_input": raw.decode("ascii") + " " * INPUT_READ}, {"_adapter": {"refusals": True}}])
        self.assertEqual(self.credited(Padded()), set())

def _decoy(pick):
    """Drops every set it refuses silently, and adds refusals quoting pick(the file's lines), no _field."""
    class Decoy(Reference):
        def parse(self, raw, fmt):
            out = super().parse(raw, fmt)
            if fmt not in ("tle", "2le"):
                return out
            ls = raw.decode("ascii").split("\r\n")
            return [r for r in out if "_refused" not in r] + [{"_refused": "x", "_input": q} for q in pick(ls)] + [{"_adapter": {"refusals": True}}]
    return Decoy()


def _el(ls):
    return [i for i, l in enumerate(ls) if l[:2] in ("1 ", "2 ")]


# the decoys of the comparison (D-395), each with how many corrupt inputs it is credited on, measured 2026-11-07 on
# D-393's code (no contradiction rule: the owner's ruling, D-395)
KNOWN_LIMITS = {
    "per line": (lambda ls: [ls[i] for i in _el(ls)], 8),
    "whole file": (lambda ls: ["\r\n".join(ls)], 8),
    "all but one line": (lambda ls: ["\r\n".join(l for i, l in enumerate(ls) if i != _el(ls)[-1])], 8),
    "first 6 lines": (lambda ls: ["\r\n".join(ls[:6])], 7),
    "file minus last set": (lambda ls: ["\r\n".join(ls[:-4])], 7),
    "lines 4-6": (lambda ls: ["\r\n".join(ls[3:6])], 6),
    "last 6 lines": (lambda ls: ["\r\n".join(ls[-7:])], 6),
    "file minus first set": (lambda ls: ["\r\n".join(ls[3:])], 7),
}


def _reader(make):
    """A correct reader: the reference's verdicts, each refusal's _input replaced by the quotes make(i, lines) gives
    for the refused line i (spans (lo, hi) or text), one refusal per quote, no _field (the review of D-395's shapes)."""
    class Reader(Reference):
        def parse(self, raw, fmt):
            out = super().parse(raw, fmt)
            if fmt not in ("tle", "2le"):
                return out
            ls, res = raw.decode("ascii").split("\r\n"), []
            for r in out:
                if "_refused" in r:
                    i = next(k for k, l in enumerate(ls) if l[:69] == (r.get("_input") or "")[:69])
                    for q in make(i, ls):
                        res.append({"_refused": r["_refused"], "_input": q if isinstance(q, str) else "\r\n".join(ls[max(q[0], 0):q[1]])})
                else:
                    res.append(r)
            return res
    return Reader()


def _set_start(i, ls):
    return i - (1 if ls[i].startswith("1 ") else 2)


def _elems(i, ls):
    s = _set_start(i, ls)
    return [j for j in (s + 1, s + 2) if j < len(ls) and ls[j][:2] in ("1 ", "2 ")]


def _next_line1(i, ls):
    return next((k for k in range(i + 1, len(ls)) if ls[k].startswith("1 ")), len(ls) - 1)


ALL = ["c10", "c11", "c2", "c3", "c6", "c7", "c8", "c9"]
SELF = ["c10", "c11", "c3", "c6", "c7", "c9"]
# correct readers and what each is credited on today, measured 2026-11-07; a future rule must keep each one's credit
# (the owner's principle: gpconf must not fail a correct reader); without _field none can be credited on input 4
CORRECT_READERS = {
    "self only": (lambda i, ls: [(i, i + 1)], SELF),
    "±1 lines": (lambda i, ls: [(i - 1, i + 2)], ALL),
    "±2 lines": (lambda i, ls: [(i - 2, i + 3)], ALL),
    "±3 lines": (lambda i, ls: [(i - 3, i + 4)], ALL),
    "whole set before": (lambda i, ls: [(_set_start(i, ls) - 3, _set_start(i, ls) + 3)], ALL),
    "whole set after": (lambda i, ls: [(_set_start(i, ls), _set_start(i, ls) + 6)], ALL),
    "to the next line 1": (lambda i, ls: [(i, _next_line1(i, ls) + 1)], ALL),
    "previous line 2 and name, then self": (lambda i, ls: [(_set_start(i, ls) - 1, _set_start(i, ls) + 1), (i, i + 1)], SELF),
    "previous line 2, name and self": (lambda i, ls: [(_set_start(i, ls) - 1, i + 1)], SELF),
    "per element line, two forward": (lambda i, ls: [(j, j + 3) for j in _elems(i, ls)], ALL),
    "per element line, two back": (lambda i, ls: [(j - 2, j + 1) for j in _elems(i, ls)], ALL),
    "per element line": (lambda i, ls: [(j, j + 1) for j in _elems(i, ls)], ALL),
    "self, and the other line two forward": (lambda i, ls: [(i, i + 1)] + [(j, j + 3) for j in _elems(i, ls) if j != i], ALL),
    "neighbour's line 2 and part of self, then self": (lambda i, ls: [ls[_set_start(i, ls) - 1] + "\r\n" + ls[i][:40], ls[i]], SELF),
}


class KnownLimitsOfQuotedInputEvidence(unittest.TestCase):
    """D-395 (the owner's rulings, 2026-11-07): no rule on refusals' quotes is kept, since each rule measured failed a
    correct reader (the per-line rule, the review found, failed readers that quote a neighbour's line beside the
    edit). Eight decoys that drop the corrupt set silently and plant quoting refusals are known limits: each is credited
    on some inputs, and none passes the case, since input 4 adds no line to quote and so credits only through _field."""

    def run_case(self, p):
        from gpconf.runner import Runner
        (r,) = Runner(p, root=ROOT, fetch_hints=False).run(case_ids=["corrupt-input"])
        return r.status, sorted(os.path.basename(i.file or "")[:3].rstrip("-") for i in r.items
                                if i.check.startswith("corrupt-tle") and i.status == "pass")

    def test_each_decoy_is_credited_on_some_inputs_and_never_passes(self):
        for name, (pick, n) in KNOWN_LIMITS.items():
            with self.subTest(name):
                status, credited = self.run_case(_decoy(pick))
                self.assertEqual(status, "fail")
                self.assertNotIn("c4", credited)          # why it never passes: input 4 credits only through _field
                self.assertEqual(len(credited), n)

    def test_the_twin_the_same_drop_without_the_quote_gets_nothing(self):
        self.assertEqual(self.run_case(_decoy(lambda ls: [])), ("fail", []))

    def test_correct_readers_keep_their_credit(self):
        for name, (make, want) in CORRECT_READERS.items():
            with self.subTest(name):
                self.assertEqual(self.run_case(_reader(make))[1], want)

    def test_a_reader_giving_its_field_is_credited_everywhere(self):
        self.assertEqual(self.run_case(Reference()), ("pass", ["c10", "c11", "c2", "c3", "c4", "c6", "c7", "c8", "c9"]))

SAID = "returned and refused the same record — a refusal means the record was dropped; don't report warnings as refusals"


def _checksum_bad(l):
    return (l[:2] in ("1 ", "2 ") and len(l) == 69 and l[68].isdigit()
            and int(l[68]) != sum(int(c) if c.isdigit() else c == "-" for c in l[:68]) % 10)


class FieldPerSet(Reference):
    """The review's F3: drops each corrupt set silently and plants one refusal per set of the file naming its catalog
    field, the sets it returns among them. Before D-396 it passed corrupt-input."""
    ONLY_DROPPED = False

    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        if fmt not in ("tle", "2le"):
            return out
        kept = [r for r in out if "_refused" not in r]
        fields = []
        for l in raw.decode("ascii").split("\r\n"):
            if l[:2] in ("1 ", "2 ") and l[2:7] not in fields:
                fields.append(l[2:7])
        if self.ONLY_DROPPED:   # the twin: the same drop, refusing only the sets it does not return
            returned = {str(r.get("norad_cat_id")) for r in kept}
            fields = [f for f in fields if f.strip().lstrip("0") not in returned]
        return kept + [{"_refused": "x", "_field": f} for f in fields] + [{"_adapter": {"refusals": True}}]


class FieldPerDroppedSet(FieldPerSet):
    ONLY_DROPPED = True


class LenientWarns(Reference):
    """Reads input 1 (a wrong checksum) as unedited, as the reference does, and reports the checksum as a refusal of
    the record it loaded: a warning given as a refusal (the owner's example, D-396)."""

    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        if fmt not in ("tle", "2le"):
            return out
        return out + [{"_refused": "checksum mismatch; record loaded anyway", "_field": l[2:7], "_input": l}
                      for l in raw.decode("ascii").split("\r\n") if _checksum_bad(l)]


class RefusesWhatItReturns(Reference):
    """Returns every record of a TLE file and refuses its first one too, with or without a reason."""
    REASON = "a warning"

    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        if fmt not in ("tle", "2le"):
            return out
        first = next(l for l in raw.decode("ascii").split("\r\n") if l.startswith("1 "))
        return out + [{"_refused": self.REASON, "_field": first[2:7]}]


class ReturnedAndRefused(unittest.TestCase):
    """D-396 (the owner's ruling, 2026-11-08): a file in which a record is both returned and refused fails its
    refusals item, naming the record, since a refusal means the record was dropped with an error."""

    def items(self, parser, case):
        from gpconf.runner import Runner
        (r,) = Runner(parser, root=ROOT, fetch_hints=False).run(case_ids=[case])
        return r.status, [i for i in r.items if i.check == "refusals"]

    def test_the_field_per_set_decoy_fails_corrupt_input(self):
        status, items = self.items(FieldPerSet(), "corrupt-input")
        self.assertEqual(status, "fail")
        bad = {os.path.basename(i.file): i.detail for i in items if i.status == "fail"}
        self.assertEqual(len(bad), 10)   # every TLE input: it refuses the neighbours it returns
        self.assertIn(SAID, bad["c3-letter-in-epoch.tle"])
        self.assertIn("ids 20453, 25544", bad["c3-letter-in-epoch.tle"])

    def test_its_twin_refusing_only_what_it_drops_is_not_failed_by_it(self):
        status, items = self.items(FieldPerDroppedSet(), "corrupt-input")
        self.assertEqual(status, "pass")
        self.assertFalse([i for i in items if SAID in i.detail])

    def test_a_warning_given_as_a_refusal_fails_and_says_why(self):
        status, items = self.items(LenientWarns(), "corrupt-input")
        self.assertEqual(status, "fail")
        (item,) = [i for i in items if i.status == "fail"]
        self.assertEqual(os.path.basename(item.file), "c1-checksum-digit.tle")
        self.assertIn(SAID + " (id 69999; D-396)", item.detail)

    def test_the_same_reading_without_the_warning_passes(self):
        self.assertEqual(self.items(Reference(), "corrupt-input")[0], "pass")

    @needs_raw(ISS_RAW)
    def test_in_a_record_case_too_with_or_without_a_reason(self):
        for reason in ("a warning", ""):
            with self.subTest(reason=reason):
                p = RefusesWhatItReturns()
                p.REASON = reason
                status, items = self.items(p, "baseline-iss-five-formats")
                self.assertEqual(status, "fail")
                fails = [i for i in items if i.status == "fail"]
                self.assertTrue(fails)
                self.assertTrue(all(SAID + " (id 25544; D-396)" in i.detail for i in fails))
                self.assertEqual(all("without a reason" in i.detail for i in fails), not reason)

    def test_a_file_holding_an_id_twice_may_return_one_copy_and_refuse_the_other(self):
        # no shipped file holds an id twice (a fetched one may, D-311); the item is read directly
        import collections
        from gpconf.runner import CaseResult, Runner, split_refusals
        one = {"_refused": "line 2 short", "_field": "25544"}
        for returned, refused, held, want in ((1, 1, 2, "info"), (1, 2, 2, "info"), (2, 1, 2, "fail"), (1, 1, 1, "fail"),
                                              (1, 1, 0, "fail")):
            with self.subTest(returned=returned, refused=refused, held=held):
                _, refusals, _ = split_refusals([one] * refused)
                res = CaseResult("t", "t")
                Runner(Reference(), root=ROOT, fetch_hints=False).report_refusals(
                    res, "f.tle", refusals, collections.Counter({25544: returned}), collections.Counter({25544: held} if held else {}))
                (item,) = res.items
                self.assertEqual(item.status, want)
                self.assertEqual(SAID in item.detail, want == "fail")

    @needs_raw(ISS_RAW)
    def test_the_copies_held_come_from_the_reference_reading(self):
        import collections
        from gpconf.runner import Runner
        seen = []
        r = Runner(Refuses(), root=ROOT, fetch_hints=False)
        orig = r.report_refusals
        r.report_refusals = lambda res, path, refusals, returned=None, held=None: (seen.append((os.path.basename(path), held)), orig(res, path, refusals, returned, held))[1]
        r.run(case_ids=["baseline-iss-five-formats"])
        self.assertIn(("iss.tle", collections.Counter({25544: 1})), seen)

    def test_an_alpha5_field_names_the_record_it_decodes_to(self):
        status, items = self.items(RefusesWhatItReturns(), "alpha5-tle-derived")
        self.assertEqual(status, "fail")
        self.assertTrue(any("id 100000; D-396" in i.detail for i in items if i.status == "fail"))

    def test_a_refusal_of_the_cut_json_may_name_its_last_record(self):
        # the review of D-396: a correct reader returns the three complete records and refuses the cut naming the last
        class CutNamesLast(Reference):
            def parse(self, raw, fmt):
                if fmt == "json" and not raw.rstrip().endswith(b"]"):
                    txt = raw.decode()
                    recs = Reference().parse((txt.rstrip() + "]").encode(), fmt)
                    return recs + [{"_refused": "unexpected end of input after the last record", "_input": txt[-60:],
                                    "_field": str(recs[-1]["norad_cat_id"])}, {"_adapter": {"refusals": True}}]
                return Reference.parse(self, raw, fmt)
        status, items = self.items(CutNamesLast(), "corrupt-input")
        self.assertEqual(status, "pass")
        self.assertFalse([i for i in items if SAID in i.detail])


if __name__ == "__main__":
    unittest.main()
