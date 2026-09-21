# tle-omits-six-digit-objects

A group with only 6-digit objects: OMM formats return 256 records, the TLE request returns HTTP 404

## What it tests

- tle-unavailable-above-99999
- 6-digit-catalog-number

## How to read a failure

A group whose members are all six-digit. The OMM formats return every record; the TLE request returns nothing (HTTP 404). A pipeline that treats a 404 or an empty TLE file as 'no new data' silently loses every object launched after 2026-07-11. When objects below 100000 are in the window again the TLE response holds exactly those; the count check covers both states.

## Checks

- **tle-format-omits-ids-above-99999** — A TLE/3LE/2LE request returns only objects with catalog numbers below 100000; if none qualify the response is HTTP 404 'No GP data found'.
- **tle-count-equals-omm-count-below-100000** — The number of TLE records equals the number of OMM records whose NORAD_CAT_ID < 100000 for the same query.
- **catalog-number-is-integer** — NORAD_CAT_ID parses as an integer in every OMM format, including values of six and nine digits; leading zeros and an explicit '+' are legal in KVN.

## Coverage

Provides:

- 256 six-digit ids 100404-100789 in CSV
- TLE request -> 404 with body 'No GP data found' (captured twice, 00:10Z hand-recorded and 00:41Z clean)
- 11 records with non-zero second derivative
- negative BSTAR values

Gaps (stated explicitly for this case):

- window-dependent: once objects below 100000 re-enter the 30-day window the TLE request will return data again; the structural check covers both outcomes

## Ambiguities recorded

- none

## Sources

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `fixtures/tle-omits-six-digit-objects/raw/last-30-days.csv` | live | 200 | 39336 | 2026-09-21T00:10:07Z | `bc9a5dff288a26d3…` |
| `fixtures/tle-omits-six-digit-objects/raw/last-30-days.tle` | live | 404 | 16 | 2026-09-21T00:10:10Z | `000844fd5b7a7b64…` |
| `fixtures/tle-omits-six-digit-objects/raw/last-30-days-recapture.tle` | live | 404 | 16 | 2026-09-21T00:41:28Z | `000844fd5b7a7b64…` |

URLs (each requested once when the fixtures were built):

- <https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=tle>

Expected values: `fixtures/tle-omits-six-digit-objects/expected.json` (schema_version 1.0).
