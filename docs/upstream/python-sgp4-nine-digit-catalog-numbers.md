# Draft bug report: `sgp4.omm.initialize` (and Skyfield `EarthSatellite.from_omm`) reject nine-digit NORAD_CAT_IDs that CelesTrak publishes

Status: draft, not yet filed. Target: brandon-rhodes/python-sgp4 (Skyfield inherits the behaviour).

## Environment

- python-sgp4 2.27, Skyfield 1.55, Python 3.14.4, macOS (observed 2026-09-21)
- Behaviour is in `Satrec.sgp4init` (reached through `sgp4.omm.initialize` and
  `skyfield.api.EarthSatellite.from_omm`); `Satrec.twoline2rv` is unaffected because a TLE
  cannot carry such a number.

## Summary

`sgp4.omm.initialize(sat, fields)` raises

```
ValueError: satellite number cannot exceed 339999, whose Alpha 5 encoding is 'Z9999'
```

for any OMM record whose `NORAD_CAT_ID` is above 339999. Such records are live provider data,
not hypothetical:

- CelesTrak's supplemental GP feed carries 18 SDS nine-digit launch-nominal catalog numbers
  (7995xxxxx) for roughly 5-8 days after each Starlink launch. On 2026-09-21 ~00:12 UTC,
  `https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=starlink&FORMAT=CSV`
  contained 27 records with `NORAD_CAT_ID` 799501621-799501647, and
  `.../sup-gp.php?CATNR=799501621&FORMAT=CSV` returned that object alone. All 27 fail to load.
- CelesTrak's documentation: "18 SPCS is already assigning catalog numbers in their new
  analyst sat range of 7995xxxxx" and "we are already using the 18 SDS 9-digit launch nominals
  catalog numbers (in the 799xxxxxx range)"
  (https://celestrak.org/NORAD/documentation/gp-data-formats.php).
- CCSDS 502.0-B-3, Table 4-3: `NORAD_CAT_ID` is "an integer of up to nine digits".
- Space-Track: OMM formats "are capable of handling object numbers up to 999,999,999"
  (https://www.space-track.org/documentation, Alpha-5 FAQ).

The Alpha-5 ceiling is a property of the fixed-width TLE format, which the OMM formats were
introduced to escape; applying it on OMM ingestion makes the library unable to load the very
data that motivated OMM.

## Minimal standalone reproducer (no network)

The element values below are the OMM example from CCSDS 502.0-B-3 annex G (GOES 9); only
`NORAD_CAT_ID` is replaced by a real nine-digit number published by CelesTrak on 2026-09-21.

```python
from sgp4.api import Satrec
from sgp4 import omm

fields = {
    "OBJECT_NAME": "GOES 9", "OBJECT_ID": "1995-025A",
    "EPOCH": "2020-03-04T10:34:41.426400",
    "MEAN_MOTION": "1.00273272", "ECCENTRICITY": "0.0005013", "INCLINATION": "3.0539",
    "RA_OF_ASC_NODE": "81.7939", "ARG_OF_PERICENTER": "249.2363", "MEAN_ANOMALY": "150.1602",
    "EPHEMERIS_TYPE": "0", "CLASSIFICATION_TYPE": "U",
    "NORAD_CAT_ID": "799501621",          # nine digits: 18 SDS launch nominal, CelesTrak SupGP, 2026-09-21
    "ELEMENT_SET_NO": "925", "REV_AT_EPOCH": "4316",
    "BSTAR": "0.0001", "MEAN_MOTION_DOT": "-0.00000113", "MEAN_MOTION_DDOT": "0.0",
}

sat = Satrec()
omm.initialize(sat, fields)   # ValueError: satellite number cannot exceed 339999, whose Alpha 5 encoding is 'Z9999'
```

Skyfield:

```python
from skyfield.api import EarthSatellite, load
ts = load.timescale(builtin=True)
EarthSatellite.from_omm(ts, fields)   # same ValueError
```

Expected: the record loads and propagates; the catalog number is only informational for SGP4.
Actual: `ValueError` from `sgp4init`.

## Live reproducer (one request; respect CelesTrak's usage policy)

Nominals exist only for about a week after a launch; check
https://celestrak.org/NORAD/elements/supplemental/ for a recent Starlink launch first.
Do not repeat the request more than once per two hours.

```python
import csv, io, urllib.request
from sgp4.api import Satrec
from sgp4 import omm

url = "https://celestrak.org/NORAD/elements/supplemental/sup-gp.php?FILE=starlink&FORMAT=CSV"
req = urllib.request.Request(url, headers={"User-Agent": "sgp4-issue-repro (single request)"})
text = urllib.request.urlopen(req, timeout=60).read().decode()
rows = [r for r in csv.DictReader(io.StringIO(text)) if int(r["NORAD_CAT_ID"]) >= 100_000_000]
print(len(rows), "nine-digit records")           # 27 on 2026-09-21
if rows:
    omm.initialize(Satrec(), rows[0])             # ValueError
```

## Where it comes from

`sgp4init` (both the C++ accelerated and the pure-Python `sgp4.model` paths) stores the
satellite number as a five-character string via the Alpha-5 encoder (`sgp4/alpha5.py`
`to_alpha5`, which raises above 339999). Propagation never needs the string; only
`sgp4.exporter.export_tle` does, and a TLE genuinely cannot carry such a number.

## Suggested direction (for discussion)

Keep the integer catalog number on the `Satrec` (e.g. `satnum` as an int up to 999,999,999)
and raise the Alpha-5 limit only in `export_tle`, where it is real. `satnum_str` could then
be derived on demand for numbers <= 339999 and be `None` (or raise) above.

## Provenance of the claim

Observed with the gp-omm-conformance corpus (private at the time of writing); the 27 records
were fetched once, hashed and inventoried (SHA-256 of the CSV: 762cac2d...). No provider bytes
are reproduced above beyond a catalog number.
