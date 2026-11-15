# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The blind review of the 0.8.0 candidate (D-369; a fresh session with the wheel only, the owner's ruling of
2026-10-27): the grader findings fixed in 0.8.0, each with a wrong-on-purpose input or adapter and its twin.

- check-tle --against passed a file that lost or repeated source records, with exit 0 (finding 1); the secondary
  fields stayed information (D-095) until D-387.
- a decoder that read only the first two characters of an Alpha-5 field passed alpha5-encoding-vectors (finding 4,
  the Alpha-5 part; the catalog-id and epoch vectors are 0.8.1's).
- a command whose JSON began with a byte-order mark, and a parser returning a TLE name as its 24-column line, failed
  where they were right (finding 8).
- a parser's message printed raw could forge a report line and move the terminal's cursor (finding 7), and a writer
  that changed a secondary field passed with no word of it outside -v (finding 2, its note; the verdict is 0.8.1's).

The files are the corpus's own derived files and vectors (no provider's bytes, so the module runs in the public
export). Run: python -m unittest tests.adversarial.test_blind_review_080"""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf import writer as W  # noqa: E402
from gpconf.__main__ import main as gpconf_main  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import CommandParser, Runner, compare_value  # noqa: E402
from tests.raw_needed import needs_raw  # noqa: E402

ISS_RAW = os.path.join("fixtures", "baseline-iss-five-formats", "raw")   # withheld from the export (D-408)

CI = os.path.join(ROOT, "derived", "corrupt-input")
SETS, ROWS = os.path.join(CI, "unedited-sets.tle"), os.path.join(CI, "unedited-rows.csv")


def items(parser, case):
    return Runner(parser, root=ROOT, fetch_hints=False).run(case_ids=[case])[0]


def check_tle(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = gpconf_main(["check-tle", *argv])
    return code, out.getvalue()


class CheckTleAgainstTheSource(unittest.TestCase):
    """Finding 1: every source record written, none more often than the source holds it."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        with open(SETS, encoding="utf-8") as f:
            self.lines = f.read().splitlines()
        self.assertEqual(len(self.lines), 9)   # three named sets: the file the case's unedited records come from

    def write(self, name, lines):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return path

    def test_a_file_that_lost_records_fails(self):
        code, out = check_tle(self.write("one.tle", self.lines[:3]), "--against", ROWS)
        self.assertEqual(code, 1, out)
        self.assertIn("[fail] 2 source records no file wrote: 20453, 69999", out)
        self.assertIn("1 record: 1 passes, 0 fail; against the source, 2 failures", out)

    def test_a_record_written_twice_fails(self):
        code, out = check_tle(self.write("twice.tle", self.lines + self.lines[6:9]), "--against", ROWS)
        self.assertEqual(code, 1, out)
        self.assertIn("[fail] 1 id written more often than the source holds: 20453 written 2, held 1", out)
        self.assertNotIn("[pass] every source record", out)   # the reading's mutant M3

    def test_the_records_split_over_two_files_pass(self):
        """The twin: the source's three records, in two files, each once."""
        code, out = check_tle(self.write("a.tle", self.lines[:6]), self.write("b.tle", self.lines[6:]), "--against", ROWS)
        self.assertEqual(code, 0, out)
        self.assertIn("[pass] every source record written, none more often than the source holds it", out)

    def test_the_whole_file_passes_and_the_json_says_so(self):
        js = os.path.join(self.tmp, "out.json")
        code, out = check_tle(SETS, "--against", ROWS, "--json", js)
        self.assertEqual(code, 0, out)
        with open(js, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["source"], {"not_compared": [], "not_written": [], "refusal_correct": [], "written_more": []})

    def test_a_changed_secondary_field_fails(self):
        """The first derivative's sign changed (checksum recomputed): reported, not failed, under D-095; from D-387 (the
        owner's ruling extending D-381 to check-tle) another value than the source's fails the record."""
        from gpconf import tle as T
        l1 = self.lines[1]
        self.assertEqual(l1[33], "-", l1)   # ISS's first derivative is negative in this set
        l1 = l1[:33] + " " + l1[34:68]
        l1 += str(T.checksum(l1))
        code, out = check_tle(self.write("ndot.tle", [self.lines[0], l1] + self.lines[2:]), "--against", ROWS)
        self.assertEqual(code, 1, out)
        self.assertIn("side field mean_motion_dot written as another value", out)

    def test_a_lost_copy_of_an_id_the_source_holds_twice_fails(self):
        """The reading of D-369, finding 1: a history source holding ISS at two epochs, a file writing one of them."""
        from gpconf import tle as T
        l1 = self.lines[1].replace(" 98324.28472222 ", " 98325.28472222 ")
        l1 = l1[:68] + str(T.checksum(l1[:68]))
        src = self.write("history.tle", self.lines + [self.lines[0], l1, self.lines[2]])
        self.assertEqual(W.load_against(src).held, {25544: 2, 69999: 1, 20453: 1})   # the reading's mutant W2
        code, out = check_tle(self.write("one-iss.tle", self.lines), "--against", src)
        self.assertEqual(code, 1, out)
        self.assertIn("[fail] 1 source record no file wrote: 25544 (1 of 2 written)", out)
        self.assertIn("paired by its epoch with copy 1 of 2 in the source", out)   # compared now (D-403)

    def test_a_history_written_whole_passes_each_copy_paired_by_its_epoch(self):
        """The owner's ruling on D-369's reading: no false fail on a history source. In 0.8.0 the ids it held more
        than once were not compared, and the run exited 3 (D-370); per-epoch pairing compares each (D-403)."""
        from gpconf import tle as T
        l1 = self.lines[1].replace(" 98324.28472222 ", " 98325.28472222 ")
        l1 = l1[:68] + str(T.checksum(l1[:68]))
        history = self.lines + [self.lines[0], l1, self.lines[2]]
        src = self.write("history.tle", history)
        js = os.path.join(self.tmp, "h.json")
        code, out = check_tle(self.write("written.tle", history), "--against", src, "--json", js)
        # the correct file passes: each ISS record paired with the copy whose epoch it writes (D-403; before, both read
        # [not compared] and the run exited 3, D-370)
        self.assertEqual(code, 0, out)
        self.assertIn("paired by its epoch with copy 1 of 2 in the source", out)
        self.assertIn("paired by its epoch with copy 2 of 2 in the source", out)
        self.assertIn("4 records: 4 pass, 0 fail", out)
        with open(js, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["source"]["not_compared"], [])
        # its twin: an id the source holds once is still compared, and a wrong value there still fails the round trip
        # (DELTA's mean motion, line 2 columns 53 to 63, one digit changed, the checksum recomputed: the reading's N16)
        bad = list(history)
        self.assertTrue(bad[8].startswith("2 20453 "), bad[8])
        bad[8] = bad[8][:60] + ("0" if bad[8][60] != "0" else "1") + bad[8][61:68]
        bad[8] += str(T.checksum(bad[8]))
        code, out = check_tle(self.write("bad.tle", bad), "--against", src)
        self.assertEqual(code, 1, out)
        self.assertIn("round trip: mean_motion", out)

    def test_a_history_with_wrong_values_in_one_copy_fails_and_one_copy_written_twice_is_one_lost(self):
        """D-403's own cases: per-epoch pairing compares, so a wrong copy fails; a copy written twice is one copy, and
        the other is not written; a record at an epoch the source holds no copy at fails."""
        from gpconf import tle as T
        l1 = self.lines[1].replace(" 98324.28472222 ", " 98325.28472222 ")
        l1 = l1[:68] + str(T.checksum(l1[:68]))
        second = [self.lines[0], l1, self.lines[2]]
        src = self.write("history.tle", self.lines + second)
        wrong = list(second)
        wrong[2] = wrong[2][:60] + ("0" if wrong[2][60] != "0" else "1") + wrong[2][61:68]
        wrong[2] += str(T.checksum(wrong[2]))
        code, out = check_tle(self.write("w1.tle", self.lines + wrong), "--against", src)
        self.assertEqual(code, 1, out)
        self.assertIn("round trip: mean_motion", out)
        code, out = check_tle(self.write("w2.tle", self.lines + self.lines[:3]), "--against", src)
        self.assertEqual(code, 1, out)
        self.assertIn("[fail] 1 source record no file wrote: 25544 (1 of 2 written)", out)
        l1x = self.lines[1].replace(" 98324.28472222 ", " 98326.28472222 ")
        l1x = l1x[:68] + str(T.checksum(l1x[:68]))
        code, out = check_tle(self.write("w3.tle", self.lines + [self.lines[0], l1x, self.lines[2]]), "--against", src)
        self.assertEqual(code, 1, out)
        self.assertIn("no source copy of 25544 has the epoch written ('98326.28472222')", out)

    def test_a_source_holding_the_same_set_twice_written_twice_passes(self):
        """The review of D-403's finding 1: two identical copies, each written once, are both written (a first-match
        pairing put both records on the first copy and failed the second as not written)."""
        src = self.write("twice.tle", self.lines + self.lines[:3])
        code, out = check_tle(self.write("twice-w.tle", self.lines + self.lines[:3]), "--against", src)
        self.assertEqual(code, 0, out)
        self.assertNotIn("no file wrote", out)

    @needs_raw(ISS_RAW)
    def test_a_copy_without_an_epoch_is_a_candidate_for_every_record(self):
        """The review of D-403's finding 3: a source copy with no epoch is compared as the same copy held once is."""
        import json as _json
        with open(os.path.join(ROOT, "fixtures", "baseline-iss-five-formats", "raw", "iss.json"), encoding="utf-8") as f:
            rec = _json.load(f)[0]
        bare = dict(rec)
        bare.pop("EPOCH")
        src = os.path.join(self.tmp, "noepoch.json")
        with open(src, "w", encoding="utf-8") as f:
            _json.dump([rec, bare], f)
        with open(os.path.join(ROOT, "fixtures", "baseline-iss-five-formats", "raw", "iss.tle"), encoding="utf-8") as f:
            iss = f.read().splitlines()
        code, out = check_tle(self.write("iss-twice.tle", iss + iss), "--against", src)
        self.assertNotIn("no source copy of 25544 has the epoch written", out)

    def test_a_history_id_written_by_no_file_is_lost_twice_and_not_listed_as_not_compared(self):
        """The re-reading's N11, N12 and N19: an id the source holds twice, written by no file."""
        from gpconf import tle as T
        l1 = self.lines[1].replace(" 98324.28472222 ", " 98325.28472222 ")
        l1 = l1[:68] + str(T.checksum(l1[:68]))
        src = self.write("history.tle", self.lines + [self.lines[0], l1, self.lines[2]])
        js = os.path.join(self.tmp, "z.json")
        code, out = check_tle(self.write("no-iss.tle", self.lines[3:]), "--against", src, "--json", js)
        self.assertEqual(code, 1, out)
        self.assertIn("[fail] 2 source records no file wrote: 25544 (0 of 2 written)", out)
        with open(js, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["source"]["not_compared"], [])

    @unittest.skipIf(sys.platform == "win32", "Windows forbids control characters in file names (D-374)")
    def test_the_paths_are_printed_escaped(self):
        """The re-reading's N13 and N14: a file name and an --against name holding a terminal escape."""
        code, out = check_tle(self.write("e\x1bx.tle", self.lines), "--against", shutil.copy(ROWS, os.path.join(self.tmp, "s\x1by.csv")))
        self.assertEqual(code, 0, out)
        self.assertNotIn("\x1b", out)
        self.assertIn("e\\x1bx.tle: 3 records", out)
        self.assertIn("round trip against " + os.path.join(self.tmp, "s\\x1by.csv"), out)

    def test_a_number_written_in_six_digits_is_written_not_lost(self):
        """The reading of D-369, finding 2: the record fails on its own; the id is not reported as written by no file."""
        wide = self.lines[1].replace("1 25544U", "1 100000U", 1)
        r = W.check_record(None, wide, self.lines[2])
        self.assertEqual((r["status"], r["norad_cat_id"], r["written_id"]), ("fail", None, 100000))
        against = W.Against({100000: {}, 340000: {}})
        against.held = {100000: 1, 340000: 1}
        cov = W.source_coverage([r, {"norad_cat_id": None, "written_id": 340000}], against)
        self.assertEqual(cov, {"not_compared": [], "not_written": [], "refusal_correct": [], "written_more": []})

    def test_a_source_row_without_a_catalog_number_is_noted_and_crashes_nothing(self):
        """The reading's mutant W1: a CSV row whose NORAD_CAT_ID is empty."""
        with open(ROWS, encoding="utf-8") as f:
            rows = f.read().splitlines()
        head = rows[0].split(",")
        i = head.index("NORAD_CAT_ID")
        cells = rows[1].split(",")
        cells[i] = ""
        src = self.write("no-id.csv", [rows[0], ",".join(cells)] + rows[2:])
        code, out = check_tle(SETS, "--against", src)
        self.assertIn("note: 1 source record without a catalog number, which no written record can be held to", out)
        self.assertNotIn("Traceback", out)

    def test_a_number_the_format_cannot_carry_left_unwritten_is_noted(self):
        """The reading's mutant M4: a source holding 340000, the file writing the other records."""
        with open(ROWS, encoding="utf-8") as f:
            rows = f.read().splitlines()
        i = rows[0].split(",").index("NORAD_CAT_ID")
        lines = [rows[0]]
        for row in rows[1:]:
            cells = row.split(",")
            if cells[i] == "69999":
                cells[i] = "340000"
            lines.append(",".join(cells))
        src = self.write("wide.csv", lines)
        code, out = check_tle(self.write("two.tle", self.lines[:3] + self.lines[6:]), "--against", src)
        self.assertEqual(code, 0, out)
        self.assertIn("note: 1 id the TLE format cannot carry, written by no file, as a refusal should be: ids 340000", out)

    def test_a_long_list_of_ids_is_cut_with_a_count(self):
        """The reading's mutant M12."""
        from gpconf.__main__ import ids_shown
        self.assertEqual(ids_shown(list(range(25))), ", ".join(map(str, range(20))) + ", and 5 more")

    def test_a_name_line_with_control_characters_is_printed_escaped(self):
        """The reading's mutants M7 to M10: a name line a tool wrote, carrying a terminal escape and a C1 character (not
        U+0085, which Python reads as a line break, so that the name line would end there)."""
        code, out = check_tle(self.write("esc.tle", [self.lines[0] + "\x1b[2K\x9f"] + self.lines[1:]))
        self.assertNotIn("\x1b", out)
        self.assertNotIn("\x9f", out)
        self.assertIn("ISS (ZARYA)             \\x1b[2K\\x9f | catalog field '25544'", out)

    def test_an_id_the_source_holds_twice_may_be_written_twice(self):
        against = W.Against({25544: {}})
        against.held = {25544: 2}
        cov = W.source_coverage([{"norad_cat_id": 25544}, {"norad_cat_id": 25544}], against)
        self.assertEqual(cov, {"not_compared": [], "not_written": [], "refusal_correct": [], "written_more": []})   # D-403
        one = W.source_coverage([{"norad_cat_id": 25544, "matches_copies": [1]}] * 2, against)
        self.assertEqual(one["not_written"], [(25544, 1, 2)])   # one copy written twice: the other is not written
        same = W.source_coverage([{"norad_cat_id": 25544, "matches_copies": [1, 2]}] * 2, against)
        self.assertEqual(same["not_written"], [])   # two copies alike, each written once (the review of D-403's 1)
        near = W.source_coverage([{"norad_cat_id": 25544, "matches_copies": [1]}, {"norad_cat_id": 25544, "matches_copies": [1, 2]}], against)
        self.assertEqual(near["not_written"], [])   # one record fits both copies, the other only one (its 2)
        cov = W.source_coverage([{"norad_cat_id": 25544}] * 3, against)
        self.assertEqual(cov["written_more"], [(25544, 3, 2)])

    def test_an_id_the_format_cannot_carry_is_no_failure_when_not_written(self):
        against = W.Against({25544: {}, 340000: {}})
        against.held = {25544: 1, 340000: 1}
        cov = W.source_coverage([{"norad_cat_id": 25544}], against)
        self.assertEqual(cov, {"not_compared": [], "not_written": [], "refusal_correct": [340000], "written_more": []})


class FirstTwoCharacters(Reference):
    """Finding 4: an Alpha-5 decoder that checks only the field's first two characters and reads the rest as digits,
    anything else as 0 (A12B4 -> 101204)."""

    def alpha5_decode(self, field):
        if len(field) != 5 or field[0] in "IO" or not field[0].isupper() and not field[0].isdigit() or not field[1].isdigit():
            raise ValueError(field)
        if field[0].isdigit():
            return int(field)
        letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
        return (letters.index(field[0]) + 10) * 10000 + int("".join(c if c.isdigit() else "0" for c in field[1:]))


class Alpha5WholeField(unittest.TestCase):

    def test_a_decoder_reading_two_characters_fails_naming_each_field(self):
        (got,) = [i for i in items(FirstTwoCharacters(), "alpha5-encoding-vectors").items if i.check == "alpha5-decode"]
        self.assertEqual(got.status, "fail", got.detail)
        for shown in ("'A12B4' accepted as 101204", "'A1-34' accepted as 101034", "'A12.4' accepted as 101204", "'A1 34' accepted as 101034"):
            self.assertIn(shown, got.detail)

    def test_the_reference_rejects_every_one(self):
        """The twin."""
        (got,) = [i for i in items(Reference(), "alpha5-encoding-vectors").items if i.check == "alpha5-decode"]
        self.assertEqual(got.status, "pass", got.detail)

    def test_the_vectors_hold_the_whole_field_cases(self):
        with open(os.path.join(ROOT, "vectors", "alpha5.json"), encoding="utf-8") as f:
            fields = [v["field"] for v in json.load(f)["decode_invalid"]]
        for f in ("A12B4", "A1-34", "A12.4", "A1 34", "1234A"):
            self.assertIn(f, fields)


COMMAND = textwrap.dedent("""
    import json, sys, os
    sys.path.insert(0, {root!r})
    from gpconf.adapters.reference import Parser
    from gpconf.runner import Unsupported
    try:
        recs = Parser().parse(sys.stdin.buffer.read(), sys.argv[1])
    except Unsupported:
        sys.exit(3)
    body = json.dumps(recs, default=str)
    mode = os.environ["MODE"]
    sys.stdout.buffer.write({{"bom": b"\\xef\\xbb\\xbf", "banner": b"loaded lib v1.2\\n", "plain": b""}}[mode] + body.encode())
""")


@unittest.skipIf(sys.platform == "win32", "a POSIX command line")
class CommandOutput(unittest.TestCase):
    """Finding 8: a byte-order mark before the command's JSON is no part of it; a banner line still is."""

    def run_mode(self, mode):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        script = os.path.join(tmp, "cmd.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(COMMAND.format(root=ROOT))
        env = dict(os.environ, MODE=mode)
        return items(CommandParser(cmd=f"{sys.executable} {script} {{fmt}}", env=env), "alpha5-tle-derived")

    def test_a_byte_order_mark_is_read_past(self):
        self.assertEqual(self.run_mode("bom").status, "pass")

    def test_a_banner_line_still_fails(self):
        """The twin: text that is not JSON is still no answer."""
        got = self.run_mode("banner")
        self.assertEqual(got.status, "fail")
        self.assertTrue(any("stdout is not JSON" in (i.detail or "") for i in got.items))

    def script(self, body):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        path = os.path.join(tmp, "cmd.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(body).format(root=ROOT))
        return f"{sys.executable} {path}"

    def test_a_byte_order_mark_before_written_lines_is_read_past(self):
        """The reading's mutant R14: --write-cmd."""
        cmd = self.script("""
            import json, sys
            sys.path.insert(0, {root!r})
            from gpconf.adapters.reference import Parser
            out = Parser().write_tle(json.loads(sys.stdin.read()))
            text = "\\n".join(out) + "\\n" if isinstance(out, (tuple, list)) else out
            sys.stdout.buffer.write(b"\\xef\\xbb\\xbf" + text.encode())
        """)
        with open(os.path.join(ROOT, "fixtures", "tle-writer-alpha5", "expected.json"), encoding="utf-8") as f:
            record = json.load(f)["records"][0]["canonical"]
        text = CommandParser(cmd=None, write_cmd=cmd).write_tle(record)   # one call: the case makes 762 (D-399)
        self.assertFalse(text.startswith("\ufeff"), repr(text[:3]))
        self.assertEqual(W.check_file(text)[0]["status"], "pass")

    def test_a_byte_order_mark_before_a_vectors_answer_is_read_past(self):
        """The reading's mutant R15: --vectors-cmd."""
        cmd = self.script("""
            import json, sys
            sys.path.insert(0, {root!r})
            from gpconf.adapters.reference import Parser
            q = json.loads(sys.stdin.read())
            try:
                body = {{"result": getattr(Parser(), q["op"])(q["input"])}}
            except Exception as e:
                body = {{"error": str(e)}}
            sys.stdout.buffer.write(b"\\xef\\xbb\\xbf" + json.dumps(body, default=str).encode())
            sys.exit(1 if "error" in body else 0)
        """)
        p = CommandParser(cmd=None, vectors_cmd=cmd)
        self.assertEqual(p.alpha5_decode("A0000"), 100000)   # two calls: the case makes 172
        with self.assertRaises(ValueError):
            p.alpha5_decode("A12B4")

    def test_the_byte_order_mark_is_taken_off_once(self):
        self.assertEqual(subprocess.run([sys.executable, "-c", "import sys; sys.stdout.buffer.write(b'\\xef\\xbb\\xbf[]')"],
                                        capture_output=True).stdout.decode("utf-8-sig"), "[]")


class Padded(Reference):
    """Finding 8: the name as its 24-column TLE line, padded with blanks, as CelesTrak writes it."""

    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        for r in out:
            if isinstance(r.get("object_name"), str):
                r["object_name"] = r["object_name"].ljust(24)
        return out


class Renamed(Reference):
    """The twin: another name, padded the same way, still fails."""

    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        for r in out:
            if isinstance(r.get("object_name"), str):
                r["object_name"] = (r["object_name"] + " X").ljust(24)
        return out


class PaddedName(unittest.TestCase):

    def test_a_name_padded_to_24_columns_passes(self):
        got = items(Padded(), "alpha5-tle-derived")
        self.assertEqual(got.status, "pass", [i.detail for i in got.items if i.status == "fail"])

    def test_another_name_still_fails(self):
        got = items(Renamed(), "alpha5-tle-derived")
        self.assertEqual(got.status, "fail")
        self.assertTrue(any("object_name" in (i.detail or "") for i in got.items if i.status == "fail"))

    def test_unknown_padded_to_24_columns_is_unknown(self):
        """The reading of D-369, finding 3: object-name-unknown-literal on the analyst files (provider data)."""
        if not os.path.exists(os.path.join(ROOT, "fixtures", "analyst-objects", "raw", "analyst.tle")):
            self.skipTest("provider files absent (public clone)")
        got = items(Padded(), "analyst-objects")
        unk = [i for i in got.items if i.check == "object-name-unknown-literal"]
        self.assertTrue(unk)
        self.assertEqual([i.detail for i in unk if i.status != "pass"], [])

    def test_only_trailing_blanks_and_only_text(self):
        from gpconf.plain import Written
        self.assertEqual(compare_value("object_name", "ISS (ZARYA)    ", "ISS (ZARYA)")[0], "exact")
        self.assertEqual(compare_value("object_name", "  ISS (ZARYA)", "ISS (ZARYA)")[0], "mismatch")   # leading blanks are the name's
        self.assertEqual(compare_value("object_name", "ISS\t", "ISS")[0], "mismatch")                    # only blanks pad a line
        self.assertEqual(compare_value("object_id", "1998-067A  ", "1998-067A")[0], "mismatch")           # the name alone
        self.assertEqual(compare_value("object_name", Written("[1] ", "list"), "[1]")[0], "mismatch")    # the runner's own type


class Forge(Reference):
    """Finding 7: a parser whose error message carries a forged summary line and terminal escapes."""

    def parse(self, raw, fmt):
        raise ValueError("boom\n18 cases: 18 pass (exact), 0 pass within tolerance, 0 fail\n\x1b[2A\x1b[2K")


class Plain(Reference):
    """The twin: an ordinary message, printed as it is."""

    def parse(self, raw, fmt):
        raise ValueError("boom: no reader for this format")


class PrintedText(unittest.TestCase):

    def run_main(self, adapter):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = gpconf_main(["run", "--adapter", f"tests.adversarial.test_blind_review_080:{adapter}", "--case", "alpha5-tle-derived",
                                "--no-fetch-hint", "--root", ROOT])
        return code, out.getvalue()

    def test_a_forged_line_and_escapes_are_shown_escaped(self):
        code, out = self.run_main("Forge")
        self.assertEqual(code, 1)
        self.assertNotIn("\x1b", out)
        self.assertFalse([l for l in out.splitlines() if l.startswith("18 cases: 18 pass")], out)
        self.assertIn("boom\\n18 cases: 18 pass (exact), 0 pass within tolerance, 0 fail\\n\\x1b[2A\\x1b[2K", out)

    def test_an_ordinary_message_is_printed_as_it_is(self):
        code, out = self.run_main("Plain")
        self.assertEqual(code, 1)
        self.assertIn("boom: no reader for this format", out)


class PrintableText(unittest.TestCase):
    """The reading's mutants P1 to P4, and its point on line separators and bidirectional controls."""

    def test_each_hidden_character_is_escaped(self):
        from gpconf.words import printable
        self.assertEqual(printable("a\x7fb\x85c\x9fd"), "a\\x7fb\\x85c\\x9fd")
        self.assertEqual(printable("boom\u202818 cases: 18 pass"), "boom\\u202818 cases: 18 pass")
        self.assertEqual(len(printable("x\u2029y").splitlines()), 1)
        self.assertEqual(printable("a\u202eb\u2066c\u2069d\u202ae"), "a\\u202eb\\u2066c\\u2069d\\u202ae")   # both ends of both ranges (N9)
        self.assertEqual(printable("SARAMAGO ✓ é"), "SARAMAGO ✓ é")   # printable text as it is


class NdotAbs(Reference):
    """Finding 2: a writer that writes the first derivative's magnitude, dropping its sign."""

    def write_tle(self, record):
        from decimal import Decimal
        r = dict(record)
        r["mean_motion_dot"] = str(abs(Decimal(str(r.get("mean_motion_dot") or 0))))
        return super().write_tle(r)


class NoName(Reference):
    """The reading's mutant R10: a writer that writes two lines, no name line."""

    def write_tle(self, record):
        out = super().write_tle(record)
        return "\n".join(list(out)[-2:] if isinstance(out, (tuple, list)) else out.splitlines()[-2:]) + "\n"


class ZeroNdot(Reference):
    """The reading's mutant R11: a writer that zeroes the first derivative."""

    def write_tle(self, record):
        return super().write_tle(dict(record, mean_motion_dot="0"))


class SecondaryFieldsSaid(unittest.TestCase):

    def test_a_dropped_name_and_a_zeroed_derivative_are_said(self):
        self.assertEqual(items(NoName(), "tle-writer-alpha5").status_text(), "pass (1 secondary field not kept)")
        self.assertEqual(items(ZeroNdot(), "tle-writer-alpha5").status_text(), "pass (1 secondary field not kept)")


    def test_a_changed_secondary_field_fails(self):
        # the fields were information (D-095) and this writer passed, its case saying so; from D-381 and D-383 a side
        # field written as another value, here MEAN_MOTION_DOT with its sign dropped, fails the case
        got = items(NdotAbs(), "tle-writer-alpha5")
        self.assertEqual(got.status, "fail")
        (it,) = [i for i in got.items if i.check == "tle-writer-secondary-not-changed"]
        self.assertEqual(it.status, "fail")
        self.assertIn("mean_motion_dot", it.detail)

    def test_the_reference_says_nothing_more(self):
        """The twin: a name cut to the line's 24 columns is kept as the format allows."""
        got = items(Reference(), "tle-writer-alpha5")
        self.assertEqual(got.status_text(), "pass")


if __name__ == "__main__":
    unittest.main()
