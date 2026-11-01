# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Lane C's two cases (D-360, the owner's confirmation of 2026-10-23), each with a wrong-on-purpose adapter and its
twin: a blank or an empty Alpha-5 field read as 0 passed alpha5-encoding-vectors (no decode_invalid vector was blank);
and no shipped TLE file held an invalid catalog field, so a TLE reader that read I9999 as 189999 (letters mapped by
their code without skipping I) was caught only through its decode hook, never through its own reader.

The files are the corpus's own vectors and derived files (no provider's bytes, so the module runs in the public
export). Run: python -m unittest tests.adversarial.test_lane_c_cases_080"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import CommandCrashed, CommandParser, Runner  # noqa: E402

C6 = "c6-invalid-catalog-field.tle"


class BlankIsZero(Reference):
    """The reference, but its Alpha-5 decoder reads a blank or empty field as 0 (lane C's probe, BlankIsZero)."""

    def alpha5_decode(self, field):
        if field.strip() == "":
            return 0
        return super().alpha5_decode(field)


class LettersByCode(Reference):
    """The reference, but its TLE reader decodes the catalog field's letter by its code without skipping I: I9999 is
    read as 189999, the number J9999 stands for (the bug the decode vectors name, now in the reader)."""

    def parse(self, raw, fmt):
        return super().parse(raw.replace(b"I9999", b"J9999") if fmt in ("tle", "2le") else raw, fmt)


class DropsIt(Reference):
    """The reference, but the set it refuses is dropped without a word."""

    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        return [r for r in out if not (isinstance(r, dict) and "_refused" in r and "I9999" in str(r.get("_field", "")))]


class FieldOnly(Reference):
    """The reference, but its refusals carry _refused and _field and no _input, the minimal form ADAPTERS.md allows."""

    def parse(self, raw, fmt):
        return [{k: v for k, v in r.items() if k != "_input"} if isinstance(r, dict) and "_refused" in r else r
                for r in super().parse(raw, fmt)]


class NoReasonField(FieldOnly):
    """FieldOnly, but its refusals give no reason."""

    def parse(self, raw, fmt):
        return [dict(r, _refused="") if isinstance(r, dict) and "_refused" in r else r for r in super().parse(raw, fmt)]


class Decoy(Reference):
    """Drops the corrupt set without a word and sends one refusal with the _field given: text the edit introduced that is
    not the set's catalog field (D-360's second reading, finding 1), or that field padded (its third reading, N4)."""

    def __init__(self, field):
        self.field = field

    def parse(self, raw, fmt):
        out = [r for r in super().parse(raw, fmt) if not (isinstance(r, dict) and "_refused" in r)]
        return out + [{"_refused": "decoy: not about the corrupt set", "_field": self.field}] if fmt in ("tle", "2le") else out


class NoReasonDecoy(Reference):
    """Drops the corrupt set and sends a refusal without a reason that quotes nothing: still a drop."""

    def parse(self, raw, fmt):
        out = [r for r in super().parse(raw, fmt) if not (isinstance(r, dict) and "_refused" in r)]
        return out + [{"_refused": "", "_field": "VANGUARD"}] if fmt in ("tle", "2le") else out


class Echoes(Reference):
    """A decoder that hands a blank or empty field back as its result."""

    def alpha5_decode(self, field):
        return field if field.strip() == "" else super().alpha5_decode(field)


class CrashesOnBlank(CommandParser):
    """A command parser whose decode hook crashes on a blank or empty field (a CommandParser's CommandCrashed is a crash)."""

    def __init__(self):
        super().__init__(cmd="true")

    def alpha5_decode(self, field):
        if field.strip() == "":
            raise CommandCrashed("was ended by signal 6 (SIGABRT)")
        return Reference().alpha5_decode(field)


def items(parser, case):
    return Runner(parser, root=ROOT, fetch_hints=False).run(case_ids=[case])[0].items


class LaneCsCases(unittest.TestCase):

    def test_a_blank_or_empty_alpha5_field_is_no_catalog_number(self):
        """The decode vectors hold a blank and an empty field: a decoder reading them as 0 fails alpha5-decode, naming
        each; its twin, the reference, passes."""
        (got,) = [i for i in items(BlankIsZero(), "alpha5-encoding-vectors") if i.check == "alpha5-decode"]
        self.assertEqual(got.status, "fail", got.detail)
        # each field shown as it is, a blank one too (D-360's first reading, finding 3)
        self.assertIn("'     ' accepted as 0 (should be rejected: a blank field is no catalog number", got.detail)
        self.assertIn("'' accepted as 0 (should be rejected: an empty field is no catalog number", got.detail)
        (twin,) = [i for i in items(Reference(), "alpha5-encoding-vectors") if i.check == "alpha5-decode"]
        self.assertEqual(twin.status, "pass", twin.detail)

    def test_an_invalid_catalog_field_in_a_tle_file_is_refused(self):
        """Input 6: a TLE reader reading I9999 as 189999 fails the new item (a record built from the corrupt input, an
        id the file does not hold); one dropping the set without a word fails it too; the reference refuses it with a
        reason, its neighbours loaded."""
        for name, p, words in (("read as 189999", LettersByCode(), "1 record the file does not hold, built from garbage"),
                               ("dropped silently", DropsIt(), "the corrupt record dropped")):
            with self.subTest(name):
                got = {i.check: i for i in items(p, "corrupt-input") if (i.file or "").endswith(C6)}
                self.assertEqual(got["corrupt-tle-invalid-catalog-field"].status, "fail", got["corrupt-tle-invalid-catalog-field"].detail)
                self.assertIn(words, got["corrupt-tle-invalid-catalog-field"].detail)
        got = {i.check: i for i in items(Reference(), "corrupt-input") if (i.file or "").endswith(C6)}
        self.assertEqual(got["corrupt-tle-invalid-catalog-field"].status, "pass", got["corrupt-tle-invalid-catalog-field"].detail)
        self.assertIn("refused with a reason", got["corrupt-tle-invalid-catalog-field"].detail)
        self.assertEqual(got["corrupt-input-neighbours-load"].status, "pass")

    def test_a_refusal_naming_the_invalid_field_is_credited(self):
        """D-360's first reading, finding 1: a refusal in the minimal form, _refused and _field and no _input, whose
        _field is the invalid field the edit introduced, is credited to the corrupt record (D-282's evidence: text the
        edit introduced and the unedited file does not hold); without a reason it is said to be that, not a drop the
        adapter never reported (finding 4)."""
        self.assertFalse(any("_input" in r for r in FieldOnly().parse(open(os.path.join(ROOT, "derived", "corrupt-input", C6), "rb").read(), "tle")
                             if isinstance(r, dict) and "_refused" in r))   # the minimal form: no _input (the second reading, T2)
        got = {i.check: i for i in items(FieldOnly(), "corrupt-input") if (i.file or "").endswith(C6)}
        self.assertEqual(got["corrupt-tle-invalid-catalog-field"].status, "pass", got["corrupt-tle-invalid-catalog-field"].detail)
        # the field padded, as a reader may hand the columns back, is the field (D-360's third reading, mutant N4)
        got = {i.check: i for i in items(Decoy(" I9999 "), "corrupt-input") if (i.file or "").endswith(C6)}
        self.assertEqual(got["corrupt-tle-invalid-catalog-field"].status, "pass", got["corrupt-tle-invalid-catalog-field"].detail)
        got = {i.check: i for i in items(NoReasonField(), "corrupt-input") if (i.file or "").endswith(C6)}
        self.assertEqual(got["corrupt-tle-invalid-catalog-field"].status, "fail")
        self.assertEqual(got["corrupt-tle-invalid-catalog-field"].detail, "the corrupt record refused without a reason: no better than a drop (D-144)")
        # its twin: a refusal without a reason that quotes nothing the edit introduced is still a drop (the second reading, R9)
        got = {i.check: i for i in items(NoReasonDecoy(), "corrupt-input") if (i.file or "").endswith(C6)}
        self.assertTrue(got["corrupt-tle-invalid-catalog-field"].detail.startswith("the corrupt record dropped"), got["corrupt-tle-invalid-catalog-field"].detail)

    def test_a_decoy_field_credits_no_silent_drop(self):
        """D-360's second reading, finding 1: a _field is evidence only where it is the catalog field of an element line
        the edit introduced; text the edit introduced elsewhere ("O" on c3, digits on c2, part of the field on c6) credits
        no record, and the drop fails, on each TLE input."""
        for name, field in (("c3-letter-in-epoch.tle", "O"), ("c2-line-2-short.tle", "480"), (C6, " I"), (C6, "I9"), (C6, "2")):
            with self.subTest(file=name, field=field):
                got = {i.check: i for i in items(Decoy(field), "corrupt-input") if (i.file or "").endswith(name)}
                check = next(c for c in got if c.startswith("corrupt-tle-"))
                self.assertEqual(got[check].status, "fail", got[check].detail)
                # its words, pinned (D-360's check of its mended lines, point 4)
                self.assertIn("; 1 refusal naming no record of this file credited to none (D-282, D-360)", got[check].detail)

    def test_the_decode_words_show_a_blank_field(self):
        """D-360's second reading, finding 2: in the crash words and the value returned, a blank or empty field shows."""
        (got,) = [i for i in items(Echoes(), "alpha5-encoding-vectors") if i.check == "alpha5-decode"]
        self.assertIn("'     ' accepted as '     '", got.detail)
        self.assertIn("'' accepted as ''", got.detail)
        (got,) = [i for i in items(CrashesOnBlank(), "alpha5-encoding-vectors") if i.check == "alpha5-decode"]
        self.assertIn("'     ': the parser's command was ended by signal 6", got.detail)
        self.assertIn("'': the parser's command was ended by signal 6", got.detail)


if __name__ == "__main__":
    unittest.main()
