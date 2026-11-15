// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
//! A gpconf adapter template for a parser in Rust, run by command:
//!
//!     cargo build --release --manifest-path templates/rust/Cargo.toml
//!     python3 -m gpconf run --cmd "templates/rust/target/release/gpconf-adapter-template {fmt}"
//!
//! gpconf writes one file to standard input and reads a JSON array of records from standard output (docs/ADAPTERS.md,
//! "The command protocol"). Replace `toy_parse` with a call to your library; keep the rest. The toy parser reads TLE
//! only and is here so the template runs as it stands; it is not a parser to use. Same toy as templates/python/adapter.py.
//! A panic aborts or unwinds to a non-zero exit (101); return errors and exit 1 instead, so a refusal is never a crash.
//! UNTESTED: written without a Rust toolchain on the machine that wrote it; templates/README.md says which were run.
use std::io::{Read, Write};

const ALPHA5: &str = "ABCDEFGHJKLMNPQRSTUVWXYZ"; // I and O are skipped

fn digits(s: &str) -> bool {
    !s.is_empty() && s.bytes().all(|c| c.is_ascii_digit())
}

fn json(s: &str) -> String {
    let mut o = String::from("\"");
    for c in s.chars() {
        match c {
            '"' | '\\' => { o.push('\\'); o.push(c); }
            c if (c as u32) < 0x20 || c as u32 == 0x7f => o.push_str(&format!("\\u{:04x}", c as u32)),
            c => o.push(c),
        }
    }
    o.push('"');
    o
}

/// Columns a..b of a line, by characters, clipped to its length.
fn cols(l: &[char], a: usize, b: usize) -> String {
    l[a.min(l.len())..b.min(l.len())].iter().collect()
}

fn trim(s: &str) -> String {
    s.trim_matches(|c| c == ' ' || c == '\t').to_string()
}

fn alpha5(f: &str) -> Result<u64, String> {
    let c: Vec<char> = f.chars().collect();
    if c.len() != 5 || !digits(&f[1..]) {
        return Err(format!("invalid catalog field {}", json(f)));
    }
    if c[0].is_ascii_digit() {
        return Ok(f.parse().unwrap());
    }
    let k = ALPHA5.find(c[0]).ok_or_else(|| format!("invalid catalog field {}", json(f)))?;
    Ok((k as u64 + 10) * 10000 + f[1..].parse::<u64>().unwrap())
}

fn checksum(l: &[char]) -> u32 {
    l.iter().take(68).map(|&c| if c.is_ascii_digit() { c as u32 - '0' as u32 } else if c == '-' { 1 } else { 0 }).sum::<u32>() % 10
}

/// " 12345-3" -> "0.12345e-3", compared exactly as text.
fn exponent(field: &str) -> String {
    let f = trim(field);
    let sign = if f.starts_with('-') { "-" } else { "" };
    let f: Vec<char> = f.trim_start_matches(|c| c == '-' || c == '+').chars().collect();
    format!("{}0.{}e{}", sign, cols(&f, 0, 5), cols(&f, 5, f.len()))
}

fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    // H. Hinnant's algorithm: days since 1970-01-01
    let y = if m <= 2 { y - 1 } else { y };
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = y - era * 400;
    let doy = (153 * (if m > 2 { m - 3 } else { m + 9 }) + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146097 + doe - 719468
}

fn civil_from_days(z: i64) -> (i64, i64, i64) {
    let z = z + 719468;
    let era = if z >= 0 { z } else { z - 146096 } / 146097;
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    (yoe + era * 400 + if m <= 2 { 1 } else { 0 }, m, d)
}

/// "DDD.DDDDDDDD" -> "YYYY-MM-DDThh:mm:ss.ffffff"; eight decimals of a day are whole microseconds (1e-8 day = 864 us).
fn epoch_text(year: i64, day: &str) -> Result<String, String> {
    let d: Vec<char> = day.chars().collect();
    if d.len() != 12 || d[3] != '.' || !digits(&(cols(&d, 0, 3) + &cols(&d, 4, 12))) {
        return Err(format!("epoch day {} is not DDD.DDDDDDDD", json(day)));
    }
    let us = (cols(&d, 0, 3).parse::<i64>().unwrap() - 1) * 86_400_000_000 + cols(&d, 4, 12).parse::<i64>().unwrap() * 864;
    let (y, m, dd) = civil_from_days(days_from_civil(year, 1, 1) + us / 86_400_000_000);
    let rest = us % 86_400_000_000;
    Ok(format!("{:04}-{:02}-{:02}T{:02}:{:02}:{:02}.{:06}", y, m, dd, rest / 3_600_000_000, rest / 60_000_000 % 60,
               rest / 1_000_000 % 60, rest % 1_000_000))
}

fn record(name: Option<String>, l1: &[char], l2: &[char]) -> Result<String, String> {
    if l1.len() != 69 || l2.len() != 69 {
        return Err(format!("line lengths {}/{}, not 69", l1.len(), l2.len()));
    }
    if l1[68].to_digit(10) != Some(checksum(l1)) || l2[68].to_digit(10) != Some(checksum(l2)) {
        return Err("checksum".into());
    }
    if cols(l1, 2, 7) != cols(l2, 2, 7) {
        return Err("line 2's catalog number is not line 1's".into());
    }
    if !digits(&cols(l1, 18, 20)) {
        return Err(format!("epoch year {} is not two digits", json(&cols(l1, 18, 20))));
    }
    let yy: i64 = cols(l1, 18, 20).parse().unwrap();
    Ok(format!(
        "{{\"norad_cat_id\":{},\"object_name\":{},\"epoch\":{},\"mean_motion\":{},\"eccentricity\":{},\"inclination\":{},\
         \"ra_of_asc_node\":{},\"arg_of_pericenter\":{},\"mean_anomaly\":{},\"bstar\":{},\"mean_motion_dot\":{},\"mean_motion_ddot\":{}}}",
        alpha5(&cols(l1, 2, 7))?,
        name.map(|n| json(&n)).unwrap_or_else(|| "null".into()),
        json(&epoch_text(if yy >= 57 { 1900 + yy } else { 2000 + yy }, &cols(l1, 20, 32))?),
        json(&trim(&cols(l2, 52, 63))),
        json(&format!("0.{}", cols(l2, 26, 33))),
        json(&trim(&cols(l2, 8, 16))),
        json(&trim(&cols(l2, 17, 25))),
        json(&trim(&cols(l2, 34, 42))),
        json(&trim(&cols(l2, 43, 51))),
        json(&exponent(&cols(l1, 53, 61))),
        json(&cols(l1, 33, 43).replace(' ', "")),
        json(&exponent(&cols(l1, 44, 52))),
    ))
}

/// The toy: name line optional, two element lines, fixed columns, the checksum checked.
fn toy_parse(text: &str) -> Vec<String> {
    let lines: Vec<Vec<char>> = text.split('\n').map(|l| l.strip_suffix('\r').unwrap_or(l).chars().collect()).collect();
    let mut out = Vec::new();
    let mut i = 0;
    while i < lines.len() {
        let l1 = &lines[i];
        let s1: String = l1.iter().collect();
        if s1.starts_with("1 ") && i + 1 < lines.len() && lines[i + 1].starts_with(&['2', ' ']) {
            let prev: String = if i > 0 { lines[i - 1].iter().collect() } else { String::new() };
            let name = if !trim(&prev).is_empty() && !prev.starts_with("2 ") { Some(trim(&prev)) } else { None };
            match record(name, l1, &lines[i + 1]) {
                Ok(r) => out.push(r),
                // the refusal channel: the record was dropped, and why
                Err(e) => out.push(format!("{{\"_refused\":{},\"_field\":{},\"_input\":{}}}", json(&format!("error: {}", e)),
                                           json(&cols(l1, 2, 7)), json(&cols(l1, 0, 80)))),
            }
            i += 2;
            continue;
        }
        if s1.starts_with("1 ") || s1.starts_with("2 ") {
            out.push(format!("{{\"_refused\":\"an element line that pairs with nothing\",\"_field\":{},\"_input\":{}}}",
                             json(&cols(l1, 2, 7)), json(&cols(l1, 0, 80))));
        }
        i += 1;
    }
    out
}

fn main() {
    let fmt = std::env::args().nth(1).unwrap_or_else(|| "tle".into());
    if fmt != "tle" && fmt != "2le" {
        std::process::exit(3); // exit 3: format not supported; the file is reported as a skip
    }
    let mut raw = Vec::new();
    if let Err(e) = std::io::stdin().read_to_end(&mut raw) {
        eprintln!("adapter: {}", e);
        std::process::exit(1);
    }
    let text = String::from_utf8_lossy(&raw);
    let out = format!("[{}]", toy_parse(&text).join(","));
    if std::io::stdout().write_all(out.as_bytes()).is_err() {
        std::process::exit(1);
    }
}
