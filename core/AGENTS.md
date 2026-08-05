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

Adapters and dialects are exercised against recorded provider documents, so the
full nine-provider contract suite runs on every pull request without a
credential, a network, or a token. What a fixture cannot cover is the carry
itself — that is what `make preflight` is for.

---

Repository-wide rules — the constitution, the tier table, code style, and the
footguns — are in the root [`AGENTS.md`](../AGENTS.md). This file records only
what is specific to `core/`.
