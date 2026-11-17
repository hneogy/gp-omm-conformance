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
                                     "merge_commit_sha": "c" * 40, "user": {"login": "hneogy"}},
        "/repos/o/libone/releases/latest": {"tag_name": "2.27"},
        f"/repos/o/libone/compare/{'c' * 40}...2.27": {"status": "behind"},
        "/repos/o/libtwo/issues/5": {"state": "closed", "created_at": "2026-09-20T10:00:00Z", "closed_at": "2026-09-26T09:00:00Z"},
        "/repos/o/libtwo/pulls/6": {"state": "closed", "merged": True, "merged_at": "2026-09-26T09:00:00Z", "created_at": "2026-09-21T10:00:00Z",
                                    "merge_commit_sha": "e" * 40, "user": {"login": "HNeogy"}},
        # GitHub's tag order is not version order: the check sorts by version itself
        "/repos/o/libtwo/tags?per_page=100&page=1": [{"name": "7.2.0-rc1"}, {"name": "7.0.0"}, {"name": "7.2.0"}, {"name": "7.1.0"}],
        "/repos/o/libtwo/commits/7.2.0": {"commit": {"committer": {"date": "2026-11-11T22:00:00Z"}}},
        "/repos/o/libtwo/commits/7.1.0": {"commit": {"committer": {"date": "2026-09-01T00:00:00Z"}}},
        "/repos/o/libtwo/commits/7.0.0": {"commit": {"committer": {"date": "2026-06-01T00:00:00Z"}}},
        f"/repos/o/libtwo/compare/{'e' * 40}...7.0.0": {"status": "behind"},
        f"/repos/o/libtwo/compare/{'e' * 40}...7.2.0": {"status": "ahead"},
        f"/repos/o/libtwo/compare/{'e' * 40}...7.1.0": {"status": "behind"},
        "/repos/o/libtwo/releases/tags/7.2.0": {"tag_name": "7.2.0", "published_at": "2026-11-11T22:22:13Z"},
        "/repos/o/libthree/issues/4": {"state": "closed", "created_at": "2026-09-22T10:00:00Z", "closed_at": "2026-09-25T10:00:00Z"},
        "/repos/o/libthree/issues/4/events": [{"event": "referenced", "commit_id": "a" * 40}, {"event": "closed", "commit_id": "b" * 40}],
        f"/repos/o/libthree/commits/{'b' * 40}": {"sha": "b" * 40, "commit": {"committer": {"date": "2026-09-25T09:00:00Z"}},
                                                  "author": {"login": "maint"}},
        "/repos/o/libthree/tags?per_page=100&page=1": [{"name": "4.1.0"}],
        f"/repos/o/libthree/compare/{'b' * 40}...4.1.0": {"status": "identical"},
        "/repos/o/libthree/releases/tags/4.1.0": {"tag_name": "4.1.0", "published_at": "2026-09-30T00:00:00Z"},
        "/repos/o/libfour/issues/8": {"state": "closed", "created_at": "2026-10-01T10:00:00Z", "closed_at": "2026-10-03T10:00:00Z"},
        "/repos/o/libfour/pulls/9": {"state": "closed", "merged": True, "merged_at": "2026-10-03T10:00:00Z", "created_at": "2026-10-02T10:00:00Z",
                                     "merge_commit_sha": "9" * 40, "user": {"login": "contrib"}},
        "/repos/o/libfour/tags?per_page=100&page=1": [{"name": "v1.0.4"}, {"name": "v1.0.3"}],
        "/repos/o/libfour/commits/v1.0.4": {"commit": {"committer": {"date": "2026-10-04T00:00:00Z"}}},
        "/repos/o/libfour/commits/v1.0.3": {"commit": {"committer": {"date": "2026-09-01T00:00:00Z"}}},
        f"/repos/o/libfour/compare/{'9' * 40}...v1.0.4": {"status": "ahead"},
        f"/repos/o/libfour/compare/{'9' * 40}...v1.0.3": {"status": "behind"},
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

    def test_another_users_report_whose_issue_is_closed_fails(self):
        """The owner's ruling of 2026-11-16: a row under "another user's report, open upstream" is checked as open is."""
        r = ut.parse_bullet(f"- **libeight**: a field refused; involvement: reported by another user. [#12]({G}/o/libeight/issues/12); "
                            "status: another user's report, open upstream.", "other")
        ut.complete([r], {})
        self.assertEqual((r["status"], ut.STATUS_WORD[r["status"]]), ("open-others-report", "another user's report, open upstream"))
        is_open = {"/repos/o/libeight/issues/12": {"state": "open", "created_at": "2026-08-20T10:00:00Z", "closed_at": None}}
        self.assertEqual(run_check(self.rows + [r], answers(**is_open)), [])
        closed = {"/repos/o/libeight/issues/12": {"state": "closed", "created_at": "2026-08-20T10:00:00Z", "closed_at": "2026-11-16T00:00:00Z"}}
        p = run_check(self.rows + [r], answers(**closed))
        self.assertTrue(any("libeight" in x and "marked open" in x for x in p), p)

    def test_the_summary_names_another_users_report_apart(self):
        rows = [{"status": "open-others-report"}, {"status": "declined"}, {"status": "closed-planned"}]
        md = ut.render({"as_of": "x", "summary": {"total": 3, "my-pr": 0, "maintainer": 0, "open": 0, "other": 3}, "rows": []})
        self.assertIn("3 that ended another way;", md)
        md = ut.render({"as_of": "x", "summary": {"total": 3, "my-pr": 0, "maintainer": 0, "open": 0, "other": 3},
                        "rows": [dict(library="l", finding="f", issues=[], prs=[], commits=[], release=None, proof=None, date=None,
                                      inferred=None, proof_given=None, involvement=None, opt_in=None, **x) for x in rows]})
        self.assertIn("3 others: 2 that ended another way and 1 another user's report;", md)

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
             "/repos/o/x/pulls/85": {"state": "closed", "merged": True, "merged_at": "2026-11-10T00:00:00Z", "user": {"login": "maint"}},
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
               f"/repos/o/libnine/commits/{'f' * 40}": {"sha": "f" * 40, "commit": {"committer": {"date": "2026-10-11T04:15:39Z"}},
                                                  "author": {"login": "maint"}},
               "/repos/o/libnine/tags?per_page=100&page=1": [{"name": "4.1.0"}, {"name": "4.0.0"}],
               "/repos/o/libnine/commits/4.1.0": {"commit": {"committer": {"date": "2026-10-11T04:15:39Z"}}},
               "/repos/o/libnine/commits/4.0.0": {"commit": {"committer": {"date": "2026-06-01T00:00:00Z"}}},
               f"/repos/o/libnine/compare/{'f' * 40}...4.1.0": {"status": "ahead"},
               f"/repos/o/libnine/compare/{'f' * 40}...4.0.0": {"status": "behind"}}

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


class AuthorshipReleasesAndReleaseOnlyFixes(unittest.TestCase):
    """The three checks the owner added for 0.9.1 (the site's S-164 ruling): whose pull request fixed it, whether the
    named release holds the fix and is the first that does, and whether a fix shown only by its release notes has its
    report closed. Each mismatch is planted once on the consistent synthetic table."""
    def setUp(self):
        self.rows, _, gaps = build()
        self.assertEqual(gaps, [])

    def check(self, a, rows=None):
        unchecked = []
        path = recorded(a)
        try:
            p = cu.check({"rows": rows or self.rows}, cu.Recorded(path), unchecked=unchecked)[0]
        finally:
            os.unlink(path)
        return p, unchecked

    def test_the_consistent_table_passes_all_three_with_nothing_unchecked(self):
        self.assertEqual(self.check(answers()), ([], []))

    def test_a_my_pr_row_whose_pull_request_is_someone_elses(self):
        a = answers(); a["/repos/o/libtwo/pulls/6"] = dict(a["/repos/o/libtwo/pulls/6"], user={"login": "someone"})
        p, _ = self.check(a)
        self.assertTrue(any("libtwo" in x and "fixed by my pull requests" in x and "is by someone" in x for x in p), p)

    def test_a_maintainer_row_whose_pull_request_is_the_owners(self):
        a = answers(); a["/repos/o/libfour/pulls/9"] = dict(a["/repos/o/libfour/pulls/9"], user={"login": "hneogy"})
        p, _ = self.check(a)
        self.assertTrue(any("libfour" in x and "is the owner's" in x for x in p), p)

    def test_a_maintainer_row_whose_commit_is_the_owners(self):
        a = answers(); a[f"/repos/o/libthree/commits/{'b' * 40}"] = dict(a[f"/repos/o/libthree/commits/{'b' * 40}"], author={"login": "hneogy"})
        p, _ = self.check(a)
        self.assertTrue(any("libthree" in x and "is the owner's" in x for x in p), p)

    def test_the_owner_is_a_setting(self):
        p, _ = self.check(answers(), )
        self.assertEqual(p, [])
        path = recorded(answers())
        try:
            p = cu.check({"rows": self.rows}, cu.Recorded(path), owner="someone-else", unchecked=[])[0]
        finally:
            os.unlink(path)
        self.assertTrue(any("libone" in x and "is by hneogy" in x for x in p), p)

    def test_an_author_github_does_not_name_is_not_a_pass(self):
        a = answers(); a["/repos/o/libfour/pulls/9"] = {k: v for k, v in a["/repos/o/libfour/pulls/9"].items() if k != "user"}
        p, u = self.check(a)
        self.assertEqual(p, [])
        self.assertTrue(any("libfour" in x and "names no author" in x for x in u), u)
        self.assertTrue(any("names no author" in x for x in run_check(self.rows, a)))   # without a list, it is a problem

    def test_a_release_that_does_not_hold_the_fix(self):
        p, _ = self.check(answers(**{f"/repos/o/libtwo/compare/{'e' * 40}...7.2.0": {"status": "behind"}}))
        self.assertTrue(any("libtwo" in x and "7.2.0 does not hold" in x for x in p), p)

    def test_a_release_whose_commit_proof_it_does_not_hold(self):
        p, _ = self.check(answers(**{f"/repos/o/libthree/compare/{'b' * 40}...4.1.0": {"status": "diverged"}}))
        self.assertTrue(any("libthree" in x and "4.1.0 does not hold" in x for x in p), p)

    def test_an_earlier_release_already_held_it(self):
        p, _ = self.check(answers(**{f"/repos/o/libtwo/compare/{'e' * 40}...7.1.0": {"status": "ahead"}}))
        self.assertTrue(any("libtwo" in x and "the earlier release 7.1.0 already holds" in x for x in p), p)

    def test_a_pre_release_before_it_is_not_the_earlier_release(self):
        a = answers(**{f"/repos/o/libtwo/compare/{'e' * 40}...7.2.0-rc1": {"status": "ahead"}})
        self.assertEqual(self.check(a), ([], []))

    def test_a_bare_tag_takes_the_next_listed_tag_when_it_is_older(self):
        p, _ = self.check(answers(**{f"/repos/o/libfour/compare/{'9' * 40}...v1.0.3": {"status": "identical"}}))
        self.assertTrue(any("libfour" in x and "the earlier release v1.0.3 already holds" in x for x in p), p)

    def test_a_bare_tag_whose_next_listed_tag_is_newer_is_not_checked(self):
        a = answers(**{"/repos/o/libfour/commits/v1.0.3": {"commit": {"committer": {"date": "2026-12-01T00:00:00Z"}}}})
        p, u = self.check(a)
        self.assertEqual(p, [])
        self.assertTrue(any("libfour" in x and "is not checked" in x for x in u), u)

    def test_a_compare_github_cannot_make_is_not_a_pass(self):
        a = answers(); a.pop(f"/repos/o/libtwo/compare/{'e' * 40}...7.2.0")
        p, u = self.check(a)
        self.assertTrue(any("libtwo" in x and "could not compare" in x for x in u), u)

    def test_a_released_pull_request_with_no_merge_commit_is_not_a_pass(self):
        a = answers(); a["/repos/o/libtwo/pulls/6"] = dict(a["/repos/o/libtwo/pulls/6"], merge_commit_sha=None)
        p, u = self.check(a)
        self.assertTrue(any("libtwo" in x and "no merge commit" in x for x in u), u)

    def test_a_release_notes_only_fix_whose_report_is_open(self):
        g = GivenProofsAndInferredLinks()
        r = g.row()
        a = dict(g.ANSWERS); a["/repos/o/libnine/issues/4"] = dict(a["/repos/o/libnine/issues/4"], state="open")
        p, _ = self.check(a, rows=[r])
        self.assertTrue(any("libnine" in x and "shown only by its release notes" in x and "is open" in x for x in p), p)

    def test_a_release_notes_only_fix_whose_inferred_commit_is_not_in_the_release(self):
        g = GivenProofsAndInferredLinks()
        a = dict(g.ANSWERS); a[f"/repos/o/libnine/compare/{'f' * 40}...4.1.0"] = {"status": "behind"}
        p, _ = self.check(a, rows=[g.row()])
        self.assertTrue(any("libnine" in x and "4.1.0 does not hold" in x for x in p), p)

    # the blind reader's findings on the three checks (F1-F5)
    def test_a_bare_tag_between_two_releases_counts(self):
        a = answers(**{"/repos/o/libtwo/tags?per_page=100&page=1": [{"name": "7.2.0"}, {"name": "7.1.0"}, {"name": "7.1.5"}],
                       "/repos/o/libtwo/commits/7.1.5": {"commit": {"committer": {"date": "2026-10-01T00:00:00Z"}}},
                       f"/repos/o/libtwo/compare/{'e' * 40}...7.1.5": {"status": "ahead"}})
        p, _ = self.check(a)
        self.assertTrue(any("libtwo" in x and "the earlier release 7.1.5 already holds" in x for x in p), p)

    def test_the_version_order_is_read_not_githubs_list_order(self):
        a = answers(**{"/repos/o/libtwo/tags?per_page=100&page=1": [{"name": "7.2.0"}, {"name": "7.10.0"}, {"name": "7.1.0"}, {"name": "7.9.0"}],
                       f"/repos/o/libtwo/compare/{'e' * 40}...7.1.0": {"status": "behind"}})
        self.assertEqual(cu.version_key("v7.10.0") > cu.version_key("7.9.0"), True)
        self.assertEqual(cu.version_key("1.0"), cu.version_key("v1.0.0"))
        self.assertIsNone(cu.version_key("7.2.0-rc1"))
        p, _ = self.check(a)   # 7.2.0's predecessor is 7.1.0 in version order, wherever GitHub lists it
        self.assertEqual(p, [])

    def test_tags_are_read_across_pages(self):
        page1 = [{"name": f"9.{i}.0"} for i in range(100)]
        a = answers(**{"/repos/o/libtwo/tags?per_page=100&page=1": page1,
                       "/repos/o/libtwo/tags?per_page=100&page=2": [{"name": "7.2.0"}, {"name": "7.1.0"}]})
        self.assertEqual(self.check(a), ([], []))
        a[f"/repos/o/libtwo/compare/{'e' * 40}...7.1.0"] = {"status": "ahead"}
        p, _ = self.check(a)
        self.assertTrue(any("the earlier release 7.1.0 already holds" in x for x in p), p)

    def test_more_tags_than_it_reads_is_not_checked(self):
        a = answers()
        for page in range(1, cu.TAG_PAGES + 1):
            a[f"/repos/o/libtwo/tags?per_page=100&page={page}"] = [{"name": f"{page}.{i}.1"} for i in range(100)]
        a["/repos/o/libtwo/tags?per_page=100&page=1"][0] = {"name": "7.2.0"}
        p, u = self.check(a)
        self.assertTrue(any("libtwo" in x and "no version order" in x for x in u), u)

    def test_a_my_pr_row_with_no_pull_request_fails(self):
        rows = [dict(r, prs=[], proof=f"{G}/o/libone/commit/{'c' * 40}") if r["library"] == "libone" else r for r in self.rows]
        a = answers(**{f"/repos/o/libone/commits/{'c' * 40}": {"sha": "c" * 40, "author": {"login": "someone"},
                                                                "commit": {"committer": {"date": "2026-09-24T12:00:00Z"}}}})
        p, _ = self.check(a, rows=rows)
        self.assertTrue(any("libone" in x and "links no pull request" in x for x in p), p)

    def test_a_my_pr_row_whose_proof_is_not_a_pull_request_fails(self):
        rows = [dict(r, proof=f"{G}/o/libone/commit/{'c' * 40}") if r["library"] == "libone" else r for r in self.rows]
        a = answers(**{f"/repos/o/libone/commits/{'c' * 40}": {"sha": "c" * 40, "author": {"login": "hneogy"},
                                                                "commit": {"committer": {"date": "2026-09-24T12:00:00Z"}}}})
        p, _ = self.check(a, rows=rows)
        self.assertTrue(any("libone" in x and "is not a pull request" in x for x in p), p)

    def test_a_release_notes_only_fix_with_no_report_linked_fails(self):
        g = GivenProofsAndInferredLinks()
        r = dict(g.row(), issues=[])
        p, _ = self.check(dict(g.ANSWERS), rows=[r])
        self.assertTrue(any("libnine" in x and "no report is linked" in x for x in p), p)

    def test_merged_not_released_reads_the_newest_version_not_the_first_listed_tag(self):
        a = answers(); a.pop("/repos/o/libone/releases/latest")
        a["/repos/o/libone/tags?per_page=100&page=1"] = [{"name": "v2.14"}, {"name": "v2.9"}, {"name": "2.28"}, {"name": "2.27"}]
        a[f"/repos/o/libone/compare/{'c' * 40}...v2.14"] = {"status": "behind"}
        a[f"/repos/o/libone/compare/{'c' * 40}...2.28"] = {"status": "ahead"}
        p, _ = self.check(a)
        self.assertTrue(any("libone" in x and "2.28 already holds" in x for x in p), p)

    def test_merged_not_released_with_nothing_readable_is_not_checked(self):
        a = answers(); a.pop("/repos/o/libone/releases/latest")
        p, u = self.check(a)
        self.assertTrue(any("libone" in x and "has shipped since could not be read" in x for x in u), u)

    def test_the_command_fails_on_a_not_checked_item(self):
        a = answers(); a.pop(f"/repos/o/libtwo/compare/{'e' * 40}...7.2.0")
        rows_path = recorded({"rows": self.rows})
        path = recorded(a)
        try:
            import contextlib, io
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = cu.main(["--table", rows_path, "--recorded", path])
        finally:
            os.unlink(path); os.unlink(rows_path)
        self.assertEqual(rc, 1)
        self.assertIn("NOT CHECKED:", out.getvalue())
        self.assertIn("0 mismatch(es), 1 not checked", out.getvalue())


class ANamedEarlierReleaseNotCounted(unittest.TestCase):
    """The owner's ruling on akhenakh/sgp4 #16 (option A): a row may name the one earlier release that holds the fix
    but is not counted, with its reason shown in the table. The check passes it only if the earlier release holding
    the fix is exactly that one, and fails it once it is no longer needed."""
    BULLET = (f"- **libtwo**: epochs truncated. [#5]({G}/o/libtwo/issues/5), [PR #6]({G}/o/libtwo/pull/6), merged 2026-09-26, "
              f"released in [7.2.0]({G}/o/libtwo/releases/tag/7.2.0) (7.1.0 not counted: re-tagged after a checksum database stored the old 7.1.0).")

    RULED = {("o/libtwo", "7.2.0"): "7.1.0"}

    def row(self, bullet=None):
        r = ut.parse_bullet(bullet or self.BULLET, "my-pr")
        ut.complete([r], {f"{G}/o/libtwo/pull/6": {"merged": True, "merged_at": "2026-09-26T09:00:00Z"}})
        return r

    def check(self, a, r=None):
        unchecked = []
        path = recorded(a)
        try:
            p = cu.check({"rows": [r or self.row()]}, cu.Recorded(path), unchecked=unchecked, exceptions=self.RULED)[0]
        finally:
            os.unlink(path)
        return p, unchecked

    def held_by_7_1(self, **more):
        return answers(**dict({f"/repos/o/libtwo/compare/{'e' * 40}...7.1.0": {"status": "identical"}}, **more))

    def test_read_from_the_ledger(self):
        r = self.row()
        self.assertEqual(r["release"]["name"], "7.2.0")
        self.assertEqual(r["release"]["not_counted"], {"tag": "7.1.0", "why": "re-tagged after a checksum database stored the old 7.1.0"})

    def test_shown_in_the_table_with_its_reason(self):
        md = ut.render({"as_of": "x", "summary": {"total": 1, "my-pr": 1, "maintainer": 0, "open": 0, "other": 0}, "rows": [self.row()]})
        self.assertIn(f"[7.2.0]({G}/o/libtwo/releases/tag/7.2.0) (7.1.0 not counted: re-tagged after a checksum database stored the old 7.1.0)", md)

    def test_a_row_without_one_has_none(self):
        r = self.row(self.BULLET.split(" (7.1.0")[0] + ".")
        self.assertNotIn("not_counted", r["release"])

    def test_passes_when_the_earlier_release_is_exactly_the_named_one(self):
        self.assertEqual(self.check(self.held_by_7_1()), ([], []))

    def test_without_the_exception_the_same_answers_fail(self):
        r = self.row(); del r["release"]["not_counted"]
        p, _ = self.check(self.held_by_7_1(), r)
        self.assertTrue(any("the earlier release 7.1.0 already holds" in x for x in p), p)

    def test_fails_when_it_names_another_release(self):
        r = self.row(); r["release"]["not_counted"] = dict(r["release"]["not_counted"], tag="7.0.0")
        p, _ = self.check(self.held_by_7_1(), r)
        self.assertTrue(any("names 7.0.0 as not counted, which no ruling allows" in x for x in p), p)
        self.assertTrue(any("the earlier release 7.1.0 already holds" in x for x in p), p)

    def test_fails_once_it_is_no_longer_needed(self):
        p, _ = self.check(answers())   # 7.1.0 does not hold the fix
        self.assertTrue(any("names 7.1.0 as not counted" in x and "is not needed" in x for x in p), p)

    def test_fails_when_the_release_before_the_named_one_holds_it_too(self):
        p, _ = self.check(self.held_by_7_1(**{f"/repos/o/libtwo/compare/{'e' * 40}...7.0.0": {"status": "ahead"}}))
        self.assertTrue(any("7.1.0 is not counted, but the release before it, 7.0.0, already holds" in x for x in p), p)

    def test_fails_when_there_is_no_earlier_release(self):
        a = self.held_by_7_1(**{"/repos/o/libtwo/tags?per_page=100&page=1": [{"name": "7.2.0"}]})
        p, _ = self.check(a)
        self.assertTrue(any("the release before 7.2.0 is none" in x and "is not needed" in x for x in p), p)

    # the blind reader's findings on the exception (E1-E3)
    def test_no_ruling_no_exception_on_another_row_or_tag(self):
        r = self.row()
        for ruled in ({}, {("o/libtwo", "7.2.0"): "7.0.0"}, {("o/other", "7.2.0"): "7.1.0"}):
            path = recorded(self.held_by_7_1())
            try:
                p = cu.check({"rows": [r]}, cu.Recorded(path), unchecked=[], exceptions=ruled)[0]
            finally:
                os.unlink(path)
            self.assertTrue(any("which no ruling allows" in x for x in p), (ruled, p))
            self.assertTrue(any("already holds" in x for x in p), (ruled, p))   # and the real mismatch is reported

    def test_the_shipped_ruling_is_the_one_row_only(self):
        self.assertEqual(cu.EXCEPTIONS, {("akhenakh/sgp4", "v1.0.4"): "v1.0.3"})

    def test_an_exception_on_a_row_that_is_not_released_fails(self):
        r = ut.parse_bullet(f"- **libtwo**: epochs truncated. [#5]({G}/o/libtwo/issues/5), open, released in "
                            f"[7.2.0]({G}/o/libtwo/releases/tag/7.2.0) (7.1.0 not counted: a reason).", "open")
        ut.complete([r], {})
        self.assertEqual(r["status"], "open")
        p, _ = self.check(answers(**{"/repos/o/libtwo/issues/5": {"state": "open", "created_at": "2026-09-20T10:00:00Z"}}), r)
        self.assertTrue(any("is not marked released" in x for x in p), p)

    def test_an_exception_with_no_reason_fails(self):
        for why in ("", "   ", None):
            r = self.row(); r["release"]["not_counted"] = {"tag": "7.1.0", "why": why}
            if why is None:
                del r["release"]["not_counted"]["why"]
            p, _ = self.check(self.held_by_7_1(), r)
            self.assertTrue(any("with no reason" in x for x in p), (why, p))

    def test_a_reason_with_parentheses_drops_the_exception_loudly(self):
        r = self.row(self.BULLET.replace("stored the old 7.1.0", "(sum.golang.org) stored the old 7.1.0"))
        self.assertNotIn("not_counted", r["release"])
        p, _ = self.check(self.held_by_7_1(), r)
        self.assertTrue(any("the earlier release 7.1.0 already holds" in x for x in p), p)

    def test_a_pipe_in_the_reason_is_escaped(self):
        r = self.row(); r["release"]["not_counted"]["why"] = "a | b"
        md = ut.render({"as_of": "x", "summary": {"total": 1, "my-pr": 1, "maintainer": 0, "open": 0, "other": 0}, "rows": [r]})
        self.assertIn("(7.1.0 not counted: a \\| b)", md)

    def test_on_a_bare_tag(self):
        bullet = (f"- **libfour**: one bad set lost the file. [#8]({G}/o/libfour/issues/8), [PR #9]({G}/o/libfour/pull/9), fixed by "
                  f"someone, a contributor, released in [v1.0.4]({G}/o/libfour/releases/tag/v1.0.4) (v1.0.3 not counted: re-tagged).")
        r = ut.parse_bullet(bullet, "maintainer")
        ut.complete([r], {f"{G}/o/libfour/pull/9": {"merged": True, "merged_at": "2026-10-03T10:00:00Z"}})
        a = answers(**{f"/repos/o/libfour/compare/{'9' * 40}...v1.0.3": {"status": "identical"}})
        path = recorded(a)
        try:
            ok = cu.check({"rows": [r]}, cu.Recorded(path), unchecked=[], exceptions={("o/libfour", "v1.0.4"): "v1.0.3"})[0]
            no = cu.check({"rows": [r]}, cu.Recorded(path), unchecked=[], exceptions={})[0]
        finally:
            os.unlink(path)
        self.assertEqual(ok, [])
        self.assertTrue(any("which no ruling allows" in x for x in no), no)

    def test_a_compare_with_the_release_before_that_cannot_be_made_is_not_a_pass(self):
        a = self.held_by_7_1(); a.pop(f"/repos/o/libtwo/compare/{'e' * 40}...7.0.0")
        p, u = self.check(a)
        self.assertTrue(any("could not compare" in x and "7.0.0" in x for x in u), u)


class OptInFixes(unittest.TestCase):
    """D-593: a row the record marks as an opt-in fix says plainly that the fix exists, that it is an
    opt-in, and that the default behaviour is unchanged; the check finds the opt-in's name in the upstream's own
    release notes or changelog at the named release, or in the merged pull request's text."""
    REL = (f"- **libtwo**: epochs truncated. [#5]({G}/o/libtwo/issues/5), [PR #6]({G}/o/libtwo/pull/6), opt-in `keep_going` for one bad set, "
           f"merged 2026-09-26, released in [7.2.0]({G}/o/libtwo/releases/tag/7.2.0).")
    MRG = (f"- **libone**: an empty field raised an error. [#10]({G}/o/libone/issues/10), [PR #11]({G}/o/libone/pull/11), "
           "opt-in `lenient`, merged 2026-09-24, not yet released.")

    def row(self, bullet):
        r = ut.parse_bullet(bullet, "my-pr")
        ut.complete([r], {f"{G}/o/libtwo/pull/6": {"merged": True}, f"{G}/o/libone/pull/11": {"merged": True},
                          f"{G}/o/libtwo/releases/tag/7.2.0": {"exists": True}})
        return r

    def check(self, a, r):
        unchecked = []
        path = recorded(a)
        try:
            p = cu.check({"rows": [r]}, cu.Recorded(path), unchecked=unchecked)[0]
        finally:
            os.unlink(path)
        return [x for x in p if "opt-in" in x], [x for x in unchecked if "opt-in" in x]

    def test_read_from_the_ledger(self):
        self.assertEqual(self.row(self.REL)["opt_in"], {"name": "keep_going", "scope": "one bad set"})
        self.assertEqual(self.row(self.MRG)["opt_in"], {"name": "lenient", "scope": None})
        self.assertIsNone(ut.parse_bullet(self.REL.replace("opt-in `keep_going` for one bad set, ", ""), "my-pr")["opt_in"])

    def test_the_table_says_it_plainly(self):
        md = ut.render({"as_of": "x", "summary": {"total": 2, "my-pr": 2, "maintainer": 0, "open": 0, "other": 0},
                        "rows": [self.row(self.REL), self.row(self.MRG)]})
        self.assertIn("epochs truncated; for one bad set, the fix is an opt-in (`keep_going`), and the default behaviour is unchanged |", md)
        self.assertIn("an empty field raised an error; the fix is an opt-in (`lenient`), and the default behaviour is unchanged |", md)

    def test_a_released_opt_in_named_in_the_release_notes_passes(self):
        a = answers(); a["/repos/o/libtwo/releases/tags/7.2.0"] = dict(a["/repos/o/libtwo/releases/tags/7.2.0"], body="Added `keep_going`.")
        self.assertEqual(self.check(a, self.row(self.REL)), ([], []))

    def test_a_released_opt_in_named_in_the_changelog_at_the_tag_passes(self):
        import base64
        a = answers(**{"/repos/o/libtwo/contents/CHANGELOG.md?ref=7.2.0": {"content": base64.b64encode(b"### Added\n- keep_going\n").decode()}})
        self.assertEqual(self.check(a, self.row(self.REL)), ([], []))

    def test_a_released_opt_in_the_notes_do_not_name_fails(self):
        a = answers(); a["/repos/o/libtwo/releases/tags/7.2.0"] = dict(a["/repos/o/libtwo/releases/tags/7.2.0"], body="Bug fixes.")
        p, _ = self.check(a, self.row(self.REL))
        self.assertTrue(any("marks the fix as the opt-in `keep_going`, but the release notes or changelog at 7.2.0 does not name it" in x for x in p), p)

    def test_notes_that_cannot_be_read_are_not_checked(self):
        p, u = self.check(answers(), self.row(self.REL))   # no body, no changelog
        self.assertEqual(p, [])
        self.assertTrue(any("could not be read, so the opt-in `keep_going` is not checked" in x for x in u), u)

    def test_a_merged_opt_in_named_in_its_pull_request_passes_and_unnamed_fails(self):
        a = answers(); a["/repos/o/libone/pulls/11"] = dict(a["/repos/o/libone/pulls/11"], body="Adds `lenient=True`; default unchanged.")
        self.assertEqual(self.check(a, self.row(self.MRG)), ([], []))
        a["/repos/o/libone/pulls/11"] = dict(a["/repos/o/libone/pulls/11"], body="Fixes it.")
        p, _ = self.check(a, self.row(self.MRG))
        self.assertTrue(any("does not name it" in x for x in p), p)

    def test_an_opt_in_on_a_row_not_fixed_fails(self):
        r = ut.parse_bullet(f"- **libfive**: a letter read as a digit. [#3]({G}/o/libfive/issues/3), opt-in `strict`, open.", "open")
        ut.complete([r], {})
        p, _ = self.check(answers(), r)
        self.assertTrue(any("marks an opt-in fix, but is not marked as fixed" in x for x in p), p)

    def test_the_shipped_table_marks_the_three_rows_the_owner_named(self):
        with open(os.path.join(ROOT, "docs", "upstream", "table.json"), encoding="utf-8") as f:
            rows = json.load(f)["rows"]
        marked = sorted((r["library"], r["opt_in"]["name"]) for r in rows if r.get("opt_in"))
        self.assertEqual(marked, [("Basilisk", "on_error"), ("SGPKit (swift-sgp4)", "decodeValidSets"), ("satkit", "on_error")])


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
