# Tarefas — 061 Changes proposed by the agent

Depends on 058 (config write/preview path, approval-gated saves), 059
(operating-context section and final-text preview), 056 (detector-candidate
shape, knowledge versioning). Ordered, one commit each, test-first.

## Fase 1 — generalise the queue

- **T-001** Characterisation tests over `ProposalQueue.propose` and the
  knowledge applier as they behave today (screen, request, rollback plan,
  apply); green before any refactor.
- **T-002** Extract the shared propose-screen-queue shape with
  `proposal_type`; knowledge origin migrated onto it; T-001 stays green.
- **T-003** Failing tests: the validator refuses a proposal without
  evidence, rationale, or originating run; refuses any payload touching a
  schema-marked credential field or the guardian document, at propose
  time, with the refusal returned to the caller (acceptance 6). Implement.
- **T-004** Failing tests per new origin, one commit each:
  - operating-context proposal → applier writes the section through the
    config service; provenance reads `agent, approved by <actor>`;
  - detector proposal → applier enables the (possibly created, disabled)
    detector row;
  - configuration proposal → applier is 058's write path.
  Each stores its rollback plan at propose time and rolls back through
  `POST /v1/approvals/{id}/rollback` (acceptance 5).

## Fase 2 — the screen

- **T-005** Queue screen in the settings zone: list with type, summary,
  origin-run link; contract test that the run link resolves. Component
  tests first.
- **T-006** Per-type effect rendering: config → 058 preview diff; detector
  → dry-run result; knowledge/context → final text and destination.
  Approve control absent until the effect has rendered (acceptance 3);
  e2e drives the bypass attempt.
- **T-007** Rejection with required reason; recall of prior rejections by
  correlation key rendered on a matching new proposal (acceptance 4).
  Failing tests first for the query and the rendering.
- **T-008** Dashboard attention-band counter + nav counter from one count
  endpoint; absent at zero (the band may disappear, D3 §1). Component
  tests.

## Fase 3 — the loop, end to end

- **T-009** e2e: a scripted investigation calls `knowledge_propose`; the
  proposal appears with evidence and run link; approve after viewing the
  effect; the document exists with agent+approver attribution; roll it
  back; audit shows both acts (acceptances 1, 2, 5).
- **T-010** Failing test: nothing in any applier path executes without a
  decided approval — drive an undecided proposal through every applier
  entry point and assert refusal (acceptance 2's negative half).
- **T-011** Acceptance-rate figure on the queue screen from decided
  history. `make verify` + `make test-postgres` green (approval-store
  metadata changes); `schema.ts` regenerated; visual baselines.

## Definição de pronto

1. An investigation that finds something new produces a queued proposal
   with evidence and a working link to its run (T-009).
2. No proposal applies without explicit human approval (T-010).
3. Approving a config proposal requires the preview; a detector one, the
   dry-run (T-006).
4. Rejection requires a reason, and the reason resurfaces on the next
   similar proposal (T-007).
5. Every applied proposal is reversible and audited with agent and
   approver (T-004/T-009).
6. Credential- or guardrail-touching proposals are refused at the origin
   (T-003).

## Dependências em outras features specs_v3

- **058** (hard), **059** (hard), **056** (hard) as above.
- **Feeds 062**: proposal decisions are among the events a delivery
  destination can subscribe to ("aprovação pendente" is one of 062's
  event types).
