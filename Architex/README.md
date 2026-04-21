```
   █████╗ ██████╗  ██████╗██╗  ██╗██╗████████╗███████╗██╗  ██╗
  ██╔══██╗██╔══██╗██╔════╝██║  ██║██║╚══██╔══╝██╔════╝╚██╗██╔╝
  ███████║██████╔╝██║     ███████║██║   ██║   █████╗   ╚███╔╝
  ██╔══██║██╔══██╗██║     ██╔══██║██║   ██║   ██╔══╝   ██╔██╗
  ██║  ██║██║  ██║╚██████╗██║  ██║██║   ██║   ███████╗██╔╝ ██╗
  ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝
```

<h1 align="center">Architex</h1>

<p align="center">
  <b>A declarative UI language for Vortex Mini Apps — reactive state, composable layouts, zero build step.</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/TypeScript-5.4+-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript">
  <img src="https://img.shields.io/badge/Runtime-~30KB_gzip-06D6F0?style=for-the-badge" alt="Runtime size">
  <img src="https://img.shields.io/badge/Build_step-None-7C3AED?style=for-the-badge" alt="No build">
  <img src="https://img.shields.io/badge/License-MIT-D22128?style=for-the-badge" alt="License">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Declarative-yes-22c55e?style=flat-square" alt="Declarative">
  <img src="https://img.shields.io/badge/Reactive-fine--grained-22c55e?style=flat-square" alt="Reactive">
  <img src="https://img.shields.io/badge/Hosts-web_%2B_iOS_%2B_Android-22c55e?style=flat-square" alt="Hosts">
  <img src="https://img.shields.io/badge/Dependencies-0-22c55e?style=flat-square" alt="Zero deps">
</p>

---

## What is Architex?

Architex is a small declarative DSL designed to ship user interfaces inside the Vortex messenger as **Mini Apps**. You describe what the screen should look like; the runtime keeps pixels in sync with state automatically.

No virtual DOM. No bundler. No JSX. The `.arx` file **is** the app.

```architex
@screen Hello
  ~name = "world"

  col :: pad(24) gap(12) center
    header "Hello, {~name}!" :: bold size(28)
    input ~name :: pad(8) radius(6) border(#ccc)
    text "Type a name above." :: size(12) color(#888)
```

That's a complete, reactive screen. Save it, hit Run in the Vortex bot studio, watch it render.

---

## Table of Contents

- [1. Design goals](#1-design-goals)
- [2. Why Architex](#2-why-architex)
- [3. Install and run](#3-install-and-run)
- [4. Language at a glance](#4-language-at-a-glance)
  - [4.1 The four declarations](#41-the-four-declarations)
  - [4.2 Reactive and computed variables](#42-reactive-and-computed-variables)
  - [4.3 Components](#43-components)
  - [4.4 Modifiers](#44-modifiers)
  - [4.5 Actions](#45-actions)
- [5. Examples](#5-examples)
- [6. Runtime architecture](#6-runtime-architecture)
- [7. Host adapters](#7-host-adapters)
- [8. Comparison with other DSLs](#8-comparison-with-other-dsls)
- [9. Full reference](#9-full-reference)
- [10. Roadmap](#10-roadmap)
- [11. Project structure](#11-project-structure)
- [12. Contributing](#12-contributing)
- [13. License](#13-license)

---

## 1. Design goals

| Goal | What it means |
|------|---------------|
| **Declarative** | Describe the UI you want, not the steps to build it. |
| **Reactive** | `~count += 1` propagates to every label, class, and node that reads it. |
| **Portable** | The same `.arx` runs on web (vanilla DOM), iOS (SwiftUI), Android (Compose). |
| **Tiny** | Parser + renderer ship under 30 KB gzipped. Mini Apps open instantly. |
| **Readable** | Indentation is structure. Modifiers chain with `::`. No punctuation tax. |

Every construct in the language maps to one runtime primitive. There is no magic you can't explain.

---

## 2. Why Architex

Vortex Mini Apps needed a UI layer that:

1. **Opens fast** — chat users will not wait 1-2 seconds for a React bundle to parse.
2. **Works offline** — the chat itself works offline; a Mini App that fetches a framework before rendering would break parity.
3. **Runs the same bytes everywhere** — one `.arx` file has to render identically inside the web client, the iOS app, and the Android app, without per-platform forks.
4. **Is writable by non-frontend engineers** — bot authors shouldn't need to learn a component framework to make a screen.

We looked at every off-the-shelf option: React Native, Flutter, NativeScript, SwiftUI alone, Compose alone, plain HTML/CSS/JS. None met all four constraints together. So we designed a tiny DSL that does.

Architex is the cheapest possible UI layer that still feels modern: fine-grained reactivity, design tokens, composable components, native look on each host.

---

## 3. Install and run

### From the monorepo

```bash
cd Architex
npm install         # installs TypeScript 5.4+ (only dev dep)
npm run build       # emits dist/ with ESM + d.ts
```

### In a Mini App

```html
<script type="module">
  import { ArchiRuntime } from './dist/index.js';
  const runtime = new ArchiRuntime(document.getElementById('root'));
  runtime.load(await (await fetch('hello.arx')).text());
</script>
```

### In the Vortex bot studio

Pick the **Architex** tab. Paste a `.arx` file. Hit **Run**. The preview pane renders live and hot-reloads on every save. Publishing makes the Mini App available to any room in any Vortex client.

---

## 4. Language at a glance

### 4.1 The four declarations

| Syntax | Meaning |
|--------|---------|
| `@screen Name` | Declare a renderable screen — the root of a Mini App. |
| `@theme` | Define design tokens as reactive variables. |
| `@import "./file.arx"` | Pull components and screens from another file. |
| `@component Name args` | Define a reusable component with named parameters. |
| `@for item in ~list` | Render one child block per element of a reactive list. |

Each starts in column 0. Everything indented below belongs to that block. Indentation is strict: 2 spaces per level, no tabs.

### 4.2 Reactive and computed variables

Reactive variables start with `~`:

```architex
~count = 0
~name: string = "world"
~items: array = ["a", "b", "c"]
```

Computed variables use `:=` and re-evaluate when any dependency changes:

```architex
~total := ~count * ~step
~greeting := "Hello, {~name}!"
```

No subscriptions. No stale-value bugs. If an expression reads `~a`, the expression automatically depends on `~a`.

### 4.3 Components

Containers: `col` (vertical), `row` (horizontal). Leaf components include `text`, `header`, `label`, `button`, `input`, `image`, `icon`, `avatar`, `badge`, `divider`, `toast`, `tabs`, `video`, `audio`, `spinner`.

```architex
row :: gap(8) pad(16) center
  image "/avatar.png" :: w(40) h(40) radius(20)
  col :: grow gap(2)
    text ~name :: bold
    text ~bio  :: size(12) color(#888)
```

Indentation nests. No closing tags. Children walk naturally into the tree.

### 4.4 Modifiers

Chain after `::`. Five families: spacing, sizing, colour, typography, visibility, behaviour.

```architex
button "Save" :: pad(12, 18) bg(~primary) color(#fff) radius(8) bold
input ~email  :: placeholder("you@example.com") debounce(300)
text ~total   :: format("currency", "USD")
col :: visible(~show) animate(200, ease-out)
```

Unknown modifiers are parse errors — strict by design to protect forward compatibility.

### 4.5 Actions

After `=>`. Chain multiple for sequences.

```architex
button "Buy" =>
  ~busy = true =>
  send(action: "buy") =>
  ~busy = false
```

Host built-ins cover clipboard, sharing, haptics, navigation, modals, lifecycle:

```architex
button "Copy invite" => copy(~invite) => toast = true
button "Profile"     => goto("Profile", user: ~me)
button "Delete"      => confirm("Sure?") => ~remove = it
```

---

## 5. Examples

Four canonical Mini Apps ship in `examples/`. Each is under 40 lines and stress-tests a different part of the language.

| File | Teaches |
|------|---------|
| `counter.arx` | Reactive state, computed, button handlers, text binding. |
| `todo.arx` | List rendering, add / remove, inline editing. |
| `profile.arx` | Image, badges, conditional visibility, navigation. |
| `killer_features.arx` | Themes, imports, tabs, toasts, formatted numbers, ternaries, typed variables, multi-handler buttons. |

### Counter

```architex
@screen Counter
  ~count = 0
  ~step  = 1
  ~total := ~count * ~step

  col :: pad(24) gap(16) center
    header "Counter" :: bold size(28)
    text ~count :: size(64) bold center color(#4f8ef7)

    row :: gap(12) center
      button "−" :: pad(12) radius(8) bg(#f0f0f0) => ~count -= 1
      button "Reset" :: pad(12) radius(8) bg(#ffe0e0) => ~count = 0
      button "+" :: pad(12) radius(8) bg(#e0f0e0) => ~count += 1

    divider

    row :: gap(8) center
      label "Step:"
      input ~step :: w(60) pad(8) radius(6)

    text ~total :: size(14) color(#888) center
```

Copy this into `examples/counter.arx` or the Architex tab — it runs.

---

## 6. Runtime architecture

The Architex runtime is a TypeScript package with four modules:

```
Architex/
└── src/
    ├── lexer/       scans source text → tokens
    ├── parser/      tokens → typed AST
    ├── ast/         AST node types
    ├── reactive/    dependency tracking + batched updates
    ├── renderer/    walks AST, delegates to host
    └── runtime/     orchestrates lexer + parser + reactive + renderer
```

**Pipeline:**

```
  source.arx
      │
      ▼
  lexer.scanLines(source)
      │
      ▼  Token[]
  parser.parse(tokens) → Program
      │
      ▼
  parser.buildTree(program) → Node
      │
      ▼
  renderer.renderNode(node, ctx) ─► host primitives
      │
      ▼
  reactive.createState() links reads and writes
```

Reactivity is **fine-grained**. Only components that read the changed cell re-render. No virtual DOM diff. Writes are batched within a microtask, so `=> ~a = 1 => ~b = 2` triggers exactly one render pass.

Equality is strict (`===`). Writing the same value re-runs nothing. Assign a new array or object to force updates — immutability is encouraged but not required.

---

## 7. Host adapters

A host implements a narrow interface: `createNode`, `updateNode`, `removeNode`, plus modifier application. Adding a new host takes roughly 500 lines of glue code.

| Host | Primitive it renders into | Notes |
|------|---------------------------|-------|
| **Web** | Vanilla DOM with CSS custom properties | Theme tokens become CSS variables. |
| **iOS** | SwiftUI views | Every modifier maps to a SwiftUI style. |
| **Android** | Jetpack Compose | Gesture modifiers → Compose equivalents. |

The same `.arx` runs identically on all three. We don't ship per-host forks; we maintain one source tree plus three small adapter modules.

---

## 8. Comparison with other DSLs

|                        | Architex | SwiftUI | Compose | React Native | Flutter |
|------------------------|----------|---------|---------|--------------|---------|
| Runtime size           | ~30 KB   | —       | —       | ~600 KB      | ~5 MB    |
| Build step             | no       | yes     | yes     | yes          | yes      |
| Portable across iOS + Android + web | yes | no      | no      | partial      | yes      |
| Reactive state by default | yes   | yes     | yes     | no (state libs) | no    |
| Declarative            | yes      | yes     | yes     | yes          | yes      |
| Writable by non-frontend | yes    | no      | no      | no           | no       |

Architex is **smaller** than every alternative because its scope is narrower: chat-embedded Mini Apps only. You will not replace a full native app with Architex; you will ship a screen inside Vortex in a tenth the time.

---

## 9. Full reference

The complete language reference lives in the Vortex docs site:

- **`architexDocs`** — language intro, quick start, syntax, components, modifiers, examples (141 sections).
- **`arxd`** — deep reference with per-topic accordions (~800 sections, covers navigation, forms, animations, media, network, accessibility, performance, runtime, compiler, testing, debugging, migration, FAQ, gotchas).

Both ship inside every Vortex locale JSON (146 languages) and render through the docs page at `docs.html` in the introduce site.

Source of truth for rebuilds:

```
Vortex/scripts/build_architex_docs.py     # flat architexDocs
Vortex/scripts/build_architex_arxd.py     # nested arxd
```

---

## 10. Roadmap

- **v0.2** — `@component slot` stable, animations DSL, theme nesting.
- **v0.3** — stream / async iterators, form validation as a first-class modifier family.
- **v0.4** — WASM compiler target for hosts without JavaScript (Ktor, native iOS).
- **v1.0** — formal grammar freeze, backward compatibility guarantee within 1.x.

---

## 11. Project structure

```
Architex/
├── package.json           typescript devDep only; zero runtime deps
├── tsconfig.json
├── src/
│   ├── index.ts           public API
│   ├── lexer/
│   │   ├── index.ts
│   │   ├── scanner.ts     indentation-sensitive line scanning
│   │   ├── tokeniser.ts   token production
│   │   └── tokens.ts      Token / T enum
│   ├── parser/
│   │   ├── index.ts
│   │   ├── actions.ts     => handler parsing
│   │   ├── modifiers.ts   :: modifier chain parsing
│   │   ├── stream.ts      token stream helpers
│   │   ├── tree.ts        AST builder
│   │   └── values.ts      value expression parsing
│   ├── ast/               typed AST nodes
│   ├── reactive/          state cells + dependency tracking
│   ├── renderer/          walks AST, calls host primitives
│   └── runtime/           glue: ArchiRuntime class
├── examples/
│   ├── counter.arx
│   ├── todo.arx
│   ├── profile.arx
│   └── killer_features.arx
└── dist/                  emitted by `npm run build`
```

---

## 12. Contributing

The language is small on purpose. Before adding a modifier or component, consider whether it can be expressed as a user-space `@component`. Syntactic additions must match three tests:

1. It cannot be implemented in user space with existing primitives.
2. It composes cleanly with every other modifier family.
3. Every supported host can map it to a native primitive without faking.

PRs welcome. Discussions and issues go through the main Vortex repo. Every addition needs:

- Parser test (`src/parser/__tests__/`)
- Renderer test against at least the web host
- Documentation entry in `arxd` (one leaf key per sub-topic)
- An example file under `examples/` if it's user-visible

---

## 13. License

MIT. See `LICENSE` in the Vortex root.

---

<p align="center">
  <b>Architex is part of the Vortex project.</b><br/>
  <sub>Language designed for Mini Apps shipping inside a decentralised messenger.</sub>
</p>

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
