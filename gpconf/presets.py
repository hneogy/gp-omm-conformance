"""Presets: `gpconf run --preset NAME` runs a shipped adapter with no adapter written (D-151).

Each preset names the adapter module, the library it exposes, the version it was tested against and, for a
preset that needs a third-party library, the pip requirement and the optional extra the package will declare
for it. The extras are recorded here and are not yet in pyproject.toml, which v0.3.0's packaging stage writes;
until then the install hint names the library's own pip package. The report prints the version found beside the
version tested, because a count is a result against that version, not a verdict on the project.

The Node presets (D-154) run a harness shipped in gpconf/adapters/ through `node --input-type=module --eval`, from the
working directory, so the library resolves as it would for a script in the user's project; `--module PATH` names its
entry file instead. Before any case runs, a preflight checks that Node exists and the library imports; a preset that
cannot run is refused as a setup error (exit 2) that says nothing ran and nothing about the library (D-153).

Standard library only: a third-party library is imported only when its preset is run.
"""
import importlib
import json
import os
import shutil
import subprocess

PRESETS = {
    "reference": {
        "module": "gpconf.adapters.reference",
        "library": None,
        "what": "the corpus's own readers, the control: passes every case that exercises a parser",
    },
    "naive": {
        "module": "gpconf.adapters.naive",
        "library": None,
        "report_note": "a demonstration of failure, not a parser anyone should use",
        "what": "a demonstration of failure, not a parser anyone should use: the shortcuts many projects have "
                "(int() on five columns, one epoch format, every column assumed present)",
    },
    "sgp4": {
        "module": "gpconf.adapters.sgp4_adapter",
        "library": "python-sgp4",
        "distribution": "sgp4",
        "requires": "sgp4",
        "extra": "sgp4",
        "tested_with": "2.27",
        "what": "python-sgp4 as-is: TLE via twoline2rv, CSV, XML and JSON via sgp4.omm, TLE writing via export_tle",
    },
    "pyephem": {
        "module": "gpconf.adapters.pyephem_adapter",
        "library": "PyEphem",
        "distribution": "ephem",
        "requires": "ephem",
        "extra": "pyephem",
        "tested_with": "4.2.1",
        "what": "PyEphem as-is: TLE and 2LE via readtle()",
    },
    "satellite.js": {
        "kind": "node",
        "library": "satellite.js",
        "package": "satellite.js",
        "harness": "satellitejs.mjs",
        "args": [],
        "tested_with": "7.1.0",
        "what": "satellite.js as-is: twoline2satrec for TLE and 2LE, json2satrec for OMM JSON",
    },
    "tle.js": {
        "kind": "node",
        "library": "tle.js",
        "package": "tle.js",
        "harness": "tlejs.mjs",
        "args": ["fields"],
        "vectors": "tlejs_vectors.mjs",
        "tested_with": "5.0.3",
        "what": "tle.js as-is, the epoch read from the raw year and day fields (getEpochYear, getEpochDay)",
    },
    "tle.js-api": {
        "kind": "node",
        "library": "tle.js",
        "package": "tle.js",
        "harness": "tlejs.mjs",
        "args": ["api"],
        "vectors": "tlejs_vectors.mjs",
        "tested_with": "5.0.3",
        "what": "tle.js as-is, the epoch through getEpochTimestamp(), which floors it to the millisecond",
    },
}

ADAPTERS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adapters")


class PresetUnavailable(Exception):
    """An unknown preset, or one whose library is not installed."""


def found_version(distribution):
    """The installed version of a distribution, or None."""
    if not distribution:
        return None
    try:
        from importlib.metadata import version, PackageNotFoundError
    except ImportError:  # pragma: no cover
        return None
    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


def setup_error(spec, problem):
    """A preset that cannot run is not a result: the message says so (D-153)."""
    return PresetUnavailable(f"setup: preset {spec['name']!r} {problem}. Nothing was run; this says nothing about {spec['library']}.")


def load(name, module=None, cwd=None):
    """-> (parser, info). info adds 'name', 'found' (the installed version, or None) and 'label' for the report.
    module and cwd apply to the Node presets: the library's entry file, and the folder the library resolves from."""
    if name not in PRESETS:
        raise PresetUnavailable(f"no preset {name!r}; the presets are: {', '.join(PRESETS)} (gpconf presets lists them)")
    spec = dict(PRESETS[name], name=name)
    if module and spec.get("kind") != "node":
        raise PresetUnavailable(f"--module applies to the Node presets ({', '.join(n for n, p in PRESETS.items() if p.get('kind') == 'node')}), not to {name!r}")
    if spec.get("kind") == "node":
        return _load_node(spec, module, cwd or os.getcwd())
    try:
        mod = importlib.import_module(spec["module"])
    except ImportError as e:
        if spec.get("requires"):
            raise setup_error(spec, f"needs {spec['library']}, which is not installed: pip install {spec['requires']}") from e
        raise
    parser = getattr(mod, "Parser")()
    spec["found"] = found_version(spec.get("distribution"))
    spec["label"] = label(spec)
    return parser, spec


def _harness(file):
    with open(os.path.join(ADAPTERS, file), encoding="utf-8") as f:
        return f.read()


def node_command(node, file, args=()):
    """The argument list that runs a shipped harness from the working directory (tested on 2026-09-26: a harness file
    outside the user's project cannot import the library, code passed to --eval resolves from the working directory)."""
    return [node, "--input-type=module", "--eval", _harness(file), "--", *args]


def preflight(spec, module=None, cwd=None, node=None):
    """-> the preflight's answer as a dict (ok, node, entry, version, error); Node itself missing gives ok False."""
    node = node or shutil.which("node")
    if not node:
        return {"ok": False, "error": "Node.js was not found on PATH", "no_node": True}
    env = dict(os.environ)
    if module:
        env["GPCONF_NODE_MODULE"] = os.path.abspath(module)
    try:
        p = subprocess.run(node_command(node, "node_preflight.mjs", [spec["package"]]), capture_output=True, timeout=60,
                           cwd=cwd or os.getcwd(), env=env)
        return json.loads(p.stdout.decode("utf-8") or "{}") if p.returncode == 0 else {"ok": False, "error": p.stderr.decode("utf-8", "replace")[-300:]}
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _load_node(spec, module, cwd):
    from .runner import CommandParser
    node = shutil.which("node")
    if not node:
        raise setup_error(spec, "needs Node.js, which was not found on PATH")
    pre = preflight(spec, module, cwd, node)
    if not pre.get("ok"):
        where = f"the file named by --module ({module})" if module else cwd
        raise setup_error(spec, f"could not import {spec['library']} from {where}: {pre.get('error')}; install it there "
                                f"with `npm install {spec['package']}`, or name its entry file with --module")
    env = dict(os.environ)
    if module:
        env["GPCONF_NODE_MODULE"] = os.path.abspath(module)
    vectors = node_command(node, spec["vectors"]) if spec.get("vectors") else None
    parser = CommandParser(node_command(node, spec["harness"], ["{fmt}", *spec["args"]]), vectors, cwd=cwd, env=env)
    spec["found"] = pre.get("version")
    spec["runtime"] = f"Node {pre.get('node')}"
    spec["label"] = label(spec)
    return parser, spec


def label(spec):
    """How the report names the parser: the preset, and for a library the version found and the version tested."""
    if not spec.get("library"):
        return f"preset {spec['name']}" + (f" ({spec['report_note']})" if spec.get("report_note") else "")
    found, tested = spec.get("found"), spec.get("tested_with")
    if found == tested:
        return f"preset {spec['name']} ({spec['library']} {found}, the version it was tested with)"
    return (f"preset {spec['name']} ({spec['library']} {found or 'version unknown'} found; "
            f"the preset was tested with {tested}, so results may differ from the published ones)")


def listing(cwd=None):
    """Lines for `gpconf presets`. A Node preset's state is what its preflight finds from the working directory."""
    out = []
    checked = {}
    for name, spec in PRESETS.items():
        if spec.get("kind") == "node":
            if spec["package"] not in checked:
                checked[spec["package"]] = preflight(dict(spec, name=name), cwd=cwd)
            pre = checked[spec["package"]]
            if pre.get("ok"):
                state = f"{spec['library']} {pre.get('version') or '(version unknown)'} importable here, Node {pre.get('node')}"
            elif pre.get("no_node"):
                state = "Node.js not found on PATH"
            else:
                state = f"{spec['library']} not importable from this directory: npm install {spec['package']}"
            out.append(f"{name:12s} {spec['what']}; tested with {spec['library']} {spec['tested_with']}; {state}")
        elif spec.get("library"):
            found = found_version(spec.get("distribution"))
            state = f"{spec['library']} {found} installed" if found else f"{spec['library']} not installed: pip install {spec['requires']}"
            out.append(f"{name:12s} {spec['what']}; tested with {spec['library']} {spec['tested_with']}; {state}")
        else:
            out.append(f"{name:12s} {spec['what']}; standard library only")
    return out
