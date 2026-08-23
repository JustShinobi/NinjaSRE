# ADR 0009 — Full parity across all ~85 integrations

- **Status:** Superseded by [0015](0015-parity-per-embedded-integration.md), 2026-08-17
- **Date:** 2026-08-04
- **Constitution impact:** Article IX, Article XII

## Context

The two prior systems together cover roughly 85 distinct external systems: 76 vendor
integrations in the pipeline design and 51 skills in the memory design, with substantial overlap.

They cover them differently. The pipeline design provides typed tools with a consistent
package anatomy — config normalisation, `verifier.py`, `client.py` — but the tool
descriptions are terse and carry little investigative guidance. The memory design provides
methodology-rich `SKILL.md` documents (statistics-first discipline, decision
flowcharts, query-language reference, explicit anti-patterns) backed by scripts,
but with no typed schema, no side-effect declaration, and no verifier.

Where both cover a vendor, the union is strictly better than either: the pipeline design's
client and typed tools, the memory design's methodology.

## Decision

**All ~85 integrations reach full parity in v1.** Full parity for an integration
means all seven artefacts:

1. **Config schema** — credential and connection fields with validation
2. **Verifier** — a live connectivity and permission check
3. **Client** — built on `integrations/_base/client.py`, credential-proxy-only
4. **Typed tools** — full capability metadata, including `side_effect_level`
5. **Methodology skill** — `SKILL.md` with investigative guidance for the domain
6. **Documentation** — setup, required permissions, and known limitations
7. **Synthetic scenario** — at least one fixture with an answer key exercising it

## Rationale

**Coverage is the reason to adopt.** An SRE team evaluates this class of tool by
checking whether it speaks to their stack. A gap in the list they care about ends
the evaluation regardless of how good the reasoning engine is.

**Partial integrations are worse than absent ones.** An integration that appears
in the catalogue but has no verifier fails at 03:00 with an opaque error. One with
no `side_effect_level` bypasses Article III. One with no synthetic scenario is
never exercised by CI and rots silently.

**The union is already written.** For most vendors, both prior systems have working
code. The work is consolidation and consistency, not greenfield implementation.

**Scenario coverage is what makes the catalogue maintainable.** With one synthetic
scenario per integration, a change to the capability framework or the planner
surfaces breakage across the whole catalogue in CI rather than in production.

## Managing the cost

Full parity for 85 integrations is the single largest work item in the MVP. It is
made tractable by structure rather than by cutting scope:

| Lever | Effect |
|---|---|
| **Scaffold generator** | Emits all seven artefacts from a manifest; the author fills in vendor specifics |
| **Shared client base** | Auth, retry, pagination, rate limiting, and proxy routing are inherited, not rewritten |
| **Contract test suite** | One suite parameterised over the catalogue; adding an integration adds a row, not a test file |
| **Methodology templates** | Domain-level skill templates (log store, metrics store, tracing, cloud control plane, database, VCS, ticketing) that vendor skills specialise |
| **Reuse** | the pipeline design's clients and the memory design's SKILL.md content are ported, not authored |
| **Fixture-recorded scenarios** | Scenarios are generated from recorded live responses, then hand-annotated with the answer key |

Delivery order within Wave 6 is by usage frequency — Kubernetes, AWS, Datadog,
Grafana/Prometheus, Loki, Elasticsearch, PagerDuty, Slack, GitHub, Jira,
PostgreSQL first — so the catalogue is useful long before it is complete. That is
sequencing, not scope reduction: the wave does not exit until all 85 are at parity.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| ~20 curated, the rest mechanically migrated | Creates a two-tier catalogue where the second tier has no verifier, no scenario, and no methodology — the failure mode described above |
| ~20 only, framework ready for the rest | Loses the coverage that drives adoption, and defers the hardest consistency work to a point where the framework has already ossified |
| ~20 native, the rest via community MCP servers | Delegates side-effect declaration and credential handling to third parties, violating Articles III and IV |

## Consequences

**Positive**

- Every integration behaves identically: same setup, same verification, same
  approval semantics, same evidence shape
- CI exercises the entire catalogue
- Methodology quality is uniform rather than concentrated in a favoured few
- Contributors have one pattern to learn

**Negative**

- Wave 6 is the longest wave in the roadmap
- Vendor API drift across 85 systems is a permanent maintenance load
- Verifiers require live credentials for 85 systems to be fully tested

**Mitigations**

- The scaffold and shared base mean an integration is measured in hours, not days
- Contract tests run against recorded fixtures by default; live verification runs
  on a scheduled job against a credential set the maintainers hold
- An integration whose contract test fails is marked degraded in the catalogue and
  surfaces that state in the console, rather than failing silently
- MCP bridging (Wave 6, feature 026) remains available for the long tail beyond
  the 85 — as an extension path, not as a substitute for parity
