# Contributed by SM-26 in https://github.com/hneogy/gp-omm-conformance/issues/1 and kept verbatim below this header and
# the docstring's credit. It is SM-26's work, not NEOGY LLC's, and it is not covered by the project's licence, pending
# SM-26's permission.
"""Wrong-on-purpose adapters by SM-26, who answered the audit ask of issue #1 with them (2026-10-09) and chose
to be credited as SM-26: https://github.com/hneogy/gp-omm-conformance/issues/1 — kept verbatim but for this header.
On gpconf 0.6.1 the seven suspects passed the five no-data cases with zero fails; D-280 to D-283 fail every one.

Each class is the corpus's own reference Parser with one deliberate bug, so any pass it earns is the bug getting through.
Suspects (S1-S6) are bugs the runner may miss; controls (C1-C7) are bugs it should catch. Several suspects have a
twin that differs only in where or how the bug shows, so the report shows that, not the bug, decides the verdict.
"""
from decimal import Decimal

from gpconf import tle as tlemod
from gpconf.adapters.reference import Parser as Ref
from gpconf.runner import Unsupported

LETTERS = tlemod.ALPHA5_LETTERS


def remap_ids(recs, decode):
    """Re-decode every Alpha-5 catalog field with `decode`, as a parser with that decoder would have read it."""
    for r in recs:
        n = r.get("norad_cat_id")
        if "_refused" not in r and isinstance(n, int) and 100000 <= n <= 339999:
            r["norad_cat_id"] = decode(tlemod.to_alpha5(n))
    return recs


def shifted_letter_writer(record):
    """A TLE writer whose Alpha-5 letter is one too high (A -> B): valid checksums, wrong catalog field."""
    f = tlemod.omm_fields_from_record(record)
    n = int(f["NORAD_CAT_ID"])
    field = tlemod.to_alpha5(n)  # raises for 340000+ and negatives, as the correct writer does
    if n >= 100000:
        field = LETTERS[LETTERS.index(field[0]) + 1] + field[1:]
    return tlemod.render(f, catnum_field=field, mantissa_mode="round", ecc_mode="truncate")


# ---------------------------------------------------------------- S1 writer: Unsupported on the first number it can't write
class S1WriterDodge(Ref):
    def write_tle(self, record):
        if not 0 <= int(record["norad_cat_id"]) <= 339999:
            raise Unsupported("tle-writing")  # instead of refusing the record
        return shifted_letter_writer(record)


class S1WriterDodgeTwin(Ref):  # same wrong writer, refuses honestly: should fail
    def write_tle(self, record):
        return shifted_letter_writer(record)


# ---------------------------------------------------------------- S2 a "library" that raises on files it can't read
def strict_library(ref_out):
    """Raises where a strict library would: any record the reference refuses, any Alpha-5 letter past H."""
    for r in ref_out:
        if "_refused" in r:
            raise ValueError(f"bad record: {r['_refused']}")
        n = r.get("norad_cat_id")
        if isinstance(n, int) and n >= 180000:  # letters J..Z
            raise ValueError(f"unknown Alpha-5 letter in {tlemod.to_alpha5(n)}")
    return ref_out


class S2FileDodge(Ref):  # adapter maps the library's error to Unsupported
    def parse(self, raw, fmt):
        try:
            return strict_library(super().parse(raw, fmt))
        except ValueError as e:
            raise Unsupported(f"{fmt}: {e}")


class S2FileDodgeTwin(Ref):  # same library, error passed on: should fail
    def parse(self, raw, fmt):
        return strict_library(super().parse(raw, fmt))


# ---------------------------------------------------------------- S3 a second, wrong copy of every record
def wrong_copy(r):
    c = dict(r)
    c["mean_anomaly"] = str(Decimal(str(r["mean_anomaly"])) + 1)
    return c


class S3DuplicateTail(Ref):  # right copy first, wrong copy after
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        return out + [wrong_copy(r) for r in out if "_refused" not in r]


class S3DuplicateHead(Ref):  # wrong copy first: should fail
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        return [wrong_copy(r) for r in out if "_refused" not in r] + out


# ---------------------------------------------------------------- S4 parse path with a table that stops at T
def decode_table_ends_at_t(field):
    """A decoder whose letter table was typed as A..T: U..Z fall back to the first letter's value."""
    table = LETTERS[: LETTERS.index("T") + 1]
    c = field[0]
    if c.isdigit():
        return int(field)
    return ((table.index(c) if c in table else 0) + 10) * 10000 + int(field[1:])


class S4SplitDecoder(Ref):  # parse uses the bad table; the alpha5_decode hook stays correct
    def parse(self, raw, fmt):
        return remap_ids(super().parse(raw, fmt), decode_table_ends_at_t)


class S4SplitDecoderTwin(Ref):  # the hook uses the same bad table: should fail
    def parse(self, raw, fmt):
        return remap_ids(super().parse(raw, fmt), decode_table_ends_at_t)

    def alpha5_decode(self, field):
        super().alpha5_decode(field)  # same validation as the reference
        return decode_table_ends_at_t(field)


# ---------------------------------------------------------------- S5 catalog numbers that are not ints
class S5FloatIds(Ref):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        for r in out:
            if "_refused" not in r and isinstance(r.get("norad_cat_id"), int):
                r["norad_cat_id"] = float(r["norad_cat_id"])
        return out


class S5StrIds(Ref):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        for r in out:
            if "_refused" not in r and isinstance(r.get("norad_cat_id"), int):
                r["norad_cat_id"] = str(r["norad_cat_id"])
        return out


class S5FloatIdsHook(Ref):  # the same float, through the vectors' parse_catalog_id: should fail
    def parse_catalog_id(self, text):
        return float(super().parse_catalog_id(text))


# ---------------------------------------------------------------- S6 corrupt record dropped, an unrelated refusal left
class S6StrayRefusal(Ref):
    def parse(self, raw, fmt):
        out = [r for r in super().parse(raw, fmt) if "_refused" not in r]  # corrupt record dropped silently
        return [{"_adapter": {"refusals": True}}, {"_refused": "skipped a comment line", "_field": "#####"}] + out


class S6SilentDrop(Ref):  # the same drop with no stray refusal: should fail
    def parse(self, raw, fmt):
        return [{"_adapter": {"refusals": True}}] + [r for r in super().parse(raw, fmt) if "_refused" not in r]


# ---------------------------------------------------------------- controls: ordinary bugs the runner should catch
def decode_no_io_skip(field):
    c = field[0]
    if c.isdigit():
        return int(field)
    return (ord(c) - ord("A") + 10) * 10000 + int(field[1:])


class C1NoIOSkip(Ref):
    def parse(self, raw, fmt):
        return remap_ids(super().parse(raw, fmt), decode_no_io_skip)

    def alpha5_decode(self, field):
        return decode_no_io_skip(field)

    def alpha5_encode(self, n):
        if n < 100000:
            return super().alpha5_encode(n)
        if not 0 <= n <= 339999:
            raise ValueError(n)
        hi, lo = divmod(n, 10000)
        return f"{chr(ord('A') + hi - 10)}{lo:04d}"


def decode_off_by_one(field):
    return tlemod.from_alpha5(field) + (10000 if field[0].isalpha() else 0)  # A = 11


class C2OffByOne(Ref):
    def parse(self, raw, fmt):
        return remap_ids(super().parse(raw, fmt), decode_off_by_one)

    def alpha5_decode(self, field):
        return decode_off_by_one(field)


class C3Pivot58(Ref):
    def two_digit_year(self, yy):
        y = int(yy)
        return 1900 + y if y >= 58 else 2000 + y


class C4NanId(Ref):
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        for r in out:
            if "_refused" not in r and isinstance(r.get("norad_cat_id"), int) and r["norad_cat_id"] >= 100000:
                r["norad_cat_id"] = float("nan")
        return out


class C5Crash(Ref):
    def parse(self, raw, fmt):
        raise RuntimeError("segfault, more or less")

    def write_tle(self, record):
        raise RuntimeError("segfault, more or less")


class C6Lenient(Ref):
    def alpha5_decode(self, field):
        f = field.strip().upper().replace("I", "J").replace("O", "P").rjust(5, "0")
        return tlemod.from_alpha5(f[:5])


class C7PlausibleWrong(Ref):  # every value right but the eccentricity, read as a float 1e-9 off
    def parse(self, raw, fmt):
        out = super().parse(raw, fmt)
        for r in out:
            if "_refused" not in r and r.get("eccentricity") not in (None, ""):
                r["eccentricity"] = float(r["eccentricity"]) * (1 + 1e-9)
        return out
