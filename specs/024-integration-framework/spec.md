# Feature 024 — Integration Framework

- **Wave:** 6 — Integrations
- **Branch:** `feat/024-integration-framework`
- **Status:** Draft
- **Depends on:** 003, 007, 013
- **Blocks:** 025, 026
- **ADRs:** [0009](../../docs/adr/0009-full-integration-parity.md)

## Summary

The machinery that makes ~85 integrations at full parity tractable: a fixed
anatomy, a shared client base, a verifier framework, a contract suite parameterised
over the catalogue, a scaffold generator, and domain methodology templates. Get
this right and each integration is hours of work; get it wrong and Wave 6 never
finishes.

## User scenarios

### Primary story

A contributor adds Honeycomb. They run the scaffold, fill in the credential
schema, the client's four query methods, and the vendor-specific parts of a
methodology skill derived from the observability template. The contract suite
tells them what is still missing. Nothing central needs editing.

### Acceptance scenarios

1. **Given** the scaffold is run for a new integration, **when** it completes,
   **then** all seven parity artefacts exist as working stubs with provenance
   headers.
2. **Given** an integration missing any parity artefact, **when** the catalogue
   validates, **then** the build fails naming the integration and the missing
   artefact.
3. **Given** an integration client, **when** it makes an authenticated call,
   **then** it routes through the credential proxy and cannot read a secret.
4. **Given** an integration verifier, **when** it runs with valid credentials,
   **then** it confirms connectivity and the specific permissions the capabilities
   need.
5. **Given** a verifier run with insufficient permissions, **when** it completes,
   **then** it names the missing permission rather than reporting a generic
   failure.
6. **Given** a domain template, **when** a new integration in that domain is
   scaffolded, **then** its methodology skill starts from the template's structure.
7. **Given** the contract suite, **when** an integration is added, **then** it is
   covered automatically without writing a new test file.
8. **Given** an integration whose vendor API changed, **when** the contract suite
   runs, **then** the break is detected and the integration is marked degraded
   rather than failing silently.

### Edge cases

- A vendor with no verification endpoint.
- A vendor requiring different credentials per capability.
- A vendor whose API is regional, with a different host per region.
- A vendor SDK that resists proxy routing.
- An integration where one capability needs a permission others do not.
- Pagination styles that differ across a single vendor's endpoints.

## Requirements

### Functional

**Anatomy**

- **FR-001** Every integration MUST be one package under `integrations/<vendor>/`
  containing exactly these artefacts:
  1. `schema.py` — credential and connection schema
  2. `verifier.py` — connectivity and permission check
  3. `client.py` — API client on the shared base
  4. `tools/` — typed capabilities
  5. skill — methodology in `capabilities/skills/<vendor>/SKILL.md`
  6. `docs.md` — setup, permissions, limitations
  7. at least one synthetic scenario exercising it
- **FR-002** Catalogue validation MUST fail the build when any artefact is missing,
  naming both.
- **FR-003** An integration MUST NOT require editing any central file to be
  discovered.

**Shared client base**

- **FR-004** `integrations/_base/client.py` MUST provide: proxy routing, timeouts,
  retry with backoff, rate-limit handling, pagination helpers, and structured
  errors.
- **FR-005** Pagination MUST support cursor, offset, and page-token styles, and an
  integration MAY use different styles per endpoint.
- **FR-006** Errors MUST map to a shared taxonomy: `auth`, `permission`,
  `not_found`, `rate_limited`, `transient`, `invalid_request`, `unavailable`.
- **FR-007** Regional and multi-host vendors MUST be supported through
  configuration, not per-region code.
- **FR-008** No client may read a credential from the environment; a CI check MUST
  enforce this.

**Verification**

- **FR-009** A verifier MUST check connectivity **and** the specific permissions
  the integration's capabilities require.
- **FR-010** A failure MUST name the specific missing permission or the specific
  connectivity problem.
- **FR-011** A vendor with no verification endpoint MUST use the cheapest read
  capability as its probe, documented as such.
- **FR-012** Verification MUST be invocable from the CLI, the console, and CI.

**Contract suite**

- **FR-013** One contract suite MUST be parameterised over the whole catalogue, so
  adding an integration adds a row, not a file.
- **FR-014** The suite MUST assert: schema validity, proxy routing, error mapping,
  pagination behaviour, capability metadata completeness, skill-to-tool binding
  validity, and doc presence.
- **FR-015** The suite MUST run against recorded fixtures by default, and against
  live credentials on a scheduled job.
- **FR-016** A live-run failure MUST mark the integration degraded in the catalogue
  and surface it in the console, rather than failing silently.

**Scaffold**

- **FR-017** A scaffold command MUST generate all seven artefacts as working stubs
  with provenance headers and a contract-suite catalogue entry.
- **FR-018** The scaffold MUST take a domain so the skill starts from that domain's
  template.

**Methodology templates**

- **FR-019** Domain templates MUST exist for: log store, metrics store, tracing,
  cloud control plane, database, version control, CI/CD, ticketing, incident
  management, communication, and data platform.
- **FR-020** A template MUST encode the domain's investigative discipline — for log
  stores, statistics before samples; for infrastructure, events before logs — so a
  new integration inherits it rather than reinventing it.

**Catalogue**

- **FR-021** The catalogue MUST record per integration: category, capabilities,
  required credentials, required permissions, supported regions, health, and
  parity status.
- **FR-022** The catalogue MUST be exposed to the console and to documentation
  generation.

### Key entities

| Entity | Description |
|---|---|
| **Integration** | One vendor package with its seven parity artefacts |
| **CredentialSchema** | Fields, types, validation, and vault mapping |
| **Verifier** | Connectivity and permission probe |
| **BaseClient** | The shared HTTP client every integration builds on |
| **ErrorTaxonomy** | The shared error classification |
| **DomainTemplate** | A methodology skeleton for a class of integrations |
| **CatalogueEntry** | Metadata, health, and parity status |

## Success criteria

- **SC-001** Scaffolding a new integration to a passing contract suite takes under
  two hours for a typical REST vendor — measured by doing it.
- **SC-002** Adding an integration requires editing zero existing files.
- **SC-003** Every integration in the catalogue passes the parameterised contract
  suite.
- **SC-004** No integration client can read a credential — asserted catalogue-wide.
- **SC-005** A verifier with insufficient permissions names the specific missing
  permission for every integration that supports permission introspection.
- **SC-006** A vendor API break marks the integration degraded and surfaces it,
  rather than failing silently.
- **SC-007** All eleven domain templates produce a skill that passes the
  skill-to-tool binding validation.

## Out of scope

- The integrations themselves (feature 025)
- Protocol bridges (feature 026)
- Credential proxy internals (feature 007)

## Clarifications

| Question | Resolution |
|---|---|
| Why seven artefacts rather than "a client and some tools"? | Each one prevents a specific failure. No verifier means discovering a wrong token at 03:00. No skill means the agent knows the API but not the method. No scenario means the integration rots untested. No docs means nobody can set it up. |
| Is two hours per integration realistic? | For a typical REST vendor with a scaffold, a shared base handling auth, retry, and pagination, and a domain template supplying methodology — yes. SC-001 measures rather than assumes it. |
| What about vendors that need bespoke work? | They take longer; the framework does not prevent that. What it prevents is every integration needing bespoke work. |
| Why mark degraded rather than fail the build on a live-run failure? | A vendor's API break is not the operator's fault and should not block their deployment. Marking degraded tells them precisely what will not work while everything else keeps running. |
