# Corpus manifest (0.2.0)

Generated 2026-09-23T04:11:38Z by `tools/make_manifest.py`. Machine-readable form: `manifest.json`. Decisions and reversals: `DECISIONS.md`.

No raw provider files are shipped. Each case lists the exact source URLs, retrieval times and SHA-256 hashes of the files we tested; `tools/fetch.py` rebuilds them on your machine under CelesTrak's usage policy (each URL once, cached, never looped).

| # | case | kind | records | sources (stable/live) | coverage gaps |
|---|---|---|---|---|---|
| 1 | `epoch-year-19xx` | gp | 1 | 7/0 | 1 |
| 2 | `baseline-iss-five-formats` | gp | 1 | 0/7 | 1 |
| 3 | `six-digit-omm-saramago` | gp | 2 | 5/7 | 1 |
| 4 | `tle-omits-six-digit-objects` | gp | 256 | 0/3 | 1 |
| 5 | `analyst-objects` | gp | 567 | 8/6 | 2 |
| 6 | `nine-digit-supgp-launch-nominals` | gp | 28 | 0/6 | 2 |
| 7 | `supgp-celestrak-classification-c` | gp | 2 | 0/5 | 2 |
| 8 | `bstar-and-derivative-forms` | gp | 83 | 2/3 | 2 |
| 9 | `satcat-70000-cutoff` | satcat | 0 | 0/7 | 1 |
| 10 | `csv-json-omitted-mandatory-fields` | facts | 0 | 0/0 | 0 |
| 11 | `mean-motion-derivative-convention` | pairs | 0 | 0/0 | 1 |
| 12 | `tle-vs-omm-precision-loss` | pairs | 0 | 0/0 | 2 |
| 13 | `omm-xml-schema` | xml | 0 | 0/0 | 1 |
| 14 | `alpha5-encoding-vectors` | vectors | 0 | 4/0 | 1 |
| 15 | `alpha5-tle-derived` | derived-tle | 604 | 4/0 | 3 |
| 16 | `kvn-syntax-variants` | derived-kvn | 6 | 6/0 | 2 |
| 17 | `tle-writer-alpha5` | writer | 609 | 9/2 | 4 |

The records column sums the record counts of a case's source files: `analyst-objects` counts the 565 group records plus the two single-object first fetches (567).

## 1. `epoch-year-19xx`

ISS first GP record (1998): two-digit epoch year 98, seven renderings of one record

Tests: 2-digit-epoch-year, same-object-all-formats, bstar-implicit-decimal, negative-ndot, nonzero-nddot

Coverage gaps:

- the 00-56 branch is covered only by 2026 records elsewhere; no record near the 56/57 boundary exists

## 2. `baseline-iss-five-formats`

ISS current GP record: the same object in TLE, 2LE, CSV, JSON, JSON-PRETTY, XML and KVN (live)

Tests: same-object-all-formats, 2-digit-epoch-year, bstar-implicit-decimal

Coverage gaps:

- live source: a user's fetch returns a different epoch; only structural checks apply unless the SHA-256 matches

## 3. `six-digit-omm-saramago`

Catalog number 100000 (SARAMAGO): first 6-digit object, OMM formats only, TLE unavailable

Tests: 6-digit-catalog-number, tle-unavailable-above-99999, same-object-all-omm-formats

Coverage gaps:

- only one object; other 6-digit objects are in last-30-days and analyst cases

## 4. `tle-omits-six-digit-objects`

A group with only 6-digit objects: OMM formats return 256 records, the TLE request returns HTTP 404

Tests: tle-unavailable-above-99999, 6-digit-catalog-number

Coverage gaps:

- window-dependent: once objects below 100000 re-enter the 30-day window the TLE request will return data again; the structural check covers both outcomes

## 5. `analyst-objects`

Analyst objects: empty OBJECT_ID, OBJECT_NAME UNKNOWN, 8xxxx and 27xxxx ids, TLE keeps only the 5-digit ones

Tests: analyst-objects-no-object-id, 6-digit-catalog-number, tle-unavailable-above-99999

Coverage gaps:

- no analyst record with an empty OBJECT_NAME was observed; that variant is untested
- the 90000 block is not observed

## 6. `nine-digit-supgp-launch-nominals`

Nine-digit catalog numbers: 18 SDS launch nominals (7995016xx) in CelesTrak SupGP data

Tests: 9-digit-catalog-number, tle-unavailable-above-99999

Coverage gaps:

- perishable: nominals exist only for roughly 5-8 days after a launch (CelesTrak); a user's fetch may contain none, in which case the case reports 'no 9-digit ids available now' rather than failing
- no 9-digit id exists in 18 SDS GP data; only SupGP

## 7. `supgp-celestrak-classification-c`

CelesTrak supplemental GP: classification C, element set 0, RMS/DATA_SOURCE columns, 72000-series ids

Tests: supgp-extra-fields, classification-c

Coverage gaps:

- perishable: this post-deployment file is replaced after cataloguing
- the meaning of the 72000-series ids (the 70000-79999 block) is described only by a secondary source (RESEARCH.md §1); primary sources cover only the 80000-89999 analyst range and the 69999 end of the legacy range

## 8. `bstar-and-derivative-forms`

Drag terms: negative BSTAR, negative first derivative, non-zero second derivative, implied-decimal exponent fields

Tests: bstar-implicit-decimal, negative-bstar, negative-ndot, nonzero-nddot

Coverage gaps:

- no BSTAR with a positive exponent (>= 1.0 Earth radii^-1) exists in any fetched data; that encoding ('NNNNN+1') is untested
- no second derivative with a positive exponent

## 9. `satcat-70000-cutoff`

SATCAT on both sides of 70000: CSV/JSON records for 25544, 69999 and 100000; legacy fixed-width file stops at 69999

Tests: legacy-satcat-cutoff-70000

Coverage gaps:

- the 9.4 MB legacy file is not shipped; users fetch it once and the check recomputes the facts

## 10. `csv-json-omitted-mandatory-fields`

CelesTrak CSV and JSON omit the constant mandatory metadata keywords

Tests: csv-json-defaults

Coverage gaps:

- none identified

## 11. `mean-motion-derivative-convention`

MEAN_MOTION_DOT / MEAN_MOTION_DDOT in the OMM equal the TLE fields as printed

Tests: mmdot-convention

Coverage gaps:

- no record with a non-zero second derivative whose OMM text has more than 5 significant digits was observed, so the DDOT comparison is exact-equality only

## 12. `tle-vs-omm-precision-loss`

The TLE is a lossy rendering of the OMM record: eccentricity truncated, BSTAR/DDOT mantissa rounded, epoch quantised

Tests: precision-loss, round-trip-lossiness

Coverage gaps:

- no rounding tie (mantissa digit 6 exactly 5 followed by zeros) was observed, so half-up versus half-even at the tie is not distinguished
- the 24-character limit of TLE line 0 is a rule of the CelesTrak format document, not an observation: no name longer than 24 characters occurs in the 304 provider pairs; the cut appears only in one derived line (catalog 100465)

## 13. `omm-xml-schema`

CelesTrak OMM XML against the SANA schemas: valid as NDM/XML 2.0, invalid as 3.0 on the version attribute

Tests: xml-schema

Coverage gaps:

- no CelesTrak XML with units attributes, comments or covariance exists; those constructs are covered only by the CCSDS examples and derived variants

## 14. `alpha5-encoding-vectors`

Alpha-5 encode/decode vectors from the Space-Track table, with boundaries and invalid inputs

Tests: alpha5-letter-skip-rules, alpha5-range, 9-digit-catalog-number, 2-digit-epoch-year

Coverage gaps:

- vectors are not element sets; they test the mapping only

## 15. `alpha5-tle-derived`

Derived Alpha-5 TLE lines rendered from real CelesTrak OMM records (letters A and T)

Tests: alpha5-tle-parsing, alpha5-letter-skip-rules

Coverage gaps:

- letters B-H, J-N, P-S and U-Z appear in no real catalog number yet (the catalog is at ~100789 and the only other 6-digit block is 27xxxx); those letters are covered by vectors only
- these lines are derived, not provider output: CelesTrak serves no Alpha-5 and Space-Track data is not used
- renderer validation gap: the byte-for-byte validation (304/304) used only sub-100000 CelesTrak output, because CelesTrak emits no Alpha-5. The encoding step has since been corroborated against Space-Track output by the project owner (D-070: 44 records, 0 defects, letters A and T), but the derived lines are CelesTrak-style renderings and differ from Space-Track's own TLE lines in two conventions (zero second-derivative sign at column 51; eccentricity rounding versus truncation at columns 32-33), so they are not byte-identical to Space-Track output. No Space-Track data enters this repository; the public claim describes that verification, not the data.

## 16. `kvn-syntax-variants`

CCSDS-legal KVN renderings of one record that CelesTrak never emits

Tests: kvn-syntax

Coverage gaps:

- lowercase normative text values (7.5.3) and the 254-character line limit are not exercised
- no XML variants in this version

## 17. `tle-writer-alpha5`

Writing TLEs across the five-digit boundary: Alpha-5 catalog field, valid lines, refusal of numbers the format cannot carry, round trip

Tests: alpha5-tle-writing, alpha5-range, tle-checksum

Coverage gaps:

- letters B-S and U-Z occur in no real catalog number; a writer's encoding of those letters is covered by the alpha5_encode vectors only
- no input has a BSTAR or second derivative with a positive exponent
- no rounding tie at the last kept digit occurs in the inputs, so half-up versus half-even rounding is not distinguished for writers either
- no output of an external tool is shipped; strf's rffit was exercised only at function level outside this repository (DECISIONS D-097) and has no adapter because it is an interactive X11 program

## Checks

- **omm-formats-agree** — For the same object and snapshot, CSV, JSON, XML and KVN yield identical canonical values for every OMM keyword present in all of them.
- **tle-values-match-omm-within-tle-precision** — The TLE rendering equals the OMM values except: eccentricity truncated to 7 digits, BSTAR and second derivative rounded (half up) to a 5-digit mantissa, epoch at 1e-8 day resolution.
- **tle-checksums-valid** — Every TLE line 1 and line 2 is 69 characters and ends with the modulo-10 checksum (digits count their value, '-' counts 1, everything else 0).
- **catalog-number-is-integer** — NORAD_CAT_ID parses as an integer in every OMM format, including values of six and nine digits; leading zeros and an explicit '+' are legal in KVN.
- **tle-catalog-field-decodes** — Columns 3-7 of TLE lines 1 and 2 decode to the same integer (five digits, or Alpha-5 letter + four digits).
- **two-digit-year-pivot** — TLE epoch years 57-99 map to 1957-1999 and 00-56 to 2000-2056; the resulting ISO epoch equals the OMM EPOCH string.
- **object-id-may-be-empty** — OBJECT_ID (and in principle OBJECT_NAME) can be empty; parsers must not fail, and must not invent a value.
- **object-name-unknown-literal** — OBJECT_NAME may be the literal UNKNOWN (CCSDS-recommended) rather than empty.
- **csv-json-omit-constant-metadata** — CelesTrak CSV/JSON carry no CENTER_NAME, REF_FRAME, TIME_SYSTEM or MEAN_ELEMENT_THEORY; parsers must default them (EARTH, TEME, UTC, SGP4) rather than fail.
- **xml-ndm-wrapper-omm-2.0** — CelesTrak XML has an <ndm> root containing one <omm> per record with id=CCSDS_OMM_VERS and version=2.0; CREATION_DATE and ORIGINATOR elements are present but empty.
- **kvn-blank-mandatory-values** — CelesTrak KVN writes CREATION_DATE and ORIGINATOR with blank values and blank OBJECT_ID for analyst objects; MEAN_ELEMENT_THEORY is 'SGP/SGP4'.
- **leading-dot-decimals** — CSV, KVN and XML values may start with '.' or '-.' (no leading zero) and use 'E' exponents; JSON carries numbers.
- **tle-format-omits-ids-above-99999** — A TLE/3LE/2LE request returns only objects with catalog numbers below 100000; if none qualify the response is HTTP 404 'No GP data found'.
- **tle-count-equals-omm-count-below-100000** — The number of TLE records equals the number of OMM records whose NORAD_CAT_ID < 100000 for the same query.
- **nine-digit-ids-parse** — NORAD_CAT_ID values >= 100000000 parse and round-trip as integers in CSV, JSON, XML and KVN.
- **supgp-extra-keys-tolerated** — SupGP CSV/JSON add non-OMM keys (RMS, DATA_SOURCE); parsers must ignore unknown keys rather than fail.
- **classification-c** — CLASSIFICATION_TYPE may be 'C' (CelesTrak supplemental) rather than 'U'.
- **element-set-zero-and-rev-one** — ELEMENT_SET_NO may be 0 and REV_AT_EPOCH may be 1 or 0.
- **mmdot-is-tle-field-value** — OMM MEAN_MOTION_DOT equals the TLE first-derivative field as printed (the TLE 'ndot/2' convention); MEAN_MOTION_DDOT likewise equals the TLE second-derivative field.
- **bstar-implied-decimal-exponent** — TLE BSTAR and second-derivative fields are +/-NNNNN+/-E with an implied leading decimal point: ' 15975-3' is 0.15975e-3; zero is written ' 00000+0'.
- **negative-bstar-and-ndot** — BSTAR and the first derivative can be negative; parsers must keep the sign.
- **alpha5-decode** — An Alpha-5 catalog field decodes as (letter value)*10000 + digits with A=10 ... Z=33 and I, O unused; 'I', 'O' and lowercase are invalid.
- **alpha5-encode** — Integers 100000-339999 encode to the Alpha-5 table; below 100000 encode as five digits with leading zeros; above 339999 cannot be encoded.
- **satcat-legacy-below-70000** — The legacy fixed-width SATCAT contains only NORAD ids below 70000; the CSV/JSON SATCAT contains ids on both sides.
- **kvn-syntax-tolerance** — KVN parsers accept blank lines, COMMENT lines at allowed positions, arbitrary whitespace around '=', bracketed units, day-of-year epochs, an optional trailing Z, signed integers, lowercase 'e' exponents, LF or CRLF endings.
- **optional-tle-parameters-may-be-absent** — EPHEMERIS_TYPE, CLASSIFICATION_TYPE, NORAD_CAT_ID, ELEMENT_SET_NO and REV_AT_EPOCH are Optional in CCSDS Table 4-3 and may be missing from a valid OMM.
- **omm-version-3-accepted** — CCSDS_OMM_VERS 3.0 messages (with CLASSIFICATION and MESSAGE_ID in the header) are accepted alongside 2.0.
- **sha256-matches-tested-snapshot** — If the user's fetched bytes hash to the recorded SHA-256, the frozen expected values apply exactly; otherwise only structural checks apply and the tool says so.
- **tle-writer-catalog-field** — A TLE writer puts the catalog number in columns 3-7 of both lines as five digits with leading zeros below 100000 and, from 100000 to 339999, as Alpha-5 (letter value 10-33, A=10 ... Z=33 with I and O never used, then the last four digits); both lines carry the same field.
- **tle-writer-round-trip** — The written lines, read back by the corpus reference reader, reproduce the record's epoch, mean motion, eccentricity, inclination, RA of ascending node, argument of pericenter, mean anomaly and BSTAR at each field's resolution, quantised by truncation or by rounding half up (CelesTrak truncates the eccentricity, Space-Track rounds it; either is accepted and the convention observed is reported).
- **tle-writer-refuses-unencodable** — A TLE catalog field cannot represent a number above 339999 (Z9999) or below 0, so the correct output for such a record is a refusal: an error and no lines. Those numbers belong in the OMM formats. The check passes when the writer refuses and fails when it writes lines with a six-digit, blank or otherwise invalid field.
- **tle-writer-secondary-fields** — Whether the writer preserves, zeroes or drops MEAN_MOTION_DOT, MEAN_MOTION_DDOT, ELEMENT_SET_NO, REV_AT_EPOCH, CLASSIFICATION_TYPE, OBJECT_ID and OBJECT_NAME, and which exponent sign it writes for a zero second derivative (CelesTrak +, Space-Track -). Reported for information, never failed: orbit-fitting tools regenerate these fields by design.
- **tle-writer-matches-provider-rendering** — Per field, how many written fields are byte-identical to the provider's rendering of the same record (CelesTrak's TLE line, or the corpus's CelesTrak-style derived line). Information only: an equivalent rendering under the other provider's convention is not a defect.

## Ambiguities

- **unknown-vs-blank** — CCSDS 502.0-B-3 Table 4-2 says an unknown OBJECT_NAME/OBJECT_ID 'should be set to UNKNOWN' and 7.5.1 requires a non-empty value for mandatory keywords; CelesTrak writes an empty OBJECT_ID (empty string in CSV/JSON/KVN, empty element in XML) while the first-ever analyst records carry OBJECT_NAME 'UNKNOWN'. The corpus expects the provider's actual output and records the spec text.
- **empty-mandatory-header** — CCSDS Table 4-1 makes CREATION_DATE and ORIGINATOR mandatory; CelesTrak emits them empty in XML and blank in KVN. The 2.0 schema's epochType pattern accepts an empty string, so schema validation may pass; the KVN rule 7.5.1 is still violated.
- **omm-version-2-vs-3** — CelesTrak declares OMM version 2.0 (Silver Book 2009) although the current standard is 3.0 (Blue Book 2023). The 2.0 XML schema set is still downloadable from SANA by direct URL; against the current 4.0.0/3.0 set the documents fail on the fixed version attribute.
- **met-sgp-sgp4-vs-sgp4** — For the same record CelesTrak writes MEAN_ELEMENT_THEORY = SGP/SGP4 in KVN and SGP4 in XML. Both appear in CCSDS examples; parsers should accept both.
- **leading-dot-decimals** — CCSDS 7.5.6 requires at least one digit before and after the decimal point in KVN fixed-point values; CelesTrak writes '.00048259' and '.15975118E-3'. Most decimal parsers accept this; strict KVN validators may not.
- **mmdot-convention** — CCSDS 4.2.4.7 NOTE 2 says TLE-sourced MEAN_MOTION_DOT/DDOT 'need to be divided by 2 and 6 respectively' but does not say which convention the OMM value carries. Observed: CelesTrak's OMM values equal the TLE fields as printed (304/304 records), i.e. the halved / sixth-ed values. Parsers converting to true derivatives must multiply by 2 and 6.
- **ecc-truncation-vs-mantissa-rounding** — CelesTrak's TLE rendering truncates eccentricity to 7 digits but rounds (half up) BSTAR and the second derivative to a 5-digit mantissa (304/304 CelesTrak records reproduced with these rules; 0 with the opposite rules). No document states either rule; treat as observed CelesTrak behaviour. It is not universal: in the owner's Space-Track verification run (D-070) Space-Track's TLE for the same epoch differed from the CelesTrak-rendered line in the last one or two eccentricity digits (columns 32-33), consistent with rounding, and wrote a zero second derivative as 00000-0 (column 51) where CelesTrak writes 00000+0.
- **object-id-launch-year-pivot** — No document defines how a two-digit launch year in the TLE international designator maps to a century. The corpus applies the same 57 pivot as the epoch year (python-sgp4 export_omm does the same); CelesTrak's OMM OBJECT_ID carries four-digit years, so the mapping matters only for TLE input.
- **tle-epoch-resolution** — The TLE epoch has 1e-8 day (864 microsecond) resolution. CelesTrak GP epochs convert exactly between the two representations; SupGP epochs do not (86 microsecond difference observed), so a TLE->OMM epoch comparison needs a tolerance of half the TLE resolution.
- **supgp-extra-keys** — SupGP CSV/JSON carry RMS and DATA_SOURCE, which are not OMM keywords (CCSDS 7.9.2.2 allows only Table 4-x keywords in an OMM); CelesTrak's CSV/JSON are OMM-keyword-based formats, not OMM instances, so this is a format extension rather than a violation. Parsers must tolerate unknown keys.
- **gp-first-stability** — The corpus assumes CelesTrak's gp-first.php ('first GP data available') returns the same record for a given catalog number indefinitely. This was not verified over time. tools/fetch.py compares every fetched file with the SHA-256 recorded in manifest.json after each run (and on demand with --check-drift) and prints a DRIFT line for any stable-tier source whose bytes differ; the runner independently labels such a source 'live' and stops applying the frozen values to it. Related observation (D-070, D-074): gp-first records are historical in their elements but can carry metadata assigned after first publication. For catalog 100000, Space-Track's earliest record has a blank international designator, Space-Track's current record carries the same designator as CelesTrak, and CelesTrak's gp-first record shows that designator back-filled; the line-2 elements are identical. Treat OBJECT_NAME and OBJECT_ID in a gp-first record as current metadata, not as the values first published.
- **analyst-number-reuse** — Space-Track states analyst numbers 'can be constantly reused for different objects'; gp-first.php for an analyst id therefore returns whichever object first carried that number, which may differ from the object currently using it.
- **satcat-record-drift** — SATCAT records for existing objects change when an object decays or its orbit summary is updated; records.php sources are treated as live for checksum purposes even though most fields are stable.
- **supgp-redistribution** — SupGP data derives from operator-provided data (some explicitly 'with permission' to CelesTrak). Under the corpus design no raw bytes are shipped; the snapshot values for one SupGP record are published as a dated reference and may be removed by the owner before publication.
