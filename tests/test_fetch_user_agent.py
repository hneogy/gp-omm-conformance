"""D-252: the fetch's User-Agent names gpconf, the version that asks and the repository.

Up to 0.6.0 every request of `gpconf fetch` carried "gp-omm-conformance-corpus/0.1 (fixture fetch, each URL once; see
repository README)": a name nobody could look up, a version that was never the corpus's, and no address of the
repository it pointed at. The provider's operator could not tell from a log which software was asking, or which
release of it. These tests hold the header to the version constant, to what a request really sends and what the
metadata records, and to the sentence of the README that gives it; and they hold D-007, which keeps the contact
details of the person running the fetch out of it unless that person puts them in.

No network: sockets are blocked and the opener is a stub.

Run: python -m unittest tests.test_fetch_user_agent"""
import contextlib
import datetime as dt
import email.message
import io
import json
import os
import re
import socket
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fetch  # noqa: E402
import gpconf  # noqa: E402

REPO = "https://github.com/hneogy/gp-omm-conformance"
T0 = dt.datetime(2026, 10, 5, 12, 0, 0, tzinfo=dt.timezone.utc)
A = {"stage": "A", "case": "c", "file": "a.csv", "url": "https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=CSV"}
ENV = ("GPCONF_USER_AGENT", "GPCONF_CONTACT")


def _blocked(*a, **k):
    raise AssertionError("a test tried to open a socket")


class _Resp:
    def __init__(self, body):
        self.status, self.reason, self.version, self._body = 200, "OK", 11, body
        self.headers = email.message.Message()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Opener:
    """Answers every request with one CSV record and keeps the User-Agent each request carried."""

    def __init__(self):
        self.sent = []

    def open(self, req, timeout=None):
        self.sent.append(req.get_header("User-agent"))
        return _Resp(b"OBJECT_NAME,NORAD_CAT_ID\r\nX,81011\r\n")


class TheHeader(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.pop(k, None) for k in ENV}
        self.tmp = tempfile.TemporaryDirectory()
        self._saved = (fetch._opener, socket.socket, socket.create_connection)
        socket.socket = socket.create_connection = _blocked

    def tearDown(self):
        fetch._opener, socket.socket, socket.create_connection = self._saved
        for k, v in self._env.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
        self.tmp.cleanup()

    def test_it_names_the_kit_the_version_that_asks_and_the_repository(self):
        ua = fetch.user_agent()
        self.assertEqual(ua, f"gpconf/{gpconf.__version__} (+{REPO}; fetch, each URL once)")
        self.assertRegex(ua, r"^gpconf/\d+\.\d+\.\d+ \(\+https://github\.com/hneogy/gp-omm-conformance; ")
        self.assertEqual(fetch.REPO_URL, REPO)
        self.assertEqual(fetch.ISSUES_URL, REPO + "/issues")   # the address a stopped run tells its user to report to
        self.assertNotIn("gp-omm-conformance-corpus/0.1", ua)

    def test_it_carries_no_contact_unless_one_is_given(self):
        # D-007: the header says nothing about the person running the fetch
        self.assertNotIn("@", fetch.user_agent())
        os.environ["GPCONF_CONTACT"] = "ops@example.invalid"
        self.assertEqual(fetch.user_agent(), f"gpconf/{gpconf.__version__} (+{REPO}; fetch, each URL once) ops@example.invalid")

    def test_gpconf_user_agent_replaces_the_string(self):
        os.environ["GPCONF_USER_AGENT"] = "mirror/1.0"
        self.assertEqual(fetch.user_agent(), "mirror/1.0")
        os.environ["GPCONF_CONTACT"] = "ops@example.invalid"
        self.assertEqual(fetch.user_agent(), "mirror/1.0 ops@example.invalid")

    def test_a_request_sends_it_and_the_metadata_records_it(self):
        opener = fetch._opener = Opener()
        out = io.StringIO()
        with contextlib.redirect_stderr(io.StringIO()):
            code = fetch.run([], root=self.tmp.name, entries=[A], now=T0, out=out, pause=0)
        self.assertEqual(code, 0, out.getvalue())
        self.assertEqual(opener.sent, [fetch.user_agent()])
        with open(os.path.join(self.tmp.name, "fixtures", "c", "raw", "a.csv.meta.json")) as f:
            meta = json.load(f)
        self.assertEqual(meta["request_headers"]["User-Agent"], fetch.user_agent())
        self.assertEqual(meta["user_agent"], fetch.user_agent())


class TheReadme(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            cls.readme = " ".join(f.read().split())

    def test_it_gives_the_header_with_the_version_left_open(self):
        self.assertIn(f"`User-Agent: gpconf/<version> (+{REPO}; fetch, each URL once)`", self.readme)
        self.assertEqual(fetch.user_agent.__globals__["REPO_URL"], REPO)
        saved = {k: os.environ.pop(k, None) for k in ENV}
        try:
            self.assertEqual(fetch.user_agent().replace(gpconf.__version__, "<version>", 1),
                             f"gpconf/<version> (+{REPO}; fetch, each URL once)")
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v
        for name in ENV:
            self.assertIn(f"`{name}`", self.readme)

    def test_the_status_paragraph_gives_the_header_of_this_version(self):
        # the one place the README writes the header out with its number: it moves with the version constant
        status = self.readme[self.readme.index("Status: version `"):self.readme.index("Maintainer: Honorius Neogy")]
        self.assertIn(f"`gpconf/{gpconf.__version__} (+{REPO}; fetch, each URL once)`", status)

    def test_it_gives_one_size_for_a_users_fetch(self):
        # the quick start says it twice and "Fetching responsibly" once; up to 0.6.0 all three gave the size computed from
        # the corpus's own captures, 3.1 MB, where both timed first-time fetches measured 3.2 MB (D-235, D-250, D-252)
        sizes = re.findall(r"46 requests(?:,| and) (\d+\.\d) MB", self.readme)
        self.assertEqual(len(sizes), 3, sizes)
        self.assertEqual(set(sizes), {"3.2"})


if __name__ == "__main__":
    unittest.main()
