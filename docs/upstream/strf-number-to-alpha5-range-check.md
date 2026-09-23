# Draft note for strf: a range check for `number_to_alpha5` (hardening suggestion, not a bug report)

Status: **filed** as https://github.com/cbassa/strf/issues/88 on 2026-09-23 (owner's decision and instruction; text
below filed verbatim, paragraphs unwrapped, without this status block). Prepared 2026-09-22 for the maintainer of
this corpus to read first and to decide whether and where to send it.
Prose only, no diff: strf is GPL-3.0 and this corpus is MIT, so no strf code appears here or anywhere
in the corpus. Every statement below is labelled. Decision D-101.

---

**Suggested title:** Range check for `number_to_alpha5` above 339999

**Text:**

strf's Alpha-5 writing is correct across the representable range. Calling `format_tle`
(rffit.c) and `number_to_alpha5` (satutl.c) directly, sources unmodified at commit 92d2425, gives
`A0000` for 100000, `J0000` for 180000 (I skipped), `P0000` for 230000 (O skipped), `T0449` for 270449,
`Z9999` for 339999, and 69-character lines with valid checksums for real records. [tested at function
level]

Above 339999 there is no range check: `number/10000` is 34 or more and the table has 34 entries, so for
340000 to 349999 the lookup lands on the string terminator, the helper returns an empty string, and
`format_tle` writes five blanks in columns 3-7 of both lines, with a valid checksum and no error.
[tested: 340000]

From 350000 upward the index runs past the table. Reading past it is undefined behaviour, and other
builds may differ. Here it gave the same blank field (350000, 999999, 799501621). [tested on one machine]

Only one route delivers such a number: the interactive `c` menu, item 9 "Satellite ID", which stores
`atoi` of the typed text (rffit.c line 769). Every catalog entry copied into the orbit passes through
`alpha5_to_number`, whose arithmetic cannot exceed 339999, and `-i` only selects among those entries. No
real catalog number reaches 339999 today. [code trace; decoder tested]

Suggestion: reject numbers below 0 or above 339999 in `number_to_alpha5`, or refuse in `format_tle`, so
a typed number outside the range gives a message instead of a TLE with a blank field. One line would
do; I can send a patch if welcome.

Reproduction: both files compiled unmodified in isolation and linked to a small harness (the `rffit`
binary was not built); source and commands in `docs/WRITERS.md` at
https://github.com/hneogy/gp-omm-conformance.

---

Word count of the text: about 270, a minute's read. Nothing here claims a defect in the `rffit` binary; the observation
is that the helper lacks a range check and the write path lacks a refusal, on a route no real catalog
number takes today.
