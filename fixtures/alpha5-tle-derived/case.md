# alpha5-tle-derived

Derived Alpha-5 TLE lines rendered from real CelesTrak OMM records (letters A and T)

## Evidence basis

- The renderer that produced these lines applies a rendering rule (eccentricity truncated to 7 digits; BSTAR and second-derivative mantissa rounded half up to 5 digits) that was derived empirically from 304 CelesTrak TLE/OMM record pairs and is not documented in any specification we located. See case tle-vs-omm-precision-loss.
- The renderer was validated only against CelesTrak output for catalog numbers below 100000, because CelesTrak emits no Alpha-5 TLE at all. The Alpha-5 encoding step itself is corroborated by python-sgp4's independent implementation (all 604 derived lines decode to the source catalog number) and by the official Space-Track vectors.
- Provider corroboration of the encoding (D-070): on 2026-09-21 the project owner ran tools/verify_against_spacetrack.py against their own Space-Track account (44 records: current GP for 100000-100020 and 270000-270020, and the first historical record of 100000 and of 270449). Zero defects: every Alpha-5 field decoded to the queried catalog number, every line-2 field equalled line 1, and both observed letters (A and T) matched the derived encoding; where epochs matched, the international designator and elements agreed. No line was byte-identical, for rendering reasons that are not encoding differences: Space-Track writes a zero second derivative as 00000-0 (column 51, plus the checksum) where CelesTrak writes 00000+0, and Space-Track's line-2 eccentricity differs in its last one or two digits (columns 32-33) from CelesTrak's truncated rendering. No Space-Track data is in this repository; this paragraph describes the verification, not the data.

## What it tests

- alpha5-tle-parsing
- alpha5-letter-skip-rules

## How to read a failure

Derived, not provider output: real CelesTrak OMM records rendered into TLE layout with the Alpha-5 catalog field, using a renderer that reproduces all 304 CelesTrak TLE lines byte for byte. Only letters A (ids 100000-100789) and T (270000-270449) occur in real catalog numbers today; other letters are covered by vectors only. python-sgp4 2.27 decodes all 604 lines correctly, and the owner's Space-Track check (D-070, 44 records, 0 defects) found the same encoding for both letters; expect Space-Track's own lines to differ from these in the zero second-derivative sign and the last eccentricity digits, which are rendering conventions, not encoding.

## Checks

- **alpha5-decode** — An Alpha-5 catalog field decodes as (letter value)*10000 + digits with A=10 ... Z=33 and I, O unused; 'I', 'O' and lowercase are invalid.
- **tle-catalog-field-decodes** — Columns 3-7 of TLE lines 1 and 2 decode to the same integer (five digits, or Alpha-5 letter + four digits).
- **tle-checksums-valid** — Every TLE line 1 and line 2 is 69 characters and ends with the modulo-10 checksum (digits count their value, '-' counts 1, everything else 0).
- **tle-values-match-omm-within-tle-precision** — The TLE rendering equals the OMM values except: eccentricity truncated to 7 digits, BSTAR and second derivative rounded (half up) to a 5-digit mantissa, epoch at 1e-8 day resolution.

## Coverage

Provides:

- 604 Alpha-5 lines: 257 with letter A (ids 100000-100789), 347 with letter T (ids 270000-270449)

Gaps (stated explicitly for this case):

- letters B-H, J-N, P-S and U-Z appear in no real catalog number yet (the catalog is at ~100789 and the only other 6-digit block is 27xxxx); those letters are covered by vectors only
- these lines are derived, not provider output: CelesTrak serves no Alpha-5 and Space-Track data is not used
- renderer validation gap: the byte-for-byte validation (304/304) used only sub-100000 CelesTrak output, because CelesTrak emits no Alpha-5. The encoding step has since been corroborated against Space-Track output by the project owner (D-070: 44 records, 0 defects, letters A and T), but the derived lines are CelesTrak-style renderings and differ from Space-Track's own TLE lines in two conventions (zero second-derivative sign at column 51; eccentricity rounding versus truncation at columns 32-33), so they are not byte-identical to Space-Track output. No Space-Track data enters this repository; the public claim describes that verification, not the data.

## Library behaviour observed (docs/CROSSCHECK.md)

- python-sgp4 2.27 twoline2rv decodes all 604 derived Alpha-5 lines to the correct integer (from_alpha5).

## Ambiguities recorded

- **ecc-truncation-vs-mantissa-rounding** — CelesTrak's TLE rendering truncates eccentricity to 7 digits but rounds (half up) BSTAR and the second derivative to a 5-digit mantissa (304/304 CelesTrak records reproduced with these rules; 0 with the opposite rules). No document states either rule; treat as observed CelesTrak behaviour. It is not universal: in the owner's Space-Track verification run (D-070) Space-Track's TLE for the same epoch differed from the CelesTrak-rendered line in the last one or two eccentricity digits (columns 32-33), consistent with rounding, and wrote a zero second derivative as 00000-0 (column 51) where CelesTrak writes 00000+0.

## Sources

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `derived/alpha5-tle/alpha5-A-100000-saramago-first.tle` | stable | None | 168 | 2026-09-21T01:01:34Z | `686824ecd57ff4bc…` |
| `derived/alpha5-tle/alpha5-T-270449-analyst-first.tle` | stable | None | 168 | 2026-09-21T01:01:34Z | `74a8c9e508c0b062…` |
| `derived/alpha5-tle/alpha5-A-last-30-days-snapshot.tle` | stable | None | 43008 | 2026-09-21T01:01:34Z | `72e2845cdb484932…` |
| `derived/alpha5-tle/alpha5-T-analyst-27xxxx-snapshot.tle` | stable | None | 58128 | 2026-09-21T01:01:34Z | `f4868060a6ab61d3…` |

Expected values: `fixtures/alpha5-tle-derived/expected.json` (schema_version 1.0).
