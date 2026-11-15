#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
// A gpconf adapter template for a parser in JavaScript, run by command:
//
//     python3 -m gpconf run --cmd "node templates/node/adapter.mjs {fmt}"
//
// gpconf writes one file to standard input and reads a JSON array of records from standard output (docs/ADAPTERS.md,
// "The command protocol"). Replace toyParse with a call to your library; keep the rest. The toy parser reads TLE only
// and is here so the template runs as it stands; it is not a parser to use. Same toy as templates/python/adapter.py.
import { readFileSync } from "node:fs";

const ALPHA5 = "ABCDEFGHJKLMNPQRSTUVWXYZ"; // I and O are skipped
const isDigits = (s) => /^[0-9]+$/.test(s);

function alpha5(field) {
  if (field.length !== 5 || !isDigits(field.slice(1))) throw new Error(`invalid catalog field ${JSON.stringify(field)}`);
  const c = field[0];
  if (isDigits(c)) return Number(field);
  const k = ALPHA5.indexOf(c);
  if (k < 0) throw new Error(`invalid catalog field ${JSON.stringify(field)}`);
  return (k + 10) * 10000 + Number(field.slice(1));
}

function checksum(line) {
  let s = 0;
  for (const c of line.slice(0, 68)) s += isDigits(c) ? Number(c) : c === "-" ? 1 : 0;
  return s % 10;
}

// ' 12345-3' -> '0.12345e-3' as text, so gpconf compares it exactly
function exponent(field) {
  let f = field.trim();
  const sign = f.startsWith("-") ? "-" : "";
  f = f.replace(/^[+-]/, "");
  return `${sign}0.${f.slice(0, 5)}e${f.slice(5)}`;
}

// 'DDD.DDDDDDDD' -> 'YYYY-MM-DDThh:mm:ss.ffffff'; eight decimals of a day are whole microseconds (1e-8 day = 864 us)
function epochText(year, day) {
  if (day.length !== 12 || day[3] !== "." || !isDigits(day.slice(0, 3) + day.slice(4))) {
    throw new Error(`epoch day ${JSON.stringify(day)} is not DDD.DDDDDDDD`);
  }
  const us = BigInt(Number(day.slice(0, 3)) - 1) * 86400000000n + BigInt(day.slice(4)) * 864n;
  const ms = Number(us / 1000n);
  const t = new Date(Date.UTC(year, 0, 1) + ms);
  if (year < 100) t.setUTCFullYear(year); // Date.UTC reads 0-99 as 1900-1999
  const p = (n, w) => String(n).padStart(w, "0");
  return `${p(t.getUTCFullYear(), 4)}-${p(t.getUTCMonth() + 1, 2)}-${p(t.getUTCDate(), 2)}T${p(t.getUTCHours(), 2)}:` +
    `${p(t.getUTCMinutes(), 2)}:${p(t.getUTCSeconds(), 2)}.${p(Number(us % 1000000n), 6)}`;
}

function record(name, l1, l2) {
  if (l1.length !== 69 || l2.length !== 69) throw new Error(`line lengths ${l1.length}/${l2.length}, not 69`);
  if (l1[68] !== String(checksum(l1)) || l2[68] !== String(checksum(l2))) throw new Error("checksum");
  if (l1.slice(2, 7) !== l2.slice(2, 7)) throw new Error("line 2's catalog number is not line 1's");
  if (!isDigits(l1.slice(18, 20))) throw new Error(`epoch year ${JSON.stringify(l1.slice(18, 20))} is not two digits`);
  const yy = Number(l1.slice(18, 20));
  return {
    norad_cat_id: alpha5(l1.slice(2, 7)),
    object_name: name,
    epoch: epochText(yy >= 57 ? 1900 + yy : 2000 + yy, l1.slice(20, 32)),
    mean_motion: l2.slice(52, 63).trim(),
    eccentricity: "0." + l2.slice(26, 33),
    inclination: l2.slice(8, 16).trim(),
    ra_of_asc_node: l2.slice(17, 25).trim(),
    arg_of_pericenter: l2.slice(34, 42).trim(),
    mean_anomaly: l2.slice(43, 51).trim(),
    bstar: exponent(l1.slice(53, 61)),
    mean_motion_dot: l1.slice(33, 43).replaceAll(" ", ""),
    mean_motion_ddot: exponent(l1.slice(44, 52)),
  };
}

// The toy: name line optional, two element lines, fixed columns, the checksum checked.
function toyParse(text) {
  const lines = text.split("\n").map((l) => l.replace(/\r$/, ""));
  const out = [];
  for (let i = 0; i < lines.length; i++) {
    const l1 = lines[i];
    if (l1.startsWith("1 ") && i + 1 < lines.length && lines[i + 1].startsWith("2 ")) {
      const prev = i > 0 ? lines[i - 1] : "";
      const name = prev.trim() && !prev.startsWith("2 ") ? prev.trim() : null;
      try {
        out.push(record(name, l1, lines[i + 1]));
      } catch (e) { // the refusal channel: the record was dropped, and why (docs/ADAPTERS.md, "Refusals")
        out.push({ _refused: `Error: ${e.message}`, _field: l1.slice(2, 7), _input: l1.slice(0, 80) });
      }
      i++;
    } else if (l1.startsWith("1 ") || l1.startsWith("2 ")) {
      out.push({ _refused: "an element line that pairs with nothing", _field: l1.slice(2, 7), _input: l1.slice(0, 80) });
    }
  }
  return out;
}

const fmt = process.argv[2] ?? "tle";
if (fmt !== "tle" && fmt !== "2le") process.exit(3); // exit 3: format not supported; the file is reported as a skip
try {
  process.stdout.write(JSON.stringify(toyParse(new TextDecoder("utf-8").decode(readFileSync(0)))));
} catch (e) { // anything unexpected: say so on standard error and exit 1, never crash with a signal
  process.stderr.write(`adapter: ${e}\n`);
  process.exit(1);
}
