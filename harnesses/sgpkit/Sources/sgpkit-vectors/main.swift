// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
// Vector hooks for the gpconf runner over SGPKit, each through the library's own entry points, TLE(...) and then
// its bridge function createTLE(), reached through SGPKitBridge (nothing is decoded by this program):
//   alpha5_decode(field)  a valid line pair with the field in columns 3 to 7 of both lines -> Tle.NoradNumber()
//   two_digit_year(yy)    the same pair with the epoch year set -> Tle.Epoch().Year()
//   alpha5_encode         the library has no TLE writer and no Alpha-5 encoder: answered unsupported
//   parse_epoch, parse_catalog_id  the library reads TLE lines only: answered unsupported
// Input: {"op": ..., "input": ...} on standard input; output {"result": ...}, {"error": ...} or {"unsupported": ...}.

import SGPKit
import SGPKitBridge
import Foundation
import HarnessSupport

let (op, input) = readVectorRequest()

func fail(_ reason: String) -> Never {
    answer("{\"error\":\(jsonString(reason))}", exitCode: 1)
}

func read(_ first: String, _ second: String) -> sgpkit_tle_fields {
    let tle: TLE
    do { tle = try TLE(title: "X", firstLine: first, secondLine: second) } catch { fail(String(reflecting: error)) }
    let title = tle.title.utf8.map { CChar(bitPattern: $0) }
    let line1 = tle.firstLine.utf8.map { CChar(bitPattern: $0) }
    let line2 = tle.secondLine.utf8.map { CChar(bitPattern: $0) }
    var out = sgpkit_tle_fields()
    guard sgpkit_create_tle(title, title.count, line1, line1.count, line2, line2.count, &out) == 1 else {
        fail("createTLE() returned nothing: libsgp4 threw, and SGPKit's bridge keeps no message (TLEInterpreter.Error.tle)")
    }
    return out
}

switch op {
case "alpha5_decode":
    guard input.utf8.count == 5 else { fail("field must be five characters") }
    let t = read(withChecksum(replacing(sampleLine1, 2..<7, with: input)), withChecksum(replacing(sampleLine2, 2..<7, with: input)))
    answer("{\"result\":\(t.norad_number)}")

case "two_digit_year":
    guard input.utf8.count == 2 else { fail("two digits expected") }
    let t = read(withChecksum(replacing(sampleLine1, 18..<20, with: input)), sampleLine2)
    answer("{\"result\":\(t.year)}")

case "alpha5_encode":
    answer("{\"unsupported\":\"SGPKit has no TLE writer and no Alpha-5 encoder\"}")

case "parse_epoch", "parse_catalog_id":
    answer("{\"unsupported\":\"SGPKit reads TLE lines only; it has no OMM (CSV/JSON/XML/KVN) epoch or catalog-id parser\"}")

default:
    fail("unknown op \(op)")
}
