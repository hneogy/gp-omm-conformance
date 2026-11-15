# gpconf specification 1.0 (draft)

Status: **draft**, written 2026-11-10 for gpconf 0.9.0 (plan item d1, decision D-432). Not yet read by an outside
reader; a second implementation has not been written from it [untested]. It is versioned apart from the package:
gpconf 0.9.0 implements specification 1.0, and the results schema `gpconf/schemas/results-1.0.schema.json` is its
report format.

The key words MUST, MUST NOT, SHOULD and MAY are used as in RFC 2119. Where this text and `docs/ADAPTERS.md` differ,
`docs/ADAPTERS.md` describes what gpconf 0.9.0 does, and the difference is a fault in this draft.

## 1. Scope

gpconf grades a *reader* of general-perturbations (GP) element data: a program that turns a provider's text (TLE,
2LE, OMM in CSV, JSON, XML or KVN) into records. It also grades, where a reader offers them, five vector hooks, a TLE
writer and an SGP4 propagator. It grades what the reader returns against expected values the corpus holds; it does not
propagate, determine orbits, or judge a provider.

## 2. Terms

- **Corpus:** the inputs (provider files, fetched; derived files, shipped; vectors, shipped), the expected values
  (`fixtures/*/expected.json`, `vectors/*.json`) and the manifest (`manifest.json`).
- **Case:** a named group of checks over a set of inputs. **Check:** one rule, named by an id. **Item:** one check
  applied to one input; an item has a status. The runner adds one item per check and file for a case that reads
  files, one per hook for the vector case (its input is the vector file), and one per check, with no file, for the
  propagation cases. It also adds items under names of its own that are not in `manifest.json`: `values`, `parse`,
  `format-supported`, `source-present`, `records-returned`, `refusals`, `fields-not-returned`,
  `stable-source-drift`, `parser-exit` among them.
- **Adapter:** the bridge between gpconf and the reader under test, by Python import (§6.1) or by command (§6.2).
- **Record:** one element set as the adapter returns it (§4).
- **GP:** general perturbations, the mean element sets SGP4 propagates. **TLE:** the two-line element set, lines 1
  and 2 of 69 columns each, with a checksum in column 69. **Alpha-5:** the TLE's five-character catalog field for
  100000 to 339999: a letter for 10 to 33 (A to Z without I and O), then four digits (`vectors/alpha5.json`,
  `gpconf/tle.py`).
- **Formats (`fmt`):** `tle` is a TLE file in which a set may have a name line before line 1 (a 3LE); `2le` holds
  the two element lines only, and its expected `object_name` is none. **OMM:** the CCSDS Orbit Mean-Elements Message
  (CCSDS 502.0-B-3), as `csv`, `json`, `xml` (inside an **NDM**, the CCSDS Navigation Data Message wrapper) or `kvn`
  (one `KEYWORD = value` per line).
- **SGP4:** the propagator for GP element sets. **TEME:** the true-equator, mean-equinox frame SGP4 answers in.
  **WGS-72:** the gravity constants the references use. **opsmode `'i'`:** SGP4's improved operation mode, as against
  `'a'`.

## 3. Cases and checks

The cases, their inputs and their checks are listed normatively in `manifest.json`: `cases[*].id`, `.kind`,
`.checks`, `.sources`, and the check definitions in `checks`. For 0.9.0:

| case | kind | checks |
|---|---|---|
| `epoch-year-19xx` | gp | `catalog-number-is-integer`, `omm-formats-agree`, `tle-values-match-omm-within-tle-precision`, `tle-checksums-valid`, `two-digit-year-pivot`, `csv-json-omit-constant-metadata`, `xml-ndm-wrapper-omm-2.0`, `kvn-blank-mandatory-values`, `leading-dot-decimals`, `negative-bstar-and-ndot`, `sha256-matches-tested-snapshot` |
| `baseline-iss-five-formats` | gp | `catalog-number-is-integer`, `omm-formats-agree`, `tle-values-match-omm-within-tle-precision`, `tle-checksums-valid`, `two-digit-year-pivot`, `csv-json-omit-constant-metadata`, `xml-ndm-wrapper-omm-2.0`, `kvn-blank-mandatory-values`, `leading-dot-decimals` |
| `six-digit-omm-saramago` | gp | `catalog-number-is-integer`, `omm-formats-agree`, `tle-format-omits-ids-above-99999`, `empty-answer-yields-no-records`, `csv-json-omit-constant-metadata`, `xml-ndm-wrapper-omm-2.0`, `sha256-matches-tested-snapshot` |
| `tle-omits-six-digit-objects` | gp | `tle-format-omits-ids-above-99999`, `empty-answer-yields-no-records`, `tle-count-equals-omm-count-below-100000`, `catalog-number-is-integer` |
| `analyst-objects` | gp | `object-id-may-be-empty`, `object-name-unknown-literal`, `catalog-number-is-integer`, `tle-format-omits-ids-above-99999`, `empty-answer-yields-no-records`, `tle-count-equals-omm-count-below-100000`, `omm-formats-agree`, `xml-ndm-wrapper-omm-2.0`, `kvn-blank-mandatory-values` |
| `nine-digit-supgp-launch-nominals` | gp | `nine-digit-ids-parse`, `catalog-number-is-integer`, `omm-formats-agree`, `tle-format-omits-ids-above-99999`, `empty-answer-yields-no-records`, `supgp-extra-keys-tolerated`, `classification-c` |
| `supgp-celestrak-classification-c` | gp | `catalog-number-is-integer`, `supgp-extra-keys-tolerated`, `classification-c`, `element-set-zero-and-rev-one`, `omm-formats-agree`, `tle-values-match-omm-within-tle-precision`, `tle-checksums-valid` |
| `bstar-and-derivative-forms` | gp | `catalog-number-is-integer`, `bstar-implied-decimal-exponent`, `negative-bstar-and-ndot`, `mmdot-is-tle-field-value`, `tle-values-match-omm-within-tle-precision`, `tle-checksums-valid`, `tle-count-equals-omm-count-below-100000` |
| `satcat-70000-cutoff` | satcat | `satcat-legacy-below-70000` |
| `csv-json-omitted-mandatory-fields` | facts | `csv-json-omit-constant-metadata`, `supgp-extra-keys-tolerated`, `catalog-number-is-integer` |
| `mean-motion-derivative-convention` | pairs | `mmdot-is-tle-field-value` |
| `tle-vs-omm-precision-loss` | pairs | `tle-values-match-omm-within-tle-precision` |
| `omm-xml-schema` | xml | `xml-ndm-wrapper-omm-2.0`, `catalog-number-is-integer` |
| `alpha5-encoding-vectors` | vectors | `alpha5-decode`, `alpha5-encode`, `catalog-number-is-integer`, `two-digit-year-pivot`, `ccsds-epoch-strings` |
| `alpha5-tle-derived` | derived-tle | `tle-catalog-field-decodes`, `tle-checksums-valid`, `catalog-number-is-integer` |
| `kvn-syntax-variants` | derived-kvn | `kvn-syntax-tolerance`, `optional-tle-parameters-may-be-absent`, `omm-version-3-accepted`, `catalog-number-is-integer` |
| `tle-writer-alpha5` | writer | `tle-checksums-valid`, `tle-writer-catalog-field`, `tle-writer-column-layout`, `tle-writer-round-trip`, `tle-writer-refuses-unencodable`, `tle-writer-secondary-not-changed`, `tle-writer-secondary-fields`, `tle-writer-matches-provider-rendering` |
| `corrupt-input` | corrupt-input | `corrupt-tle-checksum-digit`, `corrupt-tle-line-short`, `corrupt-tle-letter-in-number`, `corrupt-tle-missing-line-2`, `corrupt-tle-invalid-catalog-field`, `corrupt-tle-line-fields-differ`, `corrupt-file-cut`, `corrupt-input-neighbours-load`, `catalog-number-is-integer` |
| `sgp4-ver-propagation` | propagation | `sgp4-ver-positions`, `sgp4-ver-error-codes` |
| `propagation-tle-omm-twins` | propagation-twins | `twins-tle-positions`, `twins-omm-positions`, `twins-tle-omm-agree` |
| `ephemeris-type-4-refused` | propagation-type4 | `type4-not-propagated`, `type4-twins-propagate` |

Inputs whose kind is a provider's (`gp`, `satcat`, `facts`, `pairs`, `xml`) are fetched by the user and are not
shipped; an absent input that a fetch can bring is `not-fetched`, and one that is the corpus's own capture of a
launch window, which no fetch requests, is `not-available` (D-229); a case's status follows §9. The `derived-*`,
`vectors`, `writer`, `corrupt-input` and `propagation*` kinds run from shipped files, except `sgp4-ver-propagation`,
whose reference files are located on the user's machine (§8).

`manifest.json` is normative for the case ids, their kinds, the check ids each case lists (`cases[*].checks`) and
the check definitions (`checks`). Each case's expected values are in the file its `cases[*].expected` names,
`fixtures/<case>/expected.json`. Where the files are: provider files under `fixtures/<case>/raw/` (brought by
`gpconf fetch`); derived files under `derived/` (`derived/kvn-variants/`, `derived/propagation-twins/` and the
others); vectors under `vectors/`. A shipped file that is not on disk stops the run: the copy of the corpus is
incomplete, and no status is reported for it.

The parts of an `expected.json` the runner grades from:

- `kind`, which selects how the case is run;
- `sources`: each input by its path, with its `format` (the `fmt` it is sent as), `sha256`, `tier`, `record_count`
  and `http_status`. A file whose SHA-256 is the recorded one is graded against the frozen values (mode
  `snapshot`); otherwise against the corpus's own reference reader's reading of the same bytes (mode `live`), and a
  `stable` file whose bytes changed fails `stable-source-drift`;
- `records`: one entry per expected record, with `norad_cat_id`, `canonical` (the expected values under the keys of
  §4, element values as decimal strings), the file it belongs to (`derived_file` in a derived case, `present_in` in
  a provider case), `by_format.tle.differs_from_omm` (the values a TLE rendering carries in place of the OMM's) and
  `keywords_absent` (§7.3);
- `sets`, which group the files a case compares with each other;
- `case_specific`, per kind: the vector case holds a copy of each of the four `vectors/*.json` files under its path
  (§6.4); the corrupt-input case its edits and the files it grades for their values.

The other keys (`as_written`, `differences`, `values_identical_to_base`, `kvn`, `transform`, `coverage`,
`ambiguities`, `notes`, `tests`) document the case and are not graded. In `kvn-syntax-variants`, every KVN file the
parser reads passes `kvn-syntax-tolerance`, `optional-tle-parameters-may-be-absent` and `omm-version-3-accepted`, and
its values are graded in its `values` item. The case's one XML file, `derived/kvn-variants/v07-xml-ndm-reserialised.xml`,
is not one of its sources: it is graded for its values in the `corrupt-input` case (D-299).

## 4. The record

A record is a mapping with these keys. Core keys MUST be present in every record; an optional key is compared only
when present, and an adapter SHOULD leave out a key its reader does not keep rather than invent a value. The one
exception to the core rule is a key whose keyword the input leaves out (§7.3).

| key | core | type and unit |
|---|---|---|
| `norad_cat_id` | yes | integer |
| `epoch` | yes | an instant, UTC: a `datetime` (a naive one is read as UTC, an aware one converted to UTC) or a string in one of the forms of §7.2 |
| `mean_motion` | yes | revolutions per day |
| `eccentricity` | yes | dimensionless |
| `inclination`, `ra_of_asc_node`, `arg_of_pericenter`, `mean_anomaly` | yes | degrees |
| `bstar` | yes | as the TLE and OMM carry it (earth radii⁻¹) |
| `mean_motion_dot`, `mean_motion_ddot` | yes | as the TLE prints them (rev/day², rev/day³), which is also how the OMM carries them |
| `object_name`, `object_id`, `classification_type`, `center_name`, `ref_frame`, `time_system`, `mean_element_theory` | no | strings |
| `ephemeris_type`, `element_set_no`, `rev_at_epoch` | no | integers |

An integer key MUST hold an integer type: a float, a string or a `Decimal` that converts cleanly fails, and so does
a bool (D-283). The element values, `mean_motion` to `mean_motion_ddot`, MAY be strings, `Decimal`, `int` or `float`
(§7.1).

A TLE file holds one record per set. A KVN file MAY hold several OMM messages, each beginning with its
`CCSDS_OMM_VERS` line, and each message is one record (`derived/kvn-variants/v08-synthetic-epochs.kvn` holds eight).

Keys beginning with `_` are the adapter's own and are not graded, except `_refused` and `_adapter` (§5) and the
runner's reserved `_notes`, `_bad` and `_record`, which an adapter MUST NOT use.

## 5. Refusals and declarations

A reader that rejects a record SHOULD say so: an entry `{"_refused": REASON, "_field": CATALOG_FIELD, "_input":
TEXT}` in the same list as the records. `REASON` MUST be a non-empty string; `_field` is the catalog field exactly
as the input carried it and credits the refusal to that record; `_input` quotes the offending input. A refusal means
the record was dropped: a record both returned and refused fails (D-396), and a refused record that the case
expects still fails its file's values outside `corrupt-input` (§7.3). An entry `{"_adapter": {"refusals": true,
"propagation": {"gravity": ..., "opsmode": ...}}}` declares that the adapter reports refusals and which constants its
propagator uses; a declaration is reported, never trusted (D-413).

## 6. The adapter protocols

### 6.1 Python

`parse(raw: bytes, fmt: str) -> list` where `fmt` is one of `tle`, `2le`, `csv`, `json`, `xml`, `kvn`. Raising
`gpconf.runner.Unsupported` answers that the format is not read; any other exception refuses the file as a whole.
Optional methods: the five vector hooks, `write_tle(record)` and `propagate(raw, fmt, tsince)` (§8). The vector hooks:

- `alpha5_decode(field: str) -> int`;
- `alpha5_encode(n: int) -> str`, the five-character field;
- `two_digit_year(yy: str) -> int`, `yy` being two ASCII digits, such as `"57"` or `"00"`;
- `parse_epoch(text: str) -> datetime`; a string returned fails the vector (D-306);
- `parse_catalog_id(text: str) -> int`.

A hook rejects its input by raising any exception other than `Unsupported`. Raising `Unsupported` answers that the
library has no such operation (§6.3). A hook that is absent skips its item. A returned integer MUST be of an integer
type, never a bool or a float of the same value (D-296).

### 6.2 Command

`--cmd "PROGRAM {fmt}"`: the string runs through a shell; gpconf substitutes the format for `{fmt}`, writes the file's bytes to standard input and reads
standard output. Exit 0 with a JSON array: the records and entries of §4 and §5. Exit 3: the format is not read (a
skip). Any other exit, or output that is not a JSON array of objects: the file fails as `parse`. An end by a signal,
or a run past the budget (120 seconds by default), is a crash, never a refusal. JSON numbers are compared as binary
floats within the float tolerance, strings exactly (§7). An object holding one key twice with two values is no
answer (D-398).

`--vectors-cmd PROGRAM`: one run per vector, `{"op": NAME, "input": VALUE}` on standard input. `NAME` is the hook's
name (`alpha5_decode`, `alpha5_encode`, `two_digit_year`, `parse_epoch`, `parse_catalog_id`, and `propagate`, §8).
`VALUE` is a JSON string for every op but two: an integer for `alpha5_encode`, and an object for `propagate`; for
`two_digit_year` it is the two-digit string (`"00"`, not `0`). The answer is `{"result": V}`, `{"error": REASON}`
(a rejection) or `{"unsupported": REASON}` (the hook is absent: for all of an op's vectors or none; `REASON` MUST be a
non-empty string). Any non-zero exit, 3 included, and an answer with none of the three keys, are rejections (D-205).
A crash or a timeout is no rejection: the vector fails (D-341). For `parse_epoch`, `V` is an epoch string, read as
§7.2 reads one; an answer that is no epoch, or the input's own text sent back where it is not already the calendar
form, is an answer and never a rejection: it fails a valid vector and accepts an invalid one (D-306, D-382). Once
`--vectors-cmd` is given, all five vector hooks are asked. `--write-cmd PROGRAM`: one record in, TLE lines out
(`docs/WRITERS.md`).

### 6.3 Unsupported is all or none

An outcome that is not a graded pass or fail (unsupported, a skip, a refusal) holds for all of its scope or none: a
format answered unsupported for some inputs of a run and read for others fails those inputs (D-280). The scopes are:
for a format, every input of that format in the run, in the same case or another; for a vector hook, every vector
of that hook; for `write_tle`, every record of the writer case; for `propagate`, every set of
`sgp4-ver-propagation`, and in `propagation-tle-omm-twins` every set of one rendering (the seven TLE sets, or the
seven CSV rows). Unsupported for all of a scope skips its items; for part of it, those items fail. The one exception
is the type-4 case's type-4 files (D-410).

### 6.4 The vector case

`alpha5-encoding-vectors` reads its vectors from its `expected.json`, `case_specific`, which holds the four files of
`vectors/` under their paths. Each file's lists are normative for which inputs are valid. One item per hook:

- `vectors/alpha5.json`, check `alpha5-decode`: for every entry of `official_examples`, `boundaries`,
  `skip_boundaries` and `below_100000`, `alpha5_decode(field)` MUST return the integer `norad_cat_id`; every
  `decode_invalid[*].field` MUST be rejected.
- `vectors/alpha5.json`, check `alpha5-encode`: for the same four lists, `alpha5_encode(norad_cat_id)` MUST return
  `field` exactly; every `encode_unrepresentable[*].norad_cat_id` MUST be rejected.
- `vectors/two-digit-epoch-year.json`, check `two-digit-year-pivot`: for every entry of `vectors`,
  `two_digit_year(yy)` MUST return the integer `year`; a raise fails that vector. The file's `epoch_field_examples`
  are not graded.
- `vectors/ccsds-epoch-strings.json`, check `ccsds-epoch-strings`: for every `valid[*].text`, `parse_epoch` MUST
  return a `datetime` within 2 microseconds of `iso` or of one of `iso_alternatives` (a leap second may read as
  23:59:59 or as the next second); every `invalid[*].text` MUST be rejected. The 27 leap-second dates are
  `LEAP_SECOND_DATES` in `gpconf/tle.py`. These are the inputs `parse_epoch` is given; they are not the forms a
  record's epoch may take (§7.2), which allow an offset.
- `vectors/norad-cat-id-text.json`, check `catalog-number-is-integer`: every `valid[*].text` MUST parse to the
  integer `value`; every `invalid_in_omm[*].text` MUST be rejected.

Each vector is one call, an entry listed twice is called twice, and the item passes when every vector agrees.

## 7. Comparison

This section holds for the records a reader returns. Propagation has its own rule (§8).

### 7.1 Values

Expected values are exact decimal strings (`records[*].canonical`). A returned string, `Decimal` or integer MUST
match exactly as a decimal value, not as text: `.0125362` matches `0.0125362`, and `1.15630e-5` matches
`0.000011563`. A string MUST be a plain decimal number (optional sign, ASCII digits, optional point and exponent,
nothing around it); text outside that form, a NaN or an infinity is no value and fails the file as `parse`. A binary
float is read as the decimal of its shortest round-trip text (Python's `repr`): when that equals the expected value it
is a `pass`; otherwise it passes as `pass-tolerance` when |got − want| / max(|got|, |want|) ≤ 1e-12, with no floor,
and an expected zero MUST be an exact zero. A text key MUST match exactly, except that `object_name` is compared without the blanks that end it (D-369).
Where the format carries no value for `center_name`, `ref_frame`, `time_system`, `mean_element_theory` or
`classification_type`, the record MAY leave it out or answer none or the OMM default (`EARTH`, `TEME`, `UTC`,
`SGP4` or `SGP/SGP4`, `U`); any other value fails (D-285, D-336).

### 7.2 Epochs

A returned epoch string MUST take one of the forms `YYYY-MM-DDThh:mm:ss[.f]` (the calendar form) or
`YYYY-DDDThh:mm:ss[.f]` (the day-of-year form), with any number of fraction digits (rounded to the microsecond, half
to even), and an optional `Z` or `+hh:mm`/`-hh:mm` offset, which is converted to UTC. Second 60 is read only at a
leap second, 23:59:60 UTC on one of the 27 dates of `gpconf/tle.py`, as 23:59:59; an expected leap-second epoch also
accepts the next second. Whitespace around the epoch, or any other text, fails the file as `parse` (D-325). A
string that is not exactly the calendar form, with no zone, and that the input holds as written (or, for the
day-of-year form, holds once a `Z`, a zero offset and the fraction's trailing zeros are set aside) is the input's own
text handed back: it fails the record (D-306, D-370). So for an input whose epoch is `1998-324T06:49:59.999808Z`, a
reader returns a `datetime` or a string it built, such as `1998-11-20T06:49:59.999808`. An epoch equal to the expected
instant passes; one within 2 microseconds of it is `pass-tolerance`. The one other epoch bound is 432 microseconds,
half the TLE's 1e-8-day resolution: in `tle-values-match-omm-within-tle-precision`, which holds the parser's TLE
record against its OMM record of the same object, and nowhere else in the record comparison.

### 7.3 Matching

Records are compared file by file. The expected records of a file are the `records` whose `derived_file` is the
file's name or whose `present_in` names it, and they are matched to the returned records by catalog number. The file's
`values` item fails when:

- a record carries no `norad_cat_id`, or one that is not an integer;
- an expected record is not returned. Outside `corrupt-input` this holds whether or not it is refused: a refusal with
  a reason is counted as `refused_matched`, a record with none as `dropped`, and both fail the item;
- a record carries a catalog number the file does not hold (unless the expected values cover only part of the
  file, as some provider cases' do);
- a catalog number is returned more often than the input holds it (D-311), or less often (D-344);
- a core key is missing, or an optional key is returned for some records of the file and left out of others (D-284);
- a compared value does not match (§7.1, §7.2).

An optional key with expected values that the parser never returns in a file is not compared; it adds a
`fields-not-returned` item, `not-exercised` (D-284).

Where an expected record lists keywords in `keywords_absent` (the input leaves them out), the keys they stand for
(`EPHEMERIS_TYPE` `ephemeris_type`, `CLASSIFICATION_TYPE` `classification_type`, `NORAD_CAT_ID` `norad_cat_id`,
`ELEMENT_SET_NO` `element_set_no`, `REV_AT_EPOCH` `rev_at_epoch`) MUST be left out of the returned record or be
none: the `canonical` values for them are not expected values, and a value, an empty text included, fails (D-358).
Where `NORAD_CAT_ID` is among them, the expected record is matched to the returned record that carries no catalog
number, and `catalog-number-is-integer` is not graded on that file (`kvn-syntax-variants`'s v05).

## 8. Propagation

`propagate(raw: bytes, fmt: str, tsince: list) -> list` is called once per element set and rendering. `raw` is that
set alone: for `fmt` `tle`, its two element lines, with no name line, each ended by CR LF; for `csv`, the header line
and the set's one row. `tsince` is a list of minutes since the set's epoch. The answer is one step per time, in
order, `{"r": [x, y, z], "v": [vx, vy, vz], "error": CODE}`: TEME, km and km/s, the SGP4 error code an integer (0
when the step propagated; a step without `error` reads as 0). On a step with code 0, `r` and `v` MUST each be three
finite numbers; on an error step they are not compared and MAY be none. An answer with more or fewer steps than the
times asked fails the set. Raising refuses the set, and since every graded set is valid input, a refusal fails;
`Unsupported` follows §6.3. By command, the op is `propagate` with `{"raw": TEXT, "fmt": FMT, "tsince": [...]}` as
its input and the list of steps as its result. A command's first `propagate` call of a run is a probe with no times
(`"tsince": []`) and MUST be answered `{"result": []}`; any other answer means the command has no propagate op, and
the propagation items skip. A Python hook is not probed.

The bar is absolute: every component of `r` and `v` within 2e-7 km and km/s of the reference, with WGS-72 and
opsmode `'i'`; §7's relative rule does not apply. A positions item passes when every compared difference is exactly
zero, is `pass-tolerance` when the largest is above zero and within the bar, and fails above the bar or when no step
was compared. Error codes MUST match exactly.

- `sgp4-ver-propagation`: each set of Vallado's `SGP4-VER.TLE`, sent as `tle`, at the times its line gives (0 first,
  then from the start by the step to the stop), against `tcppver.out`. gpconf ships neither file: they are looked
  for in the directory given with `--sgp4-ver`, in the installed python-sgp4 package and in the copy
  `gpconf fetch --include-propagation` downloads, and used only when their SHA-256 are those of
  `harnesses/vallado/reference-manifest.json`; without them both items are `not-exercised`. Where a set's run ends
  in an SGP4 error, the code at the step after the block's last printed line MUST be the manifest's; a non-zero code
  before it fails as a false decay.
- `propagation-tle-omm-twins` (D-406): seven sets, `derived/propagation-twins/twins.tle` (a name line, then the two
  element lines, per set) and their exact OMM twins, the rows of `derived/propagation-twins/twins.csv`, in the same
  order. The expected steps are `sets[k].steps[*]` (`t`, `error`, `r`, `v`) of `vectors/propagation-twins.json`, the
  corpus's own SGP4 output. `twins-tle-positions` grades the TLE answers, `twins-omm-positions` the CSV answers;
  `twins-tle-omm-agree` requires the two answers of each set propagated both ways to agree within the same bar with
  the same codes at every step, over at least one step both propagated.
- `ephemeris-type-4-refused`: an ephemeris-type-4 set MUST NOT be propagated as SGP4 (D-409, D-410); its rules are in
  `docs/ADAPTERS.md`.

An adapter MAY declare its constants in `parse`'s answer (§5). gpconf reads the declaration once a run, from `parse`'s
answer to the first twins set, and reports it as an `info` item; it never changes the reference.

## 9. Statuses and the report

An item ends in one of `pass`, `pass-tolerance`, `fail`, `skip`, `not-fetched`, `not-available`, `not-exercised`,
`info`. A case's status follows from its items, by the first rule that applies:

1. `fail`, if any item fails;
2. `not-exercised`, if some check the case lists in `manifest.json` has items and every one of them is
   `not-exercised` by the parser's own doing (cause `parser`, D-294);
3. the first of `pass-tolerance`, `pass`, `not-exercised`, `not-fetched`, `not-available` that any item has, in
   that order;
4. `skip`, otherwise: every item skipped or is `info`, or there is none.

So one `pass-tolerance` item makes a case `pass-tolerance`, a case with passing and skipped items is `pass`, and an
`info` item never moves a case. What triggers each item status:

- `pass`, `pass-tolerance`, `fail`: a graded comparison (§7, §8); `pass-tolerance` when it needed a tolerance.
- `skip`: the parser answered `Unsupported` for the whole of a scope (§6.3), or has no such hook.
- `not-fetched`: a provider file that a fetch can bring is not on disk (§3).
- `not-available`: a provider file that is the corpus's own capture of a launch window is not on disk; no fetch
  requests it (D-229).
- `not-exercised`: the check could not be measured. Cause `data`: the data lacks what the check needs (no nine-digit
  id in a fresh fetch; Vallado's files not found). Cause `parser`: the parser's own behaviour voided the comparison
  (a field it never returns, D-284; a record it drops from the unedited file as well, D-175).
- `info`: reported and not graded: a property of the file that no parser takes part in (`tle-checksums-valid` on a
  file read, `sha256-matches-tested-snapshot`), the refusals a file carries (`refusals`, which fails instead for a
  refusal without a reason or a record both returned and refused), an adapter's propagation declaration, the
  writer's secondary fields.

The `--json` report's shape is the results schema 1.0 (`gpconf/schemas/results-1.0.schema.json`);
`python3 -m gpconf.schema REPORT` checks a report against it. `gpconf run` exits 0 when no case failed and some case
was graded (ended `pass`, `pass-tolerance` or `fail`), 1 when a case failed, and 2 when nothing could run, no case
was graded, or the `--json` report could not be written (D-370, D-389).

## 10. Versioning

This specification and the results schema carry one version, `MAJOR.MINOR`. A minor version MAY add cases, checks,
hooks, keys and statuses' details; a change that can turn a passing reader into a failing one is listed in the
changelog under "Changes that can move your result", and a removed key or a changed meaning is a new major version.

## 11. Open points in this draft

- §9's rule for a case's status from its items was checked against `CaseResult.status` in `gpconf/runner.py` on
  2026-11-11, with the item statuses' triggers.
- The record matching of §7.3 covers every case but `corrupt-input`. That case's crediting rules (refusals credited
  by `_field`, by a quote in `_input`, a cut file's records) are in `docs/ADAPTERS.md` and would have to move here for
  a second implementation to grade from this text alone; so would the writer case's rules (`docs/WRITERS.md`), the
  type-4 case's (§8) and the provider cases' per-check rules beyond the `checks` text of `manifest.json`.
- No outside reader yet (the plan's bar: "reviewed by one outside reader").
