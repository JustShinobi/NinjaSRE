# Plan — 038 Continuous Observation and Incident Lifecycle

## Technical context

| Concern | Choice |
|---|---|
| Tier | `platform/observation/` and `platform/incidents/` — tier 3 |
| Storage | Postgres: a bounded signal table with a retention sweep, and incident tables beside the run tables |
| Concurrency | The scheduler's lease-based claiming, unchanged |
| Detector definitions | Configuration through the hierarchical config service, validated against a schema |
| Dispatch | The existing run recorder and pipeline protocol, exactly as the scheduler uses them |
| Escalation | The existing `platform/notifications/escalation.py` registry |

## Constitution Check

| Article | Bearing | Compliance |
|---|---|---|
| I — Evidence over assertion | An incident asserts something is wrong. | Every incident records the signal values and the rule that produced it. An incident with no evidence cannot be constructed. |
| II — Bounded autonomy | The system now starts work on its own. | FR-024 rate-limits dispatch per team and globally; FR-021 provides a global pause; every run remains under the runtime's existing iteration and wall-clock ceilings. |
| III — Read-only by default | Detection reads; it never writes to infrastructure. | Detectors call read-only capabilities only, enforced by the capability side-effect level, asserted by test. |
| VIII — Layered architecture | Two new platform modules. | They depend on `platform/estate/`, `platform/persistence/`, `platform/notifications/` and `config/`. The pipeline is a protocol a composition root satisfies, exactly as the scheduler does it. |
| XI — Single datastore | Time-series data invites a time-series database. | Refused. Signals live in Postgres, bounded by retention. If that proves insufficient the answer is a narrower retention, not a second datastore. |
| XII — Test-first | Replayability is what makes detectors testable. | NFR-005 makes evaluation pure with respect to its inputs, so SC-009 is a unit test rather than an integration one. |

## Architecture decisions

**One incident lifecycle, whatever raised it.** A webhook alert and a detected
condition become the same object through the same path. The alternative — an
`Alert` from webhooks and an `Incident` from detectors — means every downstream
component handles two cases, and the second one is the one nobody tests. The
existing webhook routes are rewired to raise incidents rather than to start runs
directly.

**Detection reads only.** A detector may call nothing with a side effect. This is
enforced at registration against the capability catalogue's declared side-effect
level, not by convention, because a detector that can act is an autonomous
actuator with none of feature 040's controls in front of it.

**Absence is a condition, not a gap.** "The signal stopped arriving" is the most
important detector in any homelab and the one most systems cannot express,
because they only evaluate the samples they have. Making absence a first-class
condition kind means a node that stopped answering produces an incident rather
than a flat line nobody looks at.

**Suppression is recorded, never silent.** A firing inside a maintenance window
is written down as suppressed. An operator asking "why did nothing happen" must
get an answer, and a suppression rule that is too broad is invisible unless the
suppressions it caused are countable.

**A failing detector is an incident about the detector.** The worst failure mode
of any monitoring system is looking healthy because it stopped looking. FR-011
makes evaluation failure an attention item in its own right.

**Dispatch is rate-limited before it is useful.** A correlated storm — a node
going down takes twenty guests with it — must not become twenty investigations.
Correlation handles most of it; the rate limit is what handles the rest, and it
exists from the first commit rather than after the first storm.

## Phases

1. **Signals.** The signal model, the poller source, the estate-transition
   source, the external-query source, retention, and the absence representation.
2. **Detector model.** Declaration schema, config-service resolution, the four
   condition kinds, hysteresis, enable and disable.
3. **Evaluation.** The tick, lease-based claiming, idempotence across restart,
   purity for replay, failure surfacing, the evaluation budget.
4. **Incidents.** Model, closed state set, timeline, correlation and grouping,
   self-close on recovery, human close with reason.
5. **Unification.** Rewire the webhook routes to raise incidents; assert
   structural identity with detected ones; migrate the existing alert path.
6. **Suppression.** Maintenance windows from the estate, scoped suppression
   rules, the global pause, recorded suppressions.
7. **Dispatch and escalation.** Objective derivation, run linkage, per-team and
   global rate limits, one-run-per-correlation, escalation with cancel on close.
8. **Surfaces.** Gateway endpoints, CLI commands, and the console's incident
   views inside feature 036's frame.

## Risks

- **Detectors as configuration become a second programming language.** Mitigated
  by keeping the condition kinds to four and refusing expressions. Anything more
  expressive is a capability, not a detector.
- **Signal volume outgrows Postgres.** Mitigated by NFR-004's retention bound and
  by measuring at ten thousand resources before the feature is done, rather than
  discovering it in production.
- **Correlation groups too aggressively and hides a second cause.** Mitigated by
  keeping the grouping key on the detector, where it is inspectable, and by
  recording every subject rather than a count.
