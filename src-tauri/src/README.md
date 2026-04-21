# `src-tauri/src/` — Tauri Rust Source

Rust source for the desktop shell. Minimal — Tauri handles the heavy lifting; this code only sets up the window, registers custom commands (if any), and launches the event loop.

## Files

| File      | Role                                                                                |
| --------- | ----------------------------------------------------------------------------------- |
| `main.rs` | Entry point. Builds the Tauri app, registers any `#[tauri::command]` handlers, starts the event loop. |

## Typical shape

```rust
fn main() {
    tauri::Builder::default()
        .setup(|app| { /* optional custom init */ Ok(()) })
        .invoke_handler(tauri::generate_handler![/* commands */])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

## Commands

Currently none — the front-end talks to Vortex over HTTP/WebSocket directly. If a future feature needs privileged filesystem / OS access (e.g. clipboard history, native notifications with custom actions), add a `#[tauri::command]` here and whitelist it in `../tauri.conf.json`.

## Building

See [`../README.md`](../README.md).

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
