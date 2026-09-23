# Writer-side checks: TLEs written across the five-digit boundary

The parser cases ask whether code that *reads* GP data survives the migration. This document covers
the other direction: code that *writes* TLE lines, which every newly catalogued object now forces into
the Alpha-5 form and which amateur tools generate for new launches. It records the protocol, the
precision rule, what the case contains, what the three bundled writers did, and what was observed about
strf's `rffit`, with every claim about an external tool labelled **tested** or **inferred**. The
reasoning is in `DECISIONS.md`, D-095 to D-101.

## What a writer must get right

1. **Columns 3-7 of both lines.** Five digits with leading zeros below 100000; from 100000 to 339999
   the Alpha-5 form, a letter worth 10 to 33 (A=10 ... Z=33, I and O never used) followed by the last
   four digits: 100000 is `A0000`, 180000 is `J0000`, 230000 is `P0000`, 339999 is `Z9999`.
2. **Sixty-nine characters and a valid modulo-10 checksum** on each line. A letter counts 0 in the
   checksum, a minus sign counts 1.
3. **A refusal for a number the field cannot carry.** Above 339999, and below 0, there is no TLE
   rendering. The correct output is an error and no lines; the record belongs in an OMM format. The
   corpus reports that refusal as a pass. Writing six digits (a 70-character line), a blank field or a
   garbage field is the failure.
4. **The elements read back at the field's resolution** (next section).

## The protocol

- Python adapter: `write_tle(record) -> (line1, line2)` or `(line0, line1, line2)`; `record` has the
  same keys as `parse()` returns (`norad_cat_id` as int, `epoch` as ISO text, the elements as decimal
  text). Raise to refuse. The hook is optional; without it the case is skipped.
- External writer: `python3 -m gpconf run --write-cmd "mytool --emit-tle"`: one JSON record on stdin,
  the lines on stdout, exit 3 for "writing unsupported", any other non-zero exit is a refusal.
- A file a tool wrote: `python3 -m gpconf check-tle FILE... [--against RECORDS]`. Same checks (length,
  checksum, catalog field, column layout), applied to every `1 `/`2 ` line pair in the file whatever its
  length; name lines, `#` comment lines and LF or CRLF endings are accepted; an element line without its
  partner, an indented line and a byte-order mark are reported as failures, not skipped; `--against`
  supplies the source records (CSV, JSON, XML, KVN or TLE, with the epoch in the calendar or the
  day-of-year form) for the round trip. A written record whose catalog number has no match in those records is a failure, not a
  note: the line is about some other object, or about none. When the number is `00000` or `99999` the detail
  names the likely cause on the rffit path (an `-i` lookup that found no elements leaves rffit's orbit
  zero-initialised, and 99999 is its default). Exit 1 on any failing record or when no record is found.

## The precision rule

A TLE field has a fixed resolution: epoch 1e-8 day, mean motion 8 decimals, the four angles 4 decimals,
eccentricity 7 digits, BSTAR and the second derivative a 5-digit mantissa. A written field is correct
when it equals the input quantised at that resolution **either by truncation or by rounding half up**,
because the two providers differ: CelesTrak truncates the eccentricity and rounds the mantissas
(304 of 304 records, case `tle-vs-omm-precision-loss`), Space-Track rounds the eccentricity (D-070,
D-071). The runner reports which convention it observed per field, and reports mixed conventions
without failing them. This is the format's resolution, not a tolerance: the comparison is exact against
one of two renderings, and the corpus's own renderer stays exact.

Fields an orbit-fitting tool regenerates by design (first and second derivative of mean motion, element
set number, revolution number, classification, designator, name) and the exponent sign written for a
zero second derivative (`+` at CelesTrak, `-` at Space-Track) are reported for information and never
failed.

## The case `tle-writer-alpha5`

Inputs are records already frozen in the corpus, so the case runs offline, with no CelesTrak request:
the 604 derived Alpha-5 records (603 distinct ids, letters A and T), the first ISS record (1998 epoch,
negative first derivative, non-zero second derivative, zero BSTAR), the first record of 69999 (negative
BSTAR and first derivative) and of analyst 81011 (blank designator, empty OBJECT_ID): 606 records, each
carrying the file it was copied from, the source file and its SHA-256. Three further inputs are
synthetic-derived with the owner's approval (D-096): the SARAMAGO first record with the catalog number
replaced by 340000, 799501621 and -1, the `encode_unrepresentable` values of `vectors/alpha5.json`.
Real elements, vector ids; their correct output is a refusal.

Checks: `tle-checksums-valid`, `tle-writer-catalog-field`, `tle-writer-round-trip`,
`tle-writer-refuses-unencodable`; information items `tle-writer-secondary-fields` and
`tle-writer-matches-provider-rendering`. Texts in `MANIFEST.md`.

## Three writers, one run (2026-09-22, `docs/FAILURES.md`)

| writer | result |
|---|---|
| reference (`gpconf.tle.render`, CelesTrak conventions) | every check passes exactly; 606 of 606 fields byte-identical to the provider or derived rendering; all three unrepresentable numbers refused |
| naive (`tests/adapters/naive.py`, the catalog number through an integer format) | 603 Alpha-5 inputs written as six digits in 70-character lines; nothing refused (`34000`, `79950` and `-0001` written); the three five-digit records are correct |
| python-sgp4 2.27 (`omm.initialize` + `exporter.export_tle`) | every real record passes, 606 of 606; eccentricity rounded (Space-Track style), zero second derivative written `-0`; 340000 and 799501621 refused in `omm.initialize` (the correct output); the single failure is the synthetic -1 vector, written as `-0001` because `to_alpha5` has no lower bound |

## strf's `rffit`, the writer behind satno2tle

strf (https://github.com/cbassa/strf, GPL-3.0; observed at HEAD 92d2425 of 2026-03-06) fits orbits to
Doppler observations and writes the result as a TLE. satno2tle (https://github.com/hobisatelit/satno2tle)
drives it from SatNOGS observations. Neither repository's code is in this corpus; strf is cited by file
and line only.

**Where it writes** (code reading). `format_tle`, rffit.c lines 111-149, is the only line formatter. It
writes the catalog field as `%5s` of the string returned by `number_to_alpha5`, satutl.c lines 45-58,
which looks up `number/10000` in a 34-character table with I and O skipped and appends the last four
digits; there is no range check. Fixed content: classification `U`, a zero first derivative, a zero
second derivative with the `-` sign, ephemeris type 0, element set 0, revolution 0. The eccentricity is
rounded (`%07.0f` of 1e7 times the value) and the BSTAR mantissa rounded to five digits. The checksum
(lines 130-146) counts digits and minus signs. `print_tle` (lines 1853-1890) writes the name, the two
lines and a `#` trailer with LF endings when the `w` key is pressed (lines 902-907). Alpha-5 reading was
added on 2024-12-22 (commits c1eb772, d3f5ab0), writing on 2024-12-24 (dbc250f); strf's own tests cover
decoding only.

**Build.** The `rffit` binary needs PGPLOT, X11, GSL and gfortran, none of which were present on the
machine used; nothing was installed. Instead, strf's unmodified `satutl.c` and `rffit.c` were compiled in
isolation and linked to a small harness that calls the two functions directly (recipe below). Every
"tested" statement is therefore **function-level, on strf's real code, not through the binary**.

**Tested (function level, 2026-09-22).**

- Encoder across the representable range: 5 gives `00005`, 99999 gives `99999`, 100000 `A0000`,
  109999 `A9999`, 110000 `B0000`, 179999 `H9999`, 180000 `J0000` (I skipped), 229999 `N9999`,
  230000 `P0000` (O skipped), 270449 `T0449`, 339999 `Z9999`. All agree with `vectors/alpha5.json`.
- Real records: the SARAMAGO first record (100000) gives two 69-character lines with valid checksums
  whose field decodes to 100000 in the corpus reference reader; epoch, mean motion, inclination, RAAN,
  argument of perigee, mean anomaly and designator exact; the lines differ from the corpus's
  CelesTrak-style rendering only at columns 40-42 (first derivative zeroed), 51 (`-0`) and 65-69
  (element set, revolution, checksum). 270449 gives `T0449` with the eccentricity rounded (`0045560`,
  where CelesTrak truncates to `0045559`) and the BSTAR mantissa rounded (`10753-3`). 69999 keeps
  `-70517-5`.
- Above the ceiling: for 340000, 350000, 999999 and 799501621 `number_to_alpha5` returns an empty
  string, and `format_tle` writes five blank characters in columns 3-7 of both lines, still 69
  characters with a valid checksum, no error, exit 0. For 340000 to 349999 the lookup index is 34, the
  table's string terminator; from 350000 the read is past the end of the table, undefined behaviour
  that happened to give the same result on the machine used. -1 gives `0-001`.
- Outside the catalog-number scope: the epoch year is written as `%2d` of `year-2000`, so 2005 gives
  ` 5` and 1998 gives `-2` in columns 19-20. Not relevant to rffit's use (epochs come from current
  observations).

**Reachability (code trace plus a decoder harness; one answer).** The only route for a number above
339999 into `format_tle` is the interactive `c` menu, item 9 "Satellite ID", rffit.c line 769, which
stores `atoi` of the typed text without a range check. Every copy of a parsed catalog entry into the
orbit (lines 169, 207, 232, 418, 856, 929) comes through `alpha5_to_number`, whose arithmetic caps the
result at 33 x 10000 + 9999 = 339999 (harness: `Z9999` gives 339999, `ZZZZZ` 330000, an unknown letter
0); the `-i` option (line 333) only selects among those entries (lines 411-420). No real catalog number
reaches 339999 today.

**Inferred, not run.** `rffit` has no non-interactive write path: options `-d -c -i -s -g -m -F -h`
(line 322), display device hard-coded to `/xs` (line 426), keys read through `cpgband` (line 704). An
adapter that only calls the binary would need an X display and keystroke injection, which is what
satno2tle's `auto.sh` does with xterm and xdotool (lines 293-303). That is why **there is no strf
adapter** in this corpus. `auto.sh` line 212 takes the second token of the third line of the SatNOGS
TLE file, the catalog field as text, and passes it to `rffit -i`, which applies `atoi` (rffit.c 333);
an Alpha-5 field such as `A0000` would become 0 and the catalog lookup would find nothing.

**Not claimed.** No bug is claimed for the `rffit` binary. A short hardening suggestion (a range check in
the helper, a refusal in the write path) is drafted in
`docs/upstream/strf-number-to-alpha5-range-check.md` and was filed, at the corpus maintainer's decision, as
https://github.com/cbassa/strf/issues/88 on 2026-09-23.

**For rffit and satno2tle users.** Check the file rffit wrote (satno2tle renames it `<obs>-tle.txt`):

```bash
python3 -m gpconf check-tle 13266946-tle.txt
```

The `#` trailer lines are ignored; a blank or six-digit catalog field is reported with the Alpha-5 form
it should have had.

## Reproducing the strf observation

Everything below is the corpus maintainer's own text; strf's files are used unmodified from your own
checkout. It was run with Apple clang on macOS; any C compiler with the same flags should do. Compiling
`rffit.c` needs an empty stand-in for PGPLOT's header, because only `format_tle` is called and the
plotting calls are never executed; `-undefined dynamic_lookup` (macOS) lets those symbols stay
unresolved. On Linux, provide empty stub functions instead or link with `--unresolved-symbols=ignore-all`.

```bash
git clone https://github.com/cbassa/strf.git          # GPL-3.0; stays in its own directory
mkdir -p harness/stubs && cd harness
printf '/* empty stand-in for cpgplot.h: rffit.c compiles, its plotting calls are never run */\n' > stubs/cpgplot.h
cc -O0 -g -w -c ../strf/satutl.c -o satutl.o
cc -O0 -g -std=gnu89 -w -Dmain=strf_main -I stubs -I ../strf -c ../strf/rffit.c -o rffit.o
cc -O0 -g -I ../strf -c harness.c -o harness.o
cc -o harness harness.o rffit.o satutl.o -lm -Wl,-undefined,dynamic_lookup
./harness 100000
./harness 340000
./harness 100000 2026 195.90649229 97.4593 154.0970 0.00055903 270.5113 89.5482 15.20467281 0.00022159168 26067CY
```

The last command renders the SARAMAGO first record (values from `fixtures/six-digit-omm-saramago`; the
day of year is the epoch 2026-07-14T21:45:20.933856). `harness.c`:

```c
/* Scratch harness (not part of any repository): calls strf's own number_to_alpha5() and
   format_tle() with a caller-supplied catalog number and elements, prints the result.
   usage: harness SATNO [ep_year ep_day incl_deg raan_deg ecc argp_deg ma_deg mm bstar desig] */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "sgdp4h.h"
void number_to_alpha5(int number, char *result);
void format_tle(orbit_t orb, char *line1, char *line2);
static void hexdump(const char *label, const char *s, int n) {
  int i; printf("%s bytes:", label); for (i = 0; i < n; i++) printf(" %02x", (unsigned char)s[i]); printf("\n");
}
int main(int argc, char **argv) {
  orbit_t orb; char satstr[16]; char line1[128], line2[128];
  memset(&orb, 0, sizeof orb); memset(satstr, 0x7e, sizeof satstr);
  if (argc < 2) { fprintf(stderr, "usage\n"); return 2; }
  orb.satno = atoi(argv[1]);
  number_to_alpha5(orb.satno, satstr);
  printf("satno=%d number_to_alpha5 -> \"%s\" (strlen %zu)\n", orb.satno, satstr, strlen(satstr));
  hexdump("  satstr", satstr, 8);
  if (argc >= 12) {
    orb.ep_year = atoi(argv[2]); orb.ep_day = atof(argv[3]);
    orb.eqinc = atof(argv[4]) * M_PI / 180.0; orb.ascn = atof(argv[5]) * M_PI / 180.0;
    orb.ecc = atof(argv[6]); orb.argp = atof(argv[7]) * M_PI / 180.0; orb.mnan = atof(argv[8]) * M_PI / 180.0;
    orb.rev = atof(argv[9]); orb.bstar = atof(argv[10]);
    strncpy(orb.desig, argv[11], sizeof orb.desig - 1);
    memset(line1, 0, sizeof line1); memset(line2, 0, sizeof line2);
    format_tle(orb, line1, line2);
    printf("line1=[%s] len=%zu\n", line1, strlen(line1));
    printf("line2=[%s] len=%zu\n", line2, strlen(line2));
  }
  return 0;
}
```

## What this document does not say

It does not say that strf, python-sgp4 or any other tool is broken; it records what each did on real
records and on the three vector ids. It does not compare any writer byte for byte with a provider as a
pass or fail: the two providers render the same values differently, and both are accepted. And it ships
no output of any external tool: every fixture line in the writer case was rendered by the corpus itself
from records whose provenance is in `manifest.json`.
