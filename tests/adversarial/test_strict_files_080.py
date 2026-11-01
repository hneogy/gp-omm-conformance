# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The reference reader reads a file as strictly as the runner reads a parser's answer (D-336), with its wrong-on-purpose
parsers and twins (CLAUDE.md, "Grader changes").

The reference reader is the oracle: it made the frozen expected values, and on live bytes the runner compares a parser
with it directly. It read a file's numbers with Decimal() and int(), which take underscores between digits, the digits
of other scripts, Unicode spaces, NaN and Infinity, and it split TLE and KVN files at every line break Python knows.
Measured on the committed reader (e9f6666) with the inputs below: a KVN MEAN_MOTION with a Unicode line separator or a
form feed inside it read as 16.05, the digits before it; a TLE element set number ' 1_0' read as 10; a TLE set with a
form feed inside line 1 was passed over, no record and no error; NaN in CSV, JSON or XML and INF in XML were read as
values; '16.050_64833', the same digits in Arabic-Indic script and the value with a no-break space after it read as
16.05064833. A parser that reads numbers the same way agreed with the oracle on such a file, and passed it.

Now the reader rejects each such file in words naming the field, and on live bytes the runner fails the file as
"reference reader rejected the file". The twins: each format's own padding (a TLE column's blanks, XML whitespace
around a number, the blanks and tabs around a KVN value) and every number form a parser may return still read as
before, and every file the corpus reads still reads.

The records are written here from the frozen values of a public expected.json (the 1998 ISS record), so no provider
file is needed. Run: python -m unittest tests.adversarial.test_strict_files_080"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf import reference as ref  # noqa: E402
from gpconf import tle as tlemod  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import Runner  # noqa: E402

OTHER_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")   # Arabic-Indic
FULLWIDTH = str.maketrans("0123456789", "０１２３４５６７８９")
BACK_TO_ASCII = {ord(c): str(i) for t in ("٠١٢٣٤٥٦٧٨٩",
                                          "０１２３４５６７８９") for i, c in enumerate(t)}

with open(os.path.join(ROOT, "fixtures", "epoch-year-19xx", "expected.json"), encoding="utf-8") as _f:
    R = json.load(_f)["records"][0]["canonical"]   # ISS (ZARYA), 1998-11-20, frozen
FIELDS = tlemod.omm_fields_from_record(R)          # OMM keyword -> text, as a provider writes it
MM = FIELDS["MEAN_MOTION"]                          # '16.05064833'
CSV_COLUMNS = ["OBJECT_NAME", "OBJECT_ID", "EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE",
               "ARG_OF_PERICENTER", "MEAN_ANOMALY", "EPHEMERIS_TYPE", "CLASSIFICATION_TYPE", "NORAD_CAT_ID",
               "ELEMENT_SET_NO", "REV_AT_EPOCH", "BSTAR", "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT"]   # CelesTrak's order
TEXT = {"OBJECT_NAME", "OBJECT_ID", "EPOCH", "CLASSIFICATION_TYPE"}
META = [("OBJECT_NAME", "metadata"), ("OBJECT_ID", "metadata"), ("CENTER_NAME", "metadata"), ("REF_FRAME", "metadata"),
        ("TIME_SYSTEM", "metadata"), ("MEAN_ELEMENT_THEORY", "metadata")]
MEAN = ["EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY"]
TLEP = ["EPHEMERIS_TYPE", "CLASSIFICATION_TYPE", "NORAD_CAT_ID", "ELEMENT_SET_NO", "REV_AT_EPOCH", "BSTAR",
        "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT"]
CONSTANT = {"CENTER_NAME": "EARTH", "REF_FRAME": "TEME", "TIME_SYSTEM": "UTC", "MEAN_ELEMENT_THEORY": "SGP4"}


def values(**change):
    v = dict(FIELDS, **CONSTANT)
    v.update(change)
    return v


def csv_text(**change):
    v = values(**change)
    return ",".join(CSV_COLUMNS) + "\r\n" + ",".join(v[k] for k in CSV_COLUMNS) + "\r\n"


def json_text(raw=None, **change):
    """JSON numbers written as the text given; raw maps a key to the JSON token itself (NaN, a string, true)."""
    v = values(**change)
    raw = raw or {}
    parts = []
    for k in CSV_COLUMNS:
        token = raw.get(k, json.dumps(v[k]) if k in TEXT else v[k])
        parts.append(f'"{k}": {token}')
    return "[{" + ", ".join(parts) + "}]"


def xml_text(**change):
    v = values(**change)
    meta = "".join(f"<{k}>{v[k]}</{k}>" for k, _ in META)
    mean = "".join(f"<{k}>{v[k]}</{k}>" for k in MEAN)
    tlep = "".join(f"<{k}>{v[k]}</{k}>" for k in TLEP)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<ndm><omm id="CCSDS_OMM_VERS" version="2.0"><header>'
            "<CREATION_DATE/><ORIGINATOR/></header><body><segment>"
            f"<metadata>{meta}</metadata><data><meanElements>{mean}</meanElements>"
            f"<tleParameters>{tlep}</tleParameters></data></segment></body></omm></ndm>\n")


def kvn_text(eol="\n", around=" ", **change):
    v = values(**change)
    keys = ["OBJECT_NAME", "OBJECT_ID", "CENTER_NAME", "REF_FRAME", "TIME_SYSTEM", "MEAN_ELEMENT_THEORY"] + MEAN + TLEP
    lines = ["CCSDS_OMM_VERS = 2.0", "CREATION_DATE = ", "ORIGINATOR = "] + [f"{k}{around}={around}{v[k]}" for k in keys]
    return eol.join(lines) + eol


LINES = tlemod.render(FIELDS, mantissa_mode="round", ecc_mode="truncate")   # (line0, line1, line2), the corpus's writer


def tle_text(l1=None, l2=None, eol="\n"):
    """The ISS set with line 1 or 2 replaced and its check digit written again, as a careless writer would."""
    l1 = l1 if l1 is not None else LINES[1]
    l2 = l2 if l2 is not None else LINES[2]
    fix = lambda line: line[:68] + str(tlemod.checksum(line))   # noqa: E731
    return eol.join([LINES[0].rstrip(), fix(l1), fix(l2)]) + eol


def column(line, start, end, text):
    assert len(text) == end - start, (text, end - start)
    return line[:start] + text + line[end:]


def one(reader, text):
    recs, *_ = reader(text) if reader is not ref.read_tle_text else (reader(text),)
    return recs


class AFileOutsideTheParserRuleIsRejectedNamingTheField(unittest.TestCase):
    """Each of these the committed reader read as a number (or as no record, or as the wrong number)."""

    def rejects(self, reader, text, *words):
        with self.assertRaises(ValueError) as cm:
            reader(text)
        for w in words:
            self.assertIn(w, str(cm.exception))
        return str(cm.exception)

    def test_csv(self):
        for name, mm in (("underscore", "16.050_64833"), ("Arabic-Indic", MM.translate(OTHER_DIGITS)),
                         ("fullwidth", MM.translate(FULLWIDTH)), ("NaN", "NaN"), ("Infinity", "Infinity"),
                         ("a space before", " " + MM), ("a no-break space after", MM + " ")):
            with self.subTest(mean_motion=name):
                self.rejects(ref.read_csv_text, csv_text(MEAN_MOTION=mm), "MEAN_MOTION")
        for name, cat in (("underscore", "25_544"), ("Arabic-Indic", "25544".translate(OTHER_DIGITS)), ("a space", " 25544")):
            with self.subTest(norad_cat_id=name):
                self.rejects(ref.read_csv_text, csv_text(NORAD_CAT_ID=cat), "NORAD_CAT_ID")
        with self.subTest(element_set_no="a space"):
            self.rejects(ref.read_csv_text, csv_text(ELEMENT_SET_NO=" 1"), "ELEMENT_SET_NO")
        for name, ep in (("a space before", " " + FIELDS["EPOCH"]), ("Arabic-Indic", FIELDS["EPOCH"].translate(OTHER_DIGITS))):
            with self.subTest(epoch=name):
                self.rejects(ref.read_csv_text, csv_text(EPOCH=ep), "EPOCH")

    def test_json(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=token):
                self.rejects(ref.read_json_text, json_text(raw={"MEAN_MOTION": token}), token, "not a JSON number")
        for name, token in (("a padded string", json.dumps(" " + MM)), ("an underscore", json.dumps("16.050_64833")),
                            ("other digits", json.dumps(MM.translate(OTHER_DIGITS)))):
            with self.subTest(mean_motion=name):
                self.rejects(ref.read_json_text, json_text(raw={"MEAN_MOTION": token}), "MEAN_MOTION")
        with self.subTest(norad_cat_id="true"):
            self.rejects(ref.read_json_text, json_text(raw={"NORAD_CAT_ID": "true"}), "NORAD_CAT_ID")
        with self.subTest(epoch="padded"):
            self.rejects(ref.read_json_text, json_text(raw={"EPOCH": json.dumps(FIELDS["EPOCH"] + " ")}), "EPOCH")

    def test_xml(self):
        for name, mm in (("NaN", "NaN"), ("INF", "INF"), ("-INF", "-INF"), ("underscore", "16.050_64833"),
                         ("a no-break space", " " + MM), ("Arabic-Indic", MM.translate(OTHER_DIGITS))):
            with self.subTest(mean_motion=name):
                self.rejects(ref.read_xml_text, xml_text(MEAN_MOTION=mm), "MEAN_MOTION")
        with self.subTest(epoch="whitespace around it, which an xsd:string pattern keeps"):
            self.rejects(ref.read_xml_text, xml_text(EPOCH="\n  " + FIELDS["EPOCH"] + "\n"), "EPOCH", "whitespace")

    def test_kvn(self):
        for name, ch in (("a Unicode line separator", " "), ("a paragraph separator", " "), ("a form feed", "\x0c"),
                         ("a vertical tab", "\x0b"), ("NEL", "\x85"), ("a file separator", "\x1c")):
            with self.subTest(inside_mean_motion=name):
                # the committed reader split the line there and read MEAN_MOTION as 16.05
                self.rejects(ref.read_kvn_text, kvn_text(MEAN_MOTION=MM[:5] + ch + MM[5:]), "MEAN_MOTION")
        for name, mm in (("a no-break space after", MM + " "), ("an em space before", " " + MM),
                         ("underscore", "16.050_64833"), ("NaN", "NaN")):
            with self.subTest(mean_motion=name):
                self.rejects(ref.read_kvn_text, kvn_text(MEAN_MOTION=mm), "MEAN_MOTION")

    def test_tle(self):
        l1, l2 = LINES[1], LINES[2]
        cases = [
            ("inclination", "an underscore", None, column(l2, 8, 16, "51.5_908")),
            ("inclination", "Arabic-Indic digits", None, column(l2, 8, 16, l2[8:16].translate(OTHER_DIGITS))),
            ("inclination", "a no-break space", None, column(l2, 8, 16, " " + l2[9:16])),
            ("mean motion", "fullwidth digits", None, column(l2, 52, 63, l2[52:63].translate(FULLWIDTH))),
            ("element set number", "' 1_0', read as 10", column(l1, 64, 68, " 1_0"), None),
            ("revolution number", "an underscore", None, column(l2, 63, 68, "1_000")),
            ("ephemeris type", "a no-break space, read as 0", column(l1, 62, 63, " "), None),
            ("eccentricity", "a blank in the seven digits", None, column(l2, 26, 33, l2[27:33] + " ")),
            ("epoch", "a blank at the end", column(l1, 18, 32, l1[18:31] + " "), None),
            ("epoch", "Arabic-Indic digits in the day", column(l1, 18, 32, l1[18:20] + l1[20:32].translate(OTHER_DIGITS)), None),
            ("BSTAR", "a no-break space", column(l1, 53, 61, " " + l1[54:61]), None),
            ("second derivative", "an underscore", column(l1, 44, 52, " 1_563-4"), None),
        ]
        for what, how, a, b in cases:
            with self.subTest(field=what, how=how):
                self.rejects(ref.read_tle_text, tle_text(a, b), f"TLE {what} field", "is not a number")

    def test_a_tle_line_with_a_form_feed_inside_is_no_longer_passed_over(self):
        text = tle_text()
        broken = text.replace(LINES[1][:30], LINES[1][:30] + "\x0c", 1)
        self.rejects(ref.read_tle_text, broken, "TLE epoch field")   # the committed reader returned no record and no error
        # (named in its field since D-338, where D-336 said "line length"); and in line 2, in its field too
        self.rejects(ref.read_tle_text, text.replace(LINES[2][:30], LINES[2][:30] + "\x0c", 1), "TLE eccentricity field")


class TheFormatsOwnPaddingAndEveryNumberFormStillRead(unittest.TestCase):
    """The twins: what the formats allow and what a parser may return reads as it did."""

    WANT = {k: R[k] for k in ("norad_cat_id", "mean_motion", "eccentricity", "inclination", "ra_of_asc_node",
                              "arg_of_pericenter", "mean_anomaly", "bstar", "mean_motion_dot", "mean_motion_ddot",
                              "element_set_no", "rev_at_epoch", "ephemeris_type")}

    def same(self, rec, want=None):
        self.assertEqual({k: rec[k] for k in self.WANT}, want or self.WANT)

    def test_each_format_written_plainly_reads_the_frozen_values(self):
        for name, reader, text in (("csv", ref.read_csv_text, csv_text()), ("json", ref.read_json_text, json_text()),
                                   ("xml", ref.read_xml_text, xml_text()), ("kvn", ref.read_kvn_text, kvn_text())):
            with self.subTest(fmt=name):
                rec = reader(text)[0][0]
                self.same(rec)
                self.assertEqual(rec["epoch"], FIELDS["EPOCH"])
        self.same(ref.read_tle_text(tle_text())[0])

    def test_a_tle_columns_blanks_are_its_padding(self):
        rec = ref.read_tle_text(tle_text())[0]
        self.assertEqual(LINES[2][8:16], " 51.5908")       # a leading blank in the column
        self.assertEqual(LINES[1][64:68], "   1")          # the element set number right-aligned
        self.assertEqual(LINES[2][63:68], "    0")         # the revolution number right-aligned
        self.assertEqual((rec["inclination"], rec["element_set_no"], rec["rev_at_epoch"]), ("51.5908", 1, 0))
        blank_ephemeris = ref.read_tle_text(tle_text(column(LINES[1], 62, 63, " ")))[0]
        self.assertEqual(blank_ephemeris["ephemeris_type"], 0)   # a blank ephemeris type is 0, as it was

    def test_xml_whitespace_around_a_number_is_its_padding(self):
        for pad in ("\n  ", "\t", " \r\n "):
            with self.subTest(pad=pad):
                rec = ref.read_xml_text(xml_text(MEAN_MOTION=pad + MM + pad, NORAD_CAT_ID=pad + "25544" + pad))[0][0]
                self.assertEqual((rec["mean_motion"], rec["norad_cat_id"]), (R["mean_motion"], 25544))

    def test_kvn_blanks_and_tabs_around_a_value_and_its_units(self):
        for around in ("", "   ", "\t", " \t "):
            with self.subTest(around=around):
                self.same(ref.read_kvn_text(kvn_text(around=around))[0][0])
        rec = ref.read_kvn_text(kvn_text(MEAN_MOTION=MM + " [rev/day]   "))[0][0]
        self.assertEqual(rec["mean_motion"], R["mean_motion"])
        self.assertEqual(rec["kvn"]["units"], {"MEAN_MOTION": "rev/day"})

    def test_cr_lf_and_crlf_line_ends_read_the_same(self):
        for eol in ("\n", "\r\n", "\r"):
            with self.subTest(eol=repr(eol)):
                self.same(ref.read_kvn_text(kvn_text(eol=eol))[0][0])
                self.same(ref.read_tle_text(tle_text(eol=eol))[0])
        self.same(ref.read_kvn_text(kvn_text(eol="\n\r"))[0][0])   # KVN's LFCR: an empty line between, which means nothing

    def test_every_number_form_a_parser_may_return_reads(self):
        for mm in ("16.05064833", "+16.05064833", "1.605064833E1", "1605064833e-8", "16.0506483300"):
            with self.subTest(mean_motion=mm):
                self.assertEqual(ref.read_csv_text(csv_text(MEAN_MOTION=mm))[0][0]["mean_motion"], R["mean_motion"])
        for bstar, want in ((".15975118E-3", "0.00015975118"), ("-.11606E-4", "-0.000011606"), ("0", "0"), ("16.", "16"), (".5", "0.5")):
            with self.subTest(bstar=bstar):
                self.assertEqual(ref.read_csv_text(csv_text(BSTAR=bstar))[0][0]["bstar"], want)
        self.assertEqual(ref.read_json_text(json_text(raw={"MEAN_MOTION": json.dumps(MM)}))[0][0]["mean_motion"], R["mean_motion"])
        self.assertIsNone(ref.read_csv_text(csv_text(BSTAR=""))[0][0]["bstar"])   # an empty CSV value is no value, as before


class EveryFileTheCorpusReadsStillReads(unittest.TestCase):
    """Every OMM and TLE file the manifest lists that is on disk (in a clone without provider data, the corpus's own
    derived files) reads under the strict reader, with the record count the manifest records. The frozen values
    themselves were checked when the change was made: every expected.json written again from a fresh reading is equal
    to the committed one but for its generation time (D-336)."""

    def test_all_files_on_disk(self):
        with open(os.path.join(ROOT, "manifest.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        read = 0
        for case in manifest["cases"]:
            for src in case["sources"]:
                path = os.path.join(ROOT, src["path"])
                if src.get("format") not in ("tle", "2le", "csv", "json", "xml", "kvn") or not os.path.exists(path):
                    continue
                if src.get("http_status") not in (None, 200):   # a derived file has none; a provider's recorded refusal is not data
                    continue
                if case["id"] == "corrupt-input" and not os.path.basename(src["path"]).startswith("unedited"):
                    continue   # the edited inputs are corrupt on purpose; the unedited comparison files are valid

                with self.subTest(path=src["path"]):
                    with open(path, "rb") as fh:
                        body = fh.read().strip()
                    if body in (b"No GP data found", b"No SupGP data found"):
                        continue
                    _, recs, _ = ref.read_file(path)
                    if isinstance(src.get("record_count"), int):
                        self.assertEqual(len(recs), src["record_count"])
                    read += 1
        self.assertGreater(read, 0)


class Generous(Reference):
    """A wrong parser: it reads a number the way Decimal(), int() and float() do, so another script's digits and an
    underscore between digits become the number they spell, and it splits a file at every line break Python knows."""

    def parse(self, raw, fmt):
        text = re.sub(r"(?<=[0-9])_(?=[0-9])", "", raw.decode("utf-8").translate(BACK_TO_ASCII))
        if fmt == "kvn":
            text = "\n".join(text.splitlines()) + "\n"
        return super().parse(text.encode("utf-8"), fmt)


LIVE = os.path.join("fixtures", "baseline-iss-five-formats", "raw")


class ALiveFileOnlyAGenerousReaderCanReadFailsForEveryParser(unittest.TestCase):
    """On a user's bytes the oracle is the reference reader (live mode). A wrong parser that reads what the format does
    not carry agreed with the committed reader, so the file passed; now the reader rejects the file and the runner fails
    it, for every parser, in words naming the field. Twins: the same parser, and the reference, on the same file
    written plainly, have no failure on it."""

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-strict-files-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def items_for(self, parser, name, text):
        os.makedirs(os.path.join(self.data, LIVE), exist_ok=True)
        with open(os.path.join(self.data, LIVE, name), "w", encoding="utf-8", newline="") as f:
            f.write(text)
        res = Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["baseline-iss-five-formats"])[0]
        path = os.path.join(LIVE, name).replace(os.sep, "/")
        mine = [i for i in res.items if (i.file or "").replace(os.sep, "/").endswith(path)]
        self.assertTrue(mine, [(i.check, i.file) for i in res.items][:5])
        return mine

    def assert_rejected(self, items, field):
        fails = [i for i in items if i.status == "fail"]
        self.assertTrue(any(i.check == "reference-reader" and "reference reader rejected the file" in i.detail and field in i.detail
                            for i in fails), [(i.check, i.status, i.detail[:120]) for i in items])
        self.assertFalse([i for i in items if i.status in ("pass", "pass-tolerance")], "nothing on a file the oracle cannot read passes")

    def assert_clean(self, items):
        self.assertEqual([(i.check, i.detail[:120]) for i in items if i.status == "fail"], [])

    def test_a_csv_with_another_scripts_digits(self):
        bad = csv_text(MEAN_MOTION=MM.translate(OTHER_DIGITS))
        self.assert_rejected(self.items_for(Generous(), "iss.csv", bad), "MEAN_MOTION")
        self.assert_rejected(self.items_for(Reference(), "iss.csv", bad), "MEAN_MOTION")   # no parser passes it
        self.assert_clean(self.items_for(Generous(), "iss.csv", csv_text()))               # twin: written plainly
        self.assert_clean(self.items_for(Reference(), "iss.csv", csv_text()))

    def test_a_kvn_value_with_a_line_separator_inside(self):
        bad = kvn_text(MEAN_MOTION=MM[:5] + " " + MM[5:])   # the committed reader and this parser both read 16.05
        self.assert_rejected(self.items_for(Generous(), "iss.kvn", bad), "MEAN_MOTION")
        self.assert_clean(self.items_for(Generous(), "iss.kvn", kvn_text()))

    def test_a_tle_with_an_underscore_in_the_element_set_number(self):
        bad = tle_text(column(LINES[1], 64, 68, " 1_0"))       # the committed reader and this parser both read 10
        self.assert_rejected(self.items_for(Generous(), "iss.tle", bad), "element set number")
        self.assert_clean(self.items_for(Generous(), "iss.tle", tle_text()))



class TheReviewersFirstReading(unittest.TestCase):
    """The separate reviewer's reading of D-336's first form (2026-10-15), under the owner's model: a wrong value the
    reader lets through is an escape. Each route with its twin; every frozen expected value is still unchanged."""

    def rejects(self, reader, text, *words):
        with self.assertRaises(ValueError) as cm:
            reader(text)
        for w in words:
            self.assertIn(w, str(cm.exception))

    def test_a_kvn_line_with_a_unicode_character_before_its_keyword_is_refused_not_dropped(self):
        """Finding 1: with ASCII-only blanks, such a line no longer matched KEYWORD = value and was dropped silently."""
        base = kvn_text()
        for name, bad in (("a no-break space", "\u00a0MEAN_MOTION"), ("a file separator", "\x1cMEAN_MOTION"),
                          ("NEL", "\x85MEAN_MOTION")):
            with self.subTest(before=name):
                self.rejects(ref.read_kvn_text, base.replace("MEAN_MOTION", bad, 1), "MEAN_MOTION", "printable ASCII")
        self.rejects(ref.read_kvn_text, base.replace("CCSDS_OMM_VERS", "\u2003CCSDS_OMM_VERS", 1), "CCSDS_OMM_VERS")
        for before in (" ", "\t", "   "):                                        # twin: ASCII blanks before a keyword
            with self.subTest(twin=repr(before)):
                self.assertEqual(ref.read_kvn_text(base.replace("MEAN_MOTION", before + "MEAN_MOTION", 1))[0][0]["mean_motion"],
                                 R["mean_motion"])

    def test_a_kvn_value_broken_by_a_line_end_is_refused(self):
        """Finding 2: CR and LF are KVN's own line ends, so 16.05<CR>064833 read as 16.05, the rest set aside."""
        for eol in ("\r", "\n", "\r\n"):
            with self.subTest(eol=repr(eol)):
                self.rejects(ref.read_kvn_text, kvn_text(MEAN_MOTION=MM[:5] + eol + MM[5:]), "neither a COMMENT nor KEYWORD = value")
        self.rejects(ref.read_kvn_text, kvn_text(NORAD_CAT_ID="255\r\n44"), "neither a COMMENT nor KEYWORD = value")
        text = kvn_text().replace("MEAN_MOTION", "COMMENT a note\n\nMEAN_MOTION", 1)     # twin: comments, blank lines
        self.assertEqual(ref.read_kvn_text(text)[0][0]["mean_motion"], R["mean_motion"])

    def test_kvn_units_need_their_blank(self):
        """Finding 8: 16.05[064833] read as 16.05 with units "064833"; CCSDS 502.0-B-3 7.7.1.1 puts a blank first."""
        self.rejects(ref.read_kvn_text, kvn_text(MEAN_MOTION="16.05[064833]"), "MEAN_MOTION")
        self.assertEqual(ref.read_kvn_text(kvn_text(MEAN_MOTION=MM + " [rev/day]"))[0][0]["mean_motion"], R["mean_motion"])

    def test_tle_columns_take_only_what_the_format_writes(self):
        """Finding 4: an exponent in the eccentricity or a fixed-point column, two signs on an exponent field, and line
        2's catalog field, which was never read."""
        l1, l2 = LINES[1], LINES[2]
        for what, a, b in (("eccentricity", None, column(l2, 26, 33, "12345E1")), ("eccentricity", None, column(l2, 26, 33, "0001E-1")),
                           ("inclination", None, column(l2, 8, 16, "5.1591E1")),
                           ("second derivative", column(l1, 44, 52, "+-1159-4"), None), ("BSTAR", column(l1, 53, 61, "--1234-5"), None)):
            with self.subTest(field=what, line=(a or b)[:40]):
                self.rejects(ref.read_tle_text, tle_text(a, b), f"TLE {what} field", "is not a number")
        self.rejects(ref.read_tle_text, tle_text(None, column(l2, 2, 7, "25545")), "line 2's catalog field")
        for what, a in (("BSTAR, negative", column(l1, 53, 61, "-11606-4")), ("BSTAR, zero", column(l1, 53, 61, " 00000+0")),
                        ("second derivative, positive", column(l1, 44, 52, "+11563-4"))):      # twins: the format's forms
            with self.subTest(twin=what):
                self.assertEqual(len(ref.read_tle_text(tle_text(a))), 1)

    def test_a_tle_line_is_printable_ascii_in_every_column(self):
        """Findings 7a: a no-break space in a separator column, and another script's digit in the designator."""
        l1 = LINES[1]
        self.rejects(ref.read_tle_text, tle_text(column(l1, 8, 9, "\u00a0")), "column 9", "printable ASCII")
        self.rejects(ref.read_tle_text, tle_text(column(l1, 11, 12, "\u0660")), "international designator")

    def test_an_epoch_past_the_years_a_datetime_holds_is_refused_in_words(self):
        """Finding 5: OverflowError, which the runner reported as an internal error of the corpus."""
        self.rejects(ref.read_csv_text, csv_text(EPOCH="9999-12-31T23:59:59.9999999"), "EPOCH")

    def test_json_names_the_key_of_a_constant_and_refuses_repeats_and_non_objects(self):
        """Findings 7b, 7d, 8: NaN refused without the key; the last of a repeated key won; an entry that is no object
        raised TypeError, an error of the corpus in the runner's words."""
        self.rejects(ref.read_json_text, json_text(raw={"MEAN_MOTION": "NaN"}), "MEAN_MOTION", "NaN is not a JSON number")
        twice = json_text().replace('"MEAN_MOTION": ', '"MEAN_MOTION": 1.0, "MEAN_MOTION": ', 1)
        self.rejects(ref.read_json_text, twice, "MEAN_MOTION", "more than once")
        self.rejects(ref.read_json_text, "[5]", "not an object")
        self.assertEqual(ref.read_json_text(json_text())[0][0]["mean_motion"], R["mean_motion"])           # twin

    def test_xml_refuses_repeats_markup_inside_a_value_and_what_is_not_xml(self):
        """Finding 8 and 7d: the last of a repeated element won; 16.05<b/>064833 read as 16.05; a parse error was a
        SyntaxError, an error of the corpus in the runner's words."""
        x = xml_text()
        self.rejects(ref.read_xml_text, x.replace("<MEAN_MOTION>", "<MEAN_MOTION>1.0</MEAN_MOTION><MEAN_MOTION>", 1), "MEAN_MOTION", "more than once")
        self.rejects(ref.read_xml_text, xml_text(MEAN_MOTION=MM[:5] + "<b/>" + MM[5:]), "MEAN_MOTION", "markup")
        self.rejects(ref.read_xml_text, x[:-20], "not well-formed")
        self.assertEqual(ref.read_xml_text(x)[0][0]["mean_motion"], R["mean_motion"])                     # twin

    def test_a_csv_header_names_each_column_once(self):
        """Finding 8: the last column of a repeated name won."""
        c = csv_text().replace("MEAN_MOTION,ECCENTRICITY", "MEAN_MOTION,MEAN_MOTION", 1)
        self.rejects(ref.read_csv_text, c, "MEAN_MOTION", "more than once")


class ALiveEpochInAnyCcsdsFormReadsAsTheInstant(unittest.TestCase):
    """Finding 3, a false fail older than D-336: on live bytes the oracle kept the file's epoch text, and the comparison
    reads only the calendar form with six fraction digits, so a legal day-of-year epoch, a trailing Z, no fraction or a
    seventh fraction digit failed every parser, the reference adapter included. The twin: a wrong instant still fails."""

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-strict-epochs-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def values(self, parser, epoch):
        os.makedirs(os.path.join(self.data, LIVE), exist_ok=True)
        with open(os.path.join(self.data, LIVE, "iss.csv"), "w", encoding="utf-8", newline="") as f:
            f.write(csv_text(EPOCH=epoch))
        res = Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["baseline-iss-five-formats"])[0]
        return [i for i in res.items if i.check == "values" and (i.file or "").endswith("iss.csv")]

    def test_every_ccsds_form_of_the_same_instant(self):
        e = FIELDS["EPOCH"]                                   # 1998-11-20T06:49:59.999808
        for form in (e, e + "Z", "1998-324T06:49:59.999808", "1998-324T06:49:59.999808Z", e + "0", "1998-11-20T06:50:00"):
            with self.subTest(epoch=form):
                items = self.values(Reference(), form)
                self.assertTrue(items)
                self.assertEqual([i.status for i in items], ["pass"], [i.detail[:160] for i in items])

    def test_the_twin_a_parser_with_another_instant_fails(self):
        class Off(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                for r in out:
                    if "_refused" not in r:
                        r["epoch"] = "1998-11-20T06:50:01.000000"
                return out
        self.assertEqual([i.status for i in self.values(Off(), "1998-324T06:49:59.999808Z")], ["fail"])



class TheReviewersSecondReading(unittest.TestCase):
    """The separate reviewer's second reading of D-336 (2026-10-15), under the owner's model. Each route with its twin;
    every frozen expected value is still unchanged."""

    def rejects(self, reader, text, *words):
        with self.assertRaises(ValueError) as cm:
            reader(text)
        for w in words:
            self.assertIn(w, str(cm.exception))

    def test_an_indented_comment_is_a_comment(self):
        """Finding 1, a false fail of the first mend: blanks before a keyword mean nothing (7.4.5), COMMENT's too."""
        for indent in ("  ", "\t", " \t "):
            with self.subTest(indent=repr(indent)):
                text = kvn_text().replace("MEAN_MOTION", indent + "COMMENT a note\nMEAN_MOTION", 1)
                rec = ref.read_kvn_text(text)[0][0]
                self.assertEqual(rec["mean_motion"], R["mean_motion"])
                self.assertIn("a note", rec["kvn"]["comments"])

    def test_a_json_constant_inside_an_array_is_refused_with_its_key(self):
        """Finding 2: NaN in an array under a key was read as an object's address."""
        for token in ("[NaN]", "[[Infinity]]", "[1, -Infinity]"):
            with self.subTest(value=token):
                self.rejects(ref.read_json_text, json_text(raw={"OBJECT_NAME": token}), "OBJECT_NAME", "not a JSON number")

    def test_tle_values_stay_in_their_columns(self):
        """Findings 3 and 4: a value written over the blank between two fields, an exponent field one column over, and a
        sign in a column the format writes unsigned were read; BSTAR -116060-4 over columns 53 to 61 lost its sign."""
        l1, l2 = LINES[1], LINES[2]
        cases = [("line 1, over a blank", column(l1, 52, 61, "-116060-4"), None, "the blank between two fields"),
                 ("line 2, over a blank", None, column(l2, 7, 16, "151.59080"), "the blank between two fields"),
                 ("element set over a blank", column(l1, 63, 68, "12345"), None, "the blank between two fields"),
                 ("BSTAR one column over", column(l1, 53, 61, "  1234-5"), None, "TLE BSTAR field"),
                 ("a signed inclination", None, column(l2, 8, 16, "-51.5908"), "TLE inclination field"),
                 ("a signed mean motion", None, column(l2, 52, 63, "-16.0506483"), "TLE mean motion field"),
                 ("a signed mean anomaly", None, column(l2, 43, 51, "-359.745"), "TLE mean anomaly field"),
                 ("a signed element set", column(l1, 64, 68, "  -1"), None, "TLE element set number field"),
                 ("a signed revolution", None, column(l2, 63, 68, " -123"), "TLE revolution number field")]
        for name, a, b, words in cases:
            with self.subTest(how=name):
                self.rejects(ref.read_tle_text, tle_text(a, b), words)
        for name, a in (("a negative first derivative", column(l1, 33, 43, "-.00003657")),          # twins: the format's own
                        ("a positive one", column(l1, 33, 43, " .00003657")), ("BSTAR negative", column(l1, 53, 61, "-11606-4"))):
            with self.subTest(twin=name):
                self.assertEqual(len(ref.read_tle_text(tle_text(a))), 1)

    def test_a_tle_element_line_that_pairs_with_nothing_is_refused(self):
        """Finding 7: a blank line inside a set, LFCR ends, a line 2 before its line 1, an indented line 1 and a form feed
        before it were passed over, the set missing from the oracle."""
        name, l1, l2 = LINES[0].rstrip(), tle_text().splitlines()[1], tle_text().splitlines()[2]
        for how, text in (("a blank line inside", f"{name}\n{l1}\n\n{l2}\n"), ("LFCR ends", f"{name}\n\r{l1}\n\r{l2}\n\r"),
                          ("line 2 first", f"{name}\n{l2}\n{l1}\n"), ("an indented line 1", f"{name}\n {l1}\n{l2}\n")):
            with self.subTest(how=how):
                self.rejects(ref.read_tle_text, text, "pairs with nothing")
        self.assertEqual(len(ref.read_tle_text(f"{name}\n{l1}\n{l2}\n\n\n")), 1)            # twin: blank lines after a set
        # a form feed before line 1, a page break, is taken off since the sixth reading and the set is read, not passed
        # over (ADosEraFileReadsAsItsSets)
        self.assertEqual(ref.read_tle_text(f"{name}\n\x0c{l1}\n{l2}\n")[0]["mean_motion"], MM)

    def test_xml_blocks_appear_once_and_hold_no_text_between_elements(self):
        """Findings 5 and 6: a repeated segment or data block was read first-wins, and text between elements set aside."""
        x = xml_text()
        twice_data = x.replace("<data>", "<data><meanElements><MEAN_MOTION>1.0</MEAN_MOTION></meanElements></data><data>", 1)
        self.rejects(ref.read_xml_text, twice_data, "data", "more than once")
        twice_segment = x.replace("<segment>", "<segment><metadata/><data/></segment><segment>", 1)
        self.rejects(ref.read_xml_text, twice_segment, "segment", "more than once")
        between = x.replace("</MEAN_MOTION>", "</MEAN_MOTION>064833", 1)
        self.rejects(ref.read_xml_text, between, "text between its elements")
        pretty = x.replace("><", ">\n  <")                                                       # twin: indentation
        self.assertEqual(ref.read_xml_text(pretty)[0][0]["mean_motion"], R["mean_motion"])

    def test_a_kvn_message_starts_with_its_version_line(self):
        """Finding 8: assignments before CCSDS_OMM_VERS were skipped, the message dropped whole."""
        text = kvn_text().replace("CCSDS_OMM_VERS = 2.0\n", "", 1)
        self.rejects(ref.read_kvn_text, text, "comes before the message's CCSDS_OMM_VERS")
        self.assertEqual(len(ref.read_kvn_text("COMMENT a header\n" + kvn_text())[0]), 1)       # twin: a comment first

    def test_a_json_text_field_holds_text(self):
        """Finding 9: true read as "True" and ["ISS"] as "['ISS']"."""
        for token in ("true", '["ISS"]', "25544", "{}"):
            with self.subTest(object_name=token):
                self.rejects(ref.read_json_text, json_text(raw={"OBJECT_NAME": token}), "OBJECT_NAME", "where the field is text")
        self.assertIsNone(ref.read_json_text(json_text(raw={"OBJECT_NAME": "null"}))[0][0]["object_name"])   # twin: null

    def test_kvn_units_only_where_the_table_gives_them_and_as_it_gives_them(self):
        """Finding 10: a bracketed tail on any keyword was taken off as units, unchecked."""
        self.assertEqual(ref.read_kvn_text(kvn_text(OBJECT_NAME="ISS [ZARYA]"))[0][0]["object_name"], "ISS [ZARYA]")
        self.rejects(ref.read_kvn_text, kvn_text(MEAN_MOTION=MM + " [deg]"), "MEAN_MOTION", "units")
        self.rejects(ref.read_kvn_text, kvn_text(ECCENTRICITY=FIELDS["ECCENTRICITY"] + " [deg]"), "ECCENTRICITY")
        self.assertEqual(ref.read_kvn_text(kvn_text(INCLINATION=FIELDS["INCLINATION"] + " [deg]"))[0][0]["inclination"],
                         R["inclination"])                                                     # twin: the table's units

    def test_an_offset_epoch_only_in_xml(self):
        """Finding 11: 502.0-B-3 7.5.10 gives a UTC epoch with an optional Z; the NDM/XML epochType alone allows an offset."""
        e = FIELDS["EPOCH"]
        self.rejects(ref.read_csv_text, csv_text(EPOCH=e + "+00:00"), "EPOCH", "offset")
        self.rejects(ref.read_kvn_text, kvn_text(EPOCH=e + "+01:00"), "EPOCH", "offset")
        self.assertEqual(ref.read_csv_text(csv_text(EPOCH=e + "Z"))[0][0]["epoch"], e + "Z")           # twin: Z
        self.assertEqual(len(ref.read_xml_text(xml_text(EPOCH=e + "+00:00"))[0]), 1)                 # and XML's offset

    def test_check_tle_says_what_is_wrong_for_a_csv_or_json_its_modules_refuse(self):
        """Finding 15: a field past the csv module's limit, or JSON nested past the recursion limit, ended in a traceback."""
        self.rejects(ref.read_csv_text, "OBJECT_NAME,MEAN_MOTION\r\n" + "x" * 200000 + ",1\r\n", "CSV cannot be read")
        self.rejects(ref.read_json_text, "[" * 1000000 + "]" * 1000000, "nested too deep")
        self.rejects(ref.read_json_text, "[" + '{"a":' * 100000 + "1" + "}" * 100000 + "]", "nested too deep")


class ALeapSecondOnLiveBytesTakesEitherInstant(unittest.TestCase):
    """Finding 12: a leap-second epoch, which a datetime cannot hold, was read as the instant a second earlier only, so
    a parser that gave the next one failed, where the epoch vectors accept either. Twin: a third instant fails."""

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-strict-leap-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def statuses(self, epoch):
        class Gives(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                for r in out:
                    if "_refused" not in r:
                        r["epoch"] = epoch
                return out
        os.makedirs(os.path.join(self.data, LIVE), exist_ok=True)
        with open(os.path.join(self.data, LIVE, "iss.csv"), "w", encoding="utf-8", newline="") as f:
            f.write(csv_text(EPOCH="2016-12-31T23:59:60.5"))
        res = Runner(Gives(), root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["baseline-iss-five-formats"])[0]
        return [i.status for i in res.items if i.check == "values" and (i.file or "").endswith("iss.csv")]

    def test_either_instant(self):
        self.assertEqual(self.statuses("2016-12-31T23:59:59.500000"), ["pass"])
        self.assertEqual(self.statuses("2017-01-01T00:00:00.500000"), ["pass"])
        self.assertEqual(self.statuses("2017-01-01T00:00:01.500000"), ["fail"])



class TheReviewersThirdReading(unittest.TestCase):
    """The separate reviewer's third reading of D-336 (2026-10-15), under the owner's model. Each route with its twin;
    every frozen expected value is still unchanged."""

    def rejects(self, reader, text, *words):
        with self.assertRaises(ValueError) as cm:
            reader(text)
        for w in words:
            self.assertIn(w, str(cm.exception))

    def test_a_comment_directly_in_xml_data_is_a_comment(self):
        """Finding 1, a false fail of the second mend: ommData allows COMMENT elements before its blocks."""
        x = xml_text()
        for n in (1, 2):
            with self.subTest(comments=n):
                text = x.replace("<data>", "<data>" + "<COMMENT>a note</COMMENT>" * n, 1)
                self.assertEqual(ref.read_xml_text(text)[0][0]["mean_motion"], R["mean_motion"])
        inside = x.replace("<meanElements>", "<meanElements><COMMENT>a note</COMMENT>", 1)          # twin: in a block
        self.assertEqual(ref.read_xml_text(inside)[0][0]["mean_motion"], R["mean_motion"])

    def test_a_tle_line_with_something_odd_in_column_2_is_refused(self):
        """Finding 3: a tab, a no-break space, a letter or an underscore in column 2 hid an element line from the
        pairing, and the set was passed over."""
        l1, l2 = tle_text().splitlines()[1], tle_text().splitlines()[2]
        for name, odd in (("a tab", "\t"), ("an underscore", "_"), ("a letter", "X"), ("a no-break space", "\u00a0")):
            with self.subTest(column_2=name):
                # the odd column on both lines of a second set, after a good one: on its own an odd line 1 left line 2
                # an orphan, which was refused anyway (the fourth reading's finding 1)
                text = f"ISS\n{l1}\n{l2}\nISS 2\n{l1[0] + odd + l1[2:]}\n{l2[0] + odd + l2[2:]}\n"
                with self.assertRaises(ValueError):
                    ref.read_tle_text(text)
                self.assertTrue(any("_refused" in r for r in Reference().parse(text.encode(), "tle")))   # the control too
        self.assertEqual(len(ref.read_tle_text(f"{l1}\n{l2}\n{l1}\n{l2}\n")), 2)                         # twin: a 2LE file

    def test_the_name_line_is_printable_ascii_and_its_blanks_are_ascii(self):
        """Finding 4: the name line was read with Unicode str.strip() and held to nothing; and the international
        designator's piece was not checked."""
        l1, l2 = tle_text().splitlines()[1], tle_text().splitlines()[2]
        for name, line0 in (("a no-break space", "ISS (ZARYA)\u00a0"), ("a file separator", "\x1cISS (ZARYA)"), ("NEL", "ISS (ZARYA)\x85")):
            with self.subTest(name_line=name):
                self.rejects(ref.read_tle_text, f"{line0}\n{l1}\n{l2}\n", "name line", "printable ASCII")
        self.assertEqual(ref.read_tle_text(f"ISS (ZARYA)             \n{l1}\n{l2}\n")[0]["object_name"], "ISS (ZARYA)")   # twin
        self.rejects(ref.read_tle_text, tle_text(column(LINES[1], 9, 17, "98067a#!")), "international designator")

    def test_a_blank_classification_is_no_value(self):
        """Finding 5: a blank column is its padding, so a blank classification is no classification, not ' '."""
        self.assertIsNone(ref.read_tle_text(tle_text(column(LINES[1], 7, 8, " ")))[0]["classification_type"])
        self.assertEqual(ref.read_tle_text(tle_text())[0]["classification_type"], "U")            # twin

    def test_space_tracks_three_line_name_drops_its_line_number(self):
        """Finding 6: Space-Track writes the name line as "0 NAME"."""
        l1, l2 = tle_text().splitlines()[1], tle_text().splitlines()[2]
        self.assertEqual(ref.read_tle_text(f"0 ISS (ZARYA)\n{l1}\n{l2}\n")[0]["object_name"], "ISS (ZARYA)")

    def test_an_xml_epoch_may_end_in_a_bare_point(self):
        """Finding 7: the NDM/XML epochType allows a point with no digits after it."""
        e = FIELDS["EPOCH"][:19]                                                                    # whole seconds
        for form in (e + ".", e + ".Z"):
            with self.subTest(epoch=form):
                self.assertEqual(len(ref.read_xml_text(xml_text(EPOCH=form))[0]), 1)
        self.rejects(ref.read_csv_text, csv_text(EPOCH=e + "."), "EPOCH")                          # not outside XML

    def test_units_are_those_the_schema_enumerates(self):
        """Finding 8f: the vendored NDM/XML schemas enumerate rev/day and REV/DAY, and 1/ER for BSTAR."""
        for units in ("rev/day", "REV/DAY"):
            with self.subTest(units=units):
                self.assertEqual(ref.read_kvn_text(kvn_text(MEAN_MOTION=MM + f" [{units}]"))[0][0]["mean_motion"], R["mean_motion"])
        self.assertEqual(ref.read_kvn_text(kvn_text(BSTAR=FIELDS["BSTAR"] + " [1/ER]"))[0][0]["bstar"], R["bstar"])
        self.rejects(ref.read_kvn_text, kvn_text(MEAN_MOTION=MM + " [Rev/Day]"), "units")             # twin: another case

    def test_check_tle_itself_stops_in_words_on_json_nested_too_deep(self):
        """Finding 8e: the test ran the reader, not check-tle."""
        import contextlib
        import io
        from gpconf.__main__ import main
        d = tempfile.mkdtemp(prefix="gpconf-strict-deep-")
        try:
            src = os.path.join(d, "deep.json")
            with open(src, "w") as f:
                f.write("[" + '{"a":' * 100000 + "1" + "}" * 100000 + "]")
            tle = os.path.join(d, "w.tle")
            with open(tle, "w") as f:
                f.write(tle_text())
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                rc = main(["check-tle", tle, "--against", src])
            self.assertEqual(rc, 2)
            self.assertIn("nested too deep", err.getvalue())
        finally:
            shutil.rmtree(d, ignore_errors=True)


class ALeapSecondAtTheEndOfTime(unittest.TestCase):
    """Finding 2, a false fail of the second mend: the last second of 9999 has no next instant a datetime can hold, and
    the case ended as an internal error. Twin: a wrong instant still fails."""

    def statuses(self, epoch):
        data = tempfile.mkdtemp(prefix="gpconf-strict-leap-9999-")
        try:
            class Gives(Reference):
                def parse(self, raw, fmt):
                    out = super().parse(raw, fmt)
                    for r in out:
                        if "_refused" not in r:
                            r["epoch"] = epoch
                    return out
            os.makedirs(os.path.join(data, LIVE), exist_ok=True)
            with open(os.path.join(data, LIVE, "iss.csv"), "w", encoding="utf-8", newline="") as f:
                f.write(csv_text(EPOCH="9999-12-31T23:59:60"))
            res = Runner(Gives(), root=ROOT, data=data, fetch_hints=False).run(case_ids=["baseline-iss-five-formats"])[0]
            self.assertFalse([i for i in res.items if "internal error" in i.detail])
            return [i.status for i in res.items if i.check == "values" and (i.file or "").endswith("iss.csv")]
        finally:
            shutil.rmtree(data, ignore_errors=True)

    def test_the_last_second(self):
        self.assertEqual(self.statuses("9999-12-31T23:59:59.000000"), ["pass"])
        self.assertEqual(self.statuses("9999-12-31T23:59:58.000000"), ["fail"])



class TheReviewersFourthReading(unittest.TestCase):
    """The separate reviewer's fourth reading of D-336 (2026-10-15), under the owner's model. Each route with its twin;
    none, the reviewer judged, likely on real provider files."""

    def test_an_element_line_is_one_whatever_its_length_or_what_stands_before_it(self):
        """Finding 3: an odd column 2 on a line of 70 characters, or an invisible character before the line number, hid
        the set; it was passed over."""
        l1, l2 = tle_text().splitlines()[1], tle_text().splitlines()[2]
        for name, a, b in (("an odd column 2 and a trailing blank", l1[0] + "_" + l1[2:] + " ", l2[0] + "_" + l2[2:] + " "),
                           ("a zero-width space before the number", "\u200b" + l1, "\u200b" + l2),
                           ("a byte-order mark before the number", "\ufeff" + l1, "\ufeff" + l2)):
            with self.subTest(how=name):
                with self.assertRaises(ValueError):
                    ref.read_tle_text(f"ISS\n{l1}\n{l2}\nISS 2\n{a}\n{b}\n")
        self.assertEqual(len(ref.read_tle_text(f"ISS\n{l1}\n{l2}\n1 SATELLITE\n{l1}\n{l2}\n")), 2)   # twin: a name "1 SATELLITE"

    def test_xml_units_are_held_to_the_same_table_as_kvn(self):
        """Finding 4: a units attribute was never read, so radians or units on an element without any passed."""
        x = xml_text()
        for name, tag, units in (("radians", "INCLINATION", "rad"), ("another case", "INCLINATION", "DEG"), ("units on eccentricity", "ECCENTRICITY", "deg")):
            with self.subTest(how=name):
                with self.assertRaises(ValueError):
                    ref.read_xml_text(x.replace(f"<{tag}>", f'<{tag} units="{units}">', 1))
        self.assertEqual(ref.read_xml_text(x.replace("<INCLINATION>", '<INCLINATION units="deg">', 1))[0][0]["inclination"], R["inclination"])

    def test_an_xml_epoch_may_end_in_a_bare_point_before_an_offset(self):
        """Finding 6."""
        e = FIELDS["EPOCH"][:19]
        self.assertEqual(len(ref.read_xml_text(xml_text(EPOCH=e + ".+00:00"))[0]), 1)

    def test_written_lines_keep_the_writer_contract_for_name_and_designator(self):
        """Finding 2: the name and the designator of lines a writer wrote are reported for information and never failed
        (docs/WRITERS.md, the hooks table); the provider-file rules reached them through the reader."""
        from gpconf import writer as W
        l0, l1, l2 = LINES
        for name, n0, d1 in (("a non-ASCII name", "\u00d1USAT-1", l1), ("a short designator", l0, column(l1, 9, 17, "98067   "))):
            with self.subTest(how=name):
                fixed = d1[:68] + str(tlemod.checksum(d1))
                self.assertEqual(W.round_trip(n0, fixed, l2, R)[0], [])                      # the round trip passes
                with self.assertRaises(ValueError):                                          # twin: a provider file fails
                    ref.read_tle_text(f"{n0}\n{fixed}\n{l2}\n")


class ABlankClassificationOnLiveBytes(unittest.TestCase):
    """Finding 5: a blank classification is no value; as D-285 does for metadata the format does not carry, a parser
    may answer None or the default U. Twin: another letter fails."""

    def statuses(self, answer):
        data = tempfile.mkdtemp(prefix="gpconf-strict-class-")
        try:
            class Gives(Reference):
                def parse(self, raw, fmt):
                    out = super().parse(raw, fmt)
                    for r in out:
                        if "_refused" not in r:
                            r["classification_type"] = answer
                    return out
            os.makedirs(os.path.join(data, LIVE), exist_ok=True)
            with open(os.path.join(data, LIVE, "iss.tle"), "w", encoding="utf-8", newline="") as f:
                f.write(tle_text(column(LINES[1], 7, 8, " ")))
            res = Runner(Gives(), root=ROOT, data=data, fetch_hints=False).run(case_ids=["baseline-iss-five-formats"])[0]
            return [i.status for i in res.items if i.check == "values" and (i.file or "").endswith("iss.tle")]
        finally:
            shutil.rmtree(data, ignore_errors=True)

    def test_none_or_u(self):
        self.assertEqual(self.statuses(None), ["pass"])
        self.assertEqual(self.statuses("U"), ["pass"])
        self.assertEqual(self.statuses("C"), ["fail"])



class TheReviewersFifthReading(unittest.TestCase):
    """The separate reviewer's fifth reading of D-336 (2026-10-15), under the owner's model. Each route with its twin."""

    def test_a_stray_last_line_is_refused_in_words_by_the_reader_and_the_control(self):
        """Finding 1, a crash of the fourth mend: a last line that is not printable ASCII read past the end of the file
        (IndexError), the runner blaming the corpus and check-tle ending in a traceback."""
        import contextlib
        import io
        from gpconf.__main__ import main
        base = tle_text()
        for name, last in (("a DOS end-of-file mark and a letter", "\x1aX"), ("a no-break space", "\u00a0"), ("a name", "\u00d1USAT-1")):   # a tab alone: a blank line, since the sixth reading; a DOS mark alone at the end, padding, since the seventh
            with self.subTest(last_line=name):
                text = base + last + "\n"
                with self.assertRaises(ValueError):
                    ref.read_tle_text(text)
                out = Reference().parse(text.encode(), "tle")                      # the control refuses, set by set
                self.assertTrue(any("_refused" in r for r in out) and any("_refused" not in r for r in out))
        d = tempfile.mkdtemp(prefix="gpconf-strict-last-")
        try:
            src, w = os.path.join(d, "s.tle"), os.path.join(d, "w.tle")
            with open(src, "w", encoding="utf-8") as f:
                f.write(base + "\x1aX\n")
            with open(w, "w", encoding="utf-8") as f:
                f.write(base)
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                rc = main(["check-tle", w, "--against", src])
            self.assertEqual(rc, 2, err.getvalue())
        finally:
            shutil.rmtree(d, ignore_errors=True)
        self.assertEqual(len(ref.read_tle_text(base + "\n\n")), 1)                 # twin: blank lines at the end

    def test_schema_legal_units_on_spacecraft_parameters_and_the_covariance_read(self):
        """Finding 2, a false fail of the fourth mend: MASS in kg, the areas in m**2 and the covariance's units are what
        the schemas allow, and refused every parser on a CCSDS-legal file."""
        x = xml_text()
        sc = x.replace("<tleParameters>", '<spacecraftParameters><MASS units="kg">420000</MASS><SOLAR_RAD_AREA units="m**2">1.5</SOLAR_RAD_AREA>'
                       '<DRAG_AREA units="m**2">2.5</DRAG_AREA></spacecraftParameters><tleParameters>', 1)
        self.assertEqual(ref.read_xml_text(sc)[0][0]["mean_motion"], R["mean_motion"])
        cov = x.replace("</tleParameters>", '</tleParameters><covarianceMatrix><CX_X units="km**2">1.0</CX_X></covarianceMatrix>', 1)
        self.assertEqual(ref.read_xml_text(cov)[0][0]["mean_motion"], R["mean_motion"])
        with self.assertRaises(ValueError):                                           # twin: MASS in grams
            ref.read_xml_text(sc.replace('units="kg"', 'units="g"'))

    def test_only_a_point_right_after_the_seconds_is_bare(self):
        """Finding 3: a point after the fraction's digits was taken off too."""
        e = FIELDS["EPOCH"][:19]
        for form in (e + ".5.", e + ".5.Z", e + ".5.+05:00"):
            with self.subTest(epoch=form):
                with self.assertRaises(ValueError):
                    ref.read_xml_text(xml_text(EPOCH=form))
        self.assertEqual(len(ref.read_xml_text(xml_text(EPOCH=e + ".Z"))[0]), 1)       # twin: a bare point

    def test_a_padded_short_name_that_begins_like_a_line_number_is_a_name(self):
        """Finding 4: trailing blanks counted toward "longer than a name"."""
        l1, l2 = tle_text().splitlines()[1], tle_text().splitlines()[2]
        self.assertEqual(ref.read_tle_text(f"{'1 HOPE':25}\n{l1}\n{l2}\n")[0]["object_name"], "1 HOPE")

    def test_a_written_designator_that_is_none_is_reported_not_failed(self):
        """Finding 6: a writer that copies OBJECT_ID "UNKNOWN" into the designator failed the round trip, against the
        writer contract."""
        from gpconf import writer as W
        l0, l1, l2 = LINES
        bad = column(l1, 9, 17, "UNKNOWN ")
        bad = bad[:68] + str(tlemod.checksum(bad))
        self.assertEqual(W.round_trip(l0, bad, l2, R)[0], [])
        with self.assertRaises(ValueError):                                           # twin: a provider file fails
            ref.read_tle_text(f"{l0}\n{bad}\n{l2}\n")



class WhatTheAnyBytesPropertyFound(unittest.TestCase):
    """The property the owner asked for on the fifth reading (tests/test_properties.py, ReaderOnAnyBytes): whatever the
    bytes, the reader reads them or refuses them in words, and check-tle exits 0, 1 or 2. Each crash it found, with its
    twin."""

    def test_a_csv_header_the_csv_module_cannot_read_is_refused_in_words(self):
        """A carriage return inside a header field raised the csv module's own error from the header, read before the
        guard around the rows: the runner blaming the corpus, check-tle ending in a traceback."""
        import contextlib
        import io
        from gpconf.__main__ import main
        c = csv_text()
        bad = c.replace("NORAD_CAT_ID", "NORAD\rCAT_ID", 1)
        with self.assertRaises(ValueError) as cm:
            ref.read_csv_text(bad)
        self.assertIn("CSV cannot be read", str(cm.exception))
        self.assertNotIn("do you need", str(cm.exception))                         # the module's advice to the corpus
        d = tempfile.mkdtemp(prefix="gpconf-strict-header-")
        try:
            src, w = os.path.join(d, "s.csv"), os.path.join(d, "w.tle")
            with open(src, "w", encoding="utf-8", newline="") as f:
                f.write(bad)
            with open(w, "w", encoding="utf-8") as f:
                f.write(tle_text())
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                rc = main(["check-tle", w, "--against", src])
            self.assertEqual(rc, 2, err.getvalue())
        finally:
            shutil.rmtree(d, ignore_errors=True)
        self.assertEqual(one(ref.read_csv_text, c)[0]["norad_cat_id"], R["norad_cat_id"])   # twin: CRLF ends, as written



class AnExponentPastAnyValue(unittest.TestCase):
    """The fifth reading left one crash outside the model: a number written with an exponent so large that its plain
    form filled memory. The owner's ruling on that reading: any crash blamed on the corpus is mended. '1E9999999999' was
    expanded to ten billion digits; the reader now refuses a number whose plain form holds more than PLAIN_DIGITS (4,300,
    Python's own limit for an integer read from text). Here a thousandth of that exponent, which the old form expanded
    to ten million digits and read."""

    def test_refused_in_words_in_every_format_that_writes_an_exponent(self):
        big = "1E9999999"
        for name, reader, text in (("csv", ref.read_csv_text, csv_text(MEAN_MOTION=big)),
                                   ("json", ref.read_json_text, json_text(MEAN_MOTION=big)),
                                   ("xml", ref.read_xml_text, xml_text(MEAN_MOTION=big)),
                                   ("kvn", ref.read_kvn_text, kvn_text(MEAN_MOTION=big)),
                                   ("kvn, small", ref.read_kvn_text, kvn_text(BSTAR="1E-9999999"))):
            with self.subTest(fmt=name):
                with self.assertRaises(ValueError) as cm:
                    reader(text)
                self.assertIn("any value needs", str(cm.exception))

    def test_an_exponent_decimal_cannot_hold_is_refused_in_words(self):
        """The sixth reading: Decimal() raised decimal.InvalidOperation, no ValueError, for an exponent past what it
        holds, from plain() and from inside json.loads; the runner said "reference reader raised", check-tle ended in a
        traceback and the control adapter raised. The seventh: JSON's refusal named no key."""
        import contextlib
        import io
        from gpconf.__main__ import main
        huge = "1E" + "9" * 19
        for name, reader, text in (("csv", ref.read_csv_text, csv_text(MEAN_MOTION=huge)),
                                   ("json", ref.read_json_text, json_text(MEAN_MOTION=huge)),
                                   ("json, zero", ref.read_json_text, json_text(MEAN_MOTION="0E" + "1" + "0" * 18)),
                                   ("xml", ref.read_xml_text, xml_text(MEAN_MOTION=huge)),
                                   ("kvn", ref.read_kvn_text, kvn_text(MEAN_MOTION=huge)),
                                   ("kvn, small", ref.read_kvn_text, kvn_text(BSTAR="1E-" + "9" * 19))):
            with self.subTest(fmt=name):
                with self.assertRaises(ValueError) as cm:
                    reader(text)
                self.assertIn("exponent past what any value needs", str(cm.exception))
                self.assertIn("BSTAR" if "kvn, small" in name else "MEAN_MOTION", str(cm.exception))
        d = tempfile.mkdtemp(prefix="gpconf-strict-huge-")
        try:
            src, w = os.path.join(d, "s.csv"), os.path.join(d, "w.tle")
            with open(src, "w", encoding="utf-8", newline="") as f:
                f.write(csv_text(MEAN_MOTION=huge))
            with open(w, "w", encoding="utf-8") as f:
                f.write(tle_text())
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                rc = main(["check-tle", w, "--against", src])
            self.assertEqual(rc, 2, err.getvalue())
        finally:
            shutil.rmtree(d, ignore_errors=True)
        with self.assertRaises(ValueError):                                          # the control refuses in words too
            Reference().parse(csv_text(MEAN_MOTION=huge).encode(), "csv")

    def test_an_integer_of_more_digits_than_any_needs_is_refused_in_our_words(self):
        """The seventh reading: int() refused an integer of more than 4,300 digits with advice to whoever runs Python
        ("use sys.set_int_max_str_digits()"), passed on to the user."""
        long = "1" * 4301
        for name, reader, text in (("csv", ref.read_csv_text, csv_text(NORAD_CAT_ID=long)), ("json", ref.read_json_text, json_text(NORAD_CAT_ID=long)),
                                   ("kvn", ref.read_kvn_text, kvn_text(NORAD_CAT_ID=long)), ("xml", ref.read_xml_text, xml_text(NORAD_CAT_ID=long))):
            with self.subTest(fmt=name):
                with self.assertRaises(ValueError) as cm:
                    reader(text)
                self.assertIn("more digits than any integer needs", str(cm.exception))
                self.assertNotIn("set_int_max_str_digits", str(cm.exception))
        self.assertEqual(ref.plain_int("0" * 4299 + "7"), 7)                        # twin: 4,300 digits read

    def test_the_twin_every_exponent_a_value_needs_reads(self):
        for form, want in (("1.1563E-5", "0.000011563"), ("-11563E-9", "-0.000011563"), ("0.0E+0", "0"), ("1E-4300", "0." + "0" * 4299 + "1"),
                           ("16.05064833E0", MM), ("0E4300", "0"), ("0E-4301", "0"), ("0E" + "9" * 18, "0"), ("1E" + "0" * 30 + "5", "100000")):
            with self.subTest(form=form):
                self.assertEqual(ref.plain(form), want)



class ADosEraFileReadsAsItsSets(unittest.TestCase):
    """The sixth reading: a TLE file whose every set is valid was refused whole when it carried what older files carry
    around their sets: a DOS end-of-file mark as its last byte, a page break (form feed) on a line of its own or before
    a name line, a line holding only a tab. None changes a value; the reader and the control now read such a file as
    its sets. Inside a line each is still refused, and a blank line inside a set too."""

    def sets(self, text):
        recs = ref.read_tle_text(text)
        out = Reference().parse(text.encode(), "tle")
        self.assertFalse([r for r in out if "_refused" in r], [r.get("_refused") for r in out][:2])
        return [(r["norad_cat_id"], r["object_name"], r["mean_motion"]) for r in recs]

    def test_what_older_files_carry_between_sets(self):
        one = tle_text()
        plain = self.sets(one + one)
        crlf = (one + one).replace("\n", "\r\n")
        for name, text in (("a DOS end-of-file mark", crlf + "\x1a"), ("a form feed between sets", one + "\x0c\n" + one),
                           ("a form feed before a name line", one + "\x0c" + one), ("a tab alone between sets", one + "\t\n" + one),
                           ("a vertical tab and blanks between sets", one + " \x0b \n" + one),
                           ("a form feed before line 1 of a two-line set", "\x0c" + "\n".join(one.splitlines()[1:]) + "\n"),
                           ("XMODEM padding, the mark to the end of the block", crlf + "\x1a" * 40),
                           ("the mark and a line end", crlf + "\x1a\r\n"), ("the mark and NUL padding", crlf + "\x1a\x00\x00"),
                           ("NUL padding alone", one + one + "\x00" * 30),
                           ("CR CR LF ends, CRLF written again in text mode", (one + one).replace("\n", "\r\r\n"))):
            with self.subTest(file=name):
                got = self.sets(text)
                self.assertEqual(got, plain if "two-line" not in name else [(plain[0][0], None, plain[0][2])])

    def test_the_twins_inside_a_line_or_a_set_still_refused(self):
        one = tle_text()
        l0, l1, l2 = one.splitlines()
        for name, text in (("a DOS mark inside a line", one.replace("98067A", "98067\x1a", 1)),
                           ("a DOS mark on a line of its own, sets after it", one + "\x1a\n" + one),
                           ("a NUL inside a line", one.replace("98067A", "98067\x00", 1)),
                           ("a form feed inside line 1", one.replace(" 98067A", "\x0c98067A", 1)),
                           ("a tab line inside a set", f"{l0}\n{l1}\n\t\n{l2}\n"),
                           ("a form feed line inside a set", f"{l0}\n{l1}\n\x0c\n{l2}\n")):
            with self.subTest(file=name):
                with self.assertRaises(ValueError):
                    ref.read_tle_text(text)



class ALeapSecondWhereYearsAreNotPadded(unittest.TestCase):
    """The seventh reading: where strftime("%Y") pads no year below 1000 (glibc under the Pythons that leave it so [inferred: which versions is an open question], as CI's 3.9 job
    runs), iso_epoch writes '999-...', and the leap-second branch read that back with strptime, which raised ValueError:
    the case ended as an internal error of the runner. Simulated here by writing the year unpadded; the twin is this
    platform's padded year."""

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-strict-leap999-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def statuses(self, unpadded, answer):
        from unittest import mock
        from gpconf import tle as T

        class Gives(Reference):
            def parse(self, raw, fmt):
                out = super().parse(raw, fmt)
                for r in out:
                    if "_refused" not in r:
                        r["epoch"] = answer
                return out
        os.makedirs(os.path.join(self.data, LIVE), exist_ok=True)
        with open(os.path.join(self.data, LIVE, "iss.csv"), "w", encoding="utf-8", newline="") as f:
            f.write(csv_text(EPOCH="0999-12-31T23:59:60.5"))
        real = T.iso_epoch
        bare = (lambda t: (lambda s: s.lstrip("0") if s[:4] < "1000" else s)(real(t))) if unpadded else real
        with mock.patch.object(T, "iso_epoch", bare):
            res = Runner(Gives(), root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["baseline-iss-five-formats"])[0]
        self.assertFalse([i.detail for i in res.items if "internal error" in (i.detail or "")])
        return [i.status for i in res.items if i.check == "values" and (i.file or "").endswith("iss.csv")]

    def test_unpadded_and_padded_years(self):
        for unpadded in (True, False):
            for answer in ("0999-12-31T23:59:59.500000", "1000-01-01T00:00:00.500000"):   # either instant, across the year
                with self.subTest(unpadded=unpadded, answer=answer):
                    self.assertEqual(self.statuses(unpadded, answer), ["pass"])
            with self.subTest(unpadded=unpadded, answer="a third instant"):
                self.assertEqual(self.statuses(unpadded, "1000-01-01T00:00:01.500000"), ["fail"])



class ACardImageReadsAsItsLines(unittest.TestCase):
    """D-338, the owner's ruling: a TLE kept as 80-column card images, element lines blank from column 70 to 80, reads
    as its 69-column lines, in the reader, the control adapter and on live bytes; any other character past column 69,
    or a line past column 80, is still refused in words; the writer case holds written lines to 69 columns. Before, a
    card image was refused whole as "line length 80/80 != 69"."""

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-strict-card-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    @staticmethod
    def values(recs):
        return [{k: v for k, v in r.items() if k != "tle"} for r in recs]

    def test_a_card_image_reads_the_values_of_its_69_column_lines(self):
        l0, l1, l2 = tle_text().splitlines()
        plain = self.values(ref.read_tle_text(tle_text()))
        control = Reference().parse(tle_text().encode(), "tle")
        for name, text in (("every line padded to 80", f"{l0:80}\n{l1:80}\n{l2:80}\n"),
                           ("element lines padded to 70 and 75", f"{l0}\n{l1:70}\n{l2:75}\n"),
                           ("CRLF card images, two sets", f"{l0:80}\r\n{l1:80}\r\n{l2:80}\r\n" * 2)):
            with self.subTest(file=name):
                got = ref.read_tle_text(text)
                self.assertEqual(self.values(got), plain * (2 if "two sets" in name else 1))
                self.assertEqual(got[0]["tle"]["line_lengths"][1:], [69, 69])
                out = Reference().parse(text.encode(), "tle")                       # the control: as from the plain file
                self.assertEqual(self.values(out), self.values(control) * (2 if "two sets" in name else 1))

    def test_the_twin_anything_but_blanks_past_column_69_is_refused_in_words(self):
        l0, l1, l2 = tle_text().splitlines()
        for name, line, words in (("a digit in column 70", l1 + "0", "column 70"), ("a letter in column 80", f"{l1:79}X", "column 80"),
                                  ("a tab in column 70", l1 + "\t", "column 70"), ("a no-break space", l1 + "\u00a0", "column 70"),
                                  ("blanks to column 81", f"{l1:81}", "81 columns"),
                                  ("an extra digit in column 20", l1[:19] + "5" + l1[19:], "70 columns")):
            with self.subTest(line=name):
                with self.assertRaises(ValueError) as cm:
                    ref.read_tle_text(f"{l0}\n{line}\n{l2}\n")
                self.assertIn(words, str(cm.exception))
                out = Reference().parse(f"{l0}\n{line}\n{l2}\n".encode(), "tle")
                self.assertTrue(out and all("_refused" in r for r in out))

    def test_a_line_cut_short_and_padded_is_no_card_image(self):
        """The reading of D-338: a card cut inside its last field and padded read the cut element set or revolution
        number as the value (292 as 29, 56353 as 5635). A card blank in column 69, its checksum, is refused, a whole card
        whose checksum was never written with it (the second reading); the twins: a whole card reads, and a 69-column
        line with a blank checksum column reads as it always has."""
        l0, l1, l2 = tle_text().splitlines()
        for name, a, b in (("line 1 cut at column 67", f"{l1[:67]:80}", f"{l2:80}"), ("line 2 cut at column 67", f"{l1:80}", f"{l2[:67]:80}"),
                           ("line 2 without its checksum", f"{l1:80}", f"{l2[:68]:80}"), ("line 2 cut at column 64", f"{l1:80}", f"{l2[:64]:72}")):
            with self.subTest(card=name):
                with self.assertRaises(ValueError) as cm:
                    ref.read_tle_text(f"{l0}\n{a}\n{b}\n")
                self.assertIn("a line cut short, or one whose checksum was never written", str(cm.exception))
                out = Reference().parse(f"{l0}\n{a}\n{b}\n".encode(), "tle")
                self.assertTrue(out and all("_refused" in r for r in out))
        self.assertEqual(len(ref.read_tle_text(f"{l0}\n{l1:80}\n{l2:80}\n")), 1)
        self.assertFalse(ref.read_tle_text(f"{l0}\n{l1[:68]} \n{l2}\n")[0]["tle"]["checksums_valid"])

    def test_on_live_bytes_a_card_image_is_graded_and_a_line_with_more_fails_every_parser(self):
        l0, l1, l2 = tle_text().splitlines()

        def statuses(text):
            os.makedirs(os.path.join(self.data, LIVE), exist_ok=True)
            with open(os.path.join(self.data, LIVE, "iss.tle"), "w", encoding="utf-8", newline="") as f:
                f.write(text)
            res = Runner(Reference(), root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["baseline-iss-five-formats"])[0]
            return [(i.check, i.status) for i in res.items if (i.file or "").endswith("iss.tle")]
        card = statuses(f"{l0:80}\n{l1:80}\n{l2:80}\n")
        self.assertIn(("values", "pass"), card)
        self.assertFalse([c for c in card if c[1] == "fail"], card)
        more = statuses(f"{l0}\n{l1:75}9\n{l2}\n")                              # twin: a digit in column 76
        self.assertTrue([c for c in more if c[1] == "fail"], more)
        self.assertNotIn(("values", "pass"), more)

    def test_written_lines_are_still_held_to_69_columns(self):
        """The writer contract: a writer that pads its lines to 80 writes 80-character lines, and the writer's own
        check says so."""
        from gpconf import writer as W
        l0, l1, l2 = tle_text().splitlines()
        self.assertTrue(any("not 69" in p for p in W.check_lines(f"{l1:80}", f"{l2:80}")))
        self.assertEqual(W.check_lines(l1, l2), [])                                   # twin: 69 columns
        with self.assertRaises(ValueError):
            ref.parse_tle_lines(l0, f"{l1:80}", f"{l2:80}", written=True)



class CheckTleNotesTrailingBlanksOnWrittenLines(unittest.TestCase):
    """D-338, the owner's second ruling: check-tle takes trailing whitespace off every line it reads (D-119), so a
    written card image passed with no word; it now says which written element lines carry trailing blanks and in which
    columns, as a note, never a failure, the exit code unchanged. The twins: the same lines without them carry no note;
    a written fault beside them still fails, the note beside it."""

    def check(self, text, as_json=False):
        import contextlib
        import io
        from gpconf.__main__ import main
        d = tempfile.mkdtemp(prefix="gpconf-strict-ctnote-")
        try:
            w, j = os.path.join(d, "w.tle"), os.path.join(d, "out.json")
            with open(w, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                rc = main(["check-tle", w, "--json", j])
            with open(j, encoding="utf-8") as f:
                rec = json.load(f)["files"][0]["records"]
            return rc, out.getvalue(), rec
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_a_written_card_image_is_noted_and_passes(self):
        l0, l1, l2 = tle_text().splitlines()
        rc, out, recs = self.check(f"{l0}\n{l1:80}\n{l2:75}\n")
        self.assertEqual(rc, 0)
        self.assertEqual(recs[0]["status"], "pass")
        self.assertIn("file line 2 (the set's line 1) carries 11 trailing blanks (columns 70 to 80)", out)
        self.assertIn("file line 3 (the set's line 2) carries 6 trailing blanks (columns 70 to 75)", out)
        self.assertIn("card image's padding", out)
        self.assertEqual(len([n for n in recs[0]["notes"] if "trailing" in n]), 2)
        rc, out, recs = self.check(f"{l0}\n{l1}\t\n{l2}\n")
        self.assertIn("file line 2 (the set's line 1) carries 1 trailing whitespace character (column 70)", out)
        self.assertNotIn("card image", out)                                          # a tab is no card's padding
        rc, out, recs = self.check(f"{l0}\n  {l1}   \n  {l2}\n")                    # an indented pair: file columns
        self.assertIn("file line 2 (the set's line 1) carries 3 trailing blanks (columns 72 to 74)", out)
        self.assertEqual(recs[0]["status"], "fail")                                   # the indentation fails, as before

    def test_the_twins_no_note_without_them_and_a_fault_still_fails(self):
        l0, l1, l2 = tle_text().splitlines()
        rc, out, recs = self.check(tle_text())
        self.assertEqual((rc, recs[0]["status"]), (0, "pass"))
        self.assertNotIn("trailing", out)
        bad = column(l1, 9, 17, "98067B  ")[:68]                                    # a fault: the checksum no longer holds
        rc, out, recs = self.check(f"{l0}\n{bad + str((tlemod.checksum(bad + '0') + 1) % 10):80}\n{l2}\n")
        self.assertEqual((rc, recs[0]["status"]), (1, "fail"))
        self.assertIn("file line 2 (the set's line 1) carries 11 trailing blanks", out)


if __name__ == "__main__":
    unittest.main()
