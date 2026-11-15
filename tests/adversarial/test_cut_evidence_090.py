# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""D-400 (Phase 2 of 0.9.0): the cut site's evidence in corrupt-input. A refusal quoting the cut site credits the CSV
cut's row as it credits the JSON cut (a correct CSV reader failed before: the check of D-360's mended lines), and it is
no evidence from a parser that refuses with a reason in the unedited file too (the third blind pass's 12: a refusal
quoting every JSON answer's tail was credited)."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from gpconf.adapters.reference import Parser as Reference  # noqa: E402


def _cut_csv(raw):
    return raw.rstrip(b"\r\n").split(b"\n")[-1].count(b",") < 16


class CsvRefusesTheCutRow(Reference):
    """Loads the two complete rows of the cut CSV and refuses the cut row with a reason, no _field, quoting QUOTE."""
    QUOTE = "row"

    def parse(self, raw, fmt):
        if fmt == "csv" and _cut_csv(raw):
            lines = raw.decode().rstrip("\r\n").split("\n")
            out = Reference.parse(self, "\n".join(lines[:-1]).encode() + b"\n", fmt)
            q = {"row": lines[-1], "tail": raw.decode()[-24:]}[self.QUOTE]
            return [r for r in out if "_refused" not in r] + [{"_refused": "row cut short", "_input": q}]
        return super().parse(raw, fmt)


class CsvQuotesTheCutSite(CsvRefusesTheCutRow):
    QUOTE = "tail"


class JsonRefusesTheCut(Reference):
    """Loads the three complete records of the cut JSON and refuses the cut, quoting the file's tail, no _field."""

    def parse(self, raw, fmt):
        if fmt == "json" and not raw.rstrip().endswith(b"]"):
            txt = raw.decode()
            return Reference.parse(self, (txt.rstrip() + "]").encode(), fmt) + [
                {"_refused": "unexpected end of input after the last record", "_input": txt[-60:]}, {"_adapter": {"refusals": True}}]
        return super().parse(raw, fmt)


class TailDecoy(Reference):
    """The third blind pass's e12, for both formats: repairs the cut and plants a refusal quoting every answer's tail."""

    def parse(self, raw, fmt):
        if fmt == "json" and not raw.rstrip().endswith(b"]"):
            out = Reference.parse(self, raw.rstrip() + b"]", fmt)
        elif fmt == "csv" and _cut_csv(raw):
            lines = raw.decode().rstrip("\r\n").split("\n")
            out = Reference.parse(self, "\n".join(lines[:-1]).encode() + b"\n", fmt)
        else:
            out = super().parse(raw, fmt)
        if fmt in ("json", "csv"):
            out = [{"_adapter": {"refusals": True}}] + [r for r in out if "_adapter" not in r and "_refused" not in r] + [
                {"_refused": "input may be truncated", "_input": raw.decode().rstrip()[-24:]}]
        return out


def cut_items(parser):
    from gpconf.runner import Runner
    (r,) = Runner(parser, root=ROOT, fetch_hints=False).run(case_ids=["corrupt-input"])
    return r.status, {os.path.basename(i.file): (i.status, i.detail) for i in r.items if i.check == "corrupt-file-cut"}


class TheCutSite(unittest.TestCase):
    def test_a_csv_reader_quoting_the_cut_site_is_credited(self):
        status, cut = cut_items(CsvQuotesTheCutSite())
        self.assertEqual(cut["c5-cut-last-row.csv"][0], "pass", cut["c5-cut-last-row.csv"][1])
        self.assertEqual(status, "pass")

    def test_one_quoting_the_cut_row_whole_still_is(self):
        self.assertEqual(cut_items(CsvRefusesTheCutRow())[1]["c5-cut-last-row.csv"][0], "pass")

    def test_a_json_reader_refusing_the_cut_is_credited(self):
        status, cut = cut_items(JsonRefusesTheCut())
        self.assertEqual((status, cut["c5-cut-closing-bracket.json"][0]), ("pass", "pass"))

    def test_the_tail_decoy_is_credited_on_neither(self):
        status, cut = cut_items(TailDecoy())
        self.assertEqual(status, "fail")
        self.assertEqual(cut["c5-cut-closing-bracket.json"][0], "fail")
        self.assertEqual(cut["c5-cut-last-row.csv"][0], "fail")

    def test_the_reference_refusing_both_files_whole_passes(self):
        self.assertEqual(cut_items(Reference())[0], "pass")


class JsonQuotesTheLastRecord(Reference):
    """The review of D-400's finding 2: loads the three records and refuses the cut quoting the last record whole, from
    its brace to the cut; its first 80 characters lie outside the file's last 200."""

    def parse(self, raw, fmt):
        if fmt == "json" and not raw.rstrip().endswith(b"]"):
            txt = raw.decode()
            return Reference.parse(self, (txt.rstrip() + "]").encode(), fmt) + [
                {"_refused": "unexpected end of input", "_input": txt[txt.rindex("{"):]}, {"_adapter": {"refusals": True}}]
        return super().parse(raw, fmt)


class CsvNamesANeighbour(CsvQuotesTheCutSite):
    """Drops the cut row and refuses quoting the cut site, but names a row it returns (20453) as the refusal's _field."""

    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        if fmt == "csv" and _cut_csv(raw):
            out = [dict(r, _field="20453") if "_refused" in r else r for r in out]
        return out


class NoteEverywhere(JsonRefusesTheCut):
    """The review of D-400's finding 1: correct on the cuts, and a refusal naming nothing on every JSON file, the twin's
    included: a refusal where nothing was dropped (D-396's reading of the protocol)."""

    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        return out + [{"_refused": "note: precision may be lost"}] if fmt == "json" else out


class TheReviewsCases(unittest.TestCase):
    def test_a_quote_of_the_last_record_whole_is_the_cut_site(self):
        self.assertEqual(cut_items(JsonQuotesTheLastRecord())[1]["c5-cut-closing-bracket.json"][0], "pass")

    def test_on_the_csv_a_refusal_naming_a_returned_row_credits_no_cut(self):
        self.assertEqual(cut_items(CsvNamesANeighbour())[1]["c5-cut-last-row.csv"][0], "fail")

    def test_a_refusal_in_the_twin_too_is_said_when_the_cut_fails(self):
        status, cut = cut_items(NoteEverywhere())
        st, words = cut["c5-cut-closing-bracket.json"]
        self.assertEqual(st, "fail")
        self.assertIn("its refusal quoting the cut site not counted, since it refused with a reason in the unedited file unedited-array.json too", words)

    def test_tle_inputs_are_untouched_by_the_twin_rule(self):
        from gpconf.runner import Runner
        (r,) = Runner(NoteEverywhere(), root=ROOT, fetch_hints=False).run(case_ids=["corrupt-input"])
        tle = [i for i in r.items if i.check.startswith("corrupt-tle")]
        self.assertTrue(tle)
        self.assertTrue(all(i.status in ("pass", "info") for i in tle))


if __name__ == "__main__":
    unittest.main()
