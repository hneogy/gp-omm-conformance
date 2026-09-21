# epoch-year-19xx

ISS first GP record (1998): two-digit epoch year 98, seven renderings of one record

## What it tests

- 2-digit-epoch-year
- same-object-all-formats
- bstar-implicit-decimal
- negative-ndot
- nonzero-nddot

## How to read a failure

A parser must turn epoch field 98324.28472222 into 1998-11-20T06:49:59.999808 (not 2098) and must read a negative first derivative, a non-zero second derivative and a zero BSTAR written 00000+0. All seven renderings must yield the same record. A failure on this case alone usually means a two-digit-year pivot bug or an implied-decimal sign bug.

## Checks

- **omm-formats-agree** — For the same object and snapshot, CSV, JSON, XML and KVN yield identical canonical values for every OMM keyword present in all of them.
- **tle-values-match-omm-within-tle-precision** — The TLE rendering equals the OMM values except: eccentricity truncated to 7 digits, BSTAR and second derivative rounded (half up) to a 5-digit mantissa, epoch at 1e-8 day resolution.
- **tle-checksums-valid** — Every TLE line 1 and line 2 is 69 characters and ends with the modulo-10 checksum (digits count their value, '-' counts 1, everything else 0).
- **two-digit-year-pivot** — TLE epoch years 57-99 map to 1957-1999 and 00-56 to 2000-2056; the resulting ISO epoch equals the OMM EPOCH string.
- **csv-json-omit-constant-metadata** — CelesTrak CSV/JSON carry no CENTER_NAME, REF_FRAME, TIME_SYSTEM or MEAN_ELEMENT_THEORY; parsers must default them (EARTH, TEME, UTC, SGP4) rather than fail.
- **xml-ndm-wrapper-omm-2.0** — CelesTrak XML has an <ndm> root containing one <omm> per record with id=CCSDS_OMM_VERS and version=2.0; CREATION_DATE and ORIGINATOR elements are present but empty.
- **kvn-blank-mandatory-values** — CelesTrak KVN writes CREATION_DATE and ORIGINATOR with blank values and blank OBJECT_ID for analyst objects; MEAN_ELEMENT_THEORY is 'SGP/SGP4'.
- **leading-dot-decimals** — CSV, KVN and XML values may start with '.' or '-.' (no leading zero) and use 'E' exponents; JSON carries numbers.
- **negative-bstar-and-ndot** — BSTAR and the first derivative can be negative; parsers must keep the sign.
- **sha256-matches-tested-snapshot** — If the user's fetched bytes hash to the recorded SHA-256, the frozen expected values apply exactly; otherwise only structural checks apply and the tool says so.

## Coverage

Provides:

- two-digit year in the 57-99 branch (98 -> 1998)
- negative first derivative
- non-zero second derivative (11563-4)
- BSTAR zero written 00000+0
- element set number 1, revolution number 0

Gaps (stated explicitly for this case):

- the 00-56 branch is covered only by 2026 records elsewhere; no record near the 56/57 boundary exists

## Ambiguities recorded

- **mmdot-convention** — CCSDS 4.2.4.7 NOTE 2 says TLE-sourced MEAN_MOTION_DOT/DDOT 'need to be divided by 2 and 6 respectively' but does not say which convention the OMM value carries. Observed: CelesTrak's OMM values equal the TLE fields as printed (301/301 records), i.e. the halved / sixth-ed values. Parsers converting to true derivatives must multiply by 2 and 6.
- **empty-mandatory-header** — CCSDS Table 4-1 makes CREATION_DATE and ORIGINATOR mandatory; CelesTrak emits them empty in XML and blank in KVN. The 2.0 schema's epochType pattern accepts an empty string, so schema validation may pass; the KVN rule 7.5.1 is still violated.
- **leading-dot-decimals** — CCSDS 7.5.6 requires at least one digit before and after the decimal point in KVN fixed-point values; CelesTrak writes '.00048259' and '.15975118E-3'. Most decimal parsers accept this; strict KVN validators may not.
- **met-sgp-sgp4-vs-sgp4** — For the same record CelesTrak writes MEAN_ELEMENT_THEORY = SGP/SGP4 in KVN and SGP4 in XML. Both appear in CCSDS examples; parsers should accept both.
- **omm-version-2-vs-3** — CelesTrak declares OMM version 2.0 (Silver Book 2009) although the current standard is 3.0 (Blue Book 2023). The 2.0 XML schema set is still downloadable from SANA by direct URL; against the current 4.0.0/3.0 set the documents fail on the fixed version attribute.
- **gp-first-stability** — The corpus assumes CelesTrak's gp-first.php ('first GP data available') returns the same record for a given catalog number indefinitely. This was not verified over time. tools/fetch.py compares every fetched file with the SHA-256 recorded in manifest.json after each run (and on demand with --check-drift) and prints a DRIFT line for any stable-tier source whose bytes differ; the runner independently labels such a source 'live' and stops applying the frozen values to it. Related observation (D-070, D-074): gp-first records are historical in their elements but can carry metadata assigned after first publication. For catalog 100000, Space-Track's earliest record has a blank international designator, Space-Track's current record carries the same designator as CelesTrak, and CelesTrak's gp-first record shows that designator back-filled; the line-2 elements are identical. Treat OBJECT_NAME and OBJECT_ID in a gp-first record as current metadata, not as the values first published.

## Sources

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `fixtures/epoch-year-19xx/raw/iss-first.tle` | stable | 200 | 168 | 2026-09-21T00:11:49Z | `274de71dc147837c…` |
| `fixtures/epoch-year-19xx/raw/iss-first.2le` | stable | 200 | 142 | 2026-09-21T00:43:47Z | `a3c757af5751a3f2…` |
| `fixtures/epoch-year-19xx/raw/iss-first.csv` | stable | 200 | 368 | 2026-09-21T00:43:39Z | `cbdd6a2e36b97d54…` |
| `fixtures/epoch-year-19xx/raw/iss-first.json` | stable | 200 | 414 | 2026-09-21T00:11:51Z | `e18ebbe14d38ae61…` |
| `fixtures/epoch-year-19xx/raw/iss-first.pretty.json` | stable | 200 | 517 | 2026-09-21T00:43:50Z | `481ea9ae0881f58a…` |
| `fixtures/epoch-year-19xx/raw/iss-first.xml` | stable | 200 | 1198 | 2026-09-21T00:43:41Z | `cdcfd5fbd9e8b476…` |
| `fixtures/epoch-year-19xx/raw/iss-first.kvn` | stable | 200 | 626 | 2026-09-21T00:43:45Z | `b23fb2823e24b7f9…` |

URLs (each requested once when the fixtures were built):

- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=25544&FORMAT=2LE>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=25544&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=25544&FORMAT=JSON>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=25544&FORMAT=JSON-PRETTY>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=25544&FORMAT=KVN>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=25544&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=25544&FORMAT=XML>

Expected values: `fixtures/epoch-year-19xx/expected.json` (schema_version 1.0).
