# Feature 008 — Guardrails and Masking

- **Wave:** 1 — Trust & Safety
- **Branch:** `feat/008-guardrails-and-masking`
- **Status:** Draft
- **Depends on:** 001, 004, 006
- **Blocks:** 017, 021, 022, 023

## Summary

Two complementary controls at the trust boundary. **Guardrails** scan every string
the system persists or transmits and redact, block, or audit it by rule.
**Masking** replaces infrastructure identifiers with reversible tokens before any
external LLM call and restores them when rendering to an authorised human.

Feature 007 removes credentials from the agent's reach. This feature handles
everything else sensitive that legitimately *is* in reach — pod names, cluster
identifiers, account IDs, customer data in log lines, PII in error messages.

## User scenarios

### Primary story

An operator in a regulated environment uses a cloud LLM provider. Their pod names,
cluster names, and AWS account IDs are replaced with stable pseudonyms before the
prompt leaves the network. The model reasons about `pod-a1` and `cluster-b2`; the
report the on-call engineer reads names the real pod and cluster.

### Acceptance scenarios

1. **Given** a prompt containing infrastructure identifiers, **when** it is sent to
   an external provider, **then** each identifier is replaced with a stable token
   for the duration of the run.
2. **Given** a model response referencing a masked token, **when** the report is
   rendered to an authorised human, **then** the original identifier is restored.
3. **Given** the same identifier appearing in two places, **when** masking runs,
   **then** both receive the same token, so the model can correlate them.
4. **Given** a guardrail rule with action `redact`, **when** matching text is about
   to be persisted or transmitted, **then** the match is replaced and the event is
   audited.
5. **Given** a rule with action `block`, **when** matching text appears in a tool
   argument, **then** the call is denied via `pre_tool_use` and the model receives
   a structured denial.
6. **Given** overlapping matches from several rules, **when** redaction runs,
   **then** spans are merged deterministically and the representative rule is the
   widest contributing match.
7. **Given** a locally-hosted model, **when** masking policy is set to
   `local_models_exempt`, **then** identifiers are not masked, because nothing
   leaves the host.
8. **Given** an operator adding a custom rule in YAML, **when** the platform
   reloads, **then** the rule takes effect without a code change.
9. **Given** a malformed rules file, **when** it loads, **then** the platform
   starts with the last known-good ruleset and reports the error — it does not
   start unguarded.

### Edge cases

- A masked token appearing inside a JSON payload the model must return verbatim.
- An identifier that is also a common English word (`frontend`, `production`).
- Masking so aggressive that the model loses the ability to distinguish entities.
- A regular expression with catastrophic backtracking on a large log payload.
- Restoration when a report is delivered to a channel with mixed authorisation.
- A rule matching text inside an already-redacted span.

## Requirements

### Functional

**Masking**

- **FR-001** Masking MUST be reversible: an identifier maps to a stable token for
  the run, and the mapping is retained for restoration.
- **FR-002** The same identifier MUST always receive the same token within a run,
  so the model can correlate occurrences.
- **FR-003** Detection MUST cover at minimum: Kubernetes pod names, namespaces,
  cluster names, service and deployment names, hostnames, cloud account IDs, ARNs,
  IP addresses, and operator-configured custom patterns.
- **FR-004** Contextual detectors (namespace, cluster, service) MUST match only
  when preceded by a recognised label, so generic words are not masked
  spuriously.
- **FR-005** All detector regular expressions MUST be non-backtracking on
  adversarial input. A ReDoS test MUST cover every detector.
- **FR-006** Masking MUST apply at the external-LLM boundary. Restoration MUST
  apply when rendering to an authorised human.
- **FR-007** Masking policy MUST be configurable per team: `off`, `standard`,
  `strict`, and `local_models_exempt`.
- **FR-008** The mapping MUST be stored with the run and MUST itself be treated as
  sensitive — never transmitted externally, never in a report.
- **FR-009** Masking MUST NOT alter text the model must reproduce exactly, unless
  that text contains an identifier — in which case restoration handles it.

**Guardrails**

- **FR-010** Rules MUST be declarative YAML with: name, description, patterns,
  keywords, action (`redact` | `block` | `audit`), replacement, enabled.
- **FR-011** Rules MUST load from an operator-controlled path with hot reload.
- **FR-012** A malformed ruleset MUST NOT start the platform unguarded — the last
  known-good set is retained and the failure reported (FR acceptance 9).
- **FR-013** `redact` MUST replace the match; `block` MUST deny the operation;
  `audit` MUST record without altering.
- **FR-014** Overlapping matches MUST merge deterministically, with the
  representative rule being the widest contributing individual match.
- **FR-015** Scanning MUST be bounded: a maximum match count and a maximum input
  size, both named constants, with truncation recorded.
- **FR-016** Guardrails MUST apply at three points: `pre_tool_use` (tool
  arguments), `post_tool_use` (tool results), and any persistence or transmission
  boundary.
- **FR-017** A `block` at `pre_tool_use` MUST return a structured denial the model
  can reason about, not an exception.
- **FR-018** Every guardrail action MUST be audited with rule name, action, and
  location — never the matched value for `redact` and `block`.
- **FR-019** Default rules MUST ship covering common secret shapes (API-key
  patterns, private keys, connection strings, JWTs) as defence in depth behind
  feature 007.

**Boundaries**

- **FR-020** No exception detail (`str(exc)`, traceback, provider internals) may
  reach an external surface — HTTP responses and chat messages. Full detail is
  logged server-side. Local CLI output is not an external surface.
- **FR-021** Redaction MUST happen at the sink boundary, not per call site, so the
  shared engine keeps full detail for local development.

### Key entities

| Entity | Description |
|---|---|
| **MaskingPolicy** | Per-team configuration of level and custom patterns |
| **DetectedIdentifier** | Kind, span, and value found by a detector |
| **MaskMapping** | Run-scoped bidirectional identifier ↔ token map, itself sensitive |
| **GuardrailRule** | Name, patterns, keywords, action, replacement, enabled |
| **ScanMatch** | One rule match: rule, action, span |
| **MergedSpan** | Collapsed overlapping matches with the representative rule |
| **ScanResult** | Matches, resulting text, and whether the operation is blocked |
| **GuardrailAudit** | Rule, action, location, timestamp — never the value |

## Success criteria

- **SC-001** A run against a cloud provider transmits no unmasked pod name,
  cluster name, or account ID — asserted by intercepting every outbound provider
  request in a test.
- **SC-002** Restoration is lossless: a report rendered after masking is
  byte-identical to the same report produced with masking off, for identifier
  content.
- **SC-003** Every detector survives a ReDoS corpus with bounded execution time.
- **SC-004** Overlapping-match merging is deterministic — a golden test pins the
  representative rule for chained and contained overlaps.
- **SC-005** A malformed ruleset leaves the previous ruleset active and reports the
  error; the platform never runs with zero rules due to a parse failure.
- **SC-006** No exception detail reaches an external surface — asserted by a test
  driving errors through the HTTP and chat sinks.
- **SC-007** Masking overhead stays under the configured budget on a 10MB evidence
  payload.

## Out of scope

- Credential removal from the agent (feature 007)
- Approval of side-effecting actions (feature 017)
- Audit storage (feature 006) and audit UI (feature 021)

## Clarifications

| Question | Resolution |
|---|---|
| Does masking hurt investigation quality? | It can if too aggressive, which is why policy is per-team with a `standard` default, `local_models_exempt` for no-egress deployments, and stable tokens (FR-002) so correlation survives. The evaluation suite runs with masking on and off, making the quality cost measurable rather than assumed. |
| Why guardrails as well as the credential proxy? | Defence in depth. The proxy stops credentials the platform manages; guardrails catch secrets that appear in *data* — a connection string in a log line, a token in an error message. |
| Are guardrails applied to local CLI output? | Redaction at the sink means the local CLI keeps full detail (FR-021), because the human running it is already authorised. Persistence and external transmission are always filtered. |
| Can an operator disable guardrails entirely? | Rules can be disabled individually. The engine cannot be removed from the boundary, so the audit action still records what would have matched. |
