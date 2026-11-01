# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""D-329: the fetch asks for gzip, for a smaller transfer, and what it writes is the data itself.

A request carries `Accept-Encoding: gzip`. A gzip answer is decompressed before the file is written and hashed, so a
file's bytes and SHA-256 are the provider's data whatever came over the wire, and a stable-tier file still matches
the manifest; the metadata records the coding and the bytes on the wire. An answer that was not plain text sent
uncompressed or gzip, or a gzip body that does not decompress, is a response the fetch did not expect: the run stops
and the body is kept beside the data, as for any other (D-228).

No network: sockets are blocked and the opener is a stub.

Run: python -m unittest tests.test_fetch_gzip"""
import contextlib
import datetime as dt
import email.message
import gzip
import hashlib
import io
import json
import os
import socket
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fetch  # noqa: E402

T0 = dt.datetime(2026, 10, 15, 12, 0, 0, tzinfo=dt.timezone.utc)
A = {"stage": "A", "case": "c", "file": "a.csv", "url": "https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=CSV"}
DATA = b"OBJECT_NAME,NORAD_CAT_ID\r\nX,81011\r\n"


def _blocked(*a, **k):
    raise AssertionError("a test tried to open a socket")


class _Resp:
    def __init__(self, body, coding=None):
        self.status, self.reason, self.version, self._body = 200, "OK", 11, body
        self.headers = email.message.Message()
        if coding is not None:
            self.headers["Content-Encoding"] = coding

    def read(self, amt=None):   # as http.client's: at most amt bytes when given, from where the last read ended (D-370)
        if amt is None:
            raise AssertionError("the fetch read an answer with no size: an unbounded read (D-370)")
        part, self._body = self._body[:amt], self._body[amt:]
        return part

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Opener:
    """Answers every request with the body and coding it was given, and keeps the headers each request carried."""

    def __init__(self, body, coding=None):
        self.body, self.coding, self.sent = body, coding, []

    def open(self, req, timeout=None, encoding="utf-8"):
        self.sent.append({k.lower(): v for k, v in req.header_items()})
        return _Resp(self.body, self.coding)


class Gzip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._saved = (fetch._opener, socket.socket, socket.create_connection)
        socket.socket = socket.create_connection = _blocked

    def tearDown(self):
        fetch._opener, socket.socket, socket.create_connection = self._saved
        self.tmp.cleanup()

    def go(self, body, coding=None):
        opener = fetch._opener = Opener(body, coding)
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                code = fetch.run([], root=self.tmp.name, entries=[A], now=T0, out=out, pause=0)
        except SystemExit as e:
            code = f"exit {e.code}"
        return code, opener.sent, err.getvalue()

    def path(self, name):
        return os.path.join(self.tmp.name, "fixtures", "c", "raw", name)

    def meta(self, name):
        with open(self.path(name) + ".meta.json", encoding="utf-8") as f:
            return json.load(f)

    def test_every_request_asks_for_gzip(self):
        code, sent, _ = self.go(DATA)
        self.assertEqual(code, 0)
        self.assertEqual(sent[0]["accept-encoding"], "gzip")
        self.assertEqual(self.meta("a.csv")["request_headers"]["Accept-Encoding"], "gzip")

    def test_a_gzip_answer_is_written_and_hashed_as_the_data_itself(self):
        wire = gzip.compress(DATA, mtime=0)
        code, _, err = self.go(wire, "gzip")
        self.assertEqual(code, 0, err)
        with open(self.path("a.csv"), "rb") as f:
            self.assertEqual(f.read(), DATA)
        m = self.meta("a.csv")
        self.assertEqual((m["bytes"], m["sha256"]), (len(DATA), hashlib.sha256(DATA).hexdigest()))
        self.assertEqual((m["content_encoding"], m["bytes_on_wire"]), ("gzip", len(wire)))

    def test_an_answer_sent_uncompressed_is_recorded_as_identity(self):
        code, _, _ = self.go(DATA)
        m = self.meta("a.csv")
        self.assertEqual((m["content_encoding"], m["bytes_on_wire"], m["bytes"]), ("identity", len(DATA), len(DATA)))

    def test_the_coding_name_is_read_without_regard_to_case(self):
        code, _, err = self.go(gzip.compress(DATA, mtime=0), "GZip")
        self.assertEqual(code, 0, err)
        with open(self.path("a.csv"), "rb") as f:
            self.assertEqual(f.read(), DATA)

    def test_a_gzip_body_that_does_not_decompress_stops_the_run_and_is_kept_beside_the_data(self):
        code, _, err = self.go(b"\x1f\x8b not gzip at all", "gzip")
        self.assertEqual(code, "exit 2")
        self.assertFalse(os.path.exists(self.path("a.csv")))
        self.assertTrue(self.meta("a.csv.unexpected")["unexpected"].startswith("a gzip body that does not decompress"))
        self.assertIn("STOP: a gzip body that does not decompress", err)

    def test_a_coding_that_was_not_asked_for_stops_the_run(self):
        code, _, err = self.go(b"\x00\x01\x02", "br")
        self.assertEqual(code, "exit 2")
        self.assertFalse(os.path.exists(self.path("a.csv")))
        self.assertEqual(self.meta("a.csv.unexpected")["unexpected"], "Content-Encoding 'br', which was not asked for")

    def test_a_gzip_html_page_is_still_an_unexpected_answer(self):
        code, _, _ = self.go(gzip.compress(b"<!DOCTYPE html><html>busy</html>", mtime=0), "gzip")
        self.assertEqual(code, "exit 2")
        self.assertEqual(self.meta("a.csv.unexpected")["unexpected"], "an HTML page under HTTP 200")


if __name__ == "__main__":
    unittest.main()
