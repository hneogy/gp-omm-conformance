# tle-vs-omm-precision-loss

The TLE is a lossy rendering of the OMM record: eccentricity truncated, BSTAR/DDOT mantissa rounded, epoch quantised

## Evidence basis

- The rendering rule stated by this case (eccentricity truncated to 7 digits; BSTAR and second-derivative mantissa rounded half up to 5 digits) was derived empirically from a sample of 304 CelesTrak TLE/OMM record pairs fetched 2026-09-21 (219 analyst, 79 decaying, 2 SupGP, 4 single objects). It is not documented in any specification or provider document we located (CCSDS 502.0-B-3, CelesTrak TLE format documentation, Space-Track TLE documentation); it is observed provider behaviour, and the sample is what supports it.
- With these rules the renderer in gpconf/tle.py reproduced 304 of 304 records byte for byte; with eccentricity rounded instead, 257 of 304; with the mantissa truncated instead, 251 of 304.
- The rule is CelesTrak's, not the TLE format's. Space-Track rounds the eccentricity: confirmed by prediction (D-071). From the CelesTrak OMM sources of the 21 records whose epochs matched in the owner's Space-Track run, rounding to 7 digits differs from truncation for exactly 8 (T0000, T0003, T0008, T0011, T0016, T0018, T0020, T0449; three of them with a carry into the sixth digit), and exactly those 8 Space-Track lines differed from the CelesTrak-rendered lines at column 33 (the three carries at columns 32-33); the other 13, where rounding equals truncation, matched. All 21 derived lines carry a zero second derivative, so the column-51 difference present on every one of them is the +0 (CelesTrak) versus -0 (Space-Track) sign of that field. A parser comparing a TLE to its OMM must therefore know which provider rendered the TLE.

## What it tests

- precision-loss
- round-trip-lossiness

## How to read a failure

The CelesTrak TLE is a lossy rendering of the OMM record: eccentricity truncated to 7 digits (304/304, never rounded), BSTAR and second derivative rounded half up to a 5-digit mantissa (304/304), SupGP epochs quantised to 1e-8 day. Space-Track's own TLE lines for the same records round the eccentricity and write a zero second derivative with the opposite exponent sign (D-070), so these rules describe CelesTrak's rendering specifically. Line 0 is limited to 24 characters by the CelesTrak format document, but no provider record in the 304 pairs has a longer name, so truncation is not an observed rule here (it occurs only in one derived line). Consequences: OMM -> TLE -> OMM does not round-trip; TLE -> OMM -> TLE does, verified byte for byte by tests/test_roundtrip.py over every CelesTrak TLE record in the corpus. Tests that compare a TLE to an OMM must apply exactly these rules, not a generic tolerance.

## Checks

- **tle-values-match-omm-within-tle-precision** — The TLE rendering equals the OMM values except: eccentricity truncated to 7 digits, BSTAR and second derivative rounded (half up) to a 5-digit mantissa, epoch at 1e-8 day resolution.

## Coverage

Provides:

- eccentricity: OMM has up to 8 decimals, TLE keeps the first 7 (truncation)
- BSTAR / DDOT: OMM has up to 8 significant digits, TLE keeps 5, rounded half up
- epoch: GP records convert exactly; SupGP records differ by up to half the 864 us TLE resolution
- TLE -> OMM -> TLE round trip through these rules is byte-exact (tests/test_roundtrip.py, every CelesTrak TLE record in the corpus plus the 604 derived lines)

Gaps (stated explicitly for this case):

- no rounding tie (mantissa digit 6 exactly 5 followed by zeros) was observed, so half-up versus half-even at the tie is not distinguished
- the 24-character limit of TLE line 0 is a rule of the CelesTrak format document, not an observation: no name longer than 24 characters occurs in the 304 provider pairs; the cut appears only in one derived line (catalog 100465)

## Library behaviour observed (docs/CROSSCHECK.md)

- python-sgp4 2.27 export_tle writes a zero second derivative as ' 00000-0', matching Space-Track's rendering; CelesTrak writes ' 00000+0', so a byte-exact round trip of a CelesTrak line succeeds only when the second derivative is non-zero. The values are identical; this is a provider divergence (D-072), not a library defect.

## Ambiguities recorded

- **ecc-truncation-vs-mantissa-rounding** — CelesTrak's TLE rendering truncates eccentricity to 7 digits but rounds (half up) BSTAR and the second derivative to a 5-digit mantissa (304/304 CelesTrak records reproduced with these rules; 0 with the opposite rules). No document states either rule; treat as observed CelesTrak behaviour. It is not universal: in the owner's Space-Track verification run (D-070) Space-Track's TLE for the same epoch differed from the CelesTrak-rendered line in the last one or two eccentricity digits (columns 32-33), consistent with rounding, and wrote a zero second derivative as 00000-0 (column 51) where CelesTrak writes 00000+0.
- **tle-epoch-resolution** — The TLE epoch has 1e-8 day (864 microsecond) resolution. CelesTrak GP epochs convert exactly between the two representations; SupGP epochs do not (86 microsecond difference observed), so a TLE->OMM epoch comparison needs a tolerance of half the TLE resolution.

## Sources

The `raw/` files below are not in the repository: `tools/fetch.py` creates them on your machine, one request per URL under CelesTrak's usage policy, and until they exist the runner reports this case's checks as skipped, not failed.

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `fixtures/epoch-year-19xx/raw/iss-first.tle` | mixed | 200 | 168 | 2026-09-21T00:11:49Z | `274de71dc147837c…` |
| `fixtures/epoch-year-19xx/raw/iss-first.csv` | mixed | 200 | 368 | 2026-09-21T00:43:39Z | `cbdd6a2e36b97d54…` |
| `fixtures/baseline-iss-five-formats/raw/iss.tle` | mixed | 200 | 168 | 2026-09-21T00:09:33Z | `674ea527c1ff8a70…` |
| `fixtures/baseline-iss-five-formats/raw/iss.csv` | mixed | 200 | 378 | 2026-09-21T00:09:37Z | `643c0d9a52417f27…` |
| `fixtures/analyst-objects/raw/analyst.tle` | mixed | 200 | 36792 | 2026-09-21T00:11:41Z | `3d3aac4567f7f709…` |
| `fixtures/analyst-objects/raw/analyst.csv` | mixed | 200 | 76633 | 2026-09-21T00:11:30Z | `e1d437ebf2a53ed9…` |
| `fixtures/analyst-objects/raw/analyst-81011-first.tle` | mixed | 200 | 168 | 2026-09-21T00:44:20Z | `f06539e94675d87b…` |
| `fixtures/analyst-objects/raw/analyst-81011-first.csv` | mixed | 200 | 357 | 2026-09-21T00:44:23Z | `339ed35b58d6300d…` |
| `fixtures/bstar-and-derivative-forms/raw/decaying.tle` | mixed | 200 | 13272 | 2026-09-21T00:11:44Z | `90b5925c40cec7ac…` |
| `fixtures/bstar-and-derivative-forms/raw/decaying.csv` | mixed | 200 | 13599 | 2026-09-21T00:11:46Z | `e40fb090eb7d485d…` |
| `fixtures/satcat-70000-cutoff/raw/gp-69999-first.tle` | mixed | 200 | 168 | 2026-09-21T00:44:29Z | `b7f96c3912c2445c…` |
| `fixtures/satcat-70000-cutoff/raw/gp-69999-first.csv` | mixed | 200 | 376 | 2026-09-21T00:44:33Z | `601736c2b121cea2…` |
| `fixtures/nine-digit-supgp-launch-nominals/raw/starlink-g15-27.tle` | mixed | 200 | 336 | 2026-09-21T00:08:32Z | `4c606834f41b486d…` |
| `fixtures/nine-digit-supgp-launch-nominals/raw/starlink-g15-27.csv` | mixed | 200 | 577 | 2026-09-21T00:08:23Z | `bedd85824461412b…` |

URLs (each requested once when the fixtures were built):

- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=25544&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=25544&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=69999&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=69999&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=81011&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=81011&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/gp.php?SPECIAL=DECAYING&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp.php?SPECIAL=DECAYING&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=starlink-g15-27&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=starlink-g15-27&FORMAT=TLE>

Expected values: `fixtures/tle-vs-omm-precision-loss/expected.json` (schema_version 1.0).
