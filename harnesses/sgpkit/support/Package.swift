// swift-tools-version: 6.0
// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 NEOGY LLC
// Shared by the two harness packages beside this one: output, input and calendar helpers. No library is imported here.

import PackageDescription

let package = Package(
    name: "support",
    platforms: [.macOS(.v13)],
    products: [.library(name: "HarnessSupport", targets: ["HarnessSupport"])],
    targets: [.target(name: "HarnessSupport")],
    swiftLanguageModes: [.v5]
)
