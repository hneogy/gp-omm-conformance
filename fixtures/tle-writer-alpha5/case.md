# tle-writer-alpha5

Writing TLEs across the five-digit boundary: Alpha-5 catalog field, valid lines, refusal of numbers the format cannot carry, round trip

## Evidence basis

- Inputs are records already frozen in this corpus (the v0.1.0 expected values of stable-tier sources): the 604 derived Alpha-5 records (603 distinct ids, letters A and T), the first ISS record (1998 epoch, negative first derivative, non-zero second derivative, zero BSTAR), the first record of 69999 (negative BSTAR and first derivative) and the first record of analyst 81011 (blank international designator, empty OBJECT_ID). No new provider request and no new raw bytes.
- Three inputs are synthetic-derived (PLAN.md section 2.1; owner approval 2026-09-22, DECISIONS D-096): the SARAMAGO first record with NORAD_CAT_ID replaced by 340000, 799501621 and -1, the values of vectors/alpha5.json encode_unrepresentable. The elements are real; the ids are specification vectors that no catalogued object carries. The correct output for them is a refusal.
- The precision rule (a written field equals the input quantised at the field's resolution by truncation or by rounding half up) rests on the evidence of tle-vs-omm-precision-loss: CelesTrak truncates the eccentricity and rounds the mantissas (304/304 records), Space-Track rounds the eccentricity (D-070, D-071). A writer may follow either provider; the corpus reports which convention it observed.

## What it tests

- alpha5-tle-writing
- alpha5-range
- tle-checksum

## How to read a failure

The writer-side mirror of the corpus. Each input record is handed to the adapter's write_tle hook (or to --write-cmd) and the lines it returns are checked: columns 3-7 must carry five digits below 100000 and Alpha-5 from 100000 (A0000 ... Z9999) on both lines; both lines must be 69 characters with a valid checksum (a letter counts 0); every field must sit in its fixed columns (tle-writer-column-layout: a left-justified value with a recomputed checksum has the right length and checksum and still fails); read back through the corpus reference reader, the element fields must equal the input at the field's resolution, by truncation or by rounding half up (CelesTrak truncates the eccentricity, Space-Track rounds it; both are accepted and the convention seen is reported). Three inputs carry numbers the TLE catalog field cannot represent (340000, 799501621, -1): the correct output for them is a refusal, an error and no lines, because those numbers belong in the OMM formats; tle-writer-refuses-unencodable passes on a refusal and fails when lines are written with a six-digit, blank or otherwise invalid field. Fields a fitting tool regenerates (first and second derivative, element set, revolution, classification, designator, name) and the exponent sign written for a zero second derivative are reported for information only. A writer that formats the catalog number with an integer conversion (%05d) fails on every Alpha-5 input: six digits, a 70-character line and a checksum over shifted columns. A file written by a tool that cannot be wrapped by an adapter is checked with python -m gpconf check-tle FILE [--against RECORDS], which applies the same format checks to every record in the file and the round trip when the source records are supplied.

## Checks

- **tle-checksums-valid** — Every TLE line 1 and line 2 is 69 characters and ends with the modulo-10 checksum (digits count their value, '-' counts 1, everything else 0).
- **tle-writer-catalog-field** — A TLE writer puts the catalog number in columns 3-7 of both lines as five digits with leading zeros below 100000 and, from 100000 to 339999, as Alpha-5 (letter value 10-33, A=10 ... Z=33 with I and O never used, then the last four digits); both lines carry the same field.
- **tle-writer-column-layout** — Every field of a written TLE sits in its fixed columns: on line 1 the decimal points at columns 24 and 35 and the separators at 2, 9, 18, 33, 44, 53, 62 and 64; on line 2 the decimal points at 12, 21, 38, 47 and 55, the separators at 2, 8, 17, 26, 34, 43 and 52, seven eccentricity digits, right-justified element set and revolution numbers. A left-justified value with a recomputed checksum has the right length and checksum and still fails this check.
- **tle-writer-round-trip** — The written lines, read back by the corpus reference reader, reproduce the record's epoch, mean motion, eccentricity, inclination, RA of ascending node, argument of pericenter, mean anomaly and BSTAR at each field's resolution, quantised by truncation or by rounding half up (CelesTrak truncates the eccentricity, Space-Track rounds it; either is accepted and the convention observed is reported).
- **tle-writer-refuses-unencodable** — A TLE catalog field cannot represent a number above 339999 (Z9999) or below 0, so the correct output for such a record is a refusal: an error and no lines. Those numbers belong in the OMM formats. The check passes when the writer refuses and fails when it writes lines with a six-digit, blank or otherwise invalid field.
- **tle-writer-secondary-fields** — Whether the writer preserves, zeroes or drops MEAN_MOTION_DOT, MEAN_MOTION_DDOT, ELEMENT_SET_NO, REV_AT_EPOCH, CLASSIFICATION_TYPE, OBJECT_ID and OBJECT_NAME, and which exponent sign it writes for a zero second derivative (CelesTrak +, Space-Track -). Reported for information, never failed: orbit-fitting tools regenerate these fields by design.
- **tle-writer-matches-provider-rendering** — Per field, how many written fields are byte-identical to the provider's rendering of the same record (CelesTrak's TLE line, or the corpus's CelesTrak-style derived line). Information only: an equivalent rendering under the other provider's convention is not a defect.

## Coverage

Provides:

- 606 real records as writer inputs: 603 distinct Alpha-5 ids (257 with letter A, 346 with letter T; the 604 derived lines carry 270449 twice, from its first record and from the analyst snapshot) and three five-digit ids (25544 at a 1998 epoch, 69999, 81011)
- a 1998 epoch, a negative first derivative, a non-zero second derivative, zero and negative BSTAR, a blank international designator, an empty OBJECT_ID
- three numbers the TLE catalog field cannot represent (340000, 799501621, -1), for which the correct output is a refusal
- provider-rendered field substrings for the three five-digit records and the CelesTrak-style derived fields for the 604 Alpha-5 records, for an information-only byte comparison

Gaps (stated explicitly for this case):

- letters B-S and U-Z occur in no real catalog number; a writer's encoding of those letters is covered by the alpha5_encode vectors only
- no input has a BSTAR or second derivative with a positive exponent
- no rounding tie at the last kept digit occurs in the inputs, so half-up versus half-even rounding is not distinguished for writers either
- no output of an external tool is shipped; strf's rffit was exercised only at function level outside this repository (DECISIONS D-097) and has no adapter because it is an interactive X11 program

## Library behaviour observed

- python-sgp4 2.27, exporter.export_tle after omm.initialize (tests/adapters/sgp4_adapter.py, run 2026-09-22): passes every real record, 606 of 606 (valid 69-character lines with correct checksums, correct Alpha-5 fields A0000 ... T0449, round trip at the field resolution), preserves the first derivative, rounds the eccentricity (Space-Track style) and writes a zero second derivative as 00000-0. It refuses both real-range unrepresentable ids, 340000 and 799501621, in omm.initialize (ValueError: satellite number cannot exceed 339999), the correct output. Its only failing input is the synthetic -1 vector: to_alpha5 has no lower bound (as alpha5-encoding-vectors already records) and the library writes a line with the field -0001. The case status 'fail (1 fail)' in docs/FAILURES.md refers to that single synthetic input and to nothing else.
- strf (rffit, upstream HEAD 92d2425 of 2026-03-06): format_tle (rffit.c lines 111-149) writes the catalog field through number_to_alpha5 (satutl.c lines 45-58). Exercised at function level only, in an isolated scratch build outside this repository (the rffit binary needs PGPLOT, X11 and GSL and was not built; nothing was installed), it encodes 100000-339999 correctly (A0000; J0000 after the I skip; P0000 after the O skip; T0449; Z9999) and produces 69-character lines with valid checksums for real records; it rounds the eccentricity and the BSTAR mantissa and zeroes the first derivative, the element set and the revolution number. For 340000 and above, and for nine-digit numbers, the helper returns an empty string and the lines carry five blank characters in columns 3-7, still 69 characters with a valid checksum; that path is reachable only through rffit's interactive Satellite ID entry (rffit.c line 769), never from a loaded catalog, whose decoder cannot exceed 339999. No adapter exists: rffit is an interactive X11 program with no non-interactive write path (DECISIONS D-097).

## Ambiguities recorded

- **ecc-truncation-vs-mantissa-rounding** — CelesTrak's TLE rendering truncates eccentricity to 7 digits but rounds (half up) BSTAR and the second derivative to a 5-digit mantissa (304/304 CelesTrak records reproduced with these rules; 0 with the opposite rules). No document states either rule; treat as observed CelesTrak behaviour. It is not universal: in the owner's Space-Track verification run (D-070) Space-Track's TLE for the same epoch differed from the CelesTrak-rendered line in the last one or two eccentricity digits (columns 32-33), consistent with rounding, and wrote a zero second derivative as 00000-0 (column 51) where CelesTrak writes 00000+0.

## Sources

| file | tier | HTTP | bytes | retrieved (UTC) | sha256 |
|---|---|---|---|---|---|
| `derived/alpha5-tle/alpha5-A-100000-saramago-first.tle` | stable | None | 168 | 2026-09-21T01:01:34Z | `686824ecd57ff4bc…` |
| `derived/alpha5-tle/alpha5-A-last-30-days-snapshot.tle` | stable | None | 43008 | 2026-09-21T01:01:34Z | `72e2845cdb484932…` |
| `derived/alpha5-tle/alpha5-T-270449-analyst-first.tle` | stable | None | 168 | 2026-09-21T01:01:34Z | `74a8c9e508c0b062…` |
| `derived/alpha5-tle/alpha5-T-analyst-27xxxx-snapshot.tle` | stable | None | 58128 | 2026-09-21T01:01:34Z | `f4868060a6ab61d3…` |
| `fixtures/analyst-objects/raw/analyst-270449-first.csv` | stable | 200 | 363 | 2026-09-21T00:44:08Z | `f9caeec84ba49dc0…` |
| `fixtures/analyst-objects/raw/analyst-81011-first.csv` | stable | 200 | 357 | 2026-09-21T00:44:23Z | `339ed35b58d6300d…` |
| `fixtures/analyst-objects/raw/analyst.csv` | live | 200 | 76633 | 2026-09-21T00:11:30Z | `e1d437ebf2a53ed9…` |
| `fixtures/epoch-year-19xx/raw/iss-first.csv` | stable | 200 | 368 | 2026-09-21T00:43:39Z | `cbdd6a2e36b97d54…` |
| `fixtures/satcat-70000-cutoff/raw/gp-69999-first.csv` | stable | 200 | 376 | 2026-09-21T00:44:33Z | `601736c2b121cea2…` |
| `fixtures/six-digit-omm-saramago/raw/saramago-first.csv` | stable | 200 | 374 | 2026-09-21T00:43:55Z | `2a1913dc0c5e2bab…` |
| `fixtures/tle-omits-six-digit-objects/raw/last-30-days.csv` | live | 200 | 39336 | 2026-09-21T00:10:07Z | `bc9a5dff288a26d3…` |

URLs (each requested once when the fixtures were built):

- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=100000&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=25544&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=270449&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=69999&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp-first.php?CATNR=81011&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=CSV>
- <https://celestrak.org/NORAD/elements/gp.php?GROUP=last-30-days&FORMAT=CSV>

Expected values: `fixtures/tle-writer-alpha5/expected.json` (schema_version 1.0).
