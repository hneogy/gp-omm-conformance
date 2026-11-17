# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""A propagation detail names every failing set before its list of steps, so a cut list cannot hide a set (the owner's
ruling, D-593; found while checking GPKit 2.0.0 against gpconf 0.9.0: 23333 fell outside the six steps shown after 20413's).
Each test here fails if any set that fails is missing from the item's text. No status changes: only the words.

Run: python -m unittest tests.test_failing_sets_0100"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import runner as R  # noqa: E402


def sgp4_present():
    try:
        import sgp4.api  # noqa: F401
        return True
    except ImportError:
        return False


def vallado_present():
    ref = os.path.join(ROOT, "harnesses", "vallado", "reference")
    return all(os.path.exists(os.path.join(ref, f)) for f in ("SGP4-VER.TLE", "tcppver.out"))


def catalog_of(raw, fmt):
    """The catalog number a propagate call is for: from TLE line 1, or the CSV's NORAD_CAT_ID."""
    text = raw.decode("utf-8", "replace")
    if fmt == "tle":
        from gpconf.tle import from_alpha5
        line1 = [l for l in text.splitlines() if l.startswith("1 ")][0]
        return str(from_alpha5(line1[2:7]))   # the catalog field may be Alpha-5 (270354 is T0354)
    import csv
    import io
    (row,) = list(csv.DictReader(io.StringIO(text)))
    return str(int(row["NORAD_CAT_ID"]))


def shifting(base, wrong):
    """A propagator whose answers for some sets are moved 1 km: wrong maps a catalog to the step indexes moved ("all"
    for every step)."""
    class Shifted(type(base)):
        def propagate(self, raw, fmt, tsince):
            out = type(base).propagate(self, raw, fmt, tsince)
            which = wrong.get(catalog_of(raw, fmt))
            if which is None:
                return out
            moved = []
            for i, s in enumerate(out):
                if (which == "all" or i in which) and s.get("r") is not None:
                    s = dict(s, r=[s["r"][0] + 1.0, s["r"][1], s["r"][2]])
                moved.append(s)
            return moved
    return Shifted()


class Helper(unittest.TestCase):
    def test_the_opening_names_every_set_in_number_order(self):
        self.assertEqual(R.failing_sets(["23333", "20413", "20413"]), "steps fail in 2 sets: 20413, 23333; ")
        self.assertEqual(R.failing_sets([]), "")
        self.assertEqual(R.failing_sets(["b.tle", "a.tle"], "fails in"), "fails in 2 sets: a.tle, b.tle; ")
        self.assertEqual(R.failing_sets(["9", "10"]), "steps fail in 2 sets: 9, 10; ")


def failing_sets_named(test, item):
    """Every set behind the item's failing entries is named before its list (the whole list is in details when cut)."""
    entries = item.details or [e for e in item.detail.split("; ")]
    sets = {e.split()[0].rstrip(":,") for e in entries if e and e.split()[0].rstrip(":,").isdigit()}
    test.assertTrue(sets, item.detail)
    opening = item.detail.split("; ")[0]
    for s in sets:
        test.assertIn(s, opening, f"set {s} fails but the text's opening does not name it: {item.detail[:300]}")
    return sets


@unittest.skipUnless(sgp4_present(), "needs python-sgp4")
class TheTwins(unittest.TestCase):
    def test_a_set_failing_one_step_after_another_failing_six_is_named(self):
        from gpconf.adapters.sgp4_adapter import Parser
        p = shifting(Parser(), {"25544": "all", "270354": [5]})   # 6 steps of the first set, then 1 of the last
        (r,) = R.Runner(p, root=ROOT, fetch_hints=False).run(case_ids=["propagation-tle-omm-twins"])
        for check in ("twins-tle-positions", "twins-omm-positions"):
            (item,) = [i for i in r.items if i.check == check]
            self.assertEqual(item.status, "fail")
            self.assertEqual(failing_sets_named(self, item), {"25544", "270354"})
            self.assertIn("steps fail in 2 sets: 25544, 270354; ", item.detail)
            self.assertIn("… and 1 more", item.detail)   # the seventh entry, 270354's, is past the six shown

    def test_a_correct_propagator_gets_no_opening(self):
        from gpconf.adapters.sgp4_adapter import Parser
        (r,) = R.Runner(Parser(), root=ROOT, fetch_hints=False).run(case_ids=["propagation-tle-omm-twins"])
        self.assertTrue(all("steps fail in" not in i.detail for i in r.items), [i.detail[:80] for i in r.items])


class TypeFour(unittest.TestCase):
    """The type-4 case: its sets are files (one type-4 file and its type-0 twin per format), named the same way."""
    def stand_in(self):
        sys.path.insert(0, os.path.join(ROOT, "tests"))
        import test_type4 as T4

        class Broken(T4.Exact):
            TYPE4 = "propagate"   # every type-4 set propagated as SGP4: a failure per format

            def propagate(self, raw, fmt, tsince):
                out = T4.Exact.propagate(self, raw, fmt, tsince)
                if self.etype(raw, fmt) == 4:
                    return out
                return [dict(x, r=[x["r"][0] + 1.0, x["r"][1], x["r"][2]]) if x.get("r") else x for x in out]
        return Broken()

    def test_every_failing_file_is_named(self):
        (r,) = R.Runner(self.stand_in(), root=ROOT, fetch_hints=False).run(case_ids=["ephemeris-type-4-refused"])
        items = {i.check: i for i in r.items}
        for check in ("type4-not-propagated", "type4-twins-propagate"):
            item = items[check]
            self.assertEqual(item.status, "fail", item.detail[:200])
            entries = item.details or item.detail.split("; ")
            files = {e.split()[0].rstrip(":,") for e in entries if e.split() and "." in e.split()[0]}
            self.assertGreater(len(files), 1, item.detail[:300])
            opening = item.detail.split("; ")[0]
            for f in files:
                self.assertIn(f, opening, f"{check}: {f} fails but the opening does not name it: {item.detail[:300]}")


@unittest.skipUnless(sgp4_present() and vallado_present(), "needs python-sgp4 and Vallado's files (private, D-388)")
class Vallado(unittest.TestCase):
    def test_every_failing_set_is_named_however_many_steps_come_first(self):
        from gpconf import sgp4ver
        from gpconf.adapters.sgp4_adapter import Parser
        with open(os.path.join(ROOT, "harnesses", "vallado", "reference", "SGP4-VER.TLE"), encoding="ascii") as f:
            cats = list(dict.fromkeys(e["catalog"] for e in sgp4ver.parse_ver_tle(f.read())))
        first, last = str(cats[0]), str(cats[-1])
        (r,) = R.Runner(shifting(Parser(), {first: "all", last: [0]}), root=ROOT, fetch_hints=False,
                        sgp4_ver=os.path.join(ROOT, "harnesses", "vallado", "reference")).run(case_ids=["sgp4-ver-propagation"])
        (item,) = [i for i in r.items if i.check == "sgp4-ver-positions"]
        self.assertEqual(item.status, "fail")
        self.assertEqual(failing_sets_named(self, item), {first, last})


if __name__ == "__main__":
    unittest.main()
