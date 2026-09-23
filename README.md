# gp-omm-conformance

A conformance corpus for orbital-data parsers crossing the five-digit catalog-number boundary:
Alpha-5 TLEs, six- and nine-digit `NORAD_CAT_ID`s, and the CCSDS Orbit Mean-Elements Message
(OMM) in CSV, JSON, XML and KVN, as actually served by CelesTrak.

It answers one question for a developer: **does my parser survive the migration?** You point it
at your parser; it tells you, case by case, what breaks and why, with every expected value
traceable to a provider response whose URL, retrieval time and SHA-256 are recorded. One case
(`tle-writer-alpha5`) asks the same of code that *writes* TLEs: Alpha-5 in the catalog field,
valid lines, and a refusal for the numbers the format cannot carry.

Status: version `0.2.1`, a patch release: fixes to the runner, the reference readers, `check-tle` and
the tooling from the audit follow-up of 2026-09-23; the seventeen cases and their frozen expected values
are unchanged, and what the corpus reports about the naive and python-sgp4 adapters is unchanged. The
independent audit (`AUDIT.md`) covered v0.1.0; neither the writer-side case of v0.2.0 nor the fixes of
v0.2.1 have been separately audited. Maintainer: Honorius Neogy (NEOGY LLC).

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22867654.svg)](https://doi.org/10.5281/zenodo.22867654) See `DECISIONS.md` for the full decision log and `MANIFEST.md` for every case,
source and known gap.

## The migration in one page

**What changed.** On 2026-07-11 the US Space Force catalog assigned number 100000 (to the
Portuguese CubeSat SARAMAGO) after exhausting the five-digit range, which ends at 69999 (CelesTrak).
Of the 70000-99999 block, primary sources describe only 80000-89999, the analyst range (Space-Track);
what the rest of the block is used for is reported by secondary sources only. Every object catalogued
since has a six-digit number. The fixed-width
TLE format has room for five characters, so two coexisting answers exist:

- **Alpha-5** (US Space Force stopgap; Space-Track serves it, CelesTrak does not): the first digit is replaced
  by a letter, A=10 ... Z=33 with I and O skipped, so 100000 becomes `A0000` and the ceiling is
  339999. Only TLE/3LE lines carry it.
- **OMM** (CCSDS 502.0-B-3, served by CelesTrak since May 2020 and by Space-Track's GP class): `NORAD_CAT_ID` is
  an integer of up to nine digits; four-digit years; no fixed widths.

**What CelesTrak does.** It emits no Alpha-5 at all. A TLE/3LE/2LE request returns only the
objects below 100000; if none qualify (today, any group of recent launches) the response is
HTTP 404 with the body `No GP data found`. The OMM formats return everything. CelesTrak's
default format has been CSV since 2026-05-09.

**What breaks** (each item is a corpus case; see `docs/FAILURES.md` for the evidence):

1. `int()` on TLE columns 3-7, or any five-character assumption about the catalog number.
2. Treating an empty TLE file or a 404 as "no new data" and silently losing every object
   launched after 2026-07-11.
3. Requiring `OBJECT_ID`: analyst objects have an empty one in every format, and Python's
   ElementTree returns `None` for the empty element (other XML libraries may do the same).
4. Requiring the constant metadata keywords: CelesTrak CSV/JSON omit `CENTER_NAME`,
   `REF_FRAME`, `TIME_SYSTEM`, `MEAN_ELEMENT_THEORY` and the whole header.
5. One epoch format: CCSDS allows day-of-year, no fraction and a trailing `Z`.
6. Assuming `CLASSIFICATION_TYPE` is `U`, that `ELEMENT_SET_NO` is never 0, or that a CSV has
   no columns you do not know (`RMS`, `DATA_SOURCE` in supplemental data).
7. Comparing a TLE to its OMM digit for digit: the TLE truncates eccentricity to 7 digits and
   rounds the BSTAR and second-derivative mantissa to 5, so OMM to TLE to OMM does not round trip.
8. Reading `MEAN_MOTION_DOT` as the true derivative: the OMM carries the TLE field as printed
   (the ndot/2 convention).
9. Storing the catalog number as an Alpha-5 string internally: python-sgp4 cannot load any
   nine-digit record, and such records are live (18 SDS launch nominals in CelesTrak SupGP).
10. Writing a TLE with the catalog number through an integer format (`%05d`, `f"{n:05d}"`):
    above 99999 that yields six digits, a 70-character line and a checksum over shifted columns.
    The field must be Alpha-5 from 100000, and a number above 339999 cannot be written as a TLE
    at all: the correct output is a refusal, and the record belongs in an OMM format.

**What to change.** Parse the catalog number as an integer from any source; decode Alpha-5
strictly (reject I, O, lowercase) if you read Space-Track TLEs; treat empty `OBJECT_ID` and
`OBJECT_NAME` as legitimate; default the constant metadata; accept all CCSDS epoch forms;
tolerate unknown keys and non-`U` classifications; compare TLE and OMM under the precision
rules; treat a TLE 404 as "unrepresentable in this format", not as an outage; and prefer the
OMM formats, which are what both providers say the future is. When writing TLEs, encode the
catalog number as Alpha-5 above 99999 and refuse numbers above 339999 (or below 0).

## What is in the corpus, and what is not

| in the repository | not in the repository |
|---|---|
| `fixtures/<case>/expected.json`: frozen expected values and structural checks for 17 cases, all numbers as decimal strings | raw CelesTrak responses (`fixtures/<case>/raw/`): rebuilt on your machine by `tools/fetch.py` under CelesTrak's own usage policy |
| `fixtures/<case>/case.md`: what the case tests, how to read a failure, coverage gaps stated per case | Space-Track data, in any form (a `.gitignore` guard refuses such paths) |
| `derived/`: Alpha-5 TLE lines rendered from real CelesTrak OMM records (letters A and T only), six CCSDS-legal KVN variants, each with a provenance sidecar | invented element sets: none, anywhere |
| `vectors/`: specification vectors (Alpha-5 table, catalog-id text forms, two-digit-year pivot, CCSDS epoch strings) | |
| `manifest.json` / `MANIFEST.md`: every source with URL, retrieval time, SHA-256, tier; every check and ambiguity by id | SupGP-derived snapshot values: the element values of CelesTrak supplemental records are withheld from the public release; those cases keep their structural checks and run against your own fetch |
| `schemas/`: SANA NDM/XML schema sets 2.0.0 and 4.0.0, unmodified | |
| `gpconf/`: the runner (standard library, Python 3.9+) | |
| `docs/`: research notes with verbatim sources, cross-check, breakage catalogue, upstream bug-report drafts; `AUDIT.md`: the independent audit and its resolutions | |

Why no raw files: CelesTrak's site states no redistribution terms for its data
(`docs/RESEARCH.md` §11), and silence is not permission. Rebuilding locally means the
provider's terms apply to you directly, fixtures cannot rot unnoticed, and SHA-256 hashes tell
you whether you are looking at the exact bytes we tested.

## Quick start

```bash
git clone https://github.com/hneogy/gp-omm-conformance.git && cd gp-omm-conformance
python3 tools/fetch.py            # once: ~60 requests, ~12.6 MB, 2 s apart, cached, never repeated
python3 -m gpconf run --adapter tests.adapters.reference:Parser   # the control: 17 cases pass
python3 -m gpconf run --adapter tests.adapters.naive:Parser       # the parser most projects have
```

Then write an adapter for your own parser and run it:

```bash
python3 -m gpconf run --adapter mypkg.gpconf_adapter:Parser --json report.json
```

Or drive a non-Python parser as an external command (raw bytes on stdin, JSON array on
stdout, `{fmt}` substituted, exit code 3 for an unsupported format):

```bash
python3 -m gpconf run --cmd "mytool --input-format {fmt}"
```

A TLE writer is driven the same way: `--write-cmd "mytool --emit-tle"` receives one JSON record
on stdin and must print the two (or three) TLE lines; exit code 3 marks writing as unsupported,
and any other non-zero exit is a refusal, which is the correct output for a catalog number the TLE
field cannot represent.

If the writer cannot be wrapped at all (an interactive program such as strf's `rffit`, which
satno2tle drives), check the file it wrote instead. The format checks need nothing else; the
round trip needs the source records the lines were written from:

```bash
python3 -m gpconf check-tle output.tle                          # lines, checksums, catalog field, column layout
python3 -m gpconf check-tle output.tle --against records.csv    # plus the round trip, per record
```

Name lines, `#` comment lines (rffit's trailer) and LF or CRLF endings are accepted; a six-digit
number in the catalog columns is reported with the Alpha-5 form it should have had, and a number the
format cannot carry with the statement that a refusal was the correct output. Exit code 1 on any
failure or when no record is found.

`python3 -m gpconf list` prints the cases and their tags; `--case ID` and `--tag TAG` select.

### Fetching responsibly

`tools/fetch.py` follows CelesTrak's published usage policy
(https://celestrak.org/usage-policy.php): each URL once, files cached with metadata, no
redirects followed, no retries, 2 s between requests, and it stops on the first unexpected
response. The largest file is the 9.4 MB legacy SATCAT; leave it out with
`--skip-case satcat-70000-cutoff` if you do not need the 70000-cutoff case. Do not run the fetch
more than once per two hours; the tool never re-fetches a file it already has (with or without its
metadata) unless you pass `--force` and the recorded `retrieved_at` is at least two hours old, and it
never requests a URL twice in one run (a re-capture entry is requested only when its original is on
disk and two hours old). After each run it compares every file with the SHA-256 recorded in
`manifest.json`, prints a `DRIFT` line for any stable-tier source whose bytes differ and exits 2
(`--check-drift` does the comparison without fetching). If you receive an HTTP 403 read the
body: CelesTrak explains why.

### Two tiers: snapshot and live

Each source in the manifest is `stable` or `live`.

- **stable** (CelesTrak `gp-first.php` first-ever records, derived files, vectors): if your
  fetched bytes hash to the recorded SHA-256, the frozen, human-verified expected values are
  applied exactly.
- **live** (rolling groups, current objects, supplemental data, SATCAT records): CelesTrak
  updates every two hours, so your bytes will differ from the tested snapshot. The runner then
  applies the case's structural checks (cross-format agreement, count relations, presence rules,
  404 semantics) and compares values against the corpus's own reference reader applied to your
  bytes, and it says so in the report. The snapshot values remain in `expected.json` as a dated
  reference.

## Writing an adapter

An adapter is any object with a `parse` method; the hooks are optional: four feed the vector
case and `write_tle` feeds the writer case.

```python
from gpconf.runner import Unsupported

class Parser:
    def parse(self, raw: bytes, fmt: str) -> list[dict]:
        # fmt is one of: tle, 2le, csv, json, xml, kvn
        if fmt == "kvn":
            raise Unsupported(fmt)
        records = my_library.load(raw, fmt)
        return [{
            "norad_cat_id": r.satnum,                 # int
            "epoch": r.epoch,                          # datetime or ISO string
            "mean_motion": r.mean_motion,              # str, Decimal, int or float
            "eccentricity": r.ecc, "inclination": r.inc, "ra_of_asc_node": r.raan,
            "arg_of_pericenter": r.argp, "mean_anomaly": r.ma,
            "bstar": r.bstar, "mean_motion_dot": r.ndot, "mean_motion_ddot": r.nddot,
            # optional:
            "object_name": r.name, "object_id": r.intldes, "classification_type": r.cls,
            "ephemeris_type": r.ephtype, "element_set_no": r.elnum, "rev_at_epoch": r.revnum,
        } for r in records]

    def alpha5_decode(self, field: str) -> int: ...
    def alpha5_encode(self, n: int) -> str: ...
    def two_digit_year(self, yy: str) -> int: ...
    def parse_epoch(self, text: str): ...     # return a datetime for the instant (it is compared), raise on invalid input
    def write_tle(self, record: dict): ...    # -> (line1, line2) or (line0, line1, line2); raise to refuse
```

Values may be strings, `Decimal`, `int` or `float`. The eleven core fields must be present in
every record; optional fields are compared when you return them. `mean_motion_dot` and
`mean_motion_ddot` are expected in the TLE convention (rev/day² and rev/day³ as printed). The
fifth hook, `parse_catalog_id(text) -> int`, feeds the catalog-id text vectors, which include
nine-digit values. `write_tle(record)` receives a record with the same keys as `parse()` returns
and must return the TLE lines it writes; raise for a record it cannot write. For a catalog number
above 339999 or below 0 a refusal is the correct output, and the runner reports it as a pass. The
written lines are read back by the corpus's reference reader and must equal the record at each
field's resolution, by truncation or by rounding half up (both provider conventions exist); the
runner reports which convention it saw, and reports separately, without failing, how the writer
treated the derivatives, element set, revolution and name.

### Tolerances, and how they are reported

The oracle values are exact decimal strings. For the parser under test the runner allows:

| comparison | tolerance | why |
|---|---|---|
| a value you return as a binary `float` | 1e-12 relative: abs(got − want) / max(abs(got), abs(want)); an exact zero on either side must be matched by an exact zero | most decimal element values have no exact double; 1e-12 is far below any physical meaning and above the noise of unit conversions (observed 1e-16 in `docs/CROSSCHECK.md`) |
| an epoch you return | 2 microseconds | python-sgp4's Julian-date epoch differed from the exact value by up to 1 microsecond in the cross-check (`docs/CROSSCHECK.md`) |
| TLE epoch against the OMM epoch of the same record | 432 microseconds | half of the TLE's 1e-8 day resolution; the provider itself rounds here |

Everything else is exact. A check that passed only because of a tolerance is reported as
`pass-tolerance`, separately from `pass` (exact), with the per-field count, mean signed
difference and maximum, so a systematic sub-tolerance bias is visible instead of hidden. The
reference adapter must be exact; the test suite enforces that.

A source file the corpus's own reader reads zero records from, where the manifest records some, fails
the case with a `source-readable` item that says what the file looked like (size, first bytes, and a guess
such as an HTML error page, an empty file, a BOM prefix or a TLE cut off after line 1), and the file's other
checks are not run; a 16-byte CelesTrak 404 body is a legitimate zero-record file and stays `empty-404`.
A stable-tier source whose bytes no longer hash to the recorded SHA-256 is reported, not silently treated
as live: the case gets a failing `stable-source-drift` item naming the recorded and actual hashes, the JSON
report gets a `drift` field, and the file's values item says the frozen expected values were not applied
and that the parser was compared against the reference reader instead.

## The seventeen cases

| case | what it covers |
|---|---|
| `epoch-year-19xx` | first ISS record (1998) in seven renderings; two-digit year 98; negative first derivative; non-zero second derivative |
| `baseline-iss-five-formats` | a current object in every rendering (live) |
| `six-digit-omm-saramago` | catalog number 100000, stable and live; TLE request 404 |
| `tle-omits-six-digit-objects` | a group that is entirely six-digit: 256 OMM records, TLE request 404 |
| `analyst-objects` | empty `OBJECT_ID`, `UNKNOWN` names, 8xxxx and 27xxxx ids, TLE keeps only the five-digit ones |
| `nine-digit-supgp-launch-nominals` | nine-digit ids (7995016xx) in CelesTrak supplemental data; perishable |
| `supgp-celestrak-classification-c` | classification `C`, element set 0, extra columns, 72000-series ids |
| `bstar-and-derivative-forms` | negative BSTAR and first derivative, non-zero second derivative, implied-decimal fields |
| `satcat-70000-cutoff` | legacy SATCAT stops at 69999; CSV/JSON SATCAT continues |
| `csv-json-omitted-mandatory-fields` | CelesTrak CSV/JSON omit the constant CCSDS-mandatory keywords |
| `mean-motion-derivative-convention` | OMM `MEAN_MOTION_DOT` equals the TLE field as printed (304/304) |
| `tle-vs-omm-precision-loss` | eccentricity truncated, mantissa rounded half up, SupGP epochs quantised; TLE→OMM→TLE round trip tested (the 24-character name limit is a format rule, not observed in provider data) |
| `omm-xml-schema` | valid NDM/XML 2.0, invalid against 3.0 on the version attribute alone |
| `alpha5-encoding-vectors` | the Space-Track table, official examples, boundaries, invalid inputs |
| `alpha5-tle-derived` | 604 derived Alpha-5 lines (letters A and T) from real CelesTrak records |
| `kvn-syntax-variants` | six CCSDS-legal KVN renderings CelesTrak never emits |
| `tle-writer-alpha5` | writer side: 606 frozen records (603 Alpha-5 ids, three five-digit) written through `write_tle`, plus three numbers the TLE field cannot carry, for which a refusal is the correct output |

Full detail, sources and per-case gaps: `MANIFEST.md`; per case: `fixtures/<case>/case.md`.

## Known gaps (summary; each is also stated in the case that has it)

- Real catalog numbers exist only for Alpha-5 letters **A** (100000-100789) and **T**
  (270000-270449, Space Fence analyst objects). Other letters are covered by vectors only.
- The renderer behind the derived Alpha-5 lines was validated (304 of 304 lines byte for byte)
  only against sub-100000 CelesTrak output, because CelesTrak emits no Alpha-5. The encoding
  step is corroborated by python-sgp4's independent implementation, by the official vectors, and
  by the maintainer's run of `tools/verify_against_spacetrack.py` against their own Space-Track
  account (44 records, zero defects, letters A and T; D-070). The derived lines remain
  CelesTrak-style renderings: Space-Track's own TLE lines for the same records differ in the sign
  written for a zero second derivative and in the last eccentricity digits, so they are not
  byte-identical to Space-Track output. The rendering rule the corpus applies (eccentricity
  truncated, BSTAR and second-derivative mantissa rounded half up) is CelesTrak's, derived
  empirically from those 304 records and documented in no specification we located.
- No positive-exponent BSTAR (>= 1.0) exists in the fetched data.
- Nine-digit ids exist only in supplemental launch nominals for roughly a week after a launch;
  outside that window the case reports `not-exercised`.
- Stability of CelesTrak's `gp-first.php` over time is assumed, not yet observed; `tools/fetch.py`
  compares every fetched file with the manifest after each run and reports `DRIFT` for stable
  sources whose bytes changed.
- The writer case's inputs are the corpus's own frozen records; no output of an external tool is
  shipped. strf's `rffit` (the writer behind satno2tle) was exercised at function level only, in a
  scratch build outside the repository, and has no adapter because it is an interactive X11 program
  (`DECISIONS.md` D-097).

## Library behaviour found while building the corpus

Documented in `docs/CROSSCHECK.md`, with draft upstream reports in `docs/upstream/`:

- python-sgp4 2.27 and Skyfield 1.55 raise `ValueError` for every nine-digit `NORAD_CAT_ID`
  loaded from OMM data.
- python-sgp4's `sgp4.omm.parse_xml` turns an empty `<OBJECT_ID/>` into `None` and
  `initialize()` raises `TypeError` on 564 of the 566 analyst XML records in the case (563 of the 565
  group records, plus the single 270449 first record).
- python-sgp4's `export_tle` writes a zero second derivative as ` 00000-0`, which matches
  Space-Track's rendering; CelesTrak writes ` 00000+0`, so byte-exact round trips of CelesTrak
  lines fail while values agree. A provider divergence, not a library defect; documented in
  `docs/upstream/`, not filed (D-072).
- python-sgp4's `omm.initialize` sets the classification and then `sgp4init` resets it to `U`,
  so CelesTrak supplemental records (`C`) come back as `U`; and its Alpha-5 decoder accepts
  `I`, `O`, lowercase and four-character input that Space-Track's definition excludes.
- As a writer, python-sgp4's `export_tle` encodes Alpha-5 correctly and `omm.initialize` refuses
  340000 and nine-digit numbers, the correct output for a TLE writer; `to_alpha5(-1)` still yields
  `-0001`, so a negative number is written rather than refused.

## Writer-side tools

The writer case (`tle-writer-alpha5`) and `check-tle` exist because every newly catalogued object
needs an Alpha-5 field and amateur tools generate TLEs for new launches. Three writers were run
(`docs/FAILURES.md`): the corpus's own renderer passes every check; a writer that formats the catalog
number as an integer fails every Alpha-5 input; python-sgp4 2.27's `export_tle` passes every real
record and refuses 340000 and nine-digit numbers, failing only the synthetic -1 vector.

strf's `rffit`, the writer behind satno2tle, could not be built here and is interactive, so it has no
adapter; its two formatting functions were exercised unmodified in an isolated build outside the
repository. Tested at function level: correct Alpha-5 across the representable range and valid lines
for real records; above 339999 no range check, so the lines carry a blank catalog field, on a route only
the interactive Satellite ID entry takes and that no real catalog number reaches today. Labels, details
and the reproduction recipe are in `docs/WRITERS.md`. No bug is claimed for the binary; a short
hardening suggestion, `docs/upstream/strf-number-to-alpha5-range-check.md`, was filed as
[cbassa/strf#88](https://github.com/cbassa/strf/issues/88) on 2026-09-23. Users of rffit or satno2tle can check the file it wrote with `python3 -m gpconf check-tle`.

## Upstream

Status of the findings above with python-sgp4, as of 2026-09-23:

- **Empty `<OBJECT_ID/>` import failure**: filed by the maintainer of this corpus as
  [brandon-rhodes/python-sgp4#171](https://github.com/brandon-rhodes/python-sgp4/issues/171)
  (draft and prepared patch in `docs/upstream/`); the patch is open as
  [PR #172](https://github.com/brandon-rhodes/python-sgp4/pull/172), opened 2026-09-21 and amended
  2026-09-23 after the maintainer's review.
- **Nine-digit `NORAD_CAT_ID` rejected**: independently reported before this corpus existed as
  [#169](https://github.com/brandon-rhodes/python-sgp4/issues/169), with
  [PR #170](https://github.com/brandon-rhodes/python-sgp4/pull/170) open. Not filed again. PR #170
  at head `5e4f308` was tested locally against the sixteen cases the corpus had at the time, on both the accelerated and the
  pure-Python build: it adds two tests and no library code change, the nine-digit reproducer still
  raises, and the runner results are identical to the 2.27 baseline (0 fixed, 0 regressions). The
  test report is in `docs/upstream/pr170-test-comment.md` (DECISIONS D-088).
- **`export_tle` zero second derivative** (` 00000-0`): not a library defect, not filed (D-072).
- **`omm.initialize` classification reset to `U`**: draft note only, not filed.

For strf, `docs/upstream/strf-number-to-alpha5-range-check.md` holds a hardening suggestion, not a
bug report, drafted 2026-09-22 (D-101) and filed as [cbassa/strf#88](https://github.com/cbassa/strf/issues/88)
on 2026-09-23 (D-108).

## Verifying the derived Alpha-5 lines against Space-Track yourself

CelesTrak emits no Alpha-5 TLEs, so the corpus's Alpha-5 lines are rendered from CelesTrak OMM
records (`derived/alpha5-tle/`). Space-Track does emit Alpha-5 for catalog numbers 100000–339999.
The corpus redistributes no Space-Track data, and its Space-Track name guard keeps any such data
out of the repository; but anyone with their own Space-Track account can check the encoding
against provider output:

```bash
python3 tools/verify_against_spacetrack.py
```

The tool asks for your Space-Track username and password interactively (never as arguments, never
logged or stored), logs in, runs exactly four queries at least three seconds apart (the current
records for 100000–100020 and 270000–270020, and the first historical record of 100000 and of
270449), logs out, saves the raw responses under `~/spacetrack-verify/` (it refuses to run if that
directory would be inside the repository), and compares each returned TLE with the derived lines. It
prints only catalog fields, verdicts, differing column numbers and summary counts, never element
values or lines. In the maintainer's run (2026-09-21, D-070) no line was byte-identical and none
was expected to be: Space-Track writes a zero second derivative as `00000-0` (column 51, and the
checksum at 69) where CelesTrak writes `00000+0`, and its eccentricity field differs in the last
one or two digits (columns 32–33) from CelesTrak's truncated rendering on exactly the 8 of 21
same-epoch records where rounding and truncation disagree (D-071); what the run verified is
that every Alpha-5 field decoded to the queried id, every line-2 field matched line 1, and
designators and inclinations agreed. Use of Space-Track is governed by its user agreement; keep the
saved responses to yourself.

## Reproducing or refreshing the corpus

The build is a pipeline of small scripts, all in `tools/`, all offline except `fetch.py`:
`fetch.py` → `inventory.py` → `validate_render.py` → `derive_alpha5.py`,
`derive_kvn_variants.py` → `make_expected.py` → `crosscheck.py` (needs the optional
`crosscheck` extra: python-sgp4, Skyfield, xmlschema) → `validate_xml.py` → `make_manifest.py`
→ `make_failures.py`. Refreshing live sources produces new snapshot values and bumps the
corpus minor version; frozen values of a released version are never rewritten.

## Versioning

`corpus_version` in `manifest.json`. Patch: documentation and tooling only. Minor: refreshed
live snapshots or added cases. Major: changed `expected.json` schema or check semantics.
Expected values published under a version are frozen; corrections arrive as new versions with a
`DECISIONS.md` entry.

## How this corpus was built

This corpus was built with AI assistance (Anthropic's Claude, operating as a coding agent)
under human direction and verification. The work ran in phases, each ending in a review by the
project owner before the next began; the agent worked under a written decision policy
(`CLAUDE.md`) that required it to record every non-trivial choice, reversal and correction.

- **Audit trail:** `DECISIONS.md` is the complete, append-only log of decisions, the owner's
  and the agent's, including the ones that were reversed. Read it first if you want to know why
  something is the way it is.
- **Sources:** `docs/RESEARCH.md` records every document consulted, with verbatim quotations,
  URLs and retrieval dates. Nothing in the corpus rests on the model's memory of the domain; the
  catalog change it documents happened after that model's training data ends.
- **Data provenance:** no element set was invented. Every value traces to a CelesTrak response
  whose URL, retrieval time and SHA-256 are recorded in the manifest, to a published standard
  cited by clause, or to a committed, labelled transformation of such a record (`derived/`,
  each with a `.provenance.json`).
- **Verification:** the expected values were produced by reference readers written from the
  format documents and cross-checked, record by record, against python-sgp4 and Skyfield
  (`docs/CROSSCHECK.md`); the renderer used for derived TLE lines was validated by reproducing
  304 of 304 CelesTrak TLE lines byte for byte. Where a specification and the provider's
  practice disagree, both are recorded (`manifest.json` → `ambiguities`) and neither is silently
  chosen.
- **Independent audit:** completed on 2026-09-21, before publication; the report is
  [`AUDIT.md`](AUDIT.md). It was performed by a separate AI session that had no access to the
  building session's context, was instructed to trust no document in the repository and to recompute
  values independently; it was not a human review. It found no wrong expected value and a number of
  documentation and tooling defects; every finding's resolution is recorded at the end of `AUDIT.md`
  and in `DECISIONS.md` (D-054 onward). The public copy of `AUDIT.md` withholds one row of its
  appendix table (a sample entry from the SupGP case, per D-033/D-049) and says so in a notice; the
  auditor's text is otherwise unchanged and the private original is intact. It covered v0.1.0; neither
  the writer-side case of v0.2.0 nor the fixes of v0.2.1 have been separately audited.

If you find an error, the most useful report names the case id, the source file's SHA-256 and
the field, so that the discrepancy can be traced to a specific fetched byte sequence.

## Licence and attribution

MIT, copyright NEOGY LLC (see `LICENSE`), for the corpus's code, documentation, vectors, derived
files and expected values. Provider data is not included; `tools/fetch.py` retrieves it under CelesTrak's own
terms. The schemas under `schemas/` are CCSDS/SANA publications redistributed unmodified.

Data source: CelesTrak (Dr. T.S. Kelso), https://celestrak.org, a 501(c)(3) non-profit that
makes this data freely available; please respect its usage policy. Standards: CCSDS 502.0-B-3
(Orbit Data Messages) and CCSDS 505.0-B-3 (XML Specification for Navigation Data Messages).
Alpha-5 definition: Space-Track, https://www.space-track.org/documentation.

To cite, use `CITATION.cff` (GitHub's "Cite this repository" reads it): *Neogy, H. (NEOGY LLC).
gp-omm-conformance, version 0.2.1, 2026-09-23, https://github.com/hneogy/gp-omm-conformance.*
Two Zenodo DOIs exist: the **concept DOI** [10.5281/zenodo.22867654](https://doi.org/10.5281/zenodo.22867654) refers to the
corpus as a whole and always resolves to the latest release; use it when you mean the corpus in
general. The **version DOI** for this release, v0.2.1, is added here and to `CITATION.cff` after Zenodo
mints it at the release; v0.2.0 keeps its own, [10.5281/zenodo.22906966](https://doi.org/10.5281/zenodo.22906966),
and v0.1.0, the release the independent audit covered, keeps [10.5281/zenodo.22867655](https://doi.org/10.5281/zenodo.22867655).
Use a version DOI when your results depend on a specific set of expected values; each release gets its
own under the same concept DOI.
