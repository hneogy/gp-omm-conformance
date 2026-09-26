// Presets `tle.js` and `tle.js-api` (tested with 5.0.3): tle.js as-is through the runner's command protocol. Each
// element set (name line optional) is handed as one string to the library's public getters; the harness only splits
// the file into sets, which the library leaves to the caller. Raw bytes on stdin, JSON records on stdout, exit 3 for
// formats the library has no reader for. Second argument: 'fields' (preset tle.js; the epoch rebuilt from
// getEpochYear() and getEpochDay(), the raw field values) or 'api' (preset tle.js-api; the epoch from
// getEpochTimestamp(), the library's millisecond Unix time). Moved into the package from the corpus's hand run
// (D-139), its parsing unchanged (D-153, D-154).
// gpconf runs this file as `node --input-type=module --eval <this source> -- <arguments>` from the working directory,
// so the library resolves as it would for a script in the user's project; a file outside the project could not import
// it (D-154). GPCONF_NODE_MODULE, set by `--module PATH`, names the library's entry file instead.
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const target = process.env.GPCONF_NODE_MODULE;
const T = await import(target ? pathToFileURL(target).href : 'tle.js');
const [fmt, mode = 'fields'] = process.argv.slice(1);
if (fmt !== 'tle' && fmt !== '2le') process.exit(3);
const lines = readFileSync(0, 'utf8').split(/\r?\n/);
const num = (v) => (Number.isNaN(v) ? 'NaN' : v);   // JSON has no NaN; the runner then reports the string and its type
function isoFromFields(yy, day) {
  const year = yy < 57 ? yy + 2000 : yy + 1900;      // the pivot as the corpus states it; the library's own pivot is tested through the vectors
  let doy = Math.floor(day); let us = Math.round((day - doy) * 86400e6);
  if (us >= 86400e6) { us -= 86400e6; doy += 1; }
  const p = (n, w) => String(n).padStart(w, '0');
  return `${year}-${p(doy, 3)}T${p(Math.floor(us / 3600e6), 2)}:${p(Math.floor((us % 3600e6) / 60e6), 2)}:${p(Math.floor((us % 60e6) / 1e6), 2)}.${p(us % 1e6, 6)}`;
}
const out = [];
for (let i = 0; i + 1 < lines.length; i++) {
  if (!lines[i].startsWith('1 ') || !lines[i + 1].startsWith('2 ')) continue;
  const hasName = i > 0 && lines[i - 1].trim() !== '' && !lines[i - 1].startsWith('1 ') && !lines[i - 1].startsWith('2 ');
  const tle = (hasName ? lines[i - 1] + '\n' : '') + lines[i] + '\n' + lines[i + 1];
  try {
    const rec = {
      norad_cat_id: num(T.getCatalogNumber(tle)), _catalog_number_line2: num(T.getCatalogNumber2(tle)), _catalog_field: lines[i].substr(2, 5),
      object_name: hasName ? T.getSatelliteName(tle) : null, _cospar: T.getCOSPAR(tle), classification: T.getClassification(tle),
      epoch: mode === 'fields' ? isoFromFields(T.getEpochYear(tle), T.getEpochDay(tle)) : new Date(T.getEpochTimestamp(tle)).toISOString(),
      _epoch_timestamp_ms: num(T.getEpochTimestamp(tle)),
      mean_motion: T.getMeanMotion(tle), eccentricity: T.getEccentricity(tle), inclination: T.getInclination(tle),
      ra_of_asc_node: T.getRightAscension(tle), arg_of_pericenter: T.getPerigee(tle), mean_anomaly: T.getMeanAnomaly(tle),
      bstar: T.getBstarDrag(tle), mean_motion_dot: T.getFirstTimeDerivative(tle), mean_motion_ddot: T.getSecondTimeDerivative(tle),
      rev_at_epoch: T.getRevNumberAtEpoch(tle), element_set_no: T.getTleSetNumber(tle), ephemeris_type: T.getOrbitModel(tle),
      _is_valid_tle: T.isValidTLE(tle),
    };
    out.push(rec);
  } catch (e) { process.stderr.write(`set at line ${i + 1}: ${e.message}\n`); }
  i += 1;
}
T.clearTLEParseCache();
process.stdout.write(JSON.stringify(out));
