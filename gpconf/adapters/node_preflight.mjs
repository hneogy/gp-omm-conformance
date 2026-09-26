// Preflight for a Node preset (D-153, D-154): can the working directory import the library? Run by gpconf as
// `node --input-type=module --eval <this source> -- <package>` before any case, so that a missing Node library is a
// setup error, never a parse failure charged to the library. Prints one JSON object: ok, node, entry, version, error.
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const [name] = process.argv.slice(1);
const target = process.env.GPCONF_NODE_MODULE;
const out = { ok: false, node: process.versions.node };
try {
  await import(target ? pathToFileURL(target).href : name);
  let entry = target || null;
  if (!entry) {
    try { entry = fileURLToPath(import.meta.resolve(name)); } catch { entry = null; }
  }
  out.entry = entry;
  // the version: the nearest package.json above the entry that names the library (a maintainer's checkout included)
  for (let d = entry ? dirname(entry) : null; d && d !== dirname(d); d = dirname(d)) {
    const p = join(d, 'package.json');
    if (!existsSync(p)) continue;
    const pj = JSON.parse(readFileSync(p, 'utf8'));
    if (pj.name === name) { out.version = pj.version; break; }
  }
  out.ok = true;
} catch (e) {
  out.error = `${e.code || e.name}: ${e.message}`.slice(0, 300);
}
process.stdout.write(JSON.stringify(out));
