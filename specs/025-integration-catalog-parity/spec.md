# Feature 025 — Integration Catalogue Parity

- **Wave:** 6 — Integrations
- **Branch:** `feat/025-integration-catalog-parity`
- **Status:** Draft
- **Depends on:** 024
- **ADRs:** [0009](../../docs/adr/0009-full-integration-parity.md)

## Summary

Bring all ~85 integrations to full parity — every one with a credential schema,
verifier, proxied client, typed capabilities, methodology skill, documentation,
and a synthetic scenario. This is the largest single work item in the MVP, and the
one that decides whether a team can adopt NinjaSRE without a gap in their stack.

## User scenarios

### Primary story

A platform team runs Kubernetes on AWS with Grafana, Loki, PagerDuty, GitHub, and
Jira. They connect all six in the console, each verifies successfully with a clear
report of what permissions it has, and their first investigation draws on all of
them without anyone writing configuration glue.

### Acceptance scenarios

1. **Given** any integration in the catalogue, **when** the parity check runs,
   **then** all seven artefacts are present and valid.
2. **Given** any integration, **when** its verifier runs with valid credentials,
   **then** it confirms connectivity and enumerates the permissions it has.
3. **Given** any integration, **when** an investigation uses it, **then** its
   capabilities route through the credential proxy and return structured evidence.
4. **Given** any integration, **when** its synthetic scenario runs, **then** the
   agent uses it and reaches the scenario's expected conclusion.
5. **Given** two integrations covering the same domain, **when** both are
   configured, **then** capability selection scores them appropriately rather than
   arbitrarily preferring one.
6. **Given** an integration in the catalogue but not configured, **when** the
   catalogue is resolved for a team, **then** it is excluded with a recorded
   reason and appears in the console as available-but-unconfigured.
7. **Given** the delivery order, **when** tier-1 integrations are complete,
   **then** the platform is usable for the most common stacks even though the wave
   is not finished.

### Edge cases

- Two vendors with near-identical capabilities and overlapping scenarios.
- A vendor requiring a paid tier for the API a capability needs.
- A vendor whose API is deprecated during the wave.
- An integration usable only in specific regions.
- A vendor whose rate limits make a capability impractical for investigation.
- A self-hosted vendor with a customer-specific base URL.

## Requirements

### Functional

**Coverage**

- **FR-001** All integrations listed in the catalogue below MUST reach full parity
  as defined in feature 024.
- **FR-002** Delivery MUST be ordered by usage frequency, so the platform becomes
  useful before the wave completes.
- **FR-003** An integration that cannot reach parity for an external reason (API
  removed, paid tier required) MUST be recorded with that reason and marked
  explicitly, not silently omitted.

**Capability design**

- **FR-004** Each integration's capabilities MUST cover its investigative purpose,
  not merely wrap its API surface.
- **FR-005** Read capabilities MUST be bounded: time windows, result caps, and
  pagination limits from named constants.
- **FR-006** Capabilities that could return very large payloads MUST offer a
  statistics-first variant, per the domain methodology.
- **FR-007** Write capabilities MUST declare the correct `side_effect_level` and
  provide a rollback generator (feature 017).

**Methodology skills**

- **FR-008** Each integration's skill MUST specialise its domain template with
  vendor-specific query syntax, gotchas, and anti-patterns.
- **FR-009** A skill MUST direct only tools that exist in that integration or in
  the shared capability set.
- **FR-010** Skill bodies MUST NOT instruct shell execution against production.

**Scenarios**

- **FR-011** Each integration MUST have at least one synthetic scenario with a
  ground-truth answer key exercising its primary capabilities.
- **FR-012** Scenarios MUST use recorded vendor responses so they run without
  credentials.

**Documentation**

- **FR-013** Each integration MUST document: required credentials, minimum
  permissions, setup steps, regional considerations, rate limits, and known
  limitations.
- **FR-014** Documentation MUST be generated into the docs site from the catalogue
  where possible, to prevent drift.

### The catalogue

**Observability (20)** — Grafana (Loki, Mimir, Tempo, annotations), Prometheus,
Datadog, New Relic, Honeycomb, Coralogix, groundcover, CloudWatch, Sentry,
Elasticsearch, OpenSearch, Better Stack, Splunk, VictoriaLogs, VictoriaMetrics,
SigNoz, OpenObserve, Azure Monitor, Jaeger, Hermes

**Infrastructure & Cloud (17)** — Kubernetes, AWS S3, AWS Lambda, AWS EKS, AWS EC2,
AWS ECS, AWS ELB, AWS CloudTrail, AWS RDS, GCP, Azure, Docker, ArgoCD, Helm,
Jenkins, Vercel, Railway

**Databases (11)** — PostgreSQL, MySQL, MariaDB, MongoDB, MongoDB Atlas,
ClickHouse, Azure SQL, Snowflake, BigQuery, Redis, Supabase

**Data platform (8)** — Airflow, Kafka, Spark, Prefect, RabbitMQ, Dagster,
Temporal, Flink

**Version control (4)** — GitHub, GitLab, Bitbucket, Sourcegraph

**Incident management (7)** — PagerDuty, Opsgenie, incident.io, Blameless,
FireHydrant, ServiceNow, Alertmanager

**Project & docs (7)** — Jira, Linear, ClickUp, Trello, Confluence, Notion,
Google Docs

**Communication (9)** — Slack, Microsoft Teams, Telegram, Discord, Rocket.Chat,
WhatsApp, Pushover, SMTP, Twilio

**Analytics & config (3)** — Amplitude, PostHog, flagd/OpenFeature

**Total: 86**

### Delivery tiers

| Tier | Integrations | Rationale |
|---|---|---|
| **1** | Kubernetes, AWS (EKS, EC2, CloudWatch, RDS, Lambda, ECS, CloudTrail), Grafana (Loki, Prometheus), Datadog, Elasticsearch, PagerDuty, Slack, GitHub, Jira, PostgreSQL, Sentry, Alertmanager | The most common production stack |
| **2** | Remaining observability, GCP, Azure, ArgoCD, Jenkins, MySQL, Redis, Kafka, GitLab, Opsgenie, Teams, Confluence | Broad coverage |
| **3** | Everything else | Long tail |

Tiers are a delivery order, not a quality distinction — all reach the same parity
(FR-001).

## Success criteria

- **SC-001** All 86 integrations pass the parameterised contract suite.
- **SC-002** All 86 have a synthetic scenario that the agent solves.
- **SC-003** No integration client can read a credential — catalogue-wide.
- **SC-004** Every write capability declares its level and provides a rollback
  generator.
- **SC-005** Every skill passes binding validation and the shell anti-pattern lint.
- **SC-006** With tier 1 complete, an end-to-end investigation on a Kubernetes and
  AWS stack works using only tier-1 integrations.
- **SC-007** Documentation is generated for all 86 with no drift from the
  catalogue.
- **SC-008** Live verification succeeds for every integration where the maintainers
  hold credentials, and the rest are marked unverified rather than assumed working.

## Out of scope

- Framework changes (feature 024)
- Protocol bridges for non-catalogued systems (feature 026)

## Clarifications

| Question | Resolution |
|---|---|
| Is 86 integrations realistic for an MVP? | It is the decision recorded in ADR 0009, taken because coverage is what drives adoption. Feature 024 exists specifically to make the per-integration cost small, and SC-001 of that feature measures whether it did. |
| What if a vendor cannot reach parity? | FR-003: recorded with the reason and marked explicitly. An honest gap is fine; a silent one is not. |
| Do overlapping vendors both need scenarios? | Yes — each scenario exercises that vendor's specific query syntax and response shape, which is where breakage happens. |
| How is quality kept consistent across 86? | The contract suite, the domain templates, and the scenario requirement. Consistency is enforced mechanically rather than by review attention. |
