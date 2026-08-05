# Experimental runtimes

NinjaSRE has one canonical runtime — the first-party ReAct loop in
`core/agent/react_loop.py` — and it is the only one whose results are ever
published. This document says what an alternative runtime is for, what it costs
you, and what stops it from quietly becoming the default.

The decision behind it is [ADR 0003](adr/0003-single-canonical-runtime.md).

## Why an alternative exists at all

A team already running on a vendor's agent SDK should be able to point NinjaSRE
at their existing setup while they migrate, rather than choosing between the two
on day one. The runtime port was defined in Wave 0 for exactly this: so an
adapter could exist without anything above it depending on which runtime is
underneath.

That is the whole benefit. Everything below is the price.

## What an alternative runtime cannot enforce

In an alternative runtime the loop belongs to somebody else. Every guardrail
that is a property of loop control flow has no seam to be inserted into, so it
is simply absent:

| Guardrail | What its absence means |
|---|---|
| Iteration ceiling | The run stops when the vendor decides. Nothing here notices, let alone prevents, a run that exceeds the bound. |
| Stagnation breaker | There is no point at which "this iteration produced no new evidence" can be evaluated, so a run can spin on the same call. |
| Duplicate tool-call cache | Repeated calls re-execute, and the model is never told it already holds the result. |
| Context budget | Eviction happens inside the vendor's session by its own policy. No eviction is recorded, so a missing observation cannot be explained afterwards. |
| `pre_tool_use` denial | **Approval gating cannot run.** There is no point between the model asking and the tool running. Article III is unenforceable. |
| `pre_tool_use` rewriting | **Argument masking cannot run.** Article IV is unenforceable. |
| Per-iteration trace records | Turn records are reconstructed from what the SDK reports rather than observed as they happen, so the trace is not replayable to the standard SC-008 sets. |

The last two are the serious ones, and they are why selecting an alternative
runtime is an environment variable rather than a configuration file entry: it is
a decision somebody should have to make deliberately, per process, with the
consequence visible in the command they typed.

The list is also available as data — `ClaudeAgentSdkRuntime.unenforceable_guardrails`
— so a console or a CLI can show it to an operator before they select it.

## Why no benchmark may use one

The product's differentiator is that trajectory quality is measured against
golden trajectories and a regression fails CI. That comparison is only valid if
every scenario ran the same way. Split the suite across two runtimes and every
number becomes ambiguous: a score change could be the model, the prompt, the
memory, or the runtime, and nobody can tell which.

So `core.agent.guard.require_canonical_runtime` sits in front of every
evaluation and benchmark entry point and raises `NonCanonicalRuntimeError` if
the active runtime declares itself experimental. It reads the runtime's
`is_canonical` property rather than matching a class name — a name check would
pass the day somebody subclassed the adapter, and it would pass silently.

## Selecting one

```bash
NINJASRE_RUNTIME=claude_sdk ninjasre investigate ...
```

Unset for the canonical runtime, which is the default and what every unset
process gets. An unrecognised value reads as the default rather than failing, so
a typo cannot silently select something else.

## The dependency is optional

The vendor package is not a dependency of NinjaSRE and is not installed by
default. Provider neutrality means a deployment where nothing leaves the
operator's infrastructure installs no vendor packages and is still fully
functional; an adapter that forced one into the dependency tree would break that
for everyone in order to serve the few teams that want it.

Without the extra installed, the runtime reports its own unavailability as a
failed result rather than raising — a caller that selected it learns that in the
same shape every other failure arrives in.

## Adding another adapter

Put it in `core/agent/adapters/`, satisfy `core.agent.runtime_port.Runtime`
structurally (never by inheritance), answer `False` to `is_canonical`, and list
what it cannot enforce both in the module docstring and as a
`UNENFORCEABLE_GUARDRAILS` tuple. `tests/architecture/test_canonical_runtime.py`
asserts the second and third of those for every adapter in the package, so an
adapter that forgets fails the build rather than the next benchmark.
