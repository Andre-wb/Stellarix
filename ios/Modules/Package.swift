// swift-tools-version: 5.10
import PackageDescription

/// Vortex iOS — feature modules.
///
/// The app target (VortexApp) imports the `App` library which re-exports
/// every feature. Each feature is a standalone library with `api/`,
/// `impl/`, and (where applicable) `ui/` folders — same SOLID split as
/// the Kotlin client. Dependencies between features are declared here
/// explicitly so the compiler enforces the layering.
let package = Package(
    name: "VortexModules",
    platforms: [
        .iOS(.v16),
    ],
    products: [
        .library(name: "App",        targets: ["App"]),
        .library(name: "VortexCrypto", targets: ["VortexCrypto"]),
        .library(name: "Bootstrap",  targets: ["Bootstrap"]),
        .library(name: "Net",        targets: ["Net"]),
        .library(name: "Auth",       targets: ["Auth"]),
        .library(name: "Identity",   targets: ["Identity"]),
        .library(name: "DB",         targets: ["DB"]),
        .library(name: "Rooms",      targets: ["Rooms"]),
        .library(name: "Keys",       targets: ["Keys"]),
        .library(name: "WS",         targets: ["WS"]),
        .library(name: "Chat",       targets: ["Chat"]),
        .library(name: "Files",      targets: ["Files"]),
        .library(name: "Stickers",   targets: ["Stickers"]),
        .library(name: "Calls",      targets: ["Calls"]),
        .library(name: "Push",       targets: ["Push"]),
        .library(name: "Federation", targets: ["Federation"]),
        .library(name: "Search",     targets: ["Search"]),
        .library(name: "Spaces",     targets: ["Spaces"]),
        .library(name: "Bots",       targets: ["Bots"]),
        .library(name: "Threads",    targets: ["Threads"]),
        .library(name: "Feeds",      targets: ["Feeds"]),
        .library(name: "Settings",   targets: ["Settings"]),
        .library(name: "I18N",       targets: ["I18N"]),
    ],
    dependencies: [
        // GRDB — SQLite wrapper used for the local DB (Wave 7+).
        .package(url: "https://github.com/groue/GRDB.swift", from: "6.29.0"),
        // Argon2 through libargon2 — CryptoKit doesn't ship it.
        .package(url: "https://github.com/tmthecoder/Argon2Swift", from: "1.1.0"),
        // libwebrtc binary for iOS — Google stopped publishing, Stasel's
        // fork is the de-facto standard.
        .package(url: "https://github.com/stasel/WebRTC", from: "125.0.0"),
    ],
    targets: [
        // Feature targets start empty in Wave 1; they're filled in by
        // subsequent waves. The `App` target glues everything together
        // and re-exports what the UI needs.
        .target(name: "VortexCrypto", dependencies: [
            .product(name: "Argon2Swift", package: "Argon2Swift"),
        ]),
        .target(name: "Bootstrap",  dependencies: []),
        .target(name: "Net",        dependencies: ["Bootstrap"]),
        .target(name: "Auth",       dependencies: ["Net"]),
        .target(name: "Identity",   dependencies: ["VortexCrypto", "Auth"],
                resources: [.copy("Resources/bip39_english.txt")]),
        .target(name: "DB",         dependencies: [
            .product(name: "GRDB", package: "GRDB.swift"),
        ]),
        .target(name: "Rooms",      dependencies: ["Net", "DB", "VortexCrypto", "Identity"]),
        .target(name: "Keys",       dependencies: ["Net", "DB", "VortexCrypto"]),
        .target(name: "WS",         dependencies: ["Net", "Auth"]),
        .target(name: "Chat",       dependencies: ["WS", "Keys", "DB", "VortexCrypto", "Search", "Auth", "Threads"]),
        .target(name: "Files",      dependencies: ["Net", "VortexCrypto", "Keys"]),
        .target(name: "Stickers",   dependencies: ["Net"]),
        .target(name: "Calls",      dependencies: [
            "WS", "Net",
            .product(name: "WebRTC", package: "WebRTC"),
        ]),
        .target(name: "Push",       dependencies: ["Net", "VortexCrypto"]),
        .target(name: "Federation", dependencies: ["Net"]),
        .target(name: "Search",     dependencies: ["DB"]),
        .target(name: "Spaces",     dependencies: ["Net", "DB"]),
        .target(name: "Bots",       dependencies: ["Net", "DB"]),
        .target(name: "Threads",    dependencies: ["Net", "DB"]),
        .target(name: "Feeds",      dependencies: ["Net", "DB"]),
        .target(name: "Settings",   dependencies: ["DB", "Identity", "Auth"]),
        .target(name: "I18N",       dependencies: [], resources: [.copy("Resources/locales")]),
        .target(name: "App", dependencies: [
            "Bootstrap", "Net", "Auth", "Identity", "DB", "Rooms", "Keys", "WS", "Chat",
            "Files", "Stickers", "Calls", "Push", "Federation", "Search",
            "Spaces", "Bots", "Threads", "Feeds", "Settings", "I18N", "VortexCrypto",
        ]),
        .testTarget(name: "VortexCryptoTests", dependencies: ["VortexCrypto"]),
    ]
)
