# ADR 0007 — No first-party telemetry

- **Status:** Accepted
- **Date:** 2026-08-04
- **Constitution impact:** Article X

## Context

The pipeline design embeds PostHog (product analytics) and Sentry (error reporting) as
**opt-out** — active by default, disabled with `NO_TELEMETRY=1`. This is
standard practice for open-source projects seeking usage signal.

NinjaSRE's target operator runs regulated or security-sensitive infrastructure and
chose a self-hosted tool specifically to keep production telemetry inside their
perimeter. For that buyer, a default outbound connection to a third-party
analytics endpoint is not a minor default — it is a procurement finding.

The exposure is also worse here than in a typical developer tool. An SRE agent's
error reports naturally contain infrastructure identifiers: cluster names, service
names, namespaces, hostnames, alert text, and stack traces from vendor API calls.
That is exactly the data the operator is trying to contain.

## Decision

**NinjaSRE contains no first-party telemetry, analytics, crash reporting, or
usage tracking that transmits off-host.**

1. No PostHog, no Sentry, no analytics SDK in the dependency tree.
2. Observability is OpenTelemetry pointed at an **operator-configured** collector,
   **disabled by default**.
3. No component phones home for version checks, licence validation, or feature
   flags.
4. Transcripts, traces, episodes, and reports live only in the operator's
   database.

PostHog and Sentry remain available as **user integrations** — the agent can query
the operator's own PostHog or Sentry as evidence sources. That is the opposite
direction of data flow and is explicitly in scope.

## Rationale

**Adoption, not analytics, is the constraint.** For this product category the
binding constraint on adoption is security review, not product-analytics
sophistication. A tool that transmits by default fails the review.

**Opt-out is a trust statement.** Shipping opt-out telemetry in a tool that
handles production incident data communicates a posture inconsistent with
everything else in the constitution — mandatory credential proxying, reversible
masking before external LLM calls, read-only by default.

**The usage signal is replaceable.** GitHub stars, issues, discussions, and direct
operator conversation provide product signal without a network egress from a
production-adjacent process.

**Local observability is strictly better for the operator.** OTel traces into
their own collector give them more insight than a vendor dashboard gives us, and
they own the retention policy.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Keep opt-out telemetry | Blocks adoption in the target segment and contradicts the rest of the constitution |
| Opt-in telemetry to our endpoint | Better, but still requires shipping and maintaining collection code, and still invites the "what exactly is sent?" review question |
| Opt-in telemetry to an operator-hosted backend | Effectively what OTel already provides; a second mechanism adds no value |

## Consequences

**Positive**

- Passes security review without a telemetry exception
- No collection code, no privacy policy surface, no data-processing agreement
- Consistent with the product's stated posture
- Smaller dependency tree

**Negative**

- No aggregate visibility into feature usage, error rates, or version distribution
- Bug reports depend on operators reporting them
- Cannot measure adoption quantitatively

**Mitigations**

- Structured local logs and an optional OTel export give operators everything
  needed to file a high-quality bug report
- A `ninjasre diagnose` command bundles a redacted local diagnostic archive the
  operator can review and attach to an issue
- The CI evaluation suite substitutes for production error signal on the
  investigation path, which is where quality regressions actually matter

## Implementation notes

- Remove the pipeline design's `platform/analytics/` and Sentry integration during the port
- The provenance map records both as explicit rejections
- A CI dependency check fails the build if `posthog`, `sentry-sdk`, or a similar
  package enters the runtime dependency set (they may appear in optional
  integration extras, which are user-facing and inert unless configured)
