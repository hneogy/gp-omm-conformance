"""python-sgp4 adapter (optional dependency). TLE via twoline2rv; CSV/XML/JSON via sgp4.omm; KVN unsupported.
Exposes the library's behaviour as-is, including the failures documented in docs/upstream/."""
import io
import json
import math

from gpconf.runner import Unsupported

try:
    from sgp4.api import Satrec
    from sgp4 import omm
    from sgp4.conveniences import sat_epoch_datetime
    from sgp4.alpha5 import from_alpha5, to_alpha5
except ImportError as e:  # pragma: no cover
    raise ImportError("install python-sgp4 to use this adapter") from e

XPDOTP = 1440.0 / (2.0 * math.pi)


def _rec(s, name=None):
    return {"norad_cat_id": s.satnum, "object_name": name, "epoch": sat_epoch_datetime(s),
            "mean_motion": s.no_kozai * XPDOTP, "eccentricity": s.ecco, "inclination": math.degrees(s.inclo),
            "ra_of_asc_node": math.degrees(s.nodeo), "arg_of_pericenter": math.degrees(s.argpo), "mean_anomaly": math.degrees(s.mo),
            "bstar": s.bstar, "mean_motion_dot": s.ndot * XPDOTP * 1440.0, "mean_motion_ddot": s.nddot * XPDOTP * 1440.0 * 1440.0,
            "ephemeris_type": s.ephtype, "classification_type": s.classification, "element_set_no": s.elnum, "rev_at_epoch": s.revnum}


class Parser:
    def parse(self, raw, fmt):
        text = raw.decode("utf-8")
        if fmt in ("tle", "2le"):
            lines = text.splitlines()
            out = []
            for i, l in enumerate(lines):
                if l.startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
                    name = lines[i - 1].strip() if i and not lines[i - 1].startswith(("1 ", "2 ")) else None
                    out.append(_rec(Satrec.twoline2rv(l, lines[i + 1]), name))
            return out
        if fmt == "csv":
            fields_iter = omm.parse_csv(io.StringIO(text))
        elif fmt == "xml":
            fields_iter = omm.parse_xml(io.StringIO(text))
        elif fmt == "json":
            fields_iter = json.loads(text)
        else:
            raise Unsupported(fmt)
        out = []
        for fields in fields_iter:
            s = Satrec()
            omm.initialize(s, fields)
            r = _rec(s, fields.get("OBJECT_NAME"))
            r["object_id"] = fields.get("OBJECT_ID") or None
            out.append(r)
        return out

    def alpha5_decode(self, field):
        return from_alpha5(field)

    def alpha5_encode(self, n):
        return to_alpha5(n)
