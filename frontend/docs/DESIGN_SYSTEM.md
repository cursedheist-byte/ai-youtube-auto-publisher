# AUTO PUBLISHER — Design System "Aperture"

Design language for the AI YouTube Auto Publisher SaaS. Futuristic black/white
creator-tool identity with a single controlled red accent.

## Tokens

### Color
| Token | Value | Usage |
|---|---|---|
| `ink` | `#0505` | App background |
| `surface` | `#0D0D0D` | Cards |
| `surface2` | `#141414` | Raised elements |
| `line` | `#262626` | Borders/dividers |
| `paper` | `#F7F7F5` | Primary text |
| `muted` | `#9A9A9A` | Secondary text |
| `accent` | `#FF003` | Brand red — logo dot, primary CTA, active markers. Use sparingly, never as a fill for large areas. |
| `good` / `bad` / `warn` | `#4ADE80` / `#F871` / `#FBBF24` | Status semantics only |

### Typography
- Display: **Space Grotesk** — headlines, numerals, logo. Tight tracking (−.04em).
- Body: **Inter** — UI text, forms.
- Eyebrow: 11px, `.16em` tracking, uppercase, muted.

### Radius scale
`14px` buttons/inputs · `20px` inner cards · `28px` panels

### Elevation
- `panel`: gradient `#141414 → #0909`, 1px white/10 border, deep soft shadow + inner highlight
- `glass`: blur(18px), for floating elements

## Components
- `.btn-primary` — accent red fill, white text; hover lifts with red glow
- `.btn-ghost` — translucent white, 1px border
- `.field` — dark input, white/11 border, focus ring in accent at 10% opacity
- `.status-pill` + `.status-ok / status-bad / status-warn / status-idle`
- `.alert-bad / .alert-ok` — message banners
- `.panel-soft` — quiet inner container
- `.eyebrow`, `.muted`, `.dashboard-card`, `.grid-bg`, `.noise`, `.reveal`

## Motion
- `reveal` (fade-up .65s), `float`, `pulseDotAccent`, `orbit`
- All suppressed under `prefers-reduced-motion`

## Responsive
- Sidebar ≥ `lg` (1024px); below: hamburger + slide-in drawer with scrim
- Grids collapse: 5→2→1 (stats), 2→1 (forms), landing 2→1
- Touch targets ≥ 44px on mobile nav

## Rules
1. Red is a signal, not a decoration — one accent element per view region.
2. Status color is semantic only (success/error/warning); never decorative.
3. Never replace the dark monochrome base — polish happens via elevation,
   spacing and accent restraint.
4. All interactive elements have hover, focus-visible, and disabled states.
