# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The TLE/OMM exact twins (D-406): seven shipped TLE sets and their OMM CSV twins, graded through the propagate hook
against the corpus's own reference vectors.

Run: python -m unittest tests.test_twins"""
import hashlib
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
from gpconf.runner import Runner  # noqa: E402

TWINS = os.path.join(ROOT, "derived", "propagation-twins")
VEC = os.path.join(ROOT, "vectors", "propagation-twins.json")


def sgp4_present():
    try:
        import sgp4.api  # noqa: F401
        return True
    except ImportError:
        return False


def run(parser):
    (r,) = Runner(parser, root=ROOT, fetch_hints=False).run(case_ids=["propagation-tle-omm-twins"])
    return r.status, {i.check: i for i in r.items}


class TheData(unittest.TestCase):
    def test_the_vectors_name_the_files_they_were_made_from(self):
        with open(VEC, encoding="utf-8") as f:
            v = json.load(f)
        for name, sha in v["files"].items():
            with open(os.path.join(TWINS, name), "rb") as f:
                self.assertEqual(hashlib.sha256(f.read()).hexdigest(), sha, name)
        self.assertEqual([s["norad_cat_id"] for s in v["sets"]], [25544, 20453, 69999, 100000, 100686, 100530, 270354])

    def test_each_csv_twin_reads_as_its_tle(self):
        import gpref
        _, tle, _ = gpref.read_file(os.path.join(TWINS, "twins.tle"))
        _, csv, _ = gpref.read_file(os.path.join(TWINS, "twins.csv"))
        for a, b in zip(tle, csv):
            for k in ("norad_cat_id", "epoch", "mean_motion", "eccentricity", "inclination", "ra_of_asc_node",
                      "arg_of_pericenter", "mean_anomaly", "bstar"):
                self.assertEqual(str(a[k]), str(b[k]), (a["norad_cat_id"], k))

    def test_a_parser_without_the_hook_skips(self):
        status, items = run(Reference())
        self.assertEqual({k: v.status for k, v in items.items()},
                         {"twins-tle-positions": "skip", "twins-omm-positions": "skip", "twins-tle-omm-agree": "skip"})


@unittest.skipUnless(sgp4_present(), "needs python-sgp4")
class TheCase(unittest.TestCase):
    def stand_in(self, shift_s=0.0, mm_scale=1.0, epoch_late_days=0.0, false_decay=False, refuse=False, partial=False,
                 codes_differ=False):
        """python-sgp4 with its OMM path made wrong on purpose: tsince shifted, the mean motion scaled, the EPOCH itself
        read late, a false decay, every CSV refused, or unsupported for some CSVs only."""
        import io
        from sgp4 import omm
        from sgp4.api import Satrec, WGS72
        from gpconf.adapters.sgp4_adapter import Parser

        class Wrong(Parser):
            def propagate(self, raw, fmt, tsince):
                if fmt != "csv":
                    return Parser.propagate(self, raw, fmt, tsince)
                (fields,) = list(omm.parse_csv(io.StringIO(raw.decode())))
                if refuse:
                    raise ValueError("cannot read this OMM")
                if partial and fields["NORAD_CAT_ID"] == "25544":
                    from gpconf.runner import Unsupported
                    raise Unsupported("csv")
                fields["MEAN_MOTION"] = str(float(fields["MEAN_MOTION"]) * mm_scale)
                if epoch_late_days:
                    import datetime as _dt
                    e = _dt.datetime.fromisoformat(fields["EPOCH"]) + _dt.timedelta(days=epoch_late_days)
                    fields["EPOCH"] = e.isoformat()
                s = Satrec()
                omm.initialize(s, fields)
                out = []
                for t in tsince:
                    e, r, v = s.sgp4_tsince(t - shift_s / 60.0)
                    if false_decay and t == 10080.0:
                        e = 6
                    out.append({"r": list(r), "v": list(v), "error": e} if e == 0 else {"error": e})
                return out
        return Wrong()

    def test_the_preset_passes(self):
        from gpconf.adapters.sgp4_adapter import Parser
        status, items = run(Parser())
        self.assertEqual(status, "pass-tolerance", {k: v.detail for k, v in items.items()})

    def test_an_omm_path_a_second_late_fails_the_omm_item_and_the_agreement(self):
        status, items = run(self.stand_in(shift_s=1.0))
        self.assertEqual(items["twins-tle-positions"].status, "pass")
        self.assertEqual(items["twins-omm-positions"].status, "fail")
        self.assertEqual(items["twins-tle-omm-agree"].status, "fail")

    def test_an_omm_path_with_the_mean_motion_off_fails(self):
        self.assertEqual(run(self.stand_in(mm_scale=1.0 + 1e-9))[1]["twins-omm-positions"].status, "fail")


    def test_the_epoch_read_late_fails_through_the_deep_space_sets(self):
        status, items = run(self.stand_in(epoch_late_days=1.0))   # the review of D-406's finding 1: EPOCH itself
        self.assertEqual(items["twins-omm-positions"].status, "fail")
        detail = items["twins-omm-positions"].detail
        self.assertTrue("100530" in detail or "270354" in detail, detail)

    def test_a_false_decay_fails_the_codes(self):
        self.assertIn("where the reference gives 0", run(self.stand_in(false_decay=True))[1]["twins-omm-positions"].detail)

    def test_codes_that_differ_between_renderings_fail_the_agreement(self):
        status, items = run(self.stand_in(false_decay=True))
        self.assertEqual(items["twins-tle-omm-agree"].status, "fail")
        self.assertIn("error codes differ", items["twins-tle-omm-agree"].detail)

    def test_a_refused_csv_fails_and_a_partly_unsupported_one_fails(self):
        self.assertIn("7 sets refused", run(self.stand_in(refuse=True))[1]["twins-omm-positions"].detail)
        items = run(self.stand_in(partial=True))[1]
        self.assertEqual(items["twins-omm-positions"].status, "fail")
        self.assertIn("all or none", items["twins-omm-positions"].detail)

    def test_a_two_line_hook_is_not_failed(self):
        from gpconf.adapters.sgp4_adapter import Parser
        from sgp4.api import Satrec, WGS72

        class TwoLines(Parser):
            def propagate(self, raw, fmt, tsince):
                if fmt != "tle":
                    return Parser.propagate(self, raw, fmt, tsince)
                l1, l2 = raw.decode().splitlines()   # exactly two lines, as the review's stand-in
                s = Satrec.twoline2rv(l1, l2, WGS72)
                return [dict(zip(("error", "r", "v"), s.sgp4_tsince(t))) for t in tsince]
        self.assertEqual(run(TwoLines())[1]["twins-tle-positions"].status, "pass")


if __name__ == "__main__":
    unittest.main()
