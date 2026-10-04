"""
gpconf fetch -- download corpus source files from CelesTrak exactly once each.

The same code runs as `gpconf fetch` (`python3 -m gpconf fetch`) in an installed copy and as `tools/fetch.py` in a
clone (D-150). It reads the fetch list and the manifest from the corpus root and writes the provider files to the data
root: in a clone both are the repository; installed, the data root is a per-user cache folder unless --data or the
GPCONF_DATA environment variable names another (see gpconf/locate.py).

What CelesTrak asks of software that downloads from it, in its usage policy and in the
FAQ of its GP formats page (as recorded in docs/RESEARCH.md sections 3 and 11), and
what the fetch does about each:
  * download data once per update, and GP data updates every 2 hours at most. Each URL
    is requested at most once per run and, across runs, an existing file is never
    re-fetched, with or without its metadata, unless --force is given AND its recorded
    retrieved_at is at least 2 hours old (a file's mtime is not used because a checkout
    or a sync rewrites it). A re-capture entry (--include-recaptures) is requested only
    when its original is on disk, was retrieved at least 2 hours earlier and was not
    requested in the same run (D-119);
  * stop on any response that is not an HTTP 200 and have a person look; a 403 or 404
    will not change by repeating the request. The run stops for a human at the first
    response the list does not expect (D-228): anything that is not an HTTP 200, and a
    200 that is an HTML page or empty. That response is kept beside the data as
    <file>.unexpected, never in its place, and the URL is not requested again unless
    --force is given two hours or more later. After a refusal (HTTP 403 or 429) no
    request at all is made for two hours. No request of a user's run is expected to
    answer anything but 200 (D-247): the four TLE requests for objects numbered above
    99999, which answer HTTP 404 with the 16-byte text "No GP data found", are not
    made. That answer ships with the corpus as a recorded response (recorded/), and
    the fetch writes it where it used to request it. Only a maintainer's re-capture
    entry (--include-recaptures) still names a 404 as its expected answer
    (expect_status);
  * no more than 50 errors in 2 hours and 100 MB a day from one address. The fetch list
    is static (tools/fetchlist.json): no discovery and no wildcard expansion, so the
    number of requests a run can make is known in advance. An entry that names a launch
    window (launch_window) is the record of one of the corpus's own captures and is
    never requested, under any flag (D-229): CelesTrak serves launch nominals and
    post-deployment files for the days after a launch, so a fetch that asked for them
    would stop for every user once the window closed;
  * only download the data you need. The legacy SATCAT file, three quarters of the
    bytes of the whole list, is read by one data check in which no parser takes part,
    so it is requested only with --include-satcat (D-231).

The fetch's own choices, which CelesTrak does not ask for (D-230):
  * requests are sequential with a fixed pause between them, redirects are not
    followed and nothing is retried;
  * every response gets a sibling .meta.json recording the URL, UTC timestamps, the
    status line, every response header in order, the request headers sent, byte count
    and SHA-256;
  * after a run (and on demand with --check-drift) every file on disk is compared with
    the SHA-256 recorded in manifest.json; a stable-tier source whose bytes differ is
    reported as DRIFT, because the frozen expected values then no longer apply to it
    (live-tier differences are expected and only counted), and the run's exit code is 2.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request

from . import locate
from .words import pick, qty

FETCHLIST = os.path.join("tools", "fetchlist.json")   # relative to the corpus root
RECORDED_PROVENANCE = "recorded"   # a file's metadata says so when the fetch wrote it from the corpus's record (D-247)
PAUSE_SECONDS = 2.0
MIN_REFETCH_AGE_SECONDS = 2 * 3600
TIMEOUT = 60
TOOL_VERSION = "tools/fetch.py v3 (full header capture; stops on any unexpected response)"
NO_DATA_TEXTS = ("No GP data found", "No SupGP data found")  # CelesTrak's body for a query with nothing to return
UNEXPECTED = ".unexpected"          # suffix of a response the fetch list did not expect, kept beside the data (D-228)
REFUSALS = (403, 429)               # the provider refusing the address: no request for two hours afterwards (D-228)
ISSUES_URL = "https://github.com/hneogy/gp-omm-conformance/issues"


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


def default_roots():
    """(corpus, data) as the command line would resolve them with no flags."""
    loc = locate.resolve()
    return loc["corpus"], loc["data"]


def target_paths(entry, root=None):
    """root is the data root, where provider files are written and read."""
    d = os.path.join(root or default_roots()[1], "fixtures", entry["case"], "raw")
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


def unexpected_paths(entry, root=None):
    """Where a response the fetch list did not expect is kept: beside the data file, never in its place, so that
    nothing reads an error page as provider data (D-228) -> (body path, metadata path)."""
    _, path, _ = target_paths(entry, root)
    return path + UNEXPECTED, path + UNEXPECTED + ".meta.json"


def read_unexpected(entry, root=None):
    """The metadata of the unexpected response kept for this entry, {} when the response is there without its
    metadata, or None when there is none."""
    body, meta_path = unexpected_paths(entry, root)
    if not os.path.exists(body):
        return None
    try:
        with open(meta_path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def unexpected_age_seconds(entry, now, root=None):
    """Seconds since the unexpected response kept for this entry arrived: its metadata's retrieved_at, else the
    file's mtime."""
    body, _ = unexpected_paths(entry, root)
    meta = read_unexpected(entry, root) or {}
    try:
        t = dt.datetime.strptime(meta["retrieved_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
        return (now - t).total_seconds()
    except (KeyError, ValueError):
        return now.timestamp() - os.path.getmtime(body)


def why_unexpected(entry, status, body):
    """Why a response is not one the fetch list expects for this entry, or None when it is (D-228).

    Expected: an HTTP 200 that carries something other than an HTML page or nothing; or, on an entry that names
    it with expect_status, the provider's 404 with its no-data text, which is the answer the corpus records for a
    TLE request with nothing to return. Since D-247 the entries of a user's run that name it are never requested
    (their answer ships with the corpus), so this second case is reached only by a maintainer's re-capture.
    CelesTrak asks software to stop at any other response and to have a
    person look, so the old allow_error flag, which let any HTTP error pass on the entries that carried it, a 403
    included, is gone."""
    if status == 200:
        head = body[:1024].lstrip().lower()
        if not body.strip():
            return "an empty body under HTTP 200"
        if head.startswith(b"<!doctype html") or b"<html" in head:
            return "an HTML page under HTTP 200"
        return None
    if status == entry.get("expect_status") and body.decode("utf-8", "replace").strip() in NO_DATA_TEXTS:
        return None
    return f"HTTP {status}"


def recent_refusal(entries, now, root=None):
    """The newest refusal (HTTP 403 or 429) kept for any entry, if it is less than two hours old
    -> (entry, metadata, seconds since it arrived), else None. While one is in force a run makes no request at
    all: without this each re-run would ask the next URL of the list and collect one more refusal (D-228)."""
    newest = None
    for e in entries:
        meta = read_unexpected(e, root)
        if meta is None or meta.get("http_status") not in REFUSALS:
            continue
        age = unexpected_age_seconds(e, now, root)
        if age < MIN_REFETCH_AGE_SECONDS and (newest is None or age < newest[2]):
            newest = (e, meta, age)
    return newest


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


def version_folders(root):
    """Other corpus versions' folders beside a per-user cache folder, newest first -> [(version, folder)] (D-157)."""
    parent, here = os.path.split(os.path.abspath(root))
    if not os.path.isdir(parent):
        return []
    out = []
    for name in os.listdir(parent):
        d = os.path.join(parent, name)
        if name != here and re.fullmatch(r"\d+(\.\d+)*", name) and os.path.isdir(os.path.join(d, "fixtures")):
            out.append((name, d))
    return sorted(out, key=lambda v: tuple(int(p) for p in v[0].split(".")), reverse=True)


def reusable(entries, root, corpus, sources):
    """-> {path: (version, source file)} for each stable-tier entry this folder lacks whose copy in an earlier version's
    folder holds exactly the bytes this version's manifest records, metadata included (D-153, D-157). A live file is
    never reused, even when its bytes match: an upgrade brings current data."""
    man = manifest_sources(corpus)
    out = {}
    for e in entries:
        rel = f"fixtures/{e['case']}/raw/{e['file']}"
        m = man.get(rel) or {}
        if m.get("tier") != "stable" or not m.get("sha256") or is_cached(e, root) or e.get("recorded"):
            continue   # a recorded answer is written from the corpus itself, never copied from another version
        for version, d in sources:
            src = os.path.join(d, rel)
            if os.path.isfile(src) and os.path.isfile(src + ".meta.json"):
                with open(src, "rb") as f:
                    if hashlib.sha256(f.read()).hexdigest() == m["sha256"]:
                        out[rel] = (version, src)
                        break
    return out


def reuse_one(entry, version, src, root=None):
    """Copy a reusable file and its metadata into this folder. The metadata keeps the original retrieved_at, so the
    two-hour rule and the provenance still describe the one request that was made, and gains reused_from."""
    d, path, meta_path = target_paths(entry, root)
    os.makedirs(d, exist_ok=True)
    shutil.copyfile(src, path)
    with open(src + ".meta.json") as f:
        meta = json.load(f)
    meta["reused_from"] = {"corpus_version": version, "path": src}
    meta["reused_at"] = now_utc()
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, sort_keys=True)
        f.write("\n")
    return f"reused from {version}"


def recorded_answer(entry, corpus):
    """The provider response the corpus ships for this entry -> (body, the provenance file's content). Refuses a
    record that is not the bytes its own provenance and the manifest give for this file: the fetch writes nothing it
    cannot tie to a capture (D-247)."""
    rel = entry["recorded"]
    path = os.path.join(corpus, *rel.split("/"))
    with open(path, "rb") as f:
        body = f.read()
    with open(os.path.splitext(path)[0] + ".provenance.json") as f:
        prov = json.load(f)
    actual = hashlib.sha256(body).hexdigest()
    want = (manifest_sources(corpus).get(f"fixtures/{entry['case']}/raw/{entry['file']}") or {}).get("sha256")
    if actual != prov.get("sha256") or (want and actual != want):
        raise ValueError(f"{rel} does not hold the bytes its provenance and the manifest record for {entry['file']}")
    return body, prov


def record_one(entry, corpus, root=None):
    """Write the corpus's recorded answer for this entry into the data folder, with metadata that says where it came
    from. No request is made (D-247). The metadata gives the status and the time of the corpus's own capture of this
    URL, so that the runner reads the file as it reads a fetched one, and says in so many words that this fetch did not
    ask for it."""
    body, prov = recorded_answer(entry, corpus)
    capture = next((c for c in prov.get("captures", []) if c.get("url") == entry["url"]), {})
    d, path, meta_path = target_paths(entry, root)
    os.makedirs(d, exist_ok=True)
    status = capture.get("http_status", prov.get("http_status"))
    meta = {
        "url": entry["url"],
        "retrieved_at": capture.get("retrieved_at"),
        "http_status": status,
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "provenance": RECORDED_PROVENANCE,
        "requested": False,
        "recorded": {"file": entry["recorded"], "written_at": now_utc(),
                     "captured_at": capture.get("retrieved_at"),
                     "received_again": sorted(r["retrieved_at"] for r in prov.get("received_again", []) if r.get("url") == entry["url"])},
        "case": entry["case"],
        "purpose": entry.get("purpose", ""),
        "note": (f"Not requested by this fetch. Written from the corpus's record of CelesTrak's answer to this URL: HTTP {status}, "
                 f"{qty(len(body), 'byte')}, the text {body.decode('utf-8', 'replace').strip()!r}, captured {capture.get('retrieved_at')}. "
                 f"The record ships with the corpus as {entry['recorded']} (D-247)."),
        "tool": TOOL_VERSION,
    }
    with open(path, "wb") as f:
        f.write(body)
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, sort_keys=True)
        f.write("\n")
    return f"written from the record, {qty(len(body), 'byte')}"


def plan(entries, force=False, include_recaptures=False, root=None, now=None, reuse=None, include_satcat=False):
    """What a run would do for each entry, without touching the network -> [{'entry', 'action', 'reason'}], action
    'fetch' | 'cached' | 'skip' | 'reuse' | 'record' | 'unexpected'. One request per URL per run. An entry whose answer
    ships with the corpus ('record') is written from that record and requested under no flag (D-247). A re-capture entry (the same
    endpoint a second time, for the recapture cases) is planned only with include_recaptures, and requested only
    when its original is on disk, was retrieved at least two hours earlier and is not itself requested in this run
    (D-119). An entry whose last answer was unexpected ('unexpected': the response is kept beside the data) is not
    requested again unless force is given and that answer is at least two hours old (D-228)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    by_file = {(e["case"], e["file"]): e for e in entries}
    requested, out = set(), []

    def hours(seconds):
        return f"{seconds / 3600:.1f} h"

    for e in entries:
        recap = e.get("recapture_of")
        if recap and not include_recaptures:
            continue
        if e.get("launch_window"):  # a capture of a launch window: never requested (D-229)
            continue
        if e.get("recorded"):  # the provider's answer to this URL ships with the corpus: never requested (D-247)
            if is_cached(e, root):
                out.append({"entry": e, "action": "cached", "reason": "on disk; this URL's answer is the corpus's record and is never requested"})
            else:
                out.append({"entry": e, "action": "record", "reason": f"the corpus's record of this URL's answer, {e['recorded']}: written from it, not requested"})
            continue
        # the legacy SATCAT file is requested only when asked for (D-231): not planned when absent, and not refreshed by
        # --force when an earlier fetch left it on disk, where it is kept and still compared with the manifest
        opted_out = e.get("opt_in") == "satcat" and not include_satcat
        if opted_out and not is_cached(e, root):
            continue
        unexp = read_unexpected(e, root)
        rel = f"fixtures/{e['case']}/raw/{e['file']}"
        if unexp is not None and not (reuse and rel in reuse and not is_cached(e, root)):
            # the URL's last answer was one the list did not expect: whatever else is true of the entry, it is not
            # asked again inside two hours, and after that only with --force
            u_age = unexpected_age_seconds(e, now, root)
            what = f"HTTP {unexp['http_status']}" if unexp.get("http_status") else "an unexpected response"
            if unexp.get("unexpected", "").startswith("an "):
                what = unexp["unexpected"]
            kept = os.path.basename(unexpected_paths(e, root)[0])
            if force and u_age >= MIN_REFETCH_AGE_SECONDS and not opted_out:
                action, reason = "fetch", f"--force: answered {what} {hours(u_age)} ago"
            else:
                action = "cached" if is_cached(e, root) else "unexpected"
                reason = (f"answered {what} {hours(u_age)} ago: kept as {kept}, not requested again"
                          + (" (less than two hours: --force does not apply)" if force else " (--force applies after two hours)"))
        elif is_cached(e, root):
            age, basis = age_seconds(e, now, root)
            if read_meta(e, root) is None:
                if force and age >= MIN_REFETCH_AGE_SECONDS and not opted_out:
                    action, reason = "fetch", f"--force: on disk without metadata, mtime {hours(age)} old"
                else:
                    action, reason = "cached", "on disk without metadata: kept, not re-requested (delete the file to fetch it again)"
            elif force and age >= MIN_REFETCH_AGE_SECONDS and not opted_out:
                action, reason = "fetch", f"--force: retrieved {hours(age)} ago"
            else:
                action, reason = "cached", f"retrieved {hours(age)} ago" + (
                    " (refreshed only with --include-satcat)" if force and opted_out
                    else " (less than two hours: --force does not apply)" if force else "")
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
        elif reuse and rel in reuse:
            version = reuse[rel][0]
            action, reason = "reuse", (f"stable tier: the copy in corpus {version}'s cache holds the bytes this version's "
                                       f"manifest records; copied, not requested")
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
    """path -> {'sha256', 'tier'} from manifest.json under root, the corpus root; 'stable' wins when several cases
    list one path."""
    root = root or default_roots()[0]
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


def drift_report(entries, root=None, corpus=None):
    """Compare each entry's on-disk file (under root, the data root) with the SHA-256 recorded in the corpus root's
    manifest (corpus; the same folder as root when not given, as in a clone).
    Returns a list of dicts: path, tier, status in match | drift | not-in-manifest | missing."""
    if root is None:
        corpus, root = (corpus, default_roots()[1]) if corpus else default_roots()
    src = manifest_sources(corpus or root)
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


def drift_line(match, stable, stable_drift, live_drift, missing, unlisted):
    """The drift check's last line, each count agreeing in number with its noun and verb (D-239)."""
    return (f"{qty(match, 'file')} {pick(match, 'matches', 'match')} the tested snapshot ({stable} stable, {match - stable} live); "
            f"{qty(stable_drift, 'STABLE source')} drifted; "
            f"{qty(live_drift, 'live source')} {pick(live_drift, 'differs', 'differ')} (expected: live data changes every 2 hours); "
            f"{missing} missing; {unlisted} not in the manifest.")


def captures_line(n, windows):
    """What the fetch says of the launch-window captures it does not request (D-229), agreeing in number (D-239)."""
    return (f"not requested: {qty(n, 'launch-window capture')} ({'; '.join(windows)}). "
            f"CelesTrak serves launch nominals for the days after a launch; {pick(n, 'this entry records', 'these entries record')} "
            f"the corpus's own capture and no fetch asks for {pick(n, 'it', 'them')}.")


def refusal_line(status, age, left, url, kept):
    """The stop inside the two quiet hours after a refusal (D-228); the minutes agree in number (D-239)."""
    ago, remain = round(age / 60), round(left / 60)
    return (f"STOP: CelesTrak refused this address with HTTP {status} {qty(ago, 'minute')} ago "
            f"({url}). No request is made for two hours after a refusal, with or without --force: "
            f"{qty(remain, 'minute')} {pick(remain, 'remains', 'remain')}. The refused response is kept as {kept}; read it, it says why.")


def recorded_line(n):
    """What the fetch says of the requests it does not make because their answer ships with the corpus (D-247)."""
    return (f"not requested: {qty(n, 'TLE request')} for {pick(n, 'an object', 'objects')} numbered above 99999, which CelesTrak answers with HTTP 404 and the "
            f"text 'No GP data found'. That answer ships with the corpus as a recorded response (recorded/); "
            f"{pick(n, 'the file is', 'the files are')} written from it.")


def dry_run_line(n_fetch, n_reuse, left, n_record=0):
    """What a dry run says a real run would do (D-150), agreeing in number (D-239)."""
    also = f", reuse {qty(n_reuse, 'file')} from an earlier corpus version's cache" if n_reuse else ""
    also += f", write {qty(n_record, 'file')} from the corpus's record of the provider's answer" if n_record else ""
    return (f"dry run: no request made; a run would make {qty(n_fetch, 'request')}{also} and leave "
            f"{qty(left, 'entry', 'entries')} as {pick(left, 'it is', 'they are')}")


def done_line(made, reused, skipped, recorded=0):
    """The fetch's closing line, agreeing in number (D-239)."""
    also = f", {qty(reused, 'file')} reused from an earlier corpus version's cache" if reused else ""
    also += f", {qty(recorded, 'file')} written from the corpus's record of the provider's answer" if recorded else ""
    return f"done: {qty(made, 'request')} made{also}, {qty(skipped, 'entry', 'entries')} skipped"


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
    print("  " + drift_line(len(match), sum(1 for r in match if r["tier"] == "stable"), len(stable_drift), len(live_drift),
                            len(missing), len(unlisted)), file=out)
    return len(stable_drift)


def fetch_one(entry, root=None):
    d, path, meta_path = target_paths(entry, root)
    os.makedirs(d, exist_ok=True)
    req_headers = {"User-Agent": user_agent(), "Accept": "*/*"}
    req = urllib.request.Request(entry["url"], headers=req_headers)
    started = now_utc(precise=True)
    t0 = time.monotonic()
    try:
        with _opener.open(req, timeout=TIMEOUT) as resp:
            status, reason, version = resp.status, resp.reason, resp.version
            body = resp.read()
            headers_all = [[k, v] for k, v in resp.headers.items()]
    except urllib.error.HTTPError as e:
        status, reason, version = e.code, e.reason, getattr(e, "version", None) or 11
        body = e.read() or b""
        headers_all = [[k, v] for k, v in e.headers.items()] if e.headers is not None else []
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"\nSTOP: network error for {entry['url']}: {e}\nNot retrying.", file=sys.stderr)
        sys.exit(3)
    finished = now_utc(precise=True)
    elapsed_ms = round((time.monotonic() - t0) * 1000)
    why = why_unexpected(entry, status, body)
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
    u_path, u_meta_path = unexpected_paths(entry, root)
    if why:
        # Kept beside the data, never in its place (D-228): the runner would otherwise read an error page as provider
        # data. The file is what stops a later run asking this URL again.
        meta["unexpected"] = why
        meta["note"] = (meta["note"] + " " if meta["note"] else "") + (
            f"Unexpected response ({why}): kept beside the data, not in its place, and not requested again.")
        with open(u_path, "wb") as f:
            f.write(body)
        with open(u_meta_path, "w") as f:
            json.dump(meta, f, indent=2, sort_keys=True)
            f.write("\n")
        kept = os.path.relpath(u_path, root or default_roots()[1])
        lines = [f"\nSTOP: {why} for {entry['url']}",
                 f"The response is kept as {kept} (with its metadata), beside the data and not in its place.",
                 "Nothing was retried and no further request was made."]
        if status in REFUSALS:
            lines.append("CelesTrak has refused this address. Read the kept response: it says why. The fetch makes no "
                         "request at all for the next two hours, with or without --force.")
        else:
            lines.append(f"This is not the answer the corpus's fetch list expects for this URL, and CelesTrak states the "
                         f"response will not change by repeating the request. Report it at {ISSUES_URL}: the list may be "
                         f"out of date. The URL is asked again only with --force, two hours or more from now.")
        lines.append(f"--- response body (first 2000 bytes) ---\n{body[:2000].decode('utf-8', 'replace')}\n---")
        print("\n".join(lines), file=sys.stderr)
        sys.exit(2)
    with open(path, "wb") as f:
        f.write(body)
    if status != 200:
        meta["note"] = (meta["note"] + " " if meta["note"] else "") + (
            f"The answer the fetch list expects here (expect_status {status}): the provider's no-data text, recorded as the response.")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, sort_keys=True)
        f.write("\n")
    for stale in (u_path, u_meta_path):  # an earlier unexpected answer to this URL is superseded by this one
        if os.path.exists(stale):
            os.remove(stale)
    return f"{meta['status_line']}, {qty(len(body), 'byte')}"


def run(argv=None, root=None, entries=None, now=None, fetch_one=None, out=None, pause=PAUSE_SECONDS, corpus=None, prog=None,
        reuse_sources=None):
    """The command line, parameterised so the request logic can be tested with a stub in place of fetch_one and a
    temporary root: returns the exit code (0; 1 for a bad fetch list; 2 when a stable-tier source drifted, or when
    a refusal less than two hours old means no request is made).
    root is the data root and corpus the corpus root; given by a caller they bypass the command line's --root and
    --data, and corpus defaults to root, the layout of a clone and of the tests. Stable-tier files are reused from
    earlier corpus versions' folders when the data root is a per-user cache folder (D-157); reuse_sources, a list of
    (version, folder), names them for a caller."""
    ap = argparse.ArgumentParser(prog=prog, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="corpus root (default: the clone this runs from, or the corpus installed with the package)")
    ap.add_argument("--data", help=f"folder the provider files are written to (default: ${locate.DATA_ENV}, else the clone, else a per-user cache folder)")
    ap.add_argument("--stage", action="append", help="only entries with this stage (repeatable)")
    ap.add_argument("--case", action="append", help="only entries for this case id (repeatable)")
    ap.add_argument("--skip-case", action="append", default=[], help="leave out this case id (repeatable), e.g. --skip-case satcat-70000-cutoff")
    ap.add_argument("--check-drift", action="store_true", help="do not fetch; compare the files already on disk with the manifest and report drift")
    ap.add_argument("--force", action="store_true", help="re-fetch cached files whose recorded retrieved_at is at least 2 hours old")
    ap.add_argument("--dry-run", action="store_true", help="print what would be requested and exit")
    ap.add_argument("--include-satcat", action="store_true",
                    help="also fetch the 9.4 MB legacy SATCAT file (pub/satcat.txt). Only the data check satcat-70000-cutoff reads it, "
                         "and no parser takes part in that check, so a fetch leaves it out unless asked")
    ap.add_argument("--include-recaptures", action="store_true",
                    help="also fetch maintainer-only re-capture entries (same endpoint requested a second time when the corpus was built); "
                         "requested only when the original is on disk and at least 2 hours old")
    args = ap.parse_args(argv)
    out = out or sys.stdout
    now = now or dt.datetime.now(dt.timezone.utc)
    do_fetch = fetch_one or globals()["fetch_one"]
    data_why = None
    if root is None:
        try:
            loc = locate.resolve(args.root, args.data)
        except locate.CorpusNotFound as e:
            print(f"gpconf fetch: {e}", file=sys.stderr)
            return 2
        corpus, root, data_why = loc["corpus"], loc["data"], loc["data_why"]
        print(f"provider data: {root} ({data_why})", file=out)
    corpus = corpus or root
    if entries is None:
        with open(os.path.join(corpus, FETCHLIST)) as f:
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
    # Launch-window captures are never requested (D-229). Where one is on disk, as in the maintainer's clone, it is
    # still compared with the manifest.
    captures = [e for e in selected if e.get("launch_window")]
    selected = [e for e in selected if not e.get("launch_window")]
    if args.check_drift:
        present = [e for e in selected + captures if is_cached(e, root)]
        n = print_drift(drift_report(present, root, corpus), out)
        return 2 if n else 0
    left_out = [e for e in selected if e.get("opt_in") == "satcat" and not args.include_satcat and not is_cached(e, root)]
    if left_out:
        print("not requested: the legacy SATCAT file (pub/satcat.txt, 9.4 MB). Only the data check satcat-70000-cutoff reads it, "
              "and no parser takes part in that check; pass --include-satcat to fetch it.", file=out)
    if captures:
        print(captures_line(len(captures), sorted({e["launch_window"] for e in captures})), file=out)
    from_record = [e for e in selected if e.get("recorded") and not is_cached(e, root)]
    if from_record:
        print(recorded_line(len(from_record)), file=out)
    refused = recent_refusal(entries, now, root)
    if refused:
        # two quiet hours after a refusal, whatever is asked for (D-228); the dry run says the same and makes none either
        e, meta, age = refused
        left = MIN_REFETCH_AGE_SECONDS - age
        kept = os.path.relpath(unexpected_paths(e, root)[0], root)
        print(refusal_line(meta.get("http_status"), age, left, e["url"], kept), file=out)
        return 2
    sources = reuse_sources if reuse_sources is not None else (version_folders(root) if data_why == "per-user cache" else [])
    reuse = reusable(selected, root, corpus, sources) if sources else {}
    planned = plan(selected, force=args.force, include_recaptures=args.include_recaptures, root=root, now=now, reuse=reuse,
                   include_satcat=args.include_satcat)
    made = reused = recorded = 0
    for p in planned:
        e, label = p["entry"], f"{p['entry']['case']}/{p['entry']['file']}"
        if args.dry_run:
            head = {"fetch": "FETCH   ", "reuse": "REUSE   ", "record": "RECORD  "}.get(p["action"], f"{p['action']:7s} ")
            print(head + e["url"] + ("" if p["action"] == "fetch" else f"  ({p['reason']})"), file=out)
            continue
        if p["action"] == "record":
            recorded += 1
            print(f"{record_one(e, corpus, root=root):>34}  {label}  (the corpus's record of this URL's answer; no request)", file=out)
            continue
        if p["action"] == "reuse":
            version, src = reuse[f"fixtures/{e['case']}/raw/{e['file']}"]
            reused += 1
            print(f"{reuse_one(e, version, src, root=root):>34}  {label}  (stable tier, the bytes this version records; no request)", file=out)
            continue
        if p["action"] != "fetch":
            print(f"{p['action']:>34}  {label}  ({p['reason']})", file=out)
            continue
        if made and pause:
            time.sleep(pause)
        made += 1
        print(f"{do_fetch(e, root=root):>34}  {label}", file=out)
    if args.dry_run:  # the planned requests are not "skipped" (D-150): say what a real run would do
        n_fetch = sum(1 for p in planned if p["action"] == "fetch")
        n_reuse = sum(1 for p in planned if p["action"] == "reuse")
        n_record = sum(1 for p in planned if p["action"] == "record")
        print(dry_run_line(n_fetch, n_reuse, len(planned) - n_fetch - n_reuse - n_record, n_record), file=out)
        return 0
    print(done_line(made, reused, len(planned) - made - reused - recorded, recorded), file=out)
    n = print_drift(drift_report([e for e in [p["entry"] for p in planned] + captures if is_cached(e, root)], root, corpus), out)
    return 2 if n else 0
