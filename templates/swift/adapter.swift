// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
// A gpconf adapter template for a parser in Swift, run by command:
//
//     swiftc -O -o adapter templates/swift/adapter.swift
//     python3 -m gpconf run --cmd "./adapter {fmt}"
//
// gpconf writes one file to standard input and reads a JSON array of records from standard output (docs/ADAPTERS.md,
// "The command protocol"). Replace toyParse with a call to your library; keep the rest. The toy parser reads TLE only
// and is here so the template runs as it stands; it is not a parser to use. Same toy as templates/python/adapter.py.
// Throw and catch your errors: fatalError and a force-unwrap of nil trap, which gpconf reads as a crash, never a refusal.
import Foundation

struct Refusal: Error { let why: String }

let alpha5Letters = Array("ABCDEFGHJKLMNPQRSTUVWXYZ")  // I and O are skipped

func isDigits<S: StringProtocol>(_ s: S) -> Bool { !s.isEmpty && s.allSatisfy { ("0"..."9").contains($0) } }

func cols(_ line: [Character], _ a: Int, _ b: Int) -> String { String(line[min(a, line.count)..<min(b, line.count)]) }

func trim(_ s: String) -> String { s.trimmingCharacters(in: CharacterSet(charactersIn: " \t")) }

func alpha5(_ f: String) throws -> Int {
    let c = Array(f)
    guard c.count == 5, isDigits(f.dropFirst()) else { throw Refusal(why: "invalid catalog field \(f)") }
    if isDigits(String(c[0])) { return Int(f)! }
    guard let k = alpha5Letters.firstIndex(of: c[0]) else { throw Refusal(why: "invalid catalog field \(f)") }
    return (k + 10) * 10000 + Int(String(c[1...]))!
}

func checksum(_ l: [Character]) -> Int {
    var s = 0
    for c in l.prefix(68) { if let d = c.wholeNumberValue, c.isASCII { s += d } else if c == "-" { s += 1 } }
    return s % 10
}

func exponent(_ field: String) -> String {  // " 12345-3" -> "0.12345e-3", compared exactly as text
    var f = trim(field), sign = ""
    if f.hasPrefix("-") { sign = "-" }
    if f.hasPrefix("-") || f.hasPrefix("+") { f.removeFirst() }
    return "\(sign)0.\(f.prefix(5))e\(f.dropFirst(5))"
}

// "DDD.DDDDDDDD" -> "YYYY-MM-DDThh:mm:ss.ffffff"; eight decimals of a day are whole microseconds (1e-8 day = 864 us)
func epochText(_ year: Int, _ day: String) throws -> String {
    let d = Array(day)
    guard d.count == 12, d[3] == ".", isDigits(String(d[0..<3]) + String(d[4...])) else {
        throw Refusal(why: "epoch day \(day) is not DDD.DDDDDDDD")
    }
    let us = Int64(Int(String(d[0..<3]))! - 1) * 86_400_000_000 + Int64(String(d[4...]))! * 864
    var cal = Calendar(identifier: .gregorian)
    cal.timeZone = TimeZone(identifier: "UTC")!
    let jan1 = cal.date(from: DateComponents(year: year, month: 1, day: 1))!
    let date = cal.date(byAdding: .day, value: Int(us / 86_400_000_000), to: jan1)!
    let ymd = cal.dateComponents([.year, .month, .day], from: date)
    let rest = us % 86_400_000_000
    return String(format: "%04d-%02d-%02dT%02lld:%02lld:%02lld.%06lld", ymd.year!, ymd.month!, ymd.day!,
                  rest / 3_600_000_000, rest / 60_000_000 % 60, rest / 1_000_000 % 60, rest % 1_000_000)
}

func record(_ name: String?, _ l1: [Character], _ l2: [Character]) throws -> [String: Any] {
    guard l1.count == 69, l2.count == 69 else { throw Refusal(why: "line lengths \(l1.count)/\(l2.count), not 69") }
    guard l1[68].wholeNumberValue == checksum(l1), l2[68].wholeNumberValue == checksum(l2) else { throw Refusal(why: "checksum") }
    guard cols(l1, 2, 7) == cols(l2, 2, 7) else { throw Refusal(why: "line 2's catalog number is not line 1's") }
    guard isDigits(cols(l1, 18, 20)) else { throw Refusal(why: "epoch year \(cols(l1, 18, 20)) is not two digits") }
    let yy = Int(cols(l1, 18, 20))!
    return [
        "norad_cat_id": try alpha5(cols(l1, 2, 7)),
        "object_name": name ?? NSNull(),
        "epoch": try epochText(yy >= 57 ? 1900 + yy : 2000 + yy, cols(l1, 20, 32)),
        "mean_motion": trim(cols(l2, 52, 63)),
        "eccentricity": "0." + cols(l2, 26, 33),
        "inclination": trim(cols(l2, 8, 16)),
        "ra_of_asc_node": trim(cols(l2, 17, 25)),
        "arg_of_pericenter": trim(cols(l2, 34, 42)),
        "mean_anomaly": trim(cols(l2, 43, 51)),
        "bstar": exponent(cols(l1, 53, 61)),
        "mean_motion_dot": cols(l1, 33, 43).replacingOccurrences(of: " ", with: ""),
        "mean_motion_ddot": exponent(cols(l1, 44, 52)),
    ]
}

// The toy: name line optional, two element lines, fixed columns, the checksum checked.
func toyParse(_ text: String) -> [[String: Any]] {
    // split on "\n" by unicode scalars, so a CR LF pair (one Character in Swift) is not read as one
    let lines = text.unicodeScalars.split(separator: "\n", omittingEmptySubsequences: false).map { sub -> [Character] in
        var s = String(String.UnicodeScalarView(sub))
        if s.unicodeScalars.last == "\r" { s.unicodeScalars.removeLast() }
        return Array(s)
    }
    var out: [[String: Any]] = []
    var i = 0
    while i < lines.count {
        let l1 = lines[i], s1 = String(l1)
        if s1.hasPrefix("1 "), i + 1 < lines.count, String(lines[i + 1]).hasPrefix("2 ") {
            let prev = i > 0 ? String(lines[i - 1]) : ""
            let name: String? = !trim(prev).isEmpty && !prev.hasPrefix("2 ") ? trim(prev) : nil
            do {
                out.append(try record(name, l1, lines[i + 1]))
            } catch let e as Refusal {  // the refusal channel: the record was dropped, and why
                out.append(["_refused": "error: \(e.why)", "_field": cols(l1, 2, 7), "_input": cols(l1, 0, 80)])
            } catch {
                out.append(["_refused": "error: \(error)", "_field": cols(l1, 2, 7), "_input": cols(l1, 0, 80)])
            }
            i += 2
            continue
        }
        if s1.hasPrefix("1 ") || s1.hasPrefix("2 ") {
            out.append(["_refused": "an element line that pairs with nothing", "_field": cols(l1, 2, 7), "_input": cols(l1, 0, 80)])
        }
        i += 1
    }
    return out
}

let fmt = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "tle"
if fmt != "tle" && fmt != "2le" { exit(3) }  // exit 3: format not supported; the file is reported as a skip
let data = FileHandle.standardInput.readDataToEndOfFile()
guard let text = String(data: data, encoding: .utf8) else {
    FileHandle.standardError.write("adapter: the input is not UTF-8\n".data(using: .utf8)!)
    exit(1)
}
do {
    let out = try JSONSerialization.data(withJSONObject: toyParse(text), options: [.withoutEscapingSlashes])
    FileHandle.standardOutput.write(out)
} catch {  // anything unexpected: say so and exit 1, never trap
    FileHandle.standardError.write("adapter: \(error)\n".data(using: .utf8)!)
    exit(1)
}
