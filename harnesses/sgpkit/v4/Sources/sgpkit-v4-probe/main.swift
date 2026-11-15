// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
// sgpkit-v4-probe FILE...: for each file, what SGPKit's `TLEDecoder().decodeCollection` gives back, one line each:
// "FILE: N sets" or "FILE: threw ERROR". The library's answer only; nothing is decided for it.
import Foundation
import SGPKit

for path in CommandLine.arguments.dropFirst() {
    guard let data = FileManager.default.contents(atPath: path) else {
        print("\(path): unreadable")
        continue
    }
    do {
        let sets = try TLEDecoder().decodeCollection(data)
        print("\(path): \(sets.count) sets")
    } catch {
        print("\(path): threw \(error)")
    }
}
