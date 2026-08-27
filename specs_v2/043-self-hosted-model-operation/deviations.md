# Deviations — 043 Self-Hosted Model Operation

Every place the implementation differs from `plan.md` or `tasks.md`, and why.
Recorded as they happened rather than reconstructed afterwards.

---

## Where each success criterion is proven

The definition of done asks for a named test per criterion. These are they.

| Criterion | Where it is proven |
|---|---|
| SC-001 | `tests/unit/core/llm/test_model_probe.py::TestTheProbeClassifiesAModel` — one model that tool calls, one that answers instead, one whose usable context is measured at a fraction of its advertised figure |
| SC-002 | `tests/contract/llm/test_misbehaving_models.py::TestACallWrittenAsText::test_a_bare_json_call_is_extracted_and_recorded_as_a_repair`, driven from `transcripts/tool_call_as_text.json` |
| SC-003 | `…::TestArgumentsAgainstTheSchema::test_an_out_of_schema_argument_is_rejected_by_name` and `…::test_the_capability_is_never_called_with_the_rejected_argument` |
| SC-004 | `…::TestDoubledAndRepeatedCalls::test_a_model_stuck_on_one_call_is_broken_out_of_inside_the_window`, which asserts the turn it broke on *and* that it is below the window |
| SC-005 | `tests/unit/core/agent/test_small_model_context.py::TestTheRunRecordsWhatItDidToItsOwnContext::test_a_run_against_a_small_window_completes_with_compaction_in_the_trace` |
| SC-006 | `tests/contract/llm/test_small_model_operation.py::TestAModelThatCannotBeCorrected::test_the_run_degrades_with_the_behaviour_named_and_never_raises` |
| SC-007 | `tests/unit/core/llm/test_task_routing.py::TestResolvingAModelPerTask` and `…::TestTheTraceRecordsWhichModelProducedWhat::test_a_run_records_the_model_behind_every_turn` |
| SC-008 | `tests/contract/llm/test_small_model_operation.py::TestAWellBehavedModelPaysNothing::test_the_layer_makes_exactly_the_calls_the_bare_client_would` — request sequences compared for equality, not for count |
| SC-009 | `…::TestAnInvestigationAgainstASmallLocalModel::test_it_completes_and_says_what_it_found`. See §9: the model is recorded rather than live, deliberately |
| SC-010 | `tests/unit/core/llm/test_resilience.py::TestNoRepairPathCanInventAValue::test_tool_calls_are_only_built_where_their_values_are_verified` — an `ast` walk of the package, see §7 |

---

## 1. Result truncation is bounded by the *measured* window, not by a constant

**Planned.** T-021: "Oversized capability result truncated, truncation stated to
the model, full result retained in the trace." FR-015 says "too large for the
context".

**Done first, and it was wrong.** The first implementation used a flat
`MAX_TOOL_RESULT_CHARS = 8_000`, applied on every deployment.

**What caught it.** `tests/synthetic/test_ablation_value_scenario.py::
test_a_mechanism_this_corpus_does_not_exercise_reports_an_honest_zero` went red:
the synthetic corpus holds capability results above 8,000 characters, so a flat
bound changed what the model read in a scenario the ablation is supposed to leave
untouched, and a mechanism that changes nothing started reporting a number.

**Why the test was right and the implementation was wrong.** NFR-004 says a
well-behaved model must incur *no measurable overhead* from any of this. A fixed
character ceiling shortens a 200k-window model's log queries for the sake of a
mechanism that exists for seven-billion-parameter local builds — which is exactly
the tax on the frontier configuration NFR-004 forbids, and the ablation was
measuring it.

**What shipped.** `ModelLimits.tool_result_chars` — a quarter of the model's
*measured* usable context, floored at `MIN_TOOL_RESULT_CHARS`, and **zero when
nobody probed**. `truncate_for_model` takes `ceiling` with no default, deliberately:
a default is how a flat bound would come back without anybody choosing it. A
deployment that never ran the probe truncates nothing and behaves exactly as it
did before this feature existed.

`MAX_TOOL_RESULT_CHARS` was therefore never committed; `TOOL_RESULT_CONTEXT_SHARE`
and `MIN_TOOL_RESULT_CHARS` are what `config/constants/investigation.py` carries.

---

## 2. `FailureClass` gained a member, and the closed-taxonomy test was updated

**Not in the plan.** `core/llm/failures.py` gained `MODEL_BEHAVIOUR`, and
`tests/unit/core/llm/test_failures.py::test_taxonomy_is_closed` was edited to
match.

**Why.** FR-010 requires a degradation "whose failure names the model's
behaviour" and FR-021 requires an endpoint's failure to be "distinguishable from
a model behaving badly". Every one of the eight existing members describes the
*endpoint* — a rejected key, a rate limit, a context window, a model the server
does not hold. There was no way to say "the endpoint worked and the model did
not", so the two requirements could not both be met inside the existing set.

Editing a test named "the taxonomy is closed" deserves saying out loud: the
taxonomy is still closed, it is now nine, and the new member is not retryable —
repeating a request repeats the behaviour. A second test was added beside it
asserting the distinction the feature turns on, so the reason for the ninth
member is in the suite rather than only here.

---

## 3. `ProviderClient` now reads a 200 whose body is an error

**Not a task.** The spec's edge-case list includes "an endpoint that returns a
200 with an error body"; nothing in `tasks.md` says where that is handled.

**Done.** `ProviderClient._successful_result` asks the adapter to read the
document as an error **only when the parse produced no text, no tool calls and no
structured output**. Every adapter already implements `observe_error`, so this is
provider-neutral by construction and costs a response with anything in it
nothing at all.

**Why there and not in the resilience layer.** The layer works in neutral terms
and never sees the wire document; by the time a turn reaches it, an error body
has already become an empty turn, and an empty turn is indistinguishable from a
model that said nothing. The failure has to be recognised where the document
still exists.

`failures.py` also gained the `model_not_loaded` code and two text markers, because
that is what a local model server actually says and the taxonomy did not
recognise it.

---

## 4. Two new configured model roles, rather than six new ones

**Planned.** T-022/T-023: six task classes, resolved per class through the config
service.

**Done.** Six `TaskClass` members, mapped onto the config service's roles by
`TASK_ROLES`. Four of them reuse roles that already existed; two roles were added
— `selection` and `summarisation`.

**Why not six new fields.** `reasoning` *is* the investigator's call and
`classification` *is* what intake does — `core/AGENTS.md` says so of the intake
stage. Giving each of those a role of its own would hand an operator two
configuration fields that had to agree with each other, and a deployment where
they disagreed would have no defined behaviour. Two genuinely unrepresented jobs
got roles; the rest reuse what the closed set already declared.

`ModelsConfig` gained `selection_for(role)` alongside `for_role(role)`. The
difference is the whole of what routing needs: `for_role` returns the default pair
for an unconfigured role, and the router has to be able to tell a role somebody
chose from one that fell through — a default that looks like a choice is how a
deployment comes to believe it split its models when it did not.

---

## 5. A ninth metric family, and the dashboard row that goes with it

**Planned.** T-028: "Metrics for repairs, degradations, loop breaks, compactions
and truncations, per model."

**Done.** `MetricFamily.MODEL` with five counters, plus the Grafana row and five
panels in `deploy/dashboards/grafana-ninjasre.json`, plus the two declaration
tests and the "everything appears when enabled" driver.

**Why a new family rather than a label on `guardrail.actions`.** FR-022 requires
these per *model*, and `guardrail.actions` is labelled `(rule, action)`. Adding a
model dimension to it would have changed the cardinality of an existing family
for every deployment. More to the point, every one of the eight existing families
describes the platform; this one describes the weights behind it, which on a
self-hosted deployment is the thing an operator can actually change.

The `kind` label was added to the permitted-dimensions list in
`test_no_instrument_declares_an_unbounded_dimension`, whose docstring says
"adding to it is the review this test forces". The review: every value is a
member of `RepairKind` or one of two named degradation causes, so it cannot grow
with traffic the way a capability name or a team could.

---

## 6. Structure — modules the plan's phases imply and do not name

`plan.md` names one location (`core/llm/` extended). What that became:

| Module | Why |
|---|---|
| `core/llm/probe/` | Phase 2 in full: `behaviours.py` (what is measured and which are required), `report.py` (the result, `ModelLimits`, and the one gate that refuses an unusable model), `suite.py` (the measurements), `cache.py` (identity-keyed, invalidated when the model changes). One module would have been four concerns in one file. |
| `core/llm/resilience/` | Phases 3 and 4: `extraction.py`, `arguments.py`, `bounds.py`, `loops.py`, `client.py`, `recorder.py`. The split is what makes the no-invention guarantee checkable — see §7. |
| `core/llm/routing.py` | Phase 6. |
| `core/llm/health.py` | FR-021. Separate from `preflight.py` and `verification.py` because those answer "is this provider configured" and "does this model meet the contract"; this answers "is the endpoint answering *right now*", which is a question asked during an incident rather than at setup. |
| `core/agent/result_truncation.py` | FR-015. In `core/agent/` rather than `core/llm/` because what it bounds is a *capability* result, and the seam it acts on — the tool result entering the transcript while the evidence entry keeps the whole thing — is the runtime's. |
| `platform/observability/metrics/model_behaviour.py` | The recorder and the turn reader, beside `cost.py`, which has the same shape for the same reason. |
| `core/agent/hooks/builtin/model_behaviour.py` | Wires the counters to a run. Deliberately **not** a default hook: it needs a metric registry, and a registry is a deployment's to build. |
| `config/prompts/resilience.py` | Every correction sent back to the model. `AGENTS.md` requires prompts to live in `config/prompts/`, and these are prompts. |
| `tests/support/misbehaviour/` | T-001 and T-002: nine transcripts as data files plus the replay harness. |

---

## 7. SC-010 is asserted by reading the package's syntax tree

**Planned.** T-014: "Structural test: no repair path can supply a value the model
did not."

**Done.** Three things together, because none of them is sufficient alone.

1. `_verified_call` is the only function in `core/llm/resilience/` that
   constructs a `ToolCall`, and it passes every argument through
   `verified_arguments`, which raises unless each scalar's JSON text appears
   verbatim in the model's own output.
2. `test_tool_calls_are_only_built_where_their_values_are_verified` walks every
   module in the package with `ast` and asserts the set of `ToolCall(...)`
   construction sites is exactly `{SOLE_CONSTRUCTION_SITE}`.
3. `ArgumentVerdict.call` carries the model's call **unchanged**. A verdict that
   returned a *fixed* call would be the one place invention could enter, and
   there is nothing that could do the fixing without choosing a value.

A behavioural test proves the paths it exercised. This proves there is no other
path, and it keeps proving it after somebody adds a format to the recognised set.

NFR-003 is asserted the same way: `test_no_module_in_the_layer_names_a_provider`
reads the package's source and fails on any of the nine provider identifiers
appearing in it.

---

## 8. Compaction keeps a shorter tail when it is the measured window that fired

**Not in the plan.** `TRANSCRIPT_COMPACTION_TIGHT_KEEP_MESSAGES` was added.

**Why.** The existing compaction keeps the last twelve messages and triggers at
forty. Both numbers assume the message count is the trigger. Driven by a measured
context instead, the trigger fires on a *short* transcript carrying one enormous
result — and keeping twelve of eleven messages leaves nothing in the middle to
summarise, so compaction ran, removed nothing, and the run stayed over its window.

The fix is one constant and two lines: when the measured window is what fired,
keep half the usual tail, bounded so at least one message is summarisable. The
message-count path is arithmetically unchanged — at forty messages
`min(12, len - 2)` is still 12 — which is why no existing compaction test moved.

---

## 9. SC-009's "modest machine" is a recorded model, not a live one

**Planned.** T-030: "End-to-end investigation against a small local model on a
modest machine, as a test in the suite."

**Done.** `tests/contract/llm/test_small_model_operation.py` drives a full
investigation through the canonical ReAct loop against a scripted
seven-billion-parameter build that misbehaves in the ways the recorded
transcripts hold — narrating a call, inventing a parameter, repeating itself —
and asserts it completes, answers, and leaves a trace saying what it cost.

**What is genuinely different from the task as written.** No live model runs, and
no path in the gate could start one.

**Why.** These misbehaviours are intermittent by nature — a quantised build
produces valid JSON nine times in ten — so a test that asked a real model to
misbehave would pass most of the time for the wrong reason, and fail
occasionally for no reason anybody could reproduce. It would also need a running
model server, which `AGENTS.md` is explicit belongs in `make preflight` and the
chaos suites rather than in the gate, for the same reason feature 019's
deviations record about SC-001: a gate that needs infrastructure is a gate people
learn to skip.

**What this means for the definition of done.** SC-009 is proven for everything a
recording can carry — the loop, the layer, the bounds, the degradation, the trace
— and not for the carry itself against a real endpoint. That last leg is one
`make preflight` run per deployment. It is a real gap and it is deliberate, and it
is the same gap the provider contract suite has documented since feature 004.

---

## 10. The probe's schema limit is demonstrated, and it costs calls

FR-014 says the schema count must respect "the model's demonstrated limit". The
probe demonstrates it with a doubling ladder — 2, 4, 8, … up to the shipped
ceiling — stopping at the first rung where the model stops emitting a structured
call. Six calls at the shipped ceiling for a model with no limit, two for a model
with a low one.

The alternative was deriving the limit from the context window, which would have
been a *calculation* rather than a demonstration, and the whole point of the
probe is that calculations from advertised figures are what this feature exists
to stop trusting.

`plan.md`'s risk table warns the probe could become slow enough that setup feels
broken. The whole suite is about twenty small calls and its result is cached
against the model's identity, so an operator pays once per model.

---

## 11. `ReActLoop` narrowing is a backstop, not the narrowing mechanism

FR-014 and scenario 7 say the schema set is "narrowed by the existing selection
mechanism". Selection lives in `capabilities/`, which is tier 2 and which `core/`
must never import, so the loop cannot ask it for fewer.

What shipped: the composition root asks selection for `limits.max_tool_schemas`
capabilities, and the loop enforces the same bound as a backstop, dropping from
the end of the order it was constructed with — which *is* selection's ranking —
and recording a `SCHEMAS_NARROWED` guardrail action naming what was dropped and
why. A turn that silently carried fewer capabilities than the run was configured
with would explain nothing.

---

## Not deviations, recorded because they look like they might be

- **The resilience layer is a wrapper, not a change to `ProviderClient`.**
  `plan.md` says "a layer between adapter and runtime". `ResilientClient`
  satisfies `LLMClient`, so wrapping is the whole integration and the loop that
  was given a provider client is given this instead. Nothing else changes, which
  is what makes SC-008's "exactly the calls it would have made" comparable at all.
- **Repetition is detected per session, keyed off request metadata.** A client is
  cached per role and shared by every run in the process, so a detector with one
  window would let two investigations making the same call add up to a loop in
  neither. The session identifier is already on `InvokeRequest.metadata`; nothing
  new was threaded through.
- **`StreamEvent` gained `tool_call_fragment`.** The neutral vocabulary could not
  represent a streamed argument delta, so reassembly would have had to live in
  every adapter that streams — nine copies of the thing the layer exists to have
  one of.
- **`Session` gained `attributions` rather than `Turn` gaining a task field.**
  Not every model call is a turn: a summary, an embedding and a classification
  each produce an output the run is accountable for and none of them appears in
  the transcript. FR-018 is about all of them.
- **T-012's per-run bound is enforced on the client, not the session.** The layer
  holds one `RepairBudget` for its lifetime, which is the run's, because the loop
  holds the client for exactly one run. A budget on the session would have had to
  be threaded through `InvokeRequest`, and the request is deliberately a value
  with nothing mutable read back out of it.
