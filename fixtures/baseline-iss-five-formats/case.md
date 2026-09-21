# baseline-iss-five-formats

ISS current GP record: the same object in TLE, 2LE, CSV, JSON, JSON-PRETTY, XML and KVN (live)

## What it tests

- same-object-all-formats
- 2-digit-epoch-year
- bstar-implicit-decimal

## How to read a failure

A live snapshot of one well-known object. If your fetched bytes match the recorded SHA-256, the exact values apply; otherwise the structural checks apply (seven renderings agree, TLE checksums valid, CSV/JSON defaults). Do not expect the TLE eccentricity and BSTAR to equal the OMM values digit for digit; see tle-vs-omm-precision-loss.

## Checks

- **omm-formats-agree** — For the same object and snapshot, CSV, JSON, XML and KVN yield identical canonical values for every OMM keyword present in all of them.
- **tle-values-match-omm-within-tle-precision** — The TLE rendering equals the OMM values except: eccentricity truncated to 7 digits, BSTAR and second derivative rounded (half up) to a 5-digit mantissa, epoch at 1e-8 day resolution.
- **tle-checksums-valid** — Every TLE line 1 and line 2 is 69 characters and ends with the modulo-10 checksum (digits count their value, '-' counts 1, everything else 0).
- **two-digit-year-pivot** — TLE epoch years 57-99 map to 1957-1999 and 00-56 to 2000-2056; the resulting ISO epoch equals the OMM EPOCH string.
- **csv-json-omit-constant-metadata** — CelesTrak CSV/JSON carry no CENTER_NAME, REF_FRAME, TIME_SYSTEM or MEAN_ELEMENT_THEORY; parsers must default them (EARTH, TEME, UTC, SGP4) rather than fail.
- **xml-ndm-wrapper-omm-2.0** — CelesTrak XML has an <ndm> root containing one <omm> per record with id=CCSDS_OMM_VERS and version=2.0; CREATION_DATE and ORIGINATOR elements are present but empty.
- **kvn-blank-mandatory-values** — CelesTrak KVN writes CREATION_DATE and ORIGINATOR with blank values and blank OBJECT_ID for analyst objects; MEAN_ELEMENT_THEORY is 'SGP/SGP4'.
- **leading-dot-decimals** — CSV, KVN and XML values may start with '.' or '-.' (no leading zero) and use 'E' exponents; JSON carries numbers.

## Coverage

Provides:

- a current 5-digit object in every rendering
- eccentricity with 8 OMM digits truncated to 7 in the TLE
- BSTAR with 8 OMM digits rounded to 5 in the TLE

Gaps (stated explicitly for this case):

- live source: a user's fetch returns a different epoch; only structural checks apply unless the SHA-256 matches

## Ambiguities recorded

- **ecc-truncation-vs-mantissa-rounding** — CelesTrak's TLE rendering truncates eccentricity to 7 digits but rounds (half up) BSTAR and the second derivative to a 5-digit mantissa (304/304 CelesTrak records reproduced with these rules; 0 with the opposite rules). No document states either rule; treat as observed CelesTrak behaviour. It is not universal: in the owner's Space-Track verification run (D-070) Space-Track's TLE for the same epoch differed from the CelesTrak-rendered line in the last one or two eccentricity digits (columns 32-33), consistent with rounding, and wrote a zero second derivative as 00000-0 (column 51) where CelesTrak writes 00000+0.
- **mmdot-convention** — CCSDS 4.2.4.7 NOTE 2 says TLE-sourced MEAN_MOTION_DOT/DDOT 'need to be divided by 2 and 6 respectively' but does not say which convention the OMM value carries. Observed: CelesTrak's OMM values equal the TLE fields as printed (301/301 records), i.e. the halved / sixth-ed values. Parsers converting to true derivatives must multiply by 2 and 6.

## Sources

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `fixtures/baseline-iss-five-formats/raw/iss.tle` | live | 200 | 168 | 2026-09-21T00:09:33Z | `674ea527c1ff8a70…` |
| `fixtures/baseline-iss-five-formats/raw/iss.2le` | live | 200 | 142 | 2026-09-21T00:09:35Z | `8800ed02add033af…` |
| `fixtures/baseline-iss-five-formats/raw/iss.csv` | live | 200 | 378 | 2026-09-21T00:09:37Z | `643c0d9a52417f27…` |
| `fixtures/baseline-iss-five-formats/raw/iss.json` | live | 200 | 425 | 2026-09-21T00:09:40Z | `d84b9c1d500d1613…` |
| `fixtures/baseline-iss-five-formats/raw/iss.pretty.json` | live | 200 | 528 | 2026-09-21T00:09:42Z | `cf4e1c6d118e322f…` |
| `fixtures/baseline-iss-five-formats/raw/iss.xml` | live | 200 | 1208 | 2026-09-21T00:09:45Z | `1aea7dbbba3f0ce8…` |
| `fixtures/baseline-iss-five-formats/raw/iss.kvn` | live | 200 | 636 | 2026-09-21T00:09:47Z | `cc31f171ca83f1b7…` |

URLs (each requested once when the fixtures were built):

- <https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=2LE>
- <https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=JSON>
- <https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=JSON-PRETTY>
- <https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=KVN>
- <https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=XML>

Expected values: `fixtures/baseline-iss-five-formats/expected.json` (schema_version 1.0).
