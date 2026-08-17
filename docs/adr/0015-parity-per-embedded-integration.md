# ADR 0015 — Parity per embedded integration, breadth staged by validatable environment

- **Status:** Accepted
- **Date:** 2026-08-17
- **Supersedes:** [0009](0009-full-integration-parity.md)
- **Constitution impact:** the capabilities article's parity clause

## Context

ADR 0009 committed the catalogue to full parity across every integration the two
prior systems covered between them, and defined parity as seven artefacts: config
schema, verifier, client, typed tools, methodology skill, documentation, and at
least one synthetic scenario.

That definition has held up. The seven are enforced by a gate that walks the
catalogue rather than a list, so an integration cannot reach the console without
them, and the failure names the vendor and the artefact.

What has not held up is the breadth the same ADR committed to. Parity was
enforced against the *shape* of each integration, never against evidence that the
integration works. The artefacts were present and the vendor was unreachable: no
credential to store, no endpoint to verify against, no real response to read. A
verifier that has never run against the system it verifies is a file that passes a
gate, and a synthetic scenario built from a fixture nobody recorded from a live
call is a test of the fixture.

The catalogue therefore carried two populations that looked identical from the
console — integrations an operator could configure and use, and integrations that
had every artefact and no way to be exercised. The second population is not
neutral. A card in the catalogue is a promise, and it is chosen on the strength of
being there, by someone who discovers at 03:00 that the promise was structural.

## Decision

**Parity is per embedded integration, and it is unchanged in form.** Every
integration in the catalogue ships all seven artefacts. No artefact becomes
optional, no tier of lesser integrations is created, and the gate is not relaxed.

**Breadth is staged by validatable environment.** An integration is embedded when
a deployment exists that can validate it end to end:

1. its credential can be stored,
2. its connection can be verified against the real system, and
3. at least one real read has been exercised against it.

An integration that cannot meet those three conditions is not embedded. Its
intent is recorded, and its code is not in the tree — because code that ships
without an environment to exercise it is the shape this decision exists to
prevent.

**The current breadth is read from the integration scope section of
[the roadmap](../roadmap.md), not from this record.** A decision record that names
a set fixes it at the date it was written; the roadmap is where the set moves.

An integration returns by the same door it left: an environment that validates it,
plus its synthetic scenario.

## Rationale

**A verifiable catalogue is a smaller claim that is true.** Coverage drives
adoption, which is why 0009 chose breadth — but the coverage that drives adoption
is coverage of the systems the evaluating team runs, and every entry beyond that
is weight. An operator who finds their stack covered and working is convinced by a
short list; an operator who finds their stack covered and broken is not convinced
by a long one.

**The three conditions are the cheapest honest test of "this works".** Stored,
verified, read. Each is observable, each fails loudly, and together they
distinguish an integration that functions from one that is merely well-formed.
Nothing weaker separates the two populations, and nothing stronger can be enforced
without a live credential set for every vendor in CI.

**Parity had to survive intact for the change to be safe.** Narrowing breadth
while also loosening the artefact requirement would produce a small catalogue with
the same defect. Keeping the seven means the reduction is purely a reduction in
promises, and the gate that enforces them gets stricter in effect: it now runs
against a set where every member can be checked.

**Deferring is not deleting.** The intent behind an integration is worth keeping
even when the code is not, and the methodology written for a vendor outlives the
package. Both are recorded in the tree rather than in memory.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Keep every integration, mark the unvalidatable ones degraded in the console | The degraded state is honest and still leaves the code in the tree, carrying maintenance and vendor-API drift for systems nobody can exercise. It relabels the problem rather than removing it |
| Keep the code, drop the parity requirement for unvalidatable vendors | Recreates the two-tier catalogue that 0009 rejected for the right reason: the second tier has no verifier and no scenario, and fails in the most expensive way available |
| Name the embedded set in this record | Fixes the set at today's date. A record that must be amended every time an environment appears is a record that will be stale instead of amended |
| Gate breadth on a live credential in CI for every vendor | The strongest possible evidence and unaffordable: it requires the maintainers to hold and rotate credentials for every vendor, and makes the catalogue's size a function of the maintainers' billing relationships |

## Consequences

**Positive**

- Every card in the catalogue corresponds to a system this deployment can reach,
  verify, and read from
- The parity gate runs against a set whose members can each be exercised, so a
  green gate means more than it did
- Vendor-API drift is a maintenance load only for vendors in use
- The synthetic scenario corpus shrinks to scenarios built from systems that exist

**Negative**

- The catalogue is smaller, and an evaluating team whose stack is outside it sees
  a gap where there was previously an entry
- Removing an integration removes its coverage of any pattern it was the only
  example of; a pattern left with no vendor exercising it is covered by unit tests
  of the mechanism alone
- The embedded set now depends on the environments available, which is a property
  of the deployment rather than of the repository

**Mitigations**

- The intent behind every deferred integration is recorded in the roadmap's
  integration scope section, with the condition that would bring it back
- The methodology written for a deferred vendor is archived in the tree rather
  than deleted, so an integration that returns brings its investigative guidance
  with it instead of being re-derived
- The framework is unchanged: the scaffold still emits seven artefacts, and an
  integration whose environment appears is a scaffold run plus a scenario, not a
  redesign
- Protocol bridging remains available for systems beyond the embedded set, as an
  extension path rather than a substitute for parity
