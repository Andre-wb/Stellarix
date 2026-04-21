# `src-tauri/` — Tauri Desktop Shell

Native desktop wrapper for the Vortex web client. Uses [Tauri v5](https://tauri.app/) — the app boots a real browser engine (WKWebView on macOS, WebView2 on Windows, WebKitGTK on Linux) and points it at either the bundled static UI or a running Vortex node.

Minimal on purpose — the heavy lifting (auth, crypto, networking) happens in the JavaScript front-end. Tauri only provides the window, menu bar, file-system shims, and native notifications.

## Files

| Path              | Role                                                                                          |
| ----------------- | --------------------------------------------------------------------------------------------- |
| `Cargo.toml`      | Rust dependencies — Tauri runtime, any custom commands.                                       |
| `build.rs`        | Tauri's build script. Runs during `cargo build` to embed the web assets and window metadata.  |
| `tauri.conf.json` | App identity, window size, allowlist (which Tauri APIs the front-end can call), updater URL. |
| `src/main.rs`     | Entry point. Registers custom `#[tauri::command]` handlers and starts the Tauri builder.      |
| `icons/`          | Platform icons — `.icns` (macOS), `.ico` (Windows), and PNG sizes for Linux.                  |

## Building

Requires Rust stable + the Tauri CLI:

```bash
cargo install tauri-cli --version '^2.0'
cd src-tauri
cargo tauri dev                # live-reload during development
cargo tauri build              # release bundle (.app / .msi / .deb / .AppImage)
```

On macOS the build produces `src-tauri/target/release/bundle/macos/Vortex.app`.

## What lives here vs. the wizard

| Concern            | Tauri shell (`src-tauri/`)                        | Wizard bundle (`vortex_wizard/`)                 |
| ------------------ | ------------------------------------------------- | ------------------------------------------------ |
| Bundles the node?  | No — connects to an already-running node.         | Yes — PyInstaller ships everything in one binary. |
| Language           | Rust (native) + JS front-end.                     | Python + pywebview + bundled Python runtime.      |
| Intended for       | Daily-driver chat UI.                             | First-run operator setup.                         |
| Auto-update        | Yes — Tauri updater pulls signed bundles.         | No — manual replace.                             |

The two are independent releases; either can ship without the other.

## Config notes

- `tauri.conf.json` sets `identifier: "com.vortex.chat"`, `version: "1.0.0"`, and points the dev URL at `http://localhost:5173/` (vite-served mirror of `static/` + `templates/`).
- The production build reads its UI from `../static/` + `../templates/` via Tauri's asset protocol; no file-system access outside that sandbox.
- The updater endpoint is disabled by default — set `plugins.updater.endpoints` before you ship.

---

## License

Vortex is released under the **Apache License 2.0**.

```
Copyright 2026 Andrey Karavaev, Boris Maltsev

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

---

## Authors

**Boris Maltsev**

[![GitHub](https://img.shields.io/badge/GitHub-BorisMalts-181717?style=flat-square&logo=github)](https://github.com/BorisMalts)

**Andrey Karavaev**

[![GitHub](https://img.shields.io/badge/GitHub-Andre--wb-181717?style=flat-square&logo=github)](https://github.com/Andre-wb)
