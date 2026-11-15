// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
//! gpconf harness for the Rust `sgp4` crate (0.9.0 item b2), one program for `--cmd` and `--vectors-cmd`:
//!   gpconf-rust-sgp4 parse {fmt}   reads TLE/2LE through Elements::from_tle and OMM JSON through serde
//!   gpconf-rust-sgp4 vectors       answers the propagate op through Constants::from_elements; the other ops unsupported
//! UNTESTED: written without a Rust toolchain on the machine that wrote it, from the crate's documented interface
//! (README.md). Values are the library's, as it holds them; nothing is decided for it.
use serde_json::{json, Value};
use std::io::Read;

fn record(e: &sgp4::Elements) -> Value {
    json!({
        "norad_cat_id": e.norad_id,
        "object_name": e.object_name,
        "epoch": e.datetime.format("%Y-%m-%dT%H:%M:%S%.6f").to_string(),
        "mean_motion": e.mean_motion,
        "eccentricity": e.eccentricity,
        "inclination": e.inclination,
        "ra_of_asc_node": e.right_ascension,
        "arg_of_pericenter": e.argument_of_perigee,
        "mean_anomaly": e.mean_anomaly,
        "bstar": e.drag_term,
        "mean_motion_dot": e.mean_motion_dot,
        "mean_motion_ddot": e.mean_motion_ddot,
        "ephemeris_type": e.ephemeris_type,
        "element_set_no": e.element_set_number,
        "rev_at_epoch": e.revolution_number,
    })
}

/// TLE sets, the line before a line 1 as its name; a set the library refuses goes back through the refusal channel.
fn parse_tle(text: &str) -> Vec<Value> {
    let lines: Vec<&str> = text.split('\n').map(|l| l.strip_suffix('\r').unwrap_or(l)).collect();
    // the harness reports the library's refusals (D-440) and propagates with WGS-72, opsmode 'i' (D-441)
    let mut out = vec![json!({"_adapter": {"refusals": true, "propagation": {"gravity": "wgs72", "opsmode": "i"}}})];
    let mut i = 0;
    while i < lines.len() {
        if lines[i].starts_with("1 ") {
            // a line 1 with no line 2 after it goes to the library as it is, for the library to answer (D-440)
            let paired = i + 1 < lines.len() && lines[i + 1].starts_with("2 ");
            let l2 = if paired { lines[i + 1] } else { "" };
            let name = if i > 0 && !lines[i - 1].trim().is_empty() && !lines[i - 1].starts_with("2 ") {
                Some(lines[i - 1].trim().to_string())
            } else {
                None
            };
            match sgp4::Elements::from_tle(name, lines[i].as_bytes(), l2.as_bytes()) {
                Ok(e) => out.push(record(&e)),
                Err(err) => out.push(json!({"_refused": format!("{:?}", err), "_field": lines[i].get(2..7), "_input": lines[i]})),
            }
            i += if paired { 2 } else { 1 };
        } else {
            i += 1;
        }
    }
    out
}

fn parse(fmt: &str, raw: &[u8]) -> Result<Vec<Value>, String> {
    match fmt {
        "tle" | "2le" => Ok(parse_tle(&String::from_utf8_lossy(raw))),
        "json" => serde_json::from_slice::<Vec<sgp4::Elements>>(raw).map(|v| v.iter().map(record).collect()).map_err(|e| e.to_string()),
        _ => std::process::exit(3), // the library reads TLE and OMM JSON only: exit 3, the format unsupported
    }
}

/// WGS-72 constants with the IAU sidereal time, built through the crate's own `Constants::new`: the reference's
/// gravity model (WGS-72, opsmode 'i'). The crate's `Constants::from_elements` uses WGS-84, which the first run used and
/// which put it 0.03 km off the WGS-72 reference at t = 0 (D-441); the choice is declared in `parse`'s answer.
fn wgs72_constants(e: &sgp4::Elements) -> Result<sgp4::Constants, String> {
    let d = core::f64::consts::PI / 180.0;
    let orbit = sgp4::Orbit::from_kozai_elements(
        &sgp4::WGS72,
        e.inclination * d,
        e.right_ascension * d,
        e.eccentricity,
        e.argument_of_perigee * d,
        e.mean_anomaly * d,
        e.mean_motion * (core::f64::consts::PI / 720.0),
    )
    .map_err(|x| format!("{:?}", x))?;
    sgp4::Constants::new(sgp4::WGS72, sgp4::iau_epoch_to_sidereal_time, e.epoch(), e.drag_term, orbit)
        .map_err(|x| format!("{:?}", x))
}

/// The crate's errors as Vallado's codes where one is meant [inferred: by name; untested]; any other error 99.
fn code(err: &impl std::fmt::Debug) -> i64 {
    let s = format!("{:?}", err);
    if s.contains("OutOfRangeEccentricity") { 1 } else if s.contains("OutOfRangeMeanMotion") { 2 }
    else if s.contains("OutOfRangePerturbedEccentricity") { 3 } else if s.contains("NegativeSemiLatusRectum") { 4 }
    else if s.contains("Decay") { 6 } else { 99 }
}

fn propagate(input: &Value) -> Value {
    let raw = input["raw"].as_str().unwrap_or("").as_bytes().to_vec();
    let fmt = input["fmt"].as_str().unwrap_or("");
    let times: Vec<f64> = input["tsince"].as_array().map(|a| a.iter().filter_map(|t| t.as_f64()).collect()).unwrap_or_default();
    if times.is_empty() {
        return json!({"result": []}); // the probe: the op exists
    }
    let elements = match fmt {
        "tle" | "2le" => {
            let text = String::from_utf8_lossy(&raw).to_string();
            let l: Vec<&str> = text.lines().filter(|l| l.starts_with("1 ") || l.starts_with("2 ")).collect();
            if l.len() != 2 { return json!({"error": "one element set expected"}); }
            match sgp4::Elements::from_tle(None, l[0].as_bytes(), l[1].as_bytes()) { Ok(e) => e, Err(e) => return json!({"error": format!("{:?}", e)}) }
        }
        _ => return json!({"unsupported": "the harness propagates TLE only"}),
    };
    let constants = match wgs72_constants(&elements) {
        Ok(c) => c,
        Err(e) => return json!({"result": times.iter().map(|_| json!({"r": null, "v": null, "error": code(&e)})).collect::<Vec<_>>()}),
    };
    let steps: Vec<Value> = times.iter().map(|t| match constants.propagate(sgp4::MinutesSinceEpoch(*t)) {
        Ok(p) => json!({"r": p.position, "v": p.velocity, "error": 0}),
        Err(e) => json!({"r": null, "v": null, "error": code(&e)}),
    }).collect();
    json!({"result": steps})
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let mut raw = Vec::new();
    if std::io::stdin().read_to_end(&mut raw).is_err() { std::process::exit(1); }
    match args.get(1).map(String::as_str) {
        Some("parse") => match parse(args.get(2).map(String::as_str).unwrap_or("tle"), &raw) {
            Ok(v) => println!("{}", Value::Array(v)),
            Err(e) => { eprintln!("parse: {}", e); std::process::exit(1); }
        },
        Some("vectors") => {
            let req: Value = match serde_json::from_slice(&raw) { Ok(v) => v, Err(e) => { eprintln!("{}", e); std::process::exit(1); } };
            let ans = match req["op"].as_str() {
                Some("propagate") => propagate(&req["input"]),
                Some(op) => json!({"unsupported": format!("the sgp4 crate has no {} hook", op)}),
                None => json!({"error": "no op"}),
            };
            println!("{}", ans);
        }
        _ => { eprintln!("usage: gpconf-rust-sgp4 parse FMT | vectors"); std::process::exit(1); }
    }
}
