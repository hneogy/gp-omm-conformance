"""
Naive adapter: the parser many projects actually have. Written deliberately with the common
shortcuts so the runner's failures document what breaks in the migration:
  * catalog number read with int() from five columns / assumed five characters wide
  * two-digit year pivot present, but OBJECT_ID's year sliced unconditionally
  * OMM epoch parsed with the single format '%Y-%m-%dT%H:%M:%S.%f'
  * classification assumed to be 'U'
  * KVN parsed as strict 'KEY = value' with float() on the value
  * every CelesTrak CSV/JSON column assumed present
"""
import csv
import datetime as dt
import io
import json
import xml.etree.ElementTree as ET


def _year(yy):
    yy = int(yy)
    return 1900 + yy if yy >= 57 else 2000 + yy


def _tle_epoch(field):
    year = _year(field[:2])
    day = float(field[2:])
    return (dt.datetime(year, 1, 1) + dt.timedelta(days=day - 1)).strftime("%Y-%m-%dT%H:%M:%S.%f")


def _exp(f):
    f = f.strip()
    return float(f"{f[:-2]}e{f[-2:]}".replace("-", "-0.", 1) if f.startswith("-") else f"0.{f[:-2]}e{f[-2:]}")


class Parser:
    def parse(self, raw, fmt):
        text = raw.decode("utf-8")
        if fmt in ("tle", "2le"):
            return self._tle(text)
        if fmt == "csv":
            return [self._omm(r) for r in csv.DictReader(io.StringIO(text))]
        if fmt == "json":
            return [self._omm(r) for r in json.loads(text)]
        if fmt == "xml":
            root = ET.fromstring(text)
            out = []
            for seg in root.iter("segment"):
                f = {}
                for blk in ("metadata", "data/meanElements", "data/tleParameters"):
                    for e in seg.find(blk):
                        f[e.tag] = e.text
                out.append(self._omm(f))
            return out
        if fmt == "kvn":
            out, cur = [], None
            for line in text.splitlines():
                if not line.strip():
                    continue
                k, v = [x.strip() for x in line.split("=", 1)]
                if k == "CCSDS_OMM_VERS":
                    cur = {}
                    out.append(cur)
                cur[k] = v
            return [self._omm(f) for f in out]
        raise ValueError(fmt)

    def _tle(self, text):
        lines = text.splitlines()
        out = []
        for i, l in enumerate(lines):
            if l.startswith("1 ") and lines[i + 1].startswith("2 "):
                l1, l2 = l, lines[i + 1]
                cat = int(l1[2:7])                    # breaks on Alpha-5
                assert l1[7] == "U", "classification"  # breaks on 'C'
                out.append({
                    "norad_cat_id": cat, "object_name": (lines[i - 1].strip() if i and not lines[i - 1].startswith(("1 ", "2 ")) else None),
                    "object_id": f"{_year(l1[9:11])}-{l1[11:17].strip()}",   # invents '1900-' + blanks for empty designator? no: _year('  ') raises
                    "epoch": _tle_epoch(l1[18:32]), "mean_motion": float(l2[52:63]), "eccentricity": float("0." + l2[26:33]),
                    "inclination": float(l2[8:16]), "ra_of_asc_node": float(l2[17:25]), "arg_of_pericenter": float(l2[34:42]),
                    "mean_anomaly": float(l2[43:51]), "bstar": _exp(l1[53:61]), "mean_motion_dot": float(l1[33:43]),
                    "mean_motion_ddot": _exp(l1[44:52]), "ephemeris_type": int(l1[62]), "classification_type": l1[7],
                    "element_set_no": int(l1[64:68]), "rev_at_epoch": int(l2[63:68]),
                })
        return out

    def _omm(self, f):
        cat = int(f["NORAD_CAT_ID"])
        assert len(f"{cat:05d}") == 5, "catalog number wider than five digits"   # breaks on 6- and 9-digit ids
        epoch = dt.datetime.strptime(f["EPOCH"], "%Y-%m-%dT%H:%M:%S.%f")       # breaks on day-of-year / Z / no fraction
        launch_year = int(f["OBJECT_ID"][:4])                                    # breaks on empty OBJECT_ID (and None)
        assert f["CLASSIFICATION_TYPE"] == "U"                                   # breaks on 'C'
        return {
            "norad_cat_id": cat, "object_name": f["OBJECT_NAME"], "object_id": f["OBJECT_ID"], "epoch": epoch,
            "mean_motion": float(f["MEAN_MOTION"]), "eccentricity": float(f["ECCENTRICITY"]), "inclination": float(f["INCLINATION"]),
            "ra_of_asc_node": float(f["RA_OF_ASC_NODE"]), "arg_of_pericenter": float(f["ARG_OF_PERICENTER"]), "mean_anomaly": float(f["MEAN_ANOMALY"]),
            "bstar": float(f["BSTAR"]), "mean_motion_dot": float(f["MEAN_MOTION_DOT"]), "mean_motion_ddot": float(f["MEAN_MOTION_DDOT"]),
            "ephemeris_type": int(f["EPHEMERIS_TYPE"]), "classification_type": f["CLASSIFICATION_TYPE"],
            "element_set_no": int(f["ELEMENT_SET_NO"]), "rev_at_epoch": int(f["REV_AT_EPOCH"]),
        }

    def alpha5_decode(self, field):
        return int(field)  # breaks on any letter

    def alpha5_encode(self, n):
        return f"{n:05d}"  # produces six digits above 99999, never a letter

    def two_digit_year(self, yy):
        return _year(yy)

    def parse_catalog_id(self, text):
        return int(text)  # accepts ten digits; no width check

    def parse_epoch(self, text):
        return dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%f")
