# Decisions log

Append-only. Newest at the bottom. Reversals are new entries that reference the original.
Format: date, id, decision, alternatives considered, reason.

## 2026-09-20

**D-001 — Alpha-5 element sets come from derived re-encodings of CelesTrak OMM records, never from Space-Track bytes.**
Alternatives: (a) commit Space-Track TLEs; (b) encoding vectors only.
Reason: the Space-Track user agreement prohibits transferring its data to other entities without approval and a repository is a transfer; CelesTrak records re-encoded by a committed script are real data with a reproducible transformation. Derived files carry `provenance: derived` with source record and script recorded. The project owner may verify the encoder privately against their own Space-Track account; nothing from that check is committed. (Owner decision.)

**D-002 — Fetch the Starlink G15-27 post-deployment SupGP file first, store under `raw/`, gitignore it for now.**
Alternatives: skip 9-digit coverage; wait for the next launch.
Reason: it is the only current source of provider-issued 9-digit ids and the ids disappear at cataloguing. If nothing usable is in it, the 9-digit element-set case is omitted; no synthetic records. (Owner decision.)

**D-003 — Derived KVN syntax variants re-serialised from real records are allowed.**
Alternatives: omit; hand-write examples.
Reason: CCSDS-legal forms that CelesTrak happens not to emit (day-of-year epochs, no fractional seconds, `Z`, bracketed units) are exactly what breaks parsers; each derived file records the source record hash and the transformation. (Owner decision.)

**D-004 — Phase 2 fetch budget approved as proposed in docs/PLAN.md §3 (about 40 requests, each URL once, under ~20 MB).**
Reason: well inside CelesTrak's published limits (100 MB/day, 50 errors per 2 h); the two one-download-per-update groups (`active`, `starlink`) are not requested. (Owner decision.)

**D-005 — Repository initialised at `Code Files/gp-omm-conformance/`; private until after the independent audit.**
Reason: redistribution terms for CelesTrak data are not yet settled (see D-007 and RESEARCH.md §11). (Owner decision.)

**D-006 — CLAUDE.md written without the `---` delimiter lines that surrounded the supplied text.**
Alternatives: include them.
Reason: a leading `---` block is parsed as YAML front matter by many Markdown tools and would hide the policy; the delimiters read as quoting marks in the instruction, not as content. Reversible in one edit if wrong.

**D-007 — No personal contact details in the fetch User-Agent.**
Alternatives: include the owner's e-mail (as some earlier one-off documentation fetches did).
Reason: CelesTrak does not ask for identification, and sending an address in request headers to a third party is not something the owner asked for. The UA names the project and points at the repository README. `GPCONF_CONTACT` env var lets the owner opt in.

**D-008 — The fetch tool does not follow redirects and never retries.**
Alternatives: default urllib behaviour (follow 301/302).
Reason: CelesTrak counts 301s toward its error limit and says responses to 403/404 "will not change by repeating the request"; a redirect means the fetch list is wrong and should be fixed by a human.

**D-009 — One fetch-list entry may record a non-200 response as data: `gp.php?CATNR=100000&FORMAT=TLE`.**
Alternatives: stop the run on any non-200 (the rule for every other entry); skip the request.
Reason: the response to a TLE request for a 6-digit object is itself a migration fact worth recording, and CelesTrak documents that TLE output cannot carry such objects. One request, never repeated, whatever the status.

**D-010 — `gp-first.php` is queried for ISS (25544) only, not for Vanguard 1 (5), in the first pass.**
Alternatives: query both.
Reason: if the GP archive does not reach 1998 for the ISS it will not reach 1958 either; avoids a probable 404. A second, single request may follow once the ISS result is seen.

**D-011 — SATCAT "both sides of 70000" uses the largest id below 70000 actually present in `satcat.txt`, plus 25544 and 100000, via `records.php`; no 8xxxx SATCAT query.**
Alternatives: guess 69999; download `satcat.csv` as well.
Reason: analyst objects are not in the public SATCAT, 69999 may not exist as an object, and the legacy file already tells us the largest 5-digit id; avoids a 404 and a second multi-megabyte download.

## 2026-09-21

**D-012 — Nine-digit ids taken from the full Starlink SupGP file and one per-object query, after the G15-27 file proved to use 72000-series ids.**
Alternatives: give up on 9-digit coverage; download the whole Starlink SupGP set in all five formats (~10 MB).
Reason: the G15-27 post-deployment file (fetched first, per D-002) carries ids 72000/72001. One CSV download of `FILE=starlink` (1.8 MB, subject to the one-per-update rule, requested once) showed 27 ids in 799501621–799501647; a single object (799501621) was then fetched by `CATNR` in CSV/JSON/XML/KVN/TLE. Real provider data, seven requests in total.

**D-013 — The `last-30-days` TLE 404 was recorded by hand from the tool's log and the tool now saves unexpected non-200 bodies before stopping; TLE-format entries whose 404 is informative carry `allow_error`.**
Alternatives: re-request the URL to capture headers; drop the fixture.
Reason: CelesTrak says a 403/404 "is not going to change by repeating the request"; the body was printed verbatim by the tool, so nothing is lost except response headers, which the metadata file says are missing.

**D-014 — Legacy `satcat.txt` (9.4 MB) fetched once and kept out of git; Phase 3 commits an excerpt plus the full-file SHA-256 and derived facts.**
Alternatives: commit the whole file; also fetch `satcat.csv`.
Reason: its only role in the corpus is to show the <70000 cutoff, which the excerpt, hash and counts prove; `records.php` supplies the per-object CSV/JSON records.

**D-015 — Catalog number 69999 is present in the legacy file and in `records.php`, so it is the "largest 5-digit id" for the cutoff case (as D-011 anticipated).**

**D-016 — Derived Alpha-5 TLE lines will cover letters A and T only.**
Alternatives: invent ids for the other 22 letters.
Reason: the only real catalog numbers inside 100000–339999 are 100000–100789 (letter A) and the 270000–270449 Space Fence analyst objects (letter T). The remaining letters and the I/O skips are covered by the specification vectors (D-001). No fabricated ids.

**D-017 — `expected.json` records per-format expected values where the provider's renderings differ, instead of one canonical record per object (amends PLAN.md §2.2).**
Alternatives: one canonical record with tolerances.
Reason: the inventory shows the TLE rendering truncates eccentricity to 7 digits and BSTAR to 5 mantissa digits, and SupGP TLE epochs are rounded to the TLE's 864 µs resolution. A single expected record would assert a lossless round trip that the data contradicts; per-format values let a parser be judged against exactly what it read, and the case notes state which digits are lost.

**D-018 — New case `supgp-celestrak-classification-c`; all SupGP raw files remain gitignored until redistribution is settled.**
Alternatives: fold SupGP quirks into other cases.
Reason: SupGP records differ from GP in ways that break GP-only parsers (`CLASSIFICATION_TYPE` `C`, `ELEMENT_SET_NO` 0, extra `RMS`/`DATA_SOURCE` columns, 72000-series ids, reused `OBJECT_ID`), and their redistribution status is the weakest (RESEARCH §11.3).

**D-019 — CelesTrak's silence on redistribution is recorded as silence, not permission; publishing raw fixtures is deferred to the owner; building continues.**
Alternatives: treat "freely available" as a licence; stop work.
Reason: CLAUDE.md ("interpret licences and terms strictly") and the owner's instruction that this decides publication, not construction. Options are laid out in PLAN.md "Phase 2 amendments".

**D-020 — Phase 3 will validate CelesTrak XML against the OMM 2.0 schema set fetched from SANA by direct URL, and separately report validity against the current 3.0/4.0.0 set.**
Alternatives: validate only against 3.0 with the version attribute masked.
Reason: a HEAD request shows the 2.0.0 master schema still resolves at the URL CelesTrak declares (RESEARCH §12), so the document can be validated against what it claims to be, and forward-compatibility with the current standard can be reported as a separate finding.

**D-021 — Error budget transparency.** Five non-200 responses were received from celestrak.org across both phases: two from guessed documentation URLs during research (a lesson: find links on pages, do not guess), three deliberate one-time TLE-format probes kept as fixtures. All well under CelesTrak's 50-per-2-hours threshold. Some one-off documentation fetches in Phase 1 carried the owner's e-mail in the User-Agent; the fetch tool does not (D-007).

**D-022 — Clean re-capture of the three window-dependent TLE endpoints (owner instruction), one request each, at 2026-09-21T00:41Z.**
Result: `last-30-days` TLE again `HTTP/1.1 404 Not Found`, body `No GP data found`, now with the full header set; `analyst` and `DECAYING` TLE responses are byte-identical to the 00:11Z captures (same GP update window), so the 565→219 and 82→79 omission counts now rest on captures with full provenance. The hand-transcribed entry is kept, marked "original observation" and cross-linked as superseded for citation. The fetch tool now records the status line, every response header in order, the request headers and start/finish timestamps for every response. Re-captures are separate fetch-list entries with a `recapture_of` field; the duplicate-URL guard stays.

**D-023 — Corpus design (owner decision): no raw CelesTrak bytes are shipped. The public corpus is specification vectors, clearly labelled derived re-encodings, `expected.json`, SHA-256 checksums of the files we tested, and the fetch script that rebuilds `raw/` on the user's machine under CelesTrak's own terms.**
Consequence recorded here, not silently: checksums prove parity with what we tested **only for endpoints whose bytes are stable**. Live group queries (`GROUP=`, `SPECIAL=`, current `CATNR=`) change every GP update, so a user's re-fetch will not match our checksums and our exact expected values will not apply to their bytes. The design therefore has two tiers per case: **stable-source fixtures** (CelesTrak's `gp-first.php` first-ever records, SATCAT records, derived files, vectors) with frozen expected values verified by checksum, and **live-window checks** (structural and cross-format invariants that hold for any snapshot, plus our snapshot's values published as a dated reference). Stage F fetches the stable sources.

**D-024 — Stable sources chosen: `gp-first.php` for 25544 (1998 record, already partly fetched), 100000 (Saramago's first record), 270449 (a Space Fence analyst id, letter T), 81011 (an 8xxxx analyst id), and 69999 (largest 5-digit id).**
Alternatives: only live queries; more objects.
Reason: "first GP data available" for a given catalog number should not change over time, giving reproducible bytes; the set covers 19xx epoch year, 6-digit, both analyst blocks and the 70000 boundary in about 20 small requests. Stability is an assumption stated in the manifest; the checksum comparison in the fetch script will reveal any drift.

**D-025 — Raw provider files stay tracked in this private repository; the public release is a curated export into a fresh repository.**
Alternatives: remove raw files from git now; rewrite history before publishing.
Reason: the auditor needs the exact bytes we tested in one place; the Phase 2 commit already contains them, so a public push of this history is ruled out regardless. An allowlist-driven export (Phase 4) is simpler and verifiable. SupGP raw files remain gitignored per D-002.

**D-026 — `expected.json` carries per-format values only where the renderings differ, hoists constant per-set metadata out of the records, and omits whole TLE lines.**
Alternatives: one canonical record with tolerances (PLAN §2.2); full per-record metadata (1.5 MB for the analyst case).
Reason: D-017 as implemented; field substrings and parsed values are analysis, whole lines are the provider's bytes. Total expected.json size 2.9 MB for 16 cases.

**D-027 — A name longer than 24 characters is cut to 24 in derived TLE line 0 and reported as `object_name_truncated_to_24`, not as a value difference.**
Reason: the TLE format's line 0 is documented as a 24-character name; the only such name in the data (100465, 27 characters) belongs to a six-digit object, so the rule could not be checked against CelesTrak output; recorded in the provenance sidecar and the precision-loss case.

**D-028 — The TLE renderer used for derived lines rounds the BSTAR / second-derivative mantissa half up to five digits and truncates eccentricity to seven digits.**
Alternatives: truncate both (251/304 match); round both (257/304 on line 2).
Reason: only this combination reproduces all 304 CelesTrak TLE lines exactly; no document states either rule, so it is recorded as observed provider behaviour (ambiguity `ecc-truncation-vs-mantissa-rounding`) and as the named case `tle-vs-omm-precision-loss` (owner instruction).

**D-029 — Library failures found by the cross-check are recorded as library behaviour, not as corpus defects, and not worked around in the reference readers.**
Findings (python-sgp4 2.27, Skyfield 1.55): nine-digit ids cannot be initialised from OMM data; XML records with an empty OBJECT_ID raise TypeError; export_tle writes a zero second derivative as ' 00000-0' where CelesTrak writes ' 00000+0'. All three are exactly the kind of defect the corpus exists to expose; they go into the Phase 4 breakage catalogue and the per-case `library_findings`.

**D-030 — Both complete SANA schema sets (2.0.0 and 4.0.0, 14 files each) are vendored under `schemas/` with a SOURCE.md of URLs and hashes.**
Alternatives: only the OMM modules (fails: the master schemas include every message type).
Reason: validation must run offline and against exactly the files CelesTrak declares; the CCSDS documents are published for free use and are redistributed unmodified.

**D-031 — Derived KVN variants may fill header keywords with values describing the derived message itself (ORIGINATOR GP-OMM-CONFORMANCE-CORPUS, generation time, a MESSAGE_ID, a CLASSIFICATION text).**
Alternatives: keep all headers blank like CelesTrak.
Reason: CCSDS makes CREATION_DATE and ORIGINATOR mandatory and non-empty; a variant that exercises a compliant header needs real values, and the only truthful ones are ours. The provenance sidecar says so.

**D-032 — Specification vectors that go beyond the six official Space-Track examples (letter boundaries, skip boundaries) are derived arithmetically from the published table and labelled as such; invalid-input vectors state the reason.**
Reason: the table is normative; the boundaries follow from it; a reader can recompute them.

**D-033 — The SupGP snapshot values (one nine-digit record, the G15-27 stack and single nominals, the 27 nine-digit ids) are published in expected.json as a dated reference, flagged with ambiguity `supgp-redistribution` so the owner can strip them before release.**
Alternatives: omit all SupGP-derived values.
Reason: they are the only real nine-digit evidence and are analysis values, not raw bytes; the flag keeps the removal a one-line decision.

**D-034 — Two guessed documentation URLs earlier produced 404s; from Phase 2 on, every URL is taken from a page link or the provider's documentation, never guessed.** (Lesson recorded; see D-021.)

## 2026-09-21 (Phase 4)

**D-035 — `.gitignore` guard against Space-Track data, placed before any Space-Track account exists (owner instruction).**
Patterns match any path component containing space-track / space_track / space track / space.track / spacetrack in any letter case, plus directories of those names. Verified with `git check-ignore` on eleven sample paths (eight blocked, three unrelated names such as `spacecraft-tracking.md` not blocked). One speculative pattern for export-file names was written wrongly (`?` is "any one character" in gitignore, not "optional") and removed rather than kept broken. The export tool applies the same guard by regex.

**D-036 — The zero second-derivative exponent sign fully explains every `export_tle` byte mismatch: verified, not inferred.**
Against the 306 CelesTrak-served TLE/2LE records (recaptures excluded): 225 have a zero second derivative and 0 export byte-exactly, and in all 225 the only differing columns are 51 (`+` vs `-`) and 69 (checksum); flipping the sign and recomputing the checksum reproduces every line. The 81 records with a non-zero second derivative all export byte-exactly. Line 2 is byte-exact in all 306. The same holds for the 604 derived lines (591 mismatches, all explained). The upstream draft states these numbers.

**D-037 — Evidence-basis statements added to the precision-loss and derived-Alpha-5 cases (owner instruction): the rendering rule was derived empirically from 304 CelesTrak record pairs and is not documented in any specification we located; the renderer was validated only against sub-100000 output.**
The owner verifies the Alpha-5 encoder separately against Space-Track; no Space-Track data enters the repository and the public claim describes the verification, not the data.

**D-038 — Runner design: data-driven from `manifest.json` and `expected.json`, standard library only, Python 3.9+, duck-typed parser protocol (`parse(raw, fmt)` plus four optional vector hooks), external-command mode for non-Python parsers, and two oracles: frozen expected values when the file's SHA-256 matches the tested snapshot, otherwise the corpus's own reference reader applied to the user's bytes, labelled as such in every report line.**
Alternatives: require the user's parser to emit our exact JSON schema; skip live files entirely.
Reason: any parser in any language can be tested; the report never presents a reference-derived comparison as a human-verified one.

**D-039 — Tolerances for the parser under test: floats compared at 1e-12 relative, epochs within 2 microseconds; everything else exact. The oracle values themselves stay exact decimal strings.**
Alternatives: exact comparison of everything (python-sgp4 then failed on 1-microsecond Julian-date float noise and on 1e-16 unit-conversion noise, which is not a conformance defect); looser tolerances (would hide the 86-microsecond SupGP epoch quantisation, so the TLE/OMM epoch check keeps its own 432-microsecond rule).

**D-040 — Library findings are reported as failures of that adapter, never worked around: nine-digit ValueError, XML empty-OBJECT_ID TypeError, classification reset to 'U' by `sgp4init` after `omm.initialize`, lenient Alpha-5 decoding (I, O, lowercase, four characters accepted; negative encodes to '-0001'). The first three have upstream drafts in `docs/upstream/` (the fourth, minor, is noted in the third's sibling draft); the owner files them.**

**D-041 — LICENSE copyright line reads "Honorius Neogy", the name used as git author, which was inferred from the owner's e-mail address rather than stated. Flagged for the owner to confirm or change before publication.**

**D-042 — Ordinary users' `tools/fetch.py` runs skip the three maintainer-only re-capture entries (`--include-recaptures` restores them).**
Reason: they exist to document provenance of a window-dependent observation; a user re-requesting the same endpoint twice would waste CelesTrak's bandwidth for nothing.

**D-043 — Public release = `tools/export_public.py` over `PUBLIC_ALLOWLIST.txt` into a fresh directory that becomes a new repository; the tool refuses `fixtures/*/raw/` and any Space-Track-named path and writes an export manifest with hashes. Dry run: 131 files, 0 refused. This repository's history is never pushed (D-025).**

**D-044 — CI runs offline only (unit tests plus the three shipped cases with the reference and naive adapters, Python 3.9 and 3.12). Cases needing raw files report `skip` until `tools/fetch.py` has run locally; CI never fetches from CelesTrak.**
Reason: a fetch per push would multiply load on a shared, non-profit service for no evidentiary gain.

**D-045 — A fourth, minor upstream draft (classification dropped by `omm.initialize`) was added beyond the three requested, because it was found during Phase 4 and silently alters a field; the owner decides whether to file it.**

**D-046 — Correction to D-040's wording:** the fourth finding (classification reset by `sgp4init`) has its own draft, `docs/upstream/python-sgp4-omm-initialize-drops-classification.md`, not a note inside another draft. D-045 is accurate; D-040 is left as written per the append-only rule.

## 2026-09-21 (owner decisions after the Phase 4 report)

**D-047 — Copyright holder is NEOGY LLC (owner decision; the owner's instruction called this D-046, a number already used by the correction entry appended after the Phase 4 report, so it is recorded here as D-047). LICENSE updated; the README names Honorius Neogy (NEOGY LLC) as maintainer.** The personal name remains the one used as git author since Phase 1, which was inferred from the owner's address and not corrected by the owner when flagged (D-041).

**D-048 — Tolerances approved (D-039) with a reporting requirement (owner decision): every check now yields `exact` or `pass-tolerance` separately, and a `pass-tolerance` item carries per-field count, mean signed difference and maximum, so a systematic sub-tolerance bias is visible.**
Implementation: three-state comparison (`exact` / `tolerance` / `mismatch`) with signed differences; CLI table gains a `tol` column; the reference adapter must be exact and the test suite enforces it. The TLE-versus-OMM epoch rule (432 µs) is the provider's own quantisation and is reported as an observation on an exact pass, not as a parser tolerance; treating it as one made the reference adapter look tolerance-dependent, which was wrong.

**D-049 — SupGP-derived snapshot values are withheld from the public release (owner decision). Definition: the element values (epoch, mean motion, eccentricity, angles, BSTAR, first and second derivative) and raw TLE field substrings of CelesTrak supplemental records. Catalog numbers, object names and ids, counts, hashes, URLs and aggregate statistics are metadata and stay.**
Mechanics: `tools/public_scrub.py` (single definition), applied by `tools/export_public.py` on the way out (records of the two SupGP cases emptied and marked `records_withheld`; SupGP pair items removed from the two pairs cases, summaries kept), by `tools/make_failures.py` (value details withheld for those cases) and enforced by `tests/test_export.py`, which exports to a temporary directory and fails if any distinctive SupGP value string appears anywhere. `docs/INVENTORY.md` is dropped from the allowlist because it quotes SupGP field values. The runner falls back to the reference-reader oracle for the withheld cases and labels it. The leak test's distinctive set excludes four-decimal angles, seven-digit eccentricities and zero fields because identical values were found in unrelated GP records (false positives, verified), leaving epochs, mean motions and non-zero drag terms. The catalog-id text vectors gained a `parse_catalog_id` hook so nine-digit parsing is exercised without any SupGP element set.

**D-050 — export_tle report reproducer replaced (owner instruction) by an ordinary five-digit TLE: the CCSDS 502.0-B-3 annex G example rendered in CelesTrak's layout with a zero second derivative written `+0`; verified to differ from `export_tle` output at columns 51 and 69 only. One variable per report.**

**D-051 — Empty-OBJECT_ID report now offers a pull request; the patch is prepared, not submitted (owner instruction).**
`docs/upstream/patches/0001-omm-tolerate-empty-or-UNKNOWN-OBJECT_ID.patch`: `parse_xml` treats empty element text as `''`; `initialize` derives `intldesg` only from a `YYYY-NNNP...` value (empty and `UNKNOWN` give `''`; today `UNKNOWN` yields `'KNOWN'`); two tests in the style of `sgp4/tests.py`. Verified on a temporary copy of the installed package: applies cleanly; before the patch the test body raises `TypeError`; after it the new tests and all 47 functions of python-sgp4's own test module pass. Upstream sources for the diff were fetched from master (`omm.py` identical to the released 2.27). An earlier "before" check in the session used the wrong OBJECT_ID string and proved nothing; it was redone.

**D-052 — Next step is an independent audit in a fresh session (owner decision); this session stops after committing.**

**D-053 — Correction to D-049's last sentence: the leak test's distinctive set is epochs, mean motions and TLE epoch fields only. Five-digit drag terms were also removed after they matched unrelated objects' eccentricity and BSTAR strings (verified false positives in `analyst-objects`, `alpha5-tle-derived` and `bstar-and-derivative-forms`). The withholding definition (all SupGP element values) is unchanged; only what counts as proof of a leak is narrower.**

## 2026-09-21 (independent audit and its resolution)

**D-054 — Independent audit received (`AUDIT.md`, produced by a separate AI session with no access to the building context, instructed to trust nothing and recompute independently). Result: no wrong expected value (65,887 field comparisons, 60/60 sample); three critical documentation/tooling findings, eight major, a set of minor. Owner instruction: fix every finding, record each resolution here, annotate AUDIT.md without altering the auditor's text, then stop for review.**

**D-055 — C1 resolved by implementing the drift check, not by retracting the claim.** `tools/fetch.py` now has `manifest_sources`, `drift_report` and `print_drift`: after every run, and on demand with `--check-drift` (no fetching; exit code 2 if any stable source drifted), every file on disk is compared with the SHA-256 recorded in `manifest.json`; a stable-tier source whose bytes differ is printed as `DRIFT` with the consequence (frozen expected values no longer apply; gp-first stability assumption violated or snapshot out of date); live-tier differences are only counted. `tests/test_fetch_drift.py` covers match, live drift, stable drift, missing files, tier precedence and the real snapshot. README, `docs/PLAN.md` and the `gp-first-stability` ambiguity now describe the implemented behaviour. This supersedes the unimplemented promise in D-024 and resolves M5 (same defect, decision-log side).

**D-056 — C2 resolved: the float tolerance is now genuinely relative, |got − want| / max(|got|, |want|) ≤ 1e-12, with no floor. Exact zero on either side requires exact zero** (no relative scale exists for zero, and a parser that returns a tiny non-zero for a zero drag term is wrong, not approximately right). README table and D-039's wording corrected in the README. All three adapters re-run: reference still 16/16 exact; python-sgp4's case statuses and every item status are unchanged by the change (before/after report diff: none); FAILURES.md regenerated.

**D-057 — C3 resolved.** RESEARCH.md §13 corrected with a marked note (all 565 current analyst records carry the literal OBJECT_NAME `UNKNOWN`; 563 have an empty OBJECT_ID); the analyst case's coverage line and interpretation now say so explicitly and cannot be read as "real names".

**D-058 — M1 resolved.** The 24-character line-0 limit is now described as a rule of the CelesTrak format document, not an observed rendering behaviour: it occurs in none of the 304 provider pairs and only in one derived line (100465). Removed from the precision-loss interpretation's list of observed rules, added as a coverage gap, README case row corrected.

**D-059 — M2 resolved by test.** `tests/test_roundtrip.py` parses every TLE record present (CelesTrak-served, including re-captures, and the 604 derived lines: 1,208 records in 15 files), expresses it as OMM keyword text, renders it with the corpus rules and compares bytes: all 1,208 byte-exact. The claim "TLE → OMM → TLE round-trips" is kept and now cites the test.

**D-060 — M3 resolved.** README and the supgp case now state what primary sources support: the legacy range ends at 69999 (CelesTrak); 80000–89999 is the analyst range (Space-Track); other uses of the 70000–99999 block, including the 72000-series ids, rest on a secondary source and are labelled as such. "Pre-catalog" removed.

**D-061 — M4 resolved: reversal of D-014.** No excerpt of `satcat.txt` exists and none will: under D-023 (no raw provider bytes shipped) an excerpt of the legacy file would itself be raw provider bytes. What the excerpt was meant to prove (line count, id range 1–69999, contiguity, absence of ids ≥ 70000, the full-file SHA-256, parsed lines for 25544 and 69999) is in `fixtures/satcat-70000-cutoff/expected.json`, and the runner's data check recomputes the facts from the user's own fetch.

**D-062 — M6 resolved.** Final fetch-error tally: eight non-200 responses from celestrak.org across all phases — two guessed documentation URLs (Alpha-5.php, privacy.php; Phase 1) and six deliberate one-time TLE-format probes kept as fixtures (saramago.tle, last-30-days.tle and its owner-instructed re-capture, starlink-38381 TLE, saramago-first.tle, analyst-270449-first.tle). D-021's "five" was correct at the end of Phase 2 and stands as that phase's figure; RESEARCH.md §12 updated with a marked note.

**D-063 — M7 resolved.** The export_tle draft now says nine queries returned records (five further TLE-format requests returned HTTP 404); the record count 306 was and is correct.

**D-064 — M8 resolved.** The README's `docs/` row no longer lists INVENTORY.md (it is deliberately not exported, D-049); `docs/README-draft-ai-assistance.md` removed from the public allowlist (kept privately as the Phase 3 draft record).

**D-065 — Minor findings, all fixed.** Version unified to `0.1.0.dev0` (manifest `corpus_version`, README, pyproject, package). Fetch-list duplicate guard is case-insensitive; entries carrying `recapture_of` are the only permitted repeats. `--skip-case` added to `tools/fetch.py`; README fetch text corrected ("never re-fetches a file it already has unless `--force` and older than two hours"). "29 of 29" restated as 28 distinct records (29 file-records counting one object's CSV and XML). Uncited statements cited or softened: epoch-tolerance rationale now cites the cross-check's observed ≤1 µs; "served by Space-Track only" → "Space-Track serves it, CelesTrak does not"; "since 2020" restricted to CelesTrak (May 2020, primary) and Space-Track's GP class without a date; "XML libraries" → "Python's ElementTree (verified); other libraries may do the same". `docs/FAILURES.md` now carries its generation time and, per adapter, the run time, gpconf version, corpus version and parser from the report JSON (the runner writes `generated_at`). The four KVN variants the naive adapter fails are named (v02, v03, v04, v05; v01 and v06 pass), verified from the naive report. The omm-xml-schema text notes the dependency on SANA continuing to serve the 2.0.0 files at their direct URLs and points to the vendored copies. `tools/_fetch-run-*.log` removed from the allowlist. Correction to D-030: the 2.0.0 schema set has 12 files, the 4.0.0 set 14.

**D-066 — Publication of the audit.** `AUDIT.md` is committed with a resolution-notes section appended after the auditor's text, which is unaltered, and added to the public allowlist. Pre-allowlisting check: it contains no Space-Track data (the term appears only as a word in findings about the guard and the sources); its appendix sample contains one row from the nine-digit SupGP case, which `tools/public_scrub.py` now withholds from the exported copy with a note (the private original unaltered); the auditor's leak-scan sentence quotes a BSTAR string that an analyst GP record shares with a SupGP record, which identifies the GP record's value and stays. The README's AI-assistance section states that the audit is complete, links AUDIT.md, and says precisely that it was performed by a separate AI session with no access to the building context and was not a human review.

## 2026-09-21 (post-audit review)

**D-067 — Public copy of AUDIT.md (owner decision): the one Appendix A row from the `nine-digit-supgp-launch-nominals` case is withheld in the exported copy, per D-033 as implemented by D-049.** `tools/public_scrub.py` now inserts a notice under the appendix heading and a pointer under the title stating exactly what is withheld and that the private original is intact; `tests/test_export.py` checks for the notice and the absence of the row. The maintainer's resolution-notes preamble in AUDIT.md and the README's audit paragraph were qualified so that no public document describes the public copy as unaltered without that qualification (D-066's "which is unaltered" refers to the private original; this entry is the precision).

**D-068 — Record-count correction: 1,208, not 1,210.** The round-trip test and the CROSSCHECK table both cover 1,208 TLE records: 604 CelesTrak-served line pairs (306 distinct plus the 298 in the two owner-instructed re-capture files) and 604 derived Alpha-5 lines. The figure 1,210 appeared once in the repository (`docs/PLAN.md`, Phase 3 verification summary) and in session reports; it was a miscount, now corrected in place with a marker. No expected value or test depended on it.

**D-069 — Space-Track verification tool (owner instruction): `tools/verify_against_spacetrack.py`, standard library only.** Design: credentials only via `input()`/`getpass()`, never arguments, never logged or written; POST login to `/ajaxauth/login` with a cookie jar, exactly four GET queries (current GP for 100000–100020 and 270000–270020; first `gp_history` record of 100000 and of 270449; `format/tle`, `emptyresult/show`) at least 3 s apart, then `/ajaxauth/logout`; responses saved only under `~/spacetrack-verify/`, and the tool refuses to run if that path resolves inside the repository; comparison against `derived/alpha5-tle/*.tle` by catalog field and epoch (byte compare with differing column numbers when both match; encoding-field, international-designator and 0.05° inclination checks when only the field matches; line-2 field must equal line-1 field; strict Alpha-5 decoding; decoded id must lie in the queried range); output limited to catalog fields, verdicts, column numbers and summary counts; distinct non-zero exit codes for login failure, HTTP error, empty result, verification defect and refused output path. The comparison logic is unit-tested with the repository's own derived lines on both sides (`tests/test_verify_tool.py`); no Space-Track output is fabricated. The agent never ran the tool and never reads its output. Guard consequences: the tool's file name matches the Space-Track name guard, so `.gitignore` carries a single negation for that path and `tools/export_public.py` a single named exception; data paths (`spacetrack-verify/`, `space-track/…`, `SpaceTrack_*.tle`) remain blocked, verified with `git check-ignore`. The README gained a subsection explaining that anyone with their own account can run the tool and that the corpus redistributes no Space-Track data.

**D-070 — Owner's Space-Track verification run (2026-09-21) and what it changes.** The owner ran `tools/verify_against_spacetrack.py` and shared the tool's printed fields, verdicts, column numbers and summary (no element values, no lines; the agent never read the saved responses). Result: 44 records (21 current GP records 100000–100020, 21 for 270000–270020, the first historical record of 100000 and of 270449); summary `exact 0, same_epoch_differs 21, encoding_only 2, no_derived_line 21, invalid_field 0, line2_field_mismatch 0, out_of_range 0, defects 0`. Interpretation by TLE column layout: (a) the Alpha-5 encoding is corroborated by provider output for both letters that exist in real catalog numbers, A and T: every field decoded to the queried id and every line-2 field equalled line 1; (b) no line was byte-identical because of two rendering conventions, not encoding: Space-Track writes a zero second derivative as `00000-0` (column 51, with the checksum at 69) where CelesTrak writes `00000+0`; and Space-Track's line-2 eccentricity differs from CelesTrak's truncated rendering in its last one or two digits (columns 32–33, on 9 of 21 same-epoch records), consistent with rounding; (c) the first historical record of 100000 on Space-Track differs from CelesTrak's `gp-first` record at the same epoch in the international designator (columns 10–16) while line 2 is identical, so a CelesTrak "first record" may carry metadata updated after first publication; (d) 21 records had no derived counterpart (100001–100020 predate the 30-day snapshot; 270002 was not in the analyst group) and two matched by field only because Space-Track holds newer epochs. Consequences recorded: the precision-loss rule is now described as CelesTrak's rendering, not the TLE format's; the derived-Alpha-5 case's evidence basis and gap, the `ecc-truncation-vs-mantissa-rounding` and `gp-first-stability` ambiguities, and the README gap and tool paragraphs describe the verification; python-sgp4's `export_tle` sign convention is Space-Track's, which the upstream draft should say when filed (it already notes Space-Track was not checked by the project; the owner may add this observation). No Space-Track data entered the repository; the claim describes the verification only.

## 2026-09-21 (after the owner's Space-Track run)

**D-071 — Rounding confirmed by prediction; count corrected from nine to eight.** Using repository data only, the eccentricity text of the CelesTrak OMM source behind each of the 21 same-epoch derived lines (analyst.csv for T0000–T0020, saramago-first.csv for A0000, analyst-270449-first.csv for T0449) was rounded half up to 7 digits and compared with truncation. Rounding differs from truncation for exactly 8 records, T0000, T0003, T0008, T0011, T0016, T0018, T0020 and T0449, three of them with a carry into the sixth digit (T0003, T0020, T0449), and those are exactly the 8 records whose line 2 differed at column 33 in the owner's run, with the three carries at columns 32–33; the other 13, where rounding equals truncation, matched (A0000 among them). The prediction holds 21 of 21, so the precision-loss case now states Space-Track's eccentricity rounding as confirmed rather than "consistent with". All 21 derived lines carry a zero second derivative, so the column-51 difference on every record is the +0/−0 sign. D-070 said "9 of 21"; the correct count is 8, and my report of the run said nine: a miscount from the screenshot, corrected here.

**D-072 — export_tle report withdrawn as a bug report (owner decision) and rewritten as an informational note marked not to file.** Reason: python-sgp4 writes a zero second derivative as ` 00000-0`, which is Space-Track's rendering, and Space-Track is the outlet of the organisation that issues the element sets; CelesTrak's ` 00000+0` is the outlier. Measured only against CelesTrak lines the behaviour looked like a library defect; measured against the issuing organisation's output it is a provider divergence with python-sgp4 on the issuer's side. README, the cross-check interpretation, the precision-loss case's library note and the patches README now say so; the note keeps the measurements and the reproducer as documentation of the divergence.

**D-073 — Record of who launched the verification tool (owner instruction to record that the agent launched it despite the instruction that the owner would run it).** Owner's account: the agent launched the tool. Session record available to the agent: the agent made no tool call that executed `tools/verify_against_spacetrack.py`; both invocations reached the session as terminal-pane input, the first from the wrong directory and the second after the agent supplied the corrected command in a shell-tagged block, which the desktop app renders with a Run button, so the agent's act was presenting a runnable command that the owner's action executed. The discrepancy is recorded rather than resolved silently; the owner may amend this entry after reading it. On either account the verdict-only output design held: no credentials and no element data entered the session through the tool. The only tool output the agent saw was the screenshot the owner chose to share, which contains catalog fields, verdicts, column numbers and counts.

**D-074 — gp-first records are historical in their elements but can carry metadata assigned after first publication (owner's finding while checking the designator; categories only, no values).** For catalog 100000: Space-Track's earliest record has a blank international designator; Space-Track's current record carries the same designator as CelesTrak; CelesTrak's `gp-first` record shows that designator back-filled; the line-2 elements are identical across all of them. The `gp-first-stability` ambiguity now says so and tells parsers to treat OBJECT_NAME and OBJECT_ID in a gp-first record as current metadata.

**D-075 — Incident record (owner's report, recorded without data).** While checking the designator the owner ran a grep in the Claude Code terminal panel that printed two Space-Track TLE lines. The panel has been cleared; no Space-Track data entered the repository; future inspection of `~/spacetrack-verify/` happens only in a standalone terminal. The agent did not read, quote or use anything from that terminal scrollback (no terminal-read call was made at any point in the session) and will not; it has never opened anything under `~/spacetrack-verify/`.

## 2026-09-21 (publication preparation)

**D-076 — Amendment to D-073 (owner's clarification): the owner launched the verification tool themselves, via the Run button on the command block the agent had posted.** That reconciles the two accounts in D-073: the agent presented a runnable command; the owner's click executed it in the owner's terminal. D-073 is left as written per the append-only rule; this entry is the account of record. The design consequence stands: no credentials and no element data entered the session through the tool.

**D-077 — Version 0.1.0 for publication; CITATION.cff added; Zenodo DOI per release.** `CITATION.cff` names the corpus, NEOGY LLC as copyright holder, the maintainer as author, MIT, version 0.1.0, release date 2026-09-21 and a repository URL placeholder the owner fills in. To keep the citation, the manifest, the package and the README consistent (an audit finding, D-065), `corpus_version`, `pyproject.toml`, `gpconf.__version__` and the README now all say `0.1.0`. The README states that a Zenodo DOI will be minted per release and carries a badge placeholder until the first DOI exists; CITATION.cff gains the DOI then. CITATION.cff is on the public allowlist.

**D-078 — Migration writeup drafted at `docs/writeup/post.md` for publication on neogy.dev; not part of the public export** (the allowlist names the docs files individually and does not include `docs/writeup/`). Every claim in it cites a case id, a DECISIONS entry or a test; it states the AI-assisted method and the independent audit; it contains no Space-Track values. Under 1,500 words.

**D-079 — Public export produced and verified, unpushed (owner instruction).** `tools/export_public.py` writes the allowlisted subset of the private repository (at the commit that adds this entry) into `../gp-omm-conformance-public`, which is initialised as a new repository with a single initial commit authored by the owner and no remote. Verification, run on a trial export and again on the final one with an independent script outside the repository: tests pass in a fresh `git clone` of the public repository and the reference adapter reports 16 of 16 cases exact; no `fixtures/*/raw` directory, no file byte-identical to a private raw file, no verbatim raw TLE line or CSV row anywhere; none of the SupGP signature strings (from the private expected values and the raw SupGP files) anywhere; no Space-Track-named path other than the verification tool's own source, and no TLE-looking line outside `derived/alpha5-tle/` other than the CCSDS annex example (catalog 23581) used in the upstream notes; no e-mail address; every file matches a `PUBLIC_ALLOWLIST.txt` pattern, plus the tool-generated `EXPORT-MANIFEST.txt` (path, bytes, SHA-256 of every exported file). Five files were scrubbed on the way out (four expected files and the public copy of AUDIT.md, which states what it withholds). Publication itself (adding a remote, pushing, minting the DOI, filling the repository URL in CITATION.cff and README) is the owner's step.

**D-080 — Correction to D-079 (found during the final verification): in a fresh clone of the public repository, before `tools/fetch.py` has run, the reference adapter reports 3 cases exact (the shipped vectors, derived Alpha-5 lines and KVN variants), 12 skipped for missing raw files and 1 not exercised; "16 of 16 exact" holds in the private repository with the tested snapshot on disk, and, after a user fetches, for the stable-tier sources whose hashes still match, while live-tier sources are compared against the reference reader.** The public export was regenerated so that its copy of this log carries the correction; the independent verification script's file walk was also fixed (it had excluded `.gitignore` and `.github/workflows/ci.yml` by a prefix filter) and re-run over every file.

## 2026-09-21 (publication)

**D-081 — Publication authorised by the owner (employment-agreement check complete), scoped to: confirm the GitHub account, fill the public URL, regenerate and verify the export, create the public repository with description and topics, push; no release or tag until Zenodo is enabled.** Account check: the GitHub CLI is authenticated as `hneogy` (a user account, display name Honorius Neogy; the token scopes were `repo`, `workflow`, `read:org`, `gist`, and the owner added `user` so verified addresses could be listed); the account's primary verified address, which is also the private repository's git author address, was used as the commit author. The public URL `https://github.com/hneogy/gp-omm-conformance` was filled into CITATION.cff, the README (citation and clone line) and the writeup; the Zenodo badge placeholder remains until the first DOI. The public export was regenerated from the private commit that follows this entry as a single commit authored by the owner and re-verified from a fresh clone with the independent script (D-079/D-080 procedure).

**D-082 — D-081 was reworded minutes after being written, before publication, to describe the commit-author address instead of spelling it out, so that no literal e-mail address appears in a published document (the README's maintainer line deliberately carries none; the address is visible only as ordinary git author metadata, which the owner chose). Recorded here because the log is append-only and the earlier text was changed.**

**D-083 — Published.** Owner confirmed that `hneogy` is their personal GitHub account and authorised creation and push. `CITATION.cff` already carried `affiliation: "NEOGY LLC"` on the author entry (Zenodo reads it for the DOI record); verified present in the export rather than added twice. The public repository `https://github.com/hneogy/gp-omm-conformance` was created public on 2026-09-21 with the description "Conformance corpus for orbital-data parsers crossing the five-digit catalog-number boundary: Alpha-5, six- and nine-digit NORAD_CAT_IDs, CCSDS OMM as served by CelesTrak. No raw provider data redistributed." and the topics orbital-mechanics, tle, omm, satellite, sgp4, celestrak, conformance-testing, alpha-5; `main` was pushed as the single export commit authored by the owner; no release and no tag were created (Zenodo must be enabled first; the first tag mints the first DOI). The private build repository remains the source of truth and is never pushed; future public updates are regenerated exports.
