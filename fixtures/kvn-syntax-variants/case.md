# kvn-syntax-variants

CCSDS-legal KVN renderings of one record that CelesTrak never emits

## What it tests

- kvn-syntax

## How to read a failure

Six CCSDS-legal renderings of one record that CelesTrak never emits: day-of-year epoch with Z, bracketed units, comments and blank lines and odd whitespace with LF endings, an OMM 3.0 header with the optional TLE parameters omitted, signed integers and a lowercase exponent. Every variant must parse to the same orbital values as the base record. The naive adapter (tests/adapters/naive.py) fails four of the six: v02 (day-of-year epoch with Z), v03 (bracketed units), v04 (COMMENT lines and irregular whitespace) and v05 (optional keywords omitted); it passes v01 and v06.

## Checks

- **kvn-syntax-tolerance** — KVN parsers accept blank lines, COMMENT lines at allowed positions, arbitrary whitespace around '=', bracketed units, day-of-year epochs, an optional trailing Z, signed integers, lowercase 'e' exponents, LF or CRLF endings.
- **optional-tle-parameters-may-be-absent** — EPHEMERIS_TYPE, CLASSIFICATION_TYPE, NORAD_CAT_ID, ELEMENT_SET_NO and REV_AT_EPOCH are Optional in CCSDS Table 4-3 and may be missing from a valid OMM.
- **omm-version-3-accepted** — CCSDS_OMM_VERS 3.0 messages (with CLASSIFICATION and MESSAGE_ID in the header) are accepted alongside 2.0.

## Coverage

Provides:

- day-of-year epoch with Z
- bracketed units
- COMMENT and blank lines, irregular whitespace, TAB, LF endings
- OMM 3.0 header with optional TLE parameters omitted
- signed integers and lowercase exponent

Gaps (stated explicitly for this case):

- lowercase normative text values (7.5.3) and the 254-character line limit are not exercised
- no XML variants in this version

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

Expected values: `fixtures/kvn-syntax-variants/expected.json` (schema_version 1.0).
