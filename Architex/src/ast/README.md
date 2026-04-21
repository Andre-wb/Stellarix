# `Architex/src/ast/` — AST Types & Walker

Typed AST nodes for an Architex program + a visitor-pattern walker. No evaluation logic — the runtime lives in `../runtime/`.

## Node kinds

```ts
type Node =
  | File           // root — a parsed .arx file
  | Screen         // @screen Name
  | Component      // @component Name(params)
  | StateDecl      // ~foo = expr
  | EffectDecl     // @effect ...
  | Element        // col / row / text / … + modifiers + children
  | Modifier       // pad(8), bold, color(#fff)
  | Expr           // literal, ident, call, interpolation
  | …
```

## Walker

```ts
interface Visitor<T> {
  visitScreen?(node: Screen, ctx: T): void;
  visitComponent?(node: Component, ctx: T): void;
  visitElement?(node: Element, ctx: T): void;
  visitExpr?(node: Expr, ctx: T): void;
  …
}

walk<T>(root: File, visitor: Visitor<T>, ctx: T): void;
```

The walker is depth-first pre-order. Visitors can return `false` from any hook to skip descent.

## Why a separate folder

- The runtime's evaluator is ~600 lines. Keeping AST types next to it would bloat imports for tests and tools (linters, formatters) that only need the shape.
- Any future visualiser / printer / formatter lives here too.

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
