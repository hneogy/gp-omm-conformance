#!/usr/bin/env python3
"""tools/make_recorded.py -- write the one provider response the corpus ships, with its provenance (D-247).

CelesTrak answers a GP query that has nothing to return in the format asked for with HTTP 404 and a 16-byte body,
`No GP data found`. Four entries of the fetch list are TLE requests for objects numbered above 99999, which the TLE
format cannot carry, and each is recorded as answering exactly that. From v0.6.0 a fetch no longer requests them: the
body ships with the corpus, in recorded/, and the fetch writes it where it used to request it.

This is a named exception to D-023, which ships no raw CelesTrak bytes. The body holds no orbital data: no element, no
catalog number, nothing that could stand in for a fetch. No other provider response is shipped, and this tool refuses
to write anything that is not that body.

It runs on the maintainer's copy only, where the captures are: it checks that every capture of the answer holds
exactly these 16 bytes under HTTP 404, and writes

    recorded/celestrak-no-gp-data-found.txt
    recorded/celestrak-no-gp-data-found.provenance.json

Standard library only. It makes no request.
"""
import datetime as dt
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BODY = b"No GP data found"
SHA256 = "000844fd5b7a7b64f14b58cc34f0016ad51b0982b0d38f915986560e4e217683"
OUT = os.path.join("recorded", "celestrak-no-gp-data-found.txt")

# The captures made when the corpus was built, 2026-09-21: the files under fixtures/<case>/raw/ on the maintainer's copy.
CAPTURES = [
    ("six-digit-omm-saramago", "saramago.tle"),
    ("six-digit-omm-saramago", "saramago-first.tle"),
    ("tle-omits-six-digit-objects", "last-30-days.tle"),
    ("tle-omits-six-digit-objects", "last-30-days-recapture.tle"),
    ("analyst-objects", "analyst-270449-first.tle"),
]

# The same four requests as a user's fetch made them at the release of v0.5.1 (D-235): the maintainer's timed
# first-time fetch of 2026-10-04, from a clean install. Each answered HTTP 404 with the same 16 bytes.
RECEIVED_AGAIN = [
    ("https://celestrak.org/NORAD/elements/gp.php?CATNR=100000&FORMAT=TLE", "2026-10-04T03:25:04Z"),
    ("https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=TLE", "2026-10-04T03:25:14Z"),
    ("https://celestrak.org/NORAD/elements/gp-first.php?CATNR=100000&FORMAT=TLE", "2026-10-04T03:26:08Z"),
    ("https://celestrak.org/NORAD/elements/gp-first.php?CATNR=270449&FORMAT=TLE", "2026-10-04T03:26:20Z"),
]


def main():
    with open(os.path.join(ROOT, "tools", "fetchlist.json"), encoding="utf-8") as f:
        fetchlist = json.load(f)
    written_for = sorted(f"fixtures/{e['case']}/raw/{e['file']}" for e in fetchlist if e.get("recorded") == OUT.replace(os.sep, "/"))
    captures = []
    for case, name in CAPTURES:
        path = os.path.join(ROOT, "fixtures", case, "raw", name)
        if not os.path.exists(path):
            print(f"make_recorded: {path} is not on disk; this tool runs on the maintainer's copy, where the captures are", file=sys.stderr)
            return 1
        raw = open(path, "rb").read()
        meta = json.load(open(path + ".meta.json", encoding="utf-8"))
        if raw != BODY or hashlib.sha256(raw).hexdigest() != SHA256 or meta.get("http_status") != 404:
            print(f"make_recorded: {path} is not the 16-byte answer with HTTP 404; nothing written", file=sys.stderr)
            return 1
        entry = {"file": f"fixtures/{case}/raw/{name}", "url": meta["url"], "retrieved_at": meta["retrieved_at"],
                 "http_status": meta["http_status"], "bytes": len(raw), "sha256": SHA256}
        if "reconstructed" in (meta.get("note") or "").lower():
            entry["note"] = ("the fetch tool discarded this body at the time, and it was written back by hand from the tool's log (D-013); "
                             "last-30-days-recapture.tle is the same endpoint captured cleanly 31 minutes later (D-022)")
        captures.append(entry)
    os.makedirs(os.path.join(ROOT, "recorded"), exist_ok=True)
    with open(os.path.join(ROOT, OUT), "wb") as f:
        f.write(BODY)
    provenance = {
        "file": OUT.replace(os.sep, "/"),
        "what": ("CelesTrak's answer to a GP query with nothing to return in the format asked for: HTTP 404 with this body. "
                 "Here, to TLE requests for objects numbered above 99999, which the TLE format cannot carry."),
        "text": BODY.decode("ascii"), "bytes": len(BODY), "sha256": SHA256, "http_status": 404,
        "holds_orbital_data": False,
        "exception": ("The one provider response shipped with the corpus: a named exception to D-023, which ships no raw CelesTrak "
                      "bytes (DECISIONS.md, D-247). No other provider response is shipped."),
        "licence": "CelesTrak's text, reproduced as recorded. The corpus's MIT licence does not cover it (NOTICE).",
        "how_it_is_used": ("gpconf fetch writes this body to each path of written_by_the_fetch_as, with metadata that says it was "
                           "written from this record, and requests none of those URLs. The runner hands it to the parser under test "
                           "(check empty-answer-yields-no-records)."),
        "written_by_the_fetch_as": written_for,
        "captures": captures,
        "received_again": [{"url": url, "retrieved_at": when, "http_status": 404, "bytes": len(BODY), "sha256": SHA256} for url, when in RECEIVED_AGAIN],
        "received_again_by": "the maintainer's first-time fetch at the release of v0.5.1, from a clean install (DECISIONS.md, D-235)",
        "generator": "tools/make_recorded.py",
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open(os.path.join(ROOT, os.path.splitext(OUT)[0] + ".provenance.json"), "w", encoding="utf-8") as f:
        json.dump(provenance, f, indent=1)
        f.write("\n")
    print(f"recorded: {OUT} ({len(BODY)} bytes, sha256 {SHA256[:16]}...), {len(captures)} captures, "
          f"{len(RECEIVED_AGAIN)} later answers, written by the fetch as {len(written_for)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
