# Design language — 032 Console Design System

The concrete values. `spec.md` says a token table must exist and must pass its
contrast thresholds; this document *is* the table, and the numbers in it are
computed, not chosen by eye.

**Mockups:** [`../_design/mockups.html`](../_design/mockups.html) renders every
decision here. Screenshots are in [`../_design/`](../_design/).

| Image | Shows |
|---|---|
| `01-tokens-colour.png` | Every role pair with its measured ratio; status shapes |
| `02-tokens-scales.png` | Type, spacing, radius and duration scales |
| `08-theme-dark.png` | The same geometry under the dark token set |

---

## 1. Design principles

Five, in priority order. When two conflict, the earlier wins.

1. **Honest over reassuring.** A stale reading says stale. A disconnected stream
   says disconnected. A verification that could not tell says inconclusive. The
   console never renders a comfortable state it cannot substantiate.
2. **The consequence, not just the reading.** "Not quorate" is a fact the
   operator still has to interpret. "Not quorate, so `/etc/pve` is read-only, so
   nothing starts" is the same fact with the inferences that always follow it.
   Screens carry the inference.
3. **Weight follows consequence.** The proposal card that could delete a recovery
   point gets the strongest border, the largest type and the slowest path to
   confirmation. A refresh button does not.
4. **Density where scanning matters.** An operator at 03:00 is scanning, not
   reading. Tables are compact, numbers are tabular, and the eye travels down one
   column rather than across a paragraph.
5. **Nothing moves under the pointer.** Live data updates in place. Lists do not
   reorder while being read. New events below the fold announce themselves rather
   than scrolling the viewport.

---

## 2. Colour

Roles, never hues. Both themes declare the same names.

### Light

| Token | Value | Role |
|---|---|---|
| `--surface` | `#ffffff` | Cards, raised panels, inputs |
| `--sunken` | `#f5f7f8` | Page background, table zebra, code blocks |
| `--text` | `#11161c` | Body and headings |
| `--muted` | `#59626d` | Secondary text, labels, metadata |
| `--accent` | `#0f6f5c` | Primary action, current nav, focus ring |
| `--on-accent` | `#ffffff` | Text on accent |
| `--border` | `#d5dade` | Decorative separators only |
| `--border-strong` | `#78828d` | Control boundaries — buttons, inputs |
| `--success` | `#136c46` | Healthy, effective, verified |
| `--warning` | `#8a5a00` | Degraded, awaiting decision, stale trend |
| `--danger` | `#a11b21` | Unhealthy, harmful, irreversible |
| `--info` | `#0a5ea8` | Neutral emphasis, maintenance, informational |
| `--on-danger` | `#ffffff` | Text on danger |

Tinted backgrounds pair with each semantic role: `--success-bg #e8f5ee`,
`--warning-bg #fdf4e3`, `--danger-bg #fdecec`, `--info-bg #eaf2fb`,
`--accent-bg #e7f3f0`.

### Dark

| Token | Value |
|---|---|
| `--surface` | `#0d1117` |
| `--sunken` | `#0a0e13` |
| `--raised` | `#161c24` |
| `--text` | `#e9eef4` |
| `--muted` | `#9aa5b1` |
| `--accent` | `#4fd6b0` |
| `--on-accent` | `#06231c` |
| `--border` | `#242c36` |
| `--border-strong` | `#8b96a3` |
| `--success` | `#5fd996` |
| `--warning` | `#e8b463` |
| `--danger` | `#f28b8b` |
| `--info` | `#77b6f5` |
| `--on-danger` | `#2b0b0c` |

Tints: `--success-bg #0f2a1e`, `--warning-bg #2c2110`, `--danger-bg #2e1416`,
`--info-bg #0f2237`, `--accent-bg #0e2b25`.

### Measured contrast

Computed from the table above by the same WCAG arithmetic the Python palette
already uses. Body pairs need 4.5:1; control boundaries need 3:1.

| Pair | Light | Dark |
|---|---:|---:|
| text / surface | 18.18 | 16.22 |
| text / raised | 18.18 | 14.69 |
| muted / surface | 6.19 | 7.56 |
| muted / sunken | 5.76 | 7.73 |
| on-accent / accent | 6.09 | 9.15 |
| on-danger / danger | 7.79 | 7.65 |
| accent / surface | 6.09 | 10.43 |
| success / surface | 6.44 | 10.68 |
| warning / surface | 5.93 | 10.04 |
| danger / surface | 7.79 | 7.97 |
| info / surface | 6.60 | 8.83 |
| border-strong / surface *(3:1)* | 3.91 | 6.30 |

**Two border tokens, deliberately.** `--border` is decorative and is not required
to reach 3:1 — it separates table rows and card edges, where WCAG 1.4.11 does not
apply. `--border-strong` bounds controls and does reach it. Collapsing them into
one would either make every table line heavy or make every button boundary
non-compliant.

### Status never rides on colour alone

Each state carries a label *and* a shape.

| State | Shape | Role |
|---|---|---|
| healthy | filled circle | success |
| degraded | triangle | warning |
| unhealthy | square | danger |
| unknown | hollow circle | neutral |
| stale | dimmed circle | neutral |
| maintenance | rotated square | info |
| absent | dash | neutral |

An unmapped provider status renders neutral with its raw text — never blank, and
never as an error.

---

## 3. Type

One family: the system UI stack. One monospace stack for identifiers, payloads
and anything an operator might copy.

| Step | Size / line | Weight | Used for |
|---|---|---|---|
| `display` | 34 / 1.15 | 680 | The single number on a stat tile |
| `title` | 26 / 1.25 | 650 | Page title |
| `section` | 20 / 1.3 | 650 | Section heading |
| `strong` | 16 / 1.45 | 600 | Card title, emphasised sentence |
| `body` | 14 / 1.5 | 400 | Default |
| `small` | 13 / 1.5 | 400 | Table cells, dense lists |
| `meta` | 12 / 1.45 | 400 | Secondary metadata |
| `micro` | 11 / 1.4 | 650 | Uppercase labels, badges, column heads |

Numbers that are compared use `font-variant-numeric: tabular-nums` — every
percentage, byte count, duration and cost. Headings use `-0.01em` to `-0.03em`
tracking; `micro` uses `+0.06em` because uppercase at 11px needs it.

**Identifiers are monospace, always.** VMIDs, UPIDs, storage names, metric
selectors, node names. They are copied and compared character by character, and
a proportional font makes `local-lvm` and `local-1vm` look alike.

---

## 4. Spacing, radius, elevation, motion

**Spacing** — 4px base: `4 · 8 · 12 · 16 · 24 · 32 · 48`. Card padding is 16.
Page gutter and grid gap are 24. Section break is 32.

**Radius** — `4` badge and kbd · `6` control and input · `10` card and tile ·
`14` panel and drawer.

**Elevation** — two shadows only. `sh1` for resting cards, `sh2` for overlays.
Depth beyond two levels reads as decoration.

**Motion** — `120ms` hover and colour, `160ms` drawer and modal, `200ms` toast.
All ease-out. Under `prefers-reduced-motion` every duration becomes `0ms` —
removed, not shortened.

---

## 5. Iconography

One outline set, 1.5–2px stroke, inheriting `currentColor`. Sizes: 13 inline,
15 nav, 19 page header, 20 empty state. Imported per icon so the bundle carries
only what is used.

An icon is never the only carrier of an action or a status. Every icon-only
control has an accessible name. The nav has an icon *and* a label at every width
above the collapse breakpoint.

---

## 6. Component anatomy

The decisions that are not obvious from the mockups.

**Stat tile** — label with icon, one number at `display`, one line of context.
The context line is mandatory and must contain either a comparison to the
previous period or a breakdown. A tile with no drill-down may not be rendered.

**Attention row** — severity badge, subject sentence in `strong`, cause line in
`meta`, chevron. The whole row is one link. Rows are ordered by severity then
age, and the block header states the age of the oldest.

**Proposal card** — the most consequential component in the product. Fixed
field order, every field mandatory: target, current state, proposed change,
what each item protects, blast radius, rollback plan, verification, resolved
autonomy with the rule that produced it. Border is `--border-strong`, or
`--danger` when the risk class is 4 or above. Buttons are ordered
destructive-first only when the destructive option is what the operator came
for; the safe partial option always sits beside it. Rejection requires a reason.

**Transcript event** — rail, icon well, and a body with a header line
(`kind`, actor, timestamp, duration, side-effect badge) and content. Payloads
are bounded by ranking, never truncated silently, and the bound states what it
bounded and by what.

**Meter** — 6px, bordered so it is visible at 0%, `--accent` under the first
threshold, `--warning` between, `--danger` above. The numeric value always sits
beside it; a bar without its number is not readable at a glance.

**Empty state** — icon, one-line heading, one sentence saying what would be here
and how to get it, and an action. All four required. An empty state with no
action fails the suite.

**Error state** — scoped to its panel. Names the dependency, states that the
rest of the page is unaffected, offers a retry for that panel only.

---

## 7. Layout

Sidebar 236px, fixed. Topbar 52px. Content max 1360px, gutter 24.

Grid: `2fr 1fr` for a primary surface with a context rail; four equal columns
for tile rows; three for card rows.

Breakpoints — `≥1280` full; `1024–1279` context rail wraps below; `768–1023`
sidebar collapses to a drawer, tiles go two-up; `<768` single column, tables
become stacked rows with `data-label` prefixes.

Nav is grouped, and the grouping is the product's information architecture:
**Operate** (Dashboard, Incidents, Runs, Approvals) · **Estate** (Resources,
Topology, Detectors) · **Learn** (Memory, Knowledge) · **Govern** (Autonomy,
Configuration, Audit). Counts appear only on groups that can demand action.

The sidebar footer always states guardian liveness and the current posture. An
operator should never have to navigate to find out whether the system is
watching and whether it is allowed to act.

---

## 8. What is deliberately absent

- **No brand illustration, no gradients beyond the single hero tint.** This is an
  operations console read under stress.
- **No colour-only severity.** See §2.
- **No skeleton that changes layout when real data arrives.** Skeletons reserve
  exact dimensions.
- **No modal for anything that is not a confirmation.** Everything else is a
  drawer, which keeps the underlying context visible.
- **No toast as the only record.** Every outcome a toast announces also lands in
  the transcript, the audit view, or the notification centre.
- **No third-party font, icon CDN or analytics.** A strict bundle-everything
  rule, asserted by the network audit in feature 033.
