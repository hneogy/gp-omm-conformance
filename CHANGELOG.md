# Changelog

Notable changes to the corpus. The version number is assigned when the owner tags a release, under
the rule in the README (patch: documentation and tooling only; minor: refreshed live snapshots or
added cases; major: changed `expected.json` schema or check semantics). `DECISIONS.md` holds the
reasoning behind every entry, by decision number.

## [Unreleased]

- Runner: three Node presets, `satellite.js` (tested with 7.1.0), `tle.js` and `tle.js-api` (tested with 5.0.3; the epoch from the raw fields and from the millisecond API), run from the working directory so that the library resolves as it would in the user's project, with `--module PATH` for a checkout. A preflight refuses a missing Node or library before any case runs; every library preset's refusal now says that nothing ran and that this says nothing about the library (exit 2). The command parser also takes an argument list, a working directory and an environment. No published result changed (D-153, D-154).

- Runner: `--preset NAME` runs a shipped adapter with no adapter written, and `gpconf presets` lists them: `reference` and `naive` (standard library only; naive is a demonstration of failure, not a parser to use), `sgp4` (python-sgp4, tested with 2.27) and `pyephem` (PyEphem, tested with 4.2.1). A library preset's report names the version it found beside the version it was tested with; a missing library is refused with the command that installs it. The three built-in adapters moved to `gpconf/adapters/`, where the old `tests.adapters` names still reach them, and the PyEphem adapter joined from the corpus's hand run. No result changed (D-151).

- Runner: works outside a clone. The corpus's shipped files and the fetched provider files have separate roots: a clone uses itself for both, as before; a copy elsewhere reads its corpus from the package (`gpconf/corpus/`) and keeps provider files in a per-user cache folder, one per corpus version, unless `--data DIR` or the `GPCONF_DATA` environment variable names another. The fetch script is the `gpconf fetch` subcommand (`tools/fetch.py` runs the same code in a clone), `check-tle` needs no corpus, and the fetch command a run prints names the subcommand where no clone script exists. The runner's line about re-capture files is corrected: a normal fetch never requests them. No result changed (D-150).

- Runner: a provider file that is not on disk reports `not-fetched`, never `skip`, which is kept for a parser with no reader for a format or no hook for a check. The count line says how many cases need fetched data, a new `n/f` column counts missing files, a case that ran on part of its files is named below the count line, and the fetch command names a script that exists under the corpus root. A missing file that ships with the corpus stops the run with exit status 2. The gate no longer claims "every format it reads" or calls a parser TLE-only when a format was never tried, takes its snapshot date from the frozen capture, and judges a freshly fetched CSV against its own record count. No published count changed (D-148).

- Adapter protocol: a refusal channel. An entry carrying `_refused` with a non-empty reason (and optionally `_field`, `_input`) reports a record the library refused; `{"_adapter": {"refusals": true}}` declares that every error-drop is reported. The runner credits refusals to expected ids, keeps them apart from silent drops in the values detail, the JSON counts and the gate, and fails a refusal without a reason. The built-in python-sgp4 adapter uses it (D-144).

- Runner: the provider's recorded empty answer (HTTP 404 body) is handed to the parser under test as its own check, `empty-answer-yields-no-records`, in the four cases that hold one; zero records and no error is the pass (D-143).

- Runner: a gate over this month's launches, printed below the case table and written to the JSON report under `gates`; values items carry structured record counts (`counts`). Wording names the behaviour, never grades the project (D-142).

### Added
- One synthetic-derived writer input with a positive-exponent BSTAR (five-digit vector id 99999, BSTAR 1.2345, TLE
  field ` 12345+1`), rendered by the corpus under the D-096 precedent, closing the writer side of a declared coverage gap
  (D-125). The writer case now has 610 inputs; no frozen expected value changed.

### Changed
- `satcat-70000-cutoff` reports `not-exercised` for every parser where it reported `pass`: its only pass/fail item
  is a check the runner makes on the legacy SATCAT file, no adapter reads SATCAT, and a per-library table could read
  the pass as a library result (D-129). The reference adapter now reports 16 cases exact and 1 not exercised; the
  naive and python-sgp4 failing counts are unchanged at 14 and 7 of 17. A legacy file with an id at or above 70000
  still fails the item, as a data property.

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
