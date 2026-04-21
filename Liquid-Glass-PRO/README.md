# liquid-glass-pro

**v4.1.0** — WebGL2 physically-based liquid glass rendering for the web.

Real Snell's law background refraction via html2canvas, Sellmeier optical dispersion across five Schott glass types, twelve physically-grounded glass surface variants, PCG2D-hashed Voronoi caustics with F2−F1 distance fields and domain warping, Cook-Torrance PBR specular, Beer-Lambert chromatic absorption, frosted scatter refraction, thin-film iridescence, Fresnel reflection, chromatic aberration, spring-physics cursor tracking — with an intelligent CSS fallback for every GPU tier.

---

## Table of Contents

- [What's New in v4.1](#whats-new-in-v41)
- [What's New in v4.0](#whats-new-in-v40)
- [How It Works](#how-it-works)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [HTML Usage](#html-usage)
- [React / Vue / Svelte](#react--vue--svelte)
- [Configuration Reference](#configuration-reference)
- [Public API](#public-api)
- [CSS Classes & Data Attributes](#css-classes--data-attributes)
- [Glass Types & Sellmeier Dispersion](#glass-types--sellmeier-dispersion)
- [Glass Variants](#glass-variants)
- [Caustics Tuning](#caustics-tuning)
- [GPU Tiers & Fallback Strategy](#gpu-tiers--fallback-strategy)
- [Physics Reference](#physics-reference)
- [Performance Notes](#performance-notes)
- [Browser Support](#browser-support)
- [Known Issues & Fixes](#known-issues--fixes)
- [Changelog](#changelog)

---

## What's New in v4.1

### Glass Variant System

Twelve physically-grounded surface presets derived from real optical constants (Schott catalogue 2023, Warren & Brandt 2008, Palik 1998). Each variant encodes a complete optical and visual character: IOR, Beer-Lambert chromatic absorption, scatter amount, mirror strength, smoke density, caustic scale, caustic tint, CSS backdrop-filter overrides, and per-variant hover states.

Switch variants at runtime with a single call — no reinitialisation required:

```js
setGlassVariant('obsidian');     // volcanic glass, near-black, purple sheen
setGlassVariant('tinted-amber'); // warm honey glass, Beer-Lambert σB=4.2
setGlassVariant('mirror');       // first-surface silver mirror, SF11 IOR=1.785
setGlassVariant('ice');          // polycrystalline H₂O ice, IOR=1.309
```

| Variant | IOR | Character |
|---|---|---|
| `clear` | 1.45 | Near-invisible soda-lime float glass |
| `frosted` | 1.47 | Ground-glass scatter, 40px blur |
| `smoke` | 1.52 | Dark neutral-density automotive tint |
| `tinted-blue` | 1.47 | Cobalt architectural glass |
| `tinted-violet` | 1.49 | UV-filter / amethyst crystal |
| `tinted-amber` | 1.53 | Amber / honey-gold cognac glass |
| `mirror` | 1.785 | First-surface silver mirror (SF11) |
| `ice` | 1.309 | Polycrystalline H₂O ice (Warren 2008) |
| `bronze` | 1.58 | Bronze / copper dichroic |
| `emerald` | 1.575 | Chrome-doped beryl (Cr³⁺ absorption) |
| `rose` | 1.46 | Rose quartz / manganese silicate |
| `obsidian` | 1.49 | Volcanic rhyolite glass (Fe²⁺/Fe³⁺) |

### Beer-Lambert chromatic absorption

Per-channel absorption applied to the refracted background before caustic compositing:

```
σ_ch = (1 − tintRGB_ch) · tintStrength · 3.5
I    = I₀ · exp(−σ)
```

Independent per-channel computation means tinted-glass caustic filaments appear in the glass's own hue — cobalt glass casts blue caustics, emerald glass casts green caustics.

### Frosted scatter refraction

Multi-scale noise UV jitter (11× + 27× frequency, independent drift axes) approximates sub-surface scattering in ground glass. Three texture taps are averaged to simulate the scattering lobe integral. The result blends with sharp chromatic refraction by `frostedAmount`, giving a continuous haze gradient from perfectly clear to fully diffuse.

### Mirror reflection mode

`u_mirrorStrength` collapses background transmission (`refractedBg × (1 − mirror × 0.92)`) and amplifies the environment reflection term by up to 6.5×. The mirror variant uses IOR 1.785 (SF11) for F0 ≈ 0.079 — twice the reflectance of standard glass — producing crisp Fresnel rim highlights.

### Smoke density

Broadband post-composite darkening applied after all Beer-Lambert and refraction blending:

```glsl
col *= (1.0 - u_smokeDensity * 0.68);
```

Simulates Fe²⁺/Fe³⁺ and magnetite-inclusion absorption not captured by the Beer-Lambert tint term alone. Used primarily by the `smoke` and `obsidian` variants.

### CSS variant override layer

Each variant applies a CSS class (`.lg-v-clear`, `.lg-v-frosted`, etc.) that overrides `backdrop-filter` and `background` gradient for accurate first-frame appearance before the WebGL pass renders. Variant-specific hover states are also defined. The transition between variants is smooth thanks to CSS `backdrop-filter` interpolation.

---

## What's New in v4.0

### Sellmeier dispersion — replaces Cauchy approximation

v3 used a Cauchy approximation with manually tuned IOR offsets of ±0.018. v4 replaces this with the full three-term Sellmeier equation from the Schott glass catalogue 2023:

```
n²(λ) = 1 + B₁λ²/(λ²−C₁) + B₂λ²/(λ²−C₂) + B₃λ²/(λ²−C₃)
```

The three resonance terms correspond to UV electronic absorption (C₁ ≈ 0.006–0.014 µm²), near-UV secondary (C₂ ≈ 0.020–0.060 µm²), and far-IR phonon lattice (C₃ ≈ 100–200 µm²). Accuracy vs spectrometer: RMS error < 0.0001 across 380–750 nm. Cauchy over-estimated blue dispersion by ~2.5× compared to physical measurements.

### Five optical glass types

| Glass | Abbe V | Δn R→B | Character |
|---|---|---|---|
| `BK7` | 64.17 | 0.0110 | Standard optical — camera lenses, cover glass |
| `SF11` | 25.76 | 0.0408 | Heavy flint — crystal, Swarovski, prisms |
| `NK51A` | 81.61 | 0.0054 | Fluorite crown — APO lenses, near-zero aberration |
| `NBK10` | 67.90 | 0.0084 | Thin crown — architectural window glass |
| `F2` | 36.43 | 0.0227 | Flint — vintage optics, achromatic doublets |

### Improved Voronoi caustic system

**PCG2D integer hash** (Jarzynski & Olano 2020) replaces sin()-based hash — no lattice bias, period 2³² per axis, ~30% faster on GPU.

**F2−F1 distance field** replaces F1 — peaks sharply at cell boundaries, eliminating the cell-centre pillow artefact.

**Domain warping** pre-distorts UV by a low-frequency noise field before Voronoi evaluation, breaking global square lattice regularity.

**Six octaves with 11.25° rotation stagger** — per-cell animation uses four independent PCG2D-derived random scalars (X/Y frequency, X/Y phase offset) and one depth scalar; no two cells ever move in synchrony.

### Full Cook-Torrance PBR specular pass

Dedicated `.lg-specular-canvas` per element, rendered from a shared WebGL2 context. Anisotropic GGX NDF (Burley 2012) + Smith height-correlated visibility (Heitz 2014) + Schlick Fresnel (F0 from Sellmeier) + Kulla-Conty multi-bounce (2017) + thin-film iridescence (Born & Wolf 1999) + three area lights with Karis (2013) representative-point roughness modification.

---

## How It Works

```
User DOM element (.lg)
       │
       ├─ [GPU tier high] WebGL2 Caustics + Refraction (§6)
       │    ├─ html2canvas background capture (§5)
       │    │    ├─ Fires once at init, then every bgCaptureInterval ms
       │    │    ├─ Also fires on scroll (debounced 150ms) and resize
       │    │    └─ Scroll-drift compensation via u_scroll uniform
       │    ├─ Snell's law UV displacement per pixel (surfaceNormal bump-map)
       │    ├─ Sellmeier per-channel IOR dispersion (R@680nm / G@550nm / B@450nm)
       │    ├─ Beer-Lambert chromatic absorption (per-variant tintRGB)     [v4.1]
       │    ├─ Frosted scatter refraction (multi-scale noise UV jitter)    [v4.1]
       │    ├─ Six-octave Voronoi caustics (PCG2D, F2−F1, domain warp, rotation stagger)
       │    ├─ Environment reflection probe (Fresnel-weighted horizontal mirror)
       │    └─ Born & Wolf thin-film iridescence (λR / λG / λB interference)
       │
       ├─ [GPU tier ≥ mid] PBR Specular pass (§15)
       │    ├─ Dedicated WebGL2 context (_spec singleton)
       │    ├─ Anisotropic GGX NDF (Burley 2012)
       │    ├─ Smith height-correlated visibility (Heitz 2014)
       │    ├─ Schlick Fresnel — F0 from Sellmeier n(550nm)
       │    ├─ Kulla-Conty multi-bounce energy compensation (2017)
       │    ├─ Thin-film iridescence (Born & Wolf 1999, d=320nm, n=1.38)
       │    ├─ Three-light config: L0 cursor key / L1 fill / L2 back-scatter
       │    └─ .lg-specular-canvas overlay (screen blend, z-index above caustics)
       │
       ├─ [all tiers] SVG filter bank (§7)
       │    ├─ Chromatic aberration feDisplacementMap (animated turbulence)
       │    └─ Micro-distortion fractalNoise feTurbulence on content
       │
       ├─ [all tiers] Spring physics (§3)
       │    ├─ Semi-implicit Euler damped harmonic oscillator
       │    ├─ Cursor → springX / springY → --lg-mx / --lg-my
       │    ├─ Gyroscope → tiltX / tiltY → CSS perspective transform
       │    └─ Hover intensity spring → caustic + specular opacity
       │
       └─ [GPU tier low / WebGL failure] CSS fallback (§16)
            ├─ ::before  three GGX-lobe radial-gradient (A: L0 peak, B: L1 fill, C: L2 scatter)
            ├─ :hover    seven-layer box-shadow synchronised with L0 intensity ×1.5
            └─ ::after   thin-film conic-gradient with Born & Wolf 120°/240° phase offsets
```

---

## Installation

```bash
npm install liquid-glass-pro
```

Requires **html2canvas ^1.4.1** as a peer dependency, loaded before `initLiquidGlass()` is called:

```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
```

---

## Quick Start

```js
import { initLiquidGlass, setGlassVariant } from './liquid-glass-pro.js';

initLiquidGlass({
  glassType:          'BK7',     // Optical glass material — controls Sellmeier dispersion
  glassVariant:       'clear',   // Surface variant — controls Beer-Lambert, scatter, mirror
  ior:                1.45,
  refractionStrength: 0.045,
  aberrationStrength: 1.6,
  bgCaptureInterval:  2000,
  bgCaptureScale:     0.35,
  caustics:           true,
  grain:              true,
  iridescence:        true,
  breathe:            true,
});

// Switch variant at runtime — no reinit required
setGlassVariant('frosted');
setGlassVariant('tinted-blue');
setGlassVariant('obsidian');
```

Then mark any element with the `lg` class:

```html
<div class="lg lg-card lg-interactive">
  Hello, glass world.
</div>
```

---

## HTML Usage

### Shape modifiers

| Class | Effect |
|---|---|
| `lg-card` | `border-radius: 22px`, `padding: 20px` |
| `lg-pill` | `border-radius: 999px`, `padding: 6px 18px` |
| `lg-fab` | 56×56 circular button, flex-centered |

### Interactive elements

Add `lg-interactive` to enable cursor spring-physics, hover highlight amplification and the specular pass's cursor-tracking light (L0):

```html
<button class="lg lg-pill lg-interactive">Click me</button>
```

### Own messages (chat)

```html
<div class="lg lg-own lg-interactive chat-bubble">
  Purple-tinted variant for sent messages.
</div>
```

### Reply quotes

```js
import { createReplyQuote } from './liquid-glass-pro.js';

const quote = createReplyQuote(
  'Alice',
  'The refraction looks incredible!',
  false,                              // isOwn
  () => scrollToMessage(id)           // optional click handler
);
chatContainer.appendChild(quote);
```

---

## React / Vue / Svelte

### React hook

```jsx
import { useRef } from 'react';
import { useLiquidGlass } from './liquid-glass-pro.js';

function GlassCard({ children }) {
  const ref = useRef(null);
  useLiquidGlass(ref);  // attach on mount, detach on unmount

  return (
    <div ref={ref} className="lg lg-card lg-interactive">
      {children}
    </div>
  );
}
```

### Vue 3 composable

```js
import { onMounted, onUnmounted } from 'vue';
import { attachElement, detachElement } from './liquid-glass-pro.js';

export function useLiquidGlass(elRef) {
  onMounted(()   => attachElement(elRef.value));
  onUnmounted(() => detachElement(elRef.value));
}
```

### Svelte action

```svelte
<script>
  import { attachElement, detachElement } from './liquid-glass-pro.js';

  function liquidGlass(node) {
    attachElement(node);
    return { destroy: () => detachElement(node) };
  }
</script>

<div class="lg lg-card" use:liquidGlass>
  Hello from Svelte
</div>
```

---

## Configuration Reference

All options passed to `initLiquidGlass()`. Missing values fall back to defaults.

| Option | Type | Default | Description |
|---|---|---|---|
| `selector` | `string` | `'.lg'` | CSS selector for auto-discovery via MutationObserver |
| `glassType` | `string` | `'BK7'` | Optical glass material. One of `'BK7'`, `'SF11'`, `'NK51A'`, `'NBK10'`, `'F2'`. Controls Sellmeier dispersion for both refraction and caustic passes. |
| `glassVariant` | `string` | `'clear'` | **v4.1** Surface variant. Controls Beer-Lambert absorption, scatter, mirror strength, smoke density, and CSS overrides. See [Glass Variants](#glass-variants). |
| `ior` | `number` | `1.45` | Base index of refraction for surface displacement magnitude. Per-channel IOR is computed from Sellmeier; this value controls overall displacement scale. Automatically overridden when `setGlassVariant()` is called. |
| `refractionStrength` | `number` | `0.035` | UV displacement scale for Snell refraction. Higher = stronger fish-eye effect. |
| `aberrationStrength` | `number` | `1.6` | px magnitude of SVG feDisplacementMap chromatic aberration. Half strength on `mid` tier. |
| `bgCaptureInterval` | `number` | `200` | ms between background re-captures. Lower = fresher refraction, higher CPU cost. |
| `bgCaptureScale` | `number` | `0.65` | html2canvas resolution scale. Lower = faster but blurrier refraction. |
| `caustics` | `boolean` | `true` | Master switch for WebGL2 Voronoi caustic pass. |
| `grain` | `boolean` | `true` | Inject `.lg-grain` film-grain overlay inside each element. |
| `iridescence` | `boolean` | `true` | Enable thin-film interference CSS animation on `::after`. |
| `breathe` | `boolean` | `true` | Enable `lg-breathe` border-radius morph animation. |
| `glassOpacity` | `number` | `0.12` | Base white tint alpha. |
| `glassSaturation` | `number` | `100` | `backdrop-filter: saturate()` value. Below 100 desaturates background. |

### Changing glass type at runtime

```js
import { setGlassType, refreshBackground } from './liquid-glass-pro.js';

setGlassType('SF11');      // heavy flint — vivid rainbow splitting
refreshBackground();       // force immediate re-capture with new IOR
```

### Changing glass variant at runtime

```js
import { setGlassVariant } from './liquid-glass-pro.js';

setGlassVariant('frosted');       // ground glass, 40px blur, heavy scatter
setGlassVariant('tinted-blue');   // cobalt architectural glass
setGlassVariant('mirror');        // first-surface silver mirror
setGlassVariant('clear');         // back to default
```

`setGlassVariant()` simultaneously updates the CSS class on all tracked elements and the `_opts.ior` / `_opts.glassVariant` values consumed by the WebGL uniform upload. The transition is visually smooth — the CSS `backdrop-filter` interpolates between states.

---

## Public API

### `initLiquidGlass(options?)` → `void`

Initialises the system. Safe to call from any `readyState` — deferred to `DOMContentLoaded` if the DOM is still loading. Subsequent calls are no-ops; call `destroyLiquidGlass()` first to re-initialise.

```js
initLiquidGlass({ glassType: 'SF11', glassVariant: 'smoke', bgCaptureInterval: 3000 });
```

---

### `destroyLiquidGlass()` → `void`

Full teardown: detaches all elements, destroys both WebGL contexts, cancels rAF loop, disconnects MutationObserver and IntersectionObserver, removes injected `<style>` and `<svg>`.

```js
destroyLiquidGlass();
// Safe to call initLiquidGlass() again afterwards
```

---

### `setGlassType(type)` → `void`

Changes the optical glass material at runtime. Accepts a type name string or numeric index (0–4). Takes effect on the next rendered frame.

```js
setGlassType('SF11');   // vivid rainbow splitting
setGlassType('NK51A');  // near-zero dispersion (APO quality)
setGlassType(0);        // numeric: 0=BK7, 1=SF11, 2=NK51A, 3=NBK10, 4=F2
```

---

### `setGlassVariant(variant)` → `void`

Changes the glass surface variant at runtime. Removes the previous variant CSS class from all tracked elements, applies the new one, and updates `_opts.glassVariant` and `_opts.ior` for the WebGL pass. Emits a console warning if the variant key is not recognised.

```js
setGlassVariant('ice');         // H₂O ice, IOR=1.309, cold-blue caustics
setGlassVariant('emerald');     // chrome-doped beryl, IOR=1.575
setGlassVariant('obsidian');    // volcanic glass, near-black, IOR=1.49
```

---

### `getGlassVariants()` → `Record<string, GlassVariantDef>`

Returns a shallow copy of the `GLASS_VARIANTS` object. Useful for building variant picker UIs.

```js
const variants = getGlassVariants();
Object.entries(variants).forEach(([key, def]) => {
  console.log(key, def.label, def.ior, `Abbe-like: blurPx=${def.blurPx}`);
});
```

---

### `attachElement(el)` → `void`

Manually attaches the glass effect to a single element outside the automatic selector scan. Useful for Shadow DOM or framework-managed components. Requires `initLiquidGlass()` to have been called first.

```js
attachElement(document.querySelector('#modal'));
```

---

### `detachElement(el)` → `void`

Removes the glass effect from one element and frees its resources. Safe to call if the element was never attached.

```js
detachElement(document.querySelector('#modal'));
```

---

### `wrapWithDistortion(el)` → `{ wrapper, unwrap }`

Wraps `el` in a `.lg-outer` SVG-filter container. Preserves original `display` type. Returns the wrapper element and an `unwrap()` restoration function.

```js
const { wrapper, unwrap } = wrapWithDistortion(myCard);
// Later:
unwrap();
```

---

### `createReplyQuote(sender, text, isOwn, onClick)` → `HTMLDivElement`

Factory for chat reply-quote elements. Returns a detached `.lg.lg-reply` element.

```js
const quote = createReplyQuote('Bob', 'Are you seeing the refraction?', false, () => jumpTo(id));
```

---

### `refreshBackground()` → `Promise<void>`

Forces an immediate html2canvas re-capture outside the regular interval. Call after large DOM mutations, route changes, or after calling `setGlassType()`.

```js
await refreshBackground();
```

---

### `getGpuTier()` → `'low' | 'mid' | 'high'`

Returns the memoised GPU capability tier.

| Tier | Condition | Features active |
|---|---|---|
| `'high'` | Desktop / Apple silicon | Full: refraction + caustics + specular + variants |
| `'mid'` | Adreno 500–600 / Mali-G57–G75 | Caustics + specular, aberration at ½ strength |
| `'low'` | Legacy mobile / WebGL unavailable | CSS fallback only |

---

### `isRefractionActive()` → `boolean`

Returns `true` once the first html2canvas background capture has completed and the WebGL texture is populated.

---

### `getOptions()` → `LGOptions`

Returns a **live reference** to the currently active options object. Mutations take effect on the next animation frame.

```js
const opts = getOptions();
opts.glassType = 'NK51A';
opts.refractionStrength = 0.06;
```

---

### `version()` → `'4.1.0'`

---

## CSS Classes & Data Attributes

### Classes applied by the library

| Class | Applied to | Purpose |
|---|---|---|
| `.lg-outer` | wrapper (optional) | SVG chromatic-aberration filter context |
| `.lg-grain` | `<div>` inside `.lg` | Film grain SVG noise overlay |
| `.lg-caustic-canvas` | `<canvas>` inside `.lg` | WebGL caustics / refraction blitted output |
| `.lg-specular-canvas` | `<canvas>` inside `.lg` | WebGL PBR specular blitted output |
| `.lg-reply` | `.lg` element | Reply quote shape + left-border accent |
| `.lg-own` | `.lg` element | Purple-tint variant for own messages |
| `.lg-v-{name}` | `.lg` element | **v4.1** Active glass variant CSS class |

### Data attributes set by the library

| Attribute | Meaning |
|---|---|
| `data-lg-webgl="1"` | WebGL caustic + specular passes are active on this element |
| `data-lg-refract="1"` | Background texture is populated (refraction live) |

### Houdini CSS custom properties

Set per-frame by the spring system. Usable in custom CSS for cursor-reactive effects:

| Property | Type | Description |
|---|---|---|
| `--lg-mx` | `<percentage>` | Cursor X, spring-smoothed, `0%`–`100%` |
| `--lg-my` | `<percentage>` | Cursor Y, spring-smoothed, `0%`–`100%` |
| `--lg-hover` | `<number>` | Hover intensity `0`–`1` |
| `--lg-tx` | `<number>` | Tilt X `−1`–`+1` |
| `--lg-ty` | `<number>` | Tilt Y `−1`–`+1` |
| `--lg-irid` | `<angle>` | Iridescence rotation angle |
| `--lg-sa` `--lg-sb` `--lg-sc` `--lg-sd` | — | Per-element random specular lobe offsets (re-randomised on each hover enter) |

```css
/* Custom shimmer tied to cursor — works at all GPU tiers */
.lg::before {
  background: radial-gradient(
    ellipse at var(--lg-mx) var(--lg-my),
    rgba(255,255,255,0.18) 0%,
    transparent 60%
  );
}
```

---

## Glass Types & Sellmeier Dispersion

### Physical background

The refractive index of optical glass is wavelength-dependent. The industry-standard Sellmeier equation (1871) describes this with three resonance terms:

```
n²(λ) = 1 + B₁λ²/(λ²−C₁)   ← UV electronic resonance
           + B₂λ²/(λ²−C₂)   ← near-UV secondary
           + B₃λ²/(λ²−C₃)   ← far-IR phonon lattice
```

λ is in micrometres. Coefficients from Schott catalogue 2023. Valid range: 0.365–2.325 µm. RMS error vs spectrometer: < 0.0001 across 380–750 nm. Cauchy (used in v3) over-estimated blue dispersion by ~2.5×.

RGB primary wavelengths evaluated in the shader:

```
λR = 0.680 µm (680 nm) — red,   CIE D65
λG = 0.550 µm (550 nm) — green, peak photopic (reference channel)
λB = 0.450 µm (450 nm) — blue
```

### Per-type constants

**BK7 — Borosilicate Crown**
```
Abbe V = 64.17 | n_D = 1.51680 | Δn(R→B) = 0.01101
Sellmeier: B₁=1.03961212 C₁=0.00600070  B₂=0.23179234 C₂=0.02001791  B₃=1.01046945 C₃=103.56065
```

**SF11 — Heavy Flint**
```
Abbe V = 25.76 | n_D = 1.78472 | Δn(R→B) = 0.04079
Sellmeier: B₁=1.73848403 C₁=0.01366091  B₂=0.31116800 C₂=0.06169579  B₃=1.17490871 C₃=121.92271
```

**N-FK51A — Fluorite Crown**
```
Abbe V = 81.61 | n_D = 1.48656 | Δn(R→B) = 0.00536
Sellmeier: B₁=0.97124800 C₁=0.00472302  B₂=0.21602196 C₂=0.01530890  B₃=0.90448069 C₃=168.68184
```

**N-BK10 — Thin Crown**
```
Abbe V = 67.90 | n_D = 1.49780 | Δn(R→B) = 0.00841
Sellmeier: B₁=0.88841934 C₁=0.00516901  B₂=0.32846101 C₂=0.01774020  B₃=0.95900362 C₃=95.75651
```

**F2 — Flint**
```
Abbe V = 36.43 | n_D = 1.62005 | Δn(R→B) = 0.02265
Sellmeier: B₁=1.34533359 C₁=0.00997744  B₂=0.20977271 C₂=0.04703645  B₃=0.89270000 C₃=111.88676
```

### Visual comparison

| Glass | Refraction character | Caustic colour split |
|---|---|---|
| N-FK51A | Clean, near-achromatic | Barely visible spectral fringing |
| N-BK10 | Gentle bend, everyday window | Subtle warm/cool edge |
| BK7 | Standard optical quality | Visible but controlled prismatic rim |
| F2 | Noticeably curved, warm tones | Clear rainbow edge, vintage feel |
| SF11 | Strong displacement, wide bloom | Vivid full-spectrum rainbow |

---

## Glass Variants

Each variant is a complete physical description of a glass surface. All parameters are uploaded to the WebGL fragment shader every frame as uniforms, and to CSS as class overrides.

### Variant physical parameters

| Parameter | GLSL uniform | Physical model |
|---|---|---|
| `ior` | (sets `u_ior` via `_opts.ior`) | Index of refraction for surface normal displacement |
| `tintRGB` | `u_tintRGB` | Beer-Lambert absorption target colour |
| `tintStrength` | `u_tintStrength` | Absorption coefficient scale (σ = (1−tintRGB)·tintStrength·3.5) |
| `frosted` | `u_frostedAmount` | Scatter-blur amount 0–1 (0 = sharp, 1 = fully diffuse) |
| `mirror` | `u_mirrorStrength` | Mirror reflection boost (collapses transmission at 1.0) |
| `smokeDensity` | `u_smokeDensity` | Uniform post-composite darkening (Fe²⁺/Fe³⁺ analogue) |
| `causticScale` | `u_causticScale` | Caustic intensity multiplier |
| `causticTint` | `u_causticTint` | RGB tint applied to caustic layer |
| `blurPx` | CSS `backdrop-filter: blur()` | CSS-layer blur in pixels |
| `saturate` | CSS `backdrop-filter: saturate()` | CSS-layer saturation % |
| `brightness` | CSS `backdrop-filter: brightness()` | CSS-layer brightness multiplier |

### Variant reference

**`clear`** — Soda-lime float glass, IOR 1.45. Near-invisible. Maximum background transmission. Minimal tint, crisp caustics.

**`frosted`** — Ground / sandblasted glass, IOR 1.47. `frosted=0.90` fully diffuses the refracted image. 40px backdrop-filter blur approximates sub-surface scatter mean free path. High white tint (`rgba(255,255,255,0.20)`) simulates light spread through the surface.

**`smoke`** — Automotive / architectural dark tint film, IOR 1.52. Neutral-density Beer-Lambert absorption. `smokeDensity=0.52` post-composite darkening. `brightness=0.66`.

**`tinted-blue`** — Cobalt architectural glass, IOR 1.47. Strong Beer-Lambert R/G absorption (σR=3.1, σG=1.8, σB=0.2). `hue-rotate(210deg)` in CSS layer. Blue-cyan caustic filaments.

**`tinted-violet`** — UV-filter glass / amethyst crystal, IOR 1.49. Absorbs green trough (550nm), passes R+B → purple. `hue-rotate(270deg)`.

**`tinted-amber`** — Amber / cognac glass, IOR 1.53. Strong B absorption (σB=4.2), minimal R/G → warm glow. `sepia(25%)` in CSS layer. Warm caustic filaments.

**`mirror`** — First-surface silver mirror coating. IOR 1.785 (SF11) → F0 ≈ 0.079. `mirror=0.92` collapses transmission. `causticScale=1.50` — caustics become sharp specular flares. `blur(3px)` — mirror glass is optically flat.

**`ice`** — Polycrystalline H₂O ice (Warren & Brandt 2008, 550nm, T=−10°C). IOR 1.309. `frosted=0.42` simulates grain-boundary scatter. Cold-blue caustic tint. High brightness (1.22) — ice transmits very well in visible range.

**`bronze`** — Bronze / copper dichroic glass, IOR 1.58. Beer-Lambert absorbs B strongly. `sepia(40%)` + warm saturate in CSS. Warm gold caustic filaments.

**`emerald`** — Chrome-doped beryl (Cr³⁺ absorption peaks at 430nm and 610nm), IOR 1.575. Strong G transmission window near 500–570nm. `hue-rotate(140deg)`. Vivid green caustic filaments.

**`rose`** — Rose quartz / manganese silicate, IOR 1.46. Absorbs 490–580nm (green), passes red+blue. `hue-rotate(330deg)`.

**`obsidian`** — Volcanic rhyolite glass (~72% SiO₂), IOR 1.49. Near-black from Fe²⁺/Fe³⁺/magnetite inclusions. `smokeDensity=0.74`, `tintStrength=0.86`. Subtle purple glow in shadow stack from characteristic obsidian iridescence. `brightness=0.54`.

### Listing all variants programmatically

```js
import { getGlassVariants } from './liquid-glass-pro.js';

const variants = getGlassVariants();
// { clear: { label, ior, tintRGB, ... }, frosted: { ... }, ... }

Object.entries(variants).forEach(([key, def]) => {
  console.log(`${key}: IOR=${def.ior}, blur=${def.blurPx}px`);
});
```

---

## Caustics Tuning

### Six-octave default configuration

```glsl
// causticBandImproved(uv, cellFreq, speed, seed, octIdx, sharp)

float c = 0.0;
c += causticBandImproved(uv + mw,        5.8,  0.28, vec2( 0.000,  0.000), 0.0, 1.8) * 0.26;
c += causticBandImproved(uv + mw * 0.7,  9.3,  0.41, vec2( 7.139, 13.000), 1.0, 2.2) * 0.22;
c += causticBandImproved(uv + mw * 1.1, 13.7,  0.57, vec2(17.321,  4.472), 2.0, 2.5) * 0.18;
c += causticBandImproved(uv,             6.2,  0.19, vec2(31.623, 22.360), 3.0, 1.6) * 0.14;
c += causticBandImproved(uv + mw * 0.3, 11.1,  0.33, vec2( 2.646, 44.721), 4.0, 2.0) * 0.12;
c += causticBandImproved(uv + mw * 1.4, 18.4,  0.72, vec2(54.772,  8.944), 5.0, 3.0) * 0.08;
```

### `causticBandImproved` parameter reference

| Parameter | Type | Effect |
|---|---|---|
| `uv` | `vec2` | Input UV — apply `mw` cursor offset here for interactive focus |
| `cellFreq` | `float` | Cell density — higher = smaller bubbles, more cells |
| `speed` | `float` | Animation speed multiplier |
| `seed` | `vec2` | UV offset — break inter-octave alignment |
| `octIdx` | `float` | Octave index 0–5 — drives 11.25° rotation stagger |
| `sharp` | `float` | Power curve exponent — higher = tighter filament lines |

### Per-variant caustic tinting

In v4.1 the `u_causticScale` and `u_causticTint` uniforms are uploaded from the active glass variant. To override caustic character independently of the variant, modify the variant definition before passing it to `setGlassVariant()`, or patch the uniforms directly via a fork of the source.

### Overall brightness

```glsl
// In main(), step 5–6 of the composition pass:
float cBase = pow(caustic(uvA), 1.7) * u_causticScale;
vec3 col = u_causticTint * cBase * 0.52 + chromCaustic * 0.5;

// Quieter:
vec3 col = u_causticTint * cBase * 0.25 + chromCaustic * 0.3;

// More pronounced:
vec3 col = u_causticTint * cBase * 0.70 + chromCaustic * 0.7;
```

### Quick tuning reference

| Parameter | Location | Effect |
|---|---|---|
| `cellFreq` | `caustic()` in `_FRAG_SRC` | Bubble size — higher = smaller |
| `sharp` | `caustic()` in `_FRAG_SRC` | Filament tightness |
| Octave `* N` weight | `caustic()` in `_FRAG_SRC` | Per-octave brightness contribution |
| `cBase * N` | `main()` in `_FRAG_SRC` | Master caustic brightness multiplier |
| `chromCaustic * N` | `main()` in `_FRAG_SRC` | Chromatic caustic split brightness |
| `pow(caustic(uvA), 1.7)` exponent | `main()` | Global contrast |
| `causticScale` | `GLASS_VARIANTS[key]` | Per-variant caustic intensity |
| `causticTint` | `GLASS_VARIANTS[key]` | Per-variant caustic colour |

---

## GPU Tiers & Fallback Strategy

### Tier `high` — Full WebGL2
*Desktop and Apple silicon (M-series) GPUs.*

- html2canvas background capture → Snell's law UV refraction
- Sellmeier per-channel IOR dispersion (R/G/B at physical wavelengths)
- Beer-Lambert chromatic absorption + frosted scatter + mirror reflection (v4.1)
- Six-octave Voronoi caustics (PCG2D, F2−F1, domain warp, rotation stagger)
- Environment reflection probe (Fresnel-weighted planar mirror)
- Cook-Torrance PBR specular on `.lg-specular-canvas`
- SVG chromatic aberration at full `aberrationStrength`

### Tier `mid` — Caustics + Specular
*Adreno 500–600, Mali-G57/G75.*

- Same as `high` but chromatic aberration at 50% strength
- Refraction may be disabled if `EXT_color_buffer_float` is unavailable

### Tier `low` — CSS only
*Legacy mobile GPUs, WebGL2 unavailable, restricted CSP.*

- `::before` — three GGX-lobe radial-gradients derived from GGX NDF α=0.04, A=0.35
- `:hover` — seven-layer box-shadow stack synchronised with L0 intensity ×1.5
- `::after` — thin-film iridescence conic-gradient with Born & Wolf 120°/240° phase offsets
- SVG filter bank and spring physics still fully active
- Glass variant CSS classes still applied (backdrop-filter varies per variant)

All tiers produce a recognisable glass element. GPU-specific visual layers are purely additive.

---

## Physics Reference

### Glass Constants (§15)

| Constant | Value | Physical basis |
|---|---|---|
| `GLASS_IOR` | Sellmeier n(550nm) | Green-channel IOR from selected glass type |
| `GLASS_F0` | `((n−1)/(n+1))²` | Fresnel at normal incidence — derived from Sellmeier |
| `FILM_THICKNESS` | 320 nm | MgF₂ antireflection coating thickness |
| `FILM_IOR` | 1.38 | MgF₂ coating refractive index |
| `BASE_ROUGHNESS` | 0.04 | α = roughness² — near-specular glass microsurface |
| `ANISOTROPY` | 0.35 | Burley 2012 tangent axis stretch |

### Specular BRDF

```
f_r(l,v) = D(h)·F(v,h)·V(l,v) + f_ms(l,v)
```

- **D** — Anisotropic GGX NDF (Burley 2012): `αT = α/√(1−0.9·A) ≈ 0.0483`, `αB = α·√(1−0.9·A) ≈ 0.0331`
- **F** — Schlick: `F0 + (1−F0)·(1−VdotH)⁵`, F0 = `((n_G−1)/(n_G+1))²` from Sellmeier
- **V** — Smith height-correlated GGX (Heitz 2014): `0.5 / (NdotL·√(NdotV²(1−a²)+a²) + NdotV·√(NdotL²(1−a²)+a²))`
- **f_ms** — Kulla-Conty multi-bounce (2017): `(1−E(NdotV))·(1−E(NdotL)) / (π·(1−E_avg))`

### Three-Light Config (§15.K)

| Light | Colour | Intensity | Position |
|---|---|---|---|
| L0 — key | warm white `(1.00, 0.97, 0.92)` | `2.8 + hover·1.4` | cursor-tracking |
| L1 — fill | cool blue `(0.88, 0.93, 1.00)` | `0.55` | static upper-left |
| L2 — back | violet `(0.76, 0.70, 1.00)` | `0.30` | mirror of L0 |

### Beer-Lambert Transmission (v4.1 — §H2)

```
σ_ch   = (1.0 − tintRGB_ch) · tintStrength · 3.5
I_ch   = I₀_ch · exp(−σ_ch)
+ emission_ch = tintRGB_ch · tintStrength · 0.06   (fluorescence term)
```

### Thin-Film Iridescence (§15.H — Born & Wolf 1999)

```
OPD = 2 · FILM_IOR · FILM_THICKNESS · cos(θt)
    = 2 · 1.38 · 320 · cos(0°) = 883.2 nm

I(λ) = 0.5 + 0.5 · cos(2π · OPD / λ)
```

Phase shifts at normal incidence: 0° / 120° / 240° for λR / λG / λB. Same offsets used in CSS fallback conic-gradient.

### Voronoi Caustic System (§D)

**PCG2D hash** (Jarzynski & Olano 2020):
```glsl
uvec2 v = p * uvec2(1664525u, 1013904223u) + uvec2(1013904223u, 1664525u);
v.x += v.y * 1664525u;  v.y += v.x * 1664525u;  v ^= (v >> 16u);
v.x += v.y * 1664525u;  v.y += v.x * 1664525u;  v ^= (v >> 16u);
return vec2(v) * (1.0 / 4294967295.0);
```

**F2−F1 distance field**: `return clamp(minD2 - minD1, 0.0, 1.0);` — peaks at cell boundaries.

**Domain warp**: `uv + vec2(wx, wy) * 0.18` — max ±0.18 UV offset from gnoise at 2.3× / 1.7× frequency.

**Rotation stagger**: `octIdx * 0.19635` radians (11.25° = π/16 per octave).

### Spring Physics (§3)

Semi-implicit (symplectic) Euler — unconditionally stable for all positive dt:

```
F        = −k·(x − target) − d·v
v(t+dt)  = v(t) + (F/m)·dt    ← velocity first
x(t+dt)  = x(t) + v(t+dt)·dt
```

| Preset | Stiffness | Damping | Mass | Character |
|---|---|---|---|---|
| `cursor` | 180 | 18 | 1.0 | Fast, snappy |
| `hover` | 120 | 14 | 1.0 | Slightly slower fade |
| `tilt` | 90 | 12 | 1.2 | Heavy, inertial |

Max delta-time capped at 50 ms to prevent integrator explosion on tab wake-up.

---

## Performance Notes

**Shared GL contexts** — both caustic (§6) and specular (§15) passes use a single `WebGL2RenderingContext` each, shared across all glass elements. Canvas resized per-element before each draw.

**IntersectionObserver gate** — elements outside the viewport skip all WebGL work entirely. Threshold: 0, no root margin — gate activates the moment any pixel enters or leaves the viewport.

**Frame budgets (60 fps, high tier):**

| Operation | Frequency | Reasoning |
|---|---|---|
| Spring integration + CSS props | Every frame (60 fps) | Required for smooth cursor tracking |
| Specular GL pass | Every frame (60 fps) | Cursor-tracking L0 needs full rate |
| Caustic GL pass | Every 2nd frame (≈30 fps) | Caustic noise is slow-moving; halving is imperceptible |
| domRect refresh | Every 8th frame (≈7.5 Hz) | Reduces layout thrash |
| `data-lg-refract` sync | Every 30th frame (≈2 Hz) | Data attribute, no urgency |
| Background capture | `bgCaptureInterval` + scroll/resize | Via requestIdleCallback |

**Glass variant overhead** — uploading the seven variant uniforms (`u_tintRGB`, `u_tintStrength`, `u_frostedAmount`, `u_mirrorStrength`, `u_smokeDensity`, `u_causticScale`, `u_causticTint`) adds negligible CPU cost. Frosted glass (`frostedAmount > 0.02`) triggers three extra `texture()` taps in the GLSL frosted scatter pass — the most expensive of the new uniforms.

**Hard cap** — `MAX_WEBGL_ELEMENTS = 32`. Elements beyond this count receive CSS fallback only.

**Recommendations:**
- Keep `bgCaptureScale` at `0.35` or below for most use cases
- Increase `bgCaptureInterval` to 3000–5000 ms on pages with stable backgrounds
- Use `caustics: false` on decorative elements that don't need the full effect
- `glassType: 'NK51A'` has the smallest per-channel IOR spread — marginally cheaper
- `glassVariant: 'frosted'` is the most GPU-intensive variant due to the three-tap scatter pass
- `glassVariant: 'clear'` or `'mirror'` have no scatter cost

---

## Known Issues & Fixes

### `.lg-specular-canvas` stretching to 4096px

**Root cause:** `buildSpecularCSS()` (§15.4, the exported function) correctly includes `position: absolute` for `.lg-specular-canvas`. However, the internal `_buildSpecularCSS()` (§16, called by `_buildCSS()`) only sets `transition` and `pointer-events` — it omits `position`. Since `_buildCSS()` calls the internal version, `position: absolute` never reaches the injected stylesheet, leaving each specular canvas at `position: static`. A 4096×4096 in-flow canvas then stretches its parent `.lg` to 4096px.

**Fix:** add `position: absolute !important; inset: 0 !important; width: 100% !important; height: 100% !important;` to the `.lg-specular-canvas` block inside `_buildSpecularCSS()` (§16). This is already applied in v4.1.0.

---

## Browser Support

| Browser | Caustics + Refraction | PBR Specular | CSS Fallback |
|---|---|---|---|
| Chrome 90+ | ✅ | ✅ | ✅ |
| Firefox 90+ | ✅ | ✅ | ✅ |
| Safari 16.4+ | ✅ | ✅ | ✅ |
| Safari 15 | ❌ | ✅ | ✅ |
| iOS Safari 16+ | ✅ | ✅ | ✅ |
| iOS Safari 15 | ❌ | ❌ | ✅ |
| Samsung Internet 16+ | ✅ | ✅ | ✅ |

`EXT_color_buffer_float` is required for the refraction pass (floating-point background texture). Browsers that lack it fall through gracefully to the specular-only or CSS-only path.

---

## Changelog

### v4.1.0

**Glass Variant System (`GLASS_VARIANTS`, `setGlassVariant()`, `getGlassVariants()`)**
- Twelve physically-grounded surface presets from real optical constants
- `GlassVariantDef` type: `{ label, cssClass, ior, tintRGB, tintStrength, frosted, mirror, smokeDensity, causticScale, causticTint, blurPx, saturate, brightness, bgTint }`
- `setGlassVariant(key)` removes old variant class, applies new one, updates `_opts.ior` and `_opts.glassVariant`
- `getGlassVariants()` returns shallow copy of `GLASS_VARIANTS` for picker UIs
- Runtime IOR sync: `setGlassVariant()` also patches `_opts.ior` to the variant's physical IOR

**Beer-Lambert chromatic absorption (§H2)**
- `u_tintRGB` + `u_tintStrength` + `u_smokeDensity` uniforms added to fragment shader
- `beerLambertTransmit()` GLSL function: σ = (1−tintRGB)·tintStrength·3.5, I = I₀·exp(−σ)
- Fluorescence emission term: `tintRGB · tintStrength · 0.06`
- Applied to `refractedBg` before caustic compositing

**Frosted scatter refraction (§H3)**
- `u_frostedAmount` uniform
- `frostedScatterRefraction()`: three-tap average with large-scale (11×) + fine (27×) noise UV jitter
- Mixed with `chromaticRefraction()` by `frostedAmount` in `main()`

**Mirror reflection mode (§12 composition)**
- `u_mirrorStrength` uniform
- `transmitFactor = 1.0 − u_mirrorStrength · 0.92` applied to `refrBlend`
- `environmentReflection()` amplified by `(1.0 + u_mirrorStrength · 5.5)`

**Smoke density (§12 composition)**
- `col *= (1.0 − u_smokeDensity · 0.68)` as final pre-vignette step

**WebGL uniform upload (§6.1 `_renderCausticsGL`)**
- `gl.uniform3f(u_tintRGB, ...)`, `gl.uniform1f(u_tintStrength, ...)`, `u_frostedAmount`, `u_mirrorStrength`, `u_smokeDensity`, `u_causticScale`, `gl.uniform3f(u_causticTint, ...)` all uploaded from `GLASS_VARIANTS[_opts.glassVariant]` each frame

**CSS variant override layer (§8)**
- Twelve `.lg-v-{name}` rule blocks added to `_buildCSS()` output
- Each overrides `backdrop-filter` and `background` gradient for first-frame accuracy
- Variant-specific hover/active states per class
- Shared `.lg.lg-interactive:hover` brightness overrides for tinted/dark variants

**_buildSpecularCSS() §16 bugfix**
- Added `position: absolute !important; inset: 0 !important; width: 100% !important; height: 100% !important;` to `.lg-specular-canvas` block — fixes 4096px height stretch

**`_opts` default additions**
- `glassVariant: 'clear'` added to `_defaults`

---

### v4.0.0

**§C — Sellmeier dispersion replaces Cauchy approximation**
- Full three-term Sellmeier equation in GLSL: `n²(λ) = 1 + Σ Bⱼλ²/(λ²−Cⱼ)`
- Five glass types from Schott catalogue 2023: BK7, SF11, N-FK51A, N-BK10, F2
- RMS error < 0.0001 vs spectrometer across 380–750 nm
- Per-channel IOR at λR=680nm / λG=550nm / λB=450nm
- `u_glassType` uniform (float 0–4), mapped from `glassType` option string
- Fresnel F0 now derived from Sellmeier n(550nm) — was fixed 0.04 in v3

**§D — Improved Voronoi caustic system**
- PCG2D integer hash (Jarzynski & Olano 2020, JCGT Vol 9 No 3) — no lattice bias, period 2³² per axis, ~30% faster on GPU
- F2−F1 distance field replaces F1 — peaks at cell boundaries, eliminates pillow artefact
- Domain warping (IQ "Warped domain Voronoi")
- Per-cell independent animation: 4 PCG2D scalars (rx, ry, px, py) per cell + depth scalar
- Six octaves (was four) with 11.25° (π/16) rotation stagger
- 3×3 neighbourhood search (was 5×5)

**§15 — Full Cook-Torrance PBR Specular WebGL2 pass**
- Anisotropic GGX NDF (Burley 2012)
- Smith height-correlated visibility (Heitz 2014)
- Schlick Fresnel — F0 from Sellmeier n(550nm)
- Kulla-Conty multi-bounce energy compensation (2017)
- Thin-film iridescence (Born & Wolf 1999, d=320nm, n=1.38)
- Area light representative-point approximation (Karis 2013)
- Three-light configuration: L0 cursor key, L1 static fill, L2 back-scatter
- Dedicated `.lg-specular-canvas` per element

**§G — chromaticRefraction() updated for Sellmeier**
- Per-channel displacement delta uses `iorR`, `iorG`, `iorB` from Sellmeier
- SF11 shows 3.7× more chromatic splitting than BK7

**`getOptions()` now returns live reference** (was shallow copy in v3)

---

### v3.0.0

- Screen-space background refraction (html2canvas → WebGL2 texture)
- Cook-Torrance PBR specular pass (§15)
- `_buildSpecularCSS()` CSS fallback layer (§16)
- `specularStrength` and `specularWhiteness` init options
- IntersectionObserver viewport gate
- Frame-budget system (`_rafFrame` counter)
- `MAX_WEBGL_ELEMENTS = 32` hard cap

### v2.x

- Voronoi caustics (4 animated octaves, sin()-based hash, F1 metric)
- SVG chromatic aberration + micro-distortion filter bank
- Spring physics (semi-implicit Euler, three presets)
- Device orientation gyroscope support
- `createReplyQuote()` helper
- React hook `useLiquidGlass()` (§14)
- MutationObserver auto-discovery

### v1.x

- CSS-only glass effect
- `backdrop-filter` blur + saturation
- Film grain overlay
- Initial spring physics cursor tracking

---

## License

[Apache 2.0](http://www.apache.org/licenses/LICENSE-2.0) © 2026 Boris Maltsev
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
