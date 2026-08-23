# Tasks — 042 Self-Hosted Model Operation

## Phase 1 — Fixtures

- **T-001** Record transcripts for each misbehaviour: tool call as text, tool
  call in fenced JSON, out-of-schema argument, missing required argument,
  fragmented streamed call, two calls where one was expected, identical repeated
  calls, oversized result, 200 with an error body.
- **T-002** A fixture harness that replays these into the resilience layer with
  no live model.

## Phase 2 — Probe

- **T-003** Behaviour suite: structured tool calling, schema adherence,
  multi-tool turn, streaming, usable context.
- **T-004** Failing test: the probe classifies a tool-calling model, a
  non-tool-calling model, and one whose usable context is below its advertised
  figure.
- **T-005** Usable-context measurement rather than trusting the advertised value.
- **T-006** Per-model reporting; a model failing a required behaviour is
  unselectable for investigation, with the behaviour named.
- **T-007** Cache by model identity; invalidate when the model changes underneath
  a running deployment.

## Phase 3 — Resilience layer

- **T-008** Layer placed between provider adapter and runtime; assert no
  mechanism branches on a provider name.
- **T-009** Failing test: a tool call emitted as text is extracted and the repair
  is recorded as a repair.
- **T-010** Failing test: an out-of-schema argument is rejected with the
  parameter named and the capability is not called.
- **T-011** Missing required argument produces a specific correction message.
- **T-012** Bounded repairs per turn and per run.
- **T-013** Failing test: exhausting the bound degrades to a partial result whose
  failure names the model's behaviour, never an unhandled exception.
- **T-014** Structural test: no repair path can supply a value the model did not.

## Phase 4 — Loop breaking

- **T-015** Failing test: a model repeating one call is broken out of within the
  declared window, not at the iteration ceiling.
- **T-016** Windowed repetition detection with a message to the model.

## Phase 5 — Context management

- **T-017** Usable-context tracking per model.
- **T-018** Failing test: a run against a too-small context completes, with
  compaction visible in the trace.
- **T-019** Compaction strategy preserving objective, evidence and recent turns,
  recording what was dropped.
- **T-020** Schema count per turn limited by the lower of the existing ceiling
  and the model's demonstrated limit.
- **T-021** Oversized capability result truncated, truncation stated to the
  model, full result retained in the trace.

## Phase 6 — Task routing

- **T-022** Task classification: reasoning, selection, summarisation, extraction,
  embedding, classification.
- **T-023** Per-class model resolution through the config service with a default.
- **T-024** Failing test: the trace records which model produced which output.
- **T-025** Evaluation results record the model set that produced them; assert
  Article V's canonical runtime is unchanged.

## Phase 7 — Operational

- **T-026** Per-call time budget; failing with the endpoint and elapsed time
  named, degrading rather than hanging.
- **T-027** Endpoint health check distinguishable from model misbehaviour.
- **T-028** Metrics for repairs, degradations, loop breaks, compactions and
  truncations, per model.

## Phase 8 — Overhead and end-to-end

- **T-029** Failing test: a well-behaved model's run makes exactly the calls it
  would have made without this feature.
- **T-030** End-to-end investigation against a small local model on a modest
  machine, as a test in the suite.

## Definition of done

- SC-001 through SC-010 each proven by a named test.
- Every resilience behaviour tested from a fixture, with no live model required.
- `make verify` green.
