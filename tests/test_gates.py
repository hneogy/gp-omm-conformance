"""The gate over this month's launches (D-142): wording names the behaviour, never grades; counts come from the
structured values counts; the snapshot facts travel with every headline."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gpconf import gates  # noqa: E402
from gpconf.runner import Runner  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402
from tests.adapters.naive import Parser as Naive  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATE = gates.GATES[0]
SNAP = {"date": "2026-09-21", "count": 256, "id_min": 100404, "id_max": 100789, "alpha5_letters": ["A"]}


def meas(loaded=0, mis=0, dropped=0, note=None):
    r = {"state": "measured", "expected": 256, "returned": loaded + mis, "loaded": loaded, "misidentified": mis, "dropped": dropped}
    if note:
        r["note"] = note
    return r


class HeadlineWording(unittest.TestCase):
    def test_reads_in_every_format(self):
        h = gates.headline({"tle": meas(loaded=256), "csv": meas(loaded=256)}, GATE, SNAP)
        self.assertTrue(h.startswith("reads this month's launches in every format it reads here"), h)
        self.assertNotIn("LOADS", h)

    def test_only_via_csv(self):
        h = gates.headline({"tle": meas(dropped=256), "csv": meas(loaded=256)}, GATE, SNAP)
        self.assertTrue(h.startswith("only via CSV"), h)
        self.assertIn("256 dropped", h)

    def test_not_in_any_format(self):
        h = gates.headline({"tle": meas(mis=256), "csv": meas(mis=256)}, GATE, SNAP)
        self.assertTrue(h.startswith("not in any format it reads:"), h)  # unchanged wording where every format was tried (D-148)

    def test_tle_only_parser_has_nothing_to_load_from_the_feed(self):
        h = gates.headline({"tle": meas(mis=256), "csv": {"state": "not read"}}, GATE, SNAP)
        self.assertTrue(h.startswith("nothing to load from this feed"), h)
        self.assertIn("HTTP 404", h)
        self.assertIn("as Space-Track serves them (Alpha-5): 256 misidentified", h)
        self.assertIn("CSV (as CelesTrak serves them): not read", h)

    def test_parser_that_raises_counts_as_dropped(self):
        h = gates.headline({"tle": meas(note="the parser raised on the file"), "csv": {"state": "not fetched"}}, GATE, SNAP)
        self.assertIn("256 dropped (the parser raised on the file)", h)
        self.assertIn("CSV not measured: not fetched", h)


class UnmeasuredFormatsLimitTheClaim(unittest.TestCase):
    """D-148: a format whose file was not fetched, or whose case was not run, was never tried. A headline over the
    other formats says 'measured here', names the one left out before the numbers, and never calls the parser
    TLE-only."""

    def test_every_format_measured_here_names_the_missing_one_first(self):
        for state in ("not fetched", "not run"):
            with self.subTest(state=state):
                h = gates.headline({"tle": meas(loaded=256), "csv": {"state": state}}, GATE, SNAP)
                self.assertTrue(h.startswith(f"reads this month's launches in every format measured here (CSV not measured: {state}):"), h)
                self.assertNotIn("it reads here", h)

    def test_no_tle_only_claim_when_csv_was_not_tried(self):
        h = gates.headline({"tle": meas(mis=256), "csv": {"state": "not fetched"}}, GATE, SNAP)
        self.assertTrue(h.startswith("not in any format measured here (CSV not measured: not fetched):"), h)
        self.assertNotIn("nothing to load from this feed", h)
        self.assertNotIn("HTTP 404", h)

    def test_a_declared_unsupported_format_is_a_fact_and_keeps_the_old_wording(self):
        h = gates.headline({"tle": meas(loaded=256), "csv": {"state": "not read"}}, GATE, SNAP)
        self.assertTrue(h.startswith("reads this month's launches in every format it reads here:"), h)
        self.assertIn("CSV (as CelesTrak serves them): not read", h)

    def test_only_via_names_the_scope_when_a_format_is_unknown(self):
        gate = {**GATE, "formats": {**GATE["formats"], "kvn": {"label": "KVN (test)"}}}
        h = gates.headline({"tle": meas(dropped=256), "csv": meas(loaded=256), "kvn": {"state": "not fetched"}}, gate, SNAP)
        self.assertTrue(h.startswith("only via CSV of the formats measured here (KVN not measured: not fetched):"), h)


class LiveCaptureIsJudgedOnItsOwnCount(unittest.TestCase):
    """D-148: a freshly fetched CSV differs from the frozen capture. It is judged against its own expected count, not
    the snapshot's, and named as a live capture; the bracket keeps describing the snapshot."""

    def test_a_complete_live_read_is_not_reported_as_a_failure(self):
        live = {**meas(loaded=246), "expected": 246, "live": {"retrieved_at": "2026-09-26T08:00:00Z"}}
        h = gates.headline({"tle": meas(loaded=256), "csv": live}, GATE, SNAP)
        self.assertTrue(h.startswith("reads this month's launches in every format it reads here"), h)
        self.assertIn("live capture fetched 2026-09-26, 246 objects, not the snapshot: 246 loaded", h)
        self.assertIn("snapshot 2026-09-21, 256 objects", h)
        self.assertNotIn("only via", h)

    def test_a_live_file_the_parser_raised_on_has_no_borrowed_count(self):
        live = {"state": "measured", "note": "the parser raised on the file", "expected": None, "returned": 0, "loaded": 0,
                "misidentified": 0, "dropped": None, "live": {"retrieved_at": None}}
        h = gates.headline({"tle": meas(loaded=256), "csv": live}, GATE, SNAP)
        self.assertIn("every record dropped (the parser raised on the file)", h)
        self.assertNotIn("None", h)

    def test_every_headline_carries_the_snapshot_facts_and_the_letter_caveat(self):
        for formats in ({"tle": meas(loaded=256), "csv": meas(loaded=256)}, {"tle": {"state": "not read"}, "csv": {"state": "not read"}}):
            h = gates.headline(formats, GATE, SNAP)
            self.assertIn("snapshot 2026-09-21, 256 objects, ids 100404-100789", h)
            self.assertIn("beginning with A", h)
            self.assertIn("wrong from J upward", h)
        self.assertTrue(gates.headline({"tle": {"state": "not read"}, "csv": {"state": "not read"}}, GATE, SNAP).startswith("not measured"))

    def test_no_grade_words(self):
        for formats in ({"tle": meas(loaded=256), "csv": meas(loaded=256)}, {"tle": meas(mis=256), "csv": {"state": "not read"}}):
            h = gates.headline(formats, GATE, SNAP)
            for word in ("LOADS", "PARTLY", "NO ", "verdict", "passes", "fails"):
                self.assertNotIn(word, h)


class SnapshotFacts(unittest.TestCase):
    def test_read_from_the_case_data(self):
        s = gates.snapshot_facts(ROOT, GATE)
        self.assertEqual((s["count"], s["id_min"], s["id_max"], s["alpha5_letters"]), (256, 100404, 100789, ["A"]))
        self.assertRegex(s["date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_the_date_is_the_frozen_captures_whether_or_not_anything_was_fetched(self):
        # D-148: the date used to come from the local fetch's metadata, falling back to expected.json's generation
        # date, so a run with nothing fetched printed the build date (2026-09-23) for a capture of 2026-09-21.
        import json
        import shutil
        import tempfile
        case = GATE["snapshot_from"]["case"]
        with open(os.path.join(ROOT, "fixtures", case, "expected.json")) as f:
            exp = json.load(f)
        recorded = exp["sources"][GATE["snapshot_from"]["source"]]["retrieved_at"][:10]
        self.assertEqual(gates.snapshot_facts(ROOT, GATE)["date"], recorded)
        self.assertNotEqual(recorded, exp["generated_at"][:10])  # the two dates differ, so the test can tell them apart
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "fixtures", case))
            shutil.copy(os.path.join(ROOT, "fixtures", case, "expected.json"), os.path.join(tmp, "fixtures", case))
            self.assertEqual(gates.snapshot_facts(tmp, GATE)["date"], recorded)


class GateFromARun(unittest.TestCase):
    """Offline: the derived Alpha-5 file is in the repository; the CSV capture may or may not be on disk."""
    def test_reference_reads_the_alpha5_rendering(self):
        runner = Runner(Reference(), root=ROOT)
        results = runner.run(case_ids=["alpha5-tle-derived", "tle-omits-six-digit-objects"])
        g = gates.compute_gates(results, ROOT)[0]
        self.assertEqual(g["formats"]["tle"]["state"], "measured")
        self.assertEqual((g["formats"]["tle"]["loaded"], g["formats"]["tle"]["misidentified"], g["formats"]["tle"]["dropped"]), (256, 0, 0))
        self.assertIn(g["formats"]["csv"]["state"], ("measured", "not fetched"))
        if g["formats"]["csv"]["state"] == "measured":
            self.assertEqual(g["formats"]["csv"]["loaded"], 256)
            self.assertTrue(g["headline"].startswith("reads this month's launches in every format"), g["headline"])
        self.assertIn("snapshot", g["headline"])

    def test_naive_drops_them_all(self):
        runner = Runner(Naive(), root=ROOT)
        results = runner.run(case_ids=["alpha5-tle-derived", "tle-omits-six-digit-objects"])
        g = gates.compute_gates(results, ROOT)[0]
        self.assertEqual(g["formats"]["tle"]["loaded"], 0)
        self.assertEqual(g["formats"]["tle"].get("note"), "the parser raised on the file")
        if g["formats"]["csv"]["state"] == "not fetched":  # public clone: CSV never tried, so no claim about it (D-148)
            self.assertTrue(g["headline"].startswith("not in any format measured here (CSV not measured: not fetched)"), g["headline"])
        else:
            self.assertTrue(g["headline"].startswith("not in any format it reads") or g["headline"].startswith("nothing to load from this feed"), g["headline"])

    def test_gate_says_not_run_when_its_cases_were_not_run(self):
        runner = Runner(Reference(), root=ROOT)
        results = runner.run(case_ids=["alpha5-encoding-vectors"])
        g = gates.compute_gates(results, ROOT)[0]
        self.assertEqual({r["state"] for r in g["formats"].values()}, {"not run"})
        self.assertTrue(g["headline"].startswith("not measured"))


if __name__ == "__main__":
    unittest.main()
