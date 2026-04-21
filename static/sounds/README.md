# `static/sounds/` — Notification / UI Sounds

Short audio clips for notifications, calls, and UI feedback.

## Files (typical)

- `notification.ogg` / `.mp3` — new-message sound.
- `mention.ogg` — direct-mention sound.
- `call-ringing.ogg` — outgoing call loop.
- `call-incoming.ogg` — incoming call loop.
- `call-end.ogg` — call-end short.
- `join.ogg`, `leave.ogg` — voice-room affordances.
- `error.ogg` — error toast.

Both `.ogg` and `.mp3` variants ship — browsers pick whichever they can decode.

## Conventions

- All clips ≤ 2 seconds except the ringing loops.
- Normalised to −16 LUFS so no clip is noticeably louder than the others.
- Safe-for-work; no voice.
- Every clip is license-cleared for redistribution (CC0 / CC-BY source, noted in the commit message when added).

## Loading

Sounds are loaded by `../../js/notification-sounds.js` and played through an `AudioContext` with per-kind volume settings exposed in user settings.

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
