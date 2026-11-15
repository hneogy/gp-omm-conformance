// swift-tools-version: 5.9
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
// A probe of SGPKit 4.x through its public API (D-441). From 4.2.0 SGPKit is an ordinary package dependency, and its
// public API holds a TLE's three lines and propagates to a geodetic state: no parsed field is exposed, so 4.x cannot
// be graded by a gpconf reader harness. The probe asks one question the corpus's corrupt-input files can answer: does
// `TLEDecoder.decodeCollection` return the valid sets of a file that holds one corrupt set?
import PackageDescription

let package = Package(
    name: "sgpkit-v4-probe",
    platforms: [.macOS(.v13)],
    dependencies: [
        .package(url: "https://github.com/csanfilippo/swift-sgp4.git", exact: "4.4.0"),
    ],
    targets: [
        .executableTarget(name: "sgpkit-v4-probe", dependencies: [.product(name: "SGPKit", package: "swift-sgp4")]),
    ]
)
