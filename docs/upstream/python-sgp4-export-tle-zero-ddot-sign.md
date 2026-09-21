# Informational note (NOT TO FILE): `export_tle` writes a zero second derivative as ` 00000-0`, which matches Space-Track; CelesTrak writes ` 00000+0`

Status: **withdrawn as a bug report; kept as documentation of a provider divergence.** Decision
D-072. Earlier drafts of this file proposed reporting the behaviour to python-sgp4; that was wrong.

## Why this is not a python-sgp4 bug

Space-Track, the outlet of the organisation that issues the element sets, writes a zero second
derivative of mean motion as ` 00000-0` (line 1 columns 45–52). python-sgp4's `export_tle` writes
the same, so its round trip is byte-consistent with the issuing organisation's rendering. It is
CelesTrak that renders the same value as ` 00000+0`, and because the exponent sign participates in
the modulo-10 checksum, column 69 differs too. Both spellings encode zero and every parser reads
both. What looked like a library defect when measured only against CelesTrak lines is a divergence
between the two providers' renderings, with python-sgp4 on Space-Track's side.

## What was measured

- Against CelesTrak-served files (2026-09-21, 306 TLE/2LE records from nine queries that returned
  records; five further TLE-format requests returned 404): the 225 records with a zero second
  derivative export from python-sgp4 with only columns 51 and 69 changed; the 81 with a non-zero
  second derivative export byte-exactly; line 2 is byte-exact in all 306.
- Against Space-Track (the corpus owner's own account, `tools/verify_against_spacetrack.py`,
  2026-09-21, DECISIONS D-070): every same-epoch Space-Track line differed from the corresponding
  CelesTrak-style derived line at column 51 (and 69), i.e. Space-Track uses `-0`, the convention
  python-sgp4 implements. No Space-Track data is reproduced here or anywhere in the corpus.

## Consequence for users of either library or provider

A byte-level TLE round-trip test succeeds against Space-Track lines and fails against CelesTrak
lines for every record with a zero second derivative; a value-level comparison succeeds against
both. Tests should compare values, or normalise the zero exponent sign, rather than bytes. The same
divergence exists in the eccentricity field: CelesTrak's TLE rendering truncates the OMM
eccentricity to seven digits while Space-Track's rendering rounds it (D-071), so a CelesTrak TLE and
a Space-Track TLE of the same element set can differ in the last eccentricity digit as well.

## Reference reproducer of the CelesTrak-side behaviour (no network)

An ordinary five-digit TLE in CelesTrak's layout (element values from the CCSDS 502.0-B-3 annex G
example, catalog 23581):

```python
from sgp4.api import Satrec
from sgp4.exporter import export_tle

l1 = "1 23581U 95025A   20064.44075725 -.00000113  00000+0  10000-3 0  9254"
l2 = "2 23581   3.0539  81.7939 0005013 249.2363 150.1602  1.00273272 43169"
e1, e2 = export_tle(Satrec.twoline2rv(l1, l2))
assert e2 == l2 and e1 != l1            # differs at columns 51 and 69 only: '-0' (Space-Track/python-sgp4) vs '+0' (CelesTrak)
```

## Suggested follow-up (documentation, not code)

If anything is worth raising with python-sgp4, it is a one-line README note that `export_tle`
follows Space-Track's zero-exponent convention and that CelesTrak lines differ in that one column,
so users expecting byte-exact round trips of CelesTrak TLEs are not surprised. That is optional and
is not part of the corpus's planned reports.
