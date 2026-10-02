# A letter in a numeric TLE field

Four TLE readers named on this page accept a line 1 whose epoch field has the letter O where a 0 belongs, and read
the field as if it ended at the letter: the epoch comes back 14 minutes 16 seconds early, with no error and every
other value right. The line's checksum still holds, because the TLE checksum counts a letter as 0, as it counted the
0 the letter replaced. Two other readers named here refuse the line. The difference is whether the reader checks
that it converted the whole field. A seventh reader, python-sgp4's accelerated path, does a third thing: where the
four readers get one field wrong and the rest right, it accepts the line, stops reading it at the letter and leaves
four more fields unread, the two derivatives, BSTAR and the element-set number, with no error (below, for
comparison). This page is not a survey: it covers the readers named on it.

## The line

The corpus's `corrupt-input` case, input 3 ([`derived/corrupt-input/c3-letter-in-epoch.tle`](../derived/corrupt-input/c3-letter-in-epoch.tle)),
is the first record of catalog number 69999 with one edit, set between two valid records:

```
1 69999U 58002D   26189.7O990935 -.00000023  00000+0 -70517-5 0  9996
```

Column 26, the second fractional digit of the epoch field (columns 19 to 32), holds the letter O in place of 0, so
the field reads `26189.7O990935` where the record has `26189.70990935`. Read up to the letter, the day is 189.7,
2026-07-08 16:48:00 UTC, 14 min 16.17 s before the epoch the line means. The line is synthetic-derived: a real record
frozen in the corpus with this one edit, served by no provider ([`case.md`](../fixtures/corrupt-input/case.md) gives
its provenance; the case's check is `corrupt-tle-letter-in-number`).

## What each reader does

Each library was run on 2026-09-27 at the version named, against corpus v0.4.0. **Run** is what the library returned
for this line. **Read** is what its source shows at the same version, with links. Only the epoch field was given a
letter; where a line says that other fields are read the same way, that comes from the source, not from a run.

### Readers that accept the line

**PyEphem 4.2.1.** Run: `readtle()` returned the body with its epoch at day 189.7 and every other value equal to its
reading of the unedited set. Read: the day is read with `tle_fld()`
([`libastro/dbfmt.c#L239`](https://github.com/brandon-rhodes/pyephem/blob/4.2.1/libastro/dbfmt.c#L239)), which copies
the columns and returns `atod()` of them
([`#L362-L368`](https://github.com/brandon-rhodes/pyephem/blob/4.2.1/libastro/dbfmt.c#L362-L368)); `atod()` calls
`ascii_strtod()` without an end pointer
([`libastro/misc.c#L370-L374`](https://github.com/brandon-rhodes/pyephem/blob/4.2.1/libastro/misc.c#L370-L374)), so the
conversion stops at the letter and nothing records where. The other numeric fields go through the same functions.

**satellite.js 7.1.0.** Run: `twoline2satrec()` returned `epochdays` 189.7 and `error` 0, every other field as for the
unedited set (the npm package, where the line is `dist/io.js:77`). Read: the epoch field is converted with
`parseFloat()` ([`src/io.ts#L89`](https://github.com/shashwatak/satellite-js/blob/7.1.0/src/io.ts#L89)), which reads the
longest prefix that is a number and stops at the letter without an error. The other numeric fields of both lines are
read the same way.

**Gpredict 2.6.** Run: Gpredict's `sgp_in.c` at the tag, compiled by the corpus's recipe with a stand-in that maps
GLib's `g_ascii_strtod()` to C's `strtod()`; the application itself was not built. `Get_Next_Tle_Set()` returned 1, the
epoch at day 189.7, every other field as for the unedited set. Read: `Good_Elements()` accepts the line, since the
checksum ([`src/sgpsdp/sgp_in.c#L52-L77`](https://github.com/csete/gpredict/blob/v2.6/src/sgpsdp/sgp_in.c#L52-L77))
counts a letter as 0 and the decimal point it checks in the epoch field is in place
([`#L94`](https://github.com/csete/gpredict/blob/v2.6/src/sgpsdp/sgp_in.c#L94)). `Convert_Satellite_Data()` then
converts the epoch with `g_ascii_strtod()` and no end pointer
([`#L136`](https://github.com/csete/gpredict/blob/v2.6/src/sgpsdp/sgp_in.c#L136), the day fraction at
[`#L158`](https://github.com/csete/gpredict/blob/v2.6/src/sgpsdp/sgp_in.c#L158)), and every numeric field of both lines
with it or `atoi()` ([`#L136-L228`](https://github.com/csete/gpredict/blob/v2.6/src/sgpsdp/sgp_in.c#L136-L228)). GLib
documents `g_ascii_strtod()` as behaving like `strtod()` in the C locale, so the application should do what the
harness did; that part was not run.

**tle.js 5.0.3.** Run: `getEpochDay()` returned 189.7, every other getter as for the unedited set, and `isValidTLE()`
returned true for the set. Read: the epoch day is a float field of line 1
([`src/line-1-definitions.js#L105-L109`](https://github.com/davidcalhoun/tle.js/blob/v5.0.3/src/line-1-definitions.js#L105-L109)),
and `getFromTLE()` converts float fields with `parseFloat()`
([`src/utils.js#L154-L155`](https://github.com/davidcalhoun/tle.js/blob/v5.0.3/src/utils.js#L154-L155)), which stops at
the letter; integer fields go through `parseInt()`, which stops the same way. `isValidTLE()` checks the line numbers
and the checksums ([`src/parsing.js#L166-L190`](https://github.com/davidcalhoun/tle.js/blob/v5.0.3/src/parsing.js#L166-L190)),
and the letter changes neither.

### Readers that refuse the line

**libsgp4 v3.0.** Run: constructing a `Tle` from the set throws `TleException` with the message "Invalid digit", and
the sets around it load. Read: `Tle::ExtractDouble()`
([`libsgp4/Tle.cpp#L271-L376`](https://github.com/dnwrnr/sgp4/blob/v3.0/libsgp4/Tle.cpp#L271-L376)) checks a fixed-point
field one character at a time before converting it: an optional sign or leading spaces, then only digits in the
integer part, the decimal point exactly where the field puts it, and only digits after it; anything else throws. The
epoch's day goes through it ([`#L202`](https://github.com/dnwrnr/sgp4/blob/v3.0/libsgp4/Tle.cpp#L202)). Only a letter
after the decimal point was run; the checks on the integer part are read.

**astroz v0.14.0**, on Zig 0.16.0. Run: `Tle.parseLines()` returns `error.InvalidCharacter` for the set, and the sets
around it load. Read: astroz converts the epoch field with Zig's standard `std.fmt.parseFloat()`
([`src/Tle.zig#L85`](https://github.com/ATTron/astroz/blob/v0.14.0/src/Tle.zig#L85)), which returns a number only when
it has consumed the whole string and `error.InvalidCharacter` otherwise
([`lib/std/fmt/parse_float/parse.zig#L238-L246`](https://codeberg.org/ziglang/zig/src/tag/0.16.0/lib/std/fmt/parse_float/parse.zig#L238-L246),
[`lib/std/fmt/parse_float.zig#L37-L39`](https://codeberg.org/ziglang/zig/src/tag/0.16.0/lib/std/fmt/parse_float.zig#L37-L39);
Zig's own test rejects `"1abc"`,
[`#L77`](https://codeberg.org/ziglang/zig/src/tag/0.16.0/lib/std/fmt/parse_float.zig#L77)). The check is the
language's, not code of astroz's own.

For comparison, outside the libraries above: python-sgp4 2.27's accelerated `Satrec.twoline2rv`, Vallado's C++
`twoline2rv` as python-sgp4 ships it, accepts the line, but not as the four readers above do. Its `sscanf` over line 1
([`extension/SGP4.cpp#L2235`](https://github.com/brandon-rhodes/python-sgp4/blob/2.27/extension/SGP4.cpp#L2235))
converts the epoch field up to the letter, day 189.7, and stops there: the first and second derivatives, BSTAR and
the element-set number are never read and keep what the structure held, zero in python-sgp4, and `error` stays 0;
line 2 is read in full. Run on the library and, with sentinel values in the structure, on the C++ alone, 2026-10-01.
So the epoch is 14 min 16 s early and the drag term is gone, with no error: propagated about seven hours, the
position is 5,195.5 km from the unedited line's. Its pure-Python `sgp4.io.twoline2rv` raises `ValueError` on the
line, a split its maintainer documents as by design
([python-sgp4 #116](https://github.com/brandon-rhodes/python-sgp4/issues/116), and the README's "Double-checking your
TLE lines"). The corpus's own reference reader refuses the line with "TLE epoch field '26189.7O990935' is not a
number" ([`gpconf/reference.py`](../gpconf/reference.py)).

## Why the checksum does not catch it

The TLE checksum adds the line's digits, counts a minus sign as 1 and every other character as 0. A letter in place of
a 0 leaves the sum unchanged, so the line passes any checksum test. A letter in place of any other digit changes the
sum, and the readers above that test the checksum (PyEphem, Gpredict and tle.js's `isValidTLE()`) would refuse that
line, by their sources; only the 0 case was run. The line's length, its line numbers and the epoch's decimal point
are all as they should be. Only a check on the characters inside the field sees the letter.

## The fix

Refuse a field unless the conversion consumed all of it.

- C: pass an end pointer to `strtod()` (or `g_ascii_strtod()`) and refuse the field unless it reaches the end of the
  field; `strtod()` skips leading spaces itself. `atof()` and `atoi()` cannot report where they stopped, so use
  `strtod()` and `strtol()` instead.
- C with `sscanf()`: a conversion that fails part-way returns fewer items than asked for and leaves the rest
  unassigned. Compare the return value with the count expected, or add `%n` and check that it reached the end of the
  line.
- C++: the same, or a character check before converting, as libsgp4's `Tle::ExtractDouble()` does (linked above).
- JavaScript: `parseFloat()` and `parseInt()` read a prefix. Test the trimmed field against a number pattern first, or
  convert it with `Number()`, which returns `NaN` for `"26189.7O990935"`; `Number()` returns 0 for a blank field, so
  test for blank separately.
- Python: `float()` of the whole field already raises `ValueError`; the corpus's reference reader wraps it with the
  field's name.
- Zig: `std.fmt.parseFloat()` and `std.fmt.parseInt()` already refuse trailing characters, as astroz shows.

## Reproduce

The line alone is enough: hand it to the library's TLE reader and look at the epoch it returns. With the corpus
installed (`pip install gpconf`), `gpconf run --preset <name> --case corrupt-input` runs this line and the case's other
inputs, and needs no provider data; `gpconf presets` lists the presets (PyEphem, satellite.js and tle.js among them),
and the recipes in [`harnesses/`](../harnesses/) cover libraries a preset cannot load, Gpredict and libsgp4 among them.

---

Runs of 2026-09-27 against corpus v0.4.0, recorded in the corpus's decision log (D-174 to D-185; this page, D-193);
the python-sgp4 comparison re-run 2026-10-01 (D-197) and restated under D-211.
Reported on 2026-09-28 to PyEphem ([#297](https://github.com/brandon-rhodes/pyephem/issues/297)), satellite.js
([#190](https://github.com/shashwatak/satellite-js/issues/190)), Gpredict
([#427](https://github.com/csete/gpredict/issues/427)) and tle.js
([#63](https://github.com/davidcalhoun/tle.js/issues/63)).
