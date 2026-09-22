"""Reference adapter: the corpus's own readers. Should pass every case (it produced the expected values)."""
import datetime as dt

from gpconf import reference as ref
from gpconf import tle as tlemod
from gpconf.runner import CORE_FIELDS, OPTIONAL_FIELDS

FMT = {"tle": ref.read_tle_text, "2le": ref.read_tle_text}


class Parser:
    def parse(self, raw, fmt):
        text = raw.decode("utf-8")
        if fmt in ("tle", "2le"):
            recs = ref.read_tle_text(text)
        elif fmt == "csv":
            recs, _ = ref.read_csv_text(text)
        elif fmt == "json":
            recs, _ = ref.read_json_text(text)
        elif fmt == "xml":
            recs, _ = ref.read_xml_text(text)
        elif fmt == "kvn":
            recs, _ = ref.read_kvn_text(text)
        else:
            from gpconf.runner import Unsupported
            raise Unsupported(fmt)
        out = []
        for r in recs:
            d = {k: r.get(k) for k in CORE_FIELDS + OPTIONAL_FIELDS if r.get(k) is not None or k in CORE_FIELDS}
            out.append(d)
        return out

    def write_tle(self, record):
        # the corpus's own renderer (CelesTrak conventions: eccentricity truncated, mantissas rounded half up);
        # to_alpha5 raises for a catalog number the TLE field cannot carry, which is the correct answer
        return tlemod.render(tlemod.omm_fields_from_record(record), mantissa_mode="round", ecc_mode="truncate")

    def alpha5_decode(self, field):
        if len(field) != 5 or field != field.strip():
            raise ValueError("field must be five characters")
        return tlemod.from_alpha5(field)

    def alpha5_encode(self, n):
        return tlemod.to_alpha5(n)

    def two_digit_year(self, yy):
        return ref.two_digit_year(yy)

    def parse_catalog_id(self, text):
        import re
        s = text.strip()
        if not re.fullmatch(r"\+?\d{1,9}", s):  # CCSDS: integer of up to nine digits; KVN allows a leading sign and zeros
            raise ValueError(f"not a NORAD_CAT_ID: {text!r}")
        return int(s)

    def parse_epoch(self, text):
        import re
        m = re.fullmatch(r"(\d{4})-(?:(\d{2})-(\d{2})|(\d{3}))T(\d{2}):(\d{2}):(\d{2})(\.\d+)?Z?", text)
        if not m:
            raise ValueError(text)
        s = text.rstrip("Z")
        frac = m.group(8) or ""
        base = s[: len(s) - len(frac)]
        fmt = "%Y-%jT%H:%M:%S" if m.group(4) else "%Y-%m-%dT%H:%M:%S"
        try:
            t = dt.datetime.strptime(base, fmt)
        except ValueError:
            if base.endswith(":60"):  # leap second: valid per CCSDS, not representable in datetime
                t = dt.datetime.strptime(base[:-3] + ":59", fmt)
            else:
                raise
        if frac:
            t = t + dt.timedelta(microseconds=int(round(float("0" + frac) * 1e6)))
        return t
