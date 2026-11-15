# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The generated upstream table and its check against GitHub (D-552, D-553), offline: a synthetic ledger section and
recorded GitHub answers, with each kind of mismatch planted once.

Run: python -m unittest tests.test_upstream_table"""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import upstream_table as ut  # noqa: E402
import check_upstream_table as cu  # noqa: E402

G = "https://github.com"
LEDGER = f"""# ledger

## 2. Something else
- **ignored**: not in section 3. [#1]({G}/a/b/issues/1), open.

## 3. Grouped (the owner's three groups)

#### Fixed by my pull requests (2)

- **libone**: an empty field raised an error. [#10]({G}/o/libone/issues/10), [PR #11]({G}/o/libone/pull/11), merged 2026-09-24, not yet released.
- **libtwo**: epochs truncated. [#5]({G}/o/libtwo/issues/5), [PR #6]({G}/o/libtwo/pull/6), merged 2026-09-26, released in [7.2.0]({G}/o/libtwo/releases/tag/7.2.0).

#### Fixed by maintainers and contributors after my report (2)

- **libthree**: six-digit ids refused. [#4]({G}/o/libthree/issues/4), fixed by someone, the maintainer, released in 4.1.0.
- **libfour**: one bad set lost the file. [#8]({G}/o/libfour/issues/8), [PR #9]({G}/o/libfour/pull/9), fixed by someone, a contributor, released in v1.0.4.

#### Reported, still open (1)

- **libfive**: a letter read as a digit. [#3]({G}/o/libfive/issues/3), open.

#### Ended another way (2)

- **libsix**: a letter accepted. [#7]({G}/o/libsix/issues/7), closed by the maintainer without a change.
- **libseven**: sets dropped. [#2]({G}/o/libseven/issues/2), closed by the reporter after the maintainers said it was planned; status: closed (maintainers said planned).

#### Per library

- **a note**: not a finding. [#99]({G}/o/x/issues/99).

## 4. Public items that cite gpconf
- **cited**: not counted. [#1]({G}/o/y/pull/1).

## 5. Observed, not reported (private)
- **secret**: never in the table. [#1]({G}/o/z/issues/1).
"""


def answers(**overrides):
    a = {
        "/repos/o/libone/issues/10": {"state": "closed", "created_at": "2026-09-23T10:00:00Z", "closed_at": "2026-09-24T12:00:00Z"},
        "/repos/o/libone/pulls/11": {"state": "closed", "merged": True, "merged_at": "2026-09-24T12:00:00Z", "created_at": "2026-09-23T11:00:00Z",
                                     "merge_commit_sha": "c" * 40},
        "/repos/o/libone/releases/latest": {"tag_name": "2.27"},
        f"/repos/o/libone/compare/{'c' * 40}...2.27": {"status": "behind"},
        "/repos/o/libtwo/issues/5": {"state": "closed", "created_at": "2026-09-20T10:00:00Z", "closed_at": "2026-09-26T09:00:00Z"},
        "/repos/o/libtwo/pulls/6": {"state": "closed", "merged": True, "merged_at": "2026-09-26T09:00:00Z", "created_at": "2026-09-21T10:00:00Z"},
        "/repos/o/libtwo/releases/tags/7.2.0": {"tag_name": "7.2.0", "published_at": "2026-11-11T22:22:13Z"},
        "/repos/o/libthree/issues/4": {"state": "closed", "created_at": "2026-09-22T10:00:00Z", "closed_at": "2026-09-25T10:00:00Z"},
        "/repos/o/libthree/issues/4/events": [{"event": "referenced", "commit_id": "a" * 40}, {"event": "closed", "commit_id": "b" * 40}],
        f"/repos/o/libthree/commits/{'b' * 40}": {"sha": "b" * 40, "commit": {"committer": {"date": "2026-09-25T09:00:00Z"}}},
        "/repos/o/libthree/releases/tags/4.1.0": {"tag_name": "4.1.0", "published_at": "2026-09-30T00:00:00Z"},
        "/repos/o/libfour/issues/8": {"state": "closed", "created_at": "2026-10-01T10:00:00Z", "closed_at": "2026-10-03T10:00:00Z"},
        "/repos/o/libfour/pulls/9": {"state": "closed", "merged": True, "merged_at": "2026-10-03T10:00:00Z", "created_at": "2026-10-02T10:00:00Z"},
        "/repos/o/libfour/releases/tags/v1.0.4": {"_status": 404},
        "/repos/o/libfour/git/ref/tags/v1.0.4": {"ref": "refs/tags/v1.0.4"},
        "/repos/o/libfive/issues/3": {"state": "open", "created_at": "2026-10-05T10:00:00Z", "closed_at": None},
        "/repos/o/libsix/issues/7": {"state": "closed", "created_at": "2026-09-27T10:00:00Z", "closed_at": "2026-09-28T10:00:00Z"},
        "/repos/o/libseven/issues/2": {"state": "closed", "created_at": "2026-09-24T10:00:00Z", "closed_at": "2026-09-30T10:00:00Z"},
    }
    a.update(overrides)
    return a


def recorded(a):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(a, f)
    f.close()
    return f.name


def build(a=None):
    """rows from the synthetic ledger, completed with facts recorded from the synthetic answers."""
    rows, counts = ut.parse_ledger(LEDGER)
    path = recorded(a or answers())
    try:
        _, facts = cu.check({"rows": [dict(r, proof=(r["prs"] or r["issues"])[-1], date=None, date_is=None) for r in rows]},
                            cu.Recorded(path), record={})
        gaps = ut.complete(rows, facts)
    finally:
        os.unlink(path)
    return rows, counts, gaps


def run_check(rows, a):
    path = recorded(a)
    try:
        return cu.check({"rows": rows}, cu.Recorded(path))[0]
    finally:
        os.unlink(path)


class TheLedgerIsParsed(unittest.TestCase):
    def test_only_section_3s_four_groups_are_rows(self):
        rows, counts = ut.parse_ledger(LEDGER)
        self.assertEqual([r["library"] for r in rows], ["libone", "libtwo", "libthree", "libfour", "libfive", "libsix", "libseven"])
        self.assertEqual(counts, {"my-pr": 2, "maintainer": 2, "open": 1, "other": 2})
        self.assertFalse({"ignored", "a note", "cited", "secret"} & {r["library"] for r in rows})   # D-134: section 5 never read

    def test_statuses_releases_and_dates(self):
        rows = {r["library"]: r for r in ut.parse_ledger(LEDGER)[0]}
        self.assertEqual({k: r["status"] for k, r in rows.items()},
                         {"libone": "merged", "libtwo": "released", "libthree": "released", "libfour": "released",
                          "libfive": "open", "libsix": "declined", "libseven": "closed-planned"})
        self.assertEqual(rows["libtwo"]["release"], {"name": "7.2.0", "url": f"{G}/o/libtwo/releases/tag/7.2.0"})
        self.assertEqual(rows["libfour"]["release"], {"name": "v1.0.4", "url": None})
        self.assertEqual(rows["libone"]["merged"], "2026-09-24")
        self.assertEqual(rows["libone"]["finding"], "an empty field raised an error")


class GapsAreFilledFromTheRecordedFacts(unittest.TestCase):
    def test_complete_table_has_no_gap(self):
        rows, _, gaps = build()
        self.assertEqual(gaps, [])
        r = {x["library"]: x for x in rows}
        self.assertEqual(r["libthree"]["proof"], f"{G}/o/libthree/commit/{'b' * 40}")   # the closing commit, not a referencing one
        self.assertEqual(r["libthree"]["release"]["url"], f"{G}/o/libthree/releases/tag/4.1.0")
        self.assertEqual(r["libfour"]["release"]["url"], f"{G}/o/libfour/releases/tag/v1.0.4")   # a tag with no release page
        self.assertEqual((r["libfive"]["date"], r["libfive"]["date_is"]), ("2026-10-05", "reported"))
        self.assertEqual((r["libsix"]["date"], r["libsix"]["date_is"]), ("2026-09-28", "closed"))
        self.assertEqual((r["libfour"]["date"], r["libfour"]["date_is"]), ("2026-10-03", "merged"))
        self.assertEqual((r["libthree"]["date"], r["libthree"]["date_is"]), ("2026-09-25", "merged"))   # the fixing commit's date

    def test_without_facts_the_gaps_are_named(self):
        rows, _ = ut.parse_ledger(LEDGER)
        gaps = ut.complete(rows, {})
        self.assertTrue(any(g.startswith("libthree:") and "no proof link" in g for g in gaps), gaps)
        self.assertTrue(any(g.startswith("libfive:") and "no date" in g for g in gaps), gaps)
        self.assertFalse(any(g.startswith("libone:") for g in gaps), gaps)   # the ledger has all of libone


class TheCheckFindsEachMismatch(unittest.TestCase):
    def setUp(self):
        self.rows, _, gaps = build()
        self.assertEqual(gaps, [])

    def test_a_consistent_table_passes(self):
        self.assertEqual(run_check(self.rows, answers()), [])

    def test_a_merged_row_whose_pr_is_not_merged(self):
        p = run_check(self.rows, answers(**{"/repos/o/libone/pulls/11": {"state": "closed", "merged": False, "merged_at": None}}))
        self.assertTrue(any("libone" in x and "not merged" in x for x in p), p)

    def test_an_open_row_whose_issue_is_closed(self):
        p = run_check(self.rows, answers(**{"/repos/o/libfive/issues/3": {"state": "closed", "created_at": "2026-10-05T10:00:00Z"}}))
        self.assertTrue(any("libfive" in x and "marked open" in x for x in p), p)

    def test_a_declined_row_whose_issue_is_open(self):
        p = run_check(self.rows, answers(**{"/repos/o/libsix/issues/7": {"state": "open", "created_at": "2026-09-27T10:00:00Z"}}))
        self.assertTrue(any("libsix" in x and "marked declined" in x for x in p), p)

    def test_a_link_that_does_not_resolve(self):
        a = answers(); a.pop("/repos/o/libtwo/issues/5")
        p = run_check(self.rows, a)
        self.assertTrue(any("libtwo" in x and "does not resolve" in x for x in p), p)

    def test_a_release_that_does_not_exist(self):
        a = answers(); a.pop("/repos/o/libtwo/releases/tags/7.2.0")
        p = run_check(self.rows, a)
        self.assertTrue(any("releases/tag/7.2.0 does not resolve" in x for x in p), p)

    def test_a_date_more_than_a_day_off(self):
        rows = [dict(r, date="2026-09-01") if r["library"] == "libone" else r for r in self.rows]
        p = run_check(rows, answers())
        self.assertTrue(any("libone" in x and "dated 2026-09-01" in x for x in p), p)

    def test_a_date_a_day_off_is_a_time_zone(self):
        rows = [dict(r, date="2026-09-25") if r["library"] == "libone" else r for r in self.rows]
        self.assertEqual(run_check(rows, answers()), [])

    def test_a_merged_fix_that_has_shipped_since(self):
        p = run_check(self.rows, answers(**{f"/repos/o/libone/compare/{'c' * 40}...2.27": {"status": "ahead"}}))
        self.assertTrue(any("libone" in x and "2.27 already holds" in x for x in p), p)

    def test_a_hand_closed_issue_takes_the_commit_that_referenced_it(self):
        a = answers(**{"/repos/o/libthree/issues/4/events": [
            {"event": "referenced", "commit_id": "d" * 40, "created_at": "2026-09-25T08:00:00Z"},
            {"event": "closed", "commit_id": None, "created_at": "2026-09-25T10:00:00Z"},
            {"event": "referenced", "commit_id": "e" * 40, "created_at": "2026-09-26T10:00:00Z"}]})
        path = recorded(a)
        try:
            self.assertEqual(cu.closing_commit(cu.Recorded(path), f"{G}/o/libthree/issues/4"), f"{G}/o/libthree/commit/{'d' * 40}")
        finally:
            os.unlink(path)

    def test_a_fix_whose_proof_is_an_issue(self):
        rows = [dict(r, proof=r["issues"][0]) if r["library"] == "libthree" else r for r in self.rows]
        p = run_check(rows, answers())
        self.assertTrue(any("libthree" in x and "must be a merged pull request or a commit" in x for x in p), p)


class InvolvementNotesStatusesAndPrivateNotes(unittest.TestCase):
    """D-560: a row where gpconf did not find the issue says what it did; the long detail lives in "Private notes:",
    never read; only the allowed statuses pass."""
    def test_involvement_is_split_from_the_finding_and_rendered_after_it(self):
        r = ut.parse_bullet(f"- **libx**: TLEs refused; involvement: reproduced and fix verified with gpconf. [#35]({G}/o/x/issues/35), "
                            f"[PR #47]({G}/o/x/pull/47), merged 2026-11-10, released in v1.6.1 (2026-11-11). Private notes: opened by someone else.", "my-pr")
        self.assertEqual((r["finding"], r["involvement"]), ("TLEs refused", "reproduced and fix verified with gpconf"))
        self.assertEqual(r["release"]["name"], "v1.6.1")
        r.update(proof=f"{G}/o/x/pull/47", date="2026-11-10", date_is="merged", release={"name": "v1.6.1", "url": f"{G}/o/x/releases/tag/v1.6.1"})
        md = ut.render({"as_of": "x", "summary": {"total": 1, "my-pr": 1, "maintainer": 0, "open": 0, "other": 0}, "rows": [r]})
        self.assertIn("| TLEs refused (reproduced and fix verified with gpconf) |", md)
        self.assertTrue(md.startswith("| library | finding | status |"))

    def test_private_notes_are_never_read(self):
        r = ut.parse_bullet(f"- **libx**: a finding. [#1]({G}/o/x/issues/1), open. Private notes: SECRET-DETAIL [#9]({G}/o/x/issues/9).", "open")
        self.assertNotIn("SECRET-DETAIL", json.dumps(r))
        self.assertEqual(r["issues"], [f"{G}/o/x/issues/1"])

    def test_a_close_without_a_reason_is_a_gap(self):
        r = ut.parse_bullet(f"- **libx**: a finding. [#1]({G}/o/x/issues/1), closed by the reporter.", "other")
        self.assertEqual(r["status"], "unclassified")
        gaps = ut.complete([r], {f"{G}/o/x/issues/1": {"state": "closed", "closed_at": "2026-09-27T00:00:00Z"}})
        self.assertTrue(any("allowed status" in g for g in gaps), gaps)

    def test_merged_with_no_releases(self):
        r = ut.parse_bullet(f"- **libx**: a finding. [#84]({G}/o/x/issues/84), [PR #85]({G}/o/x/pull/85), fixed by someone, the maintainer, "
                            "on master; status: merged; the project has no releases.", "maintainer")
        self.assertEqual(r["status"], "merged-no-releases")
        a = {"/repos/o/x/issues/84": {"state": "closed", "created_at": "2026-11-09T00:00:00Z"},
             "/repos/o/x/pulls/85": {"state": "closed", "merged": True, "merged_at": "2026-11-10T00:00:00Z"},
             "/repos/o/x/releases": []}
        ut.complete([r], {f"{G}/o/x/pull/85": {"merged": True, "merged_at": "2026-11-10T00:00:00Z"}})
        self.assertEqual(run_check([r], a), [])
        a["/repos/o/x/releases"] = [{"tag_name": "v1.0"}]
        p = run_check([r], a)
        self.assertTrue(any("says the project has no releases, but GitHub lists v1.0" in x for x in p), p)

    def test_the_table_never_claims_a_find_it_did_not_make(self):
        r = dict(build()[0][0], involvement="reported by another user; gpconf tested the fix", finding="x; found by gpconf")
        p = run_check([r], answers())
        self.assertTrue(any("says gpconf found it" in x for x in p), p)
        r = dict(r, finding="x", involvement="found by gpconf")
        p = run_check([r], answers())
        self.assertTrue(any("may not claim a find" in x for x in p), p)

    def test_an_unknown_status_fails_the_check(self):
        r = dict(build()[0][0], status="closed")
        p = run_check([r], answers())
        self.assertTrue(any("is not one of the allowed ones" in x for x in p), p)


class GivenProofsAndInferredLinks(unittest.TestCase):
    """D-558: a fix with no pull request may name its release notes as the proof, and a commit the ledger can only
    infer is shown beside it, labelled as inferred; the check fails an inferred link whose label does not say so."""
    BULLET = (f"- **libnine**: ids refused. [#4]({G}/o/libnine/issues/4), fixed by someone, the maintainer, released in "
              f"[4.1.0]({G}/o/libnine/releases/tag/4.1.0); proof: [4.1.0 release notes]({G}/o/libnine/releases/tag/4.1.0); "
              f"likely fixing commit (inferred: only code change in 4.1.0, no commit references #4): [a416eea]({G}/o/libnine/commit/{'f' * 40}).")
    ANSWERS = {"/repos/o/libnine/issues/4": {"state": "closed", "created_at": "2026-10-08T10:00:00Z", "closed_at": "2026-10-11T04:30:31Z"},
               "/repos/o/libnine/releases/tags/4.1.0": {"tag_name": "4.1.0", "published_at": "2026-10-11T04:29:12Z"},
               f"/repos/o/libnine/commits/{'f' * 40}": {"sha": "f" * 40, "commit": {"committer": {"date": "2026-10-11T04:15:39Z"}}}}

    def row(self):
        r = ut.parse_bullet(self.BULLET, "maintainer")
        facts = {f"{G}/o/libnine/releases/tag/4.1.0": {"exists": True, "published_at": "2026-10-11T04:29:12Z", "resolves": True}}
        self.assertEqual(ut.complete([r], facts), [])
        return r

    def test_the_parts_are_read(self):
        r = self.row()
        self.assertEqual(r["proof"], f"{G}/o/libnine/releases/tag/4.1.0")
        self.assertEqual((r["date"], r["date_is"]), ("2026-10-11", "released"))
        self.assertEqual(r["commits"], [])   # the inferred commit is never taken as the proof
        self.assertTrue(r["inferred"]["label"].startswith("likely fixing commit (inferred:"))
        self.assertEqual(r["finding"], "ids refused")

    def test_rendered_with_its_label(self):
        r = self.row()
        md = ut.render({"as_of": "x", "summary": {"total": 1, "my-pr": 0, "maintainer": 1, "open": 0, "other": 0}, "rows": [r]})
        self.assertIn(f"[4.1.0 release notes]({G}/o/libnine/releases/tag/4.1.0); likely fixing commit (inferred: only code change in 4.1.0, no commit references #4): [a416eea]", md)

    def test_the_check_passes_it(self):
        self.assertEqual(run_check([self.row()], self.ANSWERS), [])

    def test_an_inferred_link_without_its_label_fails(self):
        r = self.row()
        r["inferred"] = dict(r["inferred"], label="fixing commit")
        p = run_check([r], self.ANSWERS)
        self.assertTrue(any("is inferred but its label does not say so" in x for x in p), p)

    def test_a_release_proof_the_ledger_did_not_give_fails(self):
        r = dict(self.row(), proof_given=None)
        p = run_check([r], self.ANSWERS)
        self.assertTrue(any("must be a merged pull request or a commit" in x for x in p), p)


class TheTableIsRenderedAndInjected(unittest.TestCase):
    def test_render_and_inject_round_trip(self):
        rows, counts, _ = build()
        table = {"as_of": "2026-11-14", "summary": dict(counts, total=len(rows)), "rows": rows}
        md = ut.render(table)
        self.assertEqual(sum(1 for l in md.splitlines() if l.startswith("| ")), len(rows) + 1)   # the header and one row per finding
        self.assertIn("7 findings: 2 fixed by this project's pull requests, 2 by maintainers", md)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "README.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(f"intro\n{ut.BEGIN}\nold\n{ut.END}\noutro\n")
            self.assertTrue(ut.inject(p, md))
            self.assertFalse(ut.inject(p, md))   # a second run changes nothing
            with open(p, encoding="utf-8") as f:
                text = f.read()
            self.assertTrue(text.startswith("intro\n") and text.endswith(f"{ut.END}\noutro\n") and "old" not in text)

    def test_the_committed_files_carry_the_committed_table(self):
        path = os.path.join(ROOT, "docs", "upstream", "table.json")
        if not os.path.exists(path):
            self.skipTest("no docs/upstream/table.json yet")
        table = json.load(open(path, encoding="utf-8"))
        block = ut.render(table)
        for rel in ("README.md", "docs/LIBRARIES.md"):
            text = open(os.path.join(ROOT, rel), encoding="utf-8").read()
            if ut.BEGIN in text:
                self.assertIn(ut.BEGIN + "\n" + block + ut.END, text, rel)


class TheRealLedger(unittest.TestCase):
    def test_the_private_ledger_parses_to_its_own_counts(self):
        path = os.path.join(ROOT, "docs", "handoff", "upstream-ledger.md")
        if not os.path.exists(path):
            self.skipTest("the ledger is private: this runs in the private repository")
        rows, counts = ut.parse_ledger(open(path, encoding="utf-8").read())
        got = {g: sum(1 for r in rows if r["group"] == g) for _, g in ut.GROUPS}
        self.assertEqual(got, counts)


if __name__ == "__main__":
    unittest.main()
