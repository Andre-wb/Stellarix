# `templates/components/` — Reusable Template Fragments

Jinja2 fragments included across screens. Each file is a self-contained snippet — pure markup, no logic beyond `{% if %}` and `{{ t(...) }}` i18n lookups.

## Files

| File                     | Where it's used                                                        |
| ------------------------ | ---------------------------------------------------------------------- |
| `sidebar.html`           | Chat shell left rail — room list, spaces switcher, search button.      |
| `bottom_tabs.html`       | Mobile tab bar — Chat / Contacts / Calls / Bots / Settings.           |
| `room_info_panel.html`   | Right rail opened on any room — members, files, pinned, settings.      |
| `thread_panel.html`      | Slide-in thread view over any room.                                    |
| `stream.html`            | Live-stream player + chat layout.                                      |
| `group_call.html`        | Group call tile grid.                                                  |
| `profile_modal.html`     | Self profile edit modal.                                               |
| `user_profile_modal.html`| Another user's profile viewer.                                         |
| `fingerprint_modal.html` | Key fingerprint verification modal (QR + text + challenge).           |
| `lang_picker.html`       | Language selector dropdown, powered by `../../static/js/lang-picker.js`. |
| `pin_lock.html`          | Lock screen (app-level PIN for privacy).                               |
| `contact_sync.html`      | Contact-sync opt-in flow.                                              |
| `birthday_picker.html`   | Birthday picker used in profile edit.                                  |
| `doc_viewer.html`        | Inline document viewer (PDF / markdown / txt).                         |
| `page_viewer.html`       | Inline full-page viewer used by the docs portal.                       |
| `inline_scripts.html`    | Allowed inline `<script>` bootstrapper (CSP-nonced). Contains the boot glue that sets up global namespaces. |

## Conventions

- Components never `{% extends %}` — only screens do.
- A component may `{% include %}` another component, but try to keep the tree shallow.
- All user-visible strings go through `{{ t("key.name") }}`. Never `hello, world` in markup.
- Accessibility is mandatory: every interactive element has a text label; focus order makes sense.
- Components expose their JS counterparts by data attributes (`data-component="sidebar"`), which the corresponding module in `../../static/js/` picks up on DOMContentLoaded.

## Adding a component

1. Create the `.html` file here.
2. If it has matching JS, add a module under `../../static/js/` with the same stem.
3. Include it from the relevant screen via `{% include "components/<name>.html" %}`.
4. Add a one-line entry to this README's table.

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
