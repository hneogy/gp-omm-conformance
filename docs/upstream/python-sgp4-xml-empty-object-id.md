# Draft bug report: `sgp4.omm.parse_xml` + `initialize` raise `TypeError` on an empty `<OBJECT_ID/>` (CelesTrak analyst objects)

Status: draft, not yet filed. Target: brandon-rhodes/python-sgp4.

## Environment

- python-sgp4 2.27, Python 3.14.4, macOS (observed 2026-09-21)

## Summary

CelesTrak's OMM XML for analyst objects (objects with no international designator) writes an
empty element `<OBJECT_ID></OBJECT_ID>`. `sgp4.omm.parse_xml` copies `element.text`, which
`xml.etree.ElementTree` returns as `None` for an empty element, and `sgp4.omm.initialize`
then evaluates `fields['OBJECT_ID'][2:]`:

```
TypeError: 'NoneType' object is not subscriptable
```

Scale, from live data on 2026-09-21: `https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=XML`
held 565 records, 563 of them with an empty `OBJECT_ID`; **563 of 565 records cannot be
loaded through the XML path**, while the identical records fetched as CSV
(`...&FORMAT=CSV`, where the empty field is the empty string `''`) load without error.
The first-ever record for analyst id 270449 (`gp-first.php?CATNR=270449&FORMAT=XML`) fails
the same way.

CelesTrak documents the behaviour: "an object in the current analyst sat range (80000-series)
typically will not have a name (OBJECT_NAME) or International Designator (OBJECT_ID)" and
"Some elements may be blank (KVN) or null (XML)"
(https://celestrak.org/NORAD/documentation/gp-data-formats.php). Space-Track defines analyst
objects as tracked "with insufficient fidelity for publication in the public satellite
catalog" (https://www.space-track.org/documentation). Note that CCSDS 502.0-B-3 Table 4-2
recommends the literal `UNKNOWN` for an unknown `OBJECT_ID`; CelesTrak emits an empty element
instead, so parsers meet both.

## Minimal standalone reproducer (no network)

Element values are the CCSDS 502.0-B-3 annex G example; the document shape (an `<ndm>`
wrapper, OMM version 2.0, empty header elements, empty `OBJECT_ID`) is CelesTrak's.

```python
import io
from sgp4.api import Satrec
from sgp4 import omm

xml = """<?xml version="1.0" encoding="UTF-8"?>
<ndm xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="https://sanaregistry.org/r/ndmxml_unqualified/ndmxml-2.0.0-master-2.0.xsd">
<omm id="CCSDS_OMM_VERS" version="2.0">
<header><CREATION_DATE/><ORIGINATOR/></header><body><segment><metadata><OBJECT_NAME>UNKNOWN</OBJECT_NAME><OBJECT_ID></OBJECT_ID><CENTER_NAME>EARTH</CENTER_NAME><REF_FRAME>TEME</REF_FRAME><TIME_SYSTEM>UTC</TIME_SYSTEM><MEAN_ELEMENT_THEORY>SGP4</MEAN_ELEMENT_THEORY></metadata><data><meanElements><EPOCH>2020-03-04T10:34:41.426400</EPOCH><MEAN_MOTION>1.00273272</MEAN_MOTION><ECCENTRICITY>.0005013</ECCENTRICITY><INCLINATION>3.0539</INCLINATION><RA_OF_ASC_NODE>81.7939</RA_OF_ASC_NODE><ARG_OF_PERICENTER>249.2363</ARG_OF_PERICENTER><MEAN_ANOMALY>150.1602</MEAN_ANOMALY></meanElements><tleParameters><EPHEMERIS_TYPE>0</EPHEMERIS_TYPE><CLASSIFICATION_TYPE>U</CLASSIFICATION_TYPE><NORAD_CAT_ID>81011</NORAD_CAT_ID><ELEMENT_SET_NO>999</ELEMENT_SET_NO><REV_AT_EPOCH>4316</REV_AT_EPOCH><BSTAR>.1E-3</BSTAR><MEAN_MOTION_DOT>-.113E-5</MEAN_MOTION_DOT><MEAN_MOTION_DDOT>0</MEAN_MOTION_DDOT></tleParameters></data></segment></body></omm>
</ndm>
"""

fields = next(omm.parse_xml(io.StringIO(xml)))
print(repr(fields["OBJECT_ID"]))     # None
omm.initialize(Satrec(), fields)     # TypeError: 'NoneType' object is not subscriptable
```

Expected: the record loads with an empty international designator (`intldesg == ''`), as it
does from CSV. Actual: `TypeError`.

## Live reproducer (one request; respect CelesTrak's usage policy)

```python
import io, urllib.request
from sgp4.api import Satrec
from sgp4 import omm

url = "https://celestrak.org/NORAD/elements/gp.php?GROUP=analyst&FORMAT=XML"
req = urllib.request.Request(url, headers={"User-Agent": "sgp4-issue-repro (single request)"})
text = urllib.request.urlopen(req, timeout=60).read().decode()
ok = bad = 0
for fields in omm.parse_xml(io.StringIO(text)):
    try:
        omm.initialize(Satrec(), fields); ok += 1
    except TypeError:
        bad += 1
print(ok, "loaded;", bad, "TypeError")    # 2 loaded; 563 TypeError on 2026-09-21
```

## Suggested fix, and an offer

In `parse_xml`, use `(field.text or '')`; in `initialize`, derive `intldesg` only from an
`OBJECT_ID` of the form `YYYY-NNNP...` and otherwise set it to `''` (this also covers the
CCSDS-recommended literal `UNKNOWN`, which today yields `intldesg == 'KNOWN'`). The same guard
applies to `OBJECT_NAME`, which the provider says can also be blank.

I have a patch ready with two tests (`test_omm_xml_with_empty_object_id`,
`test_omm_unknown_object_id`) in the style of `sgp4/tests.py`; it applies cleanly to master
and the existing test module still passes with it. Happy to open a pull request if that is
welcome, or to adjust the approach if you would rather handle it differently.

(Prepared, not yet submitted: `docs/upstream/patches/0001-omm-tolerate-empty-or-UNKNOWN-OBJECT_ID.patch`
in the gp-omm-conformance repository.)
