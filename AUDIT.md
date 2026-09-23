# Independent audit of gp-omm-conformance

_Public copy: one row of the Appendix A table withheld; see the notice under Appendix A._

Audited state: commit `4db7d2a` (working tree clean). Auditor stance: nothing in the repository's own
documents or readers was trusted; every number below was recomputed with the auditor's own code (no
`gpconf` or `tools/` import) unless the finding says otherwise. Nothing in the repository was modified
except the creation of this file. Network use: one GET to sanaregistry.org to spot-check a vendored
schema hash; no request was sent to CelesTrak.

## Verdict in one paragraph

No wrong expected value was found: 65,887 field-level comparisons across every record of every
gp/derived case (3,876 record-file pairings), recomputed from the raw bytes with independent parsers,
agreed with `expected.json` in every instance; the 60-value random sample required by the brief is in
Appendix A (60/60 agree). All 128 recorded source hashes, byte counts, HTTP statuses and record counts
match the files on disk. The Alpha-5 vectors are arithmetically correct and all 604 derived lines are
byte-identical to an independent rendering. The library-behaviour claims re-run as stated. The public
export contains no raw provider bytes, no per-record SupGP signature, no Space-Track-named path, no
e-mail address and no credential. What the audit did find are three false statements in public
documentation (none affects an expected value), several claims stated more strongly than the evidence
in the repository supports, two recorded decisions that were never implemented, and a set of minor
inconsistencies.

## Critical (false claim in public documentation, or wrong expected value)

No wrong expected values. Three false public statements:

**C1. The fetch script does not report hash drift, although four public documents say it does.**
README.md line 215 ("the fetch script reports hash drift"), docs/PLAN.md line 373, the manifest
ambiguity `gp-first-stability` ("the fetch script compares SHA-256 hashes and reports drift") and
DECISIONS D-024 all assert it. `tools/fetch.py` computes a SHA-256 only to write it into `.meta.json`;
it never reads `manifest.json` or `expected.json` and never compares anything (grep of the file for
`manifest`, `expected`, `drift`: no hits). Drift is visible only when the *runner* labels a source
`live`. Impact: users following the README will expect a warning at fetch time that never comes; the
gp-first stability assumption therefore has no automatic check at the point where it would be cheapest.

**C2. The README's tolerance table states "1e-12 relative" for float values; the implementation is
1e-12 absolute for every value below 1.** `gpconf/runner.py` `compare_value` uses
`scale = max(1, |a|, |b|)`, so eccentricities, BSTAR, both derivatives and every other sub-unity value
are compared at an absolute 1e-12. For a BSTAR of 7e-6 that is a relative allowance of ~1.4e-7, not
1e-12; DECISIONS D-039 and D-048 repeat the "relative" wording. Impact on bias detection: none hidden,
because every non-exact comparison is reported as `pass-tolerance` with count, mean signed difference
and maximum, and the reference adapter is verified exact. Impact on the public statement: it is false as
written, and a parser author reading it would misjudge what the corpus accepts for small values.

**C3. docs/RESEARCH.md §13 states that "the current analyst group carries names (e.g. object
designations) and empty OBJECT_ID in 563 of 565 records".** Recount from `analyst.csv`: all 565
records have `OBJECT_NAME` equal to the literal `UNKNOWN`; none carries a designation-style name. The
case document's coverage line "563 of 565 with empty OBJECT_ID, all with a name" is technically true
only because `UNKNOWN` is a non-empty string, and it invites the wrong reading; the case's own
interpretation text ("may carry OBJECT_NAME 'UNKNOWN'") and the README table ("`UNKNOWN` names")
are correct. RESEARCH.md is on the public allowlist.

## Major (claim with weaker evidence than stated)

**M1. "Names cut to 24 characters" is presented as an observed TLE rendering rule; it was never
observed in provider output.** `fixtures/tle-vs-omm-precision-loss/case.md` lists it with the
truncation/rounding rules that were established from 304 pairs, and the README case table repeats
"names cut to 24". The case's own summary records `names_longer_than_24: 0` among those 304 pairs; the
only long name (100465, 27 characters) is a six-digit object with no CelesTrak TLE, so the cut exists
only in a derived line. The rule rests on the CelesTrak format document's "twenty-four character name"
(cited in RESEARCH §7), which is a format statement, not an observation of truncation behaviour.

**M2. "TLE → OMM → TLE does [round-trip]" is asserted without any test.** (case.md interpretation for
`tle-vs-omm-precision-loss`.) The repository demonstrates OMM → TLE reproduction (304/304) and
python-sgp4's TLE → Satrec → TLE (byte-exact only for 81 non-zero-ddot lines, for the library's sign
reason). Nothing parses a TLE, re-serialises it through the corpus's own rules and compares bytes.
The claim is plausible from the rules, but it is stated as a consequence, not shown.

**M3. The reserved block 70000–99999 is stated as fact; the repository's own research marks it as
partly secondary and partly unsourced.** README line 19: "the five-digit range ends at 69999 because
70000-99999 is reserved". RESEARCH §1: the 70000–79999 reservation comes from Wikipedia (marked
secondary), 80000–89999 from Space-Track, and "the 90000 block is not described in any primary source
I read". The `supgp-celestrak-classification-c` case likewise calls 72000-series ids "pre-catalog" on
the same secondary basis. The primary evidence supports only "runs out at 69999" (CelesTrak) and the
analyst range (Space-Track).

**M4. DECISIONS D-014 records that "Phase 3 commits an excerpt plus the full-file SHA-256" of the
legacy SATCAT; no excerpt exists and no entry reverses D-014.** `fixtures/satcat-70000-cutoff/`
contains only `case.md`, `expected.json` and the ignored `raw/`. The later design (D-023: no raw bytes
shipped) makes an excerpt inappropriate, but the log's append-only rule required a reversal entry.

**M5. DECISIONS D-024 promises a fetch-script hash comparison that was never built** (the decision-log
side of C1).

**M6. The fetch-error tally is stale.** D-021 and the RESEARCH §12 fetch log say five non-200 responses
were received from celestrak.org "across both phases". Six `.meta.json` files record HTTP 404
(saramago.tle, saramago-first.tle, last-30-days.tle and its recapture, analyst-270449-first.tle,
starlink-38381 TLE), plus the two documentation 404s described in D-021: eight by the end of Phase 3.
No later entry updates the count. All remain far below CelesTrak's stated threshold.

**M7. Upstream draft `python-sgp4-export-tle-zero-ddot-sign.md` says "306 TLE/2LE records across ten
queries".** Nine TLE-format responses contained records (iss.tle, iss.2le, analyst.tle,
analyst-81011-first.tle, decaying.tle, iss-first.tle, iss-first.2le, starlink-g15-27.tle,
gp-69999-first.tle); the other five TLE-format responses were 404s. The record count 306 is correct.

**M8. The README lists `docs/INVENTORY.md` among the documentation the corpus contains, but the
public allowlist deliberately excludes it** (it quotes SupGP field values). A reader of the public
README is pointed at a document that is not there. `docs/README-draft-ai-assistance.md`, a stale
near-duplicate of the README section, is exported.

## Minor (clarity, consistency)

- DECISIONS D-030: "14 files each" — the 2.0.0 schema set has 12 files, the 4.0.0 set 14.
- Version strings disagree: `pyproject.toml` and `gpconf.__version__` say `0.1.0.dev0`, `manifest.json`
  says `0.1.0-dev`.
- The fetch list's duplicate-URL guard is case-sensitive; three recapture entries are the same
  endpoint with `FORMAT=tle` in lower case (deliberate, per D-022, and skipped for users per D-042),
  so the guard does not protect against that class of duplicate.
- README "skip it with `--case` selection" (the 9.4 MB SATCAT): `--case` includes cases, so skipping one
  means listing the other fifteen. README "the tool refuses to anyway" holds only for files already
  fetched; a fresh clone fetches everything.
- `nine-digit-supgp-launch-nominals/case.md` "29 of 29 tested": 28 distinct records (27 in the full
  file, one single-object query); the 29 counts the single object's CSV and XML renderings separately.
- README tolerance rationale "Julian-date floats are about 1 microsecond coarse near the present" and
  the statements "Alpha-5 … served by Space-Track only", "OMM … served by … Space-Track since 2020",
  "XML libraries return `None` for the empty element" have no cited source in the repository. The
  first is consistent with the observed 1.0 µs maximum in CROSSCHECK; the second is an inference from
  two providers; the third rests on a secondary source; the fourth was verified for ElementTree only.
- `docs/FAILURES.md` carries no generation timestamp or report identifier, so a reader cannot tell
  which runner outputs it summarises.
- `kvn-syntax-variants/case.md` "a parser hard-coded to CelesTrak's exact layout fails four of the six"
  is consistent with the naive adapter's four failing items for that case, but the identity of the four
  variants is not stated anywhere.
- `omm-xml-schema/case.md` "a validator that follows the declared schemaLocation accepts them" depends
  on SANA continuing to serve the 2.0.0 files at their direct URLs (observed once, 2026-09-21).
- The export ships `tools/_fetch-run-*.log`; they contain only URLs, statuses and byte counts.

## What was verified, with the numbers

- **Sources:** 128 entries; SHA-256, byte count and HTTP status match the on-disk files and their
  `.meta.json`; record counts recomputed by independent readers match for every parsable file.
- **Expected values:** full recomputation of every record in the 10 gp/derived cases (analyst 2,705
  record-file pairings, derived Alpha-5 604, tle-omits 256, bstar 242, nine-digit 31, supgp 10, ISS 7+7,
  saramago 8, KVN variants 6): 65,887 field comparisons, 0 mismatches. TLE field substrings and
  checksums in `by_format.tle.fields` agree with independent slicing for every TLE record. Oracle
  numeric values are all JSON strings; no expected file contains a whole TLE line (`line0/1/2` absent).
- **Alpha-5 (item 3):** my own table from the stated rule (letters A–Z minus I and O, values 10–33)
  equals `vectors/alpha5.json`'s table; all official examples, boundaries, skip boundaries (H9999→J0000,
  N9999→P0000), sub-100000 forms, invalid inputs and unencodable integers behave as the vector file
  says. All 604 derived lines decode to an id present in their source file and are byte-identical to an
  independent re-rendering from the source CSV (letters: A 257, T 347); all checksums valid.
- **Precision rules:** over the 304 CelesTrak TLE/CSV pairs, recomputed independently: eccentricity
  truncation matches 304, rounding 257; BSTAR 5-digit round-half-up 304, truncation 271; DDOT round 304;
  epoch exact 302 with maximum 86 µs; 0 rounding ties; 0 names over 24 characters. Identical to the
  repository's summary.
- **Other case figures:** analyst 565 = 219 (8xxxx) + 346 (270000–270449), 563 empty OBJECT_ID, TLE
  219 records; last-30-days 256 records, all 100404–100789, 11 non-zero DDOT, 52 negative BSTAR;
  decaying 82 CSV / 79 TLE, 3 six-digit; 27 nine-digit ids 799501621–799501647 contiguous; G15-27 ids
  72000/72001, element set 0, classification C, OBJECT_ID 2026-219A shared with 799501621, TLE epoch
  86 µs from CSV; legacy SATCAT 69,999 lines, ids 1–69999 contiguous, none ≥ 70000, parsed lines for
  25544 and 69999 agree; no positive-exponent BSTAR or DDOT field in 1,208 line-1 records; ISS 1998
  record: ndot `-.00003657`, nddot ` 11563-4`, BSTAR ` 00000+0`, element set 1, rev 0, year `98`.
- **Library claims (venv: python-sgp4 2.27, Skyfield 1.55, xmlschema 4.3.2):** 28/28 nine-digit CSV
  records raise ValueError, Skyfield likewise; 564/566 analyst XML records raise TypeError;
  export_tle: 225 zero-ddot records, 0 exact, 81 non-zero, 81 exact, no mismatch outside columns 51 and
  69; `omm.initialize` returns classification `U` for a `C` record; `from_alpha5` accepts I0000, O1234,
  a0000, A000 and `to_alpha5(-1)` returns `'-0001'`. All three upstream reproducers run as their drafts
  show. The patch applies cleanly to a copy of the installed package; python-sgp4's own 47 test functions
  pass with it.
- **Schemas:** 8/8 CelesTrak XML files valid against ndmxml-2.0.0, 0/8 against 4.0.0, and 8/8 against
  4.0.0 after changing only the version attribute to 3.0, so "solely the version attribute" holds. The
  2.0.0 `epochType` pattern does accept an empty string. One vendored file
  (`ndmxml-4.0.0-omm-3.0.xsd`) re-fetched from SANA hashes identically.
- **Export (item 4):** dry run and real export: 136 files, 0 refused, 4 expected files scrubbed; no
  `raw` directory; no exported file byte-identical to a raw provider file; no raw TLE line 1/2 and no raw
  CSV row appears verbatim anywhere; no SupGP epoch or mean-motion string (unique per record) appears
  anywhere; the 11 BSTAR-text coincidences found belong to other objects (e.g. analyst 81052's
  `.16864E-2` equals Starlink 67994's) and are not leaks; no e-mail address, no credential-like string;
  the owner's name appears only in README and DECISIONS; no local path fragments. Space-Track is
  mentioned in 32 files as a word (documentation and guard code), no data. The simulated public checkout
  (tests run inside the exported tree) passes: 10 tests, 1 skipped; the two CI commands behave as the
  workflow expects; a full run without raw files reports 3 pass, 12 skip, 1 not-exercised, 0 fail.
- **Tolerances (item 5):** mechanics reviewed in `gpconf/runner.py`: three-state comparison; any
  non-exact numeric or epoch agreement produces a `pass-tolerance` item carrying per-field count, mean
  signed difference and maximum in both the CLI detail and the JSON `tolerance_stats`; the TLE-vs-OMM
  432 µs epoch allowance is reported as a quantisation observation, not as a tolerance pass; the
  reference adapter is 16/16 exact and `test_reference_is_exact` enforces it. A systematic parser bias
  therefore cannot be hidden, though see C2 for the mis-stated magnitude.
- **Decisions (item 6):** D-001–D-013, D-015–D-020, D-022, D-023, D-025–D-029, D-031–D-053 are
  reflected in the tree as recorded (spot checks: no Space-Track content tracked; recaptures have
  `recapture_of` and are skipped by default; allow_error entries present; SupGP raw ignored; both
  schema sets present; guard patterns present and tested; scrub applied by export, catalogue and
  test). Exceptions are M4 (D-014) and M5/C1 (D-024); D-030's file count is wrong (minor).
- **Model-memory (item 7):** the domain facts that carry the corpus (catalog event date and number,
  Alpha-5 table and examples, CCSDS keyword tables and syntax rules, TLE column layout, checksum rule,
  two-digit-year pivot, CelesTrak API and policy, Space-Track statements) all have verbatim quotations
  with URLs and dates in RESEARCH.md. The unsourced items found are listed under M3 and the minor
  section; none of them is used to compute an expected value.

## Could not be verified (recorded, not assumed fine)

- Anything that depends on the network state at fetch time: that the quoted CelesTrak and Space-Track
  texts are verbatim, the HTTP statuses and headers in `.meta.json`, and the assumption that
  `gp-first.php` returns stable bytes (no second observation exists; and per C1 nothing will flag it
  automatically). No CelesTrak request was made during this audit, by design.
- Python 3.9 compatibility claimed by `pyproject.toml` and CI: only Python 3.14 is available here; a
  scan found no 3.10+ syntax, which is not a proof.
- The login-gated parts of Space-Track's documentation and the owner's private Space-Track
  verification of the encoder (absent from the repository by design, D-037).
- That the `2026-09-21` timestamps in metadata are accurate: they are internally consistent (the
  recaptures' `Date` headers agree with `retrieved_at` to within seconds) but cannot be checked
  against an external clock.
- The single `last-30-days.tle` first observation whose metadata was reconstructed from a log
  (documented, superseded by the clean recapture, which is what the case cites).

## Appendix A — the 60-value random sample (seed 20260921), recomputed from raw bytes

**Public-copy notice.** One row of the Appendix A table, a random-sample entry from the `nine-digit-supgp-launch-nominals` case, is withheld from this public copy because it shows SupGP-derived element values (withheld per DECISIONS D-033, implemented by D-049). Nothing else in this document differs from the private original, which is intact.

| case | id | file | field | expected | recomputed | agree |
|---|---|---|---|---|---|---|
| analyst-objects | 89213 | analyst-recapture.tle | norad_cat_id | `89213` | `89213` | yes |
| alpha5-tle-derived | 270026 | alpha5-T-analyst-27xxxx-snapshot.tle | arg_of_pericenter | `219.004` | `219.0040` | yes |
| analyst-objects | 87029 | analyst.tle | ra_of_asc_node | `290.419` | `290.4190` | yes |
| alpha5-tle-derived | 270444 | alpha5-T-analyst-27xxxx-snapshot.tle | mean_motion_ddot | `0` | `0.00000` | yes |
| alpha5-tle-derived | 270116 | alpha5-T-analyst-27xxxx-snapshot.tle | mean_motion_dot | `5E-8` | `5E-8` | yes |
| analyst-objects | 82693 | analyst.kvn | inclination | `100.529` | `100.5290` | yes |
| analyst-objects | 270338 | analyst.csv | element_set_no | `999` | `999` | yes |
| analyst-objects | 270262 | analyst.kvn | mean_motion_ddot | `0` | `0` | yes |
| analyst-objects | 85246 | analyst.tle | object_id | `None` | `None` | yes |
| analyst-objects | 270211 | analyst.kvn | bstar | `0.00018319067` | `0.00018319067` | yes |
| analyst-objects | 270202 | analyst.kvn | mean_motion_ddot | `0` | `0` | yes |
| alpha5-tle-derived | 270387 | alpha5-T-analyst-27xxxx-snapshot.tle | rev_at_epoch | `17330` | `17330` | yes |
| analyst-objects | 270289 | analyst.csv | mean_anomaly | `84.4081` | `84.4081` | yes |
| analyst-objects | 270091 | analyst.json | eccentricity | `0.003033` | `0.003033` | yes |
| alpha5-tle-derived | 270379 | alpha5-T-analyst-27xxxx-snapshot.tle | arg_of_pericenter | `318.212` | `318.2120` | yes |
| analyst-objects | 270405 | analyst.json | epoch | `2026-09-20T08:57:41.808384` | `2026-09-20T08:57:41.808384` | yes |
| analyst-objects | 87211 | analyst.xml | eccentricity | `0.0053017` | `0.0053017` | yes |
| alpha5-tle-derived | 100697 | alpha5-A-last-30-days-snapshot.tle | ephemeris_type | `0` | `0` | yes |
| tle-omits-six-digit-objects | 100784 | last-30-days.csv | bstar | `0.000044617326` | `0.000044617326` | yes |
| analyst-objects | 87204 | analyst-recapture.tle | ra_of_asc_node | `123.1317` | `123.1317` | yes |
| analyst-objects | 270441 | analyst.xml | rev_at_epoch | `11141` | `11141` | yes |
| analyst-objects | 270089 | analyst.csv | mean_anomaly | `16.3032` | `16.3032` | yes |
| analyst-objects | 81865 | analyst.xml | mean_motion | `13.88677454` | `13.88677454` | yes |
| alpha5-tle-derived | 270012 | alpha5-T-analyst-27xxxx-snapshot.tle | mean_motion_ddot | `0` | `0.00000` | yes |
| bstar-and-derivative-forms | 45395 | decaying-recapture.tle | object_name | `STARLINK-1297` | `STARLINK-1297` | yes |
| alpha5-tle-derived | 270237 | alpha5-T-analyst-27xxxx-snapshot.tle | epoch | `2026-09-13T01:47:45.627360` | `2026-09-13T01:47:45.627360` | yes |
| analyst-objects | 270036 | analyst.csv | object_name | `UNKNOWN` | `UNKNOWN` | yes |
| analyst-objects | 85238 | analyst-recapture.tle | rev_at_epoch | `64988` | `64988` | yes |
| analyst-objects | 270441 | analyst.csv | mean_motion_dot | `0.00003958` | `0.00003958` | yes |
| tle-omits-six-digit-objects | 100639 | last-30-days.csv | ra_of_asc_node | `237.6533` | `237.6533` | yes |
| analyst-objects | 87293 | analyst.json | classification_type | `U` | `U` | yes |
| analyst-objects | 85100 | analyst.tle | bstar | `0.000067095` | `0.000067095` | yes |
| analyst-objects | 84006 | analyst.csv | norad_cat_id | `84006` | `84006` | yes |
| alpha5-tle-derived | 270302 | alpha5-T-analyst-27xxxx-snapshot.tle | classification_type | `U` | `U` | yes |
| analyst-objects | 82199 | analyst.kvn | bstar | `0.00029019` | `0.00029019` | yes |
| analyst-objects | 270202 | analyst.json | epoch | `2026-09-19T13:14:21.240672` | `2026-09-19T13:14:21.240672` | yes |
| analyst-objects | 270387 | analyst.csv | rev_at_epoch | `17330` | `17330` | yes |
| analyst-objects | 270346 | analyst.csv | ephemeris_type | `0` | `0` | yes |
| alpha5-tle-derived | 270116 | alpha5-T-analyst-27xxxx-snapshot.tle | element_set_no | `999` | `999` | yes |
| analyst-objects | 87054 | analyst.csv | mean_motion | `14.12077194` | `14.12077194` | yes |
| analyst-objects | 87071 | analyst.kvn | object_name | `UNKNOWN` | `UNKNOWN` | yes |
| alpha5-tle-derived | 270071 | alpha5-T-analyst-27xxxx-snapshot.tle | rev_at_epoch | `27935` | `27935` | yes |
| bstar-and-derivative-forms | 51827 | decaying.csv | eccentricity | `0.00040848` | `0.00040848` | yes |
| analyst-objects | 81844 | analyst.xml | mean_anomaly | `350.303` | `350.3030` | yes |
| tle-omits-six-digit-objects | 100549 | last-30-days.csv | rev_at_epoch | `286` | `286` | yes |
| alpha5-tle-derived | 270117 | alpha5-T-analyst-27xxxx-snapshot.tle | inclination | `90.2417` | `90.2417` | yes |
| tle-omits-six-digit-objects | 100425 | last-30-days.csv | bstar | `0.00020671647` | `0.00020671647` | yes |
| analyst-objects | 270090 | analyst.json | bstar | `0.000064096141` | `0.000064096141` | yes |
| analyst-objects | 85246 | analyst.csv | classification_type | `U` | `U` | yes |
| analyst-objects | 270415 | analyst.kvn | ephemeris_type | `0` | `0` | yes |
| analyst-objects | 82073 | analyst.tle | bstar | `0.0003576` | `0.00035760` | yes |
| alpha5-tle-derived | 270046 | alpha5-T-analyst-27xxxx-snapshot.tle | epoch | `2026-09-14T15:21:42.501600` | `2026-09-14T15:21:42.501600` | yes |
| analyst-objects | 85151 | analyst.xml | arg_of_pericenter | `332.4362` | `332.4362` | yes |
| analyst-objects | 270181 | analyst.json | classification_type | `U` | `U` | yes |
| analyst-objects | 270345 | analyst.csv | arg_of_pericenter | `37.2013` | `37.2013` | yes |
| alpha5-tle-derived | 100468 | alpha5-A-last-30-days-snapshot.tle | mean_anomaly | `185.476` | `185.4760` | yes |
| alpha5-tle-derived | 100425 | alpha5-A-last-30-days-snapshot.tle | epoch | `2026-09-20T13:55:46.969536` | `2026-09-20T13:55:46.969536` | yes |
| analyst-objects | 81893 | analyst.json | mean_motion_dot | `0.00000648` | `0.00000648` | yes |
| bstar-and-derivative-forms | 58720 | decaying.tle | inclination | `53.1264` | `53.1264` | yes |

---

## Resolution notes (maintainer, 2026-09-21)

Added after the audit. In this private original the auditor's text above is unaltered. The public copy
of this file withholds one row of the Appendix A table (a sample entry from the SupGP case, per D-033 as
implemented by D-049) and carries a notice saying so; nothing else differs. Each note names the change
and the `DECISIONS.md` entry that records it.

| finding | resolution | decision |
|---|---|---|
| C1 | Implemented, not retracted: `tools/fetch.py` compares every file on disk with the manifest's SHA-256 after each run and via `--check-drift`; stable-tier drift is printed as `DRIFT` with its consequence; `tests/test_fetch_drift.py` added; README, PLAN and the `gp-first-stability` ambiguity now describe the implemented behaviour | D-055 |
| C2 | Float tolerance is now |got − want| / max(|got|, |want|) ≤ 1e-12 with no floor; exact zero requires exact zero; README table corrected; adapters re-run: no python-sgp4 case or item status changed; FAILURES.md regenerated | D-056 |
| C3 | RESEARCH.md §13 corrected (marked note); analyst case coverage and interpretation now state that all 565 records carry the literal `UNKNOWN` | D-057 |
| M1 | 24-character limit reclassified as a format-document rule not observed in the 304 pairs; case.md and README corrected | D-058 |
| M2 | `tests/test_roundtrip.py` added: TLE → OMM text → TLE byte-exact for all 1,208 records (CelesTrak-served incl. re-captures, plus 604 derived); claim kept and cited | D-059 |
| M3 | README and supgp case reworded to primary-source support; "pre-catalog" removed; secondary basis stated | D-060 |
| M4 | Reversal entry for D-014 appended: no excerpt under the D-023 design; the facts live in expected.json and are recomputed by the runner | D-061 |
| M5 | Resolved by C1 | D-055 |
| M6 | Tally updated to eight with the full breakdown; RESEARCH.md §12 marked note | D-062 |
| M7 | "ten queries" → nine that returned records (five 404s) | D-063 |
| M8 | INVENTORY.md reference removed from the README; README draft removed from the allowlist | D-064 |
| minor | version unified (`0.1.0.dev0`); case-insensitive duplicate-URL guard with documented recapture exemption; `--skip-case`; README fetch text; "28 distinct records"; each uncited statement cited or softened; FAILURES.md timestamp and report identifiers; four failing KVN variants named (v02, v03, v04, v05); SANA schemaLocation dependency noted; fetch run logs out of the export; D-030 file count corrected | D-065 |
| publication | AUDIT.md committed and allowlisted; one appendix row from the SupGP case is withheld in the exported copy by `tools/public_scrub.py`, which inserts a notice stating exactly that (private original intact); README AI-assistance section updated and qualified accordingly | D-066, D-067 |

Verification after the fixes: reference adapter 16/16 exact; python-sgp4 results unchanged; full test
suite green (see the commit that adds this section); export dry run 133 files, 0 refused, 5 files
scrubbed on the way out (four expected files and the exported copy of this report).

## Correction (maintainer, 2026-09-23)

The line under "Library claims" above that reads "564/566 analyst XML records raise TypeError" repeats a
miscount and is left as written. The figure entered the repository in the Phase 3 cross-check text of
2026-09-20 (`docs/RESEARCH.md`, copied into the README) and the audit reproduced it without recounting. The
only analyst-group fetch on record, `fixtures/analyst-objects/raw/analyst.xml` retrieved 2026-09-21T00:11:35Z
(SHA-256 `8c76a786…`, the same bytes at the Phase 3 commit and today), holds 565 records, 563 of them with an
empty `OBJECT_ID`, as `docs/CROSSCHECK.md`'s per-file table and python-sgp4 issue #171 state. The README and
`docs/RESEARCH.md` now say 563 of 565 (DECISIONS D-109).

## Retraction of the correction above (maintainer, 2026-09-23)

The correction appended earlier today was wrong and is left in place as a record. The audit's line "564/566 analyst
XML records raise TypeError" was correct: the analyst case has two XML sources, `fixtures/analyst-objects/raw/analyst.xml`
(565 records, 563 with an empty `OBJECT_ID`) and `fixtures/analyst-objects/raw/analyst-270449-first.xml` (1 record,
empty `OBJECT_ID`), so python-sgp4 raises on 564 of the case's 566 XML records, as `docs/CROSSCHECK.md`'s per-file table
states at its rows for the two files (lines 30 and 33). "563 of 565" is true only of the group file. The documentation now
says "564 of the 566 analyst XML records in the case (563 of the 565 group records, plus the single 270449 first record)"
(DECISIONS D-110).
