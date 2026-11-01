# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""
gpconf/words.py -- number agreement for the text the runner prints (D-239). Standard library only.

A count joined to a fixed phrase reads wrongly for one: "1 need fetched data", or a plural hedged with a bracketed
s. Every count the runner, the fetch and the reports print with a noun or a verb goes through these two functions, so
that one reads as one and every other number, zero included, as a plural.

    qty(1, "record")              -> "1 record"
    qty(0, "record")              -> "0 records"
    qty(2, "entry", "entries")    -> "2 entries"
    pick(1, "needs", "need")      -> "needs"
    pick(3, "it", "them")         -> "them"
"""


def pick(n, singular, plural):
    """The form of a word that agrees with the count: `singular` for exactly one, `plural` for any other number."""
    return singular if n == 1 else plural


def qty(n, singular, plural=None):
    """The count followed by its noun, agreeing in number. The plural is the singular with an s unless given."""
    return f"{n} {pick(n, singular, plural if plural is not None else singular + 's')}"


_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


# the line and paragraph separators Python's splitlines() breaks at, and the bidirectional controls that reorder what a
# terminal shows: escaped with the control characters (the reading of D-369)
_SHOWN_ESCAPED = {0x2028, 0x2029, *range(0x202A, 0x202F), *range(0x2066, 0x206A)}


def _hidden(c):
    o = ord(c)
    return o < 32 or 127 <= o < 160 or o in _SHOWN_ESCAPED


def printable(text):
    """Text a parser or a written file controls, as the printed report shows it: each control character (C0, DEL, C1),
    line or paragraph separator and bidirectional control escaped, a line break as \\n, so that no such text can start
    a line of its own, forge a report line, reorder what is shown or move the terminal's cursor (D-369; the blind
    review's finding 7). The JSON reports carry the text as it was."""
    text = str(text)
    if not any(_hidden(c) for c in text):
        return text
    return "".join(_ESCAPES.get(c) or ((f"\\x{ord(c):02x}" if ord(c) < 256 else f"\\u{ord(c):04x}") if _hidden(c) else c) for c in text)
