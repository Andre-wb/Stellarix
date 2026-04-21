# `Gravitix/examples/` — Example `.grv` Bots

Reference bots showcasing every Gravitix feature. Each file is runnable via the `gravitix` CLI or via the in-browser IDE.

## Running

```bash
cd Gravitix
cargo run --release -- run examples/hello.grv
# or via the IDE in the Vortex web client
```

## Selected examples

| File                    | Teaches                                                  |
| ----------------------- | -------------------------------------------------------- |
| `hello.grv`             | The canonical `on /start { emit "Hello!" }`.            |
| `todo_list.grv`         | Persistent state across invocations.                    |
| `todo_fsm.grv`          | FSM / flows for multi-step conversations.               |
| `poll_bot.grv`          | Poll composer with per-user vote tracking.              |
| `weather.grv`           | Allow-listed HTTP fetch + response card.                |
| `moderator.grv`         | `on join / on message` event handlers + pattern-matched ban triggers. |
| `scheduler.grv`         | `on schedule("0 9 * * *")` daily digest.                |
| `math_stats.grv`        | Demonstrates `math_stats.*` stdlib usage.                |
| `pipe.grv`              | Pipe operator and lambdas.                              |
| `match.grv`             | Pattern matching and guards.                            |
| `miniapp.grv`           | `emit screen "MyApp"` — hands off to an Architex Mini App. |

## Conventions

- One concept per file.
- Start each file with a one-line comment: `# Demonstrates: <concept>`.
- No external secrets. Examples use obviously fake endpoints / keys.

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
