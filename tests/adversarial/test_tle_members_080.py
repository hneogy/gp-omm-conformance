# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Every TLE member of a set, its .tle and its .2le, is compared with the set's OMM records in items of its own (D-345,
the 0.8.0 plan's 2d, D-318's stated limit), with wrong-on-purpose adapters and twins.

Before: the set checks compared the first TLE member alone, so a set's .2le was never compared with its OMM records,
not even where the .tle was missing. A recapture, another fetch of the TLE answer at a later hour, is not a
member: its records are the provider's at that later time.

The files are built at test time from the ISS record epoch-year-19xx freezes (no provider's bytes, so the module runs
in the public export).

Run: python -m unittest tests.adversarial.test_tle_members_080"""
import glob
import json
import os
import shutil
import sys
import tempfile
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from gpconf import reference as ref  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import CaseResult, Runner  # noqa: E402
from tests.adversarial.test_history_080 import SETS, csv_text, json_text, tle_text  # noqa: E402

ONE = SETS[:1]   # the ISS once
TLE = tle_text(ONE)
TWO_LE = "\n".join(TLE.splitlines()[1:]) + "\n"   # the same set without its name line
CSV = csv_text(ONE)
JSON = json_text(ONE)
CONSISTENCY = "tle-values-match-omm-within-tle-precision"
COUNTS = ("tle-count-equals-omm-count-below-100000", "tle-format-omits-ids-above-99999")


def answering(how, fmts=("2le",)):
    """The reference's records, those of the formats named passed through how."""
    class Adapter(Reference):
        def parse(self, raw, fmt):
            out = [r for r in super().parse(raw, fmt) if "_refused" not in r]
            return how(out) if fmt in fmts else out
    return Adapter()


def mean_anomaly_off(rs):
    return [dict(r, mean_anomaly=str(Decimal(str(r["mean_anomaly"])) + 7)) for r in rs]


def mean_motion_dot_doubled(rs):
    return [dict(r, mean_motion_dot=str(Decimal(str(r["mean_motion_dot"])) * 2)) for r in rs]


class EveryTleMemberOfASetIsCompared(unittest.TestCase):

    def setUp(self):
        self.data = tempfile.mkdtemp(prefix="gpconf-tle-members-")

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def write(self, files):
        raw = os.path.join(self.data, "fixtures", "baseline-iss-five-formats", "raw")
        os.makedirs(raw, exist_ok=True)
        paths = {}
        for name, text in files:
            paths[name] = os.path.join(raw, name)
            with open(paths[name], "w", encoding="utf-8", newline="") as f:
                f.write(text)
        return paths

    def iss(self, parser, files=(("iss.tle", TLE), ("iss.2le", TWO_LE), ("iss.csv", CSV))):
        self.write(files)
        res = Runner(parser, root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["baseline-iss-five-formats"])[0]
        return {i.file: i for i in res.items if i.check == CONSISTENCY}

    def test_a_correct_parser_passes_both_members(self):
        got = self.iss(Reference())
        self.assertEqual(sorted(got), ["iss-live", "iss-live: iss.2le"])
        for label, item in got.items():
            with self.subTest(member=label):
                self.assertEqual(item.status, "pass", item.detail)
                self.assertIn("1 TLE/OMM pair consistent", item.detail)

    def test_a_wrong_2le_reading_fails_its_own_item(self):
        got = self.iss(answering(mean_anomaly_off))
        self.assertEqual(got["iss-live"].status, "pass", got["iss-live"].detail)   # the .tle, read right
        self.assertEqual(got["iss-live: iss.2le"].status, "fail", got["iss-live: iss.2le"].detail)
        self.assertIn("mean_anomaly", got["iss-live: iss.2le"].detail)
        twin = self.iss(answering(lambda rs: rs, ("2le",)))   # its twin: the same adapter, the .2le read right
        self.assertEqual([i.status for i in twin.values()], ["pass", "pass"])

    def test_a_set_whose_tle_is_missing_is_compared_by_its_2le(self):
        """D-318's limit: a set with a .2le beside a missing .tle was not compared by its .2le."""
        got = self.iss(Reference(), (("iss.2le", TWO_LE), ("iss.csv", CSV)))
        self.assertEqual(sorted(got), ["iss-live: iss.2le"])
        self.assertEqual(got["iss-live: iss.2le"].status, "pass", got["iss-live: iss.2le"].detail)
        got = self.iss(answering(mean_anomaly_off), (("iss.2le", TWO_LE), ("iss.csv", CSV)))
        self.assertEqual(got["iss-live: iss.2le"].status, "fail", got["iss-live: iss.2le"].detail)

    def drive(self, parser, files, active=COUNTS, declined=()):
        """The set checks driven as run_gp_like drives them: the runner's reading of each file the parser answers, the
        reference reader's records of the same bytes; a missing file, a file the parser returns nothing of (parse-error,
        D-144) and a format it declines, each as the runner marks them."""
        paths = self.write(files)
        runner = Runner(parser, root=ROOT, data=self.data, fetch_hints=False)
        state = {}
        missing = os.path.join(os.path.dirname(paths["iss.csv"]), "iss.tle")
        if "iss.tle" not in paths:
            state[missing] = ("missing", "tle", None, [])
        for name, path in paths.items():
            fmt, refrecs = name.rsplit(".", 1)[1], ref.read_file(path)[1]
            parsed = None if fmt in declined else runner.parse(path, fmt)
            state[path] = (("unsupported", fmt, None, refrecs) if fmt in declined else
                           ("parse-error", fmt, None, refrecs) if not parsed and refrecs else ("ok", fmt, parsed, refrecs))
        order = [missing if "iss.tle" not in paths else paths["iss.tle"]] + [p for n, p in paths.items() if n != "iss.tle"]
        res = CaseResult("iss", "iss")
        runner.check_set_relations(res, {"sources": {}}, "iss-live", {p: state[p] for p in order}, set(active))
        return {(i.check, i.file): i for i in res.items}

    def test_the_count_checks_read_every_member(self):
        got = self.drive(Reference(), (("iss.2le", TWO_LE), ("iss.csv", CSV)))
        for c in COUNTS:
            with self.subTest(check=c):
                self.assertEqual(got[(c, "iss-live")].status, "not-exercised", got[(c, "iss-live")].detail)   # the .tle missing, as before
                self.assertEqual(got[(c, "iss-live: iss.2le")].status, "pass", got[(c, "iss-live: iss.2le")].detail)
        both = (("iss.tle", TLE), ("iss.2le", TWO_LE), ("iss.csv", CSV))
        got = self.drive(answering(lambda rs: []), both)
        twin = self.drive(Reference(), both)
        for c in COUNTS:   # a parser that reads the .2le as nothing fails its member's items, the .tle's passing
            with self.subTest(check=c, parser="nothing from the .2le"):
                self.assertEqual(got[(c, "iss-live")].status, "pass", got[(c, "iss-live")].detail)
                self.assertEqual(got[(c, "iss-live: iss.2le")].status, "fail", got[(c, "iss-live: iss.2le")].detail)
                self.assertEqual([twin[(c, label)].status for label in ("iss-live", "iss-live: iss.2le")], ["pass", "pass"])
        got = self.drive(Reference(), both, declined=("2le",))   # a declined second member says which format it was
        self.assertIn("parser reports 2le unsupported", got[(COUNTS[0], "iss-live: iss.2le")].detail)

    def test_the_mean_motion_dot_check_reads_every_member(self):
        both = (("iss.tle", TLE), ("iss.2le", TWO_LE), ("iss.csv", CSV))
        got = self.drive(answering(mean_motion_dot_doubled), both, active=("mmdot-is-tle-field-value",))
        self.assertEqual(got[("mmdot-is-tle-field-value", "iss-live")].status, "pass")
        self.assertEqual(got[("mmdot-is-tle-field-value", "iss-live: iss.2le")].status, "fail",
                         got[("mmdot-is-tle-field-value", "iss-live: iss.2le")].detail)
        twin = self.drive(Reference(), both, active=("mmdot-is-tle-field-value",))
        self.assertEqual({i.status for i in twin.values()}, {"pass"})

    def test_each_member_is_compared_with_the_first_omm_file_the_parser_read(self):
        """The JSON copy wrong: compared with the CSV, the first OMM file, both members pass this check (the values item
        and omm-formats-agree are the JSON's judges); with the CSV declined, the JSON is the first read, and both fail."""
        files = (("iss.tle", TLE), ("iss.2le", TWO_LE), ("iss.csv", CSV), ("iss.json", JSON))
        wrong_json = answering(mean_anomaly_off, ("json",))
        got = self.drive(wrong_json, files, active=(CONSISTENCY,))
        self.assertEqual({i.status for i in got.values()}, {"pass"}, [i.detail for i in got.values()])
        got = self.drive(wrong_json, files, active=(CONSISTENCY,), declined=("csv",))
        self.assertEqual([got[(CONSISTENCY, label)].status for label in ("iss-live", "iss-live: iss.2le")], ["fail", "fail"])

    def test_no_set_lists_a_recapture_first(self):
        """The rule takes a set's first TLE file as a member whatever it is, so no set lists a recapture before its
        original: each recapture names a file of its own set, listed before it."""
        for path in sorted(glob.glob(os.path.join(ROOT, "fixtures", "*", "expected.json"))):
            with open(path, encoding="utf-8") as f:
                exp = json.load(f)
            recapture_of = {os.path.basename(p): s.get("recapture_of") for p, s in exp.get("sources", {}).items()}
            for name, s in exp.get("sets", {}).items():
                files = s["files"]
                tles = [b for b in files if b.endswith((".tle", ".2le"))]
                with self.subTest(case=os.path.basename(os.path.dirname(path)), set=name):
                    if tles:
                        self.assertIsNone(recapture_of.get(tles[0]), tles[0])
                    for i, b in enumerate(files):
                        if recapture_of.get(b):
                            self.assertIn(recapture_of[b], files[:i], b)

    def test_a_recapture_is_not_a_member(self):
        """A recapture holding other records than the OMM set is not compared with it, for any parser."""
        later = tle_text([dict(SETS[0], NORAD_CAT_ID="25545")])   # the provider's answer at a later time, another object
        paths = self.write((("iss.tle", TLE), ("iss-recapture.tle", later), ("iss.csv", CSV)))
        runner = Runner(Reference(), root=ROOT, data=self.data, fetch_hints=False)
        files = {p: ("ok", n.rsplit(".", 1)[1], runner.parse(p, "tle" if n.endswith(".tle") else "csv"), ref.read_file(p)[1])
                 for n, p in paths.items()}
        res = CaseResult("iss", "iss")
        runner.check_set_relations(res, {"sources": {paths["iss-recapture.tle"]: {"recapture_of": "iss.tle"}}}, "iss-live", files,
                                   set(COUNTS) | {CONSISTENCY})
        self.assertEqual(sorted({i.file for i in res.items}), ["iss-live"])
        self.assertEqual({i.status for i in res.items}, {"pass"}, [i.detail for i in res.items])
        res = CaseResult("iss", "iss")   # its twin: the same file named as no recapture is a member, and differs
        runner.check_set_relations(res, {"sources": {}}, "iss-live", files, set(COUNTS) | {CONSISTENCY})
        self.assertIn("fail", {i.status for i in res.items if i.file == "iss-live: iss-recapture.tle"})


if __name__ == "__main__":
    unittest.main()
