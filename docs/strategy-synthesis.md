# Synthesised playbooks

Once a team has investigated the same kind of failure on the same component
enough times, NinjaSRE writes a **playbook** from those investigations and hands
it to the next one alongside the individual episodes.

This page is for the person who has to answer five questions about that: what a
playbook contains, when one is generated, how to correct one, how to turn them
off, and how to trace a claim in one back to the runs it came from.

Episodes themselves are [`episodic-memory.md`](episodic-memory.md). A playbook is
a derivation of episodes and nothing else; if there are no episodes there are no
playbooks.

## What a playbook is

One playbook belongs to one **key**: an organisation, a team, a class of failure,
and a component.

```
acme / team-payments / oom_kill / service:payments
```

It has four sections, in this order:

| Section | What it holds |
|---|---|
| Common root causes | The causes that recurred across the investigations, with how many support each |
| Recommended investigation steps | An ordered sequence, most effective first, based on what actually produced findings |
| Capabilities and queries | The specific capabilities that produced those findings, named as the runs named them |
| Anti-patterns | Approaches that looked promising in previous runs and did not help |

and it carries, alongside them:

| Field | What it is for |
|---|---|
| Episode count and date range | So the agent — and you — can weigh it. Three runs last week is not twenty across a year |
| Source episode ids | Every investigation the playbook was drawn from |
| Anti-pattern episode ids | Specifically the runs the anti-patterns section was entitled to come from |
| Prompt version | Which version of the synthesis prompt produced it |
| Generated at, stale | When it was written, and whether something has happened since that contradicts it |
| Operator amendments | Anything a human has added, with who added it |

**The anti-patterns section is the reason the feature exists.** Runbooks describe
what should work and documentation describes what a system is for. Only
accumulated failure describes what an experienced colleague would have told you
not to bother with, and that section is derived specifically from the
investigations that did *not* establish a cause — never from the ones that did.

## When a playbook is generated

It is generated lazily, when an investigation searches memory and the key it
lands on has no current playbook. Three conditions have to hold.

1. **At least `MIN_EPISODES_FOR_STRATEGY` episodes** share the issue type and the
   normalised component. Below that, nothing is generated and the reason is
   recorded — a young corpus should look young rather than broken.
2. **Strategies are enabled** for the team (see *Turning them off*).
3. **There is no current playbook** for the key — none at all, or the one that
   exists is stale or older than `STRATEGY_MAX_AGE_DAYS`.

Generation is one model call over the highest-ranked episodes on the key, bounded
by `STRATEGY_MAX_INPUT_EPISODES`. It happens at most once per key per change, and
every request after that is a database read.

If several investigations of the same component start at once — an alert storm —
they produce **one** generation, not one each. The rest wait and read the result.

### Why a playbook might not appear

In roughly the order they actually happen:

- **Too few episodes on the key.** The commonest reason, and it resolves itself.
- **The component name drifted more than normalisation covers.** See below.
- **The episodes have no issue type.** Extraction could not classify them, so they
  belong to no key. This shows up as a corpus that grows without any playbook
  appearing.
- **Strategies are switched off** for the team.
- **Synthesis failed.** A provider outage, say. Episode recall is unaffected —
  that is deliberate, and the reason is recorded.

## Component names, and when two of them are one thing

A corpus records the same service as `payments-api`, `payments-service`,
`prod-payments`, and `payments-7f9dd8b6c4-x7gr9`. Left alone, those are four keys
with one or two episodes each and no playbook is ever generated. So names are
normalised before they become a key:

| Rule | Example |
|---|---|
| Case and separators | `PaymentsAPI`, `payments_api`, `payments.api` → `payments` |
| Describing words at either end | `payments-api`, `payments-service`, `payments-worker` → `payments` |
| Environment words at either end | `prod-payments`, `payments-staging` → `payments` |
| Generated segments, and everything after one | `payments-7f9dd8b6c4-x7gr9` → `payments` |
| Trailing ordinals | `checkout-0`, `checkout-2` → `checkout` |

**Normalisation is deliberately timid.** Anything the rules above do not cover
stays separate:

| Kept apart | Why |
|---|---|
| `payments` and `payment-gateway` | Routinely two systems |
| `redis-cache` and `redis-queue` | Two roles, two failure modes |
| `payments-v1` and `payments-v2` | A version is part of a name |
| `service:payments` and `database:payments` | The *type* is always part of the key |

That last row is absolute. A service and a database of the same name are never
one playbook, however their names fold together.

The trade is one-sided on purpose. A merge that should have happened costs a
playbook that does not exist yet, and you will notice. A merge that should not
have happened produces a playbook about two systems presented as one, every claim
in it wrong for whichever one you were looking at — and nothing in the system can
detect that.

### Telling it that two names are the same thing

When two components genuinely are one subject and the rules will not merge them,
say so in the team's configuration:

```yaml
component_aliases:
  checkout: cart-service
```

The alias is applied after the rules, so declaring `checkout` once covers
`checkout-api`, `prod-checkout`, and `CheckoutAPI`. Chains resolve
(`a → b`, `b → c` gives `a → c`); a cycle is treated as the typo it is and
ignored. A malformed entry costs that entry and nothing else — synthesis for the
team keeps working, with the two names left separate.

## Keeping playbooks current

A playbook is marked **stale** automatically when an investigation writes an
episode matching its key. It is marked, not deleted: the next investigation of
that failure would otherwise reach an empty shelf, and a stale playbook is still
the best available summary — it is served with its date range so it can be
discounted, and it is regenerated on the next request.

A playbook is also regenerated once it is older than `STRATEGY_MAX_AGE_DAYS`,
even if nothing invalidated it. Infrastructure is retired without producing an
episode, and a playbook nobody contradicted is not thereby a playbook anybody
confirmed.

## Correcting a playbook

If a playbook is wrong, you have three moves.

**Amend it.** Add a note, attributed to you. Amendments are shown to the agent
below the generated sections, marked as human and described as authoritative over
them, and — this is the part that matters — **they survive regeneration**. A
correction that vanished at the next regeneration would teach everyone to stop
correcting.

**Invalidate it.** Marks it stale so the next request regenerates it from the
current corpus. Amendments are kept.

**Delete it.** Removes it and its amendments. This is for a playbook whose subject
no longer exists — a retired service — rather than for one that is merely wrong.

All three are available through the console, over the same read/write API.

## Tracing a claim back to its investigations

Every playbook records the ids of the episodes it was drawn from, and records
separately which of those the anti-patterns section came from. A recommendation
that makes no sense is therefore diagnosable: read the runs behind it. The usual
finding is that four of the five were the same misdiagnosis, which is exactly the
failure mode a synthesised generalisation has and an individual episode does not.

Every retrieval is recorded in the run trace: which playbook was returned, and
whether the run's answer went on to use it. A deployment where playbooks are
returned constantly and never acted on is one where they are not helping, and
nothing else in the system would say so.

## Turning them off

| Scope | How |
|---|---|
| Deployment | `NINJASRE_MEMORY_STRATEGY=0` |
| One team | The team's strategy switch |

Off means off for both halves — nothing is generated and nothing is retrieved —
so a run with playbooks disabled is exactly a run in a deployment that does not
have the feature. That is what makes it a usable baseline.

It is a **separate** switch from the two that control episodic memory. Turning
playbooks off leaves the corpus intact and recall working, which is the
comparison worth running: not "does memory help" but "do playbooks help, given
the episodes were already there".

Episode writes still invalidate playbooks while the switch is off. Otherwise a
corpus that moved while nobody was reading would leave a stale playbook looking
current the moment the feature was switched back on.

## What a playbook is not

It is not an observation of the incident in front of you, and it is labelled to
say so every time it is shown. It is a generalisation over previous
investigations; where it disagrees with evidence gathered in the current
incident, the evidence wins. The agent is told that in the same breath as it is
handed the playbook, and the evidence entry recorded in the trace says what the
playbook *is* rather than what it concludes — so a diagnosis cannot end up citing
a summary of other incidents as though it were a measurement of this one.
