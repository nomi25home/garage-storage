# Kapaat Design System — v1.2.3

**Status:** Proposed (awaiting implementation sign-off)  
**Branch:** `main`  
**Product:** Self-hosted storage inventory SPA — scan a QR, read a bin, edit a row, move items in bulk.  
**Memory:** "It feels like opening a well-organized toolbox — quick, certain, no friction."

---

## 1. Color

### Tokens (dark mode default)

```css
:root {
  /* Neutral scale — step-10 increments, all values in HSL space for safe interpolation */
  --bg:       #0b1326;  /* page background */
  --lowest:   #060e20;  /* deepest surface (modal, toast) */
  --low:      #131b2e;  /* table rows, card interiors */
  --cont:     #171f33;  /* containers (header, filters, drawer) */
  --high:     #222a3d;  /* sticky headers, hovered rows */
  --highest:  #2d3449;  /* active/selected row, scrollbar thumb */
  --bright:   #31394d;  /* hover on interactive surfaces */

  /* Text & borders */
  --on:           #dae2fd;  /* primary text */
  --on-var:       #bcc9cd;  /* secondary / muted text */
  --outline:      #869397;  /* default borders, chip outlines */
  --outline-var:  #3d494c;  /* subtle borders (input, card) */

  /* Accents — ONE primary, others functional only */
  --primary:        #4cd7f6;  /* interactive color: links, focus rings, active chips, primary buttons, selected row indicator */
  --primary-cont:   #06b6d4;  /* primary button background */
  --on-primary-cont:#00424f;  /* primary button text */

  --amber:   #f5c26b;  /* warning/attention banner ONLY */
  --green:   #4edea3;  /* success/status indicator ONLY */
  --error:   #ffb4ab;  /* destructive actions, error text */

  /* Typography */
  --mono: "JetBrains Mono", ui-monospace, monospace;
  --sans: "Geist", system-ui, sans-serif;
}
```

### Usage rules

| Token | Where it appears | NOT for |
|-------|------------------|---------|
| `--primary` | Links, focus rings, `.chip.on`, `.btn.primary`, selected row inset, primary CTAs | backgrounds, large fills, decorative elements |
| `--primary-cont` | `.btn.primary` background | anything else |
| `--amber` | `.banner` (conflict/attention), warning toast left border | buttons, links, chips |
| `--green` | success toast left border, "synced" badge | buttons, links, general UI |
| `--error` | `.btn.danger`, error toast left border, destructive action focus | anything else |
| `--outline` | default borders, `.chip`, `.tag`, `.btn` border | focus states (use `--primary`) |

### Light mode (opt-in, not shipped yet)

```css
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {
    --bg:       #f8fafc;  --lowest: #ffffff;  --low: #f1f5f9;
    --cont:     #e2e8f0;  --high: #cbd5e1;    --highest: #94a3b8;  --bright: #64748b;
    --on:       #0f172a;  --on-var: #475569;  --outline: #94a3b8; --outline-var: #cbd5e1;
    --primary:  #0891b2;  --primary-cont: #0e7490; --on-primary-cont: #ffffff;
    --amber:    #b45309;  --green: #166534;    --error: #b91c1c;
  }
}
```

---

## 2. Typography

| Role | Font | Size / Line-height | Weight | Use |
|------|------|-------------------|--------|-----|
| Display / brand | Geist | 17px / 1.0 | 700 | Header brand text |
| Heading (h3) | Geist | 17px / 1.2 | 600 | Drawer titles |
| Subheading (h4) | JetBrains Mono | 10px / 1.4 | 600, uppercase, letter-spacing 0.06em | Card section headers |
| Body / UI | Geist | 13px / 1.38 | 400 | Default text, inputs, buttons |
| Dense / data | JetBrains Mono | 12px / 1.33 | 400 | Table cells, tags, monospace labels |
| Micro / labels | JetBrains Mono | 10px / 1.4 | 400, uppercase, letter-spacing 0.05em | Chip text, column headers, k/v keys |

**No other font weights or families are used.** The Material Symbols Outlined icon font (`ms` class) is loaded from Google Fonts and stays at 18px/1.

---

## 3. Spacing & Layout

### Base unit: 4px

| Token | Value | Use |
|-------|-------|-----|
| `--space-1` | 4px | inline gaps, icon-button padding |
| `--space-2` | 8px | component internal padding, card gaps |
| `--space-3` | 12px | card padding, section margins |
| `--space-4` | 16px | page margins, drawer side padding |
| `--space-5` | 20px | header horizontal padding, section horizontal padding |
| `--space-6` | 24px | large vertical gaps, modal side padding |

### Layout constants

| Token | Value | Purpose |
|-------|-------|---------|
| `--header-h` | 48px | sticky header height |
| `--strip-h` | 42px | KPI strip height |
| `--drawer-w` | 400px | right drawer width |
| `--modal-max-w` | 480px | modal max-width |
| `--radius` | 3px | universal border radius (buttons, inputs, cards, tags) |

### Grid / density

- Table rows: 36px line-height (13px font + 23px vertical padding split)
- Filter chips: 24px height
- Buttons: 28px height (primary/secondary), 32px in drawer footer
- Inputs: 32px height

---

## 4. Components

### 4.1 Header (sticky, 48px)
- Brand: logo SVG + app name, cyan color
- Crumb pill (mobile: hidden; desktop: shows bin count when drilling)
- Search input: 32px height, monospace, 32px right padding for kbd hint
- Actions: primary button, secondary button, icon buttons (export, backup, full-backup, login/logout)
- User avatar/name (when authenticated) + logout
- Border-bottom: `1px solid var(--outline-var)`

### 4.2 Filter strip (sticky, below header)
- Chip group: Room | Zone | Shelf | Bin (multi-select, `.chip.on` gets primary border/color)
- Tags filter (dropdown or chip group)
- Search cleared when any filter changes

### 4.3 Data table
- Sticky header row (th): 11px mono uppercase, `--high` bg, bottom border
- Row: `--lowest` bg, bottom border `rgba(61,73,76,.4)`
- Hover: `rgba(23,31,51,.8)`
- Selected: `--high` bg + `inset 2px 0 var(--primary)`
- Photo column: 48px fixed, thumbnail 40px square, `object-fit: cover`
- Tag: inline-block, mono 10px, uppercase, border, `--high` bg
- Sub text: 11px mono, `--outline` color

### 4.4 Drawer (right, 400px, mobile: full-width fixed bottom sheet)
- Header: title + close (17px Geist 600)
- Cards: `--cont` bg, `--outline-var` border, 3px radius
- Inner card: `--lowest` bg, `rgba(61,73,76,.6)` border
- Key/value grid: 80px label column, mono 12px value
- Actions at bottom (`.dfoot`): full-width buttons, 32px height

### 4.5 Modal
- Backdrop: `rgba(0,0,0,.7)` + `backdrop-filter: blur(2px)`
- Card: `--high` bg, cyan border `rgba(76,215,246,.4)`, 3px radius
- Header: `--cont` bg, bottom border
- Body: grid gap 12px
- Footer: `--cont` bg, flex-end, gap 8px

### 4.6 Toast
- Fixed bottom-right, z-index 60
- Min 240px, max 400px
- `--highest` bg, `--outline-var` border, 3px left accent border
- Success: `--green` left border; Warning: `--amber`; Error: `--error`
- Auto-dismiss after 4s (except error)

### 4.7 Buttons
| Variant | Background | Text | Border | Hover |
|---------|------------|------|--------|-------|
| Primary | `--primary-cont` | `--on-primary-cont` | none | brightness 1.08 |
| Secondary | `--high` | `--on` | `--outline-var` | `--bright` |
| Danger | transparent | `--error` | `rgba(255,180,171,.35)` | `rgba(147,0,10,.25)` |
| Icon | none | `--outline` | none | `--bright` bg + `--on` |

All: 3px radius, 600 11px mono, `letter-spacing: .02em`

### 4.8 Inputs
- 32px height, `--lowest` bg, `--outline-var` border, 3px radius
- Focus: border `--primary`, no outline
- Select: cursor pointer
- Textarea: same tokens, min-height 80px

### 4.9 Chips / Tags
- 24px height, 8px horizontal padding
- Default: `--low` bg, `--outline-var` border, `--on-var` text
- Active (`.on`): `--high` bg, `--primary` border & text
- Tag (`.tag`): same as chip, plus `.tag.bin` variant (cyan text, cyan-tinted bg/border)

---

## 5. Surfaces

### 5.1 Desktop dashboard (default)
Full chrome: header + filter strip + table + footer + drawer.  
Purpose: bulk editing, search, multi-bin management.

### 5.2 Mobile single-bin scan view
**No header chrome** (except back button + app name).  
- Centered card with bin metadata (room/zone/shelf/color)
- QR label card (large, printable)
- Contents table (item, category, qty only)
- Purpose: read-only, fast, one-handed on phone in garage.

### 5.3 Login / MFA screens
**Reuse dashboard tokens, centered card, no data chrome.**  
- Header: brand only (no search, no actions)
- Card: `--cont` bg, `--outline-var` border, 3px radius, max-width 480px
- Form: email input → OTP input (two steps)
- Primary button for submit, secondary for back
- Error toast uses `--error` left border
- Same header height (48px) for visual continuity

---

## 6. Motion & Interaction

| Interaction | Duration | Easing | Notes |
|-------------|----------|--------|-------|
| Button hover/press | 100ms | ease-out | brightness transform only |
| Chip toggle | 120ms | ease-out | border + bg + color together |
| Drawer slide | 200ms | ease-out | transform X |
| Modal fade + scale | 150ms | ease-out | 0.96 → 1.0 scale |
| Toast slide-in | 200ms | ease-out | from bottom-right |
| Row select | 0ms | — | instant inset shadow |
| Focus ring | 0ms | — | `--primary` border, no outline |

**No other animations.** Reduce-motion media query disables all non-essential motion.

---

## 7. Accessibility

- WCAG AA contrast on all token pairs (verify with `--primary` on `--primary-cont`, `--on` on `--bg`, `--on-var` on `--cont`, etc.)
- Focus visible on every interactive element (2px solid `--primary`, no outline)
- Semantic HTML: `<header>`, `<main>`, `<aside>`, `<table>`, `<form>`, `<button>`
- ARIA labels on icon-only buttons (`title` attribute sufficient for now)
- Reduce-motion respected
- No color-only state changes (chips: border + bg + color; selected row: bg + inset shadow)

---

## 8. Anti-Slop Rules (enforced in code review)

1. **No new color tokens.** Every color maps to the 15 tokens above.
2. **No new font families.** Geist + JetBrains Mono + Material Symbols only.
3. **No new border radii.** 3px universal.
4. **No arbitrary spacing.** Multiples of 4px only (1–6 scale).
5. **No inline styles in new code.** Use token classes or CSS custom properties.
6. **No component without a token mapping.** If you add a UI element, document which tokens it uses.
7. **No density regression.** New tables/cards match or beat existing row height (36px) and tap targets (44px min).

---

## 9. Token File (for build-time injection)

`tokens.json` (to be created at repo root):

```json
{
  "color": {
    "bg": "#0b1326",
    "lowest": "#060e20",
    "low": "#131b2e",
    "cont": "#171f33",
    "high": "#222a3d",
    "highest": "#2d3449",
    "bright": "#31394d",
    "on": "#dae2fd",
    "onVar": "#bcc9cd",
    "outline": "#869397",
    "outlineVar": "#3d494c",
    "primary": "#4cd7f6",
    "primaryCont": "#06b6d4",
    "onPrimaryCont": "#00424f",
    "amber": "#f5c26b",
    "green": "#4edea3",
    "error": "#ffb4ab"
  },
  "font": {
    "mono": "JetBrains Mono",
    "sans": "Geist"
  },
  "spacing": {
    "base": 4,
    "scale": [4, 8, 12, 16, 20, 24]
  },
  "radius": 3,
  "layout": {
    "headerH": 48,
    "stripH": 42,
    "drawerW": 400,
    "modalMaxW": 480
  }
}
```

---

## 10. Implementation Checklist

- [ ] Create `tokens.json` at repo root
- [ ] Refactor `templates/index.html` CSS custom properties to match §1 tokens exactly (no value changes, just dedupe and order)
- [ ] Add light-mode media query (§1)
- [ ] Implement login/MFA screens per §5.3 using existing tokens
- [ ] Verify all existing components match §4 spec (audit pass)
- [ ] Add WCAG AA contrast verification to CI (optional future step)

---

*End of DESIGN.md — ready for implementation sign-off.*