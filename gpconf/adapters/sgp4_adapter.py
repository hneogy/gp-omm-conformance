"""Preset `sgp4`: python-sgp4 (an optional dependency, tested with 2.27). TLE via twoline2rv; CSV/XML/JSON via
sgp4.omm; KVN unsupported; TLE writing via omm.initialize + exporter.export_tle.
Exposes the library's behaviour as-is, including the failures documented in docs/upstream/."""
import io
import json
import math

from gpconf.runner import Unsupported
from gpconf import tle as tlemod

try:
    from sgp4.api import Satrec
    from sgp4 import omm, exporter
    from sgp4.conveniences import sat_epoch_datetime
    from sgp4.alpha5 import from_alpha5, to_alpha5
except ImportError as e:  # pragma: no cover
    raise ImportError("this adapter needs python-sgp4: pip install sgp4") from e

XPDOTP = 1440.0 / (2.0 * math.pi)


def _rec(s, name=None):
    return {"norad_cat_id": s.satnum, "object_name": name, "epoch": sat_epoch_datetime(s),
            "mean_motion": s.no_kozai * XPDOTP, "eccentricity": s.ecco, "inclination": math.degrees(s.inclo),
            "ra_of_asc_node": math.degrees(s.nodeo), "arg_of_pericenter": math.degrees(s.argpo), "mean_anomaly": math.degrees(s.mo),
            "bstar": s.bstar, "mean_motion_dot": s.ndot * XPDOTP * 1440.0, "mean_motion_ddot": s.nddot * XPDOTP * 1440.0 * 1440.0,
            "ephemeris_type": s.ephtype, "classification_type": s.classification, "element_set_no": s.elnum, "rev_at_epoch": s.revnum}


DECLARATION = {"_adapter": {"refusals": True}}  # every record this adapter drops with an error is reported as a refusal (D-144)


class Parser:
    def parse(self, raw, fmt):
        text = raw.decode("utf-8")
        if fmt in ("tle", "2le"):
            lines = text.splitlines()
            out = [DECLARATION]
            for i, l in enumerate(lines):
                if l.startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
                    name = lines[i - 1].strip() if i and not lines[i - 1].startswith(("1 ", "2 ")) else None
                    try:
                        out.append(_rec(Satrec.twoline2rv(l, lines[i + 1]), name))
                    except ValueError as e:  # the refusal channel (D-144): the library's own reason, the field as the line carried it
                        out.append({"_refused": f"ValueError: {e}", "_field": l[2:7], "_input": l[:80]})
            return out
        if fmt == "csv":
            fields_iter = omm.parse_csv(io.StringIO(text))
        elif fmt == "xml":
            fields_iter = omm.parse_xml(io.StringIO(text))
        elif fmt == "json":
            fields_iter = json.loads(text)
        else:
            raise Unsupported(fmt)
        out = [DECLARATION]
        for fields in fields_iter:
            s = Satrec()
            try:
                omm.initialize(s, fields)
            except ValueError as e:  # e.g. a nine-digit NORAD_CAT_ID: refused with the library's reason, not dropped (D-144)
                out.append({"_refused": f"ValueError: {e}", "_field": str(fields.get("NORAD_CAT_ID")), "_input": str(fields.get("NORAD_CAT_ID"))})
                continue
            r = _rec(s, fields.get("OBJECT_NAME"))
            r["object_id"] = fields.get("OBJECT_ID") or None
            out.append(r)
        return out

    def write_tle(self, record):
        # omm.initialize raises ValueError for a catalog number above 339999: the correct answer for the writer case
        s = Satrec()
        omm.initialize(s, tlemod.omm_fields_from_record(record))
        return exporter.export_tle(s)

    def alpha5_decode(self, field):
        return from_alpha5(field)

    def alpha5_encode(self, n):
        return to_alpha5(n)
