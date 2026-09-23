# mean-motion-derivative-convention

MEAN_MOTION_DOT / MEAN_MOTION_DDOT in the OMM equal the TLE fields as printed

## What it tests

- mmdot-convention

## How to read a failure

In 304 of 304 pairs the OMM MEAN_MOTION_DOT equals the TLE first-derivative field as printed, i.e. the OMM carries the TLE convention (ndot/2, nddot/6). A parser that treats the OMM value as the true derivative is off by a factor of 2 (and 6). The standard leaves this open (4.2.4.7 NOTE 2); this case records what the provider does.

## Checks

- **mmdot-is-tle-field-value** — OMM MEAN_MOTION_DOT equals the TLE first-derivative field as printed (the TLE 'ndot/2' convention); MEAN_MOTION_DDOT likewise equals the TLE second-derivative field.

## Coverage

Provides:

- 304 TLE/OMM record pairs compared

Gaps (stated explicitly for this case):

- no record with a non-zero second derivative whose OMM text has more than 5 significant digits was observed, so the DDOT comparison is exact-equality only

## Ambiguities recorded

- **mmdot-convention** — CCSDS 4.2.4.7 NOTE 2 says TLE-sourced MEAN_MOTION_DOT/DDOT 'need to be divided by 2 and 6 respectively' but does not say which convention the OMM value carries. Observed: CelesTrak's OMM values equal the TLE fields as printed (304/304 records), i.e. the halved / sixth-ed values. Parsers converting to true derivatives must multiply by 2 and 6.

## Sources

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

Expected values: `fixtures/mean-motion-derivative-convention/expected.json` (schema_version 1.0).
