#!/usr/bin/env python3
"""
gpconf/tle.py -- TLE column layout, checksum, Alpha-5 codec and an OMM -> TLE renderer.

Standard library only. Also imported by tools/tlerender.py (shim).

Purpose: produce the derived Alpha-5 TLE fixtures. To be trustworthy, the renderer must
reproduce CelesTrak's own TLE rendering byte for byte on records that CelesTrak *does* render
as TLE (tools/validate_render.py: 304/304 CelesTrak records reproduced byte for byte), so that a derived Alpha-5 line differs from what
CelesTrak would emit only in the catalog-number field.

Text in, text out. Values are handled as decimal strings, never as binary floats.

Column layout: CelesTrak TLE format documentation
(https://celestrak.org/NORAD/documentation/tle-fmt.php) and Space-Track's TLE description.
"""
import datetime as dt
import re
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN

ALPHA5_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # I and O skipped (Space-Track)


def to_alpha5(n):
    n = int(n)
    if n < 0:
        raise ValueError("negative catalog number")
    if n < 100000:
        return f"{n:05d}"
    if n > 339999:
        raise ValueError(f"{n} exceeds the Alpha-5 ceiling 339999")
    hi, lo = divmod(n, 10000)
    return f"{ALPHA5_LETTERS[hi - 10]}{lo:04d}"


def from_alpha5(field):
    """Space-Track's definition, strictly: five characters, a digit or an uppercase letter other than I and O in the
    first, four digits after. 'A-001', 'A 000', '+1234', lowercase and four- or six-character fields are errors (D-117)."""
    if not isinstance(field, str) or not re.fullmatch(r"[0-9A-HJ-NP-Z][0-9]{4}", field):
        raise ValueError(f"invalid Alpha-5 field {field!r}: one digit or uppercase letter (never I or O) followed by four digits")
    c = field[0]
    if c.isdigit():
        return int(field)
    return (ALPHA5_LETTERS.index(c) + 10) * 10000 + int(field[1:])


def checksum(line):
    return sum(int(c) if c.isdigit() else (c == "-") for c in line[:68]) % 10


def exp_field(text, mantissa_mode="truncate"):
    """OMM decimal text -> 8-char TLE implied-decimal exponent field, e.g. '.15975118E-3' -> ' 15975-3'."""
    d = Decimal((text or "0").strip() or "0")
    if d == 0:
        return " 00000+0"
    sign = "-" if d < 0 else " "
    a = d.copy_abs()
    t = a.normalize().as_tuple()
    digits = "".join(map(str, t.digits))
    e = len(digits) + t.exponent  # a == 0.<digits> * 10**e
    if mantissa_mode == "truncate":
        m5 = digits[:5].ljust(5, "0")
    else:
        q = (a / (Decimal(10) ** e)).quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)
        if q >= 1:
            q = q / 10
            e += 1
        m5 = f"{q:.5f}"[2:]
    if not -9 <= e <= 9:
        raise ValueError(f"exponent {e} not representable in a TLE field")
    return f"{sign}{m5}{e:+d}"


EPOCH_RE = re.compile(r"(\d{4})-(?:(\d{2})-(\d{2})|(\d{3}))T(\d{2}):(\d{2}):(\d{2})(\.\d+)?(Z|[+-]\d{2}:\d{2})?")


def iso_epoch(text):
    """An epoch string in any form the corpus accepts -> canonical 'YYYY-MM-DDThh:mm:ss.ffffff' (UTC, naive).
    Accepts the CCSDS 502.0-B-3 7.5.10 calendar and day-of-year forms, any number of fraction digits (quantised
    to microseconds, half even), an optional 'Z', a '+HH:MM'/'-HH:MM' offset (converted to UTC: a parser under test
    may return one) and second 60 (a leap second, mapped to :59 as the reference adapter does). Raises ValueError
    for anything else, so a caller never sees a bare strptime failure (D-119)."""
    s = str(text).strip()
    m = EPOCH_RE.fullmatch(s)
    if not m:
        raise ValueError(f"not an ISO/CCSDS epoch: {text!r}")
    year, mon, day, doy, hh, mi, ss, frac, zone = m.groups()
    year = int(year)
    if doy is not None:
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        if not 1 <= int(doy) <= (366 if leap else 365):
            raise ValueError(f"day of year {doy} is outside the year in {text!r}")
        date = dt.date(year, 1, 1) + dt.timedelta(days=int(doy) - 1)
    else:
        date = dt.date(year, int(mon), int(day))  # raises ValueError for month 13 or day 32
    sec = int(ss)
    if sec == 60:
        sec = 59
    elif sec > 60:
        raise ValueError(f"second {ss} in {text!r}")
    us = int((Decimal("0" + frac) * 1_000_000).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)) if frac else 0
    t = dt.datetime(date.year, date.month, date.day, int(hh), int(mi), sec) + dt.timedelta(microseconds=us)
    if zone and zone != "Z":
        sign = 1 if zone[0] == "+" else -1
        t -= sign * dt.timedelta(hours=int(zone[1:3]), minutes=int(zone[4:6]))
    return t.strftime("%Y-%m-%dT%H:%M:%S.%f")


def epoch_field(iso, rounding=ROUND_HALF_UP):
    """ISO epoch (calendar or day-of-year form, see iso_epoch) -> 'YYDDD.DDDDDDDD' (14 chars)."""
    t = dt.datetime.strptime(iso_epoch(iso), "%Y-%m-%dT%H:%M:%S.%f")
    us = ((t.hour * 60 + t.minute) * 60 + t.second) * 1_000_000 + t.microsecond
    frac = (Decimal(us) / Decimal(86_400_000_000)).quantize(Decimal("0.00000001"), rounding=rounding)
    doy = t.timetuple().tm_yday
    year = t.year
    if frac >= 1:
        frac -= 1
        nxt = t.date() + dt.timedelta(days=1)
        doy, year = nxt.timetuple().tm_yday, nxt.year
    # format(..., 'f'): str(Decimal) prints a quantised zero as '0E-8', which used to render midnight as 'YYDDD.-8000000' (D-111)
    return f"{year % 100:02d}{doy:03d}.{format(frac, 'f')[2:].ljust(8, '0')}"


def ndot_field(text):
    d = Decimal((text or "0").strip() or "0")
    s = str(d.copy_abs().quantize(Decimal("1e-8"), rounding=ROUND_HALF_UP))  # 0.NNNNNNNN, half up like the provider (D-118)
    if "E" in s.upper():
        s = format(Decimal(s), "f")
    if not s.startswith("0."):
        raise ValueError(f"MEAN_MOTION_DOT {text!r} too large for the TLE field")
    return ("-" if d < 0 else " ") + s[1:]


def ecc_field(text, mode="truncate"):
    d = Decimal(text.strip())
    if d < 0 or d >= 1:
        raise ValueError(f"eccentricity {text!r} out of range")
    if mode == "truncate":
        digits = f"{d:.20f}".split(".")[1]
        return digits[:7]
    return f"{d.quantize(Decimal('0.0000001'), rounding=ROUND_HALF_UP):.7f}"[2:]


def fixed(text, places, width):
    d = Decimal(text.strip())
    return f"{d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP):.{places}f}".rjust(width)


def intl_designator(object_id):
    s = (object_id or "").strip()
    if not s:
        return " " * 8
    yyyy, rest = s.split("-", 1)
    return (yyyy[2:] + rest).ljust(8)[:8]


RECORD_TO_OMM = [("object_name", "OBJECT_NAME"), ("object_id", "OBJECT_ID"), ("epoch", "EPOCH"),
                 ("mean_motion", "MEAN_MOTION"), ("eccentricity", "ECCENTRICITY"), ("inclination", "INCLINATION"),
                 ("ra_of_asc_node", "RA_OF_ASC_NODE"), ("arg_of_pericenter", "ARG_OF_PERICENTER"), ("mean_anomaly", "MEAN_ANOMALY"),
                 ("ephemeris_type", "EPHEMERIS_TYPE"), ("classification_type", "CLASSIFICATION_TYPE"), ("norad_cat_id", "NORAD_CAT_ID"),
                 ("element_set_no", "ELEMENT_SET_NO"), ("rev_at_epoch", "REV_AT_EPOCH"), ("bstar", "BSTAR"),
                 ("mean_motion_dot", "MEAN_MOTION_DOT"), ("mean_motion_ddot", "MEAN_MOTION_DDOT")]


def omm_fields_from_record(rec):
    """A record in the runner's key names (parse() output, expected.json 'canonical') -> OMM keyword text
    as an OMM producer would write it, ready for render(). None becomes ''; a datetime epoch becomes ISO text."""
    out = {}
    for key, kw in RECORD_TO_OMM:
        v = rec.get(key)
        if v is None:
            out[kw] = ""
        elif isinstance(v, dt.datetime):
            out[kw] = v.strftime("%Y-%m-%dT%H:%M:%S.%f")
        elif isinstance(v, float):
            out[kw] = repr(v)
        else:
            out[kw] = str(v)
    return out


def render(rec, *, catnum_field=None, mantissa_mode="truncate", ecc_mode="truncate",
           epoch_rounding=ROUND_HALF_UP, name_mode="pad24"):
    """rec: dict of OMM keyword -> text (CSV/KVN/XML text values). Returns (line0, line1, line2)."""
    cat = int(rec["NORAD_CAT_ID"])
    sat = catnum_field if catnum_field is not None else to_alpha5(cat)
    if len(sat) != 5:
        raise ValueError("catalog field must be 5 characters")
    l1 = (f"1 {sat}{(rec.get('CLASSIFICATION_TYPE') or 'U')[:1]} {intl_designator(rec.get('OBJECT_ID'))} "
          f"{epoch_field(rec['EPOCH'], epoch_rounding)} {ndot_field(rec.get('MEAN_MOTION_DOT'))} "
          f"{exp_field(rec.get('MEAN_MOTION_DDOT'), mantissa_mode)} {exp_field(rec.get('BSTAR'), mantissa_mode)} "
          f"{str(rec.get('EPHEMERIS_TYPE') or '0')[:1]} {str(int(rec.get('ELEMENT_SET_NO') or 0)):>4}")
    l2 = (f"2 {sat} {fixed(rec['INCLINATION'], 4, 8)} {fixed(rec['RA_OF_ASC_NODE'], 4, 8)} "
          f"{ecc_field(rec['ECCENTRICITY'], ecc_mode)} {fixed(rec['ARG_OF_PERICENTER'], 4, 8)} "
          f"{fixed(rec['MEAN_ANOMALY'], 4, 8)} {fixed(rec['MEAN_MOTION'], 8, 11)}{str(int(rec.get('REV_AT_EPOCH') or 0)):>5}")
    assert len(l1) == 68 and len(l2) == 68, (len(l1), len(l2))
    l1 += str(checksum(l1))
    l2 += str(checksum(l2))
    name = rec.get("OBJECT_NAME") or ""
    l0 = name.ljust(24)[:24] if name_mode == "pad24" else name
    return l0, l1, l2
