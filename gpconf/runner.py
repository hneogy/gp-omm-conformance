# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""
gpconf/runner.py -- run a parser under test against the corpus.

Standard library only. Data-driven: reads manifest.json and fixtures/<case>/expected.json.

Parser protocol (duck-typed):
    parse(raw: bytes, fmt: str) -> list[dict]     fmt in tle, 2le, csv, json, xml, kvn
        returns one dict per record using the expected.json key names
        (norad_cat_id, epoch, mean_motion, eccentricity, inclination, ra_of_asc_node,
        arg_of_pericenter, mean_anomaly, bstar, mean_motion_dot, mean_motion_ddot, and
        optionally object_name, object_id, ephemeris_type, classification_type,
        element_set_no, rev_at_epoch, center_name, ref_frame, time_system,
        mean_element_theory). Raise gpconf.runner.Unsupported for a format you do not read.
    optional hooks used by the vector case:
        alpha5_decode(field: str) -> int          raise for invalid input
        alpha5_encode(n: int) -> str              raise for unencodable input
        two_digit_year(yy: str) -> int
        parse_epoch(text: str) -> datetime        raise for invalid input
        parse_catalog_id(text: str) -> int        raise for invalid input
        any of the five: raise gpconf.runner.Unsupported for an operation the library does not have, and the
        item skips with the reason; an operation is unsupported for all of its vectors or none (D-205)
    optional hook used by the writer case (see gpconf/writer.py):
        write_tle(record: dict) -> (line1, line2) | (line0, line1, line2)
                                                  raise to refuse; refusing a number above 339999 is correct

Two tiers: if the bytes on disk hash to the SHA-256 recorded when the corpus was built, the
frozen expected values are the oracle ("snapshot"). Otherwise the oracle is the corpus's own
reference reader applied to your bytes ("live"), which is clearly labelled as such. A stable-tier
source whose bytes changed is not silently downgraded: the case gets a failing `stable-source-drift`
item and a `drift` field in the JSON report, and its values item says the frozen values were not applied.
"""
import bisect
import collections
import datetime as dt
import functools
import hashlib
import itertools
import json
import os
import re
import signal
import subprocess
import sys
import weakref
from decimal import Decimal, InvalidOperation, ROUND_DOWN

from . import plain
from . import reference as ref
from . import tle as tlemod
from . import writer as W
from .words import pick, qty

CORE_FIELDS = ["norad_cat_id", "epoch", "mean_motion", "eccentricity", "inclination", "ra_of_asc_node",
               "arg_of_pericenter", "mean_anomaly", "bstar", "mean_motion_dot", "mean_motion_ddot"]
OPTIONAL_FIELDS = ["object_name", "object_id", "ephemeris_type", "classification_type", "element_set_no", "rev_at_epoch",
                   "center_name", "ref_frame", "time_system", "mean_element_theory"]
INT_FIELDS = {"norad_cat_id", "ephemeris_type", "element_set_no", "rev_at_epoch"}
TEXT_FIELDS = {"object_name", "object_id", "classification_type", "center_name", "ref_frame", "time_system", "mean_element_theory"}
DEC_FIELDS = {"mean_motion", "eccentricity", "inclination", "ra_of_asc_node", "arg_of_pericenter", "mean_anomaly",
              "bstar", "mean_motion_dot", "mean_motion_ddot"}
TLE_EPOCH_TOLERANCE_US = 432  # half of the TLE's 1e-8 day resolution
EPOCH_TOLERANCE_US = 2        # allowed for the parser under test: python-sgp4's Julian-date epoch was within 1 us in the cross-check; the oracle itself is exact
FLOAT_RELATIVE_TOLERANCE = 1e-12  # for values the parser returns as binary floats: |got - want| / max(|got|, |want|); zero requires zero
# Metadata the TLE formats carry no value for: a parser may answer None or the OMM constant default, and
# nothing else -- an invented value is a wrong value, not a default (D-285; the SM-26 audit, issue #1).
OMM_CONSTANT_DEFAULTS = {"center_name": ("EARTH",), "ref_frame": ("TEME",), "time_system": ("UTC",),
                         "mean_element_theory": ("SGP4", "SGP/SGP4"),
                         "classification_type": ("U",)}   # a blank TLE classification, or an OMM file's empty, null or
                                                           # absent one: None, or the default U (D-336)
KEYWORD_TO_FIELD = {"EPHEMERIS_TYPE": "ephemeris_type", "CLASSIFICATION_TYPE": "classification_type", "NORAD_CAT_ID": "norad_cat_id",
                    "ELEMENT_SET_NO": "element_set_no", "REV_AT_EPOCH": "rev_at_epoch"}


class Unsupported(Exception):
    """Raise from parse() for a format the parser does not implement, from write_tle() when it has no writer, or from
    a vector hook for an operation the library does not have (D-205)."""


class ParserExit(Exception):
    """The parser under test tried to end the process (sys.exit, or another BaseException that is not an
    Exception). The runner turns it into this ordinary exception, so the input fails like any other raise, the
    report is written and the exit status says a case failed (D-293; the red team's E9: on 0.6.2 a sys.exit()
    inside parse() ended the run with status 0 and no report)."""


class ParserRaised(Exception):
    """An exception the parser's own code raised, read inside the guard into the runner's own type (D-337): it carries
    the name of the parser's exception class and its message as plain text, and callers word it as they always have,
    "parser raised ValueError: ...", by that name. No method of the parser's exception runs after the guard, and an
    exception of the runner's own type that the parser raised (CorpusIncomplete, which ends a run) is not taken for
    the runner's. `Unsupported` stays Unsupported, the protocol's answer for an operation the parser does not have."""


class CommandCrashed(Exception):
    """The parser's command was ended by a signal (a crash: a negative return code, or, from a shell command, 128 plus
    the number of one of CRASH_SIGNALS, as a shell reports it) or did not finish within its time (D-341). Raised by the
    runner's own CommandParser, which records each one it raises (_CRASHES), and passed through the guard as itself
    when it is one of those, by identity, however it reached the guard (through a proxy or a wrapper that lets it pass
    unchanged), or when the parser is a CommandParser subclass by its type: any other CommandCrashed a Python parser
    made, a wrapper's copy of a crash among them, is read as the parser's raise. No class the parser claims is read
    (D-342). A crash or a timeout is no answer: wherever a refusal or a rejection is the right outcome (a corrupt input
    refused, an invalid vector rejected, an id the TLE field cannot carry refused by a writer) it fails, and everywhere
    it is worded as the command's end, never as the parser's raise. POSIX only: Windows has no signals, and a crash
    there is its exit code."""


# the signals a program does not end by on purpose (a fault, an abort or a trap, a kill, the kernel's resource limits):
# a shell's exit of 128 plus one of these is read as that signal; any other exit, 130 (SIGINT) and 143 (SIGTERM) among
# them, is the command's own answer (the readings of D-341). None on Windows, which has no signals.
CRASH_SIGNALS = () if os.name == "nt" else tuple(
    s for s in (getattr(signal, n, None) for n in
                ("SIGSEGV", "SIGBUS", "SIGABRT", "SIGILL", "SIGFPE", "SIGTRAP", "SIGSYS", "SIGKILL", "SIGXCPU", "SIGXFSZ"))
    if s is not None)


_RAISED: dict[str, type] = {}
_CRASHES: "weakref.WeakSet[CommandCrashed]" = weakref.WeakSet()   # the crashes CommandParser raised (D-342)


def _raised_type(name):
    """The ParserRaised subclass that bears this name, so that type(e).__name__ reads as the parser's exception did."""
    if name not in _RAISED:
        _RAISED[name] = type(name, (ParserRaised,), {"__module__": __name__})
    return _RAISED[name]


class _Guarded:
    """The parser under test, with every call guarded, and everything it returns read inside the guard into plain
    built-in values (`gpconf.plain`, D-337): a parse() answer, a hook's answer, a written line, an attribute. After the
    guard the runner calls no method of any object the parser made, so no `__eq__`, `__str__`, `keys()` or
    `strftime()` of the parser's own decides what a check sees. A SystemExit or other non-Exception BaseException
    raised inside it becomes ParserExit and is counted, so no caller can mistake it for a rejection (D-293); any other
    exception is the parser's, as a ParserRaised of the same name (or Unsupported). KeyboardInterrupt is the user's,
    and passes. A process-level exit (os._exit) cannot be contained in-process; a parser that must be isolated, or is
    not trusted to leave the runner alone, runs behind --cmd, where the runner owns the process."""

    def __init__(self, parser, events):
        object.__setattr__(self, "_parser", parser)
        object.__setattr__(self, "_events", events)

    def _read(self, fn, name, read):
        """fn() and read(its answer), both inside the guard."""
        try:
            return read(fn())
        except KeyboardInterrupt:
            raise
        except Unsupported as e:
            raise Unsupported(self._text(e, name)) from None
        except CommandCrashed as e:
            # one CommandParser raised, known by identity, so a crash that came up through a proxy or a wrapper is the
            # crash it was; or one a CommandParser subclass made, by its type, which reads no code of the parser's: a
            # forged one fails only the forger (D-342, the third reading of D-341 and D-342's two readings)
            if type(e) is CommandCrashed and (e in _CRASHES or issubclass(type(self._parser), CommandParser)):
                raise CommandCrashed(self._text(e, name)) from None   # the runner's own words, from its own code (D-341)
            raise _raised_type(plain.name(type(e)))(self._text(e, name)) from None
        except Exception as e:
            raise _raised_type(plain.name(type(e)))(self._text(e, name)) from None
        except BaseException as e:  # SystemExit, GeneratorExit and anything else outside Exception
            raise self._exit(e, name) from None

    def _text(self, e, name):
        """An exception's message as plain text, read inside the guard: its __str__ is the parser's code too. One whose
        text is Python's own (a builtin exception class's __str__) keeps Python's words when what they read is plain,
        and is otherwise written from the plain reading of its arguments, bounded, so a shared list in an exception's
        arguments or attributes is written once (the seventh, eighth and ninth readings of D-337)."""
        try:
            if plain.pythons_own(type(e).__str__):
                return plain.exception_text(e)
            return str.__str__(str(e))
        except KeyboardInterrupt:
            raise
        except Exception as inner:
            return f"(its message could not be read: {type(inner).__name__})"
        except BaseException as inner:
            raise self._exit(inner, name) from None

    def _exit(self, e, name):
        if issubclass(type(e), SystemExit):   # by its type: an exception's own __class__ is the parser's code
            try:
                code = plain.hook_answer(SystemExit.__dict__["code"].__get__(e))   # past any property of a subclass
                code = (str.__str__(code) if type(code) is plain.Written else
                        f"(a code that {code.what})" if type(code) is plain.Problem else repr(code))
            except KeyboardInterrupt:
                raise
            except BaseException:
                code = "(unreadable)"
            what = f"{plain.name(type(e))}({code})"
        else:
            what = plain.name(type(e))
        self._events.append((name, what))
        return ParserExit(f"the parser raised {what} inside {name}: a parser must not end the run")

    def _guard(self, fn, name):
        read = plain.answer if name == "parse" else plain.lines if name == "write_tle" else plain.hook_answer

        def call(*a, **k):
            return self._read(lambda: fn(*a, **k), name, read)
        return call

    def __getattr__(self, name):
        try:
            v = getattr(self._parser, name)   # a property is the parser's code too
        except AttributeError as e:
            # so getattr(..., None) still answers None for a hook it does not have: the runner's own AttributeError,
            # its text read here, so no method of the parser's exception runs after the guard (D-337)
            raise AttributeError(self._text(e, name)) from None
        except KeyboardInterrupt:
            raise
        except Unsupported as e:
            # a property that declares the operation unsupported: the hook is there and answers Unsupported when it is
            # called, as it would from inside the call (D-205, D-280)
            text = self._text(e, name)

            def unsupported(*a, **k):
                raise Unsupported(text)
            return unsupported
        except Exception as e:
            raise _raised_type(plain.name(type(e)))(self._text(e, name)) from None
        except BaseException as e:
            raise self._exit(e, name) from None
        if callable(v):
            return self._guard(v, name)
        return self._read(lambda: v, name, plain.value)

    def __call__(self, *a, **k):
        return self._guard(self._parser, "parse")(*a, **k)


class CorpusIncomplete(Exception):
    """A file that ships with the corpus (derived/, vectors/) is not on disk: the copy is broken, and no status
    the runner could report for the case would be true of the parser (D-148)."""


REPO_URL = "https://github.com/hneogy/gp-omm-conformance"


def is_provider_data(path):
    """A provider response under fixtures/<case>/raw/: never shipped there with the corpus (D-019). A fetch brings it,
    or, for the provider's recorded empty answer, writes it from the one response the corpus ships, in recorded/ (D-247)."""
    parts = path.replace("\\", "/").split("/")
    return len(parts) >= 4 and parts[0] == "fixtures" and parts[2] == "raw"


def launch_window_files(root):
    """Provider files that are the corpus's own captures of a launch window -> {path: which launch} (D-229).

    CelesTrak serves launch nominals and post-deployment files for the days after a launch, so no fetch requests
    these files and a user cannot obtain them: a case that needs one reports not-available for it, never
    not-fetched, which would send the user to a fetch that does not bring it. The list is read from the fetch list,
    which ships with the corpus; a bare copy without it has none."""
    try:
        with open(os.path.join(root, "tools", "fetchlist.json"), encoding="utf-8") as f:
            entries = json.load(f)
    except (OSError, ValueError):
        return {}
    return {f"fixtures/{e['case']}/raw/{e['file']}": e["launch_window"] for e in entries if e.get("launch_window")}


def opt_in_files(root):
    """Provider files the fetch brings only on request -> {path: the flag that asks for it} (D-231): the legacy SATCAT
    file, most of the bytes of the whole fetch list, which one data check reads and no parser. Read from the fetch
    list; a bare copy without it has none."""
    try:
        with open(os.path.join(root, "tools", "fetchlist.json"), encoding="utf-8") as f:
            entries = json.load(f)
    except (OSError, ValueError):
        return {}
    return {f"fixtures/{e['case']}/raw/{e['file']}": "--include-" + e["opt_in"] for e in entries if e.get("opt_in")}


def fetch_hint(root, *args, data=None, data_why=None):
    """The command that fetches provider data into the folder this run reads, naming a command that exists
    (D-148, D-150).

    A clone has tools/fetch.py; the path is given relative to the working directory when that is shorter and quoted
    when it needs to be. Without the script (an installed runner, or a bare copy of the corpus) the command is the
    package's own `python3 -m gpconf fetch`. A data folder chosen with --data is passed on; one chosen with the
    GPCONF_DATA environment variable is not, since the variable reaches the fetch too; a bare corpus copy given as
    --root is passed on, since the fetch would otherwise look elsewhere."""
    import shlex
    import subprocess
    py = "python" if os.name == "nt" else "python3"                      # the interpreter name each platform has (D-270)
    q = (lambda s: subprocess.list2cmdline([s])) if os.name == "nt" else shlex.quote
    script = os.path.join(root, "tools", "fetch.py")
    flags = ""
    if data_why == "--root" and not os.path.exists(script):
        flags += f" --root {q(root)}"
    if data_why == "--data" and data:
        flags += f" --data {q(data)}"
    tail = flags + "".join(" " + a for a in args)
    if os.path.exists(script):
        try:
            rel = os.path.relpath(script)
        except ValueError:  # another drive on Windows
            rel = script
        path = script if rel.startswith("..") else rel
        return f"{py} {q(path)}{tail}"
    return f"{py} -m gpconf fetch{tail}"


# --------------------------------------------------------------------------- normalisation
# An epoch as calendar-form text: what a parser that parsed the epoch can write without help. Anything else a
# parser returns as text -- day-of-year form, a trailing Z, an offset, second 60 -- the runner still normalises,
# since the corpus's own harnesses return TLE epochs as year and day-of-year text by design (D-306).
CALENDAR_EPOCH = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$")


_DOY_TEXT = re.compile(r"(\d{4}-\d{3}T\d{2}:\d{2}:\d{2})(?:\.(\d*))?(Z|[+-]00:00)?")


def _doy_key(text):
    """A day-of-year epoch text without what does not change its instant: a Z or a zero offset, and the fraction's
    trailing zeros (D-370). None for any other text."""
    m = _DOY_TEXT.fullmatch(text)
    return (m.group(1), (m.group(2) or "").rstrip("0")) if m else None


@functools.lru_cache(maxsize=8)
def _doy_keys_in(raw_text):
    """The keys of every day-of-year epoch text in an input, once an input (the text's hash is kept by Python)."""
    return frozenset(_doy_key(m.group(0)) for m in _DOY_TEXT.finditer(raw_text))


def unparsed_epoch(value, raw_text):
    """True when an epoch came back as the input's own text, unparsed: text that is not calendar-form and is found
    verbatim in the file it was read from (D-306; the red team's E6), or is a day-of-year epoch the input holds once
    a Z, a zero offset and the fraction's trailing zeros are set aside (D-370; the second blind review's F3: the text
    handed back with its Z made +00:00, or a zero added, passed). A parser that gives up on a day-of-year epoch and
    hands the text back used to pass, because the runner parsed the text for it. Text a harness built itself, such as
    a TLE epoch written out as year and day of year, is in no input and is normalised as before."""
    if not isinstance(value, str):
        return False
    s = value.strip()
    if not s or CALENDAR_EPOCH.match(s):
        return False
    if s in raw_text:
        return True
    k = _doy_key(s)
    return k is not None and k in _doy_keys_in(raw_text)


def norm_epoch(v):
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        if v.tzinfo is not None:
            try:
                v = v.astimezone(dt.timezone.utc).replace(tzinfo=None)
            except OverflowError as e:   # an offset that takes the instant outside the years a datetime holds (D-325)
                raise UnreadableValue(f"epoch = {v!r} is not an epoch the runner can read: {e}") from None
        return tlemod.epoch_text(v)
    s = str(v)
    if s != s.strip():
        # the strict rule of D-319 for element text, applied to the epoch (D-325): the reader strips, so padding around
        # an epoch a parser returned was read as the instant inside it
        raise UnreadableValue(f"epoch = {v!r} has whitespace around it: an epoch string is the epoch and nothing around it (D-325)")
    try:
        return tlemod.iso_epoch(v)  # calendar or day-of-year form, fraction, Z, offset, leap second (D-118, D-119)
    except (ValueError, OverflowError) as e:   # OverflowError: a fraction or an offset past the years a datetime holds
        # the reader's refusal is about a value the parser returned, not an exception the parser raised (D-325)
        raise UnreadableValue(f"epoch = {v!r} is not an epoch the runner can read: {e}") from None


def is_integral(v):
    """True for an integer TYPE: int, an int subclass, or a type registered as numbers.Integral (numpy's integer
    types are). Never a bool, a float, a string or a Decimal, whatever their value (D-283, D-295). The check used
    to compare the type's name with "int", which failed a correct parser returning its library's own integer type
    (the red team's finding, section 6)."""
    import numbers
    return isinstance(v, numbers.Integral) and not isinstance(v, bool)


def as_integer(v):
    """-> (int or None, problem or None). A bool, a value int() cannot convert, or a float or Decimal with a
    fractional part is not an integer; the problem text carries the value and its type for the report (D-131)."""
    if isinstance(v, bool):
        return None, f"{v!r} (bool)"
    if type(v) is plain.Written:   # a container, or an int too long to write, as the guard's text
        return None, f"{v!r} ({v.kind}{', too long to write in decimal' if v.kind == 'int' else ', as its text'})"
    if isinstance(v, Decimal) and v.is_finite() and not v.is_zero() and v.adjusted() >= plain.int_digits():
        # int() of it raised outside every guard, or took minutes (the eighth reading of D-337)
        return None, f"{str(v)[:40]!r} (Decimal, more digits than an integer can be written with)"
    try:
        i = int(v)
    except (TypeError, ValueError):
        return None, f"{v!r} ({type(v).__name__})"
    except OverflowError:   # an infinite float or Decimal: int() raises, and the report blamed the parser for the runner's conversion (D-325)
        return None, f"{v!r} ({type(v).__name__}, not finite)"
    if isinstance(v, (float, Decimal)) and v != i:
        return None, f"{v!r} ({type(v).__name__}, fractional)"
    return i, None


# What an element value may look like when a parser returns it as text (D-319): an optional sign, ASCII digits with an
# optional point, an optional exponent; nothing before or after. Decimal() itself is far more generous: it reads the
# digits of other scripts, underscores between digits and surrounding whitespace, so text of those kinds was graded
# as the number it spells. Text outside the grammar is what "N/A" has always been here: a value the runner cannot
# read, which raises, and the whole file fails as `parse` (ADAPTERS.md, "What happens when the output is unexpected").
# It raises rather than travel on as an empty value because an empty value on both sides of a later comparison is
# equal: the first form of this change did that, and two wrong parsers passed the cases that pair TLE with OMM.
PLAIN_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


class UnreadableValue(ValueError):
    """A value a parser returned that the runner cannot read as what the field holds (D-319)."""


class NotRecords(UnreadableValue):
    """A parser's answer that is not an iterable of records (D-330). `what` is the phrase after "the answer" (D-334)."""

    def __init__(self, what):
        super().__init__(f"the answer {what}")
        self.what = what


def as_records(out):
    """A parser's answer, as the guard read it (`gpconf.plain.answer`) -> its records as a list of plain dicts, or
    NotRecords saying what it is instead (D-330). Any iterable of mappings will do, a list, a tuple or a generator; a
    mapping, a string or bytes is one value, not a list of records. Each record is a plain dict of text keys (D-334,
    D-337): a mapping whose get() and items() disagreed was read one way for one check and the other way for another,
    and a mapping that was not a dict was not read as a refusal. Before D-330, an answer holding strings ended the
    corrupt-input case as "internal error in runner: AttributeError", and a dict read as "parser raised
    AttributeError", though the parser raised nothing. A caller outside the guard (a test) gets the guard's reading here."""
    if type(out) is plain.Problem:
        raise NotRecords(out.what)
    if type(out) is list:
        for r in out:
            if type(r) is plain.Problem:
                raise NotRecords(r.what)
    if not (type(out) is list and all(type(r) is dict for r in out) and plain.is_plain(out)):
        out = plain.answer(out)   # a caller outside the guard gets the guard's reading; a plain answer is one already
    if type(out) is plain.Problem:
        raise NotRecords(out.what)
    for r in out:
        if type(r) is plain.Problem:
            raise NotRecords(r.what)
    return out


def unreadable_words(e):
    """A value the runner could not read, in the corrupt-input case's words; the exception's name only when it is not the
    runner's own UnreadableValue (D-325)."""
    if isinstance(e, UnreadableValue):
        return f"the parser returned a value the runner cannot read: {str(e)[:200]}"
    return f"the parser returned a value the runner cannot read: {type(e).__name__}: {str(e)[:200]}"


def parse_failure(e):
    """The words for a file that fails as `parse`. A value the runner cannot read is the parser's output, not an exception
    the parser raised, and the report says so (D-325): it used to read "parser raised UnreadableValue"."""
    if isinstance(e, UnreadableValue):
        return f"the parser returned a value the runner cannot read: {str(e)[:200]}"
    if type(e) is CommandCrashed:
        return f"the parser's command {e}"
    return f"parser raised {type(e).__name__}: {str(e)[:200]}"


def crashed(e):
    """The words for the parser's command crashing or timing out where a refusal or a rejection would be right, or None
    for any other exception, which is the refusal or the rejection it always was (D-341)."""
    return f"the parser's command {e}: a crash or a timeout is no refusal and no rejection (D-341)" if type(e) is CommandCrashed else None


def raised(e, text=False):
    """How an exception that fails an item reads: a crash or a timeout as the command's end (D-341), any other as the
    parser's raise, by its type's name (and its text, when asked)."""
    if type(e) is CommandCrashed:
        return f"the parser's command {e}"
    return f"raised {type(e).__name__}" + (f": {e}" if text else "")


def norm_record(rec):
    """Parser output -> {field: comparable value}; also returns type notes. A field that should be an integer but is
    not stays None and is named in the record's _bad map, so the values item reports the value and its type
    instead of the runner raising (D-131). An element value whose text is not a plain decimal number raises
    UnreadableValue, as does one whose exponent is past what Decimal holds (D-355), and an epoch the reader cannot read
    raises ValueError: the caller fails the file as `parse` (D-319)."""
    out, notes, bad = {}, {}, {}
    for k, v in rec.items():
        if k in RUNNERS_OWN:
            continue   # the runner's own notes on a record: a parser's key of that name ended cases as an internal error
        if k in INT_FIELDS:
            if v is None or v == "":
                out[k] = None
                if v == "":
                    notes[k] = "empty text"   # read as absent, and told apart on the file whose keyword is absent (D-358)
            else:
                notes[k] = "int" if is_integral(v) else type(v).__name__   # any integer type reads as "int" (D-295)
                out[k], problem = as_integer(v)
                if problem:
                    bad[k] = problem
        elif k in DEC_FIELDS:
            if v is None or v == "":
                out[k] = None
            elif isinstance(v, (float, Decimal)) and not isinstance(v, bool) and not Decimal(repr(float(v)) if isinstance(v, float) else v).is_finite():
                # NaN or an infinity is no element value: it used to travel on and end the case as "internal error in runner:
                # InvalidOperation" at the first comparison; it is a value the runner cannot read, as text outside the grammar is (D-325)
                raise UnreadableValue(f"{k} = {v!r} is not a finite number (D-325)")
            elif isinstance(v, float):
                notes[k] = "float"
                # repr of the plain float, not of the object (D-321): numpy.float64 is a float whose own repr under
                # numpy 2 is "np.float64(1.5)", which is no number, so a correct parser returning it failed every file
                out[k] = Decimal(repr(float(v)))
            elif isinstance(v, (int, Decimal)) and not isinstance(v, bool):
                out[k] = Decimal(v)
            else:
                # text, or anything else that is not a number: its text form is held to the grammar (D-319)
                if not PLAIN_DECIMAL.fullmatch(str(v)):
                    raise UnreadableValue(f"{k} = {v!r} is not a plain decimal number: ASCII digits with an optional sign, point and exponent, "
                                          "and nothing around them (D-319)")
                try:
                    out[k] = Decimal(str(v))
                except (ArithmeticError, ValueError):
                    # an exponent past what Decimal holds raised InvalidOperation here, and the file failed as "parser
                    # raised InvalidOperation", though the parser raised nothing (D-355)
                    text = str(v)
                    shown = repr(text) if len(text) <= 60 else f"{text[:60]!r}... ({len(text)} characters)"
                    raise UnreadableValue(f"{k} = {shown} has an exponent past what the runner's decimals can hold (D-355)") from None
        elif k == "epoch":
            out[k] = norm_epoch(v)
        elif k not in TEXT_FIELDS:
            # a key no check reads is handed on as the guard read it, never written out: str() of bytes or of a mapping
            # under such a key, in every record, cost the records times its size (the eighth reading of D-337)
            out[k] = v
        elif v is None or v == "":
            out[k] = None
        elif type(v) is plain.Written:
            out[k] = v   # a container's text, or an int's: the guard's own type, never equal to a parser's own text
        else:
            out[k] = field_text(v)
    return out, notes, bad


RUNNERS_OWN = ("_notes", "_bad", "_record")   # set by the runner on each record it normalises (D-131, D-337, D-343)
_FIELD_TEXTS: dict = {}


def field_text(v):
    """A text field's value that is not text, as its text: one long value shared by every record (bytes, a Decimal) is
    written once, not once per record, from a cache of the last sixteen such values (the ninth reading of D-337); an
    int Python will not write in decimal, given here by a caller other than the guard, is a marker."""
    if type(v) is str:
        return v
    hit = _FIELD_TEXTS.get(id(v))
    if hit is not None and hit[0] is v:
        return hit[1]
    try:
        text = str(v)
    except ValueError:
        text = plain.Written(f"<an integer too long to write in decimal, #{plain._digest(v).hex()[:32]}>", "int")
    if len(text) > 1024:
        if len(_FIELD_TEXTS) >= 16:
            _FIELD_TEXTS.pop(next(iter(_FIELD_TEXTS)))
        _FIELD_TEXTS[id(v)] = (v, text)
    return text


def epoch_diff_us(a, b):
    ta = dt.datetime.strptime(a, "%Y-%m-%dT%H:%M:%S.%f")
    tb = dt.datetime.strptime(b, "%Y-%m-%dT%H:%M:%S.%f")
    return abs((ta - tb).total_seconds()) * 1e6


def _shown(rec, field, how=repr):
    """A record's value in the words, or "left out" where the parser gave no key for it (D-358)."""
    return "left out" if field not in rec else how(rec[field])


class _Sinks:
    """Failures or tolerances added to two items at once: a DDOT mismatch fails the consistency item and the mmdot item
    both (D-358)."""

    def __init__(self, *sinks):
        self.sinks = sinks

    def append(self, text):
        for s in self.sinks:
            s.append(text)

    def add(self, field, diff):
        for s in self.sinks:
            s.add(field, diff)


def compare_value(field, got, want, note=None, epoch_tolerance_us=EPOCH_TOLERANCE_US):
    """-> (result, signed_diff). result: 'exact' | 'tolerance' | 'mismatch'.
    signed_diff is got - want: microseconds for epochs, relative for float-derived decimals."""
    if got is None and want is None:
        return "exact", None
    if got is None or want is None:
        return "mismatch", None
    if field == "epoch":
        try:
            ta = dt.datetime.strptime(str(got), "%Y-%m-%dT%H:%M:%S.%f")
            tb = dt.datetime.strptime(str(want), "%Y-%m-%dT%H:%M:%S.%f")
        except ValueError:
            return ("exact" if str(got) == str(want) else "mismatch"), None
        d = (ta - tb).total_seconds() * 1e6
        if d == 0:
            return "exact", 0.0
        return ("tolerance" if abs(d) <= epoch_tolerance_us else "mismatch"), d
    if field in DEC_FIELDS:
        a, b = Decimal(str(got)), Decimal(str(want))
        if a == b:
            return "exact", 0.0
        if note == "float":
            if a == 0 or b == 0:
                return "mismatch", None  # zero requires zero: no relative scale exists for a zero value
            rel = float((a - b) / max(abs(a), abs(b)))  # genuinely relative, no floor
            return ("tolerance" if abs(rel) <= FLOAT_RELATIVE_TOLERANCE else "mismatch"), rel
        return "mismatch", None
    if field == "object_name" and type(got) is str and type(want) is str:
        # a TLE name line padded to 24 columns, as CelesTrak writes it, names the same object: trailing blanks are the
        # line's, not the name's (D-369); the runner's own Written type is never stripped, so it never equals a text
        got, want = got.rstrip(" "), want.rstrip(" ")
    return ("exact" if got == want else "mismatch"), None


def values_equal(field, a, b, note=None):
    return compare_value(field, a, b, note)[0] != "mismatch"


class TolStats:
    """Per-field tally of comparisons that passed only within tolerance, so a systematic bias shows."""

    def __init__(self):
        self.f = {}

    def add(self, field, diff):
        s = self.f.setdefault(field, [0, 0.0, 0.0])
        s[0] += 1
        s[1] += diff or 0.0
        s[2] = max(s[2], abs(diff or 0.0))

    def __bool__(self):
        return bool(self.f)

    def text(self):
        parts = []
        for field, (n, tot, mx) in self.f.items():
            unit = "us" if field == "epoch" else "rel"
            parts.append(f"{field} n={n} mean={tot / n:+.3g}{unit} max={mx:.3g}{unit}")
        return "within tolerance: " + "; ".join(parts)

    def as_dict(self):
        return {k: {"n": v[0], "mean_signed": v[1] / v[0], "max_abs": v[2]} for k, v in self.f.items()}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def strip_ref(rec):
    return {k: rec.get(k) for k in CORE_FIELDS + OPTIONAL_FIELDS}


def oracle_from_expected(exp_rec, fmt):
    vals = dict(exp_rec["canonical"])
    if fmt in ("tle", "2le") and exp_rec.get("by_format", {}).get("tle"):
        d = exp_rec["by_format"]["tle"].get("differs_from_omm", {})
        for k, v in d.items():
            if k == "object_name_truncated_to_24":
                vals["object_name"] = v
            else:
                vals[k] = v
    if fmt == "2le":
        vals["object_name"] = None
    for k in list(vals):
        if k in DEC_FIELDS and vals[k] is not None:
            vals[k] = Decimal(str(vals[k]))
    return vals


# --------------------------------------------------------------------------- the refusal channel (D-144)
REFUSAL_KEY, ADAPTER_KEY = "_refused", "_adapter"


def field_to_id(field):
    """The expected integer behind a catalog field as the input carried it: digits, or an Alpha-5 field; None otherwise."""
    if not isinstance(field, str):
        return None
    f = field.strip()
    if re.fullmatch(r"\d+", f) and len(f) <= plain.int_digits():   # one of more digits than int() takes is no catalog number (D-337)
        return int(f)
    if re.fullmatch(r"[A-Z]\d{4}", f):
        try:
            return tlemod.from_alpha5(f)
        except ValueError:
            return None
    return None


def split_refusals(recs):
    """An adapter's list -> (records, refusals, declared). A refusal is an entry carrying `_refused`; its reason must be a
    non-empty string, or the refusal is no better than a drop and is marked so (ok=False). `declared` is the adapter's
    capability declaration ({"_adapter": {"refusals": true}}), None when absent: without it, zero refusals means only that
    none were reported, not that none happened."""
    records, refusals, declared = [], [], None
    for r in recs:
        if isinstance(r, dict) and ADAPTER_KEY in r and not any(k for k in r if k != ADAPTER_KEY and not str(k).startswith("_")):
            # the declaration is an entry of its own; a record that carries an _adapter key beside its fields is a
            # record, and used to be dropped here without a word (D-295; the red team's finding, section 6)
            decl = r.get(ADAPTER_KEY)
            declared = bool(decl.get("refusals")) if isinstance(decl, dict) else None   # its truth value, read in the guard (D-337)
            continue
        if isinstance(r, dict) and REFUSAL_KEY in r:
            reason = r.get(REFUSAL_KEY)
            ok = isinstance(reason, str) and bool(reason.strip())
            field = r.get("_field")
            inp = r.get("_input")
            if isinstance(inp, bytes):   # the input's own bytes, as the file holds them, not their repr (D-282, D-337)
                inp = inp.decode("utf-8", "replace")
            refusals.append({"reason": reason.strip() if ok else None, "ok": ok, "field": field if isinstance(field, str) else None,
                             "input": str(inp)[:80] if inp is not None else None, "id": field_to_id(field)})
            continue
        records.append(r)
    return records, refusals, declared


# --------------------------------------------------------------------------- report objects
class Item:
    def __init__(self, check, status, file=None, detail="", tolerance=None, counts=None, cause=None):
        self.check, self.status, self.file, self.detail, self.tolerance = check, status, file, detail, tolerance
        self.counts = counts  # structured record counts behind a values item (D-142), so headlines never parse the sentence
        # why a not-exercised item was not exercised (D-294): "parser" when the parser's own behaviour voided the
        # comparison (it does not return the record from the unedited file either, D-175; it never returns the
        # field, D-284), "data" when the data on disk lacks the feature or no parser takes part in the check
        self.cause = cause

    def as_dict(self):
        d = {"check": self.check, "status": self.status, "file": self.file, "detail": self.detail}
        if self.cause:
            d["cause"] = self.cause
        if self.tolerance:
            d["tolerance_stats"] = self.tolerance.as_dict()
        if self.counts is not None:
            d["counts"] = self.counts
        return d


# The statuses a case can end in, in the order the count line names them (D-240).
CASE_STATUSES = ("pass", "pass-tolerance", "fail", "skip", "not-fetched", "not-available", "not-exercised")


def _values(rec):
    """A record's values, without the runner's own keys (an underscore's)."""
    return {k: v for k, v in rec.items() if not k.startswith("_")}


FAIL_WEIGHT = 1000     # a failure outweighs any number of values within tolerance in the pairing's cost (D-343)
PAIRING_CAP = 10_000   # copy-and-record pairs costed for one id beyond the first pass; past it, epoch order (D-343)


def _pairing_cost(compare):
    """cost(copy, record) from compare(copy, record) -> (failures, values within tolerance): a failure weighs
    FAIL_WEIGHT, a value within tolerance one, so an exact pairing wins over one within tolerance (the reading of D-343)."""
    def cost(g, r):
        fails, tols = compare(g, r)
        return FAIL_WEIGHT * len(fails) + len(tols)
    return cost


def _ordinal(rec):
    """The fields that tell one element set of an id from another, as given: its element set number and revolution."""
    return (rec.get("element_set_no"), rec.get("rev_at_epoch"))


def _match_copies(got_list, records, cost):
    """-> [(copy, record index)] for an id the input holds more than once (D-343, 2a). First, a copy that gives both its
    element set number and its revolution is paired with the record of that ordinal when the input holds one such record
    and it is still free and the copy fails nothing against it: one pass, a lookup each. The copies left are paired with
    the records left: exhaustively at least cost up to seven of each; up to PAIRING_CAP pairs least cost first, and where
    that leaves a failure, by augmenting paths over the pairs that fail nothing, so a pairing that fails nothing is found
    wherever one exists; beyond the cap, both sorted by epoch and paired in that order (a stated limit: where two of those
    records share an epoch, or lie within the tolerance of each other, and differ, a correct parser that returns them in
    another order than the input's can fail; a wrong parser never passes). Every record is paired with a copy while
    copies last; a copy beyond them (a surplus, which D-311 fails) goes to the record it matches best among those of its
    ordinal, or among all of them, or the first, as the cap allows. Ties go to the input's order."""
    n, m = len(got_list), len(records)
    pairs, free = {}, set(range(m))
    by_ordinal: dict = {}
    for j, r in enumerate(records):
        by_ordinal.setdefault(_ordinal(r), []).append(j)
    for i, g in enumerate(got_list):
        key = _ordinal(g)
        js = by_ordinal.get(key, []) if None not in key else []
        if len(js) == 1 and js[0] in free and cost(g, records[js[0]]) < FAIL_WEIGHT:
            pairs[i] = js[0]
            free.discard(js[0])
    left_i = [i for i in range(n) if i not in pairs]
    left_j = sorted(free)
    if left_i and left_j:
        if len(left_i) <= 7 and len(left_j) <= 7:
            c = {(i, j): cost(got_list[i], records[j]) for i in left_i for j in left_j}
            if len(left_i) <= len(left_j):   # each copy to a record of its own
                best = min(itertools.permutations(left_j, len(left_i)),
                           key=lambda js: (sum(c[i, j] for i, j in zip(left_i, js)), js))
                pairs.update(zip(left_i, best))
            else:                            # each record to a copy of its own; the copies left to their best record
                best = min(itertools.permutations(left_i, len(left_j)),
                           key=lambda ii: (sum(c[i, j] for i, j in zip(ii, left_j)), ii))
                pairs.update({i: j for i, j in zip(best, left_j)})
        elif len(left_i) * len(left_j) <= PAIRING_CAP:
            c = {(i, j): cost(got_list[i], records[j]) for i in left_i for j in left_j}
            greedy: dict = {}
            used_j = set()
            for _, i, j in sorted((c[i, j], i, j) for i in left_i for j in left_j):
                if i not in greedy and j not in used_j:
                    greedy[i] = j
                    used_j.add(j)
            if any(c[i, j] >= FAIL_WEIGHT for i, j in greedy.items()):
                match_r = {j: i for i, j in greedy.items() if c[i, j] < FAIL_WEIGHT}
                edges = {i: [j for j in left_j if c[i, j] < FAIL_WEIGHT] for i in left_i}

                def augment(i, seen):
                    for j in edges[i]:
                        if j not in seen:
                            seen.add(j)
                            if j not in match_r or augment(match_r[j], seen):
                                match_r[j] = i
                                return True
                    return False
                matched = set(match_r.values())
                for i in left_i:
                    if i not in matched and augment(i, set()):
                        matched = set(match_r.values())
                if len(match_r) == min(len(left_i), len(left_j)):
                    greedy = {i: j for j, i in match_r.items()}
            pairs.update(greedy)
        else:
            pairs.update(zip(sorted(left_i, key=lambda i: str(got_list[i].get("epoch"))),
                             sorted(left_j, key=lambda j: str(records[j].get("epoch")))))
    surplus = [i for i in range(n) if i not in pairs]
    for i in surplus:
        g = got_list[i]
        js = by_ordinal.get(_ordinal(g)) or range(m)   # a range, so the cap below cuts it at no cost (the third reading)
        if len(surplus) * len(js) > PAIRING_CAP:
            js = js[:1]
        pairs[i] = min(js, key=lambda j: (cost(g, records[j]), j))
    return [(got_list[i], pairs[i]) for i in range(n)]


def _oracle_by_id(pairs):
    """{id: the input's record of it}: the first, carrying every record of the id under "_copies" where the input holds
    the id more than once, which compare_values pairs with the copies returned (D-343). Before, the last record of a
    repeated id was the only one kept."""
    by: dict = {}
    for cid, vals in pairs:
        by.setdefault(cid, []).append(vals)
    return {cid: (dict(vs[0], _copies=vs) if len(vs) > 1 else vs[0]) for cid, vs in by.items()}


_ABSENT = object()   # a field a parser's record does not give, for the presence checks' lookup (D-344)


def _epoch_of(q):
    """A copy's epoch as an instant; None where it is not in the runner's form (D-344)."""
    try:
        return dt.datetime.strptime(str(q.get("epoch")), "%Y-%m-%dT%H:%M:%S.%f")
    except (TypeError, ValueError):
        return None


class _Nearest:
    """Some copies of one id, for _pair_copies: the one nearest an instant, the first of equals, by bisection (D-344)."""

    def __init__(self, eps, ks):
        self.eps = eps
        self.ks = sorted(ks)                                             # every member, in the answer's order
        self.by = sorted((eps[k], k) for k in self.ks if eps[k] is not None)   # those with an epoch, by epoch

    def __bool__(self):
        return bool(self.ks)

    def pick(self, e):
        """The member nearest e in epoch, the first of equals; the first member where either side has no epoch."""
        if e is None or not self.by:
            return self.ks[0]
        i = bisect.bisect_left(self.by, (e, -1))
        near = [(self.by[i][0] - e, self.by[i][1])] if i < len(self.by) else []   # the first at or after e
        if i > 0:                                                                   # the first of those just before it
            el = self.by[i - 1][0]
            near.append((e - el, self.by[bisect.bisect_left(self.by, (el, -1))][1]))
        return min(near)[1]

    def drop(self, k):
        del self.ks[bisect.bisect_left(self.ks, k)]
        if self.eps[k] is not None:
            del self.by[bisect.bisect_left(self.by, (self.eps[k], k))]


def _pair_copies(ts, os_):
    """[(t, o)] for the copies of one id in two answers, every copy of both in a pair (D-344): each copy of ts, in order,
    with the untaken copy of os_ that gives the same element set number and revolution, where it gives both and one is
    left; else with the untaken copy nearest in epoch; else, none left, with the nearest of all; then each copy of os_ no
    copy took with the copy of ts nearest in epoch. The first of equals each time, a bisection each, so a history of
    thousands of element sets is paired at once, with the two numbers or without them."""
    teps, oeps = [_epoch_of(q) for q in ts], [_epoch_of(q) for q in os_]
    groups: dict = {}
    for k, q in enumerate(os_):
        if None not in _ordinal(q):
            groups.setdefault(_ordinal(q), []).append(k)
    by_ordinal = {key: _Nearest(oeps, ks) for key, ks in groups.items()}
    free, every = _Nearest(oeps, range(len(os_))), _Nearest(oeps, range(len(os_)))
    pairs = []
    for t, e in zip(ts, teps):
        key = _ordinal(t)
        pool = (by_ordinal.get(key) if None not in key else None) or (free if free else every)
        k = pool.pick(e)
        pairs.append((t, os_[k]))
        if pool is not every:
            free.drop(k)
            if None not in _ordinal(os_[k]):
                by_ordinal[_ordinal(os_[k])].drop(k)
    near = _Nearest(teps, range(len(ts)))
    for k in list(free.ks):   # a copy of os_ no copy of ts took is compared too
        pairs.append((ts[near.pick(oeps[k])], os_[k]))
    return pairs


def _input_epoch(rec):
    """An input record's epoch as the reference reader read it, in any CCSDS form (calendar or day of year, any
    fraction, a Z, second 60), as an instant; None where it is not one (D-352)."""
    try:
        return dt.datetime.strptime(tlemod.iso_epoch(rec.get("epoch")), "%Y-%m-%dT%H:%M:%S.%f")
    except (TypeError, ValueError, OverflowError):   # OverflowError: a year-9999 epoch that rounds over, as norm_epoch
        return None


class _EmptyCopies:
    """For an id the input holds more than once (D-352): the input's OMM copies whose field the reference reader reads
    empty, by epoch. A parser's OMM copy that returns the field empty takes one of them at its own epoch, within the
    consistency check's own TLE/OMM epoch allowance (TLE_EPOCH_TOLERANCE_US), once for that copy however many TLE copies
    it pairs with, each input copy taken once; where none is left, the parser's copy has no empty input copy to answer
    (the input gives a value there, or holds fewer empty copies than the parser returns, or none within the allowance of
    its epoch, or another of its copies took the one there). Neither
    the parser's element set numbers nor an epoch it leaves out choose the copy it is judged by: a copy with no epoch
    takes none (the item says so), and copies at one epoch are counted, but within the allowance which copy an empty
    answer belongs to is not judged. Each id and field indexed once, each answer a bisection."""

    def __init__(self, recs):
        self.groups: dict = {}
        for r in recs:
            for f in ("eccentricity", "bstar", "mean_motion_ddot"):
                if _empty(r.get(f)):
                    self.groups.setdefault((r.get("norad_cat_id"), f), []).append(r)
        self.pools: dict = {}
        self.answers: dict = {}

    def take(self, cat, f, q):
        """True where q's empty field answers an input copy that leaves it empty (taken now, or earlier by q itself). The
        answer is kept by q's id(), so a caller keeps q alive for as long as it asks (the runner's records live for the
        whole check)."""
        key = (id(q), f)
        if key not in self.answers:
            self.answers[key] = self._take(cat, f, _epoch_of(q))
        return self.answers[key]

    def _take(self, cat, f, e):
        mine = self.groups.get((cat, f))
        if not mine or e is None:
            return False
        if (cat, f) not in self.pools:
            self.pools[(cat, f)] = _Nearest([_input_epoch(r) for r in mine], range(len(mine)))
        pool = self.pools[(cat, f)]
        if not pool.by:
            return False
        k = pool.pick(e)
        if abs((pool.eps[k] - e) / dt.timedelta(microseconds=1)) > TLE_EPOCH_TOLERANCE_US:
            return False
        pool.drop(k)
        return True


class _TleValuesByEpoch:
    """For an id the input holds more than once (D-352): the values the input's TLE copies give at each of their epochs,
    so that a parser's TLE value is compared with what the input's TLE file holds at that copy's epoch, ties included,
    each epoch and field indexed once and each answer a bisection."""

    def __init__(self, recs):
        by: dict = {}
        for r in recs:
            e = _input_epoch(r)
            if e is not None:
                by.setdefault(r.get("norad_cat_id"), {}).setdefault(e, []).append(r)
        self.eps = {cat: sorted(groups) for cat, groups in by.items()}
        self.by = by
        self.values: dict = {}

    def values_near(self, cat, e, f):
        """(texts, numbers): the distinct values of field f the input's TLE copies of cat give at the epoch nearest e,
        sorted as numbers, with those numbers; the numbers None where a value is not one (the texts then in the file's
        order); ([], None) where it holds no copy of cat, ([], []) where its copies at that epoch give no value of f.
        Each epoch and field converted once."""
        eps = self.eps.get(cat)
        if not eps or e is None:
            return [], None
        i = bisect.bisect_left(eps, e)
        near = min((eps[k] for k in (i - 1, i) if 0 <= k < len(eps)), key=lambda x: abs(x - e))
        key = (cat, near, f)
        if key not in self.values:
            texts = list(dict.fromkeys(r[f] for r in self.by[cat][near] if f in r and not _empty(r[f])))
            try:
                pairs = sorted((Decimal(str(v)), v) for v in texts)
                self.values[key] = ([v for _, v in pairs], [d for d, _ in pairs])
            except (ValueError, ArithmeticError, TypeError):
                self.values[key] = (texts, None)
        return self.values[key]


def closest(texts, numbers, got):
    """The one of texts nearest got, by bisection over their numbers (sorted, from values_near); the first of texts
    where they or got are not numbers."""
    try:
        if numbers is None:
            raise ValueError
        g = Decimal(str(got))
        i = bisect.bisect_left(numbers, g)
        return texts[min((k for k in (i - 1, i) if 0 <= k < len(texts)), key=lambda k: abs(numbers[k] - g))]
    except (ValueError, ArithmeticError, TypeError):
        return texts[0]


def tle_side(field, value):
    """An OMM value as its TLE field holds it: the eccentricity truncated to seven decimals, BSTAR and the second
    derivative rounded to a five-digit mantissa, a zero of any exponent as 0; None for a value no TLE field holds as
    providers write it (an eccentricity below 0 or of 1 and more; BSTAR or a second derivative whose exponent, as
    0.ddddd times 10 to it, lies beyond -10 to 9, decided before its digits are written out (D-354), or that rounds
    beyond -9 to 9; a value that is not a finite number). Most of these ended the consistency check as an internal
    error; an eccentricity below 0, or from 1 to about 1E+21, was a plain mismatch (D-351)."""
    try:
        d = Decimal(str(value))
        if not d.is_finite():
            return None
        if field == "eccentricity":
            q = d.quantize(Decimal("0.0000001"), rounding=ROUND_DOWN)
            return q if 0 <= d and q < 1 else None
        if not d:   # a zero, whatever its exponent ("0.0000000000000", 0E-13): the field holds it as 0 (D-354's reading)
            return "0"
        if not -10 <= d.adjusted() + 1 <= 9:   # no field holds it: decided before format() writes out its digits (D-354)
            return None
        return ref.tle_exp_to_plain(tlemod.exp_field(format(d, "f"), "round"))   # its text, as the check compared it before
    except (ValueError, ArithmeticError):
        return None


def _empty(value):
    """A value a record leaves empty: None, or text of spaces alone."""
    return value is None or (isinstance(value, str) and not value.strip())


def saved_meta(full, suffix=".meta.json"):
    """What a fetch recorded beside a provider file (its .meta.json), or {} where it recorded nothing readable: no file,
    a directory, text that is not JSON or JSON that is not an object (D-351)."""
    try:
        with open(full + suffix, encoding="utf-8") as f:
            meta = json.load(f)
        return meta if isinstance(meta, dict) else {}
    except (OSError, ValueError):
        return {}


def _held(ids):
    """{id: how many records of that id an input holds} (D-311)."""
    out = {}
    for i in ids:
        out[i] = out.get(i, 0) + 1
    return out


def annotation_totals(results):
    """Across the cases of a run: `items_skipped` and `field_gaps` (CaseResult.annotations), and `cases_graded`, the
    cases that ended pass, pass within tolerance or fail (D-312). The JSON report's `inside_cases`."""
    out = {"items_skipped": 0, "field_gaps": 0, "cases_graded": sum(1 for r in results if r.status in ("pass", "pass-tolerance", "fail"))}
    for r in results:
        for k, v in r.annotations().items():
            out[k] += v
    return out


def status_totals(results):
    """How many cases ended in each status, as numbers: `cases`, the number of cases run, then every status with its
    count, zeros included. It is the JSON report's `summary` and what the count line is written from, so that a script
    reads the totals and never the printed line (D-240)."""
    totals = {"cases": len(results), **{s: 0 for s in CASE_STATUSES}}
    for r in results:
        totals[r.status] = totals.get(r.status, 0) + 1
    return totals


class CaseResult:
    def __init__(self, case_id, title, purpose=()):
        self.case_id, self.title, self.items, self.modes = case_id, title, [], {}
        self.purpose = tuple(purpose)  # the checks the case lists in the manifest: what the case is for (D-294)
        self.drift = {}  # path -> {recorded_sha256, actual_sha256}: stable-tier sources whose bytes changed (D-115)
        self.refusals, self.declared = {}, {}  # path -> the adapter's refusal entries; path -> its capability declaration (D-144)
        self.reused = {}  # path -> the corpus version whose cache the file was copied from, not fetched (D-157)
        self.unexpected = {}  # path -> what the fetch recorded when the answer for that file was not one it expected (D-228)
        self.on_request = {}  # path -> the fetch's flag for a file it brings only on request, when a data check waits on it (D-232)
        self.recorded = {}  # path -> the corpus's record the fetch wrote this file from, where it requested nothing (D-247)
        self.empty_answers = {}  # path -> the provider's no-data text the file holds
        self.fmt_read = {}        # fmt -> paths this parser read (or graded) in this case (D-280)
        self.fmt_dodged = []      # (fmt, item index, path) for each per-input Unsupported answer (D-280)
        self.secondary_not_kept = []   # the writer case's secondary fields some record lost, for the printed status (D-369)

    def add(self, check, status, file=None, detail="", tolerance=None, counts=None, cause=None):
        if tolerance and status == "pass":
            status = "pass-tolerance"
            detail = (detail + "; " if detail else "") + tolerance.text()
        self.items.append(Item(check, status, file, detail, tolerance, counts, cause))

    def voided_by_parser(self):
        """The checks this case lists whose every item is not-exercised by the parser's own doing (D-294)."""
        out = []
        for chk in self.purpose:
            items = [i for i in self.items if i.check == chk]
            if items and all(i.status == "not-exercised" and i.cause == "parser" for i in items):
                out.append(chk)
        return out

    @property
    def status(self):
        # not-fetched ranks above skip: a case with no provider data on disk says so, and never borrows skip, which
        # means the parser has no reader for the format (D-148). A case that ran on some of its files keeps the
        # result of those files; its missing ones are counted under not-fetched and named below the table.
        # not-available ranks below not-fetched (D-229): a case with anything still to fetch says that, since it is
        # what the user can act on; a case all of whose provider files are launch-window captures can never run
        # from a fetch and says not-available.
        st = {i.status for i in self.items}
        if "fail" in st:
            return "fail"
        # D-294 (the red team's E8): a case cannot read "pass" when a check it exists for was voided by the parser
        # itself -- a record it drops from the unedited file as well is not graded (D-175), and a case all of whose
        # corrupt checks went that way used to print "pass". Such a case reads not-exercised: nothing failed, and
        # what the case is for was not measured. Data-caused not-exercised items (no nine-digit id in a fresh
        # fetch) leave the ranking as it was.
        if self.voided_by_parser():
            return "not-exercised"
        for s in ("pass-tolerance", "pass", "not-exercised", "not-fetched", "not-available"):
            if s in st:
                return s
        return "skip"

    def annotations(self):
        """What a case's status does not say by itself (D-312, the second red team's F2 and F3): `items_skipped`, the
        items that skipped because the parser answered unsupported or has no hook, inside a case that did not skip
        as a whole; and `field_gaps`, the files in which a field with expected values was never returned
        (`fields-not-returned`). Zeros for a case that skipped, was not fetched or is not available."""
        if self.status not in ("pass", "pass-tolerance", "fail", "not-exercised"):
            return {"items_skipped": 0, "field_gaps": 0}
        return {"items_skipped": sum(1 for i in self.items if i.status == "skip"),
                "field_gaps": sum(1 for i in self.items if i.check == "fields-not-returned")}

    def status_text(self):
        """The status as the table prints it: the status, then what it leaves out, as `pass (1 item skipped, 2 field
        gaps)`. The status itself, the counts and the exit code are untouched (D-312)."""
        a = self.annotations()
        notes = ([f"{qty(a['items_skipped'], 'item')} skipped"] if a["items_skipped"] else []) + ([qty(a["field_gaps"], "field gap")] if a["field_gaps"] else [])
        if self.secondary_not_kept:
            # the writer's secondary fields stay information (D-095), but a pass that changed or dropped them says so
            # where the status is read, not only under -v (D-369; the blind review's finding 2)
            notes.append(f"{qty(len(self.secondary_not_kept), 'secondary field')} not kept")
        return self.status + (f" ({', '.join(notes)})" if notes else "")

    def missing(self):
        """Provider files this case names that were not on disk and that a fetch can bring (D-148)."""
        return [i.file for i in self.items if i.status == "not-fetched"]

    def unavailable(self):
        """Provider files this case names that no fetch requests: launch-window captures (D-229)."""
        return [i.file for i in self.items if i.status == "not-available"]

    def counts(self):
        c = {"pass": 0, "pass-tolerance": 0, "fail": 0, "skip": 0, "not-exercised": 0, "not-fetched": 0, "not-available": 0, "info": 0}
        for i in self.items:
            c[i.status] = c.get(i.status, 0) + 1
        return c

    def as_dict(self):
        d = {"case": self.case_id, "title": self.title, "status": self.status, "counts": self.counts(),
             "modes": self.modes, "drift": self.drift, "items": [i.as_dict() for i in self.items]}
        if self.voided_by_parser():
            d["voided_by_parser"] = self.voided_by_parser()
        if any(self.annotations().values()):
            d["annotations"] = self.annotations()   # D-312: item skips and field gaps inside a case that did not skip
        if self.reused:
            d["reused"] = self.reused
        if self.unexpected:
            d["unexpected"] = self.unexpected
        if self.on_request:
            d["on_request"] = self.on_request
        if self.recorded:
            d["recorded"] = self.recorded
        return d


# --------------------------------------------------------------------------- the runner
def leading_dot_keywords(text, fmt):
    """OMM keywords whose value is written without a leading zero ('.00048259', '-.15975118E-3') in a CSV, KVN or XML text."""
    kws = set()
    if fmt == "csv":
        import csv as _csv
        import io as _io
        for row in _csv.DictReader(_io.StringIO(text)):
            kws |= {k for k, v in row.items() if k and isinstance(v, str) and re.match(r"^-?\.\d", v.strip())}
    elif fmt == "kvn":
        kws |= set(re.findall(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*-?\.\d", text, re.M))
    elif fmt == "xml":
        kws |= set(re.findall(r"<([A-Z][A-Z0-9_]*)>\s*-?\.\d", text))
    return kws


def describe_bytes(raw, fmt=None, limit=48):
    """What a file the reference reader could not read looks like: size, first bytes, and a guess (D-113)."""
    n = len(raw)
    guesses = []
    if n == 0:
        guesses.append("empty file")
    elif not raw.strip():
        guesses.append("whitespace only")
    if raw.startswith(b"\xef\xbb\xbf"):
        guesses.append("UTF-8 BOM prefix")
    low = raw[:1024].lower()
    if low.lstrip().startswith(b"<!doctype") or b"<html" in low:
        guesses.append("HTML document (an error or challenge page?)")
    if raw.strip() in (b"No GP data found", b"No SupGP data found"):
        guesses.append("CelesTrak's empty-response text")
    if fmt in ("tle", "2le", "3le") and re.search(rb"^1 ", raw, re.M) and not re.search(rb"^2 ", raw, re.M):
        guesses.append("a TLE line 1 without a line 2 (truncated?)")
    if fmt == "csv" and n and raw.count(b"\n") <= 1 and b"," in raw:
        guesses.append("CSV header only")
    return f"{qty(n, 'byte')}, starts with {raw[:limit]!r}" + (f"; looks like: {', '.join(guesses)}" if guesses else "")


class _HookCalls:
    """One vector hook, counting the vectors it declares unsupported (a raise of Unsupported), so that an operation the
    library does not have skips its item, for all of its vectors or none (D-205)."""

    def __init__(self, name, hook):
        self.name, self.hook, self.calls, self.unsupported, self.reasons = name, hook, 0, 0, []

    def __call__(self, value):
        self.calls += 1
        try:
            out = self.hook(value)
            if type(out) is plain.Problem:   # an answer that holds one thing and shows another, in its words (D-337)
                return f"(an answer that {out.what})"
            return out
        except Unsupported as e:
            self.unsupported += 1
            reason = str(e).strip() or "no reason given"
            if reason not in self.reasons:
                self.reasons.append(reason)
            raise


def _vector_item(res, check, file, calls, bad, ok_detail):
    """The item for one hook: skip when the parser declared every vector unsupported, fail when it declared only some,
    since an operation is unsupported for all of its vectors or none, else pass or fail on the vectors (D-205)."""
    if calls.unsupported and calls.unsupported == calls.calls:
        res.add(check, "skip", file, f"parser reports {calls.name} unsupported: {'; '.join(calls.reasons)}")
    elif calls.unsupported:
        res.add(check, "fail", file, f"{calls.name} answered unsupported for {calls.unsupported} of {qty(calls.calls, 'vector')} "
                f"({'; '.join(calls.reasons)}) and answered the rest: an operation is unsupported for all of its vectors or none"
                + (f"; {'; '.join(bad[:8])}" if bad else ""))
    else:
        res.add(check, "fail" if bad else "pass", file, "; ".join(bad[:8]) if bad else ok_detail)


class Runner:
    def __init__(self, parser, root=None, verbose=False, data=None, data_why=None, fetch_hints=True):
        self.parser_exits = []   # (where, what) for every attempt of the parser to end the run (D-293)
        # by its type: a parser whose __class__ said _Guarded was left unwrapped, its own comparisons deciding checks (D-342)
        self.parser = parser if type(parser) is _Guarded else _Guarded(parser, self.parser_exits)
        # Two roots (D-150): the corpus root holds what ships (manifest, expected values, derived/, vectors/), the
        # data root the provider files this machine fetched. With no root given, both are resolved as the command
        # line resolves them (a clone, or the installed corpus and a per-user cache); with a root and no data, the
        # provider files are looked for under the root, the layout of a clone and of every test.
        if root is None:
            from . import locate
            loc = locate.resolve(None, data)
            root, data, data_why = loc["corpus"], loc["data"], loc["data_why"]
        self.root = root
        self.data = data or root
        self.data_why = data_why or ("--data" if data else "--root")
        # False for a run that is offline by design, the GitHub Action's: its data folder is empty and discarded with
        # the job, so a command that fetches into it would be wrong advice (D-158)
        self.fetch_hints = fetch_hints
        self.verbose = verbose
        self.manifest = json.load(open(os.path.join(self.root, "manifest.json"), encoding="utf-8"))
        self.launch_window = launch_window_files(self.root)
        self.opt_in = opt_in_files(self.root)

    def path(self, rel):
        """A source's path on disk: provider data under the data root, everything that ships under the corpus root."""
        return os.path.join(self.data if is_provider_data(rel) else self.root, rel)

    def hint(self, *args):
        return fetch_hint(self.root, *args, data=self.data, data_why=self.data_why)

    # ---- parsing helpers
    def parse(self, path, fmt):
        raw = open(path, "rb").read()
        fn = getattr(self.parser, "parse", None) or self.parser
        recs, self._refusals, self._declared = split_refusals(as_records(fn(raw, fmt)))
        raw_text = raw.decode("utf-8", "replace")
        out = []
        for r in recs:
            n, notes, bad = norm_record(r)
            n["_notes"] = notes
            if unparsed_epoch(r.get("epoch"), raw_text):   # D-306: graded as a wrong epoch, not parsed for the parser
                bad["epoch"] = f"{r.get('epoch')!r} is the input's own epoch text, passed back unparsed"
            if bad:
                n["_bad"] = bad
            out.append(n)
        return out

    def page_in_place(self, res, path, full, meta, src):
        """A response an earlier fetch saved in the data's place, refused in load_source's words (D-228), and in
        run_satcat's, which read it as a SATCAT file (D-351)."""
        got = meta.get("http_status")
        res.unexpected[path] = {"http_status": got, "at": meta.get("retrieved_at"), "why": f"HTTP {got}", "kept": os.path.basename(full),
                                "in_place": True}
        res.add("source-present", "not-fetched", path,
                f"holds an HTTP {got} response that an earlier fetch saved in the data's place"
                + (f" at {meta['retrieved_at']}" if meta.get("retrieved_at") else "")
                + ", where the corpus records HTTP " + str(src.get("http_status", 200))
                + ": not provider data, and not read"
                + (("; delete the file and its .meta.json, then fetch it again"
                    + (f" with {self.hint(self.opt_in[path])}" if path in self.opt_in else "")) if self.fetch_hints else ""))

    def launch_window_detail(self, path):
        return (f"not on disk: a launch-window capture ({self.launch_window[path]}). CelesTrak serves launch nominals for "
                "the days after a launch; the corpus captured this file then, and no fetch requests it")

    def unexpected_response(self, path):
        """What the fetch kept when its last answer for this provider file was not one it expected (D-228): the
        response sits beside the data as <file>.unexpected, never in its place -> {'http_status', 'at', 'why',
        'kept'}, or None when there is none."""
        full = self.path(path)
        if not os.path.exists(full + ".unexpected"):
            return None
        meta = saved_meta(full, ".unexpected.meta.json")
        status = meta.get("http_status")
        return {"http_status": status, "at": meta.get("retrieved_at"),
                "why": meta.get("unexpected") or (f"HTTP {status}" if status else "a response it did not expect"),
                "kept": os.path.basename(full) + ".unexpected"}

    def report_missing(self, res, path):
        """A source file that is not on disk. Provider data is reported as not-fetched with the command that fetches
        it; a file that ships with the corpus stops the run, since the copy itself is incomplete (D-148). When the
        fetch asked for the file and got a response it did not expect, the item says so and names no command: a
        plain fetch does not ask again (D-228)."""
        if not is_provider_data(path):
            raise CorpusIncomplete(f"{path} ships with the corpus and is not on disk under {self.root}: "
                                   f"this copy of the corpus is incomplete; re-clone {REPO_URL} or reinstall")
        if path in self.launch_window:
            res.add("source-present", "not-available", path, self.launch_window_detail(path))
            return
        unexp = self.unexpected_response(path)
        if unexp:
            res.unexpected[path] = unexp
            res.add("source-present", "not-fetched", path,
                    f"not on disk: the fetch got {unexp['why']} for it" + (f" at {unexp['at']}" if unexp["at"] else "")
                    + f" and kept that response as {unexp['kept']}, which is not provider data and is not read"
                    + ("; the fetch asks again only with --force, two hours or more after that answer" if self.fetch_hints else ""))
            return
        if path in self.opt_in:  # a plain fetch does not bring it, so the command names the flag that does (D-231)
            res.add("source-present", "not-fetched", path,
                    "not on disk: the fetch brings this file only on request, since no parser takes part in the check that reads it"
                    + (f"; fetch it with {self.hint(self.opt_in[path])}" if self.fetch_hints else ""))
            return
        res.add("source-present", "not-fetched", path, "not on disk: provider data is not shipped with the corpus"
                + (f"; fetch it with {self.hint()}" if self.fetch_hints else ""))

    def load_source(self, res, case, path, src):
        """Returns (state, fmt, mode, parsed, refrecs, reffacts). state: ok | missing | empty-404 | unreadable | parse-error | unsupported"""
        full = self.path(path)
        fmt = src.get("format")
        if not os.path.exists(full):
            self.report_missing(res, path)
            return "missing", fmt, None, None, None, None
        if is_provider_data(path) and os.path.exists(full + ".meta.json"):
            # a list, a string or a directory there ended the case as "internal error in runner" (D-351)
            meta = saved_meta(full)
            came = meta.get("reused_from")  # reused rather than fetched (D-157)
            if isinstance(came, dict) and came:
                res.reused[path] = came.get("corpus_version")
            if meta.get("provenance") == "recorded":  # written by the fetch from the corpus's record, not requested (D-247)
                recorded = meta.get("recorded")
                res.recorded[path] = {"file": recorded.get("file") if isinstance(recorded, dict) else None, "http_status": meta.get("http_status"),
                                      "captured_at": meta.get("retrieved_at")}
            got = meta.get("http_status")
            if got not in (None, 200) and got != src.get("http_status", 200):
                # A fetch before v0.5.1 wrote a response it did not expect to the data path itself, "so it is never
                # re-requested". It is not the source, and reading it would charge the parser with an error page or
                # with the provider's no-data text where data is recorded (D-228).
                if path in self.launch_window:  # what a fetch before v0.5.1 met once the window had closed (D-229)
                    res.add("source-present", "not-available", path, self.launch_window_detail(path)
                            + f"; the file on disk holds an HTTP {got} response that an earlier fetch saved in its place, and is not read")
                    return "missing", fmt, None, None, None, None
                self.page_in_place(res, path, full, meta, src)
                return "missing", fmt, None, None, None, None
        actual = sha256(full)
        mode = "snapshot" if actual == src.get("sha256") else "live"
        res.modes[path] = mode
        if mode == "live" and src.get("tier") == "stable":
            # A stable-tier source is frozen by promise; changed bytes are reported, never silently downgraded (D-115).
            res.drift[path] = {"recorded_sha256": src.get("sha256"), "actual_sha256": actual}
            res.add("stable-source-drift", "fail", path,
                    f"stable-tier source's bytes differ from the tested snapshot (recorded SHA-256 {str(src.get('sha256'))[:12]}…, actual {actual[:12]}…); "
                    "the frozen expected values were not applied to this file and the parser was compared against the corpus's reference reader instead. "
                    + (f"Run {self.hint('--check-drift')}; if" if self.fetch_hints else "If")
                    + " CelesTrak changed this first-ever record, tell the corpus maintainer.")
        raw = open(full, "rb").read()
        text = raw.decode("utf-8", "replace")
        if src.get("http_status", 200) != 200 or text.strip() in ("No GP data found", "No SupGP data found"):
            if text.strip() in ("No GP data found", "No SupGP data found"):
                res.empty_answers[path] = text.strip()
                if "empty-answer-yields-no-records" in case.get("checks", []):
                    self.check_empty_answer(res, path, fmt, raw, text.strip(), src.get("http_status"))
                return "empty-404", fmt, mode, [], [], {}
        if fmt in ("satcat-json", "satcat-csv", "satcat-legacy-fixed-width", "vectors-json"):
            return "data", fmt, mode, None, None, None
        try:
            _, refrecs, reffacts = ref.read_file(full)
        except ValueError as e:  # the reader rejected the file: a BOM, a namespace, a duplicate keyword, a bad day (D-117)
            res.add("reference-reader", "fail", path, f"reference reader rejected the file: {e}")
            return "parse-error", fmt, mode, None, None, None
        except Exception as e:  # the corpus's own reader failed: report, do not hide
            res.add("reference-reader", "fail", path, f"internal: reference reader raised {e!r}")
            return "parse-error", fmt, mode, None, None, None
        # A file the reference reader reads nothing from is not a file with nothing in it (D-113): the checks
        # below would all pass on zero records. The manifest's record_count says what the file should hold.
        expected_n = src.get("record_count")
        if isinstance(expected_n, int) and expected_n > 0 and not refrecs:
            res.add("source-readable", "fail", path,
                    f"reference reader found 0 of {qty(expected_n, 'expected record')}; the file is {describe_bytes(raw, fmt)}")
            return "unreadable", fmt, mode, None, refrecs, reffacts
        if mode == "snapshot" and isinstance(expected_n, int) and len(refrecs) != expected_n:
            res.add("source-readable", "fail", path,
                    f"internal: reference reader found {len(refrecs)} of {qty(expected_n, 'recorded record')} in a file whose hash matches the tested snapshot")
            return "unreadable", fmt, mode, None, refrecs, reffacts
        try:
            parsed = self.parse(full, fmt)
        except Unsupported:
            res.add("format-supported", "skip", path, f"parser reports {fmt} unsupported")
            res.fmt_dodged.append((fmt, len(res.items) - 1, path))
            return "unsupported", fmt, mode, None, refrecs, reffacts
        except Exception as e:
            res.add("parse", "fail", path, parse_failure(e))
            return "parse-error", fmt, mode, None, refrecs, reffacts
        res.fmt_read.setdefault(fmt, []).append(path)
        res.refusals[path], res.declared[path] = self._refusals, self._declared
        self.report_refusals(res, path, self._refusals)
        if refrecs and not parsed:
            # Fail closed (D-144): a file the reference reads records from, for which the parser returned none, is not a
            # file with nothing in it. Every per-file check would pass on zero records, so none of them runs; the item
            # names what happened to the records, refused with a reason or dropped.
            refs = self._refusals
            with_reason = [r for r in refs if r["ok"]]
            want = _held(r["norad_cat_id"] for r in refrecs)
            per: dict = {}   # refusals with a reason, by id; each credits one record of its id, the records without one once, as before (D-344)
            for r in with_reason:
                if r["id"] in want:
                    per[r["id"]] = per.get(r["id"], 0) + 1
            credited = sum(min(n, 1 if i is None else want[i]) for i, n in per.items())
            top = sorted(((n, reason) for reason, n in collections.Counter(r["reason"] for r in with_reason).items()), reverse=True)   # each counted once (D-356)
            counts = {"expected": len(refrecs), "returned": 0, "loaded": 0, "misidentified": 0, "dropped": len(refrecs) - credited,
                      "extra": 0, "ids_not_returned": len(want) - len(per),
                      "non_integer_id": 0, "refused": len(with_reason), "refused_matched": credited,
                      "refused_without_reason": len(refs) - len(with_reason), "refusals_reported": self._declared,
                      "top_refusal_reason": top[0][1] if top else None}
            what = (f"{credited} refused with a reason ({top[0][1][:120]})" if credited else "") + (", " if credited and counts["dropped"] else "") + \
                   (f"{counts['dropped']} dropped" + (" silently" if self._declared else " (refusals not reported by this adapter)") if counts["dropped"] else "")
            res.add("records-returned", "fail", path, f"parser returned 0 of {qty(len(refrecs), 'record')}: {what}", counts=counts)
            return "parse-error", fmt, mode, None, refrecs, reffacts
        return "ok", fmt, mode, parsed, refrecs, reffacts

    def check_surplus(self, res, path, parsed, refrecs):
        """D-311's surplus rule in the cases with no values item, the pairs, facts and XML cases (2e, D-346): a parser
        returning more copies of an id than the input holds fails `records-returned`, in D-311's words, as the values item
        fails it in the other cases, and so does one returning a record under a catalog number the file does not hold, or
        with none, in the values item's words (D-348); a parser that returns neither adds no item. Before, run alone, a pairs or facts case
        passed a surplus copy, and the XML case one standing in for a dropped record, its count of <omm> elements unchanged
        (in a full run, the values item of another case read the same file and failed it)."""
        held = _held(r["norad_cat_id"] for r in refrecs or [])
        got = _held(q.get("norad_cat_id") for q in parsed or [])
        over = [(i, n, held[i]) for i, n in got.items() if i is not None and i in held and n > held[i]]
        words = ["; ".join(f"id {i}: returned {qty(n, 'time')} where the input holds it {'once' if h == 1 else qty(h, 'time')} (D-311)"
                           for i, n, h in over[:12]) + (" ..." if len(over) > 12 else "")] if over else []
        # and a record under a catalog number the file does not hold, or with none where the file's records all carry one,
        # in the values item's words: no check of a pairs case read it, nor of the facts or XML case for an integer id in
        # place of one the file holds, so run alone such a case passed it (D-346's reading, its finding 1; D-348)
        unexpected = list(dict.fromkeys(i for i in (q.get("norad_cat_id") for q in parsed or []) if i is not None and i not in held))
        if unexpected:
            words.append(f"{qty(len(unexpected), 'unexpected record id')}, e.g. {unexpected[:3]}")
        if None not in held:
            nameless = [q for q in parsed or [] if q.get("norad_cat_id") is None]
            non_int = [q["_bad"]["norad_cat_id"] for q in nameless if q.get("_bad", {}).get("norad_cat_id")]
            if non_int:
                words.append(f"{qty(len(non_int), 'record')} whose norad_cat_id is not an integer, e.g. " + ", ".join(non_int[:3]))
            if len(nameless) - len(non_int):
                words.append(f"{qty(len(nameless) - len(non_int), 'record')} without norad_cat_id")
        if words:
            res.add("records-returned", "fail", path, "; ".join(words))

    def report_refusals(self, res, path, refusals):
        """One item per file that carries refusals (D-144): the reasons with their counts; a refusal without a reason fails it."""
        if not refusals:
            return
        reasons = {}
        for r in refusals:
            if r["ok"]:
                reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
        no_reason = sum(1 for r in refusals if not r["ok"])
        text = f"{len(refusals) - no_reason} refused with a reason" + ("" if not reasons else ": " + "; ".join(
            f"{reason[:120]!r} x{n}" for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1])[:5]))
        if no_reason:
            text += (f"; {qty(no_reason, 'refusal')} without a reason, counted as no refusal, crediting no record: a refusal "
                     f"that gives no reason is no better than a drop")
        res.add("refusals", "fail" if no_reason else "info", path, text)

    # ---- value comparison
    def compare_values(self, res, path, fmt, mode, parsed, oracle, check="values", exempt=None, partial=False, oracle_label=None, held=None, held_in_file=None):
        """oracle: {id: {field: value}}, an id the input holds more than once carrying all its records under "_copies"
        (D-343); parsed: list of normalised dicts. partial: oracle lists a subset of the file.
        held: {id: how many records of that id the input holds}; an id it does not name is held once (D-311).
        held_in_file: the same for every id of the file, by the reference reader, where the oracle is partial."""
        exempt = exempt or set()
        held = held or {}
        tol = TolStats()
        by_id = {}
        for p in parsed:
            if p.get("norad_cat_id") is None:
                by_id.setdefault(None, []).append(p)
            else:
                by_id.setdefault(p["norad_cat_id"], []).append(p)
        fails = []
        if None in by_id and "norad_cat_id" not in exempt:
            non_int = [p["_bad"]["norad_cat_id"] for p in by_id[None] if p.get("_bad", {}).get("norad_cat_id")]
            absent = len(by_id[None]) - len(non_int)
            if non_int:
                fails.append(f"{qty(len(non_int), 'record')} whose norad_cat_id is not an integer, e.g. " + ", ".join(non_int[:3]))
            if absent:
                fails.append(f"{qty(absent, 'record')} without norad_cat_id")
        missing_ids = [i for i in oracle if i not in by_id]
        refusals = res.refusals.get(path, [])
        with_reason = [r for r in refusals if r["ok"]]
        refused_ids = {r["id"] for r in with_reason if r["id"] is not None and r["id"] in oracle and r["id"] not in by_id}
        reasons: dict = {}   # refusals with a reason, by id
        for r in with_reason:
            reasons[r["id"]] = reasons.get(r["id"], 0) + 1

        def times(i):
            """The records the input holds of an id, the records without one counted once, as before (D-344)."""
            return 1 if i is None else held.get(i, 1)
        if missing_ids and "norad_cat_id" not in exempt:
            lost = sum(times(i) for i in missing_ids)   # in records, as the counts are (D-344)
            if refused_ids:
                credited = sum(min(reasons.get(i, 0), times(i)) for i in refused_ids)
                silent = [i for i in missing_ids if i not in refused_ids or reasons[i] < times(i)]
                eg = next((r for r in with_reason if r["id"] in refused_ids), None)
                fails.append(f"{qty(lost, 'expected record')} not returned: {credited} refused with a reason"
                             + (f" (e.g. {eg['field']!r}: {eg['reason'][:100]})" if eg else "") + f", {lost - credited} silently" + (f", e.g. {silent[:3]}" if silent else ""))
            else:
                fails.append(f"{qty(lost, 'expected record')} not returned, e.g. {missing_ids[:3]}")
        extra = [i for i in by_id if i is not None and i not in oracle]
        if extra and not partial:
            fails.append(f"{qty(len(extra), 'unexpected record id')}, e.g. {extra[:3]}")
        outside_copies = 0   # surplus copies of the file's ids outside the compared subset, counted in extra (D-349)
        if partial and held_in_file:
            # D-311 where the frozen values cover a subset of the file: the ids outside the subset are not compared,
            # but one returned more often than the file holds it is a surplus copy all the same
            over = [i for i in extra if i in held_in_file and len(by_id[i]) > held_in_file[i]]
            outside_copies = sum(len(by_id[i]) - held_in_file[i] for i in over)
            if over:
                fails.append(f"{qty(len(over), 'id')} outside the compared subset returned more often than the input holds {pick(len(over), 'it', 'them')}, "
                             f"e.g. {over[:3]} (D-311)")
            # and an id the file does not hold at all is a record no input has, failed as it is where the values cover the
            # whole file; where they cover part of it, it passed (D-348's reading, its finding 3; D-349)
            unknown = [i for i in extra if i not in held_in_file]
            if unknown:
                fails.append(f"{qty(len(unknown), 'unexpected record id')}, e.g. {unknown[:3]}")
            # and the file's own records outside the subset, which no frozen value grades, are still the file's: one that
            # comes back neither as a record nor as a refusal with a reason has been dropped, which passed, even all 11,114
            # of starlink-all.csv's (D-349's reading, its finding 5; the owner's ruling: fixed here)
            lost = {i: n - len(by_id.get(i, [])) - reasons.get(i, 0) for i, n in held_in_file.items() if i is not None and i not in oracle}
            lost = {i: k for i, k in lost.items() if k > 0}
            if lost:
                fails.append(f"{qty(sum(lost.values()), 'record')} outside the compared subset neither returned nor refused with a reason that "
                             f"names it, e.g. {list(lost)[:3]}")
        # the fields this parser ever returns in this file (D-284): one with expected values that never comes
        # back is a visible gap below, not a silent pass; one returned for some records and omitted for others fails
        returned_fields = set()
        for pr in parsed:
            returned_fields.update(k for k in pr if not k.startswith("_"))
        compared, dup_surplus, repeated, loaded_records, short_by_id = 0, 0, [], 0, {}
        graded_records = 0   # expected records graded, loaded or not, one copy each at most: the words' number (D-357)

        def compare_copy(cat, got, want, tag, who=None):
            """One returned copy against one of the input's records: its failures, and its values within tolerance. who:
            the record's name in the words, "id N" unless given (D-358)."""
            name = who or f"id {cat}"
            out, tols = [], []
            for field in CORE_FIELDS + OPTIONAL_FIELDS:
                if field in exempt:
                    # a value the guard could not read as an integer, or an empty text, is no absent keyword: it was read as
                    # None and passed ("garbage", NaN or "" for the id, "x", 1.5 or NaN for a counter; D-358)
                    marked = got.get("_bad", {}).get(field) or ("'' (an empty text)" if got.get("_notes", {}).get(field) == "empty text" else None)
                    if got.get(field) is not None or marked:
                        out.append(f"{name}: {field} should be absent/None (keyword omitted in source), got "
                                   f"{marked or repr(got.get(field))}{tag}" + (" (D-358)" if marked else ""))
                    continue
                if field not in got:
                    if field in CORE_FIELDS:
                        out.append(f"{name}: core field {field} missing from parser output{tag}")
                    elif want.get(field) is not None and field in returned_fields:
                        out.append(f"{name}: {field} omitted here but returned elsewhere in this file (D-284){tag}")
                    continue
                if field in got.get("_bad", {}):
                    out.append((f"{name}: epoch {got['_bad'][field]} (D-306){tag}" if field == "epoch" else
                                  f"{name}: {field} is not an integer: {got['_bad'][field]}{tag}"))
                    continue
                if field in INT_FIELDS and got.get(field) is not None and got.get("_notes", {}).get(field) not in (None, "int"):
                    # D-283: the protocol says integers for the catalog number and the counters; a float or a
                    # string that converts cleanly is still the wrong type, reported with D-131's value-and-type
                    out.append(f"{name}: {field} returned as {got['_notes'][field]} ({got.get(field)!r}), not int{tag}")
                    continue
                if field in OPTIONAL_FIELDS and want.get(field) is None and got.get(field) is None:
                    continue
                if field in OMM_CONSTANT_DEFAULTS and want.get(field) is None:
                    if got.get(field) in (None,) + OMM_CONSTANT_DEFAULTS[field]:
                        continue  # the format carries no value; None or the OMM constant default (D-285)
                    out.append(f"{name}: {field} = {got.get(field)!r} invented where the format carries no value "
                                 f"(None or {' / '.join(OMM_CONSTANT_DEFAULTS[field])} expected; D-285){tag}")
                    continue
                result, diff = compare_value(field, got.get(field), want.get(field), got.get("_notes", {}).get(field))
                if result == "mismatch" and field == "epoch" and want.get("_epoch_also"):
                    result, diff = compare_value(field, got.get(field), want["_epoch_also"])   # the leap second's other instant
                if result == "mismatch":
                    out.append(f"{name}: {field} = {got.get(field)!r}, expected {want.get(field)!r}{tag}")
                elif result == "tolerance":
                    tols.append((field, diff))
            return out, tols

        via_none = 0
        for cat, want in oracle.items():
            got_list = by_id.get(cat) if "norad_cat_id" not in exempt else (by_id.get(cat) or by_id.get(None))
            if not got_list:
                continue
            good = len(got_list)   # the copies counted loaded or duplicate; every copy is graded
            who = f"id {cat}"
            if "norad_cat_id" in exempt and (cat is None or not by_id.get(cat)):
                # Graded through the records without an id, which are not also misidentified (D-357). Where the file's bytes
                # are not the snapshot's, the oracle is the reference reader's, keyed None as the record is (D-355's second
                # reading). A record whose id is not an integer (the guard's `_bad`) is misidentified, as ADAPTERS.md
                # defines it, and is counted neither loaded nor a duplicate copy (D-357, D-356's first reading)
                good = sum(1 for p in got_list if not p.get("_bad", {}).get("norad_cat_id"))
                via_none += good
                who = "the record whose id the file leaves out"   # no copy carried the id (D-357, D-356's second reading)
            if good:   # an id no copy came back under, the copies' ids not integers, is an id not returned (D-357)
                compared += 1
            # every copy is graded against the input's record (the one record of its id, or, where the input holds the
            # id more than once, the one it is paired with, D-343) and the record keeps ONE outcome (D-194, D-281). D-311
            # (the second red team's F1), reversing D-281's second half: a record fails when the parser returns more
            # copies of its id than the input holds, exact copies included -- a parser that emitted every record
            # twice passed. The surplus is still counted in `extra` and `duplicate_copies`. Where the id is exempt
            # (a KVN file whose keyword is absent) the record is matched through the records that carry no id, and
            # they are counted the same way: the file holds one record, and two came back; but a copy whose id is not an
            # integer, in the surplus D-311 fails, is misidentified, not a duplicate copy (D-357)
            surplus = max(0, len(got_list) - held.get(cat, 1))
            dup_surplus += max(0, good - held.get(cat, 1))
            if surplus:
                h = held.get(cat, 1)
                fails.append(f"{who}: returned {qty(len(got_list), 'time')} where the input holds it {'once' if h == 1 else qty(h, 'time')} (D-311)")
            # the other side of D-311 (2b): an id the input holds more than once, returned fewer times, has lost a
            # record, which passed while every copy was compared with one record of it (D-344)
            short = max(0, times(cat) - len(got_list))
            if short:
                short_by_id[cat] = short
                fails.append(f"id {cat}: returned {'once' if len(got_list) == 1 else qty(len(got_list), 'time')} where the input holds it "
                             f"{qty(times(cat), 'time')} (D-344)")
            loaded_records += min(good, times(cat))
            graded_records += min(len(got_list), times(cat))
            records = want.get("_copies") or [want]
            if len(records) == 1:
                paired = [(got, 0) for got in got_list]
            else:
                # an id the input holds more than once (a live file can): each copy is compared with the input's record it
                # matches, where every copy was compared with one record and a correct parser failed (D-311's stated
                # limit; D-343)
                paired = _match_copies(got_list, records, _pairing_cost(lambda g, r: compare_copy(cat, g, r, "", who)))
                for got, ri in paired:
                    got["_record"] = records[ri]   # the record the field-form checks compare this copy with (D-343)
                if cat is not None and any(_values(r) != _values(records[0]) for r in records[1:]):
                    repeated.append((cat, len(records)))
            for ci, (got, ri) in enumerate(paired):
                tag = ("" if len(got_list) == 1 and len(records) == 1 else
                       f" (copy {ci + 1} of {len(got_list)})" if len(records) == 1 else
                       f" (copy {ci + 1} of {len(got_list)}, against the input's record {ri + 1} of {len(records)})")
                f, tols = compare_copy(cat, got, records[ri], tag, who)
                fails.extend(f)
                for field, diff in tols:
                    tol.add(field, diff)
        label = oracle_label or ("frozen expected values" if mode == "snapshot" else "reference-reader values (live bytes; not the human-verified snapshot)")
        # Record counts by identity (D-142), one outcome per expected record (D-194, D-207): loaded = returned with the
        # expected integer id; misidentified = returned with an id that is absent, not an integer, or not one the file holds
        # (the oracle's ids, or, where the frozen values cover part of the file, the file's, D-349); refused_matched = refused with a reason and credited to an expected record; dropped = the expected records
        # left, with no record returned at all and no refusal. A record returned under a wrong id is counted once, as
        # misidentified, and stands in for one of the expected records left; ids_not_returned keeps the count of expected
        # ids no record came back under (what dropped meant before 0.5.0); when more misidentified records come back than
        # there are expected records left, the surplus is counted as extra, never subtracted below zero.
        top = sorted(((n, reason) for reason, n in collections.Counter(r["reason"] for r in with_reason).items()), reverse=True)   # each counted once (D-356)
        # misidentified: a record with no catalog number, or one the file does not hold; where the frozen values cover part
        # of a file, its other records are the file's own and in no count but `returned` (they were counted misidentified,
        # 11,114 of them for a correct parser, and stood in for expected records a parser dropped; D-349)
        outside = held_in_file if partial and held_in_file else {}
        misidentified = sum(len(v) for k, v in by_id.items() if k is None or (k not in oracle and k not in outside))
        # where the id is exempt (a KVN file without the keyword), the records without one that were graded as its expected
        # records are those records, not misidentified: the one record of such a file read loaded 1, misidentified 1,
        # extra 1, and a copy beyond it is counted a duplicate copy, as on a file that carries its id (D-357)
        misidentified -= min(via_none, len(by_id.get(None, [])))
        # counted in records, not ids (2c, D-344): an id the input holds twice is two expected records; a refusal with a
        # reason credits one record of its id, of those no copy came back for. Where every id is held once, as in every
        # frozen input, each count is what it was, and so are the records without a catalog number, counted once.
        expected_records = sum(times(i) for i in oracle)
        refused_records = (sum(min(reasons.get(i, 0), times(i)) for i in refused_ids)
                           + sum(min(reasons.get(i, 0), n) for i, n in short_by_id.items()))
        unaccounted = max(0, expected_records - loaded_records - refused_records)
        counts = {"expected": expected_records, "returned": len(parsed), "loaded": loaded_records, "misidentified": misidentified,
                  "dropped": max(0, unaccounted - misidentified), "extra": max(0, misidentified - unaccounted) + dup_surplus + outside_copies,
                  "duplicate_copies": dup_surplus + outside_copies,
                  "ids_not_returned": max(0, len(oracle) - compared - len(refused_ids)),
                  "non_integer_id": len([p for p in by_id.get(None, []) if p.get("_bad", {}).get("norad_cat_id")]),
                  "refused": len(with_reason), "refused_matched": refused_records,
                  "refused_without_reason": len(refusals) - len(with_reason),
                  "refusals_reported": res.declared.get(path), "top_refusal_reason": top[0][1] if top else None}
        dup_note = f"; {qty(dup_surplus, 'duplicate copy', 'duplicate copies')} of expected records returned, counted in extra (D-281, D-311)" if dup_surplus else ""
        if outside_copies:   # and of a partly frozen file's records outside the compared subset (D-349)
            dup_note = (f"; {qty(dup_surplus + outside_copies, 'duplicate copy', 'duplicate copies')} returned, {outside_copies} of "
                        f"the file's records outside the compared subset, counted in extra (D-281, D-311, D-349)")
        if repeated:   # said, never graded: the input itself holds these ids more than once, with records that differ (D-343)
            dup_note += (f"; the input holds {qty(len(repeated), 'id')} more than once with records that differ (e.g. id {repeated[0][0]}, "
                         f"{qty(repeated[0][1], 'record')}): each copy returned is compared with the input's record it matches (D-343)")
        if fails:
            res.add(check, "fail", path, f"{graded_records} compared vs {label}; " + "; ".join(fails[:12]) + (" ..." if len(fails) > 12 else "") + dup_note, counts=counts)
        else:
            res.add(check, "pass", path, f"{qty(graded_records, 'record')} {pick(graded_records, 'matches', 'match')} {label}" + dup_note, tolerance=tol, counts=counts)
        # D-284: a field with expected values that this parser never returned in this file was not compared above;
        # that is a visible gap in the case result, never a clean pass
        if parsed and oracle:
            # every record of an id the input holds more than once, not only the first (the reading of D-343)
            valued = {f for want in oracle.values() for rec in (want.get("_copies") or [want]) for f in rec if rec.get(f) is not None}
            never = sorted(f for f in valued if f in OPTIONAL_FIELDS and f not in set(exempt) and f not in returned_fields)
            if never:
                res.add("fields-not-returned", "not-exercised", path,
                        f"{qty(len(never), 'field')} with expected values never returned by this parser in this file, "
                        "and not compared: " + ", ".join(never) + " (D-284)", cause="parser")
        return not fails

    def oracle_for(self, case_exp, path, fmt, mode, refrecs):
        """-> (oracle, label, held). Frozen values in snapshot mode; otherwise the reference reader on the user's bytes."""
        base = os.path.basename(path)
        if mode == "snapshot":
            recs = [r for r in case_exp["records"] if base in r.get("present_in", {}) or r.get("derived_file") == base]
            if recs:
                return _oracle_by_id((r["norad_cat_id"], oracle_from_expected(r, fmt)) for r in recs), "frozen expected values", _held(r["norad_cat_id"] for r in recs)
        label = ("reference-reader values (snapshot values withheld from the public release; not the human-verified snapshot)"
                 if mode == "snapshot" and case_exp.get("records_withheld") else
                 "reference-reader values (live bytes; not the human-verified snapshot)")
        out = []
        for r in refrecs or []:
            vals = strip_ref(r)
            for k in DEC_FIELDS:
                if vals.get(k) is not None:
                    vals[k] = Decimal(str(vals[k]))
            if vals.get("epoch") is not None:
                # the file's epoch in the form the comparison reads (D-336): a CCSDS day-of-year epoch, a trailing Z or
                # a seventh fraction digit failed every parser on live bytes, the reference adapter included; the
                # strict reader has already refused any epoch iso_epoch cannot read
                raw_epoch = vals["epoch"]
                vals["epoch"] = tlemod.iso_epoch(raw_epoch)
                if re.search(r"T[0-9]{2}:[0-9]{2}:60", raw_epoch):
                    # a leap second, which a datetime cannot hold: the instant a second earlier or the next one, as the
                    # epoch vectors accept (vectors/ccsds-epoch-strings.json)
                    try:
                        # from the numbers, not strptime: iso_epoch wrote through strftime("%Y"), which pads no year below
                        # 1000 on some platforms, and strptime then raised ValueError here (it writes through epoch_text
                        # now, D-355); written as iso_epoch writes, to compare alike
                        y, mo, d, h, mi, s, us = (int(x) for x in re.split(r"[-T:.]", vals["epoch"]))
                        also = dt.datetime(y, mo, d, h, mi, s, us) + dt.timedelta(seconds=1)
                        vals["_epoch_also"] = tlemod.epoch_text(also)
                    except OverflowError:   # the last second of 9999: no next instant a datetime can hold
                        pass
            out.append((r["norad_cat_id"], vals))
        return _oracle_by_id(out), label, _held(r["norad_cat_id"] for r in refrecs or [])

    # ---- the three field-form checks the case documents list (D-118): targeted comparisons against the same oracle as `values`
    def check_field_forms(self, res, path, fmt, parsed, oracle, active):
        if not oracle or not parsed:
            return

        def compare(fields, ids=None):
            n, bad, tol = 0, [], 0
            for p in parsed:
                cat = p.get("norad_cat_id")
                if cat not in oracle or (ids is not None and cat not in ids):
                    continue
                for f in fields:
                    # an id the input holds more than once: the record the values item paired this copy with, or, where
                    # no values item paired it, any of its records (D-343)
                    wants = [w for w in (rec.get(f) for rec in ([p["_record"]] if "_record" in p else
                                                                 oracle[cat].get("_copies") or [oracle[cat]])) if w is not None]
                    if not wants:
                        continue
                    want = wants[0]
                    n += 1
                    outcomes = [compare_value(f, p.get(f), w, note=(p.get("_notes") or {}).get(f))[0] for w in wants]
                    r = next((o for o in outcomes if o != "mismatch"), "mismatch")
                    if r == "mismatch":
                        bad.append(f"id {cat} {f}: got {p.get(f)!r}, want {want!r}")
                    elif r == "tolerance":
                        tol += 1
            return n, bad, tol

        def report(check, n, bad, tol, ok_text):
            res.add(check, "fail" if bad else "pass", path, "; ".join(bad[:6]) + (f" … ({len(bad)} mismatches)" if len(bad) > 6 else "") if bad
                    else ok_text + (f"; {tol} within tolerance" if tol else ""))

        if "leading-dot-decimals" in active and fmt in ("csv", "kvn", "xml"):
            kws = leading_dot_keywords(open(self.path(path), "rb").read().decode("utf-8", "replace"), fmt)
            fields = sorted({ref.DECIMAL_KEYS[k] for k in kws if k in ref.DECIMAL_KEYS})  # only decimal keywords can start with '.'
            if fields:
                n, bad, tol = compare(fields)
                report("leading-dot-decimals", n, bad, tol, f"{qty(n, 'value')} written without a leading zero ({', '.join(sorted(kws))}) parsed to the expected {pick(n, 'value', 'values')}")
        if "bstar-implied-decimal-exponent" in active and fmt in ("tle", "2le"):
            n, bad, tol = compare(["bstar", "mean_motion_ddot"])
            if n:
                report("bstar-implied-decimal-exponent", n, bad, tol, f"{qty(n, 'BSTAR and second-derivative field')} with an implied decimal point and exponent decoded to the expected {pick(n, 'value', 'values')}")
        if "negative-bstar-and-ndot" in active:
            ids = {cat for cat, o in oracle.items() if any(rec.get(f) is not None and Decimal(str(rec[f])) < 0
                                                           for rec in (o.get("_copies") or [o]) for f in ("bstar", "mean_motion_dot"))}
            if ids:
                n, bad, tol = compare(["bstar", "mean_motion_dot"], ids)
                report("negative-bstar-and-ndot", n, bad, tol, f"{qty(len(ids), 'record')} with a negative BSTAR or first derivative: sign and value preserved")

    # ---- structural checks
    def check_ints(self, res, path, parsed, active):
        if "catalog-number-is-integer" not in active and "nine-digit-ids-parse" not in active:
            return
        bad = [p for p in parsed if p.get("_notes", {}).get("norad_cat_id") not in ("int",) or p.get("norad_cat_id") is None]
        examples = [p["_bad"]["norad_cat_id"] for p in bad if p.get("_bad", {}).get("norad_cat_id")][:3]
        if "catalog-number-is-integer" in active:
            res.add("catalog-number-is-integer", "fail" if bad else "pass", path,
                    (f"{qty(len(bad), 'record')} whose norad_cat_id is not an int" + (", e.g. " + ", ".join(examples) if examples else "")) if bad else f"{qty(len(parsed), 'record')} with integer norad_cat_id")
        if "nine-digit-ids-parse" in active:
            nine = [p for p in parsed if (p.get("norad_cat_id") or 0) >= 100_000_000]
            if nine:
                res.add("nine-digit-ids-parse", "pass", path, f"{qty(len(nine), 'nine-digit id')} returned as {pick(len(nine), 'an integer', 'integers')}")

    def check_tle_lines(self, res, path, parsed, refrecs, active):
        if "tle-checksums-valid" in active:
            bad = [r["norad_cat_id"] for r in refrecs if not r["tle"]["checksums_valid"] or r["tle"]["line_lengths"][1:] != [69, 69]]
            # a check on the file's own lines, read by the corpus's reader: no parser takes part, so it is never a
            # parser pass (D-129's rule for the SATCAT check, applied here by D-297; the red team's finding)
            res.add("tle-checksums-valid", "fail" if bad else "info", path, f"invalid lines for ids {bad[:5]}; a property of the file, not a result of the parser under test" if bad
                    else f"{qty(len(refrecs), 'record')}, all checksums valid (data check; the parser under test is not involved)")
        if "tle-catalog-field-decodes" in active or "alpha5-decode" in active:
            want = {r["norad_cat_id"] for r in refrecs}
            got = {p.get("norad_cat_id") for p in parsed}
            # a record the parser refused with a reason was not decoded wrongly: the values item fails it as not
            # returned, and this item says so instead of calling it a wrong decode (D-298)
            refused = {r["id"] for r in res.refusals.get(path, []) if r["ok"] and r["id"] in want} - got
            miss = sorted(want - got - refused)
            a5 = " (Alpha-5)" if any(r["tle"]["catalog_field_is_alpha5"] for r in refrecs) else ""
            note = f"; {qty(len(refused), 'record')} refused with a reason, not graded here (the values item counts {pick(len(refused), 'it', 'them')})" if refused else ""
            if miss:
                res.add("tle-catalog-field-decodes", "fail", path, f"{qty(len(miss), 'catalog field')} not decoded to the right integer, e.g. {miss[:3]}" + note)
            elif refused and len(refused) == len(want):
                res.add("tle-catalog-field-decodes", "not-exercised", path, f"every record refused with a reason: no catalog field was decoded" + a5, cause="parser")
            else:
                res.add("tle-catalog-field-decodes", "pass", path, f"{qty(len(want) - len(refused), 'catalog field')} decoded correctly" + a5 + note)
        if "two-digit-year-pivot" in active:
            # each record of an id the input holds more than once (Space-Track's GP_History answers so) is matched with a
            # returned copy of its own, an exact epoch first, among the untaken copies next to it in epoch order (a
            # bisection, so a history of thousands of sets is read at once); such an id kept its last copy, and its other
            # records failed. An id held once reads its last copy, as before (D-344)
            copies: dict = {}
            for p in parsed:
                copies.setdefault(p.get("norad_cat_id"), []).append(p.get("epoch"))
            inheld = _held(r["norad_cat_id"] for r in refrecs)
            pools = {cat: sorted(str(e) for e in es if e is not None) for cat, es in copies.items()}
            bad, tol = [], TolStats()
            for r in refrecs:
                cat = r["norad_cat_id"]
                if inheld.get(cat, 1) == 1:
                    result, diff = compare_value("epoch", (copies.get(cat) or [None])[-1], r["epoch"])   # as before
                else:
                    pool, result, diff, take = pools.get(cat) or [], "mismatch", None, None
                    i = bisect.bisect_left(pool, str(r["epoch"]))
                    for j in (i, i - 1, i + 1):
                        if 0 <= j < len(pool):
                            o, d = compare_value("epoch", pool[j], r["epoch"])
                            if o == "exact" or (o == "tolerance" and result == "mismatch"):
                                result, diff, take = o, d, j
                    if take is not None:
                        pool.pop(take)
                if result == "mismatch":
                    bad.append(r["norad_cat_id"])
                elif result == "tolerance":
                    tol.add("epoch", diff)
            yrs = sorted({r["tle"]["two_digit_year"] for r in refrecs})
            res.add("two-digit-year-pivot", "fail" if bad else "pass", path, f"epoch mismatch for ids {bad[:3]}" if bad else f"epochs match for two-digit years {yrs}", tolerance=tol)

    def check_presence(self, res, path, parsed, refrecs, active):
        many: dict = {}
        for p in parsed:
            many.setdefault(p.get("norad_cat_id"), []).append(p)
        inheld = _held(r["norad_cat_id"] for r in refrecs)

        def copies_of(cat):
            """The copies a presence check reads for an id: the last, as before, where the input holds the id once, and for
            the records without one; every copy where it holds it more than once, so a copy of its id answers for each
            record (D-344)."""
            cs = many.get(cat) or [{}]
            return cs[-1:] if cat is None or inheld.get(cat, 1) == 1 else cs

        def bad_ids(rs, wrong):
            """The ids of the records rs for which no copy read is right (wrong(copy) false), judged once an id, so a
            history of thousands of records is read in one pass."""
            seen: dict = {}
            for r in rs:
                if r["norad_cat_id"] not in seen:
                    seen[r["norad_cat_id"]] = all(wrong(c) for c in copies_of(r["norad_cat_id"]))
            return [r["norad_cat_id"] for r in rs if seen[r["norad_cat_id"]]]
        if "object-id-may-be-empty" in active:
            empty = [r for r in refrecs if r["presence"].get("OBJECT_ID") in ("empty", "null")]
            if empty:
                bad = bad_ids(empty, lambda c: c.get("object_id") not in (None,))
                res.add("object-id-may-be-empty", "fail" if bad else "pass", path,
                        f"parser invented or kept a value for empty OBJECT_ID on ids {bad[:3]}" if bad else f"{qty(len(empty), 'empty OBJECT_ID record')} handled")
        if "object-name-unknown-literal" in active:
            unk = [r for r in refrecs if r.get("object_name") == "UNKNOWN"]
            if unk:
                # held as the values item holds the name, so a TLE name line padded to 24 columns is UNKNOWN too (D-369)
                bad = bad_ids(unk, lambda c: compare_value("object_name", c.get("object_name"), "UNKNOWN")[0] == "mismatch")
                res.add("object-name-unknown-literal", "fail" if bad else "pass", path, f"UNKNOWN not preserved for {bad[:3]}" if bad else f"{qty(len(unk), 'UNKNOWN name')} preserved")
        if "classification-c" in active:
            cc = [r for r in refrecs if r.get("classification_type") == "C"]
            if cc:
                bad = bad_ids(cc, lambda c: "classification_type" in c and c["classification_type"] != "C")
                res.add("classification-c", "fail" if bad else "pass", path, f"C not preserved for {bad[:3]}" if bad else f"{qty(len(cc), 'record')} with classification C accepted")
        if "element-set-zero-and-rev-one" in active:
            z = [r for r in refrecs if r.get("element_set_no") == 0 or r.get("rev_at_epoch") in (0, 1)]
            if z:
                # a copy is right for a record when each of the two numbers it gives is the record's: the pairs the
                # copies of each id give, a number not given read as either, looked up once a record
                given: dict = {}
                for r in z:
                    if r["norad_cat_id"] not in given:
                        given[r["norad_cat_id"]] = {(c.get("element_set_no", _ABSENT), c.get("rev_at_epoch", _ABSENT))
                                                    for c in copies_of(r["norad_cat_id"])}
                bad = [r["norad_cat_id"] for r in z
                       if not given[r["norad_cat_id"]] & {(e, v) for e in (r["element_set_no"], _ABSENT) for v in (r["rev_at_epoch"], _ABSENT)}]
                res.add("element-set-zero-and-rev-one", "fail" if bad else "pass", path, f"mismatch for {bad[:3]}" if bad else f"{qty(len(z), 'record')} with element set 0 / rev 0-1 preserved")

    def check_empty_answer(self, res, path, fmt, raw, body, status):
        """The provider's empty answer is presented to the parser under test (D-143): an empty but valid result must
        come back as zero records and no error, or 'nothing to load' is indistinguishable from 'unreadable'."""
        what = f"the provider's empty answer (HTTP {status or 404}, body {body!r}, {qty(len(raw), 'byte')})"
        try:
            got = (getattr(self.parser, "parse", None) or self.parser)(raw, fmt)   # a callable adapter too, as Runner.parse
        except Unsupported:
            res.add("empty-answer-yields-no-records", "skip", path, f"parser reports {fmt} unsupported")
            res.fmt_dodged.append((fmt, len(res.items) - 1, path))
            return
        except Exception as e:
            res.add("empty-answer-yields-no-records", "fail", path,
                    (f"the parser's command {e}" if type(e) is CommandCrashed else f"parser raised {type(e).__name__}: {str(e)[:160]}")
                    + f" on {what}; an empty but valid answer must yield no records, not an error")
            return
        res.fmt_read.setdefault(fmt, []).append(path)
        try:
            got = as_records(got)   # D-330: an answer that is not a list of records is worded as such, a tuple accepted
        except NotRecords as e:
            res.add("empty-answer-yields-no-records", "fail", path, f"{unreadable_words(e)}, from {what}; an empty answer must yield no records")
            return
        records, refusals, _ = split_refusals(got)
        if refusals:
            reason = next((r["reason"] for r in refusals if r["ok"]), "no reason given")
            res.add("empty-answer-yields-no-records", "fail", path,
                    f"parser refused {what} ({reason[:120]}) instead of yielding zero records; an empty answer is not an unreadable one")
            return
        n = len(records)   # as_records has made it a list (D-334)
        if n == 0:
            res.add("empty-answer-yields-no-records", "pass", path, f"{what} read as zero records, no error")
        else:
            res.add("empty-answer-yields-no-records", "fail", path,
                    f"parser returned {qty(n, 'record')} from {what}; an empty answer must yield none")

    def check_format_facts(self, res, path, fmt, parsed, reffacts, active):
        if fmt in ("csv", "json") and "csv-json-omit-constant-metadata" in active:
            absent = reffacts.get("omm_mandatory_metadata_absent", [])
            bad = []
            for p in parsed:
                for k, default in (("center_name", "EARTH"), ("ref_frame", "TEME"), ("time_system", "UTC"), ("mean_element_theory", None)):
                    v = p.get(k)
                    if v not in (None, default) and not (k == "mean_element_theory" and v in ("SGP4", "SGP/SGP4")):
                        bad.append((p.get("norad_cat_id"), k, v))
            res.add("csv-json-omit-constant-metadata", "fail" if bad else "pass", path,
                    f"non-default metadata invented: {bad[:3]}" if bad else f"parsed with {absent} absent; defaults or None returned")
        if fmt in ("csv", "json") and "supgp-extra-keys-tolerated" in active:
            extra = reffacts.get("non_omm_columns") or reffacts.get("non_omm_keys") or []
            if extra:
                res.add("supgp-extra-keys-tolerated", "pass", path, f"parsed with extra keys {extra}")
        if fmt == "xml" and "xml-ndm-wrapper-omm-2.0" in active:
            n = reffacts.get("omm_count")
            res.add("xml-ndm-wrapper-omm-2.0", "pass" if len(parsed) == n else "fail", path,
                    f"{qty(len(parsed), 'record')} from <{reffacts.get('root_element')}> with {n} <omm> (version {reffacts.get('version_attributes')})")
        if fmt == "kvn" and "kvn-blank-mandatory-values" in active:
            res.add("kvn-blank-mandatory-values", "pass", path, f"{qty(len(parsed), 'message')} parsed despite blank CREATION_DATE/ORIGINATOR")

    def check_set_relations(self, res, case_exp, set_name, files, active):
        """files: {path: (state, fmt, parsed, refrecs)}"""
        omm = {p: v for p, v in files.items() if v[1] in ("csv", "json", "xml", "kvn") and v[0] == "ok"}
        tles = {p: v for p, v in files.items() if v[1] in ("tle", "2le")}
        if "omm-formats-agree" in active and len(omm) >= 2:
            ids = set()
            for v in omm.values():
                ids |= {p.get("norad_cat_id") for p in v[2]}
            bad = []
            names = [os.path.basename(path) for path in omm]
            helds = [_held(r["norad_cat_id"] for r in (v[3] or [])) for v in omm.values()]
            copies: list = [{} for _ in omm]
            for fi, v in enumerate(omm.values()):
                for q in v[2]:
                    copies[fi].setdefault(q.get("norad_cat_id"), []).append(q)

            def add(vals, rec, name):
                for f in CORE_FIELDS:
                    if f in rec:
                        vals.setdefault(f, {}).setdefault(str(rec[f]), []).append(name)
            records = 1 if None in ids else 0
            for cat in sorted(i for i in ids if i is not None):
                times = max(h.get(cat, 1) for h in helds)
                records += times
                if times == 1:   # held once by the input: the first copy in each file, as before
                    vals: dict = {}
                    for fi, name in enumerate(names):
                        if not copies[fi].get(cat):
                            bad.append(f"id {cat} missing from {name}")
                            continue
                        add(vals, copies[fi][cat][0], name)
                    for f, d in vals.items():
                        if len(d) > 1:
                            bad.append(f"id {cat} {f}: {d}")
                    continue
                # an id the input holds more than once: each file's copies paired with the first file's by element set
                # number and revolution, or the nearest in epoch, every copy in a pair; the first copy of each file
                # alone was compared, so copies returned in another order failed (D-344)
                anchor = next(fi for fi in range(len(names)) if copies[fi].get(cat))
                firsts = copies[anchor][cat]
                place = {id(q): i for i, q in enumerate(firsts)}
                groups: list = [{} for _ in firsts]
                for i, q in enumerate(firsts):
                    add(groups[i], q, names[anchor])
                for fi, name in enumerate(names):
                    if fi == anchor:
                        continue
                    if not copies[fi].get(cat):
                        bad.append(f"id {cat} missing from {name}")
                        continue
                    for a, b in _pair_copies(firsts, copies[fi][cat]):
                        add(groups[place[id(a)]], b, name)
                for i, vals in enumerate(groups):
                    for f, d in vals.items():
                        if len(d) > 1:
                            bad.append(f"id {cat} {f} (copy {i + 1} of {len(firsts)} in {names[anchor]}): {d}")
            res.add("omm-formats-agree", "fail" if bad else "pass", set_name, "; ".join(bad[:6]) if bad else f"{len(omm)} OMM renderings agree on {qty(records, 'record')}")
        if tles and omm:
            opath, (_, ofmt, oparsed, orefs) = next(iter(omm.items()))
            oby = {p.get("norad_cat_id"): p for p in oparsed}
            # every TLE member of the set (its .tle and its .2le) is compared with the first OMM file of the set the parser
            # read, each in items of its own; only the first was, so a set's .2le was never compared, not even where its
            # .tle was missing (D-318's stated limit; 2d, D-345). A recapture other than the set's first TLE file (no set
            # lists one first, a test holds) is not a member: another fetch of the TLE answer, made later, it holds the
            # provider's records of that later time, which the OMM set need not
            srcs = case_exp.get("sources", {})
            members = [(k, tpath, v) for k, (tpath, v) in enumerate(tles.items()) if k == 0 or not srcs.get(tpath, {}).get("recapture_of")]
            for k, tpath, (tstate, tfmt, tparsed, trefs) in members:
                tby = {p.get("norad_cat_id"): p for p in (tparsed or [])}
                label = set_name if k == 0 else f"{set_name}: {os.path.basename(tpath)}"   # the first member's items as before
                if "tle-format-omits-ids-above-99999" in active or "tle-count-equals-omm-count-below-100000" in active:
                    below = {i for i in oby if i is not None and i < 100000}
                    status = None
                    if tstate == "empty-404":
                        ok = not below
                        body = res.empty_answers.get(tpath, "No GP data found")  # the text the file holds: GP or SupGP
                        rec = res.recorded.get(tpath)
                        if rec is None:
                            detail = f"TLE request returned {body!r}; OMM set has {qty(len(below), 'id')} below 100000 (expected 0)"
                        elif ok:
                            # The answer is the corpus's record, written by the fetch, which did not request it (D-247).
                            detail = (f"the corpus's record of the TLE answer is {body!r} (HTTP {rec['http_status']}, captured {rec['captured_at']}; "
                                      f"not requested by this fetch); OMM set has {qty(len(below), 'id')} below 100000 (expected 0)")
                        else:
                            # A record cannot be wrong about today: where the fetched OMM set now holds ids the TLE format can
                            # carry, CelesTrak's answer today is not the recorded one, and the comparison is not made.
                            status = "not-exercised"
                            detail = (f"the corpus's record of the TLE answer is {body!r} (captured {rec['captured_at']}), from when this set held no id "
                                      f"below 100000; the OMM set fetched now holds {len(below)}, so CelesTrak's TLE answer today is not the recorded one, "
                                      f"and this fetch did not request it: not compared")
                    elif tstate == "missing":
                        # D-318: the TLE file of this set is not on disk (not fetched, or a capture no fetch brings). The
                        # comparison used to run on nothing and FAIL -- "TLE has 0 records" -- for any parser at all, the
                        # reference adapter included: a data folder a fetch left half done blamed a correct library. The
                        # file's own item already says it is missing; the comparison is not made.
                        ok, status = None, "not-exercised"
                        detail = (f"the TLE file of this set ({os.path.basename(tpath)}) is not on disk, so its records are not compared with the OMM set's "
                                  f"{qty(len(below), 'id')} below 100000")
                    elif tstate == "unsupported":
                        # D-318, the same fault from the other side: a parser with no TLE reader has nothing to count, and
                        # the file's own item already skips. All-or-none holds as for any format (D-280).
                        ok, status = None, "skip"
                        detail = f"parser reports {'TLE' if k == 0 else tfmt} unsupported, so its records are not compared with the OMM set's"
                    else:
                        ok = set(tby) == below
                        detail = f"TLE has {qty(len(tby), 'record')}, OMM has {qty(len(below), 'id')} below 100000 and {len(oby) - len(below)} at or above"
                    for c in ("tle-format-omits-ids-above-99999", "tle-count-equals-omm-count-below-100000"):
                        if c in active:
                            res.add(c, status or ("pass" if ok else "fail"), label, detail, cause="data" if status == "not-exercised" else None)
                if tstate == "ok" and ("tle-values-match-omm-within-tle-precision" in active or "mmdot-is-tle-field-value" in active):
                    bad, bad_dot, n = [], [], 0
                    tol, tol_dot, quant = TolStats(), TolStats(), TolStats()  # quant: the provider's own TLE epoch quantisation, not a parser tolerance
                    tall: dict = {}
                    oall: dict = {}
                    for q in tparsed or []:
                        tall.setdefault(q.get("norad_cat_id"), []).append(q)
                    for q in oparsed:
                        oall.setdefault(q.get("norad_cat_id"), []).append(q)
                    pairs = []
                    theld = _held(r["norad_cat_id"] for r in trefs or [])
                    oheld = _held(r["norad_cat_id"] for r in orefs or [])
                    # the input's own record of each id it holds once, as the reference reader reads it: where the parser
                    # leaves an OMM value empty, that record says whether the input gives one (D-351)
                    oonce = {r["norad_cat_id"]: r for r in orefs or [] if oheld.get(r["norad_cat_id"]) == 1}
                    tonce = {r["norad_cat_id"]: r for r in trefs or [] if theld.get(r["norad_cat_id"]) == 1}
                    # and of each id it holds more than once, by epoch (D-352)
                    oempty, tvalues = _EmptyCopies(orefs or []), _TleValuesByEpoch(trefs or [])
                    for cat, ts in tall.items():
                        os_ = list(oall.get(cat, []))
                        if not os_:
                            continue
                        if cat is None or (theld.get(cat, 1) == 1 and oheld.get(cat, 1) == 1):   # held once by the input: as before
                            pairs.append((cat, ts[-1], os_[-1]))
                            continue
                        # an id the input holds more than once: every TLE copy with the OMM copy of its element set number
                        # and revolution, or the nearest in epoch, and every OMM copy left with the nearest TLE copy; only the
                        # last of each was compared, so copies returned in another order failed (D-344)
                        pairs.extend((cat, t, o) for t, o in _pair_copies(ts, os_))
                    for cat, t, o in pairs:
                        n += 1
                        tn, on = t.get("_notes", {}), o.get("_notes", {})
                        def note(f):
                            return "float" if (tn.get(f) == "float" or on.get(f) == "float") else None
                        def judge(f, a, b, sink, sink_tol, text):
                            result, diff = compare_value(f, a, b, note(f))
                            if result == "mismatch":
                                sink.append(text)
                            elif result == "tolerance":
                                sink_tol.add(f, diff)
                        for f in ("mean_motion", "inclination", "ra_of_asc_node", "arg_of_pericenter", "mean_anomaly", "mean_motion_dot"):
                            sink = bad_dot if f == "mean_motion_dot" else bad
                            if t.get(f) is None or o.get(f) is None:
                                # every TLE carries these fields, so a value left out or None on either side is no value of the
                                # input's: a key left out was not compared, and None on both sides read as equal (D-358, the
                                # pairs-case escapes entry; the D-284 rule for core fields)
                                sink.append(f"id {cat} {f}: tle {_shown(t, f, str)} omm {_shown(o, f, str)}, where every TLE carries a value (D-358)")
                                continue
                            judge(f, t[f], o[f], sink, tol_dot if f == "mean_motion_dot" else tol, f"id {cat} {f}: tle {t[f]} omm {o[f]}")
                        # the OMM value as its TLE field would hold it. A value the parser returns empty (None), for an id the
                        # input holds once, is judged by the input's record of it: where that record gives a value the item
                        # fails, as the pairs cases have no values item to fail it; where it is empty too, the TLE value is
                        # compared with the input's TLE record. For an id the input holds more than once, the parser's copy
                        # must take an input copy that leaves it empty at its epoch (_EmptyCopies), and the TLE value is
                        # compared with the values the input's TLE copies give at the parser's TLE copy's epoch, which the
                        # epoch check below holds to the OMM copy's, or at the OMM copy's where the TLE copy has none
                        # (D-352); within the 432 us allowance of a parser copy's epoch, which input copy an empty answer
                        # belongs to is not judged, and the TLE values at one epoch are compared as a set (the values check is
                        # D-359's, split off D-358). One no TLE field holds as providers write it fails the item naming
                        # it. Each ended the case as "internal error in runner" (D-351). A key the parser leaves out is read
                        # as None (D-358)
                        for f, how in (("eccentricity", "truncated"), ("bstar", "5-digit-rounded"), ("mean_motion_ddot", "5-digit-rounded")):
                            # a key the parser leaves out is read as None, on either side, as the values cases read it: it was
                            # not compared (D-358). DDOT is the second-derivative field, which the mmdot item holds to the
                            # TLE field too, as its case says ("MEAN_MOTION_DDOT likewise equals the TLE second-derivative
                            # field"): its mismatches went to the consistency item alone, which that case does not run (D-358)
                            fbad, ftol = (_Sinks(bad, bad_dot), _Sinks(tol, tol_dot)) if f == "mean_motion_ddot" else (bad, tol)
                            tv, ov = t.get(f), o.get(f)
                            if _empty(ov):
                                if cat not in oheld:
                                    fbad.append(f"id {cat} {f}: omm {_shown(o, f)}, for an id the input's OMM file does not hold (D-351)")
                                elif oheld[cat] > 1 or theld.get(cat, 0) > 1:
                                    if _epoch_of(o) is None:
                                        fbad.append(f"id {cat} {f}: omm {_shown(o, f)} in a copy with no epoch, which can take no input copy "
                                                   f"that leaves it empty (D-352)")
                                    elif not oempty.take(cat, f, o):
                                        fbad.append(f"id {cat} {f}: omm {_shown(o, f)} at {o.get('epoch')}, but no copy of the id that leaves it "
                                                   f"empty is left within {TLE_EPOCH_TOLERANCE_US} us of that epoch (D-352)")
                                    else:
                                        # at the TLE copy's epoch, or the OMM copy's where the TLE copy has none (the
                                        # OMM copy's is the one it took an empty copy at)
                                        theirs, nums = tvalues.values_near(cat, _epoch_of(t) or _epoch_of(o), f)
                                        if theirs:
                                            v = closest(theirs, nums, tv)
                                            judge(f, tv, v, fbad, ftol, f"id {cat} {f}: tle {_shown(t, f, str)} vs the TLE file's {v} at that epoch (the OMM record leaves it empty)")
                                elif not _empty(oonce[cat].get(f)):
                                    fbad.append(f"id {cat} {f}: omm {_shown(o, f)}, where the input gives a value (D-351)")
                                elif cat in tonce and f in tonce[cat]:
                                    judge(f, tv, tonce[cat][f], fbad, ftol, f"id {cat} {f}: tle {_shown(t, f, str)} vs the TLE file's {tonce[cat][f]} (the OMM record leaves it empty)")
                                continue
                            want = tle_side(f, ov)
                            if want is None:
                                fbad.append(f"id {cat} {f}: omm {ov} is a value no TLE field holds as providers write it (D-351)")
                            else:
                                judge(f, tv, want, fbad, ftol, f"id {cat} {f}: tle {_shown(t, f, str)} vs {how} omm {want}")
                        if not (t.get("epoch") and o.get("epoch")):
                            bad.append(f"id {cat} epoch: tle {_shown(t, 'epoch', str)} omm {_shown(o, 'epoch', str)}, where every TLE carries one (D-358)")
                        else:
                            result, diff = compare_value("epoch", t["epoch"], o["epoch"], epoch_tolerance_us=TLE_EPOCH_TOLERANCE_US)
                            if result == "mismatch":
                                bad.append(f"id {cat} epoch: tle {t['epoch']} omm {o['epoch']}")
                            elif result == "tolerance":
                                quant.add("epoch", diff)
                    shared = ({r["norad_cat_id"] for r in trefs or []} & {r["norad_cat_id"] for r in orefs or []}) - {None}
                    if not n and shared:
                        # no pair, where the input's two files share a catalog number: nothing was compared, and the item
                        # passed on nothing (a parser returning every TLE record without its number did; D-348)
                        none = (f"0 pairs: the two files share {qty(len(shared), 'catalog number')}, and no record the parser returned "
                                "from one has a catalog number it returned from the other (D-348)")
                        bad.append(none)
                        bad_dot.append(none)
                    if "tle-values-match-omm-within-tle-precision" in active:
                        detail = "; ".join(bad[:6]) if bad else f"{qty(n, 'TLE/OMM pair')} consistent under the precision rules"
                        if quant and not bad:
                            detail += "; provider TLE epoch quantisation observed (data property, not a parser tolerance): " + quant.text().replace("within tolerance: ", "")
                        res.add("tle-values-match-omm-within-tle-precision", "fail" if bad else "pass", label, detail, tolerance=tol)
                    if "mmdot-is-tle-field-value" in active:
                        res.add("mmdot-is-tle-field-value", "fail" if bad_dot else "pass", label,
                                "; ".join(bad_dot[:6]) if bad_dot else f"{qty(n, 'pair')}: OMM MEAN_MOTION_DOT equals the TLE field as printed, and MEAN_MOTION_DDOT the TLE field's five rounded digits", tolerance=tol_dot)

    # ---- per-kind drivers
    def run_gp_like(self, case, exp, res):
        active = set(case["checks"])
        # group sources into sets
        sets = {}
        for name, s in exp.get("sets", {}).items():
            for b in s["files"]:
                sets.setdefault(name, []).append(b)
        derived_files = [os.path.basename(p) for p in exp["sources"] if exp["kind"] in ("derived-tle", "derived-kvn")]
        if derived_files:
            sets["derived"] = derived_files
        assigned = {b for fs in sets.values() for b in fs}
        for p in exp["sources"]:
            if os.path.basename(p) not in assigned:
                sets.setdefault("_ungrouped", []).append(os.path.basename(p))
        bypath = {os.path.basename(p): p for p in exp["sources"]}
        read_any = False  # a case none of whose files is on disk reports not-fetched, never "not exercised" (D-119, D-148)
        for set_name, basenames in sets.items():
            files = {}
            for b in basenames:
                path = bypath.get(b)
                if not path:
                    continue
                src = exp["sources"][path]
                state, fmt, mode, parsed, refrecs, reffacts = self.load_source(res, case, path, src)
                read_any = read_any or state == "ok"
                files[path] = (state, fmt, parsed, refrecs)
                if state != "ok":
                    if state == "empty-404":
                        rec = res.recorded.get(path)
                        res.add("sha256-matches-tested-snapshot", "info", path, f"{mode}: empty response body preserved" if rec is None else
                                f"{mode}: the corpus's record of the provider's empty answer (captured {rec['captured_at']}), written by the fetch and not requested")
                    continue
                res.add("sha256-matches-tested-snapshot", "info", path, "drift: stable-tier source differs from the tested snapshot" if path in res.drift else mode)
                exempt = set()
                if exp["kind"] == "derived-kvn":
                    rec = next((r for r in exp["records"] if r.get("derived_file") == b), None)
                    if rec:
                        exempt = {KEYWORD_TO_FIELD[k] for k in rec.get("keywords_absent", [])}
                oracle, label, held = self.oracle_for(exp, path, fmt, mode, refrecs)
                if path in res.drift:
                    label = "reference-reader values (frozen expected values not applied: the stable source drifted from the tested snapshot; not the human-verified snapshot)"
                partial = bool(exp.get("sets", {}).get(set_name, {}).get("record_filter")) and mode == "snapshot" and not exp.get("records_withheld")
                if oracle:
                    self.compare_values(res, path, fmt, mode, parsed, oracle, exempt=exempt, partial=partial, oracle_label=label, held=held,
                                        held_in_file=_held(r["norad_cat_id"] for r in refrecs or []) if partial else None)
                self.check_ints(res, path, parsed, active if not exempt else active - {"catalog-number-is-integer"})
                if fmt in ("tle", "2le"):
                    self.check_tle_lines(res, path, parsed, refrecs, active)
                self.check_presence(res, path, parsed, refrecs, active)
                self.check_format_facts(res, path, fmt, parsed, reffacts, active)
                self.check_field_forms(res, path, fmt, parsed, oracle, active)
                if exp["kind"] == "derived-kvn" and fmt == "kvn":   # the case's one XML file is not a KVN variant (D-299)
                    for c in ("kvn-syntax-tolerance", "optional-tle-parameters-may-be-absent", "omm-version-3-accepted"):
                        if c in active:
                            res.add(c, "pass", path, "variant parsed" + (f"; omitted keywords {sorted(exempt)}" if exempt and c == "optional-tle-parameters-may-be-absent" else ""))
            if any(v[0] in ("ok", "empty-404") for v in files.values()):
                self.check_set_relations(res, exp, set_name, files, active)
        if not read_any:
            return  # nothing was parsed: "not exercised" would claim the data lacked the feature, when there was no data
        if "nine-digit-ids-parse" in active and not any(i.check == "nine-digit-ids-parse" for i in res.items):
            res.add("nine-digit-ids-parse", "not-exercised", None, "no nine-digit ids in the fetched data (launch nominals exist only ~5-8 days after a launch)", cause="data")
        for c, what in (("leading-dot-decimals", "no value written without a leading zero in the fetched OMM files"),
                        ("bstar-implied-decimal-exponent", "no TLE file with an oracle in this run"),
                        ("negative-bstar-and-ndot", "no negative BSTAR or first derivative in the fetched data")):
            if c in active and not any(i.check == c for i in res.items):
                res.add(c, "not-exercised", None, what, cause="data")

    def run_pairs(self, case, exp, res):
        active = set(case["checks"])
        pairs = exp["case_specific"]["pairs"]
        stems = {}
        bypath = {os.path.basename(p): p for p in exp["sources"]}
        for it in pairs:
            if "tle_file" in it:
                stems.setdefault((it["tle_file"], it["omm_file"]), None)
        if not stems:  # fall back to pairing sources by stem
            for b in bypath:
                if b.endswith(".tle") and b[:-4] + ".csv" in bypath:
                    stems.setdefault((b, b[:-4] + ".csv"), None)
        surplus_read = set()   # a file in two pairs is read for its surplus once
        for tb, ob in stems:
            files = {}
            for b in (tb, ob):
                path = bypath[b]
                state, fmt, mode, parsed, refrecs, reffacts = self.load_source(res, case, path, exp["sources"][path])
                files[path] = (state, fmt, parsed, refrecs)
                if state == "ok" and path not in surplus_read:
                    surplus_read.add(path)
                    self.check_surplus(res, path, parsed, refrecs)
            if all(v[0] == "ok" for v in files.values()):
                self.check_set_relations(res, exp, f"{tb} vs {ob}", files, active)

    def run_facts(self, case, exp, res):
        active = set(case["checks"])
        for path, src in exp["sources"].items():
            state, fmt, mode, parsed, refrecs, reffacts = self.load_source(res, case, path, src)
            if state == "ok":
                self.check_surplus(res, path, parsed, refrecs)
                self.check_ints(res, path, parsed, active)   # listed since D-283, evaluated since D-301
                self.check_format_facts(res, path, fmt, parsed, reffacts, active)

    def run_xml(self, case, exp, res):
        active = set(case["checks"])
        for path, src in exp["sources"].items():
            state, fmt, mode, parsed, refrecs, reffacts = self.load_source(res, case, path, src)
            if state == "ok":
                self.check_surplus(res, path, parsed, refrecs)
                self.check_ints(res, path, parsed, active)   # listed since D-283, evaluated since D-301
                self.check_format_facts(res, path, fmt, parsed, reffacts, active | {"xml-ndm-wrapper-omm-2.0"})
                v = exp["case_specific"].get(path, {}).get("validation")
                if isinstance(v, dict):
                    res.add("schema-validation-recorded", "info", path, "; ".join(f"{k}: {'valid' if r['valid'] else 'invalid'}" for k, r in v.items()))

    def run_satcat(self, case, exp, res):
        for path, src in exp["sources"].items():
            full = self.path(path)
            if not os.path.exists(full):
                if path in self.opt_in and src.get("format") == "satcat-legacy-fixed-width" and not self.unexpected_response(path):
                    # The legacy file comes only on request (D-231), and the check that reads it involves no parser.
                    # Without the file the case says what it says with it, not-exercised, and names the flag that
                    # runs the check: "needs fetched data" would tell every user to fetch the file that was made
                    # optional so that they would not (D-232, reversing the status D-231 chose).
                    res.on_request[path] = self.opt_in[path]
                    res.add("satcat-legacy-below-70000", "not-exercised", path,
                            "the data check was not made: the fetch brings the legacy SATCAT file only on request, and the parser "
                            "under test is not involved in the check"
                            + (f"; to run it, fetch the file with {self.hint(self.opt_in[path])}" if self.fetch_hints
                               else f"; the fetch brings the file with {self.opt_in[path]}"), cause="data")
                    continue
                self.report_missing(res, path)
                continue
            meta = saved_meta(full)
            got = meta.get("http_status")
            if got not in (None, 200) and got != src.get("http_status", 200):
                # an error page an earlier fetch saved in the data's place, refused as load_source refuses it (D-228): it was
                # read as a SATCAT file (D-351)
                self.page_in_place(res, path, full, meta, src)
                continue
            mode = "snapshot" if sha256(full) == src.get("sha256") else "live"
            res.modes[path] = mode
            if src.get("format") == "satcat-legacy-fixed-width":
                ids = [int(l[13:18]) for l in open(full, encoding="utf-8", errors="replace").read().splitlines() if l[13:18].strip().isdigit()]
                if not ids:   # it ended the case as "internal error in runner: ValueError: max() ..." (D-351)
                    res.add("satcat-legacy-below-70000", "not-exercised", path, f"the file holds no SATCAT line ({qty(os.path.getsize(full), 'byte')}): "
                            "the data check was not made; the parser under test is not involved in it", cause="data")
                    continue
                above = sum(i >= 70000 for i in ids)
                what = f"{qty(len(ids), 'id')}, max {max(ids)}, {above} at or above 70000 (data check, {mode})"
                if above:  # the corpus's premise about the legacy file no longer holds: loud, and about the data
                    res.add("satcat-legacy-below-70000", "fail", path, what + "; a data property of the legacy file, not a result of the parser under test")
                else:  # no adapter reads SATCAT: the check involves no parser, so it must never count as a parser pass (D-129)
                    res.add("satcat-legacy-below-70000", "not-exercised", path, what + "; the parser under test was not involved: no adapter reads SATCAT, so this is not a parser result", cause="data")
            else:
                res.add("satcat-record", "info", path, f"{mode}; SATCAT records are not parsed by the GP parser under test")

    def run_vectors(self, case, exp, res):
        hooks = {h: _HookCalls(h, getattr(self.parser, h, None)) if getattr(self.parser, h, None) else None
                 for h in ("alpha5_decode", "alpha5_encode", "two_digit_year", "parse_epoch", "parse_catalog_id")}
        vec = exp["case_specific"]
        a5 = next((v for k, v in vec.items() if k.endswith("alpha5.json")), None)
        if a5:
            if hooks["alpha5_decode"]:
                bad = []
                for group in ("official_examples", "boundaries", "skip_boundaries", "below_100000"):
                    for v in a5[group]:
                        try:
                            got = hooks["alpha5_decode"](v["field"])
                        except Unsupported:
                            continue
                        except Exception as e:
                            if type(e) is CommandCrashed:   # a crash, worded apart from a value returned (D-341)
                                bad.append(f"{v['field']}: {raised(e)}")
                                continue
                            got = raised(e)
                        if got != v["norad_cat_id"]:
                            bad.append(f"{v['field']} -> {got} (expected {v['norad_cat_id']})")
                        elif not is_integral(got):   # 100000.0 == 100000, and is not a catalog number (D-296)
                            bad.append(f"{v['field']} -> {got!r} ({type(got).__name__}; expected int {v['norad_cat_id']})")
                for v in a5["decode_invalid"]:
                    try:
                        got = hooks["alpha5_decode"](v["field"])
                        bad.append(f"{v['field']!r} accepted as {got!r} (should be rejected: {v['reason']})")   # a blank field shows (D-360)
                    except Exception as e:
                        if crashed(e):   # a crash or a timeout rejects nothing (D-341)
                            bad.append(f"{v['field']!r}: {crashed(e)}")   # a blank field shows (D-360's second reading)
                _vector_item(res, "alpha5-decode", "vectors/alpha5.json", hooks["alpha5_decode"], bad, "all decode vectors and all invalid inputs handled")
            else:
                res.add("alpha5-decode", "skip", "vectors/alpha5.json", "parser exposes no alpha5_decode hook")
            if hooks["alpha5_encode"]:
                bad = []
                for group in ("official_examples", "boundaries", "skip_boundaries", "below_100000"):
                    for v in a5[group]:
                        try:
                            got = hooks["alpha5_encode"](v["norad_cat_id"])
                        except Unsupported:
                            continue
                        except Exception as e:
                            if type(e) is CommandCrashed:
                                bad.append(f"{v['norad_cat_id']}: {raised(e)}")
                                continue
                            got = raised(e)
                        if got != v["field"]:
                            bad.append(f"{v['norad_cat_id']} -> {got!r} (expected {v['field']!r})")
                for v in a5["encode_unrepresentable"]:
                    try:
                        got = hooks["alpha5_encode"](v["norad_cat_id"])
                        bad.append(f"{v['norad_cat_id']} encoded as {got!r} (should be rejected: {v['reason']})")
                    except Exception as e:
                        if crashed(e):
                            bad.append(f"{v['norad_cat_id']}: {crashed(e)}")
                _vector_item(res, "alpha5-encode", "vectors/alpha5.json", hooks["alpha5_encode"], bad, "all encode vectors and all unrepresentable inputs handled")
            else:
                res.add("alpha5-encode", "skip", "vectors/alpha5.json", "parser exposes no alpha5_encode hook")
        yy = next((v for k, v in vec.items() if k.endswith("two-digit-epoch-year.json")), None)
        if yy:
            if hooks["two_digit_year"]:
                bad = []
                for v in yy["vectors"]:
                    try:
                        got = hooks["two_digit_year"](v["yy"])
                    except Unsupported:
                        continue
                    except Exception as e:  # a raising hook fails this vector, not the case (D-118)
                        bad.append(f"{v['yy']} -> {raised(e, text=True)}")
                        continue
                    if got != v["year"]:
                        bad.append(f"{v['yy']} -> {got}")
                    elif not is_integral(got):
                        bad.append(f"{v['yy']} -> {got!r} ({type(got).__name__}; expected int {v['year']})")
                _vector_item(res, "two-digit-year-pivot", "vectors/two-digit-epoch-year.json", hooks["two_digit_year"], bad, f"{qty(len(yy['vectors']), 'pivot vector')} correct")
            else:
                res.add("two-digit-year-pivot", "skip", "vectors/two-digit-epoch-year.json", "parser exposes no two_digit_year hook")
        ep = next((v for k, v in vec.items() if k.endswith("ccsds-epoch-strings.json")), None)
        if ep and hooks["parse_epoch"]:
            bad = []
            for v in ep["valid"]:
                try:
                    got = hooks["parse_epoch"](v["text"])
                except Unsupported:
                    continue
                except Exception as e:
                    bad.append(f"valid {v['text']!r}: {raised(e)}" if type(e) is CommandCrashed else f"valid {v['text']!r} rejected ({type(e).__name__})")
                    continue
                if not isinstance(got, dt.datetime):
                    # D-306 (the red team's E6): the hook's contract is text -> datetime. Text handed back was parsed
                    # by the runner's own reader, so a hook that returned its input unparsed passed every vector.
                    bad.append(f"valid {v['text']!r} -> {got!r} ({type(got).__name__}): parse_epoch must return a datetime")
                    continue
                accepted = ([v["iso"]] + list(v.get("iso_alternatives", []))) if v.get("iso") else []
                if not accepted:
                    continue
                try:  # the value is compared, not only that the hook returned (D-119): a constant-returning hook fails
                    got_iso = norm_epoch(got)
                except Exception as e:
                    bad.append(f"valid {v['text']!r} -> {got!r} is not an epoch ({type(e).__name__})")
                    continue
                if all(compare_value("epoch", got_iso, a)[0] == "mismatch" for a in accepted):
                    bad.append(f"valid {v['text']!r} -> {got_iso}, expected {' or '.join(accepted)}")
            for v in ep["invalid"]:
                try:
                    hooks["parse_epoch"](v["text"])
                    bad.append(f"invalid {v['text']!r} accepted")
                except Exception as e:
                    if crashed(e):
                        bad.append(f"invalid {v['text']!r}: {crashed(e)}")
            _vector_item(res, "ccsds-epoch-strings", "vectors/ccsds-epoch-strings.json", hooks["parse_epoch"], bad,
                         f"{qty(len(ep['valid']), 'valid epoch string')} parsed to the {pick(len(ep['valid']), 'instant it denotes', 'instants they denote')} "
                         f"(within {EPOCH_TOLERANCE_US} us) and {qty(len(ep['invalid']), 'invalid string')} rejected")
        elif ep:
            res.add("ccsds-epoch-strings", "skip", "vectors/ccsds-epoch-strings.json", "parser exposes no parse_epoch hook")
        cid = next((v for k, v in vec.items() if k.endswith("norad-cat-id-text.json")), None)
        if cid and hooks["parse_catalog_id"]:
            bad = []
            for v in cid["valid"]:
                try:
                    got = hooks["parse_catalog_id"](v["text"])
                except Unsupported:
                    continue
                except Exception as e:
                    if type(e) is CommandCrashed:
                        bad.append(f"{v['text']!r}: {raised(e)}")
                        continue
                    got = raised(e)
                if got != v["value"] or not is_integral(got):
                    bad.append(f"{v['text']!r} -> {got!r} (expected int {v['value']})")
            for v in cid["invalid_in_omm"]:
                try:
                    got = hooks["parse_catalog_id"](v["text"])
                    bad.append(f"{v['text']!r} accepted as {got!r} (should be rejected: {v['reason']})")
                except Exception as e:
                    if crashed(e):
                        bad.append(f"{v['text']!r}: {crashed(e)}")
            nine = sum(1 for v in cid["valid"] if v["value"] >= 100_000_000)
            _vector_item(res, "catalog-number-is-integer", "vectors/norad-cat-id-text.json", hooks["parse_catalog_id"], bad,
                         f"{qty(len(cid['valid']), 'valid text form')} parsed as int ({nine} nine-digit) and {qty(len(cid['invalid_in_omm']), 'invalid form')} rejected")
        elif cid:
            res.add("catalog-number-is-integer", "skip", "vectors/norad-cat-id-text.json", "parser exposes no parse_catalog_id hook")

    def run_writer(self, case, exp, res):
        """Writer case: every record in expected.json is an input to write_tle; inputs the TLE format cannot
        represent must be refused (that is the correct output); the rest must produce valid, decodable,
        round-tripping lines. Inputs are inline, so the case runs without any fetched file."""
        hook = getattr(self.parser, "write_tle", None)
        if hook is None:
            res.add("tle-writer-catalog-field", "skip", None, "parser exposes no write_tle hook")
            return
        lines_bad, cat_bad, rt_bad, emitted_bad, refused_ok, layout_bad, crashed_bad = [], [], [], [], [], [], []
        conv, sec, signs, prov = {}, {}, {}, {}
        written, refused_real, rt_checked, unreadable = 0, 0, 0, 0
        unsupported, unsupported_reasons = 0, []
        for it in exp["records"]:
            cat, rec, ok_id = it["norad_cat_id"], it["canonical"], it["representable_in_tle"]
            try:
                out = hook(dict(rec))
            except Unsupported as e:
                # collected, never an early return: a writer is unsupported for all of its records or none
                # (D-205's rule, extended by D-280), and what it wrote before raising stays graded
                unsupported += 1
                reason = str(e).strip() or "no reason given"
                if reason not in unsupported_reasons:
                    unsupported_reasons.append(reason)
                continue
            except Exception as e:
                if ok_id:
                    refused_real += 1
                    cat_bad.append(f"id {cat}: {raised(e)}" if type(e) is CommandCrashed else
                                   f"id {cat} refused although the TLE field can carry it: {type(e).__name__}: {str(e)[:120]}")
                elif crashed(e):   # a crash or a timeout refuses nothing (D-341)
                    crashed_bad.append(f"id {cat}: {crashed(e)}")
                else:
                    refused_ok.append(cat)
                continue
            try:
                if type(out) is plain.Problem:   # an answer that holds one set of lines and shows another (D-337)
                    raise ValueError(f"the writer's answer {out.what}")
                l0, l1, l2 = W.normalise_lines(out)
            except Exception as e:
                (lines_bad if ok_id else emitted_bad).append(f"id {cat}: {e}")
                unreadable += bool(ok_id)   # counted with the records the checksum item covers (D-337)
                continue
            if not ok_id:
                emitted_bad.append(f"id {cat}: lines written instead of a refusal (line 1 columns 3-7 {l1[2:7]!r}, {qty(len(l1), 'character')})")
                continue
            written += 1
            problems = W.check_lines(l1, l2)
            if problems:
                lines_bad.append(f"id {cat}: " + "; ".join(problems))
            ok, detail = W.check_catalog_field(l1, l2, cat)
            if not ok:
                cat_bad.append(f"id {cat}: {detail}")
            if len(l1) != 69 or len(l2) != 69:
                continue  # the reader needs well-formed lines; the length failure is already recorded
            layout = W.check_layout(l1, l2)  # right length and checksum say nothing about where the fields sit (D-119)
            if layout:
                layout_bad.append(f"id {cat}: " + "; ".join(layout[:3]) + (f" … ({len(layout)} fields)" if len(layout) > 3 else ""))
            rt_checked += 1
            try:
                mism, c = W.round_trip(l0, l1, l2, rec)
                s = W.secondary_fields(l0, l1, l2, rec)
            except Exception as e:
                rt_bad.append(f"id {cat}: reference reader raised {type(e).__name__}: {str(e)[:120]}")
                continue
            if mism:
                rt_bad.append(f"id {cat}: " + "; ".join(mism))
            for f, k in c.items():
                conv.setdefault(f, {})[k] = conv.setdefault(f, {}).get(k, 0) + 1
            for f in W.SECONDARY_FIELDS:
                sec.setdefault(f, {})[s[f]] = sec.setdefault(f, {}).get(s[f], 0) + 1
            if s["zero_ddot_sign"]:
                signs[s["zero_ddot_sign"]] = signs.get(s["zero_ddot_sign"], 0) + 1
            if it.get("reference_tle_fields"):
                for f, same in W.provider_field_matches(l1, l2, it["reference_tle_fields"]).items():
                    p = prov.setdefault(f, [0, 0])
                    p[0] += bool(same)
                    p[1] += 1

        if unsupported == len(exp["records"]):
            res.add("tle-writer-catalog-field", "skip", None,
                    f"parser reports TLE writing unsupported: {'; '.join(unsupported_reasons)}")
            return
        if unsupported:
            res.add("tle-writer-catalog-field", "fail", None,
                    f"write_tle answered unsupported for {unsupported} of {qty(len(exp['records']), 'record')} "
                    f"({'; '.join(unsupported_reasons[:3])}) and wrote or refused the rest: an operation is "
                    "unsupported for all of its records or none (D-205, D-280); what was written is graded below")

        def summary(fails, ok_text, n_ok, n_all, unit="record"):
            # a failing detail opens with what passed, so a failure confined to a few inputs cannot read as a general one
            if not fails:
                return ok_text
            return f"{n_ok} of {qty(n_all, unit)} correct; " + "; ".join(fails[:8]) + (" ..." if len(fails) > 8 else "")

        n_real = written + refused_real
        n_lines = written + unreadable   # an output that could not be read as lines is one of these, and failed (D-337)
        # with nothing written, nothing was checked: "pass, 0 written correctly" said otherwise (D-337)
        nothing = "no record was written as TLE lines that could be read, so nothing here was checked"
        if n_lines:
            res.add("tle-checksums-valid", "fail" if lines_bad else "pass", None,
                    summary(lines_bad, f"{qty(written, 'record')} written as two 69-character lines with valid checksums", n_lines - len(lines_bad), n_lines))
        else:
            res.add("tle-checksums-valid", "not-exercised", None, nothing, cause="parser")
        if n_real or cat_bad:
            res.add("tle-writer-catalog-field", "fail" if cat_bad else "pass", None,
                    summary(cat_bad, f"{qty(written, 'catalog field')} written correctly (five digits below 100000, Alpha-5 from 100000)",
                            n_real - len(cat_bad), n_real, "catalog field"))
        elif not any(i.check == "tle-writer-catalog-field" for i in res.items):   # the all-or-none item speaks otherwise
            res.add("tle-writer-catalog-field", "not-exercised", None, nothing, cause="parser")
        conv_text = "; ".join(f"{f}: " + ", ".join(f"{k} {n}" for k, n in sorted(v.items())) for f, v in conv.items())
        if rt_checked:
            res.add("tle-writer-column-layout", "fail" if layout_bad else "pass", None,
                    summary(layout_bad, f"{qty(rt_checked, 'record')} with every field in its fixed columns", rt_checked - len(layout_bad), rt_checked))
            res.add("tle-writer-round-trip", "fail" if rt_bad else "pass", None,
                    summary(rt_bad, f"{qty(written, 'record')} read back at the TLE field resolution (rendering observed per field: {conv_text})",
                            rt_checked - len(rt_bad), rt_checked))
        else:
            res.add("tle-writer-column-layout", "not-exercised", None, nothing, cause="parser")
            res.add("tle-writer-round-trip", "not-exercised", None, nothing, cause="parser")
        unrep = [it["norad_cat_id"] for it in exp["records"] if not it["representable_in_tle"]]
        if unrep:
            head = f"{len(refused_ok)} of {qty(len(unrep), 'number')} the TLE catalog field cannot represent (synthetic inputs, D-096) correctly refused"
            if emitted_bad or crashed_bad:
                detail = (head + (f" ({', '.join(map(str, refused_ok))})" if refused_ok else "")
                          + ("; written instead of refused: " + "; ".join(emitted_bad[:8]) if emitted_bad else "")
                          + ("; crashed instead of refusing: " + "; ".join(crashed_bad[:8]) if crashed_bad else ""))
            else:
                detail = head + f" ({', '.join(map(str, refused_ok))}); a refusal is the right output here, and such numbers belong in the OMM formats"
            res.add("tle-writer-refuses-unencodable", "fail" if emitted_bad or crashed_bad else "pass", None, detail)
        if sec:
            sec_text = "; ".join(f"{f}: " + ", ".join(f"{k} {n}" for k, n in sorted(v.items())) for f, v in sec.items())
            sign_text = ", ".join(f"'{k}' {n}" for k, n in sorted(signs.items())) or "no zero second derivative written"
            res.add("tle-writer-secondary-fields", "info", None, f"{sec_text}; zero second-derivative exponent sign: {sign_text} (CelesTrak writes +, Space-Track -)")
            # a name cut to the line's 24 columns is kept as the format allows; any other outcome is not (D-369)
            res.secondary_not_kept = [f for f, v in sec.items() if set(v) - {"preserved", "cut-to-24"}]
        if prov:
            res.add("tle-writer-matches-provider-rendering", "info", None,
                    "byte-identical to the provider's or derived rendering: " + ", ".join(f"{f} {a}/{n}" for f, (a, n) in prov.items()))

    @staticmethod
    def unedited_diffs(got, base):
        """The fields in which a record the parser returned from a corrupt input differs from the same parser's reading
        of that record in the unedited file (D-175), compared exactly: the same parser read the same record, so a
        difference is the edit's doing. How close either reading comes to the frozen values is the values check's
        question, asked in the records' own cases; asked here as well, it failed a parser that reads these records
        imprecisely in every file, whatever it did with the corrupt input."""
        def same(a, b):
            return a == b or (isinstance(a, Decimal) and isinstance(b, Decimal) and a.is_nan() and b.is_nan())
        diffs = []
        for field in CORE_FIELDS + OPTIONAL_FIELDS:
            a, b = got.get(field), base.get(field)
            bad_a, bad_b = got.get("_bad", {}).get(field), base.get("_bad", {}).get(field)
            if not same(a, b) or bad_a != bad_b:
                diffs.append(f"{field} = {bad_a or repr(a)}, from the unedited file {bad_b or repr(b)}")
        return diffs

    def read_unedited(self, res, path, src, fmt, readings):
        """The parser's reading of an unedited file (D-175), made once per run of the case: ({id: first record}, {id:
        count}, None), or (None, None, why) when the file cannot serve as the comparison, because the parser refused it
        as a whole or declared it unsupported, or its bytes are not the ones the case was built on. A refusal by a raise,
        an answer that is not a list of records (D-330) or a value the runner cannot read (D-319) fails the file as
        `parse`, since it is a valid file of its format (D-339); `Unsupported` there is a skip (D-280)."""
        if path in readings:
            return readings[path]
        full = self.path(path)
        if not os.path.exists(full):
            self.report_missing(res, path)  # ships with the corpus: an incomplete copy stops the run (D-148)
        actual = sha256(full)
        res.modes[path] = "snapshot" if actual == src.get("sha256") else "live"
        if actual != src.get("sha256"):
            res.drift[path] = {"recorded_sha256": src.get("sha256"), "actual_sha256": actual}
            res.add("stable-source-drift", "fail", path, f"the unedited file's bytes differ from the ones the case was built on (recorded SHA-256 "
                    f"{str(src.get('sha256'))[:12]}…, actual {actual[:12]}…): the inputs it is the comparison for were not graded")
            readings[path] = (None, None, "its bytes are not the recorded ones")
            return readings[path]
        with open(full, "rb") as f:
            raw = f.read()
        try:
            out = (getattr(self.parser, "parse", None) or self.parser)(raw, fmt)
        except Unsupported as e:
            # an unedited file is an input of its format like any other (D-280): declaring it unsupported counts
            # in the all-or-none bookkeeping, where before it went unregistered and a per-input dodge could hide
            readings[path] = (None, None, f"the parser declared it unsupported ({str(e)[:160]})")
            res.add("format-supported", "skip", path, f"parser reports {fmt} unsupported (the unedited comparison file)")
            res.fmt_dodged.append((fmt, len(res.items) - 1, path))
            return readings[path]
        except Exception as e:
            # a raise on the unedited file, a valid file of its format, fails it as `parse`, as on any other valid file
            # (D-339, the owner's ruling on D-334's finding 6); before, the case's checks were set aside with no failure
            res.add("parse", "fail", path, parse_failure(e))
            readings[path] = (None, None, f"the parser's command {e}" if type(e) is CommandCrashed else
                              f"the parser refused it as a whole ({type(e).__name__}: {str(e)[:160]})")
            res.fmt_read.setdefault(fmt, []).append(path)   # it read the format far enough to refuse the file
            return readings[path]
        res.fmt_read.setdefault(fmt, []).append(path)
        try:
            out = as_records(out)
        except NotRecords as e:
            # the comparison file fails as `parse`, as a file does in every other case, and nothing is compared with it (D-330)
            res.add("parse", "fail", path, unreadable_words(e))
            readings[path] = (None, None, f"the parser's answer {e.what}")
            return readings[path]
        base, count, parsed = {}, {}, []
        try:
            for r in split_refusals(out)[0]:
                n, notes, bad = norm_record(r)
                n["_notes"] = notes
                if bad:
                    n["_bad"] = bad
                parsed.append(n)
                base.setdefault(n.get("norad_cat_id"), n)
                count[n.get("norad_cat_id")] = count.get(n.get("norad_cat_id"), 0) + 1
        except (ValueError, ArithmeticError) as e:
            # a value the runner cannot read as a decimal or an epoch: the whole file fails as `parse`, as it does in
            # every other case (D-319; before, this one raised inside the runner and the case was lost to an internal error)
            res.add("parse", "fail", path, unreadable_words(e))
            readings[path] = (None, None, f"the parser returned a value in it that the runner cannot read ({str(e)[:120]})")
            return readings[path]
        readings[path] = (base, count, None)
        readings[("parsed", path)] = parsed
        return readings[path]

    def run_corrupt_input(self, case, exp, res):
        """Corrupt-input case (D-171): each file that ships with the corpus hands the parser one corrupt input between
        valid records. The corrupt record must come back refused with a reason and the valid ones loaded; every record's
        outcome is counted in the vocabulary of D-142 and D-144 (loaded, misidentified, refused, dropped), a record built
        from garbage counting as misidentified. What the parser returns is compared, record by record and exactly, with
        what the same parser returns from the input's unedited file, the same records with no edit (D-175), so the items
        that isolate the edit grade what it changes and nothing else; a record the parser does not return from the
        unedited file either is left out of them. Each unedited file is also held to its records' frozen values, a values item of its
        own (D-299, D-342). A parser that raises on a file has refused it as a whole, which is fail-closed for a
        file cut mid-record, the complete records it gave up counted (owner decision 3), and for a TLE file gives up the
        valid sets around the corrupt one. A parser that validates no checksum returns input 1's set exactly as it
        returns it unedited: reported, not failed (owner decision 2)."""
        by_file = {}
        for r in exp["records"]:
            by_file.setdefault(r["file"], []).append(r)
        unedited = exp["case_specific"].get("unedited", {})
        readings = {}  # unedited file -> the parser's reading of it, made once
        for path, src in exp["sources"].items():
            if path in unedited or path in exp["case_specific"].get("graded", {}):
                continue  # read when an input it is the comparison for is graded; a graded file after the inputs
            base_name = os.path.basename(path)
            spec = exp["case_specific"]["files"][base_name]
            check, fmt, cut = spec["check"], spec["format"], spec["check"] == "corrupt-file-cut"
            want = sorted(by_file.get(base_name, []), key=lambda r: r["position"])
            full = self.path(path)
            if not os.path.exists(full):
                self.report_missing(res, path)  # ships with the corpus: an incomplete copy stops the run (D-148)
                continue
            actual = sha256(full)
            res.modes[path] = "snapshot" if actual == src.get("sha256") else "live"
            if actual != src.get("sha256"):
                res.drift[path] = {"recorded_sha256": src.get("sha256"), "actual_sha256": actual}
                res.add("stable-source-drift", "fail", path, f"the file's bytes differ from the input the case was built on (recorded SHA-256 "
                        f"{str(src.get('sha256'))[:12]}…, actual {actual[:12]}…): its expectations describe other bytes and were not applied")
                continue
            whole = None
            with open(full, "rb") as f:
                raw = f.read()
            try:
                out = (getattr(self.parser, "parse", None) or self.parser)(raw, fmt)
            except Unsupported:
                res.add(check, "skip", path, f"parser reports {fmt} unsupported")
                res.fmt_dodged.append((fmt, len(res.items) - 1, path))
                continue
            except Exception as e:  # the parser refused the file as a whole, with the exception as its reason
                if crashed(e):   # a crash or a timeout refuses nothing: the input's check fails (D-341)
                    res.add(check, "fail", path, crashed(e))
                    res.fmt_read.setdefault(fmt, []).append(path)
                    continue
                whole, out = f"{type(e).__name__}: {str(e)[:160]}", []
            if whole is None:
                res.fmt_read.setdefault(fmt, []).append(path)
            try:
                out = as_records(out)
            except NotRecords as e:
                res.add(check, "fail", path, unreadable_words(e))   # D-330
                continue
            upath = spec["unedited"]
            uname = os.path.basename(upath)
            base, base_count, why = self.read_unedited(res, upath, exp["sources"][upath], fmt, readings)
            if ("surplus", upath) not in readings:
                # D-311: the unedited file holds each of its records once too, and it is the reading everything here
                # is compared with; a record the parser returns twice from it fails there, once per file
                readings[("surplus", upath)] = True
                over = sorted(k for k, n in (base_count or {}).items() if k is not None and n > 1)
                if over:
                    res.add("values", "fail", upath, "; ".join(f"id {k}: returned {qty(base_count[k], 'time')} where the input holds it once (D-311)" for k in over[:6])
                            + (" ..." if len(over) > 6 else ""))
            if why:
                for c in (check, "corrupt-input-neighbours-load"):
                    res.add(c, "not-exercised", path, f"no comparison: the unedited file {uname} cannot serve as one ({why}), so nothing here isolates what the edit changes",
                            cause="data" if "bytes are not the recorded ones" in why else "parser")
                continue
            if fmt in ("tle", "csv", "json") and ("graded", upath) not in readings:
                # D-299 (the red team's E15): before this, no case that runs without fetched data compared an OMM
                # value with an expected one -- these files were read only to be compared with the parser's own
                # reading of them (D-175). They hold real records with negative drag terms; their frozen values
                # are the ones the inputs' records already carry, the values of the record with no edit. The TLE
                # file too (D-342): a parser that dropped a record from it as well as from the inputs read
                # not-exercised there, where the CSV and JSON files caught the same drop.
                readings[("graded", upath)] = True
                oracle = {}
                for r in want:
                    vals = dict(r["expected"])
                    for k in list(vals):
                        if k in DEC_FIELDS and vals[k] is not None:
                            vals[k] = Decimal(str(vals[k]))
                    oracle[r["norad_cat_id"]] = vals
                self.compare_values(res, upath, fmt, "snapshot", readings[("parsed", upath)], oracle, oracle_label="frozen expected values")
            got, refusals, declared = split_refusals(out)
            res.refusals[path], res.declared[path] = refusals, declared
            self.report_refusals(res, path, refusals)
            parsed = []
            try:
                for r in got:
                    n, notes, bad = norm_record(r)
                    n["_notes"] = notes
                    if bad:
                        n["_bad"] = bad
                    parsed.append(n)
            except (ValueError, ArithmeticError) as e:   # as in read_unedited: the file fails as `parse` (D-319)
                res.add("parse", "fail", path, unreadable_words(e))
                continue
            if parsed:
                self.check_ints(res, path, parsed, set(case["checks"]))   # D-283: active here like any record case
            by_id = {}
            for p in parsed:
                by_id.setdefault(p.get("norad_cat_id"), []).append(p)
            ids = {r["norad_cat_id"] for r in want}
            with_reason = [x for x in refusals if x["ok"]]
            outcome: dict = {}  # id -> (outcome, what)
            for r in want:
                cat = r["norad_cat_id"]
                if whole:
                    outcome[cat] = ("refused" if r["role"] == "corrupt" else "given up", whole)
                elif by_id.get(cat):
                    if cat in base:   # every copy is compared (D-281)
                        diffs = [d for copy in by_id[cat] for d in self.unedited_diffs(copy, base[cat])]
                    else:
                        diffs = ["a record the parser does not return from the unedited file"]
                    outcome[cat] = ("garbage", "; ".join(diffs[:3])) if diffs else ("loaded", None)
                elif any(x["id"] == cat for x in with_reason):
                    outcome[cat] = ("refused", next(x["reason"] for x in with_reason if x["id"] == cat))
                elif any(x["id"] == cat for x in refusals):
                    outcome[cat] = ("refused without a reason", None)
                else:
                    outcome[cat] = ("dropped", None)
            corrupt = next((r for r in want if r["role"] == "corrupt"), None)
            # D-311: these files hold each id once. A second copy is a failure of its own, said in its own words: it
            # is not the edit's doing, so it changes no outcome above and no count below, and it does not depend on
            # how often the parser returned the record from the unedited file.
            surplus = {cat: len(by_id[cat]) for cat in ids if len(by_id.get(cat, [])) > 1}
            def twice(cat):
                return f"{cat} returned {qty(surplus[cat], 'time')} where the input holds it once (D-311)"
            unmatched = [x for x in with_reason if x["id"] not in ids]
            # D-282: a refusal whose _field decodes to no record credits a record only on evidence -- an _input, or a
            # _field (D-360: an invalid catalog field decodes to no record, and _input is optional), that quotes this
            # file's text and not the unedited file's, i.e. something the edit introduced.
            # ADAPTERS.md has said so all along ("a field of any other form credits the refusal to no record");
            # the earlier behaviour credited any unmatched refusal, which let a silent drop hide behind a decoy.
            edited_text = raw.decode("utf-8", "replace")
            unedited_text = open(self.path(upath), "rb").read().decode("utf-8", "replace")
            # a _field is the catalog field as the input carried it (ADAPTERS.md), so it is evidence only where it is the
            # catalog field (columns 3-7) of an element line the edit introduced: any other text the edit introduced, "O"
            # or a few digits, let a decoy credit a silent drop (D-360's second reading)
            def catalog_fields(text):
                return {l[2:7].strip() for l in text.splitlines() if l[:2] in ("1 ", "2 ") and len(l) >= 7}
            new_fields = catalog_fields(edited_text) - catalog_fields(unedited_text)
            def quotes_edit(x):
                q = x["input"]
                return bool((q and q.strip() and q in edited_text and q not in unedited_text)
                            or (x["field"] and x["field"].strip() in new_fields))
            evidenced = [x for x in unmatched if quotes_edit(x)]
            # a cut introduces no new text, so its evidence is the cut site: a refusal quoting the edited file's tail
            evidenced_cut = [x for x in with_reason if x["input"] and x["input"].strip() and x["input"] in edited_text[-200:]]
            if corrupt and outcome[corrupt["norad_cat_id"]][0] == "dropped" and evidenced:
                outcome[corrupt["norad_cat_id"]] = ("refused", evidenced[0]["reason"])
            # a refusal without a reason that quotes the edit is that, not a drop the adapter never reported (D-360's
            # reading: on the invalid catalog field it read "refusals not reported by this adapter")
            elif corrupt and outcome[corrupt["norad_cat_id"]][0] == "dropped" and any(
                    quotes_edit(x) for x in refusals if not x["ok"] and x["id"] not in ids):
                outcome[corrupt["norad_cat_id"]] = ("refused without a reason", None)
            # records the parser does not return from the unedited file either: what it does with them here is not the edit's doing
            unread = {cat for cat in ids if cat not in base and outcome[cat][0] != "garbage"}
            # records beyond the expected ones (an id the file does not hold, a second copy), unless the unedited reading has them too
            extra = [p for k, ps in by_id.items() for p in ps[max(base_count.get(k, 0), 1 if k in ids else 0):]]
            reasons = [x["reason"] for x in with_reason] or ([whole] if whole else [])
            counts = {"expected": len(want), "returned": len(parsed),
                      "loaded": sum(1 for o, _ in outcome.values() if o == "loaded"),
                      "misidentified": sum(1 for o, _ in outcome.values() if o == "garbage") + len(extra),
                      "dropped": sum(1 for o, _ in outcome.values() if o in ("dropped", "refused without a reason")),
                      "non_integer_id": len([p for p in by_id.get(None, []) if p.get("_bad", {}).get("norad_cat_id")]),
                      "refused": len(want) if whole else len(with_reason),
                      "refused_matched": sum(1 for o, _ in outcome.values() if o in ("refused", "given up")),
                      "refused_without_reason": len(refusals) - len(with_reason), "refusals_reported": declared,
                      # a tie settled by the reason's text, as compare_values settles it: by set order it followed the hash
                      # seed, and a report compared byte for byte could differ with nothing changed (D-356)
                      "top_refusal_reason": max(collections.Counter(reasons).items(), key=lambda kv: (kv[1], kv[0]))[0] if reasons else None}
            garbage_extra = f"; {qty(len(extra), 'record')} the file does not hold, built from garbage" if extra else ""
            # the corrupt input itself
            if corrupt is None:  # the JSON array without its closing bracket: every record complete, the file cut
                if whole:
                    status, text = "pass", f"the parser refused the file as a whole ({whole}): fail-closed; {qty(len(want), 'complete record')} given up with it"
                elif evidenced_cut and not extra:
                    status, text = "pass", f"the cut reported with a reason that quotes the cut site ({evidenced_cut[0]['reason'][:120]!r})"
                else:
                    status, text = "fail", (f"{counts['loaded']} of {qty(len(want), 'record')} loaded and nothing said of the cut "
                                            f"({spec.get('file_edit', 'the file is cut')}): silent partial loading" + garbage_extra)
            elif corrupt["norad_cat_id"] in unread:
                status, text = "not-exercised", (f"the parser does not return {corrupt['norad_cat_id']} from the unedited file {uname} either, "
                                                 "so what it does with the edited record says nothing about the edit")
            else:
                o, what = outcome[corrupt["norad_cat_id"]]
                if o == "refused":
                    status, text = "pass", (f"the parser refused the file as a whole ({whole})" + (": fail-closed for a file cut mid-record" if cut else "")
                                            if whole else f"the corrupt record refused with a reason: {what[:160]!r}")
                elif o == "loaded":
                    status = "info" if corrupt["if_read_as_unedited"] == "report" else "fail"
                    text = f"{corrupt['read_as_unedited_means']} ({corrupt['edit']})"
                elif o == "garbage":
                    status, text = "fail", f"built a record from the corrupt input: {what}"
                elif o == "refused without a reason":
                    status, text = "fail", "the corrupt record refused without a reason: no better than a drop (D-144)"
                else:
                    status, text = "fail", ("the cut row dropped with nothing said: silent partial loading" if cut else "the corrupt record dropped " +
                                            ("silently" if declared else "(refusals not reported by this adapter)"))
                    if unmatched:
                        # said without a reason why: the evidence a refusal may carry differs by input and branch (D-360's
                        # checks: each explanation was false somewhere, the CSV cut row's among them)
                        text += f"; {qty(len(unmatched), 'refusal')} naming no record of this file credited to none (D-282, D-360)"
                if extra:
                    status, text = "fail", text + garbage_extra
                if corrupt["norad_cat_id"] in surplus:
                    status, text = "fail", text + "; " + twice(corrupt["norad_cat_id"])
            res.add(check, status, path, text, counts=counts, cause="parser" if status == "not-exercised" else None)
            # the valid records around it, graded where the parser returns them from the unedited file
            valid = [r for r in want if r["role"] == "valid"]
            graded = [r for r in valid if r["norad_cat_id"] not in unread]
            def where(k):  # the count with its noun, agreeing in number (D-239)
                return qty(k, "complete record") if cut else f"{qty(k, 'valid set')} around the corrupt one"
            left_out = [str(r["norad_cat_id"]) for r in valid if r["norad_cat_id"] in unread]
            note = f"; not graded: {', '.join(left_out)}, which the parser does not return from the unedited file either" if left_out else ""
            label = {"garbage": "changed by the corrupt input"}
            problems = [f"{r['norad_cat_id']} {label.get(outcome[r['norad_cat_id']][0], outcome[r['norad_cat_id']][0])}"
                        + (f" ({outcome[r['norad_cat_id']][1][:160]})" if outcome[r['norad_cat_id']][1] else "")
                        for r in graded if outcome[r["norad_cat_id"]][0] != "loaded"]
            loaded_n = len(graded) - len(problems)
            problems += [twice(r["norad_cat_id"]) for r in graded if r["norad_cat_id"] in surplus]
            if not graded:
                res.add("corrupt-input-neighbours-load", "not-exercised", path, (f"the parser does not return the {where(1)}" if len(valid) == 1 else f"the parser returns none of the {where(len(valid))}")
                        + f" from the unedited file {uname} either, so nothing here shows what the edit changed", cause="parser")
            elif whole and cut:
                res.add("corrupt-input-neighbours-load", "info", path, f"{where(len(graded))} given up with the file: a whole-file refusal of a file cut mid-record is fail-closed (owner decision 3, D-171)" + note)
            elif whole:
                res.add("corrupt-input-neighbours-load", "fail", path, f"the parser refused the file as a whole ({whole}), so the {where(len(graded))} {pick(len(graded), 'was', 'were')} given up with it" + note)
            elif problems:
                res.add("corrupt-input-neighbours-load", "fail", path, f"{loaded_n} of {where(len(graded))} loaded as the parser reads {pick(len(graded), 'it', 'them')} from "
                        f"the unedited file {uname}; " + "; ".join(problems) + note)
            else:
                res.add("corrupt-input-neighbours-load", "pass", path, f"{where(len(graded))} loaded, {pick(len(graded), '', 'each ')}exactly as the parser reads it from the unedited file {uname}" + note)
        self.grade_values_only(case, exp, res, by_file)

    def grade_values_only(self, case, exp, res, by_file):
        """The files of the corrupt-input case that are graded for their values and nothing else (D-299): the one
        derived XML file, held to the frozen values the CSV input's records carry for the same record."""
        for path, g in exp["case_specific"].get("graded", {}).items():
            full, fmt = self.path(path), g["format"]
            if not os.path.exists(full):
                self.report_missing(res, path)
                continue
            src = exp["sources"][path]
            actual = sha256(full)
            res.modes[path] = "snapshot" if actual == src.get("sha256") else "live"
            if actual != src.get("sha256"):
                res.drift[path] = {"recorded_sha256": src.get("sha256"), "actual_sha256": actual}
                res.add("stable-source-drift", "fail", path, "the file's bytes differ from the ones the case was built on: its expectations describe other bytes and were not applied")
                continue
            try:
                parsed = self.parse(full, fmt)
            except Unsupported:
                res.add("format-supported", "skip", path, f"parser reports {fmt} unsupported")
                res.fmt_dodged.append((fmt, len(res.items) - 1, path))
                continue
            except Exception as e:
                res.add("parse", "fail", path, parse_failure(e))
                continue
            res.fmt_read.setdefault(fmt, []).append(path)
            oracle = {}
            for r in by_file.get(g["values_like"], []):
                if r["norad_cat_id"] in g["norad_cat_ids"]:
                    vals = dict(r["expected"])
                    for k in list(vals):
                        if k in DEC_FIELDS and vals[k] is not None:
                            vals[k] = Decimal(str(vals[k]))
                    oracle[r["norad_cat_id"]] = vals
            self.compare_values(res, path, fmt, "snapshot", parsed, oracle, oracle_label="frozen expected values")

    def run_case(self, case):
        exp = json.load(open(os.path.join(self.root, "fixtures", case["id"], "expected.json"), encoding="utf-8"))
        res = CaseResult(case["id"], case["title"], purpose=case.get("checks", ()))
        kind = exp["kind"]
        exits_before = len(self.parser_exits)
        try:
            if kind in ("gp", "derived-tle", "derived-kvn"):
                self.run_gp_like(case, exp, res)
            elif kind == "pairs":
                self.run_pairs(case, exp, res)
            elif kind == "facts":
                self.run_facts(case, exp, res)
            elif kind == "xml":
                self.run_xml(case, exp, res)
            elif kind == "satcat":
                self.run_satcat(case, exp, res)
            elif kind == "vectors":
                self.run_vectors(case, exp, res)
            elif kind == "writer":
                self.run_writer(case, exp, res)
            elif kind == "corrupt-input":
                self.run_corrupt_input(case, exp, res)
        except CorpusIncomplete:
            raise  # a broken copy of the corpus is not a result about the parser (D-148); the parser's own is a ParserRaised
        except ParserExit:
            # counted where the guard caught it, and the parser-exit item below says so (D-293); one the guard did not
            # count is the runner's own type raised by the parser's code, and is counted here, never swallowed (D-337)
            if len(self.parser_exits) == exits_before:
                self.parser_exits.append(("the runner's reading of its answer", "ParserExit"))
        except ParserRaised as e:
            # the parser's exception where no check takes it, a property it raised from as the runner looked a hook up,
            # say: the parser's, in its words, not "internal error in runner" (D-337)
            res.add("parser-raised", "fail", None, f"the parser raised {type(e).__name__}: {str(e)[:200]}")
        except Exception as e:
            res.add("runner", "fail", None, f"internal error in runner: {type(e).__name__}: {e}")
        except BaseException as e:
            if issubclass(type(e), KeyboardInterrupt):
                raise
            # the runner raises none of these, and since D-337 nothing the parser made is called after the guard, so
            # none should reach here; if one does, it is the parser's code, and it is counted, never the end of the run
            what = type(e).__name__
            self.parser_exits.append(("the runner's reading of its answer", what))
        # D-293 (the red team's E9): every attempt of the parser to end the run during this case is a failure of the
        # case, whatever the code that called it made of the exception
        exits = self.parser_exits[exits_before:]
        if exits:
            kinds = sorted({f"{what} in {where}" for where, what in exits})
            res.add("parser-exit", "fail", None, f"the parser tried to end the run {qty(len(exits), 'time')} ({'; '.join(kinds[:4])}): "
                    "a parser must not exit the process; the run continued and this case fails (D-293)")
        # D-280 (the SM-26 audit, issue #1): an Unsupported format is unsupported for all of a case's inputs or
        # none, as D-205 holds for the vector hooks. A skip earned while other files of the same format were read
        # is a dodge, and becomes the failure it hid.
        for fmt, idx, path in res.fmt_dodged:
            read = res.fmt_read.get(fmt, [])
            if read:
                it = res.items[idx]
                it.status = "fail"
                it.detail += (f" — but this parser read {qty(len(read), 'other ' + str(fmt) + ' input')} of this case"
                              f" (e.g. {os.path.basename(read[0])}): a format is unsupported for all of a case's"
                              " inputs or none (D-280)")
        return res

    def run(self, case_ids=None, tags=None):
        results = []
        for case in self.manifest["cases"]:
            if case_ids and case["id"] not in case_ids:
                continue
            if tags and not (set(tags) & set(case["tests"])):
                continue
            results.append(self.run_case(case))
        # D-280, across the whole run: a parser that read a format anywhere in this run cannot declare an input
        # of that format unsupported in another case; the per-case pass in run_case caught same-case mixes already.
        read_anywhere = {}
        for res in results:
            for fmt, paths in res.fmt_read.items():
                read_anywhere.setdefault(fmt, []).extend(paths)
        for res in results:
            for fmt, idx, path in res.fmt_dodged:
                it = res.items[idx]
                if it.status == "skip" and read_anywhere.get(fmt):
                    others = [q for q in read_anywhere[fmt] if q != path]
                    if others:
                        it.status = "fail"
                        it.detail += (f" — but this parser read {qty(len(others), 'other ' + str(fmt) + ' input')} in this run"
                                      f" (e.g. {os.path.basename(others[0])}): a format is unsupported for all inputs or none (D-280)")
        return results


# --------------------------------------------------------------------------- external command adapter
def _crash(words):
    """A CommandCrashed of the runner's own, recorded so the guard knows it by identity (D-342)."""
    e = CommandCrashed(words)
    _CRASHES.add(e)
    return e


class CommandParser:
    """Runs an external program per file: raw bytes on stdin, JSON array of records on stdout.
    {fmt} in the command is replaced with the file's format, the only placeholder. Exit 3 = format unsupported; any
    other non-zero exit, or output that is not a JSON array = parse failure (docs/ADAPTERS.md, D-161). For all three
    commands, an end by a signal (a negative return code; from a shell command, an exit of 128 plus one of
    CRASH_SIGNALS) or a run past `timeout` is a crash, CommandCrashed, never a refusal or a rejection (D-341).
    vectors_cmd (optional): {"op", "input"} on stdin, one of {"result": value}, {"error": reason} (a rejection) or,
    from 0.5.0, {"unsupported": reason} (the operation the library does not have: the item skips) on stdout; any
    non-zero exit is a rejection, 3 included, since the vectors protocol never gave it a meaning (D-205).
    write_cmd (optional): one JSON record on stdin, the TLE lines on stdout (2 or 3 lines); exit 0 =
    written, exit 3 = writing unsupported, any other non-zero exit = the record was refused.

    A command is a shell string, as `--cmd` gives it, or an argument list, as the Node presets build it (D-154): a list
    runs without a shell, in `cwd` with `env` when given, and only an element that is exactly "{fmt}" is substituted, so
    a harness's source passed as an argument is never altered."""

    def __init__(self, cmd, vectors_cmd=None, timeout=120, write_cmd=None, cwd=None, env=None):
        self.cmd, self.vectors_cmd, self.timeout, self.write_cmd = cmd, vectors_cmd, timeout, write_cmd
        self.cwd, self.env = cwd, env

    @staticmethod
    def _stderr(p):
        """A failing command's standard error as an item's detail carries it: the last 300 characters, without the
        line ending most programs end with, which would otherwise break the report's line (D-177)."""
        return p.stderr.decode("utf-8", "replace").strip()[-300:]

    def _run(self, cmd, data, fmt=None):
        """The command's completed process; a command ended by a signal, or still running after `timeout` seconds,
        raises CommandCrashed, which no caller takes for a refusal or a rejection (D-341). A timeout kills the process
        the runner started; behind a shell, the shell's own children may run on."""
        try:
            if isinstance(cmd, (list, tuple)):
                argv = [fmt if (a == "{fmt}" and fmt is not None) else a for a in cmd]
                p = subprocess.run(argv, input=data, capture_output=True, timeout=self.timeout, cwd=self.cwd, env=self.env)
            else:
                if fmt is not None:
                    cmd = cmd.replace("{fmt}", fmt)
                p = subprocess.run(cmd, shell=True, input=data, capture_output=True, timeout=self.timeout, cwd=self.cwd, env=self.env)
        except subprocess.TimeoutExpired:
            raise _crash(f"did not finish within {self.timeout} seconds") from None
        shell = not isinstance(cmd, (list, tuple))
        if p.returncode < 0 or (shell and p.returncode - 128 in CRASH_SIGNALS):
            sig = -p.returncode if p.returncode < 0 else p.returncode - 128
            try:
                shown = f"signal {sig} ({signal.Signals(sig).name})"
            except ValueError:
                shown = f"signal {sig}"
            how = f"was ended by {shown}" if p.returncode < 0 else f"exited {p.returncode}, which is how a shell reports {shown}"
            tail = self._stderr(p)
            raise _crash(how + (f": {tail}" if tail else ""))
        return p

    def parse(self, raw, fmt):
        if not self.cmd:
            raise Unsupported(fmt)
        p = self._run(self.cmd, raw, fmt)
        if p.returncode == 3:
            raise Unsupported(fmt)
        if p.returncode != 0:
            raise RuntimeError(f"exit {p.returncode}: {self._stderr(p)}")
        try:
            # a byte-order mark before the JSON (.NET and PowerShell tools write one) is no part of it (D-369)
            data = json.loads(p.stdout.decode("utf-8-sig"))
        except ValueError as e:
            raise RuntimeError(f"stdout is not JSON ({e}): {p.stdout.decode('utf-8', 'replace')[:120]!r}")
        return data   # its shape is judged by as_records, as a Python adapter's is (D-334)

    def write_tle(self, record):
        if not self.write_cmd:
            raise Unsupported("tle-writing")
        p = self._run(self.write_cmd, json.dumps(record, default=str).encode())
        if p.returncode == 3:
            raise Unsupported("tle-writing")
        if p.returncode != 0:
            raise RuntimeError(f"exit {p.returncode}: {self._stderr(p)}")
        return p.stdout.decode("utf-8-sig")   # a byte-order mark is no part of the lines (D-369)

    def _vec(self, op, value):
        if not self.vectors_cmd:
            raise AttributeError(op)
        p = self._run(self.vectors_cmd, json.dumps({"op": op, "input": value}).encode())
        try:
            out = json.loads(p.stdout.decode("utf-8-sig") or "{}")   # a byte-order mark is no part of the JSON (D-369)
        except ValueError as e:
            raise ValueError(f"the command's output is not JSON: {e}")
        if p.returncode != 0:  # any non-zero exit is a rejection, 3 included (D-205)
            raise ValueError(out.get("error", f"exit {p.returncode}"))
        if "unsupported" in out:  # an operation the library does not have: the item skips (D-205)
            reason = out["unsupported"]
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("the command's unsupported answer carries no reason")
            raise Unsupported(reason.strip())
        if "error" in out:
            raise ValueError(out["error"])
        if "result" not in out:  # a well-formed answer carries result, error or unsupported (D-118, D-205)
            raise ValueError("the command's answer carries neither 'result', 'error' nor 'unsupported'")
        return out["result"]

    def __getattr__(self, name):
        if name in ("alpha5_decode", "alpha5_encode", "two_digit_year", "parse_epoch", "parse_catalog_id") and self.vectors_cmd:
            def hook(value):
                r = self._vec(name, value if not isinstance(value, dt.datetime) else value.isoformat())
                if name != "parse_epoch":
                    return r
                # a command answers in text, which is converted here; the input's own text handed back unparsed is
                # no answer, whatever this Python's fromisoformat would make of it (D-306)
                if isinstance(r, str) and isinstance(value, str) and r.strip() == value.strip() and not CALENDAR_EPOCH.match(r.strip()):
                    raise ValueError("the command returned the input's own epoch text, unparsed")
                return dt.datetime.strptime(tlemod.iso_epoch(r), "%Y-%m-%dT%H:%M:%S.%f")
            return hook
        raise AttributeError(name)
