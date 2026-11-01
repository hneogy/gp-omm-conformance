#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""
gpconf/reference.py -- reference readers for GP data in TLE, CSV, JSON, XML and KVN.

Standard library only. Also imported by tools/gpref.py (shim).

Written from the format documents, not from any library (CelesTrak TLE column table,
CCSDS 502.0-B-3 sections 4 and 7, CCSDS 505.0-B-3 / SANA schemas). Used only to *produce*
expected values; python-sgp4 and Skyfield are used separately to cross-check them.

Numbers are carried as decimal text (Python Decimal), never as binary floats, and are
rendered in plain notation ('0.00015975118', not '.15975118E-3' or 1.5975118e-04).
"""
import csv
import datetime as dt
import io
import json
import numbers
import os
import re
import sys
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_EVEN

from .tle import from_alpha5, checksum, epoch_text, iso_epoch
from .words import qty

OMM_HEADER = ["CCSDS_OMM_VERS", "COMMENT", "CLASSIFICATION", "CREATION_DATE", "ORIGINATOR", "MESSAGE_ID"]
OMM_META = ["OBJECT_NAME", "OBJECT_ID", "CENTER_NAME", "REF_FRAME", "REF_FRAME_EPOCH", "TIME_SYSTEM", "MEAN_ELEMENT_THEORY"]
OMM_MEAN = ["EPOCH", "SEMI_MAJOR_AXIS", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE",
            "ARG_OF_PERICENTER", "MEAN_ANOMALY", "GM"]
OMM_SC = ["MASS", "SOLAR_RAD_AREA", "SOLAR_RAD_COEFF", "DRAG_AREA", "DRAG_COEFF"]
OMM_TLEP = ["EPHEMERIS_TYPE", "CLASSIFICATION_TYPE", "NORAD_CAT_ID", "ELEMENT_SET_NO", "REV_AT_EPOCH", "BSTAR",
            "BTERM", "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT", "AGOM"]
OMM_KEYWORDS = set(OMM_HEADER + OMM_META + OMM_MEAN + OMM_SC + OMM_TLEP)
MANDATORY_META = ["OBJECT_NAME", "OBJECT_ID", "CENTER_NAME", "REF_FRAME", "TIME_SYSTEM", "MEAN_ELEMENT_THEORY"]
CELESTRAK_CSV_JSON_KEYS = ["OBJECT_NAME", "OBJECT_ID", "EPOCH", "MEAN_MOTION", "ECCENTRICITY", "INCLINATION",
                           "RA_OF_ASC_NODE", "ARG_OF_PERICENTER", "MEAN_ANOMALY", "EPHEMERIS_TYPE",
                           "CLASSIFICATION_TYPE", "NORAD_CAT_ID", "ELEMENT_SET_NO", "REV_AT_EPOCH", "BSTAR",
                           "MEAN_MOTION_DOT", "MEAN_MOTION_DDOT"]

DECIMAL_KEYS = {"MEAN_MOTION": "mean_motion", "ECCENTRICITY": "eccentricity", "INCLINATION": "inclination",
                "RA_OF_ASC_NODE": "ra_of_asc_node", "ARG_OF_PERICENTER": "arg_of_pericenter",
                "MEAN_ANOMALY": "mean_anomaly", "BSTAR": "bstar", "MEAN_MOTION_DOT": "mean_motion_dot",
                "MEAN_MOTION_DDOT": "mean_motion_ddot", "SEMI_MAJOR_AXIS": "semi_major_axis", "GM": "gm",
                "BTERM": "bterm", "AGOM": "agom"}
INT_KEYS = {"NORAD_CAT_ID": "norad_cat_id", "EPHEMERIS_TYPE": "ephemeris_type", "ELEMENT_SET_NO": "element_set_no",
            "REV_AT_EPOCH": "rev_at_epoch"}
TEXT_KEYS = {"OBJECT_NAME": "object_name", "OBJECT_ID": "object_id", "CENTER_NAME": "center_name",
             "REF_FRAME": "ref_frame", "TIME_SYSTEM": "time_system", "MEAN_ELEMENT_THEORY": "mean_element_theory",
             "CLASSIFICATION_TYPE": "classification_type", "EPOCH": "epoch", "REF_FRAME_EPOCH": "ref_frame_epoch",
             "CCSDS_OMM_VERS": "ccsds_omm_vers", "CREATION_DATE": "creation_date", "ORIGINATOR": "originator",
             "MESSAGE_ID": "message_id", "CLASSIFICATION": "classification"}


# What a number in a provider's file may look like, as the reference reads it (D-336): the grammar a parser's answer is
# held to (D-319), an optional sign, ASCII digits with an optional point and an optional exponent, once the format's own
# padding is taken off: a TLE column's blanks, XML whitespace around a number (the schema's numbers are xsd:double and
# xsd:integer, whose whitespace rule is "collapse"), and nothing in CSV or JSON, where a space is part of the value. The
# KVN reader takes the whitespace around a value off with its line (CCSDS 502.0-B-3 7.4.5-7.4.7), ASCII whitespace only.
# Decimal() and int() read far more: underscores between digits, the digits of other scripts, Unicode spaces, NaN and
# Infinity. The reference is the oracle, so it reads no more generously from a file than from a parser.
PLAIN_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
PLAIN_INTEGER = re.compile(r"[+-]?[0-9]+")
TLE_PAD, XML_PAD = " ", " \t\r\n"
# The longest plain form a number may take, in digits on either side of the point: Python's own limit on the digits of
# an integer read from text (sys.int_info.default_max_str_digits). A number written with a larger exponent,
# '1E9999999999', was expanded in full, ten billion digits, until memory ran out, and one with an exponent past what
# Decimal() holds raised decimal.InvalidOperation, no ValueError, which the runner and check-tle took for a fault of the
# corpus (D-336);
# no OMM value comes near the bound, the largest a semi-major axis in km and the smallest a second derivative near 1E-13.
PLAIN_DIGITS = 4300


class NotPlain(ValueError):
    """A number in a file that is not written as one (D-336); the TLE reader words it as before, "is not a number"."""


def plain(value, pad=""):
    """Decimal text/number -> plain decimal string without exponent; None/'' -> None. `pad` is the format's padding,
    taken off text first. Text outside PLAIN_NUMBER, and a Decimal that is not finite, raise NotPlain (D-336)."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise NotPlain(f"{value!r} is not a finite number")
        d = value
    else:
        s = str(value).strip(pad)
        if s == "":
            return None
        if not PLAIN_NUMBER.fullmatch(s):
            raise NotPlain(f"{s!r} is not a plain decimal number (ASCII digits, an optional sign, point and exponent)")
        try:
            d = Decimal(s)
        except ArithmeticError:   # an exponent past what Decimal() holds: decimal.InvalidOperation, which is no ValueError
            raise NotPlain(f"{s[:40]!r} has an exponent past what any value needs") from None
    if not d:
        return "0"   # a zero, whatever exponent Decimal() holds
    if d.adjusted() >= PLAIN_DIGITS or len(d.as_tuple().digits) - d.adjusted() - 1 > PLAIN_DIGITS:   # digits before the point, after it
        shown = str(d) if isinstance(value, Decimal) else s
        raise NotPlain(f"{shown[:40]!r} holds more than any value needs: written out, it runs past {PLAIN_DIGITS} digits on one side of the point")
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".") or "0"
    if s in ("-0", ""):
        s = "0"
    return s


def plain_int(value, pad=""):
    """An integer field's value -> int. An int (JSON's own integers) is taken as it is, a bool is not one; text is ASCII
    digits with an optional sign once `pad` is taken off; anything else raises NotPlain (D-336). int() read underscores,
    other scripts' digits and whitespace of any kind around them."""
    if isinstance(value, bool):
        raise NotPlain(f"{value!r} is not an integer")
    if isinstance(value, int):
        return value
    s = str(value).strip(pad)
    if not PLAIN_INTEGER.fullmatch(s):
        raise NotPlain(f"{s!r} is not an integer (ASCII digits with an optional sign)")
    if len(s.lstrip("+-")) > PLAIN_DIGITS:   # int() refuses it with advice to whoever runs Python, not to the user
        raise NotPlain(f"{s[:40]!r} holds more digits than any integer needs: more than {PLAIN_DIGITS}")
    return int(s)


def text_lines(text):
    """A TLE or KVN file's lines, split at CR, LF and CRLF only. str.splitlines() also split at a form feed, a vertical
    tab, the file, group and record separators, NEL and the Unicode line and paragraph separators, so a KVN value with
    one inside it was read as the digits before it and a TLE line with one inside it was passed over (D-336). KVN's
    fourth terminator, LFCR (CCSDS 502.0-B-3 7.3.7), reads as an empty line, which means nothing there (7.3.5)."""
    lines = re.split(r"\r\n|\r|\n", text)
    return lines[:-1] if lines and lines[-1] == "" else lines


TLE_PAGE = "\x0c\x0b"   # a form feed or a vertical tab: a printer's page break, which older listings carry between sets


def tle_lines(text):
    """A TLE file's lines (text_lines), with what older files carry around their sets taken off, none of which changes a
    value: the padding at a file's end that begins with a DOS end-of-file mark or a NUL (XMODEM filled a file's last
    block with the mark) and holds nothing but those and line ends; a run of CRs before an LF, one line end (CR CR LF
    is CRLF text written again in Windows' text mode); a page break at the start of a line; and a line of nothing but
    blanks, tabs and page breaks, which reads as a blank line (D-336, the sixth and seventh readings: a DOS-era file or a
    saved copy whose every set is valid was refused whole). Inside a line each is still refused, and a blank line inside
    a set too, but for a mark or a NUL that ends the file's last line, which goes with the padding; a file of nothing but
    padding reads as an empty one."""
    # by string operations and a look-behind, not a pattern tried at every byte of a run: that took time growing with
    # the square of a run of NULs, DOS marks or CRs that is not at the file's end (the eighth reading)
    end = len(text.rstrip("\x1a\x00\r\n"))
    k = next((i for i in range(end, len(text)) if text[i] in "\x1a\x00"), None)
    if k is not None:
        text = text[:k]
    text = re.sub(r"(?<!\r)\r+\n", "\n", text)
    return ["" if not l.strip(" \t" + TLE_PAGE) else l.lstrip(TLE_PAGE) for l in text_lines(text)]


def line_endings(raw: bytes):
    crlf = raw.count(b"\r\n")
    return {"crlf": crlf, "lf": raw.count(b"\n") - crlf, "bom": raw.startswith(b"\xef\xbb\xbf")}


# --------------------------------------------------------------------------- canonical record
def canonical_from_fields(fields, presence, fmt):
    """fields: OMM keyword -> text (str) or Decimal/int for JSON; presence: keyword -> 'value'|'empty'|'null'|'absent'."""
    rec = {}
    pad = XML_PAD if fmt == "xml" else ""
    if fmt == "xml" and isinstance(fields.get("EPOCH"), str):
        # the NDM/XML epochType allows a point with no digits after it; the epoch reader does not (D-336)
        fields = dict(fields, EPOCH=re.sub(r"(:[0-9]{2})\.(?=(?:Z|[+-][0-9]{2}:[0-9]{2})?$)", r"\1", fields["EPOCH"]))
    for k, name in TEXT_KEYS.items():
        v = fields.get(k)
        rec[name] = (str(v) if v is not None and str(v) != "" else None) if presence.get(k) in ("value", "empty", "null") else None
    try:
        for k, name in INT_KEYS.items():
            v = fields.get(k)
            rec[name] = plain_int(v, pad) if v not in (None, "") else None
        for k, name in DECIMAL_KEYS.items():
            v = fields.get(k)
            rec[name] = plain(v, pad) if v not in (None, "") else None
        if rec["epoch"] is not None:
            # held to a parser's rule (D-319, D-325): the epoch is the epoch and nothing around it, in a form the epoch
            # reader reads (an XML epoch is a pattern on xsd:string, whose whitespace is kept, so padding is invalid there too)
            k = "EPOCH"
            if rec["epoch"] != rec["epoch"].strip():
                raise NotPlain(f"{rec['epoch']!r} has whitespace around it")
            if fmt != "xml" and re.search(r"[+-][0-9]{2}:[0-9]{2}$", rec["epoch"]):
                # 7.5.10 gives a UTC epoch, with an optional Z; the NDM/XML epochType alone allows an offset (D-336)
                raise NotPlain(f"{rec['epoch']!r} carries an offset from UTC, which 502.0-B-3 7.5.10 does not allow here")
            iso_epoch(rec["epoch"])
    except (ValueError, OverflowError) as e:   # OverflowError: an epoch past the years a datetime holds, as in norm_epoch
        raise NotPlain(f"{k}: {e}") from None
    rec["extra"] = {k: (str(v) if v is not None else None) for k, v in fields.items() if k not in OMM_KEYWORDS}
    rec["presence"] = {k: presence[k] for k in sorted(presence)}
    rec["source_format"] = fmt
    return rec


# --------------------------------------------------------------------------- TLE
TLE_YEAR_PIVOT = 57  # two-digit years 57-99 -> 1957-1999, 00-56 -> 2000-2056 (CelesTrak, Satellite Times Jan 1998)


def two_digit_year(yy):
    # two digits, 00 to 99 (D-325): int() made -1 into 1999 and 100 into 2000. Text is the TLE's own field, so it is two
    # ASCII digits; an integer is 0 to 99, and a bool is not one
    if isinstance(yy, str):
        if not (len(yy) == 2 and yy.isascii() and yy.isdigit()):
            raise ValueError(f"two-digit year {yy!r} is not two digits")
    elif isinstance(yy, bool) or not isinstance(yy, numbers.Integral):   # any integer type, as the runner's (D-295)
        raise ValueError(f"two-digit year {yy!r} ({type(yy).__name__}) is neither two digits nor an integer")
    yy = int(yy)
    if not 0 <= yy <= 99:
        raise ValueError(f"two-digit year {yy} is outside 00 to 99")
    return yy + 1900 if yy >= TLE_YEAR_PIVOT else yy + 2000


def tle_epoch_to_iso(field):
    """'26263.52959654' -> '2026-09-20T12:42:37.141056' (microsecond resolution, exact for 8-decimal days)."""
    yy, rest = field[:2], field[2:]
    if not re.fullmatch(r"[0-9]{3}(?:\.[0-9]*)?", rest):   # three ASCII digits, then the fraction; Decimal read blanks around it too (D-336)
        raise NotPlain(f"TLE epoch day {rest!r} is not DDD.DDDDDDDD")
    day = Decimal(rest)
    doy = int(day)
    year = two_digit_year(yy)
    days_in_year = 366 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 365
    if not 1 <= doy <= days_in_year:  # day 000 used to land in the previous year and 367 in the next, silently (D-117)
        raise ValueError(f"TLE epoch day of year {doy:03d} is outside 001..{days_in_year} for {year}")
    frac = day - doy
    us = (frac * Decimal(86_400_000_000)).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
    base = dt.datetime(year, 1, 1) + dt.timedelta(days=doy - 1, microseconds=int(us))
    return epoch_text(base)


def tle_exp_to_plain(field):
    f = field.strip(TLE_PAD)
    if not f:
        return None
    if not (TLE_EXPONENT.fullmatch(field) or (len(field) != 8 and re.fullmatch(r"[+-]?[0-9]+[+-][0-9]", f))):
        # in a TLE line the field is eight columns: a sign or a blank, five digits, the exponent's sign and digit, so a
        # value written one column over is refused, not read with its sign lost (D-336); the runner's own exp_field
        # text is read the same way
        raise NotPlain(f"TLE exponent field {field!r} is not a sign, five digits and a signed exponent")
    sign = "-" if f[0] == "-" else ""
    body = f.lstrip("+-")
    mant, exp = body[:-2], body[-2:]
    if not (re.fullmatch(r"[0-9]+", mant) and re.fullmatch(r"[+-][0-9]", exp)):   # ASCII mantissa, signed exponent (D-336)
        raise NotPlain(f"TLE exponent field {field!r} is not digits with a signed one-digit exponent")
    return plain(Decimal(f"{sign}0.{mant}E{exp}"))


def intl_designator_to_object_id(field):
    f = field.rstrip()
    if not f.strip():
        return None
    yy, launch, piece = f[0:2], f[2:5], f[5:8].strip()
    return f"{two_digit_year(yy)}-{launch}{piece}"


def tle_number(fn, field, what):
    """A numeric TLE column read by fn; a letter or stray character in it is a ValueError naming the field. Decimal
    raises decimal.InvalidOperation there, which is not a ValueError, so the runner used to report a malformed
    provider line as an internal error of the corpus (D-117, D-171)."""
    try:
        return fn(field)
    except (ArithmeticError, NotPlain):   # NotPlain: underscores, other scripts' digits, odd blanks (D-336)
        raise ValueError(f"TLE {what} field {field!r} is not a number") from None


TLE_FIXED = re.compile(r"[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+)")   # a fixed-point column: no exponent, as the format writes it
TLE_UNSIGNED = re.compile(r"(?:[0-9]+\.[0-9]*|\.[0-9]+)")        # the angles and the mean motion carry no sign
TLE_EXPONENT = re.compile(r"[ +-][0-9]{5}[+-][0-9]")             # BSTAR and the second derivative: sign, five digits, exponent
TLE_SEPARATORS = {1: (1, 8, 17, 32, 43, 52, 61, 63), 2: (1, 7, 16, 25, 33, 42, 51)}   # the blank columns between fields
TLE_LINE = re.compile(r"[\x20-\x7e]*")                         # a TLE line is printable ASCII
TLE_ELEMENT_START = re.compile(r"[12].[0-9A-Z][0-9]{4}")         # a line meant as an element line, whatever is in column 2
TLE_COLUMNS = {1: [((2, 7), "catalog number"), ((7, 8), "classification"), ((9, 17), "international designator"),
                   ((18, 32), "epoch"), ((33, 43), "first derivative"), ((44, 52), "second derivative"), ((53, 61), "BSTAR"),
                   ((62, 63), "ephemeris type"), ((64, 68), "element set number"), ((68, 69), "checksum")],
               2: [((2, 7), "catalog number"), ((8, 16), "inclination"), ((17, 25), "right ascension"), ((26, 33), "eccentricity"),
                   ((34, 42), "argument of perigee"), ((43, 51), "mean anomaly"), ((52, 63), "mean motion"),
                   ((63, 68), "revolution number"), ((68, 69), "checksum")]}


def _column(f):
    if not TLE_FIXED.fullmatch(f.strip(TLE_PAD)):
        raise NotPlain(f"{f!r} is not a fixed-point number")
    return plain(f, TLE_PAD)


def _unsigned(f):
    if not TLE_UNSIGNED.fullmatch(f.strip(TLE_PAD)):
        raise NotPlain(f"{f!r} is not an unsigned fixed-point number")
    return plain(f, TLE_PAD)


def _digits(f):
    if not re.fullmatch(r"[0-9]+", f.strip(TLE_PAD)):
        raise NotPlain(f"{f!r} is not digits")
    return int(f.strip(TLE_PAD))


def _eccentricity(f):
    if not re.fullmatch(r"[0-9]{7}", f):   # seven ASCII digits after an implied point, nothing else (D-336)
        raise NotPlain(f"{f!r} is not seven digits")
    return plain("0." + f)


def _column_int(f):
    return plain_int(f, TLE_PAD)


def _object_id(field, written):
    """The designator as an OBJECT_ID; on lines a writer wrote one that is not a designator ("UNKNOWN ") is none,
    since the writer contract reports the designator and never fails it (D-336)."""
    try:
        return intl_designator_to_object_id(field)
    except ValueError:
        if written:
            return None
        raise


CARD = 80   # a punched card's columns: an element line kept as a card image is blank from column 70 to 80


def card_image(n, line):
    """A provider's element line kept as an 80-column card image -> the line: blanks past column 69, up to column 80,
    are the card's padding, no part of the line, and are taken off; any other character past column 69, or a line
    past column 80, is refused in words (the owner's ruling, D-338). A card blank in column 69, its checksum, is refused:
    a line cut short and padded gave the cut element set or revolution number as the value (the reading of D-338), and
    a whole card whose checksum was never written is refused with it, the safer of the two (the second reading). Lines
    a writer wrote are not read through it."""
    if len(line) <= 69:
        return line
    tail = line[69:]
    odd = next((i for i, c in enumerate(tail) if c != " "), None)
    if odd is not None:
        raise ValueError(f"TLE line {n} is {len(line)} columns; past column 69 only blanks may follow, and column {70 + odd} holds {tail[odd]!r}")
    if len(line) > CARD:
        raise ValueError(f"TLE line {n} is {len(line)} columns, blank past column 69 but past column {CARD} too, where a card image ends")
    if line[68] == " ":
        raise ValueError(f"TLE line {n} is blank in column 69, its checksum, and blank past it: a line cut short, or one whose checksum was never written, "
                         "and no card image to read")
    return line[:69]


def _printable(n, line):
    if not TLE_LINE.fullmatch(line):   # a no-break space in a separator column, another script's digit in the designator (D-336)
        col = next(i for i, c in enumerate(line) if not TLE_LINE.fullmatch(c))
        for (a, b), what in TLE_COLUMNS[n]:
            if a <= col < b:
                raise ValueError(f"TLE {what} field {line[a:b]!r} is not a number" if what not in
                                 ("classification", "international designator") else
                                 f"TLE {what} field {line[a:b]!r} holds {line[col]!r}, which is not printable ASCII")
        raise ValueError(f"TLE line {n} holds {line[col]!r} in column {col + 1}, which is not printable ASCII")


def parse_tle_lines(l0, l1, l2, strict=True, written=False):
    if not written:
        # a character no TLE holds is named in its field first, then an 80-column card image's blanks past column 69 are
        # taken off (D-338); before, a form feed in column 31 of a 70-column line read as a fault in column 70
        for n, line in ((1, l1), (2, l2)):
            _printable(n, line)
        l1, l2 = card_image(1, l1), card_image(2, l2)
    if strict and (len(l1) != 69 or len(l2) != 69):
        raise ValueError(f"line length {len(l1)}/{len(l2)} != 69")
    if not written:
        # a right-justified element set or revolution number never leaves its last column blank: a provider line blank
        # in column 68 was cut inside that number and padded, and read the cut number (292 as 29), so it is refused (the
        # owner's ruling on D-338's second reading, D-341); a card blank in column 69 is refused in card_image
        for n, line, what in ((1, l1, "element set number"), (2, l2, "revolution number")):
            if len(line) == 69 and line[67] == " ":
                raise ValueError(f"TLE line {n} is blank in column 68, the last digit of its {what}: a line cut short "
                                 "inside that number, which is right-justified and never ends in a blank")
    for n, line in ((1, l1), (2, l2)):
        _printable(n, line)
        for i in TLE_SEPARATORS[n]:   # a value written over the blank between two fields was read as its neighbour's
            if i < len(line) and line[i] != " ":
                raise ValueError(f"TLE line {n} column {i + 1}, the blank between two fields, holds {line[i]!r}")
    if strict and l2[2:7] != l1[2:7]:   # line 2 carries the catalog number again; it was never read
        raise ValueError(f"TLE line 2's catalog field {l2[2:7]!r} is not line 1's {l1[2:7]!r}")
    cat_field = l1[2:7]
    # a provider's name line is printable ASCII and its designator a year, a launch number and a piece, or blank (D-336);
    # lines a writer wrote (written=True) report both for information only, as the writer case and check-tle always have
    if not written and l0 is not None and not TLE_LINE.fullmatch(l0):
        raise ValueError(f"TLE name line {l0[:40]!r} is not printable ASCII")
    if not written and not re.fullmatch(r"(?:[0-9]{5}[A-Z]{1,3})? *", l1[9:17]):
        raise ValueError(f"TLE international designator field {l1[9:17]!r} is not a year, a launch number and a piece")
    name = l0.strip(TLE_PAD) if l0 is not None else ""
    if name.startswith("0 "):   # Space-Track's three-line form numbers its name line 0 (D-336)
        name = name[2:].strip(TLE_PAD)
    rec = {
        "norad_cat_id": from_alpha5(cat_field),
        "object_name": name or None,
        "object_id": _object_id(l1[9:17], written),
        "epoch": tle_number(tle_epoch_to_iso, l1[18:32], "epoch"),
        "mean_motion": tle_number(_unsigned, l2[52:63], "mean motion"),
        "eccentricity": tle_number(_eccentricity, l2[26:33], "eccentricity"),
        "inclination": tle_number(_unsigned, l2[8:16], "inclination"), "ra_of_asc_node": tle_number(_unsigned, l2[17:25], "right ascension"),
        "arg_of_pericenter": tle_number(_unsigned, l2[34:42], "argument of perigee"), "mean_anomaly": tle_number(_unsigned, l2[43:51], "mean anomaly"),
        "bstar": tle_number(tle_exp_to_plain, l1[53:61], "BSTAR"),
        "mean_motion_dot": tle_number(_column, l1[33:43], "first derivative"),
        "mean_motion_ddot": tle_number(tle_exp_to_plain, l1[44:52], "second derivative"),
        "ephemeris_type": tle_number(_digits, l1[62], "ephemeris type") if l1[62] != " " else 0,
        "classification_type": l1[7] if l1[7] != " " else None,   # a blank column is its padding, no value (D-336)
        "element_set_no": tle_number(_digits, l1[64:68], "element set number"),
        "rev_at_epoch": tle_number(_digits, l2[63:68], "revolution number"),
        "center_name": None, "ref_frame": None, "time_system": None, "mean_element_theory": None,
        "ccsds_omm_vers": None, "creation_date": None, "originator": None,
        "extra": {}, "source_format": "tle",
        "tle": {
            "line0": l0, "line1": l1, "line2": l2,
            "catalog_field": cat_field, "catalog_field_is_alpha5": cat_field[0].isalpha(),
            "intl_designator_field": l1[9:17], "epoch_field": l1[18:32], "two_digit_year": l1[18:20],
            "ndot_field": l1[33:43], "nddot_field": l1[44:52], "bstar_field": l1[53:61],
            "ephemeris_type_field": l1[62], "element_set_field": l1[64:68],
            "ecc_field": l2[26:33], "rev_field": l2[63:68],
            "checksum_written": [l1[68], l2[68]], "checksum_computed": [checksum(l1), checksum(l2)],
            "checksums_valid": l1[68] == str(checksum(l1)) and l2[68] == str(checksum(l2)),
            "line_lengths": [len(l0) if l0 is not None else None, len(l1), len(l2)],
        },
    }
    rec["presence"] = {"OBJECT_NAME": "value" if rec["object_name"] else "empty",
                       "OBJECT_ID": "value" if rec["object_id"] else "empty"}
    return rec


def element_line(line):
    """'1' or '2' when a line is meant as a TLE element line, else None: one that begins "1 " or "2 " after any
    whitespace and is longer than a name (24 characters, trailing blanks apart), or one that begins with the line
    number, any one character and a catalog field.
    The reader and the control adapter's tle_sets both use it (D-336). No name in the corpus's SATCAT file begins
    this way."""
    s = line.lstrip()
    if s[:2] in ("1 ", "2 ") and len(s.rstrip()) > 24:   # a name is 24 characters at most, so "1 SATELLITE" stays one
        return s[0]
    if TLE_ELEMENT_START.match(line):   # the line number, any one character, a catalog field's first five (D-336)
        return line[0]
    return None


def _pairs_at(lines, i):
    """True when lines[i] is a line 1 in column 1 and lines[i + 1] a line 2 in column 1: a set to read."""
    return (i + 1 < len(lines) and element_line(lines[i]) == "1" and lines[i][:1] == "1"
            and element_line(lines[i + 1]) == "2" and lines[i + 1][:1] == "2")


def read_tle_text(text):
    lines = tle_lines(text)
    recs = []
    i = 0
    while i < len(lines):
        l = lines[i]
        if _pairs_at(lines, i):
            l0 = lines[i - 1] if i > 0 and element_line(lines[i - 1]) is None else None
            recs.append(parse_tle_lines(l0, l, lines[i + 1]))
            i += 2
            continue
        if element_line(l):
            # a line 1 with no line 2 after it (a blank line between, LFCR ends), a line 2 alone, or an element line set
            # in from column 1: passed over without a word, so a set went missing from the oracle (D-336); the control
            # adapter refuses each the same way (D-171)
            raise ValueError(f"TLE line {i + 1} is an element line that pairs with nothing: {l[:40]!r}")
        if not TLE_LINE.fullmatch(l) and not _pairs_at(lines, i + 1):
            # a stray line with a character no TLE holds, an invisible one before a line number, say; a name line is
            # checked with its set (D-336)
            raise ValueError(f"TLE line {i + 1} holds a character that is not printable ASCII: {l[:40]!r}")
        i += 1
    return recs


# --------------------------------------------------------------------------- CSV / JSON
def read_csv_text(text):
    reader = csv.DictReader(io.StringIO(text))
    try:   # the header is read here, so a header the csv module cannot read is refused here too
        header = reader.fieldnames or []
        all_rows = list(reader)
    except csv.Error as err:   # a field past the csv module's limit, say: a file it cannot read, not a fault of the corpus
        why = str(err).split(" - do you need")[0]   # the module's advice to whoever opened the file, which is not the user
        raise ValueError(f"the CSV cannot be read: {why}") from None
    twice = sorted({c for c in header if header.count(c) > 1})
    if twice:   # the last column of a name won, silently (D-336)
        raise ValueError(f"CSV header names {', '.join(twice)} more than once")
    rows = []
    for r in all_rows:
        # A row with fewer fields than the header (a file cut inside a row) or more used to come back as a record
        # with the missing values None and the cut value read as it stood, a wrong record (D-117, D-171).
        if None in r or None in r.values():
            n = sum(1 for k, v in r.items() if k is not None and v is not None) + len(r.get(None) or [])
            raise ValueError(f"CSV data row {len(rows) + 1} has {qty(n, 'field')} and the header {len(reader.fieldnames)}: a file cut inside a row?")
        rows.append(r)
    cols = list(rows[0].keys()) if rows else []
    recs = []
    for r in rows:
        presence = {k: ("value" if v != "" else "empty") for k, v in r.items()}
        for k in OMM_META + OMM_TLEP + OMM_MEAN + OMM_HEADER:
            presence.setdefault(k, "absent")
        recs.append(canonical_from_fields(r, presence, "csv"))
    facts = {"columns": cols, "omm_mandatory_metadata_absent": [k for k in MANDATORY_META if k not in cols],
             "non_omm_columns": [c for c in cols if c not in OMM_KEYWORDS]}
    return recs, facts


class _Constant:
    """NaN, Infinity or -Infinity where a JSON value was: Python's json module reads them, JSON does not have them; or a
    number past what any value needs. Kept as this, so that the record's reading can name the key it was found under
    (D-336)."""

    def __init__(self, name, why="is not a JSON number"):
        self.name = name
        self.why = why


def _pairs(pairs):
    keys = [k for k, _ in pairs]
    twice = sorted({k for k in keys if keys.count(k) > 1})
    if twice:   # the last value of a key won, silently (D-336)
        raise ValueError(f"a JSON object names {', '.join(twice)} more than once")
    def inside(v):   # a constant at the pair, or anywhere in an array under it; an object inside has its own pairs
        if type(v) is _Constant:
            return v
        return next((c for c in map(inside, v) if c), None) if isinstance(v, list) else None
    for k, v in pairs:
        c = inside(v)
        if c:
            raise NotPlain(f"{k}: {c.name} {c.why}")
    return dict(pairs)



def _json_decimal(token):
    """A JSON number's text -> Decimal; one with an exponent past what Decimal() holds raised decimal.InvalidOperation from
    inside json.loads, no ValueError (D-336, the sixth reading); it is kept as a _Constant, so its key is named."""
    try:
        return Decimal(token)
    except ArithmeticError:
        return _Constant(repr(token[:40]), "has an exponent past what any value needs")


def _json_int(token):
    """A JSON integer's text -> int; one of more digits than any value needs, which int() refuses with advice to
    whoever runs Python, is kept as a _Constant, so its key is named (D-336, the seventh reading)."""
    if len(token.lstrip("-")) > PLAIN_DIGITS:
        return _Constant(repr(token[:40]), f"holds more digits than any integer needs: more than {PLAIN_DIGITS}")
    return int(token)


def read_json_text(text):
    try:
        return _read_json(text)
    except RecursionError:   # JSON nested past what Python's decoder or str() can follow: no provider writes it
        raise ValueError("the JSON is nested too deep to read") from None


def _read_json(text):
    data = json.loads(text, parse_float=_json_decimal, parse_int=_json_int, parse_constant=_Constant, object_pairs_hook=_pairs)
    if not isinstance(data, list):
        raise ValueError("expected a JSON array of records")
    keys = []
    for i, r in enumerate(data, 1):
        if not isinstance(r, dict):
            raise ValueError(f"JSON entry {i} is {(r.name + ', which ' + r.why) if type(r) is _Constant else type(r).__name__}, not an object")
        for k in r:
            if k not in keys:
                keys.append(k)
    recs = []
    types = {}
    for r in data:
        presence = {}
        fields = {}
        for k in keys:
            if k not in r:
                presence[k] = "absent"
            elif r[k] is None:
                presence[k] = "null"
            elif r[k] == "":
                presence[k] = "empty"
            else:
                if k in TEXT_KEYS and not isinstance(r[k], str):
                    # true read as "True" and ["ISS"] as "['ISS']": Python's str(), which no JSON reader shares (D-336)
                    raise ValueError(f"{k}: a JSON {type(r[k]).__name__} where the field is text")
                presence[k] = "value"
                fields[k] = r[k]
                types.setdefault(k, set()).add(type(r[k]).__name__)
        for k in OMM_META + OMM_TLEP + OMM_MEAN + OMM_HEADER:
            presence.setdefault(k, "absent")
        recs.append(canonical_from_fields(fields, presence, "json"))
    facts = {"keys": keys, "omm_mandatory_metadata_absent": [k for k in MANDATORY_META if k not in keys],
             "non_omm_keys": [k for k in keys if k not in OMM_KEYWORDS],
             "json_value_types": {k: sorted(v) for k, v in types.items()}}
    return recs, facts


# --------------------------------------------------------------------------- XML
def _strip_ns(tag):
    return tag.split("}", 1)[1] if "}" in tag else tag


def read_xml_text(text):
    try:
        root = ET.fromstring(text)
    except ET.ParseError as err:   # a SyntaxError, which the callers took for an error of the corpus (D-336)
        raise ValueError(f"the XML is not well-formed: {err}") from None
    if root.tag.startswith('{'):  # a default namespace: the unqualified CelesTrak/SANA form has none, and the field lookups below would all miss (D-117)
        raise ValueError(f"XML document declares a default namespace ({root.tag.split('}')[0][1:]}); the corpus reads the unqualified NDM/XML form only")
    rtag = _strip_ns(root.tag)
    omms = [root] if rtag == "omm" else [e for e in root if _strip_ns(e.tag) == "omm"]
    recs = []
    units_seen = {}
    for o in omms:
        sg = o.find("body/segment")
        for parent, tag in ((o, "header"), (o, "body"), (o.find("body"), "segment"), (sg, "metadata"), (sg, "data")):
            if parent is not None and len(parent.findall(tag)) > 1:   # the first of a repeated block was read (D-336)
                raise ValueError(f"XML element {tag} appears more than once in one OMM")
        data = sg.find("data") if sg is not None else None
        if data is not None:
            twice = sorted({_strip_ns(b.tag) for b in data if _strip_ns(b.tag) != "COMMENT" and sum(1 for c in data if c.tag == b.tag) > 1})
            if twice:
                raise ValueError(f"XML element {twice[0]} appears more than once in one OMM")
        for c in [o, o.find("header"), o.find("body"), sg, sg.find("metadata") if sg is not None else None, data] + (list(data) if data is not None else []):
            if c is None or _strip_ns(c.tag) == "COMMENT":   # a COMMENT's text is the comment (ommData allows them, D-336)
                continue
            if (c.text or "").strip(XML_PAD) or any((e.tail or "").strip(XML_PAD) for e in c):
                # <MEAN_MOTION>16.05</MEAN_MOTION>064833 read as 16.05: text between elements, set aside (D-336)
                raise ValueError(f"XML element {_strip_ns(c.tag)} holds text between its elements")
        fields, presence = {}, {}
        fields["CCSDS_OMM_VERS"] = o.get("version")
        presence["CCSDS_OMM_VERS"] = "value" if o.get("version") else "absent"
        blocks = []
        h = o.find("header")
        if h is not None:
            blocks.append(h)
        seg = o.find("body/segment")
        if seg is not None:
            m = seg.find("metadata")
            if m is not None:
                blocks.append(m)
            d = seg.find("data")
            if d is not None:
                for b in d:
                    if _strip_ns(b.tag) == "COMMENT":
                        fields.setdefault("_comments", []).append(b.text or "")
                    else:
                        blocks.append(b)
        for b in blocks:
            for e in b:
                k = _strip_ns(e.tag)
                if k == "COMMENT":
                    fields.setdefault("_comments", []).append(e.text or "")
                    continue
                t = e.text if e.text is not None else ""
                if len(e):   # 16.05<b/>064833 read as 16.05 (D-336)
                    raise ValueError(f"XML element {k} holds markup inside its value")
                if "units" in e.attrib and k in OMM_KEYWORDS and (k not in KVN_UNITS or e.attrib["units"] not in KVN_UNITS[k]):
                    # the units the schema allows for an OMM keyword, or none where it has none, as in KVN (D-336); an
                    # element that is no OMM keyword (the covariance's, USER_DEFINED's, one this reader does not know)
                    # keeps its units unchecked
                    raise ValueError(f"XML element {k} carries units {e.attrib['units']!r}, which it does not take")
                if k in fields and k != "USER_DEFINED":   # the last of a repeated element won, silently (D-336)
                    raise ValueError(f"XML element {k} appears more than once in one OMM")
                fields[k] = t
                presence[k] = "value" if t.strip() != "" else "empty"
                if "units" in e.attrib:
                    units_seen[k] = e.attrib["units"]
        for k in OMM_META + OMM_TLEP + OMM_MEAN + OMM_HEADER:
            presence.setdefault(k, "absent")
        comments = fields.pop("_comments", None)
        rec = canonical_from_fields(fields, presence, "xml")
        rec["xml"] = {"omm_id_attribute": o.get("id"), "version_attribute": o.get("version"),
                      "comments": comments, "units_attributes": dict(units_seen)}
        recs.append(rec)
    facts = {"root_element": rtag, "root_attributes": {_strip_ns(k): v for k, v in root.attrib.items()},
             "omm_count": len(omms), "version_attributes": sorted({o.get("version") for o in omms}),
             "units_attributes_seen": units_seen}
    return recs, facts


# --------------------------------------------------------------------------- KVN
# ASCII whitespace only (D-336): a no-break space or another Unicode space around a value stays in it, and the value then
# fails as a number. KVN is printable ASCII (7.3.4), so a tab is out of format too; it is still read as a blank, as it
# always was, since a tab around a value changes no number.
KVN_LINE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$", re.ASCII)
ASCII_SPACE = " \t\n\r\x0b\x0c"
KVN_UNITS = {"SEMI_MAJOR_AXIS": ("km",), "MEAN_MOTION": ("rev/day", "REV/DAY"), "INCLINATION": ("deg",),
             "RA_OF_ASC_NODE": ("deg",), "ARG_OF_PERICENTER": ("deg",), "MEAN_ANOMALY": ("deg",),
             "GM": ("km**3/s**2", "KM**3/S**2"), "BSTAR": ("1/ER",), "MEAN_MOTION_DOT": ("rev/day**2", "REV/DAY**2"),
             "MEAN_MOTION_DDOT": ("rev/day**3", "REV/DAY**3"), "BTERM": ("m**2/kg",), "AGOM": ("m**2/kg",),
             "MASS": ("kg",), "SOLAR_RAD_AREA": ("m**2",), "DRAG_AREA": ("m**2",)}
# the units of a mean-element OMM's keywords, as the vendored NDM/XML schemas (ndmxml-2.0.0, ndmxml-4.0.0) enumerate them;
# 7.7.1.1 says they must match Table 4-3 exactly, and docs/RESEARCH.md gives BSTAR's there as "1/[Earth radii]"
# (D-336, an open question; the schemas, CCSDS's examples and the corpus's own files write 1/ER)


def read_kvn_text(text):
    msgs = []
    cur = None
    max_len = 0
    for n, raw in enumerate(text_lines(text), 1):
        max_len = max(max_len, len(raw))
        bad = re.search(r"[^\t\x20-\x7e]", raw)
        if bad:   # 7.3.4: printable ASCII, a tab tolerated; a Unicode space before a keyword dropped its line silently (D-336)
            name = re.search(r"[A-Z][A-Z0-9_]*", raw)
            raise ValueError(f"KVN line {n}{f' ({name.group()})' if name else ''} holds {bad.group()!r}, which is not "
                             "printable ASCII (CCSDS 502.0-B-3 7.3.4)")
        line = raw.rstrip(ASCII_SPACE)   # str.rstrip() took a no-break space after a value off with the line's end (D-336)
        if not line.strip(ASCII_SPACE):
            continue
        if line.lstrip(" \t").startswith("COMMENT"):   # blanks before a keyword mean nothing (7.4.5), COMMENT's too
            if cur is not None:
                body = line.lstrip(" \t")
                cur["_comments"].append(body[len("COMMENT"):].lstrip(" ", ) if len(body) > 7 else "")
            continue
        m = KVN_LINE.match(line)
        if not m:   # 7.4.3: one KEYWORD = value per line; a value broken by CR or LF read as its first digits (D-336)
            raise ValueError(f"KVN line {n} is neither a COMMENT nor KEYWORD = value: {raw[:80]!r}")
        k, v = m.group(1), m.group(2)
        if k == "CCSDS_OMM_VERS":
            cur = {"_fields": {}, "_order": [], "_units": {}, "_comments": [], "_unparsed": []}
            msgs.append(cur)
        if cur is None:   # an assignment before CCSDS_OMM_VERS: a message without its version line was dropped whole (D-336)
            raise ValueError(f"KVN line {n}: {k} comes before the message's CCSDS_OMM_VERS")
        um = re.match(r"^(.*?)\s+\[([^\]]+)\]$", v) if k in KVN_UNITS else None
        if um:
            # 7.7.1.1: units only where the table gives them, matching exactly, after a blank; a bracketed tail on any
            # other keyword is part of its value, and a number's then fails as one (D-336)
            if um.group(2) not in KVN_UNITS[k]:
                raise ValueError(f"KVN line {n}: {k}'s units [{um.group(2)}] are not [{KVN_UNITS[k][0]}]")
            v = um.group(1)
            cur["_units"][k] = um.group(2)
        if k in cur["_fields"]:  # last-wins used to hide a repeated keyword (D-117)
            raise ValueError(f"duplicate keyword {k} in one KVN message")
        cur["_fields"][k] = v
        cur["_order"].append(k)
    recs = []
    for m in msgs:
        presence = {k: ("value" if v != "" else "empty") for k, v in m["_fields"].items()}
        for k in OMM_META + OMM_TLEP + OMM_MEAN + OMM_HEADER:
            presence.setdefault(k, "absent")
        rec = canonical_from_fields(m["_fields"], presence, "kvn")
        rec["kvn"] = {"keyword_order": m["_order"], "units": m["_units"], "comments": m["_comments"],
                      "unparsed_lines": m["_unparsed"]}
        recs.append(rec)
    facts = {"message_count": len(msgs), "max_line_length": max_len,
             "keyword_order_first_message": msgs[0]["_order"] if msgs else []}
    return recs, facts


# --------------------------------------------------------------------------- dispatch
def read_file(path):
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(b"\xef\xbb\xbf"):  # a BOM used to be read as part of the first field or line and the record came back wrong (D-117)
        raise ValueError("UTF-8 BOM at the start of the file; the provider formats carry none and the corpus does not read past one")
    text = raw.decode("utf-8")
    ext = path.rsplit(".", 1)[-1].lower()
    if ext in ("tle", "2le"):
        recs, facts = read_tle_text(text), {}
        fmt = "tle" if ext == "tle" else "2le"
    elif ext == "csv":
        recs, facts = read_csv_text(text)
        fmt = "csv"
    elif ext == "json":
        recs, facts = read_json_text(text)
        fmt = "json"
    elif ext == "xml":
        recs, facts = read_xml_text(text)
        fmt = "xml"
    elif ext == "kvn":
        recs, facts = read_kvn_text(text)
        fmt = "kvn"
    else:
        raise ValueError(f"unknown format for {path}")
    facts.update({"format": fmt, "record_count": len(recs), "line_endings": line_endings(raw), "bytes": len(raw)})
    return fmt, recs, facts


if __name__ == "__main__":
    for p in sys.argv[1:]:
        fmt, recs, facts = read_file(p)
        print(p, fmt, facts)
        for r in recs[:2]:
            print(json.dumps(r, indent=1, default=str)[:1500])
