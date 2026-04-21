# `Gravitix/src/interpreter/` — AST Evaluator

AST-walking interpreter. Takes an `Ast` from the parser and evaluates it against a mutable `Environment`.

## Responsibilities

- Walk every AST node; produce a `Value`.
- Maintain lexical scope (let-bindings, closures, parameter shadowing).
- Run `on /command` handlers when dispatched by `../bot/`.
- Evaluate flow control — `if`, `match` with patterns + guards, `for`, `while`, `loop`, `break`, `continue`.
- Evaluate pipe operator `|>`, lambdas, pattern destructuring.
- Dispatch to `../stdlib/` for built-ins and to `../bot/` for runtime-backed functions.

## Hot path

The evaluator is designed to be cheap in the common bot case:

- **Single dispatch** — no dynamic dispatch table, match on `AstNode` variants.
- **Arena scope** — variables are slots in a `Vec<Value>` indexed at parse time; no hash lookups in hot code.
- **Tail calls** become loops at the interpreter level (explicit handling for simple cases).

## Sandboxing hooks

Every evaluator call is checked against:

- `instruction_budget` — hard cap on AST nodes evaluated per handler run.
- `wall_time_budget` — handler is killed if evaluation takes too long.
- `max_heap` — list / map growth beyond this aborts the handler.

Budgets come from `../bot/` configuration; the interpreter itself doesn't know about users or tenants.

## Testing

Interpreter-focused tests live in `../../tests/interpreter_*.rs`:

- `interpreter_control_flow.rs` — if / match / for / while / loop / break / continue.
- `interpreter_closures.rs` — capture semantics, partial application.
- `interpreter_patterns.rs` — pattern matching + guards.
- `interpreter_errors.rs` — error propagation, recovery, positions.

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
