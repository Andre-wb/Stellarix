# `Architex/src/renderer/` — Pluggable Renderers

Turns the reactive element tree produced by `../runtime/` into actual output. Three renderers ship in-box; adding a fourth is a one-file exercise.

## Renderers

| Renderer     | Target                                                                  | Use case                                |
| ------------ | ----------------------------------------------------------------------- | --------------------------------------- |
| `html/`      | DOM — creates real `HTMLElement`s, wires events, sets styles.           | Browser (the web client).               |
| `native/`    | Opaque view descriptor tree — `{ kind, props, children }` JSON.         | iOS + Android clients; they translate descriptors into real `UIView` / Compose nodes. |
| `diff/`      | Headless diff output — arrays of "create / update / remove" patches.    | Tests, SSR, bot-driven verification.    |

## Interface

Every renderer exports:

```ts
interface RendererRoot {
  mount(element: ReactiveElement): Handle;
  update(handle: Handle, element: ReactiveElement): void;
  unmount(handle: Handle): void;
}
```

The `runtime/` wraps every update inside an `effect()` so the renderer's `update` is called only when reactive dependencies actually change.

## Modifier translation

Every renderer translates the abstract modifier set (`pad(n)`, `gap(n)`, `radius(n)`, `bold`, `center`, `color(#fff)`, …) into its native equivalent:

- HTML → inline CSS (prefixed custom properties, no runtime CSS-in-JS).
- Native → structured props (`{ kind: "col", pad: 8, gap: 12 }`).
- Diff → echoes the abstract modifier verbatim.

## Testing

Each renderer has its own `__tests__/`. The `diff` renderer is particularly useful — a deterministic output lets us assert exact reactive behaviour without a DOM or a device.

## Adding a renderer

```ts
// renderer/my-target/index.ts
export const myRenderer: RendererRoot = {
  mount(el)  { /* build native handle */ },
  update(h, el) { /* apply reactive updates */ },
  unmount(h) { /* tear down */ },
};
```

Register it in `index.ts` and the `runtime/` picks it up via the `target` parameter to `mount()`.

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
