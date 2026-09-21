# Plan: GP/OMM conformance test corpus

Status: **Phase 1 deliverable — awaiting review.** No code written, no GP data fetched.
Companion document: `RESEARCH.md` (sources and verbatim quotes; everything below cites it).

## 0. Three findings that change the brief

**A. CelesTrak does not emit Alpha-5.** Its TLE/3LE/2LE output silently omits every object
with a catalog number >= 100000 (RESEARCH §2.2). Real Alpha-5 element sets exist only on
Space-Track, behind a login, via the GP class with `format/tle` (RESEARCH §4). So the
"Alpha-5 across the range" coverage cannot come from CelesTrak, and the corpus has to
distinguish three kinds of Alpha-5 artefact:

1. **Encoding vectors** — the six official Space-Track examples plus the full letter table.
   Pure integer<->string pairs, provenance = specification. No element sets involved.
2. **Real Alpha-5 TLEs** — only from Space-Track. Needs either your credentials or a file
   you download yourself and drop into the corpus (I would record the query URL and your
   retrieval timestamp).
3. **The CelesTrak omission behaviour itself** — the same group requested as CSV and as TLE,
   with the expected outcome that the TLE response has fewer records and that every missing
   record has a 6-digit number. This is real data and a real migration hazard (a pipeline
   that "still works" but has quietly lost objects).

Without Space-Track access, the only way to get an Alpha-5 *TLE line* is to re-encode a real
CelesTrak OMM record for a 100000+ object into TLE layout. That is a deterministic
transformation of real data, not invention, but it is not a byte-for-byte artefact from a
provider. **I will not do this unless you say so**, and if you do it will be marked
`provenance: derived` with the generating script committed.

**B. Nine-digit numbers.** No cataloged object has one (the catalog is at ~100789).
CelesTrak's own FAQ says its supplemental GP data for recent Starlink / Transporter /
Bandwagon launches uses 18 SDS 9-digit launch-nominal numbers in the 799xxxxxx range
(RESEARCH §2.3). A Starlink G15-27 post-deployment SupGP file exists as of today
(launch 2026-09-20 01:47 UTC). That is real, provider-issued 9-digit data, but it is
short-lived: nominals are replaced when the objects are cataloged. If, when Phase 2 runs,
no SupGP file carries 9-digit numbers, the choices are (a) a clearly labelled
`synthetic-derived` record (real record, NORAD_CAT_ID rewritten) or (b) no 9-digit element
set, only the CCSDS "integer of up to nine digits" rule as a schema/regex case. I recommend
(b) unless you prefer (a).

**C. OMM version mismatch.** CelesTrak states it emits OMM **2.0** XML; the current CCSDS
standard and the only publicly downloadable SANA schema fix `version="3.0"`; the 2.0 schema
archive is behind a CCSDS SharePoint login (RESEARCH §2.5, §6). Schema validation of
CelesTrak XML will therefore be reported in two parts: structural validity against the 3.0
schema with the version attribute masked, and the version string itself. Recorded as an
ambiguity in the manifest, not silently resolved.

Two further spec-vs-practice divergences to record rather than resolve:

- CCSDS says unknown OBJECT_NAME / OBJECT_ID "should be set to UNKNOWN" and KVN mandatory
  keywords need a non-empty value (7.5.1); CelesTrak emits blank (KVN) / null (XML) / omitted
  (JSON, CSV) for analyst objects (RESEARCH §2.4, §5.3, §5.5).
- CCSDS is silent on whether MEAN_MOTION_DOT / DDOT carry the TLE field value (ndot/2,
  nddot/6) or the true derivative; practice is the TLE field value (RESEARCH §5.4). Will be
  confirmed empirically from a same-object TLE/OMM pair and documented.

## 1. Deliverable and non-goals

Deliverable: a versioned, MIT-licensed directory of real fixtures plus expected parsed
values, a machine-readable manifest, and a small stdlib-only Python runner that can drive
either a Python callable or an external command. Language-agnostic: the fixtures and
`expected.json` are the product; the runner is a convenience.

Non-goals: a parser library, a propagator, any Space-Track client with stored credentials,
anything that fetches on a schedule.

## 2. Repository layout

```
gp-omm-conformance/
├── LICENSE                     MIT
├── README.md                   migration explainer + how to run
├── manifest.json               every case: id, tests, files, provenance, ambiguities
├── MANIFEST.md                 generated human-readable view of manifest.json
├── fixtures/
│   └── <case-id>/
│       ├── raw/                exact bytes as received, one file per format
│       │   ├── <name>.<ext>
│       │   └── <name>.<ext>.meta.json   url, retrieved_at (UTC), status, headers subset, sha256, bytes
│       ├── expected.json       canonical parsed values for every record in raw/
│       └── case.md             what this case tests, how to interpret failures
├── schemas/                    vendored SANA XSDs + SOURCE.md (URLs, dates)
├── vectors/                    non-element-set test vectors (Alpha-5 table, epoch pivots)
├── gpconf/                     runner package (stdlib only)
├── tools/                      fetch.py (cached, rate-aware), make_expected.py, crosscheck.py
├── tests/                      runner self-tests using reference adapters
└── docs/                       PLAN.md, RESEARCH.md, later FAILURES.md
```

### 2.1 Provenance model (in every `.meta.json` and in the manifest)

| provenance | meaning |
|---|---|
| `live` | bytes exactly as served by the named URL at `retrieved_at` |
| `excerpt` | contiguous lines/records copied verbatim from a `live` file that is too large to vendor whole (the full file's sha256 and size are recorded) |
| `specification` | values transcribed from a standard or provider document (page + section cited) |
| `derived` | produced by a committed script from a `live` file (e.g. re-serialising a CelesTrak record as CCSDS day-of-year KVN); script path + input sha256 recorded |
| `synthetic-derived` | a `live` record with one field deliberately altered to exercise a case no real data covers; only if you approve it |

Nothing without a provenance entry ships.

### 2.2 `expected.json` schema

One object per fixture directory:

```json
{
  "case": "six-digit-omm-saramago",
  "records": [
    {
      "key": "100000",
      "norad_cat_id": 100000,
      "norad_cat_id_tle_field": null,
      "object_name": "SARAMAGO",
      "object_id": "2026-067CY",
      "epoch": "2026-09-19T12:34:56.123456",
      "epoch_year_2digit": null,
      "epoch_day_of_year": null,
      "mean_motion": "15.12345678",
      "eccentricity": "0.0001234",
      "inclination": "97.4321",
      "ra_of_asc_node": "123.4567",
      "arg_of_pericenter": "89.0123",
      "mean_anomaly": "271.0000",
      "bstar": "1.2345e-4",
      "mean_motion_dot": "1.2e-5",
      "mean_motion_ddot": "0",
      "ephemeris_type": 0,
      "classification_type": "U",
      "element_set_no": 999,
      "rev_at_epoch": 1234,
      "center_name": "EARTH",
      "ref_frame": "TEME",
      "time_system": "UTC",
      "mean_element_theory": "SGP4",
      "tle_line1_checksum": null,
      "tle_line2_checksum": null
    }
  ],
  "per_format": {
    "csv":  {"present_keys": [...], "absent_keys": ["CENTER_NAME", "REF_FRAME", "TIME_SYSTEM", "MEAN_ELEMENT_THEORY"]},
    "tle":  {"record_count": 0, "note": "CelesTrak omits objects >= 100000 from TLE output"}
  }
}
```

Conventions:

- **Numbers that were parsed from text are stored as decimal strings**, never as JSON floats,
  so the corpus does not bake in one language's float formatting. The runner compares with
  `decimal.Decimal` equality. Integers (catalog number, element set number, revolution
  number, ephemeris type) are JSON integers.
- `norad_cat_id` is always the integer. `norad_cat_id_tle_field` is the raw 5-character
  field when the source was a TLE (so `"A0000"` or `"00964"`), otherwise null.
- `epoch` is the ISO 8601 calendar form in UTC with microseconds. For TLE sources it is
  computed from the two-digit year and fractional day; the manifest states the pivot rule
  used and the runner allows a tolerance of 1 µs on epoch only, and only when the parser
  under test reports epoch as a datetime rather than a string.
- `mean_motion_dot` / `mean_motion_ddot` are the **values as printed** in the source, in
  rev/day² and rev/day³ (the TLE half / sixth convention). The manifest ambiguity entry
  explains this once.
- `bstar` is in 1/Earth-radii as a decimal string in the source's own notation normalised to
  Decimal canonical form; the raw TLE substring (e.g. `" 12345-4"`) is kept in
  `norad`-style side fields only where the case is specifically about the field encoding.
- Fields a format cannot carry are `null`, not omitted, so a parser cannot pass by
  accident because a key was missing.

### 2.3 `manifest.json` schema

```json
{
  "corpus_version": "0.1.0",
  "generated_at": "2026-09-2xTxx:xx:xxZ",
  "sources": {"celestrak_gp_update_cadence_hours": 2, "policy_url": "..."},
  "cases": [
    {
      "id": "analyst-objects",
      "title": "Analyst objects without OBJECT_NAME / OBJECT_ID, 5- and 6-digit",
      "tests": ["six-digit-id", "missing-object-name", "missing-object-id", "csv-key-omission"],
      "formats": ["csv", "json", "xml", "kvn", "tle"],
      "files": {"csv": "fixtures/analyst-objects/raw/analyst.csv", ...},
      "provenance": "live",
      "source_urls": ["https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=csv", ...],
      "retrieved_at": "...",
      "record_count": {"csv": 123, "tle": 98},
      "required_fields": ["norad_cat_id", "epoch", "mean_motion", ...],
      "ambiguities": [
        {"id": "unknown-vs-blank", "text": "CCSDS 502.0-B-3 Table 4-2 says unknown OBJECT_ID 'should be set to UNKNOWN'; CelesTrak emits blank/null/omitted. The corpus expects the provider's behaviour and records the spec text here."}
      ]
    }
  ]
}
```

Every ambiguity gets an id so a parser author can cite it in an issue or a skip list.

## 3. Case list

Required coverage from your brief is in the "Covers" column. "Source" is the exact query.
Budget column is the one-time download I expect.

| # | Case id | Covers | Source (one request per format) | Formats | Provenance | Risk |
|---|---|---|---|---|---|---|
| 1 | `baseline-iss-five-formats` | same object in all five formats; round-trip; 2-digit year (26); implicit decimals; checksum | `gp.php?CATNR=25544&FORMAT={TLE,2LE,CSV,JSON,JSON-PRETTY,XML,KVN}` | 7 files, ~10 kB | live | none |
| 2 | `six-digit-omm-saramago` | first 6-digit object; all OMM formats; TLE unavailable | `gp.php?CATNR=100000&FORMAT={TLE,CSV,JSON,XML,KVN}` + `satcat/records.php?CATNR=100000&FORMAT={JSON,CSV}` | 7 files | live | TLE request may 404 (counts toward error limit; one request only) |
| 3 | `tle-omits-six-digit-objects` | CSV vs TLE record-count mismatch; every missing id >= 100000 | `gp.php?GROUP=last-30-days&FORMAT={CSV,TLE}` | 2 files, ~100 kB | live | none |
| 4 | `analyst-objects` | no OBJECT_NAME/OBJECT_ID; 8xxxx and 27xxxx ids; KVN blank vs XML null vs JSON/CSV omission | `gp.php?GROUP=analyst&FORMAT={CSV,JSON,XML,KVN,TLE}` | 5 files, size unknown (small) | live | group contents vary; document counts |
| 5 | `nine-digit-supgp-launch-nominals` | 9-digit NORAD_CAT_ID in OMM formats; behaviour of TLE format for them | `sup-gp.php?FILE=starlink-g15-27&FORMAT={CSV,JSON,XML,KVN,TLE}` (or whichever current SupGP file has 799xxxxxx ids) | 5 files | live | **time-sensitive**; may already be replaced by cataloged ids |
| 6 | `alpha5-encoding-vectors` | letter-skip rules across the range; boundaries; invalid letters; lowercase; leading zeros below 100000 | Space-Track documentation table and six examples; boundary values derived arithmetically from the stated rule | `vectors/alpha5.json` | specification | none |
| 7 | `alpha5-tle-real` | real Alpha-5 TLEs across the range | Space-Track `class/gp/NORAD_CAT_ID/100000--339999/format/tle` and `/format/3le` | 2 files | live (yours) | **blocked on your decision** (§6 Q1) |
| 8 | `epoch-year-19xx` | 2-digit year in the 57–99 branch of the pivot | `gp-first.php?CATNR=25544&FORMAT={TLE,JSON}` (first ISS elset, 1998) and `gp-first.php?CATNR=5&FORMAT={TLE,JSON}` (Vanguard 1, 1958, if available) | 4 files | live | gp-first may not go back that far; fall back to whatever oldest record it returns |
| 9 | `bstar-and-derivative-forms` | BSTAR negative / zero / positive-exponent; negative ndot; non-zero nddot; implicit decimals | selected records from cases 1, 3, 4 plus `gp.php?SPECIAL=DECAYING&FORMAT={TLE,CSV}` | 2 new files, small | live (records cited by id from other cases) | positive-exponent BSTAR may not exist today; document absence rather than invent |
| 10 | `satcat-70000-cutoff` | objects on both sides of 70000; legacy file excludes >= 70000 | `satcat/records.php?CATNR={69999,25544,100000,<one 8xxxx>}&FORMAT={JSON,CSV}`; `/pub/satcat.txt` once (HEAD first to log size), vendored as head+tail excerpt with full-file sha256 and computed max id | ~8 small files + 1 excerpt | live / excerpt | 69999 may not exist as an object; then use the largest id below 70000 present |
| 11 | `omm-xml-schema` | XML structure; version attribute 2.0 vs 3.0; `<ndm>` wrapper; units attributes | XML files from cases 1, 2, 4 validated against vendored SANA schemas | none new | live | ambiguity C |
| 12 | `csv-json-omitted-mandatory-fields` | parser must default CENTER_NAME/REF_FRAME/TIME_SYSTEM/MEAN_ELEMENT_THEORY when absent | CSV/JSON from case 1 | none new | live | none |
| 13 | `mean-motion-derivative-convention` | ndot/2, nddot/6 convention across TLE vs OMM for the same object | TLE + CSV from case 1 (and 3) | none new | live | confirm empirically |
| 14 | `kvn-syntax-variants` | CCSDS-legal KVN that CelesTrak does not happen to emit: day-of-year epoch, epoch without fraction, `Z` suffix, `[units]`, extra whitespace, COMMENT lines, blank lines, CRLF | re-serialisation of case 1's KVN by a committed script | 1–2 files | **derived** | only if you accept derived files (§6 Q3) |
| 15 | `parser-breakage-catalogue` | not a fixture: `docs/FAILURES.md` documenting how the naive parser and python-sgp4 `omm.py` fail on cases 2, 4, 5, 14 | — | — | — | Phase 4 |

Approximate total Phase 2 traffic: about 40 requests and well under 15 MB, most of it
`satcat.txt`. Nothing is requested twice. `GROUP=active` and `GROUP=starlink` (the two
groups under the one-download-per-update rule) are not needed and will not be requested.

## 4. Phase 2 — fetch and inventory (next step, after your go-ahead)

1. `git init` the project directory; commit this plan and the research notes.
2. Write `tools/fetch.py`:
   - reads a static fetch list (URL, target path, purpose) — no wildcards, no discovery;
   - refuses to download a URL whose target already exists unless `--force`, and even then
     refuses if the existing file is less than 2 hours old;
   - one request at a time, 2 s spacing, User-Agent identifying the project and a contact;
   - stops the whole run on the first non-200 and prints the body (CelesTrak puts the reason
     in a 403 body);
   - writes `.meta.json` next to each file (URL, UTC timestamp, status, Content-Type,
     Last-Modified/Date headers, sha256, byte count);
   - never retries.
3. `HEAD /pub/satcat.txt` first; if it is over 20 MB, ask you before fetching it.
4. Run the list once. Then run `tools/inventory.py` to produce `docs/INVENTORY.md`: per file,
   record count, id range, count of ids >= 100000, whether OBJECT_NAME/OBJECT_ID are empty
   or absent, XML root element and version attribute, epoch string shape, CREATION_DATE,
   and the smallest/largest BSTAR and their raw TLE text.
5. Stop for your review with the inventory. That review is where we settle the unresolved
   items in RESEARCH §10.

## 5. Phase 3 — fixtures and expected values

- `tools/make_expected.py` produces `expected.json` from the raw files using a
  **column-slicing reference implementation written from the CelesTrak/Space-Track column
  tables** (not from any library), plus a direct field read for CSV/JSON/XML/KVN.
- Independent cross-check in a venv with `sgp4` (`twoline2rv`, `omm.initialize`,
  `export_tle`) and `skyfield` (`EarthSatellite.from_omm`): every expected value must agree
  with at least one, and any disagreement is written into the case's `ambiguities` rather
  than resolved by me.
- For the five-format cases, the expected record is asserted identical across formats
  except for documented representational differences (epoch precision, absent keys).
  Where TLE -> OMM -> TLE is lossy (epoch below the TLE's 8-decimal day, BSTAR mantissa
  digits) the case file says exactly which digits are lossy.
- XML validated with `xmlschema` against the vendored SANA 4.0.0 schema; results recorded in
  the case, version-attribute check separated.
- Manifest generated, `MANIFEST.md` rendered.
- Stop for review.

## 6. Phase 4 — runner, README, licence

- `gpconf.run(parser, cases=None, tolerance=None) -> Report`; `parser(raw: bytes, fmt: str)
  -> list[dict]` using the `expected.json` key names (a subset is allowed; the manifest's
  `required_fields` decide pass/fail for missing keys).
- `python -m gpconf --cmd "mytool --format {fmt}"` pipes the raw bytes to any executable and
  reads JSON lines back, for non-Python parsers.
- Output: per-case pass/fail with a field-level diff; `--json` for CI; non-zero exit on any
  failure; `--list` to print cases and their `tests` tags; `--select tag` to filter.
- Reference adapters in `tests/` for python-sgp4 and Skyfield, and the naive parser from
  Phase 0 of your original outline, so CI demonstrates one green and one red run.
- README: the migration in one page (what changed on 2026-07-11, Alpha-5 vs OMM, what to
  change in a parser), the CelesTrak usage rules we followed and that users must follow if
  they refresh fixtures, how to add a case, corpus versioning policy (fixtures are frozen per
  version; refreshes bump the minor version and never rewrite old fixtures).
- MIT `LICENSE`; `schemas/SOURCE.md` noting the SANA files are CCSDS publications
  redistributed unmodified with their URLs.
- GitHub Actions: run the runner against the reference adapters on push. No network.

## 7. Decisions I need from you before Phase 2

1. **Alpha-5 element sets.** (a) You provide Space-Track access or a downloaded file, (b) I
   re-encode real CelesTrak 6-digit OMM records into Alpha-5 TLE lines marked `derived`, or
   (c) the corpus ships only encoding vectors plus the CelesTrak-omission case. My
   recommendation: (a) if you have an account, else (c) now and (a) later.
2. **Nine-digit fallback** if no SupGP file carries 799xxxxxx ids when I fetch: (a) omit,
   (b) `synthetic-derived` record clearly labelled. Recommendation: (a).
3. **Derived KVN variants** (case 14): acceptable as `derived`, or leave out?
4. **Fetch budget** as listed in §3 (about 40 requests, < 15 MB, once): approved?
5. **Repository**: create it as `Code Files/gp-omm-conformance/` with `git init`, or do you
   want a different location or an existing remote?
6. **Runner Python floor**: 3.9+ with stdlib only (proposal).

## 8. Time-sensitive note

The Starlink G15-27 SupGP file is the only lead on real 9-digit numbers, and launch nominals
are replaced within days of cataloguing. If you approve Phase 2 quickly I will fetch that
file first. If it is gone, I will check the supplemental index for the next launch rather
than poll; there is no polling in any phase.

---

# Phase 2 amendments (2026-09-21)

Written after the fetch and inventory; see `docs/INVENTORY.md` for the numbers and
`DECISIONS.md` D-012 to D-021 for the reasoning. Earlier sections are left as written.

## Changes to the case list

| # | Case id | Change |
|---|---|---|
| 3 | `tle-omits-six-digit-objects` | Stronger than planned: the group is now entirely 6-digit, so the TLE request returns HTTP 404 `No GP data found` (the group disappears, not just some objects). Partial omission is shown by `analyst` (565 → 219) and `DECAYING` (82 → 79). |
| 5 | `nine-digit-supgp-launch-nominals` | Real data obtained: one object (799501621) in CSV/JSON/XML/KVN, TLE 404, plus the full Starlink SupGP CSV with 27 nine-digit ids. **SupGP-sourced, so raw files are gitignored pending the redistribution decision.** |
| 7 | `alpha5-tle-real` | **Removed** (D-001). Replaced by `alpha5-tle-derived`: re-encodings of real CelesTrak records for ids 100000–100789 (letter A) and 270000–270449 (letter T) only (D-016), plus the specification vectors (case 6). |
| 8 | `epoch-year-19xx` | Satisfied by the real first ISS record (1998): two-digit year `98`, negative first derivative, non-zero second derivative, `00000+0` BSTAR, element set 1. No second request needed. |
| 9 | `bstar-and-derivative-forms` | Non-zero second derivative is plentiful (79 decaying, 11 recent, 2 analyst records); negative BSTAR present (7 records); zero BSTAR appears as `00000+0`. **No positive-exponent BSTAR exists in the fetched data**; the case will say so rather than invent one. |
| 10 | `satcat-70000-cutoff` | 69999 exists ("VANGUARD DEB", 1958-002D); legacy file is exactly ids 1..69999. Fixture will be an excerpt plus full-file hash (D-014). |
| 11 | `omm-xml-schema` | CelesTrak XML: `<ndm>` root, `version="2.0"`, schema URL resolves on SANA. Validation will be run against both the 2.0 and current schema sets (D-020). New findings to encode: empty mandatory `CREATION_DATE`/`ORIGINATOR`; `MEAN_ELEMENT_THEORY` `SGP/SGP4` in KVN vs `SGP4` in XML; leading-dot decimals (CCSDS 7.5.6 requires a digit before the point); CRLF line endings. |
| 16 | `supgp-celestrak-classification-c` | **New** (D-018): classification `C`, element set 0, `RMS`/`DATA_SOURCE` columns, 72000-series ids, `OBJECT_ID` shared between stack and per-satellite nominals, TLE epoch rounded to 864 µs resolution. |

## Change to `expected.json` (D-017)

Each record now has a `by_format` block for the fields whose rendering differs between the
TLE and the OMM formats of the same object (eccentricity, BSTAR, and for SupGP the epoch),
with the OMM value as `omm` and the TLE value as `tle`, plus a `lossy_digits` note. Fields
that agree across formats stay at the record level as before.

## Publishability options (not decided; owner's call after the audit)

1. Ask CelesTrak directly whether fixture files may be redistributed with attribution
   (owner-only action: contacting a person).
2. Publish the corpus with `expected.json`, metadata and SHA-256 hashes only, and have
   `tools/fetch.py` recreate `raw/` on the developer's machine. Trade-off: each adopter makes
   ~40 requests / ~12 MB against CelesTrak once, and later fetches will not reproduce the
   frozen bytes (GP data changes every 2 hours), so the hashes become documentation rather
   than a check.
3. Publish raw files on the permissive reading of "freely available". Not recommended under
   CLAUDE.md.

Recommendation: 1, with 2 as the fallback design if no answer comes.

## Phase 2 budget actually used

Data fetches: 41 files, 12.5 MB, every URL once (see INVENTORY.md). Documentation and policy
pages: 12 requests. Non-200 responses from celestrak.org: 5 (RESEARCH §12 fetch log).

---

# Phase 3 design (final, 2026-09-21)

Owner decision after Phase 2: **no raw CelesTrak files are shipped.** This section replaces the
"publishability options" above; it is the design, not a fallback.

## What the public corpus contains

| component | location | provenance | publishable |
|---|---|---|---|
| specification vectors (Alpha-5 table and boundaries, catalog-id text forms, two-digit-year pivot, CCSDS epoch strings) | `vectors/*.json` | specification | yes |
| derived re-encodings of real CelesTrak records, each with a `.provenance.json` (source URL, SHA-256, retrieval time, transform, renderer validation) | `derived/alpha5-tle/`, `derived/kvn-variants/` | derived | yes (labelled DERIVED) |
| expected values and structural checks per case | `fixtures/<case>/expected.json`, `case.md` | analysis of provider data | yes |
| manifest with every source's URL, retrieval time, SHA-256, tier, per-case coverage gaps and ambiguities | `manifest.json`, `MANIFEST.md` | — | yes |
| fetch script and static fetch list that rebuild `fixtures/<case>/raw/` on the user's machine | `tools/fetch.py`, `tools/fetchlist.json` | — | yes |
| vendored SANA schema sets 2.0.0 and 4.0.0 | `schemas/` | CCSDS/SANA publications, unmodified | yes |
| raw CelesTrak responses | `fixtures/<case>/raw/` | live | **no** — rebuilt locally; kept in this private repository for the audit |

## Two tiers, because checksums only prove parity for stable bytes

- **stable** sources (`gp-first.php` first-ever records for 25544, 100000, 270449, 81011, 69999;
  derived files; vectors): a user whose rebuilt file hashes to the recorded SHA-256 gets the
  frozen expected values applied exactly. Stability of `gp-first.php` over time is an
  assumption recorded as ambiguity `gp-first-stability`; the fetch script reports drift.
- **live** sources (`GROUP=`, `SPECIAL=`, current `CATNR=`, SupGP, SATCAT records): the
  snapshot values in `expected.json` are a dated reference; the runner applies the case's
  structural checks (cross-format agreement, count relations, presence rules, 404 semantics) to
  whatever the user fetched and says which tier applied.

## Final case list (16)

| # | case | kind | tier of sources |
|---|---|---|---|
| 1 | `epoch-year-19xx` | gp | stable |
| 2 | `baseline-iss-five-formats` | gp | live |
| 3 | `six-digit-omm-saramago` | gp | stable + live |
| 4 | `tle-omits-six-digit-objects` | gp | live |
| 5 | `analyst-objects` | gp | stable + live |
| 6 | `nine-digit-supgp-launch-nominals` | gp | live (perishable) |
| 7 | `supgp-celestrak-classification-c` | gp | live (perishable) |
| 8 | `bstar-and-derivative-forms` | gp | stable + live |
| 9 | `satcat-70000-cutoff` | satcat | live |
| 10 | `csv-json-omitted-mandatory-fields` | facts | mixed |
| 11 | `mean-motion-derivative-convention` | pairs | mixed |
| 12 | `tle-vs-omm-precision-loss` | pairs | mixed |
| 13 | `omm-xml-schema` | xml | mixed |
| 14 | `alpha5-encoding-vectors` | vectors | stable |
| 15 | `alpha5-tle-derived` | derived | stable |
| 16 | `kvn-syntax-variants` | derived | stable |

`parser-breakage-catalogue` (planned as case 17) is a Phase 4 document, not a fixture.

## `expected.json` (schema_version 1.0)

Per case: `sources` (path → tier, format, URL, retrieval time, HTTP status, bytes, SHA-256,
provenance, reader facts), `sets` (per snapshot: files, record count, metadata by format),
`records` (per object: `canonical` values as plain decimal strings and integers,
`present_in` with OBJECT_NAME/OBJECT_ID presence per file, `by_format.tle` with the fields where
the TLE rendering differs and the raw TLE field substrings, `omm_formats_agree`), `checks`,
`tests`, `coverage` (provides / gaps, per case), `ambiguities` (by id), and `case_specific`
(pairs analyses, SATCAT facts, XML validation, vectors). Records are produced by the reference
readers in `tools/gpref.py` and cross-checked against python-sgp4 and Skyfield
(`docs/CROSSCHECK.md`). No value is a binary float.

## Publication mechanics (Phase 4)

This repository's history contains raw files (Phase 2 commit). The public release is therefore a
**curated export into a fresh repository** from an allowlist (everything in the table above
marked "yes"), never a push of this history. The allowlist and export script are Phase 4 work.

## Phase 3 verification summary

- Renderer: 304/304 CelesTrak TLE records reproduced byte for byte from their OMM records
  (`tools/validate_render.py`), which is what makes the derived Alpha-5 lines trustworthy.
- Cross-format agreement: 0 disagreements among CSV/JSON/XML/KVN across all 16 cases.
- python-sgp4 2.27 agrees with the reference readers on all 1,208 TLE records [corrected from 1,210, D-068] (including 604
  derived Alpha-5 lines) and on every CSV/XML record it can load; it cannot load nine-digit ids
  or XML records with an empty OBJECT_ID, and its `export_tle` differs from CelesTrak only in
  the zero second-derivative sign (`docs/CROSSCHECK.md`).
- XML: 8/8 files valid against ndmxml-2.0.0, 8/8 invalid against ndmxml-4.0.0 on the version
  attribute alone.

## README (Phase 4) — section drafted now

`docs/README-draft-ai-assistance.md` holds the required statement that the corpus was built with
AI assistance under human verification, pointing to `DECISIONS.md` as the audit trail.

---

# Phase 4 (2026-09-21): runner, README, licence, export

Built: `gpconf/` (runner, CLI, external-command adapter; readers moved here from `tools/`),
`tests/` (reference, naive and python-sgp4 adapters; unit tests), `README.md`, `LICENSE`
(MIT with a scope note), `pyproject.toml`, `.github/workflows/ci.yml` (offline),
`docs/FAILURES.md` (breakage catalogue generated from runner reports), `docs/upstream/`
(three requested drafts plus one minor addition), `PUBLIC_ALLOWLIST.txt` and
`tools/export_public.py`, the Space-Track `.gitignore` guard, and the case-document additions
(evidence basis, renderer-validation gap). Decisions D-035 to D-045.

Results: reference adapter 16/16 cases pass; naive adapter fails 13 of 16 (the catalogue);
python-sgp4 adapter fails 6 cases, all traceable to the four documented library behaviours,
and skips KVN. Unit tests pass.

## What remains before publication (owner's steps)

1. Independent audit of this private repository (the audit's findings go into `DECISIONS.md`).
2. Owner's private verification of the Alpha-5 encoder against Space-Track (D-037); the
   public text will describe that verification, not the data.
3. Decide whether the SupGP snapshot values stay in `expected.json` (D-033) and confirm the
   LICENSE copyright line (D-041).
4. File the upstream reports (drafts in `docs/upstream/`).
5. `python3 tools/export_public.py --dest <new-dir>`; `git init` there; publish; set the
   citation URL in the README; tag `0.1.0`.
6. Distribution per the original outline (forums, issue trackers as a test resource, one
   brief e-mail to Dr. Kelso with the corpus): owner-only actions.

## Addendum (2026-09-21, after the Phase 4 review)

Applied: NEOGY LLC copyright and maintainer line (D-047); separate `exact` / `pass-tolerance`
outcomes with bias statistics (D-048); SupGP snapshot values withheld from the public release
with a single scrub definition, export-time scrubbing, catalogue redaction and a leak test
(D-049); export_tle report reproducer replaced by an ordinary five-digit line (D-050);
empty-OBJECT_ID report offers a PR and the verified patch sits in `docs/upstream/patches/`
(D-051). Reference adapter: 16 of 16 exact. Next: independent audit in a fresh session.
