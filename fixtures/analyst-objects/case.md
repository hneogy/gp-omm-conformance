# analyst-objects

Analyst objects: empty OBJECT_ID, OBJECT_NAME UNKNOWN, 8xxxx and 27xxxx ids, TLE keeps only the 5-digit ones

## What it tests

- analyst-objects-no-object-id
- 6-digit-catalog-number
- tle-unavailable-above-99999

## How to read a failure

Analyst objects carry an empty OBJECT_ID in every format (empty string, or an empty XML element that Python's ElementTree returns as None) and the literal OBJECT_NAME 'UNKNOWN' (all 565 records at the snapshot; the CCSDS-recommended value). Parsers must not crash, must not invent a designator or a name, and must keep six-digit ids 270000-270449 that the TLE rendering drops. Analyst numbers are reused, so identity is per snapshot.

## Checks

- **object-id-may-be-empty** — OBJECT_ID (and in principle OBJECT_NAME) can be empty; parsers must not fail, and must not invent a value.
- **object-name-unknown-literal** — OBJECT_NAME may be the literal UNKNOWN (CCSDS-recommended) rather than empty.
- **catalog-number-is-integer** — NORAD_CAT_ID parses as an integer in every OMM format, including values of six and nine digits; leading zeros and an explicit '+' are legal in KVN.
- **tle-format-omits-ids-above-99999** — A TLE/3LE/2LE request returns only objects with catalog numbers below 100000; if none qualify the response is HTTP 404 'No GP data found'.
- **tle-count-equals-omm-count-below-100000** — The number of TLE records equals the number of OMM records whose NORAD_CAT_ID < 100000 for the same query.
- **omm-formats-agree** — For the same object and snapshot, CSV, JSON, XML and KVN yield identical canonical values for every OMM keyword present in all of them.
- **xml-ndm-wrapper-omm-2.0** — CelesTrak XML has an <ndm> root containing one <omm> per record with id=CCSDS_OMM_VERS and version=2.0; CREATION_DATE and ORIGINATOR elements are present but empty.
- **kvn-blank-mandatory-values** — CelesTrak KVN writes CREATION_DATE and ORIGINATOR with blank values and blank OBJECT_ID for analyst objects; MEAN_ELEMENT_THEORY is 'SGP/SGP4'.

## Coverage

Provides:

- 565 analyst objects (219 in 80000-89999, 346 in 270000-270449) at the snapshot
- 563 of 565 with an empty OBJECT_ID; all 565 carry the literal OBJECT_NAME 'UNKNOWN' (no analyst object in the group has a real name)
- stable first records for 270449 (6-digit, letter T) and 81011, also with OBJECT_NAME UNKNOWN and empty OBJECT_ID
- TLE rendering of the 81011 record with eight blank international-designator columns

Gaps (stated explicitly for this case):

- no analyst record with an empty OBJECT_NAME was observed; that variant is untested
- the 90000 block is not observed

## Library behaviour observed (docs/CROSSCHECK.md)

- python-sgp4 2.27 sgp4.omm.parse_xml returns None for an empty <OBJECT_ID/> element and initialize() then raises TypeError; 564 of the 566 analyst XML records in the case (563 of the 565 group records, plus the single 270449 first record) fail, while the same records in CSV pass.

## Ambiguities recorded

- **unknown-vs-blank** — CCSDS 502.0-B-3 Table 4-2 says an unknown OBJECT_NAME/OBJECT_ID 'should be set to UNKNOWN' and 7.5.1 requires a non-empty value for mandatory keywords; CelesTrak writes an empty OBJECT_ID (empty string in CSV/JSON/KVN, empty element in XML) while the first-ever analyst records carry OBJECT_NAME 'UNKNOWN'. The corpus expects the provider's actual output and records the spec text.
- **analyst-number-reuse** — Space-Track states analyst numbers 'can be constantly reused for different objects'; gp-first.php for an analyst id therefore returns whichever object first carried that number, which may differ from the object currently using it.
- **gp-first-stability** — The corpus assumes CelesTrak's gp-first.php ('first GP data available') returns the same record for a given catalog number indefinitely. This was not verified over time. tools/fetch.py compares every fetched file with the SHA-256 recorded in manifest.json after each run (and on demand with --check-drift) and prints a DRIFT line for any stable-tier source whose bytes differ; the runner independently labels such a source 'live' and stops applying the frozen values to it. Related observation (D-070, D-074): gp-first records are historical in their elements but can carry metadata assigned after first publication. For catalog 100000, Space-Track's earliest record has a blank international designator, Space-Track's current record carries the same designator as CelesTrak, and CelesTrak's gp-first record shows that designator back-filled; the line-2 elements are identical. Treat OBJECT_NAME and OBJECT_ID in a gp-first record as current metadata, not as the values first published.

## Sources

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `fixtures/analyst-objects/raw/analyst.tle` | live | 200 | 36792 | 2026-09-21T00:11:41Z | `3d3aac4567f7f709…` |
| `fixtures/analyst-objects/raw/analyst.csv` | live | 200 | 76633 | 2026-09-21T00:11:30Z | `e1d437ebf2a53ed9…` |
| `fixtures/analyst-objects/raw/analyst.json` | live | 200 | 228966 | 2026-09-21T00:11:33Z | `f3a4773680d66ed3…` |
| `fixtures/analyst-objects/raw/analyst.xml` | live | 200 | 552351 | 2026-09-21T00:11:35Z | `8c76a7863573b288…` |
| `fixtures/analyst-objects/raw/analyst.kvn` | live | 200 | 350431 | 2026-09-21T00:11:38Z | `6d8c57c5260854d2…` |
| `fixtures/analyst-objects/raw/analyst-recapture.tle` | live | 200 | 36792 | 2026-09-21T00:41:30Z | `3d3aac4567f7f709…` |
| `fixtures/analyst-objects/raw/analyst-270449-first.tle` | stable | 404 | 16 | 2026-09-21T00:44:05Z | `000844fd5b7a7b64…` |
| `fixtures/analyst-objects/raw/analyst-270449-first.csv` | stable | 200 | 363 | 2026-09-21T00:44:08Z | `f9caeec84ba49dc0…` |
| `fixtures/analyst-objects/raw/analyst-270449-first.json` | stable | 200 | 409 | 2026-09-21T00:44:11Z | `c50e3ee57a010841…` |
| `fixtures/analyst-objects/raw/analyst-270449-first.xml` | stable | 200 | 1193 | 2026-09-21T00:44:15Z | `94c54614780dbe36…` |
| `fixtures/analyst-objects/raw/analyst-270449-first.kvn` | stable | 200 | 621 | 2026-09-21T00:44:17Z | `e90632bbe787b917…` |
| `fixtures/analyst-objects/raw/analyst-81011-first.tle` | stable | 200 | 168 | 2026-09-21T00:44:20Z | `f06539e94675d87b…` |
| `fixtures/analyst-objects/raw/analyst-81011-first.csv` | stable | 200 | 357 | 2026-09-21T00:44:23Z | `339ed35b58d6300d…` |
| `fixtures/analyst-objects/raw/analyst-81011-first.json` | stable | 200 | 402 | 2026-09-21T00:44:26Z | `742bd531a42360d6…` |

URLs (each requested once when the fixtures were built):

- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=270449&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=270449&FORMAT=JSON>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=270449&FORMAT=KVN>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=270449&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=270449&FORMAT=XML>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=81011&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=81011&FORMAT=JSON>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=81011&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=JSON>
- <https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=KVN>
- <https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=XML>
- <https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=tle>

Expected values: `fixtures/analyst-objects/expected.json` (schema_version 1.0).
