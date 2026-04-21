# `Architex/src/parser/` — Parser

Token stream → AST. Indentation-driven (off-side rule). Single pass, no backtracking.

## Responsibilities

- Consume the token stream from `../lexer/`.
- Produce `../ast/` node trees — one root per `@screen` / `@component` declaration.
- Enforce grammar (arity of modifiers, shape of declarations).
- Track source positions so errors point at the right line.

## Grammar sketch

```
File         := Declaration+ EOF
Declaration  := Screen | Component
Screen       := "@screen" Ident Indent Body Dedent
Component    := "@component" Ident "(" Param* ")" Indent Body Dedent
Body         := (StateDecl | EffectDecl | Element)+
StateDecl    := "~" Ident "=" Expr
EffectDecl   := "@effect" Indent Expr Dedent
Element      := Tag ModifierList? Indent Body? Dedent
Tag          := Ident | Ident "(" Args ")"
ModifierList := "::" Modifier (Modifier)*
Modifier     := Ident ("(" Args ")")?
```

## Error recovery

On an unexpected token the parser:

1. Emits a `ParseError` with position.
2. Skips to the next dedent (to stay synchronised with indentation).
3. Continues — so one broken screen doesn't kill the whole file.

Errors bubble up to the runtime, which renders an in-page red overlay during development.

## Output

Single entry point: `parse(tokens: Token[]): File`. Returns the AST root or throws if the token stream is unrecoverable.

## Testing

`__tests__/parser.test.ts` — golden AST snapshots for a curated set of `.arx` fixtures.

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
