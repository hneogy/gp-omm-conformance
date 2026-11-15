# kvn-syntax-variants

CCSDS-legal KVN renderings of one record that CelesTrak never emits, and one synthetic-derived file of day-366 and post-2038 epochs

## What it tests

- kvn-syntax

## How to read a failure

Six CCSDS-legal renderings of one record that CelesTrak never emits: day-of-year epoch with Z, bracketed units, comments and blank lines and odd whitespace with LF endings, an OMM 3.0 header with the optional TLE parameters omitted, signed integers and a lowercase exponent. Every variant must parse to the same orbital values as the base record. A seventh file, v08, is synthetic-derived: eight OMM messages in one file, as CelesTrak serves a group, each the base record's values under a five-digit specification id (99990-99997), five with the epoch on 31 December, day 366, of a leap year, two in the day-of-year form (D-384), and three at or past 2038-01-19T03:14:07, the last second a signed 32-bit time_t holds (D-385); each must parse to its own record, and every message in the file must be read. The naive adapter (tests/adapters/naive.py) fails five of the seven: v02 (day-of-year epoch with Z), v03 (bracketed units), v04 (COMMENT lines and irregular whitespace), v05 (optional keywords omitted) and v08 (its day-of-year epochs); it passes v01 and v06.

## Checks

- **kvn-syntax-tolerance** — KVN parsers accept blank lines, COMMENT lines at allowed positions, arbitrary whitespace around '=', bracketed units, day-of-year epochs, an optional trailing Z, signed integers, lowercase 'e' exponents, LF or CRLF endings.
- **optional-tle-parameters-may-be-absent** — EPHEMERIS_TYPE, CLASSIFICATION_TYPE, NORAD_CAT_ID, ELEMENT_SET_NO and REV_AT_EPOCH are marked O in CCSDS Table 4-3, but that table heads the block "TLE Related Parameters (This section is only required if MEAN_ELEMENT_THEORY=SGP/SGP4)" and the NORAD_CAT_ID row adds "This keyword is only required if MEAN_ELEMENT_THEORY=SGP/SGP4.", so for an SGP/SGP4 message the standard is ambiguous; the corpus accepts their absence from a valid OMM.
- **omm-version-3-accepted** — CCSDS_OMM_VERS 3.0 messages (with CLASSIFICATION and MESSAGE_ID in the header) are accepted alongside 2.0.
- **catalog-number-is-integer** — NORAD_CAT_ID parses as an integer in every OMM format, including values of six and nine digits, and a ten-digit value is rejected (CCSDS allows up to nine digits); leading zeros and an explicit '+' are legal in KVN.

## Coverage

Provides:

- day-of-year epoch with Z
- bracketed units
- COMMENT and blank lines, irregular whitespace, TAB, LF endings
- OMM 3.0 header with optional TLE parameters omitted
- signed integers and lowercase exponent
- eight synthetic-derived OMM messages (ids 99990-99997), the baseline values with a replaced EPOCH: five on 31 December, day 366, of a leap year (1960, 1996, 2000, 2024, 2056), two of them in the day-of-year form (D-384); three at 2038-01-19T03:14:07 and 03:14:08, the last second a signed 32-bit time_t holds and the next, and 2050-06-15 (D-385)

Gaps (stated explicitly for this case):

- lowercase normative text values (7.5.3) and the 254-character line limit are not exercised
- no XML variants here: the corpus's one derived XML file, this record re-serialised (v07 in this folder), is graded for its values in the corrupt-input case, so that this case stays a case about KVN (D-299)

## Ambiguities recorded

- **leading-dot-decimals** — CCSDS 7.5.6 requires at least one digit before and after the decimal point in KVN fixed-point values; CelesTrak writes '.00048259' and '.15975118E-3'. Most decimal parsers accept this; strict KVN validators may not.
- **met-sgp-sgp4-vs-sgp4** — For the same record CelesTrak writes MEAN_ELEMENT_THEORY = SGP/SGP4 in KVN and SGP4 in XML. Both appear in CCSDS examples; parsers should accept both.

## Sources

Every file of this case ships with the repository; nothing is fetched.

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `derived/kvn-variants/v01-baseline-reserialised.kvn` | stable | none: derived file shipped with the repository | 728 | generated 2026-09-21T00:50:18Z | `97450978821f04d3…` |
| `derived/kvn-variants/v02-day-of-year-epoch-Z.kvn` | stable | none: derived file shipped with the repository | 727 | generated 2026-09-21T00:50:18Z | `a06629aa3044698c…` |
| `derived/kvn-variants/v03-units-brackets-leading-zeros.kvn` | stable | none: derived file shipped with the repository | 796 | generated 2026-09-21T00:50:18Z | `3c9e9d9aa6190ac4…` |
| `derived/kvn-variants/v04-comments-blank-lines-whitespace-LF.kvn` | stable | none: derived file shipped with the repository | 677 | generated 2026-09-21T00:50:18Z | `1cae8ec648cc8867…` |
| `derived/kvn-variants/v05-omm-3.0-header-optional-keywords-omitted.kvn` | stable | none: derived file shipped with the repository | 728 | generated 2026-09-21T00:50:18Z | `10e02122947f3c7d…` |
| `derived/kvn-variants/v06-signed-integers-lowercase-exponent.kvn` | stable | none: derived file shipped with the repository | 733 | generated 2026-09-21T00:50:18Z | `dff1329a94b59bc8…` |
| `derived/kvn-variants/v08-synthetic-epochs.kvn` | stable | none: derived file shipped with the repository | 5820 | generated 2026-11-05T13:57:24Z | `3e39e9dabea6b4ae…` |

Expected values: `fixtures/kvn-syntax-variants/expected.json` (schema_version 1.0).
