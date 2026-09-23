#!/usr/bin/env python3
"""
tools/fetch.py -- download corpus source files from CelesTrak exactly once each.

Rules (CelesTrak usage policy; see docs/RESEARCH.md sections 3 and 11):
  * each URL is requested at most once per run and, across runs, an existing file
    is never re-fetched, with or without its metadata, unless --force is given AND
    its recorded retrieved_at is at least 2 hours old (CelesTrak refreshes GP data
    every 2 hours at most; a file's mtime is not used because a checkout or a sync
    rewrites it). A re-capture entry (--include-recaptures) is requested only when
    its original is on disk, was retrieved at least 2 hours earlier and was not
    requested in the same run; the run's exit code is 2 when a stable-tier source
    drifted (D-119);
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


def target_paths(entry, root=None):
    d = os.path.join(root or ROOT, "fixtures", entry["case"], "raw")
    return d, os.path.join(d, entry["file"]), os.path.join(d, entry["file"] + ".meta.json")


def read_meta(entry, root=None):
    """The sibling .meta.json as a dict, or None when the file has none."""
    _, _, meta_path = target_paths(entry, root)
    if not os.path.exists(meta_path):
        return None
    with open(meta_path) as f:
        return json.load(f)


def is_cached(entry, root=None):
    """A raw file on disk counts as fetched whether or not its metadata is present: a URL is never re-requested
    because a sibling file went missing (D-119). plan() reports the missing metadata."""
    return os.path.exists(target_paths(entry, root)[1])


def age_seconds(entry, now, root=None):
    """Seconds since the file was retrieved -> (seconds, 'retrieved_at' | 'mtime'): the metadata's retrieved_at when
    present, else the file's mtime (a checkout or a sync rewrites mtimes, so it is only a fallback)."""
    _, path, _ = target_paths(entry, root)
    meta = read_meta(entry, root)
    if meta and meta.get("retrieved_at"):
        try:
            t = dt.datetime.strptime(meta["retrieved_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
            return (now - t).total_seconds(), "retrieved_at"
        except ValueError:
            pass
    return now.timestamp() - os.path.getmtime(path), "mtime"


def duplicate_urls(entries):
    """URLs (case-insensitive) that more than one entry requests, re-capture entries excepted; the list must have none."""
    urls = [e["url"].lower() for e in entries if not e.get("recapture_of")]
    return sorted({u for u in urls if urls.count(u) > 1})


def plan(entries, force=False, include_recaptures=False, root=None, now=None):
    """What a run would do for each entry, without touching the network -> [{'entry', 'action', 'reason'}], action
    'fetch' | 'cached' | 'skip'. One request per URL per run. A re-capture entry (the same endpoint a second time,
    for the recapture cases) is planned only with include_recaptures, and requested only when its original is on
    disk, was retrieved at least two hours earlier and is not itself requested in this run (D-119)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    by_file = {(e["case"], e["file"]): e for e in entries}
    requested, out = set(), []

    def hours(seconds):
        return f"{seconds / 3600:.1f} h"

    for e in entries:
        recap = e.get("recapture_of")
        if recap and not include_recaptures:
            continue
        if is_cached(e, root):
            age, basis = age_seconds(e, now, root)
            if read_meta(e, root) is None:
                if force and age >= MIN_REFETCH_AGE_SECONDS:
                    action, reason = "fetch", f"--force: on disk without metadata, mtime {hours(age)} old"
                else:
                    action, reason = "cached", "on disk without metadata: kept, not re-requested (delete the file to fetch it again)"
            elif force and age >= MIN_REFETCH_AGE_SECONDS:
                action, reason = "fetch", f"--force: retrieved {hours(age)} ago"
            else:
                action, reason = "cached", f"retrieved {hours(age)} ago" + (" (less than two hours: --force does not apply)" if force else "")
        elif recap:
            orig = by_file.get((e["case"], recap))
            if orig is None or not is_cached(orig, root):
                action, reason = "skip", f"re-capture of {recap}: the original is not on disk; a re-capture repeats an endpoint only after its original was fetched"
            elif orig["url"].lower() in requested:
                action, reason = "skip", f"re-capture of {recap}: its original is requested in this run; one request per URL per run"
            else:
                age, basis = age_seconds(orig, now, root)
                if age < MIN_REFETCH_AGE_SECONDS:
                    action, reason = "skip", f"re-capture of {recap}: the original was retrieved {hours(age)} ago, less than two hours (CelesTrak refreshes at most every two hours)"
                else:
                    action, reason = "fetch", f"re-capture of {recap}, whose original was retrieved {hours(age)} ago"
        else:
            action, reason = "fetch", "not on disk"
        if action == "fetch":
            if e["url"].lower() in requested:
                action, reason = "skip", "this URL is already requested in this run"
            else:
                requested.add(e["url"].lower())
        out.append({"entry": e, "action": action, "reason": reason})
    return out


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


def print_drift(report, out=None):
    out = out or sys.stdout
    stable_drift = [r for r in report if r["tier"] == "stable" and r["status"] == "drift"]
    live_drift = [r for r in report if r["tier"] != "stable" and r["status"] == "drift"]
    match = [r for r in report if r["status"] == "match"]
    missing = [r for r in report if r["status"] == "missing"]
    unlisted = [r for r in report if r["status"] == "not-in-manifest"]
    print("\ndrift check against manifest.json (stable-tier sources are expected to be byte-identical to the tested snapshot):", file=out)
    for r in stable_drift:
        print(f"  DRIFT  stable source {r['path']}: fetched sha256 {r['actual'][:16]}... != recorded {r['recorded'][:16]}... "
              f"-> the frozen expected values for this file will NOT apply; either the provider changed a 'first record' "
              f"(gp-first stability assumption violated) or the corpus snapshot is out of date.", file=out)
    print(f"  {len(match)} file(s) match the tested snapshot ({sum(1 for r in match if r['tier'] == 'stable')} stable, "
          f"{sum(1 for r in match if r['tier'] != 'stable')} live); {len(stable_drift)} STABLE source(s) drifted; "
          f"{len(live_drift)} live source(s) differ (expected: live data changes every 2 hours); "
          f"{len(missing)} missing; {len(unlisted)} not in the manifest.", file=out)
    return len(stable_drift)


def fetch_one(entry, root=None):
    d, path, meta_path = target_paths(entry, root)
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


def run(argv=None, root=None, entries=None, now=None, fetch_one=None, out=None, pause=PAUSE_SECONDS):
    """The command line, parameterised so the request logic can be tested with a stub in place of fetch_one and a
    temporary root: returns the exit code (0; 1 for a bad fetch list; 2 when a stable-tier source drifted)."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", action="append", help="only entries with this stage (repeatable)")
    ap.add_argument("--case", action="append", help="only entries for this case id (repeatable)")
    ap.add_argument("--skip-case", action="append", default=[], help="leave out this case id (repeatable), e.g. --skip-case satcat-70000-cutoff")
    ap.add_argument("--check-drift", action="store_true", help="do not fetch; compare the files already on disk with the manifest and report drift")
    ap.add_argument("--force", action="store_true", help="re-fetch cached files whose recorded retrieved_at is at least 2 hours old")
    ap.add_argument("--dry-run", action="store_true", help="print what would be requested and exit")
    ap.add_argument("--include-recaptures", action="store_true",
                    help="also fetch maintainer-only re-capture entries (same endpoint requested a second time when the corpus was built); "
                         "requested only when the original is on disk and at least 2 hours old")
    args = ap.parse_args(argv)
    out = out or sys.stdout
    now = now or dt.datetime.now(dt.timezone.utc)
    do_fetch = fetch_one or globals()["fetch_one"]
    if entries is None:
        with open(FETCHLIST) as f:
            entries = json.load(f)
    # duplicate guard: case-insensitive on the URL; entries that document a deliberate re-capture
    # (a 'recapture_of' field) are the only permitted repeats.
    dupes = duplicate_urls(entries)
    if dupes:
        print("STOP: duplicate URLs in fetch list (a deliberate re-capture must be a separate entry "
              "with a different file name and a 'recapture_of' field):\n  " + "\n  ".join(dupes), file=out)
        return 1
    selected = [e for e in entries
                if (not args.stage or e["stage"] in args.stage)
                and (not args.case or e["case"] in args.case)
                and e["case"] not in args.skip_case
                and (args.include_recaptures or not e.get("recapture_of"))]
    if args.check_drift:
        present = [e for e in selected if is_cached(e, root)]
        n = print_drift(drift_report(present, root), out)
        return 2 if n else 0
    planned = plan(selected, force=args.force, include_recaptures=args.include_recaptures, root=root, now=now)
    made = 0
    for p in planned:
        e, label = p["entry"], f"{p['entry']['case']}/{p['entry']['file']}"
        if args.dry_run:
            print(("FETCH   " if p["action"] == "fetch" else f"{p['action']:8s}") + e["url"] + ("" if p["action"] == "fetch" else f"  ({p['reason']})"), file=out)
            continue
        if p["action"] != "fetch":
            print(f"{p['action']:>34}  {label}  ({p['reason']})", file=out)
            continue
        if made and pause:
            time.sleep(pause)
        made += 1
        print(f"{do_fetch(e, root=root):>34}  {label}", file=out)
    print(f"done: {made} request(s) made, {len(planned) - made} entries skipped", file=out)
    if args.dry_run:
        return 0
    n = print_drift(drift_report([p["entry"] for p in planned if is_cached(p["entry"], root)], root), out)
    return 2 if n else 0


def main():
    sys.exit(run())


if __name__ == "__main__":
    main()
