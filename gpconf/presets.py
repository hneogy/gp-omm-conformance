"""Presets: `gpconf run --preset NAME` runs a shipped adapter with no adapter written (D-151).

Each preset names the adapter module, the library it exposes, the version it was tested against and, for a
preset that needs a third-party library, the pip requirement and the optional extra the package will declare
for it. The extras are recorded here and are not yet in pyproject.toml, which v0.3.0's packaging stage writes;
until then the install hint names the library's own pip package. The report prints the version found beside the
version tested, because a count is a result against that version, not a verdict on the project.

Standard library only: a third-party library is imported only when its preset is run.
"""
import importlib

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
}


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


def load(name):
    """-> (parser, info). info adds 'name', 'found' (the installed version, or None) and 'label' for the report."""
    if name not in PRESETS:
        raise PresetUnavailable(f"no preset {name!r}; the presets are: {', '.join(PRESETS)} (gpconf presets lists them)")
    spec = dict(PRESETS[name], name=name)
    try:
        module = importlib.import_module(spec["module"])
    except ImportError as e:
        if spec.get("requires"):
            raise PresetUnavailable(f"preset {name!r} needs {spec['library']}, which is not installed: "
                                    f"pip install {spec['requires']}") from e
        raise
    parser = getattr(module, "Parser")()
    spec["found"] = found_version(spec.get("distribution"))
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


def listing():
    """Lines for `gpconf presets`."""
    out = []
    for name, spec in PRESETS.items():
        if spec.get("library"):
            found = found_version(spec.get("distribution"))
            state = f"{spec['library']} {found} installed" if found else f"{spec['library']} not installed: pip install {spec['requires']}"
            out.append(f"{name:10s} {spec['what']}; tested with {spec['library']} {spec['tested_with']}; {state}")
        else:
            out.append(f"{name:10s} {spec['what']}; standard library only")
    return out
