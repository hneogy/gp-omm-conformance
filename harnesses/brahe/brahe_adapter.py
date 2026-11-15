# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""gpconf adapter for brahe (duncaneddy/brahe, its Python package), loaded with --adapter (0.9.0 item b3).

    python3 -m gpconf run --adapter brahe_adapter:Parser      (from this folder, brahe installed)

OMM JSON through `brahe.GPRecord.from_json`, the library's reader of CelesTrak's and Space-Track's GP records, one
object at a time (it takes one object, as satellite.js's json2satrec does, and the adapter splits the array as that
preset does); OMM CSV, XML and KVN
through `brahe.ccsds.OMM.from_str`, which detects the format itself. A file the library raises on is refused whole,
with its reason. TLE answers Unsupported: brahe's TLE interface (`SGPPropagator.from_tle`, `epoch_from_tle`,
`keplerian_elements_from_tle`) gives back the catalog number, the epoch and the six Keplerian elements, but not the
mean motion as the line holds it, BSTAR or the derivatives, so no record in the corpus's terms can be made without
deciding values for the library (docs/ADAPTERS.md, "What not to do"). The vector hooks alpha5_decode and alpha5_encode
are the library's `parse_norad_id` (classic and Alpha-5) and `norad_id_numeric_to_alpha5`; the other three answer Unsupported.
brahe needs an Earth-orientation provider for some conversions; the adapter installs brahe's own zero provider, so
nothing is downloaded."""
import json

import brahe as bh
from brahe.ccsds import OMM

from gpconf.runner import Unsupported

bh.set_global_eop_provider(bh.StaticEOPProvider.from_zero())   # no download; UT1-UTC 0 (unused by the reading)

FIELDS = ("norad_cat_id", "object_name", "object_id", "mean_motion", "eccentricity", "inclination", "ra_of_asc_node",
          "arg_of_pericenter", "mean_anomaly", "bstar", "mean_motion_dot", "mean_motion_ddot", "ephemeris_type",
          "classification_type", "element_set_no", "rev_at_epoch", "center_name", "ref_frame", "time_system",
          "mean_element_theory")


class Parser:
    def parse(self, raw, fmt):
        if fmt in ("tle", "2le"):
            raise Unsupported(fmt)
        text = raw.decode("utf-8")
        if fmt == "json":
            out = []
            for obj in json.loads(text):
                g = bh.GPRecord.from_json(json.dumps(obj))
                out.append({k: getattr(g, k) for k in FIELDS + ("epoch",) if getattr(g, k, None) is not None})
            return out
        o = OMM.from_str(text)   # one message per call: the library's reader
        rec = {k: getattr(o, k) for k in FIELDS if getattr(o, k, None) is not None}
        rec["epoch"] = o.epoch.to_pydatetime()
        return [rec]

    def alpha5_decode(self, field):
        return bh.parse_norad_id(field)

    def alpha5_encode(self, n):
        return bh.norad_id_numeric_to_alpha5(n)

    def two_digit_year(self, yy):
        raise Unsupported("two_digit_year")

    def parse_epoch(self, text):
        raise Unsupported("parse_epoch")

    def parse_catalog_id(self, text):
        raise Unsupported("parse_catalog_id")
