# Feature 043 — Self-Hosted Model Operation

- **Wave:** 10 — Autonomous operation
- **Branch:** `feat/043-self-hosted-model-operation`
- **Status:** Draft
- **Depends on:** 002, 004

## Summary

Making the agent work when the model is a seven-billion-parameter model running
on the operator's own hardware, rather than a frontier model behind an API.

This matters for two reasons. It is the configuration a self-hoster will actually
choose — the running deployment is already set to a local provider — and it is
the configuration the first wave's provider layer has the least evidence for. The
provider abstraction reaches nine providers at parity for tool calling,
structured output, streaming, retry, schema normalisation and cost. Parity of
*interface* is not parity of *behaviour*: a local model will emit a tool call as
prose, invent a parameter, ignore a schema, loop on the same call, or exhaust its
context window on the third turn, and each of those currently surfaces as an
inscrutable failure halfway through an investigation.

The point is not to make a small model as good as a large one. It is to make the
system fail clearly instead of confusingly, degrade usefully instead of
collapsing, and use the small model where it is adequate.

## User scenarios

### Primary story

A homelab operator points the deployment at their own model server. Setup tells
them which of their pulled models can actually tool call, and warns that one of
them has a context window too small for an investigation with more than four
capabilities enabled.

They pick one. Investigations run. When the model emits a malformed tool call the
system repairs it if it can, tells the model precisely what was wrong if it
cannot, and gives up after a bounded number of attempts with a message naming the
model's behaviour — not a JSON parse error from three layers down.

Summarising an incident, embedding an episode and choosing which capability to
call next are all sent to the small local model. The final root-cause synthesis
can be routed elsewhere if the operator configures it, and the deployment says
which model produced which part of the answer.

### Acceptance scenarios

1. **Given** a local provider, **when** it is verified, **then** the verification
   reports, per available model: whether it tool calls, whether it honours a
   structured output schema, its context window, and whether it is usable for an
   investigation.
2. **Given** a model that emits a tool call as text rather than as a structured
   call, **when** it does, **then** the call is extracted where the format is
   recognisable and the extraction is recorded as a repair.
3. **Given** a malformed tool call that cannot be repaired, **when** it arrives,
   **then** the model is told specifically what was wrong, and retries are
   bounded.
4. **Given** repeated malformed calls beyond the bound, **when** the bound is
   reached, **then** the run degrades to a partial result naming the model's
   behaviour as the cause.
5. **Given** a model that calls the same capability with the same arguments
   repeatedly, **when** it does, **then** the repetition is detected, the model is
   told, and the run does not spend its whole iteration budget on it.
6. **Given** a context window smaller than the transcript would need, **when** the
   run approaches it, **then** the transcript is compacted by a declared strategy
   and the compaction is visible in the trace.
7. **Given** more capabilities enabled than the model can be offered at once,
   **when** a turn is prepared, **then** the set is narrowed by the existing
   selection mechanism and the narrowing is recorded.
8. **Given** a task classification, **when** a call is made, **then** the model
   used is resolved from configuration per task, and the trace records which
   model produced which output.
9. **Given** a local endpoint that is slow, **when** a call exceeds its budget,
   **then** it times out with a message naming the endpoint and the elapsed time,
   and the run degrades rather than hanging.
10. **Given** a model that returns a parameter not in the schema, **when** it
    does, **then** the argument is rejected with a specific message and the
    capability is not called with it.
11. **Given** any of these repairs or degradations, **when** they happen, **then**
    they are counted and visible, so an operator can see that their model is
    costing them attempts.

### Edge cases

- A model server with no model pulled.
- A model whose advertised context window is not its usable one.
- A model that streams tool calls in fragments.
- A model that emits two tool calls when one was expected.
- A quantised model that produces valid JSON nine times in ten.
- An endpoint that returns a 200 with an error body.
- A machine that swaps under load, making every call take minutes.
- A model changed underneath a running deployment.

## Requirements

### Functional

**Capability probing**

- **FR-001** A provider MUST be probeable for the behaviours the runtime depends
  on: structured tool calling, schema adherence, multi-tool turns, streaming, and
  usable context length.
- **FR-002** The probe MUST report per model, not per provider.
- **FR-003** The probe MUST measure usable context rather than trusting an
  advertised figure.
- **FR-004** A model failing a required behaviour MUST be reported as unusable for
  investigation, naming the behaviour, and MUST NOT be selectable for it.
- **FR-005** Probe results MUST be cached with the model's identity and
  invalidated when it changes.

**Tool-call resilience**

- **FR-006** A tool call emitted as text in a recognised format MUST be extracted,
  and the extraction MUST be recorded as a repair rather than passed off as a
  clean call.
- **FR-007** An argument not in the capability's schema MUST be rejected with a
  message naming the parameter, and the capability MUST NOT be called.
- **FR-008** A missing required argument MUST produce a specific correction
  message rather than a generic validation error.
- **FR-009** Repair attempts MUST be bounded per turn and per run.
- **FR-010** Exhausting the bound MUST degrade the run to a partial result whose
  failure names the model's behaviour.
- **FR-011** Repeated identical calls MUST be detected within a declared window,
  the model told, and the loop broken before the iteration budget is spent.

**Context management**

- **FR-012** The transcript MUST be compacted before the model's usable context is
  reached, by a declared strategy, and the compaction MUST appear in the trace.
- **FR-013** Compaction MUST preserve the objective, the evidence, and the most
  recent turns, and MUST record what it dropped.
- **FR-014** The number of capability schemas offered per turn MUST respect both
  the existing ceiling and the model's demonstrated limit, whichever is lower.
- **FR-015** A capability result too large for the context MUST be truncated with
  its truncation stated to the model, and the full result MUST remain in the
  trace.

**Task routing**

- **FR-016** Calls MUST be classified by task — reasoning, capability selection,
  summarisation, extraction, embedding, classification.
- **FR-017** A model MUST be resolvable per task class through the config service,
  falling back to a default.
- **FR-018** The trace MUST record which model produced which output.
- **FR-019** Routing MUST NOT change which runtime is canonical, and a published
  evaluation number MUST record the model set that produced it.

**Operational**

- **FR-020** A call MUST have a time budget, and exceeding it MUST fail with the
  endpoint and elapsed time named.
- **FR-021** A local endpoint's health MUST be checkable, and its failure MUST be
  distinguishable from a model behaving badly.
- **FR-022** Repairs, degradations, loop breaks, compactions and truncations MUST
  be counted per model and exposed as metrics.

### Non-functional

- **NFR-001** No repair may fabricate a value the model did not supply. Extraction
  and rejection only.
- **NFR-002** Every resilience behaviour MUST be testable against a recorded
  misbehaving-model transcript, without a live model.
- **NFR-003** These mechanisms MUST be provider-neutral; nothing may be
  conditional on a provider name.
- **NFR-004** A well-behaved model MUST incur no additional call and no measurable
  overhead from any of this.

## Success criteria

- **SC-001** The probe correctly classifies a model that tool calls, one that does
  not, and one whose usable context is below its advertised figure.
- **SC-002** A recorded transcript of a model emitting a tool call as text is
  extracted, and the repair is recorded.
- **SC-003** An out-of-schema argument is rejected, named, and never reaches a
  capability.
- **SC-004** A model looping on one call is broken out of within the declared
  window, not at the iteration ceiling.
- **SC-005** A run against a model whose context is too small completes with
  compaction visible in the trace.
- **SC-006** Exhausted repair bounds produce a partial result naming the model's
  behaviour, never an unhandled exception.
- **SC-007** Task routing sends each class to its configured model, recorded in
  the trace.
- **SC-008** A well-behaved model's run makes exactly the calls it would have made
  without this feature, asserted.
- **SC-009** An end-to-end investigation completes against a small local model on
  a modest machine.
- **SC-010** No repair path can invent an argument value, asserted structurally.

## Out of scope

- Improving a model's reasoning. This feature handles behaviour, not quality.
- Fine-tuning, or shipping a model.
- Changing the canonical runtime — Article V is untouched.
