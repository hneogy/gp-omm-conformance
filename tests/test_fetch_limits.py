# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""D-370 (the second blind review's F13): the fetch stops in words, never in a traceback, on an answer cut short, and
holds an answer to a size on the wire and decompressed.

- http.client's own errors, IncompleteRead among them, are no OSError: an answer cut short ended the fetch in a
  traceback, not in the "STOP ... Not retrying." it documents. It now stops so, with exit status 3.
- An answer, or its gzip body decompressed, past MAX_ANSWER_BYTES (100 MB, what CelesTrak asks one address to
  download in a day) is no answer the fetch list expects: on the wire it stops the run (exit 3); decompressed it is
  an unexpected answer, kept beside the data (exit 2, D-228). The read never holds more than the cap and one byte.

No network: sockets are blocked and the opener is a stub; the cap is lowered for the test.

Run: python -m unittest tests.test_fetch_limits"""
import contextlib
import gzip
import http.client
import io
import os
import socket
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fetch  # noqa: E402  (tools/fetch.py, as the other fetch tests import it)
import test_fetch_gzip as G  # noqa: E402  (the module, not its class: its tests run from their own module)
from test_fetch_gzip import A, DATA, T0, Opener, _Resp  # noqa: E402


class CutShort(_Resp):
    """A chunked answer cut short: http.client raises IncompleteRead from the read itself."""

    def read(self, amt=None):
        raise http.client.IncompleteRead(b"OBJECT_NAME,NO", 40)


class _Sock:
    """What http.client.HTTPResponse reads from: the bytes of an HTTP answer, from memory (no socket)."""

    def __init__(self, raw):
        self.raw = raw

    def makefile(self, mode):
        return io.BytesIO(self.raw)


def real_answer(raw):
    """A real http.client.HTTPResponse over raw bytes: the class the fetch reads in use, not a stub of it."""
    r = http.client.HTTPResponse(_Sock(raw))
    r.begin()
    return r


class RealOpener(Opener):
    def __init__(self, raw):
        super().__init__(b"")
        self.raw = raw

    def open(self, req, timeout=None, encoding="utf-8"):
        return real_answer(self.raw)


class Limits(unittest.TestCase):
    """The gzip tests' set-up and helpers (sockets blocked, a stub opener), not their tests, with the cap lowered to 64
    bytes."""
    go, path, meta = G.Gzip.go, G.Gzip.path, G.Gzip.meta

    def setUp(self):
        G.Gzip.setUp(self)
        self._cap = fetch.MAX_ANSWER_BYTES
        fetch.MAX_ANSWER_BYTES = 64

    def tearDown(self):
        fetch.MAX_ANSWER_BYTES = self._cap
        G.Gzip.tearDown(self)

    def test_an_answer_cut_short_stops_in_words(self):
        class Opener2(Opener):
            def open(self, req, timeout=None, encoding="utf-8"):
                return CutShort(b"")
        fetch._opener = Opener2(b"")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as stop:
            fetch.run([], root=self.tmp.name, entries=[A], now=T0, out=io.StringIO(), pause=0)
        self.assertEqual(stop.exception.code, 3)
        self.assertIn("STOP: network error for", err.getvalue())
        self.assertIn("IncompleteRead", err.getvalue())
        self.assertIn("Not retrying.", err.getvalue())

    def test_an_answer_shorter_than_its_content_length_stops_in_words(self):
        """D-370's reading: http.client's sized read gives back a short body with no IncompleteRead where the answer
        gives a Content-Length; the fetch checks the length still awaited and stops, writing nothing."""
        fetch._opener = RealOpener(b"HTTP/1.1 200 OK\r\nContent-Length: 35\r\n\r\n" + DATA[:20])
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as stop:
            fetch.run([], root=self.tmp.name, entries=[A], now=T0, out=io.StringIO(), pause=0)
        self.assertEqual(stop.exception.code, 3)
        self.assertIn("IncompleteRead", err.getvalue())
        self.assertFalse(os.path.exists(self.path("a.csv")))

    def test_a_whole_answer_read_through_http_client_is_written(self):
        """The twin: the same real response class, the body whole."""
        fetch._opener = RealOpener(b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\n\r\n" % len(DATA) + DATA)
        self.assertEqual(fetch.run([], root=self.tmp.name, entries=[A], now=T0, out=io.StringIO(), pause=0), 0)
        with open(self.path("a.csv"), "rb") as f:
            self.assertEqual(f.read(), DATA)

    def test_an_answer_of_exactly_the_cap_is_written(self):
        """The reading's M33 and M36: the cap is the most, not one less, plain and decompressed."""
        body = b"OBJECT_NAME,NORAD_CAT_ID\r\nX,1\r\n".ljust(64, b" ")
        self.assertEqual(len(body), 64)
        for coding in (None, "gzip"):
            with self.subTest(coding=coding):
                code, _, err = self.go(gzip.compress(body, mtime=0) if coding else body, coding)
                self.assertEqual(code, 0, err)

    def test_a_gzip_body_cut_short_is_an_unexpected_answer(self):
        """The reading's M37: a gzip body missing its end decompresses in part; it is no answer."""
        code, _, err = self.go(gzip.compress(DATA, mtime=0)[:-10], "gzip")
        self.assertEqual(code, "exit 2", err)
        self.assertTrue(self.meta("a.csv.unexpected")["unexpected"].startswith("a gzip body that does not decompress"))

    def test_the_decompression_is_held_to_the_cap(self):
        """The reading's M35: the decompressor is given the cap and one byte as its limit."""
        import zlib
        seen = []
        real = zlib.decompressobj

        class Spy:
            def __init__(self, *a):
                self.d = real(*a)

            def decompress(self, data, max_length=0):
                seen.append(max_length)
                return self.d.decompress(data, max_length)

            @property
            def eof(self):
                return self.d.eof
        fetch.zlib.decompressobj = Spy
        try:
            self.go(gzip.compress(DATA, mtime=0), "gzip")
        finally:
            fetch.zlib.decompressobj = real
        self.assertEqual(seen, [65])

    def test_a_long_answer_with_its_length_declared_says_it_is_too_large(self):
        """The re-reading's N2: past the cap, the words are the size's, not a cut answer's."""
        fetch._opener = RealOpener(b"HTTP/1.1 200 OK\r\nContent-Length: 200\r\n\r\n" + b"x" * 200)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as stop:
            fetch.run([], root=self.tmp.name, entries=[A], now=T0, out=io.StringIO(), pause=0)
        self.assertEqual(stop.exception.code, 3)
        self.assertIn("is larger than 64 bytes", err.getvalue())

    def test_no_more_than_the_cap_and_one_byte_is_asked_for(self):
        """The re-reading's N3: the pieces asked for add up to the cap and one byte at most."""
        asked = []

        class Counting(_Resp):
            def read(self, amt=None):
                asked.append(amt)
                return super().read(amt)

        class O(Opener):
            def open(self, req, timeout=None, encoding="utf-8"):
                return Counting(b"x" * 200)
        fetch._opener = O(b"")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            fetch.run([], root=self.tmp.name, entries=[A], now=T0, out=io.StringIO(), pause=0)
        self.assertNotIn(None, asked)
        self.assertLessEqual(sum(asked), 65)

    def test_an_error_page_cut_short_stops_and_is_read_in_pieces(self):
        """The re-reading's N6 and N7: the error page's branch reads through the same capped read."""
        import urllib.error
        import email.message
        for name, fp, words in (("cut short", lambda: real_answer(b"HTTP/1.1 404 Not Found\r\nContent-Length: 35\r\n\r\n" + DATA[:20]), "IncompleteRead"),
                                ("read whole", lambda: _Resp(b"x" * 200), "larger than 64 bytes")):
            with self.subTest(name):
                class O(Opener):
                    def open(self, req, timeout=None, encoding="utf-8"):
                        raise urllib.error.HTTPError(A["url"], 404, "Not Found", email.message.Message(), fp())
                fetch._opener = O(b"")
                err = io.StringIO()
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as stop:
                    fetch.run([], root=self.tmp.name, entries=[A], now=T0, out=io.StringIO(), pause=0)
                self.assertEqual(stop.exception.code, 3, err.getvalue())
                self.assertIn(words, err.getvalue())
                self.assertFalse(os.path.exists(self.path("a.csv")))

    def test_an_answer_past_the_cap_stops_the_run(self):
        code, _, err = self.go(b"x" * 200)
        self.assertEqual(code, "exit 3", err)
        self.assertIn("is larger than 64 bytes", err)
        self.assertFalse(os.path.exists(self.path("a.csv")))

    def test_a_gzip_body_that_decompresses_past_the_cap_is_an_unexpected_answer(self):
        code, _, err = self.go(gzip.compress(b"x" * 10_000, mtime=0), "gzip")   # 10 kB from a few dozen bytes
        self.assertEqual(code, "exit 2", err)
        self.assertTrue(self.meta("a.csv.unexpected")["unexpected"].startswith("a gzip body that decompresses past 64 bytes"))

    def test_an_answer_at_the_cap_is_written(self):
        """The twin: the data itself, under the cap, plain and gzip."""
        self.assertLessEqual(len(DATA), 64)
        for coding in (None, "gzip"):
            with self.subTest(coding=coding):
                body = gzip.compress(DATA, mtime=0) if coding else DATA
                code, _, err = self.go(body, coding)
                self.assertEqual(code, 0, err)
                with open(self.path("a.csv"), "rb") as f:
                    self.assertEqual(f.read(), DATA)


if __name__ == "__main__":
    unittest.main()
