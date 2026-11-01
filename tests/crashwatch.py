# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The suite's crash detector carried into a Python a test starts with an environment of its own (D-355).

tools/run_suite.py watches every Python the suite starts that inherits its environment; a test that sets PYTHONPATH,
or builds its environment from nothing (the installed-layout test), ran its Python unwatched. `watched(env)` adds the
check's sitecustomize folder and crash folder to that environment where the check runs the suite, and changes nothing
where it does not: the sitecustomize imports only the standard library, so an environment kept bare stays bare."""
import os


def watched(env):
    site, crash = os.environ.get("GPCONF_CRASH_SITE"), os.environ.get("GPCONF_CRASH_DIR")
    if not (site and crash):
        return env
    env = dict(env)
    env["PYTHONPATH"] = site + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["GPCONF_CRASH_DIR"] = crash
    return env
