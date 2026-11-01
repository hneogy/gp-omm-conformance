# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""Property-based tests (D-320, from the hardening review of 2026-10-11): what holds for EVERY input of a kind, where
the vector files hold a chosen few. Alpha-5 encoding and decoding, the two-digit year pivot, epoch reading, catalog-id
text, the element-value grammar and the TLE checksum: round trips, bounds, and refusal of what is not valid. And the
reference reader (D-336): whatever bytes a provider file holds, it reads them or refuses them in words, and so does
check-tle; nothing else may come of them. The nightly workflow runs those three at GPCONF_READER_PROPERTY_EXAMPLES,
and every property with a new seed each night (GPCONF_PROPERTY_RANDOM).
And the parser's guard (D-337): whatever an adapter returns, only plain built-in values leave it; the types real
libraries return read as their plain equivalents; and a structure that shares its parts ends in words through every
route an answer takes (GPCONF_ROUTES_PROPERTY_EXAMPLES, 20 by default).

They need Hypothesis, a test-only dependency (`pip install "gpconf[test]"`, or `pip install hypothesis`); the package
itself needs nothing. Without it each test is skipped by name, so a run says what it left out; and where
GPCONF_REQUIRE_HYPOTHESIS is set, as it is in CI, its absence is an error and the run fails: these tests do not skip
silently where they are meant to run (D-322). Examples per property: 100, or GPCONF_PROPERTY_EXAMPLES (the nightly
workflow runs 2,000). Properties the review found NOT to hold are not here; they are listed for the next release.

Run: python -m unittest tests.test_properties"""
import collections
import dataclasses
import datetime as dt
import os
import string
import sys
import types
import unittest
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from hypothesis import assume, given, settings, strategies as st
    from hypothesis.configuration import set_hypothesis_home_dir
    import tempfile
    set_hypothesis_home_dir(tempfile.mkdtemp(prefix="gpconf-hypothesis-"))   # nothing is written into the tree
except ImportError:
    if os.environ.get("GPCONF_REQUIRE_HYPOTHESIS"):
        raise ImportError("Hypothesis is not installed and GPCONF_REQUIRE_HYPOTHESIS is set: the property tests must run here "
                          "(pip install hypothesis)")
    # elsewhere every test below is skipped, one by one, so the module loads and reports them as skips
    class _Anything:
        def __call__(self, *a, **k):
            return self

        def __getattr__(self, name):
            return self
    st = _Anything()

    def given(*a, **k):
        return unittest.skip("Hypothesis is not installed")

    def settings(**k):
        return lambda f: f

    def assume(condition):
        return True

from gpconf import plain  # noqa: E402
from gpconf import reference as ref  # noqa: E402
from gpconf import tle  # noqa: E402
from gpconf.adapters.reference import Parser  # noqa: E402
from gpconf.runner import PLAIN_DECIMAL, norm_epoch, norm_record  # noqa: E402

P = Parser()
# CI runs the same examples every time; the nightly workflow sets GPCONF_PROPERTY_RANDOM, so each night explores new
# ones, and a failure prints the blob that reproduces it (D-336, the sixth reading: a fixed seed repeated the same
# 20,000 examples every night).
FIXED = os.environ.get("GPCONF_PROPERTY_RANDOM") != "1"
N = settings(max_examples=int(os.environ.get("GPCONF_PROPERTY_EXAMPLES", "100")), deadline=None, derandomize=FIXED, database=None,
             print_blob=True)
DIGITS = "0123456789"
LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
OTHER_DIGITS = str.maketrans(DIGITS, "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669")
DATETIMES = st.datetimes(min_value=dt.datetime(1957, 1, 1), max_value=dt.datetime(2056, 12, 31, 23, 59, 59, 999999))
LINE_CHARS = DIGITS + string.ascii_uppercase + " .+-"


class Alpha5(unittest.TestCase):
    @N
    @given(st.integers(min_value=0, max_value=339999))
    def test_round_trip(self, n):
        f = tle.to_alpha5(n)
        self.assertEqual(len(f), 5)
        self.assertTrue(all(c in DIGITS for c in f[1:]) and (f[0] in DIGITS or f[0] in LETTERS))
        self.assertEqual((tle.from_alpha5(f), P.alpha5_decode(f), P.alpha5_encode(n)), (n, n, f))

    @N
    @given(st.integers(min_value=0, max_value=339998))
    def test_the_next_number_is_the_next_field(self, n):
        self.assertEqual(tle.from_alpha5(tle.to_alpha5(n)) + 1, tle.from_alpha5(tle.to_alpha5(n + 1)))

    @N
    @given(st.one_of(st.integers(max_value=-1), st.integers(min_value=340000)))
    def test_encode_refuses_what_the_field_cannot_carry(self, n):
        for fn in (tle.to_alpha5, P.alpha5_encode):
            with self.assertRaises(ValueError):
                fn(n)

    @N
    @given(st.one_of(st.text(max_size=8), st.text(alphabet=string.ascii_letters + string.digits + " -+.", min_size=5, max_size=5)))
    def test_decode_accepts_exactly_the_definition(self, s):
        ok = len(s) == 5 and (s[0] in DIGITS or s[0] in LETTERS) and all(c in DIGITS for c in s[1:])
        for fn in (tle.from_alpha5, P.alpha5_decode):
            if ok:
                self.assertEqual(tle.to_alpha5(fn(s)), s)
            else:
                with self.assertRaises(ValueError):
                    fn(s)


class TwoDigitYear(unittest.TestCase):
    @N
    @given(st.integers(min_value=0, max_value=99))
    def test_the_pivot_is_57(self, yy):
        y = ref.two_digit_year(yy)
        self.assertEqual(y, 1900 + yy if yy >= 57 else 2000 + yy)
        self.assertTrue(1957 <= y <= 2056)
        self.assertEqual((ref.two_digit_year(f"{yy:02d}"), P.two_digit_year(f"{yy:02d}")), (y, y))


class Epochs(unittest.TestCase):
    @N
    @given(DATETIMES)
    def test_calendar_round_trip(self, t):
        text = t.strftime("%Y-%m-%dT%H:%M:%S.%f")
        self.assertEqual((tle.iso_epoch(text), norm_epoch(t), norm_epoch(text)), (text, text, text))
        self.assertEqual((P.parse_epoch(text), P.parse_epoch(text + "Z")), (t, t))

    @N
    @given(DATETIMES)
    def test_day_of_year_is_the_same_instant(self, t):
        doy = t.strftime("%Y-%jT%H:%M:%S.%f")
        self.assertEqual(tle.iso_epoch(doy), t.strftime("%Y-%m-%dT%H:%M:%S.%f"))
        self.assertEqual(P.parse_epoch(doy), t)

    @N
    @given(DATETIMES, st.integers(min_value=-14 * 60, max_value=14 * 60))
    def test_an_offset_is_converted_to_utc(self, t, minutes):
        text = t.strftime("%Y-%m-%dT%H:%M:%S.%f") + f"{'+' if minutes >= 0 else '-'}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"
        self.assertEqual(tle.iso_epoch(text), (t - dt.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.%f"))

    @N
    @given(DATETIMES, st.text(alphabet=DIGITS, min_size=1, max_size=12))
    def test_a_fraction_of_any_length_lands_within_half_a_microsecond(self, t, frac):
        t = t.replace(microsecond=0)
        got = dt.datetime.strptime(tle.iso_epoch(t.strftime("%Y-%m-%dT%H:%M:%S") + "." + frac), "%Y-%m-%dT%H:%M:%S.%f")
        self.assertLessEqual(abs(Decimal((got - t) // dt.timedelta(microseconds=1)) - Decimal("0." + frac) * 1_000_000), Decimal("0.5"))

    @N
    @given(st.one_of(st.text(max_size=30), st.text(alphabet=DIGITS + "-T:.Z+ ", max_size=30)))
    def test_a_reader_raises_valueerror_or_nothing(self, s):
        for fn in (tle.iso_epoch, P.parse_epoch):
            try:
                fn(s)
            except ValueError:
                pass

    @N
    @given(DATETIMES)
    def test_the_digits_of_another_script_are_refused(self, t):                 # D-319
        with self.assertRaises(ValueError):
            tle.iso_epoch(t.strftime("%Y-%m-%dT%H:%M:%S").translate(OTHER_DIGITS))

    @N
    @given(st.integers(min_value=1957, max_value=2056), st.integers(min_value=0, max_value=400))
    def test_the_runner_s_reader_holds_the_day_of_year_to_the_year(self, year, doy):
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        if 1 <= doy <= (366 if leap else 365):
            tle.iso_epoch(f"{year}-{doy:03d}T00:00:00")
        else:
            with self.assertRaises(ValueError):
                tle.iso_epoch(f"{year}-{doy:03d}T00:00:00")


class CatalogIdText(unittest.TestCase):
    @N
    @given(st.integers(min_value=0, max_value=999999999))
    def test_round_trip(self, n):
        self.assertEqual((P.parse_catalog_id(str(n)), P.parse_catalog_id(f"{n:09d}")), (n, n))

    @N
    @given(st.text(alphabet=string.printable, max_size=12))
    def test_ascii_text_is_accepted_only_as_up_to_nine_digits(self, s):
        t = s.strip()
        body = t[1:] if t.startswith("+") else t
        ok = 1 <= len(body) <= 9 and all(c in DIGITS for c in body)
        if ok:
            self.assertEqual(P.parse_catalog_id(s), int(body))
        else:
            with self.assertRaises(ValueError):
                P.parse_catalog_id(s)


class ElementValueText(unittest.TestCase):                                      # D-319
    @N
    @given(st.decimals(allow_nan=False, allow_infinity=False, places=8, min_value=-1000, max_value=1000))
    def test_a_plain_decimal_string_is_read_as_its_value(self, d):
        out, _, bad = norm_record({"mean_motion": str(d)})
        self.assertEqual((out["mean_motion"], bad), (d, {}))

    @N
    @given(st.text(max_size=14))
    def test_text_is_read_only_if_it_is_a_plain_ascii_decimal(self, s):
        assume(s != "")
        if PLAIN_DECIMAL.fullmatch(s):
            self.assertTrue(s.isascii() and s == s.strip() and "_" not in s)
            out, _, bad = norm_record({"mean_motion": s})
            self.assertEqual((out["mean_motion"], bad), (Decimal(s), {}))
        else:
            with self.assertRaises(ValueError):
                norm_record({"mean_motion": s})


class Checksum(unittest.TestCase):
    @N
    @given(st.text(alphabet=LINE_CHARS, min_size=68, max_size=68))
    def test_the_definition(self, line):
        want = (sum(int(c) for c in line if c in DIGITS) + line.count("-")) % 10
        self.assertEqual((tle.checksum(line), tle.checksum(line + "7")), (want, want))      # column 69 is the checksum itself

    @N
    @given(st.text(alphabet=LINE_CHARS, min_size=68, max_size=68), st.integers(min_value=0, max_value=67), st.sampled_from(DIGITS),
           st.sampled_from(DIGITS))
    def test_any_single_digit_change_is_detected(self, line, i, old, d):
        # the digit is put at the column, not hoped for: a filter on a random column's character threw away four inputs in
        # five, and a random seed tripped Hypothesis's health check (D-337's gates, 2026-10-16)
        assume(old != d)
        line = line[:i] + old + line[i + 1:]
        self.assertNotEqual(tle.checksum(line[:i] + d + line[i + 1:]), tle.checksum(line))


READER_N = settings(max_examples=int(os.environ.get("GPCONF_READER_PROPERTY_EXAMPLES", os.environ.get("GPCONF_PROPERTY_EXAMPLES", "100"))),
                    deadline=None, derandomize=FIXED, database=None, print_blob=True)


def _valid_files():
    """One valid file per format, written from the frozen 1998 ISS record (the strict-files test's builders)."""
    from tests.adversarial import test_strict_files_080 as S
    return {"csv": S.csv_text(), "json": S.json_text(), "xml": S.xml_text(), "kvn": S.kvn_text(), "tle": S.tle_text(),
            "2le": "\n".join(S.tle_text().splitlines()[1:]) + "\n"}


# What an edit puts in: a few bytes of any value, or a piece that means something to one of the formats (a line break of
# another kind, a no-break space, a quote, markup, an exponent past any value, a DOS end-of-file mark, a BOM), which
# random bytes would seldom spell.
_PIECES = [b"\r", b"\n", b"\r\n", b"\n\r", b"\t", b"\x0c", b"\x1a", "\u00a0".encode(), "\u2028".encode(), b"\xef\xbb\xbf",
           b"E9999999999", b"E-9999999999", b"9" * 5000, b"NaN", b"Infinity", b"-", b"+", b".", b"0", b"_", b'"', b",", b"=",
           b"[", b"]", b"{", b"}", b":", b"null", b"true", b"<", b">", b"&", b"&#0;", b"<![CDATA[x]]>", b"<!-- -->",
           b' units="deg"', b" [rev/day]", b"COMMENT x\n", b"CCSDS_OMM_VERS = 2.0\n", b"1 ", b"2 ", b"0 ", b"Z", b"T", b"60",
           "\u0661".encode()]
_EDITS = st.lists(st.tuples(st.integers(min_value=0, max_value=4000), st.sampled_from(["insert", "delete", "replace"]),
                            st.one_of(st.binary(min_size=1, max_size=4), st.sampled_from(_PIECES))), min_size=1, max_size=6)


def _edited(data, edits):
    for pos, how, b in edits:
        pos = pos % (len(data) + 1)
        if how == "insert":
            data = data[:pos] + b + data[pos:]
        elif how == "delete":
            data = data[:pos] + data[pos + len(b):]
        else:
            data = data[:pos] + b + data[pos + len(b):]
    return data


def _bytes_for(ext, raw, edits):
    return raw if raw is not None else _edited(_valid_files()[ext].encode("utf-8"), edits)


class ReaderOnAnyBytes(unittest.TestCase):                                      # D-336
    """Whatever bytes a provider file holds, the reference reader reads records from them or refuses the file in words
    (a ValueError naming what is wrong); no other exception, which the runner would report as an error of the corpus,
    and check-tle as a traceback (the owner's ruling on the fifth reading of D-336). The bytes are a valid file with a
    few bytes, or a piece that means something to a format, inserted, deleted or replaced; or bytes from nowhere."""

    @READER_N
    @given(st.sampled_from(["csv", "json", "xml", "kvn", "tle", "2le"]), st.one_of(st.none(), st.binary(max_size=400)), _EDITS)
    def test_the_reader_reads_or_refuses_in_words(self, ext, raw, edits):
        import tempfile
        data = _bytes_for(ext, raw, edits)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "f." + ext)
            with open(path, "wb") as f:
                f.write(data)
            try:
                ref.read_file(path)
            except ValueError:
                pass

    @READER_N
    @given(st.sampled_from(["csv", "json", "xml", "kvn", "tle"]), st.one_of(st.none(), st.binary(max_size=400)), _EDITS,
           st.one_of(st.none(), st.binary(max_size=400)), _EDITS)
    def test_check_tle_exits_0_1_or_2_whatever_the_bytes(self, ext, raw, edits, wraw, wedits):
        import contextlib
        import io
        import tempfile
        from gpconf.__main__ import main
        with tempfile.TemporaryDirectory() as d:
            src, written = os.path.join(d, "s." + ext), os.path.join(d, "w.tle")
            with open(src, "wb") as f:
                f.write(_bytes_for(ext, raw, edits))
            with open(written, "wb") as f:
                f.write(_bytes_for("tle", wraw, wedits))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = main(["check-tle", written, "--against", src])
            self.assertIn(rc, (0, 1, 2))

    @READER_N
    @given(st.sampled_from(["csv", "json", "xml", "kvn"]), st.sampled_from(["MEAN_MOTION", "BSTAR", "MEAN_MOTION_DDOT"]),
           st.from_regex(r"\A[+-]?([0-9]{1,4}(\.[0-9]{0,4})?|\.[0-9]{1,4})\Z"), st.integers(-10 ** 30, 10 ** 30))
    def test_a_number_with_any_exponent_reads_or_is_refused_in_words(self, ext, key, mantissa, exponent):
        """A number of the plain grammar with an exponent of any size, in each OMM format: random bytes seldom spell
        one, and one with an exponent past what Decimal() holds raised decimal.InvalidOperation (the sixth reading of D-336)."""
        from tests.adversarial import test_strict_files_080 as S
        text = {"csv": S.csv_text, "json": S.json_text, "xml": S.xml_text, "kvn": S.kvn_text}[ext](**{key: f"{mantissa}E{exponent}"})
        reader = {"csv": ref.read_csv_text, "json": ref.read_json_text, "xml": ref.read_xml_text, "kvn": ref.read_kvn_text}[ext]
        try:
            reader(text)
        except ValueError:
            pass


class _LiarStr(str):
    __hash__ = str.__hash__

    def __eq__(self, other):
        return True

    def strip(self, *a):
        return ""


class _LiarInt(int):
    __hash__ = int.__hash__

    def __eq__(self, other):
        return True

    def __int__(self):
        return 7


class _LiarFloat(float):
    def __repr__(self):
        return "1.5"

    def __float__(self):
        return 1.5


class _LiarDecimal(Decimal):
    def __str__(self):
        return "1.5"


class _When(dt.datetime):
    def strftime(self, fmt):
        return _LiarStr("no epoch")


class _Delta(dt.timedelta):
    def __repr__(self):
        return "no offset"


class _LiarList(list):
    def __iter__(self):
        return iter(list(list.__iter__(self))[:1])


class _LiarDict(dict):
    def __getitem__(self, k):
        return "x"

    def keys(self):
        return ["shown"] + list(dict.keys(self))


class _Own:
    def __init__(self, text):
        self.text = text

    def __str__(self):
        return _LiarStr(self.text)


class _Proxy:
    """A transparent proxy (wrapt's ObjectProxy pattern): isinstance() sees what it wraps, type() does not."""
    __slots__ = ("__wrapped__",)

    def __init__(self, w):
        object.__setattr__(self, "__wrapped__", w)

    @property
    def __class__(self):
        return type(self.__wrapped__)

    def __getattr__(self, n):
        return getattr(self.__wrapped__, n)

    def __str__(self):
        return _LiarStr(str(self.__wrapped__))

    def __iter__(self):
        return iter(self.__wrapped__)

    def __len__(self):
        return len(self.__wrapped__)

    def __getitem__(self, k):
        return self.__wrapped__[k]

    def __index__(self):
        return self.__wrapped__.__index__()

    def __bool__(self):
        return bool(self.__wrapped__)


_SCALARS = st.one_of(st.none(), st.booleans(), st.integers(), st.floats(), st.text(max_size=8),
                     st.decimals(allow_nan=True), st.datetimes(), st.binary(max_size=4), st.datetimes(timezones=st.timezones()))
_ODD = st.one_of(st.builds(_LiarStr, st.text(max_size=8)), st.builds(_LiarInt, st.integers()),
                 st.builds(_LiarFloat, st.floats()), st.builds(_LiarDecimal, st.decimals(allow_nan=False)),
                 st.datetimes().map(lambda d: _When(d.year, d.month, d.day, d.hour, d.minute, d.second, d.microsecond)),
                 st.builds(_Own, st.text(max_size=8)),
                 st.builds(lambda h, s: dt.timezone(_Delta(hours=h), _LiarStr(s or "x")), st.integers(-23, 23), st.text(max_size=4)))
_KEYS = st.one_of(st.text(max_size=6), st.builds(_LiarStr, st.text(max_size=6)), st.integers(), st.binary(max_size=3))
_ANYTHING = st.recursive(st.one_of(_SCALARS, _ODD), lambda inner: st.one_of(
    st.lists(inner, max_size=4), st.lists(inner, max_size=4).map(tuple), st.lists(inner, max_size=4).map(_LiarList),
    st.dictionaries(_KEYS, inner, max_size=4), st.dictionaries(st.text(max_size=6), inner, max_size=4).map(_LiarDict),
    inner.map(_Proxy), st.lists(inner, max_size=4).map(collections.deque),
    st.dictionaries(st.text(max_size=6), inner, max_size=4).map(types.MappingProxyType)),
    max_leaves=12)
_PLAIN_SCALARS = st.one_of(st.none(), st.booleans(), st.integers(), st.floats(), st.text(max_size=8), st.binary(max_size=4),
                           st.decimals(allow_nan=True), st.datetimes(),
                           st.datetimes(timezones=st.builds(dt.timezone, st.timedeltas(min_value=dt.timedelta(hours=-23),
                                                                                      max_value=dt.timedelta(hours=23)))))
_PLAIN = st.recursive(_PLAIN_SCALARS, lambda inner: st.one_of(st.lists(inner, max_size=4), st.lists(inner, max_size=4).map(tuple),
                                                        st.dictionaries(st.text(max_size=6), inner, max_size=4)), max_leaves=12)


class PlainBoundary(unittest.TestCase):                                         # D-337
    @N
    @given(_ANYTHING)
    def test_only_plain_built_in_values_leave_the_guard(self, x):
        """Whatever an adapter returns, the guard's reading of it holds nothing but plain built-in values (and the
        runner's own Problem), so no method of the adapter's own runs after the guard."""
        self.assertTrue(plain.is_plain(plain.value(x)))
        self.assertTrue(plain.is_plain(plain.answer([x, {"v": x}])))

    @N
    @given(_PLAIN)
    def test_a_plain_value_reads_as_itself(self, x):
        """The reading changes nothing an honest adapter returns as plain values."""
        self.assertEqual(repr(plain.value(x)), repr(x))



# Real-world types (the owner's ruling on D-337's stopping rule): the types real libraries hand back, each beside its plain
# equivalent. numpy's and pandas' join when they can be imported; the nightly workflow installs both and names them in
# GPCONF_REAL_TYPES, where a missing one is an error, so they cannot drop out silently there.
REAL_N = settings(max_examples=int(os.environ.get("GPCONF_REAL_TYPES_EXAMPLES", os.environ.get("GPCONF_PROPERTY_EXAMPLES", "100"))),
                  deadline=None, derandomize=FIXED, database=None, print_blob=True)


def _optional(name):
    try:
        return __import__(name)
    except ImportError:
        if name in os.environ.get("GPCONF_REAL_TYPES", "").split(","):
            raise
        return None


_np, _pd = _optional("numpy"), _optional("pandas")


@dataclasses.dataclass
class _Sighting:   # an object of the library's own under a key no check reads
    where: str
    when: dt.datetime


_Pass = collections.namedtuple("_Pass", "rise culminate set")


class _HonestDict(dict):
    """A record type that shows what it holds (an attribute-style record)."""
    def __getattr__(self, k):
        return self[k]


def _real_forms():
    """For each graded field, the forms a real library may give its value in, each a function of the plain value."""
    ints = [lambda n: n]
    epochs = [lambda t: t.isoformat(timespec="microseconds"), lambda t: t,
              lambda t: t.replace(tzinfo=dt.timezone.utc),
              lambda t: t.replace(tzinfo=dt.timezone.utc).astimezone(dt.timezone(dt.timedelta(hours=5, minutes=30)))]
    decimals = [lambda s: s, lambda s: Decimal(s), lambda s: float(s)]
    texts = [lambda s: s]
    if _np is not None:
        ints += [lambda n: _np.int64(n), lambda n: _np.int32(n), lambda n: _np.uint32(n)]
        epochs += [lambda t: _np.datetime64(t.isoformat(timespec="microseconds"), "us")]
        decimals += [lambda s: _np.float64(float(s))]
        texts += [lambda s: _np.str_(s)]
    if _pd is not None:
        epochs += [lambda t: _pd.Timestamp(t), lambda t: _pd.Timestamp(t.replace(tzinfo=dt.timezone.utc)),
                   lambda t: _pd.Timestamp(t.replace(tzinfo=dt.timezone.utc)).tz_convert(dt.timezone(dt.timedelta(hours=-7)))]
    return {"int": ints, "epoch": epochs, "decimal": decimals, "text": texts}


def _extras():
    """Values under keys no check reads, of the kinds real libraries keep beside the fields."""
    out = [_Sighting("Seattle", dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)), _Pass(1, 2, 3), Decimal("NaN"),
           types.MappingProxyType({"source": "celestrak"}), collections.OrderedDict(a=1), dt.timedelta(seconds=5)]
    if _np is not None:
        out += [_np.timedelta64(5, "s"), _np.array([1.5, 2.5]), _np.bool_(True), _np.float32(1.5)]
    if _pd is not None:
        out += [_pd.Timedelta(seconds=5), _pd.Timestamp("2026-01-01T00:00:00Z")]
    return out


_CONTAINERS = [dict, collections.OrderedDict, lambda d: types.MappingProxyType(dict(d)), _HonestDict]
_ANSWERS = [list, tuple, lambda rs: (r for r in rs)]
_GRADED = {"norad_cat_id": "int", "element_set_no": "int", "rev_at_epoch": "int", "epoch": "epoch", "mean_motion": "decimal",
           "eccentricity": "decimal", "inclination": "decimal", "object_name": "text", "object_id": "text"}


@st.composite
def _real_and_plain(draw):
    forms = _real_forms()
    plain_rec = {"norad_cat_id": draw(st.integers(1, 339999)), "element_set_no": draw(st.integers(0, 9999)),
                 "rev_at_epoch": draw(st.integers(0, 99999)),
                 "epoch": draw(st.datetimes(min_value=dt.datetime(1957, 10, 4), max_value=dt.datetime(2099, 12, 31))),
                 "mean_motion": f"{draw(st.integers(1, 1799999999)) / 1e8:.8f}", "eccentricity": f"0.{draw(st.integers(0, 9999999)):07d}",
                 "inclination": f"{draw(st.integers(0, 1800000)) / 1e4:.4f}",
                 "object_name": draw(st.text(alphabet=string.ascii_uppercase + string.digits + " ()-", min_size=1, max_size=24)),
                 "object_id": f"{draw(st.integers(1957, 2099))}-{draw(st.integers(1, 999)):03d}A"}
    real = {k: draw(st.sampled_from(forms[_GRADED[k]]))(v) for k, v in plain_rec.items()}
    for i, extra in enumerate(draw(st.lists(st.sampled_from(_extras()), max_size=4))):
        real[f"_extra{i}"] = extra
    plain_rec["epoch"] = plain_rec["epoch"].isoformat(timespec="microseconds")
    container, answer = draw(st.sampled_from(_CONTAINERS)), draw(st.sampled_from(_ANSWERS))
    return answer([container(real)]), [plain_rec]


class RealWorldTypes(unittest.TestCase):                                        # D-337
    @REAL_N
    @given(_real_and_plain())
    def test_real_world_types_read_as_their_plain_equivalents(self, pair):
        """A record built from the types real libraries return (numpy's scalars and timedelta64, pandas' Timestamp, a
        dataclass, a namedtuple, an OrderedDict, a MappingProxyType, aware datetimes, Decimal) reads, field by field
        where the checks look, as the same record written in plain values; and in a bounded time. The owner's ruling
        on D-337's stopping rule: a false fail on the types real libraries return is never negligible."""
        import time
        from gpconf.runner import norm_record
        real, plain_answer = pair
        start = time.monotonic()
        got = plain.answer(real)
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 2.0)
        self.assertEqual(len(got), 1)
        self.assertIs(type(got[0]), dict, got[0])
        want = norm_record(plain.answer(plain_answer)[0])[0]
        have = norm_record(got[0])[0]
        for k in _GRADED:
            self.assertEqual(have.get(k), want.get(k), (k, real))


ROUTES_N = settings(max_examples=int(os.environ.get("GPCONF_ROUTES_PROPERTY_EXAMPLES", "20")), deadline=None,
                    derandomize=FIXED, database=None, print_blob=True)


class _Shared(list):   # a list subclass that shows what it holds
    pass


class _Holder(collections.deque):   # a subclass of deque, which Python writes with deque's own walk
    pass


class _OwnError(Exception):   # an exception of the parser's own whose text is Python's (BaseException.__str__)
    pass


def _bomb(shape, levels, wrap):
    """A structure that shares its parts: `levels` doublings, 2 ** levels paths through levels + 1 parts, inside `wrap`
    single lists, so that it may sit deeper than the reading goes. Written as a tree it does not end."""
    x = 7
    for _ in range(levels):
        x = {"list": lambda y: [y, y], "tuple": lambda y: (y, y), "dict": lambda y: {"a": y, "b": y},
             "deque": lambda y: collections.deque([y, y]), "listsub": lambda y: _Shared([y, y])}[shape](x)
    for _ in range(wrap):
        x = (x,) if shape == "tuple" else [x]   # a tuple stays hashable, to serve as a key
    return x


def _holder(kind, x):
    """x inside an object the reading has no rule for, written by Python's own walk of what it holds."""
    return {"deque subclass": lambda: _Holder([x]), "namespace": lambda: types.SimpleNamespace(a=x),
            "dict view": lambda: {"k": x}.values(), "slice": lambda: slice(x, x),
            "UserList": lambda: collections.UserList([x]), "exception": lambda: ValueError(x)}[kind]()


def _raise(kind, x):
    if kind == "exit":
        sys.exit(x)
    raise {"ValueError": lambda: ValueError(x), "KeyError": lambda: KeyError(x), "OSError": lambda: OSError(2, "gone", x),
           "SyntaxError": lambda: SyntaxError(x), "own": lambda: _OwnError("bad", x),
           "group": lambda: ExceptionGroup("g", [ValueError(x)])}[kind]()


_ROUTES = ["unknown field", "text field", "integer field", "non-text key", "key in a mapping", "hook", "written line",
           "refusal reason", "refusal input", "refusal field", "raise", "exit", "held by an object"]
_HOLDERS = ["deque subclass", "namespace", "dict view", "slice", "exception"] + (["UserList"] if sys.version_info >= (3, 10) else [])


def _routed(route, x, how):
    """A correct parser (the reference) that hands x back through one route -> (the adapter, the case it runs)."""
    from gpconf.adapters.reference import Parser as Reference

    def records(change):
        class A(Reference):
            def parse(self, raw, fmt):
                return change(super().parse(raw, fmt))
        return A()

    def each(change):
        return records(lambda rs: [r if "_refused" in r else change(dict(r)) for r in rs])

    kvn = ["kvn-syntax-variants"]
    if route == "unknown field":
        return each(lambda r: dict(r, _x=x)), kvn
    if route == "text field":
        return each(lambda r: dict(r, object_name=x)), kvn
    if route == "integer field":
        return each(lambda r: dict(r, element_set_no=x)), kvn
    if route == "non-text key":
        return each(lambda r: {**r, x: 1}), kvn
    if route == "key in a mapping":
        return each(lambda r: dict(r, _x={x: 1})), kvn
    if route == "hook":
        class H(Reference):
            def alpha5_decode(self, s):
                return x
        return H(), ["alpha5-encoding-vectors"]
    if route == "written line":
        class W(Reference):
            def write_tle(self, record):
                return [x] + list(super().write_tle(record))[-2:]
        return W(), ["tle-writer-alpha5"]
    if route.startswith("refusal"):
        key = {"refusal reason": "_refused", "refusal input": "_input", "refusal field": "_field"}[route]
        return records(lambda rs: rs + [dict({"_refused": "bad", "_input": "x"}, **{key: x})]), kvn
    if route in ("raise", "exit"):
        class R(Reference):
            def parse(self, raw, fmt):
                _raise("exit" if route == "exit" else how, x)
        return R(), kvn
    return each(lambda r: dict(r, _x=_holder(how, x))), kvn


class SharedDeepThroughEveryRoute(unittest.TestCase):                           # D-337
    @ROUTES_N
    @given(st.sampled_from(["list", "tuple", "dict", "deque", "listsub"]), st.integers(min_value=22, max_value=26),
           st.sampled_from([0, 40]), st.sampled_from(_ROUTES),
           st.sampled_from(["ValueError", "KeyError", "OSError", "SyntaxError", "own", "group"]), st.sampled_from(_HOLDERS))
    def test_a_shared_deep_answer_ends_in_words_through_every_route(self, shape, levels, wrap, route, raise_kind, holder):
        """A structure that shares its parts, which written as a tree would not end, handed back through every route a
        parser's answer takes (a field the checks read or not, a key, a hook's answer, a written line, a refusal's
        reason, input or field, an exception raised or held, an exit code, an object Python writes by walking what it
        holds) is read in bounded time, and the case ends with no internal error of the runner's (the owner's ruling on
        the ninth reading of D-337). Its cost, at 22 to 26 doublings, would be seconds to minutes as a tree."""
        import time
        from tests.adversarial.test_hardening import run
        if route in ("non-text key", "key in a mapping"):
            assume(shape == "tuple")   # a key must be hashable
        x = _bomb(shape, levels, wrap)
        adapter, cases = _routed(route, x, holder if route == "held by an object" else raise_kind)
        start = time.monotonic()
        results = run(adapter, cases=cases)
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 3.0 if cases != ["tle-writer-alpha5"] else 20.0, (route, shape, levels, wrap))
        self.assertIn(cases[0], results)
        details = [i.detail or "" for r in results.values() for i in r.items]
        self.assertFalse([d for d in details if "internal error" in d], (route, shape, levels, wrap))


class TheyRan(unittest.TestCase):
    def test_how_many_properties_this_module_holds(self):
        """A count, so that a property dropped by accident is noticed, and so that a report can say how many ran."""
        names = [n for c in (Alpha5, TwoDigitYear, Epochs, CatalogIdText, ElementValueText, Checksum, ReaderOnAnyBytes,
                             PlainBoundary, RealWorldTypes, SharedDeepThroughEveryRoute) for n in dir(c) if n.startswith("test_")]
        self.assertEqual(len(names), 25)


if __name__ == "__main__":
    unittest.main()
