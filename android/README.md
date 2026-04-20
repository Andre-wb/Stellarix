# Vortex — Android (Kotlin / Compose)

Android client for Vortex. Mirrors the web messenger feature-for-feature
across 20 waves.

## Status

**Waves 1 – 20 scaffolded.** Every feature surface is present as a
SOLID API + at least one impl + Hilt bindings. Each successive wave is
one concrete thing to flesh out behind stable interfaces that already
compile. Later waves (17 calls, 18 push, 19 federation, 20 settings /
i18n) ship as interfaces so the UI can start depending on them now
without blocking on the full native-binding work.

## Requirements

- Android Studio Ladybug (2024.2.1) or newer
- JDK 17 (Android Studio bundles it)
- Android SDK Platform 34, min device: Android 8.0 (API 26)

## Bootstrapping the Gradle wrapper

The wrapper JAR is **not** committed (binary). Generate it once after
cloning — any of these works:

```bash
# 1. open in Android Studio → it auto-downloads the wrapper on first sync
# 2. or, with Gradle installed locally:
cd android && gradle wrapper --gradle-version 8.10

# 3. or fetch the jar directly from the Gradle release
curl -L -o gradle/wrapper/gradle-wrapper.jar \
  https://raw.githubusercontent.com/gradle/gradle/v8.10.0/gradle/wrapper/gradle-wrapper.jar
```

After that:

```bash
./gradlew assembleDebug        # build app/build/outputs/apk/debug/app-debug.apk
./gradlew installDebug         # push to a connected device / running emulator
```

## Project layout

```
android/
├── app/
│   ├── build.gradle.kts
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── java/sol/vortexx/android/
│       │   ├── VortexApp.kt            ← @HiltAndroidApp
│       │   ├── MainActivity.kt
│       │   └── ui/
│       │       ├── theme/              ← palette + typography
│       │       └── screens/            ← per-wave screens
│       └── res/                        ← strings, icons, theme XML
├── build.gradle.kts
├── settings.gradle.kts
├── gradle/libs.versions.toml           ← single version catalog
└── gradle.properties
```

## Wave plan

| # | Wave | What ships |
|---|------|-----------|
|  1 | Scaffold (current) | Empty app, Compose/Hilt wired, brand dot |
|  2 | Crypto primitives | X25519, Ed25519, AES-GCM, HKDF, Argon2id |
|  3 | Bootstrap flow | vortexx.sol probe → mirror / manual URL entry |
|  4 | HTTP + JWT | Ktor client, auth header, retry, TLS handling |
|  5 | Register / login | Auth screens + encrypted JWT storage |
|  6 | Identity | BIP39 seed, X25519 keypair, key backup |
|  7 | Room DB | Users, rooms, members, messages, keys |
|  8 | Rooms | List + create + join by invite |
|  9 | Key delivery | ECIES + Variant-B auto-fetch for public rooms |
| 10 | WebSocket | Reconnect, heartbeat, outbound queue |
| 11 | Messaging | AES-GCM encrypt / decrypt on send + receive |
| 12 | Chat UI | LazyColumn, input, delivery state |
| 13 | Reactions / replies / threads | Parity with the web client |
| 14 | File upload | Resumable + E2E |
| 15 | File view | Media viewer (image / video / pdf) |
| 16 | Stickers / GIFs / voice notes | Full chat UX |
| 17 | Calls | WebRTC + SFU bridge |
| 18 | Push | FCM + `/api/push/subscribe` |
| 19 | Federation | Multihop, mirror fallback, offline cache |
| 20 | i18n + polish | 146 locales, themes, settings, release APK |
