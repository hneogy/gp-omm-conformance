"""The corrupt-input case (D-171): its inputs, the rules that grade what a parser does with them, and the control.

Each input is a frozen real record with one stated edit between valid records. A corrupt record must come back
refused with a reason and the valid ones loaded; a parser that validates no checksum is reported on input 1, not
failed (owner decision 2); a whole-file refusal of a file cut mid-record passes, the complete records it gives up
counted (owner decision 3). What a parser returns from an input is compared with what the same parser returns from
the input's unedited file, the same records with no edit (D-175), so a parser that reads these records imprecisely
everywhere is not failed for it here: the values check grades that in the records' own cases."""
import difflib
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from gpconf import reference as ref  # noqa: E402
from gpconf import tle as T  # noqa: E402
from gpconf.runner import Runner, Unsupported  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402
from tests.adapters.naive import Parser as Naive  # noqa: E402

CASE = "corrupt-input"
D = os.path.join(ROOT, "derived", "corrupt-input")
FILES = ["c1-checksum-digit.tle", "c2-line-2-short.tle", "c3-letter-in-epoch.tle", "c4-line-2-missing.tle",
         "c5-cut-last-row.csv", "c5-cut-closing-bracket.json"]
UNEDITED = ["unedited-sets.tle", "unedited-rows.csv", "unedited-array.json"]


def read(path):
    with open(path, "rb") as f:
        return f.read()


EXPECTED = json.loads(read(os.path.join(ROOT, "fixtures", CASE, "expected.json")))


def run(parser):
    return Runner(parser, root=ROOT).run(case_ids=[CASE])[0]


def items(result, name):
    """{(check, status)} of the items for one file."""
    return {(i.check, i.status) for i in result.items if i.file and i.file.endswith(name) and i.check != "refusals"}


def item(result, name, check):
    return next(i for i in result.items if i.file and i.file.endswith(name) and i.check == check)


def text(name):
    return read(os.path.join(D, name)).decode("utf-8")


class Inputs(unittest.TestCase):
    def test_every_file_matches_its_provenance_record(self):
        import hashlib
        for name in FILES + UNEDITED:
            with self.subTest(name):
                raw = read(os.path.join(D, name))
                prov = json.loads(read(os.path.join(D, name.rsplit(".", 1)[0] + ".provenance.json")))
                self.assertEqual(prov["provenance"], "derived" if name in UNEDITED else "synthetic-derived")
                self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (prov["bytes"], prov["output_sha256"]))
                self.assertEqual(EXPECTED["sources"][f"derived/corrupt-input/{name}"]["sha256"], prov["output_sha256"])

    def test_the_tool_rebuilds_the_same_bytes_from_the_public_expected_values(self):
        # derive_corrupt_inputs.py reads only fixtures/*/expected.json, so a public clone rebuilds the files exactly
        import contextlib
        import io
        import derive_corrupt_inputs as tool
        with tempfile.TemporaryDirectory() as tmp:
            out, tool.OUT = tool.OUT, tmp
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    tool.main()
            finally:
                tool.OUT = out
            for name in FILES + UNEDITED:
                with self.subTest(name):
                    self.assertEqual(read(os.path.join(tmp, name)), read(os.path.join(D, name)))

    def clean_tle(self):
        """The three sets as the corpus renders them, with no edit."""
        sets = []
        for case, s, cat in (("epoch-year-19xx", "iss-first", 25544), ("bstar-and-derivative-forms", "gp-69999-first", 69999),
                             ("bstar-and-derivative-forms", "decaying", 20453)):
            e = json.loads(read(os.path.join(ROOT, "fixtures", case, "expected.json")))
            r = next(x for x in e["records"] if x.get("set") == s and x["norad_cat_id"] == cat)
            sets += list(T.render(T.omm_fields_from_record(r["canonical"]), mantissa_mode="round", ecc_mode="truncate"))
        return sets

    def test_each_tle_input_is_one_stated_edit_of_the_clean_rendering(self):
        clean = self.clean_tle()
        for name, want in (("c1-checksum-digit.tle", ("replace", 4, 1)), ("c2-line-2-short.tle", ("replace", 5, 1)),
                           ("c3-letter-in-epoch.tle", ("replace", 4, 1)), ("c4-line-2-missing.tle", ("delete", 5, 1))):
            with self.subTest(name):
                lines = text(name).split("\r\n")[:-1]
                ops = [op for op in difflib.SequenceMatcher(a=clean, b=lines, autojunk=False).get_opcodes() if op[0] != "equal"]
                self.assertEqual(len(ops), 1, ops)
                tag, i1, i2 = ops[0][:3]
                self.assertEqual((tag, i1, i2 - i1), want)
        c1 = text("c1-checksum-digit.tle").split("\r\n")[4]
        self.assertEqual((len(c1), c1[:68], c1[68]), (69, clean[4][:68], "1"))
        self.assertNotEqual(T.checksum(c1), int(c1[68]))                      # input 1: the checksum no longer holds
        c2 = text("c2-line-2-short.tle").split("\r\n")[5]
        self.assertEqual((len(c2), c2), (68, clean[5][:29] + clean[5][30:]))   # input 2: column 30 lost, the rest moved left
        c3 = text("c3-letter-in-epoch.tle").split("\r\n")[4]
        self.assertEqual([(k, a, b) for k, (a, b) in enumerate(zip(clean[4], c3)) if a != b], [(25, "0", "O")])
        self.assertEqual(T.checksum(c3), int(c3[68]))                          # input 3: the checksum still holds

    def test_each_input_is_its_unedited_file_with_its_one_edit(self):
        # D-175: the comparison is only fair if the unedited file differs from each input by the input's edit alone
        self.assertEqual(text("unedited-sets.tle"), "\r\n".join(self.clean_tle()) + "\r\n")  # inputs 1 to 4: see the test above
        rows, cut = text("unedited-rows.csv"), text("c5-cut-last-row.csv")
        self.assertTrue(rows.startswith(cut) and rows.endswith("\r\n") and len(rows) > len(cut))
        self.assertEqual(rows[len(cut):], "23," + rows.split("\r\n")[-2].rsplit(",", 1)[1] + "\r\n")  # the cut: the value's last two digits and the row's last field
        self.assertEqual(text("unedited-array.json"), text("c5-cut-closing-bracket.json") + "]\r\n")
        by = {u: v["for_inputs"] for u, v in EXPECTED["case_specific"]["unedited"].items()}
        self.assertEqual(by, {"derived/corrupt-input/unedited-sets.tle": [1, 2, 3, 4], "derived/corrupt-input/unedited-rows.csv": [5],
                              "derived/corrupt-input/unedited-array.json": [5]})
        self.assertEqual({n: f["unedited"].rsplit("/", 1)[1] for n, f in EXPECTED["case_specific"]["files"].items()},
                         dict(zip(FILES, ["unedited-sets.tle"] * 4 + ["unedited-rows.csv", "unedited-array.json"])))

    def test_the_cut_files(self):
        csv_text = text("c5-cut-last-row.csv")
        self.assertFalse(csv_text.endswith("\r\n"))
        rows = csv_text.split("\r\n")
        self.assertEqual((len(rows), len(rows[0].split(",")), [len(r.split(",")) for r in rows[1:]]), (4, 17, [17, 17, 16]))
        self.assertTrue(rows[-1].endswith(",-0.000000"))
        json_text = text("c5-cut-closing-bracket.json")
        self.assertTrue(json_text.startswith("[{") and json_text.endswith("}"))
        self.assertEqual(json.loads(json_text + "]")[2]["NORAD_CAT_ID"], 69999)  # the bracket is all that is missing

    def test_the_expected_values_are_those_of_the_record_without_the_edit(self):
        by = {(r["file"], r["norad_cat_id"]): r for r in EXPECTED["records"]}
        self.assertEqual(len(EXPECTED["records"]), 18)
        corrupt = by[("c3-letter-in-epoch.tle", 69999)]
        self.assertEqual((corrupt["role"], corrupt["expected"]["epoch"]), ("corrupt", "2026-07-08T17:02:16.167840"))
        self.assertEqual(by[("c1-checksum-digit.tle", 69999)]["if_read_as_unedited"], "report")
        self.assertEqual({by[(f, 69999)]["if_read_as_unedited"] for f in FILES[1:5]}, {"fail"})
        self.assertEqual(by[("c5-cut-last-row.csv", 69999)]["expected"]["mean_motion_dot"], "-0.00000023")
        self.assertEqual({r["role"] for r in EXPECTED["records"] if r["file"] == "c5-cut-closing-bracket.json"}, {"valid"})


class Control(unittest.TestCase):
    """The reference adapter reads TLE sets one at a time and refuses a set its strict reader rejects, so the sets
    around it still load; its reader refuses a CSV row cut short and a JSON array left open, the file as a whole."""

    @classmethod
    def setUpClass(cls):
        cls.r = run(Reference())

    def test_it_passes(self):
        self.assertEqual(self.r.status, "pass", [(i.check, i.status, i.detail) for i in self.r.items if i.status == "fail"])

    def test_each_file(self):
        want = {
            "c1-checksum-digit.tle": {("corrupt-tle-checksum-digit", "info"), ("corrupt-input-neighbours-load", "pass")},
            "c2-line-2-short.tle": {("corrupt-tle-line-short", "pass"), ("corrupt-input-neighbours-load", "pass")},
            "c3-letter-in-epoch.tle": {("corrupt-tle-letter-in-number", "pass"), ("corrupt-input-neighbours-load", "pass")},
            "c4-line-2-missing.tle": {("corrupt-tle-missing-line-2", "pass"), ("corrupt-input-neighbours-load", "pass")},
            "c5-cut-last-row.csv": {("corrupt-file-cut", "pass"), ("corrupt-input-neighbours-load", "info")},
            "c5-cut-closing-bracket.json": {("corrupt-file-cut", "pass"), ("corrupt-input-neighbours-load", "info")},
        }
        for name, w in want.items():
            with self.subTest(name):
                self.assertEqual(items(self.r, name), w)
        self.assertIn("validates no checksum", item(self.r, "c1-checksum-digit.tle", "corrupt-tle-checksum-digit").detail)
        self.assertIn("line length 69/68", item(self.r, "c2-line-2-short.tle", "corrupt-tle-line-short").detail)
        self.assertIn("epoch field '26189.7O990935' is not a number", item(self.r, "c3-letter-in-epoch.tle", "corrupt-tle-letter-in-number").detail)
        self.assertIn("no line 2", item(self.r, "c4-line-2-missing.tle", "corrupt-tle-missing-line-2").detail)
        self.assertIn("2 complete record(s) given up", item(self.r, "c5-cut-last-row.csv", "corrupt-input-neighbours-load").detail)

    def test_the_counts_use_the_existing_vocabulary(self):
        c = item(self.r, "c2-line-2-short.tle", "corrupt-tle-line-short").counts
        self.assertEqual({k: c[k] for k in ("expected", "returned", "loaded", "misidentified", "refused", "refused_matched", "dropped")},
                         {"expected": 3, "returned": 2, "loaded": 2, "misidentified": 0, "refused": 1, "refused_matched": 1, "dropped": 0})
        c = item(self.r, "c5-cut-last-row.csv", "corrupt-file-cut").counts
        self.assertEqual((c["loaded"], c["refused"], c["refused_matched"], c["dropped"]), (0, 3, 3, 0))
        self.assertIn("CSV data row 3 has 16 fields", c["top_refusal_reason"])

    def test_a_valid_tle_file_reads_exactly_as_the_reader_reads_it(self):
        raw = read(os.path.join(ROOT, "derived", "alpha5-tle", "alpha5-A-last-30-days-snapshot.tle"))
        got = Reference().parse(raw, "tle")
        self.assertFalse([r for r in got if "_refused" in r])
        self.assertEqual([r["norad_cat_id"] for r in got], [r["norad_cat_id"] for r in ref.read_tle_text(raw.decode())])

    def test_an_orphan_line_2_is_refused_too(self):
        lines = text("c1-checksum-digit.tle").split("\r\n")
        got = Reference().parse("\r\n".join(lines[:3] + [lines[5]] + lines[6:]).encode(), "tle")
        refusals = [r for r in got if "_refused" in r]
        self.assertEqual([(r["_refused"], r["_field"]) for r in refusals], [("a line 2 with no line 1 before it", "69999")])
        self.assertEqual([r["norad_cat_id"] for r in got if "_refused" not in r], [25544, 20453])


class Demonstration(unittest.TestCase):
    """The naive adapter, the corpus's own demonstration of failure."""

    def test_it_fails_where_it_should(self):
        r = run(Naive())
        self.assertEqual(r.status, "fail")
        self.assertEqual(items(r, "c1-checksum-digit.tle"), {("corrupt-tle-checksum-digit", "info"), ("corrupt-input-neighbours-load", "pass")})
        self.assertEqual(items(r, "c2-line-2-short.tle"), {("corrupt-tle-line-short", "fail"), ("corrupt-input-neighbours-load", "pass")})
        self.assertIn("built a record from the corrupt input", item(r, "c2-line-2-short.tle", "corrupt-tle-line-short").detail)
        self.assertEqual(items(r, "c3-letter-in-epoch.tle"), {("corrupt-tle-letter-in-number", "pass"), ("corrupt-input-neighbours-load", "fail")})
        self.assertEqual(items(r, "c4-line-2-missing.tle"), {("corrupt-tle-missing-line-2", "fail"), ("corrupt-input-neighbours-load", "pass")})
        self.assertIn("refusals not reported by this adapter", item(r, "c4-line-2-missing.tle", "corrupt-tle-missing-line-2").detail)
        self.assertIn("given up", item(r, "c3-letter-in-epoch.tle", "corrupt-input-neighbours-load").detail)


class Rules(unittest.TestCase):
    """Parsers written to show each rule, over the reference adapter's own reading."""

    class Lenient(Reference):
        """The reference readers without their strictness: TLE lines read at fixed columns whatever their length and
        whatever is in them, a CSV row read as far as it goes, a JSON array read without its closing bracket."""
        declare = True

        def parse(self, raw, fmt):
            from gpconf.runner import CORE_FIELDS, OPTIONAL_FIELDS
            text = raw.decode()
            out = [{"_adapter": {"refusals": True}}] if self.declare else []
            recs = []
            if fmt == "tle":
                lines = text.splitlines()
                for i, l in enumerate(lines):
                    if l.startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
                        # a C-style number reader: the epoch stops at the letter and the rest of the field reads as 0
                        l1 = l[:18] + l[18:32].split("O")[0].ljust(14, "0") + l[32:]
                        recs.append(ref.parse_tle_lines(lines[i - 1], l1, lines[i + 1].ljust(69)))
            elif fmt == "json":
                recs, _ = ref.read_json_text(text if text.rstrip().endswith("]") else text + "]")
            else:
                raise Unsupported(fmt)
            return out + [{k: r.get(k) for k in CORE_FIELDS + OPTIONAL_FIELDS if r.get(k) is not None or k in CORE_FIELDS} for r in recs]

    def test_a_record_built_from_garbage_is_misidentified(self):
        r = run(self.Lenient())
        it = item(r, "c3-letter-in-epoch.tle", "corrupt-tle-letter-in-number")
        self.assertEqual(it.status, "fail")
        self.assertIn("built a record from the corrupt input: epoch", it.detail)
        self.assertEqual((it.counts["misidentified"], it.counts["loaded"]), (1, 2))

    def test_a_short_line_read_at_fixed_columns_is_garbage(self):
        # the lost digit moves every column after it one to the left: the eccentricity, the mean anomaly, the mean
        # motion and the revolution number are all read from the wrong characters
        it = item(run(self.Lenient()), "c2-line-2-short.tle", "corrupt-tle-line-short")
        self.assertEqual(it.status, "fail")
        self.assertIn("built a record from the corrupt input", it.detail)
        for wrong in ("mean_motion = Decimal('1.623733631')", "eccentricity = Decimal('0.148004')", "mean_anomaly = Decimal('45.3718')"):
            self.assertIn(wrong, it.detail)
        self.assertEqual(it.counts["misidentified"], 1)

    def test_silent_partial_loading_of_a_cut_file_fails(self):
        it = item(run(self.Lenient()), "c5-cut-closing-bracket.json", "corrupt-file-cut")
        self.assertEqual(it.status, "fail")
        self.assertIn("silent partial loading", it.detail)

    def test_a_cut_reported_with_a_reason_passes(self):
        class Reports(self.Lenient):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                return out + [{"_refused": "JSON array not closed"}] if fmt == "json" else out
        it = item(run(Reports()), "c5-cut-closing-bracket.json", "corrupt-file-cut")
        self.assertEqual(it.status, "pass")
        self.assertIn("JSON array not closed", it.detail)

    def test_a_silent_drop_and_a_reasonless_refusal_fail(self):
        class Drops(Reference):
            def parse(self, raw, fmt):
                got = [r for r in super().parse(raw, fmt) if "_refused" not in r]
                return [{"_adapter": {"refusals": True}}] + got

        class NoReason(Reference):
            def parse(self, raw, fmt):
                return [{**r, "_refused": ""} if "_refused" in r else r for r in super().parse(raw, fmt)]
        self.assertIn("dropped silently", item(run(Drops()), "c4-line-2-missing.tle", "corrupt-tle-missing-line-2").detail)
        it = item(run(NoReason()), "c4-line-2-missing.tle", "corrupt-tle-missing-line-2")
        self.assertEqual(it.status, "fail")
        self.assertIn("without a reason", it.detail)

    def test_a_refusal_that_names_no_record_stands_for_the_corrupt_one(self):
        class Unnamed(Reference):
            def parse(self, raw, fmt):
                return [{"_refused": r["_refused"]} if "_refused" in r else r for r in super().parse(raw, fmt)]
        it = item(run(Unnamed()), "c3-letter-in-epoch.tle", "corrupt-tle-letter-in-number")
        self.assertEqual(it.status, "pass")
        self.assertEqual((it.counts["refused"], it.counts["refused_matched"]), (1, 1))

    def test_a_whole_tle_file_refused_gives_up_the_neighbours(self):
        class Strict(Reference):
            def parse(self, raw, fmt):
                if fmt == "tle":
                    return ref.read_tle_text(raw.decode())  # raises on the first bad set: the file as a whole
                return super().parse(raw, fmt)
        r = run(Strict())
        self.assertEqual(items(r, "c3-letter-in-epoch.tle"), {("corrupt-tle-letter-in-number", "pass"), ("corrupt-input-neighbours-load", "fail")})
        self.assertIn("2 valid set(s) around the corrupt one were given up", item(r, "c3-letter-in-epoch.tle", "corrupt-input-neighbours-load").detail)


class Comparison(unittest.TestCase):
    """D-175: every record a parser returns from an input is compared with the same parser's reading of the unedited
    file, exactly. The case first compared with the frozen expected values, as the values check does, and so failed a
    parser that reads these records imprecisely in every file, whatever it did with the corrupt input (PyEphem 4.2.1,
    D-174: seven fields in single precision, no second derivative)."""

    class Imprecise(Reference):
        """The reference readers with PyEphem's precision: seven fields rounded to single precision, no second
        derivative. The values check fails it on every TLE record; the corrupt input changes nothing it reads."""
        SINGLE = ("inclination", "ra_of_asc_node", "eccentricity", "arg_of_pericenter", "mean_anomaly", "bstar", "mean_motion_dot")

        def parse(self, raw, fmt):
            import struct
            out = []
            for r in super().parse(raw, fmt):
                if "_refused" not in r:
                    r = {k: (struct.unpack("f", struct.pack("f", float(v)))[0] if k in self.SINGLE and v is not None else v)
                         for k, v in r.items() if k != "mean_motion_ddot"}
                out.append(r)
            return out

    def test_a_parser_that_reads_the_records_imprecisely_is_not_failed_for_it_here(self):
        from gpconf.runner import compare_value
        parser = self.Imprecise()
        iss = next(r for r in parser.parse(read(os.path.join(D, "unedited-sets.tle")), "tle") if r["norad_cat_id"] == 25544)
        want = next(r for r in EXPECTED["records"] if r["file"] == "c1-checksum-digit.tle" and r["norad_cat_id"] == 25544)["expected"]
        self.assertEqual(compare_value("inclination", iss["inclination"], want["inclination"], "float")[0], "mismatch")  # the values check fails it
        self.assertNotIn("mean_motion_ddot", iss)
        r, control = run(parser), run(Reference())
        self.assertEqual(r.status, "pass")
        self.assertEqual([(i.check, i.status, i.file) for i in r.items], [(i.check, i.status, i.file) for i in control.items])
        for name in FILES[:4]:
            with self.subTest(name):
                self.assertIn("exactly as the parser reads it from the unedited file", item(r, name, "corrupt-input-neighbours-load").detail)

    def test_a_neighbour_the_corrupt_input_changes_fails(self):
        from decimal import Decimal

        class Leaky(Reference):
            """State carried over from a refused set into the next one: a parser that does not pick up cleanly."""
            def parse(self, raw, fmt):
                out, after = [], False
                for r in super().parse(raw, fmt):
                    if "_refused" in r:
                        after = True
                    elif after:
                        r, after = {**r, "inclination": str(Decimal(r["inclination"]) + Decimal("0.0001"))}, False
                    out.append(r)
                return out
        r = run(Leaky())
        it = item(r, "c3-letter-in-epoch.tle", "corrupt-input-neighbours-load")
        self.assertEqual(it.status, "fail")
        self.assertIn("1 of 2 valid set(s) around the corrupt one loaded as the parser reads them from the unedited file", it.detail)
        self.assertIn("20453 changed by the corrupt input (inclination = Decimal('35.5935'), from the unedited file Decimal('35.5934'))", it.detail)
        self.assertEqual(item(r, "c1-checksum-digit.tle", "corrupt-input-neighbours-load").status, "pass")  # nothing refused there
        self.assertEqual(item(r, "c3-letter-in-epoch.tle", "corrupt-tle-letter-in-number").counts["misidentified"], 1)

    def test_a_parser_that_refuses_the_unedited_file_too_is_not_exercised(self):
        class NoTle(Reference):
            def parse(self, raw, fmt):
                if fmt == "tle":
                    raise ValueError("cannot read this file")
                return super().parse(raw, fmt)
        r = run(NoTle())
        for name in FILES[:4]:
            with self.subTest(name):
                self.assertEqual({s for _, s in items(r, name)}, {"not-exercised"})
                self.assertIn("unedited-sets.tle cannot serve as one (the parser refused it as a whole (ValueError: cannot read this file))", item(r, name, "corrupt-input-neighbours-load").detail)
        self.assertEqual(items(r, "c5-cut-last-row.csv"), {("corrupt-file-cut", "pass"), ("corrupt-input-neighbours-load", "info")})

    def test_a_record_the_parser_does_not_return_unedited_is_not_graded(self):
        class No69999(Reference):
            def parse(self, raw, fmt):
                return [r for r in super().parse(raw, fmt) if r.get("norad_cat_id") != 69999 and r.get("_field") != "69999"]
        r = run(No69999())
        it = item(r, "c3-letter-in-epoch.tle", "corrupt-tle-letter-in-number")
        self.assertEqual(it.status, "not-exercised")
        self.assertIn("does not return 69999 from the unedited file unedited-sets.tle either", it.detail)
        self.assertEqual(item(r, "c3-letter-in-epoch.tle", "corrupt-input-neighbours-load").status, "pass")
        it = item(r, "c5-cut-closing-bracket.json", "corrupt-input-neighbours-load")
        self.assertIn("2 complete record(s) given up with the file", it.detail)
        self.assertIn("not graded: 69999, which the parser does not return from the unedited file either", it.detail)

    def test_a_record_the_parser_returns_from_the_unedited_file_too_is_not_blamed_on_the_edit(self):
        class Phantom(Reference):
            """Returns one record no file holds, whatever it reads: not the edit's doing."""
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                return out + [{**next(x for x in out if "_refused" not in x), "norad_cat_id": 99999}] if fmt == "tle" else out
        r = run(Phantom())
        self.assertEqual(r.status, "pass", [(i.check, i.status, i.detail) for i in r.items if i.status == "fail"])
        self.assertEqual(item(r, "c2-line-2-short.tle", "corrupt-tle-line-short").counts["misidentified"], 0)


class ReaderHardening(unittest.TestCase):
    """D-117's rule carried to two more inputs (D-171): a letter in a numeric TLE column and a CSV row cut short are
    clear errors from the reference readers, never a wrong record or an internal error."""

    L0 = "VANGUARD DEB"
    L1 = "1 69999U 58002D   26189.70990935 -.00000023  00000+0 -70517-5 0  9996"
    L2 = "2 69999  34.2417 341.8745 1487004  19.9191 345.3718 11.62373363189308"

    def test_a_letter_in_a_numeric_tle_column_is_a_value_error_naming_the_field(self):
        for line, col, what in ((1, 25, "epoch"), (2, 58, "mean motion"), (2, 28, "eccentricity"), (1, 55, "BSTAR"), (1, 37, "first derivative")):
            with self.subTest(what):
                l1, l2 = self.L1, self.L2
                if line == 1:
                    l1 = l1[:col] + "O" + l1[col + 1:]
                else:
                    l2 = l2[:col] + "O" + l2[col + 1:]
                with self.assertRaises(ValueError) as cm:
                    ref.parse_tle_lines(self.L0, l1, l2)
                self.assertIn(f"TLE {what} field", str(cm.exception))

    def test_a_csv_row_with_the_wrong_number_of_fields_is_rejected(self):
        header = ",".join(ref.CELESTRAK_CSV_JSON_KEYS)
        row = "X,2026-001A,2026-01-01T00:00:00.000000,15.5,0.001,51.6,0,0,0,0,U,25544,999,1,0,0,0"
        self.assertEqual(len(ref.read_csv_text(f"{header}\r\n{row}\r\n")[0]), 1)
        for bad, n in ((row.rsplit(",", 1)[0], 16), (row + ",7", 18)):
            with self.subTest(n):
                with self.assertRaises(ValueError) as cm:
                    ref.read_csv_text(f"{header}\r\n{row}\r\n{bad}")
                self.assertIn(f"CSV data row 2 has {n} fields and the header 17", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
