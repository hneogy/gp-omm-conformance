# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The item statuses of two WRONG parsers on the full data, pinned (D-320, the hardening review's T1).

The suite ran one parser against provider data, the reference adapter, which must pass; so a check that only provider
data exercises could go lenient, or stop running, and no test would say so: mutation testing left 113 logic mutants
alive in those checks. Here the naive adapter and python-sgp4 2.27 are run on every case and every item they produce
is held to a recorded status: the check, the file and whether it passed, failed, skipped or was not exercised. A
change to the runner that moves one of them fails this test, and the golden file is then regenerated on purpose, with
the difference read:

    python tests/test_item_statuses.py --write

A release-time test: it needs the maintainer's provider files, launch-window captures included, which no fetch
brings, and skips without them (a fresh clone, an export, public CI). The golden files hold check ids, file names and
statuses only: no provider value."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gpconf.runner import Runner  # noqa: E402

GOLDEN = os.path.join(ROOT, "tests", "golden")
CAPTURE = os.path.join(ROOT, "fixtures", "nine-digit-supgp-launch-nominals", "raw", "starlink-g15-27.csv")   # a launch-window file: the maintainer's copy only


def full_data():
    return os.path.exists(CAPTURE)


def adapters():
    from gpconf.adapters.naive import Parser as Naive
    out = {"naive": (Naive, None)}
    try:
        import sgp4
        from gpconf.adapters.sgp4_adapter import Parser as Sgp4
        out["sgp4"] = (Sgp4, getattr(sgp4, "__version__", None))
    except ImportError:
        pass
    return out


def statuses(parser):
    results = Runner(parser, root=ROOT, fetch_hints=False).run()
    return {r.case_id: {"status": r.status, "items": [[i.check, os.path.basename(i.file) if i.file else None, i.status] for i in r.items]} for r in results}


class ItemStatusesOnTheFullData(unittest.TestCase):
    maxDiff = None

    def check(self, name):
        if not full_data():
            self.skipTest("the maintainer's provider files are not on disk (a fresh clone, an export, public CI)")
        found = adapters()
        if name not in found:
            self.skipTest(f"the library behind the {name} adapter is not installed")
        cls, version = found[name]
        with open(os.path.join(GOLDEN, f"item-statuses-{name}.json"), encoding="utf-8") as f:
            golden = json.load(f)
        if golden.get("library_version") != version:
            self.skipTest(f"recorded with {golden.get('library_version')}, installed {version}: a different library is a different run")
        got = statuses(cls())
        self.assertEqual(sorted(got), sorted(golden["cases"]))
        for case in golden["cases"]:
            with self.subTest(case=case):
                self.assertEqual(got[case]["status"], golden["cases"][case]["status"])
                self.assertEqual(got[case]["items"], golden["cases"][case]["items"])

    def test_naive(self):
        self.check("naive")

    def test_python_sgp4(self):
        self.check("sgp4")

    def test_the_golden_files_hold_failures_and_no_provider_value(self):
        for name in ("naive", "sgp4"):
            with open(os.path.join(GOLDEN, f"item-statuses-{name}.json"), encoding="utf-8") as f:
                golden = json.load(f)
            items = [i for c in golden["cases"].values() for i in c["items"]]
            self.assertGreater(sum(1 for i in items if i[2] == "fail"), 20, name)       # a wrong parser: it must be failing things
            self.assertTrue(all(len(i) == 3 and i[2] in ("pass", "pass-tolerance", "fail", "skip", "not-exercised", "not-fetched", "not-available", "info") for i in items))


if __name__ == "__main__":
    if "--write" in sys.argv:
        import gpconf
        if not full_data():
            sys.exit("the maintainer's provider files are not on disk: nothing written")
        os.makedirs(GOLDEN, exist_ok=True)
        for name, (cls, version) in adapters().items():
            cases = statuses(cls())
            with open(os.path.join(GOLDEN, f"item-statuses-{name}.json"), "w", encoding="utf-8") as f:
                json.dump({"adapter": name, "library_version": version, "recorded_with_gpconf": gpconf.__version__, "cases": cases}, f, indent=0, sort_keys=True)
                f.write("\n")
            n = sum(len(c["items"]) for c in cases.values())
            print(f"{name}: {len(cases)} cases, {n} items, {sum(1 for c in cases.values() for i in c['items'] if i[2] == 'fail')} failing")
    else:
        unittest.main()
