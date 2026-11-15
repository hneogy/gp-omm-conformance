# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The provider's no-data answer is read as the empty answer only where it is the answer the corpus records (D-540).

0.9.0's blind pass on D-515's path found four wrong verdicts in the older no-data branch of `load_source`, which took
any file whose stripped text was either provider's no-data text as the clean empty answer:
- W1, padded text in a source recorded as CelesTrak's 404 (line ends, blank lines, spaces, tabs, other whitespace);
- W2, the other provider's text (SupGP's in a GP source, and the reverse);
- W3, a .meta.json giving HTTP 200 beside the recorded 404 answer;
- W4, a source recorded with records replaced by the no-data text.
Each test for a finding fails on the code before D-540 and passes on it; the recorded-403 test guards the rule's
edge (it passes before too, as D-515 caught that file), and the correct-case tests pass on both. The correct situations stay as they were: the exact
answer, the HTTP 200 no-data answer of D-514 and D-517, and records in a 404 source's place.

Run: python -m unittest tests.adversarial.test_nodata_answer_090"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from gpconf.runner import CaseResult, Runner  # noqa: E402
from tests.adapters.reference import Parser as Reference  # noqa: E402

GP, SUPGP = b"No GP data found", b"No SupGP data found"
SARAMAGO = "six-digit-omm-saramago"
SARAMAGO_TLE = f"fixtures/{SARAMAGO}/raw/saramago.tle"


def source(case, path):
    """The corpus's own record of a source, from its case's expected.json."""
    with open(os.path.join(ROOT, "fixtures", case, "expected.json"), encoding="utf-8") as f:
        return json.load(f)["sources"][path]


def gp_404():
    return source(SARAMAGO, SARAMAGO_TLE)


def supgp_404():
    case = "nine-digit-supgp-launch-nominals"
    with open(os.path.join(ROOT, "fixtures", case, "expected.json"), encoding="utf-8") as f:
        srcs = json.load(f)["sources"]
    return next(s for s in srcs.values() if s.get("http_status") == 404)


# W1's paddings, each around or after the recorded 16 bytes, as the blind pass made them
PADDINGS = {
    "trailing LF": GP + b"\n",
    "trailing CRLF": GP + b"\r\n",
    "blank lines around": b"\n\n\n" + GP + b"\n\n\n\n",
    "spaces and tabs": b" \t" + GP + b"\t ",
    "control whitespace": b"\x1c\x1d" + GP + b"\x1e\x1f\x0b\x0c",
    "Unicode whitespace": " \u0085　".encode("utf-8") + GP + "   ".encode("utf-8"),
}


class LoadSource(unittest.TestCase):
    def setUp(self):
        self.runner = Runner(Reference(), root=ROOT)
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def load(self, data, src):
        path = os.path.join(self.tmp, "answer.tle")
        with open(path, "wb") as f:
            f.write(data)
        res = CaseResult("scratch", "scratch")
        state, *_ = self.runner.load_source(res, {"id": "scratch", "checks": ["empty-answer-yields-no-records"]}, path, src)
        return state, res

    def assert_file_fails(self, state, res):
        """The file fails as a file (source-readable, or the reference reader refusing it), never as the parser, and
        is not taken as the empty answer."""
        self.assertNotEqual(state, "empty-404")
        self.assertIn(state, ("unreadable", "parse-error"))
        fails = [i for i in res.items if i.status == "fail"]
        self.assertTrue(fails)
        self.assertTrue(all(i.check in ("source-readable", "reference-reader") for i in fails), fails)
        self.assertFalse(any(i.check == "empty-answer-yields-no-records" for i in res.items), res.items)

    def test_the_exact_recorded_answer_is_the_empty_answer(self):
        for name, data, src in (("GP", GP, gp_404()), ("SupGP", SUPGP, supgp_404())):
            with self.subTest(name):
                state, res = self.load(data, src)
                self.assertEqual(state, "empty-404")
                self.assertEqual([i for i in res.items if i.status == "fail"], [])
                self.assertTrue(any(i.check == "empty-answer-yields-no-records" and i.status == "pass" for i in res.items))

    def test_w1_padded_text_in_a_404_source_fails_as_the_file(self):
        for name, data in PADDINGS.items():
            with self.subTest(name):
                self.assert_file_fails(*self.load(data, gp_404()))
        with self.subTest("SupGP text with blank lines after it"):
            self.assert_file_fails(*self.load(SUPGP + b"\n\n\n", supgp_404()))

    def test_w1_the_failure_says_the_recorded_answer_is_exactly_16_bytes(self):
        state, res = self.load(GP + b"\n\n", gp_404())
        fails = [i for i in res.items if i.status == "fail"]
        self.assertEqual([i.check for i in fails], ["source-readable"], fails)
        self.assertIn("not the provider's no-data text", fails[0].detail)
        self.assertIn("HTTP 404, exactly 16 bytes", fails[0].detail)

    def test_w2_the_other_providers_text_fails(self):
        for name, data, src in (("SupGP text in a GP source", SUPGP, gp_404()), ("GP text in a SupGP source", GP, supgp_404())):
            with self.subTest(name):
                self.assert_file_fails(*self.load(data, src))

    def test_w4_a_source_recorded_with_records_holding_the_no_data_text_fails(self):
        src = source(SARAMAGO, f"fixtures/{SARAMAGO}/raw/saramago.csv")
        self.assertEqual((src.get("http_status"), src.get("record_count")), (200, 1))   # the premise
        for data in (GP, GP + b"\r\n"):
            with self.subTest(data):
                state, res = self.load(data, src)
                self.assert_file_fails(state, res)
                fails = [i for i in res.items if i.status == "fail"]
                self.assertIn("the corpus records 1 record for this source", fails[0].detail)
        with self.subTest("the other provider's text"):
            # not even the right provider's answer: the file is read on, and reads none of its 1 record (D-113)
            self.assert_file_fails(*self.load(SUPGP, src))

    def test_the_http_200_answer_with_no_records_recorded_stays_the_empty_answer(self):
        # D-514's ruling 2 and D-517: CelesTrak's no-data text under HTTP 200, alone or with one line end
        for data in (GP, SUPGP, GP + b"\n", GP + b"\r\n"):
            for src in ({"format": "tle", "http_status": 200, "record_count": 0, "sha256": "0" * 64},
                        {"format": "tle", "sha256": "0" * 64}):
                with self.subTest(data=data, status=src.get("http_status")):
                    state, res = self.load(data, src)
                    self.assertEqual(state, "empty-404")
                    self.assertEqual([i for i in res.items if i.status == "fail"], [])

    def test_more_than_one_line_end_or_other_whitespace_under_200_is_not_the_answer(self):
        for data in (GP + b"\n\n", b" " + GP, GP + b"\t"):
            with self.subTest(data):
                state, _ = self.load(data, {"format": "tle", "http_status": 200, "record_count": 0, "sha256": "0" * 64})
                self.assertNotEqual(state, "empty-404")

    def test_w2_under_200_or_no_status_the_other_providers_text_is_not_the_answer(self):
        # the owner's rule (D-540): the wrong provider's text never counts; the source's URL names its provider
        gp_url = "https://celestrak.org/NORAD/elements/gp.php?GROUP=x&FORMAT=TLE"
        sup_url = "https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=x&FORMAT=TLE"
        for status in (200, None):
            for url, wrong, right in ((gp_url, SUPGP, GP), (sup_url, GP, SUPGP)):
                src = {"format": "tle", "record_count": 0, "sha256": "0" * 64, "url": url}
                if status is not None:
                    src["http_status"] = status
                with self.subTest(status=status, url=url, text=wrong):
                    state, _ = self.load(wrong, src)
                    self.assertNotEqual(state, "empty-404")
                with self.subTest(status=status, url=url, text=right):
                    state, res = self.load(right, src)
                    self.assertEqual(state, "empty-404")
                    self.assertEqual([i for i in res.items if i.status == "fail"], [])

    def test_under_200_one_line_end_is_a_single_lf_or_a_single_crlf_and_nothing_more(self):
        src = {"format": "tle", "http_status": 200, "record_count": 0, "sha256": "0" * 64}
        for data in (GP + b"\r", GP + b"\n\r\n", GP + b"\r\n\n", GP + b"\r\n\r\n", GP + b"\n\n", b"\n" + GP,
                     b" " + GP, GP + b" ", GP + b"\t", "\u00a0".encode("utf-8") + GP, GP + "\u3000".encode("utf-8"),
                     GP + "\u2028".encode("utf-8"), GP + b"\x0c"):
            with self.subTest(data):
                state, _ = self.load(data, src)
                self.assertNotEqual(state, "empty-404")

    def test_a_404_source_with_no_recorded_body_takes_only_its_providers_exact_text(self):
        # the review of D-540 (3a): with no `facts`, the source's URL names the provider
        src = {"format": "tle", "http_status": 404, "record_count": 0, "sha256": "0" * 64,
               "url": "https://celestrak.org/NORAD/elements/gp.php?CATNR=100000&FORMAT=TLE"}
        state, res = self.load(GP, src)
        self.assertEqual(state, "empty-404")
        self.assertEqual([i for i in res.items if i.status == "fail"], [])
        for data in (SUPGP, GP + b"\n"):
            with self.subTest(data):
                self.assert_file_fails(*self.load(data, src))

    def test_a_recorded_body_that_is_no_no_data_text_is_never_the_empty_answer(self):
        # the review of D-540 (3b): a recorded 403 page, matched byte for byte, is not the provider's empty answer
        page = "Forbidden"
        src = {"format": "tle", "http_status": 403, "record_count": 0, "sha256": "0" * 64, "facts": {"response_body": page},
               "url": "https://celestrak.org/NORAD/elements/gp.php?GROUP=x&FORMAT=TLE"}
        self.assert_file_fails(*self.load(page.encode("utf-8"), src))


class TheFetch(unittest.TestCase):
    """The fetch expects the provider's 404 only as its exact no-data text, for the entry's own provider (the review of
    D-540, 2): a re-capture saved with other bytes would be a file the runner now refuses."""

    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import fetch
        self.fetch = fetch

    def test_the_exact_text_of_the_entrys_provider_is_the_expected_404(self):
        gp = {"expect_status": 404, "url": "https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=TLE"}
        sup = {"expect_status": 404, "url": "https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=x&FORMAT=TLE"}
        self.assertIsNone(self.fetch.why_unexpected(gp, 404, GP))
        self.assertIsNone(self.fetch.why_unexpected(sup, 404, SUPGP))
        for entry, body in ((gp, SUPGP), (sup, GP), (gp, GP + b"\n"), (gp, GP + b"\r\n"), (gp, b" " + GP), (sup, SUPGP + b"\n\n")):
            with self.subTest(url=entry["url"], body=body):
                self.assertEqual(self.fetch.why_unexpected(entry, 404, body), "HTTP 404")

    def test_the_runner_and_the_fetch_share_one_definition(self):
        from gpconf import fetch as gfetch, runner
        self.assertIs(runner.no_data_texts_for, gfetch.no_data_texts_for)
        self.assertEqual(gfetch.NO_DATA_TEXTS, ("No GP data found", "No SupGP data found"))


class ThroughACase(unittest.TestCase):
    """Through Runner.run with a data folder, where the .meta.json beside a provider file is read."""

    def setUp(self):
        self.data = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.data, "fixtures", SARAMAGO, "raw"))

    def tearDown(self):
        shutil.rmtree(self.data)

    def run_with(self, body, meta=None):
        full = os.path.join(self.data, SARAMAGO_TLE)
        with open(full, "wb") as f:
            f.write(body)
        if meta is not None:
            with open(full + ".meta.json", "w", encoding="utf-8") as f:
                json.dump(meta, f)
        r = Runner(Reference(), root=ROOT, data=self.data, fetch_hints=False).run(case_ids=[SARAMAGO])[0]
        return r, [i for i in r.items if i.file == SARAMAGO_TLE]

    def meta(self, status):
        src = gp_404()
        return {"http_status": status, "bytes": 16, "sha256": src["sha256"], "provenance": "recorded",
                "recorded": {"file": "recorded/celestrak-no-gp-data-found.txt"}, "retrieved_at": src["retrieved_at"]}

    def test_the_exact_answer_with_its_meta_passes_the_file(self):
        r, items = self.run_with(GP, self.meta(404))
        self.assertEqual([i for i in items if i.status == "fail"], [])
        self.assertTrue(any(i.check == "empty-answer-yields-no-records" and i.status == "pass" for i in items), items)

    def test_w1_a_padded_live_answer_fails_the_case(self):
        # the blind pass's A02: the case passed with the padded file read as the provider's empty answer
        r, items = self.run_with(b"\n\n\n" + GP + b"\n\n\n\n")
        self.assertEqual(r.status, "fail")
        self.assertEqual([i.check for i in items if i.status == "fail"], ["source-readable"], items)
        self.assertFalse(any(i.check == "empty-answer-yields-no-records" for i in items))

    def test_w3_a_meta_giving_http_200_beside_the_404_answer_fails_the_file(self):
        r, items = self.run_with(GP, self.meta(200))
        self.assertEqual(r.status, "fail")
        fails = [i for i in items if i.status == "fail"]
        self.assertEqual([i.check for i in fails], ["source-readable"], items)
        self.assertIn(".meta.json gives HTTP 200, not the HTTP 404 answer", fails[0].detail)


if __name__ == "__main__":
    unittest.main()
