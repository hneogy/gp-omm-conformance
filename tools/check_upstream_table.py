#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""
tools/check_upstream_table.py -- check the upstream table against GitHub (D-552, D-553).

Every link in docs/upstream/table.json must resolve, and every row's status must match what GitHub says:
- a merged or released row's proof is a merged pull request, or a commit that exists;
- a released row's release link names a release or a tag that exists;
- an open row's issue (or pull request) is open;
- a declined or closed row's issue is closed;
- a date the table takes from GitHub matches it (a day either way, for time zones);
- authorship: a "fixed by my pull requests" row links a pull request, its proof is one, and its pull requests are
  the owner's (--owner, GitHub login); no pull request or commit linked from a "fixed by maintainers and
  contributors" row is the owner's;
- a released row's release holds the fix (its merge commit, its commit, or an inferred commit), and the plain
  version just below it (every plain version tag, read across all pages, in version order) does not. One row the
  owner ruled (EXCEPTIONS) names that earlier release as not counted, with its reason: it passes only if the earlier
  release holding the fix is exactly that one and the version below it does not hold it, and fails once it is not
  needed; a not-counted release anywhere else, or with no reason, is a mismatch;
- a fix whose only proof is its release notes links its report, and the report is closed;
- a fix the maintainer's record marks as an opt-in (D-593): its name, at least four characters, appears as a whole word
  in the upstream's own release notes or changelog at the named release (the GitHub release's text, CHANGELOG.md or
  CHANGES.md at the tag), or, for a fix merged but not released, in the merged pull request's or commit's own text. It
  cannot see an opt-in the record does not mark, or tell whether the default behaviour changed: the record says that.
  Its limits (D-604, D-605): the name may appear anywhere in those texts, in the same case (a hyphen counts as a
  word's edge, so "non-strict" holds `strict`), and only CHANGELOG.md or CHANGES.md is read (not HISTORY.md or a
  docs folder), nor a pull request's title; and a CHANGELOG at the tag holds the
  whole history, so a name found there is not proof it belongs to this fix; a source that answers with an error
  beside one that reads without the name is a mismatch, not NOT CHECKED; and a marker is any clause that opens
  with "opt-in" after a link, comma, semicolon or parenthesis, whatever words follow it.
Any mismatch is printed and the exit status is 1. What could not be checked is printed as NOT CHECKED, and is not a
pass: the exit status is 1 then too.

Where the answers come from:
- live: the GitHub REST API (GITHUB_TOKEN, if set, is sent; read-only use). It makes several requests per row;
- --recorded FILE: a JSON object of API path -> response, with {"_status": 404} for a missing one. The tests use this,
  so the check's logic is tested without the network.

--record FACTS (live only) writes the facts that tools/upstream_table.py fills gaps from: for each link, its state,
whether it is merged, its dates, a fixed issue's closing commit, and which candidate release tags exist.

Usage:
  python3 tools/check_upstream_table.py --table docs/upstream/table.json [--recorded FILE] [--record FACTS]
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upstream_table import GH, STATUS_WORD, kind_of, repo_of  # noqa: E402

API = "https://api.github.com"
# The one release the owner ruled may be named as not counted (D-585): (repository, the release the row names) -> the
# earlier release. A not-counted release on any other row, or naming another tag, is a mismatch.
EXCEPTIONS = {("akhenakh/sgp4", "v1.0.4"): "v1.0.3"}
OPT_IN_MIN = 4   # an opt-in name shorter than this would match too much of any release notes (D-593)


class Live:
    """GitHub's API, politely: a pause between requests, each answer kept for the run, and a stop if the rate limit
    runs low."""
    def __init__(self, pause=0.5):
        self.token = os.environ.get("GITHUB_TOKEN")
        self.calls = 0
        self.pause = pause
        self.seen = {}

    def get(self, path):
        if path in self.seen:
            return self.seen[path]
        if self.calls:
            time.sleep(self.pause)
        self.calls += 1
        self.seen[path] = self._get(path)
        return self.seen[path]

    def _get(self, path):
        req = urllib.request.Request(API + path, headers={"Accept": "application/vnd.github+json",
                                                          "User-Agent": "gpconf-upstream-table-check",
                                                          "X-GitHub-Api-Version": "2022-11-28"})
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                left = r.headers.get("X-RateLimit-Remaining")
                if left is not None and int(left) < 20:
                    sys.exit(f"stopped: GitHub's rate limit is down to {left} requests")
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, None


class Recorded:
    def __init__(self, path):
        with open(path, encoding="utf-8") as f:
            self.answers = json.load(f)
        self.calls = 0

    def get(self, path):
        self.calls += 1
        a = self.answers.get(path)
        if a is None:
            return 404, None
        if isinstance(a, dict) and "_status" in a:
            return a["_status"], None
        return 200, a


def api_paths(url):
    """The API path(s) that answer for a github.com URL, in the order tried."""
    m = GH.match(url)
    if not m:
        return []
    o, r, kind, ref = m.groups()
    base = f"/repos/{o}/{r}"
    return {"issues": [f"{base}/issues/{ref}"], "pull": [f"{base}/pulls/{ref}"], "commit": [f"{base}/commits/{ref}"],
            "releases/tag": [f"{base}/releases/tags/{ref}", f"{base}/git/ref/tags/{ref}"]}[kind]


def look(src, url):
    """-> (exists, facts) for one URL."""
    for p in api_paths(url):
        status, body = src.get(p)
        if status == 200 and body is not None:
            k = kind_of(url)
            if k == "pr":
                return True, {"state": body.get("state"), "merged": bool(body.get("merged")),
                              "merged_at": body.get("merged_at"), "created_at": body.get("created_at"),
                              "merge_commit_sha": body.get("merge_commit_sha"),
                              "author": (body.get("user") or {}).get("login")}
            if k == "issue":
                return True, {"state": body.get("state"), "created_at": body.get("created_at"),
                              "closed_at": body.get("closed_at"), "is_pr": "pull_request" in body}
            if k == "release":
                return True, {"exists": True, "published_at": body.get("published_at")}
            if k == "commit":
                date = ((body.get("commit") or {}).get("committer") or {}).get("date")
                return True, {"exists": True, "merged_at": date, "sha": body.get("sha"),
                              "author": (body.get("author") or {}).get("login")}
            return True, {"exists": True}
    return False, {}


def closing_commit(src, issue_url):
    m = GH.match(issue_url)
    status, events = src.get(f"/repos/{m.group(1)}/{m.group(2)}/issues/{m.group(4)}/events")
    if status != 200 or not isinstance(events, list):
        return None
    for e in reversed(events):
        if e.get("event") == "closed" and e.get("commit_id"):
            return f"https://github.com/{m.group(1)}/{m.group(2)}/commit/{e['commit_id']}"
    # closed by hand: the last commit that referenced the issue before it was closed
    closed = [e.get("created_at") for e in events if e.get("event") == "closed"]
    refs = [e for e in events if e.get("event") == "referenced" and e.get("commit_id")
            and (not closed or (e.get("created_at") or "") <= closed[-1])]
    if refs:
        return f"https://github.com/{m.group(1)}/{m.group(2)}/commit/{refs[-1]['commit_id']}"
    return None


def released_since(src, pr_url, sha):
    """-> (readable, tag): the project's newest release or newest version tag that already holds `sha`, a fix the
    table calls merged that has shipped since; tag None if neither holds it. readable is False when neither the latest
    release nor the tags can be read, or a compare cannot be made: the caller says NOT CHECKED. GitHub's tag list
    is not in version order, so the newest version is read from all the tags."""
    if not sha:
        return False, None
    m = GH.match(pr_url)
    repo = f"{m.group(1)}/{m.group(2)}"
    cands = []
    status, rel = src.get(f"/repos/{repo}/releases/latest")
    if status == 200 and rel and rel.get("tag_name"):
        cands.append(rel["tag_name"])
    names = all_tags(src, repo)
    if names:
        plain = [n for n in names if version_key(n) is not None]
        if plain:
            cands.append(max(plain, key=version_key))
    if not cands and names is None:
        return False, None
    for tag in dict.fromkeys(cands):
        h = holds(src, repo, sha, tag)
        if h is None:
            return False, None
        if h:
            return True, tag
    return True, None


def holds(src, repo, sha, tag):
    """True if release `tag` holds commit `sha`, False if not, None if GitHub could not compare them."""
    status, c = src.get(f"/repos/{repo}/compare/{sha}...{tag}")
    if status != 200 or not c or c.get("status") is None:
        return None
    return c.get("status") in ("ahead", "identical")


VERSION = re.compile(r"v?(\d+(?:\.\d+)*)")
TAG_PAGES = 10   # at most 1,000 tags are read; a project with more is NOT CHECKED


def commit_date(src, repo, ref):
    status, c = src.get(f"/repos/{repo}/commits/{ref}")
    if status != 200 or not c:
        return None
    return ((c.get("commit") or {}).get("committer") or {}).get("date")


def version_key(name):
    """A plain version tag ("1.2.3" or "v1.2.3") -> (1, 2, 3); anything else (a pre-release, a word) -> None."""
    m = VERSION.fullmatch(name or "")
    if not m:
        return None
    k = [int(x) for x in m.group(1).split(".")]
    while len(k) > 1 and k[-1] == 0:
        k.pop()   # 1.0 and 1.0.0 are the same version
    return tuple(k)


def all_tags(src, repo):
    """Every tag name, read page by page, or None when they cannot all be read."""
    names = []
    for page in range(1, TAG_PAGES + 1):
        status, tags = src.get(f"/repos/{repo}/tags?per_page=100&page={page}")
        if status != 200 or not isinstance(tags, list):
            return None
        names += [t.get("name") for t in tags]
        if len(tags) < 100:
            return names
    return None


def release_before(src, repo, tag):
    """-> (found, previous tags): the plain version tags just below `tag` in version order (every tag is read, so a
    bare tag between two GitHub releases counts; GitHub's own tag order is not version order). Pre-release tags
    (anything but digits and dots, with an optional v) are left out. A previous tag whose commit is newer than the
    tag's is no order at all. found is False when there is no order to read; the caller says NOT CHECKED."""
    key = version_key(tag)
    names = all_tags(src, repo)
    if key is None or names is None or tag not in names:
        return False, []
    lower = [(version_key(n), n) for n in names if version_key(n) is not None and version_key(n) < key]
    if not lower:
        return True, []
    top = max(k for k, _ in lower)
    prevs = sorted(n for k, n in lower if k == top)
    d_tag = commit_date(src, repo, tag)
    for n in prevs:
        d = commit_date(src, repo, n)
        if not d_tag or not d or d > d_tag:
            return False, []
    return True, prevs


def upstream_notes(src, repo, tag):
    """The upstream's own words at a release: the GitHub release's text and any changelog file at the tag, joined; None
    when none of them can be read."""
    import base64
    parts = []
    status, rel = src.get(f"/repos/{repo}/releases/tags/{tag}")
    if status == 200 and rel and rel.get("body"):
        parts.append(rel["body"])
    for name in ("CHANGELOG.md", "CHANGES.md"):
        status, c = src.get(f"/repos/{repo}/contents/{name}?ref={tag}")
        if status == 200 and c and c.get("content"):
            try:
                parts.append(base64.b64decode(c["content"]).decode("utf-8", "replace"))
            except ValueError:
                pass
    return "\n".join(parts) if parts else None


def day(s):
    return dt.date.fromisoformat(s[:10]) if s else None


def check(table, src, record=None, owner="hneogy", unchecked=None, exceptions=None):
    """-> (problems, facts). What could not be checked is appended to `unchecked`, if given, else counted as a
    problem."""
    problems, facts = [], {}

    exceptions = EXCEPTIONS if exceptions is None else exceptions

    def cannot(text):
        (unchecked if unchecked is not None else problems).append(text)

    def see(url):
        if url in facts:
            return facts[url]
        ok, f = look(src, url)
        facts[url] = dict(f, resolves=ok)
        return facts[url]

    for r in table["rows"]:
        name = f"{r['library']}: {r['finding'][:50]}"
        urls = set(r.get("issues", []) + r.get("prs", []) + r.get("commits", []))
        if r.get("inferred"):
            urls.add(r["inferred"]["url"])
            # an inferred link must say so (D-558): never shown as if it were confirmed
            if "inferred" not in (r["inferred"].get("label") or "").lower():
                problems.append(f"{name}: {r['inferred']['url']} is inferred but its label does not say so")
        if r.get("proof"):
            urls.add(r["proof"])
        if r.get("release") and r["release"].get("url"):
            urls.add(r["release"]["url"])
        for u in sorted(urls):
            if not see(u)["resolves"]:
                problems.append(f"{name}: {u} does not resolve")
        proof = r.get("proof")
        pf = see(proof) if proof else {}
        st = r["status"]
        if st not in STATUS_WORD:
            problems.append(f"{name}: status {st!r} is not one of the allowed ones ({', '.join(STATUS_WORD.values())})")
        # the table never claims gpconf found what it did not (D-560): a row that says what gpconf did instead may
        # not also say it found it
        if r.get("involvement") and "found by gpconf" in (r["finding"] + " " + r["involvement"]).lower():
            problems.append(f"{name}: says gpconf found it, but its involvement note says otherwise")
        if r.get("involvement") and "found" in r["involvement"].lower():
            problems.append(f"{name}: an involvement note may not claim a find: {r['involvement']!r}")
        if st == "merged-no-releases":
            if not (kind_of(proof or "") == "pr" and pf.get("merged")):
                problems.append(f"{name}: marked merged, but {proof} is not a merged pull request on GitHub")
            m = GH.match(proof or "")
            if m:
                status, rels = src.get(f"/repos/{m.group(1)}/{m.group(2)}/releases")
                if status == 200 and rels:
                    problems.append(f"{name}: says the project has no releases, but GitHub lists {rels[0].get('tag_name')}")
        if st in ("merged", "released"):
            if not proof:
                problems.append(f"{name}: no proof link")
            elif kind_of(proof) == "pr" and not pf.get("merged"):
                problems.append(f"{name}: marked {st}, but {proof} is not merged on GitHub")
            elif kind_of(proof) == "release" and r.get("proof_given"):
                pass   # the ledger names the release notes as the primary source (D-558); it must resolve, above
            elif kind_of(proof) not in ("pr", "commit"):
                problems.append(f"{name}: the proof of a fix must be a merged pull request or a commit, not {proof}")
        if st == "merged" and proof and kind_of(proof) == "pr" and pf.get("merged"):
            readable, tag = released_since(src, proof, pf.get("merge_commit_sha"))
            if not readable:
                cannot(f"{name}: whether {proof} has shipped since could not be read (no merge commit, release, tag or compare)")
            elif tag:
                problems.append(f"{name}: marked merged, not yet released, but {tag} already holds {proof}")
        if st == "released" and not (r.get("release") and r["release"].get("url")):
            problems.append(f"{name}: marked released, with no release link")
        # authorship: the group says whose fix it is, and that feeds the summary's counts
        if r["group"] == "my-pr" and st in ("merged", "released", "merged-no-releases"):
            # a fix by the owner's pull request: the row links one, and its proof is that pull request
            if not r.get("prs"):
                problems.append(f"{name}: listed as fixed by my pull requests, but links no pull request")
            elif kind_of(proof or "") != "pr":
                problems.append(f"{name}: listed as fixed by my pull requests, but its proof {proof} is not a pull request")
        if r["group"] in ("my-pr", "maintainer"):
            linked = [u for u in r.get("prs", []) + r.get("commits", []) + [proof or ""]
                      + ([r["inferred"]["url"]] if r.get("inferred") else []) if kind_of(u) in ("pr", "commit")]
            for u in dict.fromkeys(linked):
                f = see(u)
                if not f.get("resolves"):
                    continue
                who = f.get("author")
                if r["group"] == "my-pr" and kind_of(u) == "pr":
                    if who is None:
                        cannot(f"{name}: GitHub names no author for {u}")
                    elif who.lower() != owner.lower():
                        problems.append(f"{name}: listed as fixed by my pull requests, but {u} is by {who}")
                if r["group"] == "maintainer":
                    if who is None:
                        cannot(f"{name}: GitHub names no author for {u}")
                    elif who.lower() == owner.lower():
                        problems.append(f"{name}: listed as fixed by maintainers or contributors, but {u} is the owner's")
        # a release named as not counted: only where the owner ruled it, with a reason, and only on a released row
        rel = r.get("release") or {}
        nc = rel.get("not_counted")
        if nc:
            rtag = GH.match(rel["url"]).group(4) if rel.get("url") and GH.match(rel["url"]) else rel.get("name")
            ruled = exceptions.get((repo_of(rel.get("url") or "") or "", rtag))
            if ruled is None or nc.get("tag") != ruled:
                problems.append(f"{name}: names {nc.get('tag')} as not counted, which no ruling allows for this row")
                nc = None
            elif not (nc.get("why") or "").strip():
                problems.append(f"{name}: names {nc.get('tag')} as not counted, with no reason")
                nc = None
            elif st != "released":
                problems.append(f"{name}: names {nc.get('tag')} as not counted, but is not marked released")
                nc = None
        # the release holds the fix, and is the first that does
        if st == "released" and rel.get("url") and see(rel["url"]).get("resolves"):
            repo, tag = repo_of(rel["url"]), GH.match(rel["url"]).group(4)
            fix = []
            if kind_of(proof or "") == "pr" and pf.get("merged"):
                fix.append((proof, pf.get("merge_commit_sha")))
            elif kind_of(proof or "") == "commit":
                fix.append((proof, pf.get("sha") or GH.match(proof).group(4)))
            if r.get("inferred") and kind_of(r["inferred"]["url"]) == "commit":
                fix.append((r["inferred"]["url"], see(r["inferred"]["url"]).get("sha") or GH.match(r["inferred"]["url"]).group(4)))
            if not fix:
                cannot(f"{name}: no commit to look for in {tag}")
            for u, sha in fix:
                if not sha:
                    cannot(f"{name}: GitHub gives no merge commit for {u}")
                    continue
                h = holds(src, repo, sha, tag)
                if h is None:
                    cannot(f"{name}: GitHub could not compare {sha[:7]} with {tag}")
                    continue
                if not h:
                    problems.append(f"{name}: marked released in {tag}, but {tag} does not hold {u}")
                    continue
                found, prevs = release_before(src, repo, tag)
                if not found:
                    cannot(f"{name}: no version order of {repo}'s tags around {tag} could be read, so whether it is the first to hold the fix is not checked")
                    continue
                answers_ = {pv: holds(src, repo, sha, pv) for pv in prevs}
                if None in answers_.values():
                    cannot(f"{name}: GitHub could not compare {sha[:7]} with {', '.join(prevs)}")
                    continue
                holding = [pv for pv, a in answers_.items() if a]
                if holding and nc and holding == [nc["tag"]]:
                    # the named exception: the earlier release is exactly the one not counted, and nothing before it
                    found2, prevs2 = release_before(src, repo, nc["tag"])
                    if not found2:
                        cannot(f"{name}: no version order of {repo}'s tags around {nc['tag']} could be read, so the exception is not checked")
                        continue
                    a2 = {pv: holds(src, repo, sha, pv) for pv in prevs2}
                    if None in a2.values():
                        cannot(f"{name}: GitHub could not compare {sha[:7]} with {', '.join(prevs2)}")
                    elif any(a2.values()):
                        problems.append(f"{name}: {nc['tag']} is not counted, but the release before it, "
                                        f"{', '.join(pv for pv, a in a2.items() if a)}, already holds {u}")
                elif holding:
                    problems.append(f"{name}: marked released in {tag}, but the earlier release {', '.join(holding)} already holds {u}"
                                    + (f" (the row's exception names {nc['tag']})" if nc else ""))
                elif nc:
                    problems.append(f"{name}: names {nc['tag']} as not counted, but the release before {tag} is "
                                    f"{', '.join(prevs) or 'none'}, which does not hold {u}: the exception is not needed")
        # an opt-in fix the record marks: the upstream's own words at the release name the opt-in (D-593)
        oi = r.get("opt_in")
        if oi:
            name_ = oi.get("name") or ""
            text = where = None
            if st not in ("released", "merged", "merged-no-releases"):
                problems.append(f"{name}: marks an opt-in fix, but is not marked as fixed")
            elif len(name_) < OPT_IN_MIN:
                problems.append(f"{name}: the opt-in name `{name_}` is too short to find reliably (under {OPT_IN_MIN} characters)")
            elif st == "released":
                if rel.get("url") and GH.match(rel["url"]):
                    text = upstream_notes(src, repo_of(rel["url"]), GH.match(rel["url"]).group(4))
                    where = f"the release notes or changelog at {GH.match(rel['url']).group(4)}"
                else:
                    cannot(f"{name}: the release is not a GitHub release or tag, so the opt-in `{name_}` is not checked")
            elif kind_of(proof or "") in ("pr", "commit"):
                m = GH.match(proof)
                path = (f"/repos/{m.group(1)}/{m.group(2)}/pulls/{m.group(4)}" if kind_of(proof) == "pr"
                        else f"/repos/{m.group(1)}/{m.group(2)}/commits/{m.group(4)}")
                status, body = src.get(path)
                if status == 200 and body:
                    text = body.get("body") if kind_of(proof) == "pr" else (body.get("commit") or {}).get("message")
                where = f"{proof}'s text"
            else:
                cannot(f"{name}: its proof is neither a pull request nor a commit, so the opt-in `{name_}` is not checked")
            if where and not text:
                cannot(f"{name}: {where} could not be read, so the opt-in `{name_}` is not checked")
            elif where and not re.search(rf"(?<![A-Za-z0-9_]){re.escape(name_)}(?![A-Za-z0-9_])", text):
                problems.append(f"{name}: marks the fix as the opt-in `{name_}`, but {where} does not name it as a word")
        # a fix shown only by its release notes: its report is linked and closed
        if st == "released" and kind_of(proof or "") == "release":
            if not r.get("issues"):
                problems.append(f"{name}: the fix is shown only by its release notes, and no report is linked")
            for u in r.get("issues", []):
                if see(u).get("state") != "closed":
                    problems.append(f"{name}: the fix is shown only by its release notes, but its report {u} is {see(u).get('state')}")
        if st in ("open", "open-others-report") and proof and pf.get("state") != "open":
            problems.append(f"{name}: marked open, but {proof} is {pf.get('state')} on GitHub")
        if st in ("declined", "closed-planned") and proof and pf.get("state") != "closed":
            problems.append(f"{name}: marked {st}, but {proof} is {pf.get('state')} on GitHub")
        want = {"merged": pf.get("merged_at"), "reported": pf.get("created_at"), "closed": pf.get("closed_at"),
                "released": pf.get("published_at")}.get(r.get("date_is"))
        if r.get("date") and want and abs((day(r["date"]) - day(want)).days) > 1:
            problems.append(f"{name}: dated {r['date']} ({r['date_is']}), GitHub says {want[:10]}")
        if record is not None:
            if r["group"] in ("my-pr", "maintainer") and not r.get("prs") and not r.get("commits") and r.get("issues"):
                c = closing_commit(src, r["issues"][0])
                facts.setdefault(r["issues"][0], {})["closing_commit"] = c
                if c:
                    see(c)
            if r.get("release") and not r["release"].get("url"):
                repo = repo_of(proof or (r.get("issues", []) + r.get("prs", []) + [""])[0])
                n = r["release"]["name"]
                for tag in dict.fromkeys((n, n.lstrip("v"), "v" + n.lstrip("v"))):
                    see(f"https://github.com/{repo}/releases/tag/{tag}")
    return problems, facts


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", required=True)
    ap.add_argument("--recorded", help="answer from a JSON file of API path -> response instead of the network")
    ap.add_argument("--record", help="write the GitHub facts here (live only)")
    ap.add_argument("--pause", type=float, default=0.5, help="seconds between live requests")
    ap.add_argument("--owner", default="hneogy", help="the GitHub login whose pull requests the my-pr group holds")
    a = ap.parse_args(argv)
    with open(a.table, encoding="utf-8") as f:
        table = json.load(f)
    if a.record and a.recorded:
        ap.error("--record reads GitHub live; it cannot be used with --recorded")
    src = Recorded(a.recorded) if a.recorded else Live(a.pause)
    unchecked = []
    problems, facts = check(table, src, record={} if a.record else None, owner=a.owner, unchecked=unchecked)
    if a.record:
        with open(a.record, "w", encoding="utf-8") as f:
            json.dump({u: facts[u] for u in sorted(facts)}, f, indent=1)
            f.write("\n")
    for p in problems:
        print("MISMATCH:", p)
    for u in unchecked:
        print("NOT CHECKED:", u)
    print(f"{len(table['rows'])} rows, {src.calls} answers read, {len(problems)} mismatch(es), {len(unchecked)} not checked")
    return 1 if problems or unchecked else 0


if __name__ == "__main__":
    sys.exit(main())
