# Plan — 041 First Run, Seeding and Demo Mode

## Technical context

| Concern | Choice |
|---|---|
| Tier | `platform/startup/` extended, plus `deploy/ops/` for the host-side pieces |
| Bootstrap credential | An ordinary token issued through the identity system with a short expiry and a single grant, written to a host file readable by the operator |
| Self-check | Extends the existing `deploy/ops/preflight.py` and `check.py` rather than adding a third checker |
| Demo fixtures | Recorded provider responses and a scripted event stream, stored as data files, loaded through a fixture transport |
| Demo labelling | A column on every record, not a naming convention |

## Constitution Check

| Article | Bearing | Compliance |
|---|---|---|
| IV — Secrets never reach the agent | A bootstrap credential is a secret with a short life. | It is issued through the normal identity path, never logged, never audited in cleartext, and expires on first use. NFR-004 forbids any exception to the identity system. |
| X — Operator owns their data | Demo data must not contaminate real data. | FR-017 labels every record; FR-019 removes them completely; FR-020 refuses to seed over real data. |
| I — Evidence over assertion | A self-check that says "OK" without checking is worse than none. | FR-012: every step verifies against the real dependency. FR-006 for the model: tool calling and structured output are exercised, not assumed from a reachable endpoint. |
| XII — Test-first | The specific bug that motivated this feature is a missing test. | SC-001 is written first: bring up, read the token, sign in. It would have caught the rejected bootstrap token. |

## Architecture decisions

**The bootstrap credential is a real credential.** Not a bypass, not a magic
header, not an environment variable the gateway special-cases. It is issued
through the identity system with a short expiry and one grant: establish a
durable credential. This keeps the identity system the only way in, which means
the bug where an environment variable and the database disagreed cannot recur —
there is only one source.

**The end-to-end sign-in test is the point of the feature.** Everything else here
is polish; SC-001 is the regression. It brings up a clean deployment the way an
operator does, takes what the operator is given, and uses it the way the operator
would. Any test that reads the token from somewhere other than where the operator
reads it would not have caught the original failure.

**Findings carry an action or they are not findings.** FR-009 is enforced by the
type: a finding requires both a problem and a next action to construct, so
"connection error" cannot be emitted. This is the difference between a self-check
that helps and one that restates the exception.

**Model verification exercises the contract.** An endpoint answering is not the
property that matters. What matters is whether the model can call a tool and
return structured output, because a model that cannot do those will fail in the
middle of the first investigation with something inscrutable. Verifying it at
setup turns a confusing failure into a clear one — and this is the check that
matters most for the self-hosted models feature 043 addresses.

**Demo data is labelled in the schema.** A column, not a prefix on names. A
prefix is a convention that the first person to write a query forgets; a column
can be asserted on and swept.

**Demo mode fails on a real request.** The fixture transport raises when asked to
make an actual network call. Without that, demo mode drifts into "mostly
fixtures" and eventually someone's demonstration calls a paid API.

## Phases

1. **Bootstrap.** Short-lived credential through the identity system, host-file
   delivery, retrievable again, expiry on establishing a durable credential, the
   no-logging sweep, idempotent bring-up, migration version refusal.
2. **The regression test.** SC-001 end-to-end, written before anything else in
   this feature is touched.
3. **Self-check.** Extend the existing preflight with the full check list, the
   finding type requiring an action, single-pass ordered reporting, CLI and
   console and bring-up entry points, timeouts.
4. **Model verification.** Tool calling and structured output exercised against
   the configured provider, with messages naming the actual limitation.
5. **Setup experience.** The checklist, per-step real verification, completion
   and later reachability, the guided first investigation.
6. **Demo mode.** The coherent scenario dataset, referential integrity assertion,
   labelling column, fixture transport that refuses real calls, scripted
   streaming investigation, one-action removal, refusal over real data.
7. **Diagnostics.** Bring-up failure messages reachable afterwards, and the
   support bundle with secrets removed.

## Risks

- **Demo data is mistaken for real data.** Mitigated by the schema column, the
  console labelling, and FR-020's refusal to seed over real data.
- **The self-check becomes a wall of green ticks nobody reads.** Mitigated by
  FR-008's ordering: what blocks the most comes first, and a passing check reports
  briefly rather than exhaustively.
- **The fixture set rots as the API changes.** Mitigated by generating demo
  fixtures through the same contract tests the integrations already have, so an
  API change breaks the fixture at the same moment it breaks the client.
