"""Preset `pyephem`: PyEphem (the `ephem` package, an optional dependency, tested with 4.2.1). TLE and 2LE only;
every other format is Unsupported.

Exposes the library as-is: `ephem.readtle()` per element set. An element set `readtle()` refuses is reported through
the runner's refusal channel (D-144) with the library's exception as its reason (D-174); the corpus's one-off run of
2026-09-24 (corpus D-128; reported upstream as pyephem#296) dropped such sets, and over its seventeen cases
`readtle()` refused none. PyEphem reads one element set at a time and has no reader for a file of them, so this
adapter hands it each line 1 with whatever line follows, and PyEphem, not the adapter, answers for a line 1 with no
line 2 after it (D-183). Moved into the package from the one-off run's harness (D-151).
"""
import math

try:
    import ephem
except ImportError as e:  # pragma: no cover
    raise ImportError("this adapter needs PyEphem: pip install ephem") from e

from gpconf.runner import Unsupported

DECLARATION = {"_adapter": {"refusals": True}}  # every element set readtle() refuses is reported as a refusal (D-144)


def _rec(s, name):
    d = s._epoch.datetime()  # ephem.Date -> naive UTC datetime, microsecond resolution
    return {
        "norad_cat_id": s.catalog_number,
        "object_name": name or None,
        "epoch": d,
        "mean_motion": s._n,
        "eccentricity": s._e,
        "inclination": math.degrees(s._inc),
        "ra_of_asc_node": math.degrees(s._raan),
        "arg_of_pericenter": math.degrees(s._ap),
        "mean_anomaly": math.degrees(s._M),
        "bstar": s._drag,
        "mean_motion_dot": s._decay,
        # mean_motion_ddot: PyEphem keeps no second derivative (no attribute on EarthSatellite); omitted on purpose
        "rev_at_epoch": s._orbit,
        # object_id, classification_type, element_set_no, ephemeris_type: not exposed by PyEphem
    }


class Parser:
    def parse(self, raw, fmt):
        if fmt not in ("tle", "2le"):
            raise Unsupported(fmt)
        lines = raw.decode("utf-8").splitlines()
        out = [DECLARATION]
        for i, l in enumerate(lines):
            if l.startswith("1 "):  # with whatever line follows, a line 2 or not: the library answers (D-183)
                l2 = lines[i + 1] if i + 1 < len(lines) else ""
                name = lines[i - 1].strip() if i and not lines[i - 1].startswith(("1 ", "2 ")) else ""
                # readtle() rejects an empty name (db_tle returns -1 when the stripped name is empty), so a
                # name-less 2LE pair gets the catalog field as its name; object_name is then not reported
                call_name = name or l[2:7]
                try:
                    out.append(_rec(ephem.readtle(call_name, l, l2), name))
                except Exception as e:  # noqa: BLE001 -- the refusal channel (D-144): the library's own reason, the field as the line carried it
                    out.append({"_refused": f"{type(e).__name__}: {e}", "_field": l[2:7], "_input": l[:80]})
        return out
