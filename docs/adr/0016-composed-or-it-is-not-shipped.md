# ADR 0016 — Composed or it is not shipped

- **Status:** Accepted
- **Date:** 2026-08-23
- **Constitution impact:** a new article on composition and delivery — a
  mechanism merged without a path from a serving composition root, or without
  an explicit declaration that it is dormant, is not complete

## Context

Multiple independent mechanisms have merged into this repository fully
tested, passing every gate that existed, and have then sat unreachable from
anything that actually serves a request. The shape repeats: a plan's own
design review passes because the design is sound; a contract test proves the
mechanism does what it claims in isolation; the full verification gate is
green because every test that exists passes. And no caller anywhere in a
running deployment ever constructs the thing. The gap between "the piece
works" and "the piece is wired into what runs" is invisible to every check
that exists, because every one of those checks is a test — and a test is,
definitionally, a caller that is not a serving path.

This is not a design defect in the mechanisms themselves. In more than one
case the underlying safety property held regardless — a permission-denied
stub, a fail-closed default — so the absence of composition was safe rather
than dangerous. What it was not, was disclosed. A reviewer reading a green
gate and an approved plan had no way to tell "this is running in production"
from "this exists and nothing calls it" without independently tracing every
construction site by hand.

## Decision

Three rules, together:

1. **Every mechanism that is merged is reachable from a composition root that
   serves real traffic, or it declares itself dormant.** A composition root is
   the place in the running deployment's own startup or request-handling path
   where a concrete instance is actually constructed and wired to what calls
   it — not a test fixture, not a contract-test harness, not a mock data
   plane. A mechanism that is not yet wired that way does not pretend
   otherwise: the module that defines it carries an explicit declaration that
   it is dormant, naming the composition root that would wire it in once it is
   built.
2. **A symbol that only tests construct is not a delivery.** Passing tests
   prove the mechanism does what its tests say it does. They do not prove
   anything about whether the mechanism does that for a real caller, because a
   test is exactly the kind of caller this rule is not about. A feature that
   reports itself complete on the strength of test coverage alone, with no
   serving caller and no dormancy declaration, is reporting a hypothesis as a
   finding.
3. **Closing a feature includes evidence of the serving path.** Not a
   description of one — a caller a reader can open, or, for a mechanism
   deliberately not wired yet, the declaration of dormancy naming what will
   wire it. "The tests are green" answers a different question than "is this
   reachable," and closing a feature answers both or neither.

## Rationale

**The composition root is the only place these facts collide.** Whether a
mechanism is actually called by anything a deployment runs is a fact about
the running deployment, not about the source tree — and a check that runs
against the source tree can prove the pieces exist without ever proving they
are connected. Asking each feature to name where it is composed makes the
reviewer's question the same question the closing report already has to
answer, instead of a second investigation nobody has time for.

**Dormancy is not a downgrade from composition — it is the honest alternative
to a silent gap.** A mechanism nothing calls yet is not necessarily wrong to
merge: sequencing a change across several pieces of work so the
safety-critical half lands before the half that depends on it is often the
right order. What is wrong is merging it as though it were finished. A
dormancy declaration costs one sentence and changes nothing about what runs;
a missing one costs a reviewer a trace through the whole tree to discover the
same fact by hand, and costs a deployment the difference between "designed
for this" and "actually does this."

**A test is not a lesser composition root — it is not a composition root.**
The distinction is not about test quality. The most thorough contract test
suite in this repository still only proves what happens when the test calls
the mechanism, and a production request is a different caller a test can
prove nothing about by construction. Treating a test as sufficient evidence
of delivery is the exact substitution that let independent mechanisms merge
fully tested and go unreachable.

## Alternatives considered

| Alternative | Rejected because |
|---|---|
| Fold this into the existing rule about landing tests before implementation | That rule is about the order tests and implementation land in; it says nothing about whether either one is ever called from a serving path, and the failure this decision responds to happened precisely because "tests are green" was read as satisfying a question it does not answer. Attaching the new rule to the old one presents it as a corollary of test discipline, when it exists because test discipline does not imply it. |
| Rely on code review to catch an unreachable mechanism | Every instance this decision responds to passed review. A mechanism's absence from a serving path is invisible in a diff that adds the mechanism cleanly and adds its tests alongside it — the diff looks identical whether or not a later change ever calls it, because the caller, when it exists at all, is usually a separate change entirely. |
| Require full end-to-end infrastructure for every change, so an unreachable mechanism would fail at runtime | Disproportionate for the problem: most changes do not need a live cluster to prove they are composed, they need one sentence naming the composition root or the dormancy declaration. A rule only a heavy environment can satisfy is a rule contributors route around. |
| Say nothing normative and rely on the closing report's own honesty | The closing reports that missed this were not dishonest about what they measured — they answered "do the tests pass" accurately. The gap was that nothing asked the other question. A rule has to ask it, or it keeps not getting asked. |

## Consequences

**Positive**

- A reader of a closing report can tell, without tracing the tree by hand,
  whether a mechanism runs in the deployment or is declared dormant on
  purpose.
- A mechanism sequenced ahead of its own composition root is distinguishable
  from one that was simply forgotten.
- The question "who constructs this in production, and where" becomes
  something every feature answers as a matter of course, rather than
  something an auditor has to go looking for after the fact.

**Negative**

- Every feature now carries one more thing to state explicitly, which is
  friction on features that compose cleanly and would have been reachable
  anyway.
- A dormancy declaration can be used to defer composition indefinitely if
  nothing ever revisits it — the rule names the debt, it does not collect it
  automatically.

**Mitigations**

- The declaration is one sentence at the point the mechanism is defined, not a
  separate document — the cost is close to the benefit.
- A dormancy declaration names the composition root that would wire the
  mechanism in, which is exactly the fact a later change needs to close the
  gap, rather than starting from nothing.
