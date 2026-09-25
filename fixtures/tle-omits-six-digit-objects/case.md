# tle-omits-six-digit-objects

A group with only 6-digit objects: OMM formats return 256 records, the TLE request returns HTTP 404

## What it tests

- tle-unavailable-above-99999
- 6-digit-catalog-number

## How to read a failure

A group whose members are all six-digit. The OMM formats return every record; the TLE request returns nothing (HTTP 404). A pipeline that treats a 404 or an empty TLE file as 'no new data' silently loses every object launched after 2026-07-11. When objects below 100000 are in the window again the TLE response holds exactly those; the count check covers both states.

## Checks

- **tle-format-omits-ids-above-99999** — A TLE/3LE/2LE request returns only objects with catalog numbers below 100000; if none qualify the response is HTTP 404 'No GP data found'.
- **empty-answer-yields-no-records** — A provider answer that carries no data (HTTP 404, body 'No GP data found' or 'No SupGP data found') is an empty but valid result: handed to the parser, it yields zero records and no error. An error here collapses 'nothing to load' into 'unreadable' (D-143).
- **tle-count-equals-omm-count-below-100000** — The number of TLE records equals the number of OMM records whose NORAD_CAT_ID < 100000 for the same query.
- **catalog-number-is-integer** — NORAD_CAT_ID parses as an integer in every OMM format, including values of six and nine digits, and a ten-digit value is rejected (CCSDS allows up to nine digits); leading zeros and an explicit '+' are legal in KVN.

## Coverage

Provides:

- 256 six-digit ids 100404-100789 in CSV
- TLE request -> 404 with body 'No GP data found' (captured twice: at 00:10Z, when a tool defect discarded the body and it was reconstructed by hand from the tool's log, D-013; and at 00:41Z as a clean re-capture with full headers, D-022)
- 11 records with non-zero second derivative
- negative BSTAR values

Gaps (stated explicitly for this case):

- window-dependent: once objects below 100000 re-enter the 30-day window the TLE request will return data again; the structural check covers both outcomes

## Ambiguities recorded

- none

## Sources

The `raw/` files below are not in the repository: `tools/fetch.py` creates them on your machine, one request per URL under CelesTrak's usage policy, and until they exist the runner reports this case's checks as skipped, not failed.

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `fixtures/tle-omits-six-digit-objects/raw/last-30-days.csv` | live | 200 | 39336 | 2026-09-21T00:10:07Z | `bc9a5dff288a26d3…` |
| `fixtures/tle-omits-six-digit-objects/raw/last-30-days.tle` | live | 404, expected: the body is "No GP data found" | 16 | 2026-09-21T00:10:10Z | `000844fd5b7a7b64…` |
| `fixtures/tle-omits-six-digit-objects/raw/last-30-days-recapture.tle` | live | 404, expected: the body is "No GP data found" | 16 | 2026-09-21T00:41:28Z | `000844fd5b7a7b64…` |

- `last-30-days-recapture.tle` is a re-capture of `last-30-days.tle` (D-022): the same endpoint requested a second time, with the `FORMAT` value spelled in lower case; it records the response at its own retrieval time.

URLs (each requested once when the fixtures were built):

- <https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=tle>

Expected values: `fixtures/tle-omits-six-digit-objects/expected.json` (schema_version 1.0).
