#!/usr/bin/env python3
"""
tools/fetch.py -- download corpus source files from CelesTrak exactly once each.

Rules (CelesTrak usage policy; see docs/RESEARCH.md sections 3 and 11):
  * each URL is requested at most once. An existing file with metadata is never
    re-fetched unless --force is given AND the existing copy is older than 2 hours
    (CelesTrak refreshes GP data every 2 hours at most);
  * requests are sequential with a fixed pause between them;
  * redirects are not followed and nothing is retried. Any unexpected response is
    saved (so it is never requested again), then the run stops for a human;
  * every response gets a sibling .meta.json recording the URL, UTC timestamps,
    the status line, every response header in order, the request headers sent,
    byte count and SHA-256;
  * after a run (and on demand with --check-drift) every file on disk is compared
    with the SHA-256 recorded in manifest.json; a stable-tier source whose bytes
    differ is reported as DRIFT, because the frozen expected values then no longer
    apply to it (live-tier differences are expected and only counted).

The fetch list is static (tools/fetchlist.json). There is no discovery and no
wildcard expansion, so the number of requests a run can make is known in advance.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FETCHLIST = os.path.join(ROOT, "tools", "fetchlist.json")
PAUSE_SECONDS = 2.0
MIN_REFETCH_AGE_SECONDS = 2 * 3600
TIMEOUT = 60
TOOL_VERSION = "tools/fetch.py v2 (full header capture)"


def user_agent():
    ua = os.environ.get("GPCONF_USER_AGENT") or (
        "gp-omm-conformance-corpus/0.1 (fixture fetch, each URL once; see repository README)")
    contact = os.environ.get("GPCONF_CONTACT")
    return f"{ua} {contact}" if contact else ua


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # turns any 3xx into an HTTPError


_opener = urllib.request.build_opener(_NoRedirect)


def now_utc(precise=False):
    t = dt.datetime.now(dt.timezone.utc)
    if not precise:
        t = t.replace(microsecond=0)
    return t.isoformat().replace("+00:00", "Z")


def target_paths(entry):
    d = os.path.join(ROOT, "fixtures", entry["case"], "raw")
    return d, os.path.join(d, entry["file"]), os.path.join(d, entry["file"] + ".meta.json")


def is_cached(entry):
    _, path, meta_path = target_paths(entry)
    return os.path.exists(path) and os.path.exists(meta_path)


def may_refetch(entry):
    _, path, _ = target_paths(entry)
    return (time.time() - os.path.getmtime(path)) >= MIN_REFETCH_AGE_SECONDS


def _status_line(version, status, reason):
    v = {10: "HTTP/1.0", 11: "HTTP/1.1", 20: "HTTP/2"}.get(version, f"HTTP/{version}")
    return f"{v} {status} {reason}".strip()


def manifest_sources(root=None):
    """path -> {'sha256', 'tier'} from manifest.json; 'stable' wins when several cases list one path."""
    root = root or ROOT
    p = os.path.join(root, "manifest.json")
    if not os.path.exists(p):
        return {}
    out = {}
    with open(p) as f:
        m = json.load(f)
    for c in m.get("cases", []):
        for s in c.get("sources", []):
            e = out.setdefault(s["path"], {"sha256": s.get("sha256"), "tiers": set()})
            e["tiers"].add(s.get("tier"))
    for e in out.values():
        e["tier"] = "stable" if "stable" in e["tiers"] else ("live" if "live" in e["tiers"] else sorted(t for t in e["tiers"] if t)[0] if e["tiers"] else None)
        e["tiers"] = sorted(t for t in e["tiers"] if t)
    return out


def drift_report(entries, root=None):
    """Compare each entry's on-disk file with the manifest's recorded SHA-256.
    Returns a list of dicts: path, tier, status in match | drift | not-in-manifest | missing."""
    root = root or ROOT
    src = manifest_sources(root)
    out = []
    for e in entries:
        rel = f"fixtures/{e['case']}/raw/{e['file']}"
        full = os.path.join(root, rel)
        if not os.path.exists(full):
            out.append({"path": rel, "tier": None, "status": "missing"})
            continue
        with open(full, "rb") as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        m = src.get(rel)
        if not m or not m.get("sha256"):
            out.append({"path": rel, "tier": None, "status": "not-in-manifest", "actual": actual})
            continue
        out.append({"path": rel, "tier": m["tier"], "status": "match" if actual == m["sha256"] else "drift",
                    "recorded": m["sha256"], "actual": actual})
    return out


def print_drift(report):
    stable_drift = [r for r in report if r["tier"] == "stable" and r["status"] == "drift"]
    live_drift = [r for r in report if r["tier"] != "stable" and r["status"] == "drift"]
    match = [r for r in report if r["status"] == "match"]
    missing = [r for r in report if r["status"] == "missing"]
    unlisted = [r for r in report if r["status"] == "not-in-manifest"]
    print("\ndrift check against manifest.json (stable-tier sources are expected to be byte-identical to the tested snapshot):")
    for r in stable_drift:
        print(f"  DRIFT  stable source {r['path']}: fetched sha256 {r['actual'][:16]}... != recorded {r['recorded'][:16]}... "
              f"-> the frozen expected values for this file will NOT apply; either the provider changed a 'first record' "
              f"(gp-first stability assumption violated) or the corpus snapshot is out of date.")
    print(f"  {len(match)} file(s) match the tested snapshot ({sum(1 for r in match if r['tier'] == 'stable')} stable, "
          f"{sum(1 for r in match if r['tier'] != 'stable')} live); {len(stable_drift)} STABLE source(s) drifted; "
          f"{len(live_drift)} live source(s) differ (expected: live data changes every 2 hours); "
          f"{len(missing)} missing; {len(unlisted)} not in the manifest.")
    return len(stable_drift)


def fetch_one(entry):
    d, path, meta_path = target_paths(entry)
    os.makedirs(d, exist_ok=True)
    req_headers = {"User-Agent": user_agent(), "Accept": "*/*"}
    req = urllib.request.Request(entry["url"], headers=req_headers)
    started = now_utc(precise=True)
    t0 = time.monotonic()
    unexpected = False
    try:
        with _opener.open(req, timeout=TIMEOUT) as resp:
            status, reason, version = resp.status, resp.reason, resp.version
            body = resp.read()
            headers_all = [[k, v] for k, v in resp.headers.items()]
    except urllib.error.HTTPError as e:
        status, reason, version = e.code, e.reason, getattr(e, "version", None) or 11
        body = e.read() or b""
        headers_all = [[k, v] for k, v in e.headers.items()] if e.headers is not None else []
        unexpected = not entry.get("allow_error")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"\nSTOP: network error for {entry['url']}: {e}\nNot retrying.", file=sys.stderr)
        sys.exit(3)
    finished = now_utc(precise=True)
    elapsed_ms = round((time.monotonic() - t0) * 1000)
    with open(path, "wb") as f:
        f.write(body)
    meta = {
        "url": entry["url"],
        "retrieved_at": started[:19] + "Z",
        "request_started_utc": started,
        "response_completed_utc": finished,
        "elapsed_ms": elapsed_ms,
        "request_headers": dict(req_headers),
        "status_line": _status_line(version, status, reason),
        "http_status": status,
        "http_reason": reason,
        "response_headers": {k: v for k, v in headers_all},
        "response_headers_ordered": headers_all,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "provenance": "live",
        "case": entry["case"],
        "purpose": entry.get("purpose", ""),
        "note": entry.get("note", ""),
        "tool": TOOL_VERSION,
        "user_agent": user_agent(),
    }
    if status != 200:
        meta["note"] = (meta["note"] + " " if meta["note"] else "") + (
            "Unexpected non-200 response; saved so it is never re-requested." if unexpected else
            "Non-200 response deliberately recorded (fetch-list entry has allow_error).")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, sort_keys=True)
        f.write("\n")
    if unexpected:
        print(f"\nSTOP: HTTP {status} for {entry['url']} (body and metadata saved)\n"
              f"--- response body (first 2000 bytes) ---\n{body[:2000].decode('utf-8', 'replace')}\n---",
              file=sys.stderr)
        print("Not retrying: CelesTrak states the response will not change by repeating the "
              "request. Fix the fetch list or stop.", file=sys.stderr)
        sys.exit(2)
    return f"{meta['status_line']}, {len(body)} bytes"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", action="append", help="only entries with this stage (repeatable)")
    ap.add_argument("--case", action="append", help="only entries for this case id (repeatable)")
    ap.add_argument("--skip-case", action="append", default=[], help="leave out this case id (repeatable), e.g. --skip-case satcat-70000-cutoff")
    ap.add_argument("--check-drift", action="store_true", help="do not fetch; compare the files already on disk with the manifest and report drift")
    ap.add_argument("--force", action="store_true", help="re-fetch cached files that are older than 2 hours")
    ap.add_argument("--dry-run", action="store_true", help="print what would be requested and exit")
    ap.add_argument("--include-recaptures", action="store_true",
                    help="also fetch maintainer-only re-capture entries (same endpoint requested a second time when the corpus was built)")
    args = ap.parse_args()

    with open(FETCHLIST) as f:
        entries = json.load(f)
    # duplicate guard: case-insensitive on the URL; entries that document a deliberate re-capture
    # (a 'recapture_of' field) are the only permitted repeats.
    urls = [e["url"].lower() for e in entries if not e.get("recapture_of")]
    dupes = sorted({u for u in urls if urls.count(u) > 1})
    if dupes:
        print("STOP: duplicate URLs in fetch list (a deliberate re-capture must be a separate entry "
              "with a different file name and a 'recapture_of' field):\n  " + "\n  ".join(dupes), file=sys.stderr)
        sys.exit(1)

    selected = [e for e in entries
                if (not args.stage or e["stage"] in args.stage)
                and (not args.case or e["case"] in args.case)
                and e["case"] not in args.skip_case
                and (args.include_recaptures or not e.get("recapture_of"))]
    if args.check_drift:
        present = [e for e in selected if is_cached(e)]
        n = print_drift(drift_report(present))
        sys.exit(2 if n else 0)
    made = 0
    for e in selected:
        cached = is_cached(e)
        will_request = (not cached) or (args.force and may_refetch(e))
        label = f"{e['case']}/{e['file']}"
        if args.dry_run:
            print(("FETCH   " if will_request else "cached  ") + e["url"])
            continue
        if not will_request:
            print(f"{'cached':>34}  {label}")
            continue
        if made:
            time.sleep(PAUSE_SECONDS)
        made += 1
        print(f"{fetch_one(e):>34}  {label}")
    print(f"done: {made} request(s) made, {len(selected) - made} entries skipped")
    if not args.dry_run:
        print_drift(drift_report([e for e in selected if is_cached(e)]))


if __name__ == "__main__":
    main()
