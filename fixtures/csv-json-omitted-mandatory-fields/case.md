# csv-json-omitted-mandatory-fields

CelesTrak CSV and JSON omit the constant mandatory metadata keywords

## What it tests

- csv-json-defaults

## How to read a failure

CelesTrak CSV and JSON omit CENTER_NAME, REF_FRAME, TIME_SYSTEM and MEAN_ELEMENT_THEORY (constant for SGP4 data) and the header keywords. A parser that requires every CCSDS-mandatory keyword must default them (EARTH, TEME, UTC, SGP4) rather than reject the file. SupGP files add RMS and DATA_SOURCE, which must be ignored, not rejected.

## Checks

- **csv-json-omit-constant-metadata** — CelesTrak CSV/JSON carry no CENTER_NAME, REF_FRAME, TIME_SYSTEM or MEAN_ELEMENT_THEORY; parsers must default them (EARTH, TEME, UTC, SGP4) rather than fail.
- **supgp-extra-keys-tolerated** — SupGP CSV/JSON add non-OMM keys (RMS, DATA_SOURCE); parsers must ignore unknown keys rather than fail.

## Coverage

Provides:

- every CelesTrak CSV/JSON file lacks CENTER_NAME, REF_FRAME, TIME_SYSTEM, MEAN_ELEMENT_THEORY and the header keywords
- SupGP files add RMS and DATA_SOURCE

Gaps (stated explicitly for this case):

- none identified

## Ambiguities recorded

- **supgp-extra-keys** — SupGP CSV/JSON carry RMS and DATA_SOURCE, which are not OMM keywords (CCSDS 7.9.2.2 allows only Table 4-x keywords in an OMM); CelesTrak's CSV/JSON are OMM-keyword-based formats, not OMM instances, so this is a format extension rather than a violation. Parsers must tolerate unknown keys.

## Sources

The `raw/` files below are not in the repository: `tools/fetch.py` creates them on your machine, one request per URL under CelesTrak's usage policy, and until they exist the runner reports this case's checks as skipped, not failed.

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `fixtures/epoch-year-19xx/raw/iss-first.csv` | mixed | 200 | 368 | 2026-09-21T00:43:39Z | `cbdd6a2e36b97d54…` |
| `fixtures/epoch-year-19xx/raw/iss-first.json` | mixed | 200 | 414 | 2026-09-21T00:11:51Z | `e18ebbe14d38ae61…` |
| `fixtures/baseline-iss-five-formats/raw/iss.csv` | mixed | 200 | 378 | 2026-09-21T00:09:37Z | `643c0d9a52417f27…` |
| `fixtures/baseline-iss-five-formats/raw/iss.json` | mixed | 200 | 425 | 2026-09-21T00:09:40Z | `d84b9c1d500d1613…` |
| `fixtures/six-digit-omm-saramago/raw/saramago-first.csv` | mixed | 200 | 374 | 2026-09-21T00:43:55Z | `2a1913dc0c5e2bab…` |
| `fixtures/six-digit-omm-saramago/raw/saramago-first.json` | mixed | 200 | 420 | 2026-09-21T00:43:58Z | `1d04dc3b4e49d6f7…` |
| `fixtures/analyst-objects/raw/analyst.csv` | mixed | 200 | 76633 | 2026-09-21T00:11:30Z | `e1d437ebf2a53ed9…` |
| `fixtures/analyst-objects/raw/analyst.json` | mixed | 200 | 228966 | 2026-09-21T00:11:33Z | `f3a4773680d66ed3…` |
| `fixtures/tle-omits-six-digit-objects/raw/last-30-days.csv` | mixed | 200 | 39336 | 2026-09-21T00:10:07Z | `bc9a5dff288a26d3…` |
| `fixtures/bstar-and-derivative-forms/raw/decaying.csv` | mixed | 200 | 13599 | 2026-09-21T00:11:46Z | `e40fb090eb7d485d…` |
| `fixtures/nine-digit-supgp-launch-nominals/raw/starlink-38381-799501621.csv` | mixed | 200 | 407 | 2026-09-21T00:14:18Z | `6a44cde5358a4e30…` |
| `fixtures/nine-digit-supgp-launch-nominals/raw/starlink-38381-799501621.json` | mixed | 200 | 462 | 2026-09-21T00:14:20Z | `d8fdca20c5e39499…` |

URLs (each requested once when the fixtures were built):

- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=100000&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=100000&FORMAT=JSON>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=25544&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=25544&FORMAT=JSON>
- <https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=JSON>
- <https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=JSON>
- <https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp.php?SPECIAL=DECAYING&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?CATNR=799501621&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?CATNR=799501621&FORMAT=JSON>

Expected values: `fixtures/csv-json-omitted-mandatory-fields/expected.json` (schema_version 1.0).
