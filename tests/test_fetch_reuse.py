"""D-157, v0.3.0 stage 6: stable-tier files are reused across corpus versions on a hash match (D-153).

In a per-user cache, one folder per corpus version, `gpconf fetch` for a new version copies a stable-tier file from an
earlier version's folder, with its metadata, when its bytes hash to the new version's recorded SHA-256, and marks it
reused; it requests everything else. A live file is never reused, even when its bytes match. The runner's report
names the files that were reused rather than fetched. No test makes a request: a stub stands where the request would
be, and the stub is called only for the files that would be requested."""
import contextlib
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

from gpconf import fetch  # noqa: E402
from gpconf import locate  # noqa: E402

STABLE, LIVE, OTHER = b"STABLE BYTES", b"LIVE BYTES", b"CHANGED BYTES"
ENTRIES = [{"case": "c", "file": f, "url": f"https://example.invalid/{f}", "stage": "A"} for f in ("s.csv", "l.csv", "d.csv", "n.csv")]


def sha(b):
    return hashlib.sha256(b).hexdigest()


def put(folder, name, data, meta=True, retrieved="2026-09-21T00:43:39Z"):
    d = os.path.join(folder, "fixtures", "c", "raw")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "wb") as f:
        f.write(data)
    if meta:
        with open(os.path.join(d, name + ".meta.json"), "w") as f:
            json.dump({"retrieved_at": retrieved, "sha256": sha(data), "url": f"https://example.invalid/{name}"}, f)


class Layout(unittest.TestCase):
    """A cache base holding an earlier version's folder, the new version's empty folder, and a corpus whose manifest
    records s.csv and d.csv and n.csv as stable and l.csv as live."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.base = os.path.join(self.tmp, "cache", "gpconf")
        self.old = os.path.join(self.base, "0.2.0")
        self.new = os.path.join(self.base, "0.2.1")
        os.makedirs(self.new)
        put(self.old, "s.csv", STABLE)                 # stable, bytes match: reused
        put(self.old, "l.csv", LIVE)                   # live, bytes match: never reused
        put(self.old, "d.csv", OTHER)                  # stable, bytes differ: requested
        put(self.old, "n.csv", STABLE, meta=False)     # stable, bytes match, no metadata: requested
        self.corpus = os.path.join(self.tmp, "corpus")
        os.makedirs(self.corpus)
        sources = [{"path": "fixtures/c/raw/s.csv", "tier": "stable", "sha256": sha(STABLE)},
                   {"path": "fixtures/c/raw/l.csv", "tier": "live", "sha256": sha(LIVE)},
                   {"path": "fixtures/c/raw/d.csv", "tier": "stable", "sha256": sha(STABLE)},
                   {"path": "fixtures/c/raw/n.csv", "tier": "stable", "sha256": sha(STABLE)}]
        with open(os.path.join(self.corpus, "manifest.json"), "w") as f:
            json.dump({"corpus_version": "0.2.1", "cases": [{"id": "c", "sources": sources}]}, f)
        self.calls = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stub(self, entry, root=None):
        self.calls.append(entry["file"])
        return "stub, no request"

    def run_fetch(self, argv):
        out = io.StringIO()
        code = fetch.run(argv, root=self.new, corpus=self.corpus, entries=ENTRIES, fetch_one=self.stub, out=out, pause=0,
                         reuse_sources=fetch.version_folders(self.new))
        return code, out.getvalue()


class Reuse(Layout):
    def test_the_other_versions_are_found_newest_first(self):
        for name in ("0.1.9", "0.10.0", "latest", "tmp"):
            os.makedirs(os.path.join(self.base, name, "fixtures"))
        self.assertEqual([v for v, _ in fetch.version_folders(self.new)], ["0.10.0", "0.2.0", "0.1.9"])

    def test_only_the_stable_file_with_matching_bytes_and_metadata_is_reusable(self):
        self.assertEqual(sorted(fetch.reusable(ENTRIES, self.new, self.corpus, fetch.version_folders(self.new))), ["fixtures/c/raw/s.csv"])

    def test_the_dry_run_says_reuse_and_makes_no_request(self):
        code, out = self.run_fetch(["--dry-run"])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.calls, [])
        lines = [line for line in out.splitlines() if line.startswith(("REUSE", "FETCH"))]
        self.assertEqual([line.split()[0] for line in lines], ["REUSE", "FETCH", "FETCH", "FETCH"])
        self.assertIn("stable tier: the copy in corpus 0.2.0's cache holds the bytes this version's manifest records; copied, not requested", lines[0])
        self.assertIn("dry run: no request made; a run would make 3 request(s), reuse 1 file(s) from an earlier corpus version's cache and leave 0 entries as they are", out)
        self.assertFalse(os.path.exists(os.path.join(self.new, "fixtures")))

    def test_a_run_copies_and_marks_the_reused_file_and_requests_the_rest(self):
        code, out = self.run_fetch([])
        self.assertEqual(sorted(self.calls), ["d.csv", "l.csv", "n.csv"])  # the live file is requested, never reused
        target = os.path.join(self.new, "fixtures", "c", "raw", "s.csv")
        self.assertEqual(open(target, "rb").read(), STABLE)
        meta = json.load(open(target + ".meta.json"))
        self.assertEqual(meta["reused_from"]["corpus_version"], "0.2.0")
        self.assertEqual(meta["retrieved_at"], "2026-09-21T00:43:39Z")  # the one request that was made, not the copy
        self.assertIn("reused_at", meta)
        self.assertIn("reused from 0.2.0  c/s.csv  (stable tier, the bytes this version records; no request)", out)
        self.assertIn("done: 3 request(s) made, 1 file(s) reused from an earlier corpus version's cache, 0 entries skipped", out)
        self.calls.clear()
        _, out = self.run_fetch(["--dry-run"])  # now on disk: cached, not reused again
        self.assertTrue(any(line.startswith("cached") and "s.csv" in line for line in out.splitlines()), out)

    def test_reuse_happens_only_in_a_per_user_cache(self):
        with mock.patch.object(fetch, "version_folders", side_effect=AssertionError("looked for earlier versions")):
            out = io.StringIO()
            code = fetch.run(["--dry-run", "--data", self.new, "--case", "epoch-year-19xx"], out=out, fetch_one=self.stub)
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("(--data)", out.getvalue())


RAW = os.path.join(ROOT, "fixtures")
FETCHLIST = json.load(open(os.path.join(ROOT, "tools", "fetchlist.json")))
NORMAL = [e for e in FETCHLIST if not e.get("recapture_of")]
HAVE_RAW = all(os.path.exists(os.path.join(RAW, e["case"], "raw", e["file"])) for e in NORMAL)


@unittest.skipUnless(HAVE_RAW, "provider files absent (public clone)")
class RealCorpus(unittest.TestCase):
    """With this repository's fetched files as an earlier version's cache, the 22 stable-tier entries are reused and the
    39 live ones requested; the runner's report names the reused files."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = os.path.join(self.tmp, "gpconf", "0.0.9")
        self.new = os.path.join(self.tmp, "gpconf", locate.corpus_version(ROOT))
        os.makedirs(self.new)
        for e in NORMAL:
            for name in (e["file"], e["file"] + ".meta.json"):
                src = os.path.join(RAW, e["case"], "raw", name)
                d = os.path.join(self.old, "fixtures", e["case"], "raw")
                os.makedirs(d, exist_ok=True)
                shutil.copy(src, d)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_22_reused_39_requested(self):
        calls, out = [], io.StringIO()
        fetch.run(["--dry-run"], root=self.new, corpus=ROOT, entries=FETCHLIST, fetch_one=lambda e, root=None: calls.append(e), out=out,
                  pause=0, reuse_sources=fetch.version_folders(self.new))
        heads = [line.split()[0] for line in out.getvalue().splitlines() if line.startswith(("REUSE", "FETCH"))]
        self.assertEqual((heads.count("REUSE"), heads.count("FETCH")), (22, 39))
        self.assertEqual(calls, [])
        man = fetch.manifest_sources(ROOT)
        reused = [line.split()[1] for line in out.getvalue().splitlines() if line.startswith("REUSE")]
        urls = {e["url"]: f"fixtures/{e['case']}/raw/{e['file']}" for e in NORMAL}
        self.assertEqual({man[urls[u]]["tier"] for u in reused}, {"stable"})

    def test_the_run_report_names_the_reused_files(self):
        from gpconf.__main__ import main as gpconf_main
        fetch.run([], root=self.new, corpus=ROOT, entries=[e for e in NORMAL if e["case"] == "epoch-year-19xx"],
                  fetch_one=lambda e, root=None: "stub", out=io.StringIO(), pause=0, reuse_sources=fetch.version_folders(self.new))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            gpconf_main(["run", "--preset", "reference", "--data", self.new, "--case", "epoch-year-19xx"])
        stable = [e for e in NORMAL if e["case"] == "epoch-year-19xx"
                  and fetch.manifest_sources(ROOT)[f"fixtures/{e['case']}/raw/{e['file']}"]["tier"] == "stable"]
        self.assertIn(f"{len(stable)} provider file(s) were reused from corpus 0.0.9's cache rather than fetched", out.getvalue())


if __name__ == "__main__":
    unittest.main()
