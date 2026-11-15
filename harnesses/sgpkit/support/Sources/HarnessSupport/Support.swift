// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
// Shared by the harnesses and the vectors helpers: the JSON they print, the bytes they read, the calendar form of an
// epoch a library keeps as a day count, and a checksum routine of this project's own for the synthetic lines the
// vectors helpers build. Nothing here parses an element set.

import Foundation

// MARK: - input

public func readStandardInput() -> Data {
    FileHandle.standardInput.readDataToEndOfFile()
}

public func note(_ message: String) {
    FileHandle.standardError.write(Data((message + "\n").utf8))
}

/// The file's lines, split on LF at the byte level with one trailing CR removed from each. Done on bytes because a
/// Swift `Character` holds CR LF as one grapheme, so a split on "\n" would leave such a file in one piece.
public func byteLines(_ raw: Data) -> [String] {
    raw.split(separator: 0x0A, omittingEmptySubsequences: false).map { line in
        var bytes = line
        if bytes.last == 0x0D { bytes = bytes.dropLast() }
        return String(decoding: bytes, as: UTF8.self)
    }
}

/// Columns 3 to 7 of a TLE line, the catalog field as the line carries it, for a refusal's `_field`.
public func catalogField(_ line: String) -> String? {
    let bytes = Array(line.utf8)
    guard bytes.count >= 7 else { return nil }
    return String(decoding: bytes[2..<7], as: UTF8.self)
}

public func trimmingTrailingSpaces(_ s: String) -> String {
    var out = Substring(s)
    while out.last == " " { out = out.dropLast() }
    return String(out)
}

// MARK: - output

public func jsonString(_ s: String) -> String {
    var out = "\""
    for u in s.unicodeScalars {
        switch u {
        case "\"": out += "\\\""
        case "\\": out += "\\\\"
        case "\n": out += "\\n"
        case "\r": out += "\\r"
        case "\t": out += "\\t"
        default:
            if u.value < 0x20 { out += String(format: "\\u%04x", u.value) } else { out.unicodeScalars.append(u) }
        }
    }
    return out + "\""
}

/// One JSON object, its keys in the order they were added.
public struct JSONObject {
    private var parts: [String] = []
    public init() {}

    public mutating func string(_ key: String, _ value: String?) {
        parts.append(jsonString(key) + ":" + (value.map(jsonString) ?? "null"))
    }

    public mutating func integer<T: BinaryInteger>(_ key: String, _ value: T) {
        parts.append(jsonString(key) + ":" + String(value))
    }

    /// A double as the shortest text that reads back to the same double. JSON has no NaN or infinity: such a value is
    /// written as null, which the runner reads as absent, and named on standard error.
    public mutating func number(_ key: String, _ value: Double) {
        if value.isFinite {
            parts.append(jsonString(key) + ":" + "\(value)")
        } else {
            note("non-finite \(key): \(value)")
            parts.append(jsonString(key) + ":null")
        }
    }

    public mutating func raw(_ key: String, _ json: String) {
        parts.append(jsonString(key) + ":" + json)
    }

    public var text: String { "{" + parts.joined(separator: ",") + "}" }
}

/// The process's real standard output. Both libraries print to standard output on some paths (SatelliteKit's XML
/// reader prints a parse error, its `formatOK` prints its verdict), which would land inside the JSON; so standard
/// output is pointed at standard error for the life of the process and the answer goes to the descriptor kept here.
private var realOutput: Int32 = STDOUT_FILENO

public func sendLibraryPrintsToStandardError() {
    guard realOutput == STDOUT_FILENO else { return }
    fflush(stdout)
    realOutput = dup(STDOUT_FILENO)
    dup2(STDERR_FILENO, STDOUT_FILENO)
}

private func writeAnswer(_ text: String) {
    fflush(stdout)
    let bytes = Array(text.utf8)
    var done = 0
    while done < bytes.count {
        let n = bytes[done...].withUnsafeBytes { write(realOutput, $0.baseAddress, $0.count) }
        if n <= 0 { exit(1) }
        done += n
    }
}

/// The array of records and refusals a harness prints.
public final class Report {
    private var items: [String] = []

    public init() {
        sendLibraryPrintsToStandardError()
    }

    /// Says that every record this harness drops with an error is reported as a refusal.
    public func declareRefusals() {
        items.append("{\"_adapter\":{\"refusals\":true}}")
    }

    public func record(_ object: JSONObject) {
        items.append(object.text)
    }

    /// The refusal channel: the library's own reason, the catalog field as the input carried it, the input's start.
    public func refusal(reason: String, field: String?, input: String?) {
        var o = JSONObject()
        o.string("_refused", reason)
        if let field { o.string("_field", field) }
        if let input { o.string("_input", String(input.prefix(80))) }
        items.append(o.text)
    }

    public func finish() -> Never {
        writeAnswer("[" + items.joined(separator: ",") + "]\n")
        exit(0)
    }
}

/// One answer of a vectors helper.
public func answer(_ json: String, exitCode: Int32 = 0) -> Never {
    writeAnswer(json)
    exit(exitCode)
}

// MARK: - epochs

/// Days since 1970-01-01 to a proleptic Gregorian date (Howard Hinnant's civil_from_days).
public func civil(fromUnixDays z0: Int) -> (year: Int, month: Int, day: Int) {
    let z = z0 + 719_468
    let era = (z >= 0 ? z : z - 146_096) / 146_097
    let doe = z - era * 146_097
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365
    let y = yoe + era * 400
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100)
    let mp = (5 * doy + 2) / 153
    let d = doy - (153 * mp + 2) / 5 + 1
    let m = mp < 10 ? mp + 3 : mp - 9
    return (m <= 2 ? y + 1 : y, m, d)
}

/// A day count from 1949-12-31T00:00:00 UTC (the "days since 1950" of the TLE epoch, day 1 being 1950-01-01), as a
/// calendar instant to the microsecond: the whole days by integer arithmetic, the fraction rounded to the nearest
/// microsecond. nil for a value that is not finite or not a date this arithmetic covers.
public func isoInstant(daysSince1950 d: Double) -> String? {
    guard d.isFinite, abs(d) < 1.0e6 else { return nil }
    var whole = d.rounded(.down)
    var micros = ((d - whole) * 86_400_000_000.0).rounded()
    if micros >= 86_400_000_000.0 { micros -= 86_400_000_000.0; whole += 1 }
    let us = Int(micros)
    let (y, m, day) = civil(fromUnixDays: Int(whole) - 7_306)   // 1949-12-31 is 7306 days before 1970-01-01
    return String(format: "%04d-%02d-%02dT%02d:%02d:%02d.%06d", y, m, day,
                  us / 3_600_000_000, (us / 60_000_000) % 60, (us / 1_000_000) % 60, us % 1_000_000)
}

// MARK: - synthetic lines for the vectors helpers

/// A valid pair to put a field into: the ISS element set the corpus's own vectors helpers use.
public let sampleLine1 = "1 25544U 98067A   26263.52959654  .00008422  00000+0  15975-3 0  9999"
public let sampleLine2 = "2 25544  51.6308 188.2246 0004825 162.2847 197.8311 15.49196792 58653"

/// The line cut or padded to 68 columns with its checksum digit recomputed: digits count their value, '-' counts 1.
public func withChecksum(_ line: String) -> String {
    var bytes = Array(line.utf8.prefix(68))
    while bytes.count < 68 { bytes.append(0x20) }
    var sum = 0
    for b in bytes {
        if b >= 0x30 && b <= 0x39 { sum += Int(b) - 0x30 } else if b == 0x2D { sum += 1 }
    }
    bytes.append(UInt8(0x30 + sum % 10))
    return String(decoding: bytes, as: UTF8.self)
}

/// `line` with the bytes at `range` replaced by `field`.
public func replacing(_ line: String, _ range: Range<Int>, with field: String) -> String {
    let bytes = Array(line.utf8)
    return String(decoding: bytes[..<range.lowerBound] + Array(field.utf8) + bytes[range.upperBound...], as: UTF8.self)
}

/// The request a vectors helper gets: {"op": ..., "input": ...}; the input as text whether it came as a string or a number.
public func readVectorRequest() -> (op: String, input: String) {
    sendLibraryPrintsToStandardError()
    let data = readStandardInput()
    guard let obj = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any], let op = obj["op"] as? String else {
        answer("{\"error\":\"request is not {op, input}\"}", exitCode: 1)
    }
    if let s = obj["input"] as? String { return (op, s) }
    if let n = obj["input"] as? NSNumber { return (op, n.stringValue) }
    return (op, "")
}
