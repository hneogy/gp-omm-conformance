# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The second blind reading of 0.10.0's freeze move (D-593): the tests it found missing. Each catches a fault the
reading's mutants showed no test caught: a set failing only on error codes, a refused set, a values item losing its
full list, and the findings page counting passes without passes within tolerance; with them, the full list on the
other items, the opt-in marker's negation and short names, and a release body unreadable beside a readable changelog.

Run: python -m unittest tests.test_freeze_mends_0100"""
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


def sgp4_present():
    return FS.sgp4_present()


def item(r, check):
    (it,) = [i for i in r.items if i.check == check]
    return it


@unittest.skipUnless(sgp4_present(), "needs python-sgp4")
class CodeOnlyAndRefusedSets(unittest.TestCase):
    """Faults A and B: a set whose only failures are error codes, and a refused set, are named in the opening."""
    def stand_in(self, codes_for=(), refuse=()):
        from gpconf.adapters.sgp4_adapter import Parser

        class P(Parser):
            def propagate(self, raw, fmt, tsince):
                cat = FS.catalog_of(raw, fmt)
                if cat in refuse:
                    raise ValueError("refused on purpose")
                out = Parser.propagate(self, raw, fmt, tsince)
                if cat in codes_for:   # the last step answers an error code where the reference propagates
                    out = out[:-1] + [{"error": 6}]
                return out
        return P()

    def test_twins_a_set_failing_only_on_codes_is_named(self):
        (r,) = R.Runner(self.stand_in(codes_for=("69999",)), root=ROOT, fetch_hints=False).run(case_ids=["propagation-tle-omm-twins"])
        it = item(r, "twins-omm-positions")
        self.assertEqual(it.status, "fail")
        self.assertIn("steps fail in 1 set: 69999; ", it.detail)

    def test_twins_a_refused_set_is_named_apart(self):
        (r,) = R.Runner(self.stand_in(refuse=("100686",)), root=ROOT, fetch_hints=False).run(case_ids=["propagation-tle-omm-twins"])
        it = item(r, "twins-omm-positions")
        self.assertEqual(it.status, "fail")
        self.assertIn("refused in 1 set: 100686; ", it.detail)
        self.assertNotIn("steps fail in", it.detail)   # a refused set has no steps that failed

    @unittest.skipUnless(FS.vallado_present(), "needs Vallado's files (private, D-388)")
    def test_vallado_a_refused_set_is_named_apart(self):
        from gpconf import sgp4ver
        with open(os.path.join(ROOT, "harnesses", "vallado", "reference", "SGP4-VER.TLE"), encoding="ascii") as f:
            last = str(sgp4ver.parse_ver_tle(f.read())[-1]["catalog"])
        (r,) = R.Runner(self.stand_in(refuse=(last,)), root=ROOT, fetch_hints=False,
                        sgp4_ver=os.path.join(ROOT, "harnesses", "vallado", "reference")).run(case_ids=["sgp4-ver-propagation"])
        it = item(r, "sgp4-ver-positions")
        self.assertEqual(it.status, "fail")
        self.assertIn(f"refused in 1 set: {last}; ", it.detail)


class TheFullListOnOtherItems(unittest.TestCase):
    """Fault C and the reader's other items: a cut values list, and the invariant on every item of a real run."""
    def wrong_values(self):
        class P(Reference):
            def parse(self, raw, fmt):
                out = Reference.parse(self, raw, fmt)
                return [dict(r, inclination=float(r["inclination"]) + 1.0) if "inclination" in r and r.get("inclination") is not None
                        else r for r in out]
        return P()

    def test_a_values_item_cut_at_twelve_carries_every_finding(self):
        (r,) = R.Runner(self.wrong_values(), root=ROOT, fetch_hints=False).run(case_ids=["alpha5-tle-derived"])
        cut_items = [i for i in r.items if i.check == "values" and "… and" in i.detail]
        self.assertTrue(cut_items, [i.detail[:120] for i in r.items if i.check == "values"])
        for it in cut_items:
            self.assertTrue(it.details, it.detail[:120])
            n_more = int(it.detail.split("… and ")[1].split(" more")[0])
            self.assertEqual(len(it.details), 12 + n_more, it.detail[:160])

    def test_every_cut_detail_in_a_real_run_carries_its_list(self):
        """For every item whose detail says "… and N more", details is present and N longer than what was shown."""
        from gpconf.adapters.naive import Parser as Naive
        for parser in (Naive(), self.wrong_values()):
            for r in R.Runner(parser, root=ROOT, fetch_hints=False).run():
                for it in r.items:
                    if "… and " in it.detail and " more" in it.detail.split("… and ")[1][:20]:
                        self.assertTrue(it.details, (r.case_id, it.check, it.detail[:160]))


class CorruptInputSurplusCopies(unittest.TestCase):
    """The corrupt-input case's surplus-copies branch (an id returned more than once from the unedited file): its full
    list must reach details. In 0.10.0's first freeze a local name hid the helper there, a latent error no test reached
    (D-593's follow-up)."""
    def test_surplus_copies_from_the_unedited_file_are_reported_not_crashed(self):
        class Twice(Reference):
            def parse(self, raw, fmt):
                out = Reference.parse(self, raw, fmt)
                return out + [dict(r) for r in out if "norad_cat_id" in r]
        (r,) = R.Runner(Twice(), root=ROOT, fetch_hints=False).run(case_ids=["corrupt-input"])
        surplus = [i for i in r.items if i.check == "values" and "(D-311)" in i.detail]
        self.assertTrue(surplus, [(i.check, i.status, i.detail[:100]) for i in r.items][:12])
        self.assertTrue(all(i.status == "fail" for i in surplus))
        self.assertFalse([i for i in r.items if "internal error" in i.detail.lower() or "typeerror" in i.detail.lower()],
                         "the runner raised inside the case")


class ThePageCountsWhatItsTableShows(unittest.TestCase):
    """Fault E: the findings page's figures count passes within tolerance with passes, as its table does."""
    def reports(self):
        def rep(statuses):
            summary = {k: 0 for k in R.CASE_STATUSES}
            summary["cases"] = len(statuses)
            for s in statuses:
                summary[s] += 1
            return {"generated_at": "now", "gpconf": "x", "corpus_version": "x", "parser": "p", "summary": summary,
                    "platform": {"system": "TestOS-1", "python": "3.12.0"}, "preset": {"found": "2.27"},
                    "results": [{"case": f"c{k}", "status": s, "items": []} for k, s in enumerate(statuses)]}
        return {"reference": rep(["pass", "pass-tolerance", "pass", "skip"]), "naive": rep(["fail", "fail", "pass", "skip"]),
                "sgp4": rep(["pass", "fail", "pass-tolerance", "skip"])}

    def test_the_figures_count_pass_and_pass_within_tolerance(self):
        import make_failures as M
        reps = self.reports()
        text = M.basis(reps, True)
        self.assertIn("the reference passes 3, the naive adapter fails 2 and python-sgp4 fails 1", text)

    def test_the_platform_line_comes_from_the_reports(self):
        import make_failures as M
        reps = self.reports()
        self.assertEqual(M.platform_line(reps), "Platform, as the reports record it: TestOS-1; Python 3.12.0; python-sgp4 2.27.")
        reps["naive"]["platform"] = {"system": "OtherOS", "python": "3.9.1"}
        self.assertIn("the reports record different platforms", M.platform_line(reps))

    def test_the_c9_note_names_what_this_run_saw(self):
        import make_failures as M
        reps = self.reports()
        reps["sgp4"]["results"].append({"case": "corrupt-input", "status": "fail", "items": [
            {"check": "parse", "status": "fail", "file": "derived/corrupt-input/c9-letter-in-epoch-first.tle",
             "detail": "the parser returned a value the runner cannot read: bstar = nan is not a finite number (D-325)"}]})
        self.assertIn("it returned bstar NaN in this run, and was seen to return 0.0 on macOS arm64", M.basis(reps, True))
        reps["sgp4"]["results"][-1]["items"][0]["detail"] = "built a record from the corrupt input: bstar = Decimal('0.0'), from the unedited file"
        self.assertIn("it returned bstar 0.0 in this run, and was seen to return NaN on ubuntu-24.04", M.basis(reps, True))


class OptInMarkerAndCheck(unittest.TestCase):
    """F2: the marker is a clause of its own; a negation is no mark; a short name is refused; a whole word is needed;
    an unreadable release body beside a readable changelog is checked from the changelog."""
    def test_a_negation_is_no_mark(self):
        import upstream_table as ut
        G = "https://github.com"
        base = f"- **libx**: a bug. [#1]({G}/o/x/issues/1), [PR #2]({G}/o/x/pull/2), "
        self.assertEqual(ut.parse_bullet(base + "opt-in `strict`, merged 2026-01-01.", "my-pr")["opt_in"], {"name": "strict", "scope": None})
        self.assertIsNone(ut.parse_bullet(base + "not an opt-in `strict`, merged 2026-01-01.", "my-pr")["opt_in"])
        self.assertIsNone(ut.parse_bullet(base + "this is not opt-in `strict`, merged 2026-01-01.", "my-pr")["opt_in"])

    def check_row(self, name, answers):
        import json
        import tempfile
        import check_upstream_table as cu
        import upstream_table as ut
        G = "https://github.com"
        r = ut.parse_bullet(f"- **libtwo**: x. [#5]({G}/o/libtwo/issues/5), [PR #6]({G}/o/libtwo/pull/6), opt-in `{name}`, "
                            f"merged 2026-09-26, released in [7.2.0]({G}/o/libtwo/releases/tag/7.2.0).", "my-pr")
        ut.complete([r], {f"{G}/o/libtwo/pull/6": {"merged": True}, f"{G}/o/libtwo/releases/tag/7.2.0": {"exists": True}})
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(answers, f)
        f.close()
        try:
            unchecked = []
            p = cu.check({"rows": [r]}, cu.Recorded(f.name), unchecked=unchecked)[0]
        finally:
            os.unlink(f.name)
        return [x for x in p if "opt-in" in x], [x for x in unchecked if "opt-in" in x]

    def test_a_short_name_is_refused(self):
        p, _ = self.check_row("on", {"/repos/o/libtwo/releases/tags/7.2.0": {"body": "turn it on"}})
        self.assertTrue(any("too short" in x for x in p), p)

    def test_a_name_inside_another_word_is_not_found(self):
        p, _ = self.check_row("strict", {"/repos/o/libtwo/releases/tags/7.2.0": {"body": "the strictness option"}})
        self.assertTrue(any("does not name it as a word" in x for x in p), p)
        p, _ = self.check_row("strict", {"/repos/o/libtwo/releases/tags/7.2.0": {"body": "adds `strict=True`"}})
        self.assertEqual(p, [])

    def test_an_unreadable_release_body_beside_a_readable_changelog(self):
        import base64
        p, u = self.check_row("lenient", {"/repos/o/libtwo/releases/tags/7.2.0": {"_status": 500},
                                          "/repos/o/libtwo/contents/CHANGELOG.md?ref=7.2.0": {"content": base64.b64encode(b"- lenient mode").decode()}})
        self.assertEqual((p, u), ([], []))


if __name__ == "__main__":
    unittest.main()
