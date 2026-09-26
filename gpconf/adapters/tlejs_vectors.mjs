// Vector hooks for the tle.js presets (tested with 5.0.3): each op goes through the library's public getters on a
// valid line pair (the ISS baseline set of the corpus) with the one field substituted, checksums recomputed with the
// library's own computeChecksum(). Protocol: {op, input} on stdin -> {result} | {error}. Moved into the package from
// the corpus's hand run (D-139), unchanged but for how it finds the library (D-154).
// gpconf runs this file as `node --input-type=module --eval <this source> -- <arguments>` from the working directory,
// so the library resolves as it would for a script in the user's project; a file outside the project could not import
// it (D-154). GPCONF_NODE_MODULE, set by `--module PATH`, names the library's entry file instead.
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const target = process.env.GPCONF_NODE_MODULE;
const T = await import(target ? pathToFileURL(target).href : 'tle.js');
const L1 = '1 25544U 98067A   26263.52959654  .00008422  00000+0  15975-3 0  9997';
const L2 = '2 25544  51.6355 213.4302 0003462 300.5590  59.5075 15.49866287 66880';
const withChecksum = (l) => l.slice(0, 68) + String(T.computeChecksum(l));
const { op, input } = JSON.parse(readFileSync(0, 'utf8'));
let r;
try {
  if (op === 'alpha5_decode') {
    const f = String(input).padStart(5, ' ').slice(0, 5);
    const tle = withChecksum(L1.slice(0, 2) + f + L1.slice(7)) + '\n' + withChecksum(L2.slice(0, 2) + f + L2.slice(7));
    const v = T.getCatalogNumber(tle);
    r = { result: Number.isNaN(v) ? 'NaN' : v };
  } else if (op === 'two_digit_year') {
    const yy = String(input).padStart(2, '0');
    const tle = withChecksum(L1.slice(0, 18) + yy + L1.slice(20)) + '\n' + L2;
    r = { result: new Date(T.getEpochTimestamp(tle)).getUTCFullYear() };
  } else if (op === 'alpha5_encode') {
    r = { error: 'tle.js has no TLE writer' };
  } else if (op === 'parse_epoch' || op === 'parse_catalog_id') {
    r = { error: 'tle.js reads TLE lines only; it has no OMM (CSV/JSON/XML/KVN) epoch or catalog-id parser' };
  } else r = { error: `unknown op ${op}` };
} catch (e) { r = { error: `${e.name}: ${e.message}` }; }
process.stdout.write(JSON.stringify(r));
