# core/ — agent runtime, pipeline, domain rules

**Tier 3.** May import: `config`, `platform`. Must never import: `capabilities`, `integrations`, `gateway`, `surfaces`.

The canonical ReAct loop and its guardrails, the six investigation stages, the
state and evidence model, the LLM provider abstraction, the capability framework
primitives, and pure domain rules.

## Conventions

- The first-party ReAct loop is the *only* runtime used for evaluation and
  benchmarks. Alternative adapters sit behind `agent/runtime_port.py`, are marked
  experimental, and never produce a published number (Article V).
- A pipeline stage is a pure `(state) -> updates` function. Its exception is
  recorded and re-raised — never swallowed.
- Every bound the loop enforces is a named constant in
  `config/constants/investigation.py` (Article II).
- No vendor LLM SDK outside `llm/` (Article VI), enforced by
  `make check-vendor-sdks`.

## Where things go

- Runtime mechanics → `agent/`. Stage logic → `pipeline/`. State shape → `state/`.
- Provider adapters → `llm/providers/`. Schema normalisation → `llm/`.
- A rule with no I/O and no dependency → `domain/`. That package is the one that
  stays testable without a single mock.

## The agent runtime

`agent/react_loop.py` is the runtime whose behaviour defines correctness.
Everything Article II names lives inside its control flow, and lives there
rather than in a wrapper because each bound needs to see the loop's state at a
specific point: the iteration ceiling and the wall clock before a turn is built,
the duplicate cache during execution, the stagnation breaker after it, and the
context budget immediately before the model call.

**The loop never raises at the caller.** A provider failure becomes a partial
result carrying the evidence gathered so far; a tool exception is already a
classified value by the time it arrives. An investigation that lost its model
after eleven observations has produced eleven observations.

**`pre_tool_use` is the only hook point that can change control flow.** It may
deny a call and it may rewrite its arguments — that is where approval gating and
masking attach. Every other point observes, and a hook that raises is recorded
on the turn and swallowed. Concentrating the control-flow influence at one point
is what keeps the security-relevant surface small enough to audit.

**A sub-agent gets a fresh `Session` and returns a `Finding`.** Not a
transcript: the parent's context is what the isolation was protecting. Depth,
fan-out, and the child's token budget are all bounded from
`config/constants/investigation.py`.

**Alternative runtimes answer `False` to `is_canonical`.** They live in
`agent/adapters/`, they document what they cannot enforce, and
`agent/guard.py` refuses to let one produce a published number. See
[`docs/experimental-runtimes.md`](../docs/experimental-runtimes.md).

## The investigation pipeline

`pipeline/lifecycle.py` runs six stages in a fixed order —
`resolve_integrations`, `intake`, `plan_evidence`, `gather_evidence`,
`diagnose`, `deliver` — over one shared `AgentState`. A pipeline assembled out
of order fails when it is built.

**A stage returns updates; it never mutates state.**
`state.apply_state_updates` is the only merge path, and slices are replaced
whole rather than edited. That is what makes "did this stage stay inside its
slice" a value somebody can compare instead of a question about who held a
reference to what.

**Slice ownership is a table, not a habit.** `pipeline/ownership.py` declares
what each stage may write, at `slice.field` granularity, and
`tests/unit/core/pipeline/test_stage_purity.py` runs every stage and fails the
build on a write outside it. Adding a field to a stage means adding it to the
table in the same change.

**Noise costs one model call.** `intake` classifies the input and, above the
threshold in `config/constants/investigation.py`, writes an outcome whose kind
halts the run — before a single capability executes. The same mechanism ends a
run whose alert duplicates one already open, and one whose team has no
capability it can run.

**A claim is validated only if the run holds its evidence.** `diagnose` checks
every citation against the evidence slice and demotes the rest. Demotes, not
deletes: what an investigation believed and could not show is often the most
useful line in the report.

**A stage exception is annotated with its stage and re-raised.** Not wrapped —
a caller that knows what to do with a provider timeout still sees one — and
never swallowed, because a stage that failed must not look like a stage that
had nothing to say. The run-end hooks fire exactly once either way.

**Who caused the run rides on `TeamContext`.** `actor_id` and `actor_kind` sit
beside the team because that is the one value every stage already holds, so
every capability a run executes is attributable without a second thing to
thread. `AgentState.to_record` serialises the whole context, which means the
trace records it and a resumed session keeps it, and neither took a stage
remembering to. They are plain strings: `core/` describes what an investigation
is and does not need to know how anybody signed in — a transport fills them
from the principal it authenticated. Empty is a real answer for a run nothing
human started, and a better one than an invented principal.

**What the pipeline needs from tier 2 and above is a port.** The catalogue
resolver, the capability ranker, the recent-incident index, and the delivery
destinations all live above `core/` in the tier table, so `pipeline/ports.py`
declares each with a neutral default and the composition root substitutes the
real one. Substituting the neutral implementation is also how an ablation is
run.

## The LLM layer

Callers see one function — `get_llm(role)` — and one client. Everything else is
reached through the returned client and is nobody else's import.

**An adapter translates a wire and nothing else.** Retry, schema normalisation,
the context guard, prompt caching, the structured-output ladder, token
accounting, and the failure-to-partial conversion live once, in `llm/client.py`.
Putting any of them in an adapter means nine copies and nine chances to differ,
which is precisely the parity the layer exists to provide.

**A tenth provider is `llm/providers/<name>.py` plus a registry row.** If it
needs a change anywhere else, that change belongs in the shared client or in a
`SchemaDialect` instead. `tests/contract/llm/test_tenth_provider.py` adds one
and drives the whole stack with it, permanently — the day the claim stops being
true, the build says so.

**A capability a provider lacks degrades explicitly.** The result carries a
`Degradation`; it never quietly behaves differently. Silent divergence is what
makes "supports nine providers" untrue in the way that costs an incident.

**Nothing reads back from client state.** Everything a retry or an error handler
consults is captured into the request when it is built. Clients are cached per
role, so a handler that mutated the client would be deciding another turn's
behaviour — see `tests/contract/llm/test_concurrent_turns.py`, which reproduces
that race deterministically and keeps a broken control case alongside it.

**Cost that is not known is `None`, never `0.0`.** A local model has no price
and a partner-hosted one prices per region; a fabricated zero produces a run
total that reads as authoritative and is wrong. The ledger reports how much of
itself it could not price.

**Parity of interface is not parity of behaviour.** A small model running on an
operator's own hardware reaches the same place a frontier model reaches by a
longer route: it emits a tool call as prose, invents a parameter, omits a
required one, or asks for the same thing four turns running. Three packages
handle that, and all three are provider-neutral by construction.

- `llm/probe/` **measures** what a model can do rather than reading it off a
  model card — tool calling, schema adherence, multi-tool turns, streaming, and
  the *usable* context, which on a quantised build is routinely a fraction of
  the advertised one. `require_usable` is the one gate that refuses a model for
  an investigation, naming the behaviour it failed. Results are cached against
  the model's identity and dropped when that identity changes.
- `llm/resilience/` sits **between the adapter and the runtime** — one
  implementation rather than nine, and every repair is a value the trace
  carries. Two properties are enforced rather than intended: exactly one
  function in the package constructs a `ToolCall` and it verifies every argument
  against the model's own output, and no module in it may name a provider. Tests
  read the package's syntax tree and its source to prove both.
- `llm/routing.py` resolves a **task class** — reasoning, capability selection,
  summarisation, extraction, embedding, classification — to a model through the
  config service, and the session records which model produced which output.
  This is not a second runtime: the same loop runs and only which endpoint
  answers a call changes (Article V), and a published number records its model
  set.

**A well-behaved model pays nothing for any of it.** Every mechanism is
triggered by a detected problem, `ModelLimits` are the shipped ceilings until
somebody probes, and the clean path is asserted by comparing a run's request
sequence with and without the layer.

Adapters and dialects are exercised against recorded provider documents, so the
full nine-provider contract suite runs on every pull request without a
credential, a network, or a token. The misbehaviours are recorded the same way,
because they are intermittent by nature and a test that asked a live model to
misbehave would pass most of the time for the wrong reason. What a fixture
cannot cover is the carry itself — that is what `make preflight` is for.

---

Repository-wide rules — the constitution, the tier table, code style, and the
footguns — are in the root [`AGENTS.md`](../AGENTS.md). This file records only
what is specific to `core/`.
