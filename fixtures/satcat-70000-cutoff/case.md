# satcat-70000-cutoff

SATCAT on both sides of 70000: CSV/JSON records for 25544, 69999 and 100000; legacy fixed-width file stops at 69999

## What it tests

- legacy-satcat-cutoff-70000

## How to read a failure

The legacy fixed-width SATCAT stops at id 69999 by design; the CSV/JSON SATCAT continues past 100000. Software reading the legacy file will never see new objects. The expected values include the parsed legacy lines for 25544 and 69999 and the JSON/CSV records for 25544, 69999 and 100000. The runner reports this case as not exercised for every parser: its check is on the data, and no adapter reads SATCAT (D-129).

## Checks

- **satcat-legacy-below-70000** — The legacy fixed-width SATCAT contains only NORAD ids below 70000; the CSV/JSON SATCAT contains ids on both sides.
- **catalog-number-is-integer** — NORAD_CAT_ID parses as an integer in every OMM format, including values of six and nine digits, and a ten-digit value is rejected (CCSDS allows up to nine digits); leading zeros and an explicit '+' are legal in KVN.

## Coverage

Provides:

- legacy file: 69,999 lines, ids 1..69999 contiguous, none >= 70000
- records.php JSON/CSV for 25544, 69999 (VANGUARD DEB, 1958-002D) and 100000

Gaps (stated explicitly for this case):

- the 9.4 MB legacy file is not shipped; users fetch it once and the check recomputes the facts

## Ambiguities recorded

- **satcat-record-drift** — SATCAT records for existing objects change when an object decays or its orbit summary is updated; records.php sources are treated as live for checksum purposes even though most fields are stable.

## Sources

The `raw/` files below are not in the repository: `tools/fetch.py` creates them on your machine, one request per URL under CelesTrak's usage policy, and until they exist the runner reports this case's checks as skipped, not failed.

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `fixtures/satcat-70000-cutoff/raw/satcat-25544.json` | live | 200 | 337 | 2026-09-21T00:11:54Z | `44efb326be9e9b25…` |
| `fixtures/satcat-70000-cutoff/raw/satcat-25544.csv` | live | 200 | 278 | 2026-09-21T00:11:56Z | `529a3f2dbb60c542…` |
| `fixtures/satcat-70000-cutoff/raw/satcat-69999.json` | live | 200 | 334 | 2026-09-21T00:14:30Z | `f464efdf6d869c25…` |
| `fixtures/satcat-70000-cutoff/raw/satcat-69999.csv` | live | 200 | 271 | 2026-09-21T00:14:32Z | `269f8a194368e3f3…` |
| `fixtures/six-digit-omm-saramago/raw/saramago.satcat.json` | live | 200 | 332 | 2026-09-21T00:10:02Z | `235cf52e5287a8b3…` |
| `fixtures/six-digit-omm-saramago/raw/saramago.satcat.csv` | live | 200 | 269 | 2026-09-21T00:10:04Z | `ad32c117b2a0ad4c…` |
| `fixtures/satcat-70000-cutoff/raw/satcat.txt` | live | 200 | 9379866 | 2026-09-21T00:12:02Z | `8dbf69297f6c4513…` |

URLs (each requested once when the fixtures were built):

- <https://celestrak.org/pub/satcat.txt>
- <https://celestrak.org/satcat/records.php?CATNR=100000&FORMAT=CSV>
- <https://celestrak.org/satcat/records.php?CATNR=100000&FORMAT=JSON>
- <https://celestrak.org/satcat/records.php?CATNR=25544&FORMAT=CSV>
- <https://celestrak.org/satcat/records.php?CATNR=25544&FORMAT=JSON>
- <https://celestrak.org/satcat/records.php?CATNR=69999&FORMAT=CSV>
- <https://celestrak.org/satcat/records.php?CATNR=69999&FORMAT=JSON>

Expected values: `fixtures/satcat-70000-cutoff/expected.json` (schema_version 1.0).
