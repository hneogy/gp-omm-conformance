// Harness: drives gods-eye-view's satellites layer ingestion (src/layers/satellites/ingestion.js on main) with a
// corpus file as the one CelesTrak group that answers, using the layer's own parseTLE and its real twoline2satrec /
// Number(satrec.satnum) / dedupe path; Cesium is a stand-in and propagation is stubbed so that a decayed or old epoch
// cannot hide a parse result. Prints the resulting catalog as JSON records for the runner (--cmd protocol).
import { readFileSync } from 'node:fs';
import { createIngestion } from './main/src/layers/satellites/ingestion.js';
import { createOrbits } from './main/src/layers/satellites/orbits.js';
const fmt = process.argv[2];
if (fmt !== 'tle' && fmt !== '2le') process.exit(3);
const text = readFileSync(0, 'utf8');
console.log = (...a) => process.stderr.write(a.join(' ') + '\n');   // the layer logs with console.log; stdout is the JSON
const XPDOTP = 1440.0 / (2.0 * Math.PI), RAD2DEG = 180 / Math.PI;
const layerState = {
  _trackingRefreshEpoch: 0, _activeUpdateControllers: new Set(), _lastError: null,
  _pointCollection: { removeAll() {}, add(o) { return o; } }, _points: new Map(), _orbitPaths: new Map(), _catalog: new Map(),
  _detectionObjects: new Map(), _denseIds: [], _denseCursor: 0, _denseLoadController: null, _denseLoadToken: 0,
  _params: { showOrbits: false, catalog: 'core' }, _count: 0, _catalogRevision: 0, _lastUpdate: 0, _lastPropagation: 0,
};
const parts = {};
const services = {};
const source = { async readGroup(path) { return path === 'stations' ? { ok: true, text } : { ok: false, text: '' }; } };
parts.orbits = createOrbits({ state: layerState, services, parts, source });
parts.orbits.propagatePosition = () => ({ longitude: 0, latitude: 0, altitude: 400000, speedMps: 7600 });  // stub: never skip on propagation
parts.controls = { _pointStyleFor: () => ({ pixelSize: 1, color: null, outlineColor: null, outlineWidth: 0 }) };
parts.rendering = { _showOrbitPath() {} };
parts.labels = { _syncIssOverlay() {} };
parts.catalog = { _loadDenseCatalog: async () => ({ status: 'not-requested' }) };
parts.tracking = { _reconcileTrackedSubjectContext: async () => {}, _applyPendingTrackingRestore() {} };
const ingestion = createIngestion({ state: layerState, services, parts, source }).methods;  // the factory returns { methods }
await ingestion.update({ scene: { primitives: { remove() {} } } });
function isoEpoch(epochyr, epochdays) {
  const year = epochyr < 57 ? epochyr + 2000 : epochyr + 1900;
  let doy = Math.floor(epochdays); let us = Math.round((epochdays - doy) * 86400e6);
  if (us >= 86400e6) { us -= 86400e6; doy += 1; }
  const p = (n, w) => String(n).padStart(w, '0');
  return `${year}-${p(doy, 3)}T${p(Math.floor(us / 3600e6), 2)}:${p(Math.floor((us % 3600e6) / 60e6), 2)}:${p(Math.floor((us % 60e6) / 1e6), 2)}.${p(us % 1e6, 6)}`;
}
const out = [];
for (const [key, entry] of layerState._catalog) {
  const s = entry.satrec;
  out.push({
    norad_cat_id: Number.isFinite(key) ? key : null, _app_key: Number.isNaN(key) ? 'NaN' : key, _catalog_field: s.satnum,
    object_name: entry.name || null, epoch: isoEpoch(s.epochyr, s.epochdays),
    mean_motion: s.no * XPDOTP, eccentricity: s.ecco, inclination: s.inclo * RAD2DEG, ra_of_asc_node: s.nodeo * RAD2DEG,
    arg_of_pericenter: s.argpo * RAD2DEG, mean_anomaly: s.mo * RAD2DEG, bstar: s.bstar,
    mean_motion_dot: s.ndot, mean_motion_ddot: s.nddot,   // satellite.js 6.0.2 keeps both derivatives as printed (its unit conversion is commented out)
  });
}
process.stderr.write(`catalog entries: ${layerState._catalog.size}; outcome: ${JSON.stringify(layerState._lastTrackingRefreshOutcome)}\n`);
process.stdout.write(JSON.stringify(out));
