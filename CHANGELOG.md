# Changelog

Notable changes to the corpus. The version number is assigned when the owner tags a release, under
the rule in the README (patch: documentation and tooling only; minor: refreshed live snapshots, added
cases, or an additive protocol change; major: changed `expected.json` schema or check semantics).
`DECISIONS.md` holds the reasoning behind every entry, by decision number.

## [Unreleased]

The next release makes the corpus installable with pip: the runner and the corpus's own files in one package,
a `gpconf` command, presets that test a library with no adapter written, and a GitHub Action. In a clone nothing
changes: `tools/fetch.py` and `python3 -m gpconf` work as before.

### Installing and running

- `pip install gpconf` installs the runner with the corpus's own files: every case's expected values and notes,
  the derived Alpha-5 lines, the specification vectors and the manifest. Standard library only, Python 3.9 or
  later. Provider data is not in the package (D-150, D-156).
- Before any fetch, `gpconf run --preset reference` runs the four cases whose files ship in the package (the
  Alpha-5 vectors, the derived Alpha-5 lines, the KVN variants and the writer case) and reports the other thirteen
  as `not-fetched`, with the command that fetches them. `gpconf check-tle`, which checks a TLE file your own tool
  wrote, needs no corpus data at all (D-148, D-150).
- `gpconf fetch` retrieves the provider data under CelesTrak's usage policy, about 60 requests, 2 s apart, each URL
  once, into a per-user cache folder, one per corpus version: `~/.cache/gpconf/<version>` on Linux,
  `~/Library/Caches/gpconf/<version>` on macOS, `%LOCALAPPDATA%\gpconf\Cache\<version>` on Windows. `--data DIR`
  or the `GPCONF_DATA` environment variable names another folder. When a later version's folder is filled, files
  that have not changed are copied from the earlier one instead of requested again (stable-tier files whose
  SHA-256 matches); live files are always requested (D-150, D-157).

### Testing a library without writing an adapter

- `gpconf run --preset NAME`, and `gpconf presets` lists them: `reference`; `naive`, a demonstration of failure,
  not a parser to use; `sgp4` (`pip install "gpconf[sgp4]"`, tested with python-sgp4 2.27); `pyephem`
  (`pip install "gpconf[pyephem]"`, tested with PyEphem 4.2.1); and three for Node.js libraries installed in the
  folder you run from: `satellite.js` (tested with 7.1.0), and `tle.js` and `tle.js-api` (tested with 5.0.3; the
  epoch from the raw fields, or from the millisecond API). `--module PATH` points a Node preset at a checkout
  (D-151, D-154).
- The report prints the library version it found beside the version the preset was tested with. A preset whose
  library, or Node, is missing stops before any case runs, with exit status 2 and a message saying that nothing ran
  and that this says nothing about the library (D-153, D-154).
- Five libraries that cannot be presets, libsgp4, Gpredict, SatDump, astroz and gods-eye-view, have recipes in the
  repository's `harnesses/` folder: the harness, the commit it was tested at and the build commands. They are
  best-effort, tied to those projects' internals, and not in the pip package (D-152, D-155).

### In CI

- A GitHub Action: `uses: hneogy/gp-omm-conformance@<tag>` with a `preset` runs the corpus from the repository at
  that tag, after your own steps have installed your library. It runs offline and fetches nothing, so only the cases
  whose files ship with the corpus run; it fails no job on a failed case, and a preset that cannot run fails the step
  as a setup error. The job summary carries the case table, the gate line and the reminder that a count is a result
  against that version on that date. Outputs: `report`, `failed`, `exercised`. No badge. Tested on macOS, Ubuntu and
  Windows (D-153, D-158).

### In the report

- A provider file that is not on disk is reported as `not-fetched`, never as `skip`, which is kept for a parser with
  no reader for a format or no hook for a check. The count line says how many cases need fetched data, the
  `n/f` column counts the missing files per case, and the runner names the command that fetches them unless
  `--no-fetch-hint` asks it not to, as the Action does. A file that should ship with the corpus and is missing stops
  the run with exit status 2 (D-148, D-158).
- Below the case table, a gate asks whether the parser can load this month's launches: the 256 objects of
  CelesTrak's last-30-days group, captured 2026-09-21, every one above 99999. Per format, it counts records loaded
  with the right id, misidentified, or dropped, and it names the behaviour without grading the project. The JSON
  report carries the gate under `gates`, and each values item carries its record counts under `counts` (D-142,
  D-148).
- An adapter can report a record the library refused, with the library's reason, so that a refusal is counted
  apart from a silent drop; a refusal without a reason counts as a drop. The `sgp4` preset uses it (D-144).
- In the four cases that hold one, the provider's empty answer, CelesTrak's HTTP 404 body, is handed to the parser
  as a check of its own: zero records and no error is the pass (D-143).
- `satcat-70000-cutoff` is a check on the legacy SATCAT file, not on a parser, and is reported `not-exercised` for
  every parser; the `reference` preset reports 16 cases exact and 1 not exercised (D-129).
- The writer case gains a synthetic-derived input with a positive-exponent BSTAR (id 99999, TLE field
  ` 12345+1`), 610 inputs in all; no frozen expected value changed (D-125).

## [0.2.1] - 2026-09-23

A patch release under the versioning rule: fixes to the runner, the reference readers, `check-tle` and
the tooling, from the audit follow-up of 2026-09-23 (a read-only review pass under the maintainer's direction,
distinct from the independent audit of `AUDIT.md`). No frozen expected value and no
schema changed; the seventeen cases are unchanged; one check was added to the writer case
(`tle-writer-column-layout`) and one check the runner had always evaluated is now documented
(`ccsds-epoch-strings`). The corpus stops reporting pass for outcomes that were never meant to count as
one; what it reports about the naive and python-sgp4 adapters is unchanged, 14 and 7 of 17 cases
failing. The independent audit in `AUDIT.md` covered v0.1.0; neither the writer-side case of v0.2.0 nor
these fixes have been separately audited. Version DOI 10.5281/zenodo.22926017 (Zenodo record 22926017);
the concept DOI 10.5281/zenodo.22867654 resolves to the latest release.

### Fixed
- The reference renderer wrote an exact-midnight epoch as `YYDDD.-8000000`; the writer judge therefore
  failed a correct writer at any midnight epoch. Fixed with regression tests (D-111).
- `check-tle --against` passed a written record whose catalog number had no match in the source
  records, with a note; it now fails the record and names `00000` and `99999` as the likely rffit causes
  (D-112).
- A source file the reference reader read zero records from, where the manifest records some, passed every
  per-file check on zero records (an HTML error page saved by a failed fetch, a truncated TLE, an empty or
  BOM-prefixed file); it now fails the case with a `source-readable` item describing the file (D-113).
- The writer case listed the two rolling group files its derived inputs were rendered from as stable-tier
  sources, so `tools/fetch.py --check-drift` counted 24 stable sources and would have reported false drift for
  them; each source now keeps the tier its own case records, and the count is 22 (D-114).
- A stable-tier source whose bytes no longer matched the recorded SHA-256 was silently treated as live, with the
  reference reader as oracle and only a hidden info item; the case now carries a failing `stable-source-drift`
  item, the JSON report a `drift` field, and the values item says the frozen values were not applied (D-115).
- The reference readers returned wrong records silently for a BOM-prefixed CSV, KVN or 2LE file, an XML document
  with a default namespace, a repeated KVN keyword and a TLE day of year outside the year, and `from_alpha5` accepted
  fields outside Space-Track's definition; each is now a clear error (D-117).
- Three checks listed in the manifest and case documents (`leading-dot-decimals`, `bstar-implied-decimal-exponent`,
  `negative-bstar-and-ndot`) were never evaluated; they now produce items. `--vectors-cmd` reaches `parse_catalog_id`;
  a raising vector hook fails that vector rather than the case; `norm_epoch` accepts UTC offsets and a leap second;
  the JSON report names a `--write-cmd` parser; the failure catalogue withholds SupGP values for every
  value-carrying check; `ndot_field` rounds half up (D-118).
- `check-tle` dropped unpaired, indented and BOM-prefixed element lines silently and crashed on a day-of-year source
  epoch; a writer whose fields were left-justified passed every check when the length and checksum were right
  (new check `tle-writer-column-layout`); the epoch-string vectors accepted any hook that returned (they now carry
  the instants, and `ccsds-epoch-strings` is listed in the manifest); `tools/fetch.py` could re-request a file whose
  metadata was missing, request a re-capture endpoint twice in a fresh checkout and judged the two-hour rule by
  mtime; negative tests added (D-119).

## [0.2.0] - 2026-09-22

A minor release under the versioning rule: one case added. The sixteen cases of v0.1.0 and their
expected values are unchanged. The independent audit in `AUDIT.md` covered v0.1.0; the writer-side
case has not been separately audited. Version DOI 10.5281/zenodo.22906966 (Zenodo record 22906966);
the concept DOI 10.5281/zenodo.22867654 resolves to the latest release.

### Added

- Case `tle-writer-alpha5`, the first writer-side case (kind `writer`): 606 records already frozen in
  the corpus, written through the adapter's `write_tle` hook and checked for the Alpha-5 catalog field
  on both lines, 69-character lines with valid checksums, and a round trip through the reference reader
  at the TLE field's resolution (truncation or rounding half up accepted, the convention observed
  reported). Three owner-approved synthetic-derived inputs (340000, 799501621, -1: real elements, vector
  ids) for which a refusal is the correct output. Secondary fields and provider-rendering matches are
  reported for information only. (D-095, D-096)
- Adapter hook `write_tle(record)` and the external `--write-cmd` counterpart. `write_tle` on the
  reference, naive and python-sgp4 adapters. (D-095)
- `python -m gpconf check-tle FILE... [--against RECORDS] [--json OUT]`: the same checks applied to a
  TLE file written by a tool that cannot be wrapped by an adapter, such as strf's interactive `rffit`.
  (D-099)
- `docs/WRITERS.md`: the writer protocol, the precision rule, the three writers' results, and the
  function-level observation of strf's `rffit` with tested and inferred claims labelled and the
  reproduction recipe. `docs/upstream/strf-number-to-alpha5-range-check.md`: a hardening suggestion,
  drafted and not sent. (D-097, D-100, D-101) [Filed after the release as cbassa/strf#88 on 2026-09-23; D-108.]
- `tools/make_expected.py` accepts case ids, so a new case can be built without rewriting the frozen
  files of the others. (D-095)
- This changelog. (D-100)

### Changed

- README: writer-side paragraph, `write_tle` and `--write-cmd` in "Writing an adapter", breakage item
  10 (the catalog number through an integer format), the case table (seventeen cases), the `check-tle`
  recipe. `docs/FAILURES.md` lists, for the writer case, the checks each adapter passed with record
  counts, so a failure confined to the synthetic refusal inputs cannot read as a general one. (D-098)
- CI runs the writer case offline alongside the other shipped cases.

## [0.1.0] - 2026-09-21

- Initial release: sixteen cases, frozen expected values, specification vectors, derived Alpha-5 lines,
  the runner, the fetch script and the independent audit. Concept DOI 10.5281/zenodo.22867654, version
  DOI 10.5281/zenodo.22867655.
