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
- a date the table takes from GitHub matches it (a day either way, for time zones).
Any mismatch is printed and the exit status is 1.

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
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upstream_table import GH, STATUS_WORD, kind_of, repo_of  # noqa: E402

API = "https://api.github.com"


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
                              "merge_commit_sha": body.get("merge_commit_sha")}
            if k == "issue":
                return True, {"state": body.get("state"), "created_at": body.get("created_at"),
                              "closed_at": body.get("closed_at"), "is_pr": "pull_request" in body}
            if k == "release":
                return True, {"exists": True, "published_at": body.get("published_at")}
            date = ((body.get("commit") or {}).get("committer") or {}).get("date") if k == "commit" else None
            return True, {"exists": True, "merged_at": date} if k == "commit" else {"exists": True}
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
    """The project's latest release (or newest tag) if it already holds `sha`, else None: a fix the table calls
    merged that has shipped since."""
    if not sha:
        return None
    m = GH.match(pr_url)
    base = f"/repos/{m.group(1)}/{m.group(2)}"
    status, rel = src.get(f"{base}/releases/latest")
    tag = rel.get("tag_name") if status == 200 and rel else None
    if not tag:
        status, tags = src.get(f"{base}/tags")
        tag = tags[0].get("name") if status == 200 and tags else None
    if not tag:
        return None
    status, cmp_ = src.get(f"{base}/compare/{sha}...{tag}")
    if status == 200 and cmp_ and cmp_.get("status") in ("ahead", "identical"):
        return tag
    return None


def day(s):
    return dt.date.fromisoformat(s[:10]) if s else None


def check(table, src, record=None):
    """-> (problems, facts)."""
    problems, facts = [], {}

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
            tag = released_since(src, proof, pf.get("merge_commit_sha"))
            if tag:
                problems.append(f"{name}: marked merged, not yet released, but {tag} already holds {proof}")
        if st == "released" and not (r.get("release") and r["release"].get("url")):
            problems.append(f"{name}: marked released, with no release link")
        if st == "open" and proof and pf.get("state") != "open":
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
    a = ap.parse_args(argv)
    with open(a.table, encoding="utf-8") as f:
        table = json.load(f)
    if a.record and a.recorded:
        ap.error("--record reads GitHub live; it cannot be used with --recorded")
    src = Recorded(a.recorded) if a.recorded else Live(a.pause)
    problems, facts = check(table, src, record={} if a.record else None)
    if a.record:
        with open(a.record, "w", encoding="utf-8") as f:
            json.dump({u: facts[u] for u in sorted(facts)}, f, indent=1)
            f.write("\n")
    for p in problems:
        print("MISMATCH:", p)
    print(f"{len(table['rows'])} rows, {src.calls} answers read, {len(problems)} mismatch(es)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
