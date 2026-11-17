# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The third blind reading of 0.10.0's freeze (D-604) and the readings of its mends (D-605, D-606): the tests they
found missing. A refused list cut at three or
four keeps every refusal in details; a set answered "unsupported" alone is named; a type-4 twin that refuses is named
apart from failing steps; a name inside a longer word is no opt-in; and the findings page's captures and tree sentences
follow the reports, as its case count does.

Run: python -m unittest tests.test_third_reading_0100"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from gpconf import runner as R  # noqa: E402
from gpconf.adapters.reference import Parser as Reference  # noqa: E402
import test_failing_sets_0100 as FS  # noqa: E402


def item(r, check):
    (it,) = [i for i in r.items if i.check == check]
    return it


def sgp4_stand_in(refuse=(), unsupported=(), fmts=("tle", "csv")):
    """python-sgp4's adapter, refusing or answering "unsupported" for the named catalogs in the named formats."""
    from gpconf.adapters.sgp4_adapter import Parser

    class P(Parser):
        def propagate(self, raw, fmt, tsince):
            cat = FS.catalog_of(raw, fmt)
            if fmt in fmts and (refuse == "all" or cat in refuse):
                raise ValueError(f"refused {cat} on purpose")
            if fmt in fmts and cat in unsupported:
                raise R.Unsupported(f"not {cat}")
            return Parser.propagate(self, raw, fmt, tsince)
    return P()


def vallado_catalogs():
    from gpconf import sgp4ver
    with open(os.path.join(ROOT, "harnesses", "vallado", "reference", "SGP4-VER.TLE"), encoding="ascii") as f:
        return [str(c) for c in dict.fromkeys(e["catalog"] for e in sgp4ver.parse_ver_tle(f.read()))]


def run_vallado(parser):
    (r,) = R.Runner(parser, root=ROOT, fetch_hints=False,
                    sgp4_ver=os.path.join(ROOT, "harnesses", "vallado", "reference")).run(case_ids=["sgp4-ver-propagation"])
    return r


@unittest.skipUnless(FS.sgp4_present(), "needs python-sgp4")
class EveryRefusalInDetails(unittest.TestCase):
    """F3: a refused list cut where it is shown keeps every refusal, one by one, in details."""
    def test_twins_seven_refusals_all_in_details(self):
        (r,) = R.Runner(sgp4_stand_in(refuse="all", fmts=("csv",)), root=ROOT, fetch_hints=False).run(
            case_ids=["propagation-tle-omm-twins"])
        it = item(r, "twins-omm-positions")
        self.assertEqual(it.status, "fail")
        self.assertIn("refused in 7 sets: ", it.detail)
        self.assertIn("… and 4 more", it.detail)   # three refusals shown of seven
        self.assertTrue(it.details, it.detail[:200])
        self.assertEqual(len([d for d in it.details if "refused" in d and "on purpose" in d]), 7, it.details)

    @unittest.skipUnless(FS.vallado_present(), "needs Vallado's files (private, D-388)")
    def test_vallado_five_refusals_all_in_details_of_both_items(self):
        cats = vallado_catalogs()[:5]
        r = run_vallado(sgp4_stand_in(refuse=tuple(cats)))
        for check in ("sgp4-ver-positions", "sgp4-ver-error-codes"):
            it = item(r, check)
            self.assertEqual(it.status, "fail")
            self.assertIn(f"refused in 5 sets: {', '.join(sorted(cats, key=int))}; ", it.detail)
            self.assertTrue(it.details, (check, it.detail[:200]))
            for c in cats:
                self.assertTrue([d for d in it.details if d.startswith(f"{c}: ") and "on purpose" in d], (check, c, it.details))


@unittest.skipUnless(FS.sgp4_present(), "needs python-sgp4")
class UnsupportedSetsNamed(unittest.TestCase):
    """F4: a set answered "unsupported" while others are propagated is named, as the type-4 case names its twins."""
    def test_twins(self):
        (r,) = R.Runner(sgp4_stand_in(unsupported=("25544",), fmts=("csv",)), root=ROOT, fetch_hints=False).run(
            case_ids=["propagation-tle-omm-twins"])
        it = item(r, "twins-omm-positions")
        self.assertEqual(it.status, "fail")
        self.assertIn("unsupported in 1 set: 25544; ", it.detail)
        self.assertNotIn("unsupported in", item(r, "twins-tle-positions").detail)

    @unittest.skipUnless(FS.vallado_present(), "needs Vallado's files (private, D-388)")
    def test_vallado(self):
        last = vallado_catalogs()[-1]
        r = run_vallado(sgp4_stand_in(unsupported=(last,)))
        for check in ("sgp4-ver-positions", "sgp4-ver-error-codes"):
            it = item(r, check)
            self.assertEqual(it.status, "fail")
            self.assertIn(f"unsupported in 1 set: {last}; ", it.detail)


class TypeFourTwinRefused(unittest.TestCase):
    """A type-0 twin that refuses has no steps that failed; it is named under "refused or unsupported in"."""
    def test_a_refusing_twin_is_named_apart(self):
        import test_type4 as T4

        class TwinRefuses(T4.Exact):
            def propagate(self, raw, fmt, tsince):
                if fmt == "tle" and self.etype(raw, fmt) == 0:
                    raise ValueError("refused on purpose")
                return T4.Exact.propagate(self, raw, fmt, tsince)
        (r,) = R.Runner(TwinRefuses(), root=ROOT, fetch_hints=False).run(case_ids=["ephemeris-type-4-refused"])
        it = item(r, "type4-twins-propagate")
        self.assertEqual(it.status, "fail")
        self.assertRegex(it.detail, r"^refused or unsupported in 1 set: [^;]*\.tle; ")
        self.assertNotIn("steps fail in", it.detail)


class OptInWholeWordOnTheLeft(unittest.TestCase):
    """The name must not be the tail of a longer word."""
    def test_nonstrict_is_no_mark_for_strict(self):
        import test_freeze_mends_0100 as FM
        t = FM.OptInMarkerAndCheck()
        p, _ = t.check_row("strict", {"/repos/o/libtwo/releases/tags/7.2.0": {"body": "a nonstrict mode"}})
        self.assertTrue(any("does not name it as a word" in x for x in p), p)
        p, _ = t.check_row("strict", {"/repos/o/libtwo/releases/tags/7.2.0": {"body": "a new strict mode"}})
        self.assertEqual(p, [])


class ThePageSaysWhatItsReportsHold(unittest.TestCase):
    """The captures sentence follows classification-c's status in the reference's report, the tree
    sentence follows the export, and the case count is the report's."""
    def reports(self, classification_c):
        import test_freeze_mends_0100 as FM
        reps = FM.ThePageCountsWhatItsTableShows().reports()
        reps["reference"]["results"].append({"case": "supgp-celestrak-classification-c", "status": classification_c, "items": []})
        return reps

    def test_the_captures_sentence(self):
        import make_failures as M
        self.assertIn("ten operator-sourced launch-window captures are excluded (D-002)",
                      M.basis(self.reports("not-available"), True))
        text = M.basis(self.reports("pass"), True)
        self.assertNotIn("are excluded", text)
        self.assertIn("read the corpus's ten launch-window captures as well", text)

    def test_the_tree_sentence(self):
        import make_failures as M
        self.assertIn("graded on the public export", M.basis(self.reports("pass"), True))
        self.assertIn("graded on the private tree", M.basis(self.reports("pass"), False))

    def test_the_case_count_is_the_reports(self):
        import make_failures as M
        self.assertIn("Of 4 cases, the reference passes", M.basis(self.reports("pass"), True))


def twins_omm(bad=(), refuse=()):
    """The OMM twins item for python-sgp4 with the named sets' OMM answers moved 1 km, or refused."""
    from gpconf.adapters.sgp4_adapter import Parser

    class P(Parser):
        def propagate(self, raw, fmt, tsince):
            cat = FS.catalog_of(raw, fmt)
            if fmt == "csv" and cat in refuse:
                raise ValueError(f"refused {cat} on purpose")
            a = Parser.propagate(self, raw, fmt, tsince)
            if fmt == "csv" and cat in bad:
                a = [dict(x, r=[v + 1.0 for v in x["r"]]) if x.get("r") else x for x in a]
            return a
    (r,) = R.Runner(P(), root=ROOT, fetch_hints=False).run(case_ids=["propagation-tle-omm-twins"])
    return item(r, "twins-omm-positions")


def twin_sets():
    from gpconf import propagation as P
    return [(str(s["norad_cat_id"]), len(s["steps"])) for s in P.twins(ROOT)["sets"]]


@unittest.skipUnless(FS.sgp4_present(), "needs python-sgp4")
class TheCutEdges(unittest.TestCase):
    """D-605: details exactly when a list is cut where shown, at each edge of cut_any."""
    def test_a_set_of_bad_steps_and_one_refusal(self):
        (bad, steps), (refused, _) = twin_sets()[0], twin_sets()[1]
        self.assertEqual(steps, 6)   # six steps and the refusal's line: seven entries, one past the six shown
        it = twins_omm(bad=(bad,), refuse=(refused,))
        self.assertIn("more", it.detail)
        self.assertTrue(it.details, it.detail[:200])
        self.assertEqual(len([d for d in it.details if d.startswith(f"{bad} ")]), steps, it.details)
        self.assertEqual(len([d for d in it.details if d.startswith(f"{refused}: ")]), 1, it.details)

    def test_four_refusals_are_cut_and_kept(self):
        cats = tuple(c for c, _ in twin_sets()[:4])
        it = twins_omm(refuse=cats)
        self.assertIn("… and 1 more", it.detail)
        self.assertIsNotNone(it.details, it.detail[:200])
        self.assertEqual(sorted(d.split(":")[0] for d in it.details), sorted(cats))

    def test_three_refusals_are_not_cut(self):
        it = twins_omm(refuse=tuple(c for c, _ in twin_sets()[:3]))
        self.assertNotIn("more", it.detail)
        self.assertIsNone(it.details)


def all_layout_wrong(n):
    """A writer whose every record puts a letter in the ephemeris-type column (one misplaced field each), on n inputs."""
    import test_triage_090_writer_reader as TW
    inputs = TW.inputs(n)

    class OneFieldEach(Reference):
        def write_tle(self, record):
            l0, l1, l2 = TW.W.normalise_lines(Reference.write_tle(self, record))
            return [x for x in (l0, TW.fix(l1[:62] + "X" + l1[63:]), l2) if x is not None]
    return TW.run_writer(OneFieldEach(), inputs)[1]["tle-writer-column-layout"]


class TheWritersLayoutListKeptWhole(unittest.TestCase):
    """D-605, D-606: a record with more than three fields out of their columns is shown with three and its total,
    "… (N fields)", the form 0.9.0 released;
    details keeps every field. Exactly three is not cut; eight failing records are shown whole, nine are cut."""
    def changed(self, last):
        """The second of three records with line 1's fields from the epoch up to column `last` turned to letters."""
        import test_triage_090_writer_reader as TW
        inputs = TW.three_inputs()
        cat = inputs[1]["norad_cat_id"]

        def letters(l1, l2):
            return TW.fix(l1[:18] + "".join("X" if c.isdigit() else c for c in l1[18:last]) + l1[last:]), l2
        return cat, TW.run_writer(TW.OneRecordChanged(cat, letters), inputs)[1]["tle-writer-column-layout"]

    def test_every_misplaced_field_is_in_details(self):
        cat, it = self.changed(68)
        self.assertEqual(it.status, "fail")
        self.assertIn(" fields)", it.detail)
        n = int(it.detail.split(" fields)")[0].rsplit("… (", 1)[1])
        self.assertGreater(n, 3, it.detail)
        self.assertTrue(it.details, it.detail)
        (full,) = [d for d in it.details if d.startswith(f"id {cat}: ")]
        self.assertEqual(full.count("columns"), n, full)

    def test_exactly_three_fields_are_not_cut(self):
        for last in range(19, 69):
            cat, it = self.changed(last)
            if it.status == "fail" and it.detail.count("columns") == 3:
                break
        else:
            self.fail("no prefix of line 1 gives exactly three misplaced fields")
        self.assertNotIn("fields)", it.detail)
        self.assertNotIn("more", it.detail)
        self.assertIsNone(it.details, it.detail)

    def test_eight_records_are_not_cut_nine_are(self):
        eight, nine = all_layout_wrong(8), all_layout_wrong(9)
        self.assertEqual((eight.status, nine.status), ("fail", "fail"))
        self.assertNotIn("more", eight.detail)
        self.assertIsNone(eight.details, eight.detail)
        self.assertIn("… and 1 more", nine.detail)
        self.assertEqual(len(nine.details or []), 9, nine.detail)


if __name__ == "__main__":
    unittest.main()
