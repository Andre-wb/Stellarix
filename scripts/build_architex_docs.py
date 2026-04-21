#!/usr/bin/env python3
"""
Build the `architexDocs` i18n block and splice it into every relevant
locale file. Single source of truth for Architex language reference.

Targets:
  * ios/Modules/Sources/I18N/Resources/locales/en.json         (iOS app)
  * vortex-introduce-page/locales/*.json                       (all 146 locales)

For non-English locales we copy the English text verbatim — user asked
"остальное просто скопируй". A future automated translator can walk the
same `architexDocs` key path and overwrite in-place.
"""
from __future__ import annotations

import json
from pathlib import Path


ARCHITEX_DOCS: dict = {
    "title": "Architex Language Reference",
    "subtitle": "A declarative UI language for Vortex Mini Apps. Reactive state, composable layouts, zero build step.",

    # ── Intro ──────────────────────────────────────────────────────
    "intro": "What is Architex?",
    "introDesc": "Architex is a small declarative DSL designed to ship UI inside the Vortex messenger. You describe what the screen should look like; the runtime keeps pixels in sync with state automatically. No virtual DOM, no bundler, no JSX — the `.arx` file is the app.",
    "designGoals": "Design goals",
    "goalDeclarative": "Declarative — you write the UI you want, not the steps to build it",
    "goalReactive": "Reactive — `~count += 1` and every label that reads it updates in place",
    "goalPortable": "Portable — the same `.arx` runs on web, iOS, and Android runtimes without edits",
    "goalTiny": "Tiny — parser + renderer ship in under 30 KB, so Mini Apps open instantly",
    "goalReadable": "Readable — indentation is structure; modifiers are chained with `::`; there is no punctuation tax",
    "whoIsThisFor": "Who is this for?",
    "whoDesc": "Anyone who wants to ship an interactive screen in Vortex — customer forms, dashboards, voting pages, Telegram-style Mini Apps. If you have ever written HTML+CSS+JS, Architex will feel familiar but faster to write. If you haven't, Architex is also a gentle introduction to reactive programming because the language keeps the footprint small.",
    "howToRead": "How to read this reference",
    "howToReadDesc": "Each section builds on the one before. Start at Quick Start, then read Syntax, State, Layout, Modifiers, Actions, and the advanced section last. Jump around via the table of contents if you already know React or Svelte — the concepts map cleanly.",

    # ── Quick Start ────────────────────────────────────────────────
    "quickStart": "Quick Start",
    "quickStartDesc": "The shortest path from a blank file to a running Mini App.",
    "yourFirstScreen": "Your first screen",
    "firstScreenExample": """@screen Hello

  ~name = "world"

  col :: pad(24) gap(12) center

    header "Hello, {~name}!" :: bold size(28)

    input ~name :: pad(8) radius(6) border(#ccc)

    text "Type a name above — this text updates as you type."
      :: size(12) color(#888)""",
    "whatHappened": "What just happened?",
    "whatHappenedDesc": "`@screen Hello` declares the root. `~name = \"world\"` creates a reactive variable. `col`, `header`, `input`, `text` are built-in components. `::` attaches modifiers (padding, colours, size). When the user types into the input, every `{~name}` interpolation updates — no wiring, no subscriptions, no renders by hand.",
    "runningIt": "Running the screen",
    "runningItDesc": "Open the Architex tab in the Vortex bot studio, paste the code, press Run. The runtime renders into the preview pane and hot-reloads on save. When you publish, your users open the app from any chat — no installs.",

    # ── Syntax at a glance ─────────────────────────────────────────
    "syntaxAtGlance": "Syntax at a Glance",
    "syntaxDesc": "Every Architex program is made of four things: declarations that start with `@`, reactive variables prefixed with `~`, components written as bare identifiers, and modifiers attached after `::`.",
    "anatomyDecl": "Anatomy of a declaration",
    "anatomyDeclDesc": "`@screen Name`, `@theme`, `@import \"./lib.arx\"`, and `@for item in ~list` all start in column 0. Everything indented below them belongs to that block.",
    "anatomyComp": "Anatomy of a component",
    "anatomyCompDesc": "Components sit on their own line: `text`, `button`, `image`, `header`, `label`, `badge`, `divider`, `col`, `row`. Their positional argument comes right after the name: `text ~message`, `button \"Save\"`, `image \"/logo.png\"`.",
    "anatomyModifier": "Anatomy of a modifier chain",
    "anatomyModifierDesc": "After `::` you can chain as many modifiers as you like. Each takes zero or more arguments in parentheses: `:: pad(24) gap(16) center bold size(20) color(#4f8ef7)`. Modifiers are positional, not keyword — order does not matter except for the last-writer-wins ones like `color`.",
    "anatomyAction": "Anatomy of an action",
    "anatomyActionDesc": "`=>` on a button (or any interactive component) runs the assignment or function call that follows. Multiple `=>` chain side-by-side: `button \"Submit\" => ~busy = true => send(action: \"save\", data: ~form)`.",

    # ── Variables & types ─────────────────────────────────────────
    "variablesAndTypes": "Variables & Types",
    "reactiveVars": "Reactive variables",
    "reactiveVarsDesc": "Any name prefixed with `~` is a reactive cell. Write `~count = 0` to declare, `~count = 5` to re-assign, `~count += 1` to update. Every UI node that reads the cell — directly or via interpolation — re-renders when the cell changes.",
    "computedVars": "Computed variables",
    "computedVarsDesc": "Use `:=` instead of `=` to declare a computed expression: `~total := ~count * ~step`. The right-hand side re-evaluates whenever any dependency changes. There is no manual subscription and no stale-value bug — if you read `~a` somewhere in the expression, you automatically depend on it.",
    "typeAnnotations": "Type annotations",
    "typeAnnotationsDesc": "Annotations are optional but help with autocomplete and error messages: `~count: number = 0`, `~name: string = \"\"`, `~ok: boolean = false`, `~items: array = []`, `~user: object = {}`. If you skip them the type is inferred from the initialiser.",
    "supportedTypes": "Supported types",
    "supportedTypesList": "`number`, `string`, `boolean`, `array`, `object`, `null`. Dates and blobs are passed through as strings and objects respectively. The runtime uses JavaScript's coercion rules under the hood, so `~count + 1` works even if `~count` started life as a string.",
    "stringInterpolation": "String interpolation",
    "stringInterpolationDesc": "Any string can embed expressions with `{...}`: `\"Hello, {~user.name}!\"`, `\"Total: {~count * ~price}\"`. Interpolation is always reactive.",

    # ── Layout ─────────────────────────────────────────────────────
    "layout": "Layout",
    "layoutDesc": "Architex has two composable containers and a dozen leaf components. Nest them with indentation — no closing tags.",
    "containers": "Containers: col and row",
    "containersDesc": "`col` stacks children vertically, `row` horizontally. Both accept `gap(n)`, `pad(n)`, `center`, `grow`, and a width/height modifier. Indent children one level deeper to nest.",
    "containerExample": """row :: gap(8) pad(16) center
  image "/avatar.png" :: w(40) h(40) radius(20)
  col :: grow gap(2)
    text ~name :: bold
    text ~bio  :: size(12) color(#888)""",
    "leafComponents": "Leaf components",
    "leafComponentsList": "`text` — any body copy. `header` — semantically a heading. `label` — small caption text. `button` — tap-able control. `input` — text field bound to a reactive var. `image` — picture from a URL. `badge` — pill-shaped tag. `divider` — thin separator line. `toast` — ephemeral snackbar. `tabs` / `tab` — tab switcher.",
    "componentText": "text",
    "componentTextDesc": "`text \"Hello\"` renders a static string. `text ~message` renders a reactive one. Combine with interpolation: `text \"Total: {~count}\"`.",
    "componentHeader": "header",
    "componentHeaderDesc": "Heading text. Defaults to larger, bolder than `text`. Same positional argument: `header \"Settings\"`. Size scales with screen — override with `size(n)`.",
    "componentButton": "button",
    "componentButtonDesc": "Tap-able element. The positional string is the label; the `=>` action runs on tap. `button \"Save\" => ~draft = null`. Multiple `=>` fire in order.",
    "componentInput": "input",
    "componentInputDesc": "Two-way-bound text field. The reactive variable after the name holds the current value: `input ~email`. Modifiers: `placeholder(\"…\")`, `debounce(300)` for throttled updates.",
    "componentImage": "image",
    "componentImageDesc": "Loads from an HTTPS URL or `/uploads/...` path. Modifiers `w(px)`, `h(px)`, `radius(px)` trim the box. Falls back to a placeholder silhouette if the URL 404s.",
    "componentDivider": "divider",
    "componentDividerDesc": "Hairline separator, 1px, honours the current theme colour. No arguments.",
    "componentBadge": "badge",
    "componentBadgeDesc": "Pill that hugs its content: `badge ~count`, `badge \"new\"`. Use for unread counters and tag chips.",
    "componentLabel": "label",
    "componentLabelDesc": "Caption/helper text — visually subdued. Good for form field names.",
    "componentToast": "toast",
    "componentToastDesc": "Non-blocking notification. `toast ~visible \"Saved!\" :: duration(2000)` shows for 2 s whenever `~visible` is true, then auto-dismisses. No modal stacking, no z-index wars.",
    "componentTabs": "tabs / tab",
    "componentTabsDesc": "Tab container bound to a reactive string: `tabs ~activeTab`. Inside it, each `tab \"Label\" \"key\"` declares one tab; the body indented beneath is shown when the key matches.",

    # ── Modifiers ──────────────────────────────────────────────────
    "modifiers": "Modifiers",
    "modifiersDesc": "Modifiers are the only way to style a component. Chain them after `::`. They come in five families: spacing, sizing, colour, typography, and behaviour.",
    "modSpacing": "Spacing",
    "modSpacingDesc": "`pad(n)` — padding on all sides. `pad(x, y)` — horizontal + vertical. `pad(top, right, bottom, left)` — CSS-order. `gap(n)` — space between children of a `col` / `row`. `margin(n)` — outer spacing from siblings.",
    "modSizing": "Sizing",
    "modSizingDesc": "`w(px)` — fixed width. `h(px)` — fixed height. `grow` — fill remaining space in a row/col. `center` — centre along the cross axis; in a `col` it centres horizontally, in a `row` it centres vertically.",
    "modColour": "Colour",
    "modColourDesc": "`color(#rrggbb)` — foreground. `bg(#rrggbb)` — background. Both accept theme tokens: `color(~primary)` reads from the current `@theme` block. Opacity goes through an 8-digit hex: `#00000080` is 50 %% black.",
    "modTypography": "Typography",
    "modTypographyDesc": "`size(px)` — font size. `bold` / `italic` — weight and style. `align(left|center|right)` — text alignment.",
    "modVisibility": "Visibility",
    "modVisibilityDesc": "`hidden(~flag)` — unmounts the node when the flag is true. `visible(~flag)` — inverse. Unmounted nodes shed their DOM, so conditional UI is cheap.",
    "modBehaviour": "Behaviour",
    "modBehaviourDesc": "`debounce(ms)` on `input` throttles updates. `placeholder(\"…\")` shows a hint string. `format(kind, arg)` on `text` formats a number: `format(\"currency\", \"USD\")`, `format(\"percent\")`, `format(\"compact\")`.",
    "modRadius": "Radius and border",
    "modRadiusDesc": "`radius(px)` rounds corners. `border(#rrggbb)` draws a 1 px stroke. `border(px, #rrggbb)` sets thickness too.",

    # ── Actions ────────────────────────────────────────────────────
    "actions": "Actions",
    "actionsDesc": "Actions mutate state or talk to the outside world. They run synchronously in the tap/keypress handler.",
    "actionAssign": "Assignment",
    "actionAssignDesc": "`=> ~count = 0`, `=> ~busy = true`, `=> ~list = []`. Any reactive variable is writable.",
    "actionIncDec": "Increment / decrement",
    "actionIncDecDesc": "`+= n`, `-= n`, `*= n`, `/= n`. `=> ~count += 1` is idiomatic for counters.",
    "actionMultiple": "Chaining actions",
    "actionMultipleDesc": "Multiple `=>` on the same line fire top-to-bottom in the same tick, so the UI updates once at the end: `button \"Buy\" => ~busy = true => send(action: \"buy\") => ~busy = false`. For async work, prefer a computed `@reaction`.",
    "actionSend": "Sending messages",
    "actionSendDesc": "`send(action: \"name\", ...args)` is the bridge back to the bot. The host (Vortex runtime) receives it as a JSON RPC message and can call your bot's code. Use it for login, API fetches, payments — anything the DSL itself can't express.",
    "actionNavigate": "Navigation",
    "actionNavigateDesc": "`goto(\"ScreenName\", arg: value, ...)` pushes another `@screen` onto the stack; `back()` pops. The runtime animates by default.",
    "actionHostBuiltins": "Host built-ins",
    "actionHostBuiltinsDesc": "`copy(~text)`, `share(~text)`, `haptic(\"light\" | \"medium\" | \"heavy\")`, `vibrate(ms)`, `alert(\"…\")`, `confirm(\"…\") => ~ok = it` — the `it` shorthand is the return value of the preceding expression.",

    # ── Advanced ───────────────────────────────────────────────────
    "advanced": "Advanced features",
    "theme": "@theme — design tokens",
    "themeDesc": "Declare a palette once, reuse everywhere. Tokens become regular reactive variables so your app can ship a dark-mode toggle in three lines.",
    "themeExample": """@theme
  ~primary = #4f8ef7
  ~danger  = #e53935
  ~bg      = #ffffff
  ~text    = #212121
  ~radius  = 12""",
    "imports": "@import — module system",
    "importsDesc": "`@import \"./shared/ui.arx\"` pulls every `@component` and `@screen` from that file into the current scope. Paths are relative to the importing file; circular imports are detected and reported at parse time.",
    "components": "@component — custom components",
    "componentsDesc": "Define once, use many times: `@component Avatar url size\\n  image url :: w(size) h(size) radius(size / 2)`. Inside the component body the named parameters are in scope as plain identifiers (without `~`).",
    "forLoops": "@for — repeating a block",
    "forLoopsDesc": "`@for item in ~list` renders one row per element. `@for item, idx in ~list` also binds the zero-based index. The runtime tracks identity via the element itself, so adding items at the top of a 10 000-row list costs O(1) DOM work.",
    "forExample": """@for item, idx in ~items
  row :: gap(8) pad(4)
    badge ~idx
    text ~item :: grow""",
    "ternary": "Ternary operator",
    "ternaryDesc": "`cond ? a : b` works anywhere an expression is accepted. Nest for enums: `~status >= 10 ? \"high\" : ~status >= 5 ? \"mid\" : \"low\"`.",
    "slots": "Slots",
    "slotsDesc": "Inside a component declaration, `slot` marks where the caller's body plugs in. Think of it as the React children / Vue default slot.",

    # ── Reactivity deep dive ───────────────────────────────────────
    "reactivity": "How reactivity works",
    "reactivityDesc": "Each `~var` is a signal. When you read it inside a computed, modifier argument, or interpolation, the runtime notes the read in the current dependency graph. When you write, every node that read it gets re-evaluated — once, at the end of the current microtask.",
    "reactivityBatching": "Batching",
    "reactivityBatchingDesc": "Multiple writes in the same handler are batched. `=> ~a = 1 => ~b = 2` triggers exactly one render pass.",
    "reactivityEquality": "Equality",
    "reactivityEqualityDesc": "By default the runtime uses strict equality (`===`). Writing the same value re-runs nothing. Pass a new object/array to force an update; immutability is encouraged but not required.",

    # ── Examples ───────────────────────────────────────────────────
    "examples": "Examples",
    "examplesDesc": "Four canonical apps, each self-contained and under 40 lines. Copy any of them into the Architex tab and press Run.",
    "exampleCounter": "Counter — reactive state, computed, button handlers, text binding.",
    "exampleTodo": "Todo — list rendering, add / remove, inline editing.",
    "exampleProfile": "Profile — image, badges, conditional visibility, navigation.",
    "exampleKiller": "Killer features — themes, imports, tabs, toasts, formatted numbers, ternaries, typed vars.",

    # ── Error handling ─────────────────────────────────────────────
    "errors": "Common errors and what to do",
    "errUnknownName": "`unknown name ~foo` — you used a reactive variable before declaring it. Add `~foo = …` at the top of the enclosing `@screen`.",
    "errIndent": "`unexpected indent` — children must be one level deeper than their parent. Architex uses exactly two spaces per level; tabs are rejected to avoid invisible-whitespace bugs.",
    "errModifier": "`unknown modifier` — you wrote `:: shadow` but the runtime doesn't support it. Check the modifier list above; Architex is strict about unknown names to protect forward compatibility.",
    "errType": "`type mismatch` — e.g. you passed a string where a number is expected. Annotate the reactive variable (`~count: number`) and the parser will tell you where the bad value originates.",
    "errDebug": "To debug at runtime, wrap the suspect expression in `debug(...)` — the runtime logs every evaluation to the console without affecting the value.",

    # ── Compatibility ──────────────────────────────────────────────
    "compatibility": "Runtime compatibility",
    "compatWeb": "Web — renders into vanilla DOM with CSS variables for theme tokens. No React / Vue / Svelte dependency.",
    "compatIOS": "iOS — the same `.arx` is parsed and rendered into SwiftUI views via the Vortex iOS host. Every modifier maps to a SwiftUI style.",
    "compatAndroid": "Android — the host renders into Jetpack Compose. Gesture modifiers (`:: onTap`, `:: onLongPress`) translate to Compose equivalents.",
    "compatVersions": "Version policy — Architex guarantees backward compatibility for `.arx` files across minor versions. A `.arx` file written against 0.1 still works on 0.9.",

    # ── Next steps ─────────────────────────────────────────────────
    "nextSteps": "Next steps",
    "nextStepsDesc": "Read the cookbook for patterns (infinite lists, forms, payments), the tooling guide for the CLI and VS Code plugin, and the contribution guide if you want to add a built-in component. The full source is at github.com/vortex/Architex.",
    "close": "Close",
}


def target_paths() -> list[Path]:
    root = Path("/Users/borismaltsev/RustroverProjects")
    ios_en = root / "Vortex/ios/Modules/Sources/I18N/Resources/locales/en.json"
    web_locales = sorted((root / "vortex-introduce-page/locales").glob("*.json"))
    return [ios_en] + web_locales


def splice(paths: list[Path]) -> None:
    for p in paths:
        if not p.exists():
            print(f"skip: {p} not found")
            continue
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        data["architexDocs"] = ARCHITEX_DOCS
        with p.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"wrote {p}")


if __name__ == "__main__":
    splice(target_paths())
