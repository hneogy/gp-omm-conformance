# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The pytest wiring (D-434). Run under pytest 9.2.0 on 2026-11-11 against gpconf 0.9.0's candidate (D-475); core.py,
which holds the logic, is tested by gpconf's suite.

    pytest --gpconf-cmd "./my-adapter {fmt}" --gpconf-case alpha5-tle-derived --gpconf-case corrupt-input

adds one test per chosen case (every case when none is chosen), named `gpconf[CASE]`, which passes, fails with the
failing items, or skips with gpconf's reason."""
import pytest

from .core import FAIL, SKIP, GpconfRun


def pytest_addoption(parser):
    g = parser.getgroup("gpconf", "gpconf conformance cases")
    g.addoption("--gpconf-preset", help="a gpconf preset (gpconf presets lists them)")
    g.addoption("--gpconf-adapter", help="module:Class, as gpconf run --adapter")
    g.addoption("--gpconf-cmd", help="a command, as gpconf run --cmd ('{fmt}' is replaced)")
    g.addoption("--gpconf-vectors-cmd", help="as gpconf run --vectors-cmd")
    g.addoption("--gpconf-write-cmd", help="as gpconf run --write-cmd")
    g.addoption("--gpconf-root", help="a corpus checkout, as gpconf run --root")
    g.addoption("--gpconf-case", action="append", default=[], help="a case to run (repeat); default every case")


def _run(config):
    o = config.option
    if not (o.gpconf_preset or o.gpconf_adapter or o.gpconf_cmd):
        return None
    if not hasattr(config, "_gpconf_run"):
        config._gpconf_run = GpconfRun(preset=o.gpconf_preset, adapter=o.gpconf_adapter, cmd=o.gpconf_cmd,
                                       vectors_cmd=o.gpconf_vectors_cmd, write_cmd=o.gpconf_write_cmd,
                                       root=o.gpconf_root, cases=o.gpconf_case)
    return config._gpconf_run


class GpconfItem(pytest.Item):
    def __init__(self, *, case, **kw):
        super().__init__(**kw)
        self.case = case

    def runtest(self):
        r = _run(self.config).results().get(self.case)
        if r is None:
            pytest.fail(f"gpconf reported no result for {self.case}")
        if r.outcome == SKIP:
            pytest.skip(f"gpconf: {r.status}: {r.message}")
        if r.outcome == FAIL:
            raise GpconfFailure(r)

    def repr_failure(self, excinfo):
        if isinstance(excinfo.value, GpconfFailure):
            return f"gpconf case {self.case} failed:\n{excinfo.value.result.message}"
        return super().repr_failure(excinfo)

    def reportinfo(self):
        return self.path, 0, f"gpconf[{self.case}]"


class GpconfFailure(Exception):
    def __init__(self, result):
        super().__init__(result.message)
        self.result = result


class GpconfCollector(pytest.Collector):
    def collect(self):
        run = _run(self.config)
        for case in run.results():
            yield GpconfItem.from_parent(self, name=f"gpconf[{case}]", case=case)


def pytest_collection_modifyitems(session, config, items):
    if _run(config) is None:
        return
    collector = GpconfCollector.from_parent(session, name="gpconf")
    items.extend(collector.collect())
