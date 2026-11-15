# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""D-405 (the third blind pass's E): what the fetch keeps of an answer. Every gzip member is decoded; a 200 carrying
the provider's no-data or error words is not data; a run stops before a request once it has downloaded the most
CelesTrak asks one address to take in a day. Offline: stand-ins only, no request."""
import datetime as dt
import gzip
import io
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fetch  # noqa: E402

GZ = [("Content-Encoding", "gzip")]
ENTRY = {"stage": "A", "case": "c", "file": "a.csv", "url": "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=CSV"}


class GzipMembers(unittest.TestCase):
    def test_two_members_are_both_kept(self):
        a, b = b"OBJECT_NAME,NORAD_CAT_ID\r\n", b"ISS (ZARYA),25544\r\n"
        body, coding, problem = fetch.decode_body(gzip.compress(a) + gzip.compress(b), GZ)
        self.assertEqual((body, coding, problem), (a + b, "gzip", None))

    def test_zero_padding_after_the_last_member_is_no_member(self):
        a = b"OBJECT_NAME,NORAD_CAT_ID\r\nISS (ZARYA),25544\r\n"
        self.assertEqual(fetch.decode_body(gzip.compress(a) + b"\x00" * 8, GZ), (a, "gzip", None))

    def test_a_second_member_cut_short_is_a_problem(self):
        a = gzip.compress(b"x" * 100)
        body, coding, problem = fetch.decode_body(a + a[:20], GZ)
        self.assertIn("does not decompress", problem or "")

    def test_one_member_as_before(self):
        a = b"data\r\n"
        self.assertEqual(fetch.decode_body(gzip.compress(a), GZ), (a, "gzip", None))


class WhatA200MustBe(unittest.TestCase):
    def test_the_providers_words_are_no_data(self):
        for body, words in ((b"No GP data found", "no-data text"), (b"No SupGP data found\r\n", "no-data text"),
                            (b"Invalid query: unknown group", "an error text"), (b'{"error": "rate limited"}', "a JSON error object")):
            with self.subTest(body=body):
                self.assertIn(words, fetch.why_unexpected(ENTRY, 200, body) or "")

    def test_data_is_data(self):
        for body in (b"OBJECT_NAME,NORAD_CAT_ID\r\nISS (ZARYA),25544\r\n", b'[{"OBJECT_NAME": "ISS (ZARYA)"}]',
                     b"ISS (ZARYA)\r\n1 25544U 98067A   26189.79090935  .00012345  00000+0  21739-3 0  9993\r\n",
                     b'<?xml version="1.0"?><ndm></ndm>', b"CCSDS_OMM_VERS = 2.0\r\n"):
            with self.subTest(body=body[:20]):
                self.assertIsNone(fetch.why_unexpected(ENTRY, 200, body))


class TheRunsBytes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.calls = []

    def stub(self, entry, root=None):   # each answer as large as a day's bytes, counted as fetch_one counts them
        self.calls.append(entry["file"])
        fetch.RUN_BYTES[0] += fetch.MAX_ANSWER_BYTES
        return "HTTP/1.1 200 OK (stub)"

    def test_no_request_past_a_days_bytes(self):
        second = dict(ENTRY, file="b.csv", url=ENTRY["url"].replace("25544", "20453"))
        err = io.StringIO()
        old, sys.stderr = sys.stderr, err
        try:
            code = fetch.run([], root=self.tmp.name, entries=[ENTRY, second], now=dt.datetime(2026, 9, 24, 12, tzinfo=dt.timezone.utc),
                             fetch_one=self.stub, out=io.StringIO(), pause=0)
        finally:
            sys.stderr = old
        self.assertEqual((code, self.calls), (3, ["a.csv"]))
        self.assertIn("the most CelesTrak asks one address to download in a day", err.getvalue())

    def test_a_run_counts_from_nothing(self):
        fetch.RUN_BYTES[0] = fetch.MAX_ANSWER_BYTES   # what an earlier run in the same process left
        code = fetch.run([], root=self.tmp.name, entries=[ENTRY], now=dt.datetime(2026, 9, 24, 12, tzinfo=dt.timezone.utc),
                         fetch_one=self.stub, out=io.StringIO(), pause=0)
        self.assertEqual(self.calls, ["a.csv"])

if __name__ == "__main__":
    unittest.main()
