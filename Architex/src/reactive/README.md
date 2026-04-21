# `Architex/src/reactive/` — Fine-grained Reactivity

Signal + computed + effect primitives. The foundation every `.arx` program's state lives in.

## API

```ts
function signal<T>(initial: T): [() => T, (next: T) => void];
function computed<T>(fn: () => T): () => T;
function effect(fn: () => void): () => void;   // returns dispose
function batch<T>(fn: () => T): T;              // group updates into one notify round
function untrack<T>(fn: () => T): T;            // read without subscribing
```

## Model

- Every read of a signal inside an `effect` / `computed` **subscribes** that reactive context to the signal.
- Every write to a signal **schedules** every subscribed context to run.
- Dependencies are re-computed each run — stale subscriptions are pruned automatically.
- `batch` collapses multiple writes into a single notify pass — no subscriber runs more than once per batch.
- `untrack` is for side-channel reads that must not create a dependency (e.g. logging).

## Runtime integration

The Architex interpreter wraps every `~name = expr` declaration in a `signal`, every template expression in a `computed`, and every `@effect` block in an `effect`. DOM / native updates happen inside an `effect` that reads the reactive element tree, so only the exact node that reads a signal re-renders when that signal changes — no VDOM diffing.

## Performance

- O(1) subscribe + unsubscribe.
- No object allocation per read after the first run.
- Scales to tens of thousands of signals without noticeable overhead (tested on an iPad Mini 5).

## Testing

`__tests__/reactive.test.ts` — chain of signals → computed → effects, testing correctness + prune behaviour under rapid updates.

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
