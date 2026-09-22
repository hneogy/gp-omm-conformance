#!/usr/bin/env python3
"""
tools/make_manifest.py -- build manifest.json, MANIFEST.md and fixtures/<case>/case.md from
tools/cases.py and the generated fixtures/<case>/expected.json files. Offline.

The manifest is the machine-readable index of the corpus: every case, what it tests, which
checks apply, per-case coverage and gaps, every source with tier, URL, retrieval time and
SHA-256, and every ambiguity by id. Nothing in it is computed from network access.
"""
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cases import CASES, CHECKS, AMBIGUITIES  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
CORPUS_VERSION = "0.2.0"

INTERPRETATION = {
    "epoch-year-19xx": "A parser must turn epoch field 98324.28472222 into 1998-11-20T06:49:59.999808 (not 2098) and must read a negative first derivative, a non-zero second derivative and a zero BSTAR written 00000+0. All seven renderings must yield the same record. A failure on this case alone usually means a two-digit-year pivot bug or an implied-decimal sign bug.",
    "baseline-iss-five-formats": "A live snapshot of one well-known object. If your fetched bytes match the recorded SHA-256, the exact values apply; otherwise the structural checks apply (seven renderings agree, TLE checksums valid, CSV/JSON defaults). Do not expect the TLE eccentricity and BSTAR to equal the OMM values digit for digit; see tle-vs-omm-precision-loss.",
    "six-digit-omm-saramago": "The first six-digit object. A parser must accept NORAD_CAT_ID 100000 in every OMM format and must treat the TLE request's HTTP 404 'No GP data found' as 'this object cannot be rendered as a TLE', not as an outage. The stable gp-first record has frozen expected values.",
    "tle-omits-six-digit-objects": "A group whose members are all six-digit. The OMM formats return every record; the TLE request returns nothing (HTTP 404). A pipeline that treats a 404 or an empty TLE file as 'no new data' silently loses every object launched after 2026-07-11. When objects below 100000 are in the window again the TLE response holds exactly those; the count check covers both states.",
    "analyst-objects": "Analyst objects carry an empty OBJECT_ID in every format (empty string, or an empty XML element that Python's ElementTree returns as None) and the literal OBJECT_NAME 'UNKNOWN' (all 565 records at the snapshot; the CCSDS-recommended value). Parsers must not crash, must not invent a designator or a name, and must keep six-digit ids 270000-270449 that the TLE rendering drops. Analyst numbers are reused, so identity is per snapshot.",
    "nine-digit-supgp-launch-nominals": "Nine-digit ids exist today only in CelesTrak SupGP launch nominals, for roughly a week after a launch. A parser must accept 799501621 as an integer in CSV/JSON/XML/KVN; the TLE format cannot carry it. python-sgp4 2.27 (and Skyfield through it) raise ValueError on these records because they store the catalog number as an Alpha-5 string. If your fetch finds no nine-digit ids, the case reports that state instead of failing.",
    "supgp-celestrak-classification-c": "CelesTrak supplemental records differ from 18 SDS GP records: CLASSIFICATION_TYPE C, ELEMENT_SET_NO 0, extra RMS and DATA_SOURCE columns, 72000-series ids (the use of the 70000-79999 block is described only by a secondary source), and a TLE epoch rounded to the TLE's 864 microsecond resolution. Parsers that hard-code 'U', reject unknown columns, or compare epochs exactly will fail.",
    "bstar-and-derivative-forms": "Drag-term encodings: negative BSTAR and first derivative, non-zero second derivative, implied-decimal exponent fields. A parser must read ' 51949-2' as 0.51949e-2 and '-70517-5' as -0.70517e-5. No record with a positive exponent (>= 1.0) exists in the data; that encoding is untested here.",
    "satcat-70000-cutoff": "The legacy fixed-width SATCAT stops at id 69999 by design; the CSV/JSON SATCAT continues past 100000. Software reading the legacy file will never see new objects. The expected values include the parsed legacy lines for 25544 and 69999 and the JSON/CSV records for 25544, 69999 and 100000.",
    "csv-json-omitted-mandatory-fields": "CelesTrak CSV and JSON omit CENTER_NAME, REF_FRAME, TIME_SYSTEM and MEAN_ELEMENT_THEORY (constant for SGP4 data) and the header keywords. A parser that requires every CCSDS-mandatory keyword must default them (EARTH, TEME, UTC, SGP4) rather than reject the file. SupGP files add RMS and DATA_SOURCE, which must be ignored, not rejected.",
    "mean-motion-derivative-convention": "In 304 of 304 pairs the OMM MEAN_MOTION_DOT equals the TLE first-derivative field as printed, i.e. the OMM carries the TLE convention (ndot/2, nddot/6). A parser that treats the OMM value as the true derivative is off by a factor of 2 (and 6). The standard leaves this open (4.2.4.7 NOTE 2); this case records what the provider does.",
    "tle-vs-omm-precision-loss": "The CelesTrak TLE is a lossy rendering of the OMM record: eccentricity truncated to 7 digits (304/304, never rounded), BSTAR and second derivative rounded half up to a 5-digit mantissa (304/304), SupGP epochs quantised to 1e-8 day. Space-Track's own TLE lines for the same records round the eccentricity and write a zero second derivative with the opposite exponent sign (D-070), so these rules describe CelesTrak's rendering specifically. Line 0 is limited to 24 characters by the CelesTrak format document, but no provider record in the 304 pairs has a longer name, so truncation is not an observed rule here (it occurs only in one derived line). Consequences: OMM -> TLE -> OMM does not round-trip; TLE -> OMM -> TLE does, verified byte for byte by tests/test_roundtrip.py over every CelesTrak TLE record in the corpus. Tests that compare a TLE to an OMM must apply exactly these rules, not a generic tolerance.",
    "omm-xml-schema": "CelesTrak XML is valid NDM/XML 2.0 (schema set ndmxml-2.0.0, whose epoch pattern even accepts the empty CREATION_DATE) and invalid against the current 4.0.0/OMM 3.0 set solely because of the fixed version attribute. A validator pinned to the current schema rejects every CelesTrak file; a validator that follows the declared schemaLocation accepts them, but only as long as SANA keeps serving the 2.0.0 files at those direct URLs (the registry page no longer lists them; they resolved on 2026-09-21). The vendored copies under schemas/ remove that dependency for offline validation.",
    "alpha5-encoding-vectors": "Pure mapping vectors: the six official Space-Track examples, every letter boundary, both skips (H->J, N->P), five-digit values with leading zeros, invalid letters (I, O), lowercase, and unencodable integers. A decoder that maps letters by ord() without skipping I and O is wrong from 180000 upward.",
    "alpha5-tle-derived": "Derived, not provider output: real CelesTrak OMM records rendered into TLE layout with the Alpha-5 catalog field, using a renderer that reproduces all 304 CelesTrak TLE lines byte for byte. Only letters A (ids 100000-100789) and T (270000-270449) occur in real catalog numbers today; other letters are covered by vectors only. python-sgp4 2.27 decodes all 604 lines correctly, and the owner's Space-Track check (D-070, 44 records, 0 defects) found the same encoding for both letters; expect Space-Track's own lines to differ from these in the zero second-derivative sign and the last eccentricity digits, which are rendering conventions, not encoding.",
    "kvn-syntax-variants": "Six CCSDS-legal renderings of one record that CelesTrak never emits: day-of-year epoch with Z, bracketed units, comments and blank lines and odd whitespace with LF endings, an OMM 3.0 header with the optional TLE parameters omitted, signed integers and a lowercase exponent. Every variant must parse to the same orbital values as the base record. The naive adapter (tests/adapters/naive.py) fails four of the six: v02 (day-of-year epoch with Z), v03 (bracketed units), v04 (COMMENT lines and irregular whitespace) and v05 (optional keywords omitted); it passes v01 and v06.",
    "tle-writer-alpha5": "The writer-side mirror of the corpus. Each input record is handed to the adapter's write_tle hook (or to --write-cmd) and the lines it returns are checked: columns 3-7 must carry five digits below 100000 and Alpha-5 from 100000 (A0000 ... Z9999) on both lines; both lines must be 69 characters with a valid checksum (a letter counts 0); read back through the corpus reference reader, the element fields must equal the input at the field's resolution, by truncation or by rounding half up (CelesTrak truncates the eccentricity, Space-Track rounds it; both are accepted and the convention seen is reported). Three inputs carry numbers the TLE catalog field cannot represent (340000, 799501621, -1): the correct output for them is a refusal, an error and no lines, because those numbers belong in the OMM formats; tle-writer-refuses-unencodable passes on a refusal and fails when lines are written with a six-digit, blank or otherwise invalid field. Fields a fitting tool regenerates (first and second derivative, element set, revolution, classification, designator, name) and the exponent sign written for a zero second derivative are reported for information only. A writer that formats the catalog number with an integer conversion (%05d) fails on every Alpha-5 input: six digits, a 70-character line and a checksum over shifted columns. A file written by a tool that cannot be wrapped by an adapter is checked with python -m gpconf check-tle FILE [--against RECORDS], which applies the same format checks to every record in the file and the round trip when the source records are supplied.",
}

LIBRARY_FINDINGS = {
    "nine-digit-supgp-launch-nominals": ["python-sgp4 2.27 sgp4.omm.initialize and Skyfield 1.55 EarthSatellite.from_omm raise ValueError('satellite number cannot exceed 339999') for every nine-digit record: 28 distinct records (27 in the full Starlink SupGP file plus one single-object query), 29 file-records counting that object's CSV and XML renderings separately."],
    "analyst-objects": ["python-sgp4 2.27 sgp4.omm.parse_xml returns None for an empty <OBJECT_ID/> element and initialize() then raises TypeError; 564 of 566 XML analyst records fail, while the same records in CSV pass."],
    "tle-vs-omm-precision-loss": ["python-sgp4 2.27 export_tle writes a zero second derivative as ' 00000-0', matching Space-Track's rendering; CelesTrak writes ' 00000+0', so a byte-exact round trip of a CelesTrak line succeeds only when the second derivative is non-zero. The values are identical; this is a provider divergence (D-072), not a library defect."],
    "alpha5-tle-derived": ["python-sgp4 2.27 twoline2rv decodes all 604 derived Alpha-5 lines to the correct integer (from_alpha5)."],
    "alpha5-encoding-vectors": ["python-sgp4 2.27 sgp4.alpha5.from_alpha5 is lenient: it accepts I0000 (as 180000), O1234, lowercase and four-character fields that the Space-Track definition excludes; to_alpha5(-1) returns '-0001'."],
    "supgp-celestrak-classification-c": ["python-sgp4 2.27 sgp4.omm.initialize assigns CLASSIFICATION_TYPE and then calls sgp4init, which resets classification to 'U'; SupGP records with classification 'C' come back as 'U' (twoline2rv preserves it)."],
    "tle-writer-alpha5": [
        "python-sgp4 2.27, exporter.export_tle after omm.initialize (tests/adapters/sgp4_adapter.py, run 2026-09-22): passes every real record, 606 of 606 (valid 69-character lines with correct checksums, correct Alpha-5 fields A0000 ... T0449, round trip at the field resolution), preserves the first derivative, rounds the eccentricity (Space-Track style) and writes a zero second derivative as 00000-0. It refuses both real-range unrepresentable ids, 340000 and 799501621, in omm.initialize (ValueError: satellite number cannot exceed 339999), the correct output. Its only failing input is the synthetic -1 vector: to_alpha5 has no lower bound (as alpha5-encoding-vectors already records) and the library writes a line with the field -0001. The case status 'fail (1 fail)' in docs/FAILURES.md refers to that single synthetic input and to nothing else.",
        "strf (rffit, upstream HEAD 92d2425 of 2026-03-06): format_tle (rffit.c lines 111-149) writes the catalog field through number_to_alpha5 (satutl.c lines 45-58). Exercised at function level only, in an isolated scratch build outside this repository (the rffit binary needs PGPLOT, X11 and GSL and was not built; nothing was installed), it encodes 100000-339999 correctly (A0000; J0000 after the I skip; P0000 after the O skip; T0449; Z9999) and produces 69-character lines with valid checksums for real records; it rounds the eccentricity and the BSTAR mantissa and zeroes the first derivative, the element set and the revolution number. For 340000 and above, and for nine-digit numbers, the helper returns an empty string and the lines carry five blank characters in columns 3-7, still 69 characters with a valid checksum; that path is reachable only through rffit's interactive Satellite ID entry (rffit.c line 769), never from a loaded catalog, whose decoder cannot exceed 339999. No adapter exists: rffit is an interactive X11 program with no non-interactive write path (DECISIONS D-097).",
    ],
}


def load_expected(case_id):
    p = os.path.join(ROOT, "fixtures", case_id, "expected.json")
    return json.load(open(p)) if os.path.exists(p) else None


def main():
    manifest = {
        "corpus": "gp-omm-conformance", "corpus_version": CORPUS_VERSION, "generated_at": NOW, "generator": "tools/make_manifest.py",
        "design": {
            "raw_provider_files_shipped": False,
            "what_is_shipped": ["specification vectors (vectors/)", "derived, labelled re-encodings of provider records (derived/)", "expected values and structural checks per case (fixtures/<case>/expected.json)", "SHA-256, URL and retrieval time of every source file tested", "the fetch script and static fetch list that rebuild fixtures/<case>/raw/ on the user's machine under CelesTrak's own usage policy (tools/fetch.py, tools/fetchlist.json)"],
            "tiers": {"stable": "source whose bytes should not change (gp-first.php first records, derived files, vectors): if the user's fetched bytes match the recorded SHA-256 the frozen expected values apply exactly", "live": "rolling or current query: our snapshot's values are a dated reference; structural checks apply to whatever the user fetched"},
            "provider_policy": {"celestrak_gp_update_cadence_hours": 2, "one_request_per_url_per_update": True, "policy_url": "https://celestrak.org/usage-policy.php", "documentation_url": "https://celestrak.org/NORAD/documentation/gp-data-formats.php"},
            "audit_trail": "DECISIONS.md",
        },
        "checks": CHECKS, "ambiguities": AMBIGUITIES, "cases": [],
    }
    md = [f"# Corpus manifest ({CORPUS_VERSION})", "", f"Generated {NOW} by `tools/make_manifest.py`. Machine-readable form: `manifest.json`. Decisions and reversals: `DECISIONS.md`.", "",
          "No raw provider files are shipped. Each case lists the exact source URLs, retrieval times and SHA-256 hashes of the files we tested; `tools/fetch.py` rebuilds them on your machine under CelesTrak's usage policy (each URL once, cached, never looped).", "",
          "| # | case | kind | records | sources (stable/live) | coverage gaps |", "|---|---|---|---|---|---|"]
    details = []
    for i, c in enumerate(CASES, 1):
        e = load_expected(c["id"])
        srcs = e["sources"] if e else {}
        stable = sum(1 for s in srcs.values() if s.get("tier") == "stable")
        live = sum(1 for s in srcs.values() if s.get("tier") == "live")
        entry = {"id": c["id"], "title": c["title"], "kind": c["kind"], "tests": c["tests"], "checks": c["checks"], "evidence_basis": c.get("evidence_basis", []),
                 "coverage": c["coverage"], "ambiguities": c["ambiguities"],
                 "library_findings": LIBRARY_FINDINGS.get(c["id"], []),
                 "expected": f"fixtures/{c['id']}/expected.json", "case_doc": f"fixtures/{c['id']}/case.md",
                 "record_count": len(e["records"]) if e else None,
                 "sources": [{"path": p, **{k: v for k, v in s.items() if k in ("tier", "format", "url", "retrieved_at", "http_status", "bytes", "sha256", "provenance", "record_count", "recapture_of", "superseded_for_citation_by", "provenance_file")}} for p, s in srcs.items()]}
        manifest["cases"].append(entry)
        md.append(f"| {i} | `{c['id']}` | {c['kind']} | {entry['record_count']} | {stable}/{live} | {len(c['coverage']['gaps'])} |")
        # case.md
        doc = [f"# {c['id']}", "", c["title"], ""]
        if c.get("evidence_basis"):
            doc += ["## Evidence basis", ""] + [f"- {x}" for x in c["evidence_basis"]] + [""]
        doc += ["## What it tests", ""] + [f"- {t}" for t in c["tests"]] + ["", "## How to read a failure", "", INTERPRETATION.get(c["id"], ""), "", "## Checks", ""]
        doc += [f"- **{k}** — {CHECKS[k]}" for k in c["checks"]]
        doc += ["", "## Coverage", "", "Provides:", ""] + [f"- {x}" for x in c["coverage"]["provides"]] + ["", "Gaps (stated explicitly for this case):", ""] + ([f"- {x}" for x in c["coverage"]["gaps"]] or ["- none identified"])
        if LIBRARY_FINDINGS.get(c["id"]):
            heading = "## Library behaviour observed" + ("" if c["kind"] == "writer" else " (docs/CROSSCHECK.md)")
            doc += ["", heading, ""] + [f"- {x}" for x in LIBRARY_FINDINGS[c["id"]]]
        doc += ["", "## Ambiguities recorded", ""] + ([f"- **{a}** — {AMBIGUITIES[a]}" for a in c["ambiguities"]] or ["- none"])
        doc += ["", "## Sources", "", "| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |", "|---|---|---|---|---|---|"]
        for p, s in srcs.items():
            doc.append(f"| `{p}` | {s.get('tier')} | {s.get('http_status')} | {s.get('bytes')} | {s.get('retrieved_at')} | `{(s.get('sha256') or '')[:16]}…` |")
        urls = sorted({s["url"] for s in srcs.values() if s.get("url")})
        if urls:
            doc += ["", "URLs (each requested once when the fixtures were built):", ""] + [f"- <{u}>" for u in urls]
        doc += ["", f"Expected values: `fixtures/{c['id']}/expected.json` (schema_version 1.0)."]
        open(os.path.join(ROOT, "fixtures", c["id"], "case.md"), "w").write("\n".join(doc) + "\n")
        details += [f"## {i}. `{c['id']}`", "", c["title"], "", f"Tests: {', '.join(c['tests'])}", "", "Coverage gaps:", ""] + ([f"- {x}" for x in c["coverage"]["gaps"]] or ["- none identified"]) + [""]
    md += [""] + details + ["## Checks", ""] + [f"- **{k}** — {v}" for k, v in CHECKS.items()] + ["", "## Ambiguities", ""] + [f"- **{k}** — {v}" for k, v in AMBIGUITIES.items()]
    json.dump(manifest, open(os.path.join(ROOT, "manifest.json"), "w"), indent=1)
    open(os.path.join(ROOT, "MANIFEST.md"), "w").write("\n".join(md) + "\n")
    print(f"manifest: {len(manifest['cases'])} cases, {sum(len(c['sources']) for c in manifest['cases'])} source entries; case.md written for each")


if __name__ == "__main__":
    main()
