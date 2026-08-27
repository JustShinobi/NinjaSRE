# Feature 034 — Console Design System

- **Wave:** 9 — Console rework
- **Branch:** `feat/034-console-design-system`
- **Status:** Draft
- **Depends on:** 032, 033

## Summary

The vocabulary every console screen is built from: colour, type, spacing, radius,
elevation, motion, iconography, and the two dozen primitives that compose into
pages. It exists so that a screen written next month looks like one written this
month without anybody deciding again, and so that "make it look right" is a
property that can be tested rather than reviewed by eye.

The first wave proved the contrast arithmetic and got nothing else. `theme.py`
computes WCAG ratios from its tokens and asserts them — that part was right and
carries forward. What it lacks is everything above the token: no spacing scale,
so every margin is a fresh guess; no type scale, so headings are whatever `h1`
does; no icons, so every affordance is a word; no component layer, so the same
card is rebuilt per page. The result is technically accessible and visually
unfinished, which is the specific failure this feature exists to end.

## User scenarios

### Primary story

An engineer opens the console at three in the morning. The dark theme is already
on because their system asked for it. The page reads as a product: a hierarchy
they can scan, status carried by shape and label as well as colour, controls that
look pressable, and nothing that shifts under them as data arrives. They find
what they came for without reading every word on the screen.

A contributor adds a page a week later. They compose it from primitives, pass
tokens rather than colours, and it comes out looking like the rest — not because
they were careful, but because there was no convenient way to be careless.

### Acceptance scenarios

1. **Given** any token pair the console renders text with, **when** contrast is
   computed, **then** body pairs reach 4.5:1 and boundary pairs reach 3:1, in
   both themes.
2. **Given** a viewer with no explicit preference, **when** the console loads,
   **then** it follows the operating system, and an explicit choice overrides it
   and persists.
3. **Given** a status shown in colour, **when** it is rendered, **then** it also
   carries a label or a shape, so it survives a viewer who cannot separate the
   hues.
4. **Given** a primitive, **when** it is rendered at every size and state the
   library declares, **then** each renders without layout overflow at 320px,
   768px and 1440px.
5. **Given** a keyboard user, **when** they traverse any composed screen, **then**
   focus is visible on every interactive element and the order follows the
   reading order.
6. **Given** a viewer who has asked for reduced motion, **when** anything
   animates, **then** the animation is removed rather than shortened.
7. **Given** a token changed in one place, **when** the console rebuilds, **then**
   every surface using it changes, and no surface hard-codes a value past it.

### Edge cases

- A status the API invents that the palette has no colour for.
- A very long single-token string in a fixed-width cell.
- A screen at 320px with a table of eight columns.
- A user zoomed to 200% — no horizontal scroll on the page body.
- A theme change while a live stream is open.
- Right-to-left text, and a locale whose strings are twice as long.

## Requirements

### Functional

**Tokens**

- **FR-001** The system MUST define colour by role, not by hue: surface, raised,
  sunken, text, muted, accent, on-accent, border, and the five semantic roles
  (success, warning, danger, info, neutral), each with a foreground pair.
- **FR-002** Every role MUST be defined for both themes as the same token name
  with a different value, so a screen written against tokens works in both.
- **FR-003** The system MUST define a modular type scale, a spacing scale, a
  radius scale, a border-width scale, a shadow scale, and a duration scale, each
  as a small closed set. Arbitrary values MUST be rejected by lint.
- **FR-004** Theme selection MUST follow the operating system by default, accept
  an explicit override, and persist that override across sessions without a
  flash of the wrong theme on load.

**Iconography**

- **FR-005** The system MUST ship a single icon set, used everywhere, at a fixed
  set of sizes, inheriting colour from its context.
- **FR-006** An icon MUST never be the only carrier of meaning for an action or a
  status. Every icon-only control MUST carry an accessible name.

**Primitives**

- **FR-007** The system MUST provide, at minimum: Button (with variants and a
  destructive variant), IconButton, Link, Badge, StatusDot, Card, StatTile,
  Table, DataList, Tabs, Drawer, Modal, Toast, Tooltip, Input, Select, Textarea,
  Checkbox, Radio, Switch, Combobox, DateRange, CodeBlock, DiffView, Avatar,
  Breadcrumb, Pagination, ProgressBar, Spinner, Skeleton, EmptyState,
  ErrorState, and Timeline.
- **FR-008** Every primitive MUST declare its states — default, hover, active,
  focus, disabled, loading, error — and render each without a layout shift
  between them.
- **FR-009** Interactive primitives MUST be operable by keyboard alone and MUST
  expose the roles and properties their pattern requires.
- **FR-010** Every data-bearing primitive MUST have a declared empty state, a
  loading state, and an error state. A component that can show nothing MUST say
  what nothing means.

**Semantics**

- **FR-011** A run or resource status MUST map to exactly one semantic role
  through a single declared mapping, so the same status is the same colour on
  every screen.
- **FR-012** An unknown status MUST render as neutral with its raw text, never
  blank and never as an error.
- **FR-013** Destructive actions MUST be visually distinct from accented ones and
  MUST require an explicit confirmation step that names the target.

**Density and layout**

- **FR-014** The system MUST provide a comfortable and a compact density, applied
  at the application level, affecting spacing and control height only.
- **FR-015** The system MUST define the page-level layout primitives — page
  header, section, two-column split, and content width cap — as components, not
  as per-page CSS.

### Non-functional

- **NFR-001** The compiled stylesheet for the whole system MUST stay under a
  declared budget, asserted in CI.
- **NFR-002** Every primitive MUST be documented in a browsable gallery that
  renders every variant and state, and that gallery MUST be the source the visual
  regression suite screenshots.
- **NFR-003** No component may reference a raw colour, spacing, or duration
  literal. Enforced by lint, not by review.
- **NFR-004** First contentful paint of any console page MUST not be blocked on
  loading the icon set; icons MUST be tree-shaken to what a page uses.

## Success criteria

- **SC-001** Every foreground-on-background pair in both themes passes its WCAG
  threshold, asserted from the tokens rather than from a screenshot.
- **SC-002** Every primitive, in every declared variant and state, renders in the
  gallery and is covered by a visual-regression baseline.
- **SC-003** A lint run fails on a hard-coded colour, spacing, radius, or
  duration literal anywhere in the console source.
- **SC-004** An automated accessibility audit over the gallery reports no
  violations at the level the project declares.
- **SC-005** The gallery renders without horizontal overflow at 320px, 768px and
  1440px, and at 200% zoom.
- **SC-006** Switching theme changes no layout dimension — a pixel diff between
  themes differs only in colour.

## Out of scope

- Page composition and navigation — feature 035.
- The screens themselves — feature 036.
- Live and interactive behaviour — feature 037.
- The build and test toolchain — feature 033.
- A public brand identity, logo suite, or marketing site.
