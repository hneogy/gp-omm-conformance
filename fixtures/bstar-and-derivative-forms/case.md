# bstar-and-derivative-forms

Drag terms: negative BSTAR, negative first derivative, non-zero second derivative, implied-decimal exponent fields

## What it tests

- bstar-implicit-decimal
- negative-bstar
- negative-ndot
- nonzero-nddot

## How to read a failure

Drag-term encodings: negative BSTAR and first derivative, non-zero second derivative, implied-decimal exponent fields. A parser must read ' 51949-2' as 0.51949e-2 and '-70517-5' as -0.70517e-5. No record with a positive exponent (>= 1.0) exists in the data; that encoding is untested here.

## Checks

- **bstar-implied-decimal-exponent** — TLE BSTAR and second-derivative fields are +/-NNNNN+/-E with an implied leading decimal point: ' 15975-3' is 0.15975e-3; zero is written ' 00000+0'.
- **negative-bstar-and-ndot** — BSTAR and the first derivative can be negative; parsers must keep the sign.
- **mmdot-is-tle-field-value** — OMM MEAN_MOTION_DOT equals the TLE first-derivative field as printed (the TLE 'ndot/2' convention); MEAN_MOTION_DDOT likewise equals the TLE second-derivative field.
- **tle-values-match-omm-within-tle-precision** — The TLE rendering equals the OMM values except: eccentricity truncated to 7 digits, BSTAR and second derivative rounded (half up) to a 5-digit mantissa, epoch at 1e-8 day resolution.
- **tle-checksums-valid** — Every TLE line 1 and line 2 is 69 characters and ends with the modulo-10 checksum (digits count their value, '-' counts 1, everything else 0).
- **tle-count-equals-omm-count-below-100000** — The number of TLE records equals the number of OMM records whose NORAD_CAT_ID < 100000 for the same query.

## Coverage

Provides:

- 79 decaying objects with non-zero second derivative
- negative BSTAR (69999: -70517-5) and negative first derivative
- BSTAR up to 0.0052 (51949-2)

Gaps (stated explicitly for this case):

- no BSTAR with a positive exponent (>= 1.0 Earth radii^-1) exists in any fetched data; that encoding ('NNNNN+1') is untested on the reader side (the writer case carries a synthetic-derived vector for it, D-125)
- no second derivative with a positive exponent

## Ambiguities recorded

- **ecc-truncation-vs-mantissa-rounding** — CelesTrak's TLE rendering truncates eccentricity to 7 digits but rounds (half up) BSTAR and the second derivative to a 5-digit mantissa (304/304 CelesTrak records reproduced with these rules; 0 with the opposite rules). No document states either rule; treat as observed CelesTrak behaviour. It is not universal: in the owner's Space-Track verification run (D-070) Space-Track's TLE for the same epoch differed from the CelesTrak-rendered line in the last one or two eccentricity digits (columns 32-33), consistent with rounding, and wrote a zero second derivative as 00000-0 (column 51) where CelesTrak writes 00000+0.
- **mmdot-convention** — CCSDS 4.2.4.7 NOTE 2 says TLE-sourced MEAN_MOTION_DOT/DDOT 'need to be divided by 2 and 6 respectively' but does not say which convention the OMM value carries. Observed: CelesTrak's OMM values equal the TLE fields as printed (304/304 records), i.e. the halved / sixth-ed values. Parsers converting to true derivatives must multiply by 2 and 6.

## Sources

The `raw/` files below are not in the repository: `tools/fetch.py` creates them on your machine, one request per URL under CelesTrak's usage policy, and until they exist the runner reports this case's checks as skipped, not failed.

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `fixtures/bstar-and-derivative-forms/raw/decaying.tle` | live | 200 | 13272 | 2026-09-21T00:11:44Z | `90b5925c40cec7ac…` |
| `fixtures/bstar-and-derivative-forms/raw/decaying.csv` | live | 200 | 13599 | 2026-09-21T00:11:46Z | `e40fb090eb7d485d…` |
| `fixtures/bstar-and-derivative-forms/raw/decaying-recapture.tle` | live | 200 | 13272 | 2026-09-21T00:41:33Z | `90b5925c40cec7ac…` |
| `fixtures/satcat-70000-cutoff/raw/gp-69999-first.tle` | stable | 200 | 168 | 2026-09-21T00:44:29Z | `b7f96c3912c2445c…` |
| `fixtures/satcat-70000-cutoff/raw/gp-69999-first.csv` | stable | 200 | 376 | 2026-09-21T00:44:33Z | `601736c2b121cea2…` |

- `decaying-recapture.tle` is a re-capture of `decaying.tle` (D-022): the same endpoint requested a second time, with the `FORMAT` value spelled in lower case; it records the response at its own retrieval time.

URLs (each requested once when the fixtures were built):

- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=69999&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=69999&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/gp.php?SPECIAL=DECAYING&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp.php?SPECIAL=DECAYING&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/gp.php?SPECIAL=DECAYING&FORMAT=tle>

Expected values: `fixtures/bstar-and-derivative-forms/expected.json` (schema_version 1.0).
