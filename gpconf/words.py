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
