// Preset `satellite.js` (tested with 7.1.0): satellite.js as-is through the runner's command protocol. Raw bytes on
// stdin, a JSON array of records on stdout, exit 3 for a format the library has no reader for. twoline2satrec for
// tle and 2le, json2satrec for json; csv, xml and kvn are unsupported. Moved into the package from the corpus's
// hand run (D-132), its parsing unchanged.
// gpconf runs this file as `node --input-type=module --eval <this source> -- <arguments>` from the working directory,
// so the library resolves as it would for a script in the user's project; a file outside the project could not import
// it (D-154). GPCONF_NODE_MODULE, set by `--module PATH`, names the library's entry file instead.
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const target = process.env.GPCONF_NODE_MODULE;
const { twoline2satrec, json2satrec } = await import(target ? pathToFileURL(target).href : 'satellite.js');

const [fmt] = process.argv.slice(1);
const XPDOTP = 1440.0 / (2.0 * Math.PI);   // satellite.js constants.xpdotp
const RAD2DEG = 180.0 / Math.PI;

function isoEpoch(epochyr, epochdays) {
  // the library's own pivot (io.js line 102); day-of-year form with microseconds, from the double the library kept
  const year = epochyr < 57 ? epochyr + 2000 : epochyr + 1900;
  let doy = Math.floor(epochdays);
  let us = Math.round((epochdays - doy) * 86400e6);
  if (us >= 86400e6) { us -= 86400e6; doy += 1; }
  const h = Math.floor(us / 3600e6), m = Math.floor((us % 3600e6) / 60e6), s = Math.floor((us % 60e6) / 1e6), f = us % 1e6;
  const p = (n, w) => String(n).padStart(w, '0');
  return `${year}-${p(doy, 3)}T${p(h, 2)}:${p(m, 2)}:${p(s, 2)}.${p(f, 6)}`;
}

function record(s, name) {
  const raw = s.satnum;                       // a string in this library, never decoded
  // digits -> int (what any consumer must do); anything else (an Alpha-5 field) is passed through as the string the
  // library returns, and the runner reports the value and its type (corpus D-131)
  const id = /^\s*\d+\s*$/.test(raw) ? Number(raw) : raw;
  const mm = s.nokozai ?? s.no_kozai ?? s.no; // the Kozai mean motion as parsed, if the library keeps it apart
  return {
    norad_cat_id: id,
    _catalog_field: raw,
    object_name: name || null,
    epoch: isoEpoch(s.epochyr, s.epochdays),
    mean_motion: mm * XPDOTP,
    eccentricity: s.ecco,
    inclination: s.inclo * RAD2DEG,
    ra_of_asc_node: s.nodeo * RAD2DEG,
    arg_of_pericenter: s.argpo * RAD2DEG,
    mean_anomaly: s.mo * RAD2DEG,
    bstar: s.bstar,
    mean_motion_dot: s.ndot * XPDOTP * 1440.0,
    mean_motion_ddot: s.nddot * XPDOTP * 1440.0 * 1440.0,
    _mm_field: s.nokozai !== undefined ? 'nokozai' : (s.no_kozai !== undefined ? 'no_kozai' : 'no'),
  };
}

const raw = readFileSync(0, 'utf8');
const out = [];
if (fmt === 'tle' || fmt === '2le') {
  const lines = raw.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (l.startsWith('1 ') && i + 1 < lines.length && lines[i + 1].startsWith('2 ')) {
      const name = i > 0 && !/^[12] /.test(lines[i - 1]) ? lines[i - 1].trim() : '';
      try { out.push(record(twoline2satrec(l, lines[i + 1]), name)); }
      catch (e) { process.stderr.write(`satellite.js refused line ${i + 1}: ${e && e.message}\n`); }
    }
  }
} else if (fmt === 'json') {
  let data;
  try { data = JSON.parse(raw); } catch (e) { process.stderr.write(`not JSON: ${e.message}\n`); process.exit(1); }
  for (const obj of Array.isArray(data) ? data : [data]) {
    try { out.push(record(json2satrec(obj), obj.OBJECT_NAME)); }
    catch (e) { process.stderr.write(`satellite.js refused record ${obj && obj.NORAD_CAT_ID}: ${e && e.message}\n`); }
  }
} else {
  process.exit(3);
}
// NaN and Infinity have no JSON form: JSON.stringify writes null, which the runner reads as "absent"; say so on stderr
for (const r of out) for (const [k, v] of Object.entries(r)) if (typeof v === 'number' && !Number.isFinite(v)) process.stderr.write(`non-finite ${k} for ${r.norad_cat_id}: ${v} -> null\n`);
process.stdout.write(JSON.stringify(out));
