# Migrating a GP-data reader past 99999, by failure mode

gpconf's cases find these failures in real libraries; this page gives the smallest fix for each. The README's
[migration in one page](../README.md#the-migration-in-one-page) says what changed and why.

## The recommended path

1. **Read OMM** (CSV, JSON, XML or KVN) where you can. `NORAD_CAT_ID` is an integer of up to nine digits there, and
   CelesTrak serves every object in these formats. CelesTrak emits no Alpha-5 TLE at all: a TLE request for an object
   numbered above 99999 answers HTTP 404, `No GP data found`.
2. **Hold catalog numbers as integers** everywhere inside your program, whatever format they came in.
3. **Decode Alpha-5 only if you read Space-Track TLEs**, the one source that writes it, and decode it strictly.
4. **Write TLEs only where something downstream needs them**, with Alpha-5 from 100000 and a refusal above 339999.

Each section names the gpconf case that checks it. To check your parser:

```bash
pip install gpconf
gpconf fetch                               # once: 46 requests to CelesTrak under its usage policy
gpconf run --adapter mypkg.adapter:Parser   # or --cmd "your-program {fmt}"; see docs/ADAPTERS.md
```

## 1. The catalog number in a fixed-width field or a narrow type

Cases: `alpha5-tle-derived`, `six-digit-omm-saramago`, `nine-digit-supgp-launch-nominals` and the catalog-id vectors (`vectors/norad-cat-id-text.json`).

The TLE's catalog field is five characters; OMM's `NORAD_CAT_ID` is not. Code that slices five characters out of an
OMM value, pads to five, or stores the number in a 16-bit integer (at most 32767, or 65535 unsigned) loses objects. A
signed 32-bit integer holds every nine-digit number (up to 999,999,999) and is enough; a five-character string is not.

```python
# before: the number kept as the TLE's five characters
catnum = line1[2:7]                       # "A0000" stays a string; an OMM's 799501621 has no TLE form at all
# after: an integer from any source
catnum = alpha5_to_int(line1[2:7])        # TLE (see section 3)
catnum = int(record["NORAD_CAT_ID"])      # OMM: CSV, JSON, XML, KVN
```

## 2. An empty OBJECT_ID (or OBJECT_NAME)

Cases: `analyst-objects` and `csv-json-omitted-mandatory-fields`.

CelesTrak's analyst objects (80000 to 89999) carry an empty `OBJECT_ID` in every format, and some carry the name
`UNKNOWN`. Python's ElementTree returns `None` for an empty XML element; other readers raise on a missing key.

```python
# before
intl = record["OBJECT_ID"].strip()        # KeyError, or AttributeError on None
# after
intl = (record.get("OBJECT_ID") or "").strip() or None   # empty is legitimate: keep the record
```

## 3. An Alpha-5 letter rejected, or read as zero

Cases: `alpha5-tle-derived`, `alpha5-encoding-vectors`, `corrupt-input` (an invalid field must be refused).

From 100000 the TLE field's first character is a letter: A=10 to Z=33, skipping I and O, so `A0000` is 100000 and
`Z9999` is 339999. `int()` raises on it; a lenient reader returns 0 or the digits alone. Decode it strictly, and
refuse what is not a field:

```python
LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"     # 24 letters: no I, no O
DIGITS = "0123456789"                     # ASCII only: str.isdigit() also takes full-width and other digits

def alpha5_to_int(field):
    if len(field) != 5 or not all(c in DIGITS for c in field[1:]):
        raise ValueError(f"not a catalog field: {field!r}")
    if field[0] in DIGITS:
        return int(field)
    if field[0] not in LETTERS:           # lowercase, I, O, anything else
        raise ValueError(f"not an Alpha-5 letter: {field!r}")
    return (LETTERS.index(field[0]) + 10) * 10000 + int(field[1:])
```

A five-digit field may carry leading blanks in old element sets; strip them before the check if your sources do.
Writing the field is the reverse, and a number above 339999 (or below 0) is refused, never truncated: case
`tle-writer-alpha5`.

## 4. The epoch truncated or read in one form only

Cases: `alpha5-encoding-vectors` (its `ccsds-epoch-strings` vectors) and `kvn-syntax-variants`.

CelesTrak writes six decimal places of the second; CCSDS also allows the day-of-year form (`2026-140T08:56:33`), no
fraction, and a trailing `Z`. Reading the epoch through a type with millisecond precision, or through one fixed
`strptime` pattern, loses microseconds or refuses valid files. Second 60 is valid only at the 27 leap seconds,
1972-06-30 to 2016-12-31.

```python
# before: milliseconds, one pattern
epoch = datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%f")   # refuses "2026-140T08:56:33" and a trailing "Z"
# after: every CCSDS form, to the microsecond, and nothing else
import re
from datetime import datetime, timedelta

EPOCH = re.compile(r"([0-9]{4})-(?:([0-9]{2})-([0-9]{2})|([0-9]{3}))T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]+))?Z?")

def parse_epoch(text):
    m = EPOCH.fullmatch(text)
    if not m:
        raise ValueError(f"not a CCSDS epoch: {text!r}")
    year, month, mday, yday, h, mi, sec, frac = m.groups()
    if yday:                                               # YYYY-DDD
        day = datetime(int(year), 1, 1) + timedelta(days=int(yday) - 1)
        if not 1 <= int(yday) or day.year != int(year):    # day 366 of a year that has 365 is refused
            raise ValueError(f"no such day: {text!r}")
    else:
        day = datetime(int(year), int(month), int(mday))
    micro = int((frac or "").ljust(6, "0")[:6])            # six digits kept; more are cut, so round first if you need to
    return day.replace(hour=int(h), minute=int(mi), second=int(sec), microsecond=micro)
```

This sketch takes no second 60; a reader that must keep a leap second needs a type that can hold one.

## 5. A TLE request that answers 404 read as "no new data"

Case: `tle-omits-six-digit-objects`.

A TLE request for a group of recent launches answers HTTP 404 with `No GP data found`, because every object in it is
numbered above 99999. Treating that as an outage, or as an empty update, loses every object launched since
2026-07-11. Ask for the same group as OMM.

## Where to go next

- `docs/ADAPTERS.md`: the adapter protocol, every hook and how a failure reads.
- `docs/guides/`: a five-minute guide per language, ending in a green run.
- `docs/ONBOARDING.md`: an adapter in five minutes.
- `docs/LIBRARIES.md`: how the libraries tested so far did, and what was fixed.
