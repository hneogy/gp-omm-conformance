# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Preset `sgp4`: python-sgp4 (an optional dependency, tested with 2.27). TLE via twoline2rv; CSV/XML/JSON via
sgp4.omm; KVN unsupported; TLE writing via omm.initialize + exporter.export_tle.
Exposes the library's behaviour as-is, including the failures documented in docs/upstream/."""
import io
import json
import math
from typing import Any

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


DECLARATION: dict[str, Any] = {"_adapter": {"refusals": True, "propagation": {"gravity": "wgs72", "opsmode": "i"}}}  # every record this adapter drops with an error is reported as a refusal (D-144); the propagate hook's constants, Satrec with WGS72 and opsmode 'i' (D-413)


class Parser:
    def parse(self, raw, fmt):
        text = raw.decode("utf-8")
        if fmt in ("tle", "2le"):
            lines = text.splitlines()
            out = [DECLARATION]
            for i, l in enumerate(lines):
                if l.startswith("1 "):  # with whatever line follows, a line 2 or not: the library answers (D-183)
                    l2 = lines[i + 1] if i + 1 < len(lines) else ""
                    name = lines[i - 1].strip() if i and not lines[i - 1].startswith(("1 ", "2 ")) else None
                    try:
                        out.append(_rec(Satrec.twoline2rv(l, l2), name))
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

    def propagate(self, raw, fmt, tsince):
        """The propagation tier (D-401): one element set's bytes, minutes since its epoch -> TEME r (km), v (km/s) and
        the SGP4 error code per step, by Satrec with WGS-72 and opsmode 'i', the library's defaults, through
        sgp4_tsince; an OMM CSV through sgp4.omm.initialize (D-406)."""
        from sgp4.api import WGS72
        if fmt in ("tle", "2le"):
            lines = [l for l in raw.decode("utf-8").splitlines() if l.startswith(("1 ", "2 "))]
            if len(lines) != 2:
                raise ValueError(f"one element set expected, {len(lines)} element lines given")
            s = Satrec.twoline2rv(lines[0], lines[1], WGS72)
        elif fmt == "csv":   # the OMM path, sgp4.omm, as the library's users take it (D-406)
            (fields,) = list(omm.parse_csv(io.StringIO(raw.decode("utf-8"))))
            s = Satrec()
            omm.initialize(s, fields)
        else:
            raise Unsupported(fmt)
        out = []
        for t in tsince:
            e, r, v = s.sgp4_tsince(float(t))
            out.append({"r": list(r), "v": list(v), "error": int(e)} if e == 0 else {"r": None, "v": None, "error": int(e)})
        return out
