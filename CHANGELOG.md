# Changelog

Notable changes to the corpus. The version number is assigned when the owner tags a release, under
the rule in the README (patch: documentation and tooling only; minor: refreshed live snapshots, added
cases, or an additive protocol change; major: changed `expected.json` schema or check semantics).
`DECISIONS.md` holds the reasoning behind every entry, by decision number.

## [0.7.0] - 2026-10-15

Changed: the licence. From 0.7.0 gpconf is published under Apache-2.0, with a `NOTICE` file that travels with copies
and asks for credit when the corpus or its verdicts are used. Releases up to 0.6.2 were published under the MIT licence
and stay under it; nothing already released changes. Source files carry an SPDX line and the copyright line, the README
gains a "Cite as" section, and gpconf is named as a name of NEOGY LLC (D-310).

A minor release under the versioning rule: the grading behaviour that `docs/ADAPTERS.md` documents changes, and the
counts vocabulary gains `duplicate_copies` while `extra` widens (D-291). The grader was audited by trying to get
wrong parsers past it. SM-26 answered the audit ask of issue #1 with seven wrong-on-purpose adapters, each the
reference parser with one bug, that passed 0.6.1 with no failing case; the corpus's own sweep found four more
routes; a fresh-session red team, run blind against 0.6.2 from PyPI, wrote fourteen escapes, seven by routes
already closed, five new, two it judged to be by design; and a mutation fuzzer, 20,000 one-bug parsers at a fixed
seed, found one more. Everything that got through is closed. The
eighteen cases are those of 0.6.2. **No published case verdict changes**: the three built-in adapters and the
thirteen library runs behind the site's rows, re-run under this runner, keep every case status and every gate
line (the reference passes 17 exact with the SATCAT data check not exercised, naive fails 15, python-sgp4 fails 8;
from a fresh fetch 16, 14 and 6, as before). What changes below case level, and why: failing items rise inside
cases that already failed, because the integer check now runs on every record-bearing case and the derived case
reads 146 more sets (python-sgp4's item total moves from 24 to 26, naive's from 79 to 81); a parser's fields that
it never returns show as not-exercised gaps where they showed nothing; and a file's own checksum check counts as
information, not as a parser pass, so the exact-pass counts of the TLE cases fall by the number of TLE files. The
independent audit in `AUDIT.md` covered v0.1.0; neither the writer-side case of v0.2.0, the fixes of v0.2.1, the
packaging and protocol changes of v0.3.0, the corrupt-input case of v0.4.0, the changes of v0.5.0, those of
v0.5.1, those of v0.6.0, those of v0.6.1, those of v0.6.2 nor those of this release have been separately audited:
the two readings of this release audited the grader, not the answer key. The version DOI is added once Zenodo has
archived the release; the concept DOI 10.5281/zenodo.22867654 resolves to the latest release.

Changed, the grader's rule (D-280): an outcome that is not a graded pass or fail (a skip, an `Unsupported`, a
refusal, extra or duplicate records) is all-or-none for its scope or graded and counted; there are no partial
skips. A format is unsupported for all of a run's inputs or none, the corrupt-input case's comparison files and
the recorded empty answer included; `write_tle` is unsupported for all of its records or none, and what it wrote
stays graded.

Changed: every copy of a returned record is compared, and a surplus copy counts in `extra` and in the new
`duplicate_copies`; a copy that disagrees fails its record, which keeps one outcome (D-281, inside D-194), and so does
a record returned more often than the input holds it, as said above (D-311). In the corrupt-input case a refusal credits the corrupt record only on evidence, a `_field` that decodes to
it or an `_input` quoting what the edit introduced, as `docs/ADAPTERS.md` always said (D-282).

Changed: the catalog number and the counters must be integers in every record-bearing case, and the decode and
pivot hooks are type-checked like `parse_catalog_id`; an integer is any integer type, an `int` subclass or a
library's own (numpy's among them), never a bool, a float or a string, where the check used to compare the type's
name and failed a correct parser (D-283, D-295, D-296).

Changed: a field with expected values that a parser never returns shows in the case result as a visible gap
(`fields-not-returned`, not-exercised); returned for some records and omitted for others, it fails (D-284). Where a
format carries no value for the constant metadata, `None` or the OMM defaults pass and anything else fails (D-285).

Fixed: a parser that called `sys.exit()` ended the run with exit status 0 and no report; the run now continues,
the case fails with a `parser-exit` item, the report is written and the status is 1; an adapter that exits while
loading is a setup error, status 2 (D-293). A case whose own checks were all voided by the parser, which does not
return the record from the unedited file either, read `pass`; it reads `not-exercised`, and every not-exercised
item says whether the parser or the data caused it (`cause`; D-294).

Fixed, false failures of correct parsers: a record carrying an `_adapter` key beside its fields was dropped without
a word, and is kept (D-295). Fixed, reporting: the catalog-field item no longer calls a refused record a wrong
decode, and the gate's headline says when more records came back than the file holds (D-298). A TLE file's own
checksum check is information, since no parser takes part in it (D-297, applying D-129).

Fixed, from a hardening review before the release (mutation testing of the grading code, property-based tests, type
and coverage checks): a TLE-and-OMM set with its TLE file not on disk failed its count checks for every parser, the
reference adapter included, "TLE has 0 records"; released versions do the same on a data folder a fetch left half
done. The comparison is now not made, and says which file is missing; and a parser with no TLE reader skips it
where it failed (D-318). Changed: an element value returned as text must be a plain decimal number in ASCII digits
with nothing around it, and an epoch string is held to ASCII digits; padding, an underscore between digits and the
digits of another script were read as the number they spell, and three wrong parsers passed on that. Such text is
now a value the runner cannot read, and the file fails as `parse`; no published run returns any (D-319). Added:
`tests/test_properties.py`, eighteen properties run with Hypothesis, a test-only dependency (the `test` extra), which
CI requires: where the tests are meant to run, a missing Hypothesis fails the job, it does not skip (D-322); `tests/test_item_statuses.py`,
which pins every item status of the naive adapter and python-sgp4 2.27 on the full data, 254 and 389 items, as a
release-time test; and in CI, mypy at its default settings, the properties and a 500-mutant fuzzer smoke on every
push, with the 5,000-mutant run, coverage against a floor and the stricter type check in a nightly workflow that also
runs on every tag (D-320).

Fixed: a correct parser returning its elements as `numpy.float64` failed every file. `numpy.float64` is a float, and
under numpy 2 its `repr` is `np.float64(1.5)`, which the runner handed to `Decimal()`; released versions do the same.
The value is read now, not what it prints as (D-321).

Changed, after a second blind audit, of this release's candidate (a fresh session given its wheel and sdist alone,
2026-10-10), which found seven wrong parsers that end with no failing case and no compared value that escapes: each
avoided comparison through a documented outcome. One is closed: a record fails when the parser returns more copies of
its id than the input holds, exact copies included (D-311, reversing the second half of D-281; `extra` and
`duplicate_copies` count as before; no published run returned a surplus copy). The other six stand by design (D-313),
and the run now says what they leave out (D-312): a case's status cell reads `pass (1 item skipped)` or
`pass (5 field gaps)` where an item skipped or a field with expected values was never returned; a sentence under the
count line totals them; a run without provider data says `5 of 18 cases graded offline; not a full conformance
result.`; and the JSON report gains `inside_cases`, and `annotations` on a result. No status, count or exit code
changes. The adapter guide's three sentences on `Unsupported` say what the runner checks, all-or-none within a run,
and no longer that a skip proves a reader absent. The audit's nineteen adapters are in `tests/adversarial/redteam2/`,
credited.

Changed: an epoch is the parser's to parse. `parse_epoch` returns a `datetime`, and a string fails the item; a
record whose epoch is the input's own text handed back unparsed, where that text is not already the calendar form,
fails its values. Text a parser built itself is read as before. The reference adapter parses the day-of-year
epoch of a KVN file itself, where it used to pass the file's text on (D-306).

Added: 146 synthetic-derived TLE sets in the derived case, real elements with the catalog number or the epoch's
year replaced: the lowest and highest id of each of the 24 Alpha-5 letters, less the two ids real records hold,
and one set for every two-digit epoch year; each id is a specification vector, not a catalogued object, and D-016
stands (D-286, D-300). The writer case, which takes its inputs from the derived case, writes them too. Added: OMM
values graded with no fetch: the corrupt-input case's unedited CSV and JSON files are held to the frozen values,
and one derived XML file, the ISS first record re-serialised, is graded there for its values (D-299).

Changed: four checks that a case listed and the runner never evaluated are no longer listed there, and the integer
check is evaluated wherever it is listed; a test holds every case to that (D-301). `docs/ADAPTERS.md` ships in the
sdist and the wheel, at `gpconf/corpus/docs/ADAPTERS.md` (D-302).

Added: `tests/adversarial/`, the wrong-on-purpose adapters with their authors credited (SM-26, issue #1; the
fresh-session red team of 2026-10-09; the corpus's own sweep), every one behaving as designed; and
`tools/mutant_fuzz.py`, which builds one-bug parsers from the reference by seeded mutation and fails CI on any that
survives outside a reviewed allowlist: 500 mutants on every push, 5,000 every night and on every tag (D-287, D-320).

Changed: the exact fetch size the README gives is the 0.6.2 release's measurement, 3,191,362 bytes (the owner's timed
first-time fetch on release day: 46 requests, each answered 200, in 2 min 2.4 s), where it gave the 0.6.1 release's
3,201,056; the rounded 3.2 MB is the same (D-277). The phrase "CelesTrak-style rendering" is gone: the derived lines
are described as rendered with CelesTrak's eccentricity truncation, after Dr. Kelso's reply (D-274, D-277). The
documentation inside each `expected.json` is regenerated to match `tools/cases.py`; no record, value or source hash
of a real record changed (D-278).

## [0.6.2] - 2026-10-09

Fixed: an unknown `--case` ended as a silent no-op, exit 0, so a typo in a pipeline could stay green forever; it is
now an error, exit 2, naming the corpus's cases. `gpconf check-tle` on a missing file printed a traceback; it prints
a one-line error and exits 2. Both were findings of the audit of 2026-10-08 (D-268, D-269).

Changed: every text `open()` in the package, the tools and the tests passes `encoding="utf-8"`, so Windows's legacy
default encoding cannot corrupt a read or a write; the `sgp4` extra pins `sgp4>=2.27` — python-sgp4 dropped Python
3.9 at 2.26, and on 3.9 the extra now refuses to install instead of resolving to 2.25, an older library than every
published python-sgp4 result names (D-269).

Changed: CI declares `permissions: contents: read`, pins `actions/checkout` and `actions/setup-python` by commit
id, and adds a Windows job (Python 3.12) (D-269).

Fixed: the Windows job's first run — the first time the suite ran on Windows — failed 42 of 445 tests, every one a
portability assumption and none a wrong expected value. Three causes: git converted line endings at checkout, which
a byte-exact corpus cannot allow (a `.gitattributes` now marks every file `-text`); command lines built for the
platform shell were quoted with POSIX rules (`shlex.quote`), which `cmd.exe` rejects (the fetch hint and the tests
now quote per platform); and the fetch hint named `python3`, a name Windows installs do not have (it now says
`python` there). The cache-folder answer for a faked `win32` also uses Windows separators on every host (D-270).

Changed: the exact size the README gives for a user's fetch is the latest measurement, 3,201,056 bytes, from the
timed first-time fetch at the 0.6.1 release (2026-10-04: 46 requests, each answered 200, in 2 min 11 s), where it gave
the 0.6.0 release's 3,200,451. The rounded figure, 3.2 MB, is the same (D-258).

Checked: package builds are identical across machines as far as tried. D-203 left it untested whether a build on
another machine matches the release files. For v0.6.1 a build on Linux x86_64 (CPython 3.14.6 built with GCC 13.3, zlib
1.3), from the tag with the recorded epoch and the pinned toolchain, gave the wheel and the sdist that PyPI serves,
byte for byte; they were built on macOS arm64 (Clang, zlib 1.2.12). The README says so and says what remains
untested: another Python version, another implementation of deflate, and the files of 0.5.0 to 0.6.0 (D-259).

Added to `docs/RESEARCH.md`: a last section, CelesTrak's GP formats page as read again on 2026-10-05. The CSV default
and the sentence on TLE formats and catalog numbers above 99999 stand as quoted; the site-wide notice quoted in section 1
has since been reworded (D-260).

Changed: the eight libraries' runs of September 2026 are called one-off runs in the README and in `harnesses/README.md`,
where they were called "hand-run" and "by hand"; they were made in sessions with AI tools, as "How this corpus was
built" says. The four adapters' comments in the package say it too with this release's build (D-262).

The independent audit in `AUDIT.md` covered v0.1.0; neither the writer-side case of v0.2.0, the fixes of v0.2.1, the
packaging and protocol changes of v0.3.0, the corrupt-input case of v0.4.0, the changes of v0.5.0, those of v0.5.1,
those of v0.6.0, those of v0.6.1 nor those of this release have been separately audited; the audit of 2026-10-08
(D-268) was the maintainer's own tooling, not a separate audit. Version DOI 10.5281/zenodo.23265462 (Zenodo record
23265462); the concept DOI 10.5281/zenodo.22867654 resolves to the latest release.

## [0.6.1] - 2026-10-04

A patch release under the versioning rule, tooling and documentation only: the fetch's `User-Agent` names the kit,
the version that asks and the repository (D-252); the README gives the size of a user's fetch as it was measured
(D-252); and `docs/RESEARCH.md` gains one quotation from CelesTrak's usage policy (D-253, D-254). The fetch list is
0.6.0's: 46 requests, and four answers written from the corpus's record and never requested. No case, check or frozen
expected value changed, the eighteen cases are those of 0.6.0, and the adapter protocol is as in 0.5.1. On the
maintainer's copy the reference adapter passes all eighteen cases (seventeen exact, the SATCAT data check not
exercised), the naive adapter fails 15 and python-sgp4 2.27 fails 8, as in 0.6.0; from a fresh fetch they read 16,
14 and 6, since one case cannot run without launch-window files that a new user's fetch cannot obtain (D-229). The
eight libraries run by hand and Vallado's C++ were run again under this release's tree, on the maintainer's copy and
in the environments of their latest runs, and each report compared with the latest one kept, by case status and by
count: none differs, in status, in count or in the text of any item (D-255). The independent audit in `AUDIT.md`
covered v0.1.0; neither the writer-side case of v0.2.0, the fixes of v0.2.1, the packaging and protocol changes of
v0.3.0, the corrupt-input case of v0.4.0, the changes of v0.5.0, those of v0.5.1, those of v0.6.0 nor those of this
release have been separately audited. Version DOI 10.5281/zenodo.23144821 (Zenodo record 23144821); the concept DOI
10.5281/zenodo.22867654 resolves to the latest release.

Changed: the fetch's `User-Agent` names the kit, the version that asks and the repository:
`gpconf/<version> (+https://github.com/hneogy/gp-omm-conformance; fetch, each URL once)`. Up to 0.6.0 it read
`gp-omm-conformance-corpus/0.1 (fixture fetch, each URL once; see repository README)`, which named neither gpconf nor
the corpus's version and gave no address, so CelesTrak's operator could not tell from a log what was asking.
`GPCONF_CONTACT` still appends a contact and `GPCONF_USER_AGENT` still replaces the string; without them the header
says nothing about the person running the fetch (D-007, D-252).

Corrected: the README gave the size of a user's fetch as 3.1 MB in three places. That was the figure computed from
the corpus's own captures; the two timed first-time fetches, at the releases of 0.5.1 and 0.6.0, each downloaded 3.2
MB, and the README now says 3.2 MB, with the measurement and the captures' sum beside it (D-252). The sections below
keep the figure they were published with.

Added to `docs/RESEARCH.md`, section 3: the usage policy's paragraph on addresses that many users share, quoted as
the project owner read it on the page on 2026-10-04 (D-253, D-254).

## [0.6.0] - 2026-10-04

A minor release under the versioning rule: an additive change to the JSON report, `summary`, the number of cases in
each status, which a script is now told to rely on in place of the printed lines (D-240). With it, every count the
runner, the fetch and the Action print agrees in number with the words beside it (D-239), and the project names itself
gpconf (D-241, D-242). A user's fetch drops from 50 requests to 46 and no longer asks for anything it knows will
answer 404: CelesTrak's 16-byte answer `No GP data found` ships with the corpus as a recorded response, the one
provider response it carries and a named exception to its rule of shipping no raw provider bytes (D-247). The words
"TLE set" and "line" are used strictly (D-248). No case and no frozen expected value changed, the eighteen cases are
those of 0.5.1, and the adapter protocol is as in 0.5.1. On the maintainer's copy the reference adapter passes all
eighteen cases (seventeen exact, the SATCAT data check not exercised), the naive adapter fails 15 and python-sgp4 2.27
fails 8, as in 0.5.1; from a fresh fetch they read 16, 14 and 6, since one case cannot run without launch-window files
that a new user's fetch cannot obtain (D-229). The eight libraries run by hand and Vallado's C++ were run again under
this release's tree, on the maintainer's copy and in the environments of their latest runs, and each report compared
with the latest one kept, by case status and by count: none differs, and the item texts that differ do so in the
number agreement of D-239 and, for one item, in the provider's text it quotes (D-245, D-249). The independent audit in
`AUDIT.md` covered v0.1.0; neither the writer-side case of v0.2.0, the fixes of v0.2.1, the packaging and protocol
changes of v0.3.0, the corrupt-input case of v0.4.0, the changes of v0.5.0, those of v0.5.1 nor those of this release
have been separately audited. Version DOI 10.5281/zenodo.23140585 (Zenodo record 23140585); the concept DOI
10.5281/zenodo.22867654 resolves to the latest release.

Changed: a fetch requests no answer it knows to be an error (D-247). Four entries of the fetch list are TLE requests
for objects numbered above 99999; CelesTrak answers each with HTTP 404 and the 16-byte text `No GP data found`, and up
to 0.5.1 the fetch made them and let them pass as its one exception to "stop on any response that is not a 200". They
are no longer made, under any flag. The answer ships with the corpus, `recorded/celestrak-no-gp-data-found.txt`, with
a provenance file giving the URL, time, status and SHA-256 of the five captures of 2026-09-21 and of the four answers
the maintainer's fetch received on 2026-10-04, and the fetch writes it to the four paths with metadata saying that it
was written from that record and not requested. A user's first fetch is 46 requests and 3.1 MB, every one expected to
answer 200, and any other answer stops the run; a later version on a machine that has a cache requests the 26 live
files, copies 20 stable ones and writes these four. This is the one provider response the corpus ships and a named
exception to D-023, which ships no raw CelesTrak bytes: the body holds no orbital data, and the README, `NOTICE`,
`MANIFEST.md`, `CITATION.cff` and the manifest's `design` block say so where they said that nothing raw is shipped. A
run on fetched data keeps every status and count: the parser is still handed the empty answer, and the items that rest
on the four files say that the answer is the corpus's record, captured on its date, and was not requested. What a
user's run no longer does is observe CelesTrak giving that answer. Where the record could be wrong about the day, a
fetched group that holds an id below 100000, the two checks that compare the TLE answer with the OMM set report
`not-exercised` instead of comparing. Runs with no fetched data do not change.

Fixed: the item that compares a TLE answer with its OMM set quoted `No GP data found` for a file whose body is `No
SupGP data found`, the SupGP launch-window capture; it now quotes the text the file holds (D-247).

Changed: "TLE set" and "line" are used strictly (D-248). A TLE set is one object's lines, line 1 and line 2 with the
name line where the format has one; a line is one line. Both figures the corpus quotes most are counts of sets: the
604 derived Alpha-5 TLE sets it ships, 1,208 element lines in four files, and the 304 fetched TLE sets, each with its
OMM record, from which the rendering rules were derived and of which the renderer reproduces the name line, line 1 and
line 2 byte for byte. The README, the case documents, `MANIFEST.md` and the writer guide said "lines" of both in
places. The frozen `expected.json` files keep the prose they were generated with; the runner reads none of it. A test
counts the derived files and fails on either figure said of lines.

Changed: the project calls itself gpconf, everywhere a person reads its name (D-241, D-242). `docs/BRAND.md` is the
single source for the name, what it means and the lines the project describes itself with; the repository stays
`gp-omm-conformance`, and "the GP/OMM conformance corpus" is the descriptive subtitle. The README opens with the
headline, one sentence, the install block and a table of the fixes merged or acted on upstream; what it opened with,
and the status paragraph, follow unchanged. The package's summary is the About line, and it declares keywords and
classifiers; `gpconf --help` says what the kit is. The GitHub Action is named gpconf and its job summary is headed
"gpconf: preset …"; `uses: hneogy/gp-omm-conformance@<tag>` does not change. `CITATION.cff`'s title is "gpconf: a
conformance corpus for orbital-data parsers crossing the five-digit catalog-number boundary", and its abstract says
that the audit of v0.1.0 was made by a separate AI session; the Zenodo records of earlier releases keep their titles.
No case, check, expected value or printed result changes.

Changed: every count the runner, the fetch and the Action print agrees in number with the words beside it (D-239). The
Action's summary said "1 need launch-window data", and the count line could say "1 need fetched data" under a heading
of "1 case(s)". One case now passes, fails, skips or needs fetched data where two pass, fail, skip or need it, and no
line hedges a plural with a bracketed s: "18 cases", "46 requests made", "0 of 1 record", "1 record matches" beside
"256 records match". Only wording changes: no status, count or check moves, and a line whose counts are all other than
one differs from 0.5.1's by the bracketed s alone. `docs/FAILURES.md` is regenerated with the same rows.

Added: the JSON report carries the case totals as numbers, in a `summary` object at its top level: `cases` and one
count for each status, zeros included (D-240). A script should read the JSON report or the exit status, never the
printed lines, whose wording can change from one version to the next, as it does in this one; the README and the
adapter guide now say so. The change is additive: every field the report had is where it was.

Changed: the table of `docs/FAILURES.md` gives a case's failing items as "(1 failing)" where it said "(1 fail)", a word
that does not vary with the count (D-240). The numbers are the same.

## [0.5.1] - 2026-10-03

A patch release under the versioning rule: tooling and documentation only. The fetch stops depending on data that
CelesTrak serves only around a launch, stops at any response it does not expect, and downloads a quarter of what it
did: 50 requests and 3.1 MB for a user's run, where 0.5.0 made 61 requests for 12.5 MB (D-228, D-229, D-231). The
runner has one new status, `not-available`, for a file that no fetch requests (D-229). No case, check or frozen
expected value changed, and the adapter protocol is as in 0.5.0. On the maintainer's copy the reference adapter passes
all eighteen cases (seventeen exact, the SATCAT data check not exercised), the naive adapter fails 15 and python-sgp4
2.27 fails 8, as in 0.5.0; from a fresh fetch they read 16, 14 and 6, since one case cannot run without launch-window
files that a new user's fetch cannot obtain (D-229). The independent audit in `AUDIT.md` covered v0.1.0; neither the
writer-side case of v0.2.0, the fixes of v0.2.1, the packaging and protocol changes of v0.3.0, the corrupt-input case
of v0.4.0, the changes of v0.5.0 nor those of this release have been separately audited. Version DOI
10.5281/zenodo.23130868 (Zenodo record 23130868); the concept DOI 10.5281/zenodo.22867654 resolves to the latest
release.

Changed: `gpconf fetch` stops at the first response its list does not expect (D-228). The `allow_error` flag, which let
any HTTP error pass on the entries that carried it, a 403 included, is replaced by `expect_status: 404` on the entries
recorded as answering 404; a run goes on past a non-200 only when it is that 404 with CelesTrak's no-data text. Any
other response ends the run with exit status 2, is kept beside the data as `<file>.unexpected` and is never read as
provider data; the URL is not asked again short of `--force` two hours later; after an HTTP 403 or 429 no request is
made for two hours. The runner reports such a file as `not-fetched`, and no longer reads an error page that an earlier
fetch saved in the data's place, which used to count as a failed case for the parser under test.

Changed: the fetch no longer requests ten launch-window files, and the runner says `not-available` for them (D-229).
The Starlink G15-27 post-deployment file and the launch nominal 799501621, five formats each, are served by CelesTrak
only for the days after a launch, so a fetch that asked for them would stop for every user once the window closed. They
stay in the fetch list as the record of the corpus's own captures, marked `launch_window`; a user's run is 51 requests
and 12.5 MB. One case, `supgp-celestrak-classification-c`, cannot run from a fetch and reports `not-available`; three
others are judged on their remaining files. The table has an `n/a` column and the count line says how many cases are
not available. The counts published so far were measured with those files, which a new user's fetch cannot obtain: a
fresh fetch reproduces 16 passing cases for the reference adapter, 14 failing for the naive adapter and 6 for
python-sgp4 2.27, where 17, 15 and 8 are published.

Changed: the README's "Fetching responsibly" and the text `gpconf fetch --help` prints say what CelesTrak asks of
software that downloads from it and what the fetch does about each, and then what is the corpus's own choice (D-230).
The two-second pause between requests is the corpus's choice: CelesTrak publishes no interval, and the section used to
list the pause under following its policy. The quick-start comments give a user's run as the fetch list has it. The
advice to skip the legacy SATCAT with `--skip-case satcat-70000-cutoff` is withdrawn, since it also left out two
first-record files that other cases read. The CSV default is said of GP and SupGP queries, whose default it is.

Changed: the fetch leaves out the legacy SATCAT file unless it is asked for with `--include-satcat` (D-231). The file is
9.4 MB, three quarters of what a fetch downloaded, and one case reads it, a data check in which no parser takes part. A
user's run is now 50 requests and 3.1 MB. Without the file `satcat-70000-cutoff` reports `not-exercised`, as it does with
it, and a line under the count says that the check was not made, that nothing about the parser under test depends on
it, and that `--include-satcat` runs it (D-232).

## [0.5.0] - 2026-10-01

A minor release under the versioning rule: an additive protocol change, the "unsupported" answer for vector hooks
(D-205, D-206); the gate's record counts to one outcome per record (D-207, under D-194); and reproducible package
builds (D-203). No frozen expected value changed and the eighteen cases are those of 0.4.0. The reference adapter
passes all eighteen cases (seventeen exact, the SATCAT data check not exercised); the naive adapter fails 15 of them
and python-sgp4 2.27 fails 8, as in 0.4.0. The independent audit in `AUDIT.md` covered v0.1.0; neither the
writer-side case of v0.2.0, the fixes of v0.2.1, the packaging and protocol changes of v0.3.0, the corrupt-input case
of v0.4.0 nor the changes of this release have been separately audited. Version DOI 10.5281/zenodo.23093982 (Zenodo
record 23093982); the concept DOI 10.5281/zenodo.22867654 resolves to the latest release.

Added `docs/LETTER-IN-FIELD.md`, on the corrupt-input case's input 3, the letter O in place of a 0 in line 1's epoch
field: four TLE readers read the field up to the letter with no error, reported to PyEphem, satellite.js, Gpredict
and tle.js; libsgp4 v3.0 and astroz v0.14.0 refuse the line; with the fix in each language (D-193). Documentation
only.

Fixed: the `satellite.js` preset emits an epoch it cannot form as `null` and notes it on stderr, where a NaN day
(a field that is not wholly numeric, from satellite.js's #197 on) became a string the runner reported as its own
internal error (D-199). The README names Vallado's C++ as part of the stack, python-sgp4's accelerated `Satrec`
run against every case (D-197, promised on PyEphem #297), and states the Alpha-5 rule as the vectors do (D-196).

Added: reproducible package builds. `tools/stage_package.py` needs the build time as `SOURCE_DATE_EPOCH`, stamps the
staged tree with it, passes it to the build and repacks the wheel and the sdist so that two builds of the same export
with the same epoch are byte-identical whatever the umask or the moment; from this release the files on PyPI can be
rebuilt from the tag and matched by SHA-256 with the toolchain the release notes name (D-203).

Added: a vectors command may answer `{"unsupported": "<reason>"}` and a Python hook may raise
`gpconf.runner.Unsupported` for an operation the library does not have; the hook's item then skips with the reason
instead of failing its valid vectors, for all of the hook's vectors or none; a non-zero exit stays a rejection, exit 3
included (D-205). The shipped tle.js, libsgp4 and astroz vector harnesses give the answer, so their `alpha5-encode`
items, and tle.js's `ccsds-epoch-strings` and `catalog-number-is-integer`, skip instead of failing; no case count
moves (D-206).

Changed: the record counts behind the gate follow one outcome per expected record. `dropped` is now the expected
records with no record returned at all and no refusal, so a record returned under a wrong catalog number is counted
once, as misidentified, where it was also counted as a dropped expected one before; the count `dropped` carried
before stays in the report as `ids_not_returned`, and misidentified records beyond the records left are counted as
`extra`. For a parser that returns 0 for every Alpha-5 field, the headline reads "256 misidentified" where it read
"256 misidentified, 256 dropped silently" (D-207, under D-194).

## [0.4.0] - 2026-09-27

A minor release under the versioning rule: one case added, the eighteenth, `corrupt-input`, the first case to hand a
parser corrupt input (D-171). No frozen expected value changed and the adapter protocol is as in 0.3.0. The reference
adapter passes all eighteen cases (seventeen exact, the SATCAT data check not exercised); the naive adapter fails 15
of them and python-sgp4 2.27 fails 8 (D-173). The independent audit in `AUDIT.md` covered v0.1.0; neither the
writer-side case of v0.2.0, the fixes of v0.2.1, the packaging and protocol changes of v0.3.0 nor the changes of this
release have been separately audited. Version DOI 10.5281/zenodo.23002261 (Zenodo record 23002261); the concept DOI
10.5281/zenodo.22867654 resolves to the latest release.

### Added

- `corrupt-input`: six files, each carrying one corrupt input between valid records: a wrong checksum digit on
  line 1, line 2 one character short (a digit lost mid-line, so every column after it moves), the letter O for a 0
  in the epoch field, a set with no line 2, a CSV that ends inside its last row, and a JSON array whose closing
  bracket is missing. Every input is a real record frozen in this corpus with one stated edit, synthetic-derived
  under the D-096 precedent, and `tools/derive_corrupt_inputs.py` rebuilds them from the public expected values.
  The corrupt record must come back refused with a reason and the records around it loaded. A parser that
  validates no checksum is reported on the first input, not failed, and a whole-file refusal of a cut file passes,
  with the complete records it gives up counted. The outcomes are counted in the existing loaded, misidentified,
  refused and dropped vocabulary (D-142, D-144). The case runs offline, so CI and the GitHub Action run it (D-171).
  What a parser returns from each input is compared with what it returns from the same records unedited, three
  files that ship beside the inputs, so the case grades what the corrupt input changes; how exactly a parser reads
  the records is left to the values check, which grades it in their own cases (D-175).

### Changed

- The reference reader rejects a TLE field that is not a number with an error that names the field (it used to
  surface as an internal error of the corpus), and a CSV row whose field count differs from the header's (it used
  to come back as a record with the missing values empty). The reference adapter reads TLE sets one at a time, so a
  set it rejects is refused with the reader's reason and the sets after it still load (D-171).
- `docs/FAILURES.md` covers the eighteen cases (D-173).
- The `pyephem` preset reports an element set `readtle()` refuses through the refusal channel, with PyEphem's own
  message as the reason; it used to drop the set, and the report said that refusals were not reported. Over the
  seventeen earlier cases `readtle()` refuses no set, so none of their results changes; the headline of the gate over
  this month's launches now says "dropped silently" where it said "refusals not reported by this adapter" (D-174).
- The Gpredict recipe's harness (`harnesses/gpredict/`) reports a set Gpredict rejects through the refusal channel,
  with the function's return code as the reason, where it used to drop it (D-178); so does the libsgp4 recipe's
  (`harnesses/libsgp4/`), with the library's exception message as the reason, and it now documents the build of
  release v3.0 (D-182); and so does the astroz recipe's (`harnesses/astroz/`), with the library's error name as the
  reason, and it now exits with astroz's error when astroz rejects a JSON file as a whole, where it used to return an
  empty list, so the report says that the parser refused the file (D-185).
- Every shipped adapter and recipe that splits a TLE file into sets for a library that reads one set at a time (the
  `pyephem`, `sgp4`, `satellite.js` and `tle.js` presets, and the Gpredict and libsgp4 recipes) hands each line 1 to
  the library with whatever line follows it, where it used to pass over a line 1 not followed by a line 2; the report
  then shows what the library does with a set missing its second line, not what the adapter does. `docs/ADAPTERS.md`
  asks the same of a new adapter (D-183).

### Fixed

- Three test-shim docstrings carried a local path; `tests/test_export.py` now fails on any absolute home path in an
  exported file (D-172).
- A failing command adapter's error reached an item's detail with the line ending its standard error ended with; it
  is now stripped (D-177).
- The README's row for `tle-writer-alpha5` left out the positive-exponent BSTAR input added in 0.3.0 (D-125), so the
  inputs it listed added up to 609 rather than 610; it now names all four synthetic-derived inputs (D-187).

## [0.3.0] - 2026-09-27

A minor release under the versioning rule: the adapter protocol gains a refusal channel, an additive change,
and the corpus becomes installable with pip: the runner and the corpus's own files in one package, a `gpconf`
command, presets that test a library with no adapter written, and a GitHub Action. In a clone nothing changes:
`tools/fetch.py` and `python3 -m gpconf` work as before. The seventeen cases stay and no frozen expected value
changed (the writer case gained one input); the naive and python-sgp4 adapters still fail 14 and 7 of them. The
independent audit in `AUDIT.md` covered v0.1.0; neither the writer-side case of v0.2.0, the fixes of v0.2.1 nor
the changes of this release have been separately audited. Version DOI 10.5281/zenodo.22986178 (Zenodo record
22986178); the concept DOI 10.5281/zenodo.22867654 resolves to the latest release.

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
