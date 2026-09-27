"""Preset `reference`: the corpus's own readers, the control. It passes every case that exercises a parser, since it
produced the expected values. Standard library only."""
import datetime as dt

from gpconf import reference as ref
from gpconf import tle as tlemod
from gpconf.runner import CORE_FIELDS, OPTIONAL_FIELDS

FMT = {"tle": ref.read_tle_text, "2le": ref.read_tle_text}


class Parser:
    def parse(self, raw, fmt):
        text = raw.decode("utf-8")
        if fmt in ("tle", "2le"):
            recs = tle_sets(text)
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
            d = r if "_refused" in r else {k: r.get(k) for k in CORE_FIELDS + OPTIONAL_FIELDS if r.get(k) is not None or k in CORE_FIELDS}
            out.append(d)  # a refusal (D-144) is passed on as it is
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


def tle_sets(text):
    """The reference reader's pairing (read_tle_text), one set at a time, so that a set the strict reader rejects comes
    back as a refusal with the reader's reason and the sets after it still load; a line 1 with no line 2 after it, or a
    line 2 with no line 1 before it, is refused too, where read_tle_text passes over it (D-171). A valid file gives
    exactly read_tle_text's records."""
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            l0 = lines[i - 1] if i > 0 and lines[i - 1][:2] not in ("1 ", "2 ") else None
            try:
                out.append(ref.parse_tle_lines(l0, line, lines[i + 1]))
            except ValueError as e:
                out.append({"_refused": f"ValueError: {e}", "_field": line[2:7], "_input": line[:80]})
            i += 2
            continue
        if line.startswith("1 "):
            out.append({"_refused": "a line 1 with no line 2 after it", "_field": line[2:7], "_input": line[:80]})
        elif line.startswith("2 "):
            out.append({"_refused": "a line 2 with no line 1 before it", "_field": line[2:7], "_input": line[:80]})
        i += 1
    return out
