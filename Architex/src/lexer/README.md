# `Architex/src/lexer/` — Tokeniser

Turns `.arx` source text into a flat token stream. Zero dependencies, one pass, no lookahead beyond a single character.

## Responsibilities

- Recognise keywords: `@screen`, `@component`, `@state`, `@effect`, `col`, `row`, `stack`, `text`, `input`, …
- Recognise modifiers after `::` — `pad(n)`, `gap(n)`, `radius(n)`, `bold`, `center`, `color(#...)`, …
- String interpolation: `"Hello, {~name}!"` splits into `StringStart / Expr / StringEnd`.
- Indent / dedent tokens drive the off-side parser.
- Comments — `#` to end of line — are stripped before emission.
- Numbers (int + float), colours (`#RRGGBB` / `#RGB`), identifiers.

## Output shape

```ts
type Token =
  | { kind: "ident"; value: string; pos: Pos }
  | { kind: "number"; value: number; pos: Pos }
  | { kind: "string_start"; pos: Pos }
  | { kind: "string_part"; value: string; pos: Pos }
  | { kind: "string_expr_open"; pos: Pos }
  | { kind: "string_expr_close"; pos: Pos }
  | { kind: "string_end"; pos: Pos }
  | { kind: "punct"; value: string; pos: Pos }     // ::, =, ~, @, (, ), ,
  | { kind: "indent"; level: number; pos: Pos }
  | { kind: "dedent"; level: number; pos: Pos }
  | { kind: "eof"; pos: Pos };
```

## Errors

Lexer errors are recoverable — an invalid character yields an `InvalidToken` and the lexer skips ahead. The parser decides whether this is fatal.

## Testing

Unit tests live in `__tests__/lexer.test.ts`. Snapshot-based: a fixture `.arx` file vs. its expected token stream.

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
