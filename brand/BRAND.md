# Kapaat — Brand Kit

**Kapaat** (Hindi/Marathi/Punjabi: ਕਪਾਟ / कपाट — *cabinet, closet, cupboard*) is a self-hosted storage inventory app. The name is culturally rooted, phonetically memorable, and describes the product literally.

---

## Logo & Mark

| Asset | File | Use |
|---|---|---|
| Full logo (200 × 200) | `icons/kapaat-logo.svg` | App icon, README, social cards |
| Favicon mark (32 × 32) | `icons/kapaat-icon-32.svg` | Browser tab, small UI contexts |
| Horizontal wordmark (320 × 80) | `icons/kapaat-wordmark.svg` | Headers, documentation banners |

### Mark concept

The mark is a stylized four-panel cabinet — two doors, two shelves — rendered in the brand cyan on a dark card. The doors and handles abstractly represent bins and the act of opening/closing storage compartments.

---

## Color Palette

| Role | Name | Hex | Usage |
|---|---|---|---|
| **Primary** | Kapaat Cyan | `#4cd7f6` | Interactive elements, links, active states, mark strokes |
| **Primary dark** | Deep Cyan | `#2ab8d8` | Hover, pressed, gradient end |
| **Background** | Midnight | `#0f1923` | App background, card fills |
| **Surface** | Deep Navy | `#1a2d3d` | Cards, drawers, modals |
| **Surface alt** | Steel | `#243547` | Table rows, hover states |
| **Outline** | Slate | `#869397` | Muted labels, borders, dividers |
| **On-surface** | Off-white | `#e8edf0` | Body text |
| **Secondary** | Seafoam | `#2ecc71` | Success states, quantity badges |
| **Warning** | Amber | `#f0a500` | Caution indicators |
| **Error** | Coral | `#e74c3c` | Destructive actions, error states |

### CSS Custom Properties (as used in the app)

```css
:root {
  --primary:     #4cd7f6;
  --secondary:   #2ecc71;
  --tertiary:    #9b59b6;
  --amber:       #f0a500;
  --error:       #e74c3c;
  --bg:          #0f1923;
  --surface:     #1a2d3d;
  --surface-alt: #243547;
  --outline:     #869397;
  --on-surface:  #e8edf0;
}
```

---

## Typography

| Role | Font | Fallback stack |
|---|---|---|
| **UI / mono** | DM Mono | `'Fira Mono', 'Consolas', monospace` |
| **Body / labels** | System UI | `-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif` |

The monospace type is used throughout — IDs, tags, filter chips, code — reinforcing the "inventory system" feel.

---

## Tone of Voice

- **Direct.** Kapaat is a tool, not a platform. Labels say exactly what they do: *Move*, *Edit*, *Delete*, *Add Photo*.
- **Compact.** UI text is short. No decorative copy inside the app.
- **Technical-friendly.** Users are comfortable with terms like *Zone*, *Shelf*, *Bin ID*, *QR label*.

---

## Naming Rules

- Product name: **Kapaat** (capital K, lowercase rest). Never "KAPAAT" or "kapaat" in prose.
- CLI / Docker image: `kapaat` (all lowercase).
- GitHub repo: `garage-storage` (legacy; may be renamed to `kapaat` in a future release).

---

## Usage Guidelines

✅ **Do**
- Use the SVG mark on dark backgrounds (midnight or deep navy).
- Keep the cyan stroke weight proportional when scaling the mark.
- Pair the wordmark with the tagline *STORAGE INVENTORY* in small contexts.

❌ **Don't**
- Recolor the mark outside the brand palette without permission.
- Stretch or distort the cabinet proportions.
- Place the mark on light backgrounds without adding a dark card behind it.
- Use the name "Kapaat" to imply official endorsement of a fork or derivative.
