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
        self.assertTrue(h.startswith("not in any format it reads"), h)

    def test_tle_only_parser_has_nothing_to_load_from_the_feed(self):
        h = gates.headline({"tle": meas(mis=256), "csv": {"state": "not read"}}, GATE, SNAP)
        self.assertTrue(h.startswith("nothing to load from this feed"), h)
        self.assertIn("HTTP 404", h)
        self.assertIn("as Space-Track serves them (Alpha-5): 256 misidentified", h)
        self.assertIn("CSV (as CelesTrak serves them): not read", h)

    def test_parser_that_raises_counts_as_dropped(self):
        h = gates.headline({"tle": meas(note="the parser raised on the file"), "csv": {"state": "file absent"}}, GATE, SNAP)
        self.assertIn("256 dropped (the parser raised on the file)", h)
        self.assertIn("file absent", h)

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


class GateFromARun(unittest.TestCase):
    """Offline: the derived Alpha-5 file is in the repository; the CSV capture may or may not be on disk."""
    def test_reference_reads_the_alpha5_rendering(self):
        runner = Runner(Reference(), root=ROOT)
        results = runner.run(case_ids=["alpha5-tle-derived", "tle-omits-six-digit-objects"])
        g = gates.compute_gates(results, ROOT)[0]
        self.assertEqual(g["formats"]["tle"]["state"], "measured")
        self.assertEqual((g["formats"]["tle"]["loaded"], g["formats"]["tle"]["misidentified"], g["formats"]["tle"]["dropped"]), (256, 0, 0))
        self.assertIn(g["formats"]["csv"]["state"], ("measured", "file absent"))
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
        self.assertTrue(g["headline"].startswith("not in any format it reads") or g["headline"].startswith("nothing to load from this feed"), g["headline"])

    def test_gate_says_not_run_when_its_cases_were_not_run(self):
        runner = Runner(Reference(), root=ROOT)
        results = runner.run(case_ids=["alpha5-encoding-vectors"])
        g = gates.compute_gates(results, ROOT)[0]
        self.assertEqual({r["state"] for r in g["formats"].values()}, {"not run"})
        self.assertTrue(g["headline"].startswith("not measured"))


if __name__ == "__main__":
    unittest.main()
