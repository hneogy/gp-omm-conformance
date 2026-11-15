// swift-tools-version: 6.0
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
// gpconf adapter for SGPKit (csanfilippo/swift-sgp4), release 3.1.0, compiled from a clone of the project at that
// tag in upstream/ (README.md gives the clone command). Nothing of the project is copied into this repository.
//
// SGPKit is not used as a package dependency here because its one file that calls into C++, TLEInterpreter.swift,
// needs the Swift overlay of the C++ standard library (std.string from a String, the value of a std.optional), and
// the toolchain this was built with, the Command Line Tools' Swift 6.4, ships that overlay's static library without
// its Swift module. So the three targets below are the package's own, declared over its own sources, with that one
// file left out; SGPKitBridge is this project's C interface over the library's bridge function, createTLE().

import PackageDescription

let package = Package(
    name: "harness-sgpkit",
    platforms: [.macOS(.v13)],
    dependencies: [
        .package(path: "support"),
    ],
    targets: [
        // SGPKit's own targets, sources unmodified
        .target(name: "SGPKitCPP", path: "upstream/Sources/sgp4Lib"),
        .target(name: "SGP4LibWrapper", dependencies: ["SGPKitCPP"], path: "upstream/Sources/SGP4LibWrapper"),
        .target(
            name: "SGPKit",
            path: "upstream/Sources/SGPKit",
            exclude: ["TLEInterpreter.swift", "PrivacyInfo.xcprivacy"]
        ),
        // this project's
        .target(name: "SGPKitBridge", dependencies: ["SGP4LibWrapper"]),
        // C++ interoperability is on for the two executables only so that the build can form the module of the C++
        // targets SGPKitBridge depends on; they import SGPKitBridge's C header and nothing of C++.
        .executableTarget(
            name: "sgpkit-harness",
            dependencies: ["SGPKit", "SGPKitBridge", .product(name: "HarnessSupport", package: "support")],
            swiftSettings: [.interoperabilityMode(.Cxx)]
        ),
        .executableTarget(
            name: "sgpkit-vectors",
            dependencies: ["SGPKit", "SGPKitBridge", .product(name: "HarnessSupport", package: "support")],
            swiftSettings: [.interoperabilityMode(.Cxx)]
        ),
    ],
    swiftLanguageModes: [.v5],
    cxxLanguageStandard: .cxx17
)
