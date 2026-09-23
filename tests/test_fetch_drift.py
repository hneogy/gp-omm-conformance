"""tools/fetch.py drift check: stable-tier sources whose bytes differ from the manifest are reported."""
import hashlib
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import fetch  # noqa: E402


def make_root(tmp, stable_bytes, live_bytes):
    d = os.path.join(tmp, "fixtures", "c", "raw")
    os.makedirs(d)
    for name, data in (("s.csv", stable_bytes), ("l.csv", live_bytes)):
        with open(os.path.join(d, name), "wb") as f:
            f.write(data)
        with open(os.path.join(d, name + ".meta.json"), "w") as f:
            json.dump({"sha256": hashlib.sha256(data).hexdigest()}, f)
    manifest = {"cases": [{"id": "c", "sources": [
        {"path": "fixtures/c/raw/s.csv", "tier": "stable", "sha256": hashlib.sha256(b"STABLE").hexdigest()},
        {"path": "fixtures/c/raw/l.csv", "tier": "live", "sha256": hashlib.sha256(b"LIVE").hexdigest()},
    ]}, {"id": "other", "sources": [{"path": "fixtures/c/raw/s.csv", "tier": "mixed", "sha256": hashlib.sha256(b"STABLE").hexdigest()}]}]}
    with open(os.path.join(tmp, "manifest.json"), "w") as f:
        json.dump(manifest, f)
    return [{"case": "c", "file": "s.csv"}, {"case": "c", "file": "l.csv"}, {"case": "c", "file": "absent.csv"}]


class DriftTests(unittest.TestCase):
    def test_match_and_drift_are_distinguished(self):
        with tempfile.TemporaryDirectory() as tmp:
            entries = make_root(tmp, b"STABLE", b"LIVE-NEWER")
            rep = {r["path"]: r for r in fetch.drift_report(entries, root=tmp)}
            self.assertEqual(rep["fixtures/c/raw/s.csv"]["status"], "match")
            self.assertEqual(rep["fixtures/c/raw/s.csv"]["tier"], "stable")  # 'stable' wins over 'mixed'
            self.assertEqual(rep["fixtures/c/raw/l.csv"]["status"], "drift")
            self.assertEqual(rep["fixtures/c/raw/l.csv"]["tier"], "live")
            self.assertEqual(rep["fixtures/c/raw/absent.csv"]["status"], "missing")
            self.assertEqual(fetch.print_drift(list(rep.values())), 0)  # no STABLE drift

    def test_stable_drift_is_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            entries = make_root(tmp, b"STABLE-CHANGED", b"LIVE")
            rep = fetch.drift_report(entries, root=tmp)
            stable = next(r for r in rep if r["path"].endswith("s.csv"))
            self.assertEqual((stable["status"], stable["tier"]), ("drift", "stable"))
            self.assertEqual(fetch.print_drift(rep), 1)

    def test_real_manifest_and_snapshot_agree_where_present(self):
        entries = json.load(open(os.path.join(ROOT, "tools", "fetchlist.json")))
        present = [e for e in entries if os.path.exists(os.path.join(ROOT, "fixtures", e["case"], "raw", e["file"]))]
        if not present:
            self.skipTest("no raw files in this checkout")
        rep = fetch.drift_report(present, root=ROOT)
        self.assertFalse([r for r in rep if r["status"] == "drift" and r["tier"] == "stable"], "stable source drifted from the manifest")



class RealManifestTiers(unittest.TestCase):
    def test_real_manifest_tiers(self):
        # "stable wins when several cases list one path" gives the right answer only if no case mislabels a
        # live file as stable (D-114): the two rolling group files are live, and the stable raw sources are the
        # corpus's 22 gp-first files, the count the tracker site checks (it changes only when a case is added)
        src = fetch.manifest_sources(ROOT)
        self.assertEqual(src["fixtures/analyst-objects/raw/analyst.csv"]["tier"], "live")
        self.assertEqual(src["fixtures/tle-omits-six-digit-objects/raw/last-30-days.csv"]["tier"], "live")
        self.assertEqual(sum(1 for p, e in src.items() if p.startswith("fixtures/") and e["tier"] == "stable"), 22)


if __name__ == "__main__":
    unittest.main()
