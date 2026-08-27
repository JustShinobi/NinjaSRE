# Deviations — 029 Chaos and End-to-End Suites

Recorded per task instruction. Not committed (this whole directory is
gitignored, same as `spec.md`/`plan.md`/`tasks.md`).

## 1. What "proven" means for a suite that needs infrastructure

The single largest judgement in this feature, so it is stated first and applies
to every item below.

Nothing in this repository can create a Kubernetes cluster or an AWS account
inside `make verify`, and a feature that only claimed its success criteria
against infrastructure nobody has would ship untested infrastructure code —
which is the state infrastructure code is usually in and the reason it breaks
the first time it is needed. So the framework is written against **ports** —
`Cluster`, `SymptomSource`, `CommandRunner`, `Provisioner`, `Investigator` — and
every success criterion is asserted against recorded implementations of those
ports, driven through the **real** runner, the **real** validity gate, the
**real** cleanup path, and feature 028's **real** scorer.

Concretely, per criterion:

| SC | How it is asserted | What is not asserted |
|---|---|---|
| SC-001 | All fourteen experiments run the full cycle through `run_suite` against `RecordedCluster` — injected, alerted (a real `RawAlert` that `normalise()` accepts), investigated, scored on all five axes, cleaned up, cluster verified empty | That Chaos Mesh accepts these fourteen manifests. `make chaos-run` is the entry point that does; the CI job creates a cluster and exercises preflight and the catalogue against it |
| SC-002 | Three real exits — exception, `KeyboardInterrupt`, and a genuine `os.kill(SIGTERM)` — each leave `active_faults() == ()`. Plus the `SIGKILL` case, covered by the label sweep | — |
| SC-003 | All five faults through `run_faults`, each scored, each flag verified back at its off variant afterwards, including when the investigation raises | That flagd propagates the patch — which is exactly what the validity probe is for |
| SC-004 | Interrupted run (real `SIGTERM`) leaves `leaked(...) == ()`; the reaper destroys an attributable orphan, keeps a live run's and a fresh one's, and refuses to touch an unattributable resource | An actual AWS tag sweep |
| SC-005 | An experiment whose probe never sees its symptom produces `experiment_failure` and **not** `agent_failure`, and the report says so in words | — |
| SC-006 | Genuinely end to end and with no doubles in the path: a live investigation through `PipelineInvestigator` → real capability → real client → real credential proxy → recorded vendor, reaching a wrong conclusion; captured; the captured directory loaded by the **ordinary** `load_scenario` and run by the **ordinary** `run_scenario` offline; it fails on the same axis | — |
| SC-007 | `cluster_availability` returns a message naming what is missing and the command that fixes it; `tests/chaos/test_chaos_suite.py` and `tests/e2e/test_e2e_suites.py` skip on it in every `make verify` on a machine with no cluster | — |
| SC-008 | Every scenario declares a bound and its priced resources; a 45-minute run of all six is inside both the per-scenario bounds and the suite ceiling; a stack left up for a day breaks its bound and the report says `OVER` | Real invoiced cost |

The seam is one object in each case. Point `PipelineInvestigator`'s transport at
a live proxy instead of the harness's in-process one and the same code runs
against production telemetry; that is asserted directly in
`tests/unit/harness/test_investigator.py`, which drives the whole real client
path and checks the vendor boundary was reached.

## 2. `tests/e2e/` reuses `tests/chaos/framework/`

The plan's project structure puts the cluster port, the validity probe, and the
cleanup ledger under `tests/chaos/framework/`, and puts the otel-demo suite
under `tests/e2e/`. The demo suite needs all three, unchanged: "did the fault
actually take effect" is the same question whether a kernel or a feature flag
raised it.

`tests/e2e/otel_demo/` therefore imports `tests.chaos.framework` rather than
duplicating it. A second copy would be a second place for validity to be decided
differently, which is the one thing this feature cannot afford — the whole value
of the validity gate is that one answer separates an agent failure from an
experiment failure everywhere.

Two things moved up rather than being duplicated, for the same reason:

- **`tests/support/interruption.py`** — the signal-safe deferred-cleanup
  primitive, shared by the chaos ledger and the cloud teardown.
- **`tests/support/commands.py`** — the external-command port and its recording
  double, shared by the cluster, the demo installer, and the provisioner.

## 3. Real-run scoring lives in `tests/harness/`, not in either suite

The plan's Phase 5 says "feature 028's axes applied to real runs" and does not
say where that code goes. It went into `tests/harness/realruns.py` and
`tests/harness/investigator.py`, beside the scorer it extends, rather than into
either suite.

The reason is the one the plan itself gives: the axes must be *unchanged*. Had
the chaos suite owned a copy of the scoring adapter, the demo and cloud suites
would each have grown their own, and three suites scoring "the same" way is how
two numbers that look comparable stop being. As it stands there is one
`score_real_run`, one `RealRunReport`, and one `RunValidity` — and
`tests/chaos/framework/validity.py` re-exports that enum rather than declaring a
parallel one.

## 4. `expected.yml` carries more than the plan's example

The plan's illustrative `expected.yml` has six fields. The shipped one adds
`failure_mode`, `severity`, `difficulty`, `integrations`, `available_evidence`,
`forbidden_categories`, `required_evidence_sources`, `optimal_trajectory`, and
`max_investigation_loops`.

Not scope creep: **FR-016 requires scoring on feature 028's five axes**, and
four of those axes have nothing to read without these fields. An expectation
carrying only a category and a keyword list would be scored on accuracy alone,
and the run would report four axes as "not asserted" — which is exactly the
flattering, meaningless number `AxisScore.applicable` exists to prevent.

Every added field is validated against the same controlled vocabularies the
scenario loader uses (`FAILURE_MODES`, `SEVERITIES`, the live root-cause
taxonomy, the live capability catalogue), so a renamed capability breaks the
build in the change that renamed it.

## 5. Captured scenarios are drafted at difficulty 1, not 4

`CAPTURE_DEFAULT_DIFFICULTY` was originally 4 on the reasoning that a scenario
which came from a miss is a hard one. The corpus loader rejected it, correctly:
`SCENARIO_ADVERSARIAL_FROM_DIFFICULTY` means every level at or above 2 asserts
**at least one declared confounder**, and a run against real infrastructure has
noise nobody planted and therefore none to declare.

Writing 4 would have been asserting a confounder that does not exist. The
constant is now 1, the reasoning is written where the constant is, and the
capture's review notes tell the reviewer to raise it once they can name what
misled the agent. This is a case where an existing gate caught a real defect in
new code and the new code was changed rather than the gate.

## 6. The suites take an investigator; they do not compose one

`make chaos-run`, `make e2e-demo`, and `make e2e-cloud` all require
`INVESTIGATOR=module:factory`. The suite does not build an investigation for
itself.

Composing one needs a provider and the operator's own credential proxy, and this
repository's standing position on that seam is feature 030's — the same
reasoning already recorded in `specs/020`'s deviations §1, and the same shape
`surfaces/cli/client.py`'s `LocalServices` and `gateway/http/services.py`'s
`InvestigationRunner` already have. A suite that guessed at a composition would
run against whatever ambient configuration happened to be present, which is
precisely the failure `AGENTS.md`'s credential rules exist to prevent.

`PipelineInvestigator` is the composition to build on and is complete: it takes
a model client and a proxy transport and nothing else, and there is no parameter
a credential could arrive through.

## 7. Declarative cloud modules are not written

`tests/e2e/cloud/provisioning/` drives `terraform -chdir=<modules>/<scenario>`,
and the six modules under `modules/` are not in this change. Writing six real
IaC modules that provision EKS, EC2, CloudWatch, Lambda, ECS, and RDS is a
substantial body of work that cannot be exercised, reviewed, or corrected
without an account to run it against — and an unrun module is worse than an
absent one, because it looks finished.

What *is* complete and asserted is everything the feature's success criteria are
about: the tagging, the per-run workspace isolation, the deferred teardown on
every exit including the signalled one, the tag-sweep reaper with its
attribution rules, the cost bounds and their reporting, and the scenario
declarations that name each module and price its resources. Adding a module is
adding a directory; nothing in the suite changes.

## 8. `docs/provenance-map.md` and `make check-provenance` (T062) not done

Two reasons, both structural:

- Per `CLAUDE.md`, `docs/provenance-map.md` is gitignored and never linked from
  a committed file. Editing the local copy has no effect on what ships. Same
  disposition as `specs/020`'s deviations §6.
- There is no `check-provenance` target in the `Makefile` and never has been;
  `make verify`'s guard list does not include one. Adding a guard over an
  uncommitted file would violate the rule that a committed file must not depend
  on an uncommitted one.

No provenance header, comment, or upstream project name appears anywhere in this
change.

## 9. Test-first sequencing

Followed as the plan asks for Phase 1: `tests/unit/chaos/test_cleanup_and_skip.py`
(T001 and T002) was written first and confirmed red — `ModuleNotFoundError: No
module named 'tests.chaos'` — before any framework module existed, then made
green.

From Phase 2 on, the same adaptation `specs/020`'s deviations §7 records: each
module's tests were written immediately before that module and run red for a
real reason. Writing the whole of Phases 2–7's tests up front would have
produced sixty assertions that could only fail on `ImportError`, which proves
nothing about the behaviour they describe.

Two tests were red for a genuine behavioural reason rather than a missing
module, and both found real defects: the captured-scenario difficulty (§5), and
the captured alert document, which was being written as a bare payload and was
rejected by the fixture validator that every scenario passes through.

## 10. Two dead API surfaces removed during review

- `ExperimentRefused` was declared and never raised — refusal is a *field* on
  `ExperimentOutcome`, not an exception, because a refused experiment is a
  result the report has to carry beside the scored ones.
- `run_experiment` took a `lock_root` it never used. The lock is taken once for
  the whole suite in `run_suite`, deliberately: a per-experiment lock would let
  a second suite interleave between two experiments and inject into a cluster
  this one is about to preflight.

`CloudOutcome.destroyed` was also dead — always empty, because the deferred
teardown ran outside the frame that built the outcome. Fixed properly rather
than deleted: `deferred_teardown` now yields a `Teardown` record it appends to,
so "what teardown actually removed" is reported, and a run whose teardown never
ran is distinguishable from one that had nothing to remove.

## 11. `make verify` result

Green. **8803 passed, 20 skipped** — 79 tests added by this feature, of which 5
are the infrastructure-dependent suites skipping cleanly with their reasons,
which is SC-007 being demonstrated on every run rather than asserted once.

The task brief quoted a baseline of "4223 passed, 15 skipped". The pass count
was stale — a clean tree at this commit collects 8744 tests, verified by
stashing this change and re-collecting. The skip count matches exactly: 15
before, 20 after, and the five added are this feature's.
