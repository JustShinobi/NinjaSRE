# Screen design — 034 Console Data Surfaces

What each screen is *for*, and the layout that serves it. Tokens and component
anatomy are in [`../034-console-design-system/design.md`](../034-console-design-system/design.md).

**Mockups:** [`../_design/mockups.html`](../_design/mockups.html) — screenshots in
[`../_design/`](../_design/). All example data is the real state of a two-node
Proxmox cluster; see [`../_design/../044-proxmox-integration/cluster-baseline.md`](../044-proxmox-integration/cluster-baseline.md).

| Image | Screen |
|---|---|
| `03-screen-dashboard.png` | Dashboard |
| `04-screen-incident.png` | Incident detail with proposal and transcript |
| `05-screen-estate.png` | Resources |
| `06-screen-autonomy.png` | Autonomy policy |
| `07-states-empty-error.png` | Empty, first-run and panel-error states |

---

## Dashboard

**The question it answers:** is anything wrong, and does it need me?

Order down the page is the order of urgency, and it is fixed:

1. **Attention block.** Only rendered when non-empty. Danger-bordered, headed
   with the count and the age of the oldest item. Each row reaches its subject in
   one click. This is above the statistics deliberately — a number is never more
   urgent than a decision somebody is waiting on.
2. **Four stat tiles.** Resources watched · healthy · degraded and unhealthy ·
   mean time to detect. Each carries a period comparison and drills through.
3. **Recent activity** (`2fr`) beside **estate health** and **guardian** (`1fr`).

The activity feed mixes incidents, verifications, recurrences, sweeps and
guardian events in one stream, each with an icon well coloured by outcome,
relative time, and absolute time on hover. It is the narrative of what the system
has been doing while nobody watched, which is the whole proposition.

The guardian card states posture, live detector count, freeze window and
heartbeat age. Heartbeat age is on the dashboard rather than buried in settings
because a guardian that stopped looks exactly like a cluster with no problems.

**Empty deployment:** the attention block is absent, tiles read zero with an
explanatory context line, and the activity feed shows the setup checklist rather
than a blank card.

---

## Incidents

**List** — grouped by state, ordered by severity then age. Columns: severity,
title, subjects, state, detector or source, opened, age, assigned run. Filters
for state, severity, subject kind, detector, and time; all in the URL.

**Detail** — the reference layout, `2fr 1fr`:

*Primary column*
- Page header: title as a full sentence stating the problem, state badge,
  incident id, opened time, detector, subject count.
- **Proposal card**, when one exists. Always above the transcript — the decision
  outranks the reasoning that produced it.
- **Transcript**, live or replayed through one component.
- Timeline of state changes, collapsed by default.

*Context rail*
- **Subject** — resource, kind, health, last seen, dependent count.
- **Why degraded** — the derivation. Named signals, their values, their
  thresholds, and a note that the raw provider status is retained. This panel is
  the visible form of "health is derived, not declared".
- **Effectiveness here** — how each candidate remediation has performed on *this*
  resource historically. A remediation that is 1-of-3 effective is shown as such
  before it is proposed again.

---

## Runs

**List** — status, trigger, subject, team, duration, cost, attention state.
Virtualised; ten thousand rows within budget.

**Detail** — one transcript component for live and completed runs, asserted
structurally. Event kinds are visually distinct: objective, model reasoning,
capability call, capability result, evidence retained, memory recall, sub-agent
dispatch and return, guardrail action, human interaction, report.

A capability call shows arguments and result bounded by ranking, with the bound
stated and the full payload one click away. A guardrail event that withheld an
action is styled at danger weight — it is the most important line in most
transcripts and must not read as an aside.

Cost and token usage break down by model and by turn, which matters when task
routing sends different classes to different models.

---

## Resources

**The question it answers:** what am I responsible for, and what state is it in?

Segmented filter across the top (All · Problems · Guests · Storage · Nodes),
sorted by health by default so problems are at the top without filtering.
Columns: shape indicator, name, kind, parent, health badge, utilisation, last
seen. Utilisation renders as meter plus number for anything with a capacity, and
as free text otherwise.

Clicking a health badge opens the derivation — the same panel the incident detail
shows. Health is explainable from wherever it appears.

`stale` and `absent` are visually distinct from `unhealthy`, because an
integration outage and a broken machine demand different responses. A failed
sweep must never make the estate look like a disaster.

---

## Autonomy

**The question it answers:** what is this allowed to do without me, and why?

Rules table on the left (`2fr`): scope, matcher, level, risk bound, and how many
resources it currently applies to. That last column turns an abstract selector
into a concrete blast radius. Ordered by specificity, so reading top to bottom
is reading the resolution order.

A permanent footer states that absence of a rule resolves to propose-only.

Context rail (`1fr`):
- **Bounds no level overrides** — the four, numbered, each with current state.
  Rendered as a distinct card with a strong border, because they are a different
  kind of thing from the rules above.
- **Preview before applying** — the outcome of the pending policy change against
  recorded history: how many actions would have run unattended, how many would
  still have asked, how many a bound would have refused. The apply button lives
  in this card and nowhere else, so a posture change cannot be made without the
  preview in front of the operator.

---

## Detectors

List of every detector with: name, what it watches, condition, threshold,
current state, last fired, and enablement. Each row expands to the stated
rationale for its threshold and the remedy it suggests — the shipped
documentation lives here, not in a file the operator will not open.

Dry-run against historical signals is an action on the row.

---

## Configuration, approvals, catalogue, admin

These retain the information architecture the first wave specified; what changes
is the presentation.

- **Configuration** — org tree left, effective values right, provenance chip on
  every value naming the level that set it. Locked, required and approval-gated
  fields are visually distinct and state what will happen on save. The diff is
  the server's preview response, never a client-side merge.
- **Approvals** — the proposal card, listed, grouped by urgency, decidable in
  place.
- **Catalogue** — capability cards with domain, side-effect level, risk class,
  required integrations, and per-team enablement.
- **Admin** — principals, grants, tokens, SSO, audit with export.

---

## States, everywhere

Every data-bearing region declares all three, and the empty state is content
rather than absence. This is the highest-leverage requirement in the console: the
first live run of the previous console presented eight empty tables behind a
sign-in that could not be passed, and a fresh deployment that looks broken is
indistinguishable from one that is.

- **Empty** — icon, heading, one sentence saying what would be here and how to
  get it, one action. See `07-states-empty-error.png`.
- **Loading** — skeleton reserving exact final dimensions. No layout shift.
- **Error** — scoped to the panel, names the dependency, states the rest of the
  page is unaffected, retries that panel alone.
