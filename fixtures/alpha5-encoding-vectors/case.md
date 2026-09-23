# alpha5-encoding-vectors

Alpha-5 encode/decode vectors from the Space-Track table, with boundaries and invalid inputs

## What it tests

- alpha5-letter-skip-rules
- alpha5-range
- 9-digit-catalog-number
- 2-digit-epoch-year

## How to read a failure

Pure mapping vectors: the six official Space-Track examples, every letter boundary, both skips (H->J, N->P), five-digit values with leading zeros, invalid letters (I, O), lowercase, and unencodable integers. A decoder that maps letters by ord() without skipping I and O is wrong from 180000 upward. The ccsds-epoch-strings vectors carry the instant each valid form denotes, so a parse_epoch hook is checked for the value it returns, not only for returning.

## Checks

- **alpha5-decode** — An Alpha-5 catalog field decodes as (letter value)*10000 + digits with A=10 ... Z=33 and I, O unused; 'I', 'O' and lowercase are invalid.
- **alpha5-encode** — Integers 100000-339999 encode to the Alpha-5 table; below 100000 encode as five digits with leading zeros; above 339999 cannot be encoded.
- **catalog-number-is-integer** — NORAD_CAT_ID parses as an integer in every OMM format, including values of six and nine digits; leading zeros and an explicit '+' are legal in KVN.
- **two-digit-year-pivot** — TLE epoch years 57-99 map to 1957-1999 and 00-56 to 2000-2056; the resulting ISO epoch equals the OMM EPOCH string.
- **ccsds-epoch-strings** — parse_epoch accepts every CCSDS 502.0-B-3 7.5.10 epoch form in vectors/ccsds-epoch-strings.json (calendar and day-of-year, with or without a fraction and a Z, second 60) and returns the instant each denotes (within 2 us; a leap second may read as 23:59:59 or as the next midnight), and rejects the five invalid forms.

## Coverage

Provides:

- all 24 letters and both skips, the six official examples, range boundaries, invalid letters and lowercase

Gaps (stated explicitly for this case):

- vectors are not element sets; they test the mapping only

## Library behaviour observed (docs/CROSSCHECK.md)

- python-sgp4 2.27 sgp4.alpha5.from_alpha5 is lenient: it accepts I0000 (as 180000), O1234, lowercase and four-character fields that the Space-Track definition excludes; to_alpha5(-1) returns '-0001'.

## Ambiguities recorded

- none

## Sources

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `vectors/alpha5.json` | stable | None | 9000 | None | `9df250841f0667a5…` |
| `vectors/norad-cat-id-text.json` | stable | None | 1449 | None | `58a4ae4413e161bd…` |
| `vectors/two-digit-epoch-year.json` | stable | None | 1475 | None | `c3c2f54967174770…` |
| `vectors/ccsds-epoch-strings.json` | stable | None | 2215 | None | `0add8aa91d36b40d…` |

Expected values: `fixtures/alpha5-encoding-vectors/expected.json` (schema_version 1.0).
