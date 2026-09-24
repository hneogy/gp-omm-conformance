# supgp-celestrak-classification-c

CelesTrak supplemental GP: classification C, element set 0, RMS/DATA_SOURCE columns, 72000-series ids

## What it tests

- supgp-extra-fields
- classification-c

## How to read a failure

CelesTrak supplemental records differ from the GP records of the 18th Space Defense Squadron (18 SDS): CLASSIFICATION_TYPE C, ELEMENT_SET_NO 0, extra RMS and DATA_SOURCE columns, 72000-series ids (the use of the 70000-79999 block is described only by a secondary source), and a TLE epoch rounded to the TLE's 864 microsecond resolution. Parsers that hard-code 'U', reject unknown columns, or compare epochs exactly will fail.

## Checks

- **supgp-extra-keys-tolerated** — SupGP CSV/JSON add non-OMM keys (RMS, DATA_SOURCE); parsers must ignore unknown keys rather than fail.
- **classification-c** — CLASSIFICATION_TYPE may be 'C' (CelesTrak supplemental) rather than 'U'.
- **element-set-zero-and-rev-one** — ELEMENT_SET_NO may be 0 and REV_AT_EPOCH may be 1 or 0.
- **omm-formats-agree** — For the same object and snapshot, CSV, JSON, XML and KVN yield identical canonical values for every OMM keyword present in all of them.
- **tle-values-match-omm-within-tle-precision** — The TLE rendering equals the OMM values except: eccentricity truncated to 7 digits, BSTAR and second derivative rounded (half up) to a 5-digit mantissa, epoch at 1e-8 day resolution.
- **tle-checksums-valid** — Every TLE line 1 and line 2 is 69 characters and ends with the modulo-10 checksum (digits count their value, '-' counts 1, everything else 0).

## Coverage

Provides:

- two SupGP records (stack 72000 and single 72001) in five formats
- TLE epoch rounded to 1e-8 day (86 us from the CSV epoch)
- OBJECT_ID 2026-219A shared by the stack nominal and a per-satellite nominal (799501621)

Gaps (stated explicitly for this case):

- perishable: this post-deployment file is replaced after cataloguing
- the meaning of the 72000-series ids (the 70000-79999 block) is described only by a secondary source (RESEARCH.md §1); primary sources cover only the 80000-89999 analyst range and the 69999 end of the legacy range

## Library behaviour observed (docs/CROSSCHECK.md)

- python-sgp4 2.27 sgp4.omm.initialize assigns CLASSIFICATION_TYPE and then calls sgp4init, which resets classification to 'U'; SupGP records with classification 'C' come back as 'U' (twoline2rv preserves it).

## Ambiguities recorded

- **supgp-extra-keys** — SupGP CSV/JSON carry RMS and DATA_SOURCE, which are not OMM keywords (CCSDS 7.9.2.2 allows only Table 4-x keywords in an OMM); CelesTrak's CSV/JSON are OMM-keyword-based formats, not OMM instances, so this is a format extension rather than a violation. Parsers must tolerate unknown keys.
- **tle-epoch-resolution** — The TLE epoch has 1e-8 day (864 microsecond) resolution. CelesTrak GP epochs convert exactly between the two representations; SupGP epochs do not (86 microsecond difference observed), so a TLE->OMM epoch comparison needs a tolerance of half the TLE resolution.
- **supgp-redistribution** — SupGP data derives from operator-provided data (some explicitly 'with permission' to CelesTrak). Under the corpus design no raw bytes are shipped; the snapshot values for one SupGP record are published as a dated reference and may be removed by the owner before publication.

## Sources

The `raw/` files below are not in the repository: `tools/fetch.py` creates them on your machine, one request per URL under CelesTrak's usage policy, and until they exist the runner reports this case's checks as skipped, not failed.

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `fixtures/nine-digit-supgp-launch-nominals/raw/starlink-g15-27.csv` | live | 200 | 577 | 2026-09-21T00:08:23Z | `bedd85824461412b…` |
| `fixtures/nine-digit-supgp-launch-nominals/raw/starlink-g15-27.json` | live | 200 | 926 | 2026-09-21T00:08:25Z | `97926cbbe07f3517…` |
| `fixtures/nine-digit-supgp-launch-nominals/raw/starlink-g15-27.xml` | live | 200 | 2201 | 2026-09-21T00:08:27Z | `92e227468743d56c…` |
| `fixtures/nine-digit-supgp-launch-nominals/raw/starlink-g15-27.kvn` | live | 200 | 1272 | 2026-09-21T00:08:30Z | `40e31f9ccaab24f1…` |
| `fixtures/nine-digit-supgp-launch-nominals/raw/starlink-g15-27.tle` | live | 200 | 336 | 2026-09-21T00:08:32Z | `4c606834f41b486d…` |

URLs (each requested once when the fixtures were built):

- <https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=starlink-g15-27&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=starlink-g15-27&FORMAT=JSON>
- <https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=starlink-g15-27&FORMAT=KVN>
- <https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=starlink-g15-27&FORMAT=TLE>
- <https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=starlink-g15-27&FORMAT=XML>

Expected values: `fixtures/supgp-celestrak-classification-c/expected.json` (schema_version 1.0).
