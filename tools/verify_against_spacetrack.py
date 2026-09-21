#!/usr/bin/env python3
"""
tools/verify_against_spacetrack.py -- verify the corpus's derived Alpha-5 TLE lines against
Space-Track, using YOUR OWN Space-Track account. Standard library only.

What it does
  1. asks for your Space-Track username and password interactively (never as arguments, never
     logged, never written anywhere);
  2. logs in, runs exactly four queries at least 3 seconds apart, logs out;
  3. saves the four raw responses to ~/spacetrack-verify/ (outside any repository; the tool
     refuses to run if that directory would be inside this repository);
  4. compares every returned TLE with derived/alpha5-tle/*.tle and prints ONLY catalog fields,
     verdicts, differing column numbers and summary counts -- never element values, full lines or
     file contents.

Why it exists
  CelesTrak emits no Alpha-5, so the corpus's Alpha-5 lines are rendered from CelesTrak OMM records
  (see DECISIONS D-001, D-016, D-037). Space-Track does emit Alpha-5 for ids 100000-339999. Anyone
  with a Space-Track account can therefore check the encoding against provider output. The corpus
  itself redistributes no Space-Track data, and this tool never writes into the repository.

Exit codes: 0 ran and every field checked out (column differences are reported, not failures);
            1 login failed; 2 HTTP or network error; 3 a query returned no records;
            4 a verification defect (invalid Alpha-5 field, line-2 field differs from line 1,
              or a decoded id outside the queried range); 5 refused (output path inside the repo).
"""
import datetime as dt
import getpass
import glob
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DERIVED_GLOB = os.path.join(REPO, "derived", "alpha5-tle", "*.tle")
OUT_DIR = os.path.expanduser("~/spacetrack-verify")
BASE = "https://www.space-track.org/basicspacedata/query/"
LOGIN = "https://www.space-track.org/ajaxauth/login"
LOGOUT = "https://www.space-track.org/ajaxauth/logout"
PAUSE_SECONDS = 3.0
TIMEOUT = 90
QUERIES = [
    ("q1-gp-100000-100020", "class/gp/NORAD_CAT_ID/100000--100020/orderby/NORAD_CAT_ID%20asc/format/tle/emptyresult/show", (100000, 100020)),
    ("q2-gp-270000-270020", "class/gp/NORAD_CAT_ID/270000--270020/orderby/NORAD_CAT_ID%20asc/format/tle/emptyresult/show", (270000, 270020)),
    ("q3-gp-history-100000-first", "class/gp_history/NORAD_CAT_ID/100000/orderby/EPOCH%20asc/limit/1/format/tle/emptyresult/show", (100000, 100000)),
    ("q4-gp-history-270449-first", "class/gp_history/NORAD_CAT_ID/270449/orderby/EPOCH%20asc/limit/1/format/tle/emptyresult/show", (270449, 270449)),
]
ALPHA5 = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # Space-Track table: A=10 ... Z=33, I and O unused


# --------------------------------------------------------------------------- pure comparison logic (unit-tested)
def decode_alpha5(field):
    """Strict Alpha-5 decode of a five-character catalog field; raises ValueError on anything else."""
    if len(field) != 5 or field != field.strip():
        raise ValueError("field must be five characters")
    if field[0].isalpha():
        if field[0] not in ALPHA5:
            raise ValueError("letter not in the Alpha-5 alphabet")
        return (ALPHA5.index(field[0]) + 10) * 10000 + int(field[1:])
    return int(field)


def parse_tle_pairs(text):
    """-> list of (line1, line2) for every '1 '/'2 ' pair in text (names, if any, are ignored)."""
    lines = [l.rstrip("\r") for l in text.splitlines()]
    out = []
    for i, l in enumerate(lines):
        if l.startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            out.append((l, lines[i + 1]))
    return out


def load_derived(pattern=DERIVED_GLOB):
    """Index the corpus's derived lines: {catalog_field: [(l1, l2), ...]}."""
    idx = {}
    for p in sorted(glob.glob(pattern)):
        with open(p, encoding="utf-8") as f:
            for l1, l2 in parse_tle_pairs(f.read()):
                idx.setdefault(l1[2:7], []).append((l1, l2))
    return idx


def differing_columns(a, b):
    """1-based column numbers where two lines differ (length differences count from the shorter end)."""
    cols = [i + 1 for i, (x, y) in enumerate(zip(a, b)) if x != y]
    cols += list(range(min(len(a), len(b)) + 1, max(len(a), len(b)) + 1))
    return cols


def compare_record(l1, l2, derived_idx, id_range):
    """Compare one Space-Track TLE (l1, l2) with the derived set. Returns a dict with only
    catalog fields, verdicts, booleans and column numbers -- no element values."""
    field = l1[2:7]
    r = {"field": field, "verdict": None, "line2_field_matches": l2[2:7] == field, "in_range": None,
         "decoded": None, "columns_l1": [], "columns_l2": [], "intl_designator_matches": None,
         "inclination_within_0_05": None, "invalid": False}
    try:
        r["decoded"] = decode_alpha5(field)
        r["in_range"] = id_range[0] <= r["decoded"] <= id_range[1]
    except ValueError:
        r["invalid"] = True
        r["verdict"] = "INVALID catalog field (not five characters or not in the Alpha-5 alphabet)"
        return r
    cands = derived_idx.get(field, [])
    same_epoch = [(d1, d2) for d1, d2 in cands if d1[18:32] == l1[18:32]]
    if same_epoch:
        d1, d2 = same_epoch[0]
        r["columns_l1"], r["columns_l2"] = differing_columns(l1, d1), differing_columns(l2, d2)
        r["verdict"] = "EXACT" if not r["columns_l1"] and not r["columns_l2"] else "same field and epoch; lines differ"
    elif cands:
        d1, d2 = cands[0]
        r["intl_designator_matches"] = l1[9:17] == d1[9:17]
        try:
            r["inclination_within_0_05"] = abs(float(l2[8:16]) - float(d2[8:16])) <= 0.05
        except ValueError:
            r["inclination_within_0_05"] = False
        r["verdict"] = "encoding field matches a derived line (different epoch)"
    else:
        r["verdict"] = "field decodes correctly; no derived line for this id (nothing to byte-compare)"
    return r


def summarize(results):
    s = {"records": len(results), "exact": 0, "same_epoch_differs": 0, "encoding_only": 0, "no_derived_line": 0,
         "invalid_field": 0, "line2_field_mismatch": 0, "out_of_range": 0}
    for r in results:
        if r["invalid"]:
            s["invalid_field"] += 1
        elif r["verdict"] == "EXACT":
            s["exact"] += 1
        elif r["verdict"].startswith("same field"):
            s["same_epoch_differs"] += 1
        elif r["verdict"].startswith("encoding"):
            s["encoding_only"] += 1
        else:
            s["no_derived_line"] += 1
        if not r["line2_field_matches"]:
            s["line2_field_mismatch"] += 1
        if r["in_range"] is False:
            s["out_of_range"] += 1
    s["defects"] = s["invalid_field"] + s["line2_field_mismatch"] + s["out_of_range"]
    return s


def format_result(qname, r):
    extra = []
    if r["decoded"] is not None:
        extra.append(f"decodes {r['decoded']}" + ("" if r["in_range"] else " OUT OF QUERIED RANGE"))
    if r["columns_l1"] or r["columns_l2"]:
        extra.append(f"line 1 differs at columns {r['columns_l1'] or 'none'}; line 2 at {r['columns_l2'] or 'none'}")
    if r["intl_designator_matches"] is not None:
        extra.append(f"intl designator {'matches' if r['intl_designator_matches'] else 'DIFFERS'}")
    if r["inclination_within_0_05"] is not None:
        extra.append(f"inclination {'within' if r['inclination_within_0_05'] else 'NOT within'} 0.05 deg")
    if not r["line2_field_matches"]:
        extra.append("LINE 2 CATALOG FIELD DIFFERS FROM LINE 1")
    return f"{qname:28s} {r['field']:6s} {r['verdict']}" + (f" [{'; '.join(extra)}]" if extra else "")


def output_dir_ok(out_dir, repo_root):
    """False if the output directory is (or would be) inside the repository."""
    out = os.path.realpath(os.path.expanduser(out_dir))
    repo = os.path.realpath(repo_root)
    return not (out == repo or out.startswith(repo + os.sep))


# --------------------------------------------------------------------------- network (never exercised by tests)
def main():
    if not output_dir_ok(OUT_DIR, REPO):
        print(f"refusing to run: the output directory {OUT_DIR} resolves inside this repository", file=sys.stderr)
        return 5
    derived = load_derived()
    if not derived:
        print("no derived lines found under derived/alpha5-tle/", file=sys.stderr)
        return 4
    print(f"derived Alpha-5 lines indexed: {sum(len(v) for v in derived.values())} in {len(derived)} catalog fields")
    print("Space-Track credentials are used for this session only; they are not stored, logged or echoed.")
    try:
        user = input("Space-Track username (e-mail): ").strip()
        pw = getpass.getpass("Space-Track password: ")
    except (EOFError, KeyboardInterrupt):
        print("\naborted", file=sys.stderr)
        return 1
    if not user or not pw:
        print("username and password are required", file=sys.stderr)
        return 1
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", "gp-omm-conformance verify_against_spacetrack (four queries, one session)")]
    os.makedirs(OUT_DIR, exist_ok=True)
    run = {"started_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "queries": []}
    # login
    try:
        body = urllib.parse.urlencode({"identity": user, "password": pw}).encode()
        with opener.open(urllib.request.Request(LOGIN, data=body), timeout=TIMEOUT) as resp:
            status, text = resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        print(f"login failed: HTTP {e.code}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError) as e:
        print(f"login failed: network error ({type(e).__name__})", file=sys.stderr)
        return 1
    finally:
        pw = None  # drop the reference as early as possible
    if status != 200 or "Failed" in text or not list(jar):
        print("login failed: Space-Track did not accept the credentials or set no session cookie", file=sys.stderr)
        return 1
    print("logged in")
    results_all = []
    rc = 0
    try:
        for i, (qname, path, id_range) in enumerate(QUERIES):
            if i:
                time.sleep(PAUSE_SECONDS)
            url = BASE + path
            try:
                with opener.open(url, timeout=TIMEOUT) as resp:
                    status, raw = resp.status, resp.read()
            except urllib.error.HTTPError as e:
                print(f"{qname}: HTTP {e.code} -- stopping", file=sys.stderr)
                return 2
            except (urllib.error.URLError, OSError) as e:
                print(f"{qname}: network error ({type(e).__name__}) -- stopping", file=sys.stderr)
                return 2
            out_path = os.path.join(OUT_DIR, qname + ".tle")
            with open(out_path, "wb") as f:
                f.write(raw)
            run["queries"].append({"name": qname, "url": url, "http_status": status, "bytes": len(raw),
                                   "saved_to": out_path, "utc": dt.datetime.now(dt.timezone.utc).isoformat()})
            pairs = parse_tle_pairs(raw.decode("utf-8", "replace"))
            if not pairs:
                print(f"{qname}: HTTP {status}, no TLE records returned (empty result or unexpected body; saved for inspection)", file=sys.stderr)
                rc = max(rc, 3)
                continue
            results = [compare_record(l1, l2, derived, id_range) for l1, l2 in pairs]
            results_all += results
            for r in results:
                print(format_result(qname, r))
    finally:
        time.sleep(PAUSE_SECONDS)
        try:
            opener.open(LOGOUT, timeout=TIMEOUT).read()
            print("logged out")
        except Exception:
            print("logout request failed (session will expire on its own)")
        run["finished_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        with open(os.path.join(OUT_DIR, "run.json"), "w") as f:
            json.dump(run, f, indent=1)
    s = summarize(results_all)
    print("\nsummary: " + ", ".join(f"{k} {v}" for k, v in s.items()))
    print(f"responses saved under {OUT_DIR} (not part of the repository; do not commit them)")
    if s["defects"]:
        return 4
    return rc


if __name__ == "__main__":
    sys.exit(main())
