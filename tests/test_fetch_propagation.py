# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""D-455: `gpconf fetch --include-propagation` downloads Vallado's two verification files from python-sgp4's repository at
a pinned commit and writes them only with the corpus's manifest's bytes; the runner then finds them. Offline: the network
is a stub, and the manifest a stand-in of known bytes, so nothing here needs the private files (D-388)."""
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from gpconf import fetch as F  # noqa: E402
from gpconf import propagation as P  # noqa: E402

BYTES = {"SGP4-VER.TLE": b"# a stand-in for the verification inputs\n", "tcppver.out": b"a stand-in for the output\n"}


class FetchPropagation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.corpus = os.path.join(self.tmp, "corpus")
        self.data = os.path.join(self.tmp, "data")
        os.makedirs(os.path.join(self.corpus, "harnesses", "vallado"))
        os.makedirs(self.data)
        man = {"files": {n: {"sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)} for n, b in BYTES.items()}}
        with open(os.path.join(self.corpus, "harnesses", "vallado", "reference-manifest.json"), "w") as f:
            json.dump(man, f)
        self.asked, self.limits = [], []

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def get(self, answers):
        def stub(url, limit):
            self.asked.append(url)
            self.limits.append(limit)
            return answers(url)
        return stub

    def run_fetch(self, answers, dry_run=False):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stderr", err):
            code = F.fetch_propagation(self.corpus, self.data, out, dry_run=dry_run, get=self.get(answers))
        return code, out.getvalue(), err.getvalue()

    def path(self, name):
        return os.path.join(self.data, "propagation", name)

    def test_the_two_files_come_from_the_pinned_commit_and_are_written_with_their_record(self):
        code, out, _ = self.run_fetch(lambda url: (200, BYTES[url.rsplit("/", 1)[1]]))
        self.assertEqual(code, 0)
        self.assertEqual(self.asked, [F.PROPAGATION_BASE + n for n in P.FILES])
        for url in self.asked:
            self.assertTrue(url.startswith("https://raw.githubusercontent.com/brandon-rhodes/python-sgp4/"
                                           "6e7428df7acc48e8176828289a8c14486a114759/sgp4/"), url)
        for n, b in BYTES.items():
            with open(self.path(n), "rb") as f:
                self.assertEqual(f.read(), b)
            with open(self.path(n) + ".meta.json") as f:
                meta = json.load(f)
            self.assertEqual(meta["sha256"], hashlib.sha256(b).hexdigest())
            self.assertIn("6e7428df7acc48e8176828289a8c14486a114759", meta["source"])
            self.assertEqual(meta["user_agent"], F.user_agent())

    def test_files_on_disk_with_the_manifests_bytes_are_not_asked_for_again(self):
        self.run_fetch(lambda url: (200, BYTES[url.rsplit("/", 1)[1]]))
        self.asked.clear()
        code, out, _ = self.run_fetch(lambda url: self.fail("no request expected"))
        self.assertEqual(code, 0)
        self.assertEqual(self.asked, [])
        self.assertIn("no request", out)

    def test_an_answer_that_is_not_200_stops_and_writes_nothing(self):
        code, _, err = self.run_fetch(lambda url: (404, b"404: Not Found"))
        self.assertEqual(code, 2)
        self.assertEqual(len(self.asked), 1)   # the first answer stops the run: nothing retried, nothing more asked
        self.assertIn("HTTP 404", err)
        self.assertFalse(os.path.exists(os.path.join(self.data, "propagation")))

    def test_bytes_that_are_not_the_manifests_are_never_written(self):
        code, _, err = self.run_fetch(lambda url: (200, BYTES[url.rsplit("/", 1)[1]] + b" "))
        self.assertEqual(code, 2)
        self.assertIn("Nothing was written", err)
        self.assertEqual(len(self.asked), 1)
        self.assertFalse(os.path.exists(self.path("SGP4-VER.TLE")))
        self.assertFalse(os.path.exists(self.path("SGP4-VER.TLE") + ".part"))

    def test_a_network_error_stops_with_3(self):
        def boom(url):
            raise OSError("no route")
        code, _, err = self.run_fetch(boom)
        self.assertEqual(code, 3)
        self.assertIn("Not retrying", err)

    def test_the_dry_run_asks_nothing(self):
        code, out, _ = self.run_fetch(lambda url: self.fail("no request expected"), dry_run=True)
        self.assertEqual(code, 0)
        self.assertEqual(out.count("FETCH   https://raw.githubusercontent.com/"), 2)

    def test_the_request_carries_the_fetchs_user_agent_and_asks_no_compression(self):
        seen = {}

        class Resp(io.BytesIO):
            status = 200
            length = None

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_open(req, timeout=None):
            seen["ua"], seen["enc"], seen["url"] = req.get_header("User-agent"), req.get_header("Accept-encoding"), req.full_url
            return Resp(b"x")
        with mock.patch.object(F._opener, "open", fake_open):
            status, body = F._get_plain(F.PROPAGATION_BASE + "tcppver.out", 10)
        self.assertEqual((status, body), (200, b"x"))
        self.assertEqual(seen["ua"], F.user_agent())
        self.assertEqual(seen["enc"], "identity")

    def test_the_runner_finds_the_fetched_copy(self):
        self.run_fetch(lambda url: (200, BYTES[url.rsplit("/", 1)[1]]))
        directory, where, why = P.locate(self.corpus, None, self.data)
        self.assertEqual(directory, os.path.join(self.data, "propagation"))
        self.assertIn("gpconf fetch --include-propagation", where)

    def test_a_fetched_copy_with_other_bytes_is_not_used(self):
        os.makedirs(os.path.join(self.data, "propagation"))
        for n, b in BYTES.items():
            with open(self.path(n), "wb") as f:
                f.write(b + b"changed")
        directory, where, why = P.locate(self.corpus, None, self.data)
        self.assertIsNone(directory)
        self.assertIn("differ from the corpus's manifest", why)

    def test_the_command_line_takes_the_flag_after_celestraks_files(self):
        out = io.StringIO()
        with mock.patch.object(F, "_get_plain", lambda url, limit: (200, BYTES[url.rsplit("/", 1)[1]])):
            code = F.run(["--include-propagation"], root=self.data, corpus=self.corpus, entries=[], out=out, pause=0)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(self.path("tcppver.out")))


    # the separate review's findings (D-455)
    def test_no_more_than_the_manifests_size_is_read(self):
        self.run_fetch(lambda url: (200, BYTES[url.rsplit("/", 1)[1]]))
        self.assertEqual(self.limits, [len(BYTES[n]) for n in P.FILES])

        class Big(io.BytesIO):
            status, length = 200, None

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        with mock.patch.object(F._opener, "open", lambda req, timeout=None: Big(b"y" * 10_000)):
            status, body = F._get_plain(F.PROPAGATION_BASE + "tcppver.out", 100)
        self.assertEqual(len(body), 101)   # a size past the file's is seen, and no more is read

    def test_an_http_error_or_a_redirect_is_a_status_not_a_crash(self):
        import urllib.error

        def refuse(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 301, "Moved", {}, io.BytesIO(b""))
        with mock.patch.object(F._opener, "open", refuse):
            self.assertEqual(F._get_plain(F.PROPAGATION_BASE + "tcppver.out", 10), (301, b""))

    def test_a_file_with_other_bytes_is_kept_when_the_new_answer_fails(self):
        os.makedirs(os.path.join(self.data, "propagation"))
        with open(self.path("SGP4-VER.TLE"), "wb") as f:
            f.write(b"old")
        code, out, _ = self.run_fetch(lambda url: (500, b""))
        self.assertEqual(code, 2)
        self.assertIn("other bytes", out)
        with open(self.path("SGP4-VER.TLE"), "rb") as f:
            self.assertEqual(f.read(), b"old")

    def test_the_first_file_written_and_the_second_refused_stops_with_the_first_kept(self):
        def answers(url):
            name = url.rsplit("/", 1)[1]
            return (200, BYTES[name]) if name == "SGP4-VER.TLE" else (200, b"not it")
        code, _, _ = self.run_fetch(answers)
        self.assertEqual(code, 2)
        self.assertTrue(os.path.isfile(self.path("SGP4-VER.TLE")))
        self.assertFalse(os.path.exists(self.path("tcppver.out")))
        self.assertIsNone(P.locate(self.corpus, None, self.data)[0])   # one file alone is never used

    def test_a_plain_fetch_never_asks_the_other_host(self):
        with mock.patch.object(F, "_get_plain", lambda *a: self.fail("asked the other host without the flag")):
            for argv in ([], ["--dry-run"], ["--check-drift"]):
                self.assertEqual(F.run(argv, root=self.data, corpus=self.corpus, entries=[], out=io.StringIO(), pause=0), 0)

    def test_the_dry_run_flag_through_the_command_line_asks_nothing(self):
        out = io.StringIO()
        with mock.patch.object(F, "_get_plain", lambda *a: self.fail("no request in a dry run")):
            self.assertEqual(F.run(["--dry-run", "--include-propagation"], root=self.data, corpus=self.corpus, entries=[],
                                   out=out, pause=0), 0)
        self.assertEqual(out.getvalue().count("FETCH   https://raw.githubusercontent.com/"), 2)

    def test_check_drift_says_the_flag_is_not_attempted(self):
        out = io.StringIO()
        with mock.patch.object(F, "_get_plain", lambda *a: self.fail("no request with --check-drift")):
            F.run(["--check-drift", "--include-propagation"], root=self.data, corpus=self.corpus, entries=[], out=out, pause=0)
        self.assertIn("not attempted with --check-drift", out.getvalue())

    def test_celestraks_quiet_hours_do_not_hold_back_the_other_host(self):
        with mock.patch.object(F, "recent_refusal", lambda *a: (
                {"url": "https://celestrak.org/x", "case": "c", "file": "f"}, {"http_status": 403}, 60)), \
             mock.patch.object(F, "_get_plain", lambda url, limit: (200, BYTES[url.rsplit("/", 1)[1]])):
            code = F.run(["--include-propagation"], root=self.data, corpus=self.corpus, entries=[], out=io.StringIO(), pause=0)
        self.assertEqual(code, 2)   # CelesTrak's refusal still ends the run with 2 ...
        self.assertTrue(os.path.isfile(self.path("tcppver.out")))   # ... after the other host's files were fetched

    def test_the_runner_looks_in_its_data_folder(self):
        from gpconf.runner import Runner
        seen = []

        class Prop:
            def parse(self, raw, fmt):
                return []

            def propagate(self, raw, fmt, tsince):
                return []

        def spy(root, explicit=None, data=None):
            seen.append(data)
            return None, None, "not found (spy)"
        with mock.patch.object(P, "locate", spy):
            Runner(Prop(), root=ROOT, data=self.data, fetch_hints=False).run(case_ids=["sgp4-ver-propagation"])
        self.assertEqual(seen, [self.data])

    def test_the_clones_gitignore_keeps_the_fetched_files_out(self):
        with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as f:
            self.assertIn("/" + F.PROPAGATION_DIR + "/", f.read().split())


if __name__ == "__main__":
    unittest.main()
