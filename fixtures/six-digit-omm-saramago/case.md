# six-digit-omm-saramago

Catalog number 100000 (SARAMAGO): first 6-digit object, OMM formats only, TLE unavailable

## What it tests

- 6-digit-catalog-number
- tle-unavailable-above-99999
- same-object-all-omm-formats

## How to read a failure

The first six-digit object. A parser must accept NORAD_CAT_ID 100000 in every OMM format and must treat the TLE request's HTTP 404 'No GP data found' as 'this object cannot be rendered as a TLE', not as an outage. The stable gp-first record has frozen expected values.

## Checks

- **catalog-number-is-integer** — NORAD_CAT_ID parses as an integer in every OMM format, including values of six and nine digits, and a ten-digit value is rejected (CCSDS allows up to nine digits); leading zeros and an explicit '+' are legal in KVN.
- **omm-formats-agree** — For the same object and snapshot, CSV, JSON, XML and KVN yield identical canonical values for every OMM keyword present in all of them.
- **tle-format-omits-ids-above-99999** — A TLE/3LE/2LE request returns only objects with catalog numbers below 100000; if none qualify the response is HTTP 404 'No GP data found'.
- **csv-json-omit-constant-metadata** — CelesTrak CSV/JSON carry no CENTER_NAME, REF_FRAME, TIME_SYSTEM or MEAN_ELEMENT_THEORY; parsers must default them (EARTH, TEME, UTC, SGP4) rather than fail.
- **xml-ndm-wrapper-omm-2.0** — CelesTrak XML has an <ndm> root containing one <omm> per record with id=CCSDS_OMM_VERS and version=2.0; CREATION_DATE and ORIGINATOR elements are present but empty.
- **sha256-matches-tested-snapshot** — If the user's fetched bytes hash to the recorded SHA-256, the frozen expected values apply exactly; otherwise only structural checks apply and the tool says so.

## Coverage

Provides:

- the first 6-digit catalog number, stable (gp-first) and live
- HTTP 404 'No GP data found' for the TLE request, stable and live
- SATCAT record verifying designator 2026-067CY and launch 2026-03-30

Gaps (stated explicitly for this case):

- only one object; other 6-digit objects are in last-30-days and analyst cases

## Ambiguities recorded

- **gp-first-stability** — The corpus assumes CelesTrak's gp-first.php ('first GP data available') returns the same record for a given catalog number indefinitely. This was not verified over time. tools/fetch.py compares every fetched file with the SHA-256 recorded in manifest.json after each run (and on demand with --check-drift) and prints a DRIFT line for any stable-tier source whose bytes differ; the runner independently labels such a source 'live' and stops applying the frozen values to it. Related observation (D-070, D-074): gp-first records are historical in their elements but can carry metadata assigned after first publication. For catalog 100000, Space-Track's earliest record has a blank international designator, Space-Track's current record carries the same designator as CelesTrak, and CelesTrak's gp-first record shows that designator back-filled; the line-2 elements are identical. Treat OBJECT_NAME and OBJECT_ID in a gp-first record as current metadata, not as the values first published.
- **satcat-record-drift** — SATCAT records for existing objects change when an object decays or its orbit summary is updated; records.php sources are treated as live for checksum purposes even though most fields are stable.

## Sources

The `raw/` files below are not in the repository: `tools/fetch.py` creates them on your machine, one request per URL under CelesTrak's usage policy, and until they exist the runner reports this case's checks as skipped, not failed.

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `fixtures/six-digit-omm-saramago/raw/saramago-first.tle` | stable | 404, expected: the body is "No GP data found" | 16 | 2026-09-21T00:43:53Z | `000844fd5b7a7b64…` |
| `fixtures/six-digit-omm-saramago/raw/saramago-first.csv` | stable | 200 | 374 | 2026-09-21T00:43:55Z | `2a1913dc0c5e2bab…` |
| `fixtures/six-digit-omm-saramago/raw/saramago-first.json` | stable | 200 | 420 | 2026-09-21T00:43:58Z | `1d04dc3b4e49d6f7…` |
| `fixtures/six-digit-omm-saramago/raw/saramago-first.xml` | stable | 200 | 1204 | 2026-09-21T00:44:00Z | `c2523a59549f0e95…` |
| `fixtures/six-digit-omm-saramago/raw/saramago-first.kvn` | stable | 200 | 632 | 2026-09-21T00:44:03Z | `bb9073b3b323e259…` |
| `fixtures/six-digit-omm-saramago/raw/saramago.csv` | live | 200 | 375 | 2026-09-21T00:09:50Z | `650bde1c540e1636…` |
| `fixtures/six-digit-omm-saramago/raw/saramago.json` | live | 200 | 421 | 2026-09-21T00:09:52Z | `7d06887037002ed0…` |
| `fixtures/six-digit-omm-saramago/raw/saramago.xml` | live | 200 | 1205 | 2026-09-21T00:09:55Z | `763990333a9a4f48…` |
| `fixtures/six-digit-omm-saramago/raw/saramago.kvn` | live | 200 | 633 | 2026-09-21T00:09:57Z | `8e9591ef376a57d8…` |
| `fixtures/six-digit-omm-saramago/raw/saramago.tle` | live | 404, expected: the body is "No GP data found" | 16 | 2026-09-21T00:09:59Z | `000844fd5b7a7b64…` |
| `fixtures/six-digit-omm-saramago/raw/saramago.satcat.json` | live | 200 | 332 | 2026-09-21T00:10:02Z | `235cf52e5287a8b3…` |
| `fixtures/six-digit-omm-saramago/raw/saramago.satcat.csv` | live | 200 | 269 | 2026-09-21T00:10:04Z | `ad32c117b2a0ad4c…` |

URLs (each requested once when the fixtures were built):

- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=100000&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=100000&FORMAT=JSON>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=100000&FORMAT=KVN>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=100000&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=100000&FORMAT=XML>
- <https://celestrak.org/NORAD/elements/gp.php?CATNR=100000&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp.php?CATNR=100000&FORMAT=JSON>
- <https://celestrak.org/NORAD/elements/gp.php?CATNR=100000&FORMAT=KVN>
- <https://celestrak.org/NORAD/elements/gp.php?CATNR=100000&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/gp.php?CATNR=100000&FORMAT=XML>
- <https://celestrak.org/satcat/records.php?CATNR=100000&FORMAT=CSV>
- <https://celestrak.org/satcat/records.php?CATNR=100000&FORMAT=JSON>

Expected values: `fixtures/six-digit-omm-saramago/expected.json` (schema_version 1.0).
