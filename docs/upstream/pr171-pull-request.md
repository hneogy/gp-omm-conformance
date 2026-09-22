# Pull request for python-sgp4 #171: opened as PR #172

Status: **opened 2026-09-21 from the owner's account with the owner's approval (D-094):**
https://github.com/brandon-rhodes/python-sgp4/pull/172, `hneogy:omm-empty-object-id` (commit `d281247` on
upstream master `bf25b00`) into `brandon-rhodes:master`, title and description exactly as below. Prepared
under D-092/D-093. Everything below the rule is the posted text.
---

**Title:** Accept an empty or `UNKNOWN` OBJECT_ID in `sgp4.omm`

Fixes #171

CelesTrak's OMM XML for analyst objects has an empty `<OBJECT_ID></OBJECT_ID>`. ElementTree gives `None`
for the empty element, `parse_xml()` passes it through, and `initialize()` raises `TypeError` on
`fields['OBJECT_ID'][2:]`. The same records in CSV, where the value is `''`, load fine.

What changed:

- `parse_xml()` stores an empty element as `''`, so an empty `OBJECT_ID` (or `OBJECT_NAME`) arrives the
  same way from XML as from CSV.
- `initialize()` derives `intldesg` only from an `OBJECT_ID` of the form `YYYY-NNNP...`; otherwise it
  sets `''`. That also covers the CCSDS-recommended literal `UNKNOWN`, which used to produce
  `intldesg == 'KNOWN'`.

Tests: `test_omm_xml_with_empty_object_id` and `test_omm_unknown_object_id` in `sgp4/tests.py`, next to
the other OMM tests. Both fail on master and pass with the change.

Verified with `python -m sgp4.tests` on Python 3.14 (macOS): 47 tests pass on both the pure-Python build
(`PYTHON_SGP4_COMPILE=never`) and the compiled C++ build; the README doctests pass too.
