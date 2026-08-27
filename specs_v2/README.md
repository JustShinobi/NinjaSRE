# Specifications — second wave

18 features across 3 waves, numbered 032–049. They continue from the 31 features
in `../specs/`, which delivered the platform. This wave delivers the two things
the live MVP showed were missing: **a console that looks and behaves like a
product**, and **a system that runs on its own against real infrastructure** —
specifically a Proxmox VE homelab.

Same format as the first wave: every feature has `spec.md` (what and why),
`plan.md` (how, with a Constitution Check), and `tasks.md` (numbered, executable
steps). This whole directory is gitignored, like `../specs/`.

**The number is the execution order.** Within a wave, a lower number is built
first. Where two can proceed in parallel, the dependency diagram at the bottom
says so.

---

## Why a second wave

The first wave is not thin. As it stands the repository holds roughly 175,000
lines of first-party Python outside the test suite — 84 integrations with real
REST clients, retry and pagination; a Postgres data platform behind twelve
repository ports; a canonical ReAct runtime with sub-agents, hooks and
guardrails; a six-stage investigation pipeline; a credential proxy; a scheduler
with lease-based claiming; and an HTTP gateway serving 51 endpoints. That is a
platform.

What the live run at `http://localhost:8421/` exposed is that a platform is not
a product. Three gaps, in the order a user meets them.

**The console is unstyled.** `surfaces/console/` renders semantic HTML from
Python with 250 lines of hand-written CSS and no client-side framework. Every
accessibility and correctness property the first wave asked for is genuinely
there and genuinely tested — and the result still looks like a 1996 form next to
the product it was modelled on. `../specs/021-web-console/deviations.md` records
why: `AGENTS.md` describes `surfaces/` as a backend-for-frontend, and
`make verify` is Python-only, so a TypeScript surface would have been invisible
to the gate that defines "done". Both reasons were correct at the time. Neither
survives contact with the requirement that the console look like a product, so
this wave changes the decision deliberately rather than working around it.

**Nothing happens unless a human or a cron says so.** Investigations start from
a webhook (`/webhooks/*`) or from a scheduled job whose objective was written by
hand. There is no component that watches infrastructure, notices that something
is wrong, and opens an incident by itself. For a team with PagerDuty upstream
that is a reasonable design. For a homelab with no alerting stack at all, it
means the system never speaks first.

**There is nothing to look at on first run.** The bootstrap admin token in the
environment is rejected by the running gateway, every list endpoint answers with
an empty array, and a new operator's first screen is an empty table behind a
sign-in they cannot pass. The platform works; there is no path onto it.

And one thing neither reference system has at all: **Proxmox**. A search across
both prior-art trees returns nothing. Kubernetes, ECS, EC2, Lambda, RDS and
Fargate are covered in depth; the hypervisor a self-hoster actually runs is not
covered anywhere. That is this wave's largest genuinely new surface, and the one
with the least to copy from.

---

## Two documents to read before the specs

**[`_design/mockups.html`](_design/mockups.html)** — the console, drawn. Eight
rendered screens covering tokens, dashboard, incident detail with a proposal
card, estate, autonomy policy, and the empty and error states, in both themes.
Screenshots are beside it in [`_design/`](_design/). The design language behind
them is [`034-console-design-system/design.md`](034-console-design-system/design.md);
the per-screen reasoning is [`036-console-data-surfaces/design.md`](036-console-data-surfaces/design.md).

**[`044-proxmox-integration/cluster-baseline.md`](044-proxmox-integration/cluster-baseline.md)**
— a live survey of the two-node cluster this wave targets, taken 2026-08-07,
together with its operator's thirteen postmortems, 55 runbooks and validated
inventory. Every example in the mockups is real data from it. Its §8 lists, per
feature, what the measurements changed in the specifications; §9 lists what the
guardian would raise against that cluster today.

## Decisions taken before writing

Three, recorded here because every spec downstream assumes them.

**The console is rebuilt as a real front-end application.** Next.js App Router,
TypeScript, Tailwind, a component library, an icon set, consuming the REST API
that already exists. `surfaces/console/` is retired rather than extended. The
cost — a Node toolchain in the repository and in CI — is paid explicitly by
feature 033, which puts the front end behind the same gate as the Python.

**Autonomy is configurable at every granularity, not chosen once.** The three
plausible postures — never act, act on low-risk and ask for the rest, act on
everything with notification after — are all reachable, and the level is
resolvable per deployment, per domain, per resource, per action class, and per
individual resource. Feature 040 is that policy engine. No other feature hard-codes
a posture.

**Proxmox coverage spans four domains plus an observability bridge.** Cluster,
quorum and corosync; storage, ZFS and capacity; guests (QEMU and LXC); backups
and PBS. Alongside them, a bridge to Prometheus, Grafana, Alertmanager and Loki
so a homelab that already runs an observability stack feeds it rather than
duplicating it.

---

## Wave 9 — Console rework

The visual and interaction layer, rebuilt. **032 and 033 are the two
foundations** — data to build against, and a gate to be judged by. Neither
depends on the other, and nothing else in the wave can be honestly finished
without both. 034 through 037 follow, and 035, 036 and 037 largely overlap.

| # | Feature | Delivers |
|---|---|---|
| [032](032-mock-data-plane/spec.md) | Mock data plane | An anonymised capture of a real deployment, seven scenarios, and a mock API on the real contract — so screens are built and reviewed against fixed, realistic data |
| [033](033-console-toolchain-and-gate/spec.md) | Console toolchain and gate | pnpm, build, typecheck, lint, unit tests, Playwright end-to-end and visual regression — inside `make verify` and CI |
| [034](034-console-design-system/spec.md) | Console design system | Tokens, type scale, spacing, iconography, component primitives, light and dark, contrast proven by test |
| [035](035-console-application-shell/spec.md) | Console application shell | Next.js app, sidebar and topbar, routing, session, page headers, command palette, responsive, i18n |
| [036](036-console-data-surfaces/spec.md) | Console data surfaces | Dashboard, runs, memory, topology, config, approvals, catalogue, admin — with real empty, loading and error states |
| [037](037-console-live-layer/spec.md) | Console live layer | Streaming transcripts, inline approvals, drawers, filters, toasts, reconnection, optimistic updates |

**Why the mock data plane is first.** A screen cannot be designed against an
empty array, a reviewer cannot judge a dashboard where every tile reads zero, and
a visual-regression baseline captured against live data is not a baseline — it is
a photograph of one moment that will differ on the next run because a timestamp
moved. The fidelity clauses in 034 to 037 require the built console to match the
mockups; that comparison only means anything against fixed data. Feature 032 also
supplies feature 042's demo mode, so the repository holds exactly one fictional
deployment rather than two that drift.

## Wave 10 — Autonomous operation

What turns the platform into something that runs unattended. 038 comes first;
039 depends on it; 040 and 041 depend on 039; 042 and 043 are independent.

| # | Feature | Delivers |
|---|---|---|
| [038](038-estate-inventory/spec.md) | Estate inventory and health | The managed set of resources, discovered and refreshed, with a health rollup and staleness |
| [039](039-continuous-observation/spec.md) | Continuous observation | Pollers, detectors, deduplication, incident open and close, suppression and maintenance windows |
| [040](040-autonomy-policy-engine/spec.md) | Autonomy policy engine | Granular, resolvable autonomy levels; dry-run; freeze windows; budgets; kill switch |
| [041](041-closed-loop-remediation/spec.md) | Closed-loop remediation | Verify after acting, roll back on failure, measure the effect, detect repeat offenders, escalate |
| [042](042-first-run-and-demo/spec.md) | First run and demo mode | A bootstrap that works, guided setup, seeded scenarios, a self-check that says what is wrong |
| [043](043-self-hosted-model-operation/spec.md) | Self-hosted model operation | Tool calling that survives small local models: routing, shims, degradation, tight context budgets |

## Wave 11 — Proxmox and the homelab

The new domain. 044 is the foundation; 045 and 047 depend on it; 046 depends on
045 and 040; 048 and 049 close the wave.

| # | Feature | Delivers |
|---|---|---|
| [044](044-proxmox-integration/spec.md) | Proxmox VE integration | API client through the credential proxy: cluster, nodes, guests, storage, tasks, HA, replication, backups |
| [045](045-proxmox-investigation/spec.md) | Proxmox investigation capabilities | Read tools and methodology skills across quorum, storage, guests and backups |
| [046](046-proxmox-remediation/spec.md) | Proxmox remediation capabilities | Unlock, lifecycle, migrate, HA relocate, reclaim, retry — each with a risk class and a rollback plan |
| [047](047-homelab-observability-bridge/spec.md) | Homelab observability bridge | Prometheus, Grafana, Alertmanager and Loki wired to the estate and to incidents |
| [048](048-homelab-profile-and-guardian/spec.md) | Homelab profile and cluster guardian | A single-host deployment sized for a homelab, and the standing guardian for a two-node cluster |
| [049](049-proxmox-scenario-harness/spec.md) | Proxmox scenario harness | Synthetic two-node failure scenarios, scored, as a regression gate on autonomy |

---

## Dependency order

```
wave 9    032 ─┐
               ├─> 034 ─> 035 ─> 036 ─> 037
          033 ─┘         (035–037 overlap heavily)

wave 10   038 ─> 039 ─┬─> 040 ─> 041
                      └─> 047
          042 ─ needs 032's dataset
          043 ─ independent

wave 11   044 ─┬─> 045 ─> 046 ─> 049
               ├─> 047
               └─> 048
```

Wave 9 and wave 10 are independent of each other and can run concurrently — with
one thread between them: **042's demo mode loads 032's dataset**, so 032 lands
before 042 finishes.

Wave 11 needs 040 (for 046's risk classes) and 039 (for 047's incident path).
