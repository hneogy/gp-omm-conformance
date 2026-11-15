# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 NEOGY LLC
"""The results schema (0.9.0 item d2, D-431): the shape of `gpconf run --json`'s report as a JSON Schema
(gpconf/schemas/results-1.0.schema.json, draft 2020-12), and a small validator for it, standard library only.

The validator reads the keywords the schema uses and no others: type, enum, const, required, properties,
additionalProperties, items, minimum, pattern and local $ref. Any JSON Schema validator reads the same file; this one
is here so that gpconf needs nothing installed to check its own reports.

    python3 -m gpconf.schema report.json     # exit 0 when the report matches, 1 with the first faults otherwise"""
import json
import os
import re
import sys

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schemas", "results-1.0.schema.json")
KNOWN = {"$schema", "$id", "$defs", "$ref", "title", "description", "type", "enum", "const", "required", "properties",
         "additionalProperties", "items", "minimum", "pattern"}
TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def load_schema(path=SCHEMA_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _is(value, t):
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, TYPES[t])


def errors(value, schema, root=None, where="$"):
    """-> a list of faults, empty when value matches schema."""
    root = schema if root is None else root
    unknown = set(schema) - KNOWN
    if unknown:
        raise ValueError(f"{where}: the validator does not read {sorted(unknown)}")
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/"):
            raise ValueError(f"{where}: only local references are read, not {ref!r}")
        target = root
        for part in ref[2:].split("/"):
            target = target[part]
        return errors(value, target, root, where)
    out = []
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is(value, t) for t in types):
            return [f"{where}: {type(value).__name__} where {' or '.join(types)} is expected"]
    if "enum" in schema and value not in schema["enum"]:
        out.append(f"{where}: {value!r} is not one of {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        out.append(f"{where}: {value!r} is not {schema['const']!r}")
    if "minimum" in schema and _is(value, "number") and value < schema["minimum"]:
        out.append(f"{where}: {value!r} is below {schema['minimum']}")
    if "pattern" in schema and isinstance(value, str) and not re.search(schema["pattern"], value):
        out.append(f"{where}: {value!r} does not match {schema['pattern']}")
    if isinstance(value, dict):
        for k in schema.get("required", []):
            if k not in value:
                out.append(f"{where}: {k!r} is missing")
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for k, v in value.items():
            if k in props:
                out += errors(v, props[k], root, f"{where}.{k}")
            elif extra is False:
                out.append(f"{where}: {k!r} is not allowed")
            elif isinstance(extra, dict):
                out += errors(v, extra, root, f"{where}.{k}")
    if isinstance(value, list) and "items" in schema:
        for i, v in enumerate(value):
            out += errors(v, schema["items"], root, f"{where}[{i}]")
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python3 -m gpconf.schema REPORT.json", file=sys.stderr)
        return 2
    with open(argv[0], encoding="utf-8") as f:
        report = json.load(f)
    faults = errors(report, load_schema())
    for e in faults[:20]:
        print(e)
    from .words import qty
    print(f"{argv[0]}: " + ("matches results schema 1.0" if not faults else f"{qty(len(faults), 'fault')} against results schema 1.0"))
    return 1 if faults else 0


if __name__ == "__main__":
    sys.exit(main())
