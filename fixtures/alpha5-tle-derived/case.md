# alpha5-tle-derived

Derived Alpha-5 TLE lines rendered from real CelesTrak OMM records (letters A and T), plus synthetic-derived sets for every letter and every two-digit epoch year

## Evidence basis

- The renderer that produced these lines applies a rendering rule (eccentricity truncated to 7 digits; BSTAR and second-derivative mantissa rounded half up to 5 digits) that was derived empirically from 304 TLE sets fetched from CelesTrak, each with its OMM record, and is not documented in any specification we located. See case tle-vs-omm-precision-loss.
- The renderer was validated only against CelesTrak output for catalog numbers below 100000, because CelesTrak emits no Alpha-5 TLE at all. The Alpha-5 encoding step itself is corroborated by python-sgp4's independent implementation (all 604 derived TLE sets decode to the source catalog number) and by the official Space-Track vectors.
- Provider corroboration of the encoding (D-070): on 2026-09-21 the project owner ran tools/verify_against_spacetrack.py against their own Space-Track account (44 records: current GP for 100000-100020 and 270000-270020, and the first historical record of 100000 and of 270449). Zero defects: every Alpha-5 field decoded to the queried catalog number, every line-2 field equalled line 1, and both observed letters (A and T) matched the derived encoding; where epochs matched, the international designator and elements agreed. No line was byte-identical, for rendering reasons that are not encoding differences: Space-Track writes a zero second derivative as 00000-0 (column 51, plus the checksum) where CelesTrak writes 00000+0, and Space-Track's line-2 eccentricity differs in its last one or two digits (columns 32-33) from CelesTrak's truncated rendering. No Space-Track data is in this repository; this paragraph describes the verification, not the data.

## What it tests

- alpha5-tle-parsing
- alpha5-letter-skip-rules

## How to read a failure

Derived, not provider output: real CelesTrak OMM records rendered into TLE layout with the Alpha-5 catalog field, using a renderer that reproduces all 304 fetched CelesTrak TLE sets byte for byte. Only letters A (ids 100000-100789) and T (270000-270449) occur in real catalog numbers today; other letters are covered by vectors only. python-sgp4 2.27 decodes all 604 derived TLE sets correctly, and the owner's Space-Track check (D-070, 44 records, 0 defects) found the same encoding for both letters; expect Space-Track's own lines to differ from these in the zero second-derivative sign and the last eccentricity digits, which are rendering conventions, not encoding.

## Checks

- **tle-catalog-field-decodes** — Columns 3-7 of TLE lines 1 and 2 decode to the same integer (five digits, or Alpha-5 letter + four digits).
- **tle-checksums-valid** — Every TLE line 1 and line 2 is 69 characters and ends with the modulo-10 checksum (ASCII digits count their value, '-' counts 1, everything else 0); a line a writer returns must also be ASCII throughout (D-325).
- **catalog-number-is-integer** — NORAD_CAT_ID parses as an integer in every OMM format, including values of six and nine digits, and a ten-digit value is rejected (CCSDS allows up to nine digits); leading zeros and an explicit '+' are legal in KVN.

## Coverage

Provides:

- 604 Alpha-5 TLE sets derived from real records, each a name line, line 1 and line 2 (1,208 element lines, 1,812 lines in the four files): 257 with letter A (ids 100000-100789), 347 with letter T (ids 270000-270449)
- 46 synthetic-derived TLE sets, the lowest and highest id of each of the 24 Alpha-5 letters less the two ids real records hold (100000, 270000): SARAMAGO's first-record elements rendered with the catalog number replaced and the mean anomaly stepped by 7 degrees from set to set, so each set's elements are its own, each id a specification vector, not a catalogued object (D-096, D-125, D-286, D-300, D-372)
- 100 synthetic-derived TLE sets, one per two-digit epoch year 00-99 (ids 330100-330199), the same elements with the epoch's year replaced: a reader's pivot is graded on data wherever it sits (D-300)

Gaps (stated explicitly for this case):

- letters B-H, J-N, P-S and U-Z appear in no real catalog number yet (the catalog is at ~100789 and the only other 6-digit block is 27xxxx); the parse path reads them through the synthetic-derived file and the hooks through the vectors, and no fabricated data poses as catalog data: D-016 stands, with every synthetic input naming its source record (D-286)
- these lines are derived, not provider output: CelesTrak serves no Alpha-5 and Space-Track data is not used
- renderer validation gap: the byte-for-byte validation (304 of 304 fetched TLE sets) used only sub-100000 CelesTrak output, because CelesTrak emits no Alpha-5. The encoding step has since been corroborated against Space-Track output by the project owner (D-070: 44 records, 0 defects, letters A and T), but the derived lines are rendered with CelesTrak's eccentricity truncation and differ from Space-Track's own TLE lines in two conventions (zero second-derivative sign at column 51; eccentricity rounding versus truncation at columns 32-33), so they are not byte-identical to Space-Track output. No Space-Track data enters this repository; the public claim describes that verification, not the data.

## Library behaviour observed (docs/CROSSCHECK.md)

- python-sgp4 2.27 twoline2rv decodes all 604 derived Alpha-5 TLE sets to the correct integer (from_alpha5).

## Ambiguities recorded

- **ecc-truncation-vs-mantissa-rounding** — CelesTrak's TLE rendering truncates eccentricity to 7 digits but rounds (half up) BSTAR and the second derivative to a 5-digit mantissa (304 of 304 fetched TLE sets reproduced with these rules; 0 with the opposite rules). No document states either rule; treat as observed CelesTrak behaviour. It is not universal: in the owner's Space-Track verification run (D-070) Space-Track's TLE for the same epoch differed from the CelesTrak-rendered line in the last one or two eccentricity digits (columns 32-33), consistent with rounding, and wrote a zero second derivative as 00000-0 (column 51) where CelesTrak writes 00000+0.

## Sources

Every file of this case ships with the repository; nothing is fetched.

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `derived/alpha5-tle/alpha5-A-100000-saramago-first.tle` | stable | none: derived file shipped with the repository | 168 | generated 2026-09-21T01:01:34Z | `686824ecd57ff4bc…` |
| `derived/alpha5-tle/alpha5-T-270449-analyst-first.tle` | stable | none: derived file shipped with the repository | 168 | generated 2026-09-21T01:01:34Z | `74a8c9e508c0b062…` |
| `derived/alpha5-tle/alpha5-A-last-30-days-snapshot.tle` | stable | none: derived file shipped with the repository | 43008 | generated 2026-09-21T01:01:34Z | `72e2845cdb484932…` |
| `derived/alpha5-tle/alpha5-T-analyst-27xxxx-snapshot.tle` | stable | none: derived file shipped with the repository | 58128 | generated 2026-09-21T01:01:34Z | `f4868060a6ab61d3…` |
| `derived/alpha5-tle/alpha5-synthetic-letters.tle` | stable | none: derived file shipped with the repository | 7728 | generated 2026-10-29T01:39:43Z | `1592e5efd9f1178e…` |
| `derived/alpha5-tle/alpha5-synthetic-epoch-years.tle` | stable | none: derived file shipped with the repository | 16800 | generated 2026-10-10T02:16:22Z | `de427c200042f372…` |

Expected values: `fixtures/alpha5-tle-derived/expected.json` (schema_version 1.0).
