# Draft note: `sgp4.omm.initialize` sets `classification` and then `sgp4init` resets it to `U`

Status: draft, low severity, not yet filed. Target: brandon-rhodes/python-sgp4. Found while
running the corpus; recorded because it silently alters a field.

## Environment

- python-sgp4 2.27, Python 3.14.4 (observed 2026-09-21); both the accelerated and the
  pure-Python `Satrec`.

## Summary

`sgp4.omm.initialize` does `sat.classification = fields['CLASSIFICATION_TYPE']` and then calls
`sat.sgp4init(...)`, which (re)initialises the object and leaves `classification == 'U'`. Any
non-`U` value in an OMM record is lost. CelesTrak supplemental GP records carry
`CLASSIFICATION_TYPE` `C` (CelesTrak's documented marker for supplemental data), so a program
that uses the field to tell supplemental from 18 SDS data sees `U` for both.
`Satrec.twoline2rv` preserves the letter from a TLE.

## Minimal standalone reproducer (no network)

```python
from sgp4.api import Satrec
from sgp4 import omm

fields = {  # CCSDS 502.0-B-3 annex G example values; classification set to 'C' as CelesTrak SupGP does
    "OBJECT_NAME": "GOES 9", "OBJECT_ID": "1995-025A", "EPOCH": "2020-03-04T10:34:41.426400",
    "MEAN_MOTION": "1.00273272", "ECCENTRICITY": "0.0005013", "INCLINATION": "3.0539",
    "RA_OF_ASC_NODE": "81.7939", "ARG_OF_PERICENTER": "249.2363", "MEAN_ANOMALY": "150.1602",
    "EPHEMERIS_TYPE": "0", "CLASSIFICATION_TYPE": "C", "NORAD_CAT_ID": "23581",
    "ELEMENT_SET_NO": "925", "REV_AT_EPOCH": "4316", "BSTAR": "0.0001",
    "MEAN_MOTION_DOT": "-0.00000113", "MEAN_MOTION_DDOT": "0.0",
}
sat = Satrec()
omm.initialize(sat, fields)
print(sat.classification)   # 'U'  (expected 'C')
```

## Suggested direction

Assign `classification` (and any other descriptive attributes) after `sgp4init`, or make
`sgp4init` leave them untouched.
