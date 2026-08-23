# Plano — 061 Changes proposed by the agent

## O que existe, verified — the loop is built for one origin already

More than the spec's "what exists" list:

- `platform/knowledge/proposals.py::ProposalQueue` — `propose` screens the
  content, writes an **approval request** (`create_request`) *and a
  rollback plan* (`store_rollback_plan`), with metadata keys for evidence,
  rationale, amends-target and correlation. `platform/approvals/appliers.py`
  already applies an approved knowledge proposal. So for the knowledge
  origin, propose → screen → queue → approve → apply → rollback exists end
  to end; `knowledge_propose` (the capability) binds
  `KnowledgeService.proposals`.
- The approvals surface: `/v1/approvals`, `/{id}`, `/{id}/rollback`, the
  `/approvals` screen, and `console/src/surfaces/proposal.tsx` /
  `decision.tsx` components.
- The effect-preview mechanisms per type: config
  `POST /v1/config/{node_id}/preview` (058's editor), detector
  `POST /v1/detectors/{id}/dry-run` (056's candidates are already
  disabled detector rows with `origin`), context final-text preview (059).

What is missing: the two other origins (operating context, config/
detectors), the unified queue screen with per-type effect preview,
rejection-with-reason recall, the dashboard counter, and the structural
refusals (credential, guardrail).

## Escopo A — generalise the queue

**Decision — one queue, typed proposals, not three queues.** The approval
store is the queue (it already holds state, evidence, rollback plans, and
the audit trail); a proposal is an approval request with a
`proposal_type` ∈ {knowledge, operating_context, detector, configuration}
and type-specific payload. `ProposalQueue`'s screen-then-queue shape is
extracted so the three origins share it:

- **knowledge** — exists (the extraction is a refactor under a
  characterisation test, Article XII.2);
- **operating_context** — payload is a section add/change for 059's
  `OperatingContext` at a named node; applier writes through the config
  service (so provenance shows `agent, approved by X`);
- **detector** — payload references a disabled detector row (056's shape)
  or proposes one; applier enables it;
- **configuration** — payload is a config patch for a node; applier is
  058's write path, which already honours approval-gated fields.

Every proposal carries, structurally required (validator refuses without):
what would change, why (rationale), the originating run id, and the
computed consequence reference. The originating-run link makes acceptance
1's "ligação para a investigação de origem" a field, not prose.

**Structural refusals (acceptance 6)**: the proposal validator rejects, at
`propose` time, any payload touching a credential field (the schema-marked
secret set — 051's config-route seal is the same rule) or the guardian
document. Refused at the origin means the capability returns the refusal
to the agent; nothing enters the queue.

## Escopo B — review is seeing the effect

The queue screen (settings zone, D2's "Mudanças propostas" with counter):
each proposal renders its effect with the mechanism its type already has —
config → the 058 preview diff with provenance; detector → the dry-run
("what it would have fired on"); knowledge/context → the final text and
where it will appear (059's final-text rendering for context). **Approving
requires the effect to have been rendered** — same client-flow guarantee
as 058's preview-before-save, e2e-tested the same way (acceptance 3).

## Escopo C — rejection is information

Rejecting requires a reason (the decision component gains a required
field). Reasons are stored on the approval record and **recalled**: a new
proposal whose correlation key matches a previously rejected one renders
the prior rejections — count, reasons, dates — on the review screen
(acceptance 4). The correlation key exists in the proposal metadata
(`CORRELATION_KEY`); the recall is a query over decided approvals by that
key. The spec's three-strikes insight stays human: the screen shows the
pattern; it does not auto-decide.

## Escopo D — applied is reversible

Rollback plans are already stored at propose time (the `ProposalQueue`
behaviour, generalised): context/config rollback is the prior document
section; detector rollback is disable; knowledge rollback is the prior
version (the version chain from 056). `POST /v1/approvals/{id}/rollback`
executes it; the audit shows `agent, approved by X` on apply and the
reverser on rollback (acceptance 5).

## Escopo E — visible from where you work

The dashboard's attention band (D3 §1's first band) gains the pending-
proposals counter beside pending approvals, linking to the queue; the nav
item carries the same counter (D2). Both read one count endpoint.

## O que esta feature NÃO faz

- No auto-apply at any confidence (autonomy policy's future decision, 058's
  domain).
- No proposal *generation* changes: what the agent proposes and when is
  the existing capability + guidance synthesis
  (`platform/memory/guidance.py`, `platform/knowledge/guidance.py`); this
  feature is the human side of the loop.
- No credential or guardrail proposals, structurally.

## Verificação de constituição

- **I** — a proposal without evidence/rationale/run link is refused by the
  validator; the review renders the evidence.
- **III** — this *is* Article III for learning: per-action human approval,
  stored rollback before execution, audit on both directions. Approval
  never generalises (III.4): each proposal is decided alone.
- **VII** — accepted-proposal outcomes are measurable: the applied-context
  and enabled-detector changes flow into mechanisms whose ablations 059/
  056 built; this feature adds the acceptance-rate figure to the queue
  screen (data already in the store).
- **VIII/XI** — queue generalisation in `platform/` (approvals +
  knowledge), appliers beside the existing one; storage via ports.
- **XII** — characterisation test before the `ProposalQueue` extraction;
  failing tests per origin and per refusal.
