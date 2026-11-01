# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""A history-shaped answer, one catalog number with several element sets at different epochs, as Space-Track's
GP_History class answers, is graded record by record in the pivot, TLE/OMM consistency, OMM-formats-agree and presence
checks (D-344), with wrong-on-purpose adapters and twins.

The file is built at test time from the corpus's own public frozen values (the ISS record epoch-year-19xx freezes):
the TLE form written by the corpus's own writer, the OMM forms (CSV and JSON) joined here from the same fields; no
provider's bytes, so it runs in the public export. Before: each of these checks kept one copy of an id, the last the
parser returned (the first, for OMM-formats-agree), so a correct parser failed the pivot check for the other element
sets, the consistency and OMM-formats-agree checks when it returned its copies in different orders in two files, and
the element-set-zero check for the set numbered 0. And from D-344's reading: a copy beyond the other form's copies is
compared too, and a history of thousands of element sets is read in well under a second by every one of these checks.

Run: python -m unittest tests.adversarial.test_history_080"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf import reference as ref  # noqa: E402
from gpconf import tle as tlemod  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import CaseResult, Runner  # noqa: E402

with open(os.path.join(ROOT, "fixtures", "epoch-year-19xx", "expected.json"), encoding="utf-8") as _f:
    FROZEN = json.load(_f)["records"][0]["canonical"]   # ISS (ZARYA), 1998-11-20, a public frozen record
BASE = tlemod.omm_fields_from_record(FROZEN)
CSV_COLUMNS = ["OBJECT_NAME", "OBJECT_ID", "EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE",
               "ARG_OF_PERICENTER", "MEAN_ANOMALY", "EPHEMERIS_TYPE", "CLASSIFICATION_TYPE", "NORAD_CAT_ID",
               "ELEMENT_SET_NO", "REV_AT_EPOCH", "BSTAR", "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT"]
# three element sets of one object, a day apart, the first numbered 0 (a history: the same number, other epochs)
SETS = [dict(BASE, EPOCH="1998-11-20T06:49:59.999808", ELEMENT_SET_NO="0", REV_AT_EPOCH="0"),
        dict(BASE, EPOCH="1998-11-21T06:49:59.999808", ELEMENT_SET_NO="2", REV_AT_EPOCH="16"),
        dict(BASE, EPOCH="1998-11-22T06:49:59.999808", ELEMENT_SET_NO="3", REV_AT_EPOCH="32", MEAN_ANOMALY="10.0000")]


def tle_text(sets):
    return "".join("\n".join(tlemod.render(s, mantissa_mode="round", ecc_mode="truncate")) + "\n" for s in sets)


def csv_text(sets):
    return ",".join(CSV_COLUMNS) + "\r\n" + "".join(",".join(s[k] for k in CSV_COLUMNS) + "\r\n" for s in sets)


def json_text(sets):
    def value(k, v):
        if k in ("NORAD_CAT_ID", "ELEMENT_SET_NO", "REV_AT_EPOCH", "EPHEMERIS_TYPE"):
            return int(v)
        return v if k in ("OBJECT_NAME", "OBJECT_ID", "EPOCH", "CLASSIFICATION_TYPE") else float(v)
    return json.dumps([{k: value(k, s[k]) for k in CSV_COLUMNS} for s in sets])


def long_history(n):
    """n element sets of the ISS, one an orbit (97 minutes) apart, each numbered and counted on."""
    t0 = dt.datetime(1998, 11, 20, 6, 49, 59, 999808)
    return [dict(BASE, EPOCH=(t0 + dt.timedelta(minutes=97 * i)).strftime("%Y-%m-%dT%H:%M:%S.%f"),
                 ELEMENT_SET_NO=str(i % 999 + 1), REV_AT_EPOCH=str(i + 1)) for i in range(n)]


TLE, CSV, JSON = tle_text(SETS), csv_text(SETS), json_text(SETS)


def answering(tle_how=None, omm_how=None):
    """The reference's records, the TLE copies and the OMM copies each passed through their own rearrangement."""
    class Adapter(Reference):
        def parse(self, raw, fmt):
            out = [r for r in super().parse(raw, fmt) if "_refused" not in r]
            how = tle_how if fmt in ("tle", "2le") else omm_how
            return how(out) if how else out
    return Adapter()


# a correct parser that returns its TLE copies newest first and its OMM copies in yet another order, so the last copy
# of each form is a different element set (the old check compared those two alone)
OUT_OF_ORDER = answering(lambda rs: rs[::-1], lambda rs: [rs[2], rs[0], rs[1]])


def JsonAnswering(how):
    """The reference's records, its JSON copies alone passed through how."""
    class Adapter(Reference):
        def parse(self, raw, fmt):
            out = [r for r in super().parse(raw, fmt) if "_refused" not in r]
            return how(out) if fmt == "json" else out
    return Adapter()


class AHistoryIsGradedRecordByRecord(unittest.TestCase):

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-history-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def run_case(self, parser, case="baseline-iss-five-formats", files=(("tle", TLE), ("csv", CSV))):
        """The case run on the ISS files given, in the ISS baseline's folder, which the pairs cases read too."""
        raw = os.path.join(self.data, "fixtures", "baseline-iss-five-formats", "raw")
        os.makedirs(raw, exist_ok=True)
        for ext, text in files:
            with open(os.path.join(raw, f"iss.{ext}"), "w", encoding="utf-8", newline="") as f:
                f.write(text)
        res = Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=[case])[0]
        return {(i.check, os.path.basename(i.file or "")): i for i in res.items}

    def iss(self, parser):
        return self.run_case(parser)

    def consistency(self, got):
        return [i for (c, _), i in got.items() if c == "tle-values-match-omm-within-tle-precision"]

    def zero(self, parser):
        """The element-set-zero presence check on the history's CSV. The one case that lists it reads a launch-window
        capture only from the maintainer's copy (D-229), so the check is driven here as run_gp_like drives it: the
        runner's own reading of the parser's answer, and the reference reader's records of the same bytes."""
        path = os.path.join(self.data, "history.csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(CSV)
        runner = Runner(parser, root=ROOT, data=self.data, fetch_hints=False)
        res = CaseResult("history", "history")
        runner.check_presence(res, path, runner.parse(path, "csv"), ref.read_file(path)[1], {"element-set-zero-and-rev-one"})
        (item,) = [i for i in res.items if i.check == "element-set-zero-and-rev-one"]
        return item

    def test_the_file_is_a_history(self):
        lines = TLE.splitlines()
        self.assertEqual(len(lines), 9)
        self.assertEqual({l[2:7] for l in lines if l.startswith(("1 ", "2 "))}, {"25544"})
        self.assertEqual(len({l[18:32] for l in lines if l.startswith("1 ")}), 3)

    def correct(self):
        return (("file order", Reference()), ("out of order", OUT_OF_ORDER))

    def test_a_correct_parser_passes_the_pivot_check(self):
        for order, parser in self.correct():
            with self.subTest(order=order):
                item = self.iss(parser)[("two-digit-year-pivot", "iss.tle")]
                self.assertEqual(item.status, "pass", item.detail)

    def test_a_correct_parser_passes_the_consistency_check(self):
        for order, parser in self.correct():
            with self.subTest(order=order):
                got = self.iss(parser)
                consistency = [i for (c, _), i in got.items() if c == "tle-values-match-omm-within-tle-precision"]
                self.assertEqual([i.status for i in consistency], ["pass"], [i.detail for i in consistency])
                self.assertIn("3 TLE/OMM pairs consistent", consistency[0].detail)

    def test_a_correct_parser_passes_the_presence_check(self):
        for order, parser in self.correct():
            with self.subTest(order=order):
                zero = self.zero(parser)
                self.assertEqual(zero.status, "pass", zero.detail)

    def test_the_twins_each_fail_the_check_that_reads_what_they_got_wrong(self):
        def one_epoch(rs):   # every TLE copy given the first set's epoch
            return [dict(r, epoch=rs[0]["epoch"]) for r in rs]

        def crossed(rs):     # the OMM copy of the third set given the second's mean anomaly
            third = next(r for r in rs if r["element_set_no"] == 3)
            second = next(r for r in rs if r["element_set_no"] == 2)
            return [dict(r, mean_anomaly=second["mean_anomaly"]) if r is third else r for r in rs]

        def numbered_one(rs):   # the set numbered 0 returned as 1
            return [dict(r, element_set_no=1) if r["element_set_no"] == 0 else r for r in rs]
        got = self.iss(answering(one_epoch))
        self.assertEqual(got[("two-digit-year-pivot", "iss.tle")].status, "fail")
        got = self.iss(answering(None, crossed))
        consistency = [i for (c, _), i in got.items() if c == "tle-values-match-omm-within-tle-precision"]
        self.assertEqual([i.status for i in consistency], ["fail"])
        self.assertIn("mean_anomaly", consistency[0].detail)
        zero = self.zero(answering(numbered_one, numbered_one))
        self.assertEqual(zero.status, "fail", zero.detail)

    def test_the_omm_files_agree_record_by_record(self):
        def crossed(rs):     # the JSON copy of the third set given the second's mean anomaly
            second = next(r for r in rs if r["element_set_no"] == 2)
            return [dict(r, mean_anomaly=second["mean_anomaly"]) if r["element_set_no"] == 3 else r for r in rs]
        both = (("csv", CSV), ("json", JSON))
        for order, parser in (("file order", Reference()), ("JSON newest first", JsonAnswering(lambda rs: rs[::-1]))):
            with self.subTest(order=order):
                item = self.run_case(parser, files=both)[("omm-formats-agree", "iss-live")]
                self.assertEqual(item.status, "pass", item.detail)
                self.assertIn("2 OMM renderings agree on 3 records", item.detail)
        item = self.run_case(JsonAnswering(crossed), files=both)[("omm-formats-agree", "iss-live")]
        self.assertEqual(item.status, "fail", item.detail)
        self.assertIn("id 25544 mean_anomaly (copy 3 of 3 in iss.csv)", item.detail)

    def test_a_copy_beyond_the_other_forms_is_compared_too(self):
        """The pairs case tle-vs-omm-precision-loss, whose one judge is the consistency check, on the history and on the
        ISS held once: a wrong copy a parser adds fails it, and so does a set it drops in one form, the other form's copy
        compared with the nearest copy left (the first form of D-344 left such a copy uncompared, and passed them)."""
        def plus7(r):
            return dict(r, mean_anomaly=str(Decimal(str(r["mean_anomaly"])) + 7))
        got = self.run_case(Reference(), "tle-vs-omm-precision-loss")
        self.assertEqual([i.status for i in self.consistency(got)], ["pass"], [i.detail for i in self.consistency(got)])
        self.assertIn("3 TLE/OMM pairs consistent", self.consistency(got)[0].detail)
        for name, parser in (("a fourth TLE copy, the third set wrong", answering(lambda rs: rs + [plus7(rs[2])])),
                             ("the TLE third set dropped", answering(lambda rs: rs[:2]))):
            with self.subTest(parser=name):
                got = self.run_case(parser, "tle-vs-omm-precision-loss")
                self.assertEqual([i.status for i in self.consistency(got)], ["fail"], [i.detail for i in self.consistency(got)])
        once = (("tle", tle_text(SETS[:1])), ("csv", csv_text(SETS[:1])))
        got = self.run_case(answering(lambda rs: rs + [plus7(rs[0])]), "tle-vs-omm-precision-loss", once)
        self.assertEqual([i.status for i in self.consistency(got)], ["fail"], [i.detail for i in self.consistency(got)])
        got = self.run_case(Reference(), "tle-vs-omm-precision-loss", once)   # its twin
        self.assertEqual([i.status for i in self.consistency(got)], ["pass"], [i.detail for i in self.consistency(got)])

    def test_a_long_history_is_read_in_well_under_a_second(self):
        """12,000 element sets of one object: the pivot check took minutes (each record against every copy), and so did
        the consistency check for a parser that returns no element set numbers (the first mend's pairing), and the
        presence checks were quadratic for a wrong parser; each of the three is timed alone here."""
        sets = long_history(12000)
        tp, cp = os.path.join(self.data, "long.tle"), os.path.join(self.data, "long.csv")
        for path, text in ((tp, tle_text(sets)), (cp, csv_text([dict(s, OBJECT_NAME="UNKNOWN") for s in sets]))):
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        runner = Runner(Reference(), root=ROOT, data=self.data, fetch_hints=False)
        trefs, crefs = ref.read_file(tp)[1], ref.read_file(cp)[1]
        tparsed, cparsed = runner.parse(tp, "tle"), runner.parse(cp, "csv")
        bare = [{k: v for k, v in r.items() if k not in ("element_set_no", "rev_at_epoch")} for r in tparsed[::-1]]
        renamed = [dict(r, object_name="X") for r in cparsed]
        res = CaseResult("history", "history")
        for name, check in (
                ("pivot", lambda: runner.check_tle_lines(res, tp, tparsed, trefs, {"two-digit-year-pivot"})),
                ("consistency, no counters, reversed", lambda: runner.check_set_relations(
                    res, {"sets": {}}, "long", {tp: ("ok", "tle", bare, trefs), cp: ("ok", "csv", cparsed, crefs)},
                    {"tle-values-match-omm-within-tle-precision"})),
                ("presence, a wrong parser", lambda: runner.check_presence(res, cp, renamed, crefs, {"object-name-unknown-literal"}))):
            with self.subTest(check=name):
                t = time.monotonic()
                check()
                self.assertLess(time.monotonic() - t, 3.0, name)
        self.assertEqual([(i.check, i.status) for i in res.items],
                         [("two-digit-year-pivot", "pass"), ("tle-values-match-omm-within-tle-precision", "pass"),
                          ("object-name-unknown-literal", "fail")], [i.detail for i in res.items])


if __name__ == "__main__":
    unittest.main()
