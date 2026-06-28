---
name: Chain Calm — SCRMS
description: Supply chain risk intelligence dashboard for operations analysts and risk managers
colors:
  bg: "#080c16"
  surface: "#0b111e"
  surface-raised: "#182130"
  surface-overlay: "#222f44"
  border: "#1f2a3d"
  foreground: "#f8fafc"
  muted-fg: "#7588a3"
  primary: "#3c83f6"
  primary-fg: "#080c16"
  sidebar-bg: "#0a0f1a"
  sidebar-fg: "#b8cce0"
  risk-low: "#1cce5e"
  risk-medium: "#e7b008"
  risk-high: "#ef4343"
  risk-critical: "#d31212"
  destructive: "#ef4343"
typography:
  display:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "2rem"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Inter, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "0.01em"
rounded:
  sm: "8px"
  md: "12px"
  lg: "12px"
  full: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  "2xl": "48px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-fg}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "#2d6ee0"
    textColor: "{colors.primary-fg}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  button-outline:
    backgroundColor: "transparent"
    textColor: "{colors.foreground}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.foreground}"
    rounded: "{rounded.sm}"
    padding: "8px 16px"
  badge-risk-low:
    backgroundColor: "rgba(28, 206, 94, 0.2)"
    textColor: "{colors.risk-low}"
    rounded: "{rounded.full}"
    padding: "4px 10px"
  badge-risk-medium:
    backgroundColor: "rgba(231, 176, 8, 0.2)"
    textColor: "{colors.risk-medium}"
    rounded: "{rounded.full}"
    padding: "4px 10px"
  badge-risk-high:
    backgroundColor: "rgba(239, 67, 67, 0.2)"
    textColor: "{colors.risk-high}"
    rounded: "{rounded.full}"
    padding: "4px 10px"
  badge-risk-critical:
    backgroundColor: "rgba(211, 18, 18, 0.2)"
    textColor: "{colors.risk-critical}"
    rounded: "{rounded.full}"
    padding: "4px 10px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.lg}"
    padding: "20px"
  input-default:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
---

# Design System: Chain Calm — SCRMS

## 1. Overview

**Creative North Star: "The Operations Room"**

Chain Calm is built for the operator who is already in the work — scanning for signals, ready to act. The interface is a dark, dense instrument. Every element earns its presence through operational necessity, not visual decoration. The atmosphere is that of a maritime control room or a NOC monitor wall: purposeful light in a dark environment, each illuminated element carrying meaning. Nothing glows that doesn't have a reason to glow.

The design language is restrained almost to severity. The dark navy-black surface (#080c16) recedes completely so that data has the foreground. Surface hierarchy is expressed through tonal steps — bg → card → popover are distinct tones at fixed distances, never shadows. Motion exists only when state changes: a badge shifting from amber to red, a panel sliding in, an ingest status pulsing. No choreography, no ambient animation.

This system explicitly rejects the idiom of typical SaaS analytics (purple-on-light, gradient-hero metrics, dashboard-as-marketing) and generic BI tool defaults (gray sidebar, flat blue bars, corporate blandness). It is not a product demo — it is the thing a risk analyst stares at for a full shift. It must never demand attention; it must only deliver it.

**Key Characteristics:**
- Deep navy-black base surface with three distinct tonal layers
- Single Inter family across all roles — no display/body split
- Risk tier vocabulary (green / amber / red / deep-red) is the only non-neutral color on most screens
- Primary blue (#3c83f6) reserved for actions, focus, and current selection — never decoration
- Elevation expressed through background tone, never shadow
- Motion confined to state transitions (150–250ms, ease-out-quart)

## 2. Colors: The Instrument Palette

A near-monochrome dark surface carrying one action blue and a four-tier semantic risk vocabulary.

### Primary
- **Action Blue** (#3c83f6): Primary interactive element color. Used on active navigation items, primary buttons, focus rings, and selection states. Passes WCAG AA (5.4:1 on background). Never used decoratively — only on elements the user can interact with or that represent current selection.

### Tertiary
- **Sidebar Steel** (#b8cce0): Foreground color in the sidebar panel. Slightly desaturated to reduce visual weight against the sidebar's deeper bg (#0a0f1a). Inactive nav labels only.

### Neutral
- **Void** (#080c16): Application background. The deepest surface layer. Only the page bg and modal backdrops.
- **Panel Dark** (#0b111e): Card and panel surface. The primary content container background — one tonal step above Void.
- **Recessed** (#182130): Muted content backgrounds, input fields, secondary panels. Visually below Panel Dark.
- **Overlay** (#222f44): Hover states, accent backgrounds, interactive surface highlights. The lightest persistent neutral.
- **Boundary** (#1f2a3d): All borders and dividers. Structural only — never used as a color accent.
- **Body** (#f8fafc): Primary text. Near-white with a faint blue-tint inherited from the hue. Contrast 18.7:1 on Void.
- **Subdued** (#7588a3): Secondary labels, metadata, timestamps, placeholder text. Contrast 5.0:1 on Void — passes WCAG AA. Borderline at smaller sizes; avoid below 13px.
- **Sidebar Base** (#0a0f1a): Sidebar background. Slightly deeper than Void to create visible left-edge separation.

### Named Rules

**The Signal Rule.** Risk tier colors (risk-low, risk-medium, risk-high, risk-critical) are used exclusively to communicate disruption severity. They never appear as brand decoration, chart fills for neutral data, or background tints on non-risk UI. Their rarity is what makes them legible under pressure.

**The One Blue Rule.** Primary (#3c83f6) appears on ≤10% of any given screen. Active nav item, primary CTA, focus ring. When everything is blue, nothing is a call to action.

## 3. Typography

**Body Font:** Inter (with system-ui, sans-serif fallback)
**Label/Data Font:** Inter (same family, weight-differentiated)

**Character:** A single family carrying the entire hierarchy. Inter's neutrality and optical clarity at small sizes make it correct for a data-dense instrument UI. Pairing two sans families here would create noise without meaning; weight and size differentiation within one family provides all the necessary contrast.

### Hierarchy

- **Display** (700, 2rem / 32px, line-height 1.1, letter-spacing -0.02em): Page-level headings. Rare — major section titles only. Never in data rows or cards.
- **Headline** (600, 1.5rem / 24px, line-height 1.25, letter-spacing -0.01em): Panel headings, dialog titles, chart labels.
- **Title** (600, 1.125rem / 18px, line-height 1.4): Card titles, section headers, supplier node names.
- **Body** (400, 0.875rem / 14px, line-height 1.6): Default text, event descriptions, prose content. Cap at 65–75ch for readability in wider content panels.
- **Label** (500, 0.75rem / 12px, line-height 1.4, letter-spacing 0.01em): Metadata, timestamps, table headers, badge text. Never below 11px.

### Named Rules

**The Monotone Rule.** One family, differentiated by weight and size. Display fonts in buttons, labels, or data cells are prohibited — they introduce design-for-its-own-sake noise that degrades trust in a risk context.

**The Fixed Scale Rule.** No fluid `clamp()` scaling. Product UI is viewed at consistent DPI on operator workstations. A fluid h1 that shrinks in a sidebar is worse, not better.

## 4. Elevation

This system uses tonal layering, not shadows. Depth is expressed through discrete background color steps: Void → Panel Dark → Recessed → Overlay. A surface "above" another surface has a lighter background tone, not a shadow beneath it. The layers are visually distinct but the transitions are subtle — the goal is legibility, not visual drama.

The one exception is semantic glow: risk-tier elements (badges, node markers, alert indicators) emit a soft diffuse glow (`box-shadow: 0 0 20px hsl(risk-color / 0.3)`) that communicates urgency through light rather than shape. This is purposeful, not decorative — the glow intensifies when risk is elevated, fades when it resolves.

Floating elements (dropdowns, tooltips, popovers) use a subtle `shadow-xl` (`0 20px 25px -5px rgba(0,0,0,0.5), 0 8px 10px -6px rgba(0,0,0,0.4)`) to separate them from the tonal stack. This is the only context where shadows are used.

### Named Rules

**The Flat-By-Default Rule.** Surfaces are flat at rest. Shadows appear only on floating elements (dropdowns, tooltips, modals). Tonal differentiation — not shadow — is the language of layering in this system. If you reach for `box-shadow` on a card, reconsider whether a background-color step would do the same job.

**The Semantic Glow Rule.** Colored glow is a state indicator, not decoration. The risk-glow utilities (risk-glow-low, risk-glow-medium, risk-glow-high) exist exclusively on risk-tier UI elements. Never apply them to decorative containers, feature cards, or marketing surfaces.

## 5. Components

### Buttons

Measured and direct. Buttons carry function, not personality. Rounding is consistent (8px / `rounded-sm`) across all variants.

- **Shape:** Gently rounded (8px). Not pill-shaped, not square — enough softness to read as interactive without drawing visual weight.
- **Primary:** Action Blue (#3c83f6) background, Void text (#080c16). Height 40px, padding 8px 16px. Font 14px / 500.
- **Hover / Focus:** Hover darkens to #2d6ee0 (90% primary). Focus ring: 2px solid primary, 2px offset. Transition 150ms ease-out.
- **Outline:** Transparent bg, Boundary border (#1f2a3d), Body text (#f8fafc). Hover fills to Overlay (#222f44). Used for secondary actions in toolbars.
- **Ghost:** No border, no background. Hover fills to Overlay (#222f44). Used inline in data rows and compact controls.
- **Disabled:** 50% opacity across all variants. Pointer-events none.

### Risk Badges

The signature component. Pill shape (`border-radius: 9999px`), color-keyed dot + label. The dot ensures color is never the sole signal (accessibility).

- **Low (green):** Background rgba(28, 206, 94, 0.2), text and dot #1cce5e. Padding 4px 10px.
- **Medium (amber):** Background rgba(231, 176, 8, 0.2), text and dot #e7b008.
- **High (red):** Background rgba(239, 67, 67, 0.2), text and dot #ef4343.
- **Critical (deep red):** Background rgba(211, 18, 18, 0.2), text and dot #d31212.
- All sizes: sm (12px / 0.5rem pad), md (14px / 1rem pad), lg (16px / 1.5rem pad).

### Cards / Containers

- **Corner Style:** Gently rounded (12px / `rounded-lg`).
- **Background:** Panel Dark (#0b111e). Never Void — cards must read above the page background.
- **Shadow Strategy:** None at rest. Semantic glow added on risk-tier variants via utility classes.
- **Border:** Boundary (#1f2a3d), 1px. Always present — the visual container cannot rely on bg contrast alone against Panel Dark.
- **Internal Padding:** 20px (spacing.lg equivalent). Card headers use 24px (p-6).
- **Hover:** `scale(1.02)` over 300ms for interactive cards. Framer Motion `initial={{opacity:0, y:20}} animate={{opacity:1, y:0}}` for entrance. No bounce curves.

### Inputs / Fields

- **Style:** Background Void (#080c16), border Boundary (#1f2a3d), radius 8px, padding 8px 12px.
- **Placeholder:** Subdued (#7588a3). Contrast 5.0:1 — passes WCAG AA.
- **Focus:** Border shifts to primary (#3c83f6), inner glow `box-shadow: 0 0 0 3px rgba(60, 131, 246, 0.2)`. Transition 150ms.
- **Disabled:** 50% opacity, cursor not-allowed.

### Navigation (Sidebar)

- **Default:** Sidebar foreground (#b8cce0), transparent background, 10px 12px padding, 8px radius.
- **Hover:** Overlay background (#222f44), Body text (#f8fafc).
- **Active:** Primary (#3c83f6) background, Void text (#080c16). The only persistent use of primary as a background.
- **Collapsed:** Icon-only at 72px width. Framer Motion `animate={{ width: collapsed ? 72 : 240 }}`, 200ms ease-in-out.
- **Logo mark:** Primary-tinted square (8px radius, primary bg, white Shield icon).

### Risk Node Markers (World Map)

The signature visualization component. Circular SVG markers on the world map that pulse at a rate modulated by risk level.

- Color follows risk tier vocabulary exactly (riskColors map).
- Outer pulse ring uses CSS `animation: pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite`.
- Selected state: expanded radius, elevated opacity, `box-shadow` glow at 0.5 opacity.
- `@media (prefers-reduced-motion: reduce)`: remove animation, keep color only.

### Progress Bars (Supplier Exposure)

Thin 6px track (Recessed #182130 background), filled segment follows risk-tier color based on exposure value thresholds. No rounded pill for the fill — flat ends on the fill track for precision readability.

## 6. Do's and Don'ts

### Do:
- **Do** use Action Blue (#3c83f6) only for interactive states: active nav, primary buttons, focus rings, and current selection indicators. Its scarcity is its meaning.
- **Do** express depth through background tonal steps (Void → Panel Dark → Recessed → Overlay), not through `box-shadow` on content surfaces.
- **Do** always pair a risk color with a text label or icon — never rely on color as the sole risk signal. Every RiskBadge includes a colored dot AND a label.
- **Do** verify muted text contrast (Subdued #7588a3 = 5.0:1 on bg). Never go lower than this for any body content. At 11px or below, use Body (#f8fafc) instead.
- **Do** reduce motion to instant transitions or crossfades under `prefers-reduced-motion: reduce`. Every pulsing animation, entrance, and panel slide needs this override.
- **Do** keep risk glow utilities (risk-glow-low, risk-glow-medium, risk-glow-high) exclusive to components that communicate risk severity — StatsCard variants, node markers, alert indicators.
- **Do** use `text-wrap: balance` on panel headings and card titles to prevent orphaned words.
- **Do** build a semantic z-index scale: overlay (10) → dropdown (20) → sticky (30) → modal-backdrop (40) → modal (50) → toast (60) → tooltip (70). No arbitrary 999 values.

### Don't:
- **Don't** use gradient text (`background-clip: text` with a gradient background). The `.text-gradient` utility in `index.css` violates this rule and should be removed. Use a solid primary (#3c83f6) for emphasis text instead.
- **Don't** use glassmorphism (`backdrop-blur` + semi-transparent backgrounds) as the default card surface. The `.glass-card` utility exists for specific floating overlay contexts only (panels that genuinely float over live map content). Applying it to standard content cards degrades to decoration.
- **Don't** build an interface that looks like typical SaaS analytics — no purple-on-light themes, no gradient hero metrics, no big-number-small-label stat cards with gradient accents. The data is operational, not promotional.
- **Don't** make the interface look like a generic BI tool — no gray sidebars, no flat default-blue bar charts, no corporate-bland table styling. This is a risk intelligence system with real operational stakes.
- **Don't** use risk tier colors (green, amber, red, deep-red) for neutral data visualization, decorative fills, or background tints on non-risk content. When risk colors appear everywhere, they stop communicating risk.
- **Don't** apply uppercase tracked labels (`text-xs font-bold uppercase tracking-widest`) as section kickers. One use as a deliberate system element is voice; an eyebrow on every section heading is template scaffolding.
- **Don't** animate layout properties (width, height, margin, padding) under normal scroll or hover conditions. Transform and opacity only.
- **Don't** render dropdowns with `position: absolute` inside an `overflow: hidden` container — they will be clipped. Use `position: fixed` or the native `<dialog>` / popover API.
