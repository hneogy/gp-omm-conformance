"""A command adapter for D-398's tests: the reference's answer, with a key written twice in the JSON it prints.
argv: MODE FMT. Parse modes: parse-ok; parse-twice (the first record's norad_cat_id written again as 99999);
parse-same (every record's norad_cat_id written again with its own value). Vector modes: vec-ok; vec-twice (every
answer with a key twice, two values); vec-invalidtwice (only rejections: {"error": R, "result": 0}, exit 0);
vec-nztwice (rejections as {"error": R, "error": R} and exit 1, a rejection by its exit code)."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from gpconf.adapters.reference import Parser  # noqa: E402
mode = sys.argv[1]
data = sys.stdin.buffer.read()
iso = lambda v: v.isoformat() if hasattr(v, "isoformat") else str(v)
if mode.startswith("vec"):
    q = json.loads(data)
    try:
        r = getattr(Parser(), q["op"])(q["input"])
    except Exception as e:
        reason = json.dumps(str(e))
        if mode == "vec-nztwice":
            print('{"error": %s, "error": %s}' % (reason, reason)); sys.exit(1)
        if mode in ("vec-twice", "vec-invalidtwice"):
            print('{"error": %s, "result": 0, "error": null}' % reason); sys.exit(0)
        print('{"error": %s}' % reason); sys.exit(0)
    out = json.dumps({"result": r}, default=iso)
    if mode == "vec-twice":
        out = out[:-1] + ', "result": 0}'
    print(out)
    sys.exit(0)
recs = Parser().parse(data, sys.argv[2])
text = json.dumps(recs, default=str)
if mode == "parse-twice":
    i = text.find('"norad_cat_id"')
    if i > 0:
        j = text.index(",", i)
        text = text[:j] + ', "norad_cat_id": 99999' + text[j:]
elif mode == "parse-same":
    text = re.sub(r'("norad_cat_id": ("[^"]*"|[^,}]*))', r'\1, \1', text)
print(text)
