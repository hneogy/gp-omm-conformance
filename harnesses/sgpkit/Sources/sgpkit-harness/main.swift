// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
// Harness for the gpconf runner over SGPKit (csanfilippo/swift-sgp4), in the runner's --cmd protocol: the file on
// standard input, the format as the one argument, a JSON array of records on standard output; exit 3 for a format
// the library has no reader for (everything but TLE lines).
//
// SGPKit's Swift type `TLE` holds three strings and checks one thing, that both data lines are 69 characters long.
// The fields are read by the libsgp4 it bundles, which its Swift code reaches through its bridge function,
// createTLE(title, line1, line2): libsgp4's Tle, or nothing when libsgp4 threw. This harness takes the two steps
// TLEInterpreter.satelliteData(from:date:) takes, TLE(...) and then createTLE(), and reports what the Tle holds.
// TLEInterpreter.swift itself is not compiled here (see Package.swift), so the second step goes through
// SGPKitBridge, this project's C interface over the same function.
//
// Which reader gets the file:
//   tle   TLEDecoder().decodeCollection(), the library's own file reader: non-empty lines in threes, a title and
//         two data lines
//   2le   the library has no file reader for sets without a title line, and has TLE(firstLine:secondLine:): each
//         line that begins "1 " goes to it with whatever line follows, so the library answers for the pair
// HARNESS_MODE=per-set reads tle the second way as well, with the line before as the title, through
// TLE(title:firstLine:secondLine:), for telling the file reader from the element reader.
//
// A set the library turns away comes back through the runner's refusal channel. When the initialiser throws, the
// reason is its TLEError. When createTLE() returns nothing, the reason names that: the bridge catches libsgp4's
// exception and keeps none of its message, and TLEInterpreter turns the empty result into Error.tle
// (TLEInterpreter.swift, lines 101 to 103, read and not run here). An error decodeCollection() throws is for the
// file, and the file fails with it.

import SGPKit
import SGPKitBridge
import Foundation
import HarnessSupport

let format = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : ""
let perSet = ProcessInfo.processInfo.environment["HARNESS_MODE"] == "per-set"
guard format == "tle" || format == "2le" else { exit(3) }

let report = Report()
let raw = readStandardInput()
let emptyResult = "createTLE() returned nothing: libsgp4 threw, and SGPKit's bridge keeps no message (TLEInterpreter.Error.tle)"

func fields(of tle: TLE) -> sgpkit_tle_fields? {
    let title = tle.title.utf8.map { CChar(bitPattern: $0) }
    let line1 = tle.firstLine.utf8.map { CChar(bitPattern: $0) }
    let line2 = tle.secondLine.utf8.map { CChar(bitPattern: $0) }
    var out = sgpkit_tle_fields()
    return sgpkit_create_tle(title, title.count, line1, line1.count, line2, line2.count, &out) == 1 ? out : nil
}

func emit(_ tle: TLE) {
    guard var t = fields(of: tle) else {
        report.refusal(reason: emptyResult, field: catalogField(tle.firstLine), input: tle.firstLine)
        return
    }
    var o = JSONObject()
    o.integer("norad_cat_id", t.norad_number)
    o.string("object_name", tle.title)
    o.string("_designator", withUnsafeBytes(of: &t.int_designator) { String(cString: $0.bindMemory(to: CChar.self).baseAddress!) })
    o.string("epoch", String(format: "%04d-%02d-%02dT%02d:%02d:%02d.%06d",
                             Int(t.year), Int(t.month), Int(t.day), Int(t.hour), Int(t.minute), Int(t.second), Int(t.microsecond)))
    o.number("mean_motion", t.mean_motion)
    o.number("eccentricity", t.eccentricity)
    o.number("inclination", t.inclination)
    o.number("ra_of_asc_node", t.ra_of_asc_node)
    o.number("arg_of_pericenter", t.arg_of_pericenter)
    o.number("mean_anomaly", t.mean_anomaly)
    o.number("bstar", t.bstar)
    o.number("mean_motion_dot", t.mean_motion_dt2)
    o.number("mean_motion_ddot", t.mean_motion_ddt6)
    o.integer("rev_at_epoch", t.orbit_number)
    // object_id, classification_type, ephemeris_type, element_set_no: libsgp4's Tle at this commit keeps none of them
    report.record(o)
}

report.declareRefusals()
if format == "tle" && !perSet {
    let sets: [TLE]
    do {
        sets = try TLEDecoder().decodeCollection(raw)
    } catch {
        // the library's error is for the file, not for a set: the file fails, with the error as the reason
        note("TLEDecoder.decodeCollection threw: \(String(reflecting: error))")
        exit(1)
    }
    for tle in sets { emit(tle) }
} else {
    let lines = byteLines(raw)
    for (i, line1) in lines.enumerated() where line1.hasPrefix("1 ") {
        let line2 = i + 1 < lines.count ? lines[i + 1] : ""
        let hasName = format == "tle" && i > 0 && !lines[i - 1].hasPrefix("1 ") && !lines[i - 1].hasPrefix("2 ")
        do {
            // the file pads names to 24 columns; the initialiser stores the title as given
            let tle = hasName ? try TLE(title: trimmingTrailingSpaces(lines[i - 1]), firstLine: line1, secondLine: line2)
                              : try TLE(firstLine: line1, secondLine: line2)
            emit(tle)
        } catch {
            report.refusal(reason: String(reflecting: error), field: catalogField(line1), input: line1)
        }
    }
}
report.finish()
