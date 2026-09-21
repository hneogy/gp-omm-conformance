#!/usr/bin/env python3
"""tools/validate_xml.py -- validate every raw XML fixture against the vendored SANA schema sets.
Writes tools/_out/xml-validation.json. Run with the project venv (needs xmlschema)."""
import glob
import json
import os
import sys

import xmlschema

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETS = {
    "ndmxml-2.0.0 (OMM 2.0, what CelesTrak declares)": os.path.join(ROOT, "schemas", "ndmxml-2.0.0", "ndmxml-2.0.0-master-2.0.xsd"),
    "ndmxml-4.0.0 (OMM 3.0, current CCSDS 505.0-B-3)": os.path.join(ROOT, "schemas", "ndmxml-4.0.0", "ndmxml-4.0.0-master-4.0.xsd"),
}


def main():
    results = {}
    schemas = {}
    for label, path in SETS.items():
        try:
            schemas[label] = xmlschema.XMLSchema(path)
        except Exception as e:
            print(f"SCHEMA LOAD FAILED {label}: {e}")
            schemas[label] = None
    files = sorted(glob.glob(os.path.join(ROOT, "fixtures", "*", "raw", "*.xml")))
    for f in files:
        rel = os.path.relpath(f, ROOT)
        results[rel] = {}
        for label, schema in schemas.items():
            if schema is None:
                results[rel][label] = {"valid": None, "errors": ["schema failed to load"]}
                continue
            errs = []
            try:
                for err in schema.iter_errors(f):
                    errs.append(str(err).splitlines()[0][:300])
                    if len(errs) >= 5:
                        break
            except Exception as e:
                errs = [f"validator exception: {e}"]
            results[rel][label] = {"valid": not errs, "errors": errs}
            print(f"{rel} | {label} | {'VALID' if not errs else 'INVALID'}" + (f" | {errs[0]}" if errs else ""))
    os.makedirs(os.path.join(ROOT, "tools", "_out"), exist_ok=True)
    json.dump(results, open(os.path.join(ROOT, "tools", "_out", "xml-validation.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
