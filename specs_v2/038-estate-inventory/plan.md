# Plan — 037 Estate Inventory and Health Model

## Technical context

| Concern | Choice |
|---|---|
| Tier | `platform/estate/` — tier 3, alongside `platform/knowledge/` |
| Storage | The existing Postgres, through a new repository port beside the twelve that exist |
| Relationships | The existing knowledge graph, extended with resource node and edge kinds — not a second graph |
| Scheduling | The existing scheduler's lease-based claiming, so concurrency is solved once |
| Discovery contract | A protocol in `integrations/_base/`, implemented per integration, invoked through the credential proxy |

## Constitution Check

| Article | Bearing | Compliance |
|---|---|---|
| I — Evidence over assertion | Health must be derived, not declared. | FR-013: every health state records the named signals and values that produced it, and the derivation is retrievable. A state with no evidence is `unknown`, not `healthy`. |
| IV — Secrets never reach the agent | Discovery calls providers. | Every call goes through the credential proxy. The discovery code holds no token, exactly like every other integration call. |
| VIII — Layered architecture | A new platform module. | `platform/estate/` depends on `platform/persistence/` and `config/`, and on integrations only through a protocol a composition root satisfies. No `core/` import. |
| IX — Capabilities are declared | Discovery is a new kind of integration behaviour. | It is declared in the integration's schema like any capability, with its rate limits and its side-effect level, which is always read. |
| XI — Single datastore | Tempting to add a fast key-value store for health. | Refused. Estate and health live in the same Postgres, in the same schema, under the same retention. |

## Architecture decisions

**Absent is not unhealthy.** A resource that no longer exists has not failed —
somebody deleted it. Conflating the two produces a permanent alarm for every
decommissioned machine, and an operator who learns to ignore the estate's
problem count. Absence is its own state, and only a *successful* sweep may
assign it.

**A failed sweep marks stale, never absent.** This is the single most damaging
bug this component can have: an integration outage that reports the entire estate
as gone, cascading into every detector and every autonomy decision downstream.
The distinction is written into the model rather than into the caller.

**Health is derived and shows its work.** A provider status string copied into a
column is not health — it cannot be compared across providers, it changes meaning
when the provider changes, and it cannot be explained. Signals map into a closed
set through a declared mapping, and the mapping plus the raw value is retained so
an operator can see both what the system concluded and what it was told.

**Identity comes from the source, not the name.** A virtual machine's display
name is the most likely thing about it to change and the least likely thing to be
unique. Identity is the source integration plus the provider-native identifier,
hashed to a deployment-stable key.

**The graph is reused, not rebuilt.** Relationships between resources are the
same problem the knowledge graph already solves for service topology, and blast
radius already traverses it. A second graph would mean two answers to "what does
this affect".

## Phases

1. **Model and storage.** Resource, kind registry, identity derivation, typed
   attributes, the repository port, migrations, tenant isolation.
2. **Discovery contract.** The protocol, the per-integration registration, the
   sweep with lease-based claiming, incremental and full modes.
3. **Absence and staleness.** Successful-sweep absence marking, failed-sweep
   staleness, per-kind freshness intervals.
4. **Reconciliation.** Multi-source resources, attribution per source, the
   identity-reuse and changed-parent cases.
5. **Health.** Signal recording, the closed state set, provider mappings with raw
   retention, the derivation record, parent rollup rules, maintenance windows.
6. **History and query.** Transition log, query surface by every declared
   dimension, summary rollup, links to incidents and runs, retention.
7. **Surfaces.** Gateway endpoints for estate query, summary, resource detail and
   maintenance; CLI commands; the console panels feature 036 declared.

## Risks

- **A generic resource model becomes a schemaless bag.** Mitigated by FR-002:
  kinds are declared and attributes are typed per kind, so a provider cannot
  invent a shape at runtime.
- **Discovery hammers a provider.** Mitigated by NFR-002's call bound and by
  reusing the integrations' existing rate-limit handling rather than a new one.
- **Ten thousand resources on first connection overwhelm the sweep.** Mitigated
  by bounding the sweep and resuming, rather than by raising the bound.
