# `Architex/examples/` — Example `.arx` Mini Apps

Reference apps showcasing each Architex language feature. Every file is runnable via the Vortex IDE's preview pane — paste into the IDE, hit Run.

## Files

| File                    | Demonstrates                                                     |
| ----------------------- | ---------------------------------------------------------------- |
| `counter.arx`           | The canonical Hello-world — `~count` signal + increment button.  |
| `todo.arx`              | List state, add / remove / toggle, `computed` for the footer count. |
| `form.arx`              | Multi-field form, `~valid` computed, submit handler.             |
| `router.arx`            | Nested `@screen`s routed by `~route` signal. Demonstrates conditional mounts. |
| `components.arx`        | Defines + uses `@component Card(title, body)`.                   |
| `theme.arx`             | Theming via CSS custom-property bindings.                         |
| `modifiers.arx`         | Every built-in modifier — `pad`, `gap`, `radius`, `bold`, `center`, `color`, `border`. |
| `list.arx`              | Virtualised list using the `each` primitive.                     |
| `effect.arx`            | `@effect` with cleanup — a setInterval that tears down on unmount. |
| `interpolation.arx`     | String interpolation, nested signals, computed helpers.           |

## Running

```bash
# Inside the Vortex IDE
1. Open the IDE (web client → "/ide")
2. New project → "Architex"
3. Paste a .arx example into the editor
4. Click Run
```

Or headlessly via the Node-side compiler:

```bash
cd Architex
npm test -- examples/counter.arx       # lexer + parser + runtime smoke
```

## Contributing examples

- Keep each example small — one concept per file.
- Prefer built-in modifiers over custom components unless the example is *about* components.
- Comment sparingly — the code should explain itself. A one-line `# …` header per file is fine.

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
