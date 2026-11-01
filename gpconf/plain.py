# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""What crosses the parser's guard: everything an in-process adapter returns, read once into plain built-in values
inside the guard (D-337).

gpconf grades wrong answers. An adapter in the runner's process returns Python objects, and an object's own methods
(its `__eq__`, `__str__`, `strip()`, `keys()`, `strftime()`) decide what a check sees whenever the runner calls them.
Three readings of the same change found a wrong answer passing through each of those doors in turn. So the runner
calls none of them after the guarded call has returned: the guard reads the answer here, while the parser's code is
still guarded, into the values below, and every check works on those. A wrong value that survives this reading is an
escape and is fixed. An adapter that attacks the runner itself (patching it, reading the expected values) is outside
the model: an in-process adapter is trusted not to; an untrusted parser runs behind --cmd.

The readings, one per kind of value:
- None, bool, int, float, str, bytes, Decimal: as they are; a subclass of int, float, str, bytes or Decimal as the value
  it holds, read by the base type (`int.__int__`, `float.__float__`, `str.__str__`, a slice of the bytes, `Decimal()`),
  past any method of its own; a bytearray or memoryview as the bytes it holds; each such copy made once in a reading.
- Any other integer type (numbers.Integral: numpy's integers) as an int, through `operator.index` (`int()` when it has
  no `__index__`).
- Any other binary floating type (numbers.Real that is not Rational: numpy's float16, float32, float64, longdouble) as
  the float of its value, through `float()`: compared as a value, not as the text it prints (W0's leftovers, 2g). A
  registered type without `__float__` is its text.
- datetime, date, timedelta, and their subclasses, as plain ones built from the fields they hold; a `datetime.timezone`
  built again from the offset and the name it holds; a timezone of the adapter's own as the fixed offset it gives for
  that datetime.
- A list or a tuple as a list or a tuple of plain values: an exact one walked as it is; a subclass through its own
  iteration and by what it holds, which must agree (an answer's records in any order).
- A record, a dict or any other mapping, as a plain dict of text keys (`record`): a dict by what it holds; any other
  mapping through `keys()` and `[]`; a dict subclass both ways, which must agree. Its face is read first and what it
  holds last, so a container that fills itself when first read is judged full; a face that hands back the very
  objects it holds is read once.
- Any other container through one face: iteration for an answer's records or a writer's lines, `keys()` and `[]` for
  a record. Storage is compared with that face only for a dict, list or tuple subclass; every other container, a deque
  or UserList subclass among them, is graded by the face the runner reads, and its other faces (a mapping's `items()`
  or `get()`, a list's `[]` or `len()`) are not graded (the owner's ruling on the third reading of the boundary).
- A transparent proxy, which is no subclass of what it wraps but says it is one through `__class__` (wrapt's
  ObjectProxy, lazy-object-proxy): where nothing above reads it, `isinstance()` is honoured for a record, an integer
  (any numbers.Integral) and a datetime or date, read through the proxy's own methods, here, inside the guard (the same
  ruling); one that says it is a datetime or a date and whose fields make no instant is a marker text, never its
  `str()`. A proxy is read through its own methods only: what a subclass behind it holds is not compared, a number
  behind it other than an integer is its text, a text key behind it is no key, a text reason behind it is no refusal
  reason, and a text block behind it from `write_tle` is read as an iterable (stated limits, by the owner's ruling,
  D-337). An integer type whose `int()` raises (numpy's timedelta64 in some units) is its text; an int Python will not
  write in decimal (longer than `sys.get_int_max_str_digits()`) is a marker text with a digest.
- Each container is read once at each depth in one reading, and one met again on its own path is a marker text (a
  record that holds its answer, or itself); a deque, a UserList, a dict's view and any subclass of deque, set or
  frozenset through its iteration (FACED), a set's or a keys or items view's in an order of its own (by digest), as a
  list, a dict's own views once for the dict they show; a UserString as the text it holds. A container in a record's own field, a hook's answer that is a container, and a written line
  that is no text travel on as their text (`as_text`, a `Written`, which equals no text but another container's that
  writes the same): Python's writing of what was read, up to FIELD_TEXT characters, else that much and a digest of all
  it holds; each container, and each long text, bytes or Decimal inside one, is written and digested once in a reading.
  Two readings are compared by digest. Each thread reads its own.
- An exception whose __str__ is Python's own (a builtin exception class's), raised or held in a value: Python's words
  when everything they read is plain (`_python_writes`: texts, numbers, classes, exact lists, tuples, dicts, sets and
  deques of them, no part met twice, no deeper than DEPTH); else written from the plain reading of its arguments,
  bounded, the parts Python's writing reads beside them named after them. So an Enum member, an OrderedDict or an
  object of the parser's in its arguments reads as its plain reading (the rule below, for the Enum member), not as
  Python writes it.
- Anything else as the text `str()` gives it, made once in a reading (`_text_of`), when its writing is the parser's
  own or a third-party library's (`_pythons_writing` is False): code the parser brought, as from inside parse(),
  taking as long as it takes. An object whose writing is Python's own (a builtin or standard-library type's, a
  standard-library function's) and that holds any object besides its class, or more than LEAF_BYTES itself
  (`_holds_objects`), is never printed: it is its type's name ("<SimpleNamespace object>"), since that writing may walk
  what it holds as a tree past any budget; one that holds nothing and is small is Python's writing (the owner's ruling
  on the readings of the tenth reading's mend).
- The whole reading of one answer is held to a budget (BUDGET_OBJECTS objects visited, BUDGET_BYTES bytes copied,
  hashed or written); past it the answer is a Problem in words (TOO_LARGE), never a hang, and an iteration of the
  parser's own that never ends is stopped by it.
- A refusal's reason (`_refused`, D-144) counts only as text: a reason that was not a string is no reason.
- `write_tle`'s answer (`lines`) as a str or bytes block, or any other iterable read in full.

A container or a record that shows one thing and holds another has no one answer: it travels on as a `Problem`, which
`runner.as_records` words, never as a raise, since a raise inside the guard is the parser's refusal of the file. The
reading is not meant to raise at all; what the parser's own code raises while it is read here (a `__str__` that raises,
an `__iter__` that exits) is the parser's, as from inside parse().
"""
import builtins
import collections
import datetime as dt
import functools
import gc
import hashlib
import numbers
import operator
import os
import sys
import sysconfig
import threading
import types
import weakref
from collections import Counter, OrderedDict, deque
from collections.abc import ItemsView, Iterable, KeysView, Mapping, ValuesView
from decimal import Decimal

SCALARS = (type(None), bool, int, float, str, bytes, Decimal)
TIMES = (dt.datetime, dt.date, dt.timedelta, dt.timezone)
DEPTH = 32   # a structure nested deeper than any answer is not read further
FIELD_TEXT = 1_000   # the longest text a container in a field is written as; a longer one is cut, with a digest (D-337)
_LIMITS: dict = {}
# The reading's budget, for one answer (a parse() answer, a hook's answer, a writer's answer, an exception, an exit
# code): the objects it visits, and the bytes it copies, hashes or writes. Past either, the answer is a Problem in
# words and the case fails, never a hang (the owner's ruling on the ninth reading of D-337). The largest reading in the
# sixteen published runs and GPKit's, measured on 2026-10-16, visited 467,926 objects (GPKit's) and copied, hashed or
# wrote no bytes; a reading of ten million objects takes a few seconds.
BUDGET_OBJECTS = 10_000_000
BUDGET_BYTES = 1_000_000_000
TOO_LARGE = "was too large or too deeply shared to read (past the reading's budget of {:,} objects or {:,} bytes)"
# A container with one defined face, iteration, that no rule above reads: read through it to plain values, never printed
# (the owner's bounded rule; the owner's ruling on the readings of D-337's tenth-reading mend). Its order is kept,
# but for a set's or a keys or items view's, whose order of iteration is no part of it.
FACED = (deque, set, frozenset, collections.UserList, KeysView, ValuesView, ItemsView)
UNORDERED = (set, frozenset, KeysView, ItemsView)
_VIEWS: tuple = (type({}.keys()), type({}.values()), type({}.items()))   # a dict's own views, each holding only its dict
# An object no rule reads, printed by Python's own writing (a builtin or standard-library type's, or a standard-library
# function's), that holds any object besides its class, or more than LEAF_BYTES itself, is written as its type's name:
# Python's writing may walk what it holds as a tree, a shared part once for each place that holds it, past any budget,
# since it is not the reading's code (the same ruling). The fields a check reads hold numbers, texts and epochs; a
# Fraction there, or a ZoneInfo on Python 3.10 and later, is named, a stated limit.
LEAF_BYTES = 1_000_000
HELD = 64   # objects with no weak reference whose text a reading keeps, the most recently met
READING_PEAK = [0, 0]   # the largest reading so far in this process (objects, bytes), to measure the budget's margin
_LOG2_10 = 3.321928094887362


def int_digits():
    """How many decimal digits an int may have and still be written: Python's own limit
    (sys.get_int_max_str_digits(), PYTHONINTMAXSTRDIGITS), or 4,300 where it sets none (Python before 3.11, or a limit
    of 0, under which writing a huge int would take as long as it is long); no catalog number, counter or count comes
    near it (the eighth reading of D-337)."""
    return getattr(sys, "get_int_max_str_digits", lambda: 0)() or 4300


def _too_big(n):
    """True when n has more decimal digits than int_digits(): decided from its length in bits, and only near the limit
    by comparing with 10 ** limit, made once, and never past a million digits, where an int as long as that is taken
    as too long (the ninth reading of D-337: 10 ** limit under a limit raised to a hundred million took minutes)."""
    digits = int_digits()
    bits = n.bit_length()
    if bits < (digits - 1) * _LOG2_10:
        return False
    if bits > digits * _LOG2_10 + 1 or digits > 1_000_000:
        return True
    if digits not in _LIMITS:
        _LIMITS[digits] = 10 ** digits
    return not -_LIMITS[digits] < n < _LIMITS[digits]
TEXT_ONLY = ("_refused",)   # a refusal's reason is text or it is none (D-144)
# The reading in progress, inside the guard, one per thread: each container the adapter made is read once at each
# depth, its reading kept beside it (so its id is not reused while the reading lasts), and a container met again on
# its own path is a marker text. A record that held its answer, or itself under two keys, was read once per path,
# without end (the fourth and fifth readings of D-337).
_STATE = threading.local()   # each thread its own reading, though the runner starts none


def _readings():
    if not hasattr(_STATE, "stack"):
        _STATE.stack = []
    return _STATE.stack


class _OverBudget(BaseException):
    """The reading has spent its budget: raised by the reading's own code, never from inside the parser's, and caught
    where the reading began."""


def _too_large():
    return TOO_LARGE.format(BUDGET_OBJECTS, BUDGET_BYTES)


def _one_reading(over):
    """A reader the runner calls: the reading starts and ends with the outermost call, which answers over() when the
    reading spends its budget."""
    def wrap(read):
        @functools.wraps(read)
        def reader(*a, **k):
            stack = _readings()
            if stack:
                return read(*a, **k)
            spent = [0, 0]
            stack.append(({}, set(), {}, {}, spent))   # readings, path, texts, digests, spent (objects, bytes)
            try:
                return read(*a, **k)
            except _OverBudget:
                return over()
            finally:
                stack.pop()
                READING_PEAK[0] = max(READING_PEAK[0], spent[0])
                READING_PEAK[1] = max(READING_PEAK[1], spent[1])
        return reader
    return wrap


def _problem():
    return Problem(_too_large())


def _spend(objects=1, nbytes=0):
    """Count what the reading does against its budget (no reading, no count: the runner's own use of _digest)."""
    stack = getattr(_STATE, "stack", None)
    if stack:
        spent = stack[-1][4]
        spent[0] += objects
        spent[1] += nbytes
        if spent[0] > BUDGET_OBJECTS or spent[1] > BUDGET_BYTES:
            raise _OverBudget


def _take(items):
    """The entries of an iterable the parser handed over, each counted: an iteration of the parser's own that never
    ends is stopped by the budget."""
    out = []
    for x in items:
        _spend()
        out.append(x)
    return out


def _once(v, depth, read):
    """A container's reading at one depth, made once in a reading (a reading depends on the depth it starts at, which
    bounds how deep it goes; the fifth reading of D-337); a container on its own path is a marker text, which no
    field's reader takes for a value."""
    memo, path = _readings()[-1][:2]
    key = id(v)
    if key in path:
        return f"<{name(type(v))} that holds itself>"
    if (key, depth) in memo:
        return memo[(key, depth)][1]
    path.add(key)
    try:
        out = read()
    finally:
        path.discard(key)
    memo[(key, depth)] = (v, out)
    return out


class Written(str):
    """A container, or an int Python will not write in decimal, handed on by the guard as its text (as_text, _huge): the
    runner's own type, so that it never equals a parser's own text that spells the same, and its repr says what it was
    (the eighth reading of D-337: [999] in a field read alike with the text "[999]")."""

    kind: str

    def __new__(cls, text, kind):
        self = str.__new__(cls, text)
        self.kind = kind
        return self

    def __eq__(self, other):
        return type(other) is Written and other.kind == self.kind and str.__eq__(self, other)

    def __ne__(self, other):
        return not self.__eq__(other)

    __hash__ = str.__hash__

    def __repr__(self):
        return f"<{self.kind}> {str.__repr__(self)}"


class Problem:
    """What is wrong with an answer or one of its entries, in the words as_records gives it (D-330, D-334, D-337). The
    runner's own type: it is the one thing besides plain values that leaves the guard."""

    __slots__ = ("what",)

    def __init__(self, what):
        self.what = what

    def __repr__(self):
        return f"Problem({self.what!r})"


def name(kind):
    """A class's own name, read past any `__name__` its metaclass makes up."""
    return str.__str__(type.__dict__["__name__"].__get__(kind))


@_one_reading(_problem)
def answer(out):
    """A parse() answer -> a list of plain records (each a dict, or a Problem for an entry that is not one), or a
    Problem when the answer is one value and no list of records."""
    kind = type(out)
    if issubclass(kind, (Mapping, str, bytes, bytearray)) or not issubclass(kind, Iterable):
        return Problem(f"is {name(kind)}, not a list of records (any iterable of records will do)")
    if kind in (list, tuple):
        entries = out
    elif issubclass(kind, (list, tuple)):
        entries = _sequence(out, kind, lambda xs: [_entry(r, 0) for r in xs], records=True)   # compared by what each entry is, not where
        if type(entries) is Problem:
            return entries
    else:
        entries = _take(out)   # a generator's body, an iterator's own reading
    return [_entry(r, i) for i, r in enumerate(entries, 1)]


def _sequence(v, kind, read, records=False):
    """A list or tuple subclass: its own iteration, and what it holds (read last, so a list that fills itself when first
    read is judged full) -> the entries it holds, or a Problem when the two disagree. An answer's records are compared
    in any order, since their order is not graded; any other list in order. Its `[]` and `len()` are not graded."""
    base = list if issubclass(kind, list) else tuple
    own = _take(v)
    held = _take(base.__iter__(v))
    if len(own) == len(held) and all(a is b for a, b in zip(own, held)):
        return held
    shapes = []
    for f in (own, held):
        # each container digested once in the whole reading, not once per list that holds it: a list subclass read at
        # many places, each time digesting afresh all the reading below it, cost the cube of the records (the ninth
        # reading's probe of D-337)
        keys = [_digest(x) for x in read(f)]
        shapes.append(Counter(keys) if records else keys)   # a multiset of digests
    if shapes[0] != shapes[1]:
        return Problem(f"is a {base.__name__} ({name(kind)}) whose own iteration shows other entries than it holds")
    return held


def _entry(r, i):
    kind = type(r)
    if not issubclass(kind, Mapping) and not isinstance(r, Mapping):   # isinstance: a proxy that says it is a record
        return Problem(f"holds {name(kind)} at entry {i}, where every entry must be a record (a mapping)")
    rec = record(r, entry=True)
    if type(rec) is Problem:
        return Problem(f"{rec.what}, at entry {i}")
    return rec


@_one_reading(_problem)
def record(r, depth=0, entry=False):
    """A mapping -> a plain dict of text keys and plain values, or a Problem. A dict is read by what it holds; any other
    mapping through its own `keys()` and `[]`; a dict subclass both ways, what it holds last, and the two must agree: a
    record that holds one value and shows another has no one answer, and fails in words (the owner's ruling on the
    third reading of D-334's mend). Its `items()` and `get()` are not read (the owner's ruling on the third reading of
    the boundary). A key that is a str subclass is the text it holds; a key that is not text is left out, as every key
    the runner does not know is."""
    return _once(r, (depth, entry), lambda: _record(r, depth, entry))


def _record(r, depth, entry):
    kind = type(r)
    if kind is dict:
        _spend(len(r))
        return _fields(list(dict.items(r)), depth, entry)
    shown = [(k, r[k]) for k in _take(r.keys())]
    if not issubclass(kind, dict):
        return _fields(shown, depth, entry)   # no storage of its own to compare with: graded by the face it shows
    held = list(dict.items(r))   # what it holds, read last
    if len(shown) == len(held) and all(a[0] is b[0] and a[1] is b[1] for a, b in zip(shown, held)):
        return _fields(held, depth, entry)   # it shows the very objects it holds: one reading
    a, b = _fields(shown, depth, entry), _fields(held, depth, entry)
    for x in (a, b):
        if type(x) is Problem:
            return x
    if _digest(a) != _digest(b):
        return Problem(f"holds a record ({name(kind)}) whose own keys() and [] show other fields or values than it holds")
    return b


def _fields(items, depth, entry=False):
    out: dict = {}
    for k, v in items:
        if not issubclass(type(k), str):
            continue
        k = str.__str__(k)
        if k in TEXT_ONLY and not issubclass(type(v), str):
            v = None   # a reason that is no text is no reason: bytes, a set or an object's str() is not one
        elif k == "_adapter" and isinstance(v, Mapping):
            # the capability declaration (D-144): its truth value, read here, inside the guard, as the runner read it
            # before D-337 (bool()), and not its text, which made a false object of the adapter's own read as true;
            # taken from the pairs a record is read by, never through `in`, and set on a copy, since the reading of the
            # mapping may be shared (the fifth reading of D-337)
            pairs = list(dict.items(v)) if type(v) is dict else [(x, v[x]) for x in _take(v.keys())]
            truth = next((bool(y) for x, y in pairs if issubclass(type(x), str) and str.__str__(x) == "refusals"), None)
            v = value(v, depth + 1)
            if type(v) is dict and truth is not None:
                v = dict(v, refusals=truth)
        else:
            v = value(v, depth + 1)
        if type(v) is Problem:   # a record inside a field that is wrong in the same way: the entry is
            what = "holds " + v.what[3:] if v.what.startswith("is ") else v.what   # a list in a field, not the answer
            return Problem(f"{what} in its field {k!r}")
        if entry and type(v) in (list, tuple, dict) and k != "_adapter":
            # a container in a record's field travels on as its text, written once (the seventh reading of D-337); a
            # record inside it keeps its containers, which its field's text writes whole
            v = as_text(v)
        if k in out:
            if _digest(out[k]) == _digest(v):
                continue   # the same field listed twice with one value is one field
            return Problem(f"holds the field {k!r} twice in one record, with two values")
        out[k] = v
    return out


def _digest(v, seen=None):
    """A plain value's content as a digest, for comparing two readings: equal contents give equal digests and different
    ones different digests, built without str() of an int (which refuses one of more than 4,300 digits), without float
    equality (NaN is not NaN), and each shared container once, so that a comparison takes time in what a reading holds,
    not in the paths through it (the fifth and sixth readings of D-337: a shared list was keyed, then compared, as a
    tree)."""
    if seen is None:
        stack = _readings()
        seen = stack[-1][3] if stack else {}
    kind = type(v)
    if kind in (dict, list, tuple, str, bytes, Written, Decimal) and id(v) in seen:   # before the length, which a long
        return seen[id(v)][1]   # Decimal pays in its digits (the ninth reading of D-337)
    long = _long(v)
    _spend()
    if kind in (dict, list, tuple):
        if kind is dict:
            body = b"d" + b"".join(sorted(_digest(k, seen) + _digest(x, seen) for k, x in v.items()))
        else:
            body = (b"l" if kind is list else b"t") + b"".join(_digest(x, seen) for x in v)
        out = hashlib.sha256(body).digest()
        seen[id(v)] = (v, out)
        return out
    if kind is bool or v is None:
        body = b"b" + repr(v).encode()
    elif kind is int:
        body = b"i" + format(v, "x").encode()
    elif kind is float:
        body = b"f" + v.hex().encode()
    elif kind is str:
        body = b"s" + v.encode("utf-8", "surrogatepass")
    elif kind is Written:
        body = b"W" + v.kind.encode() + b":" + str.encode(v, "utf-8", "surrogatepass")
    elif kind is bytes:
        body = b"y" + v
    elif kind is Decimal:
        body = b"D" + repr(v.as_tuple()).encode()
    elif kind is Problem:
        body = b"P" + v.what.encode("utf-8", "surrogatepass")
    elif kind is dt.timezone:
        body = b"z" + _digest(dt.timezone.utcoffset(v, None), seen) + _digest(dt.timezone.tzname(v, None), seen)
    elif kind is dt.datetime:
        body = b"T" + v.replace(tzinfo=None).isoformat().encode() + (_digest(v.tzinfo, seen) if v.tzinfo is not None else b"")
    elif kind is dt.date:
        body = b"a" + v.isoformat().encode()
    elif kind is dt.timedelta:
        body = b"e" + repr((v.days, v.seconds, v.microseconds)).encode()
    else:
        body = b"?" + name(kind).encode()
    _spend(0, len(body))
    out = hashlib.sha256(body).digest()
    if long:   # a long text, bytes or Decimal met many times is digested once
        seen[id(v)] = (v, out)
    return out


def _long(v):
    """A text, bytes or Decimal long enough to be written or digested once per reading, by its id."""
    kind = type(v)
    if kind in (str, bytes, Written):
        return len(v) > 1024
    return kind is Decimal and len(v.as_tuple().digits) > 1024


class _Full(Exception):
    """The text being written has reached its length."""


def _write(v, memo):
    """A plain value's text as Python writes it (repr), each container written once, or None when it is longer than
    FIELD_TEXT; a container's text is kept beside it, so one shared by many fields, records or places is written once."""
    kind = type(v)
    if kind in (list, tuple, dict, str, bytes, Written, Decimal) and id(v) in memo:
        return memo[id(v)][1]
    _spend()
    if kind in (list, tuple, dict):
        parts, n = [], 0
        for x in (v.items() if kind is dict else v):
            if kind is dict:
                a, b = _write(x[0], memo), _write(x[1], memo)
                s = None if a is None or b is None else a + ": " + b
            else:
                s = _write(x, memo)
            if s is None:
                break
            parts.append(s)
            n += len(s) + 2
            if n > FIELD_TEXT:
                s = None
                break
        else:
            s = ""
        if s is None:
            out = None
        else:
            body = ", ".join(parts)
            out = "[" + body + "]" if kind is list else "{" + body + "}" if kind is dict else "(" + body + ("," if len(parts) == 1 else "") + ")"
            out = out if len(out) <= FIELD_TEXT else None
        memo[id(v)] = (v, out)
        return out
    if _long(v):
        out = None   # longer than any text it would sit in
        memo[id(v)] = (v, out)
        return out
    out = str.__str__(v) if kind is Written else repr(v)   # the guard's marker as its words, not quoted (the ninth reading)
    _spend(0, len(out))
    return out if len(out) <= FIELD_TEXT else None


def _head(v):
    """The first FIELD_TEXT characters of a plain value's text, walking only as far as they reach."""
    parts, left = [], [FIELD_TEXT]

    def put(s):
        parts.append(s[:left[0]])
        left[0] -= len(s)
        if left[0] <= 0:
            raise _Full

    stack = _readings()
    texts = stack[-1][2] if stack else {}

    def walk(x):
        kind = type(x)
        _spend()
        if kind in (list, tuple, dict):
            put("[" if kind is list else "{" if kind is dict else "(")
            for i, y in enumerate(x.items() if kind is dict else x):
                if i:
                    put(", ")
                if kind is dict:
                    walk(y[0])
                    put(": ")
                    walk(y[1])
                else:
                    walk(y)
            put("]" if kind is list else "}" if kind is dict else ")")
        elif kind in (str, bytes, Written, Decimal) and (("head", id(x)) in texts or _long(x)):
            put(_leaf_head(x))   # a long text, bytes or Decimal: its start, made once, not written whole for every holder
        elif kind is Written:
            put(str.__str__(x)[:left[0] + 1])
        else:
            put(repr(x)[:left[0] + 1])
    try:
        walk(v)
    except _Full:
        pass
    return "".join(parts)


def _leaf_head(x):
    """The start of a long leaf's text, made once per reading: a text's or bytes' from a slice, a Decimal's from its
    whole text (one of ten million digits or more is not written at all)."""
    stack = _readings()
    texts = stack[-1][2] if stack else {}
    key = ("head", id(x))
    if key not in texts:
        start = x[:FIELD_TEXT + 2] if type(x) in (str, bytes, Written) else None
        texts[key] = (x, repr(start)[:FIELD_TEXT + 1] if start is not None else str(x)[:FIELD_TEXT + 1] if len(x.as_tuple().digits) < 10 ** 7 else "Decimal(…)")
    return texts[key][1]


def as_text(v):
    """A container in a field, or in a hook's answer or a written line -> its text, a Written: as Python writes its plain
    reading (repr) when that is at most FIELD_TEXT long, else its first FIELD_TEXT characters and a digest of all it
    holds, so that two values that differ never share a text, nor one with a parser's own text. Each container, and
    each long text, bytes or Decimal in it, is written and digested once in a reading (the seventh and eighth readings
    of D-337)."""
    stack = _readings()
    texts = stack[-1][2] if stack else {}
    key = ("text", id(v))
    if key in texts:
        return texts[key][1]
    whole = _write(v, texts)
    out = Written(whole if whole is not None else (_head(v) + f"… <{article(type(v).__name__)} too long to write out, #{_digest(v).hex()[:32]}>"),
                  type(v).__name__)
    texts[key] = (v, out)
    return out


def article(word):
    """'a list', 'an int'."""
    return ("an " if word[:1].lower() in "aeiou" else "a ") + word


@_one_reading(_problem)
def value(v, depth=0):
    """Any value an adapter returned -> a plain built-in value (see the module's list)."""
    return _value(v, depth)


@_one_reading(_problem)
def hook_answer(v):
    """A hook's answer: its plain value, a container as its text (as_text)."""
    out = _value(v, 0)
    return as_text(out) if type(out) in (list, tuple, dict) else out



def pythons_own(method):
    """True when an exception's __str__ is Python's own, a builtin exception class's (BaseException's, KeyError's,
    OSError's, SyntaxError's, ImportError's, the Unicode errors'), not code of the parser's."""
    owner = getattr(method, "__objclass__", None)
    return (not isinstance(method, types.FunctionType) and isinstance(owner, type) and issubclass(owner, BaseException)
            and owner.__module__ == "builtins")


_NOT_WRITTEN = {"args", "__traceback__", "__context__", "__cause__", "__suppress_context__", "__dict__", "__weakref__"}
_GROUP = getattr(builtins, "BaseExceptionGroup", None)   # Python 3.11 and later


def _group(e):
    """True for an exception group whose writing is the builtin group's: by its type, never through its own __class__,
    which is the parser's code (the reading of the tenth reading's mend of D-337)."""
    return _GROUP is not None and issubclass(type(e), _GROUP) and getattr(type(e).__str__, "__objclass__", None) is _GROUP


def _exception_parts(e):
    """What Python's own writing of e reads: its arguments, and the attributes its class's own __str__ may read
    (OSError's filename, SyntaxError's text, an ImportError's msg, a UnicodeError's object), each by name, through the
    builtin class's own descriptor, past any property of the parser's."""
    args = BaseException.__dict__["args"].__get__(e)
    if _group(e):   # "message (N sub-exceptions)": its own message member, and the exceptions it holds only counted
        return [("message", (_GROUP.__dict__["message"].__get__(e),))]
    parts = [("args", args)]
    for cls in getattr(type(e).__str__, "__objclass__", BaseException).__mro__:
        if cls is BaseException or cls is object:
            break
        for key, d in vars(cls).items():
            if key not in _NOT_WRITTEN and isinstance(d, (types.MemberDescriptorType, types.GetSetDescriptorType)):
                try:
                    parts.append((key, d.__get__(e)))
                except AttributeError:   # OSError's characters_written, unset
                    pass
    return parts


def _python_writes(x, seen, depth=0):
    """True when Python's own writing of x walks nothing but plain values (texts, numbers, bytes, Decimals, classes, and
    exact lists, tuples, dicts, sets, frozensets and deques of them), meets no part twice and goes no deeper than DEPTH:
    then it writes each part once, and costs what it writes."""
    _spend()
    kind = type(x)
    if kind in (type(None), bool, float, str, bytes, Decimal, type):
        return True
    if kind is int:
        return not _too_big(x)
    if kind in (list, tuple, dict, set, frozenset, deque) and depth <= DEPTH and id(x) not in seen:
        seen.add(id(x))
        held = [z for pair in dict.items(x) for z in pair] if kind is dict else x
        return all(_python_writes(y, seen, depth + 1) for y in held)
    return False   # an object of the parser's, a subclass, a part met twice or a cycle, a structure deeper than DEPTH


def _exception_words(e, depth):
    """An exception whose __str__ is Python's own -> its text: Python's own words when what that writing reads is plain
    (_python_writes), so the words are Python's (decimal.InvalidOperation's list of conditions, OSError's "[Errno 2]");
    else written from the plain reading of its arguments, a container as its bounded text (as_text), a huge int as its
    marker, never by walking what the parser handed it. So an argument that is an Enum member, an OrderedDict or an
    object of the parser's reads as its plain reading ({'a': 1} for the OrderedDict; _text_of's rule for the others),
    not as Python writes it (<Mode.A: 1>, OrderedDict(...)); and an OSError or SyntaxError whose parts are not plain is
    written as its arguments (the seventh, eighth and ninth readings of D-337)."""
    seen: set = set()
    named = _exception_parts(e)
    if all(_python_writes(x, seen) for _, x in named):
        return str.__str__(str(e))
    if _group(e):   # its message from the plain reading, and how many it holds, as Python writes a group
        held = len(_GROUP.__dict__["exceptions"].__get__(e))
        return _arguments_text(_value(named[0][1], depth + 1), False) + f" ({held} sub-exception{'' if held == 1 else 's'})"
    args = BaseException.__dict__["args"].__get__(e)
    text = _arguments_text(_value(args, depth + 1), type(e).__str__ is KeyError.__str__)
    # an attribute Python's own writing reads beside the arguments (OSError's filename, which it takes out of them),
    # named after them when it holds anything they do not; a group's exceptions are its arguments already
    more = [(key, _value(x, depth + 1)) for key, x in named[1:] if x is not None
            and not any(x is a or (type(x) in (int, str) and type(a) is type(x) and x == a) for a in args)]
    return text + "".join(f"; {key}: {_arguments_text((x,), True)}" for key, x in more)


def _arguments_text(parts, quoted):
    """An exception's arguments, as their plain reading, the way BaseException writes them; one argument's text, cut at
    FIELD_TEXT with a digest of the whole, so that exceptions held one inside another, each text quoting the next, cost
    what they hold (the tenth reading of D-337: a chain of OSErrors grew fourfold at each level)."""
    if type(parts) is str:
        return parts   # the guard's marker for arguments deeper than it reads, or a container that holds itself
    if type(parts) is not tuple:
        return "(its message could not be read)"
    if not parts:
        return ""
    if len(parts) > 1:
        return as_text(parts)
    one = parts[0]
    if type(one) in (list, tuple, dict):
        return as_text(one)
    text = str.__str__(one) if type(one) is Written else repr(one) if quoted else str(one)
    _spend(0, len(text))
    return text if len(text) <= FIELD_TEXT else text[:FIELD_TEXT] + f"… <a text of {len(text):,} characters, #{_digest(text).hex()[:32]}>"


@_one_reading(_too_large)
def exception_text(e):
    """The text of an exception whose __str__ is Python's own (pythons_own), read inside the guard: see _exception_words.
    Past the reading's budget, the budget's words."""
    return _exception_words(e, 0)

def _huge(n):
    """An int Python will not write in decimal -> a marker text with a digest, so that nothing downstream raises in the
    parser's name when it writes the value (the seventh reading of D-337)."""
    return Written(f"<an integer of {len(format(n, 'x'))} hex digits, too long to write in decimal, #{_digest(n).hex()[:32]}>", "int")


def _value(v, depth):
    kind = type(v)
    _spend()
    if kind is int and _too_big(v):
        return _huge(v)
    if kind in SCALARS:
        return v
    if kind is dt.timezone:
        return _tz(v)
    if depth > DEPTH:
        return f"<{name(kind)} nested more than {DEPTH} levels deep>"
    if issubclass(kind, bool):
        return bool(v)   # unreachable: bool cannot be subclassed
    if issubclass(kind, int):
        n = int.__int__(v)
        return _huge(n) if _too_big(n) else n
    if issubclass(kind, float):
        return float.__float__(v)
    if issubclass(kind, str):
        return _leaf(v, lambda: str.__str__(v), lambda: str.__len__(v))
    if issubclass(kind, bytes):   # the bytes it holds, past any __bytes__ of its own
        return _leaf(v, lambda: bytes.__getitem__(v, slice(None)), lambda: bytes.__len__(v))
    if issubclass(kind, bytearray):
        return _leaf(v, lambda: bytes(bytearray.__getitem__(v, slice(None))), lambda: bytearray.__len__(v))
    if kind is memoryview:
        return _leaf(v, v.tobytes, lambda: v.nbytes)
    if issubclass(kind, Decimal):
        return _leaf(v, lambda: Decimal(v), lambda: len(Decimal.as_tuple(v).digits))
    if issubclass(kind, TIMES):
        return _time(v)
    if issubclass(kind, (list, tuple)):
        return _once(v, depth, lambda: _sequence_value(v, kind, depth))
    if issubclass(kind, Mapping):
        return record(v, depth + 1)
    if issubclass(kind, numbers.Integral):
        n = _integer(v, kind)
        if n is not None:
            return value(n, depth + 1)
    elif issubclass(kind, numbers.Real) and not issubclass(kind, numbers.Rational) and hasattr(kind, "__float__"):
        return value(float(v), depth + 1)
    if kind in _VIEWS:
        # a dict's own view: read once in a reading for the dict it shows, however many views of it the records hold
        return _once(gc.get_referents(v)[0], (kind.__name__, depth), lambda: _iterated(v, depth))
    if issubclass(kind, FACED):
        # a subclass of deque, set or frozenset, a UserList, any other view: read through its face, never printed
        return _once(v, depth, lambda: _iterated(v, depth))
    if issubclass(kind, collections.UserString):
        # its face is the text it holds (the standard library's own __str__: str() of what it holds), read as a text
        return _value(collections.UserString.__str__(v), depth + 1)
    if issubclass(kind, BaseException) and pythons_own(kind.__str__):
        # an exception held in a value: its words, bounded as a raised one's are, made once in a reading, and one that
        # holds itself a marker (the tenth reading of D-337)
        return _once(v, depth, lambda: _exception_words(v, depth))
    return _proxy(v, depth)


def _leaf(v, plain, size):
    """A subclass of str, bytes or Decimal, a bytearray or a memoryview -> the plain value it holds, copied once in a
    reading however many fields or containers hold it (the ninth reading of D-337: a long numpy.str_ held by many was
    copied for each, and every copy kept)."""
    memo = _readings()[-1][0]
    key = ("leaf", id(v))
    if key not in memo:
        _spend(1, size())
        memo[key] = (v, plain())
    return memo[key][1]


def _sequence_value(v, kind, depth):
    read = lambda xs: [value(x, depth + 1) for x in xs]   # noqa: E731
    items = v if kind in (list, tuple) else _sequence(v, kind, read)
    if type(items) is Problem:
        return items
    plain = read(items)
    wrong = next((x for x in plain if type(x) is Problem), None)
    if wrong is not None:
        return wrong
    return tuple(plain) if issubclass(kind, tuple) else plain


def _proxy(v, depth):
    """What no reading above took: a transparent proxy's record, integer (any numbers.Integral, numpy's among them),
    datetime or date, which `isinstance()` sees through the proxy's `__class__`, read through the proxy's own methods;
    anything else as its text. A proxy that says it is a datetime or a date is never its text: fields that make no
    instant are a marker no epoch reader takes (the fourth reading of D-337: wrong fields beside a right `__str__`)."""
    if isinstance(v, Mapping):
        return record(v, depth + 1)
    if isinstance(v, bool):
        return bool(v)
    if isinstance(v, numbers.Integral):
        n = _integer(v, type(v), v.__class__)
        if n is not None:
            return value(n, depth + 1)
    if isinstance(v, dt.date):
        when = _time_through(v, depth)
        return when if when is not None else f"<{name(type(v))} whose fields make no instant>"
    return _text_of(v, depth)


_STDLIB = frozenset(getattr(sys, "stdlib_module_names", ()))
_STDLIB_PATH = os.path.realpath(sysconfig.get_paths()["stdlib"])


_STDLIB_SEEN: dict = {}


def _from_stdlib(module):
    """True when a module is the standard library's: by Python's own list (3.10 and later), else by where its file sits
    (3.9, decided once for each module), never a package installed beside it."""
    if type(module) is not str:
        return False
    if _STDLIB:
        return module.partition(".")[0] in _STDLIB
    if module not in _STDLIB_SEEN:
        loaded = sys.modules.get(module)
        where = getattr(loaded, "__file__", None)
        where = os.path.realpath(where) if type(where) is str else ""
        _STDLIB_SEEN[module] = (module.partition(".")[0] in sys.builtin_module_names   # compiled into the interpreter
                                or getattr(getattr(loaded, "__spec__", None), "origin", None) in ("built-in", "frozen")
                                or where.startswith(_STDLIB_PATH + os.sep) and "-packages" not in where)
    return _STDLIB_SEEN[module]


def _pythons_writing(how):
    """True when an object's writing (its type's __str__, or __repr__ where __str__ is object's) is Python's own: a
    function of the standard library's, or a method of a builtin or standard-library type. A third-party library's
    writing, compiled or not (lxml's elements, numpy's), and the parser's own, are code the parser brought, as from
    inside parse() (the last reading of D-337: lxml.objectify's compiled __str__ was taken as Python's, and an OMM
    value it reads became a type's name)."""
    if isinstance(how, types.FunctionType):
        return _from_stdlib(getattr(how, "__module__", None))
    owner = getattr(how, "__objclass__", None)
    if not isinstance(owner, type):
        return False
    module = getattr(owner, "__module__", None)
    return module == "builtins" or _from_stdlib(module)


def _holds_objects(v, kind):
    """True when an object holds any object besides its own class (gc.get_referents), or more than LEAF_BYTES itself:
    Python's writing of it may then walk what it holds. Whether a part holds nothing further is not asked, since gc does
    not show all that a writing reads (a datetime's time zone, a proxy's referent), and a part of few bytes can take
    long to write (a long int); the reading of the last reading's fix found a hang through each (D-337). So a Fraction
    or an IP address is its type's name, and a ZoneInfo on Python 3.10 and later, stated limits; on 3.9 gc shows a
    ZoneInfo holding nothing, and its key is Python's writing of it."""
    return any(x is not kind for x in gc.get_referents(v)) or _own_size(kind, v) > LEAF_BYTES


def _text_of(v, depth):
    """str() of an object no rule above reads, made once in a reading: kept through a weak reference, or, for a type with
    none (a dict view, a slice), among the last HELD such objects, so one object shared by every record is written once
    and nothing made afresh for each read is kept alive. A writing that is the parser's own or a third-party
    library's, compiled or not (_pythons_writing is False: lxml's elements, numpy's arrays and scalars), is code the
    parser brought, as from inside parse(), taking as long as it takes. Python's own writing (a builtin or
    standard-library type's, a standard-library function's) of an object that holds any object besides its class, or
    more than LEAF_BYTES itself (_holds_objects), is never called: such an object is written as its type's name (a
    SimpleNamespace, a slice, an Enum member, a UUID, a Fraction, a ZoneInfo on 3.10 and later, a Path), since that
    writing may walk what it holds as a tree, past any budget (the owner's ruling on the readings of D-337's
    tenth-reading mend). One that holds nothing and is small (a complex, a range, a small array, a ZoneInfo on 3.9) is
    written by Python as before. A container with a face is read through it (FACED); a Fraction, or a ZoneInfo on 3.10
    and later, in a field a check reads is named, a stated limit. An object whose own code changes what it holds while
    it is read is written as first met, a stated limit."""
    stack = _readings()
    texts = stack[-1][2] if stack else {}
    held = texts.setdefault(("held texts",), (None, OrderedDict()))[1]
    key = ("text of", id(v))
    kept = texts.get(key)
    if kept is not None and kept[0]() is v:
        _spend()
        return kept[1]
    if id(v) in held and held[id(v)][0] is v:
        _spend()
        held.move_to_end(id(v))
        return held[id(v)][1]
    kind = type(v)
    how = kind.__str__ if kind.__str__ is not object.__str__ else kind.__repr__
    if how is not object.__repr__ and _pythons_writing(how) and _holds_objects(v, kind):
        text = f"<{name(kind)} object>"
        _spend()
    else:
        text = str.__str__(str(v))
        _spend(0, len(text))
    try:
        texts[key] = (weakref.ref(v), text)
    except TypeError:
        held[id(v)] = (v, text)
        if len(held) > HELD:
            held.popitem(last=False)
    return text


def _own_size(kind, v):
    """What an object holds itself, in bytes, by its type's own __sizeof__, never one written in Python (the parser's)."""
    return 0 if isinstance(kind.__sizeof__, types.FunctionType) else sys.getsizeof(v)


def _iterated(v, depth):
    """A container read through its one face, iteration, as a list of plain values: in its order, but a set's, a
    frozenset's or a keys or items view's sorted by digest, since its order of iteration is no part of it and two equal
    sets need not share it (the seventh reading of D-337)."""
    plain = [value(x, depth + 1) for x in v]
    wrong = next((x for x in plain if type(x) is Problem), None)
    if wrong is not None:
        return wrong
    if issubclass(type(v), UNORDERED):
        plain.sort(key=_digest)
    return plain


def _integer(v, *kinds):
    """A numbers.Integral's int: through `operator.index` where every type it shows has `__index__`, then `int()`; None
    when neither gives one, raising TypeError or OverflowError or absent (numpy's timedelta64), and it is then its
    text, as a registered Real without `__float__` is (the fifth and sixth readings of D-337)."""
    ways = ([operator.index] if all(hasattr(k, "__index__") for k in kinds) else []) + ([int] if hasattr(kinds[0], "__int__") else [])
    for way in ways:
        try:
            return way(v)
        except (TypeError, OverflowError):
            continue
    return None


def _time_through(v, depth):
    """A proxy's datetime or date, built from the fields its own attributes give, each read as a plain int, and a
    datetime's offset from its own utcoffset() as a fixed one; None when they do not make one."""
    fields = ("year", "month", "day") + (("hour", "minute", "second", "microsecond", "fold") if isinstance(v, dt.datetime) else ())
    got = [value(getattr(v, n), depth + 1) for n in fields]
    if any(type(x) is not int for x in got):
        return None
    try:
        if len(got) == 3:
            return dt.date(*got)
        plain = dt.datetime(*got[:7], fold=got[7])
    except (ValueError, OverflowError):
        return None
    off = v.utcoffset()
    if off is None:
        return plain
    off = value(off, depth + 1)
    if type(off) is not dt.timedelta or not -dt.timedelta(days=1) < off < dt.timedelta(days=1):
        return None
    return plain.replace(tzinfo=dt.timezone(off))


@_one_reading(_problem)
def lines(out):
    """write_tle's answer -> a str or bytes block as it is, or the lines of any other iterable, read in full here; the
    writer case's own reading (writer.normalise_lines) then takes them as it always has."""
    kind = type(out)
    if issubclass(kind, (str, bytes, bytearray)) or kind is memoryview or not issubclass(kind, Iterable):
        return value(out)
    if issubclass(kind, Mapping):
        out = value(out)
        return as_text(out) if type(out) is dict else out
    if issubclass(kind, (list, tuple)):
        lines = value(out)
        if type(lines) is Problem:
            return lines
    else:
        lines = [value(x, 1) for x in out]   # a generator, an iterator, a map: its own reading
    wrong = next((x for x in lines if type(x) is Problem), None)
    if wrong is not None:
        return wrong
    texts = [as_text(x) if type(x) in (list, tuple, dict) else x for x in lines]   # a line that is no text, as its text
    return tuple(texts) if type(lines) is tuple else texts


def _time(v):
    """A datetime, date or timedelta, or a subclass, built again from the fields it holds, read by the base type's own
    descriptors, so that no strftime(), astimezone() or property of a subclass decides what the epoch is."""
    if issubclass(type(v), dt.timedelta):
        return dt.timedelta(days=dt.timedelta.days.__get__(v), seconds=dt.timedelta.seconds.__get__(v),
                            microseconds=dt.timedelta.microseconds.__get__(v))
    if issubclass(type(v), dt.timezone):
        return v   # unreachable: timezone cannot be subclassed
    y, m, d = dt.date.year.__get__(v), dt.date.month.__get__(v), dt.date.day.__get__(v)
    if not issubclass(type(v), dt.datetime):
        return dt.date(y, m, d)
    tz = dt.datetime.tzinfo.__get__(v)
    plain = dt.datetime(y, m, d, dt.datetime.hour.__get__(v), dt.datetime.minute.__get__(v),
                        dt.datetime.second.__get__(v), dt.datetime.microsecond.__get__(v),
                        fold=dt.datetime.fold.__get__(v))
    if tz is None:
        return plain
    if type(tz) is dt.timezone:
        return plain.replace(tzinfo=_tz(tz))
    # a timezone of the adapter's own: the offset it gives for this datetime, asked here, inside the guard
    off = dt.datetime.utcoffset(v)
    if off is None:
        return plain
    return plain.replace(tzinfo=dt.timezone(_time(off)))


def _tz(tz):
    """A datetime.timezone holds the offset and the name it was built with, which may be a timedelta or a str subclass of
    the adapter's own: built again from the values they hold."""
    off = _time(dt.timezone.utcoffset(tz, None))
    text = str.__str__(dt.timezone.tzname(tz, None))
    bare = dt.timezone(off)
    return bare if text == dt.timezone.tzname(bare, None) else dt.timezone(off, text)


def is_plain(x, depth=0, seen=None):
    """True when x holds nothing but plain built-in values and the runner's own Problem: what may leave the guard. A
    shared container is looked at once (the fifth reading of D-337)."""
    if type(x) in (list, tuple, dict):
        seen = {} if seen is None else seen
        if id(x) in seen:
            return seen[id(x)]
        seen[id(x)] = True   # a plain reading holds no cycle: a container met again while it is looked at is plain
        seen[id(x)] = out = _is_plain(x, depth, seen)
        return out
    return _is_plain(x, depth, seen)


def _is_plain(x, depth, seen):
    kind = type(x)
    if kind in SCALARS or kind in (dt.datetime, dt.date, dt.timedelta, dt.timezone, Problem, Written):
        tz = x if kind is dt.timezone else x.tzinfo if kind is dt.datetime else None
        if tz is not None:   # a timezone holds an offset and a name, which must be plain too
            return (type(tz) is dt.timezone and type(dt.timezone.utcoffset(tz, None)) is dt.timedelta
                    and type(dt.timezone.tzname(tz, None)) is str)
        return True
    if depth > 2 * DEPTH + 4:   # a container read at one depth may sit at another in the reading it is shared by
        return False
    if kind in (list, tuple):
        return all(is_plain(y, depth + 1, seen) for y in x)
    if kind is dict:
        return all(type(k) is str and is_plain(y, depth + 1, seen) for k, y in x.items())
    return False
