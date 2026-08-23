# Feature 028 — Evaluation and Ablation

- **Wave:** 7 — Evaluation
- **Branch:** `feat/028-evaluation-and-ablation`
- **Status:** Draft
- **Depends on:** 010, 011, 012, 016, 027
- **ADRs:** [0003](../../docs/adr/0003-single-canonical-runtime.md), [0008](../../docs/adr/0008-full-provider-parity.md)

## Summary

The feature that makes the product's central claim checkable. Multi-axis scoring
of every scenario run, golden-trajectory comparison, CI regression gates, and —
most importantly — an **ablation harness** that isolates the contribution of
episodic memory, strategy synthesis, and topology by running the same corpus with
each mechanism disabled.

Without this, "it learns" is an assertion. With it, it is a number.

## User scenarios

### Primary story

Before a release, the maintainer runs the ablation report. It shows that on the
level-3 scenario set, episodic memory improves root-cause accuracy from 61% to
74% and reduces median iterations from 9 to 6; strategy synthesis adds a further 4
points; topology adds 2 on scenarios involving dependency failures and nothing
elsewhere. Those numbers go in the release notes.

### Acceptance scenarios

1. **Given** a scenario run, **when** it is scored, **then** it produces a result
   on each axis — accuracy, evidence, adversarial resistance, trajectory
   efficiency, and cost — not a single pass or fail.
2. **Given** a golden trajectory, **when** the agent's trajectory is compared,
   **then** the configured matching mode is applied and the distance is reported.
3. **Given** an answer key with `forbidden_categories`, **when** the agent's
   category matches one, **then** the scenario fails regardless of keyword matches.
4. **Given** `ruling_out_keywords`, **when** they are absent, **then** the
   adversarial axis fails even if the root cause was correct.
5. **Given** an ablation configuration, **when** the suite runs, **then** the named
   mechanism is disabled and everything else is identical.
6. **Given** two suite runs, **when** they are compared, **then** a per-scenario
   and per-axis delta report is produced.
7. **Given** a regression beyond the configured tolerance, **when** CI runs,
   **then** the build fails naming the scenarios and axes that regressed.
8. **Given** variance across attempts, **when** results are reported, **then**
   variance is reported alongside the mean, so a single lucky run is not mistaken
   for improvement.
9. **Given** a cross-model run, **when** it completes, **then** a comparison table
   is produced from the canonical runtime only.

### Edge cases

- A scenario whose score improves on one axis and regresses on another.
- An ablation that makes results better, indicating the mechanism is harmful.
- A model whose non-determinism produces high variance.
- A trajectory that reaches the right answer by an entirely different route.
- A regression caused by a scenario fixture change rather than an agent change.
- Cost regression with no accuracy change.

## Requirements

### Functional

**Scoring axes**

- **FR-001** Scoring MUST produce independent results on five axes: accuracy,
  evidence, adversarial resistance, trajectory efficiency, and cost.
- **FR-002** **Accuracy**: `root_cause_category` matches the answer key or an
  equivalent; all `required_keywords` present; no `forbidden_categories` matched;
  no `forbidden_keywords` present.
- **FR-003** **Evidence**: every source in `required_evidence_sources` was
  actually collected, and every validated claim references a real evidence entry.
- **FR-004** **Adversarial resistance**: all `ruling_out_keywords` present,
  demonstrating the planted confounders were explicitly dismissed.
- **FR-005** **Trajectory efficiency**: distance from `golden_trajectory` under the
  configured matching mode, plus extra actions, redundant calls, and loop count
  against `max_investigation_loops`.
- **FR-006** **Cost**: tokens and wall-clock, reported and gated separately from
  correctness.
- **FR-007** A scenario passes only when every configured axis passes; partial
  results MUST be reported rather than collapsed.

**Trajectory matching**

- **FR-008** Three matching modes MUST be supported: `strict` (exact order),
  `lcs` (longest common subsequence with a maximum edit distance), and `set`
  (membership regardless of order).
- **FR-009** Parallel tool batches MUST be treated as an unordered set within their
  position.
- **FR-010** Redundant calls MUST be counted separately from extra calls, since
  they indicate different problems.
- **FR-011** A trajectory reaching the correct answer by a different valid route
  MUST be reported as a trajectory deviation, not an accuracy failure.

**Ablation**

- **FR-012** The harness MUST support disabling, independently: episodic memory
  read, strategy synthesis, topology, knowledge base, masking, sub-agents, seed
  calls, and capability planning.
- **FR-013** An ablation run MUST be identical to the baseline in every other
  respect.
- **FR-014** The harness MUST produce a report quantifying each mechanism's
  contribution per axis and per difficulty level.
- **FR-015** A mechanism whose ablation **improves** results MUST be flagged
  prominently — it is harming the agent.
- **FR-016** Ablation configurations MUST be declarative and reproducible.

**Comparison and gating**

- **FR-017** Two suite runs MUST be comparable, producing a per-scenario, per-axis
  delta.
- **FR-018** CI MUST gate on regression beyond a configured tolerance, naming the
  scenarios and axes.
- **FR-019** Variance across attempts MUST be reported with the mean, and gating
  MUST account for it so noise does not fail builds.
- **FR-020** Cost regression MUST be gated separately from correctness regression.
- **FR-021** A baseline MUST be storable and referenceable, so a change is measured
  against a known point.

**Benchmarks**

- **FR-022** An external benchmark adapter MUST be supported, with Cloud-OpsBench
  as the reference implementation.
- **FR-023** Cross-model comparison MUST run the corpus across providers and
  produce a table.
- **FR-024** Published benchmark numbers MUST come from the canonical runtime only;
  an attempt to benchmark a non-canonical runtime MUST fail.
- **FR-025** Benchmark results MUST be exportable for the README and release notes.

### Key entities

| Entity | Description |
|---|---|
| **AxisScore** | The result on one scoring axis with its detail |
| **ScenarioScore** | Composite of all axes for one attempt |
| **SuiteResult** | Aggregate across scenarios with variance |
| **GoldenTrajectory** | The expected action sequence with matching configuration |
| **AblationConfig** | A declarative set of disabled mechanisms |
| **AblationReport** | Per-mechanism contribution by axis and difficulty |
| **Baseline** | A stored suite result used as a comparison point |
| **RegressionGate** | The tolerance policy CI enforces |

## Success criteria

- **SC-001** Every scenario produces five independent axis scores.
- **SC-002** A deliberately-introduced accuracy regression fails the CI gate with
  the scenarios and axis named.
- **SC-003** An ablation report quantifies memory, strategy, and topology
  contributions per axis and per difficulty level.
- **SC-004** Disabling a mechanism produces a run identical to baseline in every
  other respect — verified by comparing traces.
- **SC-005** Variance-aware gating does not fail on noise — verified by running an
  unchanged codebase N times.
- **SC-006** A cost regression with no accuracy change is caught by the cost gate.
- **SC-007** An attempt to produce a benchmark number on a non-canonical runtime
  fails.
- **SC-008** Cross-model comparison produces a table covering all nine providers.
- **SC-009** A trajectory reaching the right answer by a different route is
  reported as a deviation, not an accuracy failure.

## Out of scope

- Scenario fixtures and the runner (feature 027)
- Chaos and cloud e2e (feature 029)
- The mechanisms being ablated (features 010–012)

## Clarifications

| Question | Resolution |
|---|---|
| Why five axes rather than a pass/fail? | Because they fail independently and mean different things. An agent that gets the right answer after twenty redundant calls has an efficiency problem, not an accuracy problem, and collapsing them hides which one you have. |
| What if ablation shows a mechanism hurts? | FR-015 flags it prominently, and that is the point. Discovering that memory degrades level-4 scenarios is exactly the kind of finding the constitution's Article VII exists to surface. The response is to fix or disable it, not to hide the number. |
| How is noise distinguished from regression? | N attempts with variance reported (FR-019), and gating that accounts for it (SC-005). A single-run comparison is not treated as evidence. |
| Why forbid benchmarking a non-canonical runtime? | ADR 0003. A number produced under different guardrails is not comparable to one produced under the canonical ones, and publishing both invites exactly that comparison. |
