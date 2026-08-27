# Plan — 042 Self-Hosted Model Operation

## Technical context

| Concern | Choice |
|---|---|
| Tier | `core/llm/` extended; the resilience layer sits between the provider adapter and the runtime, not inside either |
| Probing | A fixed suite of small prompts exercising each required behaviour, run against a model and cached by model identity |
| Fixtures | Recorded misbehaving-model transcripts as data files, so every behaviour is unit-testable without a model |
| Routing | Task class resolved through the config service, defaulting to one model |
| Metrics | The existing observability tier |

## Constitution Check

| Article | Bearing | Compliance |
|---|---|---|
| V — One canonical runtime | Routing per task could look like a second runtime. | It is not: the same loop runs, and only which model answers a call changes. FR-019 keeps the canonical runtime canonical and requires a published number to record its model set. |
| VI — Provider neutrality | The temptation is a special case for the local provider. | NFR-003 forbids branching on a provider name. Every mechanism keys off a probed behaviour, so a frontier model that starts misbehaving is handled by the same code. |
| I — Evidence over assertion | Repair must not manufacture evidence. | NFR-001 and SC-010: extraction and rejection only. Nothing may supply a value the model did not. |
| II — Bounded autonomy | Repairs are extra model calls. | FR-009 bounds them per turn and per run, inside the existing iteration and wall-clock ceilings, which are not raised. |
| VII — Learning is measured | A published number must be attributable. | FR-019 records the model set alongside the result. |

## Architecture decisions

**A layer between adapter and runtime.** Putting repair inside the provider
adapter would make it per-provider and invisible to the trace. Putting it inside
the runtime would put model-behaviour handling in the loop, which is about
investigation. A distinct layer means one implementation, provider-neutral, and
every repair is an event the trace can carry.

**Probe, do not assume.** Advertised context windows are frequently wrong for
quantised local models, and "supports tools" in a model card frequently means
"was trained on some". The probe measures each behaviour the runtime actually
depends on and caches the answer against the model's identity, so the deployment
knows what it has rather than what it was told.

**Repairs are recorded, never silent.** A repaired call is not a clean call. If
repairs are invisible, a model that needs three attempts per turn looks the same
as one that needs none, and the operator has no way to know that changing model
would double their throughput. Every repair is counted, traced and exposed.

**Nothing is fabricated.** The line between "extract the call the model clearly
meant" and "guess the argument the model omitted" is the line between resilience
and invention. Only the first is permitted, and SC-010 asserts it structurally
rather than trusting the implementation to stay on the right side.

**Loop detection before the ceiling.** A small model repeating one call will
otherwise consume the entire iteration budget and produce a partial result whose
stated cause is "the ceiling was reached" — true and useless. Detecting the
repetition within a short window and telling the model gives it a chance to
recover, and gives the operator the real reason if it does not.

**A well-behaved model pays nothing.** NFR-004 keeps this from becoming a tax on
the frontier-model configuration: every mechanism is triggered by a detected
problem, none adds a call or a round trip on the clean path, and SC-008 asserts
it by comparing call sequences.

## Phases

1. **Fixtures.** Record transcripts of every misbehaviour: text tool calls,
   out-of-schema arguments, missing arguments, fragmented streams, doubled calls,
   loops, oversized results, 200-with-error bodies.
2. **Probe.** The behaviour suite, per-model reporting, usable-context
   measurement, unusable-model exclusion, caching and invalidation.
3. **Resilience layer.** Extraction, schema rejection with named parameters,
   correction messages, bounded repairs, degradation with a named cause.
4. **Loop breaking.** Windowed repetition detection, the message to the model,
   the bound before the iteration ceiling.
5. **Context management.** Usable-context tracking, compaction with a declared
   strategy and a trace record, schema-count limiting, result truncation stated
   to the model with the full result kept in the trace.
6. **Task routing.** Task classification, per-class model resolution through the
   config service, trace attribution, evaluation model-set recording.
7. **Operational.** Call budgets with named timeouts, endpoint health distinct
   from model misbehaviour, metrics for every mechanism.
8. **End-to-end.** A full investigation against a small local model on a modest
   machine, as a test.

## Risks

- **Repair logic becomes a parser for every model's quirks.** Mitigated by
  keeping extraction to a small set of recognised formats and rejecting the rest
  with a correction message. The model gets a chance to fix it; the system does
  not guess.
- **Compaction drops the evidence the answer needed.** Mitigated by FR-013's
  preservation rule and by recording what was dropped, so a degraded answer can
  be traced to the compaction that caused it.
- **The probe suite becomes slow enough that setup feels broken.** Mitigated by
  keeping it to small prompts and caching per model identity.
