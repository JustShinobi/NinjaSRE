# Plano — 062 Ingress and delivery: where it came from, where it goes

## O que existe, verified

- **Ingress**: the seven webhook routes with payload cap, per-team
  verifier routing (`WebhookSourceConfig`), delivery idempotency, load
  shedding, dedup-link and resolution handling
  (`gateway/webhooks/router.py::handle`) — plus 055's alert→resource
  resolution and paste-ready panel. What ingress *lacks* is memory: the
  idempotency index remembers event ids, but no queryable record of
  deliveries (when, outcome, why rejected, what the payload looked like)
  survives for a screen.
- **A routing precedent**: `gateway/chat/routing.py::RoutingTable` — rows
  matching source + severity floor to a team target, duplicate-refusing,
  "an unrouted channel is refused rather than defaulted". 062's rules
  generalise this shape (ordered evaluation, resource/zone/criticality
  matchers from the estate) rather than inventing a second one.
- **Masking**: `platform/masking/` detectors and the guardrail engine —
  the policy a sample or an outbound payload passes through exists; what
  is missing is applying it at these two seams and *naming* the applied
  policy in the surface.
- **Outbound**: nothing. Chat integrations exist in the catalogue
  (`channels_for_alert` shows the posting half for chat), but there is no
  destination concept — which events, which channel, what detail level.
- **Provenance**: config values and investigation claims carry origins;
  transit does not.

## Escopo A — ingress made operable

1. **A transit ledger**: a new repository port (the estate feature's §2
   lesson applies — every "thirteen ports" count in the tree moves to
   fourteen in the same change) recording, per ingress delivery: source,
   instant, outcome (accepted / rejected+reason / shed / duplicate),
   matched route, resolved resource, and a **masked sample** of the last
   payload per source (stored *after* the masking policy — the raw body
   is never persisted). Bounded: samples per source = 1, delivery rows
   under the existing retention `DataClass` machinery (one sweeper, one
   enumeration — the 038 §3 rule).
2. The webhook handler writes the ledger on every path, including
   refusals — a rejected delivery that leaves no trace is the silent
   failure this spec exists to kill.
3. **The screen (settings zone, "Dados", D2/D3 §5)**, ingress column: per
   source — URL, token state (via 055's issuance panel, absorbed here),
   expected format, last delivery + when (green within window, dimmed
   **never-delivered** as the most visible state on the screen — D3 §5
   makes silence the loudest thing), counts per window, recent rejections
   with reasons, the masked sample.

## Escopo B — routing rules

A configuration section (058's tree — rules are config, with provenance
and inheritance) of **ordered rules**: match (source, zone, criticality,
resource — zone and criticality resolved from the estate via 055's
resolution, never free text), target team, action (investigate / record
only / discard-with-reason).

- Evaluation replaces the current one-team-per-verifier shortcut as the
  step *after* verification: verifier authenticates and scopes; rules
  decide what happens. The default rule set reproduces today's behaviour
  exactly (every verified delivery → matched team → investigate), proven
  by a characterisation test before the seam moves.
- **The last rule is structural**: the section validates only if the
  final rule is a catch-all whose action is explicit; the editor renders
  it always (acceptance 4). Discard is always discard-*with-reason*, and
  discarded deliveries still enter the ledger.
- **Simulation before save** (the 058 discipline, acceptance 3): a
  simulate endpoint takes a pasted payload or a ledger delivery id and
  returns the matched rule, team, and action — the same evaluation
  function the live path runs (the `preview_change` purity argument:
  one implementation, called twice, or the preview lies).

## Escopo C — outbound destinations

A destination declares: events (investigation concluded, remediation
proposed, approval pending, source degraded — a closed enum that 061's
proposal events join), channel (a delivery integration from the
catalogue), and **detail level** (summary-with-authenticated-link vs full
report) — with the applied masking policy named on the destination row.
Defaults are the safe ones: no destination receives raw evidence or
anything the masking policy holds back (acceptance 5 — the outbound
payload passes the same guardrail/masking path as any externalised text,
Article IV.4's existing seam).

Delivery attempts land in the same transit ledger: outcome, retry with
backoff (bounded, named constants), manual re-send from the screen
(acceptance 6), and failure as a visible state — "a report that did not
arrive is worse than one that never existed".

**Decision — no new outbound integrations**: the destination concept
binds whatever delivery-capable integrations the catalogue has; a
deployment with none configured shows destinations as unconfigurable with
the reason (the 054 known-gap posture).

## Escopo D — provenance for transit

The ledger rows make the two questions answerable from the screen: this
alert entered by this route, matched this rule, went to this team (ingress
row → rule → run link); this finding came from this query at this origin
at this instant (already in the trace — the screen links the claim's
evidence entry). The Dados screen's detail drawer renders the chain.

## O que esta feature NÃO faz

- No payload transformation language, no message queue, no new outbound
  channel integrations (spec's out-of-scope).
- No change to dedup/idempotency semantics (055 owns them; the ledger
  records their outcomes).

## Verificação de constituição

- **II** — sample size, ledger page sizes, retry counts/backoff, window
  lengths: named constants.
- **III** — outbound destinations are operator-configured delivery, not
  agent capabilities; re-send is a human act, audited.
- **IV** — raw payloads never persisted; samples and outbound bodies pass
  masking; the destination row names the policy applied.
- **VIII** — rule evaluation in `platform/` (the chat-routing lesson:
  matching in one function), handler stays a caller; screen over HTTP.
- **XI** — the fourteenth port, with every port-count assertion and
  document updated in the same commit; retention through the existing
  sweeper.
- **XII** — characterisation test before moving the routing seam; ledger
  contract suite runs under `make test-postgres`.
