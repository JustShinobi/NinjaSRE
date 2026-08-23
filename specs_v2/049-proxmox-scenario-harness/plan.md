# Plan — 048 Proxmox Scenario Harness and Evaluation

## Technical context

| Concern | Choice |
|---|---|
| Location | `tests/synthetic/proxmox/` for the fixture-backed suite; `tests/e2e/proxmox/` for the laboratory one |
| Harness | The existing synthetic scenario harness and evaluation suite, extended — not replaced |
| Fixtures | Recorded API responses per scenario, regenerable from the laboratory cluster |
| Laboratory | A two-node cluster restored between destructive scenarios from a known snapshot |
| Scoring | A deterministic scorer over the transcript, with diagnosis and action scored separately |

## Constitution Check

| Article | Bearing | Compliance |
|---|---|---|
| VII — Learning is measured or it is not claimed | This is the measurement. | FR-016 runs the suite with and without memory and strategy, reporting both. A claim that memory helps on Proxmox scenarios becomes a number. |
| I — Evidence over assertion | Scoring the answer alone rewards guessing. | FR-006: a right answer from wrong evidence does not score as right. This is the property that distinguishes an investigation from a lucky prior. |
| V — One canonical runtime | Published numbers must come from the canonical runtime. | The suite records the runtime and the model set with every result, and the existing benchmark guard applies unchanged. |
| XII — Test-first, trace-backed | Scenarios are tests. | Each scenario's declared correct response is written before the capability that would produce it, so feature 046's actions land against a scenario that already scores them. |

## Architecture decisions

**Action is scored separately from diagnosis, and harmful is a distinct verdict.**
The existing evaluation harness scores root-cause accuracy and required evidence.
That is the right measure for an investigation system and an insufficient one for
an acting system. A run that correctly diagnoses a quorum loss and then proposes
forcing quorum has done something worse than nothing, and a scoring scheme that
records it as "diagnosis correct" is measuring the wrong half.

**Escalation is a correct action.** Several of these scenarios have no safe
automatic response — the unreachable node in a two-node cluster being the clearest
— and the correct behaviour is to report and stop. Scoring that as "no action
taken" would train the system, and the people tuning it, in exactly the wrong
direction. FR-008 makes acting there explicitly harmful.

**Insufficient evidence is a scoreable answer.** A scenario where the readings do
not support a conclusion is one where saying so is correct and a confident
diagnosis is wrong. Without this, every scoring scheme rewards confidence.

**Fixtures first, laboratory second.** The fixture-backed suite runs in CI on
every change, needs nothing, and catches regressions. The laboratory suite runs
before a release, covers what cannot be faked, and states which scenarios were
real. Requiring a cluster in CI would mean the suite runs rarely and is disabled
the first time the cluster is down.

**Fixtures fail loudly when stale.** A recorded response that no longer matches
the API produces a suite that passes while testing nothing. NFR-004 makes a
schema mismatch a failure, and FR-020 makes regeneration a routine operation
rather than an archaeology project.

**Capability coverage is asserted.** FR-015 means feature 046 cannot add an action
without a scenario that exercises it. Given that those actions write to somebody's
hypervisor, an untested one is not acceptable, and a coverage test is the only
thing that keeps that true under deadline.

## Phases

1. **Harness extension.** Action scoring alongside diagnosis scoring; the closed
   verdict set; red-herring penalties; the insufficient-evidence case;
   determinism; per-scenario and aggregate reporting that cannot hide a
   regression.
2. **Fixture capture.** Laboratory cluster; a capture mechanism producing a
   scenario's fixtures; regeneration; the staleness check.
3. **Quorum and cluster scenarios.** The six named in the specification.
4. **Storage scenarios.** The six named.
5. **Guest scenarios.** The seven named.
6. **Backup scenarios.** The five named.
7. **The gate.** CI wiring, budget, committed baselines, reviewable baseline
   changes, the capability coverage test, the seeded-regression proof.
8. **Ablation and models.** With and without memory and strategy; at least two
   models; the cannot-complete verdict distinct from the wrong-answer verdict.
9. **Laboratory suite.** Destructive scenarios, restore between them, the
   simulated-versus-real statement in the report.

## Risks

- **The laboratory cluster is a maintenance burden nobody keeps up.** Mitigated by
  making the fixture-backed suite the CI gate and the laboratory suite a release
  activity, and by NFR-002's automated restore.
- **Scoring becomes contested rather than useful.** Mitigated by declaring the
  correct response in the scenario itself, reviewed once, rather than deriving it
  at scoring time.
- **Twenty-two scenarios become slow enough to skip.** Mitigated by FR-012's
  budget and by fixtures rather than live calls, and by the smallest model that
  can complete them being a deliberate configuration choice.
