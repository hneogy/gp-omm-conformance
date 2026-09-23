# Research notes: GP / OMM / Alpha-5 migration

All facts below were read from the cited sources on **2026-09-20 (approx. 22:30–23:10 UTC)**.
Nothing here is from model memory; where a claim rests on a secondary source it is marked.
Quotations are verbatim. Bracketed notes are mine.

Only documentation pages, standards documents and schema files were fetched in this phase.
**No GP data was downloaded.** Each page was fetched once (a few were re-read from the
local copy). See "Fetch log" at the end.

---

## 1. The catalog-number event

CelesTrak's site-wide notice (identical on the GP formats page, the SATCAT page and the
Current GP Element Sets page):

> URGENT: We ran out of 5-digit catalog numbers with the addition of Saramago on 2026-07-11.
> We had estimated that to occur around 2026‑07‑12 back on 2026-05-09.
> The official USSF SATCAT is now at 100789.
> All newly cataloged objects will have 6-digit catalog numbers of 100000+ and GP data will
> not be available for them using the TLE format. CelesTrak developed new formats that
> removed the 5-digit catalog number limitation (and finally fixed the Y2K problem) in May
> 2020 and immediately began providing GP data in those formats for software developers.
> [...] The same limitations apply to the legacy fixed-field SATCAT. That legacy format will
> continue to update but will only contain data for objects with catalog numbers below 70000.

Source: https://celestrak.org/NORAD/documentation/gp-data-formats.php (page dated
"2020 May 27, Updated 2026 Jun 23").

Why 69999 and not 99999 (same page, FAQ addendum):

> If you thought that happens at 99999, you may be surprised to discover that is not true
> [...]. When we run out of 5-digit catalog numbers at 69999, new data will not be able to be
> created using the TLE format.

The 70000–99999 block is reserved: Space-Track's documentation says "The analyst range...is
denoted by a satellite number from 80,000-89,999" and CelesTrak refers to "the current
analyst sat range (80000-series)". Wikipedia's table (secondary) lists 70000–79999 as
"Expected post-launch orbits". The 90000 block is not described in any primary source I read.

Saramago details from a **secondary** source (KeepTrack deep-dive,
https://keeptrack.space/deep-dive/satellite-100000-saramago): Portuguese CubeSat,
international designator 2026-067CY, launched 2026-03-30 on a Falcon 9 rideshare from
Vandenberg, cataloged 2026-07-11. **To verify in Phase 2 via
`satcat/records.php?CATNR=100000`.**

## 2. What CelesTrak serves

### 2.1 GP query API

> All GP queries on CelesTrak will take the form:
> https://celestrak.org/NORAD/elements/gp.php?{QUERY}=VALUE[&FORMAT=VALUE]

`{QUERY}` is one of `CATNR` ("Catalog Number (1 to 9 digits)"), `INTDES` (yyyy-nnn),
`GROUP`, `NAME`, `SPECIAL` (`GPZ`, `GPZ-PLUS`, `DECAYING`). "{QUERY} must be uppercase."

Formats:

> TLE or 3LE: Three-line element sets including 24-character satellite name on Line 0.
> 2LE: Two-line element sets (no satellite name on Line 0).
> XML: CCSDS OMM XML format including all mandatory elements.
> KVN: CCSDS OMM KVN format including all mandatory elements.
> JSON: OMM keywords for all GP elements in JSON format.
> JSON-PRETTY: OMM keywords for all GP elements in JSON pretty-print format.
> CSV: OMM keywords for all GP elements in CSV format.
> The FORMAT specification is optional, but defaults to CSV (as of 2026 May 09).

[Confirms the CSV default you mentioned.]

Companion endpoints with the same query structure: `gp-first.php` (first GP data ever
available for the match) and `gp-last.php`. Example given:
`https://celestrak.org/NORAD/elements/gp-first.php?INTDES=2024-149&FORMAT=JSON-PRETTY`.
[Useful for a real 19xx two-digit epoch year: the first ISS elset is from 1998.]

Supplemental GP (operator-supplied) data uses
`https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?{QUERY}=VALUE[&FORMAT=VALUE]`
with `CATNR`, `INTDES`, `SOURCE`, `NAME`, `SPECIAL`, `FILE`, same formats, same CSV default.
Source: https://celestrak.org/NORAD/documentation/sup-gp-queries.php

### 2.2 TLE output excludes 6-digit objects; CelesTrak does not emit Alpha-5

> Of course, TLE formats will not support objects with catalog numbers above 99999.

and, in the FAQ addendum:

> CelesTrak already provides GP data for USSF Space Fence analyst objects that use 6-digit
> catalog numbers. You can see that toward the end of this table but if you click on the link
> for the TLE-formatted data in the header, you will notice it does not include any of the
> 27xxxx catalog numbers (it only shows 8xxxx catalog numbers). Using a format like CSV or
> JSON will include all of the data.

So a TLE/3LE/2LE request for a group **silently drops** objects >= 100000 rather than
encoding them in Alpha-5. The word "Alpha-5" does not appear anywhere on CelesTrak's GP
formats page. The FAQ explains the design position:

> There have been numbering schemes suggested that would extend the range of catalog IDs
> that would fit in a 5-character field of a TLE. The easiest would be to extend the current
> 'numbering' by allowing the leading character to go from 0-9 and then A-Z. At best, this
> would allow for tracking 360,000 objects (assuming you don't discard I and O, as has been
> suggested by some). [...] 18 SPCS is already assigning catalog numbers in their new analyst
> sat range of 7995xxxxx (or over 799,500,000). So, there would be no way to map these
> 9-digit catalog numbers to 5-character IDs. [...] Including letters means the field will no
> longer be able to be simply validated by verifying that it is an integer and integer
> comparisons will no longer be possible. For example, some TLEs use leading zeros in the
> 5-digit field while others do not. But a value of 00964 parses as an integer the same way
> as 964.

**Consequence for the corpus:** real Alpha-5 TLEs are only obtainable from Space-Track
(login required; see section 4). The two open questions in PLAN.md follow from this.

### 2.3 Real 6-digit and 9-digit numbers already exist on CelesTrak

- 6-digit: `GROUP=analyst` contains Space Fence analyst objects numbered 27xxxx (quote
  above), plus every newly cataloged object since 2026-07-11 (100000+), which appear in
  `GROUP=last-30-days` and by `CATNR`.
- 9-digit: > if you look closely at the SupGP data for a recent Starlink launch, you will
  notice we are already using the 18 SDS 9-digit launch nominals catalog numbers (in the
  799xxxxxx range). The same will be true for future Transporter and Bandwagon launches.

  The supplemental index page (https://celestrak.org/NORAD/elements/supplemental/, "Current
  as of 2026 Sep 20 22:44:37 UTC") lists **"Starlink G15-27 Post-Deployment"**
  (`sup-gp.php?FILE=starlink-g15-27`), launch 2026-09-20 01:47:00 UTC, deploy
  2026-09-20 02:49:15.220 UTC. **Whether that file currently carries 799xxxxxx numbers is
  unverified** (would require fetching data). Launch nominals are by nature short-lived.

### 2.4 Analyst objects and null mandatory fields

> There are XML and KVN (key-value notation) versions of the OMM standard and CelesTrak will
> provide all mandatory elements of those formats. Some elements may be blank (KVN) or null
> (XML), if not available via the current TLE format. An example might be that an object in
> the current analyst sat range (80000-series) typically will not have a name (OBJECT_NAME)
> or International Designator (OBJECT_ID).

> Additionally, data will be provided in both JSON and CSV formats, using the same keywords
> and definitions as provided in the OMM standard (CCSDS 502.0-B-3, Table 4-1), although
> null/blank or redundant (e.g., CENTER_NAME = EARTH, REF_FRAME = TEME, TIME_SYSTEM = UTC,
> MEAN_ELEMENT_THEORY = SGP4) mandatory fields will not be included.

[Ambiguity to resolve with data in Phase 2: in JSON/CSV, is a null OBJECT_ID an absent key /
empty cell, or is the column always present? CCSDS says the value should be `UNKNOWN`
(section 5 below); CelesTrak emits blank/null instead. This is a genuine spec-vs-practice
divergence and will be recorded as such in the manifest.]

### 2.5 OMM version CelesTrak targets

> CelesTrak [...] has begun making the GP data available via standard queries using the
> Orbit Mean-Elements Message (OMM) that is part of the Orbit Data Messages (ODM)
> Recommended Standard CCSDS 502.0-B-3 [...] in November 2009. We are recommending the XML
> format of Version 2.0 of the OMM, as defined in XML Specification for Navigation Data
> Messages (CCSDS 505.0-B-3)

[Note: the page's citation is internally inconsistent. "November 2009" is the date of
502.0-B-**2**; 502.0-B-3 is April 2023 and defines OMM **3.0**. Expect CelesTrak XML to carry
`version="2.0"`. To verify in Phase 2.]

### 2.6 SATCAT API and the legacy file

> All SATCAT queries take the form:
> https://celestrak.org/satcat/records.php?{QUERY}=VALUE[&FORMAT=VALUE]

Same `{QUERY}` set; flags `PAYLOADS`, `ONORBIT`, `ACTIVE`, `MAX`; formats `JSON` (default),
`JSON-PRETTY`, `CSV`. CSV fields: `OBJECT_NAME, OBJECT_ID, NORAD_CAT_ID, OBJECT_TYPE,
OPS_STATUS_CODE, OWNER, LAUNCH_DATE, LAUNCH_SITE, DECAY_DATE, PERIOD, INCLINATION, APOGEE,
PERIGEE, RCS, DATA_STATUS_CODE, ORBIT_CENTER, ORBIT_TYPE`.

> The legacy text format is not able to support catalog numbers above 99999, Unicode
> characters, increased precision in numerical fields, or launch/decay dates including time,
> due to the fixed-column format.

Full-catalog files: `/pub/satcat.csv` and `/pub/satcat.txt` (legacy fixed width; NORAD number
in columns 14–18). Source: https://celestrak.org/satcat/satcat-format.php (Updated 2023 May 7).

## 3. CelesTrak usage policy (governs Phase 2)

From the FAQ addendum (Added 2024 Aug 30, Updated 2026 Mar 26):

> CelesTrak only checks for new GP data once every 2 hours, so there is no need for you to
> check more often.

> Your process can avoid this situation by checking for a successful response (an HTTP 200)
> and being prepared to handle unexpected responses. If some other response is received, your
> process should stop and report the problem to a human. In particular, if you receive an
> HTTP 403 or 404 error, the response is not going to change by repeating the request and
> can result in your IP address being put in the firewall.

> we now set a limit on HTTP errors (301, 403, or 404) of 50 in a 2-hour period, at which
> point the IP address is sent to the firewall.

> If you are using more than 100 MB/day you can expect that your IP address may end up in
> the firewall.

> CelesTrak will now (as of 2026 Mar 26) simply enforce the one-download-per-update policy
> for all users, starting with the Active and Starlink GROUPs. [...] The first request will
> work fine, but the second will return something like this (with an HTTP 403 response)
> until the GP data updates again

> Since 2026 Feb 16, we have seen bandwidth usage jump from ~125 GB/day to ~330 GB/day

> the 18 SDS GP data only updates 2-3 times a day.

Also: use `https://celestrak.org` (the `.com` domain issues 301s, which now count toward the
error limit). Legacy static `.txt` files were all removed 2024 Dec 24.

## 4. Alpha-5 (Space-Track)

Source: https://www.space-track.org/documentation (public FAQ and "Alpha 5" section; the
per-class model definitions on that page are login-gated: "Please login to view this content.").

> Alpha-5 is a stopgap object numbering schema from the United States Space Force that
> increases the satellite catalog's capacity to display up to 339,999 objects in the
> GP/GP_History API classes using legacy fixed-width Two and Three Line Element Set (TLE/3LE)
> formats. Replacing the 1st digit of the 5-digit object number with an alphanumeric
> character makes it possible to represent 240,000 more numbers. Objects less than 100,000
> are unaffected by Alpha-5, as are users who download elsets from the GP and GP_History API
> classes in other formats like XML, JSON, KVN, and CSV. In order to preserve legacy
> operations that depend on 5-digit integers, our legacy API Classes tle, tle_latest, and
> tle_publish will not change to Alpha-5.
> Only capital letters and numbers are used in Alpha-5. The letters "I" and "O" are omitted
> to avoid confusion with the numbers "1" and "0".

Official examples ("as they would be seen in the TLE"):

```
100000 => A0000
148493 => E8493
182931 => J2931
234018 => P4018
301928 => W1928
339999 => Z9999
```

Full table ("Full Alpha-5 Numbering"):

```
A=10 B=11 C=12 D=13 E=14 F=15 G=16 H=17 J=18 K=19 L=20 M=21 N=22
P=23 Q=24 R=25 S=26 T=27 U=28 V=29 W=30 X=31 Y=32 Z=33
```

Other statements:

> Only the TLE and 3LE formats will show this Alpha-5 designator in lines 1 and 2. All other
> formats are capable of handling object numbers up to 999,999,999.

> Users can only query the API using numbers in NORAD_CAT_ID. [...] The API will not support
> filtering on Alpha-5 values or ranges like /NORAD_CAT_ID/T0000--V9999/

How to get them:

> https://www.space-track.org/basicspacedata/query/class/gp/NORAD_CAT_ID/100000--339999/format/tle/emptyresult/show

Checksum rule as stated by Space-Track (matches CelesTrak's): "Blanks, periods, letters, '+'
signs -> 0; '-' signs -> 1", sum modulo 10. [So the Alpha-5 letter contributes 0 to the
checksum; a checksum computed by treating the letter as its Alpha-5 value would be wrong.]

Reference implementation seen: python-sgp4 `sgp4/alpha5.py` (fetched from GitHub master):

```python
def to_alpha5(n):
    if n < 100000:
        return '%05d' % n
    if n > 339999:
        raise ValueError(...)
    i, n = divmod(n, 10000)
    i += ord('A') - 10
    if i >= ord('I'): i += 1
    if i >= ord('O'): i += 1
    return '%c%04d' % (i, n)

def from_alpha5(s):
    if not s[0].isalpha():
        return int(s)
    c, s = s[0], s[1:]
    n = ord(c) - ord('A') + 10
    n -= c > 'I'
    n -= c > 'O'
    return n * 10000 + int(s)
```

[Observation: `from_alpha5` accepts lowercase letters and the forbidden letters `I`/`O`
without error, so `I0000` decodes to 180000 (same as `J0000`). The corpus should include
those as **invalid** inputs and record that lenient decoders disagree with each other.]

## 5. CCSDS 502.0-B-3, Orbit Data Messages (April 2023) — the OMM

Source PDF: https://ccsds.org/Pubs/502x0b3e1.pdf (text extracted locally with pdftotext).
Title page: "Recommended Standard, Issue 3, April 2023". Section 4 is the OMM; section 7 is
syntax; section 8 is XML; annex G has examples.

### 5.1 Structure (4.2.1)

"The OMM shall be represented as a combination of the following: a) a header; b) metadata;
c) data; and d) optional comments."

### 5.2 Header, Table 4-1

| Keyword | M/O/C | Notes |
|---|---|---|
| CCSDS_OMM_VERS | M | "Format version in the form of 'x.y'"; example value 3.0 |
| COMMENT | O | only immediately after the version keyword |
| CLASSIFICATION | O | free text |
| CREATION_DATE | M | UTC, format per 7.5.10 |
| ORIGINATOR | M | from SANA registry |
| MESSAGE_ID | O | |

### 5.3 Metadata, Table 4-2

| Keyword | M/O/C | Notes |
|---|---|---|
| COMMENT | O | |
| OBJECT_NAME | M | "If OBJECT_NAME is not listed in reference [3] or the content is either unknown or cannot be disclosed, the value should be set to UNKNOWN." |
| OBJECT_ID | M | "Recommended values have the format YYYY-NNNP{PP}" ... "If the asset is not listed [...] or the content is either unknown or cannot be disclosed, the value should be set to UNKNOWN." |
| CENTER_NAME | M | |
| REF_FRAME | M | "TEME of date shall be used for OMMs based on NORAD Two Line Element sets" |
| REF_FRAME_EPOCH | C | |
| TIME_SYSTEM | M | |
| MEAN_ELEMENT_THEORY | M | examples SGP, SGP4, SGP4-XP, DSST, USM |

### 5.4 Data, Table 4-3 (relevant rows)

| Keyword | Units | M/O/C |
|---|---|---|
| EPOCH | | M |
| SEMI_MAJOR_AXIS or MEAN_MOTION | km / rev/day | M ("if MEAN_ELEMENT_THEORY = SGP/SGP4, the Keplerian Mean motion in revolutions per day") |
| ECCENTRICITY | | M |
| INCLINATION, RA_OF_ASC_NODE, ARG_OF_PERICENTER, MEAN_ANOMALY | deg | M |
| GM | km**3/s**2 | O |
| MASS, SOLAR_RAD_AREA, SOLAR_RAD_COEFF, DRAG_AREA, DRAG_COEFF | | O |
| *TLE Related Parameters* "(This section is only required if MEAN_ELEMENT_THEORY=SGP/SGP4)" | | |
| EPHEMERIS_TYPE | | O, "Default value = 0" |
| CLASSIFICATION_TYPE | | O, "Default value = U" |
| NORAD_CAT_ID | | O — **"NORAD Catalog Number ('Satellite Number') an integer of up to nine digits. This keyword is only required if MEAN_ELEMENT_THEORY=SGP/SGP4."** |
| ELEMENT_SET_NO | | O |
| REV_AT_EPOCH | | O |
| BSTAR or BTERM | 1/[Earth radii] / m**2/kg | C (BSTAR for SGP4, BTERM for SGP4-XP) |
| MEAN_MOTION_DOT | rev/day**2 | C |
| MEAN_MOTION_DDOT or AGOM | rev/day**3 / m**2/kg | C |
| Covariance block, USER_DEFINED_x | | C / O |

TLE conventions, 4.2.4.6:

> The value associated with the CENTER_NAME keyword shall be 'EARTH'. [...] REF_FRAME [...]
> 'TEME'. [...] TIME_SYSTEM [...] 'UTC'. [...] The format of the OBJECT_NAME and OBJECT_ID
> keywords shall be that of the UN Office of Outer Space Affairs designator index. [...] The
> MEAN_MOTION keyword must be used instead of SEMI_MAJOR_AXIS.

4.2.4.7: "Some sources suggest [...] CLASSIFICATION_TYPE [...] U=unclassified, S=secret." and
EPHEMERIS_TYPE "0 = SGP, 2 = SGP4, 3 = PPT3, 4 = SGP4-XP, 6 = Special Perturbations".

**The mean-motion-derivative trap** (4.2.4.7, NOTE 2):

> If the source of MEAN_MOTION_DOT and MEAN_MOTION_DDOT is a TLE or if these values are
> intended to be used as a TLE, then these values need to be divided by 2 and 6 respectively
> to reflect the SGP theory Taylor Series expansion terms.

[The TLE fields are conventionally ndot/2 and nddot/6. The standard does not say which
convention the OMM value carries; in practice (python-sgp4 `export_omm`, and, to be verified,
CelesTrak) the OMM value is the TLE field value as printed. This will be a manifest-level
"ambiguity" entry with the empirically observed behaviour.]

4.1.2: "The checksum and formatting requirements of the TLE do not apply to the values in an
OMM."

### 5.5 KVN syntax (section 7)

- 7.3.2: "Each OPM, OMM, or OEM line must not exceed 254 ASCII characters".
- 7.3.4: printable ASCII only; 7.3.5 blank lines allowed anywhere and meaningless;
  7.3.7 CR, LF, CRLF or LFCR terminators.
- 7.4.3: one assignment per line; 7.4.4: "Keywords must be uppercase and must not contain
  blanks."; 7.4.5–7.4.7: whitespace around keyword, `=`, and end of line is not significant.
- 7.4.8: "The order of occurrence of mandatory and optional KVN assignments shall be fixed
  as shown in the tables".
- 7.5.1: "A non-empty value field must be assigned to each mandatory keyword" [CelesTrak's
  blank OBJECT_ID for analyst objects therefore violates 7.5.1; see 2.4].
- 7.5.4: integers: decimal digits, optional sign, "Leading zeroes may be used", range
  -2^31..2^31-1 [nine-digit NORAD IDs fit].
- 7.5.5–7.5.7: fixed or floating point, "E" or "e", at most 16 digits.
- 7.5.10: epochs are `YYYY-MM-DDThh:mm:ss[.d→d][Z]` **or** `YYYY-DDDThh:mm:ss[.d→d][Z]`;
  fractional seconds optional and of any length; trailing `Z` optional; leading zeros
  required. [A parser hard-coded to `%Y-%m-%dT%H:%M:%S.%f` — python-sgp4's `omm.py` — will
  reject valid day-of-year, no-fraction and `Z` forms.]
- 7.7.1: units are optional in KVN, must exactly match the table, in square brackets after
  at least one blank, e.g. `[km]`.
- 7.8.5: comment lines start with `COMMENT` followed by at least one space; 7.8.8 restricts
  where they may appear in an OMM.
- 7.9.1: version table lists `CCSDS_OMM_VERS 2.0 Silver Book 2.0, 11/2009` and
  `CCSDS_OMM_VERS 3.0 Blue Book 3.0 (this document)`.

Annex G KVN example (Figure G-7) uses `MEAN_ELEMENT_THEORY = SGP/SGP4`, day-of-year epochs
(`EPOCH = 2020-064T10:34:41.4264`), `ELEMENT_SET_NO = 0925` (leading zero) and
`CREATION_DATE = 2020-065T16:00:00` (no fraction) — all legal and all likely to break naive
parsers.

### 5.6 XML (section 8.9, 8.13)

- 8.9.1–8.9.4: root `<omm>` with attributes `id="CCSDS_OMM_VERS"` and `version="3.0"`.
- 8.9.5–8.9.7: `<header>`, then `<body>` with a single `<segment>` holding `<metadata>` and
  `<data>`.
- Table 8-5 block tags: `<meanElements>`, `<spacecraftParameters>`, `<tleParameters>`,
  `<covarianceMatrix>`, `<userDefinedParameters>`.
- 8.13.2: "Each mandatory XML tag must be present and contain a valid value."
- 2.2 / 4.1.5 note: many OMMs "can be aggregated into a single NDM XML file as described in
  8.12" (root `<ndm>`).
- Annex G Figure G-10 shows `xsi:noNamespaceSchemaLocation=".../ndmxml-3.0.0-master-3.0.xsd"`.

## 6. CCSDS 505.0-B-3 (NDM/XML, May 2023) and the SANA schemas

Source PDF: https://ccsds.org/Pubs/505x0b3e2.pdf; schemas from
https://sanaregistry.org/r/ndmxml_unqualified/ (files dated 2024-02-08, "version 4.0.0 of
the NDM/XML Schema (05/19/2023)").

Downloaded (to be vendored under `schemas/` in Phase 3 with source URLs):
`ndmxml-4.0.0-master-4.0.xsd`, `ndmxml-4.0.0-common-4.0.xsd`, `ndmxml-4.0.0-omm-3.0.xsd`
(also available: `-ndm-4.0.xsd`, `-namespace-4.0.xsd`).

Schema facts that matter for conformance:

- `ommType`: `<xsd:attribute name="id" use="required" fixed="CCSDS_OMM_VERS"/>` and
  `<xsd:attribute name="version" use="required" fixed="3.0"/>`. **A `version="2.0"` document
  cannot validate against this schema.**
- `NORAD_CAT_ID` is `xsd:integer` (unbounded). `REV_AT_EPOCH` is `xsd:nonNegativeInteger`.
  `ELEMENT_SET_NO` is an integer restricted to 0–9999. `EPHEMERIS_TYPE` is `xsd:integer`.
  `OBJECT_ID` and `OBJECT_NAME` are `xsd:string`, minOccurs default 1 (mandatory, may be
  empty string).
- `meanElements` uses `<xsd:choice>` between `SEMI_MAJOR_AXIS` and `MEAN_MOTION`;
  `tleParameters` uses choices `BSTAR|BTERM` and `MEAN_MOTION_DDOT|AGOM`;
  `MEAN_MOTION_DOT` is mandatory inside `tleParameters`.
- Units attributes are optional, enumerated: `1/ER`, `rev/day`/`REV/DAY`, `rev/day**2`,
  `rev/day**3`, `m**2/kg`.
- `epochType` regex:
  `\-?\d{4}\d*-((\d{2}\-\d{2})|\d{3})T\d{2}:\d{2}:\d{2}(\.\d*)?(Z|[+|\-]\d{2}:\d{2})?|[+|\-]?\d*(\.\d*)?`
- `odmHeader`: `COMMENT*`, `CLASSIFICATION?`, `CREATION_DATE`, `ORIGINATOR`, `MESSAGE_ID?`.
- Master schema declares global elements `ndm`, `omm`, etc.; namespace `urn:ccsds:schema:ndmxml`,
  `elementFormDefault="unqualified"`.

Older schema versions (2.0.0 / 3.0.0) are only linked to
`https://cwe.ccsds.org/moims/docs/MOIMS-NAV/NDM-XML-Schema-Archive`, which redirected to a
SharePoint login (HTTP 403). **Not obtainable anonymously.**

## 7. TLE format (fixed columns)

Source: https://celestrak.org/NORAD/documentation/tle-fmt.php (Updated 2022 Jul 01) and
T.S. Kelso, "Frequently Asked Questions: Two-Line Element Set Format", Satellite Times,
January 1998, https://celestrak.org/columns/v04n03/.

Line 1: col 1 line number; **3–7 satellite number**; 8 classification; 10–11 launch year;
12–14 launch number; 15–17 piece; **19–20 epoch year (two digits)**; 21–32 epoch day of year
with fraction; 34–43 first derivative of mean motion; 45–52 second derivative ("Leading
decimal point assumed"); 54–61 BSTAR ("Leading decimal point assumed"); 63 ephemeris type;
65–68 element number; 69 checksum.

Line 2: 1; **3–7 satellite number**; 9–16 inclination; 18–25 RAAN; 27–33 eccentricity
(leading decimal assumed); 35–42 argument of perigee; 44–51 mean anomaly; 53–63 mean motion
(rev/day); 64–68 revolution number; 69 checksum.

Checksum: "Add the values of all the numbers on each line—ignoring all letters, spaces,
periods, and plus signs—and assigning a value of 1 to all minus signs. The checksum is the
last digit of that sum."

Implied-decimal exponent fields: "the value -12345-6 corresponds to -0.12345 × 10⁻⁶".

Two-digit year: "Two-digit years from 57-99 correspond to 1957-1999 and those from 00-56
correspond to 2000-2056." python-sgp4 `io.py` implements exactly this (`if two_digit_year <
57: year += 2000 else += 1900`).

## 8. Existing parsers (for cross-checks and for the failure catalogue)

python-sgp4 (GitHub master, fetched files `io.py`, `model.py`, `alpha5.py`, `omm.py`,
`exporter.py`):

- `twoline2rv` stores `satnum_str = line[2:7]` and the `satnum` property decodes via
  `from_alpha5`. README: Alpha-5 support added in 2.14 (2020-12-16); `satnum_str` exposed in
  2.22 (2023-04-27). `export_tle` writes `satnum_str` back verbatim (so it round-trips Alpha-5
  but will also happily write whatever string it was given).
- `omm.initialize`: `satnum = int(fields['NORAD_CAT_ID'])` (fine for 9 digits);
  `datetime.strptime(fields['EPOCH'], '%Y-%m-%dT%H:%M:%S.%f')` (breaks on CCSDS-legal
  variants); `fields['OBJECT_ID'][2:]` (KeyError if the key is absent; fine if empty);
  requires `CLASSIFICATION_TYPE`, `EPHEMERIS_TYPE`, `ELEMENT_SET_NO`, `REV_AT_EPOCH` to be
  present (all optional in CCSDS).
- `omm.parse_xml` walks `.//segment` and merges `metadata`, `meanElements`, `tleParameters`
  children by tag; ignores namespaces and units attributes.
- `export_omm` emits `MEAN_MOTION_DOT` / `MEAN_MOTION_DDOT` scaled back to TLE-field units
  (rev/day², rev/day³ as printed in a TLE, i.e. the halved / sixth-ed values) and `EPOCH`
  with `%f`.
- Unit constants in `omm.py`: `_ndot_units = 1036800.0 / pi`, `_nddot_units = 2985984000.0 /
  2.0 / pi`, `no_kozai = MEAN_MOTION / 720.0 * pi`.

Skyfield (https://rhodesmill.org/skyfield/earth-satellites.html): `EarthSatellite.from_omm(ts,
fields)` consumes CelesTrak CSV/JSON rows; docs recommend `GROUP=stations&FORMAT=csv`, saving
to disk and re-downloading only when the file is older than a chosen number of days.

Environment on this machine: Python 3.14.4, pip 26.0.1, lxml 6.1.0 present; `sgp4`,
`skyfield`, `xmlschema` not installed (will go in a project venv in Phase 3).

## 9. Space-Track's direction (GP class)

> We found that the conflating API classes of data with the names of the various formats for
> the same data was confusing. With 9-digit catalog numbers on the horizon, we need new API
> classes that will efficiently handle all General Perturbations elsets: they are GP and
> GP_History.

> The new GP classes are designed to accommodate the expanded satellite catalog's 9-digit
> identifiers. Users can return ephemerides for any publicly available object in the catalog
> using the CCSDS's flexible Orbit Mean-Elements Message (OMM) format in canonical XML/KVN,
> JSON, CSV, or HTML. All 5 of these formats use the same keywords and definitions for OMM as
> provided in the Orbit Data Messages (ODM) CCSDS Recommended Standard 502.0-B-3.

> We will deprecate the OMM and TLE API classes at some point in the future, but not the OMM
> and TLE formats.

Space-Track's definition of analyst objects: "tracked by the U.S. Space Surveillance Network
(SSN) with insufficient fidelity for publication in the public satellite catalog (SATCAT).
The analyst range...is denoted by a satellite number from 80,000-89,999." and "analyst
numbers can be constantly reused for different objects."

## 10. Not verified / not obtainable in this phase

1. Whether CelesTrak's XML declares `version="2.0"` or `"3.0"`, and what its root element is
   (`<ndm>` wrapper vs bare `<omm>`). Needs data.
2. Whether CelesTrak JSON/CSV omit the key or emit an empty value for null OBJECT_NAME /
   OBJECT_ID. Needs data.
3. Whether the Starlink G15-27 SupGP file currently contains 799xxxxxx numbers. Needs data;
   time-sensitive.
4. The exact HTTP response for `gp.php?CATNR=100000&FORMAT=TLE` (empty body? 404? "No GP
   data found"?). Needs data. Note a 404 here counts toward CelesTrak's error limit.
5. Space-Track GP class field list and Alpha-5 TLE samples (login-gated).
6. OMM 2.0 XML schema (archive behind SharePoint login).
7. Saramago's designator/launch (only a secondary source so far).
8. The convention CelesTrak uses for MEAN_MOTION_DOT/DDOT (TLE-field value vs true
   derivative). Needs a same-object TLE/OMM comparison.

## Fetch log (documentation only; one request each unless noted)

| Resource | URL | Result |
|---|---|---|
| CelesTrak GP formats doc | https://celestrak.org/NORAD/documentation/gp-data-formats.php | 200, 41 kB (fetched twice: once via summariser, once raw) |
| CelesTrak current GP index | https://celestrak.org/NORAD/elements/ | 200 |
| CelesTrak supplemental index | https://celestrak.org/NORAD/elements/supplemental/ | 200 |
| CelesTrak SupGP query doc | https://celestrak.org/NORAD/documentation/sup-gp-queries.php | 200 |
| CelesTrak TLE format doc | https://celestrak.org/NORAD/documentation/tle-fmt.php | 200 |
| CelesTrak TLE FAQ column | https://celestrak.org/columns/v04n03/ | 200 |
| CelesTrak SATCAT index | https://celestrak.org/satcat/ | 200 |
| CelesTrak SATCAT format doc | https://celestrak.org/satcat/satcat-format.php | 200, 20 kB (fetched twice) |
| CelesTrak Alpha-5 page (guessed URL) | https://celestrak.org/NORAD/documentation/Alpha-5.php | **404** (page does not exist; one error) |
| Space-Track documentation | https://www.space-track.org/documentation | 200, 186 kB (fetched twice) |
| CCSDS 502.0-B-3 PDF | https://ccsds.org/Pubs/502x0b3e1.pdf | 200, 2.2 MB |
| CCSDS 505.0-B-3 PDF | https://ccsds.org/Pubs/505x0b3e2.pdf | 200, 707 kB |
| SANA NDM/XML registry | https://sanaregistry.org/r/ndmxml/ and /r/ndmxml_unqualified/ | 200 |
| SANA schemas (3 files) | https://sanaregistry.org/files/ndmxml_unqualified/ndmxml-4.0.0-{master-4.0,common-4.0,omm-3.0}.xsd | 200 |
| CCSDS schema archive | https://cwe.ccsds.org/moims/docs/MOIMS-NAV/NDM-XML-Schema-Archive | 403 (SharePoint login) |
| python-sgp4 sources | https://raw.githubusercontent.com/brandon-rhodes/python-sgp4/master/sgp4/{io,model,alpha5,omm,exporter}.py and README | 200 |
| Skyfield docs | https://rhodesmill.org/skyfield/earth-satellites.html | 200 |
| KeepTrack article (secondary) | https://keeptrack.space/deep-dive/satellite-100000-saramago | 200 |
| Wikipedia (secondary) | https://en.wikipedia.org/wiki/Satellite_Catalog_Number | 200 |

---

# Phase 2 additions (read 2026-09-21, approx. 00:05–00:20 UTC)

## 11. Redistribution terms for CelesTrak data

Question asked by the project owner: does CelesTrak's usage policy or any terms page say
whether data obtained from CelesTrak may be redistributed in a third-party repository?

**Short answer: CelesTrak's site is silent on downstream redistribution. No licence, no
copyright notice and no terms-of-use statement about the data were found. Silence is not
treated as permission.** Details:

### 11.1 Pages read in full and what they contain

- **Usage Policy**, https://celestrak.org/usage-policy.php ("2026 May 15, Updated 2026 May 22").
  Entirely about request rates and cadences. The words "redistribute", "licence/license",
  "copyright", "terms" and "permission" do not occur in the page text. The only sentences
  bearing on the character of the data:

  > Only download the data you need, when you are going to use it, and only download data once per update.

  > Bottom line: There is no way for CelesTrak to set up a system to manage millions of users
  > without having to charge for access, which would immediately break our long tradition of
  > making data freely available to all users.

  Cadence statements useful for the README: "For GP data, updates are once every 2 hours. For
  SupGP data, which updates on different schedules for different constellations, please use 2
  hours, as well. [...] The SATCAT updates manually once or twice a day." and "M2M
  (machine-to-machine) software should immediately stop querying when it receives any non-HTTP
  200 responses and report the results to a human for investigation."

- **Home page**, https://celestrak.org/:
  > CelesTrak is now a 501(c)(3) non-profit and we need your help. CelesTrak's mission remains
  > focused on making data and other resources freely available to the space community to
  > facilitate understanding of our orbital environment and how to use it safely and responsibly.

- **Footer privacy notice** (popover on every page, titled "CelesTrak's Simple Privacy Policy"):
  > We do not use cookies on CelesTrak and we do not collect any personal information, other
  > than IP addresses, which are used to detect and block malicious activity and to assess
  > system performance. We do not use IP addresses for tracking or any other purposes. No
  > personal data is shared with third parties.

  (Nothing about data reuse.)

- **GP formats documentation** (https://celestrak.org/NORAD/documentation/gp-data-formats.php),
  **SATCAT format documentation** (https://celestrak.org/satcat/satcat-format.php),
  **SupGP query documentation** (https://celestrak.org/NORAD/documentation/sup-gp-queries.php),
  **Special Data Request forms** (https://celestrak.org/NORAD/archives/request.php and
  .../sup-request.php), **webmaster page** (https://celestrak.org/webmaster.php): searched for
  the same words; no licence, copyright or redistribution statements. The request forms only
  limit request volume ("Users are limited to 10 requests per 24-hour period").

- **Supplemental GP index**, https://celestrak.org/NORAD/elements/supplemental/ describes the
  provenance of operator data in terms of permission granted *to CelesTrak*:
  > Starlink [...] Derived from latest Starlink ephemeris data from SpaceX's public data repository.
  > Starlink G15-27 Post-Deployment — Derived from a post-deployment Starlink-G15-27 state vector, provided by SpaceX.
  > OneWeb [...] Derived from latest OneWeb ephemeris data on Space Track, with permission from OneWeb.
  > Kuiper [...] with permission from Amazon/Kuiper. Planet [...] with permission from Planet. [likewise Iridium, SES, Telesat, Orbcomm, AST Space Mobile, EUMETSAT]

  Nothing is said about what recipients of the SupGP data may do with it.

### 11.2 The legal history CelesTrak itself documents

**System Notices**, https://celestrak.org/NORAD/elements/notice.php ("Future Availability of
TLE Data", 2004 August 3, Updated 2007 May 16):

> Public Law 108-136 prohibits the redistribution of the data obtained from this new NUGE
> service "without the express approval of the Secretary" [of Defense] (paragraph (d)(2)).

> Update #14 (2005 March 25): On 2005 March 24, CelesTrak received the following message from
> Air Force Space Command authorizing redistribution of Space Track data: Your request to
> redistribute CFE Pilot Program data/analysis (TLEs and Space Situation Report (SSR) data)
> obtained from the Space-Track web site (https://www.space-track.org) via the CeleTrak web
> site (https://celestrak.com/) has been approved on 24 Mar 2005 in accordance with Air Force
> Space Command Commander's authority dated 8 November 2004.

> Update #16 (2007 May 16): [...] CelesTrak has received continuing authority to redistribute
> Space Track data "until superseded by formal updated documentation signed out by either the
> AFSPC/A3 or 14 AF/CC."

**Space Track TLE Retriever Help**, https://celestrak.org/spacetrack/TLERetriever3Help.php
(Updated 2025-03-14):

> While Air Force Space Command ultimately allowed waivers to redistribute the GP data, many
> users found TLE Retriever to be quite useful [...]

So the GP data CelesTrak serves is US Government (18 SDS / Space-Track) data that CelesTrak
redistributes under an authority granted to CelesTrak. None of these pages says that the
authority extends to people who obtain the data from CelesTrak, and none says it does not.

### 11.3 Assessment under the project's rule "interpret strictly, never permissively"

1. CelesTrak grants no licence and states no restriction. Under a strict reading the corpus
   has **no affirmative permission** to republish CelesTrak-served bytes.
2. The underlying GP data is government-originated and has been publicly and freely
   distributed by CelesTrak since 1985, and the statutory restriction CelesTrak quotes is
   phrased around data "obtained from this new NUGE service" (Space-Track). A permissive
   reading exists; the project's rule says not to rely on it.
3. SupGP records are derived from operator data, several under permissions granted to
   CelesTrak specifically. These are the weakest case for redistribution and are the **only**
   source of real 9-digit catalog numbers. They stay gitignored (DECISIONS D-002, D-018).
4. Resolving this needs one of: a statement from CelesTrak (contacting Dr. Kelso is an
   owner-only action under CLAUDE.md), or the owner's own legal judgment. Options that avoid
   the question are listed in PLAN.md "Phase 2 amendments".

Building the fixtures continues; publishing them does not, until the owner decides.

## 12. Other facts learned in Phase 2

- TLE Retriever help page (same URL as above) on what the TLE format can still carry:
  > You can obtain that data in the TLE format, if desired, but anything with a catalog number
  > beyond 69999 and the 8xxxx block won't be included. We have already been issuing 27xxxx
  > analyst satellite data for years and also provide 9-digit 799xxxxxx Starlink SupGP data for
  > the typical 5-8 days between launch and when 18 SDS starts releasing GP data for months now.
- CelesTrak's XML declares `xsi:noNamespaceSchemaLocation="https://sanaregistry.org/r/ndmxml_unqualified/ndmxml-2.0.0-master-2.0.xsd"`.
  A HEAD request to that URL on 2026-09-21 returned **HTTP 200** (3,738 bytes, Last-Modified
  2022-06-23), although the SANA registry *listing* page only shows the 4.0.0 files. The
  OMM 2.0 schema set is therefore fetchable by direct URL for Phase 3 validation; this
  supersedes the "not obtainable" note in §10 item 6 for the master file (the companion
  `-common-2.0.xsd` and `-omm-2.0.xsd` files still have to be checked the same way).
- Observed provider behaviour (full detail in `docs/INVENTORY.md`, generated from the raw files):
  - Every CelesTrak response uses CRLF line endings, including JSON and XML.
  - XML is wrapped in `<ndm>`; each `<omm>` has `version="2.0"`; the header's mandatory
    `CREATION_DATE` and `ORIGINATOR` are present but **empty** in XML and blank in KVN.
  - `MEAN_ELEMENT_THEORY` is `SGP/SGP4` in KVN but `SGP4` in XML for the same record.
  - Decimal values are written without a leading zero (`.00048259`, `.15975118E-3`) in CSV,
    KVN and XML; JSON carries proper numbers, and a zero BSTAR appears in JSON as the integer `0`.
  - Analyst objects: 565 in CSV/JSON/XML/KVN (219 in the 8xxxx block, 346 in 270000–270449);
    the TLE rendering has only the 219 five-digit ones. 563 of 565 have an empty `OBJECT_ID`
    (empty string in CSV/JSON/KVN, empty element in XML; the key is never omitted). All 565
    have an `OBJECT_NAME`.
  - `GROUP=last-30-days` currently holds only 6-digit ids (100404–100789); its TLE request
    returns HTTP 404 with the body `No GP data found`. `CATNR=100000&FORMAT=TLE` and
    `sup-gp.php?CATNR=799501621&FORMAT=TLE` return 404 with `No GP data found` /
    `No SupGP data found`.
  - The TLE rendering is lower precision than the OMM record it comes from: eccentricity is
    truncated (not rounded) to 7 digits in every observed case with more digits (69 of 80
    comparable records); BSTAR has 5 mantissa digits in the TLE against up to 8 in the OMM
    (76 of 80 differ numerically). `MEAN_MOTION_DOT` in the OMM equals the TLE field as
    printed in all 301 compared records (the TLE "ndot/2" convention). GP epochs convert
    exactly between the two representations; SupGP epochs do not (the G15-27 TLE epoch differs
    from the CSV epoch by 86 µs, inside the TLE's 864 µs resolution).
  - The earliest ISS record CelesTrak serves (`gp-first.php?CATNR=25544`) is a 1998 TLE with
    two-digit year `98`, negative first derivative, non-zero second derivative (`11563-4`),
    BSTAR written `00000+0`, element set number 1.
  - The legacy `satcat.txt` has exactly 69,999 lines with ids 1..69999 contiguous, none >= 70000.
  - SupGP records add two non-OMM columns, `RMS` and `DATA_SOURCE`, use `CLASSIFICATION_TYPE`
    `C`, and the G15-27 post-deployment file uses ids 72000/72001 with `ELEMENT_SET_NO` 0.
    The stack nominal (72000) and the first per-satellite nominal (799501621) share
    `OBJECT_ID` `2026-219A`.

## Fetch log, Phase 2 (documentation and policy pages; data fetches are listed per file in INVENTORY.md)

| Resource | URL | Result |
|---|---|---|
| Supplemental GP index (raw HTML) | https://celestrak.org/NORAD/elements/supplemental/ | 200 |
| Usage policy | https://celestrak.org/usage-policy.php | 200 |
| Home page | https://celestrak.org/ | 200 |
| Webmaster page | https://celestrak.org/webmaster.php | 200 |
| Privacy page (guessed URL) | https://celestrak.org/privacy.php | **404** (the policy is a footer popover, not a page) |
| Special data request forms | https://celestrak.org/NORAD/archives/request.php, .../sup-request.php | 200, 200 |
| System notices | https://celestrak.org/NORAD/elements/notice.php | 200 |
| 2000-12-28 notice | https://celestrak.org/norad/elements/notices/notice_2000-12-28.php | 200 |
| TLE Retriever help | https://celestrak.org/spacetrack/TLERetriever3Help.php | 200 |
| HEAD legacy SATCAT | https://celestrak.org/pub/satcat.txt | 200 (9,379,866 bytes) |
| HEAD OMM 2.0 master schema | https://sanaregistry.org/r/ndmxml_unqualified/ndmxml-2.0.0-master-2.0.xsd | 200 |

Non-200 responses received from celestrak.org by the end of Phase 2: 5 (Alpha-5.php 404,
privacy.php 404, and the three deliberate TLE-format 404s recorded as fixtures). Final tally after
Phases 3 and 4 [updated after the audit, AUDIT.md M6]: 8 — the two guessed documentation URLs
(Alpha-5.php, privacy.php) and six deliberate one-time TLE-format probes kept as fixtures
(saramago.tle, last-30-days.tle and its owner-instructed re-capture, starlink-38381 TLE,
saramago-first.tle, analyst-270449-first.tle). CelesTrak's stated threshold is 50 in 2 hours.

---

# Phase 3 additions (2026-09-21)

## 13. Facts established from the data and from library behaviour

Generated evidence lives in `docs/INVENTORY.md` (raw files), `docs/CROSSCHECK.md` (python-sgp4
2.27 and Skyfield 1.55 against the reference readers) and the `case_specific` blocks of each
`fixtures/<case>/expected.json`. Headlines:

- **TLE rendering rules (304 CelesTrak TLE/OMM pairs):** eccentricity truncated to 7 digits
  (304/304; rounding would match only 257), BSTAR and second-derivative mantissa rounded half
  up to 5 digits (304/304; truncation would match 271), first derivative and mean motion equal
  as printed (304/304), epoch exact for GP records (302/304) and within 86 µs for SupGP
  records. `tools/tlerender.py` reproduces all 304 records byte for byte with these rules.
- **Derivative convention:** OMM `MEAN_MOTION_DOT` equals the TLE field as printed in 304/304
  pairs; `MEAN_MOTION_DDOT` equals it numerically in 229/304 and differs in the rest only by
  the 5-digit mantissa rounding above.
- **XML schema:** all 8 CelesTrak XML files validate against the SANA ndmxml-2.0.0 set the
  documents declare (the 2.0 `epochType` pattern accepts the empty `CREATION_DATE`), and all
  8 fail the current ndmxml-4.0.0 set on the fixed `version="3.0"` attribute only.
- **Analyst records** (`gp-first.php` for 270449 and 81011, and all 565 records of the current
  analyst group) carry `OBJECT_NAME` `UNKNOWN` (the CCSDS-recommended literal); 563 of the 565
  current records have an empty `OBJECT_ID`. [Corrected after the audit (AUDIT.md C3): an earlier
  version of this sentence said the current group "carries names (e.g. object designations)", which
  was wrong.]
- **`gp-first.php` for a 6-digit id** (100000, 270449) in TLE format returns the same
  HTTP 404 `No GP data found` as the live query: a stable 404.
- **python-sgp4 2.27 / Skyfield 1.55:** cannot initialise a Satrec from any nine-digit
  record (`ValueError: satellite number cannot exceed 339999`); `sgp4.omm.parse_xml` turns
  an empty `<OBJECT_ID/>` into `None` and `initialize()` raises `TypeError` (563 of 565
  analyst XML records; the CSV path passes); `export_tle` writes a zero second derivative as
  ` 00000-0` where CelesTrak writes ` 00000+0` (815 of 908 records differ only there and in
  the checksum). Otherwise both libraries agree with the reference readers on every record
  they can load, including all 604 derived Alpha-5 lines.
- **Names:** one object in the fetched data (100465, 27 characters) has a name longer than
  the TLE's 24-character line 0; no CelesTrak TLE exists for it, so the cut rule is taken
  from the format documentation.
