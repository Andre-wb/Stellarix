<h1 align="center">Gravitix</h1>

<p align="center">
  <b>A high-performance scripting language for building bots. Written in Rust. Designed for the <a href="https://github.com/Andre-wb/Vortex">Vortex</a> messenger.</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Rust-1.75+-DEA584?style=for-the-badge&logo=rust&logoColor=black" alt="Rust">
  <img src="https://img.shields.io/badge/Features-96_language_features-7C3AED?style=for-the-badge" alt="96 features">
  <img src="https://img.shields.io/badge/Source-12.5K_lines-06D6F0?style=for-the-badge" alt="12.5K lines">
  <img src="https://img.shields.io/badge/Tests-165_passing-22C55E?style=for-the-badge" alt="165 tests">
  <img src="https://img.shields.io/badge/Runtime_deps-0-22C55E?style=for-the-badge" alt="Zero deps">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Handlers-22c55e?style=flat-square" alt="Handlers">
  <img src="https://img.shields.io/badge/Flows-22c55e?style=flat-square" alt="Flows">
  <img src="https://img.shields.io/badge/Pattern_matching-22c55e?style=flat-square" alt="Pattern matching">
  <img src="https://img.shields.io/badge/FSM-22c55e?style=flat-square" alt="FSM">
  <img src="https://img.shields.io/badge/Pipe_operator-22c55e?style=flat-square" alt="Pipe">
  <img src="https://img.shields.io/badge/Lambdas-22c55e?style=flat-square" alt="Lambdas">
  <img src="https://img.shields.io/badge/Sandboxed-22c55e?style=flat-square" alt="Sandboxed">
</p>

---

## Hello, bot

```gravitix
on /start {
    emit "Hello, {ctx.username}!"
}

on /add <item> {
    state.list = (state.list or []) + [ctx.args.item]
    emit "Added: {ctx.args.item}"
}

on /list {
    emit "You have {len(state.list)} items"
}
```

Three commands, a shared state map, a message for each user who runs the bot. The whole program above is ~10 lines and behaves like a real production bot — persistence, per-user state, typed command arguments, safe string interpolation.

**96 language features** · **12.5K lines Rust** · **165 tests passing** · **zero runtime dependencies**

---

## The Vortex DSL family

Gravitix has a sister language for UIs:

| | **Gravitix** | **Architex** |
|---|---|---|
| What | Bot logic, event handlers, conversation flows | UI screens, reactive state, Mini Apps |
| Runs on | Vortex node (sandboxed Rust interpreter) | Every Vortex client (web / iOS / Android) |
| Syntax | `on /cmd { emit "…" }` | `@screen Name; col :: pad(24) …` |
| Scope | Stateful, multi-user, long-lived | Stateful per-open, single-user, ephemeral |
| Docs | `/Gravitix/README.md` + `gxd` in Vortex docs | `/Architex/README.md` + `arxd` in Vortex docs |

Both are designed to coexist. A Gravitix bot can publish an Architex Mini App as a response (`emit screen "MyApp"`), and the Mini App can call back into the bot via `send(action: ...)` — a neat round-trip for command-driven UIs.

---

## Full reference in 146 languages

Every Gravitix feature has a full-text chapter in the [Vortex docs site](https://github.com/Andre-wb/vortex-introduce-page). Navigate the docs tree:

```
Vortex Docs
└─ Gravitix
   ├─ Overview
   └─ Deep reference  ▸  (34 sections)
      ├─ Intro          bestpractices       bitwise
      ├─ Builtins       complex_type        ctx
      ├─ Emit           error               examples
      ├─ Flows          functions           guard
      ├─ Handlers       if                  loops
      ├─ Match          math_calculus       math_complex
      ├─ …              math_stats          math_transforms
      ├─ Operators      pipe                quickstart
      ├─ Schedule       state               strings
      ├─ Structs        syntax              types
      └─ Variables
```

Each leaf expands to an accordion with **Description**, **How it works**, **History**, and a **Formula / wire shape** panel. The reference ships in **146 locales** — the same JSON files serve the iOS app, the Android app, and the web docs.

---

## Quick Start

```bash
# Install
cargo install --path .

# Run a bot
gravitix run bot.grav --token YOUR_TOKEN --url https://vortex.example.com

# Syntax check
gravitix check bot.grav

# Interactive REPL
gravitix repl

# Run tests
gravitix test bot.grav

# Format code
gravitix fmt bot.grav

# Generate docs
gravitix doc bot.grav
```

## Table of Contents

- [Variables & Types](#variables--types)
- [Functions](#functions)
- [Handlers & Triggers](#handlers--triggers)
- [Context (ctx)](#context-ctx)
- [State](#state)
- [Control Flow](#control-flow)
- [Pattern Matching](#pattern-matching)
- [Strings](#strings)
- [Collections](#collections)
- [Flows (Dialogues)](#flows-dialogues)
- [Pipe Operator](#pipe-operator)
- [Error Handling](#error-handling)
- [Schedulers](#schedulers)
- [Keyboards & Rich Messages](#keyboards--rich-messages)
- [Structs & Enums](#structs--enums)
- [Lambdas & Closures](#lambdas--closures)
- [Destructuring](#destructuring)
- [List Comprehensions](#list-comprehensions)
- [Optional Chaining](#optional-chaining)
- [FSM (Finite State Machines)](#fsm-finite-state-machines)
- [Permissions & RBAC](#permissions--rbac)
- [Rate Limiting](#rate-limiting)
- [Caching](#caching)
- [A/B Testing](#ab-testing)
- [Decorators](#decorators)
- [Events](#events)
- [Reactive State (watch)](#reactive-state-watch)
- [Testing](#testing)
- [Validation](#validation)
- [Bot Memory](#bot-memory)
- [Database](#database)
- [HTTP & AI](#http--ai)
- [Webhooks](#webhooks)
- [Forms](#forms)
- [Tables & Charts](#tables--charts)
- [Streaming](#streaming)
- [Modules & Imports](#modules--imports)
- [Middleware](#middleware)
- [Circuit Breakers](#circuit-breakers)
- [Channels](#channels)
- [Queues](#queues)
- [NLU (Intents & Entities)](#nlu-intents--entities)
- [Sandbox](#sandbox)
- [Internationalization (i18n)](#internationalization-i18n)
- [Multiplatform](#multiplatform)
- [Migrations](#migrations)
- [Admin Panel](#admin-panel)
- [Type Aliases (typedef)](#type-aliases-typedef)
- [Metrics](#metrics)
- [Debugging](#debugging)
- [CLI Commands](#cli-commands)
- [Built-in Functions Reference](#built-in-functions-reference)
- [Examples](#examples)

---

## Variables & Types

```gravitix
// Immutable by default, type inferred
let x = 42
let name = "Alice"
let pi = 3.14
let active = true
let items = [1, 2, 3]
let config = { key: "value", count: 10 }

// Explicit types
let x: int = 42
let name: str = "Alice"
let pi: float = 3.14
let active: bool = true
let items: list = [1, 2, 3]
let config: map = {}
```

**Types:** `int`, `float`, `bool`, `str`, `list`, `map`, `void`, `any`

**Type checking:**
```gravitix
type_of(42)        // "int"
is_int(42)         // true
is_str("hello")    // true
is_null(null)      // true
is_list([1, 2])    // true
is_map({})         // true
```

**Type conversion:**
```gravitix
int("42")          // 42
float("3.14")      // 3.14
str(42)            // "42"
bool(1)            // true
```

---

## Functions

```gravitix
fn greet(name: str) -> str {
    return "Hello, " + name + "!"
}

// Default parameters
fn power(base: int, exp: int = 2) -> int {
    return base ** exp
}

// Calling
let msg = greet("Alice")
let sq = power(5)       // 25
let cb = power(5, 3)    // 125
```

**Doc comments:**
```gravitix
/// Greets a user by name.
/// @param name — the user's display name
/// @example greet("Alice") -> "Hello, Alice!"
fn greet(name: str) -> str {
    return "Hello, " + name + "!"
}
```

Generate documentation: `gravitix doc script.grav`

---

## Handlers & Triggers

Handlers respond to events. The first matching handler runs.

```gravitix
// Slash commands
on /start { emit "Welcome!" }
on /help  { emit "Available commands: /start, /help" }

// Any text message
on msg { emit "You said: {ctx.text}" }

// With guard condition
on /admin guard ctx.user_id == 12345 {
    emit "Admin panel"
}

// Callback buttons
on callback "confirm_yes" {
    emit "Confirmed!"
    answer callback "Done"
}

// Media
on file  { emit "File received: {ctx.file_url}" }
on image { emit "Photo received!" }
on voice { emit "Voice message: {ctx.duration}s" }

// User events
on join  { emit "Welcome to the chat!" }
on leave { emit "Goodbye!" }

// Special triggers
on reaction "👍"    { emit "Thanks for the like!" }
on mention          { emit "You mentioned me!" }
on dm               { emit "This is a DM" }
on edited           { emit "Message was edited" }
on forward          { emit "Forwarded message" }
on thread           { emit "Thread reply" }
on poll_vote        { emit "Voted: {ctx.vote_option}" }

// Catch-all
on any { log("Unhandled event") }

// Error handler
on error { emit "Something went wrong" }

// Idle detection (ms)
on idle 300000 { emit "Are you still there?" }
```

**Handler priority:** Command > Guard > Callback > Specific triggers > AnyMsg > Any

---

## Context (ctx)

Every handler receives `ctx` — the event context:

```gravitix
ctx.user_id         // int — sender's ID
ctx.username        // str — sender's username
ctx.room_id         // int — chat room ID
ctx.text            // str? — message text
ctx.message_id      // int — message ID
ctx.command         // str? — command name without /
ctx.args            // list<str> — command arguments
ctx.callback_data   // str? — callback button data
ctx.callback_id     // str? — callback query ID
ctx.timestamp       // int — unix timestamp
ctx.reaction        // str? — reaction emoji
ctx.file_url        // str? — uploaded file URL
ctx.file_size       // int? — file size in bytes
ctx.duration        // int? — voice message duration (sec)
ctx.is_dm           // bool — is direct message
ctx.mention_text    // str? — mention text
ctx.user_lang       // str? — user's language code
ctx.platform        // str — platform name ("vortex", "telegram")
ctx.intent          // str? — detected NLU intent
ctx.vote_option     // str? — poll vote option
ctx.forward_from    // int? — forward source user ID
ctx.is_thread       // bool — is thread reply
```

---

## State

Persistent bot state that survives restarts:

```gravitix
state {
    count: int = 0
    users: map<int, str> = {}
    active: bool = true
}

// Read
let n = state.count

// Write
state.count += 1
state.users[ctx.user_id] = ctx.username

// Scoped state (per-user, per-room)
state {
    score: int = 0 per user
    topic: str = "" per room
}
```

---

## Control Flow

```gravitix
// If / elif / else
if x > 0 {
    emit "positive"
} elif x == 0 {
    emit "zero"
} else {
    emit "negative"
}

// While
let i = 0
while i < 10 {
    i += 1
}

// For-in
for item in [1, 2, 3] {
    emit "{item}"
}

for key in config.keys() {
    emit "{key}: {config[key]}"
}

// Break & Continue
for i in range(0, 100) {
    if i % 2 == 0 { continue }
    if i > 50 { break }
    emit "{i}"
}

// Return
fn find(items: list, target: str) -> int {
    let i = 0
    for item in items {
        if item == target { return i }
        i += 1
    }
    return -1
}
```

---

## Pattern Matching

```gravitix
match ctx.text {
    "hello"       => emit "Hi there!"
    "bye"         => emit "Goodbye!"
    /^calc (.+)/  => emit "Calculating..."    // regex
    42            => emit "The answer!"
    1..10         => emit "Single digit"       // range
    _             => emit "Unknown"            // wildcard
}

// Enum destructuring
match status {
    Ok(value)     => emit "Success: {value}"
    Err(message)  => emit "Error: {message}"
}

// Struct destructuring
match point {
    Point { x: 0, y } => emit "On Y axis at {y}"
    Point { x, y: 0 }  => emit "On X axis at {x}"
    _                   => emit "At ({point.x}, {point.y})"
}
```

---

## Strings

```gravitix
// Interpolation
let msg = "Hello, {ctx.username}! You have {len(items)} items."

// Multi-line
let text = """
    This is a
    multi-line string
"""

// Operations
len("hello")               // 5
contains("hello", "ell")   // true
replace("hello", "l", "r") // "herro"
split("a,b,c", ",")        // ["a", "b", "c"]
join(["a", "b"], ", ")      // "a, b"
trim("  hello  ")           // "hello"
lowercase("Hello")          // "hello"
uppercase("Hello")          // "HELLO"

// String formatting
fmt("Hello {name}, you are {age}!", { name: "Alice", age: 25 })
```

---

## Collections

**Lists:**
```gravitix
let items = [1, 2, 3, 4, 5]

// Access
items[0]                    // 1
items[-1]                   // 5 (last)
items[1..3]                 // [2, 3] (slice)

// Methods
items.len()                 // 5
items.map(fn(x) { x * 2 }) // [2, 4, 6, 8, 10]
items.filter(fn(x) { x > 3 })        // [4, 5]
items.sort()                // [1, 2, 3, 4, 5]
items.reverse()             // [5, 4, 3, 2, 1]
items.find(fn(x) { x == 3 })         // 3
items.reduce(fn(a, b) { a + b }, 0)  // 15
items.any(fn(x) { x > 4 })           // true
items.all(fn(x) { x > 0 })           // true
items.enumerate()           // [[0,1], [1,2], [2,3], ...]
items.flat_map(fn(x) { [x, x * 10] })

// Mutation
push(items, 6)
pop(items)
```

**Maps:**
```gravitix
let config = { name: "Bot", version: 1, debug: false }

// Access
config.name                 // "Bot"
config["version"]           // 1

// Check & iterate
config.has("name")          // true
config.keys()               // ["name", "version", "debug"]
config.values()             // ["Bot", 1, false]

for key in config.keys() {
    emit "{key} = {config[key]}"
}
```

---

## Flows (Dialogues)

Multi-step conversations that suspend/resume:

```gravitix
flow register {
    emit "What is your name?"
    let name = wait msg           // suspends until user replies

    emit "How old are you?"
    let age = wait msg

    let age = int(age)
    if age < 1 || age > 150 {
        emit "Invalid age. Try /register again."
        return
    }

    state.users[ctx.user_id] = name
    emit "Registered as {name}, age {age}!"
}

on /register { run flow register }

// Wait for callback button
flow confirm {
    emit "Are you sure?"
    keyboard "Confirm?" [["Yes", "confirm_yes"], ["No", "confirm_no"]]
    let answer = wait callback
    if answer == "confirm_yes" {
        emit "Confirmed!"
    } else {
        emit "Cancelled."
    }
}
```

---

## Pipe Operator

```gravitix
// value |> function — value becomes the first argument
let clean = text |> trim |> lowercase
let words = text |> split(" ") |> reverse |> join(", ")

// With error propagation
let data = input |> parse_json? |> validate? |> transform
// If any step returns Err, the chain stops
```

---

## Error Handling

**Try / Catch / Finally:**
```gravitix
try {
    let data = http_get(url)
    emit data.body
} catch e {
    emit "Error: {e.message}"
} finally {
    track("fetch_attempt")
}
```

**Result type with ? operator:**
```gravitix
fn divide(a: int, b: int) -> Result {
    if b == 0 { return Err("division by zero") }
    return Ok(a / b)
}

let result = divide(10, 3)?   // unwraps Ok, propagates Err
```

**Assert:**
```gravitix
assert len(items) > 0, "items must not be empty"
```

---

## Schedulers

```gravitix
// Interval-based
every 5s { emit "ping" }
every 1 hour { emit "Hourly check" }
every 24 hours { emit broadcast "Daily digest" }

// Time-based
at "09:00" { emit "Good morning!" }
at "23:00" { emit "Good night!" }

// Cron expressions
schedule "0 9 * * 1-5" { emit "Weekday 9 AM" }
schedule "*/15 * * * *" { emit "Every 15 minutes" }

// Human-readable cron
every monday at 9:00 { emit "Weekly standup!" }
every weekday at 18:00 { emit "EOD reminder" }
every 1st of month at 10:00 { emit "Monthly report" }
```

---

## Keyboards & Rich Messages

```gravitix
// Inline keyboard
keyboard "Choose an option:" [
    ["Option A", "opt_a"],
    ["Option B", "opt_b"],
    ["Cancel", "cancel"]
]

// Rich message with title, image, buttons
emit rich {
    title: "Product"
    text: "Premium subscription — $9.99/mo"
    image: "https://example.com/product.png"
    buttons: [["Buy Now", "buy"], ["Later", "dismiss"]]
}

// Edit existing message
edit msg_id { text: "Updated content" }

// Delete message
delete ctx.message_id

// Reply to specific message
reply ctx.message_id { text: "This is a reply" }
```

---

## Structs & Enums

```gravitix
struct Point {
    x: int
    y: int
}

struct User {
    name: str
    age: int
    active: bool = true
}

// Construction
let p = Point { x: 10, y: 20 }
emit "Point: ({p.x}, {p.y})"

// Methods via impl
impl User {
    fn greet(self) -> str {
        return "Hi, I'm {self.name}!"
    }
}

let u = User { name: "Alice", age: 25 }
emit u.greet()

// Enums
enum Status {
    Pending
    Active
    Banned(str)
}

let s = Status::Active
match s {
    Status::Pending   => emit "Waiting..."
    Status::Active    => emit "Active!"
    Status::Banned(r) => emit "Banned: {r}"
}
```

---

## Lambdas & Closures

```gravitix
let double = fn(x) { x * 2 }
let add = fn(a, b) { a + b }

let nums = [1, 2, 3, 4, 5]
let evens = nums.filter(fn(x) { x % 2 == 0 })
let sum = nums.reduce(fn(a, b) { a + b }, 0)
```

---

## Destructuring

```gravitix
// Map destructuring
let { name, age, city } = user_data

// List destructuring
let [first, second, ...rest] = items

// In for loops
for { key, value } in entries {
    emit "{key} = {value}"
}
```

---

## List Comprehensions

```gravitix
let squares = [x ** 2 for x in range(1, 11)]
// [1, 4, 9, 16, 25, 36, 49, 64, 81, 100]

let evens = [x for x in range(1, 20) if x % 2 == 0]
// [2, 4, 6, 8, 10, 12, 14, 16, 18]

let pairs = ["{k}: {v}" for k in config.keys()]
```

---

## Optional Chaining

```gravitix
// Safe field access — returns null instead of error
let city = user?.address?.city

// Safe method call
let upper = text?.uppercase()

// Null coalescing
let name = user?.name ?? "Anonymous"
```

---

## FSM (Finite State Machines)

```gravitix
fsm order_flow {
    state idle {
        on /order => selecting
    }
    state selecting {
        on msg guard ctx.text != "" {
            state.selected_item = ctx.text
            emit "Confirm {ctx.text}?"
            => confirming
        }
    }
    state confirming {
        on callback "yes" {
            emit "Order placed!"
            => idle
        }
        on callback "no" {
            emit "Cancelled"
            => idle
        }
    }
}

on /order { run fsm order_flow }
```

---

## Permissions & RBAC

```gravitix
// Declarative role-based access control
permissions {
    roles: {
        admin: ["*"]
        moderator: ["ban", "mute", "delete_msg"]
        vip: ["custom_emoji", "long_messages"]
        user: ["send_msg", "upload_file"]
    }
    default: "user"
}

// Handlers with permission requirements
on /ban require permission "ban" {
    emit "User banned"
}

// Programmatic role management
assign_role(user_id, "moderator")
let role = get_role(user_id)
let can_ban = check_permission(user_id, "ban")
```

---

## Rate Limiting

```gravitix
// Declarative rate limits
ratelimit {
    global: 100 per minute
    per_user: 20 per minute
    command "/ai": 5 per minute
}

// On individual handlers
on /search ratelimit 5 per user per 60s {
    emit "Searching..."
}
```

---

## Caching

```gravitix
// Cache expensive computations
let data = cache "weather" ttl 300 {
    http_get("https://api.weather.com/today")
}
```

---

## A/B Testing

```gravitix
abtest "welcome_msg" {
    variant "short" weight 50 {
        emit "Hi!"
    }
    variant "long" weight 50 {
        emit "Welcome to our bot! Here's what you can do..."
    }
}
```

---

## Decorators

```gravitix
@retry(3)
@logged
fn fetch_data(url: str) -> str {
    return http_get(url).body
}

@cached(300)
fn expensive_query(q: str) {
    return db.find("items").where({ name: { contains: q } }).exec()
}
```

Available decorators:
- `@retry(n)` — retry on error up to n times
- `@logged` — log function entry/exit
- `@cached(ttl)` — cache result for ttl seconds

---

## Events

Custom event system for decoupling handlers:

```gravitix
// Define event handler
on event "order_placed" {
    emit "New order from {ctx.event_data.user}!"
    notify(ctx.event_data.user, "Order confirmed!")
}

// Fire event from another handler
on /buy {
    fire "order_placed" { user: ctx.user_id, item: ctx.args[0] }
}
```

---

## Reactive State (watch)

```gravitix
watch state.user_count {
    if state.user_count % 100 == 0 {
        emit broadcast "Milestone: {state.user_count} users!"
    }
}

watch state.maintenance {
    if state.maintenance {
        emit broadcast "Bot entering maintenance mode"
    }
}
```

---

## Testing

```gravitix
test "math basics" {
    assert 2 + 2 == 4
    assert 10 / 3 == 3
    assert "hello".len() == 5
}

test "with mocks" {
    mock http_get { return { status: 200, body: "ok" } }
    let result = fetch_data("https://example.com")
    expect(result).to_equal("ok")
    expect(result).to_not_be_null()
}

test "expect methods" {
    expect(42).to_equal(42)
    expect("hello").to_contain("ell")
    expect(fn() { panic("fail") }).to_throw()
}

test scenario "full order flow" {
    simulate user(123) sends "/start"
    expect_reply contains "Welcome"

    simulate user(123) sends "/order pizza"
    expect_reply contains "confirm"

    simulate user(123) clicks "confirm_yes"
    expect_reply contains "Order placed"
}
```

Run tests: `gravitix test bot.grav`

---

## Validation

```gravitix
on /register {
    validate ctx.args[0] as email or { emit "Invalid email"; stop }
    validate ctx.args[1] as phone or { emit "Invalid phone"; stop }
    validate ctx.args[2] as int range(18, 120) or { emit "Invalid age"; stop }
}
```

Validators: `email`, `phone`, `url`, `int`, `float`, `len(min, max)`, `range(min, max)`

---

## Bot Memory

Long-term per-user memory that persists across sessions:

```gravitix
on /start {
    let prev = recall(ctx.user_id, "last_topic")
    if prev != null {
        emit "Welcome back! Last time we talked about {prev}"
    }
}

on msg {
    remember(ctx.user_id, "last_topic", ctx.text)
}

// Delete memory
forget(ctx.user_id, "last_topic")

// Get all memories for a user
let mems = memories(ctx.user_id)
```

---

## Database

Built-in key-value database with query builder:

```gravitix
// Simple get/set
db.set("users:123", { name: "Alice", score: 100 })
let user = db.get("users:123")
db.del("users:123")

// Query builder
let results = db.find("users")
    .where({ score: { gt: 50 } })
    .sort("score")
    .limit(10)
    .exec()

// Operators: gt, lt, gte, lte, eq, ne, contains
let active = db.find("users")
    .where({ active: { eq: true }, name: { contains: "Al" } })
    .exec()

// Audit trail
audit("user_banned", { user_id: 123, reason: "spam" })
```

---

## HTTP & AI

```gravitix
// HTTP requests
let res = http_get("https://api.example.com/data")
let res = http_post("https://api.example.com/submit", { key: "value" })
let res = http_put(url, data)
let res = http_delete(url)

// AI integration
let answer = ai("Explain quantum computing in simple terms")
let sentiment = ai("Is this text positive or negative: " + ctx.text)

// AI chat with history
let response = ai_chat([
    { role: "system", content: "You are a helpful assistant." },
    { role: "user", content: ctx.text }
])
```

---

## Webhooks

Receive HTTP webhooks from external services:

```gravitix
webhook "/github" {
    secret: env("GITHUB_SECRET")
    on "push" {
        emit broadcast "Push to {ctx.webhook_body.repository.name}"
    }
    on "issue" {
        emit broadcast "New issue: {ctx.webhook_body.title}"
    }
}

webhook "/stripe" {
    on "payment_succeeded" {
        let amount = ctx.webhook_body.amount / 100
        emit "Payment received: ${amount}"
    }
}
```

Webhook URL: `POST /api/bot/webhook/{bot_id}/{path}`

---

## Forms

Interactive forms in chat:

```gravitix
on /feedback {
    let data = form {
        field "name" type text required
        field "rating" type rating(1, 5)
        field "comment" type textarea
        field "category" type select ["bug", "feature", "other"]
        submit "Send Feedback"
    }
    db.set("feedback:" + uuid(), data)
    emit "Thanks, {data.name}!"
}
```

Field types: `text`, `textarea`, `number`, `email`, `phone`, `rating(min, max)`, `select [options]`

---

## Tables & Charts

```gravitix
// Interactive table
on /users require admin {
    table {
        source: db.find("users").exec()
        columns: ["name", "email", "score"]
        page_size: 10
    }
}

// ASCII chart
on /stats {
    chart {
        type: "bar"
        title: "Commands per day"
        data: [45, 62, 38, 71, 55, 49, 80]
        labels: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    }
}
```

---

## Streaming

Send responses incrementally:

```gravitix
on /long_answer {
    stream {
        emit "Thinking..."
        let answer = ai(ctx.text)
        emit answer
        emit "Done!"
    }
}
```

---

## Modules & Imports

```gravitix
// utils.grav
fn capitalize(s: str) -> str {
    return uppercase(s[0]) + s[1..]
}

// main.grav
import "utils.grav"
import "handlers/admin.grav"
import "handlers/user.grav"

on /greet {
    emit capitalize("hello")  // "Hello"
}
```

---

## Middleware

```gravitix
middleware logging(ctx, next) {
    log("-> " + ctx.command)
    let result = next(ctx)
    log("<- done")
    return result
}

middleware timing(ctx, next) {
    let start = now_unix()
    let result = next(ctx)
    let elapsed = now_unix() - start
    log("Handler took {elapsed}ms")
    return result
}

use middleware logging
use middleware timing
```

**Hooks:**
```gravitix
hook before {
    log("Before handler: {ctx.command}")
}

hook after {
    track("command_executed", { cmd: ctx.command })
}
```

---

## Circuit Breakers

Protect against cascading failures:

```gravitix
circuit_breaker "external_api" {
    threshold: 5
    timeout: 30000
}

on /weather {
    let data = with_breaker "external_api" {
        http_get("https://api.weather.com/today")
    }
    emit data.body.temp
}
```

---

## Channels

Inter-spawn communication (actor model):

```gravitix
let ch = channel("orders")

spawn {
    // Worker process
    for msg in ch {
        db.set("orders:" + msg.id, msg)
        emit "Processed order {msg.id}"
    }
}

on /order {
    ch.send({ id: uuid(), user: ctx.user_id, item: ctx.text })
    emit "Order queued!"
}
```

---

## Queues

Background job processing:

```gravitix
queue "emails" {
    emit "Sending email to {ctx.data.to}"
    http_post("https://mail.api/send", ctx.data)
}

on /invite {
    enqueue "emails" {
        to: ctx.args[0]
        subject: "You're invited!"
        body: "Join us at..."
    }
}
```

---

## NLU (Intents & Entities)

Natural language understanding:

```gravitix
intents {
    greeting: ["hi", "hello", "hey", "good morning"]
    farewell: ["bye", "goodbye", "see you"]
    order: ["I want to order", "buy", "purchase"]
}

on intent "greeting" { emit "Hello! How can I help?" }
on intent "farewell" { emit "Goodbye! Have a nice day." }
on intent "order"    { run flow order_wizard }
on intent unknown    { emit ai(ctx.text) }  // AI fallback

// Entity extraction
entities {
    email: builtin
    phone: builtin
    city: ["Moscow", "London", "Tokyo"]
}

on msg {
    let found = extract(ctx.text)
    if found.email != null {
        emit "Found email: {found.email}"
    }
    if found.city != null {
        emit "You're from {found.city}!"
    }
}
```

---

## Sandbox

Execute user code safely:

```gravitix
on /eval require admin {
    let result = sandbox {
        timeout: 5000
        deny: ["http", "db", "fs"]
        code: ctx.text
    }
    emit "Result: {result}"
}
```

---

## Internationalization (i18n)

```gravitix
lang "en" {
    welcome: "Welcome!"
    help: "Available commands: /start, /help"
}

lang "ru" {
    welcome: "Добро пожаловать!"
    help: "Доступные команды: /start, /help"
}

on /start {
    emit i18n("welcome")  // auto-detects user language
}
```

---

## Multiplatform

One script, multiple platforms:

```gravitix
multiplatform {
    vortex: { url: env("VORTEX_URL"), token: env("VORTEX_TOKEN") }
    telegram: { token: env("TG_TOKEN") }
}

on /start {
    if ctx.platform == "telegram" {
        emit "Hello from Telegram!"
    } else {
        emit "Hello from Vortex!"
    }
}
```

---

## Migrations

Safe data migrations on bot update:

```gravitix
migration "v2_add_scores" {
    for user in db.find("users").exec() {
        if user.score == null {
            db.set("users:" + user.id, { ...user, score: 0 })
        }
    }
}
```

Migrations run once at load time. Tracked automatically.

---

## Admin Panel

Auto-generated web admin panel:

```gravitix
admin {
    title: "MyBot Admin"
    section "Users" {
        table: db.find("users").exec()
        actions: ["ban", "mute", "delete"]
    }
    section "Stats" {
        chart: "line"
        data: state.daily_stats
    }
}
```

---

## Type Aliases (typedef)

```gravitix
typedef Email = str where validate(it, "email")
typedef Age = int where it >= 0 and it <= 150
typedef UserId = int

fn register(name: str, email: Email, age: Age) {
    // email and age are validated automatically
}
```

---

## Metrics

Prometheus-compatible metrics:

```gravitix
metrics {
    counter commands_total
    counter errors_total
    histogram response_time
}

on /start {
    state.commands_total += 1
}
```

---

## Debugging

```gravitix
// Log to stderr
log("Debug info: {value}")
print("Output to console")

// Breakpoint — pauses execution in REPL/test mode
breakpoint

// Debug block — logs expression values with line numbers
debug { result }

// REPL
// $ gravitix repl bot.grav
// gravitix> state
// { count: 42, users: {...} }
// gravitix> db.find("users").limit(3).exec()
// [{name: "Alice"}, ...]
```

---

## CLI Commands

```bash
gravitix run <file.grav>         # Run bot
  --token <TOKEN>                # Vortex API token
  --url <URL>                    # Vortex server URL

gravitix check <file.grav>       # Syntax check

gravitix fmt <file.grav>         # Format code

gravitix test <file.grav>        # Run test blocks

gravitix repl [file.grav]        # Interactive REPL

gravitix doc <file.grav>         # Generate documentation

gravitix install <package>       # Install plugin
```

---

## Built-in Functions Reference

### Strings
| Function | Description | Example |
|---|---|---|
| `len(s)` | String/list length | `len("hello")` → `5` |
| `trim(s)` | Remove whitespace | `trim("  hi  ")` → `"hi"` |
| `lowercase(s)` | To lowercase | `lowercase("Hi")` → `"hi"` |
| `uppercase(s)` | To uppercase | `uppercase("hi")` → `"HI"` |
| `contains(s, sub)` | Check substring | `contains("hello", "ell")` → `true` |
| `replace(s, from, to)` | Replace substring | `replace("hello", "l", "r")` → `"herro"` |
| `split(s, sep)` | Split string | `split("a,b", ",")` → `["a", "b"]` |
| `join(list, sep)` | Join list | `join(["a", "b"], ",")` → `"a,b"` |
| `sanitize(s)` | Remove HTML/scripts | `sanitize("<b>hi</b>")` → `"hi"` |
| `fmt(template, data)` | Format template | `fmt("Hi {name}", {name: "Bob"})` → `"Hi Bob"` |

### Math
| Function | Description | Example |
|---|---|---|
| `abs(n)` | Absolute value | `abs(-5)` → `5` |
| `min(a, b)` | Minimum | `min(3, 7)` → `3` |
| `max(a, b)` | Maximum | `max(3, 7)` → `7` |
| `floor(f)` | Round down | `floor(3.7)` → `3` |
| `ceil(f)` | Round up | `ceil(3.2)` → `4` |
| `round(f)` | Round nearest | `round(3.5)` → `4` |
| `sqrt(f)` | Square root | `sqrt(16)` → `4.0` |
| `pow(a, b)` | Power | `pow(2, 10)` → `1024` |
| `random()` | Random 0.0..1.0 | `random()` → `0.7321...` |

### Collections
| Function | Description | Example |
|---|---|---|
| `range(a, b)` | Integer range | `range(1, 5)` → `[1, 2, 3, 4]` |
| `push(list, val)` | Append to list | `push(items, "new")` |
| `pop(list)` | Remove last | `pop(items)` → last element |
| `reverse(list)` | Reverse list | `reverse([1,2,3])` → `[3,2,1]` |

### Type Conversion & Checking
| Function | Description |
|---|---|
| `int(x)`, `float(x)`, `str(x)`, `bool(x)` | Convert type |
| `type_of(x)` | Get type name |
| `is_null(x)`, `is_int(x)`, `is_float(x)`, `is_str(x)` | Type check |
| `is_list(x)`, `is_map(x)`, `is_bool(x)` | Type check |

### Time
| Function | Description |
|---|---|
| `now_unix()` | Current unix timestamp |
| `now_str()` | Current datetime string |
| `sleep(ms)` | Sleep for milliseconds |

### HTTP
| Function | Description |
|---|---|
| `http_get(url)` | GET request |
| `http_post(url, body)` | POST request |
| `http_put(url, body)` | PUT request |
| `http_delete(url)` | DELETE request |

### AI
| Function | Description |
|---|---|
| `ai(prompt)` | Single AI completion |
| `ai_chat(messages)` | Multi-turn AI chat |

### Crypto
| Function | Description |
|---|---|
| `encrypt(text, key)` | AES-256-GCM encrypt |
| `decrypt(ciphertext, key)` | AES-256-GCM decrypt |
| `uuid()` | Generate UUID v4 |

### JSON
| Function | Description |
|---|---|
| `json_parse(str)` | Parse JSON string |
| `json_stringify(val)` | Value to JSON |

### Regex
| Function | Description |
|---|---|
| `regex_match(text, pattern)` | Test regex match |
| `regex_find_all(text, pattern)` | Find all matches |
| `regex_replace(text, pattern, replacement)` | Replace by regex |

### Bot / Vortex
| Function | Description |
|---|---|
| `notify(user_id, text)` | Push notification |
| `notify_room(room_id, text)` | Room notification |
| `vortex_send(room_id, text)` | Send message |
| `vortex_get_rooms()` | List rooms |

---

## Examples

### Hello Bot
```gravitix
state {
    greet_count: int = 0
}

on /start {
    state.greet_count += 1
    emit "Hello, {ctx.username}!"
    emit "I've been started {state.greet_count} times."
}

on /help {
    emit "Commands: /start, /help, /ping"
}

on /ping { emit "pong" }

on msg {
    match ctx.text {
        /hello|hi/i => emit "Hey there!"
        _           => emit "Try /help"
    }
}
```

### To-Do Bot
```gravitix
state {
    todos: map<int, list> = {}
}

fn get_todos(uid: int) -> list {
    if state.todos.has(uid) { return state.todos[uid] }
    state.todos[uid] = []
    return state.todos[uid]
}

on /add { run flow add_task }

flow add_task {
    emit "Enter your task:"
    let task = wait msg |> trim |> sanitize
    if len(task) == 0 { emit "Empty task."; return }
    let todos = get_todos(ctx.user_id)
    push(todos, task)
    emit "Added: {task}"
}

on /list {
    let todos = get_todos(ctx.user_id)
    if len(todos) == 0 { emit "No tasks!"; return }
    let i = 0
    for t in todos {
        i += 1
        emit "{i}. {t}"
    }
}
```

### AI Assistant Bot
```gravitix
state {
    history: map<int, list> = {}
}

on /start {
    state.history[ctx.user_id] = []
    emit "I'm your AI assistant. Ask me anything!"
}

on msg {
    let hist = state.history[ctx.user_id] ?? []
    push(hist, { role: "user", content: ctx.text })

    let answer = ai_chat(hist)
    push(hist, { role: "assistant", content: answer })

    // Keep last 20 messages
    if len(hist) > 20 {
        state.history[ctx.user_id] = hist[-20..]
    } else {
        state.history[ctx.user_id] = hist
    }

    emit answer
}

on /clear {
    state.history[ctx.user_id] = []
    emit "History cleared."
}
```

---

## Error Messages

Gravitix provides Rust-quality error messages with source location and suggestions:

```
error[G010]: undefined variable `coun`
  --> bot.grav:15:9
   |
15 |     let y = coun + 1
   |             ^^^^ did you mean `count`?
   |
   = help: available variables: count, name, total
```

```
error[G030]: function `greet` takes 1 argument, but 3 were provided
  --> bot.grav:8:5
   |
 8 |     greet("a", "b", "c")
   |     ^^^^^^^^^^^^^^^^^^^^
```

---

## Architecture

```
┌─────────────────────────────────────────────┐
│              .grav source code               │
└──────────────────┬──────────────────────────┘
                   ▼
┌──────────────────────────────────────────────┐
│  Lexer (src/lexer.rs)                        │
│  Source → Tokens                             │
└──────────────────┬───────────────────────────┘
                   ▼
┌──────────────────────────────────────────────┐
│  Parser (src/parser.rs)                      │
│  Tokens → AST                                │
└──────────────────┬───────────────────────────┘
                   ▼
┌──────────────────────────────────────────────┐
│  Interpreter (src/interpreter/)              │
│  ├─ mod.rs     — SharedState, load()         │
│  ├─ dispatch.rs — Route events to handlers   │
│  ├─ exec.rs    — Execute statements          │
│  ├─ eval.rs    — Evaluate expressions        │
│  └─ env.rs     — Variable environment        │
└──────────────────┬───────────────────────────┘
                   ▼
┌──────────────────────────────────────────────┐
│  Stdlib (src/stdlib/)                        │
│  ├─ strings, math, collections, time         │
│  ├─ http, json, regex, crypto                │
│  ├─ ai, db, vortex, state, io               │
│  └─ 80+ built-in functions                   │
└──────────────────────────────────────────────┘
```

## License

APACHE 2.0

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
