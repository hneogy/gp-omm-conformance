# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""D-468: one place for the suite's wall-clock limits.

The limits catch hangs: work that grew with the square of its input took minutes where it now takes a second or two.
On a shared runner, and under coverage's tracer (several times slower), an ordinary run passed some of them by a few
tenths of a second or missed them by as much (the public nightly failed on every night from 2026-11-01 to 2026-11-10 on
these limits alone). A limit here is the measured bound times a factor: 4 while a tracer or coverage is running, times
GPCONF_TIME_SCALE (a number of at least 1, default 1) when it is set. A hang of minutes still fails every one of them."""
import os
import sys

TRACED_FACTOR = 4.0


def traced():
    """True while a tracer (coverage's, a debugger's) or coverage itself is running in this process."""
    return sys.gettrace() is not None or "coverage" in sys.modules


def scale():
    raw = os.environ.get("GPCONF_TIME_SCALE", "")
    try:
        value = float(raw) if raw else 1.0
    except ValueError:
        value = 1.0
    if not value >= 1.0:   # also refuses NaN: a limit is never made tighter than the measured bound
        value = 1.0
    return value * (TRACED_FACTOR if traced() else 1.0)


def budget(seconds):
    """The wall-clock limit for work measured to finish within `seconds` on an ordinary run."""
    return seconds * scale()
